"""Frozen filesystem and packaged-tree contract for Asteria C08 v2."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import TypeAlias

from synthworld.agentic.c08_v2.generator import generate_c08_asteria_v2
from synthworld.agentic.c08_v2.models import (
    C08AsteriaEvaluatorV2,
    C08AsteriaPublicInputV2,
    C08_BENCHMARK_ID,
    C08_EVALUATOR_ARTIFACT,
    C08_PUBLIC_ARTIFACT,
    C08_SCHEMA_VERSION,
)
from synthworld.enterprise.canonical import canonical_json_bytes, canonical_json_value_bytes

C08_FROZEN_SEED = 20260809
C08_FROZEN_BENCHMARK_PATH = Path("src/synthworld/benchmarks/asteria-agentic-c08-v2")
C08_FROZEN_DIGEST_ALGORITHM = "sha256-path-bound-v1"
C08_FROZEN_MANIFEST = "manifest.json"
C08_FROZEN_PUBLIC_DIR = "public"
C08_FROZEN_EVALUATOR_DIR = "evaluator"
C08_FROZEN_PUBLIC_PAYLOAD = f"{C08_FROZEN_PUBLIC_DIR}/{C08_PUBLIC_ARTIFACT}"
C08_FROZEN_EVALUATOR_PAYLOAD = f"{C08_FROZEN_EVALUATOR_DIR}/{C08_EVALUATOR_ARTIFACT}"
C08_FROZEN_PUBLIC_MANIFEST = f"{C08_FROZEN_PUBLIC_DIR}/{C08_FROZEN_MANIFEST}"
C08_FROZEN_EVALUATOR_MANIFEST = f"{C08_FROZEN_EVALUATOR_DIR}/{C08_FROZEN_MANIFEST}"
C08_FROZEN_ROOT_INVENTORY = (
    C08_FROZEN_EVALUATOR_DIR,
    C08_FROZEN_MANIFEST,
    C08_FROZEN_PUBLIC_DIR,
)
C08_FROZEN_PUBLIC_INVENTORY = (C08_FROZEN_MANIFEST, C08_PUBLIC_ARTIFACT)
C08_FROZEN_EVALUATOR_INVENTORY = (C08_FROZEN_MANIFEST, C08_EVALUATOR_ARTIFACT)

FrozenNode: TypeAlias = Path | Traversable


class C08FrozenArtifactError(ValueError):
    """Raised when a frozen C08 artifact tree violates its contract."""


@dataclass(frozen=True, slots=True)
class C08FrozenBundle:
    """Loaded frozen public/evaluator artifacts and their verified digests."""

    public: C08AsteriaPublicInputV2
    evaluator: C08AsteriaEvaluatorV2
    public_input_digest: str
    public_artifact_set_digest: str
    evaluator_artifact_set_digest: str
    root_artifact_set_digest: str


def c08_frozen_artifact_set_digest(
    files_by_path: Mapping[str, bytes], *, excluded_paths: Iterable[str] = ()
) -> str:
    """Return the canonical path-bound digest for a set of file payloads."""

    excluded = frozenset(excluded_paths)
    digest = hashlib.sha256()
    for path in sorted(files_by_path):
        if path in excluded:
            continue
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(files_by_path[path]).digest())
    return digest.hexdigest()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _descriptor(payload: bytes) -> dict[str, int | str]:
    return {"byte_size": len(payload), "sha256": _sha256(payload)}


def _manifest_bytes(
    *,
    artifact_path: str,
    payload: bytes,
    visibility: str,
    public_input_digest: str | None = None,
) -> bytes:
    payload_name = artifact_path.rsplit("/", 1)[-1]
    manifest: dict[str, object] = {
        "artifact_set_digest": c08_frozen_artifact_set_digest({payload_name: payload}),
        "artifacts": {payload_name: _descriptor(payload)},
        "benchmark_id": C08_BENCHMARK_ID,
        "schema_version": C08_SCHEMA_VERSION,
        "seed": C08_FROZEN_SEED,
        "synthetic": True,
        "visibility": visibility,
    }
    if public_input_digest is not None:
        manifest["public_input_digest"] = public_input_digest
    return canonical_json_value_bytes(manifest)


def _root_manifest_bytes(
    files_by_path: Mapping[str, bytes],
    *,
    public_input_digest: str,
    public_artifact_set_digest: str,
    evaluator_artifact_set_digest: str,
) -> bytes:
    artifacts = {
        path: _descriptor(payload)
        for path, payload in sorted(files_by_path.items())
    }
    manifest = {
        "artifact_set_digest": c08_frozen_artifact_set_digest(
            files_by_path, excluded_paths=(C08_FROZEN_MANIFEST,)
        ),
        "artifacts": artifacts,
        "benchmark_id": C08_BENCHMARK_ID,
        "evaluator_artifact_set_digest": evaluator_artifact_set_digest,
        "evaluator_public_input_digest": public_input_digest,
        "public_artifact_set_digest": public_artifact_set_digest,
        "public_input_digest": public_input_digest,
        "schema_version": C08_SCHEMA_VERSION,
        "seed": C08_FROZEN_SEED,
        "synthetic": True,
        "visibility": "root",
    }
    return canonical_json_value_bytes(manifest)


def _build_frozen_files() -> tuple[dict[str, bytes], C08FrozenBundle]:
    generated = generate_c08_asteria_v2(C08_FROZEN_SEED)
    public_payload = canonical_json_bytes(generated.public)
    evaluator_payload = canonical_json_bytes(generated.evaluator)
    public_input_digest = _sha256(public_payload)
    public_artifact_set_digest = c08_frozen_artifact_set_digest(
        {C08_PUBLIC_ARTIFACT: public_payload}
    )
    evaluator_artifact_set_digest = c08_frozen_artifact_set_digest(
        {C08_EVALUATOR_ARTIFACT: evaluator_payload}
    )
    files_by_path = {
        C08_FROZEN_EVALUATOR_PAYLOAD: evaluator_payload,
        C08_FROZEN_EVALUATOR_MANIFEST: _manifest_bytes(
            artifact_path=C08_FROZEN_EVALUATOR_PAYLOAD,
            payload=evaluator_payload,
            visibility="evaluator",
            public_input_digest=public_input_digest,
        ),
        C08_FROZEN_PUBLIC_PAYLOAD: public_payload,
        C08_FROZEN_PUBLIC_MANIFEST: _manifest_bytes(
            artifact_path=C08_FROZEN_PUBLIC_PAYLOAD,
            payload=public_payload,
            visibility="public",
        ),
    }
    root_manifest = _root_manifest_bytes(
        files_by_path,
        public_input_digest=public_input_digest,
        public_artifact_set_digest=public_artifact_set_digest,
        evaluator_artifact_set_digest=evaluator_artifact_set_digest,
    )
    all_files = {C08_FROZEN_MANIFEST: root_manifest, **files_by_path}
    return all_files, C08FrozenBundle(
        public=generated.public,
        evaluator=generated.evaluator,
        public_input_digest=public_input_digest,
        public_artifact_set_digest=public_artifact_set_digest,
        evaluator_artifact_set_digest=evaluator_artifact_set_digest,
        root_artifact_set_digest=c08_frozen_artifact_set_digest(
            all_files, excluded_paths=(C08_FROZEN_MANIFEST,)
        ),
    )


def freeze_c08_v2_benchmark(
    output: Path = C08_FROZEN_BENCHMARK_PATH,
) -> C08FrozenBundle:
    """Materialize the deterministic Asteria C08 v2 frozen tree."""

    if output.exists() or output.is_symlink():
        raise C08FrozenArtifactError(f"refusing to overwrite existing path: {output}")
    files_by_path, bundle = _build_frozen_files()
    for relative_path, payload in sorted(files_by_path.items()):
        destination = output / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
    return bundle


def _is_symlink(node: FrozenNode) -> bool:
    return isinstance(node, Path) and node.is_symlink()


def _child(node: FrozenNode, name: str) -> FrozenNode:
    if isinstance(node, Path):
        return node / name
    return node.joinpath(name)


def _assert_directory(node: FrozenNode, expected: tuple[str, ...], label: str) -> None:
    if _is_symlink(node) or not node.is_dir():
        raise C08FrozenArtifactError(f"{label} must be a real directory")
    actual = {child.name for child in node.iterdir()}
    if actual != set(expected):
        raise C08FrozenArtifactError(
            f"{label} inventory mismatch: expected {sorted(expected)}, got {sorted(actual)}"
        )


def _read_file(node: FrozenNode, label: str) -> bytes:
    if _is_symlink(node) or not node.is_file():
        raise C08FrozenArtifactError(f"{label} must be a regular file")
    try:
        return node.read_bytes()
    except OSError as exc:
        raise C08FrozenArtifactError(f"cannot read {label}") from exc


def _canonical_document(payload: bytes, label: str) -> dict[str, object]:
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise C08FrozenArtifactError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(document, dict):
        raise C08FrozenArtifactError(f"{label} must contain a JSON object")
    if canonical_json_value_bytes(document) != payload:
        raise C08FrozenArtifactError(f"{label} is not canonical JSON")
    return document


def _require_document_keys(
    document: dict[str, object], expected: frozenset[str], label: str
) -> None:
    if frozenset(document) != expected:
        raise C08FrozenArtifactError(f"{label} has an invalid field set")


def _validate_descriptor(
    descriptor: object, payload: bytes, label: str
) -> None:
    if not isinstance(descriptor, dict):
        raise C08FrozenArtifactError(f"{label} descriptor must be an object")
    if frozenset(descriptor) != frozenset(("byte_size", "sha256")):
        raise C08FrozenArtifactError(f"{label} descriptor has an invalid field set")
    if descriptor["byte_size"] != len(payload) or descriptor["sha256"] != _sha256(payload):
        raise C08FrozenArtifactError(f"{label} descriptor does not match its payload")


def _validate_tree_manifest(
    document: dict[str, object],
    *,
    payload_name: str,
    payload: bytes,
    visibility: str,
    public_input_digest: str | None,
) -> str:
    expected = {"artifact_set_digest", "artifacts", "benchmark_id", "schema_version", "seed", "synthetic", "visibility"}
    if public_input_digest is not None:
        expected.add("public_input_digest")
    _require_document_keys(document, frozenset(expected), f"{visibility} manifest")
    if (
        document["benchmark_id"] != C08_BENCHMARK_ID
        or document["schema_version"] != C08_SCHEMA_VERSION
        or document["seed"] != C08_FROZEN_SEED
        or document["synthetic"] is not True
        or document["visibility"] != visibility
    ):
        raise C08FrozenArtifactError(f"{visibility} manifest metadata mismatch")
    artifacts = document["artifacts"]
    if not isinstance(artifacts, dict) or frozenset(artifacts) != frozenset((payload_name,)):
        raise C08FrozenArtifactError(f"{visibility} manifest inventory mismatch")
    _validate_descriptor(artifacts[payload_name], payload, f"{visibility}/{payload_name}")
    expected_digest = c08_frozen_artifact_set_digest({payload_name: payload})
    if document["artifact_set_digest"] != expected_digest:
        raise C08FrozenArtifactError(f"{visibility} artifact-set digest mismatch")
    if public_input_digest is not None and document["public_input_digest"] != public_input_digest:
        raise C08FrozenArtifactError("evaluator/public digest binding mismatch")
    return expected_digest


def _validate_root_manifest(
    document: dict[str, object], files_by_path: Mapping[str, bytes]
) -> str:
    expected = {
        "artifact_set_digest",
        "artifacts",
        "benchmark_id",
        "evaluator_artifact_set_digest",
        "evaluator_public_input_digest",
        "public_artifact_set_digest",
        "public_input_digest",
        "schema_version",
        "seed",
        "synthetic",
        "visibility",
    }
    _require_document_keys(document, frozenset(expected), "root manifest")
    if (
        document["benchmark_id"] != C08_BENCHMARK_ID
        or document["schema_version"] != C08_SCHEMA_VERSION
        or document["seed"] != C08_FROZEN_SEED
        or document["synthetic"] is not True
        or document["visibility"] != "root"
    ):
        raise C08FrozenArtifactError("root manifest metadata mismatch")
    artifacts = document["artifacts"]
    if not isinstance(artifacts, dict) or frozenset(artifacts) != frozenset(files_by_path):
        raise C08FrozenArtifactError("root manifest inventory mismatch")
    for path, payload in files_by_path.items():
        _validate_descriptor(artifacts[path], payload, path)
    expected_digest = c08_frozen_artifact_set_digest(
        files_by_path, excluded_paths=(C08_FROZEN_MANIFEST,)
    )
    if document["artifact_set_digest"] != expected_digest:
        raise C08FrozenArtifactError("root artifact-set digest mismatch")
    return expected_digest


def load_c08_v2_frozen_tree(root: FrozenNode) -> C08FrozenBundle:
    """Load and verify a filesystem or packaged Asteria C08 v2 tree."""

    _assert_directory(root, C08_FROZEN_ROOT_INVENTORY, "frozen root")
    public = _child(root, C08_FROZEN_PUBLIC_DIR)
    evaluator = _child(root, C08_FROZEN_EVALUATOR_DIR)
    _assert_directory(public, C08_FROZEN_PUBLIC_INVENTORY, "public tree")
    _assert_directory(evaluator, C08_FROZEN_EVALUATOR_INVENTORY, "evaluator tree")

    public_payload = _read_file(_child(public, C08_PUBLIC_ARTIFACT), C08_FROZEN_PUBLIC_PAYLOAD)
    evaluator_payload = _read_file(
        _child(evaluator, C08_EVALUATOR_ARTIFACT), C08_FROZEN_EVALUATOR_PAYLOAD
    )
    public_manifest = _canonical_document(
        _read_file(_child(public, C08_FROZEN_MANIFEST), C08_FROZEN_PUBLIC_MANIFEST),
        C08_FROZEN_PUBLIC_MANIFEST,
    )
    evaluator_manifest = _canonical_document(
        _read_file(_child(evaluator, C08_FROZEN_MANIFEST), C08_FROZEN_EVALUATOR_MANIFEST),
        C08_FROZEN_EVALUATOR_MANIFEST,
    )
    root_payload = _read_file(_child(root, C08_FROZEN_MANIFEST), C08_FROZEN_MANIFEST)
    root_manifest = _canonical_document(root_payload, C08_FROZEN_MANIFEST)

    public_document = _canonical_document(public_payload, C08_FROZEN_PUBLIC_PAYLOAD)
    evaluator_document = _canonical_document(evaluator_payload, C08_FROZEN_EVALUATOR_PAYLOAD)
    public_model = C08AsteriaPublicInputV2.model_validate(public_document)
    evaluator_model = C08AsteriaEvaluatorV2.model_validate(evaluator_document)
    public_digest = _sha256(public_payload)
    public_set_digest = _validate_tree_manifest(
        public_manifest,
        payload_name=C08_PUBLIC_ARTIFACT,
        payload=public_payload,
        visibility="public",
        public_input_digest=None,
    )
    evaluator_set_digest = _validate_tree_manifest(
        evaluator_manifest,
        payload_name=C08_EVALUATOR_ARTIFACT,
        payload=evaluator_payload,
        visibility="evaluator",
        public_input_digest=public_digest,
    )
    if evaluator_model.public_input_digest != public_digest:
        raise C08FrozenArtifactError("evaluator/public digest binding mismatch")
    root_files = {
        C08_FROZEN_EVALUATOR_MANIFEST: _read_file(
            _child(evaluator, C08_FROZEN_MANIFEST), C08_FROZEN_EVALUATOR_MANIFEST
        ),
        C08_FROZEN_EVALUATOR_PAYLOAD: evaluator_payload,
        C08_FROZEN_PUBLIC_MANIFEST: _read_file(
            _child(public, C08_FROZEN_MANIFEST), C08_FROZEN_PUBLIC_MANIFEST
        ),
        C08_FROZEN_PUBLIC_PAYLOAD: public_payload,
    }
    root_set_digest = _validate_root_manifest(root_manifest, root_files)
    if (
        root_manifest["public_input_digest"] != public_digest
        or root_manifest["evaluator_public_input_digest"] != public_digest
        or root_manifest["public_artifact_set_digest"] != public_set_digest
        or root_manifest["evaluator_artifact_set_digest"] != evaluator_set_digest
    ):
        raise C08FrozenArtifactError("root cross-artifact binding mismatch")
    generated = generate_c08_asteria_v2(C08_FROZEN_SEED)
    if public_model != generated.public or evaluator_model != generated.evaluator:
        raise C08FrozenArtifactError("frozen payload does not match the fixed reference")
    return C08FrozenBundle(
        public=public_model,
        evaluator=evaluator_model,
        public_input_digest=public_digest,
        public_artifact_set_digest=public_set_digest,
        evaluator_artifact_set_digest=evaluator_set_digest,
        root_artifact_set_digest=root_set_digest,
    )


def load_packaged_c08_v2_benchmark() -> C08FrozenBundle:
    """Load the Asteria C08 v2 tree through package resources."""

    return load_c08_v2_frozen_tree(
        files("synthworld.benchmarks").joinpath("asteria-agentic-c08-v2")
    )
