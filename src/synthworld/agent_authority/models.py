"""Top-level agent-authority run-plan, observation, truth, and report models."""

from __future__ import annotations

import math
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from synthworld.agent_authority.cases import (
    AgentAuthorityObservationV1,
    AgentAuthorityStimulusSetV1,
    AgentAuthorityStimulusV1,
    DependencyFaultResultV1,
    EvidenceChannel,
    L01SecretExposureObservationV1,
    L01SecretExposureStimulusV1,
    L02CredentialReplayObservationV1,
    L02CredentialReplayStimulusV1,
    L03DirectPathBypassObservationV1,
    L03DirectPathBypassStimulusV1,
    L04NetworkPolicyObservationV1,
    L04NetworkPolicyStimulusV1,
    L05CriticalDependencyFailureObservationV1,
    L05CriticalDependencyFailureStimulusV1,
    L06RevocationPropagationObservationV1,
    L06RevocationPropagationStimulusV1,
)
from synthworld.agent_authority.common import (
    AGENT_AUTHORITY_OBSERVATIONS_SCHEMA_VERSION,
    AGENT_AUTHORITY_PRODUCT_INPUT_SCHEMA_VERSION,
    AGENT_AUTHORITY_PROTOCOL_VERSION,
    AGENT_AUTHORITY_REPORT_SCHEMA_VERSION,
    AGENT_AUTHORITY_RUN_PLAN_SCHEMA_VERSION,
    AGENT_AUTHORITY_TRUTH_SCHEMA_VERSION,
    CONTROL_ORDER,
    LAB_CONTROL_IDS,
    AgentAuthorityBenchmarkBindingV1,
    AgentAuthorityControlId,
    AgentAuthorityOperatorModel,
    ControlCoverageEntryV1,
    CoverageDisposition,
    DeclaredBoundV1,
    DeploymentPattern,
    DirectPathReachability,
    EvidenceHandleV1,
    EvidenceKind,
    FindingStatus,
    RunLayer,
    canonical_unique,
    present,
    require_utc,
    unique,
)
from synthworld.agent_authority.operational import (
    AddedLatencyMeasurementV1,
    CandidateProbeOutcome,
    CompatibilityStatus,
    FailureRateMeasurementV1,
    LatencyMeasurementV1,
    LatencyStatistic,
    OperationalCoverageGapV1,
    OperationalCoveragePlanV1,
    OperationalMeasurementV1,
    TargetCompatibilityV1,
    ThroughputMeasurementV1,
    nondominated_candidate_ids,
)
from synthworld.assurance.models_v2 import DigestV2, SystemComponentProvenanceV2
from synthworld.models import SyntheticModel


class AdapterAuthor(StrEnum):
    OPERATOR = "operator"
    VENDOR = "vendor"
    SYNTHWORLD = "synthworld"
    JOINT = "joint"


class AdapterAuthorshipDisclosureV1(AgentAuthorityOperatorModel):
    author: AdapterAuthor
    disclosure: str = Field(min_length=1)


class ConfigurationReviewStatus(StrEnum):
    REVIEWED = "reviewed"
    NOT_REVIEWED = "not_reviewed"
    NOT_APPLICABLE = "not_applicable"


class RepresentativeConfigurationReviewV1(AgentAuthorityOperatorModel):
    status: ConfigurationReviewStatus
    reviewer_id: str | None = None
    evidence_refs: tuple[str, ...] = ()
    limitation: str | None = None

    @field_validator("evidence_refs")
    @classmethod
    def canonical_evidence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_unique(value, "configuration-review evidence")

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        if self.status is ConfigurationReviewStatus.REVIEWED:
            if not present(self.reviewer_id) or not self.evidence_refs:
                raise ValueError(
                    "a reviewed configuration requires reviewer and evidence"
                )
            if self.limitation is not None:
                raise ValueError("a reviewed configuration forbids a limitation")
        else:
            if self.reviewer_id is not None or self.evidence_refs:
                raise ValueError(
                    "an unreviewed configuration forbids review attribution"
                )
            if not present(self.limitation):
                raise ValueError("an unreviewed configuration requires a limitation")
        return self


class ProtocolConflictV1(AgentAuthorityOperatorModel):
    topic: str = Field(min_length=1)
    disposition: str = Field(min_length=1)


class AgentAuthorityRunPlanV1(AgentAuthorityOperatorModel):
    schema_version: Literal["1.0.0"] = AGENT_AUTHORITY_RUN_PLAN_SCHEMA_VERSION
    protocol_version: Literal["1.0.0"] = AGENT_AUTHORITY_PROTOCOL_VERSION
    run_id: str = Field(min_length=1)
    run_layer: RunLayer
    control_coverage: tuple[ControlCoverageEntryV1, ...] = Field(min_length=1)
    benchmark: AgentAuthorityBenchmarkBindingV1
    event_schedule_version: str = Field(min_length=1)
    deployment_patterns: tuple[DeploymentPattern, ...] = Field(min_length=1)
    authority_path_component_ids: tuple[str, ...] = Field(min_length=1)
    enforcement_point_ids: tuple[str, ...] = Field(min_length=1)
    direct_path_reachability: DirectPathReachability
    isolation_mechanism: str = Field(min_length=1)
    authority_critical_dependency_ids: tuple[str, ...] = Field(min_length=1)
    declared_bounds: tuple[DeclaredBoundV1, ...] = ()
    operational_coverage: OperationalCoveragePlanV1
    stimulus_set_digest: DigestV2
    adapter_authorship: AdapterAuthorshipDisclosureV1
    representative_configuration_review: RepresentativeConfigurationReviewV1
    conflicts: tuple[ProtocolConflictV1, ...] = ()
    planned_at: datetime | None = None

    @field_validator("deployment_patterns")
    @classmethod
    def canonical_patterns(
        cls, value: tuple[DeploymentPattern, ...]
    ) -> tuple[DeploymentPattern, ...]:
        if value != tuple(sorted(set(value), key=str)):
            raise ValueError("deployment patterns must be sorted and unique")
        return value

    @field_validator("authority_path_component_ids")
    @classmethod
    def ordered_unique_path(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        unique(value, "authority-path components")
        if any(not item.strip() for item in value):
            raise ValueError("authority-path components must be nonblank")
        return value

    @field_validator("enforcement_point_ids", "authority_critical_dependency_ids")
    @classmethod
    def canonical_component_sets(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_unique(value, "run-plan component references")

    @field_validator("planned_at")
    @classmethod
    def utc_planned_at(cls, value: datetime | None) -> datetime | None:
        return None if value is None else require_utc(value)

    @model_validator(mode="after")
    def validate_canonical_contract(self) -> Self:
        coverage_ids = tuple(item.control_id for item in self.control_coverage)
        if coverage_ids != CONTROL_ORDER:
            raise ValueError(
                "control coverage must contain every protocol control in order"
            )
        bound_ids = tuple(item.bound_id for item in self.declared_bounds)
        unique(bound_ids, "declared bound identifiers")
        if bound_ids != tuple(sorted(bound_ids)):
            raise ValueError("declared bounds must be canonically ordered")
        conflict_topics = tuple(item.topic for item in self.conflicts)
        unique(conflict_topics, "protocol conflict topics")
        if conflict_topics != tuple(sorted(conflict_topics)):
            raise ValueError("protocol conflicts must be canonically ordered")
        selected = {
            item.control_id
            for item in self.control_coverage
            if item.disposition is CoverageDisposition.SELECTED
        }
        if self.run_layer is RunLayer.CORE and selected & set(LAB_CONTROL_IDS):
            raise ValueError("a core run cannot select live lab controls")
        has_l07 = AgentAuthorityControlId.L07 in selected
        has_l08 = AgentAuthorityControlId.L08 in selected
        if has_l07 is not bool(self.operational_coverage.performance_stages):
            raise ValueError("SW-AA-L07 selection must match its stage denominator")
        if has_l08 is not bool(self.operational_coverage.compatibility_targets):
            raise ValueError("SW-AA-L08 selection must match its target denominator")
        compatible_patterns = {
            DeploymentPattern.PROXY_INJECTION,
            DeploymentPattern.SHORT_LIVED_MINTING,
        }
        if has_l08 and not set(self.deployment_patterns) & compatible_patterns:
            raise ValueError("SW-AA-L08 is inconsistent with the deployment pattern")
        return self


class AgentAuthorityProductInputV1(AgentAuthorityOperatorModel):
    """Exact adapter-facing envelope; intentionally has no synthetic marker."""

    run_plan_digest: DigestV2
    schema_version: Literal["1.0.0"] = AGENT_AUTHORITY_PRODUCT_INPUT_SCHEMA_VERSION
    stimuli: tuple[AgentAuthorityStimulusV1, ...] = Field(min_length=1)
    stimulus_digest: DigestV2

    @model_validator(mode="after")
    def validate_stimulus_order(self) -> Self:
        AgentAuthorityStimulusSetV1(stimuli=self.stimuli)
        return self


class CoverageLimitationKind(StrEnum):
    SKIPPED = "skipped"
    CAPPED = "capped"


class CoverageLimitationV1(AgentAuthorityOperatorModel):
    control_id: AgentAuthorityControlId
    kind: CoverageLimitationKind
    reason: str = Field(min_length=1)


class AgentAuthorityRunObservationsV1(AgentAuthorityOperatorModel):
    schema_version: Literal["1.0.0"] = AGENT_AUTHORITY_OBSERVATIONS_SCHEMA_VERSION
    run_id: str = Field(min_length=1)
    observations: tuple[AgentAuthorityObservationV1, ...] = ()
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
    def validate_inventory(self) -> Self:
        ordered_unique_models(
            self.observations, "stimulus_id", "observation stimulus identifiers"
        )
        ordered_unique_models(
            self.dependency_fault_results,
            "stimulus_id",
            "dependency-fault stimulus identifiers",
        )
        ordered_unique_models(
            self.operational_coverage_gaps,
            "stage_id",
            "operational gap stage identifiers",
        )
        ordered_unique_models(
            self.target_compatibility,
            "coverage_key",
            "compatibility coverage keys",
        )
        ordered_unique_models(
            self.evidence_handles, "handle", "evidence handle identifiers"
        )
        limitation_keys = tuple(
            (item.control_id.value, item.kind.value)
            for item in self.coverage_limitations
        )
        if len(limitation_keys) != len(set(limitation_keys)):
            raise ValueError("coverage limitations must be unique per control and kind")
        if limitation_keys != tuple(sorted(limitation_keys)):
            raise ValueError("coverage limitations must be canonically ordered")
        measurement_keys = tuple(
            (
                item.stage_id,
                item.payload.measurement_kind,
                item.payload.statistic.value
                if isinstance(item.payload, LatencyMeasurementV1)
                else "",
            )
            for item in self.operational_measurements
        )
        if len(measurement_keys) != len(set(measurement_keys)):
            raise ValueError("operational measurements must be unique")
        if measurement_keys != tuple(sorted(measurement_keys)):
            raise ValueError("operational measurements must be canonically ordered")
        return self


class _EvidenceTruthV1(SyntheticModel):
    required_evidence_kinds: tuple[EvidenceKind, ...] = Field(min_length=1)

    @field_validator("required_evidence_kinds")
    @classmethod
    def canonical_evidence_kinds(
        cls, value: tuple[EvidenceKind, ...]
    ) -> tuple[EvidenceKind, ...]:
        if value != tuple(sorted(set(value), key=str)):
            raise ValueError("required evidence kinds must be sorted and unique")
        return value


class L01SecretExposureTruthV1(_EvidenceTruthV1):
    variant: Literal["l01_secret_exposure"] = "l01_secret_exposure"
    required_channels: tuple[EvidenceChannel, ...] = Field(min_length=1)

    @field_validator("required_channels")
    @classmethod
    def canonical_channels(
        cls, value: tuple[EvidenceChannel, ...]
    ) -> tuple[EvidenceChannel, ...]:
        if value != tuple(sorted(set(value), key=str)):
            raise ValueError("required channels must be sorted and unique")
        return value


class L02CredentialReplayTruthV1(_EvidenceTruthV1):
    variant: Literal["l02_credential_replay"] = "l02_credential_replay"
    expected_decisions: tuple[Literal["deny", "error"], ...] = ("deny", "error")
    expected_no_side_effect: Literal[True] = True


class L03DirectPathBypassTruthV1(_EvidenceTruthV1):
    variant: Literal["l03_direct_path_bypass"] = "l03_direct_path_bypass"
    safe_reachability_or_denial: Literal[True] = True


class L04NetworkPolicyTruthV1(_EvidenceTruthV1):
    variant: Literal["l04_network_policy"] = "l04_network_policy"
    safe_connectivity_or_denial: Literal[True] = True


class L05CriticalDependencyFailureTruthV1(_EvidenceTruthV1):
    variant: Literal["l05_critical_dependency_failure"] = (
        "l05_critical_dependency_failure"
    )
    enforcement_point_ids: tuple[str, ...] = Field(min_length=1)
    expected_fail_closed: Literal[True] = True

    @field_validator("enforcement_point_ids")
    @classmethod
    def canonical_points(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_unique(value, "L05 truth enforcement points")


class L06RevocationPropagationTruthV1(_EvidenceTruthV1):
    variant: Literal["l06_revocation_propagation"] = "l06_revocation_propagation"
    enforcement_point_ids: tuple[str, ...] = Field(min_length=1)
    credential_or_child_handles: tuple[str, ...] = Field(min_length=1)
    bound_ns: int = Field(gt=0)

    @field_validator("enforcement_point_ids", "credential_or_child_handles")
    @classmethod
    def canonical_references(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_unique(value, "L06 truth references")


AgentAuthorityTruthPayloadV1 = Annotated[
    L01SecretExposureTruthV1
    | L02CredentialReplayTruthV1
    | L03DirectPathBypassTruthV1
    | L04NetworkPolicyTruthV1
    | L05CriticalDependencyFailureTruthV1
    | L06RevocationPropagationTruthV1,
    Field(discriminator="variant"),
]


class AgentAuthorityStimulusTruthV1(SyntheticModel):
    stimulus_id: str = Field(min_length=1)
    control_id: AgentAuthorityControlId
    payload: AgentAuthorityTruthPayloadV1


class AgentAuthorityLabTruthV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = AGENT_AUTHORITY_TRUTH_SCHEMA_VERSION
    run_id: str = Field(min_length=1)
    stimuli: tuple[AgentAuthorityStimulusTruthV1, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_inventory(self) -> Self:
        ordered_unique_models(self.stimuli, "stimulus_id", "truth stimulus identifiers")
        return self


class MetricEmptyBehaviour(StrEnum):
    NONEMPTY = "nonempty"
    NULL_IF_EMPTY = "null_if_empty"


class AgentAuthoritySecurityMetricV1(SyntheticModel):
    control_id: AgentAuthorityControlId
    name: str = Field(min_length=1)
    value: float | None
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    support: int = Field(ge=0)
    denominator_meaning: str = Field(min_length=1)
    empty_behaviour: MetricEmptyBehaviour

    @model_validator(mode="after")
    def validate_fraction(self) -> Self:
        if self.support > self.denominator:
            raise ValueError("metric support cannot exceed its denominator")
        if self.denominator == 0:
            if (
                self.empty_behaviour is not MetricEmptyBehaviour.NULL_IF_EMPTY
                or self.value is not None
                or self.numerator
            ):
                raise ValueError("an empty metric must follow its null behaviour")
        else:
            if self.value is None or not math.isclose(
                self.value,
                self.numerator / self.denominator,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                raise ValueError("metric value must equal numerator / denominator")
        return self


class StimulusFindingV1(SyntheticModel):
    stimulus_id: str = Field(min_length=1)
    control_id: AgentAuthorityControlId
    status: FindingStatus
    failure_code: str | None = None
    evidence_refs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_failure_code(self) -> Self:
        if self.status is FindingStatus.PASS:
            if self.failure_code is not None:
                raise ValueError("passing findings forbid a failure code")
        elif not present(self.failure_code):
            raise ValueError("non-passing findings require a status code")
        return self


class OperationalStageStatus(StrEnum):
    COMPLETE = "complete"
    GAP = "gap"


class OperationalRatioV1(SyntheticModel):
    numerator: int = Field(ge=0)
    denominator: int = Field(gt=0)
    numerator_meaning: str = Field(min_length=1)
    denominator_meaning: str = Field(min_length=1)


class OperationalStageReportV1(SyntheticModel):
    stage_id: str = Field(min_length=1)
    status: OperationalStageStatus
    latency_ns: tuple[tuple[LatencyStatistic, int], ...] = ()
    failure_rate: OperationalRatioV1 | None = None
    throughput: OperationalRatioV1 | None = None
    limitation: str | None = None

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        if self.status is OperationalStageStatus.COMPLETE:
            if (
                not self.latency_ns
                or self.failure_rate is None
                or self.throughput is None
                or self.limitation is not None
            ):
                raise ValueError("a complete operational stage requires every measure")
        elif (
            self.latency_ns
            or self.failure_rate is not None
            or self.throughput is not None
            or not present(self.limitation)
        ):
            raise ValueError("an operational gap carries only its limitation")
        return self


class CompatibilityCoverageReportV1(SyntheticModel):
    coverage_key: str = Field(min_length=1)
    status: CompatibilityStatus
    nondominated_minima: tuple[str, ...] = ()
    limitation: str | None = None


class AgentAuthorityLabReportV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = AGENT_AUTHORITY_REPORT_SCHEMA_VERSION
    run_id: str = Field(min_length=1)
    findings: tuple[StimulusFindingV1, ...]
    security_metrics: tuple[AgentAuthoritySecurityMetricV1, ...]
    operational_stages: tuple[OperationalStageReportV1, ...]
    added_latency: tuple[AddedLatencyMeasurementV1, ...]
    compatibility: tuple[CompatibilityCoverageReportV1, ...]
    limitations: tuple[str, ...] = ()


def stimulus_control(stimulus: AgentAuthorityStimulusV1) -> AgentAuthorityControlId:
    variants = {
        "l01_secret_exposure": AgentAuthorityControlId.L01,
        "l02_credential_replay": AgentAuthorityControlId.L02,
        "l03_direct_path_bypass": AgentAuthorityControlId.L03,
        "l04_network_policy": AgentAuthorityControlId.L04,
        "l05_critical_dependency_failure": AgentAuthorityControlId.L05,
        "l06_revocation_propagation": AgentAuthorityControlId.L06,
    }
    return variants[stimulus.payload.variant]


def validate_run_plan_references(
    plan: AgentAuthorityRunPlanV1,
    stimuli: AgentAuthorityStimulusSetV1,
    systems: tuple[SystemComponentProvenanceV2, ...],
) -> None:
    """Resolve every predeclared component, bound, and coverage reference."""

    system_ids = {item.component_id for item in systems}
    if len(system_ids) != len(systems):
        raise ValueError("systems under test must use unique component identifiers")
    references = (
        set(plan.authority_path_component_ids)
        | set(plan.enforcement_point_ids)
        | set(plan.authority_critical_dependency_ids)
        | {item.component_id for item in plan.operational_coverage.performance_stages}
        | {
            item.component_id
            for item in plan.operational_coverage.compatibility_targets
        }
    )
    if not references <= system_ids:
        raise ValueError("run plan contains unresolved system component references")

    selected = {
        item.control_id
        for item in plan.control_coverage
        if item.disposition is CoverageDisposition.SELECTED
    }
    counts = {control: 0 for control in LAB_CONTROL_IDS}
    bounds = {item.bound_id: item for item in plan.declared_bounds}
    for stimulus in stimuli.stimuli:
        control = stimulus_control(stimulus)
        counts[control] += 1
        payload = stimulus.payload
        stimulus_refs: set[str] = set()
        if isinstance(payload, L03DirectPathBypassStimulusV1):
            stimulus_refs |= set(payload.sanctioned_path_component_ids)
            stimulus_refs |= set(payload.expected_enforcement_point_ids)
        elif isinstance(payload, L04NetworkPolicyStimulusV1):
            stimulus_refs |= set(payload.enforcement_point_ids)
        elif isinstance(payload, L05CriticalDependencyFailureStimulusV1):
            stimulus_refs.add(payload.dependency_component_id)
            stimulus_refs |= set(payload.enforcement_point_ids)
            if payload.dependency_component_id not in (
                plan.authority_critical_dependency_ids
            ):
                raise ValueError("L05 fault target is not an authority dependency")
        elif isinstance(payload, L06RevocationPropagationStimulusV1):
            stimulus_refs |= set(payload.enforcement_point_ids)
            bound = bounds.get(payload.declared_bound_id)
            if bound is None or bound.control_id is not AgentAuthorityControlId.L06:
                raise ValueError("L06 stimulus does not resolve an L06 bound")
        if not stimulus_refs <= system_ids:
            raise ValueError("stimulus contains an unresolved component reference")
    for control, count in counts.items():
        if (control in selected) is not bool(count):
            raise ValueError(
                "lab control selection must match its stimulus denominator"
            )


def validate_observation_references(
    plan: AgentAuthorityRunPlanV1,
    stimuli: AgentAuthorityStimulusSetV1,
    observations: AgentAuthorityRunObservationsV1,
    systems: tuple[SystemComponentProvenanceV2, ...],
) -> None:
    """Validate observation, evidence, L07, and L08 inventories against the plan."""

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
        validate_case_observation(stimulus, observation, plan, evidence_index)

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
    validate_dependency_results(stimuli, observations, evidence_index)
    validate_operational_inventory(plan, observations, evidence_index)
    validate_compatibility_inventory(plan, observations, evidence_index)


def validate_case_observation(
    stimulus: AgentAuthorityStimulusV1,
    observation: AgentAuthorityObservationV1,
    plan: AgentAuthorityRunPlanV1,
    evidence_index: dict[str, EvidenceHandleV1],
) -> None:
    payload = stimulus.payload
    result = observation.payload
    if isinstance(payload, L01SecretExposureStimulusV1):
        if not isinstance(result, L01SecretExposureObservationV1):
            raise ValueError("L01 observation has the wrong typed payload")
        channels = tuple(item.channel for item in result.channel_scans)
        if channels != payload.required_channels:
            raise ValueError("L01 observation must scan every required channel exactly")
        require_evidence_refs(
            tuple(item.evidence_handle_ref for item in result.channel_scans),
            evidence_index,
        )
    elif isinstance(payload, L02CredentialReplayStimulusV1):
        if not isinstance(result, L02CredentialReplayObservationV1):
            raise ValueError("L02 observation has the wrong typed payload")
        require_evidence_refs(result.target_evidence_refs, evidence_index)
    elif isinstance(payload, L03DirectPathBypassStimulusV1):
        if not isinstance(result, L03DirectPathBypassObservationV1):
            raise ValueError("L03 observation has the wrong typed payload")
        if not set(result.traversed_component_ids) <= {
            *payload.sanctioned_path_component_ids,
            *plan.enforcement_point_ids,
        }:
            raise ValueError("L03 observation names an undeclared traversed component")
        require_evidence_refs(
            (*result.network_evidence_refs, *result.target_evidence_refs),
            evidence_index,
        )
    elif isinstance(payload, L04NetworkPolicyStimulusV1):
        if not isinstance(result, L04NetworkPolicyObservationV1):
            raise ValueError("L04 observation has the wrong typed payload")
        require_evidence_refs(
            (*result.network_evidence_refs, *result.target_evidence_refs),
            evidence_index,
        )
    elif isinstance(payload, L05CriticalDependencyFailureStimulusV1):
        if not isinstance(result, L05CriticalDependencyFailureObservationV1):
            raise ValueError("L05 observation has the wrong typed payload")
        if tuple(item.component_id for item in result.enforcement_outcomes) != (
            payload.enforcement_point_ids
        ):
            raise ValueError("L05 observation must cover every enforcement point")
        require_evidence_refs(
            tuple(
                evidence_ref
                for outcome in result.enforcement_outcomes
                for evidence_ref in outcome.evidence_refs
            ),
            evidence_index,
        )
    else:
        # The stimulus union is closed; the prior branches exhaust L01--L05.
        if not isinstance(result, L06RevocationPropagationObservationV1):
            raise ValueError("L06 observation has the wrong typed payload")
        validate_revocation_observation(payload, result, plan)
        require_evidence_refs(
            tuple(
                evidence_ref
                for point in result.point_results
                for evidence_ref in point.evidence_refs
            )
            + tuple(
                evidence_ref
                for attempt in result.timed_attempts
                for evidence_ref in attempt.evidence_refs
            ),
            evidence_index,
        )


def validate_revocation_observation(
    stimulus: L06RevocationPropagationStimulusV1,
    observation: L06RevocationPropagationObservationV1,
    plan: AgentAuthorityRunPlanV1,
) -> None:
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
        if item.sent_elapsed_ns > bound.value_ns
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


def validate_dependency_results(
    stimuli: AgentAuthorityStimulusSetV1,
    observations: AgentAuthorityRunObservationsV1,
    evidence_index: dict[str, EvidenceHandleV1],
) -> None:
    expected = {
        item.stimulus_id: item.payload
        for item in stimuli.stimuli
        if isinstance(item.payload, L05CriticalDependencyFailureStimulusV1)
    }
    actual = {item.stimulus_id: item for item in observations.dependency_fault_results}
    if set(actual) != set(expected):
        raise ValueError("dependency-fault result inventory differs from L05 stimuli")
    for stimulus_id, result in actual.items():
        payload = expected[stimulus_id]
        if result.dependency_component_id != payload.dependency_component_id:
            raise ValueError("dependency-fault result names the wrong dependency")
        require_evidence_refs(result.evidence_refs, evidence_index)


def validate_operational_inventory(
    plan: AgentAuthorityRunPlanV1,
    observations: AgentAuthorityRunObservationsV1,
    evidence_index: dict[str, EvidenceHandleV1],
) -> None:
    measurements: dict[str, list[OperationalMeasurementV1]] = {}
    for item in observations.operational_measurements:
        measurements.setdefault(item.stage_id, []).append(item)
        require_evidence_refs(item.evidence_refs, evidence_index)
    gaps = {item.stage_id: item for item in observations.operational_coverage_gaps}
    stage_ids = {item.stage_id for item in plan.operational_coverage.performance_stages}
    if set(measurements) & set(gaps):
        raise ValueError("an L07 stage cannot contain measurements and a gap")
    if set(measurements) | set(gaps) != stage_ids:
        raise ValueError("L07 observations differ from the predeclared stage inventory")
    for gap in gaps.values():
        require_evidence_refs(gap.evidence_refs, evidence_index)
    for stage in plan.operational_coverage.performance_stages:
        rows = measurements.get(stage.stage_id)
        if rows is None:
            continue
        latency = tuple(
            row.payload.statistic
            for row in rows
            if isinstance(row.payload, LatencyMeasurementV1)
        )
        kinds = tuple(row.payload.measurement_kind for row in rows)
        if latency != stage.statistics:
            raise ValueError("L07 latency statistics differ from the stage plan")
        if kinds.count("failure_rate") != 1 or kinds.count("throughput") != 1:
            raise ValueError("L07 requires one failure-rate and one throughput row")
        sample_counts = {row.sample_count for row in rows}
        if len(sample_counts) != 1:
            raise ValueError("L07 stage rows must use one sample count")
        sample_count = next(iter(sample_counts))
        failure = next(
            row.payload
            for row in rows
            if isinstance(row.payload, FailureRateMeasurementV1)
        )
        throughput = next(
            row.payload
            for row in rows
            if isinstance(row.payload, ThroughputMeasurementV1)
        )
        if failure.total_count != sample_count:
            raise ValueError("L07 failure-rate total must equal the sample count")
        if throughput.completed_count > sample_count:
            raise ValueError("L07 throughput completions exceed the sample count")


def validate_compatibility_inventory(
    plan: AgentAuthorityRunPlanV1,
    observations: AgentAuthorityRunObservationsV1,
    evidence_index: dict[str, EvidenceHandleV1],
) -> None:
    targets = {
        item.coverage_key: item
        for item in plan.operational_coverage.compatibility_targets
    }
    records = {item.coverage_key: item for item in observations.target_compatibility}
    if set(records) != set(targets):
        raise ValueError("L08 records differ from the predeclared target inventory")
    for key, record in records.items():
        target = targets[key]
        if (record.component_id, record.target_handle) != (
            target.component_id,
            target.target_handle,
        ):
            raise ValueError("L08 record component or target differs from the plan")
        require_evidence_refs(record.evidence_refs, evidence_index)
        candidate_ids = tuple(item.candidate_id for item in target.probe_candidates)
        result_ids = tuple(item.candidate_id for item in record.candidate_results)
        if record.status is CompatibilityStatus.NOT_ATTEMPTED:
            if result_ids:
                raise ValueError("not-attempted L08 records forbid candidate results")
            continue
        if result_ids != candidate_ids:
            raise ValueError("L08 candidate result inventory differs from the plan")
        for result in record.candidate_results:
            require_evidence_refs(result.evidence_refs, evidence_index)
        if record.status is CompatibilityStatus.MEASURED:
            obtained = {
                item.candidate_id
                for item in record.candidate_results
                if item.outcome is CandidateProbeOutcome.OBTAINED
            }
            expected = nondominated_candidate_ids(target.probe_candidates, obtained)
            if record.nondominated_minima != expected:
                raise ValueError("L08 nondominated minima do not recompute")


def require_evidence_refs(
    references: tuple[str, ...], evidence_index: dict[str, EvidenceHandleV1]
) -> None:
    if not set(references) <= set(evidence_index):
        raise ValueError("observation references an undeclared evidence handle")


def ordered_unique_models(
    values: tuple[object, ...], attribute: str, description: str
) -> None:
    keys = tuple(str(getattr(item, attribute)) for item in values)
    unique(keys, description)
    if keys != tuple(sorted(keys)):
        raise ValueError(f"{description} must be canonically ordered")


__all__ = [
    "AGENT_AUTHORITY_OBSERVATIONS_SCHEMA_VERSION",
    "AGENT_AUTHORITY_PRODUCT_INPUT_SCHEMA_VERSION",
    "AGENT_AUTHORITY_PROTOCOL_VERSION",
    "AGENT_AUTHORITY_REPORT_SCHEMA_VERSION",
    "AGENT_AUTHORITY_RUN_PLAN_SCHEMA_VERSION",
    "AGENT_AUTHORITY_TRUTH_SCHEMA_VERSION",
    "AdapterAuthor",
    "AdapterAuthorshipDisclosureV1",
    "AgentAuthorityBenchmarkBindingV1",
    "AgentAuthorityControlId",
    "AgentAuthorityLabReportV1",
    "AgentAuthorityLabTruthV1",
    "AgentAuthorityObservationV1",
    "AgentAuthorityOperatorModel",
    "AgentAuthorityProductInputV1",
    "AgentAuthorityRunObservationsV1",
    "AgentAuthorityRunPlanV1",
    "AgentAuthoritySecurityMetricV1",
    "AgentAuthorityStimulusSetV1",
    "AgentAuthorityStimulusTruthV1",
    "AgentAuthorityStimulusV1",
    "AgentAuthorityTruthPayloadV1",
    "CompatibilityCoverageReportV1",
    "ConfigurationReviewStatus",
    "CoverageLimitationKind",
    "CoverageLimitationV1",
    "MetricEmptyBehaviour",
    "OperationalRatioV1",
    "OperationalStageReportV1",
    "OperationalStageStatus",
    "ProtocolConflictV1",
    "RepresentativeConfigurationReviewV1",
    "StimulusFindingV1",
    "stimulus_control",
    "validate_observation_references",
    "validate_run_plan_references",
]
