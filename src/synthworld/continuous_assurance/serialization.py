"""Physical public/evaluator split for continuous-assurance artifacts."""

from __future__ import annotations

import stat
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

from synthworld.continuous_assurance.models import (
    ContinuousAssuranceEvaluatorV1,
    ContinuousAssurancePublicV1,
)
from synthworld.continuous_assurance.replay import (
    ContinuousAssuranceIntegrityError,
    validate_continuous_assurance_evaluator,
    validate_continuous_assurance_public,
)
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.models import (
    EnterpriseArtifactDescriptorV1,
    EnterpriseArtifactManifestV1,
)

PUBLIC_CONTINUOUS_ASSURANCE_PATH = "public/continuous-assurance-input.json"
EVALUATOR_CONTINUOUS_ASSURANCE_PATH = "evaluator/continuous-assurance-evaluator.json"
MANIFEST_NAME = "manifest.json"


class ContinuousAssuranceArtifactError(ValueError):
    """Raised when a continuous-assurance artifact tree is invalid."""


def export_continuous_assurance_benchmark(
    root: Path,
    *,
    public: ContinuousAssurancePublicV1,
    evaluator: ContinuousAssuranceEvaluatorV1,
) -> None:
    """Write separately inventoried public and evaluator trees."""

    if root.exists():
        raise ContinuousAssuranceArtifactError(
            "continuous-assurance artifact root exists"
        )
    try:
        validate_continuous_assurance_evaluator(public, evaluator)
    except ContinuousAssuranceIntegrityError as error:
        raise ContinuousAssuranceArtifactError(
            "continuous-assurance artifacts are invalid"
        ) from error
    public_bytes = canonical_json_bytes(public)
    evaluator_bytes = canonical_json_bytes(evaluator)
    public_manifest = _manifest(
        "public", "continuous-assurance-input.json", public, public_bytes
    )
    evaluator_manifest = _manifest(
        "evaluator",
        "continuous-assurance-evaluator.json",
        evaluator,
        evaluator_bytes,
    )
    _write_new(root / PUBLIC_CONTINUOUS_ASSURANCE_PATH, public_bytes)
    _write_new(root / "public" / MANIFEST_NAME, canonical_json_bytes(public_manifest))
    _write_new(root / EVALUATOR_CONTINUOUS_ASSURANCE_PATH, evaluator_bytes)
    _write_new(
        root / "evaluator" / MANIFEST_NAME,
        canonical_json_bytes(evaluator_manifest),
    )


def load_public_continuous_assurance_benchmark(
    root: Path,
) -> ContinuousAssurancePublicV1:
    """Load only the public artifact tree."""

    public = _load_one(
        root / "public",
        name="continuous-assurance-input.json",
        model=ContinuousAssurancePublicV1,
        visibility="public",
    )
    try:
        validate_continuous_assurance_public(public)
    except ContinuousAssuranceIntegrityError as error:
        raise ContinuousAssuranceArtifactError(
            "continuous-assurance public bindings are invalid"
        ) from error
    return public


def load_evaluator_continuous_assurance_benchmark(
    root: Path,
) -> ContinuousAssuranceEvaluatorV1:
    """Load evaluator truth only after the public tree validates."""

    public = load_public_continuous_assurance_benchmark(root)
    evaluator = _load_one(
        root / "evaluator",
        name="continuous-assurance-evaluator.json",
        model=ContinuousAssuranceEvaluatorV1,
        visibility="evaluator",
    )
    try:
        validate_continuous_assurance_evaluator(public, evaluator)
    except ContinuousAssuranceIntegrityError as error:
        raise ContinuousAssuranceArtifactError(
            "continuous-assurance evaluator bindings are invalid"
        ) from error
    return evaluator


def _manifest(
    visibility: Literal["public", "evaluator"],
    name: str,
    model: ContinuousAssurancePublicV1 | ContinuousAssuranceEvaluatorV1,
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
        raise ContinuousAssuranceArtifactError(
            "continuous-assurance manifest visibility differs"
        )
    artifact = _read_canonical(directory / name, model)
    if len(manifest.artifacts) != 1:
        raise ContinuousAssuranceArtifactError(
            "continuous-assurance manifest must declare one artifact"
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
        raise ContinuousAssuranceArtifactError(
            "continuous-assurance manifest binding differs"
        )
    return artifact


def _read_canonical[ModelT: BaseModel](path: Path, model: type[ModelT]) -> ModelT:
    try:
        payload = path.read_bytes()
        parsed = model.model_validate_json(payload)
    except (OSError, ValueError, ValidationError) as error:
        raise ContinuousAssuranceArtifactError(
            "continuous-assurance artifact is invalid"
        ) from error
    if payload != canonical_json_bytes(parsed):
        raise ContinuousAssuranceArtifactError(
            "continuous-assurance artifact is not canonical JSON"
        )
    return parsed


def _require_exact_files(directory: Path, expected: set[str]) -> None:
    try:
        status = directory.lstat()
        if not stat.S_ISDIR(status.st_mode):
            raise ContinuousAssuranceArtifactError(
                "continuous-assurance artifact directory is not a real directory"
            )
        entries = tuple(directory.iterdir())
        actual = {item.name for item in entries}
        if actual == expected and any(
            not stat.S_ISREG(item.lstat().st_mode) for item in entries
        ):
            raise ContinuousAssuranceArtifactError(
                "continuous-assurance inventory contains a non-regular entry"
            )
    except OSError as error:
        raise ContinuousAssuranceArtifactError(
            "continuous-assurance artifact directory is unreadable"
        ) from error
    if actual != expected:
        raise ContinuousAssuranceArtifactError(
            "continuous-assurance artifact inventory differs"
        )


def _write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as destination:
        destination.write(payload)


__all__ = [
    "EVALUATOR_CONTINUOUS_ASSURANCE_PATH",
    "PUBLIC_CONTINUOUS_ASSURANCE_PATH",
    "ContinuousAssuranceArtifactError",
    "export_continuous_assurance_benchmark",
    "load_evaluator_continuous_assurance_benchmark",
    "load_public_continuous_assurance_benchmark",
]
