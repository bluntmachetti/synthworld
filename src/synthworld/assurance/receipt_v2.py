"""Canonical inventory and schema dispatch for assurance receipt v2."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath

from pydantic import Field, field_validator

from synthworld.assurance.models import (
    ArtifactPhase,
    ArtifactSerialization,
    ExecutionReceipt,
    RunReceiptManifest,
)
from synthworld.assurance.models_v2 import (
    ArtifactDescriptorV2,
    DigestV2,
    ExecutionReceiptV2,
    ReceiptModelV2,
    RunReceiptManifestV2,
)
from synthworld.assurance.receipt import (
    MANIFEST_PATH,
    ReceiptIntegrityError,
    canonical_json_bytes,
    validate_manifest,
    write_canonical_model,
)

type AnyRunReceiptManifest = RunReceiptManifest | RunReceiptManifestV2
type AnyExecutionReceipt = ExecutionReceipt | ExecutionReceiptV2


class ArtifactSpecV2(ReceiptModelV2):
    path: str = Field(min_length=1)
    role: str = Field(min_length=1)
    phase: ArtifactPhase
    media_type: str = Field(min_length=1)
    serialization: ArtifactSerialization
    schema_version: str | None = None

    @field_validator("path")
    @classmethod
    def require_safe_canonical_relative_path(cls, value: str) -> str:
        parsed = PurePosixPath(value)
        if (
            value == "."
            or parsed.is_absolute()
            or ".." in parsed.parts
            or parsed.as_posix() != value
        ):
            raise ValueError("artifact paths must be canonical safe relative paths")
        return value


def digest_bytes_v2(payload: bytes) -> DigestV2:
    return DigestV2(value=hashlib.sha256(payload).hexdigest())


def digest_file_v2(path: Path) -> DigestV2:
    return digest_bytes_v2(path.read_bytes())


def describe_artifact_v2(root: Path, spec: ArtifactSpecV2) -> ArtifactDescriptorV2:
    payload = (root / spec.path).read_bytes()
    return ArtifactDescriptorV2(
        path=spec.path,
        role=spec.role,
        phase=spec.phase,
        media_type=spec.media_type,
        serialization=spec.serialization,
        digest=digest_bytes_v2(payload),
        byte_size=len(payload),
        schema_version=spec.schema_version,
    )


def write_manifest_last_v2(root: Path, manifest: RunReceiptManifestV2) -> None:
    declared = {item.path for item in manifest.artifacts}
    actual = {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    }
    if actual != declared:
        raise ReceiptIntegrityError(
            "manifest artifacts must exactly match the pre-manifest run files"
        )
    write_canonical_model(root / MANIFEST_PATH, manifest)


def validate_manifest_v2(root: Path) -> RunReceiptManifestV2:
    """Validate v2 canonical form, exact inventory, sizes, and every digest."""

    manifest_path = root / MANIFEST_PATH
    payload = manifest_path.read_bytes()
    try:
        manifest = RunReceiptManifestV2.model_validate_json(payload)
    except ValueError as error:
        raise ReceiptIntegrityError(
            "manifest.json does not match receipt schema 2.0.0"
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
        if digest_bytes_v2(artifact) != descriptor.digest:
            raise ReceiptIntegrityError(
                f"{descriptor.path} digest differs from manifest"
            )
        if descriptor.serialization is ArtifactSerialization.CANONICAL_JSON_V1:
            _assert_canonical_json(artifact_path, artifact)
    return manifest


def validate_manifest_dispatched(root: Path) -> AnyRunReceiptManifest:
    """Load only the explicitly supported frozen manifest lineage versions."""

    version = _schema_version((root / MANIFEST_PATH).read_bytes(), "manifest.json")
    if version == "1.0.0":
        return validate_manifest(root)
    if version == "2.0.0":
        return validate_manifest_v2(root)
    raise ReceiptIntegrityError(f"unsupported run receipt schema version: {version}")


def parse_execution_receipt(payload: bytes) -> AnyExecutionReceipt:
    version = _schema_version(payload, "execution.json")
    model: type[ExecutionReceipt] | type[ExecutionReceiptV2]
    if version == "1.0.0":
        model = ExecutionReceipt
    elif version == "2.0.0":
        model = ExecutionReceiptV2
    else:
        raise ReceiptIntegrityError(f"unsupported execution schema version: {version}")
    try:
        receipt = model.model_validate_json(payload)
    except ValueError as error:
        raise ReceiptIntegrityError(
            "execution.json does not match its dispatched schema"
        ) from error
    if payload != canonical_json_bytes(receipt):
        raise ReceiptIntegrityError("execution.json is not canonical JSON")
    return receipt


def _schema_version(payload: bytes, name: str) -> str:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise ReceiptIntegrityError(f"{name} is not a JSON object") from error
    if not isinstance(value, dict):
        raise ReceiptIntegrityError(f"{name} has no string schema_version")
    version = value.get("schema_version")
    if not isinstance(version, str):
        raise ReceiptIntegrityError(f"{name} has no string schema_version")
    return version


def _assert_canonical_json(path: Path, payload: bytes) -> None:
    try:
        value = json.loads(payload.decode("utf-8"))
        canonical = (
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (UnicodeDecodeError, ValueError) as error:
        raise ReceiptIntegrityError(f"{path.name} is not canonical JSON") from error
    if payload != canonical:
        raise ReceiptIntegrityError(f"{path.name} is not canonical JSON")


__all__ = [
    "AnyExecutionReceipt",
    "AnyRunReceiptManifest",
    "ArtifactSpecV2",
    "describe_artifact_v2",
    "digest_bytes_v2",
    "digest_file_v2",
    "parse_execution_receipt",
    "validate_manifest_dispatched",
    "validate_manifest_v2",
    "write_manifest_last_v2",
]
