"""Canonical physical visibility split for corpus and directory/RBAC artifacts."""

from __future__ import annotations

import stat
from pathlib import Path
from typing import Literal

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
    EnterpriseDirectoryRbacKernelV1,
)

PUBLIC_CORPUS_PATH = "public/evaluation-corpus.json"
EVALUATOR_CASES_PATH = "evaluator/evaluation-case-inventory.json"
PUBLIC_RBAC_KERNEL_PATH = "public/directory-rbac-kernel.json"
EVALUATOR_RBAC_TRUTH_PATH = "evaluator/directory-rbac-truth.json"
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


def load_public_enterprise_directory_rbac_kernel(
    root: Path,
) -> EnterpriseDirectoryRbacKernelV1:
    return _load_one(
        root / "public",
        name="directory-rbac-kernel.json",
        model=EnterpriseDirectoryRbacKernelV1,
        visibility="public",
    )


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
    "PUBLIC_CORPUS_PATH",
    "PUBLIC_RBAC_KERNEL_PATH",
    "EnterpriseRbacArtifactError",
    "export_enterprise_directory_rbac",
    "export_enterprise_evaluation_corpus",
    "load_evaluator_enterprise_case_inventory",
    "load_evaluator_enterprise_directory_rbac_truth",
    "load_public_enterprise_directory_rbac_kernel",
    "load_public_enterprise_evaluation_corpus",
]
