"""Canonical physical visibility split for corpus and directory/RBAC artifacts."""

from __future__ import annotations

import stat
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ValidationError

from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.models import (
    EnterpriseArtifactDescriptorV1,
    EnterpriseArtifactManifestV1,
)
from synthworld.enterprise.rbac.corpus_models import (
    EnterpriseEvaluationCaseInventoryV1,
    EnterpriseEvaluationCorpusCompileResultV1,
    EnterpriseEvaluationCorpusV1,
)
from synthworld.enterprise.rbac.models import (
    CompiledEnterpriseDirectoryRbacTruthV1,
    CompiledEnterpriseDirectoryRbacTruthV2,
    EnterpriseDirectoryRbacIntentOverlayV2,
    EnterpriseDirectoryRbacKernelV1,
)

PUBLIC_CORPUS_PATH = "public/evaluation-corpus.json"
EVALUATOR_CASES_PATH = "evaluator/evaluation-case-inventory.json"
PUBLIC_RBAC_KERNEL_PATH = "public/directory-rbac-kernel.json"
PUBLIC_RBAC_INTENT_V2_PATH = "public/directory-rbac-intent-v2.json"
EVALUATOR_RBAC_TRUTH_PATH = "evaluator/directory-rbac-truth.json"
EVALUATOR_RBAC_TRUTH_V2_PATH = "evaluator/directory-rbac-truth-v2.json"
MANIFEST_NAME = "manifest.json"


class EnterpriseRbacArtifactError(ValueError):
    """Raised for missing, unexpected, noncanonical, or digest-mismatched files."""


def export_enterprise_evaluation_corpus(
    root: Path, result: EnterpriseEvaluationCorpusCompileResultV1
) -> None:
    _export_pair(
        root,
        public_name="evaluation-corpus.json",
        public_model=result.public_corpus,
        evaluator_name="evaluation-case-inventory.json",
        evaluator_model=result.evaluator_case_inventory,
    )


def load_public_enterprise_evaluation_corpus(
    root: Path,
) -> EnterpriseEvaluationCorpusV1:
    return _load_one(
        root / "public",
        name="evaluation-corpus.json",
        model=EnterpriseEvaluationCorpusV1,
        visibility="public",
    )


def load_evaluator_enterprise_case_inventory(
    root: Path,
) -> EnterpriseEvaluationCaseInventoryV1:
    inventory = _load_one(
        root / "evaluator",
        name="evaluation-case-inventory.json",
        model=EnterpriseEvaluationCaseInventoryV1,
        visibility="evaluator",
    )
    corpus = load_public_enterprise_evaluation_corpus(root)
    if inventory.evaluation_corpus_digest != synthetic_digest(
        canonical_json_bytes(corpus)
    ):
        raise EnterpriseRbacArtifactError(
            "evaluation case inventory corpus binding differs"
        )
    cell_ids = {item.cell_id for item in corpus.evaluation_cells}
    activation_ids = {
        item.activation_request_id for item in corpus.role_activation_requests
    }
    for case in inventory.cases:
        known = cell_ids if case.target_kind.value == "access_cell" else activation_ids
        if case.target_id not in known:
            raise EnterpriseRbacArtifactError(
                "evaluation case target does not resolve in the public corpus"
            )
    return inventory


def export_enterprise_directory_rbac(
    root: Path,
    *,
    kernel: EnterpriseDirectoryRbacKernelV1,
    truth: CompiledEnterpriseDirectoryRbacTruthV1,
) -> None:
    _export_pair(
        root,
        public_name="directory-rbac-kernel.json",
        public_model=kernel,
        evaluator_name="directory-rbac-truth.json",
        evaluator_model=truth,
    )


def export_enterprise_directory_rbac_v2(
    root: Path,
    *,
    kernel: EnterpriseDirectoryRbacKernelV1,
    intent: EnterpriseDirectoryRbacIntentOverlayV2,
    truth: CompiledEnterpriseDirectoryRbacTruthV2,
) -> None:
    """Export V2 public policy input separately from evaluator-only truth."""

    if root.exists():
        raise EnterpriseRbacArtifactError(
            "enterprise RBAC artifact root already exists"
        )
    public_models: tuple[tuple[str, BaseModel], ...] = (
        ("directory-rbac-intent-v2.json", intent),
        ("directory-rbac-kernel.json", kernel),
    )
    evaluator_models: tuple[tuple[str, BaseModel], ...] = (
        ("directory-rbac-truth-v2.json", truth),
    )
    _export_models(root / "public", "public", public_models)
    _export_models(root / "evaluator", "evaluator", evaluator_models)


def load_public_enterprise_directory_rbac_kernel(
    root: Path,
) -> EnterpriseDirectoryRbacKernelV1:
    return _load_one(
        root / "public",
        name="directory-rbac-kernel.json",
        model=EnterpriseDirectoryRbacKernelV1,
        visibility="public",
    )


def load_public_enterprise_directory_rbac_kernel_v2(
    root: Path,
) -> EnterpriseDirectoryRbacKernelV1:
    kernel, _intent = _load_public_directory_rbac_v2(root)
    return kernel


def load_public_enterprise_directory_rbac_intent_v2(
    root: Path,
) -> EnterpriseDirectoryRbacIntentOverlayV2:
    _kernel, intent = _load_public_directory_rbac_v2(root)
    return intent


def load_evaluator_enterprise_directory_rbac_truth(
    root: Path,
) -> CompiledEnterpriseDirectoryRbacTruthV1:
    truth = _load_one(
        root / "evaluator",
        name="directory-rbac-truth.json",
        model=CompiledEnterpriseDirectoryRbacTruthV1,
        visibility="evaluator",
    )
    kernel = load_public_enterprise_directory_rbac_kernel(root)
    if (
        truth.directory_rbac_kernel_digest
        != synthetic_digest(canonical_json_bytes(kernel))
        or truth.identity_access_universe_digest
        != kernel.identity_access_universe_digest
    ):
        raise EnterpriseRbacArtifactError("directory/RBAC truth kernel binding differs")
    return truth


def load_evaluator_enterprise_directory_rbac_truth_v2(
    root: Path,
) -> CompiledEnterpriseDirectoryRbacTruthV2:
    truth = cast(
        CompiledEnterpriseDirectoryRbacTruthV2,
        _load_models(
            root / "evaluator",
            visibility="evaluator",
            models=(
                (
                    "directory-rbac-truth-v2.json",
                    CompiledEnterpriseDirectoryRbacTruthV2,
                ),
            ),
        )[0],
    )
    kernel, intent = _load_public_directory_rbac_v2(root)
    if (
        truth.directory_rbac_kernel_digest
        != synthetic_digest(canonical_json_bytes(kernel))
        or truth.directory_rbac_intent_digest
        != synthetic_digest(canonical_json_bytes(intent))
        or truth.identity_access_universe_digest
        != kernel.identity_access_universe_digest
        or truth.identity_access_universe_digest
        != intent.identity_access_universe_digest
        or truth.evaluation_corpus_digest != intent.evaluation_corpus_digest
    ):
        raise EnterpriseRbacArtifactError(
            "directory/RBAC V2 truth public binding differs"
        )
    return truth


def _load_public_directory_rbac_v2(
    root: Path,
) -> tuple[EnterpriseDirectoryRbacKernelV1, EnterpriseDirectoryRbacIntentOverlayV2]:
    loaded = _load_models(
        root / "public",
        visibility="public",
        models=(
            ("directory-rbac-intent-v2.json", EnterpriseDirectoryRbacIntentOverlayV2),
            ("directory-rbac-kernel.json", EnterpriseDirectoryRbacKernelV1),
        ),
    )
    intent, kernel = loaded
    typed_kernel = cast(EnterpriseDirectoryRbacKernelV1, kernel)
    typed_intent = cast(EnterpriseDirectoryRbacIntentOverlayV2, intent)
    if (
        typed_kernel.identity_access_universe_digest
        != typed_intent.identity_access_universe_digest
    ):
        raise EnterpriseRbacArtifactError(
            "directory/RBAC V2 public universe binding differs"
        )
    return typed_kernel, typed_intent


def _export_models(
    directory: Path,
    visibility: Literal["public", "evaluator"],
    models: tuple[tuple[str, BaseModel], ...],
) -> None:
    artifacts: list[EnterpriseArtifactDescriptorV1] = []
    for name, model in models:
        payload = canonical_json_bytes(model)
        _write_new(directory / name, payload)
        artifacts.append(_descriptor(name, model, payload))
    manifest = EnterpriseArtifactManifestV1(
        visibility=visibility,
        artifacts=tuple(artifacts),
    )
    _write_new(directory / MANIFEST_NAME, canonical_json_bytes(manifest))


def _load_models(
    directory: Path,
    *,
    visibility: Literal["public", "evaluator"],
    models: tuple[tuple[str, type[BaseModel]], ...],
) -> tuple[BaseModel, ...]:
    names = {name for name, _model in models}
    _require_exact_files(directory, {*names, MANIFEST_NAME})
    manifest = _read_canonical(directory / MANIFEST_NAME, EnterpriseArtifactManifestV1)
    if manifest.visibility != visibility:
        raise EnterpriseRbacArtifactError("artifact manifest visibility differs")
    descriptors = {item.path: item for item in manifest.artifacts}
    if set(descriptors) != names:
        raise EnterpriseRbacArtifactError("artifact manifest inventory differs")
    loaded: list[BaseModel] = []
    for name, model in models:
        artifact = _read_canonical(directory / name, model)
        payload = canonical_json_bytes(artifact)
        if descriptors[name] != _descriptor(name, artifact, payload):
            raise EnterpriseRbacArtifactError("artifact manifest binding differs")
        loaded.append(artifact)
    return tuple(loaded)


def _descriptor(
    name: str,
    model: BaseModel,
    payload: bytes,
) -> EnterpriseArtifactDescriptorV1:
    schema_version = model.model_dump().get("schema_version")
    return EnterpriseArtifactDescriptorV1(
        path=name,
        schema_version=str(schema_version),
        digest=synthetic_digest(payload),
        byte_size=len(payload),
    )


def _export_pair(
    root: Path,
    *,
    public_name: str,
    public_model: EnterpriseEvaluationCorpusV1 | EnterpriseDirectoryRbacKernelV1,
    evaluator_name: str,
    evaluator_model: EnterpriseEvaluationCaseInventoryV1
    | CompiledEnterpriseDirectoryRbacTruthV1,
) -> None:
    if root.exists():
        raise EnterpriseRbacArtifactError(
            "enterprise RBAC artifact root already exists"
        )
    public_bytes = canonical_json_bytes(public_model)
    evaluator_bytes = canonical_json_bytes(evaluator_model)
    public_manifest = _manifest("public", public_name, public_model, public_bytes)
    evaluator_manifest = _manifest(
        "evaluator", evaluator_name, evaluator_model, evaluator_bytes
    )
    _write_new(root / "public" / public_name, public_bytes)
    _write_new(
        root / "public" / MANIFEST_NAME,
        canonical_json_bytes(public_manifest),
    )
    _write_new(root / "evaluator" / evaluator_name, evaluator_bytes)
    _write_new(
        root / "evaluator" / MANIFEST_NAME,
        canonical_json_bytes(evaluator_manifest),
    )


def _manifest(
    visibility: Literal["public", "evaluator"],
    name: str,
    model: EnterpriseEvaluationCorpusV1
    | EnterpriseDirectoryRbacKernelV1
    | EnterpriseEvaluationCaseInventoryV1
    | CompiledEnterpriseDirectoryRbacTruthV1,
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
        raise EnterpriseRbacArtifactError("artifact manifest visibility differs")
    artifact = _read_canonical(directory / name, model)
    if len(manifest.artifacts) != 1:
        raise EnterpriseRbacArtifactError("manifest must declare exactly one artifact")
    descriptor = manifest.artifacts[0]
    payload = canonical_json_bytes(artifact)
    schema_version = artifact.model_dump().get("schema_version")
    if (
        descriptor.path != name
        or descriptor.schema_version != schema_version
        or descriptor.byte_size != len(payload)
        or descriptor.digest != synthetic_digest(payload)
    ):
        raise EnterpriseRbacArtifactError("artifact manifest binding differs")
    return artifact


def _read_canonical[ModelT: BaseModel](path: Path, model: type[ModelT]) -> ModelT:
    try:
        payload = path.read_bytes()
        parsed = model.model_validate_json(payload)
    except (OSError, ValueError, ValidationError) as error:
        raise EnterpriseRbacArtifactError(
            "enterprise RBAC artifact is invalid"
        ) from error
    if payload != canonical_json_bytes(parsed):
        raise EnterpriseRbacArtifactError(
            "enterprise RBAC artifact is not canonical JSON"
        )
    return parsed


def _require_exact_files(directory: Path, expected: set[str]) -> None:
    try:
        status = directory.lstat()
        if not stat.S_ISDIR(status.st_mode):
            raise EnterpriseRbacArtifactError(
                "artifact directory is not a real directory"
            )
        entries = tuple(directory.iterdir())
        actual = {item.name for item in entries}
        if actual == expected:
            for item in entries:
                if not stat.S_ISREG(item.lstat().st_mode):
                    raise EnterpriseRbacArtifactError(
                        "artifact inventory contains a non-regular entry"
                    )
    except OSError as error:
        raise EnterpriseRbacArtifactError("artifact directory is unreadable") from error
    if actual != expected:
        raise EnterpriseRbacArtifactError("artifact directory inventory differs")


def _write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as destination:
        destination.write(payload)


__all__ = [
    "EVALUATOR_CASES_PATH",
    "EVALUATOR_RBAC_TRUTH_PATH",
    "EVALUATOR_RBAC_TRUTH_V2_PATH",
    "PUBLIC_CORPUS_PATH",
    "PUBLIC_RBAC_INTENT_V2_PATH",
    "PUBLIC_RBAC_KERNEL_PATH",
    "EnterpriseRbacArtifactError",
    "export_enterprise_directory_rbac",
    "export_enterprise_directory_rbac_v2",
    "export_enterprise_evaluation_corpus",
    "load_evaluator_enterprise_case_inventory",
    "load_evaluator_enterprise_directory_rbac_truth",
    "load_evaluator_enterprise_directory_rbac_truth_v2",
    "load_public_enterprise_directory_rbac_intent_v2",
    "load_public_enterprise_directory_rbac_kernel",
    "load_public_enterprise_directory_rbac_kernel_v2",
    "load_public_enterprise_evaluation_corpus",
]
