"""Physical public/evaluator split for authority-governance conformance."""

from __future__ import annotations

import hashlib
import re
import stat
from importlib.resources import as_file, files
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

from synthworld.authority_governance.models import (
    AuthorityGovernanceEvaluatorV1,
    AuthorityGovernancePublicV1,
)
from synthworld.authority_governance.reference import ReferenceAuthorityGovernanceV1
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
GOLDEN_AUTHORITY_GOVERNANCE_DIRECTORY = "authority-governance-v1"
_GOLDEN_CHECKSUM_NAME = "SHA256SUMS"
_GOLDEN_ARTIFACT_PATHS = (
    EVALUATOR_AUTHORITY_GOVERNANCE_PATH,
    "evaluator/manifest.json",
    PUBLIC_AUTHORITY_GOVERNANCE_PATH,
    "public/manifest.json",
)
_LOWERCASE_SHA256 = re.compile(r"[0-9a-f]{64}").fullmatch


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


def load_golden_authority_governance_benchmark() -> ReferenceAuthorityGovernanceV1:
    """Load the packaged #73 fixture after verifying every frozen byte."""

    resource = files("synthworld.benchmarks").joinpath(
        GOLDEN_AUTHORITY_GOVERNANCE_DIRECTORY
    )
    with as_file(resource) as root:
        _verify_golden_tree(root)
        public = load_public_authority_governance_benchmark(root)
        evaluator = load_evaluator_authority_governance_benchmark(root)
    return ReferenceAuthorityGovernanceV1(public=public, evaluator=evaluator)


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


def _verify_golden_tree(root: Path) -> None:
    """Verify the frozen root inventory and its path-bound raw-byte checksums."""

    try:
        if not stat.S_ISDIR(root.lstat().st_mode):
            raise AuthorityGovernanceArtifactError(
                "frozen authority-governance root is not a real directory"
            )
        entries = {item.name: item for item in root.iterdir()}
        if set(entries) != {"public", "evaluator", _GOLDEN_CHECKSUM_NAME}:
            raise AuthorityGovernanceArtifactError(
                "frozen authority-governance root inventory differs"
            )
        if (
            not stat.S_ISDIR(entries["public"].lstat().st_mode)
            or not stat.S_ISDIR(entries["evaluator"].lstat().st_mode)
            or not stat.S_ISREG(entries[_GOLDEN_CHECKSUM_NAME].lstat().st_mode)
        ):
            raise AuthorityGovernanceArtifactError(
                "frozen authority-governance root contains a non-regular entry"
            )
        manifest = entries[_GOLDEN_CHECKSUM_NAME].read_bytes()
    except OSError as error:
        raise AuthorityGovernanceArtifactError(
            "frozen authority-governance root is unreadable"
        ) from error

    expected = _parse_golden_checksums(manifest)
    for relative_path in _GOLDEN_ARTIFACT_PATHS:
        artifact = root.joinpath(*relative_path.split("/"))
        try:
            if not stat.S_ISREG(artifact.lstat().st_mode):
                raise AuthorityGovernanceArtifactError(
                    "frozen authority-governance artifact is not a regular file"
                )
            actual = hashlib.sha256(artifact.read_bytes()).hexdigest()
        except OSError as error:
            raise AuthorityGovernanceArtifactError(
                "frozen authority-governance artifact is unreadable"
            ) from error
        if actual != expected[relative_path]:
            raise AuthorityGovernanceArtifactError(
                "frozen authority-governance artifact checksum differs"
            )


def _parse_golden_checksums(payload: bytes) -> dict[str, str]:
    try:
        text = payload.decode("ascii")
    except UnicodeDecodeError as error:
        raise AuthorityGovernanceArtifactError(
            "frozen authority-governance checksum manifest is invalid"
        ) from error
    lines = text.splitlines()
    if payload != ("\n".join(lines) + "\n").encode("ascii"):
        raise AuthorityGovernanceArtifactError(
            "frozen authority-governance checksum manifest is not canonical"
        )
    rows = tuple(line.split("  ") for line in lines)
    if any(len(fields) != 2 for fields in rows):
        raise AuthorityGovernanceArtifactError(
            "frozen authority-governance checksum manifest is invalid"
        )
    parsed = tuple((fields[0], fields[1]) for fields in rows)
    if tuple(path for _, path in parsed) != _GOLDEN_ARTIFACT_PATHS or any(
        _LOWERCASE_SHA256(digest) is None for digest, _ in parsed
    ):
        raise AuthorityGovernanceArtifactError(
            "frozen authority-governance checksum manifest is invalid"
        )
    return {path: digest for digest, path in parsed}


__all__ = [
    "EVALUATOR_AUTHORITY_GOVERNANCE_PATH",
    "GOLDEN_AUTHORITY_GOVERNANCE_DIRECTORY",
    "PUBLIC_AUTHORITY_GOVERNANCE_PATH",
    "AuthorityGovernanceArtifactError",
    "export_authority_governance_benchmark",
    "load_evaluator_authority_governance_benchmark",
    "load_golden_authority_governance_benchmark",
    "load_public_authority_governance_benchmark",
]
