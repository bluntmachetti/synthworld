"""Receipt-v2-compatible run contracts for contextual-access evaluations.

The contracts describe an external run; they do not execute a PDP, context feed,
protected system, or vendor API.  Integer ticks remain the benchmark clock while
operational durations use integer nanoseconds in separately named fields.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Annotated, Literal, Self, cast

from pydantic import Field, ValidationInfo, field_validator, model_validator

from synthworld.agent_authority.common import (
    EvidenceHandleV1,
    EvidenceKind,
    ObservedDecision,
    ObservedSideEffect,
)
from synthworld.assurance.models_v2 import DigestV2, SystemComponentProvenanceV2
from synthworld.contextual_access.common import CONTEXTUAL_ACCESS_PROTOCOL_VERSION
from synthworld.contextual_access.models import (
    ContextualAccessEvaluatorV1,
    ContextualAccessPublicV1,
    ContextualFactKind,
    ContextualMappingKind,
)
from synthworld.enterprise.canonical import (
    canonical_json_bytes,
    canonical_json_value_bytes,
    synthetic_digest,
)
from synthworld.enterprise.models import EnterpriseOperatorModel
from synthworld.enterprise.rbac.common import AuthorizationDecision
from synthworld.enterprise.rbac.metrics import EnterpriseAuthorizationMetricV1
from synthworld.models import SyntheticModel

CONTEXTUAL_RUN_PLAN_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
CONTEXTUAL_OBSERVATIONS_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
CONTEXTUAL_RUN_TRUTH_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
CONTEXTUAL_REPORT_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"

CONTEXTUAL_RUN_PLAN_PATH = "context/contextual-access-run-plan.json"
CONTEXTUAL_OBSERVATIONS_PATH = "observations/contextual-access.json"
CONTEXTUAL_RUN_TRUTH_PATH = "evaluator/contextual-access-run-truth.json"
CONTEXTUAL_REPORT_PATH = "evaluation/contextual-access-report.json"


class ContextualControlId(StrEnum):
    MAPPING_INGESTION = "SW-CA-C01"
    ACCESS_DECISION = "SW-CA-C02"
    PROTECTED_ENFORCEMENT = "SW-CA-C03"
    DELIVERY_ACCEPTANCE = "SW-CA-C04"
    SYNCHRONIZATION_FAULT = "SW-CA-C05"
    EVIDENCE_CORRELATION = "SW-CA-C06"


class ContextualCoverageDisposition(StrEnum):
    SELECTED = "selected"
    NOT_APPLICABLE = "not_applicable"


class ContextualFaultKind(StrEnum):
    DELAYED_DELIVERY = "delayed_delivery"
    DUPLICATE_DELIVERY = "duplicate_delivery"
    OUT_OF_ORDER_DELIVERY = "out_of_order_delivery"
    DROPPED_DELIVERY = "dropped_delivery"


class MappingIngestionStatus(StrEnum):
    INGESTED = "ingested"
    UNSUPPORTED = "unsupported"
    ERROR = "error"


class SynchronizationFaultStatus(StrEnum):
    RECOVERED = "recovered"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


class ContextualControlCoverageV1(EnterpriseOperatorModel):
    control_id: ContextualControlId
    disposition: ContextualCoverageDisposition
    applicability_rationale: str | None = None

    @model_validator(mode="after")
    def validate_disposition(self) -> Self:
        if self.disposition is ContextualCoverageDisposition.SELECTED:
            if self.applicability_rationale is not None:
                raise ValueError("selected contextual controls forbid a rationale")
        elif (
            not self.applicability_rationale or not self.applicability_rationale.strip()
        ):
            raise ValueError("not-applicable contextual controls require a rationale")
        return self


class ContextualRunBoundsV1(EnterpriseOperatorModel):
    feed_delay_bound_ticks: int = Field(gt=0)
    feed_delay_unit: Literal["tick"] = "tick"
    sut_acceptance_bound_ns: int = Field(gt=0)
    sut_acceptance_unit: Literal["ns"] = "ns"
    post_acceptance_decision_bound_ns: int = Field(gt=0)
    post_acceptance_decision_unit: Literal["ns"] = "ns"


class ContextualBenchmarkBindingV1(EnterpriseOperatorModel):
    benchmark_family: Literal["contextual_access"] = "contextual_access"
    benchmark_version: Literal["1.0.0"] = "1.0.0"
    enterprise_public_root_digest: DigestV2
    contextual_public_root_digest: DigestV2
    identity_access_universe_digest: DigestV2
    access_atom_digest: DigestV2
    registry_digest: DigestV2
    request_digest: DigestV2
    public_case_inventory_digest: DigestV2


class ContextualFaultV1(EnterpriseOperatorModel):
    fault_id: str = Field(min_length=1)
    kind: ContextualFaultKind
    component_id: str = Field(min_length=1)
    event_ids: tuple[str, ...] = Field(min_length=1)
    delivery_attempt_ids: tuple[str, ...] = Field(min_length=1)
    injection_tick: int = Field(ge=0)
    recovery_tick: int = Field(ge=0)

    @field_validator("event_ids", "delivery_attempt_ids")
    @classmethod
    def canonical_references(
        cls, value: tuple[str, ...], info: ValidationInfo
    ) -> tuple[str, ...]:
        return _canonical_strings(value, f"contextual fault {info.field_name}")

    @model_validator(mode="after")
    def forward_interval(self) -> Self:
        if self.recovery_tick < self.injection_tick:
            raise ValueError("contextual fault recovery precedes injection")
        return self


class _ProbeBaseV1(EnterpriseOperatorModel):
    probe_id: str = Field(min_length=1)
    component_id: str = Field(min_length=1)


class MappingIngestionProbeV1(_ProbeBaseV1):
    probe_type: Literal["mapping_ingestion"] = "mapping_ingestion"
    control_id: Literal[ContextualControlId.MAPPING_INGESTION] = (
        ContextualControlId.MAPPING_INGESTION
    )
    fact_type: ContextualFactKind
    mapping_kind: ContextualMappingKind


class AccessDecisionProbeV1(_ProbeBaseV1):
    probe_type: Literal["access_decision"] = "access_decision"
    control_id: Literal[ContextualControlId.ACCESS_DECISION] = (
        ContextualControlId.ACCESS_DECISION
    )
    request_id: str = Field(min_length=1)
    trigger_event_id: str | None = Field(default=None, min_length=1)


class ProtectedEnforcementProbeV1(_ProbeBaseV1):
    probe_type: Literal["protected_enforcement"] = "protected_enforcement"
    control_id: Literal[ContextualControlId.PROTECTED_ENFORCEMENT] = (
        ContextualControlId.PROTECTED_ENFORCEMENT
    )
    request_id: str = Field(min_length=1)


class DeliveryAcceptanceProbeV1(_ProbeBaseV1):
    probe_type: Literal["delivery_acceptance"] = "delivery_acceptance"
    control_id: Literal[ContextualControlId.DELIVERY_ACCEPTANCE] = (
        ContextualControlId.DELIVERY_ACCEPTANCE
    )
    event_id: str = Field(min_length=1)
    delivery_attempt_id: str = Field(min_length=1)


class SynchronizationFaultProbeV1(_ProbeBaseV1):
    probe_type: Literal["synchronization_fault"] = "synchronization_fault"
    control_id: Literal[ContextualControlId.SYNCHRONIZATION_FAULT] = (
        ContextualControlId.SYNCHRONIZATION_FAULT
    )
    fault_id: str = Field(min_length=1)


class EvidenceCorrelationProbeV1(_ProbeBaseV1):
    probe_type: Literal["evidence_correlation"] = "evidence_correlation"
    control_id: Literal[ContextualControlId.EVIDENCE_CORRELATION] = (
        ContextualControlId.EVIDENCE_CORRELATION
    )
    request_id: str = Field(min_length=1)
    required_evidence_kind: EvidenceKind


ContextualProbeV1 = Annotated[
    MappingIngestionProbeV1
    | AccessDecisionProbeV1
    | ProtectedEnforcementProbeV1
    | DeliveryAcceptanceProbeV1
    | SynchronizationFaultProbeV1
    | EvidenceCorrelationProbeV1,
    Field(discriminator="probe_type"),
]


class ContextualAccessRunPlanV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = CONTEXTUAL_RUN_PLAN_SCHEMA_VERSION
    protocol_version: Literal["synthworld-contextual-access-1.0.0"] = (
        CONTEXTUAL_ACCESS_PROTOCOL_VERSION
    )
    run_id: str = Field(min_length=1)
    benchmark: ContextualBenchmarkBindingV1
    mapping_profile_digest: DigestV2
    event_schedule_version: str = Field(min_length=1)
    request_ids: tuple[str, ...] = Field(min_length=1)
    event_ids: tuple[str, ...]
    delivery_attempt_ids: tuple[str, ...]
    sut_component_ids: tuple[str, ...] = Field(min_length=1)
    context_feed_component_ids: tuple[str, ...] = Field(min_length=1)
    faults: tuple[ContextualFaultV1, ...]
    bounds: ContextualRunBoundsV1
    required_evidence_kinds: tuple[EvidenceKind, ...] = Field(min_length=1)
    control_coverage: tuple[ContextualControlCoverageV1, ...] = Field(min_length=1)
    probes: tuple[ContextualProbeV1, ...] = Field(min_length=1)

    @field_validator("request_ids", "event_ids", "delivery_attempt_ids")
    @classmethod
    def unique_ordered_public_ids(
        cls, value: tuple[str, ...], info: ValidationInfo
    ) -> tuple[str, ...]:
        _unique_nonblank(value, f"contextual run-plan {info.field_name}")
        return value

    @field_validator("sut_component_ids", "context_feed_component_ids")
    @classmethod
    def canonical_components(
        cls, value: tuple[str, ...], info: ValidationInfo
    ) -> tuple[str, ...]:
        return _canonical_strings(value, f"contextual run-plan {info.field_name}")

    @field_validator("required_evidence_kinds")
    @classmethod
    def canonical_evidence(
        cls, value: tuple[EvidenceKind, ...]
    ) -> tuple[EvidenceKind, ...]:
        if value != tuple(sorted(set(value), key=str)):
            raise ValueError("contextual evidence kinds must be sorted and unique")
        return value

    @model_validator(mode="after")
    def canonical_inventory(self) -> Self:
        coverage = tuple(item.control_id for item in self.control_coverage)
        if coverage != tuple(ContextualControlId):
            raise ValueError("contextual control coverage must contain every control")
        fault_ids = tuple(item.fault_id for item in self.faults)
        if fault_ids != tuple(sorted(set(fault_ids))):
            raise ValueError("contextual faults must be sorted and unique")
        probe_ids = tuple(item.probe_id for item in self.probes)
        if probe_ids != tuple(sorted(set(probe_ids))):
            raise ValueError("contextual probes must be sorted and unique")
        selected = {
            item.control_id
            for item in self.control_coverage
            if item.disposition is ContextualCoverageDisposition.SELECTED
        }
        probed = {item.control_id for item in self.probes}
        if selected != probed:
            raise ValueError("contextual selected controls must match probe coverage")
        return self


class ContextualDecisionAttemptV1(EnterpriseOperatorModel):
    decision_tick: int = Field(ge=0)
    decision: ObservedDecision
    elapsed_ns_from_acceptance: int | None = Field(default=None, ge=0)


class _ObservationBaseV1(EnterpriseOperatorModel):
    observation_id: str = Field(min_length=1)
    probe_id: str = Field(min_length=1)
    component_id: str = Field(min_length=1)
    evidence_refs: tuple[str, ...]

    @field_validator("evidence_refs")
    @classmethod
    def canonical_evidence_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_strings(value, "contextual observation evidence refs")


class MappingIngestionObservationV1(_ObservationBaseV1):
    observation_type: Literal["mapping_ingestion"] = "mapping_ingestion"
    fact_type: ContextualFactKind
    mapping_kind: ContextualMappingKind
    status: MappingIngestionStatus


class AccessDecisionObservationV1(_ObservationBaseV1):
    observation_type: Literal["access_decision"] = "access_decision"
    request_id: str = Field(min_length=1)
    trigger_event_id: str | None = Field(default=None, min_length=1)
    accepted_delivery_attempt_id: str | None = Field(default=None, min_length=1)
    policy_version_ids: tuple[str, ...]
    attempts: tuple[ContextualDecisionAttemptV1, ...] = Field(min_length=1)

    @field_validator("policy_version_ids")
    @classmethod
    def canonical_policy_versions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_strings(value, "contextual observed policy versions")

    @model_validator(mode="after")
    def transition_coordinates_are_complete(self) -> Self:
        coordinates = (
            self.trigger_event_id,
            self.accepted_delivery_attempt_id,
        )
        if (coordinates[0] is None) is not (coordinates[1] is None):
            raise ValueError(
                "contextual transition decision coordinates are incomplete"
            )
        transition = coordinates[0] is not None
        if any(
            (item.elapsed_ns_from_acceptance is not None) is not transition
            for item in self.attempts
        ):
            raise ValueError("contextual decision latency coordinates are inconsistent")
        if tuple(item.decision_tick for item in self.attempts) != tuple(
            sorted(item.decision_tick for item in self.attempts)
        ):
            raise ValueError("contextual decision attempts must be tick ordered")
        return self


class ProtectedEnforcementObservationV1(_ObservationBaseV1):
    observation_type: Literal["protected_enforcement"] = "protected_enforcement"
    request_id: str = Field(min_length=1)
    decision: ObservedDecision
    side_effect: ObservedSideEffect


class ContextDeliveryAcceptanceObservationV1(_ObservationBaseV1):
    observation_type: Literal["delivery_acceptance"] = "delivery_acceptance"
    event_id: str = Field(min_length=1)
    delivery_attempt_id: str = Field(min_length=1)
    projected_event_tick: int = Field(ge=0)
    set_issue_tick: int = Field(ge=0)
    observed_delivery_tick: int = Field(ge=0)
    accepted: bool
    acceptance_elapsed_ns: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def acceptance_has_latency(self) -> Self:
        if self.accepted is (self.acceptance_elapsed_ns is None):
            raise ValueError("accepted contextual delivery requires acceptance latency")
        if not (
            self.projected_event_tick
            <= self.set_issue_tick
            <= self.observed_delivery_tick
        ):
            raise ValueError("contextual projected/SET/delivery ticks are out of order")
        return self


class SynchronizationFaultObservationV1(_ObservationBaseV1):
    observation_type: Literal["synchronization_fault"] = "synchronization_fault"
    fault_id: str = Field(min_length=1)
    status: SynchronizationFaultStatus
    recovery_elapsed_ns: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def recovery_has_latency(self) -> Self:
        if (self.status is SynchronizationFaultStatus.RECOVERED) is (
            self.recovery_elapsed_ns is None
        ):
            raise ValueError(
                "recovered synchronization fault requires recovery latency"
            )
        return self


class EvidenceCorrelationObservationV1(_ObservationBaseV1):
    observation_type: Literal["evidence_correlation"] = "evidence_correlation"
    request_id: str = Field(min_length=1)
    evidence_kind: EvidenceKind
    correlated: bool


ContextualObservationV1 = Annotated[
    MappingIngestionObservationV1
    | AccessDecisionObservationV1
    | ProtectedEnforcementObservationV1
    | ContextDeliveryAcceptanceObservationV1
    | SynchronizationFaultObservationV1
    | EvidenceCorrelationObservationV1,
    Field(discriminator="observation_type"),
]


class ContextualAccessObservationsV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = CONTEXTUAL_OBSERVATIONS_SCHEMA_VERSION
    run_id: str = Field(min_length=1)
    observations: tuple[ContextualObservationV1, ...]
    evidence_handles: tuple[EvidenceHandleV1, ...]
    limitations: tuple[str, ...] = ()

    @field_validator("limitations")
    @classmethod
    def canonical_limitations(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_strings(value, "contextual observation limitations")

    @model_validator(mode="after")
    def canonical_inventory(self) -> Self:
        observation_ids = tuple(item.observation_id for item in self.observations)
        if observation_ids != tuple(sorted(set(observation_ids))):
            raise ValueError("contextual observations must be sorted and unique")
        probe_ids = tuple(item.probe_id for item in self.observations)
        if len(probe_ids) != len(set(probe_ids)):
            raise ValueError("contextual observations must be unique per probe")
        handles = tuple(item.handle for item in self.evidence_handles)
        if handles != tuple(sorted(set(handles))):
            raise ValueError("contextual evidence handles must be sorted and unique")
        return self


class _TruthBaseV1(SyntheticModel):
    probe_id: str = Field(min_length=1)
    control_id: ContextualControlId


class MappingIngestionTruthV1(_TruthBaseV1):
    truth_type: Literal["mapping_ingestion"] = "mapping_ingestion"
    fact_type: ContextualFactKind
    mapping_kind: ContextualMappingKind
    expected_status: Literal[MappingIngestionStatus.INGESTED] = (
        MappingIngestionStatus.INGESTED
    )


class AccessDecisionRunTruthV1(_TruthBaseV1):
    truth_type: Literal["access_decision"] = "access_decision"
    request_id: str
    expected_decision: AuthorizationDecision
    trigger_event_id: str | None = None
    accepted_delivery_attempt_id: str | None = None
    required_policy_version_ids: tuple[str, ...]


class ProtectedEnforcementTruthV1(_TruthBaseV1):
    truth_type: Literal["protected_enforcement"] = "protected_enforcement"
    request_id: str
    expected_decision: AuthorizationDecision
    expected_side_effect: ObservedSideEffect


class DeliveryAcceptanceTruthV1(_TruthBaseV1):
    truth_type: Literal["delivery_acceptance"] = "delivery_acceptance"
    event_id: str
    delivery_attempt_id: str
    effective_tick: int = Field(ge=0)
    delivery_tick: int = Field(ge=0)


class SynchronizationFaultTruthV1(_TruthBaseV1):
    truth_type: Literal["synchronization_fault"] = "synchronization_fault"
    fault_id: str
    expected_status: Literal[SynchronizationFaultStatus.RECOVERED] = (
        SynchronizationFaultStatus.RECOVERED
    )


class EvidenceCorrelationTruthV1(_TruthBaseV1):
    truth_type: Literal["evidence_correlation"] = "evidence_correlation"
    request_id: str
    required_evidence_kind: EvidenceKind


ContextualObservationTruthV1 = Annotated[
    MappingIngestionTruthV1
    | AccessDecisionRunTruthV1
    | ProtectedEnforcementTruthV1
    | DeliveryAcceptanceTruthV1
    | SynchronizationFaultTruthV1
    | EvidenceCorrelationTruthV1,
    Field(discriminator="truth_type"),
]


class ContextualAccessRunTruthV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = CONTEXTUAL_RUN_TRUTH_SCHEMA_VERSION
    run_id: str
    contextual_public_digest: DigestV2
    evaluator_digest: DigestV2
    rows: tuple[ContextualObservationTruthV1, ...]

    @field_validator("rows")
    @classmethod
    def canonical_rows(
        cls, value: tuple[ContextualObservationTruthV1, ...]
    ) -> tuple[ContextualObservationTruthV1, ...]:
        probe_ids = tuple(item.probe_id for item in value)
        if probe_ids != tuple(sorted(set(probe_ids))):
            raise ValueError("contextual run truth must be sorted and unique")
        return value


class ContextualProtocolFindingV1(SyntheticModel):
    probe_id: str
    control_id: ContextualControlId
    passed: bool
    right_censored: bool = False
    failure_code: str | None = None

    @model_validator(mode="after")
    def failure_shape(self) -> Self:
        if self.passed:
            if self.right_censored or self.failure_code is not None:
                raise ValueError("passing contextual findings forbid failure metadata")
        elif self.failure_code is None:
            raise ValueError("failing contextual findings require a failure code")
        return self


class ContextualAccessReportV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = CONTEXTUAL_REPORT_SCHEMA_VERSION
    run_id: str
    truth_digest: DigestV2
    findings: tuple[ContextualProtocolFindingV1, ...]
    metrics: tuple[EnterpriseAuthorizationMetricV1, ...]

    @field_validator("findings")
    @classmethod
    def canonical_findings(
        cls, value: tuple[ContextualProtocolFindingV1, ...]
    ) -> tuple[ContextualProtocolFindingV1, ...]:
        probe_ids = tuple(item.probe_id for item in value)
        if probe_ids != tuple(sorted(set(probe_ids))):
            raise ValueError("contextual findings must be sorted and unique")
        return value

    @field_validator("metrics")
    @classmethod
    def canonical_metrics(
        cls, value: tuple[EnterpriseAuthorizationMetricV1, ...]
    ) -> tuple[EnterpriseAuthorizationMetricV1, ...]:
        keys = tuple((item.family, item.name) for item in value)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("contextual protocol metrics must be sorted and unique")
        return value


class ContextualProtocolError(ValueError):
    """Raised for cross-artifact contextual run contract violations."""


_MetricChecker = Callable[
    [
        ContextualObservationTruthV1,
        ContextualObservationV1 | None,
        ContextualAccessRunPlanV1,
        dict[str, EvidenceHandleV1],
    ],
    bool,
]


def contextual_public_case_inventory_digest(
    public: ContextualAccessPublicV1,
) -> DigestV2:
    """Digest only the public request IDs used as the run's case inventory."""

    return _digest_v2(
        canonical_json_value_bytes([item.request_id for item in public.requests])
    )


def validate_contextual_run_plan(
    plan: ContextualAccessRunPlanV1,
    *,
    public: ContextualAccessPublicV1,
    systems_under_test: tuple[SystemComponentProvenanceV2, ...],
) -> None:
    """Resolve every public and component reference before external execution."""

    component_ids = {item.component_id for item in systems_under_test}
    required_components = set(plan.sut_component_ids) | set(
        plan.context_feed_component_ids
    )
    if not required_components <= component_ids:
        raise ContextualProtocolError(
            "contextual run plan references unknown components"
        )
    benchmark = public.benchmark
    expected_binding = (
        _digest_v2(canonical_json_bytes(public.universe)),
        _digest_v2(canonical_json_bytes(public)),
        _digest_v2_from_synthetic(benchmark.identity_access_universe_digest.value),
        _digest_v2_from_synthetic(benchmark.access_atom_digest.value),
        _digest_v2_from_synthetic(benchmark.registry_digest.value),
        _digest_v2_from_synthetic(benchmark.request_digest.value),
        contextual_public_case_inventory_digest(public),
    )
    actual_binding = (
        plan.benchmark.enterprise_public_root_digest,
        plan.benchmark.contextual_public_root_digest,
        plan.benchmark.identity_access_universe_digest,
        plan.benchmark.access_atom_digest,
        plan.benchmark.registry_digest,
        plan.benchmark.request_digest,
        plan.benchmark.public_case_inventory_digest,
    )
    if actual_binding != expected_binding:
        raise ContextualProtocolError("contextual run-plan benchmark binding differs")
    if plan.mapping_profile_digest != _digest_v2_from_synthetic(
        benchmark.mapping_profile_digest.value
    ):
        raise ContextualProtocolError("contextual run-plan mapping digest differs")
    if plan.event_schedule_version != benchmark.event_schedule_version:
        raise ContextualProtocolError("contextual run-plan schedule version differs")
    expected_ids = (
        tuple(item.request_id for item in public.requests),
        tuple(item.id for item in public.events),
        tuple(item.attempt_id for item in public.delivery_attempts),
    )
    if (plan.request_ids, plan.event_ids, plan.delivery_attempt_ids) != expected_ids:
        raise ContextualProtocolError("contextual run-plan public inventory differs")
    _validate_fault_references(plan, public, component_ids)
    _validate_probe_references(plan, public, component_ids)


def validate_contextual_observations(
    plan: ContextualAccessRunPlanV1,
    observations: ContextualAccessObservationsV1,
) -> None:
    """Reject observations that escape the predeclared probe/component inventory."""

    if observations.run_id != plan.run_id:
        raise ContextualProtocolError("contextual observations run id differs")
    probes = {item.probe_id: item for item in plan.probes}
    component_ids = set(plan.sut_component_ids) | set(plan.context_feed_component_ids)
    handles = {item.handle for item in observations.evidence_handles}
    for observation in observations.observations:
        probe = probes.get(observation.probe_id)
        if probe is None or observation.observation_type != probe.probe_type:
            raise ContextualProtocolError("contextual observation probe differs")
        if observation.component_id != probe.component_id:
            raise ContextualProtocolError("contextual observation component differs")
        if observation.component_id not in component_ids:
            raise ContextualProtocolError("contextual observation component is unknown")
        if not set(observation.evidence_refs) <= handles:
            raise ContextualProtocolError("contextual observation evidence is unknown")
        if not _observation_matches_probe(observation, probe):
            raise ContextualProtocolError(
                "contextual observation public reference differs"
            )


def compile_contextual_run_truth(
    plan: ContextualAccessRunPlanV1,
    *,
    public: ContextualAccessPublicV1,
    evaluator: ContextualAccessEvaluatorV1,
) -> ContextualAccessRunTruthV1:
    """Compile matching run truth only after product observations are staged."""

    if (
        evaluator.public_digest.value
        != synthetic_digest(canonical_json_bytes(public)).value
    ):
        raise ContextualProtocolError("contextual evaluator does not bind public input")
    cases = {item.request_id: item for item in evaluator.truth.cases}
    policies = {item.policy_id: item.policy_version_id for item in public.policies}
    attempts = {item.attempt_id: item for item in public.delivery_attempts}
    events = {item.id: item for item in public.events}
    mappings = {item.fact_type: item for item in public.mapping_profile.mappings}
    rows: list[ContextualObservationTruthV1] = []
    for probe in plan.probes:
        if isinstance(probe, MappingIngestionProbeV1):
            mapping = mappings[probe.fact_type]
            rows.append(
                MappingIngestionTruthV1(
                    probe_id=probe.probe_id,
                    control_id=probe.control_id,
                    fact_type=probe.fact_type,
                    mapping_kind=mapping.mapping_kind,
                )
            )
        elif isinstance(probe, AccessDecisionProbeV1):
            case = cases[probe.request_id]
            accepted_attempt_id = _accepted_attempt_id(probe, public)
            rows.append(
                AccessDecisionRunTruthV1(
                    probe_id=probe.probe_id,
                    control_id=probe.control_id,
                    request_id=probe.request_id,
                    expected_decision=case.canonical.decision,
                    trigger_event_id=probe.trigger_event_id,
                    accepted_delivery_attempt_id=accepted_attempt_id,
                    required_policy_version_ids=tuple(
                        sorted(
                            policies[item]
                            for item in case.canonical.applicable_policy_ids
                        )
                    ),
                )
            )
        elif isinstance(probe, ProtectedEnforcementProbeV1):
            decision = cases[probe.request_id].canonical.decision
            rows.append(
                ProtectedEnforcementTruthV1(
                    probe_id=probe.probe_id,
                    control_id=probe.control_id,
                    request_id=probe.request_id,
                    expected_decision=decision,
                    expected_side_effect=(
                        ObservedSideEffect.OCCURRED
                        if decision is AuthorizationDecision.ALLOW
                        else ObservedSideEffect.NOT_OBSERVED
                    ),
                )
            )
        elif isinstance(probe, DeliveryAcceptanceProbeV1):
            attempt = attempts[probe.delivery_attempt_id]
            rows.append(
                DeliveryAcceptanceTruthV1(
                    probe_id=probe.probe_id,
                    control_id=probe.control_id,
                    event_id=probe.event_id,
                    delivery_attempt_id=probe.delivery_attempt_id,
                    effective_tick=events[probe.event_id].effective_tick,
                    delivery_tick=attempt.delivery_tick,
                )
            )
        elif isinstance(probe, SynchronizationFaultProbeV1):
            rows.append(
                SynchronizationFaultTruthV1(
                    probe_id=probe.probe_id,
                    control_id=probe.control_id,
                    fault_id=probe.fault_id,
                )
            )
        else:
            rows.append(
                EvidenceCorrelationTruthV1(
                    probe_id=probe.probe_id,
                    control_id=probe.control_id,
                    request_id=probe.request_id,
                    required_evidence_kind=probe.required_evidence_kind,
                )
            )
    return ContextualAccessRunTruthV1(
        run_id=plan.run_id,
        contextual_public_digest=_digest_v2(canonical_json_bytes(public)),
        evaluator_digest=_digest_v2(canonical_json_bytes(evaluator)),
        rows=tuple(rows),
    )


def evaluate_contextual_access_run(
    plan: ContextualAccessRunPlanV1,
    observations: ContextualAccessObservationsV1,
    truth: ContextualAccessRunTruthV1,
) -> ContextualAccessReportV1:
    """Score independent run dimensions, including explicit right-censoring."""

    validate_contextual_observations(plan, observations)
    if truth.run_id != plan.run_id:
        raise ContextualProtocolError("contextual run truth identifier differs")
    if tuple(item.probe_id for item in truth.rows) != tuple(
        item.probe_id for item in plan.probes
    ):
        raise ContextualProtocolError("contextual run truth probe inventory differs")
    observed = {item.probe_id: item for item in observations.observations}
    handles = {item.handle: item for item in observations.evidence_handles}
    findings = tuple(
        _score_truth_row(item, observed.get(item.probe_id), plan, handles)
        for item in truth.rows
    )
    metrics = _independent_run_metrics(
        plan=plan,
        truth=truth,
        observed=observed,
        handles=handles,
    )
    decision_truth = tuple(
        item for item in truth.rows if isinstance(item, AccessDecisionRunTruthV1)
    )
    transition_ids = {
        item.probe_id for item in decision_truth if item.trigger_event_id is not None
    }
    propagation_findings = tuple(
        item for item in findings if item.probe_id in transition_ids
    )
    metrics = (
        *metrics,
        _ratio(
            family="propagation",
            name="post_acceptance_decision_propagation",
            numerator=sum(item.passed for item in propagation_findings),
            denominator=len(propagation_findings),
            meaning=(
                "transition probes with a correct post-acceptance decision within "
                "the declared nanosecond bound; missing correct decisions are "
                "right-censored failures"
            ),
        ),
    )
    return ContextualAccessReportV1(
        run_id=plan.run_id,
        truth_digest=_digest_v2(canonical_json_bytes(truth)),
        findings=findings,
        metrics=tuple(sorted(metrics, key=lambda item: (item.family, item.name))),
    )


def _validate_fault_references(
    plan: ContextualAccessRunPlanV1,
    public: ContextualAccessPublicV1,
    component_ids: set[str],
) -> None:
    event_ids = set(plan.event_ids)
    attempts = {item.attempt_id: item for item in public.delivery_attempts}
    for fault in plan.faults:
        if fault.component_id not in component_ids:
            raise ContextualProtocolError("contextual fault component is unknown")
        if not set(fault.event_ids) <= event_ids or not set(
            fault.delivery_attempt_ids
        ) <= set(attempts):
            raise ContextualProtocolError(
                "contextual fault public reference is unknown"
            )
        if any(
            attempts[attempt_id].event_id not in fault.event_ids
            for attempt_id in fault.delivery_attempt_ids
        ):
            raise ContextualProtocolError(
                "contextual fault attempt/event binding differs"
            )


def _validate_probe_references(
    plan: ContextualAccessRunPlanV1,
    public: ContextualAccessPublicV1,
    component_ids: set[str],
) -> None:
    request_ids = set(plan.request_ids)
    event_ids = set(plan.event_ids)
    attempts = {item.attempt_id: item for item in public.delivery_attempts}
    faults = {item.fault_id for item in plan.faults}
    mappings = {
        item.fact_type: item.mapping_kind for item in public.mapping_profile.mappings
    }
    for probe in plan.probes:
        if probe.component_id not in component_ids:
            raise ContextualProtocolError("contextual probe component is unknown")
        if isinstance(probe, MappingIngestionProbeV1):
            valid = mappings.get(probe.fact_type) is probe.mapping_kind
        elif isinstance(
            probe,
            (
                AccessDecisionProbeV1,
                ProtectedEnforcementProbeV1,
                EvidenceCorrelationProbeV1,
            ),
        ):
            valid = probe.request_id in request_ids
            if (
                isinstance(probe, AccessDecisionProbeV1)
                and probe.trigger_event_id is not None
            ):
                valid = valid and probe.trigger_event_id in event_ids
        elif isinstance(probe, DeliveryAcceptanceProbeV1):
            attempt = attempts.get(probe.delivery_attempt_id)
            valid = (
                probe.event_id in event_ids
                and attempt is not None
                and attempt.event_id == probe.event_id
            )
        else:
            valid = probe.fault_id in faults
        if not valid:
            raise ContextualProtocolError("contextual probe public reference differs")


def _observation_matches_probe(
    observation: ContextualObservationV1,
    probe: ContextualProbeV1,
) -> bool:
    if isinstance(observation, MappingIngestionObservationV1) and isinstance(
        probe, MappingIngestionProbeV1
    ):
        return (
            observation.fact_type is probe.fact_type
            and observation.mapping_kind is probe.mapping_kind
        )
    if isinstance(observation, AccessDecisionObservationV1) and isinstance(
        probe, AccessDecisionProbeV1
    ):
        return (
            observation.request_id == probe.request_id
            and observation.trigger_event_id == probe.trigger_event_id
        )
    if isinstance(observation, ProtectedEnforcementObservationV1) and isinstance(
        probe, ProtectedEnforcementProbeV1
    ):
        return observation.request_id == probe.request_id
    if isinstance(observation, ContextDeliveryAcceptanceObservationV1) and isinstance(
        probe, DeliveryAcceptanceProbeV1
    ):
        return (
            observation.event_id == probe.event_id
            and observation.delivery_attempt_id == probe.delivery_attempt_id
        )
    if isinstance(observation, SynchronizationFaultObservationV1) and isinstance(
        probe, SynchronizationFaultProbeV1
    ):
        return observation.fault_id == probe.fault_id
    return (
        isinstance(observation, EvidenceCorrelationObservationV1)
        and isinstance(probe, EvidenceCorrelationProbeV1)
        and observation.request_id == probe.request_id
        and observation.evidence_kind is probe.required_evidence_kind
    )


def _accepted_attempt_id(
    probe: AccessDecisionProbeV1,
    public: ContextualAccessPublicV1,
) -> str | None:
    if probe.trigger_event_id is None:
        return None
    attempts = tuple(
        item
        for item in public.delivery_attempts
        if item.event_id == probe.trigger_event_id
    )
    return attempts[0].attempt_id


def _score_truth_row(
    truth: ContextualObservationTruthV1,
    observation: ContextualObservationV1 | None,
    plan: ContextualAccessRunPlanV1,
    handles: dict[str, EvidenceHandleV1],
) -> ContextualProtocolFindingV1:
    passed = False
    right_censored = False
    code = "missing_observation"
    if isinstance(truth, MappingIngestionTruthV1) and isinstance(
        observation, MappingIngestionObservationV1
    ):
        passed = (
            observation.fact_type is truth.fact_type
            and observation.mapping_kind is truth.mapping_kind
            and observation.status is truth.expected_status
        )
        code = "mapping_ingestion_mismatch"
    elif isinstance(truth, AccessDecisionRunTruthV1) and isinstance(
        observation, AccessDecisionObservationV1
    ):
        passed, right_censored, code = _score_decision(
            truth, observation, plan.bounds.post_acceptance_decision_bound_ns
        )
    elif isinstance(truth, ProtectedEnforcementTruthV1) and isinstance(
        observation, ProtectedEnforcementObservationV1
    ):
        passed = (
            observation.decision.value == truth.expected_decision.value
            and observation.side_effect is truth.expected_side_effect
        )
        code = "protected_enforcement_mismatch"
    elif isinstance(truth, DeliveryAcceptanceTruthV1) and isinstance(
        observation, ContextDeliveryAcceptanceObservationV1
    ):
        feed_delay = truth.delivery_tick - truth.effective_tick
        passed = (
            observation.accepted
            and observation.projected_event_tick == truth.effective_tick
            and observation.observed_delivery_tick == truth.delivery_tick
            and feed_delay <= plan.bounds.feed_delay_bound_ticks
            and cast(int, observation.acceptance_elapsed_ns)
            <= plan.bounds.sut_acceptance_bound_ns
        )
        code = "delivery_or_acceptance_bound_failed"
    elif isinstance(truth, SynchronizationFaultTruthV1) and isinstance(
        observation, SynchronizationFaultObservationV1
    ):
        passed = observation.status is truth.expected_status
        code = "synchronization_fault_not_recovered"
    elif isinstance(truth, EvidenceCorrelationTruthV1) and isinstance(
        observation, EvidenceCorrelationObservationV1
    ):
        passed = observation.correlated and any(
            handles[handle].kind is truth.required_evidence_kind
            for handle in observation.evidence_refs
        )
        code = "required_evidence_not_correlated"
    return ContextualProtocolFindingV1(
        probe_id=truth.probe_id,
        control_id=truth.control_id,
        passed=passed,
        right_censored=right_censored,
        failure_code=None if passed else code,
    )


def _score_decision(
    truth: AccessDecisionRunTruthV1,
    observation: AccessDecisionObservationV1,
    bound_ns: int,
) -> tuple[bool, bool, str]:
    policy_ok = set(truth.required_policy_version_ids) <= set(
        observation.policy_version_ids
    )
    correct = tuple(
        item
        for item in observation.attempts
        if item.decision.value == truth.expected_decision.value
    )
    if truth.trigger_event_id is None:
        return bool(correct) and policy_ok, False, "decision_or_policy_mismatch"
    if observation.accepted_delivery_attempt_id != truth.accepted_delivery_attempt_id:
        return False, False, "accepted_delivery_attempt_mismatch"
    if not correct:
        return False, True, "correct_post_acceptance_decision_not_observed"
    first = correct[0]
    return (
        cast(int, first.elapsed_ns_from_acceptance) <= bound_ns and policy_ok,
        False,
        "post_acceptance_decision_bound_or_policy_failed",
    )


def _independent_run_metrics(
    *,
    plan: ContextualAccessRunPlanV1,
    truth: ContextualAccessRunTruthV1,
    observed: dict[str, ContextualObservationV1],
    handles: dict[str, EvidenceHandleV1],
) -> tuple[EnterpriseAuthorizationMetricV1, ...]:
    groups: tuple[
        tuple[ContextualControlId, str, type[SyntheticModel], _MetricChecker], ...
    ] = (
        (
            ContextualControlId.MAPPING_INGESTION,
            "mapping_ingestion_accuracy",
            MappingIngestionTruthV1,
            _mapping_metric_match,
        ),
        (
            ContextualControlId.ACCESS_DECISION,
            "decision_accuracy",
            AccessDecisionRunTruthV1,
            _decision_metric_match,
        ),
        (
            ContextualControlId.PROTECTED_ENFORCEMENT,
            "enforcement_accuracy",
            ProtectedEnforcementTruthV1,
            _enforcement_metric_match,
        ),
        (
            ContextualControlId.DELIVERY_ACCEPTANCE,
            "feed_delay_within_bound",
            DeliveryAcceptanceTruthV1,
            _feed_delay_metric_match,
        ),
        (
            ContextualControlId.DELIVERY_ACCEPTANCE,
            "sut_acceptance_within_bound",
            DeliveryAcceptanceTruthV1,
            _acceptance_metric_match,
        ),
        (
            ContextualControlId.SYNCHRONIZATION_FAULT,
            "synchronization_resilience",
            SynchronizationFaultTruthV1,
            _fault_metric_match,
        ),
        (
            ContextualControlId.EVIDENCE_CORRELATION,
            "evidence_completeness",
            EvidenceCorrelationTruthV1,
            _evidence_metric_match,
        ),
    )
    metrics: list[EnterpriseAuthorizationMetricV1] = []
    for control_id, name, truth_type, checker in groups:
        rows = tuple(item for item in truth.rows if isinstance(item, truth_type))
        metrics.append(
            _ratio(
                family=control_id.value,
                name=name,
                numerator=sum(
                    checker(item, observed.get(item.probe_id), plan, handles)
                    for item in rows
                ),
                denominator=len(rows),
                meaning=f"predeclared {control_id.value} contextual probes",
            )
        )
    return tuple(metrics)


def _mapping_metric_match(
    truth: ContextualObservationTruthV1,
    observation: ContextualObservationV1 | None,
    _plan: ContextualAccessRunPlanV1,
    _handles: dict[str, EvidenceHandleV1],
) -> bool:
    return (
        isinstance(truth, MappingIngestionTruthV1)
        and isinstance(observation, MappingIngestionObservationV1)
        and observation.fact_type is truth.fact_type
        and observation.mapping_kind is truth.mapping_kind
        and observation.status is truth.expected_status
    )


def _decision_metric_match(
    truth: ContextualObservationTruthV1,
    observation: ContextualObservationV1 | None,
    _plan: ContextualAccessRunPlanV1,
    _handles: dict[str, EvidenceHandleV1],
) -> bool:
    return (
        isinstance(truth, AccessDecisionRunTruthV1)
        and isinstance(observation, AccessDecisionObservationV1)
        and set(truth.required_policy_version_ids)
        <= set(observation.policy_version_ids)
        and any(
            item.decision.value == truth.expected_decision.value
            for item in observation.attempts
        )
    )


def _enforcement_metric_match(
    truth: ContextualObservationTruthV1,
    observation: ContextualObservationV1 | None,
    _plan: ContextualAccessRunPlanV1,
    _handles: dict[str, EvidenceHandleV1],
) -> bool:
    return (
        isinstance(truth, ProtectedEnforcementTruthV1)
        and isinstance(observation, ProtectedEnforcementObservationV1)
        and observation.decision.value == truth.expected_decision.value
        and observation.side_effect is truth.expected_side_effect
    )


def _feed_delay_metric_match(
    truth: ContextualObservationTruthV1,
    observation: ContextualObservationV1 | None,
    plan: ContextualAccessRunPlanV1,
    _handles: dict[str, EvidenceHandleV1],
) -> bool:
    return (
        isinstance(truth, DeliveryAcceptanceTruthV1)
        and isinstance(observation, ContextDeliveryAcceptanceObservationV1)
        and observation.projected_event_tick == truth.effective_tick
        and observation.projected_event_tick
        <= observation.set_issue_tick
        <= observation.observed_delivery_tick
        and observation.observed_delivery_tick == truth.delivery_tick
        and truth.delivery_tick - truth.effective_tick
        <= plan.bounds.feed_delay_bound_ticks
    )


def _acceptance_metric_match(
    truth: ContextualObservationTruthV1,
    observation: ContextualObservationV1 | None,
    plan: ContextualAccessRunPlanV1,
    _handles: dict[str, EvidenceHandleV1],
) -> bool:
    return (
        isinstance(truth, DeliveryAcceptanceTruthV1)
        and isinstance(observation, ContextDeliveryAcceptanceObservationV1)
        and observation.accepted
        and cast(int, observation.acceptance_elapsed_ns)
        <= plan.bounds.sut_acceptance_bound_ns
    )


def _fault_metric_match(
    truth: ContextualObservationTruthV1,
    observation: ContextualObservationV1 | None,
    _plan: ContextualAccessRunPlanV1,
    _handles: dict[str, EvidenceHandleV1],
) -> bool:
    return (
        isinstance(truth, SynchronizationFaultTruthV1)
        and isinstance(observation, SynchronizationFaultObservationV1)
        and observation.status is truth.expected_status
    )


def _evidence_metric_match(
    truth: ContextualObservationTruthV1,
    observation: ContextualObservationV1 | None,
    _plan: ContextualAccessRunPlanV1,
    handles: dict[str, EvidenceHandleV1],
) -> bool:
    return (
        isinstance(truth, EvidenceCorrelationTruthV1)
        and isinstance(observation, EvidenceCorrelationObservationV1)
        and observation.correlated
        and any(
            handles[handle].kind is truth.required_evidence_kind
            for handle in observation.evidence_refs
        )
    )


def _ratio(
    *,
    family: str,
    name: str,
    numerator: int,
    denominator: int,
    meaning: str,
) -> EnterpriseAuthorizationMetricV1:
    from synthworld.enterprise.rbac.common import MetricEmptyBehaviour

    return EnterpriseAuthorizationMetricV1(
        family=family,
        name=name,
        numerator=numerator,
        denominator=denominator,
        support=denominator,
        denominator_meaning=meaning,
        empty_behaviour=MetricEmptyBehaviour.NULL_IF_EMPTY,
        value=numerator / denominator if denominator else None,
    )


def _digest_v2(payload: bytes) -> DigestV2:
    return DigestV2(value=synthetic_digest(payload).value)


def _digest_v2_from_synthetic(value: str) -> DigestV2:
    return DigestV2(value=value)


def _unique_nonblank(values: tuple[str, ...], description: str) -> None:
    if any(not item.strip() for item in values):
        raise ValueError(f"{description} must be nonblank")
    if len(values) != len(set(values)):
        raise ValueError(f"{description} must be unique")


def _canonical_strings(values: tuple[str, ...], description: str) -> tuple[str, ...]:
    _unique_nonblank(values, description)
    if values != tuple(sorted(values)):
        raise ValueError(f"{description} must be canonically ordered")
    return values


__all__ = [name for name in globals() if name.endswith("V1")]
