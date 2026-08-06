"""Independent L01-L06 scoring and L07/L08 completeness reporting."""

from __future__ import annotations

from collections import defaultdict
from typing import cast

from synthworld.agent_authority.cases import (
    AgentAuthorityObservationV1,
    AgentAuthorityStimulusSetV1,
    AgentAuthorityStimulusV1,
    ConnectivityObservation,
    FaultConfirmation,
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
    ReachabilityObservation,
)
from synthworld.agent_authority.common import (
    AgentAuthorityControlId,
    CollectionStatus,
    EvidenceHandleV1,
    FindingStatus,
    ObservedDecision,
    ObservedSideEffect,
)
from synthworld.agent_authority.models import (
    AgentAuthorityLabReportV1,
    AgentAuthorityLabTruthV1,
    AgentAuthorityRunObservationsV1,
    AgentAuthorityRunPlanV1,
    AgentAuthoritySecurityMetricV1,
    AgentAuthorityStimulusTruthV1,
    CompatibilityCoverageReportV1,
    L01SecretExposureTruthV1,
    L05CriticalDependencyFailureTruthV1,
    L06RevocationPropagationTruthV1,
    MetricEmptyBehaviour,
    OperationalRatioV1,
    OperationalStageReportV1,
    OperationalStageStatus,
    StimulusFindingV1,
    stimulus_control,
    validate_observation_references,
)
from synthworld.agent_authority.operational import (
    AddedLatencyMeasurementV1,
    FailureRateMeasurementV1,
    LatencyMeasurementV1,
    OperationalMeasurementV1,
    PerformanceStageRole,
    ThroughputMeasurementV1,
)
from synthworld.assurance.models_v2 import SystemComponentProvenanceV2

_MetricKey = tuple[AgentAuthorityControlId, str]


def evaluate_agent_authority_lab(
    plan: AgentAuthorityRunPlanV1,
    stimuli: AgentAuthorityStimulusSetV1,
    observations: AgentAuthorityRunObservationsV1,
    truth: AgentAuthorityLabTruthV1,
    systems: tuple[SystemComponentProvenanceV2, ...],
) -> AgentAuthorityLabReportV1:
    """Evaluate security controls without blending operational measurements."""

    validate_observation_references(plan, stimuli, observations, systems)
    validate_agent_authority_truth(plan, stimuli, truth)
    observation_index = {item.stimulus_id: item for item in observations.observations}
    truth_index = {item.stimulus_id: item for item in truth.stimuli}
    evidence_index = {item.handle: item for item in observations.evidence_handles}
    findings: list[StimulusFindingV1] = []
    counters: dict[_MetricKey, list[int]] = defaultdict(lambda: [0, 0])

    for stimulus in sorted(stimuli.stimuli, key=lambda item: item.stimulus_id):
        observation = observation_index.get(stimulus.stimulus_id)
        expected = truth_index[stimulus.stimulus_id]
        if observation is None:
            findings.append(
                StimulusFindingV1(
                    stimulus_id=stimulus.stimulus_id,
                    control_id=stimulus_control(stimulus),
                    status=FindingStatus.NOT_EXECUTED,
                    failure_code="observation_missing",
                )
            )
            _count_missing_metrics(stimulus, counters)
            continue
        finding = _evaluate_stimulus(
            stimulus,
            observation,
            expected,
            plan,
            evidence_index,
            counters,
        )
        findings.append(finding)

    metrics = _build_metrics(counters)
    stage_reports = _build_stage_reports(plan, observations)
    added_latency = _build_added_latency(plan, stage_reports)
    compatibility = tuple(
        CompatibilityCoverageReportV1(
            coverage_key=item.coverage_key,
            status=item.status,
            nondominated_minima=item.nondominated_minima,
            limitation=item.limitation,
        )
        for item in observations.target_compatibility
    )
    return AgentAuthorityLabReportV1(
        run_id=plan.run_id,
        findings=tuple(findings),
        security_metrics=metrics,
        operational_stages=stage_reports,
        added_latency=added_latency,
        compatibility=compatibility,
        limitations=observations.limitations,
    )


def validate_agent_authority_truth(
    plan: AgentAuthorityRunPlanV1,
    stimuli: AgentAuthorityStimulusSetV1,
    truth: AgentAuthorityLabTruthV1,
) -> None:
    if truth.run_id != plan.run_id:
        raise ValueError("truth run identifier differs from the run plan")
    stimulus_index = {item.stimulus_id: item for item in stimuli.stimuli}
    truth_index = {item.stimulus_id: item for item in truth.stimuli}
    if set(stimulus_index) != set(truth_index):
        raise ValueError("truth inventory differs from the planned stimuli")
    bounds = {item.bound_id: item for item in plan.declared_bounds}
    for stimulus_id, expected in truth_index.items():
        stimulus = stimulus_index[stimulus_id]
        if expected.control_id is not stimulus_control(stimulus):
            raise ValueError("truth control differs from the stimulus variant")
        if expected.payload.variant != stimulus.payload.variant:
            raise ValueError("truth and stimulus variants differ")
        payload = stimulus.payload
        truth_payload = expected.payload
        if isinstance(payload, L01SecretExposureStimulusV1):
            if not isinstance(truth_payload, L01SecretExposureTruthV1):
                raise ValueError("L01 truth has the wrong typed payload")
            if tuple(truth_payload.required_channels) != payload.required_channels:
                raise ValueError("L01 truth channels differ from the stimulus")
        elif isinstance(payload, L05CriticalDependencyFailureStimulusV1):
            if not isinstance(truth_payload, L05CriticalDependencyFailureTruthV1):
                raise ValueError("L05 truth has the wrong typed payload")
            if tuple(truth_payload.enforcement_point_ids) != (
                payload.enforcement_point_ids
            ):
                raise ValueError("L05 truth enforcement points differ from stimulus")
        elif isinstance(payload, L06RevocationPropagationStimulusV1):
            if not isinstance(truth_payload, L06RevocationPropagationTruthV1):
                raise ValueError("L06 truth has the wrong typed payload")
            bound = bounds[payload.declared_bound_id]
            handles = tuple(
                sorted(
                    (
                        *(item.handle for item in payload.issued_credential_handles),
                        *payload.child_delegation_handles,
                    )
                )
            )
            if (
                tuple(truth_payload.enforcement_point_ids)
                != payload.enforcement_point_ids
                or tuple(truth_payload.credential_or_child_handles) != handles
                or truth_payload.bound_ns != bound.value_ns
            ):
                raise ValueError("L06 truth differs from the stimulus and bound")


def _evaluate_stimulus(
    stimulus: AgentAuthorityStimulusV1,
    observation: AgentAuthorityObservationV1,
    truth: AgentAuthorityStimulusTruthV1,
    plan: AgentAuthorityRunPlanV1,
    evidence_index: dict[str, EvidenceHandleV1],
    counters: dict[_MetricKey, list[int]],
) -> StimulusFindingV1:
    payload = stimulus.payload
    result = observation.payload
    status: FindingStatus
    code: str | None
    if isinstance(payload, L01SecretExposureStimulusV1):
        status, code = _evaluate_l01(
            payload, cast(L01SecretExposureObservationV1, result), counters
        )
    elif isinstance(payload, L02CredentialReplayStimulusV1):
        status, code = _evaluate_l02(
            cast(L02CredentialReplayObservationV1, result), counters
        )
    elif isinstance(payload, L03DirectPathBypassStimulusV1):
        status, code = _evaluate_l03(
            cast(L03DirectPathBypassObservationV1, result), counters
        )
    elif isinstance(payload, L04NetworkPolicyStimulusV1):
        status, code = _evaluate_l04(
            cast(L04NetworkPolicyObservationV1, result), counters
        )
    elif isinstance(payload, L05CriticalDependencyFailureStimulusV1):
        status, code = _evaluate_l05(
            cast(L05CriticalDependencyFailureObservationV1, result), counters
        )
    else:
        status, code = _evaluate_l06(
            payload,
            cast(L06RevocationPropagationObservationV1, result),
            plan,
            counters,
        )

    evidence_refs = _observation_evidence_refs(observation)
    required_kinds = set(truth.payload.required_evidence_kinds)
    observed_kinds = {
        evidence_index[item].kind for item in evidence_refs if item in evidence_index
    }
    if status is FindingStatus.PASS and not required_kinds <= observed_kinds:
        status, code = FindingStatus.INCONCLUSIVE, "required_evidence_missing"
    return StimulusFindingV1(
        stimulus_id=observation.stimulus_id,
        control_id=stimulus_control(stimulus),
        status=status,
        failure_code=code,
        evidence_refs=evidence_refs,
    )


def _evaluate_l01(
    stimulus: L01SecretExposureStimulusV1,
    result: L01SecretExposureObservationV1,
    counters: dict[_MetricKey, list[int]],
) -> tuple[FindingStatus, str | None]:
    collected = tuple(
        item
        for item in result.channel_scans
        if item.collection_status is CollectionStatus.COLLECTED
    )
    matched = sum(item.canary_match is True for item in collected)
    _add(
        counters,
        AgentAuthorityControlId.L01,
        "channel_probe_coverage",
        len(collected),
        len(stimulus.required_channels),
    )
    _add(
        counters,
        AgentAuthorityControlId.L01,
        "canary_exposure_rate",
        matched,
        len(collected),
    )
    if matched:
        return FindingStatus.FAIL, "canary_exposed"
    if len(collected) == len(stimulus.required_channels):
        return FindingStatus.PASS, None
    return FindingStatus.INCONCLUSIVE, "channel_unavailable"


def _evaluate_l02(
    result: L02CredentialReplayObservationV1,
    counters: dict[_MetricKey, list[int]],
) -> tuple[FindingStatus, str | None]:
    observed = result.target_decision in {
        ObservedDecision.ALLOW,
        ObservedDecision.DENY,
        ObservedDecision.ERROR,
    }
    safe = (
        result.target_decision in {ObservedDecision.DENY, ObservedDecision.ERROR}
        and result.side_effect is ObservedSideEffect.NOT_OBSERVED
    )
    _add(
        counters,
        AgentAuthorityControlId.L02,
        "replay_rejection_rate",
        int(safe),
        int(observed),
    )
    if result.target_decision is ObservedDecision.ALLOW or (
        result.side_effect is ObservedSideEffect.OCCURRED
    ):
        return FindingStatus.FAIL, "replay_accepted"
    if safe:
        return FindingStatus.PASS, None
    return FindingStatus.INCONCLUSIVE, "replay_outcome_unobserved"


def _evaluate_l03(
    result: L03DirectPathBypassObservationV1,
    counters: dict[_MetricKey, list[int]],
) -> tuple[FindingStatus, str | None]:
    safe = (
        result.reachability is ReachabilityObservation.BLOCKED
        or result.target_decision in {ObservedDecision.DENY, ObservedDecision.ERROR}
    ) and result.side_effect is ObservedSideEffect.NOT_OBSERVED
    observed = (
        result.reachability is not ReachabilityObservation.UNKNOWN
        or result.target_decision
        in {ObservedDecision.ALLOW, ObservedDecision.DENY, ObservedDecision.ERROR}
    )
    _add(
        counters,
        AgentAuthorityControlId.L03,
        "direct_path_bypass_prevention_rate",
        int(safe),
        int(observed),
    )
    if (
        result.reachability is ReachabilityObservation.REACHABLE
        and result.target_decision is ObservedDecision.ALLOW
    ) or result.side_effect is ObservedSideEffect.OCCURRED:
        return FindingStatus.FAIL, "direct_path_bypass_succeeded"
    if safe:
        return FindingStatus.PASS, None
    return FindingStatus.INCONCLUSIVE, "direct_path_outcome_unknown"


def _evaluate_l04(
    result: L04NetworkPolicyObservationV1,
    counters: dict[_MetricKey, list[int]],
) -> tuple[FindingStatus, str | None]:
    safe = (
        result.connectivity is ConnectivityObservation.BLOCKED
        or result.target_decision in {ObservedDecision.DENY, ObservedDecision.ERROR}
    ) and result.side_effect is ObservedSideEffect.NOT_OBSERVED
    observed = (
        result.connectivity is not ConnectivityObservation.UNKNOWN
        or result.target_decision
        in {ObservedDecision.ALLOW, ObservedDecision.DENY, ObservedDecision.ERROR}
    )
    _add(
        counters,
        AgentAuthorityControlId.L04,
        "egress_policy_enforcement_rate",
        int(safe),
        int(observed),
    )
    if (
        result.connectivity is ConnectivityObservation.CONNECTED
        and result.target_decision is ObservedDecision.ALLOW
    ) or result.side_effect is ObservedSideEffect.OCCURRED:
        return FindingStatus.FAIL, "forbidden_network_path_succeeded"
    if safe:
        return FindingStatus.PASS, None
    return FindingStatus.INCONCLUSIVE, "network_outcome_unknown"


def _evaluate_l05(
    result: L05CriticalDependencyFailureObservationV1,
    counters: dict[_MetricKey, list[int]],
) -> tuple[FindingStatus, str | None]:
    confirmed = result.fault_confirmation is FaultConfirmation.CONFIRMED
    safe_count = sum(
        item.decision in {ObservedDecision.DENY, ObservedDecision.ERROR}
        and item.side_effect is ObservedSideEffect.NOT_OBSERVED
        for item in result.enforcement_outcomes
    )
    _add(
        counters,
        AgentAuthorityControlId.L05,
        "critical_dependency_fail_closed_rate",
        safe_count if confirmed else 0,
        len(result.enforcement_outcomes) if confirmed else 0,
    )
    if not confirmed:
        return FindingStatus.INCONCLUSIVE, "fault_unconfirmed"
    if any(
        item.decision is ObservedDecision.ALLOW
        or item.side_effect is ObservedSideEffect.OCCURRED
        for item in result.enforcement_outcomes
    ):
        return FindingStatus.FAIL, "dependency_failure_failed_open"
    if safe_count == len(result.enforcement_outcomes):
        return FindingStatus.PASS, None
    return FindingStatus.INCONCLUSIVE, "enforcement_outcome_unobserved"


def _evaluate_l06(
    stimulus: L06RevocationPropagationStimulusV1,
    result: L06RevocationPropagationObservationV1,
    plan: AgentAuthorityRunPlanV1,
    counters: dict[_MetricKey, list[int]],
) -> tuple[FindingStatus, str | None]:
    bound = next(
        item
        for item in plan.declared_bounds
        if item.bound_id == stimulus.declared_bound_id
    )
    acknowledgements = tuple(item.ack_elapsed_ns for item in result.point_results)
    within = sum(
        item is not None and item <= bound.value_ns for item in acknowledgements
    )
    _add(
        counters,
        AgentAuthorityControlId.L06,
        "revocation_bound_compliance_rate",
        within,
        len(stimulus.enforcement_point_ids),
    )
    post_bound = tuple(
        item for item in result.timed_attempts if item.sent_elapsed_ns > bound.value_ns
    )
    false_allows = sum(
        item.decision is ObservedDecision.ALLOW
        or item.side_effect is ObservedSideEffect.OCCURRED
        for item in post_bound
    )
    _add(
        counters,
        AgentAuthorityControlId.L06,
        "post_bound_false_allow_rate",
        false_allows,
        len(post_bound),
    )
    if false_allows or any(
        item is not None and item > bound.value_ns for item in acknowledgements
    ):
        return FindingStatus.FAIL, "revocation_bound_violated"
    if any(item is None for item in acknowledgements):
        return FindingStatus.INCONCLUSIVE, "revocation_acknowledgement_missing"
    if any(
        item.decision not in {ObservedDecision.DENY, ObservedDecision.ERROR}
        or item.side_effect is not ObservedSideEffect.NOT_OBSERVED
        for item in post_bound
    ):
        return FindingStatus.INCONCLUSIVE, "post_bound_outcome_unobserved"
    return FindingStatus.PASS, None


def _count_missing_metrics(
    stimulus: AgentAuthorityStimulusV1,
    counters: dict[_MetricKey, list[int]],
) -> None:
    payload = stimulus.payload
    if isinstance(payload, L01SecretExposureStimulusV1):
        _add(
            counters,
            AgentAuthorityControlId.L01,
            "channel_probe_coverage",
            0,
            len(payload.required_channels),
        )
        _add(counters, AgentAuthorityControlId.L01, "canary_exposure_rate", 0, 0)
    elif isinstance(payload, L02CredentialReplayStimulusV1):
        _add(counters, AgentAuthorityControlId.L02, "replay_rejection_rate", 0, 0)
    elif isinstance(payload, L03DirectPathBypassStimulusV1):
        _add(
            counters,
            AgentAuthorityControlId.L03,
            "direct_path_bypass_prevention_rate",
            0,
            0,
        )
    elif isinstance(payload, L04NetworkPolicyStimulusV1):
        _add(
            counters,
            AgentAuthorityControlId.L04,
            "egress_policy_enforcement_rate",
            0,
            0,
        )
    elif isinstance(payload, L05CriticalDependencyFailureStimulusV1):
        _add(
            counters,
            AgentAuthorityControlId.L05,
            "critical_dependency_fail_closed_rate",
            0,
            0,
        )
    else:
        revocation = payload
        _add(
            counters,
            AgentAuthorityControlId.L06,
            "revocation_bound_compliance_rate",
            0,
            len(revocation.enforcement_point_ids),
        )
        _add(
            counters,
            AgentAuthorityControlId.L06,
            "post_bound_false_allow_rate",
            0,
            0,
        )


def _add(
    counters: dict[_MetricKey, list[int]],
    control: AgentAuthorityControlId,
    name: str,
    numerator: int,
    denominator: int,
) -> None:
    values = counters[(control, name)]
    values[0] += numerator
    values[1] += denominator


def _build_metrics(
    counters: dict[_MetricKey, list[int]],
) -> tuple[AgentAuthoritySecurityMetricV1, ...]:
    nonempty = {
        "channel_probe_coverage",
        "revocation_bound_compliance_rate",
    }
    denominator_meanings = {
        "channel_probe_coverage": "required channel scans",
        "canary_exposure_rate": "collected channel scans",
        "replay_rejection_rate": "replay attempts with an observed target decision",
        "direct_path_bypass_prevention_rate": (
            "bypass attempts with reachability or decision evidence"
        ),
        "egress_policy_enforcement_rate": (
            "network-policy attempts with connectivity or decision evidence"
        ),
        "critical_dependency_fail_closed_rate": (
            "enforcement-point outcomes under a confirmed dependency fault"
        ),
        "revocation_bound_compliance_rate": "declared enforcement points",
        "post_bound_false_allow_rate": "validated post-bound attempts",
    }
    metrics = []
    for (control, name), (numerator, denominator) in sorted(
        counters.items(), key=lambda item: (item[0][0].value, item[0][1])
    ):
        behaviour = (
            MetricEmptyBehaviour.NONEMPTY
            if name in nonempty
            else MetricEmptyBehaviour.NULL_IF_EMPTY
        )
        metrics.append(
            AgentAuthoritySecurityMetricV1(
                control_id=control,
                name=name,
                value=None if denominator == 0 else numerator / denominator,
                numerator=numerator,
                denominator=denominator,
                support=denominator,
                denominator_meaning=denominator_meanings[name],
                empty_behaviour=behaviour,
            )
        )
    return tuple(metrics)


def _build_stage_reports(
    plan: AgentAuthorityRunPlanV1,
    observations: AgentAuthorityRunObservationsV1,
) -> tuple[OperationalStageReportV1, ...]:
    gaps = {item.stage_id: item for item in observations.operational_coverage_gaps}
    rows: dict[str, list[OperationalMeasurementV1]] = defaultdict(list)
    for item in observations.operational_measurements:
        rows[item.stage_id].append(item)
    reports = []
    for stage in plan.operational_coverage.performance_stages:
        gap = gaps.get(stage.stage_id)
        if gap is not None:
            reports.append(
                OperationalStageReportV1(
                    stage_id=stage.stage_id,
                    status=OperationalStageStatus.GAP,
                    limitation=gap.reason,
                )
            )
            continue
        measurements = rows[stage.stage_id]
        latency = tuple(
            (item.payload.statistic, item.payload.value_ns)
            for item in measurements
            if isinstance(item.payload, LatencyMeasurementV1)
        )
        failure = next(
            item.payload
            for item in measurements
            if isinstance(item.payload, FailureRateMeasurementV1)
        )
        throughput = next(
            item.payload
            for item in measurements
            if isinstance(item.payload, ThroughputMeasurementV1)
        )
        reports.append(
            OperationalStageReportV1(
                stage_id=stage.stage_id,
                status=OperationalStageStatus.COMPLETE,
                latency_ns=latency,
                failure_rate=OperationalRatioV1(
                    numerator=failure.failed_count,
                    denominator=failure.total_count,
                    numerator_meaning="failed requests",
                    denominator_meaning="attempted requests",
                ),
                throughput=OperationalRatioV1(
                    numerator=throughput.completed_count,
                    denominator=throughput.duration_ns,
                    numerator_meaning="completed requests",
                    denominator_meaning="measurement duration in nanoseconds",
                ),
            )
        )
    return tuple(reports)


def _build_added_latency(
    plan: AgentAuthorityRunPlanV1,
    reports: tuple[OperationalStageReportV1, ...],
) -> tuple[AddedLatencyMeasurementV1, ...]:
    report_index = {item.stage_id: item for item in reports}
    added = []
    for stage in plan.operational_coverage.performance_stages:
        if stage.role is not PerformanceStageRole.SUT:
            continue
        current = report_index[stage.stage_id]
        baseline = report_index[stage.baseline_stage_id or ""]
        if (
            current.status is OperationalStageStatus.GAP
            or baseline.status is OperationalStageStatus.GAP
        ):
            continue
        current_values = dict(current.latency_ns)
        baseline_values = dict(baseline.latency_ns)
        for statistic in stage.statistics:
            added.append(
                AddedLatencyMeasurementV1(
                    sut_stage_id=stage.stage_id,
                    baseline_stage_id=stage.baseline_stage_id or "",
                    statistic=statistic,
                    added_latency_ns=(
                        current_values[statistic] - baseline_values[statistic]
                    ),
                )
            )
    return tuple(added)


def _observation_evidence_refs(
    observation: AgentAuthorityObservationV1,
) -> tuple[str, ...]:
    refs = set(observation.evidence_handle_refs)
    payload = observation.payload
    if isinstance(payload, L01SecretExposureObservationV1):
        refs |= {item.evidence_handle_ref for item in payload.channel_scans}
    elif isinstance(payload, L02CredentialReplayObservationV1):
        refs |= set(payload.target_evidence_refs)
    elif isinstance(
        payload,
        L03DirectPathBypassObservationV1 | L04NetworkPolicyObservationV1,
    ):
        refs |= set(payload.network_evidence_refs) | set(payload.target_evidence_refs)
    elif isinstance(payload, L05CriticalDependencyFailureObservationV1):
        for outcome in payload.enforcement_outcomes:
            refs |= set(outcome.evidence_refs)
    else:
        for point in payload.point_results:
            refs |= set(point.evidence_refs)
        for attempt in payload.timed_attempts:
            refs |= set(attempt.evidence_refs)
    return tuple(sorted(refs))


__all__ = ["evaluate_agent_authority_lab", "validate_agent_authority_truth"]
