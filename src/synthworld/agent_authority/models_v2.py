"""Agent-authority observation v2 with revocation-relative L06 timing."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Literal, cast

from pydantic import Field, field_validator, model_validator

from synthworld.agent_authority.cases import (
    AgentAuthorityObservationV1,
    AgentAuthorityStimulusSetV1,
    AgentAuthorityStimulusV1,
    DependencyFaultResultV1,
    L01SecretExposureObservationV1,
    L02CredentialReplayObservationV1,
    L03DirectPathBypassObservationV1,
    L04NetworkPolicyObservationV1,
    L05CriticalDependencyFailureObservationV1,
    L06RevocationPropagationStimulusV1,
)
from synthworld.agent_authority.common import (
    AgentAuthorityOperatorModel,
    CoverageDisposition,
    EvidenceHandleV1,
    ObservationAttributionV1,
    ObservedDecision,
    ObservedSideEffect,
    canonical_unique,
    require_utc,
    unique,
)
from synthworld.agent_authority.models import (
    AgentAuthorityRunObservationsV1,
    AgentAuthorityRunPlanV1,
    CoverageLimitationV1,
    require_evidence_refs,
    validate_case_observation,
    validate_compatibility_inventory,
    validate_dependency_results,
    validate_operational_inventory,
)
from synthworld.agent_authority.operational import (
    OperationalCoverageGapV1,
    OperationalMeasurementV1,
    TargetCompatibilityV1,
)
from synthworld.assurance.models_v2 import SystemComponentProvenanceV2

AGENT_AUTHORITY_OBSERVATIONS_SCHEMA_VERSION_V2: Literal["2.0.0"] = "2.0.0"


class RevocationPointResultV2(AgentAuthorityOperatorModel):
    """First observed rejection relative to the revocation issue epoch."""

    component_id: str = Field(min_length=1)
    ack_offset_ns: int | None = Field(default=None, ge=0)
    evidence_refs: tuple[str, ...] = ()

    @field_validator("evidence_refs")
    @classmethod
    def canonical_evidence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_unique(value, "revocation acknowledgement evidence")


class TimedAttemptV2(AgentAuthorityOperatorModel):
    """Attempt timing signed relative to the revocation issue epoch."""

    enforcement_point_id: str = Field(min_length=1)
    credential_or_child_handle: str = Field(min_length=1)
    sent_offset_ns: int
    completed_offset_ns: int
    decision: ObservedDecision
    side_effect: ObservedSideEffect
    evidence_refs: tuple[str, ...] = ()

    @field_validator("evidence_refs")
    @classmethod
    def canonical_evidence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_unique(value, "timed-attempt evidence")

    @model_validator(mode="after")
    def validate_timing(self) -> TimedAttemptV2:
        if self.completed_offset_ns < self.sent_offset_ns:
            raise ValueError("attempt completion cannot precede send")
        return self


class L06RevocationPropagationObservationV2(AgentAuthorityOperatorModel):
    """L06 timing tied to one explicit monotonic revocation epoch."""

    variant: Literal["l06_revocation_propagation"] = "l06_revocation_propagation"
    revocation_epoch_monotonic_ns: int = Field(ge=0)
    point_results: tuple[RevocationPointResultV2, ...] = Field(min_length=1)
    timed_attempts: tuple[TimedAttemptV2, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_inventory(self) -> L06RevocationPropagationObservationV2:
        points = tuple(item.component_id for item in self.point_results)
        unique(points, "revocation point-result components")
        if points != tuple(sorted(points)):
            raise ValueError("revocation point results must be canonically ordered")
        attempt_keys = tuple(
            (
                item.enforcement_point_id,
                item.credential_or_child_handle,
                item.sent_offset_ns,
            )
            for item in self.timed_attempts
        )
        if len(attempt_keys) != len(set(attempt_keys)):
            raise ValueError("timed attempts must be unique")
        if attempt_keys != tuple(sorted(attempt_keys)):
            raise ValueError("timed attempts must be canonically ordered")
        return self


AgentAuthorityObservationPayloadV2 = Annotated[
    L01SecretExposureObservationV1
    | L02CredentialReplayObservationV1
    | L03DirectPathBypassObservationV1
    | L04NetworkPolicyObservationV1
    | L05CriticalDependencyFailureObservationV1
    | L06RevocationPropagationObservationV2,
    Field(discriminator="variant"),
]


class AgentAuthorityObservationV2(AgentAuthorityOperatorModel):
    """Observation envelope retaining V1 fields with an L06-v2 payload."""

    stimulus_id: str = Field(min_length=1)
    attribution: ObservationAttributionV1
    elapsed_ns: int = Field(ge=0)
    evidence_handle_refs: tuple[str, ...] = ()
    observed_at: datetime | None = None
    payload: AgentAuthorityObservationPayloadV2

    @field_validator("evidence_handle_refs")
    @classmethod
    def canonical_evidence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_unique(value, "observation evidence handles")

    @field_validator("observed_at")
    @classmethod
    def utc_observed_at(cls, value: datetime | None) -> datetime | None:
        return None if value is None else require_utc(value)


class AgentAuthorityRunObservationsV2(AgentAuthorityOperatorModel):
    """Observation document whose L06 offsets are revocation-relative."""

    schema_version: Literal["2.0.0"] = AGENT_AUTHORITY_OBSERVATIONS_SCHEMA_VERSION_V2
    run_id: str = Field(min_length=1)
    observations: tuple[AgentAuthorityObservationV2, ...] = ()
    dependency_fault_results: tuple[DependencyFaultResultV1, ...] = ()
    operational_measurements: tuple[OperationalMeasurementV1, ...] = ()
    operational_coverage_gaps: tuple[OperationalCoverageGapV1, ...] = ()
    target_compatibility: tuple[TargetCompatibilityV1, ...] = ()
    evidence_handles: tuple[EvidenceHandleV1, ...] = ()
    coverage_limitations: tuple[CoverageLimitationV1, ...] = ()
    limitations: tuple[str, ...] = ()

    @field_validator("limitations")
    @classmethod
    def canonical_limitations(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_unique(value, "run limitations")

    @model_validator(mode="after")
    def validate_inventory(self) -> AgentAuthorityRunObservationsV2:
        validator = cast(
            Callable[
                [AgentAuthorityRunObservationsV1],
                AgentAuthorityRunObservationsV1,
            ],
            AgentAuthorityRunObservationsV1.validate_inventory,
        )
        validator(cast(AgentAuthorityRunObservationsV1, self))
        return self


def validate_observation_references_v2(
    plan: AgentAuthorityRunPlanV1,
    stimuli: AgentAuthorityStimulusSetV1,
    observations: AgentAuthorityRunObservationsV2,
    systems: tuple[SystemComponentProvenanceV2, ...],
) -> None:
    """Validate V2 observations while retaining every V1 non-L06 invariant."""

    if observations.run_id != plan.run_id:
        raise ValueError("observation run identifier differs from the run plan")
    system_ids = {item.component_id for item in systems}
    stimulus_index = {item.stimulus_id: item for item in stimuli.stimuli}
    evidence_index = {item.handle: item for item in observations.evidence_handles}
    for observation in observations.observations:
        stimulus = stimulus_index.get(observation.stimulus_id)
        if stimulus is None:
            raise ValueError("observation references an undeclared stimulus")
        if observation.payload.variant != stimulus.payload.variant:
            raise ValueError("observation and stimulus variants differ")
        if not set(observation.attribution.component_ids) <= system_ids:
            raise ValueError("observation attribution references an unknown component")
        require_evidence_refs(observation.evidence_handle_refs, evidence_index)
        _validate_case_observation_v2(stimulus, observation, plan, evidence_index)

    selected = {
        item.control_id
        for item in plan.control_coverage
        if item.disposition is CoverageDisposition.SELECTED
    }
    for limitation in observations.coverage_limitations:
        if limitation.control_id not in selected:
            raise ValueError(
                "non-applicable controls cannot carry coverage limitations"
            )

    # These validators inspect only fields whose contracts are unchanged in V2.
    v1_shape = cast(AgentAuthorityRunObservationsV1, observations)
    validate_dependency_results(stimuli, v1_shape, evidence_index)
    validate_operational_inventory(plan, v1_shape, evidence_index)
    validate_compatibility_inventory(plan, v1_shape, evidence_index)


def _validate_case_observation_v2(
    stimulus: AgentAuthorityStimulusV1,
    observation: AgentAuthorityObservationV2,
    plan: AgentAuthorityRunPlanV1,
    evidence_index: dict[str, EvidenceHandleV1],
) -> None:
    if not isinstance(stimulus.payload, L06RevocationPropagationStimulusV1):
        legacy = AgentAuthorityObservationV1.model_validate(
            observation.model_dump(mode="json")
        )
        validate_case_observation(stimulus, legacy, plan, evidence_index)
        return

    payload = observation.payload
    if not isinstance(payload, L06RevocationPropagationObservationV2):
        raise ValueError("L06 observation has the wrong typed payload")
    validate_revocation_observation_v2(stimulus.payload, payload, plan)
    require_evidence_refs(
        tuple(
            evidence_ref
            for point in payload.point_results
            for evidence_ref in point.evidence_refs
        )
        + tuple(
            evidence_ref
            for attempt in payload.timed_attempts
            for evidence_ref in attempt.evidence_refs
        ),
        evidence_index,
    )


def validate_revocation_observation_v2(
    stimulus: L06RevocationPropagationStimulusV1,
    observation: L06RevocationPropagationObservationV2,
    plan: AgentAuthorityRunPlanV1,
) -> None:
    """Validate L06 completeness using signed revocation-relative offsets."""

    if tuple(item.component_id for item in observation.point_results) != (
        stimulus.enforcement_point_ids
    ):
        raise ValueError("L06 point-result inventory differs from the stimulus")
    bound = next(
        item
        for item in plan.declared_bounds
        if item.bound_id == stimulus.declared_bound_id
    )
    post_bound = tuple(
        item
        for item in observation.timed_attempts
        if item.sent_offset_ns > bound.value_ns
    )
    for point in stimulus.enforcement_point_ids:
        if not any(item.enforcement_point_id == point for item in post_bound):
            raise ValueError("L06 requires a post-bound attempt per enforcement point")
    handles = {
        *(item.handle for item in stimulus.issued_credential_handles),
        *stimulus.child_delegation_handles,
    }
    if not handles:
        raise ValueError("L06 requires a credential or child-delegation handle")
    for handle in handles:
        if not any(item.credential_or_child_handle == handle for item in post_bound):
            raise ValueError("L06 requires a post-bound attempt per declared handle")
    if any(
        item.enforcement_point_id not in stimulus.enforcement_point_ids
        or item.credential_or_child_handle not in handles
        for item in observation.timed_attempts
    ):
        raise ValueError("L06 timed attempt contains an undeclared reference")


__all__ = [
    "AGENT_AUTHORITY_OBSERVATIONS_SCHEMA_VERSION_V2",
    "AgentAuthorityObservationPayloadV2",
    "AgentAuthorityObservationV2",
    "AgentAuthorityRunObservationsV2",
    "L06RevocationPropagationObservationV2",
    "RevocationPointResultV2",
    "TimedAttemptV2",
    "validate_observation_references_v2",
    "validate_revocation_observation_v2",
]
