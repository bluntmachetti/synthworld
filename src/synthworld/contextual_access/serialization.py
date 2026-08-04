"""Canonical public/evaluator artifact split for contextual-access benchmarks."""

from __future__ import annotations

import stat
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

from synthworld.contextual_access.models import (
    ContextualAccessEvaluatorV1,
    ContextualAccessPublicV1,
)
from synthworld.contextual_access.projection import (
    ContextualAccessIntegrityError,
    compile_contextual_access_truth,
    validate_contextual_access_public,
)
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.models import (
    EnterpriseArtifactDescriptorV1,
    EnterpriseArtifactManifestV1,
)

PUBLIC_CONTEXTUAL_ACCESS_PATH = "public/contextual-access-input.json"
EVALUATOR_CONTEXTUAL_ACCESS_PATH = "evaluator/contextual-access-evaluator.json"
MANIFEST_NAME = "manifest.json"


class ContextualAccessArtifactError(ValueError):
    """Raised when a contextual artifact tree fails its physical contract."""


def export_contextual_access_benchmark(
    root: Path,
    *,
    public: ContextualAccessPublicV1,
    evaluator: ContextualAccessEvaluatorV1,
) -> None:
    """Write exactly two separately manifested visibility trees."""

    if root.exists():
        raise ContextualAccessArtifactError("contextual-access artifact root exists")
    public_bytes = canonical_json_bytes(public)
    evaluator_bytes = canonical_json_bytes(evaluator)
    public_manifest = _manifest(
        "public", "contextual-access-input.json", public, public_bytes
    )
    evaluator_manifest = _manifest(
        "evaluator",
        "contextual-access-evaluator.json",
        evaluator,
        evaluator_bytes,
    )
    _write_new(root / PUBLIC_CONTEXTUAL_ACCESS_PATH, public_bytes)
    _write_new(root / "public" / MANIFEST_NAME, canonical_json_bytes(public_manifest))
    _write_new(root / EVALUATOR_CONTEXTUAL_ACCESS_PATH, evaluator_bytes)
    _write_new(
        root / "evaluator" / MANIFEST_NAME,
        canonical_json_bytes(evaluator_manifest),
    )


def load_public_contextual_access_benchmark(root: Path) -> ContextualAccessPublicV1:
    """Load and validate only the public visibility tree."""

    public = _load_one(
        root / "public",
        name="contextual-access-input.json",
        model=ContextualAccessPublicV1,
        visibility="public",
    )
    try:
        validate_contextual_access_public(public)
    except ContextualAccessIntegrityError as error:
        raise ContextualAccessArtifactError(
            "contextual-access public bindings are invalid"
        ) from error
    return public


def load_evaluator_contextual_access_benchmark(
    root: Path,
) -> ContextualAccessEvaluatorV1:
    """Load both trees and recompile evaluator truth from its hidden labels."""

    public = load_public_contextual_access_benchmark(root)
    evaluator = _load_one(
        root / "evaluator",
        name="contextual-access-evaluator.json",
        model=ContextualAccessEvaluatorV1,
        visibility="evaluator",
    )
    try:
        recompiled = compile_contextual_access_truth(
            public=public,
            case_labels=evaluator.truth.case_labels,
        )
    except ContextualAccessIntegrityError as error:
        raise ContextualAccessArtifactError(
            "contextual-access evaluator/public bindings are invalid"
        ) from error
    if recompiled != evaluator:
        raise ContextualAccessArtifactError(
            "contextual-access evaluator differs from compiled truth"
        )
    return evaluator


def _manifest(
    visibility: Literal["public", "evaluator"],
    name: str,
    model: ContextualAccessPublicV1 | ContextualAccessEvaluatorV1,
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
        raise ContextualAccessArtifactError(
            "contextual-access manifest visibility differs"
        )
    artifact = _read_canonical(directory / name, model)
    if len(manifest.artifacts) != 1:
        raise ContextualAccessArtifactError(
            "contextual-access manifest must declare exactly one artifact"
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
        raise ContextualAccessArtifactError(
            "contextual-access manifest binding differs"
        )
    return artifact


def _read_canonical[ModelT: BaseModel](path: Path, model: type[ModelT]) -> ModelT:
    try:
        payload = path.read_bytes()
        parsed = model.model_validate_json(payload)
    except (OSError, ValueError, ValidationError) as error:
        raise ContextualAccessArtifactError(
            "contextual-access artifact is invalid"
        ) from error
    if payload != canonical_json_bytes(parsed):
        raise ContextualAccessArtifactError(
            "contextual-access artifact is not canonical JSON"
        )
    return parsed


def _require_exact_files(directory: Path, expected: set[str]) -> None:
    try:
        status = directory.lstat()
        if not stat.S_ISDIR(status.st_mode):
            raise ContextualAccessArtifactError(
                "contextual-access artifact directory is not a real directory"
            )
        entries = tuple(directory.iterdir())
        actual = {item.name for item in entries}
        if actual == expected and any(
            not stat.S_ISREG(item.lstat().st_mode) for item in entries
        ):
            raise ContextualAccessArtifactError(
                "contextual-access inventory contains a non-regular entry"
            )
    except OSError as error:
        raise ContextualAccessArtifactError(
            "contextual-access artifact directory is unreadable"
        ) from error
    if actual != expected:
        raise ContextualAccessArtifactError(
            "contextual-access artifact directory inventory differs"
        )


def _write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as destination:
        destination.write(payload)


__all__ = [
    "EVALUATOR_CONTEXTUAL_ACCESS_PATH",
    "PUBLIC_CONTEXTUAL_ACCESS_PATH",
    "ContextualAccessArtifactError",
    "export_contextual_access_benchmark",
    "load_evaluator_contextual_access_benchmark",
    "load_public_contextual_access_benchmark",
]
