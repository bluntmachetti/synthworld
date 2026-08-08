#!/usr/bin/env python3
"""Audit static-site publication boundaries.

This is a sibling control to the existing public-consumer boundary and secret
scan.  It protects the static-site publication channel and does not replace
either of those controls.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast

SCHEMA_VERSION = "1.0.0"
ALL_SENSITIVITIES = frozenset(
    {
        "public_input",
        "public_reference_truth",
        "private_held_out_truth",
        "operator_private",
        "internal_build_only",
    }
)
EXPECTED_ALLOWED_SENSITIVITIES = (
    "public_input",
    "public_reference_truth",
)
EXPECTED_FORBIDDEN_SENSITIVITIES = (
    "private_held_out_truth",
    "operator_private",
    "internal_build_only",
)
POLICY_KEYS = frozenset(
    {
        "schema_version",
        "sources",
        "allowed_sensitivities",
        "forbidden_sensitivities",
        "allowed_machine_readable_outputs",
        "forbidden_output_names",
        "forbidden_path_parts",
        "forbidden_suffixes",
    }
)
SOURCE_KEYS = frozenset(
    {
        "path",
        "source_type",
        "generator",
        "requires_sensitivity",
        "permitted_sensitivities",
    }
)
PROVENANCE_KEYS = frozenset({"schema_version", "outputs"})
OUTPUT_KEYS = frozenset({"path", "sources", "sensitivity"})

LOCAL_PATH_PATTERN = re.compile(
    r"(?:/home/[^/\s:]+(?:/|\b)|/Users/[^/\s:]+(?:/|\b)|"
    r"/(?:tmp|root|var/folders|private/var|run/user)(?:/|\b)|"
    r"file:///(?:home/[^/\s:]+|Users/[^/\s:]+|tmp|root|var/folders|private/var|run/user)(?:/|\b)|"
    r"[A-Za-z]:[\\/](?:Users[\\/][^\\/\s:]+|(?:Windows[\\/])?(?:Temp|tmp))(?:[\\/]|\b)|"
    r"\\\\[?.]\\[A-Za-z]:[\\/]|"
    r"\\\\[A-Za-z0-9_.-]+\\[A-Za-z0-9$_.-]+(?:[\\/]|\b))"
)
OMC_PLAN_PATTERN = re.compile(r"\.omc[\\/]plans(?:[\\/]|\b)")
PRIVATE_KEY_PATTERN = re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")
API_KEY_ASSIGNMENT_PATTERN = re.compile(
    r"(?im)(?<![A-Za-z0-9_])(?:api[_-]?key|apikey|token|secret|"
    r"[a-z][a-z0-9_]*?(?:api[_-]?key|token|secret))\s*[:=]\s*"
    r"(?:['\"])?([^\s'\"`]+)"
)
PLACEHOLDER_SECRET_PATTERN = re.compile(
    r"^(?:\$\{[^}]+\}|\$[A-Za-z_][A-Za-z0-9_]*|"
    r"(?:env|environment)[:/][A-Za-z_][A-Za-z0-9_]*|<[^>]+>|"
    r"redacted|none|null|changeme|todo|xxx+|your_api_key|your-token|replace-me)$",
    re.IGNORECASE,
)
MACHINE_READABLE_SUFFIXES = frozenset(
    {
        ".json",
        ".jsonl",
        ".ndjson",
        ".jsonld",
        ".yaml",
        ".yml",
        ".xml",
        ".csv",
        ".tsv",
        ".parquet",
    }
)
SAFE_BINARY_SUFFIXES = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".avif",
    }
)
DEFAULT_POLICY_PATH = (
    Path(__file__).resolve().parents[1] / "docs" / "publication-boundary.json"
)


class AuditSchemaError(ValueError):
    """Raised when an audit input does not satisfy its strict schema."""


@dataclass(frozen=True)
class Source:
    path: str
    source_type: str
    generator: str | None
    requires_sensitivity: bool
    permitted_sensitivities: frozenset[str]


@dataclass(frozen=True)
class Policy:
    sources: dict[str, Source]
    allowed_sensitivities: frozenset[str]
    forbidden_sensitivities: frozenset[str]
    allowed_machine_readable_outputs: frozenset[str]
    forbidden_output_names: frozenset[str]
    forbidden_path_parts: frozenset[str]
    forbidden_suffixes: frozenset[str]


@dataclass(frozen=True)
class ProvenanceOutput:
    path: str
    sources: tuple[str, ...]
    sensitivity: str | None


def _schema_error(message: str) -> AuditSchemaError:
    return AuditSchemaError(message)


def _load_json(path: Path, label: str) -> object:
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as error:
        raise _schema_error(f"{label} does not exist") from error
    except OSError as error:
        raise _schema_error(f"{label} cannot be read") from error
    except json.JSONDecodeError as error:
        raise _schema_error(f"{label} is not valid JSON") from error


def _require_mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _schema_error(f"{label} must be an object")
    return cast(dict[str, object], value)


def _require_exact_keys(
    value: dict[str, object], expected: frozenset[str], label: str
) -> None:
    if frozenset(value) != expected:
        raise _schema_error(f"{label} has unexpected or missing fields")


def _require_string(value: object, label: str) -> str:
    if type(value) is not str or not value:
        raise _schema_error(f"{label} must be a non-empty string")
    return value


def _require_boolean(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise _schema_error(f"{label} must be a boolean")
    return value


def _normalized_relative_path(value: object, label: str) -> str:
    path = _require_string(value, label)
    if "\\" in path:
        raise _schema_error(f"{label} must use POSIX separators")
    candidate = PurePosixPath(path)
    if candidate.is_absolute() or path in {".", ".."} or ".." in candidate.parts:
        raise _schema_error(f"{label} must be a normalized relative path")
    normalized = candidate.as_posix()
    if normalized != path or path.startswith("./") or "//" in path:
        raise _schema_error(f"{label} must be a normalized relative path")
    return path


def _string_list(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise _schema_error(f"{label} must be an array")
    values = tuple(_require_string(item, f"{label} entry") for item in value)
    if len(values) != len(set(values)):
        raise _schema_error(f"{label} must not contain duplicates")
    return values


def _load_policy(path: Path) -> Policy:
    raw = _require_mapping(_load_json(path, "policy"), "policy")
    _require_exact_keys(raw, POLICY_KEYS, "policy")
    if raw["schema_version"] != SCHEMA_VERSION:
        raise _schema_error("policy schema_version must be 1.0.0")

    raw_sources = raw["sources"]
    if not isinstance(raw_sources, list) or not raw_sources:
        raise _schema_error("policy sources must be a non-empty array")
    sources: dict[str, Source] = {}
    for index, raw_source in enumerate(raw_sources):
        label = f"policy sources[{index}]"
        source = _require_mapping(raw_source, label)
        _require_exact_keys(source, SOURCE_KEYS, label)
        source_path = _normalized_relative_path(source["path"], f"{label}.path")
        if source_path in sources:
            raise _schema_error("policy sources must not contain duplicate paths")
        generator = source["generator"]
        if generator is not None:
            generator = _require_string(generator, f"{label}.generator")
        permitted_sensitivities = _string_list(
            source["permitted_sensitivities"], f"{label}.permitted_sensitivities"
        )
        requires_sensitivity = _require_boolean(
            source["requires_sensitivity"], f"{label}.requires_sensitivity"
        )
        if any(
            value not in EXPECTED_ALLOWED_SENSITIVITIES
            for value in permitted_sensitivities
        ):
            raise _schema_error(
                f"{label}.permitted_sensitivities must contain only allowed "
                "public classes"
            )
        if requires_sensitivity and not permitted_sensitivities:
            raise _schema_error(
                f"{label}.permitted_sensitivities must not be empty when "
                "sensitivity is required"
            )
        if not requires_sensitivity and permitted_sensitivities:
            raise _schema_error(
                f"{label}.permitted_sensitivities must be empty when "
                "sensitivity is not required"
            )
        sources[source_path] = Source(
            path=source_path,
            source_type=_require_string(source["source_type"], f"{label}.source_type"),
            generator=generator,
            requires_sensitivity=requires_sensitivity,
            permitted_sensitivities=frozenset(permitted_sensitivities),
        )

    allowed = _string_list(raw["allowed_sensitivities"], "policy allowed_sensitivities")
    forbidden = _string_list(
        raw["forbidden_sensitivities"], "policy forbidden_sensitivities"
    )
    if allowed != EXPECTED_ALLOWED_SENSITIVITIES:
        raise _schema_error(
            "policy allowed_sensitivities must list the two public classes"
        )
    if forbidden != EXPECTED_FORBIDDEN_SENSITIVITIES:
        raise _schema_error(
            "policy forbidden_sensitivities must list the three private classes"
        )

    output_names = _string_list(
        raw["forbidden_output_names"], "policy forbidden_output_names"
    )
    path_parts = _string_list(
        raw["forbidden_path_parts"], "policy forbidden_path_parts"
    )
    suffixes = _string_list(raw["forbidden_suffixes"], "policy forbidden_suffixes")
    if any("/" in value or "\\" in value for value in output_names + path_parts):
        raise _schema_error(
            "policy output names and path parts must be single path components"
        )
    if any(not value.startswith(".") for value in suffixes):
        raise _schema_error("policy forbidden_suffixes entries must begin with a dot")
    normalized_output_names = tuple(value.casefold() for value in output_names)
    normalized_path_parts = tuple(value.casefold() for value in path_parts)
    normalized_suffixes = tuple(value.casefold() for value in suffixes)
    if len(normalized_output_names) != len(set(normalized_output_names)):
        raise _schema_error("policy forbidden_output_names must not contain duplicates")
    if len(normalized_path_parts) != len(set(normalized_path_parts)):
        raise _schema_error("policy forbidden_path_parts must not contain duplicates")
    if len(normalized_suffixes) != len(set(normalized_suffixes)):
        raise _schema_error("policy forbidden_suffixes must not contain duplicates")
    for source_path in sources:
        if any(
            part.casefold() in normalized_path_parts
            for part in PurePosixPath(source_path).parts
        ):
            raise _schema_error("policy source path contains a forbidden path part")

    machine_outputs = tuple(
        _normalized_relative_path(
            value, "policy allowed_machine_readable_outputs entry"
        )
        for value in _string_list(
            raw["allowed_machine_readable_outputs"],
            "policy allowed_machine_readable_outputs",
        )
    )
    if len(machine_outputs) != len(set(machine_outputs)):
        raise _schema_error(
            "policy allowed_machine_readable_outputs must not contain duplicates"
        )
    for output_path in machine_outputs:
        output = PurePosixPath(output_path)
        if output.name.casefold() in normalized_output_names:
            raise _schema_error("policy machine-readable output has a forbidden name")
        if any(part.casefold() in normalized_path_parts for part in output.parts):
            raise _schema_error(
                "policy machine-readable output has a forbidden path part"
            )
        if any(suffix.casefold() in normalized_suffixes for suffix in output.suffixes):
            raise _schema_error("policy machine-readable output has a forbidden suffix")

    return Policy(
        sources=sources,
        allowed_sensitivities=frozenset(allowed),
        forbidden_sensitivities=frozenset(forbidden),
        allowed_machine_readable_outputs=frozenset(machine_outputs),
        forbidden_output_names=frozenset(normalized_output_names),
        forbidden_path_parts=frozenset(normalized_path_parts),
        forbidden_suffixes=frozenset(normalized_suffixes),
    )


def _load_provenance(path: Path) -> dict[str, ProvenanceOutput]:
    raw = _require_mapping(_load_json(path, "provenance"), "provenance")
    _require_exact_keys(raw, PROVENANCE_KEYS, "provenance")
    if raw["schema_version"] != SCHEMA_VERSION:
        raise _schema_error("provenance schema_version must be 1.0.0")
    raw_outputs = raw["outputs"]
    if not isinstance(raw_outputs, list):
        raise _schema_error("provenance outputs must be an array")

    outputs: dict[str, ProvenanceOutput] = {}
    for index, raw_output in enumerate(raw_outputs):
        label = f"provenance outputs[{index}]"
        output = _require_mapping(raw_output, label)
        _require_exact_keys(output, OUTPUT_KEYS, label)
        output_path = _normalized_relative_path(output["path"], f"{label}.path")
        if output_path in outputs:
            raise _schema_error("provenance outputs must not contain duplicate paths")
        raw_sources = output["sources"]
        if not isinstance(raw_sources, list) or not raw_sources:
            raise _schema_error(f"{label}.sources must be a non-empty array")
        source_paths = tuple(
            _normalized_relative_path(value, f"{label}.sources entry")
            for value in raw_sources
        )
        if len(source_paths) != len(set(source_paths)):
            raise _schema_error(f"{label}.sources must not contain duplicates")

        sensitivity = output["sensitivity"]
        if sensitivity is not None:
            sensitivity = _require_string(sensitivity, f"{label}.sensitivity")
            if sensitivity not in ALL_SENSITIVITIES:
                raise _schema_error(f"{label}.sensitivity is not recognized")
        outputs[output_path] = ProvenanceOutput(
            path=output_path,
            sources=source_paths,
            sensitivity=sensitivity,
        )
    return outputs


def _collect_dist_files(dist_path: Path) -> tuple[set[str], set[str]]:
    if not dist_path.exists():
        raise _schema_error("dist does not exist")
    if not dist_path.is_dir():
        raise _schema_error("dist must be a directory")

    regular_files: set[str] = set()
    violations: set[str] = set()
    if dist_path.is_symlink():
        violations.add(".: symlink is not allowed")
        return regular_files, violations

    for root, directories, filenames in os.walk(dist_path, followlinks=False):
        root_path = Path(root)
        directories.sort()
        filenames.sort()
        for directory in tuple(directories):
            candidate = root_path / directory
            if candidate.is_symlink():
                relative = candidate.relative_to(dist_path).as_posix()
                violations.add(f"{relative}: symlink is not allowed")
                directories.remove(directory)
        for filename in filenames:
            candidate = root_path / filename
            relative = candidate.relative_to(dist_path).as_posix()
            if candidate.is_symlink():
                violations.add(f"{relative}: symlink is not allowed")
            elif candidate.is_file():
                regular_files.add(relative)
            else:
                violations.add(f"{relative}: non-regular file is not allowed")
    return regular_files, violations


def _content_violations(text: str, relative_path: str) -> set[str]:
    violations: set[str] = set()
    if LOCAL_PATH_PATTERN.search(text):
        violations.add(f"{relative_path}: contains a local absolute path")
    if OMC_PLAN_PATTERN.search(text):
        violations.add(f"{relative_path}: contains an .omc/plans reference")
    if PRIVATE_KEY_PATTERN.search(text):
        violations.add(f"{relative_path}: contains a private-key header")
    for match in API_KEY_ASSIGNMENT_PATTERN.finditer(text):
        value = match.group(1).rstrip(",;)")
        if not PLACEHOLDER_SECRET_PATTERN.fullmatch(value):
            violations.add(f"{relative_path}: contains an API-key assignment")
            break
    return violations


def _has_approved_binary_magic(suffix: str, content: bytes) -> bool:
    if suffix == ".png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if suffix in {".jpg", ".jpeg"}:
        return content.startswith(b"\xff\xd8\xff")
    if suffix == ".gif":
        return content.startswith((b"GIF87a", b"GIF89a"))
    if suffix == ".webp":
        return content.startswith(b"RIFF") and content[8:12] == b"WEBP"
    if suffix == ".ico":
        return content.startswith(b"\x00\x00\x01\x00")
    if suffix == ".woff":
        return content.startswith(b"wOFF")
    if suffix == ".woff2":
        return content.startswith(b"wOF2")
    if suffix == ".ttf":
        return content.startswith((b"\x00\x01\x00\x00", b"true", b"typ1"))
    if suffix == ".otf":
        return content.startswith(b"OTTO")
    if suffix == ".avif":
        return len(content) >= 12 and content[4:12] == b"ftypavif"
    return False


def _output_content_violations(path: Path, relative_path: str) -> set[str]:
    try:
        content = path.read_bytes()
    except OSError:
        return {f"{relative_path}: output cannot be read"}

    suffix = PurePosixPath(relative_path).suffix.casefold()
    if suffix in SAFE_BINARY_SUFFIXES:
        violations = _content_violations(
            content.decode("ascii", errors="ignore"), relative_path
        )
        if not _has_approved_binary_magic(suffix, content):
            violations.add(f"{relative_path}: binary output has unexpected magic")
        return violations

    try:
        return _content_violations(content.decode("utf-8"), relative_path)
    except UnicodeDecodeError:
        violations = _content_violations(
            content.decode("ascii", errors="ignore"), relative_path
        )
        violations.add(
            f"{relative_path}: output is not valid UTF-8 or an approved binary asset"
        )
        return violations


def audit(policy_path: Path, provenance_path: Path, dist_path: Path) -> tuple[str, ...]:
    """Return stable publication-boundary violations for one site build."""

    policy = _load_policy(policy_path)
    provenance = _load_provenance(provenance_path)
    regular_files, violations = _collect_dist_files(dist_path)
    if not regular_files:
        violations.add(".: dist contains no regular files")

    for output_path in sorted(regular_files):
        path = PurePosixPath(output_path)
        output_suffix = path.suffix.lower()
        machine_output_is_allowlisted = (
            output_path in policy.allowed_machine_readable_outputs
        )
        if path.name.casefold() in policy.forbidden_output_names:
            violations.add(f"{output_path}: forbidden output name")
        if any(part.casefold() in policy.forbidden_path_parts for part in path.parts):
            violations.add(f"{output_path}: forbidden path part")
        if any(
            suffix.casefold() in policy.forbidden_suffixes for suffix in path.suffixes
        ):
            violations.add(f"{output_path}: forbidden output suffix")
        if output_suffix in MACHINE_READABLE_SUFFIXES and (
            not machine_output_is_allowlisted
        ):
            violations.add(f"{output_path}: machine-readable output is not allowlisted")
        violations.update(
            _output_content_violations(dist_path / output_path, output_path)
        )

        output = provenance.get(output_path)
        if output is None:
            violations.add(f"{output_path}: missing provenance entry")
            continue
        if output.sensitivity in policy.forbidden_sensitivities:
            violations.add(f"{output_path}: forbidden sensitivity {output.sensitivity}")
        elif output.sensitivity is not None and (
            output.sensitivity not in policy.allowed_sensitivities
        ):
            violations.add(f"{output_path}: sensitivity is not allowed")
        for source_path in output.sources:
            source = policy.sources.get(source_path)
            if source is not None and source.requires_sensitivity:
                if output.sensitivity is None:
                    violations.add(f"{output_path}: required sensitivity is missing")
                elif output.sensitivity not in source.permitted_sensitivities:
                    violations.add(
                        f"{output_path}: sensitivity is not permitted for source "
                        f"{source_path}"
                    )
    for output_path in sorted(set(provenance) - regular_files):
        violations.add(
            f"{output_path}: provenance entry does not resolve to a regular file"
        )

    for output_path, output in sorted(provenance.items()):
        if any(source_path not in policy.sources for source_path in output.sources):
            violations.add(f"{output_path}: provenance source is not allowlisted")

    return tuple(sorted(violations))


def main(argv: Sequence[str] | None = None) -> int:
    """Run the publication-boundary audit command-line interface."""

    parser = argparse.ArgumentParser(
        description=(
            "Audit static-site publication boundaries until a site build supplies "
            "dist and provenance."
        )
    )
    parser.add_argument("--policy", default=DEFAULT_POLICY_PATH, type=Path)
    parser.add_argument("--provenance", required=True, type=Path)
    parser.add_argument("--dist", required=True, type=Path)
    arguments = parser.parse_args(argv)
    try:
        violations = audit(arguments.policy, arguments.provenance, arguments.dist)
    except AuditSchemaError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if violations:
        for violation in violations:
            print(violation, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
