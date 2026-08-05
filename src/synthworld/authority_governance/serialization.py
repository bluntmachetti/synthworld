"""Physical public/evaluator split for authority-governance conformance."""

from __future__ import annotations

import stat
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

from synthworld.authority_governance.models import (
    AuthorityGovernanceEvaluatorV1,
    AuthorityGovernancePublicV1,
)
from synthworld.authority_governance.replay import (
    AuthorityGovernanceIntegrityError,
    validate_authority_governance_evaluator,
    validate_authority_governance_public,
)
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.models import (
    EnterpriseArtifactDescriptorV1,
    EnterpriseArtifactManifestV1,
)

PUBLIC_AUTHORITY_GOVERNANCE_PATH = "public/authority-governance-input.json"
EVALUATOR_AUTHORITY_GOVERNANCE_PATH = "evaluator/authority-governance-evaluator.json"
MANIFEST_NAME = "manifest.json"


class AuthorityGovernanceArtifactError(ValueError):
    """Raised when a governance artifact tree violates its contract."""


def export_authority_governance_benchmark(
    root: Path,
    *,
    public: AuthorityGovernancePublicV1,
    evaluator: AuthorityGovernanceEvaluatorV1,
) -> None:
    """Write the public and answer-key artifacts through separate paths."""

    if root.exists():
        raise AuthorityGovernanceArtifactError(
            "authority-governance artifact root exists"
        )
    try:
        validate_authority_governance_evaluator(public, evaluator)
    except AuthorityGovernanceIntegrityError as error:
        raise AuthorityGovernanceArtifactError(
            "authority-governance artifacts are invalid"
        ) from error
    public_bytes = canonical_json_bytes(public)
    evaluator_bytes = canonical_json_bytes(evaluator)
    public_manifest = _manifest(
        "public", "authority-governance-input.json", public, public_bytes
    )
    evaluator_manifest = _manifest(
        "evaluator",
        "authority-governance-evaluator.json",
        evaluator,
        evaluator_bytes,
    )
    _write_new(root / PUBLIC_AUTHORITY_GOVERNANCE_PATH, public_bytes)
    _write_new(root / "public" / MANIFEST_NAME, canonical_json_bytes(public_manifest))
    _write_new(root / EVALUATOR_AUTHORITY_GOVERNANCE_PATH, evaluator_bytes)
    _write_new(
        root / "evaluator" / MANIFEST_NAME,
        canonical_json_bytes(evaluator_manifest),
    )


def load_public_authority_governance_benchmark(
    root: Path,
) -> AuthorityGovernancePublicV1:
    """Load only the public governance tree and its exact inventory."""

    public = _load_one(
        root / "public",
        name="authority-governance-input.json",
        model=AuthorityGovernancePublicV1,
        visibility="public",
    )
    try:
        validate_authority_governance_public(public)
    except AuthorityGovernanceIntegrityError as error:
        raise AuthorityGovernanceArtifactError(
            "authority-governance public bindings are invalid"
        ) from error
    return public


def load_evaluator_authority_governance_benchmark(
    root: Path,
) -> AuthorityGovernanceEvaluatorV1:
    """Load the evaluator tree only after validating the public tree."""

    public = load_public_authority_governance_benchmark(root)
    evaluator = _load_one(
        root / "evaluator",
        name="authority-governance-evaluator.json",
        model=AuthorityGovernanceEvaluatorV1,
        visibility="evaluator",
    )
    try:
        validate_authority_governance_evaluator(public, evaluator)
    except AuthorityGovernanceIntegrityError as error:
        raise AuthorityGovernanceArtifactError(
            "authority-governance evaluator bindings are invalid"
        ) from error
    return evaluator


def _manifest(
    visibility: Literal["public", "evaluator"],
    name: str,
    model: AuthorityGovernancePublicV1 | AuthorityGovernanceEvaluatorV1,
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
        raise AuthorityGovernanceArtifactError(
            "authority-governance manifest visibility differs"
        )
    artifact = _read_canonical(directory / name, model)
    if len(manifest.artifacts) != 1:
        raise AuthorityGovernanceArtifactError(
            "authority-governance manifest must declare one artifact"
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
        raise AuthorityGovernanceArtifactError(
            "authority-governance manifest binding differs"
        )
    return artifact


def _read_canonical[ModelT: BaseModel](path: Path, model: type[ModelT]) -> ModelT:
    try:
        payload = path.read_bytes()
        parsed = model.model_validate_json(payload)
    except (OSError, ValueError, ValidationError) as error:
        raise AuthorityGovernanceArtifactError(
            "authority-governance artifact is invalid"
        ) from error
    if payload != canonical_json_bytes(parsed):
        raise AuthorityGovernanceArtifactError(
            "authority-governance artifact is not canonical JSON"
        )
    return parsed


def _require_exact_files(directory: Path, expected: set[str]) -> None:
    try:
        status = directory.lstat()
        if not stat.S_ISDIR(status.st_mode):
            raise AuthorityGovernanceArtifactError(
                "authority-governance artifact directory is not a real directory"
            )
        entries = tuple(directory.iterdir())
        actual = {item.name for item in entries}
        if actual == expected and any(
            not stat.S_ISREG(item.lstat().st_mode) for item in entries
        ):
            raise AuthorityGovernanceArtifactError(
                "authority-governance inventory contains a non-regular entry"
            )
    except OSError as error:
        raise AuthorityGovernanceArtifactError(
            "authority-governance artifact directory is unreadable"
        ) from error
    if actual != expected:
        raise AuthorityGovernanceArtifactError(
            "authority-governance artifact inventory differs"
        )


def _write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as destination:
        destination.write(payload)


__all__ = [
    "EVALUATOR_AUTHORITY_GOVERNANCE_PATH",
    "PUBLIC_AUTHORITY_GOVERNANCE_PATH",
    "AuthorityGovernanceArtifactError",
    "export_authority_governance_benchmark",
    "load_evaluator_authority_governance_benchmark",
    "load_public_authority_governance_benchmark",
]
