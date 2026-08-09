"""Generate and validate the deterministic Blume benchmark registry."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

SCHEMA_VERSION = "1.0.0"
BENCHMARK_PREFIX = "src/synthworld/benchmarks/"
DATA_DIRECTORY = Path("docs/_data")
SCHEMA_DIRECTORY = Path("docs/_schemas")
CURATED_PATH = DATA_DIRECTORY / "benchmarks.curated.json"
GATES_PATH = DATA_DIRECTORY / "benchmark-publication-gates.json"
TRANSITIONS_PATH = DATA_DIRECTORY / "benchmark-transitions.json"
GENERATED_PATH = DATA_DIRECTORY / "benchmarks.generated.json"
RESOLVED_PATH = DATA_DIRECTORY / "benchmarks.resolved.json"
GENERATED_SCHEMA = SCHEMA_DIRECTORY / "benchmarks-generated.schema.json"
CURATED_SCHEMA = SCHEMA_DIRECTORY / "benchmarks-curated.schema.json"
RESOLVED_SCHEMA = SCHEMA_DIRECTORY / "benchmarks-resolved.schema.json"
GATES_SCHEMA = SCHEMA_DIRECTORY / "benchmark-publication-gates.schema.json"
TRANSITIONS_SCHEMA = SCHEMA_DIRECTORY / "benchmark-transitions.schema.json"
SHA256_RE = re.compile(r"[0-9a-f]{64}").fullmatch
CHANGELOG_RELEASE_RE = re.compile(r"^## \[([^]]+)](?:\s+-.*)?$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
GATE_CHECK_NAMES = (
    "independent_versions",
    "public_input",
    "evaluator_truth",
    "boundary_validation",
    "checksums",
    "submission_contract",
    "scorer_version",
    "baseline",
    "metric_denominators",
    "limitations",
    "adversarial_review",
    "safety_review",
    "clean_install_reproduction",
    "deterministic_ci_recreation",
    "catalogue_hf_metadata",
)
HF_TARGETS = {"hugging_face_raw", "hugging_face_viewer"}
PRIVATE_SENSITIVITIES = {
    "private_held_out_truth",
    "operator_private",
    "internal_build_only",
}
REPRODUCTION_TIMEOUT_SECONDS = 120

JsonObject = dict[str, Any]
_run_process = subprocess.run
_find_executable = shutil.which


class RegistryError(ValueError):
    """Raised when benchmark governance data is invalid or has drifted."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> JsonObject:
    result: JsonObject = {}
    for key, value in pairs:
        if key in result:
            raise RegistryError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def canonical_json(value: object) -> bytes:
    """Return canonical, reviewable JSON bytes."""

    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    ).encode()


def _decode_json(payload: bytes, label: str) -> JsonObject:
    try:
        value = json.loads(payload, object_pairs_hook=_reject_duplicate_keys)
    except UnicodeDecodeError as error:
        raise RegistryError(f"{label}: invalid UTF-8") from error
    except json.JSONDecodeError as error:
        raise RegistryError(
            f"{label}: invalid JSON at line {error.lineno}, column {error.colno}"
        ) from error
    if not isinstance(value, dict):
        raise RegistryError(f"{label}: top-level JSON value must be an object")
    return value


def _read_json(path: Path, *, require_canonical: bool) -> tuple[JsonObject, bytes]:
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise RegistryError(
            f"cannot read {path.as_posix()}: {error.strerror}"
        ) from error
    value = _decode_json(payload, path.as_posix())
    canonical = canonical_json(value)
    if require_canonical and payload != canonical:
        raise RegistryError(f"{path.as_posix()}: JSON is not canonical")
    return value, canonical


def _load_schema(root: Path, relative_path: Path) -> JsonObject:
    schema, _ = _read_json(root / relative_path, require_canonical=False)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as error:
        raise RegistryError(
            f"{relative_path.as_posix()}: invalid JSON Schema"
        ) from error
    return schema


def _validate_schema(root: Path, relative_path: Path, value: JsonObject) -> None:
    schema = _load_schema(root, relative_path)
    try:
        Draft202012Validator(schema).validate(value)
    except ValidationError as error:
        location = "/".join(str(part) for part in error.absolute_path) or "<root>"
        message = f"{relative_path.as_posix()} validation failed at {location}"
        raise RegistryError(f"{message}: {error.message}") from error


def _git(root: Path, arguments: Sequence[str]) -> bytes:
    executable = _find_executable("git")
    if executable is None:
        raise RegistryError(
            "git executable is unavailable; install git or add it to PATH"
        )
    try:
        process = _run_process(
            [str(Path(executable).resolve()), "-C", str(root), *arguments],
            check=False,
            capture_output=True,
        )
    except OSError as error:
        raise RegistryError("cannot execute git") from error
    if process.returncode != 0:
        message = process.stderr.decode("utf-8", errors="replace").strip()
        raise RegistryError(f"git {' '.join(arguments)} failed: {message}")
    return process.stdout


def tracked_paths(root: Path) -> tuple[str, ...]:
    """Return deterministic tracked repository paths."""

    payload = _git(root, ("ls-files", "-z"))
    try:
        paths = tuple(item for item in payload.decode().split("\0") if item)
    except UnicodeDecodeError as error:
        raise RegistryError("git returned a non-UTF-8 tracked path") from error
    return tuple(sorted(paths))


def _safe_member(member: str, *, owner: str) -> PurePosixPath:
    path = PurePosixPath(member)
    if not member or path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise RegistryError(f"{owner}: unsafe manifest path {member!r}")
    return path


def _member_path(owner: str, member: str) -> str:
    safe = _safe_member(member, owner=owner)
    parent = PurePosixPath(owner).parent
    resolved = (parent / safe).as_posix()
    if resolved == owner:
        raise RegistryError(f"{owner}: manifest cannot include itself")
    return resolved


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def artifact_set_digest(artifacts: Mapping[str, bytes]) -> str:
    """Return the repository-defined path-bound Asteria set digest."""

    digest = hashlib.sha256()
    for path, content in sorted(artifacts.items()):
        digest.update(path.encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(content).digest())
    return digest.hexdigest()


def _expected_reproduction(benchmark_id: str) -> JsonObject:
    return {
        "mode": "regenerate_and_compare",
        "argv": [
            "synthworld",
            "reproduce-benchmark",
            "--benchmark",
            benchmark_id,
            "--output",
            "{output_dir}",
        ],
    }


def _validate_reproduction_contract(benchmark: JsonObject) -> None:
    governed = benchmark["lifecycle"] in {"published", "superseded"}
    if governed:
        if benchmark["reproduction"] != _expected_reproduction(benchmark["id"]):
            raise RegistryError(
                f"{benchmark['id']}: governed benchmark needs exact reproduction argv"
            )
        if benchmark["example_command"] is not None:
            raise RegistryError(
                f"{benchmark['id']}: governed benchmark must omit example command"
            )
    elif benchmark["reproduction"] is not None:
        raise RegistryError(
            f"{benchmark['id']}: pre-publication benchmark cannot claim reproduction"
        )


def _parse_sha256sum(payload: bytes, owner: str) -> tuple[tuple[str, str], ...]:
    try:
        text = payload.decode("ascii")
    except UnicodeDecodeError as error:
        raise RegistryError(f"{owner}: checksum manifest is not ASCII") from error
    lines = text.splitlines()
    if not lines or payload != ("\n".join(lines) + "\n").encode("ascii"):
        raise RegistryError(f"{owner}: checksum manifest is not canonical")
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for line in lines:
        fields = line.split("  ")
        if len(fields) != 2 or SHA256_RE(fields[0]) is None:
            raise RegistryError(f"{owner}: invalid checksum row")
        member = fields[1]
        _safe_member(member, owner=owner)
        if member in seen:
            raise RegistryError(f"{owner}: duplicate manifest member {member}")
        seen.add(member)
        result.append((member, fields[0]))
    return tuple(result)


def _read_artifact_bytes(root: Path, paths: Iterable[str]) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for relative_path in paths:
        try:
            result[relative_path] = (root / relative_path).read_bytes()
        except OSError as error:
            raise RegistryError(
                f"cannot read tracked artifact {relative_path}"
            ) from error
    return result


def _record_integrity(
    memberships: dict[str, list[str]],
    records: list[JsonObject],
    *,
    record_id: str,
    path: str,
    scheme: str,
    members: Iterable[str],
) -> None:
    member_list = sorted(members)
    records.append(
        {"id": record_id, "members": member_list, "path": path, "scheme": scheme}
    )
    for member in member_list:
        memberships[member].append(record_id)


def _verify_sha256_manifests(
    artifacts: Mapping[str, bytes],
    memberships: dict[str, list[str]],
    records: list[JsonObject],
) -> None:
    owners = sorted(
        path for path in artifacts if PurePosixPath(path).name.endswith("SHA256SUMS")
    )
    for owner in owners:
        rows = _parse_sha256sum(artifacts[owner], owner)
        members: list[str] = []
        for member, expected in rows:
            resolved = _member_path(owner, member)
            if resolved not in artifacts:
                raise RegistryError(f"{owner}: unknown manifest member {member}")
            if _sha256(artifacts[resolved]) != expected:
                raise RegistryError(f"{owner}: checksum mismatch for {member}")
            members.append(resolved)
        _record_integrity(
            memberships,
            records,
            record_id=f"sha256sum:{owner}",
            path=owner,
            scheme="sha256sum",
            members=members,
        )


def _json_manifest(payload: bytes, owner: str) -> JsonObject:
    return _decode_json(payload, owner)


def _verify_asteria(
    artifacts: Mapping[str, bytes],
    memberships: dict[str, list[str]],
    records: list[JsonObject],
) -> None:
    public_owner = f"{BENCHMARK_PREFIX}asteria-agentic-v1/public/manifest.json"
    evaluator_owner = f"{BENCHMARK_PREFIX}asteria-agentic-v1/evaluator/checksums.json"
    if public_owner not in artifacts and evaluator_owner not in artifacts:
        return
    if public_owner not in artifacts or evaluator_owner not in artifacts:
        raise RegistryError("Asteria integrity records are incomplete")
    public = _json_manifest(artifacts[public_owner], public_owner)
    declared = public.get("artifacts")
    if not isinstance(declared, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in declared.items()
    ):
        raise RegistryError(f"{public_owner}: invalid artifacts map")
    public_base = PurePosixPath(public_owner).parent.as_posix()
    actual_public = sorted(
        path
        for path in artifacts
        if path.startswith(f"{public_base}/") and path != public_owner
    )
    resolved_public: dict[str, bytes] = {}
    for member, expected in declared.items():
        resolved = _member_path(public_owner, member)
        if resolved not in artifacts or SHA256_RE(expected) is None:
            raise RegistryError(f"{public_owner}: invalid member {member}")
        if _sha256(artifacts[resolved]) != expected:
            raise RegistryError(f"{public_owner}: checksum mismatch for {member}")
        resolved_public[member] = artifacts[resolved]
    if (
        sorted(_member_path(public_owner, member) for member in declared)
        != actual_public
    ):
        raise RegistryError(f"{public_owner}: artifact inventory differs")
    public_digest = artifact_set_digest(resolved_public)
    if public.get("artifact_set_digest") != public_digest:
        raise RegistryError(f"{public_owner}: artifact set digest differs")
    _record_integrity(
        memberships,
        records,
        record_id=f"asteria-public:{public_owner}",
        path=public_owner,
        scheme="sha256-artifact-set-v1",
        members=actual_public,
    )

    evaluator = _json_manifest(artifacts[evaluator_owner], evaluator_owner)
    declared_evaluator = evaluator.get("evaluator_artifacts")
    if not isinstance(declared_evaluator, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in declared_evaluator.items()
    ):
        raise RegistryError(f"{evaluator_owner}: invalid evaluator artifacts map")
    evaluator_base = PurePosixPath(evaluator_owner).parent.as_posix()
    actual_evaluator = sorted(
        path
        for path in artifacts
        if path.startswith(f"{evaluator_base}/") and path != evaluator_owner
    )
    resolved_evaluator: dict[str, bytes] = {}
    for member, expected in declared_evaluator.items():
        resolved = _member_path(evaluator_owner, member)
        if resolved not in artifacts or SHA256_RE(expected) is None:
            raise RegistryError(f"{evaluator_owner}: invalid member {member}")
        if _sha256(artifacts[resolved]) != expected:
            raise RegistryError(f"{evaluator_owner}: checksum mismatch for {member}")
        resolved_evaluator[member] = artifacts[resolved]
    if (
        sorted(_member_path(evaluator_owner, member) for member in declared_evaluator)
        != actual_evaluator
    ):
        raise RegistryError(f"{evaluator_owner}: artifact inventory differs")
    if evaluator.get("checksum_scheme") != "sha256-artifact-set-v1":
        raise RegistryError(f"{evaluator_owner}: unsupported checksum scheme")
    if evaluator.get("public_artifact_set_digest") != public_digest:
        raise RegistryError(f"{evaluator_owner}: public cross-digest differs")
    if evaluator.get("evaluator_artifact_set_digest") != artifact_set_digest(
        resolved_evaluator
    ):
        raise RegistryError(f"{evaluator_owner}: evaluator set digest differs")
    _record_integrity(
        memberships,
        records,
        record_id=f"asteria-evaluator:{evaluator_owner}",
        path=evaluator_owner,
        scheme="sha256-artifact-set-v1",
        members=actual_evaluator,
    )


def _verify_path_bound_manifest(
    artifacts: Mapping[str, bytes],
    memberships: dict[str, list[str]],
    records: list[JsonObject],
    *,
    owner: str,
    record_prefix: str,
    expected_members: Iterable[str],
) -> JsonObject:
    if owner not in artifacts:
        raise RegistryError(f"{owner}: missing manifest")
    manifest = _json_manifest(artifacts[owner], owner)
    descriptors = manifest.get("artifacts")
    if not isinstance(descriptors, list) or not descriptors:
        raise RegistryError(f"{owner}: invalid artifact descriptors")
    resolved_payloads: dict[str, bytes] = {}
    resolved_members: list[str] = []
    seen: set[str] = set()
    for descriptor in descriptors:
        if not isinstance(descriptor, dict):
            raise RegistryError(f"{owner}: invalid artifact descriptor")
        member = descriptor.get("path")
        digest = descriptor.get("sha256")
        byte_size = descriptor.get("byte_size")
        if (
            not isinstance(member, str)
            or member in seen
            or not isinstance(digest, str)
            or SHA256_RE(digest) is None
            or not isinstance(byte_size, int)
        ):
            raise RegistryError(f"{owner}: invalid artifact descriptor")
        seen.add(member)
        resolved = _member_path(owner, member)
        if resolved not in artifacts:
            raise RegistryError(f"{owner}: unknown manifest member {member}")
        payload = artifacts[resolved]
        if len(payload) != byte_size or _sha256(payload) != digest:
            raise RegistryError(f"{owner}: manifest binding differs for {member}")
        resolved_payloads[member] = payload
        resolved_members.append(resolved)
    if sorted(resolved_members) != sorted(expected_members):
        raise RegistryError(f"{owner}: artifact inventory differs")
    if manifest.get("artifact_set_digest") != artifact_set_digest(resolved_payloads):
        raise RegistryError(f"{owner}: artifact set digest differs")
    _record_integrity(
        memberships,
        records,
        record_id=f"{record_prefix}:{owner}",
        path=owner,
        scheme="sha256-path-bound-v1",
        members=resolved_members,
    )
    return manifest


def _path_bound_descriptor(path: str, payload: bytes) -> JsonObject:
    return {
        "byte_size": len(payload),
        "path": path,
        "sha256": _sha256(payload),
        "synthetic": True,
    }


def _verify_asteria_v2(
    artifacts: Mapping[str, bytes],
    memberships: dict[str, list[str]],
    records: list[JsonObject],
) -> None:
    root = f"{BENCHMARK_PREFIX}asteria-agentic-c08-v2"
    root_owner = f"{root}/manifest.json"
    public_owner = f"{root}/public/manifest.json"
    public_payload_path = f"{root}/public/c08-asteria-public.json"
    evaluator_owner = f"{root}/evaluator/manifest.json"
    evaluator_payload_path = f"{root}/evaluator/c08-asteria-evaluator.json"
    expected_tree = {
        root_owner,
        public_owner,
        public_payload_path,
        evaluator_owner,
        evaluator_payload_path,
    }
    actual_tree = {path for path in artifacts if path.startswith(f"{root}/")}
    if not actual_tree:
        return
    if actual_tree != expected_tree:
        raise RegistryError(f"{root}: Asteria C08 v2 inventory differs")
    root_manifest = _verify_path_bound_manifest(
        artifacts,
        memberships,
        records,
        owner=root_owner,
        record_prefix="c08-asteria-root",
        expected_members=expected_tree - {root_owner},
    )
    public_manifest = _verify_path_bound_manifest(
        artifacts,
        memberships,
        records,
        owner=public_owner,
        record_prefix="c08-asteria-public",
        expected_members=(public_payload_path,),
    )
    evaluator_manifest = _verify_path_bound_manifest(
        artifacts,
        memberships,
        records,
        owner=evaluator_owner,
        record_prefix="c08-asteria-evaluator",
        expected_members=(evaluator_payload_path,),
    )
    public_payload = artifacts[public_payload_path]
    evaluator_payload = artifacts[evaluator_payload_path]
    public_digest = _sha256(public_payload)
    public_files = {"c08-asteria-public.json": public_payload}
    evaluator_files = {"c08-asteria-evaluator.json": evaluator_payload}
    expected_public_manifest = {
        "artifact_set_digest": artifact_set_digest(public_files),
        "artifacts": [
            _path_bound_descriptor("c08-asteria-public.json", public_payload)
        ],
        "benchmark_id": "asteria-agentic-c08-v2",
        "schema_version": "2.0.0",
        "seed": 20260809,
        "synthetic": True,
        "visibility": "public",
    }
    expected_evaluator_manifest = {
        "artifact_set_digest": artifact_set_digest(evaluator_files),
        "artifacts": [
            _path_bound_descriptor("c08-asteria-evaluator.json", evaluator_payload)
        ],
        "benchmark_id": "asteria-agentic-c08-v2",
        "public_input_digest": public_digest,
        "schema_version": "2.0.0",
        "seed": 20260809,
        "synthetic": True,
        "visibility": "evaluator",
    }
    root_files = {
        "evaluator/c08-asteria-evaluator.json": evaluator_payload,
        "evaluator/manifest.json": artifacts[evaluator_owner],
        "public/c08-asteria-public.json": public_payload,
        "public/manifest.json": artifacts[public_owner],
    }
    expected_root_manifest = {
        "artifact_set_digest": artifact_set_digest(root_files),
        "artifacts": [
            _path_bound_descriptor(path, payload)
            for path, payload in sorted(root_files.items())
        ],
        "benchmark_id": "asteria-agentic-c08-v2",
        "evaluator_artifact_set_digest": artifact_set_digest(evaluator_files),
        "evaluator_public_input_digest": public_digest,
        "public_artifact_set_digest": artifact_set_digest(public_files),
        "public_input_digest": public_digest,
        "schema_version": "2.0.0",
        "seed": 20260809,
        "synthetic": True,
        "visibility": "root",
    }
    if public_manifest != expected_public_manifest:
        raise RegistryError(f"{public_owner}: manifest contract differs")
    if evaluator_manifest != expected_evaluator_manifest:
        raise RegistryError(f"{evaluator_owner}: manifest contract differs")
    if root_manifest != expected_root_manifest:
        raise RegistryError(f"{root_owner}: manifest contract differs")


def _verify_enterprise_c08_v2(artifacts: Mapping[str, bytes]) -> None:
    root = f"{BENCHMARK_PREFIX}enterprise-agentic-c08-v2"
    owner = f"{root}/SHA256SUMS"
    manifest_path = f"{root}/manifest.json"
    evaluator_path = f"{root}/evaluator/truth.json"
    public_path = f"{root}/public/public-input.json"
    expected_tree = {owner, manifest_path, evaluator_path, public_path}
    actual_tree = {path for path in artifacts if path.startswith(f"{root}/")}
    if not actual_tree:
        return
    if actual_tree != expected_tree:
        raise RegistryError(f"{owner}: enterprise C08 v2 inventory differs")
    evaluator_payload = artifacts[evaluator_path]
    public_payload = artifacts[public_path]
    manifest_payload = artifacts[manifest_path]
    expected_rows = (
        ("evaluator/truth.json", _sha256(evaluator_payload)),
        ("manifest.json", _sha256(manifest_payload)),
        ("public/public-input.json", _sha256(public_payload)),
    )
    if _parse_sha256sum(artifacts[owner], owner) != expected_rows:
        raise RegistryError(f"{owner}: enterprise C08 v2 checksum rows differ")
    expected_manifest = {
        "benchmark_id": "enterprise-agentic-c08-v2",
        "checksum_algorithm": "sha256",
        "checksum_excludes": ["SHA256SUMS"],
        "checksum_file": "SHA256SUMS",
        "evaluator_inventory": [
            _path_bound_descriptor("evaluator/truth.json", evaluator_payload)
        ],
        "public_input_digest": _sha256(public_payload),
        "public_inventory": [
            _path_bound_descriptor("public/public-input.json", public_payload)
        ],
        "schema_version": "2.0.0",
        "seed": 20260809,
        "synthetic": True,
    }
    if _json_manifest(manifest_payload, manifest_path) != expected_manifest:
        raise RegistryError(f"{manifest_path}: enterprise C08 v2 manifest differs")


def _verify_authority_manifests(
    artifacts: Mapping[str, bytes],
    memberships: dict[str, list[str]],
    records: list[JsonObject],
) -> None:
    root = f"{BENCHMARK_PREFIX}authority-governance-v1"
    root_checksum = f"{root}/SHA256SUMS"
    if root_checksum not in artifacts:
        return
    expected_root_members = {
        f"{root}/evaluator/authority-governance-evaluator.json",
        f"{root}/evaluator/manifest.json",
        f"{root}/public/authority-governance-input.json",
        f"{root}/public/manifest.json",
    }
    rows = _parse_sha256sum(artifacts[root_checksum], root_checksum)
    actual_root_members = {_member_path(root_checksum, member) for member, _ in rows}
    if actual_root_members != expected_root_members:
        raise RegistryError(f"{root_checksum}: root coverage differs")
    for visibility in ("public", "evaluator"):
        owner = f"{root}/{visibility}/manifest.json"
        manifest = _json_manifest(artifacts[owner], owner)
        descriptors = manifest.get("artifacts")
        if not isinstance(descriptors, list) or not descriptors:
            raise RegistryError(f"{owner}: invalid artifact descriptors")
        members: list[str] = []
        seen: set[str] = set()
        for descriptor in descriptors:
            if not isinstance(descriptor, dict):
                raise RegistryError(f"{owner}: invalid artifact descriptor")
            member = descriptor.get("path")
            digest = descriptor.get("digest")
            byte_size = descriptor.get("byte_size")
            if (
                not isinstance(member, str)
                or member in seen
                or not isinstance(digest, dict)
                or digest.get("algorithm") != "sha256"
                or not isinstance(digest.get("value"), str)
                or SHA256_RE(digest["value"]) is None
                or not isinstance(byte_size, int)
            ):
                raise RegistryError(f"{owner}: invalid artifact descriptor")
            seen.add(member)
            resolved = _member_path(owner, member)
            if resolved not in artifacts:
                raise RegistryError(f"{owner}: unknown manifest member {member}")
            payload = artifacts[resolved]
            if len(payload) != byte_size or _sha256(payload) != digest["value"]:
                raise RegistryError(f"{owner}: manifest binding differs for {member}")
            members.append(resolved)
        expected_directory = sorted(
            path
            for path in artifacts
            if path.startswith(f"{root}/{visibility}/") and path != owner
        )
        if sorted(members) != expected_directory:
            raise RegistryError(f"{owner}: artifact inventory differs")
        _record_integrity(
            memberships,
            records,
            record_id=f"authority-manifest:{owner}",
            path=owner,
            scheme="sha256-size-manifest-v1",
            members=members,
        )


def discover_generated(root: Path) -> JsonObject:
    """Discover and integrity-check all tracked benchmark artifact facts."""

    benchmark_paths = tuple(
        path
        for path in tracked_paths(root)
        if path.startswith(BENCHMARK_PREFIX) and not path.endswith(".py")
    )
    artifacts = _read_artifact_bytes(root, benchmark_paths)
    memberships: dict[str, list[str]] = {path: [] for path in benchmark_paths}
    records: list[JsonObject] = []
    _verify_enterprise_c08_v2(artifacts)
    _verify_sha256_manifests(artifacts, memberships, records)
    _verify_asteria(artifacts, memberships, records)
    _verify_asteria_v2(artifacts, memberships, records)
    _verify_authority_manifests(artifacts, memberships, records)
    facts = []
    for path in benchmark_paths:
        name = PurePosixPath(path).name
        file_format = (
            "sha256sum"
            if name.endswith("SHA256SUMS")
            else "jsonl"
            if name.endswith(".jsonl")
            else "json"
        )
        facts.append(
            {
                "byte_size": len(artifacts[path]),
                "format": file_format,
                "integrity_record_ids": sorted(memberships[path]),
                "package_path": path.removeprefix("src/"),
                "path": path,
                "sha256": _sha256(artifacts[path]),
            }
        )
    records.sort(key=lambda record: str(record["id"]))
    inventory = {"artifacts": facts, "integrity_records": records}
    return {
        "schema_version": SCHEMA_VERSION,
        "inventory_digest": _sha256(canonical_json(inventory)),
        **inventory,
    }


def _slug(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text).strip().lower()
    text = re.sub(r"[^\w\- ]", "", text, flags=re.UNICODE)
    return re.sub(r"\s", "-", text)


def discover_routes(root: Path) -> set[str]:
    """Discover tracked Markdown heading routes without reading fenced examples."""

    routes: set[str] = set()
    for relative_path in tracked_paths(root):
        if not relative_path.endswith(".md"):
            continue
        try:
            lines = (root / relative_path).read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as error:
            raise RegistryError(
                f"cannot read Markdown route source {relative_path}"
            ) from error
        fenced = False
        counts: dict[str, int] = {}
        for line in lines:
            if FENCE_RE.match(line):
                fenced = not fenced
                continue
            match = None if fenced else HEADING_RE.match(line)
            if match is None:
                continue
            base = _slug(match.group(2))
            count = counts.get(base, 0)
            counts[base] = count + 1
            anchor = base if count == 0 else f"{base}-{count}"
            routes.add(f"route:{relative_path}#{anchor}")
    return routes


def discover_releases(root: Path) -> tuple[set[str], bool, str]:
    """Return changelog releases, Unreleased presence, and package version."""

    try:
        changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
        project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        version = project["project"]["version"]
    except (OSError, UnicodeDecodeError, KeyError, tomllib.TOMLDecodeError) as error:
        raise RegistryError("cannot discover release evidence") from error
    if not isinstance(version, str):
        raise RegistryError("project.version must be a string")
    headings = {
        match.group(1)
        for line in changelog.splitlines()
        if (match := CHANGELOG_RELEASE_RE.match(line)) is not None
    }
    return headings - {"Unreleased"}, "Unreleased" in headings, version


def _unique(records: list[Any], field: str, label: str) -> dict[str, JsonObject]:
    result: dict[str, JsonObject] = {}
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get(field), str):
            raise RegistryError(f"{label}: invalid {field}")
        key = record[field]
        if key in result:
            raise RegistryError(f"{label}: duplicate {field} {key}")
        result[key] = record
    return result


def _validate_routes(record: JsonObject, routes: set[str]) -> None:
    references = list(record["docs_route_ids"])
    if record["limitations_route_id"] is not None:
        references.append(record["limitations_route_id"])
    unknown = sorted(set(references) - routes)
    if unknown:
        raise RegistryError(f"{record['id']}: unknown documentation route {unknown[0]}")


def _validate_release(
    benchmark: JsonObject, releases: set[str], unreleased: bool
) -> None:
    introduced = benchmark["introduced_in"]
    if introduced == "unreleased":
        if benchmark["lifecycle"] in {"published", "superseded"} or not unreleased:
            raise RegistryError(f"{benchmark['id']}: invalid unreleased provenance")
        return
    if introduced not in releases:
        raise RegistryError(
            f"{benchmark['id']}: unknown introduced release {introduced}"
        )


def _validate_transition_records(
    transitions: Mapping[str, JsonObject],
    benchmarks: Mapping[str, JsonObject],
    artifacts: Mapping[str, JsonObject],
    routes: set[str],
) -> None:
    for transition in transitions.values():
        transition_id = transition["id"]
        if not transition["rationale"].strip():
            raise RegistryError(f"{transition_id}: transition needs rationale")
        if transition["review_route_id"] not in routes:
            raise RegistryError(f"{transition_id}: unknown transition review route")
        benchmark_id = transition["benchmark_id"]
        if benchmark_id not in benchmarks:
            raise RegistryError(f"{transition_id}: unknown transition benchmark")
        if transition["decision"] == "supersede":
            replacement_id = transition["replacement_id"]
            if replacement_id == benchmark_id:
                raise RegistryError(f"{transition_id}: self replacement is forbidden")
            if replacement_id not in benchmarks:
                raise RegistryError(f"{transition_id}: unknown transition replacement")
            continue
        artifact_id = transition["artifact_id"]
        if (
            artifact_id not in artifacts
            or artifacts[artifact_id]["benchmark_id"] != benchmark_id
        ):
            raise RegistryError(f"{transition_id}: unknown transition artifact")


def validate_and_resolve(
    root: Path,
    generated: JsonObject,
    curated: JsonObject,
    gates_document: JsonObject,
    transitions_document: JsonObject,
    *,
    input_bytes: Mapping[str, bytes],
) -> JsonObject:
    """Validate editorial assertions and join them to generated facts."""

    routes = discover_routes(root)
    releases, unreleased, _ = discover_releases(root)
    generated_by_path = _unique(generated["artifacts"], "path", "generated artifacts")
    benchmarks = _unique(curated["benchmarks"], "id", "benchmarks")
    artifacts = _unique(curated["artifacts"], "id", "artifacts")
    gates = _unique(gates_document["gates"], "id", "publication gates")
    transitions = _unique(
        transitions_document["transitions"], "id", "benchmark transitions"
    )
    _validate_transition_records(transitions, benchmarks, artifacts, routes)

    assigned_paths: dict[str, str] = {}
    benchmark_artifact_ids: set[str] = set()
    for benchmark in benchmarks.values():
        _validate_reproduction_contract(benchmark)
        _validate_routes(benchmark, routes)
        _validate_release(benchmark, releases, unreleased)
        ids = benchmark["artifact_ids"]
        if len(ids) != len(set(ids)):
            raise RegistryError(f"{benchmark['id']}: duplicate artifact assignment")
        for artifact_id in ids:
            if artifact_id not in artifacts:
                raise RegistryError(
                    f"{benchmark['id']}: unknown artifact {artifact_id}"
                )
            if artifact_id in benchmark_artifact_ids:
                raise RegistryError(
                    f"artifact assigned by multiple benchmarks: {artifact_id}"
                )
            benchmark_artifact_ids.add(artifact_id)
            if artifacts[artifact_id]["benchmark_id"] != benchmark["id"]:
                raise RegistryError(
                    f"{artifact_id}: benchmark_id differs from assignment"
                )
        if benchmark["lifecycle"] == "superseded" and not benchmark["replacement_id"]:
            raise RegistryError(
                f"{benchmark['id']}: superseded benchmark needs replacement"
            )
        if benchmark["replacement_id"] == benchmark["id"]:
            raise RegistryError(f"{benchmark['id']}: self replacement is forbidden")
        if (
            benchmark["replacement_id"] is not None
            and benchmark["replacement_id"] not in benchmarks
        ):
            raise RegistryError(f"{benchmark['id']}: unknown replacement benchmark")

    if benchmark_artifact_ids != set(artifacts):
        missing = sorted(set(artifacts) - benchmark_artifact_ids)
        raise RegistryError(f"unassigned curated artifact: {missing[0]}")

    for artifact in artifacts.values():
        path = artifact["path"]
        sensitivity = artifact["sensitivity"]
        if sensitivity in PRIVATE_SENSITIVITIES:
            if (
                path is not None
                or artifact["approved_sha256"] is not None
                or artifact["present_in"]
                or artifact["approved_targets"]
            ):
                raise RegistryError(
                    f"{artifact['id']}: private artifact exposes material"
                )
        elif path is None:
            raise RegistryError(
                f"{artifact['id']}: public artifact requires a tracked path"
            )
        if sensitivity == "public_reference_truth" and not artifact["answer_key_label"]:
            raise RegistryError(
                f"{artifact['id']}: public reference truth needs answer-key label"
            )
        if path is not None:
            if path not in generated_by_path:
                raise RegistryError(f"{artifact['id']}: unknown tracked path {path}")
            if path in assigned_paths:
                raise RegistryError(f"tracked path assigned twice: {path}")
            assigned_paths[path] = artifact["id"]
            fact = generated_by_path[path]
            declared_integrity = set(artifact["integrity_record_ids"])
            discovered_integrity = set(fact["integrity_record_ids"])
            unknown_integrity = declared_integrity - discovered_integrity
            if unknown_integrity:
                raise RegistryError(f"{artifact['id']}: unknown integrity record")
            missing_integrity = discovered_integrity - declared_integrity
            if missing_integrity:
                raise RegistryError(f"{artifact['id']}: incomplete integrity coverage")
            if (
                artifact["kind"] not in {"manifest", "checksum_manifest"}
                and not discovered_integrity
            ):
                raise RegistryError(
                    f"{artifact['id']}: non-manifest payload lacks integrity coverage"
                )
            if artifact["approved_sha256"] is not None and (
                artifact["approved_sha256"] != fact["sha256"]
            ):
                raise RegistryError(f"{artifact['id']}: approved digest differs")

    if set(assigned_paths) != set(generated_by_path):
        missing = sorted(set(generated_by_path) - set(assigned_paths))
        raise RegistryError(f"unassigned generated artifact: {missing[0]}")

    resolved_benchmarks: list[JsonObject] = []
    for benchmark in sorted(benchmarks.values(), key=lambda item: str(item["id"])):
        lifecycle = benchmark["lifecycle"]
        related = [artifacts[item] for item in benchmark["artifact_ids"]]
        if lifecycle in {"candidate", "experimental"} and any(
            set(item["approved_targets"]) & HF_TARGETS for item in related
        ):
            raise RegistryError(
                f"{benchmark['id']}: pre-publication benchmark authorizes HF"
            )
        gate: JsonObject | None = None
        gate_id = benchmark["publication_gate_id"]
        if lifecycle in {"published", "superseded"}:
            if not gate_id or gate_id not in gates:
                raise RegistryError(
                    f"{benchmark['id']}: governed benchmark needs a gate"
                )
            gate = gates[gate_id]
            _validate_governed_gate(benchmark, gate, related, routes)
            for artifact in related:
                if artifact["path"] is None or not artifact["frozen"]:
                    raise RegistryError(
                        f"{artifact['id']}: governed artifact must be frozen"
                    )
        elif gate_id is not None:
            raise RegistryError(
                f"{benchmark['id']}: non-published benchmark must omit publication gate"
            )
        resolved_artifacts = []
        for artifact in sorted(related, key=lambda item: str(item["id"])):
            joined = dict(artifact)
            path = artifact["path"]
            joined["generated"] = generated_by_path[path] if path is not None else None
            resolved_artifacts.append(joined)
        joined_benchmark = dict(benchmark)
        joined_benchmark["artifacts"] = resolved_artifacts
        joined_benchmark["publication_gate"] = gate
        resolved_benchmarks.append(joined_benchmark)

    used_gate_ids = {
        benchmark["publication_gate_id"]
        for benchmark in benchmarks.values()
        if benchmark["publication_gate_id"] is not None
    }
    unused_gate_ids = set(gates) - used_gate_ids
    if unused_gate_ids:
        raise RegistryError(
            f"unassociated publication gate: {sorted(unused_gate_ids)[0]}"
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "input_digests": {
            "benchmark_publication_gates": _sha256(input_bytes["gates"]),
            "benchmark_transitions": _sha256(input_bytes["transitions"]),
            "benchmarks_curated": _sha256(input_bytes["curated"]),
            "benchmarks_generated": _sha256(canonical_json(generated)),
        },
        "benchmarks": resolved_benchmarks,
    }


def _validate_governed_gate(
    benchmark: JsonObject,
    gate: JsonObject,
    artifacts: list[JsonObject],
    routes: set[str],
) -> None:
    if (
        gate["benchmark_id"] != benchmark["id"]
        or gate["benchmark_version"] != benchmark["benchmark_version"]
        or gate["decision"] != "approved"
    ):
        raise RegistryError(
            f"{benchmark['id']}: publication gate does not approve version"
        )
    if gate["review_route_id"] not in routes:
        raise RegistryError(f"{benchmark['id']}: unknown gate review route")
    checks = gate["checks"]
    names = [check["name"] for check in checks]
    if sorted(names) != sorted(GATE_CHECK_NAMES) or len(names) != len(set(names)):
        raise RegistryError(f"{gate['id']}: publication gate checks differ")
    for check in checks:
        if check["status"] == "pending":
            raise RegistryError(f"{gate['id']}: published gate has pending check")
        if check["status"] == "not_applicable" and not check["rationale"]:
            raise RegistryError(f"{gate['id']}: N/A check needs rationale")
    checks_by_name = {check["name"]: check for check in checks}
    if (
        any(set(artifact["approved_targets"]) & HF_TARGETS for artifact in artifacts)
        and checks_by_name["catalogue_hf_metadata"]["status"] != "pass"
    ):
        raise RegistryError(
            f"{gate['id']}: HF targets require catalogue_hf_metadata pass"
        )
    approved = set(gate["approved_targets"])
    for artifact in artifacts:
        if not set(artifact["approved_targets"]).issubset(approved):
            raise RegistryError(f"{artifact['id']}: target is not gate-authorized")


def _git_show_json(root: Path, base_ref: str, relative_path: Path) -> JsonObject:
    payload = _git(root, ("show", f"{base_ref}:{relative_path.as_posix()}"))
    return _decode_json(payload, f"{base_ref}:{relative_path.as_posix()}")


def _load_base_registry(
    root: Path, base_ref: str
) -> tuple[JsonObject | None, JsonObject | None]:
    """Load base registry files, allowing only an explicit pre-registry bootstrap."""

    _git(root, ("rev-parse", "--verify", f"{base_ref}^{{commit}}"))
    payload = _git(
        root,
        (
            "ls-tree",
            "-r",
            "--name-only",
            "-z",
            base_ref,
            "--",
            RESOLVED_PATH.as_posix(),
            GENERATED_PATH.as_posix(),
        ),
    )
    try:
        paths = {item for item in payload.decode().split("\0") if item}
    except UnicodeDecodeError as error:
        raise RegistryError("git returned non-UTF-8 base registry paths") from error
    resolved = (
        _git_show_json(root, base_ref, RESOLVED_PATH)
        if RESOLVED_PATH.as_posix() in paths
        else None
    )
    generated = (
        _git_show_json(root, base_ref, GENERATED_PATH)
        if GENERATED_PATH.as_posix() in paths
        else None
    )
    return resolved, generated


def validate_base_transition(
    root: Path,
    base_ref: str,
    resolved: JsonObject,
    transitions_document: JsonObject,
) -> None:
    """Reject silent published demotions and frozen-byte transitions."""

    base_resolved, base_generated = _load_base_registry(root, base_ref)
    if base_resolved is None and base_generated is None:
        return
    if base_resolved is None or base_generated is None:
        raise RegistryError("base registry is incomplete")
    del base_generated
    current = {item["id"]: item for item in resolved["benchmarks"]}
    base_benchmark_ids = {item["id"] for item in base_resolved["benchmarks"]}
    for benchmark_id, benchmark in current.items():
        if (
            benchmark_id not in base_benchmark_ids
            and benchmark["lifecycle"] == "superseded"
        ):
            raise RegistryError(
                f"{benchmark_id}: newly introduced benchmark cannot be superseded"
            )
    transitions = transitions_document["transitions"]
    for old_benchmark in base_resolved["benchmarks"]:
        benchmark_id = old_benchmark["id"]
        new_benchmark = current.get(benchmark_id)
        if new_benchmark is None:
            raise RegistryError(f"base benchmark removed: {benchmark_id}")
        if old_benchmark["lifecycle"] == "published" and new_benchmark["lifecycle"] in {
            "candidate",
            "experimental",
        }:
            raise RegistryError(
                f"{benchmark_id}: published benchmark cannot be demoted"
            )
        if (
            old_benchmark["lifecycle"] == "superseded"
            and new_benchmark != old_benchmark
        ):
            raise RegistryError(f"{benchmark_id}: superseded benchmark is immutable")
        if new_benchmark["lifecycle"] == "superseded":
            if old_benchmark["lifecycle"] != "published":
                raise RegistryError(
                    f"{benchmark_id}: only a published benchmark can be superseded"
                )
            matches = [
                item
                for item in transitions
                if item["benchmark_id"] == benchmark_id
                and item["decision"] == "supersede"
                and item["from_version"] == old_benchmark["benchmark_version"]
                and item["to_version"] == new_benchmark["benchmark_version"]
                and item["replacement_id"] == new_benchmark["replacement_id"]
            ]
            if len(matches) != 1:
                raise RegistryError(
                    f"{benchmark_id}: transition to superseded needs exact governance"
                )
        old_artifacts = {item["id"]: item for item in old_benchmark["artifacts"]}
        new_artifacts = {item["id"]: item for item in new_benchmark["artifacts"]}
        for artifact_id, old_artifact in old_artifacts.items():
            if not old_artifact["frozen"]:
                continue
            new_artifact = new_artifacts.get(artifact_id)
            if new_artifact is None:
                raise RegistryError(f"frozen artifact removed: {artifact_id}")
            if not new_artifact["frozen"]:
                raise RegistryError(
                    f"frozen artifact cannot be unfrozen: {artifact_id}"
                )
            old_digest = old_artifact["approved_sha256"]
            new_digest = new_artifact["approved_sha256"]
            if old_digest == new_digest:
                continue
            same_version = (
                old_benchmark["benchmark_version"] == new_benchmark["benchmark_version"]
            )
            decision = "refreeze" if same_version else "version_transition"
            matches = [
                item
                for item in transitions
                if item["benchmark_id"] == benchmark_id
                and item.get("artifact_id") == artifact_id
                and item["decision"] == decision
                and item["from_version"] == old_benchmark["benchmark_version"]
                and item["to_version"] == new_benchmark["benchmark_version"]
                and item["old_sha256"] == old_digest
                and item["new_sha256"] == new_digest
            ]
            if len(matches) != 1:
                raise RegistryError(
                    f"{artifact_id}: frozen change needs exact {decision}"
                )


def validate_tags(root: Path, curated: JsonObject, gates: JsonObject) -> None:
    """Validate released evidence against a full-history local checkout."""

    releases, unreleased, package_version = discover_releases(root)
    output = _git(root, ("tag", "--list"))
    tags = set(output.decode().splitlines())
    for benchmark in curated["benchmarks"]:
        introduced = benchmark["introduced_in"]
        if introduced == "unreleased":
            continue
        expected = f"v{introduced}"
        if expected not in tags and not (
            introduced == package_version and unreleased and introduced in releases
        ):
            raise RegistryError(f"{benchmark['id']}: missing release tag {expected}")
    for gate in gates["gates"]:
        release_tag = gate["release_tag"]
        if release_tag not in tags and not (
            release_tag == f"v{package_version}" and unreleased
        ):
            raise RegistryError(f"{gate['id']}: missing release tag {release_tag}")


def validate_wheel(wheel: Path, resolved: JsonObject) -> None:
    """Require exact wheel/registry benchmark artifact equality."""

    expected = {
        artifact["generated"]["package_path"]: artifact["generated"]["sha256"]
        for benchmark in resolved["benchmarks"]
        for artifact in benchmark["artifacts"]
        if "python_package" in artifact["present_in"]
        and artifact["generated"] is not None
    }
    try:
        with zipfile.ZipFile(wheel) as archive:
            listed_names = archive.namelist()
            names = set(listed_names)
            if len(listed_names) != len(names):
                raise RegistryError("wheel contains duplicate members")
            wheel_digests = {
                name: _sha256(archive.read(name)) for name in names if name in expected
            }
    except (OSError, zipfile.BadZipFile) as error:
        raise RegistryError(f"cannot read wheel {wheel}") from error
    prefix = "synthworld/benchmarks/"
    python_members = {
        name for name in names if name.startswith(prefix) and name.endswith(".py")
    }
    if python_members - {f"{prefix}__init__.py"}:
        raise RegistryError("wheel contains an unexpected benchmark Python member")
    actual = {
        name
        for name in names
        if name.startswith(prefix)
        and not name.endswith(".py")
        and not name.endswith("/")
    }
    expected_names = set(expected)
    if actual != expected_names:
        missing = sorted(expected_names - actual)
        extra = sorted(actual - expected_names)
        detail = f"missing={missing}, extra={extra}"
        raise RegistryError(f"wheel benchmark inventory differs: {detail}")
    mismatched = sorted(
        name for name, digest in expected.items() if wheel_digests[name] != digest
    )
    if mismatched:
        raise RegistryError(f"wheel benchmark bytes differ: {mismatched[0]}")


def _snapshot_tree(root: Path) -> dict[str, tuple[str, bytes]]:
    snapshot: dict[str, tuple[str, bytes]] = {}
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in sorted(directory_names):
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                snapshot[relative] = ("symlink", os.readlink(path).encode())
            else:
                snapshot[f"{relative}/"] = ("directory", b"")
        for name in sorted(file_names):
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                snapshot[relative] = ("symlink", os.readlink(path).encode())
            elif stat.S_ISREG(mode):
                snapshot[relative] = ("file", path.read_bytes())
            else:
                snapshot[relative] = ("nonregular", b"")
    return snapshot


def _collect_reproduction_output(output_root: Path) -> dict[str, bytes]:
    if output_root.is_symlink() or not output_root.is_dir():
        raise RegistryError("reproduction did not create a regular output directory")
    outputs: dict[str, bytes] = {}
    casefolded: dict[str, str] = {}
    for current, directory_names, file_names in os.walk(output_root, followlinks=False):
        current_path = Path(current)
        for name in directory_names:
            path = current_path / name
            if path.is_symlink() or not path.is_dir():
                raise RegistryError("reproduction output contains a nonregular entry")
        for name in file_names:
            path = current_path / name
            mode = path.lstat().st_mode
            if not stat.S_ISREG(mode):
                raise RegistryError("reproduction output contains a nonregular entry")
            relative = path.relative_to(output_root).as_posix()
            folded = relative.casefold()
            previous = casefolded.get(folded)
            if previous is not None and previous != relative:
                detail = f"{previous}, {relative}"
                raise RegistryError(
                    f"reproduction output has case-colliding paths: {detail}"
                )
            casefolded[folded] = relative
            outputs[relative] = path.read_bytes()
    return outputs


def _expected_reproduction_outputs(benchmark: JsonObject) -> dict[str, str]:
    expected: dict[str, str] = {}
    for artifact in benchmark["artifacts"]:
        path = artifact["path"]
        digest = artifact["approved_sha256"]
        if not isinstance(path, str) or not path.startswith(BENCHMARK_PREFIX):
            raise RegistryError(
                f"{benchmark['id']}: governed artifact has no reproducible path"
            )
        if not isinstance(digest, str):
            raise RegistryError(
                f"{benchmark['id']}: governed artifact has no approved digest"
            )
        relative = path.removeprefix(BENCHMARK_PREFIX)
        folded = relative.casefold()
        if any(existing.casefold() == folded for existing in expected):
            raise RegistryError(
                f"{benchmark['id']}: approved inventory has case-colliding paths"
            )
        expected[relative] = digest
    return expected


def _run_reproduction(
    uv: str,
    wheel: Path,
    benchmark: JsonObject,
    output_root: Path,
    cwd: Path,
) -> None:
    reproduction = benchmark["reproduction"]
    argv = [
        str(output_root) if item == "{output_dir}" else item
        for item in reproduction["argv"]
    ]
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    command = [
        uv,
        "run",
        "--isolated",
        "--no-project",
        "--with",
        str(wheel),
        *argv,
    ]
    try:
        process = _run_process(
            command,
            check=False,
            capture_output=True,
            cwd=cwd,
            env=environment,
            shell=False,
            timeout=REPRODUCTION_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise RegistryError(f"{benchmark['id']}: reproduction timed out") from error
    except OSError as error:
        raise RegistryError(
            f"{benchmark['id']}: cannot execute reproduction"
        ) from error
    if process.returncode != 0:
        stderr = process.stderr.decode("utf-8", errors="replace").strip()
        raise RegistryError(
            f"{benchmark['id']}: reproduction failed: {stderr or process.returncode}"
        )


def validate_reproduction(wheel: Path, resolved: JsonObject, root: Path) -> None:
    """Reproduce every governed benchmark twice from one isolated wheel."""

    executable = _find_executable("uv")
    if executable is None:
        raise RegistryError(
            "uv executable is unavailable; install uv or add it to PATH"
        )
    uv = str(Path(executable).resolve())
    wheel = wheel.resolve()
    source_root = root / BENCHMARK_PREFIX
    source_before = _snapshot_tree(source_root)
    try:
        with tempfile.TemporaryDirectory(
            prefix="synthworld-reproduction-"
        ) as temporary:
            temporary_root = Path(temporary)
            wheel_directory = temporary_root / "wheel"
            wheel_directory.mkdir()
            staged_wheel = wheel_directory / wheel.name
            try:
                shutil.copyfile(wheel, staged_wheel)
            except OSError as error:
                raise RegistryError(
                    "cannot stage validated wheel for reproduction"
                ) from error
            for index, benchmark in enumerate(resolved["benchmarks"]):
                if benchmark["lifecycle"] not in {"published", "superseded"}:
                    continue
                expected = _expected_reproduction_outputs(benchmark)
                work = temporary_root / str(index)
                work.mkdir()
                outputs: list[dict[str, bytes]] = []
                for run_number in (1, 2):
                    output_root = work / f"run-{run_number}"
                    _run_reproduction(uv, staged_wheel, benchmark, output_root, work)
                    actual = _collect_reproduction_output(output_root)
                    if set(actual) != set(expected):
                        missing = sorted(set(expected) - set(actual))
                        extra = sorted(set(actual) - set(expected))
                        raise RegistryError(
                            f"{benchmark['id']}: reproduction inventory differs: "
                            f"missing={missing}, extra={extra}"
                        )
                    outputs.append(actual)
                if outputs[0] != outputs[1]:
                    raise RegistryError(
                        f"{benchmark['id']}: reproduction is not deterministic"
                    )
                for path, approved_digest in expected.items():
                    if _sha256(outputs[0][path]) != approved_digest:
                        raise RegistryError(
                            f"{benchmark['id']}: reproduced bytes differ: {path}"
                        )
    finally:
        if _snapshot_tree(source_root) != source_before:
            raise RegistryError("reproduction modified source benchmark artifacts")


def _prepare_inputs(
    root: Path, *, check: bool
) -> tuple[JsonObject, JsonObject, JsonObject, dict[str, bytes]]:
    documents: list[tuple[str, Path, Path]] = [
        ("curated", CURATED_PATH, CURATED_SCHEMA),
        ("gates", GATES_PATH, GATES_SCHEMA),
        ("transitions", TRANSITIONS_PATH, TRANSITIONS_SCHEMA),
    ]
    values: dict[str, JsonObject] = {}
    payloads: dict[str, bytes] = {}
    for name, path, schema in documents:
        value, canonical = _read_json(root / path, require_canonical=check)
        _validate_schema(root, schema, value)
        if not check:
            try:
                (root / path).write_bytes(canonical)
            except OSError as error:
                raise RegistryError(f"cannot write {path.as_posix()}") from error
        values[name] = value
        payloads[name] = canonical
    return values["curated"], values["gates"], values["transitions"], payloads


def run(
    root: Path,
    *,
    check: bool,
    require_tags: bool = False,
    base_ref: str | None = None,
    wheel: Path | None = None,
    reproduction_wheel: Path | None = None,
) -> tuple[JsonObject, JsonObject]:
    """Run generation, semantic validation, drift checks, and optional gates."""

    curated, gates, transitions, payloads = _prepare_inputs(root, check=check)
    generated = discover_generated(root)
    _validate_schema(root, GENERATED_SCHEMA, generated)
    resolved = validate_and_resolve(
        root,
        generated,
        curated,
        gates,
        transitions,
        input_bytes=payloads,
    )
    _validate_schema(root, RESOLVED_SCHEMA, resolved)
    if require_tags:
        validate_tags(root, curated, gates)
    if base_ref is not None:
        validate_base_transition(root, base_ref, resolved, transitions)
    checked_wheel = reproduction_wheel if reproduction_wheel is not None else wheel
    if checked_wheel is not None:
        validate_wheel(checked_wheel, resolved)
    if reproduction_wheel is not None:
        validate_reproduction(reproduction_wheel, resolved, root)
    outputs = ((GENERATED_PATH, generated), (RESOLVED_PATH, resolved))
    for relative_path, value in outputs:
        expected = canonical_json(value)
        path = root / relative_path
        if check:
            try:
                actual = path.read_bytes()
            except OSError as error:
                raise RegistryError(
                    f"cannot read {relative_path.as_posix()}"
                ) from error
            if actual != expected:
                raise RegistryError(
                    f"{relative_path.as_posix()}: generated output drift"
                )
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                path.write_bytes(expected)
            except OSError as error:
                raise RegistryError(
                    f"cannot write {relative_path.as_posix()}"
                ) from error
    return generated, resolved


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="check canonical inputs and output drift"
    )
    parser.add_argument(
        "--require-tags", action="store_true", help="require local release tags"
    )
    parser.add_argument("--base-ref", help="compare frozen state with a Git base ref")
    wheel_group = parser.add_mutually_exclusive_group()
    wheel_group.add_argument(
        "--check-wheel", type=Path, metavar="WHEEL", help="check exact wheel inventory"
    )
    wheel_group.add_argument(
        "--check-reproduction",
        type=Path,
        metavar="WHEEL",
        help="check wheel inventory and isolated deterministic reproduction",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line registry generator."""

    arguments = _parser().parse_args(argv)
    try:
        run(
            arguments.root,
            check=(
                arguments.check
                or arguments.check_wheel is not None
                or arguments.check_reproduction is not None
            ),
            require_tags=arguments.require_tags,
            base_ref=arguments.base_ref,
            wheel=arguments.check_wheel,
            reproduction_wheel=arguments.check_reproduction,
        )
    except RegistryError as error:
        print(f"benchmark registry error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
