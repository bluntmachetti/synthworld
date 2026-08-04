"""Physical public/evaluator split for PR4 authorization artifacts."""

from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

from synthworld.enterprise.abac.models import (
    CompiledEnterpriseAbacTruthV1,
    EnterpriseAbacIntentOverlayV1,
    EnterpriseAbacStateOverlayV1,
)
from synthworld.enterprise.authorization.models import (
    CompiledEnterpriseAccessStateV1,
    EnterpriseAuthorizationCompositionV1,
    EnterpriseAuthorizationKernelV1,
)
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.models import (
    EnterpriseArtifactDescriptorV1,
    EnterpriseArtifactManifestV1,
)
from synthworld.enterprise.rebac.models import (
    CompiledEnterpriseRebacTruthV1,
    EnterpriseRebacIntentOverlayV1,
    EnterpriseRebacStateOverlayV1,
)

PUBLIC_AUTHORIZATION_FILES = {
    "abac-intent.json",
    "abac-state.json",
    "authorization-composition.json",
    "authorization-kernel.json",
    "rebac-intent.json",
    "rebac-state.json",
}
EVALUATOR_AUTHORIZATION_FILES = {
    "abac-truth.json",
    "compiled-access-state.json",
    "rebac-truth.json",
}
MANIFEST_NAME = "manifest.json"


class EnterpriseAuthorizationArtifactError(ValueError):
    """Raised for noncanonical, unexpected, or digest-mismatched artifacts."""


@dataclass(frozen=True, slots=True)
class EnterpriseAuthorizationPublicArtifactsV1:
    abac_state: EnterpriseAbacStateOverlayV1
    abac_intent: EnterpriseAbacIntentOverlayV1
    rebac_state: EnterpriseRebacStateOverlayV1
    rebac_intent: EnterpriseRebacIntentOverlayV1
    composition: EnterpriseAuthorizationCompositionV1
    kernel: EnterpriseAuthorizationKernelV1


@dataclass(frozen=True, slots=True)
class EnterpriseAuthorizationEvaluatorArtifactsV1:
    abac_truth: CompiledEnterpriseAbacTruthV1
    rebac_truth: CompiledEnterpriseRebacTruthV1
    access_state: CompiledEnterpriseAccessStateV1


def export_enterprise_authorization(
    root: Path,
    *,
    public: EnterpriseAuthorizationPublicArtifactsV1,
    evaluator: EnterpriseAuthorizationEvaluatorArtifactsV1,
) -> None:
    if root.exists():
        raise EnterpriseAuthorizationArtifactError(
            "enterprise authorization artifact root already exists"
        )
    public_models: dict[str, BaseModel] = {
        "abac-intent.json": public.abac_intent,
        "abac-state.json": public.abac_state,
        "authorization-composition.json": public.composition,
        "authorization-kernel.json": public.kernel,
        "rebac-intent.json": public.rebac_intent,
        "rebac-state.json": public.rebac_state,
    }
    evaluator_models: dict[str, BaseModel] = {
        "abac-truth.json": evaluator.abac_truth,
        "compiled-access-state.json": evaluator.access_state,
        "rebac-truth.json": evaluator.rebac_truth,
    }
    _write_tree(root / "public", "public", public_models)
    _write_tree(root / "evaluator", "evaluator", evaluator_models)


def load_public_enterprise_authorization(
    root: Path,
) -> EnterpriseAuthorizationPublicArtifactsV1:
    directory = root / "public"
    expected = PUBLIC_AUTHORIZATION_FILES | {MANIFEST_NAME}
    _require_exact_files(directory, expected)
    models: dict[str, type[BaseModel]] = {
        "abac-intent.json": EnterpriseAbacIntentOverlayV1,
        "abac-state.json": EnterpriseAbacStateOverlayV1,
        "authorization-composition.json": EnterpriseAuthorizationCompositionV1,
        "authorization-kernel.json": EnterpriseAuthorizationKernelV1,
        "rebac-intent.json": EnterpriseRebacIntentOverlayV1,
        "rebac-state.json": EnterpriseRebacStateOverlayV1,
    }
    loaded = _load_tree(directory, "public", models)
    result = EnterpriseAuthorizationPublicArtifactsV1(
        abac_state=_as(loaded["abac-state.json"], EnterpriseAbacStateOverlayV1),
        abac_intent=_as(loaded["abac-intent.json"], EnterpriseAbacIntentOverlayV1),
        rebac_state=_as(loaded["rebac-state.json"], EnterpriseRebacStateOverlayV1),
        rebac_intent=_as(loaded["rebac-intent.json"], EnterpriseRebacIntentOverlayV1),
        composition=_as(
            loaded["authorization-composition.json"],
            EnterpriseAuthorizationCompositionV1,
        ),
        kernel=_as(
            loaded["authorization-kernel.json"], EnterpriseAuthorizationKernelV1
        ),
    )
    _validate_public_bindings(result)
    return result


def load_evaluator_enterprise_authorization(
    root: Path,
) -> EnterpriseAuthorizationEvaluatorArtifactsV1:
    public = load_public_enterprise_authorization(root)
    directory = root / "evaluator"
    expected = EVALUATOR_AUTHORIZATION_FILES | {MANIFEST_NAME}
    _require_exact_files(directory, expected)
    models: dict[str, type[BaseModel]] = {
        "abac-truth.json": CompiledEnterpriseAbacTruthV1,
        "compiled-access-state.json": CompiledEnterpriseAccessStateV1,
        "rebac-truth.json": CompiledEnterpriseRebacTruthV1,
    }
    loaded = _load_tree(directory, "evaluator", models)
    result = EnterpriseAuthorizationEvaluatorArtifactsV1(
        abac_truth=_as(loaded["abac-truth.json"], CompiledEnterpriseAbacTruthV1),
        rebac_truth=_as(loaded["rebac-truth.json"], CompiledEnterpriseRebacTruthV1),
        access_state=_as(
            loaded["compiled-access-state.json"], CompiledEnterpriseAccessStateV1
        ),
    )
    if (
        public.composition.abac is None
        or public.composition.rebac is None
        or public.composition.abac.component_digest
        != synthetic_digest(canonical_json_bytes(result.abac_truth))
        or public.composition.rebac.component_digest
        != synthetic_digest(canonical_json_bytes(result.rebac_truth))
        or result.access_state.composition_digest
        != synthetic_digest(canonical_json_bytes(public.composition))
        or result.access_state.authorization_kernel_digest
        != synthetic_digest(canonical_json_bytes(public.kernel))
    ):
        raise EnterpriseAuthorizationArtifactError(
            "authorization evaluator/public binding differs"
        )
    return result


def _validate_public_bindings(
    artifacts: EnterpriseAuthorizationPublicArtifactsV1,
) -> None:
    universe_digests = {
        artifacts.abac_state.identity_access_universe_digest,
        artifacts.abac_intent.identity_access_universe_digest,
        artifacts.rebac_state.identity_access_universe_digest,
        artifacts.rebac_intent.identity_access_universe_digest,
        artifacts.composition.identity_access_universe_digest,
        artifacts.kernel.identity_access_universe_digest,
    }
    corpus_digests = {
        artifacts.abac_state.evaluation_corpus_digest,
        artifacts.abac_intent.evaluation_corpus_digest,
        artifacts.rebac_state.evaluation_corpus_digest,
        artifacts.rebac_intent.evaluation_corpus_digest,
        artifacts.composition.evaluation_corpus_digest,
        artifacts.kernel.evaluation_corpus_digest,
    }
    if len(universe_digests) != 1 or len(corpus_digests) != 1:
        raise EnterpriseAuthorizationArtifactError(
            "authorization public artifact bindings differ"
        )
    if artifacts.kernel.composition_digest != synthetic_digest(
        canonical_json_bytes(artifacts.composition)
    ):
        raise EnterpriseAuthorizationArtifactError(
            "authorization kernel composition binding differs"
        )


def _write_tree(
    directory: Path,
    visibility: Literal["public", "evaluator"],
    models: dict[str, BaseModel],
) -> None:
    descriptors: list[EnterpriseArtifactDescriptorV1] = []
    for name in sorted(models):
        model = models[name]
        payload = canonical_json_bytes(model)
        _write_new(directory / name, payload)
        descriptors.append(
            EnterpriseArtifactDescriptorV1(
                path=name,
                schema_version=str(model.model_dump()["schema_version"]),
                digest=synthetic_digest(payload),
                byte_size=len(payload),
            )
        )
    manifest = EnterpriseArtifactManifestV1(
        visibility=visibility, artifacts=tuple(descriptors)
    )
    _write_new(directory / MANIFEST_NAME, canonical_json_bytes(manifest))


def _load_tree(
    directory: Path,
    visibility: Literal["public", "evaluator"],
    models: dict[str, type[BaseModel]],
) -> dict[str, BaseModel]:
    manifest = _read_canonical(directory / MANIFEST_NAME, EnterpriseArtifactManifestV1)
    if manifest.visibility != visibility:
        raise EnterpriseAuthorizationArtifactError(
            "authorization manifest visibility differs"
        )
    descriptors = {item.path: item for item in manifest.artifacts}
    if set(descriptors) != set(models):
        raise EnterpriseAuthorizationArtifactError(
            "authorization manifest inventory differs"
        )
    loaded: dict[str, BaseModel] = {}
    for name, model_type in models.items():
        model = _read_canonical(directory / name, model_type)
        payload = canonical_json_bytes(model)
        descriptor = descriptors[name]
        if (
            descriptor.schema_version != model.model_dump()["schema_version"]
            or descriptor.digest != synthetic_digest(payload)
            or descriptor.byte_size != len(payload)
        ):
            raise EnterpriseAuthorizationArtifactError(
                "authorization manifest descriptor differs"
            )
        loaded[name] = model
    return loaded


def _read_canonical[ModelT: BaseModel](path: Path, model: type[ModelT]) -> ModelT:
    try:
        payload = path.read_bytes()
        parsed = model.model_validate_json(payload)
    except (OSError, ValueError, ValidationError) as error:
        raise EnterpriseAuthorizationArtifactError(
            "enterprise authorization artifact is invalid"
        ) from error
    if payload != canonical_json_bytes(parsed):
        raise EnterpriseAuthorizationArtifactError(
            "enterprise authorization artifact is not canonical JSON"
        )
    return parsed


def _require_exact_files(directory: Path, expected: set[str]) -> None:
    try:
        status = directory.lstat()
        if not stat.S_ISDIR(status.st_mode):
            raise EnterpriseAuthorizationArtifactError(
                "authorization artifact directory is not a real directory"
            )
        entries = tuple(directory.iterdir())
        actual = {item.name for item in entries}
        if actual == expected and any(
            not stat.S_ISREG(item.lstat().st_mode) for item in entries
        ):
            raise EnterpriseAuthorizationArtifactError(
                "authorization artifact inventory contains a non-regular entry"
            )
    except OSError as error:
        raise EnterpriseAuthorizationArtifactError(
            "authorization artifact directory is unreadable"
        ) from error
    if actual != expected:
        raise EnterpriseAuthorizationArtifactError(
            "authorization artifact directory inventory differs"
        )


def _write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as destination:
        destination.write(payload)


def _as[ModelT: BaseModel](value: BaseModel, model: type[ModelT]) -> ModelT:
    if not isinstance(value, model):
        raise EnterpriseAuthorizationArtifactError(
            "authorization artifact loader type mismatch"
        )
    return value


__all__ = [
    "EVALUATOR_AUTHORIZATION_FILES",
    "PUBLIC_AUTHORIZATION_FILES",
    "EnterpriseAuthorizationArtifactError",
    "EnterpriseAuthorizationEvaluatorArtifactsV1",
    "EnterpriseAuthorizationPublicArtifactsV1",
    "export_enterprise_authorization",
    "load_evaluator_enterprise_authorization",
    "load_public_enterprise_authorization",
]
