"""Strict, evaluator-separated Asteria C08 v2 records."""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Final, Literal, Self

from pydantic import Field, field_validator, model_validator

from synthworld.models import SyntheticModel

type C08SchemaVersion = Literal["2.0.0"]
type C08BenchmarkId = Literal["asteria-agentic-c08-v2"]
type C08ArtifactVisibility = Literal["public", "evaluator", "submission"]
type C08MetricName = Literal[
    "exact_evidence_match",
    "missing_or_discarded_free",
    "fabricated_evidence_free",
    "wrong_action_evidence_free",
    "extra_evidence_free",
]

C08_SCHEMA_VERSION: Final[C08SchemaVersion] = "2.0.0"
C08_BENCHMARK_ID: Final[C08BenchmarkId] = "asteria-agentic-c08-v2"
C08_PUBLIC_ARTIFACT = "c08-asteria-public.json"
C08_EVALUATOR_ARTIFACT = "c08-asteria-evaluator.json"
C08_SUBMISSION_ARTIFACT = "c08-asteria-submission.json"
C08_MANIFEST_ARTIFACT = "manifest.json"
C08_METRIC_NAMES: Final[tuple[C08MetricName, ...]] = (
    "exact_evidence_match",
    "missing_or_discarded_free",
    "fabricated_evidence_free",
    "wrong_action_evidence_free",
    "extra_evidence_free",
)


def _canonical_strings(values: tuple[str, ...], label: str) -> tuple[str, ...]:
    if not values or any(not value.strip() for value in values):
        raise ValueError(f"{label} must contain nonblank values")
    if len(set(values)) != len(values):
        raise ValueError(f"{label} must be unique")
    return tuple(sorted(values))


class C08EvidenceKind(StrEnum):
    AUTHORITY_RECORD = "authority_record"
    POLICY_RECORD = "policy_record"
    RESOURCE_RECORD = "resource_record"
    REVOCATION_RECORD = "revocation_record"


class C08ScenarioKind(StrEnum):
    EXACT = "exact"
    MISSING = "missing"
    FABRICATED = "fabricated"
    WRONG_ACTION = "wrong_action"
    EXTRA = "extra"
    DISCARDED = "discarded"


class C08MeasurementScopeV2(SyntheticModel):
    """Claims deliberately limited to offline synthetic artifact evaluation."""

    offline_artifacts_only: Literal[True] = True
    proves: tuple[str, ...] = Field(min_length=1)
    does_not_prove: tuple[str, ...] = Field(min_length=1)

    _canonical_proves = field_validator("proves", "does_not_prove")(
        lambda value, info: _canonical_strings(value, info.field_name)
    )


class C08EvidenceRequirementV2(SyntheticModel):
    """Public evidence semantics without an expected observation identity."""

    evidence_kind: C08EvidenceKind
    binding_handle: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    )


class C08PublicActionV2(SyntheticModel):
    action_event_id: str = Field(min_length=1)
    event_order: int = Field(ge=1)
    action: str = Field(min_length=1)
    resource_id: str = Field(min_length=1)
    requested_scope: tuple[str, ...] = Field(min_length=1)
    required_evidence: tuple[C08EvidenceRequirementV2, ...] = Field(min_length=1)

    @field_validator("requested_scope")
    @classmethod
    def canonical_scope(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_strings(value, "requested_scope")

    @field_validator("required_evidence")
    @classmethod
    def canonical_requirements(
        cls, value: tuple[C08EvidenceRequirementV2, ...]
    ) -> tuple[C08EvidenceRequirementV2, ...]:
        identities = tuple((item.evidence_kind, item.binding_handle) for item in value)
        if len(set(identities)) != len(identities):
            raise ValueError("required evidence kind/handle pairs must be unique")
        return tuple(
            sorted(
                value,
                key=lambda item: (item.evidence_kind.value, item.binding_handle),
            )
        )


class C08EvidenceObservationV2(SyntheticModel):
    observation_id: str = Field(min_length=1)
    action_event_id: str = Field(min_length=1)
    observation_order: int = Field(ge=1)
    evidence_kind: C08EvidenceKind
    binding_handle: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    )
    payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class C08AsteriaPublicInputV2(SyntheticModel):
    schema_version: C08SchemaVersion = C08_SCHEMA_VERSION
    benchmark_id: C08BenchmarkId = C08_BENCHMARK_ID
    measurement_scope: C08MeasurementScopeV2
    actions: tuple[C08PublicActionV2, ...] = Field(min_length=1)
    evidence_observations: tuple[C08EvidenceObservationV2, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_order_and_references(self) -> Self:
        action_ids = tuple(item.action_event_id for item in self.actions)
        if len(set(action_ids)) != len(action_ids):
            raise ValueError("public action ids must be unique")
        if tuple(item.event_order for item in self.actions) != tuple(
            range(1, len(self.actions) + 1)
        ):
            raise ValueError("public actions must have contiguous event order")
        observation_ids = tuple(
            item.observation_id for item in self.evidence_observations
        )
        if len(set(observation_ids)) != len(observation_ids):
            raise ValueError("public observation ids must be unique")
        observation_orders = tuple(
            item.observation_order for item in self.evidence_observations
        )
        if observation_orders != tuple(range(1, len(self.evidence_observations) + 1)):
            raise ValueError("public observations must preserve order")
        if any(
            item.action_event_id not in set(action_ids)
            for item in self.evidence_observations
        ):
            raise ValueError("public observation references an unknown action")
        observation_bindings = tuple(
            (item.action_event_id, item.evidence_kind, item.binding_handle)
            for item in self.evidence_observations
        )
        if len(set(observation_bindings)) != len(observation_bindings):
            raise ValueError(
                "public action/kind/binding-handle observations must be unique"
            )
        observations_by_action = {
            action_id: tuple(
                item
                for item in self.evidence_observations
                if item.action_event_id == action_id
            )
            for action_id in action_ids
        }
        for action in self.actions:
            action_observations = observations_by_action[action.action_event_id]
            for requirement in action.required_evidence:
                same_kind = tuple(
                    item
                    for item in action_observations
                    if item.evidence_kind is requirement.evidence_kind
                )
                matching = tuple(
                    item
                    for item in same_kind
                    if item.binding_handle == requirement.binding_handle
                )
                if len(matching) != 1:
                    raise ValueError(
                        "public requirement must select exactly one binding handle"
                    )
                if not any(
                    item.binding_handle != requirement.binding_handle
                    for item in same_kind
                ):
                    raise ValueError(
                        "public requirement must have a same-kind binding distractor"
                    )
        return self


class C08EvidenceBindingV2(SyntheticModel):
    """Evaluator-only action-to-required-observation truth."""

    action_event_id: str = Field(min_length=1)
    required_observation_ids: tuple[str, ...] = Field(min_length=1)
    scenario_kind: C08ScenarioKind

    @field_validator("required_observation_ids")
    @classmethod
    def canonical_required_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_strings(value, "required_observation_ids")


class C08AsteriaEvaluatorV2(SyntheticModel):
    schema_version: C08SchemaVersion = C08_SCHEMA_VERSION
    benchmark_id: C08BenchmarkId = C08_BENCHMARK_ID
    public_input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    measurement_scope: C08MeasurementScopeV2
    bindings: tuple[C08EvidenceBindingV2, ...] = Field(min_length=1)

    @field_validator("bindings")
    @classmethod
    def canonical_bindings(
        cls, value: tuple[C08EvidenceBindingV2, ...]
    ) -> tuple[C08EvidenceBindingV2, ...]:
        ids = tuple(item.action_event_id for item in value)
        if len(set(ids)) != len(ids):
            raise ValueError("evaluator binding action ids must be unique")
        return tuple(sorted(value, key=lambda item: item.action_event_id))


class C08SubmissionRowV2(SyntheticModel):
    action_event_id: str = Field(min_length=1)
    retained_observation_ids: tuple[str, ...]

    @field_validator("retained_observation_ids")
    @classmethod
    def canonical_retained_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("retained observation ids must be unique")
        if any(not item.strip() for item in value):
            raise ValueError("retained observation ids must be nonblank")
        return tuple(sorted(value))


class C08AsteriaSubmissionV2(SyntheticModel):
    schema_version: C08SchemaVersion = C08_SCHEMA_VERSION
    benchmark_id: C08BenchmarkId = C08_BENCHMARK_ID
    public_input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    rows: tuple[C08SubmissionRowV2, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def canonical_rows(self) -> Self:
        ids = tuple(item.action_event_id for item in self.rows)
        if len(set(ids)) != len(ids):
            raise ValueError("submission action ids must be unique")
        ordered = tuple(sorted(self.rows, key=lambda item: item.action_event_id))
        if ordered != self.rows:
            return self.model_copy(update={"rows": ordered})
        return self


class C08AsteriaBenchmarkV2(SyntheticModel):
    schema_version: C08SchemaVersion = C08_SCHEMA_VERSION
    benchmark_id: C08BenchmarkId = C08_BENCHMARK_ID
    public: C08AsteriaPublicInputV2
    evaluator: C08AsteriaEvaluatorV2

    @model_validator(mode="after")
    def bind_public_and_evaluator(self) -> Self:
        public_actions = {item.action_event_id: item for item in self.public.actions}
        binding_ids = {item.action_event_id for item in self.evaluator.bindings}
        observations = {
            item.observation_id: item for item in self.public.evidence_observations
        }
        if set(public_actions) != binding_ids:
            raise ValueError("public actions and evaluator bindings must match")
        for binding in self.evaluator.bindings:
            required = tuple(
                observations.get(observation_id)
                for observation_id in binding.required_observation_ids
            )
            if any(item is None for item in required):
                raise ValueError("evaluator binding references an unknown observation")
            action = public_actions[binding.action_event_id]
            if any(
                item.action_event_id != binding.action_event_id
                for item in required
                if item is not None
            ):
                raise ValueError("evaluator binding crosses public actions")
            required_semantics = {
                (item.evidence_kind, item.binding_handle)
                for item in required
                if item is not None
            }
            public_semantics = {
                (item.evidence_kind, item.binding_handle)
                for item in action.required_evidence
            }
            if len(required) != len(action.required_evidence) or (
                required_semantics != public_semantics
            ):
                raise ValueError(
                    "evaluator binding evidence handles differ from public action"
                )
        return self


class C08MetricV2(SyntheticModel):
    name: C08MetricName
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    value: float | None
    denominator_meaning: str = Field(min_length=1)
    undefined_reason: str | None = None

    @model_validator(mode="after")
    def validate_metric(self) -> Self:
        if self.numerator > self.denominator:
            raise ValueError("metric numerator cannot exceed denominator")
        if self.value is None:
            if self.denominator or self.undefined_reason is None:
                raise ValueError("undefined metric must have zero support and a reason")
        else:
            if not self.denominator or self.undefined_reason is not None:
                raise ValueError("defined metric must have support and no reason")
            if not math.isfinite(self.value) or not math.isclose(
                self.value,
                self.numerator / self.denominator,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                raise ValueError("metric value must equal numerator / denominator")
        return self


class C08MetricsReportV2(SyntheticModel):
    schema_version: C08SchemaVersion = C08_SCHEMA_VERSION
    benchmark_id: C08BenchmarkId = C08_BENCHMARK_ID
    public_input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    measurement_scope: C08MeasurementScopeV2
    metrics: tuple[C08MetricV2, ...] = Field(min_length=len(C08_METRIC_NAMES))

    @model_validator(mode="after")
    def require_metric_set(self) -> Self:
        names = tuple(item.name for item in self.metrics)
        if names != C08_METRIC_NAMES:
            raise ValueError(
                "C08 metrics must be emitted in the fixed independent order"
            )
        return self


class C08ArtifactDescriptorV2(SyntheticModel):
    path: str = Field(min_length=1)
    byte_size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class C08ArtifactManifestV2(SyntheticModel):
    schema_version: C08SchemaVersion = C08_SCHEMA_VERSION
    benchmark_id: C08BenchmarkId = C08_BENCHMARK_ID
    visibility: C08ArtifactVisibility
    artifact_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifacts: tuple[C08ArtifactDescriptorV2, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def canonical_artifacts(self) -> Self:
        paths = tuple(item.path for item in self.artifacts)
        if len(set(paths)) != len(paths):
            raise ValueError("manifest artifact paths must be unique")
        ordered = tuple(sorted(self.artifacts, key=lambda item: item.path))
        if ordered != self.artifacts:
            return self.model_copy(update={"artifacts": ordered})
        return self


def _canonical_frozen_artifacts(
    artifacts: tuple[C08ArtifactDescriptorV2, ...],
) -> tuple[C08ArtifactDescriptorV2, ...]:
    paths = tuple(item.path for item in artifacts)
    if len(set(paths)) != len(paths):
        raise ValueError("frozen manifest artifact paths must be unique")
    return tuple(sorted(artifacts, key=lambda item: item.path))


class C08FrozenPublicManifestV2(SyntheticModel):
    schema_version: C08SchemaVersion = C08_SCHEMA_VERSION
    benchmark_id: C08BenchmarkId = C08_BENCHMARK_ID
    seed: Literal[20260809] = 20260809
    visibility: Literal["public"] = "public"
    artifact_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifacts: tuple[C08ArtifactDescriptorV2, ...] = Field(min_length=1, max_length=1)

    @model_validator(mode="after")
    def validate_inventory(self) -> Self:
        ordered = _canonical_frozen_artifacts(self.artifacts)
        if tuple(item.path for item in ordered) != (C08_PUBLIC_ARTIFACT,):
            raise ValueError("frozen public manifest inventory differs")
        if ordered != self.artifacts:
            return self.model_copy(update={"artifacts": ordered})
        return self


class C08FrozenEvaluatorManifestV2(SyntheticModel):
    schema_version: C08SchemaVersion = C08_SCHEMA_VERSION
    benchmark_id: C08BenchmarkId = C08_BENCHMARK_ID
    seed: Literal[20260809] = 20260809
    visibility: Literal["evaluator"] = "evaluator"
    public_input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifacts: tuple[C08ArtifactDescriptorV2, ...] = Field(min_length=1, max_length=1)

    @model_validator(mode="after")
    def validate_inventory(self) -> Self:
        ordered = _canonical_frozen_artifacts(self.artifacts)
        if tuple(item.path for item in ordered) != (C08_EVALUATOR_ARTIFACT,):
            raise ValueError("frozen evaluator manifest inventory differs")
        if ordered != self.artifacts:
            return self.model_copy(update={"artifacts": ordered})
        return self


class C08FrozenRootManifestV2(SyntheticModel):
    schema_version: C08SchemaVersion = C08_SCHEMA_VERSION
    benchmark_id: C08BenchmarkId = C08_BENCHMARK_ID
    seed: Literal[20260809] = 20260809
    visibility: Literal["root"] = "root"
    public_input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluator_public_input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    public_artifact_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluator_artifact_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifacts: tuple[C08ArtifactDescriptorV2, ...] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def validate_inventory(self) -> Self:
        ordered = _canonical_frozen_artifacts(self.artifacts)
        expected = (
            "evaluator/c08-asteria-evaluator.json",
            "evaluator/manifest.json",
            "public/c08-asteria-public.json",
            "public/manifest.json",
        )
        if tuple(item.path for item in ordered) != expected:
            raise ValueError("frozen root manifest inventory differs")
        if ordered != self.artifacts:
            return self.model_copy(update={"artifacts": ordered})
        return self


__all__ = [
    "C08_BENCHMARK_ID",
    "C08_EVALUATOR_ARTIFACT",
    "C08_MANIFEST_ARTIFACT",
    "C08_METRIC_NAMES",
    "C08_PUBLIC_ARTIFACT",
    "C08_SCHEMA_VERSION",
    "C08_SUBMISSION_ARTIFACT",
    "C08ArtifactDescriptorV2",
    "C08ArtifactManifestV2",
    "C08AsteriaBenchmarkV2",
    "C08AsteriaEvaluatorV2",
    "C08AsteriaPublicInputV2",
    "C08AsteriaSubmissionV2",
    "C08EvidenceBindingV2",
    "C08EvidenceKind",
    "C08EvidenceObservationV2",
    "C08EvidenceRequirementV2",
    "C08FrozenEvaluatorManifestV2",
    "C08FrozenPublicManifestV2",
    "C08FrozenRootManifestV2",
    "C08MeasurementScopeV2",
    "C08MetricV2",
    "C08MetricsReportV2",
    "C08PublicActionV2",
    "C08ScenarioKind",
    "C08SubmissionRowV2",
]
