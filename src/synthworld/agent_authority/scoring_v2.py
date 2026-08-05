"""Agent-authority scoring for revocation-relative observation v2."""

from __future__ import annotations

from collections import defaultdict
from typing import cast

from synthworld.agent_authority.cases import (
    AgentAuthorityObservationV1,
    AgentAuthorityStimulusSetV1,
    AgentAuthorityStimulusV1,
    L06RevocationPropagationStimulusV1,
)
from synthworld.agent_authority.common import (
    AgentAuthorityControlId,
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
    AgentAuthorityStimulusTruthV1,
    CompatibilityCoverageReportV1,
    StimulusFindingV1,
    stimulus_control,
)
from synthworld.agent_authority.models_v2 import (
    AgentAuthorityObservationV2,
    AgentAuthorityRunObservationsV2,
    L06RevocationPropagationObservationV2,
    validate_observation_references_v2,
)
from synthworld.agent_authority.scoring import (
    _add,
    _build_added_latency,
    _build_metrics,
    _build_stage_reports,
    _count_missing_metrics,
    _evaluate_stimulus,
    _observation_evidence_refs,
    validate_agent_authority_truth,
)
from synthworld.assurance.models_v2 import SystemComponentProvenanceV2

_MetricKey = tuple[AgentAuthorityControlId, str]


def evaluate_agent_authority_lab_v2(
    plan: AgentAuthorityRunPlanV1,
    stimuli: AgentAuthorityStimulusSetV1,
    observations: AgentAuthorityRunObservationsV2,
    truth: AgentAuthorityLabTruthV1,
    systems: tuple[SystemComponentProvenanceV2, ...],
) -> AgentAuthorityLabReportV1:
    """Evaluate V2 observations without changing the frozen report contract."""

    validate_observation_references_v2(plan, stimuli, observations, systems)
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
        findings.append(
            _evaluate_stimulus_v2(
                stimulus,
                observation,
                expected,
                plan,
                evidence_index,
                counters,
            )
        )

    v1_shape = cast(AgentAuthorityRunObservationsV1, observations)
    stage_reports = _build_stage_reports(plan, v1_shape)
    return AgentAuthorityLabReportV1(
        run_id=plan.run_id,
        findings=tuple(findings),
        security_metrics=_build_metrics(counters),
        operational_stages=stage_reports,
        added_latency=_build_added_latency(plan, stage_reports),
        compatibility=tuple(
            CompatibilityCoverageReportV1(
                coverage_key=item.coverage_key,
                status=item.status,
                nondominated_minima=item.nondominated_minima,
                limitation=item.limitation,
            )
            for item in observations.target_compatibility
        ),
        limitations=observations.limitations,
    )


def _evaluate_stimulus_v2(
    stimulus: AgentAuthorityStimulusV1,
    observation: AgentAuthorityObservationV2,
    truth: AgentAuthorityStimulusTruthV1,
    plan: AgentAuthorityRunPlanV1,
    evidence_index: dict[str, EvidenceHandleV1],
    counters: dict[_MetricKey, list[int]],
) -> StimulusFindingV1:
    if not isinstance(stimulus.payload, L06RevocationPropagationStimulusV1):
        legacy = AgentAuthorityObservationV1.model_validate(
            observation.model_dump(mode="json")
        )
        # V1's evaluator is the normative implementation for unchanged variants.
        return _evaluate_stimulus(
            stimulus,
            legacy,
            truth,
            plan,
            evidence_index,
            counters,
        )

    # Reference validation above has already paired this L06 stimulus with V2 payload.
    payload = cast(L06RevocationPropagationObservationV2, observation.payload)
    status, code = _evaluate_l06_v2(stimulus.payload, payload, plan, counters)
    evidence_refs = _observation_evidence_refs(
        cast(AgentAuthorityObservationV1, observation)
    )
    observed_kinds = {
        evidence_index[item].kind for item in evidence_refs if item in evidence_index
    }
    if (
        status is FindingStatus.PASS
        and not set(truth.payload.required_evidence_kinds) <= observed_kinds
    ):
        status, code = FindingStatus.INCONCLUSIVE, "required_evidence_missing"
    return StimulusFindingV1(
        stimulus_id=observation.stimulus_id,
        control_id=AgentAuthorityControlId.L06,
        status=status,
        failure_code=code,
        evidence_refs=evidence_refs,
    )


def _evaluate_l06_v2(
    stimulus: L06RevocationPropagationStimulusV1,
    result: L06RevocationPropagationObservationV2,
    plan: AgentAuthorityRunPlanV1,
    counters: dict[_MetricKey, list[int]],
) -> tuple[FindingStatus, str | None]:
    bound = next(
        item
        for item in plan.declared_bounds
        if item.bound_id == stimulus.declared_bound_id
    )
    acknowledgements = tuple(item.ack_offset_ns for item in result.point_results)
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
        item for item in result.timed_attempts if item.sent_offset_ns > bound.value_ns
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


__all__ = ["evaluate_agent_authority_lab_v2"]
