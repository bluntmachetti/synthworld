"""Frozen filesystem and packaged-tree contract for Asteria C08 v2."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path

from pydantic import BaseModel

from synthworld.agentic.c08_v2.generator import generate_c08_asteria_v2
from synthworld.agentic.c08_v2.models import (
    C08_EVALUATOR_ARTIFACT,
    C08_PUBLIC_ARTIFACT,
    C08ArtifactDescriptorV2,
    C08AsteriaEvaluatorV2,
    C08AsteriaPublicInputV2,
    C08FrozenEvaluatorManifestV2,
    C08FrozenPublicManifestV2,
    C08FrozenRootManifestV2,
)
from synthworld.enterprise.canonical import canonical_json_bytes

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

type FrozenNode = Path | Traversable


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
    """Hash sorted UTF-8 paths and payload hashes, excluding named self-files."""

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


def _descriptor(path: str, payload: bytes) -> C08ArtifactDescriptorV2:
    return C08ArtifactDescriptorV2(
        path=path,
        byte_size=len(payload),
        sha256=_sha256(payload),
    )


def _public_manifest_bytes(payload: bytes) -> bytes:
    manifest = C08FrozenPublicManifestV2(
        artifact_set_digest=c08_frozen_artifact_set_digest(
            {C08_PUBLIC_ARTIFACT: payload}
        ),
        artifacts=(_descriptor(C08_PUBLIC_ARTIFACT, payload),),
    )
    return canonical_json_bytes(manifest)


def _evaluator_manifest_bytes(
    payload: bytes, public_input_digest: str
) -> bytes:
    manifest = C08FrozenEvaluatorManifestV2(
        public_input_digest=public_input_digest,
        artifact_set_digest=c08_frozen_artifact_set_digest(
            {C08_EVALUATOR_ARTIFACT: payload}
        ),
        artifacts=(_descriptor(C08_EVALUATOR_ARTIFACT, payload),),
    )
    return canonical_json_bytes(manifest)


def _root_manifest_bytes(
    files_by_path: Mapping[str, bytes],
    *,
    public_input_digest: str,
    public_artifact_set_digest: str,
    evaluator_artifact_set_digest: str,
) -> bytes:
    manifest = C08FrozenRootManifestV2(
        public_input_digest=public_input_digest,
        evaluator_public_input_digest=public_input_digest,
        public_artifact_set_digest=public_artifact_set_digest,
        evaluator_artifact_set_digest=evaluator_artifact_set_digest,
        artifact_set_digest=c08_frozen_artifact_set_digest(
            files_by_path,
            excluded_paths=(C08_FROZEN_MANIFEST,),
        ),
        artifacts=tuple(
            _descriptor(path, payload)
            for path, payload in sorted(files_by_path.items())
        ),
    )
    return canonical_json_bytes(manifest)


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
        C08_FROZEN_EVALUATOR_MANIFEST: _evaluator_manifest_bytes(
            evaluator_payload, public_input_digest
        ),
        C08_FROZEN_PUBLIC_PAYLOAD: public_payload,
        C08_FROZEN_PUBLIC_MANIFEST: _public_manifest_bytes(public_payload),
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
            all_files,
            excluded_paths=(C08_FROZEN_MANIFEST,),
        ),
    )


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
            f"{label} inventory mismatch: expected {sorted(expected)}, "
            f"got {sorted(actual)}"
        )


def _read_file(node: FrozenNode, label: str) -> bytes:
    if _is_symlink(node) or not node.is_file():
        raise C08FrozenArtifactError(f"{label} must be a regular file")
    try:
        return node.read_bytes()
    except OSError as exc:
        raise C08FrozenArtifactError(f"cannot read {label}") from exc


def _read_canonical_model[ModelT: BaseModel](
    node: FrozenNode, label: str, model: type[ModelT]
) -> tuple[bytes, ModelT]:
    payload = _read_file(node, label)
    try:
        parsed = model.model_validate_json(payload)
    except (TypeError, ValueError) as exc:
        raise C08FrozenArtifactError(f"{label} is not valid governed JSON") from exc
    if canonical_json_bytes(parsed) != payload:
        raise C08FrozenArtifactError(f"{label} is not canonical JSON")
    return payload, parsed


def _validate_tree_manifest(
    manifest: C08FrozenPublicManifestV2 | C08FrozenEvaluatorManifestV2,
    *,
    payload_name: str,
    payload: bytes,
) -> str:
    descriptor = manifest.artifacts[0]
    if (
        descriptor.path != payload_name
        or descriptor.byte_size != len(payload)
        or descriptor.sha256 != _sha256(payload)
    ):
        raise C08FrozenArtifactError("frozen tree descriptor mismatch")
    expected_digest = c08_frozen_artifact_set_digest({payload_name: payload})
    if manifest.artifact_set_digest != expected_digest:
        raise C08FrozenArtifactError("frozen tree artifact-set digest mismatch")
    return expected_digest


def _validate_root_manifest(
    manifest: C08FrozenRootManifestV2,
    files_by_path: Mapping[str, bytes],
) -> str:
    descriptors = {item.path: item for item in manifest.artifacts}
    for path, payload in files_by_path.items():
        descriptor = descriptors[path]
        if (
            descriptor.byte_size != len(payload)
            or descriptor.sha256 != _sha256(payload)
        ):
            raise C08FrozenArtifactError(f"root descriptor mismatch: {path}")
    expected_digest = c08_frozen_artifact_set_digest(
        files_by_path,
        excluded_paths=(C08_FROZEN_MANIFEST,),
    )
    if manifest.artifact_set_digest != expected_digest:
        raise C08FrozenArtifactError("root artifact-set digest mismatch")
    return expected_digest


def freeze_c08_v2_benchmark(
    output: Path = C08_FROZEN_BENCHMARK_PATH,
    *,
    replace: bool = False,
) -> C08FrozenBundle:
    """Materialize the deterministic Asteria C08 v2 frozen tree."""

    if output.exists() or output.is_symlink():
        if not replace:
            raise C08FrozenArtifactError(
                f"refusing to overwrite existing path: {output}"
            )
        _assert_directory(output, C08_FROZEN_ROOT_INVENTORY, "frozen root")
        public = output / C08_FROZEN_PUBLIC_DIR
        evaluator = output / C08_FROZEN_EVALUATOR_DIR
        _assert_directory(public, C08_FROZEN_PUBLIC_INVENTORY, "public tree")
        _assert_directory(evaluator, C08_FROZEN_EVALUATOR_INVENTORY, "evaluator tree")
        for relative_path in (
            C08_FROZEN_MANIFEST,
            C08_FROZEN_PUBLIC_PAYLOAD,
            C08_FROZEN_PUBLIC_MANIFEST,
            C08_FROZEN_EVALUATOR_PAYLOAD,
            C08_FROZEN_EVALUATOR_MANIFEST,
        ):
            _read_file(output / relative_path, relative_path)
    files_by_path, bundle = _build_frozen_files()
    write_order = (
        *sorted(path for path in files_by_path if path != C08_FROZEN_MANIFEST),
        C08_FROZEN_MANIFEST,
    )
    for relative_path in write_order:
        destination = output / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(files_by_path[relative_path])
    return bundle


def load_c08_v2_frozen_tree(root: FrozenNode) -> C08FrozenBundle:
    """Load and verify a filesystem or packaged Asteria C08 v2 tree."""

    _assert_directory(root, C08_FROZEN_ROOT_INVENTORY, "frozen root")
    public_root = _child(root, C08_FROZEN_PUBLIC_DIR)
    evaluator_root = _child(root, C08_FROZEN_EVALUATOR_DIR)
    _assert_directory(public_root, C08_FROZEN_PUBLIC_INVENTORY, "public tree")
    _assert_directory(
        evaluator_root,
        C08_FROZEN_EVALUATOR_INVENTORY,
        "evaluator tree",
    )

    public_payload, public_model = _read_canonical_model(
        _child(public_root, C08_PUBLIC_ARTIFACT),
        C08_FROZEN_PUBLIC_PAYLOAD,
        C08AsteriaPublicInputV2,
    )
    evaluator_payload, evaluator_model = _read_canonical_model(
        _child(evaluator_root, C08_EVALUATOR_ARTIFACT),
        C08_FROZEN_EVALUATOR_PAYLOAD,
        C08AsteriaEvaluatorV2,
    )
    public_manifest_payload, public_manifest = _read_canonical_model(
        _child(public_root, C08_FROZEN_MANIFEST),
        C08_FROZEN_PUBLIC_MANIFEST,
        C08FrozenPublicManifestV2,
    )
    evaluator_manifest_payload, evaluator_manifest = _read_canonical_model(
        _child(evaluator_root, C08_FROZEN_MANIFEST),
        C08_FROZEN_EVALUATOR_MANIFEST,
        C08FrozenEvaluatorManifestV2,
    )
    _, root_manifest = _read_canonical_model(
        _child(root, C08_FROZEN_MANIFEST),
        C08_FROZEN_MANIFEST,
        C08FrozenRootManifestV2,
    )

    public_digest = _sha256(public_payload)
    public_set_digest = _validate_tree_manifest(
        public_manifest,
        payload_name=C08_PUBLIC_ARTIFACT,
        payload=public_payload,
    )
    evaluator_set_digest = _validate_tree_manifest(
        evaluator_manifest,
        payload_name=C08_EVALUATOR_ARTIFACT,
        payload=evaluator_payload,
    )
    if (
        evaluator_model.public_input_digest != public_digest
        or evaluator_manifest.public_input_digest != public_digest
    ):
        raise C08FrozenArtifactError("evaluator/public digest binding mismatch")
    root_files = {
        C08_FROZEN_EVALUATOR_MANIFEST: evaluator_manifest_payload,
        C08_FROZEN_EVALUATOR_PAYLOAD: evaluator_payload,
        C08_FROZEN_PUBLIC_MANIFEST: public_manifest_payload,
        C08_FROZEN_PUBLIC_PAYLOAD: public_payload,
    }
    root_set_digest = _validate_root_manifest(root_manifest, root_files)
    if (
        root_manifest.public_input_digest != public_digest
        or root_manifest.evaluator_public_input_digest != public_digest
        or root_manifest.public_artifact_set_digest != public_set_digest
        or root_manifest.evaluator_artifact_set_digest != evaluator_set_digest
    ):
        raise C08FrozenArtifactError("root cross-artifact binding mismatch")
    generated = generate_c08_asteria_v2(C08_FROZEN_SEED)
    if (
        public_model != generated.public
        or evaluator_model != generated.evaluator
    ):
        raise C08FrozenArtifactError(
            "frozen payload does not match the fixed reference"
        )
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
