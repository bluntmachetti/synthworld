"""Strict contracts for bounded continuous identity and authority assurance."""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, ValidationInfo, field_validator, model_validator

from synthworld.enterprise.models import SyntheticDigestV1
from synthworld.models import SyntheticModel

CONTINUOUS_ASSURANCE_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
CONTINUOUS_ASSURANCE_BENCHMARK_VERSION: Literal["1.0.0"] = "1.0.0"
CONTINUOUS_ASSURANCE_SCORING_VERSION: Literal["1.0.0"] = "1.0.0"
CONTINUOUS_ASSURANCE_GENERATOR_VERSION: Literal["1.0.0"] = "1.0.0"


class ContinuousAssuranceTier(StrEnum):
    SMOKE = "smoke"
    STANDARD = "standard"
    LONGITUDINAL = "longitudinal"
    HELD_OUT = "held_out"


class ContinuousAssuranceSourceFamily(StrEnum):
    AUTHORITY_GOVERNANCE_1_0 = "authority_governance_1_0"
    CONTEXTUAL_ACCESS_1_0 = "contextual_access_1_0"
    ENTERPRISE_AGENTIC_1_0 = "enterprise_agentic_1_0"
    IDENTITY_FABRIC_1_0 = "identity_fabric_1_0"


class AssuranceDriftKind(StrEnum):
    CREDENTIAL = "credential"
    DELEGATION = "delegation"
    ENTITLEMENT = "entitlement"
    EVIDENCE = "evidence"
    OWNER = "owner"
    POLICY = "policy"


class AssuranceObservedState(StrEnum):
    ACTIVE = "active"
    CHANGED = "changed"
    HEALTHY = "healthy"
    INACTIVE = "inactive"
    MISSING = "missing"
    PRESENT = "present"
    RETAINED = "retained"
    WITHDRAWN = "withdrawn"


class ContinuousAssuranceCaseKind(StrEnum):
    CREDENTIAL_DRIFT = "credential_drift"
    DELEGATION_RECURRENCE = "delegation_recurrence"
    ENTITLEMENT_TRANSIENT_DRIFT = "entitlement_transient_drift"
    EVIDENCE_LATE_ARRIVAL = "evidence_late_arrival"
    FEED_OUTAGE_DELAY = "feed_outage_delay"
    OWNER_DRIFT = "owner_drift"
    POLICY_LATER_VERSION = "policy_later_version"
    STABLE_CONTROL = "stable_control"


class FindingLifecycleState(StrEnum):
    CLEAR = "clear"
    OPEN = "open"


class ContinuousAssuranceMetricFamily(StrEnum):
    CLASSIFICATION = "classification"
    DETECTION = "detection"
    EVIDENCE = "evidence"
    RECURRENCE = "recurrence"
    REMEDIATION = "remediation"
    STALENESS = "staleness"


class ContinuousAssuranceMetricAggregation(StrEnum):
    MEAN_TICKS = "mean_ticks"
    RATIO = "ratio"


class ContinuousAssuranceEmptyBehavior(StrEnum):
    NULL_IF_EMPTY = "null_if_empty"


class ContinuousAssuranceConfigV1(SyntheticModel):
    """Explicit private generation inputs; only selected projections are public."""

    schema_version: Literal["1.0.0"] = CONTINUOUS_ASSURANCE_SCHEMA_VERSION
    tier: ContinuousAssuranceTier = ContinuousAssuranceTier.SMOKE
    seed: int = Field(default=20_260_804, ge=0)
    risk_threshold: int = Field(default=70, ge=0, le=100)
    justification_kind: Literal[
        "business_need", "case_assignment", "emergency_access"
    ] = "business_need"


class ContinuousAssuranceSourceBindingV1(SyntheticModel):
    family: ContinuousAssuranceSourceFamily
    public_schema_version: str = Field(min_length=1)
    public_digest: SyntheticDigestV1


class ContinuousAssuranceEvaluatorSourceBindingV1(ContinuousAssuranceSourceBindingV1):
    evaluator_schema_version: str = Field(min_length=1)
    evaluator_digest: SyntheticDigestV1


class ContinuousAssuranceSourceReferenceV1(SyntheticModel):
    family: ContinuousAssuranceSourceFamily
    record_id: str = Field(min_length=1)
    record_digest: SyntheticDigestV1


class ContinuousAssuranceSignalV1(SyntheticModel):
    signal_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    dimension: AssuranceDriftKind
    source: ContinuousAssuranceSourceReferenceV1
    observed_state: AssuranceObservedState
    action_tick: int = Field(ge=0)
    decision_tick: int = Field(ge=0)
    effective_tick: int = Field(ge=0)
    observation_tick: int = Field(ge=0)
    audit_tick: int = Field(ge=0)
    policy_version_id: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)

    @field_validator("evidence_refs")
    @classmethod
    def canonical_evidence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_strings(value, "continuous-assurance signal evidence")

    @model_validator(mode="after")
    def ordered_coordinates(self) -> Self:
        coordinates = (
            self.action_tick,
            self.decision_tick,
            self.effective_tick,
            self.observation_tick,
            self.audit_tick,
        )
        if coordinates != tuple(sorted(coordinates)):
            raise ValueError("continuous-assurance signal coordinates must be ordered")
        return self


class ContinuousAssuranceRemediationV1(SyntheticModel):
    remediation_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    dimension: AssuranceDriftKind
    observed_state: AssuranceObservedState
    action_tick: int = Field(ge=0)
    decision_tick: int = Field(ge=0)
    effective_tick: int = Field(ge=0)
    observation_tick: int = Field(ge=0)
    audit_tick: int = Field(ge=0)
    evidence_refs: tuple[str, ...] = Field(min_length=1)

    @field_validator("evidence_refs")
    @classmethod
    def canonical_evidence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_strings(value, "continuous-assurance remediation evidence")

    @model_validator(mode="after")
    def ordered_coordinates(self) -> Self:
        coordinates = (
            self.action_tick,
            self.decision_tick,
            self.effective_tick,
            self.observation_tick,
            self.audit_tick,
        )
        if coordinates != tuple(sorted(coordinates)):
            raise ValueError(
                "continuous-assurance remediation coordinates must be ordered"
            )
        return self


class ContinuousAssuranceFeedWindowV1(SyntheticModel):
    feed_window_id: str = Field(min_length=1)
    source_family: ContinuousAssuranceSourceFamily
    unavailable_from_tick: int = Field(ge=0)
    restored_at_tick: int = Field(ge=0)
    delayed_signal_ids: tuple[str, ...] = Field(min_length=1)

    @field_validator("delayed_signal_ids")
    @classmethod
    def canonical_signals(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_strings(value, "continuous-assurance delayed signals")

    @model_validator(mode="after")
    def forward_window(self) -> Self:
        if self.restored_at_tick <= self.unavailable_from_tick:
            raise ValueError("continuous-assurance feed window must be forward")
        return self


class ContinuousAssuranceCaseV1(SyntheticModel):
    case_id: str = Field(min_length=1)
    signal_ids: tuple[str, ...] = Field(min_length=1)
    remediation_ids: tuple[str, ...] = ()
    feed_window_id: str | None = Field(default=None, min_length=1)

    @field_validator("signal_ids", "remediation_ids")
    @classmethod
    def canonical_references(
        cls, value: tuple[str, ...], info: ValidationInfo
    ) -> tuple[str, ...]:
        return _canonical_strings(value, f"continuous-assurance case {info.field_name}")


class ContinuousAssuranceCheckpointV1(SyntheticModel):
    checkpoint_id: str = Field(min_length=1)
    tick: int = Field(ge=0)
    observed_signal_ids: tuple[str, ...] = ()
    observed_remediation_ids: tuple[str, ...] = ()
    available_evidence_refs: tuple[str, ...] = ()

    @field_validator(
        "observed_signal_ids", "observed_remediation_ids", "available_evidence_refs"
    )
    @classmethod
    def canonical_references(
        cls, value: tuple[str, ...], info: ValidationInfo
    ) -> tuple[str, ...]:
        return _canonical_strings(
            value, f"continuous-assurance checkpoint {info.field_name}"
        )


class ContinuousAssuranceBenchmarkBindingV1(SyntheticModel):
    benchmark_family: Literal["continuous_assurance"] = "continuous_assurance"
    benchmark_version: Literal["1.0.0"] = CONTINUOUS_ASSURANCE_BENCHMARK_VERSION
    generator_version: Literal["1.0.0"] = CONTINUOUS_ASSURANCE_GENERATOR_VERSION
    tier: ContinuousAssuranceTier
    source_public_bindings_digest: SyntheticDigestV1
    case_inventory_digest: SyntheticDigestV1
    policy_profile_id: str = Field(min_length=1)


class ContinuousAssurancePublicV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = CONTINUOUS_ASSURANCE_SCHEMA_VERSION
    benchmark: ContinuousAssuranceBenchmarkBindingV1
    horizon_tick: int = Field(ge=0)
    source_bindings: tuple[ContinuousAssuranceSourceBindingV1, ...] = Field(
        min_length=1
    )
    signals: tuple[ContinuousAssuranceSignalV1, ...] = Field(min_length=1)
    remediations: tuple[ContinuousAssuranceRemediationV1, ...]
    feed_windows: tuple[ContinuousAssuranceFeedWindowV1, ...]
    cases: tuple[ContinuousAssuranceCaseV1, ...] = Field(min_length=1)
    checkpoints: tuple[ContinuousAssuranceCheckpointV1, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def canonical_inventories(self) -> Self:
        _require_model_order(self.source_bindings, "family", "source bindings")
        _require_model_order(self.cases, "case_id", "cases")
        _require_model_order(self.feed_windows, "feed_window_id", "feed windows")
        signal_keys = tuple(
            (item.effective_tick, item.signal_id) for item in self.signals
        )
        if signal_keys != tuple(sorted(set(signal_keys))):
            raise ValueError(
                "continuous-assurance signals must be canonically ordered and unique"
            )
        remediation_keys = tuple(
            (item.effective_tick, item.remediation_id) for item in self.remediations
        )
        if remediation_keys != tuple(sorted(set(remediation_keys))):
            raise ValueError(
                "continuous-assurance remediations must be canonically ordered "
                "and unique"
            )
        checkpoint_keys = tuple(
            (item.tick, item.checkpoint_id) for item in self.checkpoints
        )
        if checkpoint_keys != tuple(sorted(set(checkpoint_keys))):
            raise ValueError(
                "continuous-assurance checkpoints must be canonically ordered "
                "and unique"
            )
        if self.checkpoints[-1].tick != self.horizon_tick:
            raise ValueError(
                "continuous-assurance final checkpoint must equal the horizon"
            )
        return self


class ContinuousAssuranceFindingTransitionTruthV1(SyntheticModel):
    tick: int = Field(ge=0)
    state: FindingLifecycleState


class ContinuousAssuranceCaseTruthV1(SyntheticModel):
    case_id: str = Field(min_length=1)
    case_kind: ContinuousAssuranceCaseKind
    drift_kind: AssuranceDriftKind | None = None
    finding_required: bool
    drift_effective_tick: int | None = Field(default=None, ge=0)
    first_observable_tick: int | None = Field(default=None, ge=0)
    expected_finding_opened_tick: int | None = Field(default=None, ge=0)
    expected_finding_cleared_ticks: tuple[int, ...] = ()
    expected_remediation_complete: bool | None = None
    expected_recurrence_opened_ticks: tuple[int, ...] = ()
    expected_evidence_continuous: bool | None = None
    canonical_policy_version_id: str = Field(min_length=1)
    lifecycle: tuple[ContinuousAssuranceFindingTransitionTruthV1, ...]
    failure_reasons: tuple[str, ...]

    @field_validator(
        "expected_finding_cleared_ticks", "expected_recurrence_opened_ticks"
    )
    @classmethod
    def canonical_ticks(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError(
                "continuous-assurance recurrence ticks must be sorted and unique"
            )
        return value

    @field_validator("failure_reasons")
    @classmethod
    def canonical_failures(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_strings(value, "continuous-assurance failure reasons")

    @model_validator(mode="after")
    def coherent_truth(self) -> Self:
        if self.finding_required:
            drift_tick = self.drift_effective_tick
            observable_tick = self.first_observable_tick
            opened_tick = self.expected_finding_opened_tick
            if (
                self.drift_kind is None
                or drift_tick is None
                or observable_tick is None
                or opened_tick is None
                or self.expected_evidence_continuous is None
                or not self.lifecycle
            ):
                raise ValueError("continuous-assurance positive truth is incomplete")
            coordinates = (
                drift_tick,
                observable_tick,
                opened_tick,
            )
            if coordinates != tuple(sorted(coordinates)):
                raise ValueError(
                    "continuous-assurance truth coordinates must be ordered"
                )
            if any(item < opened_tick for item in self.expected_finding_cleared_ticks):
                raise ValueError(
                    "continuous-assurance finding clear precedes its opening"
                )
        elif (
            self.drift_kind is not None
            or self.drift_effective_tick is not None
            or self.first_observable_tick is not None
            or self.expected_finding_opened_tick is not None
            or self.expected_remediation_complete is not None
            or self.expected_evidence_continuous is not None
            or self.expected_finding_cleared_ticks
            or self.expected_recurrence_opened_ticks
            or self.lifecycle
        ):
            raise ValueError(
                "continuous-assurance negative truth carries finding fields"
            )
        lifecycle_keys = tuple((item.tick, item.state.value) for item in self.lifecycle)
        if lifecycle_keys != tuple(sorted(set(lifecycle_keys))):
            raise ValueError(
                "continuous-assurance lifecycle must be ordered and unique"
            )
        if self.finding_required:
            open_ticks = tuple(
                item.tick
                for item in self.lifecycle
                if item.state is FindingLifecycleState.OPEN
            )
            clear_ticks = tuple(
                item.tick
                for item in self.lifecycle
                if item.state is FindingLifecycleState.CLEAR
            )
            expected_open_ticks = (
                self.expected_finding_opened_tick,
                *self.expected_recurrence_opened_ticks,
            )
            states = tuple(item.state for item in self.lifecycle)
            alternating_states = tuple(
                FindingLifecycleState.OPEN
                if index % 2 == 0
                else FindingLifecycleState.CLEAR
                for index in range(len(states))
            )
            if (
                open_ticks != expected_open_ticks
                or clear_ticks != self.expected_finding_cleared_ticks
                or states != alternating_states
            ):
                raise ValueError(
                    "continuous-assurance lifecycle differs from expected transitions"
                )
        return self


class ContinuousAssuranceEvaluatorV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = CONTINUOUS_ASSURANCE_SCHEMA_VERSION
    public_digest: SyntheticDigestV1
    private_config_digest: SyntheticDigestV1
    source_bindings: tuple[ContinuousAssuranceEvaluatorSourceBindingV1, ...] = Field(
        min_length=1
    )
    truth: tuple[ContinuousAssuranceCaseTruthV1, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def canonical_inventories(self) -> Self:
        _require_model_order(self.source_bindings, "family", "evaluator sources")
        _require_model_order(self.truth, "case_id", "continuous-assurance truth")
        return self


class ContinuousAssurancePredictionRowV1(SyntheticModel):
    case_id: str = Field(min_length=1)
    predicted_drift_kind: AssuranceDriftKind | None = None
    finding_opened_tick: int | None = Field(default=None, ge=0)
    finding_cleared_ticks: tuple[int, ...] = ()
    recurrence_opened_ticks: tuple[int, ...] = ()
    remediation_complete: bool | None = None
    evidence_continuous: bool | None = None

    @field_validator("finding_cleared_ticks", "recurrence_opened_ticks")
    @classmethod
    def canonical_ticks(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError(
                "continuous-assurance predicted lifecycle ticks must be sorted "
                "and unique"
            )
        return value

    @model_validator(mode="after")
    def coherent_finding(self) -> Self:
        if self.finding_opened_tick is None:
            if (
                self.predicted_drift_kind is not None
                or self.finding_cleared_ticks
                or self.recurrence_opened_ticks
            ):
                raise ValueError(
                    "continuous-assurance absent finding carries lifecycle data"
                )
            return self
        if self.predicted_drift_kind is None:
            raise ValueError("continuous-assurance opened finding needs a drift kind")
        if any(item < self.finding_opened_tick for item in self.finding_cleared_ticks):
            raise ValueError("continuous-assurance predicted clear precedes opening")
        if any(
            item <= self.finding_opened_tick for item in self.recurrence_opened_ticks
        ):
            raise ValueError(
                "continuous-assurance predicted recurrence precedes initial opening"
            )
        lifecycle_ticks = (
            self.finding_opened_tick,
            *self.finding_cleared_ticks,
            *self.recurrence_opened_ticks,
        )
        if len(lifecycle_ticks) != len(set(lifecycle_ticks)):
            raise ValueError(
                "continuous-assurance predicted lifecycle ticks must be unique"
            )
        return self


class ContinuousAssurancePredictionV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = CONTINUOUS_ASSURANCE_SCHEMA_VERSION
    rows: tuple[ContinuousAssurancePredictionRowV1, ...] = Field(min_length=1)

    @field_validator("rows")
    @classmethod
    def canonical_rows(
        cls, value: tuple[ContinuousAssurancePredictionRowV1, ...]
    ) -> tuple[ContinuousAssurancePredictionRowV1, ...]:
        _require_model_order(value, "case_id", "continuous-assurance predictions")
        return value


class ContinuousAssuranceCaseFindingV1(SyntheticModel):
    case_id: str = Field(min_length=1)
    detection_correct: bool
    classification_correct: bool
    opening_tick_correct: bool
    clearing_tick_correct: bool
    recurrence_correct: bool
    remediation_correct: bool
    evidence_continuity_correct: bool
    checkpoint_state_correct: bool


class ContinuousAssuranceMetricV1(SyntheticModel):
    family: ContinuousAssuranceMetricFamily
    name: str = Field(min_length=1)
    aggregation: ContinuousAssuranceMetricAggregation
    value: float | None
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    support: int = Field(ge=0)
    denominator_meaning: str = Field(min_length=1)
    empty_behavior: ContinuousAssuranceEmptyBehavior = (
        ContinuousAssuranceEmptyBehavior.NULL_IF_EMPTY
    )

    @model_validator(mode="after")
    def exact_value(self) -> Self:
        if self.support > self.denominator:
            raise ValueError(
                "continuous-assurance metric support exceeds its denominator"
            )
        if (
            self.aggregation is ContinuousAssuranceMetricAggregation.RATIO
            and self.numerator > self.denominator
        ):
            raise ValueError(
                "continuous-assurance ratio numerator exceeds its denominator"
            )
        if self.denominator == 0:
            if self.value is not None or self.numerator != 0 or self.support != 0:
                raise ValueError(
                    "continuous-assurance empty metric must be explicitly null"
                )
            return self
        expected = self.numerator / self.denominator
        if self.value is None or not math.isclose(
            self.value, expected, rel_tol=1e-12, abs_tol=1e-12
        ):
            raise ValueError(
                "continuous-assurance metric value differs from its counts"
            )
        return self


class ContinuousAssuranceReportV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = CONTINUOUS_ASSURANCE_SCHEMA_VERSION
    scoring_version: Literal["1.0.0"] = CONTINUOUS_ASSURANCE_SCORING_VERSION
    findings: tuple[ContinuousAssuranceCaseFindingV1, ...] = Field(min_length=1)
    metrics: tuple[ContinuousAssuranceMetricV1, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def canonical_results(self) -> Self:
        _require_model_order(self.findings, "case_id", "continuous-assurance findings")
        keys = tuple((item.family.value, item.name) for item in self.metrics)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("continuous-assurance metrics must be sorted and unique")
        return self


def _canonical_strings(value: tuple[str, ...], description: str) -> tuple[str, ...]:
    if any(not item.strip() for item in value):
        raise ValueError(f"{description} must be nonblank")
    if value != tuple(sorted(set(value))):
        raise ValueError(f"{description} must be sorted and unique")
    return value


def _require_model_order(
    values: tuple[object, ...], attribute: str, description: str
) -> None:
    keys = tuple(str(getattr(item, attribute)) for item in values)
    if keys != tuple(sorted(set(keys))):
        raise ValueError(f"{description} must be sorted and unique")


__all__ = [
    "CONTINUOUS_ASSURANCE_BENCHMARK_VERSION",
    "CONTINUOUS_ASSURANCE_GENERATOR_VERSION",
    "CONTINUOUS_ASSURANCE_SCHEMA_VERSION",
    "CONTINUOUS_ASSURANCE_SCORING_VERSION",
    "AssuranceDriftKind",
    "AssuranceObservedState",
    "ContinuousAssuranceBenchmarkBindingV1",
    "ContinuousAssuranceCaseFindingV1",
    "ContinuousAssuranceCaseKind",
    "ContinuousAssuranceCaseTruthV1",
    "ContinuousAssuranceCaseV1",
    "ContinuousAssuranceCheckpointV1",
    "ContinuousAssuranceConfigV1",
    "ContinuousAssuranceEmptyBehavior",
    "ContinuousAssuranceEvaluatorSourceBindingV1",
    "ContinuousAssuranceEvaluatorV1",
    "ContinuousAssuranceFeedWindowV1",
    "ContinuousAssuranceFindingTransitionTruthV1",
    "ContinuousAssuranceMetricAggregation",
    "ContinuousAssuranceMetricFamily",
    "ContinuousAssuranceMetricV1",
    "ContinuousAssurancePredictionRowV1",
    "ContinuousAssurancePredictionV1",
    "ContinuousAssurancePublicV1",
    "ContinuousAssuranceRemediationV1",
    "ContinuousAssuranceReportV1",
    "ContinuousAssuranceSignalV1",
    "ContinuousAssuranceSourceBindingV1",
    "ContinuousAssuranceSourceFamily",
    "ContinuousAssuranceSourceReferenceV1",
    "ContinuousAssuranceTier",
    "FindingLifecycleState",
]
