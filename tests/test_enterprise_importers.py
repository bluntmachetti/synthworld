"""Adversarial parser and untrusted-bundle safety tests."""

from __future__ import annotations

import csv
import hashlib
import io
import os
import stat
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from yaml.nodes import ScalarNode

from synthworld.enterprise.canonical import canonical_json_bytes
from synthworld.enterprise.models import EnterpriseIdentityAccessImportLimitsV1
from synthworld.enterprise.parsers import (
    CSV_HEADERS,
    _check_ratio,
    _is_json_integer,
    _is_json_number,
    _model_from_document,
    _read_stable_regular_file,
    _read_zip_bundle,
    _RestrictedYamlLoader,
    _validate_zip_member,
    load_enterprise_identity_access_import,
    parse_enterprise_identity_access_csv,
    parse_enterprise_identity_access_json,
    parse_enterprise_identity_access_yaml,
)
from synthworld.enterprise.reference import (
    reference_enterprise_csv_bundle,
    reference_enterprise_identity_access_import,
    reference_enterprise_json,
    reference_enterprise_yaml,
)
from synthworld.enterprise.validation import EnterpriseImportError


def _codes(error: EnterpriseImportError) -> list[str]:
    return [item.code for item in error.diagnostics]


def _replace_csv_cell(
    files: dict[str, str], name: str, row_index: int, column: str, value: str
) -> dict[str, str]:
    changed = dict(files)
    rows = list(csv.reader(io.StringIO(files[name], newline="")))
    column_index = rows[0].index(column)
    rows[row_index][column_index] = value
    destination = io.StringIO(newline="")
    writer = csv.writer(destination, lineterminator="\n")
    writer.writerows(rows)
    changed[name] = destination.getvalue()
    return changed


def _zip_bytes(files: dict[str, bytes], compression: int = zipfile.ZIP_STORED) -> bytes:
    destination = io.BytesIO()
    with zipfile.ZipFile(destination, "w", compression=compression) as archive:
        for name, payload in files.items():
            archive.writestr(name, payload)
    return destination.getvalue()


def test_yaml_json_csv_and_shuffled_csv_are_semantically_identical() -> None:
    expected = reference_enterprise_identity_access_import()
    assert (
        parse_enterprise_identity_access_yaml(reference_enterprise_yaml()) == expected
    )
    assert (
        parse_enterprise_identity_access_json(reference_enterprise_json()) == expected
    )
    files = reference_enterprise_csv_bundle()
    assert parse_enterprise_identity_access_csv(files) == expected

    shuffled = {}
    for name, payload in reversed(tuple(files.items())):
        rows = payload.splitlines()
        shuffled[name] = "\n".join((rows[0], *reversed(rows[1:]))) + "\n"
    assert parse_enterprise_identity_access_csv(shuffled) == expected

    absent_optional = dict(files)
    for name in ("group_role_assignments.csv",):
        absent_optional.pop(name)
    header_only = dict(files)
    header_only["group_role_assignments.csv"] = (
        ",".join(CSV_HEADERS["group_role_assignments.csv"]) + "\n"
    )
    absent = parse_enterprise_identity_access_csv(absent_optional)
    empty = parse_enterprise_identity_access_csv(header_only)
    assert absent == empty

    assert {
        "blueprint": hashlib.sha256(
            canonical_json_bytes(expected.blueprint)
        ).hexdigest(),
        "extension": hashlib.sha256(
            canonical_json_bytes(expected.iam_universe_extension)
        ).hexdigest(),
        "state": hashlib.sha256(
            canonical_json_bytes(expected.directory_rbac_state)
        ).hexdigest(),
    } == {
        "blueprint": "fe6d17a918935fa57fe5389c25e535378e909312e488e97d060ffdb5c434f486",
        "extension": "a5b6e7a2fc6e26f332f24d4aac1c4476113c52243056b7027a95e6d757639097",
        "state": "43a64653b41b5d3e2243232f68a8c82105e635f98b7e7f409a5254005d5d29ee",
    }


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ('{"schema_version":"1.0.0","schema_version":"1.0.0"}', "invalid_json"),
        ('{"value":NaN}', "invalid_json"),
        ("[]", "import_object_required"),
        ("{}", "model_validation"),
    ],
)
def test_json_rejects_duplicate_nonfinite_nonobject_and_invalid_models(
    text: str, code: str
) -> None:
    with pytest.raises(EnterpriseImportError) as raised:
        parse_enterprise_identity_access_json(text)
    assert code in _codes(raised.value)


@pytest.mark.parametrize(
    "text",
    [
        "a: &value 1\nb: *value\n",
        "a: !!python/object:builtins.object {}\n",
        "a: 2026-08-04\n",
        "a: yes\n",
        "a: 01\n",
        "a: .nan\n",
        "a: ~\n",
        "a: 1\na: 2\n",
        "? [a, b]\n: value\n",
    ],
)
def test_yaml_is_restricted_to_duplicate_free_json_compatible_values(text: str) -> None:
    with pytest.raises(EnterpriseImportError) as raised:
        parse_enterprise_identity_access_yaml(text)
    assert _codes(raised.value) == ["invalid_yaml"]


def test_yaml_low_level_guards_and_json_number_grammar_are_total() -> None:
    loader = _RestrictedYamlLoader("")
    try:
        scalar = ScalarNode(tag="tag:yaml.org,2002:str", value="not-a-mapping")
        with pytest.raises(yaml.constructor.ConstructorError, match="mapping_required"):
            loader.construct_mapping(scalar)  # type: ignore[arg-type]
    finally:
        loader.dispose()  # type: ignore[no-untyped-call]
    assert _is_json_integer("0") is True
    assert _is_json_integer("-7") is True
    assert _is_json_number("1.25") is True
    assert _is_json_number("not-a-number") is False


def test_document_conversion_normalizes_non_json_python_values() -> None:
    with pytest.raises(EnterpriseImportError) as raised:
        _model_from_document(
            {"unsupported": object()}, EnterpriseIdentityAccessImportLimitsV1()
        )
    assert _codes(raised.value) == ["model_validation"]


def test_yaml_requires_an_import_object_and_input_bytes_are_bounded() -> None:
    with pytest.raises(EnterpriseImportError) as raised:
        parse_enterprise_identity_access_yaml("null\n")
    assert _codes(raised.value) == ["import_object_required"]
    limits = EnterpriseIdentityAccessImportLimitsV1(max_input_bytes=10)
    with pytest.raises(EnterpriseImportError) as raised:
        parse_enterprise_identity_access_yaml(
            reference_enterprise_yaml(), limits=limits
        )
    assert _codes(raised.value) == ["input_bytes_exceeded"]


def test_csv_rejects_unknown_missing_and_too_many_files_before_rows() -> None:
    files = reference_enterprise_csv_bundle()
    unknown = dict(files)
    unknown["surprise.csv"] = "field\nvalue\n"
    with pytest.raises(EnterpriseImportError) as raised:
        parse_enterprise_identity_access_csv(unknown)
    assert _codes(raised.value) == [
        "csv_file_limit_exceeded",
        "unknown_csv_file",
    ]

    missing = dict(files)
    missing.pop("blueprint.csv")
    with pytest.raises(EnterpriseImportError) as raised:
        parse_enterprise_identity_access_csv(missing)
    assert _codes(raised.value) == ["missing_required_csv_file"]

    limits = EnterpriseIdentityAccessImportLimitsV1(max_csv_files=19)
    with pytest.raises(EnterpriseImportError) as raised:
        parse_enterprise_identity_access_csv(files, limits=limits)
    assert _codes(raised.value) == ["csv_file_limit_exceeded"]


def test_csv_rejects_a_nonnumeric_structural_count() -> None:
    files = _replace_csv_cell(
        reference_enterprise_csv_bundle(), "populations.csv", 1, "count", "many"
    )
    with pytest.raises(EnterpriseImportError) as raised:
        parse_enterprise_identity_access_csv(files)
    assert "positive_integer_required" in _codes(raised.value)


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda files: {**files, "units.csv": ""}, "missing_csv_header"),
        (
            lambda files: {
                **files,
                "units.csv": "key,key,organisation_key,unit_kind,parent_unit_key\n",
            },
            "duplicate_csv_header",
        ),
        (
            lambda files: {**files, "units.csv": "wrong\n"},
            "invalid_csv_header",
        ),
        (
            lambda files: {**files, "units.csv": files["units.csv"] + "too,few\n"},
            "csv_column_count",
        ),
        (
            lambda files: {
                **files,
                "blueprint.csv": CSV_HEADERS["blueprint.csv"][0] + "\n",
            },
            "invalid_csv_header",
        ),
    ],
)
def test_csv_header_and_row_shape_failures_have_stable_codes(
    mutation: object, code: str
) -> None:
    files = mutation(reference_enterprise_csv_bundle())  # type: ignore[operator]
    with pytest.raises(EnterpriseImportError) as raised:
        parse_enterprise_identity_access_csv(files)
    assert code in _codes(raised.value)


def test_csv_parser_reports_malformed_quoting_and_single_row_markers() -> None:
    files = reference_enterprise_csv_bundle()
    malformed = dict(files)
    malformed["units.csv"] = (
        'key,tenant_key,organisation_key,unit_kind,parent_unit_key\n"unterminated\n'
    )
    with pytest.raises(EnterpriseImportError) as raised:
        parse_enterprise_identity_access_csv(malformed)
    assert "malformed_csv" in _codes(raised.value)

    no_marker = dict(files)
    no_marker["universe_extension.csv"] = "schema_version\n"
    with pytest.raises(EnterpriseImportError) as raised:
        parse_enterprise_identity_access_csv(no_marker)
    assert "single_row_required" in _codes(raised.value)

    two_markers = dict(files)
    two_markers["directory_rbac_state.csv"] += "1.0.0\n"
    with pytest.raises(EnterpriseImportError) as raised:
        parse_enterprise_identity_access_csv(two_markers)
    assert "single_row_required" in _codes(raised.value)


def test_csv_byte_row_cell_and_total_limits_are_independent() -> None:
    files = reference_enterprise_csv_bundle()
    with pytest.raises(EnterpriseImportError) as raised:
        parse_enterprise_identity_access_csv(
            files, limits=EnterpriseIdentityAccessImportLimitsV1(max_input_bytes=10)
        )
    assert "input_bytes_exceeded" in _codes(raised.value)

    with pytest.raises(EnterpriseImportError) as raised:
        parse_enterprise_identity_access_csv(
            files, limits=EnterpriseIdentityAccessImportLimitsV1(max_rows_per_file=1)
        )
    assert "file_row_limit_exceeded" in _codes(raised.value)

    with pytest.raises(EnterpriseImportError) as raised:
        parse_enterprise_identity_access_csv(
            files, limits=EnterpriseIdentityAccessImportLimitsV1(max_total_rows=1)
        )
    assert "total_row_limit_exceeded" in _codes(raised.value)

    with pytest.raises(EnterpriseImportError) as raised:
        parse_enterprise_identity_access_csv(
            files, limits=EnterpriseIdentityAccessImportLimitsV1(max_cell_bytes=2)
        )
    assert "cell_bytes_exceeded" in _codes(raised.value)


@pytest.mark.parametrize(
    ("kind", "count", "numerator", "denominator", "codes"),
    [
        ("", "", "", "", ["selector_kind_required"]),
        ("unknown", "", "", "", ["selector_kind_unknown"]),
        ("all", "1", "", "", ["selector_fields_forbidden"]),
        (
            "count",
            "",
            "1",
            "",
            ["selector_fields_forbidden", "selector_count_required"],
        ),
        ("count", "01", "", "", ["selector_count_required"]),
        (
            "fraction",
            "1",
            "",
            "",
            [
                "selector_fields_forbidden",
                "selector_fraction_required",
                "selector_fraction_required",
            ],
        ),
        ("fraction", "", "-1", "2", ["selector_fraction_required"]),
    ],
)
def test_selector_csv_matrix_has_canonical_diagnostic_precedence(
    kind: str,
    count: str,
    numerator: str,
    denominator: str,
    codes: list[str],
) -> None:
    files = reference_enterprise_csv_bundle()
    for column, value in (
        ("selector_kind", kind),
        ("count", count),
        ("numerator", numerator),
        ("denominator", denominator),
    ):
        files = _replace_csv_cell(
            files, "principal_access_atom_rules.csv", 1, column, value
        )
    with pytest.raises(EnterpriseImportError) as raised:
        parse_enterprise_identity_access_csv(files)
    assert _codes(raised.value) == codes


def test_csv_positive_integer_and_fraction_semantics_are_not_repaired() -> None:
    files = _replace_csv_cell(
        reference_enterprise_csv_bundle(),
        "populations.csv",
        1,
        "count",
        "01",
    )
    with pytest.raises(EnterpriseImportError) as raised:
        parse_enterprise_identity_access_csv(files)
    assert _codes(raised.value) == ["positive_integer_required"]

    files = reference_enterprise_csv_bundle()
    files = _replace_csv_cell(
        files, "principal_access_atom_rules.csv", 1, "selector_kind", "fraction"
    )
    files = _replace_csv_cell(
        files, "principal_access_atom_rules.csv", 1, "numerator", "2"
    )
    files = _replace_csv_cell(
        files, "principal_access_atom_rules.csv", 1, "denominator", "4"
    )
    with pytest.raises(EnterpriseImportError) as raised:
        parse_enterprise_identity_access_csv(files)
    assert _codes(raised.value) == ["model_validation"]


def test_csv_orphan_resource_action_and_structural_refs_are_rejected() -> None:
    files = reference_enterprise_csv_bundle()
    files["resource_actions.csv"] += "missing,read\n"
    with pytest.raises(EnterpriseImportError) as raised:
        parse_enterprise_identity_access_csv(files)
    assert _codes(raised.value) == ["unknown_resource_set"]

    files = _replace_csv_cell(
        reference_enterprise_csv_bundle(),
        "organisations.csv",
        1,
        "tenant_key",
        "missing",
    )
    with pytest.raises(EnterpriseImportError) as raised:
        parse_enterprise_identity_access_csv(files)
    assert "unknown_tenant" in _codes(raised.value)


def test_diagnostic_cap_is_explicit_not_silent() -> None:
    files = reference_enterprise_csv_bundle()
    files["units.csv"] = "wrong\n"
    files["roles.csv"] = "wrong\n"
    with pytest.raises(EnterpriseImportError) as raised:
        parse_enterprise_identity_access_csv(
            files, limits=EnterpriseIdentityAccessImportLimitsV1(max_diagnostics=1)
        )
    assert _codes(raised.value) == ["diagnostics_truncated"]
    assert raised.value.diagnostics[0].measured == 2


def test_path_loader_accepts_each_format_directory_and_zip(
    tmp_path: Path,
) -> None:
    expected = reference_enterprise_identity_access_import()
    json_path = tmp_path / "input.json"
    json_path.write_text(reference_enterprise_json(), encoding="utf-8")
    yaml_path = tmp_path / "input.yaml"
    yaml_path.write_text(reference_enterprise_yaml(), encoding="utf-8")
    directory = tmp_path / "csv"
    directory.mkdir()
    for name, payload in reference_enterprise_csv_bundle().items():
        (directory / name).write_text(payload, encoding="utf-8")
    zip_path = tmp_path / "input.zip"
    zip_path.write_bytes(
        _zip_bytes(
            {
                name: payload.encode()
                for name, payload in reference_enterprise_csv_bundle().items()
            },
            compression=zipfile.ZIP_DEFLATED,
        )
    )
    assert load_enterprise_identity_access_import(json_path) == expected
    assert load_enterprise_identity_access_import(yaml_path) == expected
    assert load_enterprise_identity_access_import(directory) == expected
    assert load_enterprise_identity_access_import(zip_path) == expected


def test_path_loader_rejects_unknown_format_missing_input_and_malformed_utf8(
    tmp_path: Path,
) -> None:
    unknown = tmp_path / "input.txt"
    unknown.write_text("{}", encoding="utf-8")
    with pytest.raises(EnterpriseImportError) as raised:
        load_enterprise_identity_access_import(unknown)
    assert _codes(raised.value) == ["unsupported_import_format"]
    with pytest.raises(EnterpriseImportError) as raised:
        load_enterprise_identity_access_import(tmp_path / "missing.json")
    assert _codes(raised.value) == ["input_unreadable"]
    malformed = tmp_path / "bad.json"
    malformed.write_bytes(b"\xff")
    with pytest.raises(EnterpriseImportError) as raised:
        load_enterprise_identity_access_import(malformed)
    assert _codes(raised.value) == ["malformed_utf8"]


def test_directory_reader_rejects_unknown_nested_symlink_and_fifo_entries(
    tmp_path: Path,
) -> None:
    unknown = tmp_path / "unknown"
    unknown.mkdir()
    (unknown / "surprise.csv").write_text("x\n", encoding="utf-8")
    with pytest.raises(EnterpriseImportError) as raised:
        load_enterprise_identity_access_import(unknown)
    assert _codes(raised.value) == ["unknown_csv_file"]

    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "units.csv").mkdir()
    with pytest.raises(EnterpriseImportError) as raised:
        load_enterprise_identity_access_import(nested)
    assert _codes(raised.value) == ["regular_file_required"]

    linked = tmp_path / "linked"
    linked.mkdir()
    target = tmp_path / "target.csv"
    target.write_text("key\n", encoding="utf-8")
    (linked / "units.csv").symlink_to(target)
    with pytest.raises(EnterpriseImportError) as raised:
        load_enterprise_identity_access_import(linked)
    assert _codes(raised.value) == ["regular_file_required"]

    root_link = tmp_path / "root-link"
    root_link.symlink_to(linked, target_is_directory=True)
    with pytest.raises(EnterpriseImportError) as raised:
        load_enterprise_identity_access_import(root_link)
    assert _codes(raised.value) == ["regular_file_required"]

    fifo = tmp_path / "fifo"
    fifo.mkdir()
    os.mkfifo(fifo / "units.csv")
    with pytest.raises(EnterpriseImportError) as raised:
        load_enterprise_identity_access_import(fifo)
    assert _codes(raised.value) == ["regular_file_required"]


def test_directory_and_regular_file_stream_limits_fail_before_parsing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "input.json"
    path.write_text("12345", encoding="utf-8")
    with pytest.raises(EnterpriseImportError) as raised:
        _read_stable_regular_file(path, 1)
    assert _codes(raised.value) == ["input_bytes_exceeded"]

    directory = tmp_path / "bundle"
    directory.mkdir()
    (directory / "units.csv").write_text("key\n", encoding="utf-8")
    limits = EnterpriseIdentityAccessImportLimitsV1(max_decompressed_bytes=1)
    with pytest.raises(EnterpriseImportError) as raised:
        load_enterprise_identity_access_import(directory, limits=limits)
    assert _codes(raised.value) == ["decompressed_bytes_exceeded"]

    complete = tmp_path / "complete"
    complete.mkdir()
    for name, payload in reference_enterprise_csv_bundle().items():
        (complete / name).write_text(payload, encoding="utf-8")
    file_limit = EnterpriseIdentityAccessImportLimitsV1(max_csv_files=19)
    with pytest.raises(EnterpriseImportError) as raised:
        load_enterprise_identity_access_import(complete, limits=file_limit)
    assert _codes(raised.value) == ["csv_file_limit_exceeded"]


def test_regular_file_identity_and_growth_checks_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "input.json"
    path.write_text("{}", encoding="utf-8")
    real_fstat = os.fstat

    def changed_identity(descriptor: int) -> SimpleNamespace:
        value = real_fstat(descriptor)
        return SimpleNamespace(
            st_dev=value.st_dev,
            st_ino=value.st_ino + 1,
            st_size=value.st_size,
            st_mtime_ns=value.st_mtime_ns,
        )

    monkeypatch.setattr(os, "fstat", changed_identity)
    with pytest.raises(EnterpriseImportError) as raised:
        _read_stable_regular_file(path, 100)
    assert _codes(raised.value) == ["file_replaced_during_read"]
    monkeypatch.undo()

    calls = 0

    def changed_after(descriptor: int) -> SimpleNamespace:
        nonlocal calls
        calls += 1
        value = real_fstat(descriptor)
        return SimpleNamespace(
            st_dev=value.st_dev,
            st_ino=value.st_ino,
            st_size=value.st_size + (1 if calls == 2 else 0),
            st_mtime_ns=value.st_mtime_ns,
        )

    monkeypatch.setattr(os, "fstat", changed_after)
    with pytest.raises(EnterpriseImportError) as raised:
        _read_stable_regular_file(path, 100)
    assert _codes(raised.value) == ["file_changed_during_read"]


def test_regular_file_open_errors_are_normalized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(EnterpriseImportError) as raised:
        _read_stable_regular_file(tmp_path / "missing.json", 100)
    assert _codes(raised.value) == ["input_unreadable"]

    path = tmp_path / "input.json"
    path.write_text("{}", encoding="utf-8")

    def fail_open(_path: object, _flags: int) -> int:
        raise OSError("no access")

    monkeypatch.setattr(os, "open", fail_open)
    with pytest.raises(EnterpriseImportError) as raised:
        _read_stable_regular_file(path, 100)
    assert _codes(raised.value) == ["input_unreadable"]


def test_regular_file_reader_has_a_platform_fallback_without_nofollow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "input.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.delattr(os, "O_NOFOLLOW", raising=False)
    assert _read_stable_regular_file(path, 100) == b"{}"


def test_zip_rejects_invalid_duplicate_unsafe_and_special_members(
    tmp_path: Path,
) -> None:
    invalid = tmp_path / "bad.zip"
    invalid.write_bytes(b"not zip")
    with pytest.raises(EnterpriseImportError) as raised:
        load_enterprise_identity_access_import(invalid)
    assert _codes(raised.value) == ["invalid_zip"]

    duplicate_bytes = io.BytesIO()
    with (
        pytest.warns(UserWarning, match="Duplicate name"),
        zipfile.ZipFile(duplicate_bytes, "w") as archive,
    ):
        archive.writestr("units.csv", b"key\n")
        archive.writestr("units.csv", b"key\n")
    duplicate = tmp_path / "duplicate.zip"
    duplicate.write_bytes(duplicate_bytes.getvalue())
    with pytest.raises(EnterpriseImportError) as raised:
        load_enterprise_identity_access_import(duplicate)
    assert _codes(raised.value) == ["duplicate_zip_member"]

    for name in ("nested/units.csv", "/units.csv", "units.csv/", ".."):
        info = zipfile.ZipInfo(name)
        if name.endswith("/"):
            info.external_attr = (stat.S_IFDIR | 0o755) << 16
        with pytest.raises(EnterpriseImportError) as raised:
            _validate_zip_member(info)
        assert _codes(raised.value) == ["unsafe_zip_member"]

    link = zipfile.ZipInfo("units.csv")
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(EnterpriseImportError) as raised:
        _validate_zip_member(link)
    assert _codes(raised.value) == ["zip_special_file_forbidden"]

    encrypted = zipfile.ZipInfo("units.csv")
    encrypted.flag_bits |= 0x1
    with pytest.raises(EnterpriseImportError) as raised:
        _validate_zip_member(encrypted)
    assert _codes(raised.value) == ["encrypted_zip_forbidden"]

    unsupported = zipfile.ZipInfo("units.csv")
    unsupported.compress_type = zipfile.ZIP_BZIP2
    with pytest.raises(EnterpriseImportError) as raised:
        _validate_zip_member(unsupported)
    assert _codes(raised.value) == ["unsupported_zip_compression"]


def test_zip_file_count_size_ratio_utf8_and_member_failures(tmp_path: Path) -> None:
    files = reference_enterprise_csv_bundle()
    archive_path = tmp_path / "many.zip"
    archive_path.write_bytes(
        _zip_bytes({name: value.encode() for name, value in files.items()})
    )
    with pytest.raises(EnterpriseImportError) as raised:
        load_enterprise_identity_access_import(
            archive_path,
            limits=EnterpriseIdentityAccessImportLimitsV1(max_csv_files=19),
        )
    assert _codes(raised.value) == ["csv_file_limit_exceeded"]

    with pytest.raises(EnterpriseImportError) as raised:
        load_enterprise_identity_access_import(
            archive_path,
            limits=EnterpriseIdentityAccessImportLimitsV1(max_decompressed_bytes=1),
        )
    assert _codes(raised.value) == ["decompressed_bytes_exceeded"]

    ratio_path = tmp_path / "ratio.zip"
    ratio_path.write_bytes(
        _zip_bytes({"units.csv": b"0" * 10_000}, compression=zipfile.ZIP_DEFLATED)
    )
    with pytest.raises(EnterpriseImportError) as raised:
        load_enterprise_identity_access_import(ratio_path)
    assert "zip_member_compression_ratio_exceeded" in _codes(raised.value)
    with pytest.raises(EnterpriseImportError):
        _check_ratio(101, 1, 100, "ratio")
    _check_ratio(100, 1, 100, "ratio")

    utf8_path = tmp_path / "utf8.zip"
    utf8_path.write_bytes(_zip_bytes({"blueprint.csv": b"\xff"}))
    with pytest.raises(EnterpriseImportError) as raised:
        load_enterprise_identity_access_import(utf8_path)
    assert _codes(raised.value) == ["malformed_utf8"]


def test_zip_unknown_member_and_declared_ratio_are_checked(tmp_path: Path) -> None:
    unknown = tmp_path / "unknown.zip"
    unknown.write_bytes(_zip_bytes({"other.csv": b"x\n"}))
    with pytest.raises(EnterpriseImportError) as raised:
        load_enterprise_identity_access_import(unknown)
    assert _codes(raised.value) == ["unknown_csv_file"]

    # A highly compressed complete member exercises the declared pre-stream ratio.
    compressed = tmp_path / "compressed.zip"
    compressed.write_bytes(
        _zip_bytes({"units.csv": b"a" * 20_000}, compression=zipfile.ZIP_DEFLATED)
    )
    with pytest.raises(EnterpriseImportError) as raised:
        load_enterprise_identity_access_import(compressed)
    assert _codes(raised.value)[0].startswith("zip_")


class _RuntimeFailingReader(io.BytesIO):
    def read(self, size: int | None = -1) -> bytes:
        raise RuntimeError("member stream failed")


@pytest.mark.parametrize(
    ("reader", "limit", "code"),
    [
        (io.BytesIO(b"ab"), 1, "decompressed_bytes_exceeded"),
        (_RuntimeFailingReader(b"x"), 10, "invalid_zip_member"),
    ],
)
def test_zip_stream_guards_do_not_trust_declared_member_metadata(
    monkeypatch: pytest.MonkeyPatch,
    reader: io.BytesIO,
    limit: int,
    code: str,
) -> None:
    payload = _zip_bytes({"blueprint.csv": b"x"})

    def fake_open(*_args: object, **_kwargs: object) -> io.BytesIO:
        return reader

    monkeypatch.setattr(zipfile.ZipFile, "open", fake_open)
    limits = EnterpriseIdentityAccessImportLimitsV1(max_decompressed_bytes=limit)
    with pytest.raises(EnterpriseImportError) as raised:
        _read_zip_bundle(payload, limits)
    assert _codes(raised.value) == [code]
