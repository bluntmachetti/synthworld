"""Immutable enterprise-lineage v2 C08 models."""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Final, Literal, Self

from pydantic import Field, field_validator, model_validator

from synthworld.models import SyntheticModel

C08_V2_SCHEMA_VERSION: Final[Literal["2.0.0"]] = "2.0.0"
C08_FROZEN_BENCHMARK_ID: Final[Literal["enterprise-agentic-c08-v2"]] = (
    "enterprise-agentic-c08-v2"
)
C08_FROZEN_SEED: Final[Literal[20260809]] = 20260809
C08_REPORT_LIMITATIONS = (
    "offline scoring does not prove live evidence retention",
    "offline scoring does not prove durable logging",
    "offline scoring does not prove enforcement behavior",
)


def _ordered_ids(value: tuple[str, ...], label: str) -> tuple[str, ...]:
    if any(not item.strip() for item in value):
        raise ValueError(f"{label} must contain nonblank identifiers")
    if len(set(value)) != len(value):
        raise ValueError(f"{label} must not contain duplicates")
    if value != tuple(sorted(value)):
        raise ValueError(f"{label} must be sorted")
    return value


class C08CaseOutcomeV2(StrEnum):
    EXACT = "exact"
    MISSING = "missing"
    FABRICATED = "fabricated"
    WRONG_ACTION = "wrong_action"
    EXTRA = "extra"


class C08EvidenceKindV2(StrEnum):
    AUTHORITY = "authority"
    IDENTITY = "identity"
    POLICY = "policy"
    REVOCATION = "revocation"


class C08EvidenceRequirementV2(SyntheticModel):
    """Public non-oracle requirement semantics for one evidence candidate."""

    kind: C08EvidenceKindV2
    binding_handle: str = Field(min_length=16)


class C08SourceActionV2(SyntheticModel):
    """Oracle-bearing source record, never serialized as public input."""

    action_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    resource_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    tick: int = Field(ge=0)
    required_evidence: tuple[C08EvidenceRequirementV2, ...] = Field(min_length=1)
    required_evidence_ids: tuple[str, ...] = Field(min_length=1)

    @field_validator("required_evidence_ids")
    @classmethod
    def canonical_evidence_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _ordered_ids(value, "C08 evidence identifiers")

    @field_validator("required_evidence")
    @classmethod
    def canonical_evidence_requirements(
        cls, value: tuple[C08EvidenceRequirementV2, ...]
    ) -> tuple[C08EvidenceRequirementV2, ...]:
        keys = tuple((item.kind.value, item.binding_handle) for item in value)
        if len(set(keys)) != len(keys):
            raise ValueError("C08 evidence requirements must not contain duplicates")
        if keys != tuple(sorted(keys)):
            raise ValueError("C08 evidence requirements must be sorted")
        return value

    @model_validator(mode="after")
    def required_evidence_shapes_match(self) -> Self:
        if len(self.required_evidence_ids) != len(self.required_evidence):
            raise ValueError(
                "C08 required evidence IDs and requirements must have equal length"
            )
        return self


class C08EvidenceEventV2(SyntheticModel):
    """Public evidence semantics with an opaque, non-oracle evidence ID."""

    sequence: int = Field(ge=0)
    evidence_id: str = Field(min_length=1)
    action_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    resource_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    tick: int = Field(ge=0)
    kind: C08EvidenceKindV2
    binding_handle: str = Field(min_length=16)
    payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class C08SourceWorldV2(SyntheticModel):
    """Bounded oracle-bearing input used only to construct v2 projections."""

    actions: tuple[C08SourceActionV2, ...] = Field(min_length=1)
    evidence_events: tuple[C08EvidenceEventV2, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def canonical_action_order(self) -> Self:
        action_ids = tuple(item.action_id for item in self.actions)
        if len(set(action_ids)) != len(action_ids):
            raise ValueError("C08 action identifiers must be unique")
        expected = tuple(
            sorted(self.actions, key=lambda item: (item.tick, item.action_id))
        )
        if self.actions != expected:
            raise ValueError("C08 actions must be ordered by tick and action ID")
        evidence_ids = tuple(item.evidence_id for item in self.evidence_events)
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError("C08 evidence identifiers must be globally unique")
        if tuple(item.sequence for item in self.evidence_events) != tuple(
            range(len(self.evidence_events))
        ):
            raise ValueError("C08 evidence events must have contiguous sequence order")
        observed_bindings: set[tuple[str, C08EvidenceKindV2, str]] = set()
        actions = {item.action_id: item for item in self.actions}
        for event in self.evidence_events:
            binding = (event.action_id, event.kind, event.binding_handle)
            if binding in observed_bindings:
                raise ValueError(
                    "C08 evidence action/kind/handle bindings must be unique"
                )
            observed_bindings.add(binding)
            action = actions.get(event.action_id)
            if action is None:
                raise ValueError("C08 evidence event references an unknown action")
            if (
                event.tenant_id,
                event.resource_id,
                event.action,
                event.tick,
            ) != (action.tenant_id, action.resource_id, action.action, action.tick):
                raise ValueError("C08 evidence event semantics differ from its action")
        events_by_id = {item.evidence_id: item for item in self.evidence_events}
        for action in self.actions:
            try:
                required = tuple(
                    (
                        events_by_id[item].kind.value,
                        events_by_id[item].binding_handle,
                    )
                    for item in action.required_evidence_ids
                )
            except KeyError as error:
                raise ValueError(
                    "C08 required evidence ID is not in the evidence stream"
                ) from error
            required_bindings = tuple(sorted(required))
            expected_bindings = tuple(
                (item.kind.value, item.binding_handle)
                for item in action.required_evidence
            )
            if required_bindings != expected_bindings:
                raise ValueError(
                    "C08 required evidence semantics differ from required IDs"
                )
        return self


class C08PublicActionV2(SyntheticModel):
    """Product-facing action with no answer-key evidence binding."""

    action_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    resource_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    tick: int = Field(ge=0)
    required_evidence: tuple[C08EvidenceRequirementV2, ...] = Field(min_length=1)

    @field_validator("required_evidence")
    @classmethod
    def canonical_evidence_requirements(
        cls, value: tuple[C08EvidenceRequirementV2, ...]
    ) -> tuple[C08EvidenceRequirementV2, ...]:
        keys = tuple((item.kind.value, item.binding_handle) for item in value)
        if len(set(keys)) != len(keys):
            raise ValueError("C08 public requirements must not contain duplicates")
        if keys != tuple(sorted(keys)):
            raise ValueError("C08 public requirements must be sorted")
        return value


class C08PublicInputV2(SyntheticModel):
    schema_version: Literal["2.0.0"] = C08_V2_SCHEMA_VERSION
    actions: tuple[C08PublicActionV2, ...] = Field(min_length=1)
    evidence_events: tuple[C08EvidenceEventV2, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def canonical_action_order(self) -> Self:
        action_ids = tuple(item.action_id for item in self.actions)
        if len(set(action_ids)) != len(action_ids):
            raise ValueError("C08 public action identifiers must be unique")
        expected = tuple(
            sorted(self.actions, key=lambda item: (item.tick, item.action_id))
        )
        if self.actions != expected:
            raise ValueError("C08 public actions must be ordered by tick and action ID")
        evidence_ids = tuple(item.evidence_id for item in self.evidence_events)
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError("C08 public evidence identifiers must be unique")
        if tuple(item.sequence for item in self.evidence_events) != tuple(
            range(len(self.evidence_events))
        ):
            raise ValueError(
                "C08 public evidence events must have contiguous sequence order"
            )
        observed_bindings: set[tuple[str, C08EvidenceKindV2, str]] = set()
        actions_by_id = {item.action_id: item for item in self.actions}
        for event in self.evidence_events:
            binding = (event.action_id, event.kind, event.binding_handle)
            if binding in observed_bindings:
                raise ValueError(
                    "C08 public action/kind/handle bindings must be unique"
                )
            observed_bindings.add(binding)
            action = actions_by_id.get(event.action_id)
            if action is None:
                raise ValueError("C08 public evidence event references unknown action")
            if (
                event.tenant_id,
                event.resource_id,
                event.action,
                event.tick,
            ) != (action.tenant_id, action.resource_id, action.action, action.tick):
                raise ValueError(
                    "C08 public evidence event semantics differ from action"
                )
        for action in self.actions:
            required_handles_by_kind = {
                requirement.kind: {
                    item.binding_handle
                    for item in action.required_evidence
                    if item.kind is requirement.kind
                }
                for requirement in action.required_evidence
            }
            for requirement in action.required_evidence:
                matches = sum(
                    event.action_id == action.action_id
                    and event.kind is requirement.kind
                    and event.binding_handle == requirement.binding_handle
                    for event in self.evidence_events
                )
                if matches != 1:
                    raise ValueError(
                        "C08 public requirement must resolve to exactly one observation"
                    )
                has_distractor = any(
                    event.action_id == action.action_id
                    and event.kind is requirement.kind
                    and event.binding_handle
                    not in required_handles_by_kind[requirement.kind]
                    for event in self.evidence_events
                )
                if not has_distractor:
                    raise ValueError(
                        "C08 public requirement must have at least one "
                        "same-action/same-kind distractor with a different "
                        "binding handle"
                    )
        return self


class C08EvidenceBindingV2(SyntheticModel):
    """Evaluator-only binding between one action and its evidence universe."""

    action_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    required_evidence: tuple[C08EvidenceRequirementV2, ...] = Field(min_length=1)
    required_observation_ids: tuple[str, ...] = Field(min_length=1)

    @field_validator("required_observation_ids")
    @classmethod
    def canonical_observation_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _ordered_ids(value, "C08 binding observation identifiers")

    @field_validator("required_evidence")
    @classmethod
    def canonical_evidence_requirements(
        cls, value: tuple[C08EvidenceRequirementV2, ...]
    ) -> tuple[C08EvidenceRequirementV2, ...]:
        keys = tuple((item.kind.value, item.binding_handle) for item in value)
        if len(set(keys)) != len(keys):
            raise ValueError("C08 binding requirements must not contain duplicates")
        if keys != tuple(sorted(keys)):
            raise ValueError("C08 binding requirements must be sorted")
        return value

    @model_validator(mode="after")
    def required_evidence_shapes_match(self) -> Self:
        if len(self.required_observation_ids) != len(self.required_evidence):
            raise ValueError(
                "C08 binding observation IDs and requirements must have equal length"
            )
        return self


class C08EvaluatorTruthV2(SyntheticModel):
    schema_version: Literal["2.0.0"] = C08_V2_SCHEMA_VERSION
    public_input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    bindings: tuple[C08EvidenceBindingV2, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def canonical_bindings(self) -> Self:
        action_ids = tuple(item.action_id for item in self.bindings)
        if len(set(action_ids)) != len(action_ids):
            raise ValueError("C08 binding action identifiers must be unique")
        if self.bindings != tuple(
            sorted(self.bindings, key=lambda item: item.action_id)
        ):
            raise ValueError("C08 bindings must be sorted by action ID")
        required_ids = tuple(
            observation_id
            for binding in self.bindings
            for observation_id in binding.required_observation_ids
        )
        if len(set(required_ids)) != len(required_ids):
            raise ValueError(
                "C08 required observation identifiers must be globally unique"
            )
        return self


class C08EvidenceObservationV2(SyntheticModel):
    """One ordered evidence observation submitted for an action."""

    observation_id: str = Field(min_length=1)
    sequence: int = Field(ge=0)
    action_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    evidence_id: str = Field(min_length=1)


class C08SubmissionV2(SyntheticModel):
    schema_version: Literal["2.0.0"] = C08_V2_SCHEMA_VERSION
    public_input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    observations: tuple[C08EvidenceObservationV2, ...]

    @model_validator(mode="after")
    def canonical_observation_order(self) -> Self:
        observation_ids = tuple(item.observation_id for item in self.observations)
        if len(set(observation_ids)) != len(observation_ids):
            raise ValueError("C08 observation identifiers must be unique")
        sequences = tuple(item.sequence for item in self.observations)
        if sequences != tuple(range(len(self.observations))):
            raise ValueError("C08 observations must have contiguous sequence order")
        return self


class C08CaseResultV2(SyntheticModel):
    action_id: str = Field(min_length=1)
    outcome: C08CaseOutcomeV2
    required_count: int = Field(ge=1)
    submitted_count: int = Field(ge=0)


class C08EvaluationMetricV2(SyntheticModel):
    name: str = Field(min_length=1)
    value: float | None = Field(default=None, ge=0.0, le=1.0)
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    denominator_meaning: str = Field(min_length=1)
    undefined_reason: str | None = None

    @model_validator(mode="after")
    def validate_metric(self) -> Self:
        if self.numerator > self.denominator:
            raise ValueError("C08 metric numerator cannot exceed denominator")
        if self.denominator == 0:
            if self.value is not None:
                raise ValueError("undefined C08 metric cannot have a value")
            if self.undefined_reason is None:
                raise ValueError("undefined C08 metric requires a reason")
        else:
            if self.value is None:
                raise ValueError("defined C08 metric requires a value")
            if self.undefined_reason is not None:
                raise ValueError("defined C08 metric cannot have an undefined reason")
            if not math.isclose(
                self.value,
                self.numerator / self.denominator,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                raise ValueError("C08 metric value must equal numerator / denominator")
        return self


class C08MeasurementScopeV2(SyntheticModel):
    """Claims explicitly bounded to deterministic offline artifact scoring."""

    offline_artifacts_only: Literal[True] = True
    limitations: tuple[str, ...] = C08_REPORT_LIMITATIONS

    @field_validator("limitations")
    @classmethod
    def fixed_limitations(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != C08_REPORT_LIMITATIONS:
            raise ValueError("C08 report limitations are fixed")
        return value


class C08EvaluationReportV2(SyntheticModel):
    schema_version: Literal["2.0.0"] = C08_V2_SCHEMA_VERSION
    public_input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    measurement_scope: C08MeasurementScopeV2
    outcomes: tuple[C08CaseResultV2, ...] = Field(min_length=1)
    metrics: tuple[C08EvaluationMetricV2, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def canonical_report_order(self) -> Self:
        if self.outcomes != tuple(
            sorted(self.outcomes, key=lambda item: item.action_id)
        ):
            raise ValueError("C08 outcomes must be sorted by action ID")
        if self.metrics != tuple(sorted(self.metrics, key=lambda item: item.name)):
            raise ValueError("C08 metrics must be sorted by name")
        return self


class C08FrozenArtifactV2(SyntheticModel):
    """Manifest entry for one payload in the frozen public/evaluator tree."""

    path: str = Field(pattern=r"^(public|evaluator)/[A-Za-z0-9._-]+$")
    byte_size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class C08FrozenManifestV2(SyntheticModel):
    """Separate immutable contract for the enterprise frozen benchmark tree."""

    schema_version: Literal["2.0.0"] = C08_V2_SCHEMA_VERSION
    benchmark_id: Literal["enterprise-agentic-c08-v2"] = C08_FROZEN_BENCHMARK_ID
    seed: Literal[20260809] = C08_FROZEN_SEED
    public_input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    checksum_algorithm: Literal["sha256"] = "sha256"
    checksum_file: Literal["SHA256SUMS"] = "SHA256SUMS"
    checksum_excludes: tuple[Literal["SHA256SUMS"], ...] = ("SHA256SUMS",)
    public_inventory: tuple[C08FrozenArtifactV2, ...] = Field(min_length=1)
    evaluator_inventory: tuple[C08FrozenArtifactV2, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_inventory(self) -> Self:
        if self.checksum_excludes != ("SHA256SUMS",):
            raise ValueError("C08 frozen checksum self-exclusion is fixed")
        for inventory, prefix in (
            (self.public_inventory, "public/"),
            (self.evaluator_inventory, "evaluator/"),
        ):
            paths = tuple(item.path for item in inventory)
            if paths != tuple(sorted(paths)) or len(set(paths)) != len(paths):
                raise ValueError("C08 frozen inventories must be unique and sorted")
            if any(not path.startswith(prefix) for path in paths):
                raise ValueError("C08 frozen inventory path escapes its tree")
        if set(item.path for item in self.public_inventory) & set(
            item.path for item in self.evaluator_inventory
        ):
            raise ValueError("C08 frozen inventories must be disjoint")
        return self


__all__ = [
    "C08_FROZEN_BENCHMARK_ID",
    "C08_FROZEN_SEED",
    "C08CaseOutcomeV2",
    "C08CaseResultV2",
    "C08EvaluationMetricV2",
    "C08EvaluationReportV2",
    "C08EvaluatorTruthV2",
    "C08EvidenceBindingV2",
    "C08EvidenceEventV2",
    "C08EvidenceKindV2",
    "C08EvidenceObservationV2",
    "C08EvidenceRequirementV2",
    "C08FrozenArtifactV2",
    "C08FrozenManifestV2",
    "C08MeasurementScopeV2",
    "C08PublicActionV2",
    "C08PublicInputV2",
    "C08SourceActionV2",
    "C08SourceWorldV2",
    "C08SubmissionV2",
]
