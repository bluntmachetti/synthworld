"""Physically separate public/evaluator enterprise artifact serialization."""

from __future__ import annotations

import stat
from pathlib import Path

from pydantic import BaseModel, ValidationError

from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.models import (
    EnterpriseArtifactDescriptorV1,
    EnterpriseArtifactManifestV1,
    EnterpriseCanonicalBindingTruthV1,
    EnterpriseIdentityAccessCompileResultV1,
    EnterpriseIdentityAccessUniverseV1,
)

PUBLIC_UNIVERSE_PATH = "public/identity-access-universe.json"
PUBLIC_MANIFEST_PATH = "public/manifest.json"
EVALUATOR_BINDING_PATH = "evaluator/canonical-binding-truth.json"
EVALUATOR_MANIFEST_PATH = "evaluator/manifest.json"


class EnterpriseArtifactError(ValueError):
    """Raised when generated enterprise artifact bytes are incomplete or corrupt."""


def export_enterprise_identity_access_compile_result(
    root: Path, result: EnterpriseIdentityAccessCompileResultV1
) -> None:
    if root.exists():
        raise EnterpriseArtifactError("enterprise artifact root must not already exist")
    universe_bytes = canonical_json_bytes(result.public_universe)
    truth_bytes = canonical_json_bytes(result.evaluator_canonical_binding_truth)
    public_descriptor = EnterpriseArtifactDescriptorV1(
        path="identity-access-universe.json",
        schema_version=result.public_universe.schema_version,
        digest=synthetic_digest(universe_bytes),
        byte_size=len(universe_bytes),
    )
    evaluator_descriptor = EnterpriseArtifactDescriptorV1(
        path="canonical-binding-truth.json",
        schema_version=result.evaluator_canonical_binding_truth.schema_version,
        digest=synthetic_digest(truth_bytes),
        byte_size=len(truth_bytes),
    )
    public_manifest = EnterpriseArtifactManifestV1(
        visibility="public", artifacts=(public_descriptor,)
    )
    evaluator_manifest = EnterpriseArtifactManifestV1(
        visibility="evaluator", artifacts=(evaluator_descriptor,)
    )
    _write_new(root / PUBLIC_UNIVERSE_PATH, universe_bytes)
    _write_new(root / PUBLIC_MANIFEST_PATH, canonical_json_bytes(public_manifest))
    _write_new(root / EVALUATOR_BINDING_PATH, truth_bytes)
    _write_new(root / EVALUATOR_MANIFEST_PATH, canonical_json_bytes(evaluator_manifest))


def load_public_enterprise_identity_access_universe(
    root: Path,
) -> EnterpriseIdentityAccessUniverseV1:
    public_root = root / "public"
    _require_exact_files(
        public_root, {"identity-access-universe.json", "manifest.json"}
    )
    manifest = _read_canonical_model(
        public_root / "manifest.json", EnterpriseArtifactManifestV1
    )
    if manifest.visibility != "public":
        raise EnterpriseArtifactError("public manifest has the wrong visibility")
    universe = _read_canonical_model(
        public_root / "identity-access-universe.json",
        EnterpriseIdentityAccessUniverseV1,
    )
    _validate_descriptor(
        public_root,
        manifest,
        expected_path="identity-access-universe.json",
        expected_schema=universe.schema_version,
    )
    return universe


def load_evaluator_enterprise_canonical_binding_truth(
    root: Path,
) -> EnterpriseCanonicalBindingTruthV1:
    evaluator_root = root / "evaluator"
    _require_exact_files(
        evaluator_root, {"canonical-binding-truth.json", "manifest.json"}
    )
    manifest = _read_canonical_model(
        evaluator_root / "manifest.json", EnterpriseArtifactManifestV1
    )
    if manifest.visibility != "evaluator":
        raise EnterpriseArtifactError("evaluator manifest has the wrong visibility")
    truth = _read_canonical_model(
        evaluator_root / "canonical-binding-truth.json",
        EnterpriseCanonicalBindingTruthV1,
    )
    _validate_descriptor(
        evaluator_root,
        manifest,
        expected_path="canonical-binding-truth.json",
        expected_schema=truth.schema_version,
    )
    return truth


def _validate_descriptor(
    root: Path,
    manifest: EnterpriseArtifactManifestV1,
    *,
    expected_path: str,
    expected_schema: str,
) -> None:
    if len(manifest.artifacts) != 1:
        raise EnterpriseArtifactError("manifest must contain exactly one artifact")
    descriptor = manifest.artifacts[0]
    try:
        payload = (root / expected_path).read_bytes()
    except OSError as error:
        raise EnterpriseArtifactError("declared artifact is unreadable") from error
    if descriptor.path != expected_path or descriptor.schema_version != expected_schema:
        raise EnterpriseArtifactError("manifest path or schema binding differs")
    if descriptor.byte_size != len(payload) or descriptor.digest != synthetic_digest(
        payload
    ):
        raise EnterpriseArtifactError("manifest byte size or digest differs")


def _read_canonical_model[ModelT: BaseModel](path: Path, model: type[ModelT]) -> ModelT:
    try:
        payload = path.read_bytes()
        parsed = model.model_validate_json(payload)
    except (OSError, ValueError, ValidationError) as error:
        raise EnterpriseArtifactError(
            f"{path.name} does not match its schema"
        ) from error
    if payload != canonical_json_bytes(parsed):
        raise EnterpriseArtifactError(f"{path.name} is not canonical JSON")
    return parsed


def _require_exact_files(root: Path, expected: set[str]) -> None:
    try:
        root_status = root.lstat()
        if not stat.S_ISDIR(root_status.st_mode):
            raise EnterpriseArtifactError("artifact directory is not a real directory")
        entries = tuple(root.iterdir())
        actual = {item.name for item in entries}
        if actual == expected:
            for item in entries:
                if not stat.S_ISREG(item.lstat().st_mode):
                    raise EnterpriseArtifactError(
                        "artifact inventory contains a non-regular entry"
                    )
    except OSError as error:
        raise EnterpriseArtifactError("artifact directory is unreadable") from error
    if actual != expected:
        raise EnterpriseArtifactError("artifact directory inventory differs")


def _write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as destination:
        destination.write(payload)


__all__ = [
    "EVALUATOR_BINDING_PATH",
    "EVALUATOR_MANIFEST_PATH",
    "PUBLIC_MANIFEST_PATH",
    "PUBLIC_UNIVERSE_PATH",
    "EnterpriseArtifactError",
    "export_enterprise_identity_access_compile_result",
    "load_evaluator_enterprise_canonical_binding_truth",
    "load_public_enterprise_identity_access_universe",
]
