"""Immutable enterprise-lineage v2 C08 models."""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from synthworld.models import SyntheticModel

C08_V2_SCHEMA_VERSION = "2.0.0"


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


class C08SourceActionV2(SyntheticModel):
    """Oracle-bearing source record, never serialized as public input."""

    action_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    resource_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    tick: int = Field(ge=0)
    required_evidence_kinds: tuple[C08EvidenceKindV2, ...] = Field(min_length=1)
    required_evidence_ids: tuple[str, ...] = Field(min_length=1)

    @field_validator("required_evidence_ids")
    @classmethod
    def canonical_evidence_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _ordered_ids(value, "C08 evidence identifiers")

    @field_validator("required_evidence_kinds")
    @classmethod
    def canonical_evidence_kinds(
        cls, value: tuple[C08EvidenceKindV2, ...]
    ) -> tuple[C08EvidenceKindV2, ...]:
        if len(set(value)) != len(value):
            raise ValueError("C08 evidence kinds must not contain duplicates")
        if value != tuple(sorted(value, key=lambda item: item.value)):
            raise ValueError("C08 evidence kinds must be sorted")
        return value

    @model_validator(mode="after")
    def required_evidence_shapes_match(self) -> Self:
        if len(self.required_evidence_ids) != len(self.required_evidence_kinds):
            raise ValueError("C08 required evidence IDs and kinds must have equal length")
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
        expected = tuple(sorted(self.actions, key=lambda item: (item.tick, item.action_id)))
        if self.actions != expected:
            raise ValueError("C08 actions must be ordered by tick and action ID")
        evidence_ids = tuple(item.evidence_id for item in self.evidence_events)
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError("C08 evidence identifiers must be globally unique")
        if tuple(item.sequence for item in self.evidence_events) != tuple(
            range(len(self.evidence_events))
        ):
            raise ValueError("C08 evidence events must have contiguous sequence order")
        actions = {item.action_id: item for item in self.actions}
        for event in self.evidence_events:
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
                    events_by_id[item].kind for item in action.required_evidence_ids
                )
            except KeyError as error:
                raise ValueError(
                    "C08 required evidence ID is not in the evidence stream"
                ) from error
            required_kinds = tuple(sorted(required, key=lambda item: item.value))
            if required_kinds != action.required_evidence_kinds:
                raise ValueError("C08 required evidence kinds differ from required IDs")
        return self


class C08PublicActionV2(SyntheticModel):
    """Product-facing action with no answer-key evidence binding."""

    action_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    resource_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    tick: int = Field(ge=0)
    required_evidence_kinds: tuple[C08EvidenceKindV2, ...] = Field(min_length=1)

    @field_validator("required_evidence_kinds")
    @classmethod
    def canonical_evidence_kinds(
        cls, value: tuple[C08EvidenceKindV2, ...]
    ) -> tuple[C08EvidenceKindV2, ...]:
        if len(set(value)) != len(value):
            raise ValueError("C08 public evidence kinds must not contain duplicates")
        if value != tuple(sorted(value, key=lambda item: item.value)):
            raise ValueError("C08 public evidence kinds must be sorted")
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
        expected = tuple(sorted(self.actions, key=lambda item: (item.tick, item.action_id)))
        if self.actions != expected:
            raise ValueError("C08 public actions must be ordered by tick and action ID")
        evidence_ids = tuple(item.evidence_id for item in self.evidence_events)
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError("C08 public evidence identifiers must be unique")
        if tuple(item.sequence for item in self.evidence_events) != tuple(
            range(len(self.evidence_events))
        ):
            raise ValueError("C08 public evidence events must have contiguous sequence order")
        actions_by_id = {item.action_id: item for item in self.actions}
        for event in self.evidence_events:
            action = actions_by_id.get(event.action_id)
            if action is None:
                raise ValueError("C08 public evidence event references unknown action")
            if (
                event.tenant_id,
                event.resource_id,
                event.action,
                event.tick,
            ) != (action.tenant_id, action.resource_id, action.action, action.tick):
                raise ValueError("C08 public evidence event semantics differ from action")
        for action in self.actions:
            observed_kinds = {
                event.kind
                for event in self.evidence_events
                if event.action_id == action.action_id
            }
            if not set(action.required_evidence_kinds) <= observed_kinds:
                raise ValueError("C08 public evidence kinds are not observable for an action")
        return self


class C08EvidenceBindingV2(SyntheticModel):
    """Evaluator-only binding between one action and its evidence universe."""

    action_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    required_evidence_kinds: tuple[C08EvidenceKindV2, ...] = Field(min_length=1)
    required_evidence_ids: tuple[str, ...] = Field(min_length=1)

    @field_validator("required_evidence_ids")
    @classmethod
    def canonical_evidence_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _ordered_ids(value, "C08 binding evidence identifiers")

    @field_validator("required_evidence_kinds")
    @classmethod
    def canonical_evidence_kinds(
        cls, value: tuple[C08EvidenceKindV2, ...]
    ) -> tuple[C08EvidenceKindV2, ...]:
        if len(set(value)) != len(value):
            raise ValueError("C08 binding evidence kinds must not contain duplicates")
        if value != tuple(sorted(value, key=lambda item: item.value)):
            raise ValueError("C08 binding evidence kinds must be sorted")
        return value

    @model_validator(mode="after")
    def required_evidence_shapes_match(self) -> Self:
        if len(self.required_evidence_ids) != len(self.required_evidence_kinds):
            raise ValueError("C08 binding evidence IDs and kinds must have equal length")
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
        if self.bindings != tuple(sorted(self.bindings, key=lambda item: item.action_id)):
            raise ValueError("C08 bindings must be sorted by action ID")
        required_ids = tuple(
            evidence_id
            for binding in self.bindings
            for evidence_id in binding.required_evidence_ids
        )
        if len(set(required_ids)) != len(required_ids):
            raise ValueError("C08 binding required evidence identifiers must be globally unique")
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


class C08EvaluationReportV2(SyntheticModel):
    schema_version: Literal["2.0.0"] = C08_V2_SCHEMA_VERSION
    public_input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    outcomes: tuple[C08CaseResultV2, ...] = Field(min_length=1)
    metrics: tuple[C08EvaluationMetricV2, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def canonical_report_order(self) -> Self:
        if self.outcomes != tuple(sorted(self.outcomes, key=lambda item: item.action_id)):
            raise ValueError("C08 outcomes must be sorted by action ID")
        if self.metrics != tuple(sorted(self.metrics, key=lambda item: item.name)):
            raise ValueError("C08 metrics must be sorted by name")
        return self


__all__ = [
    "C08CaseOutcomeV2",
    "C08CaseResultV2",
    "C08EvidenceBindingV2",
    "C08EvidenceEventV2",
    "C08EvidenceKindV2",
    "C08EvidenceObservationV2",
    "C08EvaluationMetricV2",
    "C08EvaluationReportV2",
    "C08EvaluatorTruthV2",
    "C08PublicActionV2",
    "C08PublicInputV2",
    "C08SourceActionV2",
    "C08SourceWorldV2",
    "C08SubmissionV2",
]
