"""Canonical public/evaluator artifact split for enterprise-agentic smoke packs."""

from __future__ import annotations

import stat
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

from synthworld.agentic.enterprise.errors import EnterpriseAgenticArtifactError
from synthworld.agentic.enterprise.models import (
    EnterpriseAgenticEvaluatorArtifactsV1,
    EnterpriseAgenticPublicInputV1,
)
from synthworld.agentic.enterprise.projection import (
    compile_enterprise_agentic_truth,
    project_enterprise_agentic_public,
)
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.models import (
    EnterpriseArtifactDescriptorV1,
    EnterpriseArtifactManifestV1,
)

PUBLIC_ENTERPRISE_AGENTIC_PATH = "public/enterprise-agentic-input.json"
EVALUATOR_ENTERPRISE_AGENTIC_PATH = "evaluator/enterprise-agentic-evaluator.json"
MANIFEST_NAME = "manifest.json"


def export_enterprise_agentic_benchmark(
    root: Path,
    *,
    public: EnterpriseAgenticPublicInputV1,
    evaluator: EnterpriseAgenticEvaluatorArtifactsV1,
) -> None:
    """Write exactly two separately manifested visibility trees."""

    if root.exists():
        raise EnterpriseAgenticArtifactError(
            "enterprise-agentic artifact root already exists"
        )
    public_bytes = canonical_json_bytes(public)
    evaluator_bytes = canonical_json_bytes(evaluator)
    public_manifest = _manifest(
        "public", "enterprise-agentic-input.json", public, public_bytes
    )
    evaluator_manifest = _manifest(
        "evaluator",
        "enterprise-agentic-evaluator.json",
        evaluator,
        evaluator_bytes,
    )
    _write_new(root / PUBLIC_ENTERPRISE_AGENTIC_PATH, public_bytes)
    _write_new(
        root / "public" / MANIFEST_NAME,
        canonical_json_bytes(public_manifest),
    )
    _write_new(root / EVALUATOR_ENTERPRISE_AGENTIC_PATH, evaluator_bytes)
    _write_new(
        root / "evaluator" / MANIFEST_NAME,
        canonical_json_bytes(evaluator_manifest),
    )


def load_public_enterprise_agentic_benchmark(
    root: Path,
) -> EnterpriseAgenticPublicInputV1:
    """Load only the public tree and verify its deterministic projection."""

    public = _load_one(
        root / "public",
        name="enterprise-agentic-input.json",
        model=EnterpriseAgenticPublicInputV1,
        visibility="public",
    )
    try:
        reprojected = project_enterprise_agentic_public(
            access=public.access,
            snapshot=public.snapshot,
            events=public.events,
            config=public.config,
        )
    except (ValueError, ValidationError) as error:
        raise EnterpriseAgenticArtifactError(
            "enterprise-agentic public input bindings are invalid"
        ) from error
    if reprojected != public:
        raise EnterpriseAgenticArtifactError(
            "enterprise-agentic public projection differs"
        )
    return public


def load_evaluator_enterprise_agentic_benchmark(
    root: Path,
) -> EnterpriseAgenticEvaluatorArtifactsV1:
    """Load both trees and recompile evaluator truth from exact bound inputs."""

    public = load_public_enterprise_agentic_benchmark(root)
    evaluator = _load_one(
        root / "evaluator",
        name="enterprise-agentic-evaluator.json",
        model=EnterpriseAgenticEvaluatorArtifactsV1,
        visibility="evaluator",
    )
    try:
        recompiled = compile_enterprise_agentic_truth(
            public=public,
            canonical_binding_truth=evaluator.canonical_binding_truth,
            directory_rbac_truth=evaluator.directory_rbac_truth,
            abac_truth=evaluator.abac_truth,
            rebac_truth=evaluator.rebac_truth,
            access_state=evaluator.access_state,
        )
    except (ValueError, ValidationError) as error:
        raise EnterpriseAgenticArtifactError(
            "enterprise-agentic evaluator/public bindings are invalid"
        ) from error
    if recompiled != evaluator:
        raise EnterpriseAgenticArtifactError(
            "enterprise-agentic evaluator truth differs from compiled truth"
        )
    return evaluator


def _manifest(
    visibility: Literal["public", "evaluator"],
    name: str,
    model: EnterpriseAgenticPublicInputV1 | EnterpriseAgenticEvaluatorArtifactsV1,
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
        raise EnterpriseAgenticArtifactError(
            "enterprise-agentic manifest visibility differs"
        )
    artifact = _read_canonical(directory / name, model)
    if len(manifest.artifacts) != 1:
        raise EnterpriseAgenticArtifactError(
            "enterprise-agentic manifest must declare exactly one artifact"
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
        raise EnterpriseAgenticArtifactError(
            "enterprise-agentic manifest binding differs"
        )
    return artifact


def _read_canonical[ModelT: BaseModel](path: Path, model: type[ModelT]) -> ModelT:
    try:
        payload = path.read_bytes()
        parsed = model.model_validate_json(payload)
    except (OSError, ValueError, ValidationError) as error:
        raise EnterpriseAgenticArtifactError(
            "enterprise-agentic artifact is invalid"
        ) from error
    if payload != canonical_json_bytes(parsed):
        raise EnterpriseAgenticArtifactError(
            "enterprise-agentic artifact is not canonical JSON"
        )
    return parsed


def _require_exact_files(directory: Path, expected: set[str]) -> None:
    try:
        status = directory.lstat()
        if not stat.S_ISDIR(status.st_mode):
            raise EnterpriseAgenticArtifactError(
                "enterprise-agentic artifact directory is not a real directory"
            )
        entries = tuple(directory.iterdir())
        actual = {item.name for item in entries}
        if actual == expected and any(
            not stat.S_ISREG(item.lstat().st_mode) for item in entries
        ):
            raise EnterpriseAgenticArtifactError(
                "enterprise-agentic artifact inventory contains a non-regular entry"
            )
    except OSError as error:
        raise EnterpriseAgenticArtifactError(
            "enterprise-agentic artifact directory is unreadable"
        ) from error
    if actual != expected:
        raise EnterpriseAgenticArtifactError(
            "enterprise-agentic artifact directory inventory differs"
        )


def _write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as destination:
        destination.write(payload)


__all__ = [
    "EVALUATOR_ENTERPRISE_AGENTIC_PATH",
    "PUBLIC_ENTERPRISE_AGENTIC_PATH",
    "export_enterprise_agentic_benchmark",
    "load_evaluator_enterprise_agentic_benchmark",
    "load_public_enterprise_agentic_benchmark",
]
