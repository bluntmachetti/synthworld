"""Canonical physical split for identity-fabric public and evaluator artifacts."""

from __future__ import annotations

import stat
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.identity_fabric.models import (
    EnterpriseIdentityFabricEvaluatorArtifactsV1,
    EnterpriseIdentityFabricPublicInputV1,
)
from synthworld.enterprise.identity_fabric.projection import (
    compile_enterprise_identity_fabric_truth,
    project_enterprise_identity_fabric_public,
)
from synthworld.enterprise.models import (
    EnterpriseArtifactDescriptorV1,
    EnterpriseArtifactManifestV1,
)

PUBLIC_IDENTITY_FABRIC_PATH = "public/identity-fabric-input.json"
EVALUATOR_IDENTITY_FABRIC_PATH = "evaluator/identity-fabric-evaluator.json"
MANIFEST_NAME = "manifest.json"


class EnterpriseIdentityFabricArtifactError(ValueError):
    """Raised for missing, unexpected, noncanonical, or unbound artifacts."""


def export_enterprise_identity_fabric(
    root: Path,
    *,
    public: EnterpriseIdentityFabricPublicInputV1,
    evaluator: EnterpriseIdentityFabricEvaluatorArtifactsV1,
) -> None:
    if root.exists():
        raise EnterpriseIdentityFabricArtifactError(
            "enterprise identity-fabric artifact root already exists"
        )
    public_bytes = canonical_json_bytes(public)
    evaluator_bytes = canonical_json_bytes(evaluator)
    public_manifest = _manifest(
        "public", "identity-fabric-input.json", public, public_bytes
    )
    evaluator_manifest = _manifest(
        "evaluator",
        "identity-fabric-evaluator.json",
        evaluator,
        evaluator_bytes,
    )
    _write_new(root / PUBLIC_IDENTITY_FABRIC_PATH, public_bytes)
    _write_new(
        root / "public" / MANIFEST_NAME,
        canonical_json_bytes(public_manifest),
    )
    _write_new(root / EVALUATOR_IDENTITY_FABRIC_PATH, evaluator_bytes)
    _write_new(
        root / "evaluator" / MANIFEST_NAME,
        canonical_json_bytes(evaluator_manifest),
    )


def load_public_enterprise_identity_fabric(
    root: Path,
) -> EnterpriseIdentityFabricPublicInputV1:
    public = _load_one(
        root / "public",
        name="identity-fabric-input.json",
        model=EnterpriseIdentityFabricPublicInputV1,
        visibility="public",
    )
    try:
        reprojected = project_enterprise_identity_fabric_public(
            invariant=public.invariant,
            checkpoints=public.checkpoints,
        )
    except (ValueError, ValidationError) as error:
        raise EnterpriseIdentityFabricArtifactError(
            "identity-fabric public input bindings are invalid"
        ) from error
    if reprojected != public:
        raise EnterpriseIdentityFabricArtifactError(
            "identity-fabric public query projection differs"
        )
    return public


def load_evaluator_enterprise_identity_fabric(
    root: Path,
) -> EnterpriseIdentityFabricEvaluatorArtifactsV1:
    public = load_public_enterprise_identity_fabric(root)
    evaluator = _load_one(
        root / "evaluator",
        name="identity-fabric-evaluator.json",
        model=EnterpriseIdentityFabricEvaluatorArtifactsV1,
        visibility="evaluator",
    )
    try:
        recompiled = compile_enterprise_identity_fabric_truth(
            public=public,
            canonical_binding_truth=evaluator.canonical_binding_truth,
            checkpoints=evaluator.checkpoints,
        )
    except (ValueError, ValidationError) as error:
        raise EnterpriseIdentityFabricArtifactError(
            "identity-fabric evaluator/public bindings are invalid"
        ) from error
    if recompiled != evaluator:
        raise EnterpriseIdentityFabricArtifactError(
            "identity-fabric evaluator truth differs from compiled truth"
        )
    return evaluator


def _manifest(
    visibility: Literal["public", "evaluator"],
    name: str,
    model: EnterpriseIdentityFabricPublicInputV1
    | EnterpriseIdentityFabricEvaluatorArtifactsV1,
    payload: bytes,
) -> EnterpriseArtifactManifestV1:
    return EnterpriseArtifactManifestV1(
        visibility=visibility,
        artifacts=(
            EnterpriseArtifactDescriptorV1(
                path=name,
                schema_version=model.schema_version,
                digest=synthetic_digest(payload),
                byte_size=len(payload),
            ),
        ),
    )


def _load_one[ModelT: BaseModel](
    directory: Path,
    *,
    name: str,
    model: type[ModelT],
    visibility: Literal["public", "evaluator"],
) -> ModelT:
    _require_exact_files(directory, {name, MANIFEST_NAME})
    manifest = _read_canonical(directory / MANIFEST_NAME, EnterpriseArtifactManifestV1)
    if manifest.visibility != visibility:
        raise EnterpriseIdentityFabricArtifactError(
            "identity-fabric manifest visibility differs"
        )
    artifact = _read_canonical(directory / name, model)
    if len(manifest.artifacts) != 1:
        raise EnterpriseIdentityFabricArtifactError(
            "identity-fabric manifest must declare exactly one artifact"
        )
    descriptor = manifest.artifacts[0]
    payload = canonical_json_bytes(artifact)
    schema_version = artifact.model_dump().get("schema_version")
    if (
        descriptor.path != name
        or descriptor.schema_version != schema_version
        or descriptor.byte_size != len(payload)
        or descriptor.digest != synthetic_digest(payload)
    ):
        raise EnterpriseIdentityFabricArtifactError(
            "identity-fabric manifest binding differs"
        )
    return artifact


def _read_canonical[ModelT: BaseModel](path: Path, model: type[ModelT]) -> ModelT:
    try:
        payload = path.read_bytes()
        parsed = model.model_validate_json(payload)
    except (OSError, ValueError, ValidationError) as error:
        raise EnterpriseIdentityFabricArtifactError(
            "enterprise identity-fabric artifact is invalid"
        ) from error
    if payload != canonical_json_bytes(parsed):
        raise EnterpriseIdentityFabricArtifactError(
            "enterprise identity-fabric artifact is not canonical JSON"
        )
    return parsed


def _require_exact_files(directory: Path, expected: set[str]) -> None:
    try:
        status = directory.lstat()
        if not stat.S_ISDIR(status.st_mode):
            raise EnterpriseIdentityFabricArtifactError(
                "identity-fabric artifact directory is not a real directory"
            )
        entries = tuple(directory.iterdir())
        actual = {item.name for item in entries}
        if actual == expected and any(
            not stat.S_ISREG(item.lstat().st_mode) for item in entries
        ):
            raise EnterpriseIdentityFabricArtifactError(
                "identity-fabric artifact inventory contains a non-regular entry"
            )
    except OSError as error:
        raise EnterpriseIdentityFabricArtifactError(
            "identity-fabric artifact directory is unreadable"
        ) from error
    if actual != expected:
        raise EnterpriseIdentityFabricArtifactError(
            "identity-fabric artifact directory inventory differs"
        )


def _write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as destination:
        destination.write(payload)


__all__ = [
    "EVALUATOR_IDENTITY_FABRIC_PATH",
    "PUBLIC_IDENTITY_FABRIC_PATH",
    "EnterpriseIdentityFabricArtifactError",
    "export_enterprise_identity_fabric",
    "load_evaluator_enterprise_identity_fabric",
    "load_public_enterprise_identity_fabric",
]
