"""Bounded YAML, JSON, CSV-directory, and ZIP import parsers."""

from __future__ import annotations

import csv
import io
import json
import math
import os
import stat
import zipfile
from collections.abc import Hashable, Mapping
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import ValidationError
from yaml.events import AliasEvent
from yaml.nodes import MappingNode, Node, ScalarNode

from synthworld.enterprise.models import (
    EnterpriseIdentityAccessImportLimitsV1,
    EnterpriseIdentityAccessImportV1,
    EnterpriseImportDiagnosticV1,
)
from synthworld.enterprise.validation import (
    EnterpriseImportError,
    ensure_valid_enterprise_identity_access,
)

CSV_HEADERS: dict[str, tuple[str, ...]] = {
    "blueprint.csv": ("schema_version", "blueprint_key", "id_namespace_salt"),
    "tenants.csv": ("key",),
    "organisations.csv": ("key", "tenant_key"),
    "units.csv": (
        "key",
        "tenant_key",
        "organisation_key",
        "unit_kind",
        "parent_unit_key",
    ),
    "populations.csv": (
        "key",
        "tenant_key",
        "organisation_key",
        "unit_key",
        "population_kind",
        "count",
    ),
    "groups.csv": ("key", "tenant_key", "organisation_key", "owner_unit_key"),
    "roles.csv": ("key", "tenant_key", "organisation_key", "owner_unit_key"),
    "resource_sets.csv": (
        "key",
        "tenant_key",
        "organisation_key",
        "target_kind",
        "owner_unit_key",
        "instance_count",
    ),
    "resource_actions.csv": ("resource_set_key", "action"),
    "universe_extension.csv": ("schema_version",),
    "account_allocations.csv": (
        "key",
        "population_key",
        "resource_set_key",
        "account_kind",
        "selector_kind",
        "count",
        "numerator",
        "denominator",
        "accounts_per_selected_subject",
    ),
    "directory_rbac_state.csv": ("schema_version",),
    "memberships.csv": (
        "rule_key",
        "population_key",
        "group_key",
        "selector_kind",
        "count",
        "numerator",
        "denominator",
    ),
    "group_nesting.csv": ("child_group_key", "parent_group_key"),
    "group_role_assignments.csv": ("group_key", "role_key"),
    "population_role_assignments.csv": (
        "rule_key",
        "population_key",
        "role_key",
        "selector_kind",
        "count",
        "numerator",
        "denominator",
    ),
    "role_hierarchy.csv": ("senior_role_key", "junior_role_key"),
    "role_grants.csv": ("role_key", "resource_set_key", "action"),
    "principal_access_atom_rules.csv": (
        "rule_key",
        "population_key",
        "resource_set_key",
        "action",
        "selector_kind",
        "count",
        "numerator",
        "denominator",
    ),
    "account_access_atom_rules.csv": (
        "rule_key",
        "account_allocation_key",
        "action",
    ),
}

REQUIRED_CSV_FILES = frozenset(
    {
        "blueprint.csv",
        "tenants.csv",
        "organisations.csv",
        "universe_extension.csv",
        "directory_rbac_state.csv",
        "principal_access_atom_rules.csv",
        "account_access_atom_rules.csv",
    }
)

_JSON_SCALAR_TAGS = {
    "tag:yaml.org,2002:null",
    "tag:yaml.org,2002:bool",
    "tag:yaml.org,2002:int",
    "tag:yaml.org,2002:float",
    "tag:yaml.org,2002:str",
}
_JSON_NODE_TAGS = _JSON_SCALAR_TAGS | {
    "tag:yaml.org,2002:map",
    "tag:yaml.org,2002:seq",
}


class _RestrictedYamlLoader(yaml.SafeLoader):
    def compose_node(self, parent: Node | None, index: int) -> Node:
        if self.check_event(AliasEvent):  # type: ignore[no-untyped-call]
            raise yaml.constructor.ConstructorError(
                None,
                None,
                "yaml_alias_forbidden",
                self.peek_event().start_mark,  # type: ignore[no-untyped-call]
            )
        node = super().compose_node(parent, index)
        node = cast(Node, node)
        if node.tag not in _JSON_NODE_TAGS:
            raise yaml.constructor.ConstructorError(
                None, None, "yaml_non_json_tag_forbidden", node.start_mark
            )
        if isinstance(node, ScalarNode):
            _validate_json_compatible_yaml_scalar(node)
        return node

    def construct_mapping(
        self, node: MappingNode, deep: bool = False
    ) -> dict[Hashable, Any]:
        if not isinstance(node, MappingNode):
            raise yaml.constructor.ConstructorError(
                None, None, "yaml_mapping_required", node.start_mark
            )
        mapping: dict[Hashable, Any] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise yaml.constructor.ConstructorError(
                    None, None, "yaml_string_key_required", key_node.start_mark
                )
            if key in mapping:
                raise yaml.constructor.ConstructorError(
                    None, None, "duplicate_mapping_key", key_node.start_mark
                )
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def _validate_json_compatible_yaml_scalar(node: ScalarNode) -> None:
    value = node.value
    if node.tag == "tag:yaml.org,2002:null" and value != "null":
        raise yaml.constructor.ConstructorError(
            None, None, "yaml_non_json_null_forbidden", node.start_mark
        )
    if node.tag == "tag:yaml.org,2002:bool" and value not in {"true", "false"}:
        raise yaml.constructor.ConstructorError(
            None, None, "yaml_non_json_boolean_forbidden", node.start_mark
        )
    if node.tag == "tag:yaml.org,2002:int" and not _is_json_integer(value):
        raise yaml.constructor.ConstructorError(
            None, None, "yaml_non_json_integer_forbidden", node.start_mark
        )
    if node.tag == "tag:yaml.org,2002:float" and not _is_json_number(value):
        raise yaml.constructor.ConstructorError(
            None, None, "yaml_non_json_number_forbidden", node.start_mark
        )


def _is_json_integer(value: str) -> bool:
    if value == "0":
        return True
    unsigned = value[1:] if value.startswith("-") else value
    return bool(unsigned) and unsigned.isdigit() and not unsigned.startswith("0")


def _is_json_number(value: str) -> bool:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return False
    return (
        isinstance(parsed, int | float)
        and not isinstance(parsed, bool)
        and math.isfinite(parsed)
    )


def parse_enterprise_identity_access_yaml(
    text: str,
    *,
    limits: EnterpriseIdentityAccessImportLimitsV1 | None = None,
) -> EnterpriseIdentityAccessImportV1:
    selected_limits = limits or EnterpriseIdentityAccessImportLimitsV1()
    _check_text_size(text, selected_limits)
    try:
        value = yaml.load(text, Loader=_RestrictedYamlLoader)  # noqa: S506
    except yaml.YAMLError as error:
        raise _single_error(
            "invalid_yaml",
            str(error),
            "Use the restricted JSON-compatible YAML subset.",
        ) from error
    return _model_from_document(value, selected_limits)


def parse_enterprise_identity_access_json(
    text: str,
    *,
    limits: EnterpriseIdentityAccessImportLimitsV1 | None = None,
) -> EnterpriseIdentityAccessImportV1:
    selected_limits = limits or EnterpriseIdentityAccessImportLimitsV1()
    _check_text_size(text, selected_limits)
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_nonfinite_json,
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise _single_error(
            "invalid_json", str(error), "Supply strict JSON with unique keys."
        ) from error
    return _model_from_document(value, selected_limits)


def parse_enterprise_identity_access_csv(
    files: Mapping[str, str],
    *,
    limits: EnterpriseIdentityAccessImportLimitsV1 | None = None,
) -> EnterpriseIdentityAccessImportV1:
    selected_limits = limits or EnterpriseIdentityAccessImportLimitsV1()
    diagnostics: list[EnterpriseImportDiagnosticV1] = []
    names = set(files)
    for name in sorted(names - set(CSV_HEADERS)):
        diagnostics.append(
            _diagnostic(
                "unknown_csv_file",
                "CSV bundle contains a non-allowlisted file",
                file=name,
                hint="Remove the file or use an independently versioned overlay.",
            )
        )
    for name in sorted(REQUIRED_CSV_FILES - names):
        diagnostics.append(
            _diagnostic(
                "missing_required_csv_file",
                "CSV bundle is missing a required file",
                file=name,
                hint="Add the file with its exact v1 header.",
            )
        )
    if len(files) > selected_limits.max_csv_files:
        diagnostics.append(
            _diagnostic(
                "csv_file_limit_exceeded",
                "CSV bundle exceeds the file-count limit",
                measured=len(files),
                allowed=selected_limits.max_csv_files,
            )
        )
    if diagnostics:
        raise EnterpriseImportError(_bounded_diagnostics(diagnostics, selected_limits))

    tables: dict[str, list[dict[str, str]]] = {}
    total_rows = 0
    for name in CSV_HEADERS:
        if name not in files:
            tables[name] = []
            continue
        text = files[name]
        if len(text.encode("utf-8")) > selected_limits.max_input_bytes:
            diagnostics.append(
                _diagnostic(
                    "input_bytes_exceeded",
                    "CSV member exceeds the input byte limit",
                    file=name,
                    measured=len(text.encode("utf-8")),
                    allowed=selected_limits.max_input_bytes,
                )
            )
            tables[name] = []
            continue
        rows = _read_csv_table(name, text, selected_limits, diagnostics)
        tables[name] = rows
        total_rows += len(rows)
    if total_rows > selected_limits.max_total_rows:
        diagnostics.append(
            _diagnostic(
                "total_row_limit_exceeded",
                "CSV bundle exceeds the aggregate row limit",
                measured=total_rows,
                allowed=selected_limits.max_total_rows,
            )
        )
    _require_single_row("blueprint.csv", tables, diagnostics)
    _require_single_row("universe_extension.csv", tables, diagnostics)
    _require_single_row("directory_rbac_state.csv", tables, diagnostics)
    if diagnostics:
        raise EnterpriseImportError(_bounded_diagnostics(diagnostics, selected_limits))

    document = _csv_document(tables, diagnostics)
    if diagnostics:
        raise EnterpriseImportError(_bounded_diagnostics(diagnostics, selected_limits))
    return _model_from_document(document, selected_limits)


def load_enterprise_identity_access_import(
    path: Path,
    *,
    limits: EnterpriseIdentityAccessImportLimitsV1 | None = None,
) -> EnterpriseIdentityAccessImportV1:
    selected_limits = limits or EnterpriseIdentityAccessImportLimitsV1()
    try:
        input_status = path.lstat()
    except OSError as error:
        raise _single_error(
            "input_unreadable",
            str(error),
            "Supply a readable regular file or directory.",
        ) from error
    if stat.S_ISDIR(input_status.st_mode):
        files = _read_directory_bundle(path, selected_limits)
        return _parse_csv_bytes(files, selected_limits)
    payload = _read_stable_regular_file(path, selected_limits.max_input_bytes)
    suffix = path.suffix.lower()
    if suffix == ".zip":
        files = _read_zip_bundle(payload, selected_limits)
        return _parse_csv_bytes(files, selected_limits)
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise _single_error(
            "malformed_utf8", str(error), "Encode the import as UTF-8."
        ) from error
    if suffix in {".yaml", ".yml"}:
        return parse_enterprise_identity_access_yaml(text, limits=selected_limits)
    if suffix == ".json":
        return parse_enterprise_identity_access_json(text, limits=selected_limits)
    raise _single_error(
        "unsupported_import_format",
        "input must be YAML, JSON, a CSV directory, or a ZIP CSV bundle",
        "Use a supported v1 format.",
    )


def _model_from_document(
    value: object, limits: EnterpriseIdentityAccessImportLimitsV1
) -> EnterpriseIdentityAccessImportV1:
    if not isinstance(value, dict):
        raise _single_error(
            "import_object_required",
            "enterprise import must be a mapping object",
            "Wrap the independently versioned components in one import object.",
        )
    try:
        payload = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        model = EnterpriseIdentityAccessImportV1.model_validate_json(payload)
    except (TypeError, ValueError, ValidationError) as error:
        raise _validation_error(error, limits) from error
    ensure_valid_enterprise_identity_access(model, limits=limits)
    return model


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate_mapping_key:{key}")
        result[key] = value
    return result


def _reject_nonfinite_json(value: str) -> None:
    raise ValueError(f"nonfinite_number_forbidden:{value}")


def _check_text_size(text: str, limits: EnterpriseIdentityAccessImportLimitsV1) -> None:
    measured = len(text.encode("utf-8"))
    if measured > limits.max_input_bytes:
        raise EnterpriseImportError(
            (
                _diagnostic(
                    "input_bytes_exceeded",
                    "text import exceeds the byte limit",
                    measured=measured,
                    allowed=limits.max_input_bytes,
                ),
            )
        )


def _read_csv_table(
    name: str,
    text: str,
    limits: EnterpriseIdentityAccessImportLimitsV1,
    diagnostics: list[EnterpriseImportDiagnosticV1],
) -> list[dict[str, str]]:
    try:
        rows = list(
            csv.reader(io.StringIO(text, newline=""), dialect="excel", strict=True)
        )
    except csv.Error as error:
        diagnostics.append(
            _diagnostic(
                "malformed_csv",
                str(error),
                file=name,
                hint="Use RFC 4180-style comma-separated rows.",
            )
        )
        return []
    if not rows:
        diagnostics.append(
            _diagnostic(
                "missing_csv_header",
                "CSV file is empty",
                file=name,
                hint="Add the exact v1 header.",
            )
        )
        return []
    header = tuple(rows[0])
    if len(header) != len(set(header)):
        diagnostics.append(
            _diagnostic(
                "duplicate_csv_header",
                "CSV header contains duplicate columns",
                file=name,
                row=1,
            )
        )
        return []
    if header != CSV_HEADERS[name]:
        diagnostics.append(
            _diagnostic(
                "invalid_csv_header",
                "CSV header differs from the exact v1 contract",
                file=name,
                row=1,
                hint=f"Use: {','.join(CSV_HEADERS[name])}",
            )
        )
        return []
    data_rows = rows[1:]
    if len(data_rows) > limits.max_rows_per_file:
        diagnostics.append(
            _diagnostic(
                "file_row_limit_exceeded",
                "CSV file exceeds its row limit",
                file=name,
                measured=len(data_rows),
                allowed=limits.max_rows_per_file,
            )
        )
        return []
    result: list[dict[str, str]] = []
    for row_number, row in enumerate(data_rows, start=2):
        if len(row) != len(header):
            diagnostics.append(
                _diagnostic(
                    "csv_column_count",
                    "CSV row has the wrong number of cells",
                    file=name,
                    row=row_number,
                )
            )
            continue
        oversized = next(
            (
                column
                for column, value in zip(header, row, strict=True)
                if len(value.encode("utf-8")) > limits.max_cell_bytes
            ),
            None,
        )
        if oversized is not None:
            diagnostics.append(
                _diagnostic(
                    "cell_bytes_exceeded",
                    "CSV cell exceeds its byte limit",
                    file=name,
                    row=row_number,
                    column=oversized,
                )
            )
            continue
        result.append(dict(zip(header, row, strict=True)))
    return result


def _require_single_row(
    name: str,
    tables: dict[str, list[dict[str, str]]],
    diagnostics: list[EnterpriseImportDiagnosticV1],
) -> None:
    if len(tables[name]) != 1:
        diagnostics.append(
            _diagnostic(
                "single_row_required",
                "CSV component marker requires exactly one data row",
                file=name,
                measured=len(tables[name]),
                allowed=1,
            )
        )


def _csv_document(
    tables: dict[str, list[dict[str, str]]],
    diagnostics: list[EnterpriseImportDiagnosticV1],
) -> dict[str, object]:
    blueprint_row = tables["blueprint.csv"][0]
    extension_row = tables["universe_extension.csv"][0]
    state_row = tables["directory_rbac_state.csv"][0]
    actions: dict[str, list[str]] = {}
    for row in tables["resource_actions.csv"]:
        actions.setdefault(row["resource_set_key"], []).append(row["action"])
    resource_keys = {row["key"] for row in tables["resource_sets.csv"]}
    for unknown_key in sorted(set(actions) - resource_keys):
        diagnostics.append(
            _diagnostic(
                "unknown_resource_set",
                "resource action references an unknown resource set",
                file="resource_actions.csv",
                logical_key=unknown_key,
            )
        )

    resource_sets = []
    for row_number, row in enumerate(tables["resource_sets.csv"], start=2):
        resource_sets.append(
            {
                "key": row["key"],
                "tenant_key": row["tenant_key"],
                "organisation_key": row["organisation_key"],
                "target_kind": row["target_kind"],
                "owner_unit_key": _optional(row["owner_unit_key"]),
                "instance_count": _integer(
                    row["instance_count"],
                    file="resource_sets.csv",
                    row=row_number,
                    column="instance_count",
                    diagnostics=diagnostics,
                ),
                "actions": actions.get(row["key"], []),
            }
        )

    return {
        "schema_version": "1.0.0",
        "blueprint": {
            "schema_version": blueprint_row["schema_version"],
            "blueprint_key": blueprint_row["blueprint_key"],
            "id_namespace_salt": blueprint_row["id_namespace_salt"],
            "tenants": tables["tenants.csv"],
            "organisations": tables["organisations.csv"],
            "units": [
                {
                    **row,
                    "parent_unit_key": _optional(row["parent_unit_key"]),
                }
                for row in tables["units.csv"]
            ],
            "populations": [
                {
                    **row,
                    "count": _integer(
                        row["count"],
                        file="populations.csv",
                        row=index,
                        column="count",
                        diagnostics=diagnostics,
                    ),
                }
                for index, row in enumerate(tables["populations.csv"], start=2)
            ],
            "groups": [
                {**row, "owner_unit_key": _optional(row["owner_unit_key"])}
                for row in tables["groups.csv"]
            ],
            "roles": [
                {**row, "owner_unit_key": _optional(row["owner_unit_key"])}
                for row in tables["roles.csv"]
            ],
            "resource_sets": resource_sets,
            "principal_access_atom_rules": [
                {
                    "rule_key": row["rule_key"],
                    "population_key": row["population_key"],
                    "resource_set_key": row["resource_set_key"],
                    "action": row["action"],
                    "selector": _selector(
                        row,
                        file="principal_access_atom_rules.csv",
                        row_number=index,
                        diagnostics=diagnostics,
                    ),
                }
                for index, row in enumerate(
                    tables["principal_access_atom_rules.csv"], start=2
                )
            ],
        },
        "iam_universe_extension": {
            "schema_version": extension_row["schema_version"],
            "account_allocations": [
                {
                    "key": row["key"],
                    "population_key": row["population_key"],
                    "resource_set_key": row["resource_set_key"],
                    "account_kind": row["account_kind"],
                    "selector": _selector(
                        row,
                        file="account_allocations.csv",
                        row_number=index,
                        diagnostics=diagnostics,
                    ),
                    "accounts_per_selected_subject": _integer(
                        row["accounts_per_selected_subject"],
                        file="account_allocations.csv",
                        row=index,
                        column="accounts_per_selected_subject",
                        diagnostics=diagnostics,
                    ),
                }
                for index, row in enumerate(tables["account_allocations.csv"], start=2)
            ],
            "account_access_atom_rules": tables["account_access_atom_rules.csv"],
        },
        "directory_rbac_state": {
            "schema_version": state_row["schema_version"],
            "account_observations": [],
            "memberships": [
                {
                    "rule_key": row["rule_key"],
                    "population_key": row["population_key"],
                    "group_key": row["group_key"],
                    "selector": _selector(
                        row,
                        file="memberships.csv",
                        row_number=index,
                        diagnostics=diagnostics,
                    ),
                }
                for index, row in enumerate(tables["memberships.csv"], start=2)
            ],
            "group_nesting": tables["group_nesting.csv"],
            "group_role_assignments": tables["group_role_assignments.csv"],
            "population_role_assignments": [
                {
                    "rule_key": row["rule_key"],
                    "population_key": row["population_key"],
                    "role_key": row["role_key"],
                    "selector": _selector(
                        row,
                        file="population_role_assignments.csv",
                        row_number=index,
                        diagnostics=diagnostics,
                    ),
                }
                for index, row in enumerate(
                    tables["population_role_assignments.csv"], start=2
                )
            ],
            "role_hierarchy": tables["role_hierarchy.csv"],
            "role_grants": tables["role_grants.csv"],
            "direct_entitlements": [],
        },
    }


def _selector(
    row: dict[str, str],
    *,
    file: str,
    row_number: int,
    diagnostics: list[EnterpriseImportDiagnosticV1],
) -> dict[str, object]:
    kind = row["selector_kind"]
    count = row["count"]
    numerator = row["numerator"]
    denominator = row["denominator"]
    logical_key = row.get("rule_key") or row.get("key")
    if not kind:
        diagnostics.append(
            _diagnostic(
                "selector_kind_required",
                "selector kind is required",
                file=file,
                row=row_number,
                column="selector_kind",
                logical_key=logical_key,
            )
        )
        return {"kind": "all"}
    if kind not in {"all", "count", "fraction"}:
        diagnostics.append(
            _diagnostic(
                "selector_kind_unknown",
                "selector kind is outside the closed v1 vocabulary",
                file=file,
                row=row_number,
                column="selector_kind",
                logical_key=logical_key,
            )
        )
        return {"kind": "all"}
    forbidden = (
        (kind == "all" and any((count, numerator, denominator)))
        or (kind == "count" and any((numerator, denominator)))
        or (kind == "fraction" and bool(count))
    )
    if forbidden:
        diagnostics.append(
            _diagnostic(
                "selector_fields_forbidden",
                "selector contains fields forbidden for its kind",
                file=file,
                row=row_number,
                logical_key=logical_key,
            )
        )
    if kind == "all":
        return {"kind": "all"}
    if kind == "count":
        parsed = _positive_integer_or_diagnostic(
            count,
            code="selector_count_required",
            file=file,
            row=row_number,
            column="count",
            logical_key=logical_key,
            diagnostics=diagnostics,
        )
        return {"kind": "count", "count": parsed}
    parsed_numerator = _positive_integer_or_diagnostic(
        numerator,
        code="selector_fraction_required",
        file=file,
        row=row_number,
        column="numerator",
        logical_key=logical_key,
        diagnostics=diagnostics,
    )
    parsed_denominator = _positive_integer_or_diagnostic(
        denominator,
        code="selector_fraction_required",
        file=file,
        row=row_number,
        column="denominator",
        logical_key=logical_key,
        diagnostics=diagnostics,
    )
    return {
        "kind": "fraction",
        "numerator": parsed_numerator,
        "denominator": parsed_denominator,
    }


def _positive_integer_or_diagnostic(
    value: str,
    *,
    code: str,
    file: str,
    row: int,
    column: str,
    logical_key: str | None,
    diagnostics: list[EnterpriseImportDiagnosticV1],
) -> int:
    try:
        parsed = int(value)
    except ValueError:
        parsed = 0
    if parsed <= 0 or str(parsed) != value:
        diagnostics.append(
            _diagnostic(
                code,
                "selector field must be a canonical positive integer",
                file=file,
                row=row,
                column=column,
                logical_key=logical_key,
            )
        )
    return parsed


def _integer(
    value: str,
    *,
    file: str,
    row: int,
    column: str,
    diagnostics: list[EnterpriseImportDiagnosticV1],
) -> int:
    try:
        parsed = int(value)
    except ValueError:
        parsed = 0
    if parsed <= 0 or str(parsed) != value:
        diagnostics.append(
            _diagnostic(
                "positive_integer_required",
                "field must be a canonical positive integer",
                file=file,
                row=row,
                column=column,
            )
        )
    return parsed


def _optional(value: str) -> str | None:
    return value or None


def _read_directory_bundle(
    root: Path, limits: EnterpriseIdentityAccessImportLimitsV1
) -> dict[str, bytes]:
    entries = sorted(root.iterdir(), key=lambda item: item.name)
    if len(entries) > limits.max_csv_files:
        raise EnterpriseImportError(
            (
                _diagnostic(
                    "csv_file_limit_exceeded",
                    "directory bundle exceeds the file-count limit",
                    measured=len(entries),
                    allowed=limits.max_csv_files,
                ),
            )
        )
    files: dict[str, bytes] = {}
    total = 0
    for entry in entries:
        if entry.name not in CSV_HEADERS:
            raise _single_error(
                "unknown_csv_file",
                f"directory contains unexpected entry {entry.name!r}",
                "Keep only exact immediate v1 CSV files.",
            )
        payload = _read_stable_regular_file(entry, limits.max_input_bytes)
        total += len(payload)
        if total > limits.max_decompressed_bytes:
            raise EnterpriseImportError(
                (
                    _diagnostic(
                        "decompressed_bytes_exceeded",
                        "directory bundle exceeds its aggregate byte limit",
                        measured=total,
                        allowed=limits.max_decompressed_bytes,
                    ),
                )
            )
        files[entry.name] = payload
    return files


def _parse_csv_bytes(
    files: dict[str, bytes], limits: EnterpriseIdentityAccessImportLimitsV1
) -> EnterpriseIdentityAccessImportV1:
    try:
        decoded = {name: payload.decode("utf-8") for name, payload in files.items()}
    except UnicodeDecodeError as error:
        raise _single_error(
            "malformed_utf8", str(error), "Encode every CSV member as UTF-8."
        ) from error
    return parse_enterprise_identity_access_csv(decoded, limits=limits)


def _read_stable_regular_file(path: Path, byte_limit: int) -> bytes:
    try:
        before = path.lstat()
    except OSError as error:
        raise _single_error(
            "input_unreadable", str(error), "Supply a readable regular file."
        ) from error
    if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode):
        raise _single_error(
            "regular_file_required",
            f"{path.name!r} is not a stable regular file",
            "Replace links and special files with regular files.",
        )
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb", closefd=True) as source:
            opened = os.fstat(source.fileno())
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise _single_error(
                    "file_replaced_during_read",
                    "file identity changed while opening",
                    "Retry with an immutable regular-file bundle.",
                )
            chunks: list[bytes] = []
            measured = 0
            while chunk := source.read(64 * 1024):
                measured += len(chunk)
                if measured > byte_limit:
                    raise EnterpriseImportError(
                        (
                            _diagnostic(
                                "input_bytes_exceeded",
                                "file exceeds its byte limit",
                                measured=measured,
                                allowed=byte_limit,
                            ),
                        )
                    )
                chunks.append(chunk)
            after = os.fstat(source.fileno())
    except EnterpriseImportError:
        raise
    except OSError as error:
        raise _single_error(
            "input_unreadable", str(error), "Supply a stable regular file."
        ) from error
    if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) or measured != after.st_size:
        raise _single_error(
            "file_changed_during_read",
            "file was replaced or changed while reading",
            "Retry with an immutable regular-file bundle.",
        )
    return b"".join(chunks)


def _read_zip_bundle(
    payload: bytes, limits: EnterpriseIdentityAccessImportLimitsV1
) -> dict[str, bytes]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as error:
        raise _single_error(
            "invalid_zip", str(error), "Supply a valid ZIP archive."
        ) from error
    with archive:
        members = archive.infolist()
        names = [item.filename for item in members]
        if len(names) != len(set(names)):
            raise _single_error(
                "duplicate_zip_member",
                "ZIP contains duplicate member names",
                "Keep exactly one member per v1 CSV filename.",
            )
        if len(members) > limits.max_csv_files:
            raise EnterpriseImportError(
                (
                    _diagnostic(
                        "csv_file_limit_exceeded",
                        "ZIP exceeds the member-count limit",
                        measured=len(members),
                        allowed=limits.max_csv_files,
                    ),
                )
            )
        declared_uncompressed = 0
        declared_compressed = 0
        for member in members:
            _validate_zip_member(member)
            if member.filename not in CSV_HEADERS:
                raise _single_error(
                    "unknown_csv_file",
                    f"ZIP contains unexpected member {member.filename!r}",
                    "Keep only exact immediate v1 CSV files.",
                )
            declared_uncompressed += member.file_size
            declared_compressed += member.compress_size
            _check_ratio(
                member.file_size,
                member.compress_size,
                limits.max_compression_ratio,
                "zip_member_compression_ratio_exceeded",
            )
        if declared_uncompressed > limits.max_decompressed_bytes:
            raise EnterpriseImportError(
                (
                    _diagnostic(
                        "decompressed_bytes_exceeded",
                        "ZIP declared size exceeds the decompressed-byte limit",
                        measured=declared_uncompressed,
                        allowed=limits.max_decompressed_bytes,
                    ),
                )
            )
        _check_ratio(
            declared_uncompressed,
            declared_compressed,
            limits.max_compression_ratio,
            "zip_aggregate_compression_ratio_exceeded",
        )
        result: dict[str, bytes] = {}
        actual_total = 0
        for member in sorted(members, key=lambda item: item.filename):
            chunks: list[bytes] = []
            actual = 0
            try:
                with archive.open(member, "r") as source:
                    while chunk := source.read(64 * 1024):
                        actual += len(chunk)
                        actual_total += len(chunk)
                        if actual_total > limits.max_decompressed_bytes:
                            raise EnterpriseImportError(
                                (
                                    _diagnostic(
                                        "decompressed_bytes_exceeded",
                                        "ZIP exceeds the streamed byte limit",
                                        measured=actual_total,
                                        allowed=limits.max_decompressed_bytes,
                                    ),
                                )
                            )
                        _check_ratio(
                            actual,
                            member.compress_size,
                            limits.max_compression_ratio,
                            "zip_member_compression_ratio_exceeded",
                        )
                        chunks.append(chunk)
            except (RuntimeError, zipfile.BadZipFile) as error:
                raise _single_error(
                    "invalid_zip_member",
                    str(error),
                    "Use unencrypted stored or deflated regular members.",
                ) from error
            result[member.filename] = b"".join(chunks)
        _check_ratio(
            actual_total,
            declared_compressed,
            limits.max_compression_ratio,
            "zip_aggregate_compression_ratio_exceeded",
        )
        return result


def _validate_zip_member(member: zipfile.ZipInfo) -> None:
    name = member.filename
    mode = (member.external_attr >> 16) & 0xFFFF
    file_type = stat.S_IFMT(mode)
    if (
        member.is_dir()
        or "/" in name
        or "\\" in name
        or name in {".", ".."}
        or Path(name).is_absolute()
    ):
        raise _single_error(
            "unsafe_zip_member",
            f"ZIP member {name!r} is nested, absolute, or a directory",
            "Use exact immediate v1 filenames.",
        )
    if file_type not in {0, stat.S_IFREG}:
        raise _single_error(
            "zip_special_file_forbidden",
            f"ZIP member {name!r} is not a regular file",
            "Replace links and special entries with regular files.",
        )
    if member.flag_bits & 0x1:
        raise _single_error(
            "encrypted_zip_forbidden",
            f"ZIP member {name!r} is encrypted",
            "Use an unencrypted bundle.",
        )
    if member.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
        raise _single_error(
            "unsupported_zip_compression",
            f"ZIP member {name!r} uses unsupported compression",
            "Use stored or deflated members.",
        )


def _check_ratio(actual: int, compressed: int, allowed: int, code: str) -> None:
    if actual > allowed * max(1, compressed):
        raise EnterpriseImportError(
            (
                _diagnostic(
                    code,
                    "ZIP compression ratio exceeds the safety limit",
                    measured=actual,
                    allowed=allowed * max(1, compressed),
                ),
            )
        )


def _validation_error(
    error: Exception, limits: EnterpriseIdentityAccessImportLimitsV1
) -> EnterpriseImportError:
    if isinstance(error, ValidationError):
        diagnostics = [
            _diagnostic(
                "model_validation",
                item["msg"],
                column=".".join(str(part) for part in item["loc"]),
                hint="Match the independently versioned v1 component schema.",
            )
            for item in error.errors(include_url=False)
        ]
    else:
        diagnostics = [
            _diagnostic(
                "model_validation",
                str(error),
                hint="Match the independently versioned v1 component schema.",
            )
        ]
    return EnterpriseImportError(_bounded_diagnostics(diagnostics, limits))


def _bounded_diagnostics(
    diagnostics: list[EnterpriseImportDiagnosticV1],
    limits: EnterpriseIdentityAccessImportLimitsV1,
) -> tuple[EnterpriseImportDiagnosticV1, ...]:
    ordered = sorted(
        diagnostics,
        key=lambda item: (
            item.file or "",
            item.row or 0,
            _diagnostic_priority(item.code),
            item.code,
            item.column or "",
            item.logical_key or "",
            item.message,
        ),
    )
    if len(ordered) <= limits.max_diagnostics:
        return tuple(ordered)
    return (
        *ordered[: limits.max_diagnostics - 1],
        _diagnostic(
            "diagnostics_truncated",
            "additional diagnostics were suppressed",
            measured=len(ordered),
            allowed=limits.max_diagnostics,
            hint="Fix the reported errors and validate again.",
        ),
    )


def _diagnostic_priority(code: str) -> int:
    return {
        "selector_kind_required": 0,
        "selector_kind_unknown": 0,
        "selector_fields_forbidden": 1,
        "selector_count_required": 2,
        "selector_fraction_required": 2,
    }.get(code, 3)


def _diagnostic(
    code: str,
    message: str,
    *,
    file: str | None = None,
    row: int | None = None,
    column: str | None = None,
    logical_key: str | None = None,
    hint: str = "Correct the declared identity/access structure.",
    measured: int | None = None,
    allowed: int | None = None,
) -> EnterpriseImportDiagnosticV1:
    return EnterpriseImportDiagnosticV1(
        code=code,
        message=message,
        file=file,
        row=row,
        column=column,
        logical_key=logical_key,
        remediation_hint=hint,
        measured=measured,
        allowed=allowed,
    )


def _single_error(code: str, message: str, hint: str) -> EnterpriseImportError:
    return EnterpriseImportError((_diagnostic(code, message, hint=hint),))


__all__ = [
    "CSV_HEADERS",
    "REQUIRED_CSV_FILES",
    "load_enterprise_identity_access_import",
    "parse_enterprise_identity_access_csv",
    "parse_enterprise_identity_access_json",
    "parse_enterprise_identity_access_yaml",
]
