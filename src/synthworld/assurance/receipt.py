"""Generic product staging, canonical serialization, and receipt verification."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, Field

from synthworld.assurance.models import (
    AdapterProvenance,
    ArtifactDescriptor,
    ArtifactPhase,
    ArtifactSerialization,
    Digest,
    ExecutionReceipt,
    ExecutionStatus,
    RepositoryProvenance,
    RunReceiptManifest,
    TreeState,
)
from synthworld.models import SyntheticModel

SOURCE_PUBLIC_PATH = "source-public.json"
PRODUCT_INPUT_PATH = "product-input.json"
PRODUCT_OUTPUT_PATH = "product-output.json"
EXECUTION_PATH = "execution.json"
MANIFEST_PATH = "manifest.json"

PublicAdapter = Callable[[bytes], bytes]
ProductRunner = Callable[[Path, Path], int]


class ProductStageError(RuntimeError):
    """Raised when a product stage cannot produce a complete execution receipt."""


class ReceiptIntegrityError(ValueError):
    """Raised when a receipt is incomplete, noncanonical, or digest-inconsistent."""


class ArtifactSpec(SyntheticModel):
    """An expected receipt artifact before its bytes are digested."""

    path: str = Field(min_length=1)
    role: str = Field(min_length=1)
    phase: ArtifactPhase
    media_type: str = Field(min_length=1)
    serialization: ArtifactSerialization
    schema_version: str | None = None


def canonical_json_bytes(model: BaseModel) -> bytes:
    """Serialize a model as sorted UTF-8 JSON, LF, and one trailing newline."""

    return (
        json.dumps(
            model.model_dump(mode="json"),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _canonical_json_value_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def digest_bytes(payload: bytes) -> Digest:
    return Digest(value=hashlib.sha256(payload).hexdigest())


def digest_file(path: Path) -> Digest:
    return digest_bytes(path.read_bytes())


def write_canonical_model(path: Path, model: BaseModel) -> None:
    """Create a canonical model artifact without overwriting prior evidence."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as destination:
        destination.write(canonical_json_bytes(model))


def _write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as destination:
        destination.write(payload)


def run_product_stage(
    root: Path,
    *,
    source_public: bytes,
    adapter: PublicAdapter,
    runner: ProductRunner,
    adapter_provenance: AdapterProvenance,
    callable_identifier: str,
) -> ExecutionReceipt:
    """Run an adapter and product with no bundle or evaluator object in the API.

    The runner receives exactly the product input path and output destination.  At
    invocation time the receipt root contains only public product-phase material;
    no truth or normalized submission path has been created.
    """

    if root.exists():
        raise ProductStageError("a run receipt root must not already exist")
    root.mkdir(parents=True)

    source_path = root / SOURCE_PUBLIC_PATH
    input_path = root / PRODUCT_INPUT_PATH
    output_path = root / PRODUCT_OUTPUT_PATH
    _write_new(source_path, source_public)
    product_input = adapter(source_public)
    _write_new(input_path, product_input)

    exit_code = runner(input_path, output_path)
    if not output_path.is_file():
        raise ProductStageError("the product runner did not create its output file")
    output = output_path.read_bytes()
    status = ExecutionStatus.SUCCEEDED if exit_code == 0 else ExecutionStatus.FAILED
    execution = ExecutionReceipt(
        boundary=adapter_provenance.boundary,
        callable_identifier=callable_identifier,
        adapter_name=adapter_provenance.name,
        adapter_version=adapter_provenance.version,
        adapter_source_digest=adapter_provenance.source_digest,
        source_public_digest=digest_bytes(source_public),
        product_input_digest=digest_bytes(product_input),
        product_output_digest=digest_bytes(output),
        exit_code=exit_code,
        status=status,
    )
    write_canonical_model(root / EXECUTION_PATH, execution)
    return execution


def describe_artifact(root: Path, spec: ArtifactSpec) -> ArtifactDescriptor:
    path = root / spec.path
    payload = path.read_bytes()
    return ArtifactDescriptor(
        path=spec.path,
        role=spec.role,
        phase=spec.phase,
        media_type=spec.media_type,
        serialization=spec.serialization,
        digest=digest_bytes(payload),
        byte_size=len(payload),
        schema_version=spec.schema_version,
    )


def write_manifest_last(root: Path, manifest: RunReceiptManifest) -> None:
    """Verify the final artifact inventory and create the non-self-digested index."""

    declared = {item.path for item in manifest.artifacts}
    actual = {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    }
    if actual != declared:
        raise ReceiptIntegrityError(
            "manifest artifacts must exactly match the pre-manifest run files"
        )
    write_canonical_model(root / MANIFEST_PATH, manifest)


def _assert_canonical_json(path: Path, payload: bytes) -> None:
    try:
        value = json.loads(payload.decode("utf-8"))
        canonical = _canonical_json_value_bytes(value)
    except (UnicodeDecodeError, ValueError) as error:
        raise ReceiptIntegrityError(f"{path.name} is not canonical JSON") from error
    if payload != canonical:
        raise ReceiptIntegrityError(f"{path.name} is not canonical JSON")


def validate_manifest(root: Path) -> RunReceiptManifest:
    """Validate canonical form, exact inventory, byte sizes, and every digest."""

    manifest_path = root / MANIFEST_PATH
    payload = manifest_path.read_bytes()
    try:
        manifest = RunReceiptManifest.model_validate_json(payload)
    except ValueError as error:
        raise ReceiptIntegrityError(
            "manifest.json does not match its schema"
        ) from error
    if payload != canonical_json_bytes(manifest):
        raise ReceiptIntegrityError("manifest.json is not canonical JSON")

    declared = {item.path for item in manifest.artifacts}
    actual = {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    }
    if actual != declared | {MANIFEST_PATH}:
        raise ReceiptIntegrityError("the run artifact inventory differs from manifest")

    for descriptor in manifest.artifacts:
        artifact_path = root / descriptor.path
        artifact = artifact_path.read_bytes()
        if len(artifact) != descriptor.byte_size:
            raise ReceiptIntegrityError(
                f"{descriptor.path} byte size differs from manifest"
            )
        if digest_bytes(artifact) != descriptor.digest:
            raise ReceiptIntegrityError(
                f"{descriptor.path} digest differs from manifest"
            )
        if descriptor.serialization is ArtifactSerialization.CANONICAL_JSON_V1:
            _assert_canonical_json(artifact_path, artifact)
    return manifest


def _git(repo: Path, *arguments: str) -> bytes:
    return subprocess.run(  # noqa: S603 - fixed Git arguments
        ["git", *arguments],  # noqa: S607 - resolved from the caller's PATH
        cwd=repo,
        check=True,
        capture_output=True,
    ).stdout


def _digest_dirty_tree(
    repo: Path, patch: bytes, untracked: tuple[bytes, ...]
) -> Digest:
    hasher = hashlib.sha256()
    hasher.update(b"synthworld-git-tree-v1\0")
    hasher.update(len(patch).to_bytes(8, "big"))
    hasher.update(patch)
    for encoded_path in untracked:
        content = (repo / encoded_path.decode("utf-8")).read_bytes()
        hasher.update(len(encoded_path).to_bytes(8, "big"))
        hasher.update(encoded_path)
        hasher.update(len(content).to_bytes(8, "big"))
        hasher.update(content)
    return Digest(value=hasher.hexdigest())


def capture_repository_provenance(repo: Path, *, name: str) -> RepositoryProvenance:
    """Bind a Git revision and, when dirty, a deterministic patch/tree digest."""

    revision = _git(repo, "rev-parse", "HEAD").decode("ascii").strip()
    patch = _git(repo, "diff", "--binary", "HEAD", "--no-ext-diff")
    untracked = tuple(
        sorted(
            item
            for item in _git(
                repo, "ls-files", "--others", "--exclude-standard", "-z"
            ).split(b"\0")
            if item
        )
    )
    if not patch and not untracked:
        return RepositoryProvenance(
            name=name,
            revision=revision,
            tree_state=TreeState.CLEAN,
        )
    return RepositoryProvenance(
        name=name,
        revision=revision,
        tree_state=TreeState.DIRTY,
        tree_digest=_digest_dirty_tree(repo, patch, untracked),
    )


__all__ = [
    "EXECUTION_PATH",
    "MANIFEST_PATH",
    "PRODUCT_INPUT_PATH",
    "PRODUCT_OUTPUT_PATH",
    "SOURCE_PUBLIC_PATH",
    "ArtifactSpec",
    "ProductRunner",
    "ProductStageError",
    "PublicAdapter",
    "ReceiptIntegrityError",
    "canonical_json_bytes",
    "capture_repository_provenance",
    "describe_artifact",
    "digest_bytes",
    "digest_file",
    "run_product_stage",
    "validate_manifest",
    "write_canonical_model",
    "write_manifest_last",
]
