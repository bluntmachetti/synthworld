"""Mutation tests for every closed agent-authority model invariant."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from synthworld.agent_authority.cases import (
    AgentAuthorityStimulusSetV1,
    AgentAuthorityStimulusV1,
    ChannelScanV1,
    EnforcementOutcomeV1,
    EvidenceChannel,
    ExtractionVector,
    L01SecretExposureObservationV1,
    L02CredentialReplayStimulusV1,
    L05CriticalDependencyFailureObservationV1,
    L06RevocationPropagationObservationV1,
    L06RevocationPropagationStimulusV1,
    ReplayKind,
    RevocationPointResultV1,
    TimedAttemptV1,
)
from synthworld.agent_authority.common import (
    AgentAuthorityControlId,
    AttributionKind,
    BoundMetric,
    BoundUnit,
    CollectionStatus,
    ControlCoverageEntryV1,
    ControlLayer,
    CoverageDisposition,
    DeclaredBoundV1,
    DeploymentPattern,
    EvidenceHandleV1,
    EvidenceKind,
    FindingStatus,
    ObservationAttributionV1,
    ObservedDecision,
    ObservedSideEffect,
    RedactionStatus,
    RunLayer,
    SyntheticSecretHandleV1,
    canonical_unique,
    require_utc,
    unique,
)
from synthworld.agent_authority.models import (
    AgentAuthorityLabTruthV1,
    AgentAuthorityProductInputV1,
    AgentAuthorityRunPlanV1,
    AgentAuthoritySecurityMetricV1,
    ConfigurationReviewStatus,
    CoverageLimitationKind,
    CoverageLimitationV1,
    MetricEmptyBehaviour,
    OperationalRatioV1,
    OperationalStageReportV1,
    OperationalStageStatus,
    ProtocolConflictV1,
    RepresentativeConfigurationReviewV1,
    StimulusFindingV1,
    validate_case_observation,
    validate_compatibility_inventory,
    validate_dependency_results,
    validate_observation_references,
    validate_operational_inventory,
    validate_revocation_observation,
    validate_run_plan_references,
)
from synthworld.agent_authority.operational import (
    ArrivalModel,
    CandidateProbeOutcome,
    CapabilityProbeResultV1,
    CredentialKind,
    FailureRateMeasurementV1,
    LatencyMeasurementV1,
    LatencyStatistic,
    LoadProfileV1,
    OperationalCoverageGapV1,
    PerformanceStageRole,
    RationalValueV1,
    SenderConstraint,
    ThroughputMeasurementV1,
    capability_no_broader,
    capability_strictly_dominates,
    nondominated_candidate_ids,
)
from synthworld.agent_authority.reference import (
    reference_observations,
    reference_plan,
    reference_stimuli,
    reference_systems,
    reference_truth,
)
from synthworld.assurance.models_v2 import DigestV2


def _document(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")


def _reject(model: BaseModel, match: str, **updates: object) -> None:
    document = _document(model)
    document.update(updates)
    with pytest.raises(ValidationError, match=match):
        type(model).model_validate(document)


def _stimulus_payload(index: int) -> BaseModel:
    return reference_stimuli().stimuli[index].payload


def _observation_payload(index: int) -> BaseModel:
    return reference_observations().observations[index].payload


def test_stimulus_variant_invariants_reject_noncanonical_inputs() -> None:
    l01 = _stimulus_payload(0)
    _reject(
        l01,
        "sorted and unique",
        extraction_vectors=(ExtractionVector.PROMPT, ExtractionVector.PROMPT),
    )
    l02 = _stimulus_payload(1)
    _reject(l02, "distinct senders", replay_sender_handle="sender:original")
    _reject(
        l02,
        "distinct audiences",
        replay_kind=ReplayKind.WRONG_AUDIENCE,
        attempted_audience_handle="audience:target",
    )
    l03 = _stimulus_payload(2)
    _reject(
        l03,
        "nonblank",
        sanctioned_path_component_ids=("", "component-target"),
    )
    _reject(
        l03,
        "unique",
        sanctioned_path_component_ids=("component-gateway", "component-gateway"),
    )
    l05 = _stimulus_payload(4)
    _reject(l05, "follow injection", recovery_tick=5)
    l06 = _stimulus_payload(5)
    _reject(l06, "sorted, and unique", traffic_ticks=(8, 7))
    _reject(l06, "post-revocation", traffic_ticks=(6,))
    duplicated_credentials = (
        SyntheticSecretHandleV1(handle="synthetic-secret:credential-1"),
        SyntheticSecretHandleV1(handle="synthetic-secret:credential-1"),
    )
    _reject(
        l06,
        "issued credential handles",
        issued_credential_handles=duplicated_credentials,
    )
    with pytest.raises(ValidationError, match="synthetic-secret"):
        SyntheticSecretHandleV1(handle="real-password")


def test_stimulus_envelope_order_and_expiry_are_structural() -> None:
    stimuli = reference_stimuli()
    with pytest.raises(ValidationError, match="ordered by schedule"):
        AgentAuthorityStimulusSetV1(stimuli=tuple(reversed(stimuli.stimuli)))
    with pytest.raises(ValidationError, match="stimulus identifiers"):
        AgentAuthorityStimulusSetV1(stimuli=(stimuli.stimuli[0], stimuli.stimuli[0]))
    payload = _document(stimuli.stimuli[1].payload)
    payload["replay_kind"] = ReplayKind.AFTER_EXPIRY
    payload["expiry_tick"] = 2
    with pytest.raises(ValidationError, match="scheduled after expiry"):
        AgentAuthorityStimulusV1(
            stimulus_id="after-expiry",
            schedule_tick=2,
            payload=L02CredentialReplayStimulusV1.model_validate(payload),
        )
    assert (
        AgentAuthorityProductInputV1(
            run_plan_digest=DigestV2(value="1" * 64),
            stimuli=stimuli.stimuli,
            stimulus_digest=DigestV2(value="2" * 64),
        ).schema_version
        == "1.0.0"
    )


def test_observation_variant_order_timing_and_uniqueness_invariants() -> None:
    scan = ChannelScanV1(
        channel=EvidenceChannel.CONTEXT,
        collection_status=CollectionStatus.COLLECTED,
        canary_match=False,
        evidence_handle_ref="evidence:log",
    )
    existing = _observation_payload(0)
    assert isinstance(existing, L01SecretExposureObservationV1)
    with pytest.raises(ValidationError, match="canonically ordered"):
        L01SecretExposureObservationV1(channel_scans=(*existing.channel_scans, scan))
    with pytest.raises(ValidationError, match="channel scan channels"):
        L01SecretExposureObservationV1(
            channel_scans=(existing.channel_scans[0], existing.channel_scans[0])
        )

    l05 = _observation_payload(4)
    assert isinstance(l05, L05CriticalDependencyFailureObservationV1)
    second = EnforcementOutcomeV1(
        component_id="component-alpha",
        decision=ObservedDecision.DENY,
        side_effect=ObservedSideEffect.NOT_OBSERVED,
    )
    _reject(
        l05,
        "canonically ordered",
        enforcement_outcomes=(*l05.enforcement_outcomes, second),
    )
    _reject(
        l05,
        "outcome components",
        enforcement_outcomes=(l05.enforcement_outcomes[0],) * 2,
    )

    with pytest.raises(ValidationError, match="cannot precede send"):
        TimedAttemptV1(
            enforcement_point_id="point",
            credential_or_child_handle="credential",
            sent_elapsed_ns=2,
            completed_elapsed_ns=1,
            decision=ObservedDecision.DENY,
            side_effect=ObservedSideEffect.NOT_OBSERVED,
        )
    l06 = _observation_payload(5)
    assert isinstance(l06, L06RevocationPropagationObservationV1)
    point = RevocationPointResultV1(component_id="component-alpha")
    _reject(l06, "point results must be", point_results=(*l06.point_results, point))
    _reject(
        l06,
        "timed attempts must be unique",
        timed_attempts=(l06.timed_attempts[0],) * 2,
    )
    later = l06.timed_attempts[0].model_copy(update={"sent_elapsed_ns": 1})
    _reject(
        l06,
        "timed attempts must be canonically ordered",
        timed_attempts=(l06.timed_attempts[0], later),
    )


def test_shared_coverage_bound_attribution_and_time_helpers() -> None:
    selected = ControlCoverageEntryV1(
        control_id=AgentAuthorityControlId.L01,
        catalogue_layer=ControlLayer.LAB,
        disposition=CoverageDisposition.SELECTED,
    )
    _reject(selected, "layer differs", catalogue_layer=ControlLayer.CORE)
    _reject(selected, "forbid", applicability_rationale="not really selected")
    not_applicable = selected.model_copy(
        update={"disposition": CoverageDisposition.NOT_APPLICABLE}
    )
    with pytest.raises(ValidationError, match="require a rationale"):
        ControlCoverageEntryV1.model_validate(_document(not_applicable))
    with pytest.raises(ValidationError):
        DeclaredBoundV1(
            bound_id="deferred",
            control_id=AgentAuthorityControlId.L01,  # type: ignore[arg-type]
            metric=BoundMetric.DECISION_LATENCY,  # type: ignore[arg-type]
            value=1,
            unit=BoundUnit.NS,
        )
    assert {
        unit: DeclaredBoundV1(
            bound_id=unit.value,
            control_id=AgentAuthorityControlId.L06,
            metric=BoundMetric.REVOCATION_PROPAGATION,
            value=1,
            unit=unit,
        ).value_ns
        for unit in BoundUnit
    } == {
        BoundUnit.NS: 1,
        BoundUnit.US: 1_000,
        BoundUnit.MS: 1_000_000,
        BoundUnit.S: 1_000_000_000,
    }

    assert ObservationAttributionV1(
        kind=AttributionKind.MULTIPLE,
        component_ids=("a", "b"),
    ).component_ids == ("a", "b")
    assert (
        ObservationAttributionV1(
            kind=AttributionKind.AMBIGUOUS,
            reason="no component evidence",
        ).component_ids
        == ()
    )
    assert (
        ObservationAttributionV1(
            kind=AttributionKind.AMBIGUOUS,
            component_ids=("a", "b"),
            reason="two candidates",
        ).reason
        == "two candidates"
    )
    assert ObservationAttributionV1(kind=AttributionKind.UNOBSERVED).reason is None
    with pytest.raises(ValidationError, match="sorted and unique"):
        ObservationAttributionV1(
            kind=AttributionKind.MULTIPLE,
            component_ids=("b", "a"),
        )
    with pytest.raises(ValueError, match="nonblank"):
        canonical_unique(("",), "test values")
    with pytest.raises(ValueError, match="sorted and unique"):
        canonical_unique(("b", "a"), "test values")
    with pytest.raises(ValueError, match="unique"):
        unique(("same", "same"), "test values")
    with pytest.raises(ValueError, match="UTC"):
        require_utc(datetime(2026, 8, 4))
    with pytest.raises(ValueError, match="UTC"):
        require_utc(datetime(2026, 8, 4, tzinfo=timezone(timedelta(hours=1))))


def test_load_profiles_stages_and_operational_coverage_are_predeclared() -> None:
    fixed = LoadProfileV1(
        request_count=10,
        max_concurrency=1,
        arrival_model=ArrivalModel.FIXED_RATE,
        rate_numerator=1,
        rate_denominator=2,
    )
    assert fixed.rate_denominator == 2
    _reject(fixed, "reduced rational", rate_numerator=2, rate_denominator=4)
    _reject(fixed, "rational rate", rate_numerator=None, rate_denominator=None)
    closed = LoadProfileV1(
        request_count=10,
        max_concurrency=1,
        arrival_model=ArrivalModel.CLOSED_LOOP,
    )
    _reject(closed, "forbids a fixed rate", rate_numerator=1, rate_denominator=1)

    coverage = reference_plan().operational_coverage
    baseline = coverage.performance_stages[0]
    _reject(
        baseline,
        "statistics must be sorted",
        statistics=(LatencyStatistic.P95, LatencyStatistic.P50),
    )
    _reject(baseline, "baseline stage forbids", baseline_stage_id="another")
    sut = next(
        item
        for item in coverage.performance_stages
        if item.role is PerformanceStageRole.SUT
    )
    _reject(sut, "requires a baseline", baseline_stage_id=None)
    _reject(coverage, "stage identifiers", performance_stages=(baseline, baseline))
    _reject(
        coverage,
        "canonically ordered",
        performance_stages=tuple(reversed(coverage.performance_stages)),
    )
    _reject(
        coverage,
        "targets must be canonically ordered",
        compatibility_targets=tuple(reversed(coverage.compatibility_targets)),
    )
    missing_baseline = sut.model_copy(update={"baseline_stage_id": "missing"})
    _reject(
        coverage,
        "declared baseline",
        performance_stages=tuple(
            missing_baseline if item.stage_id == sut.stage_id else item
            for item in coverage.performance_stages
        ),
    )
    mismatched = sut.model_copy(update={"target_handle": "different"})
    _reject(
        coverage,
        "comparable",
        performance_stages=tuple(
            mismatched if item.stage_id == sut.stage_id else item
            for item in coverage.performance_stages
        ),
    )


def test_compatibility_target_candidate_and_status_contracts() -> None:
    target = reference_plan().operational_coverage.compatibility_targets[0]
    _reject(
        target,
        "only minting/proxy",
        applicable_patterns=(DeploymentPattern.STATIC_BEARER,),
    )
    _reject(
        target,
        "patterns must be sorted",
        applicable_patterns=(
            DeploymentPattern.SHORT_LIVED_MINTING,
            DeploymentPattern.PROXY_INJECTION,
        ),
    )
    first = target.probe_candidates[0]
    _reject(
        target,
        "candidate identifiers",
        probe_candidates=(first, first),
    )
    _reject(
        target,
        "canonically ordered",
        probe_candidates=tuple(reversed(target.probe_candidates)),
    )
    for field, value, match in (
        ("actions", ("action:unknown",), "actions exceed"),
        ("scopes", ("scope:unknown",), "scopes exceed"),
        ("audiences", ("audience:unknown",), "audiences exceed"),
    ):
        candidate = first.model_copy(update={field: value})
        _reject(target, match, probe_candidates=(candidate, target.probe_candidates[1]))

    measured = reference_observations().target_compatibility[0]
    _reject(
        measured,
        "candidate results must be canonically ordered",
        candidate_results=tuple(reversed(measured.candidate_results)),
    )
    _reject(measured, "obtained candidate", candidate_results=())
    failed = measured.candidate_results[0].model_copy(
        update={
            "outcome": CandidateProbeOutcome.FAILED,
            "reason": "failure",
        }
    )
    _reject(
        measured,
        "terminal results",
        candidate_results=(failed, measured.candidate_results[1]),
    )
    _reject(measured, "minima and no limitation", nondominated_minima=())
    unsupported = reference_observations().target_compatibility[1]
    _reject(unsupported, "rejected candidates", evidence_refs=())
    incomplete = reference_observations().target_compatibility[2]
    obtained = tuple(
        CapabilityProbeResultV1(
            candidate_id=item.candidate_id,
            outcome=CandidateProbeOutcome.OBTAINED,
        )
        for item in incomplete.candidate_results
    )
    _reject(incomplete, "failed/unobserved", candidate_results=obtained)
    not_attempted = reference_observations().target_compatibility[3]
    _reject(not_attempted, "carries only", candidate_results=(obtained[0],))
    with pytest.raises(ValidationError, match="require a reason"):
        CapabilityProbeResultV1(
            candidate_id="candidate",
            outcome=CandidateProbeOutcome.REJECTED,
        )
    with pytest.raises(ValidationError, match="forbid"):
        CapabilityProbeResultV1(
            candidate_id="candidate",
            outcome=CandidateProbeOutcome.OBTAINED,
            reason="unexpected",
        )


def test_capability_partial_order_covers_incomparable_dimensions() -> None:
    target = reference_plan().operational_coverage.compatibility_targets[0]
    narrow, wide = target.probe_candidates
    assert capability_no_broader(narrow, wide)
    assert capability_strictly_dominates(narrow, wide)
    assert not capability_strictly_dominates(narrow, narrow)
    assert not capability_no_broader(wide, narrow)
    for field, update in (
        ("credential_kind", CredentialKind.DPOP),
        ("actions", ("action:unknown",)),
        ("scopes", ("scope:unknown",)),
        ("audiences", ("audience:unknown",)),
        ("sender_constraint", SenderConstraint.UNBOUND),
        ("maximum_lifetime_ns", None),
    ):
        changed = narrow.model_copy(update={field: update})
        assert not capability_no_broader(changed, narrow)
    finite_other = narrow.model_copy(update={"maximum_lifetime_ns": 500_000_000})
    assert not capability_no_broader(narrow, finite_other)
    assert nondominated_candidate_ids(
        target.probe_candidates,
        {narrow.candidate_id, wide.candidate_id},
    ) == (narrow.candidate_id,)
    different_kind = wide.model_copy(
        update={
            "candidate_id": "candidate-dpop",
            "credential_kind": CredentialKind.DPOP,
        }
    )
    assert nondominated_candidate_ids(
        (*target.probe_candidates, different_kind),
        {narrow.candidate_id, wide.candidate_id, different_kind.candidate_id},
    ) == ("candidate-dpop", narrow.candidate_id)

    middle = wide.model_copy(
        update={
            "candidate_id": "candidate-middle",
            "scopes": ("scope:one",),
            "maximum_lifetime_ns": 2_000_000_000,
        }
    )
    assert capability_strictly_dominates(narrow, middle)
    assert capability_strictly_dominates(middle, wide)
    assert capability_strictly_dominates(narrow, wide)

    equivalent = narrow.model_copy(update={"candidate_id": "candidate-equivalent"})
    assert capability_no_broader(equivalent, narrow)
    assert not capability_strictly_dominates(equivalent, narrow)
    assert nondominated_candidate_ids(
        (equivalent, narrow),
        {equivalent.candidate_id, narrow.candidate_id},
    ) == ("candidate-equivalent", "candidate-narrow")


def test_measurement_and_report_value_models_reject_inconsistent_counts() -> None:
    with pytest.raises(ValidationError, match="cannot exceed"):
        FailureRateMeasurementV1(failed_count=2, total_count=1)
    assert ThroughputMeasurementV1(completed_count=1, duration_ns=2).duration_ns == 2
    with pytest.raises(ValidationError, match="reduced"):
        RationalValueV1(
            numerator=2,
            denominator=4,
            numerator_meaning="items",
            denominator_meaning="total",
        )
    assert (
        RationalValueV1(
            numerator=-1,
            denominator=2,
            numerator_meaning="delta",
            denominator_meaning="unit",
        ).numerator
        == -1
    )
    with pytest.raises(ValidationError, match="every measure"):
        OperationalStageReportV1(
            stage_id="stage",
            status=OperationalStageStatus.COMPLETE,
        )
    with pytest.raises(ValidationError, match="only its limitation"):
        OperationalStageReportV1(
            stage_id="stage",
            status=OperationalStageStatus.GAP,
        )
    assert (
        OperationalRatioV1(
            numerator=1,
            denominator=2,
            numerator_meaning="failed",
            denominator_meaning="attempted",
        ).denominator
        == 2
    )


def test_run_plan_internal_invariants_are_closed() -> None:
    plan = reference_plan()
    _reject(
        plan,
        "patterns must be sorted",
        deployment_patterns=tuple(reversed(plan.deployment_patterns)),
    )
    _reject(
        plan,
        "authority-path components",
        authority_path_component_ids=("component-gateway", "component-gateway"),
    )
    _reject(
        plan,
        "must be nonblank",
        authority_path_component_ids=("", "component-target"),
    )
    _reject(plan, "timestamp must be UTC", planned_at=datetime(2026, 8, 4))
    _reject(plan, "every protocol control", control_coverage=plan.control_coverage[:-1])
    _reject(
        plan,
        "bound identifiers",
        declared_bounds=(plan.declared_bounds[0], plan.declared_bounds[0]),
    )
    later_bound = plan.declared_bounds[0].model_copy(update={"bound_id": "a-bound"})
    _reject(
        plan,
        "bounds must be canonically ordered",
        declared_bounds=(plan.declared_bounds[0], later_bound),
    )
    core = plan.model_copy(update={"run_layer": RunLayer.CORE})
    with pytest.raises(ValidationError, match="core run"):
        AgentAuthorityRunPlanV1.model_validate(_document(core))
    no_stages = plan.operational_coverage.model_copy(update={"performance_stages": ()})
    _reject(plan, "L07 selection", operational_coverage=no_stages)
    no_targets = plan.operational_coverage.model_copy(
        update={"compatibility_targets": ()}
    )
    _reject(plan, "L08 selection", operational_coverage=no_targets)
    _reject(
        plan,
        "inconsistent with the deployment",
        deployment_patterns=(DeploymentPattern.STATIC_BEARER,),
    )
    conflicts = (
        ProtocolConflictV1(topic="z-topic", disposition="disclosed"),
        ProtocolConflictV1(topic="a-topic", disposition="disclosed"),
    )
    _reject(plan, "conflicts must be canonically ordered", conflicts=conflicts)
    _reject(plan, "conflict topics", conflicts=(conflicts[0], conflicts[0]))


def test_configuration_review_metric_finding_and_truth_invariants() -> None:
    reviewed = RepresentativeConfigurationReviewV1(
        status=ConfigurationReviewStatus.REVIEWED,
        reviewer_id="reviewer",
        evidence_refs=("evidence:review",),
    )
    assert reviewed.limitation is None
    _reject(reviewed, "forbids a limitation", limitation="unexpected")
    _reject(reviewed, "requires reviewer", reviewer_id=None)
    not_reviewed = RepresentativeConfigurationReviewV1(
        status=ConfigurationReviewStatus.NOT_REVIEWED,
        limitation="review did not occur",
    )
    _reject(not_reviewed, "forbids review", reviewer_id="reviewer")
    _reject(not_reviewed, "requires a limitation", limitation=None)

    metric = AgentAuthoritySecurityMetricV1(
        control_id=AgentAuthorityControlId.L02,
        name="test_rate",
        value=0.5,
        numerator=1,
        denominator=2,
        support=2,
        denominator_meaning="tests",
        empty_behaviour=MetricEmptyBehaviour.NULL_IF_EMPTY,
    )
    _reject(metric, "support cannot exceed", support=3)
    _reject(metric, "must equal", value=0.25)
    _reject(
        metric,
        "empty metric",
        numerator=0,
        denominator=0,
        support=0,
        value=None,
        empty_behaviour=MetricEmptyBehaviour.NONEMPTY,
    )
    assert (
        AgentAuthoritySecurityMetricV1(
            control_id=AgentAuthorityControlId.L02,
            name="empty",
            value=None,
            numerator=0,
            denominator=0,
            support=0,
            denominator_meaning="observed tests",
            empty_behaviour=MetricEmptyBehaviour.NULL_IF_EMPTY,
        ).value
        is None
    )
    passing = StimulusFindingV1(
        stimulus_id="stimulus",
        control_id=AgentAuthorityControlId.L01,
        status=FindingStatus.PASS,
    )
    _reject(passing, "forbid", failure_code="unexpected")
    _reject(passing, "require", status=FindingStatus.FAIL)

    truth = reference_truth()
    with pytest.raises(ValidationError, match="truth stimulus identifiers"):
        AgentAuthorityLabTruthV1(
            run_id=truth.run_id,
            stimuli=(truth.stimuli[0], truth.stimuli[0]),
        )
    l01_truth = truth.stimuli[0].payload
    _reject(
        l01_truth,
        "evidence kinds",
        required_evidence_kinds=(EvidenceKind.TRACE, EvidenceKind.LOG),
    )
    _reject(
        l01_truth,
        "channels must be sorted",
        required_channels=(EvidenceChannel.LOG, EvidenceChannel.CONTEXT),
    )


def test_top_level_observation_inventory_is_canonical() -> None:
    observations = reference_observations()
    _reject(
        observations,
        "observation stimulus identifiers",
        observations=(observations.observations[0],) * 2,
    )
    _reject(
        observations,
        "canonically ordered",
        observations=tuple(reversed(observations.observations)),
    )
    _reject(
        observations,
        "run limitations",
        limitations=("z", "a"),
    )
    limitation = CoverageLimitationV1(
        control_id=AgentAuthorityControlId.L01,
        kind=CoverageLimitationKind.CAPPED,
        reason="cap",
    )
    _reject(
        observations,
        "unique per control",
        coverage_limitations=(limitation, limitation),
    )
    skipped = limitation.model_copy(update={"kind": CoverageLimitationKind.SKIPPED})
    _reject(
        observations,
        "limitations must be canonically ordered",
        coverage_limitations=(skipped, limitation),
    )
    first_measurement = observations.operational_measurements[0]
    _reject(
        observations,
        "measurements must be unique",
        operational_measurements=(first_measurement, first_measurement),
    )
    _reject(
        observations,
        "measurements must be canonically ordered",
        operational_measurements=tuple(reversed(observations.operational_measurements)),
    )


def test_cross_artifact_reference_failures_are_distinct() -> None:
    plan = reference_plan()
    stimuli = reference_stimuli()
    observations = reference_observations()
    systems = reference_systems()
    duplicate_systems = (*systems, systems[0])
    with pytest.raises(ValueError, match="unique component"):
        validate_run_plan_references(plan, stimuli, duplicate_systems)

    l05 = stimuli.stimuli[4]
    bad_l05_payload = l05.payload.model_copy(
        update={"dependency_component_id": "component-target"}
    )
    bad_l05 = l05.model_copy(update={"payload": bad_l05_payload})
    bad_stimuli = stimuli.model_copy(
        update={"stimuli": (*stimuli.stimuli[:4], bad_l05, stimuli.stimuli[5])}
    )
    with pytest.raises(ValueError, match="not an authority dependency"):
        validate_run_plan_references(plan, bad_stimuli, systems)

    l03 = stimuli.stimuli[2]
    unresolved_l03 = l03.model_copy(
        update={
            "payload": l03.payload.model_copy(
                update={
                    "sanctioned_path_component_ids": (
                        "component-gateway",
                        "component-unknown",
                    )
                }
            )
        }
    )
    with pytest.raises(ValueError, match="stimulus contains an unresolved"):
        validate_run_plan_references(
            plan,
            stimuli.model_copy(
                update={
                    "stimuli": (
                        *stimuli.stimuli[:2],
                        unresolved_l03,
                        *stimuli.stimuli[3:],
                    )
                }
            ),
            systems,
        )

    l06 = stimuli.stimuli[5]
    bad_l06 = l06.model_copy(
        update={
            "payload": l06.payload.model_copy(update={"declared_bound_id": "missing"})
        }
    )
    bad_stimuli = stimuli.model_copy(
        update={"stimuli": (*stimuli.stimuli[:5], bad_l06)}
    )
    with pytest.raises(ValueError, match="does not resolve"):
        validate_run_plan_references(plan, bad_stimuli, systems)

    wrong_selected = tuple(
        item.model_copy(update={"disposition": CoverageDisposition.NOT_APPLICABLE})
        if item.control_id is AgentAuthorityControlId.L01
        else item
        for item in plan.control_coverage
    )
    bad_plan = plan.model_copy(update={"control_coverage": wrong_selected})
    with pytest.raises(ValueError, match="stimulus denominator"):
        validate_run_plan_references(bad_plan, stimuli, systems)

    with pytest.raises(ValueError, match="run identifier"):
        validate_observation_references(
            plan,
            stimuli,
            observations.model_copy(update={"run_id": "different"}),
            systems,
        )
    unknown_observation = observations.observations[0].model_copy(
        update={"stimulus_id": "missing"}
    )
    with pytest.raises(ValueError, match="undeclared stimulus"):
        validate_observation_references(
            plan,
            stimuli,
            observations.model_copy(update={"observations": (unknown_observation,)}),
            systems,
        )
    unknown_attribution = observations.observations[0].model_copy(
        update={
            "attribution": ObservationAttributionV1(
                kind=AttributionKind.SPECIFIC,
                component_ids=("unknown",),
            )
        }
    )
    with pytest.raises(ValueError, match="unknown component"):
        validate_observation_references(
            plan,
            stimuli,
            observations.model_copy(update={"observations": (unknown_attribution,)}),
            systems,
        )
    variant_mismatch = observations.observations[0].model_copy(
        update={"payload": observations.observations[1].payload}
    )
    with pytest.raises(ValueError, match="variants differ"):
        validate_observation_references(
            plan,
            stimuli,
            observations.model_copy(update={"observations": (variant_mismatch,)}),
            systems,
        )
    non_applicable_limitation = CoverageLimitationV1(
        control_id=AgentAuthorityControlId.C01,
        kind=CoverageLimitationKind.SKIPPED,
        reason="not selected",
    )
    with pytest.raises(ValueError, match="non-applicable controls"):
        validate_observation_references(
            plan,
            stimuli,
            observations.model_copy(
                update={"coverage_limitations": (non_applicable_limitation,)}
            ),
            systems,
        )
    selected_limitation = observations.model_copy(
        update={
            "coverage_limitations": (
                CoverageLimitationV1(
                    control_id=AgentAuthorityControlId.L01,
                    kind=CoverageLimitationKind.CAPPED,
                    reason="selected control was capped",
                ),
            )
        }
    )
    validate_observation_references(plan, stimuli, selected_limitation, systems)


def test_case_specific_cross_reference_rejections() -> None:
    plan = reference_plan()
    stimuli = reference_stimuli()
    observations = reference_observations()
    evidence = {item.handle: item for item in observations.evidence_handles}

    l01_stimulus = stimuli.stimuli[0]
    wrong_channels = observations.observations[0].model_copy(
        update={
            "payload": L01SecretExposureObservationV1(
                channel_scans=(
                    ChannelScanV1(
                        channel=EvidenceChannel.CONTEXT,
                        collection_status=CollectionStatus.COLLECTED,
                        canary_match=False,
                        evidence_handle_ref="evidence:log",
                    ),
                )
            )
        }
    )
    with pytest.raises(ValueError, match="every required channel"):
        validate_case_observation(l01_stimulus, wrong_channels, plan, evidence)
    with pytest.raises(ValueError, match="wrong typed payload"):
        validate_case_observation(
            l01_stimulus,
            observations.observations[1],
            plan,
            evidence,
        )

    l02_stimulus = stimuli.stimuli[1]
    with pytest.raises(ValueError, match="L02 observation has the wrong typed payload"):
        validate_case_observation(
            l02_stimulus,
            observations.observations[0],
            plan,
            evidence,
        )
    unknown_l02_evidence = observations.observations[1].model_copy(
        update={
            "payload": observations.observations[1].payload.model_copy(
                update={"target_evidence_refs": ("evidence:unknown",)}
            )
        }
    )
    with pytest.raises(ValueError, match="undeclared evidence"):
        validate_case_observation(l02_stimulus, unknown_l02_evidence, plan, evidence)

    l03_stimulus = stimuli.stimuli[2]
    bad_l03 = observations.observations[2].model_copy(
        update={
            "payload": observations.observations[2].payload.model_copy(
                update={"traversed_component_ids": ("component-unknown",)}
            )
        }
    )
    with pytest.raises(ValueError, match="undeclared traversed"):
        validate_case_observation(l03_stimulus, bad_l03, plan, evidence)
    with pytest.raises(ValueError, match="wrong typed payload"):
        validate_case_observation(
            l03_stimulus,
            observations.observations[1],
            plan,
            evidence,
        )

    l04_stimulus = stimuli.stimuli[3]
    with pytest.raises(ValueError, match="L04 observation has the wrong typed payload"):
        validate_case_observation(
            l04_stimulus,
            observations.observations[0],
            plan,
            evidence,
        )

    l05_stimulus = stimuli.stimuli[4]
    bad_l05 = observations.observations[4].model_copy(
        update={
            "payload": observations.observations[4].payload.model_copy(
                update={
                    "enforcement_outcomes": (
                        EnforcementOutcomeV1(
                            component_id="component-target",
                            decision=ObservedDecision.DENY,
                            side_effect=ObservedSideEffect.NOT_OBSERVED,
                        ),
                    )
                }
            )
        }
    )
    with pytest.raises(ValueError, match="every enforcement"):
        validate_case_observation(l05_stimulus, bad_l05, plan, evidence)
    with pytest.raises(ValueError, match="wrong typed payload"):
        validate_case_observation(
            l05_stimulus,
            observations.observations[1],
            plan,
            evidence,
        )

    l06_stimulus = stimuli.stimuli[5]
    with pytest.raises(ValueError, match="wrong typed payload"):
        validate_case_observation(
            l06_stimulus,
            observations.observations[1],
            plan,
            evidence,
        )


def test_revocation_dependency_operational_and_compatibility_rejections() -> None:
    plan = reference_plan()
    stimuli = reference_stimuli()
    observations = reference_observations()
    evidence = {item.handle: item for item in observations.evidence_handles}
    l06_stimulus = stimuli.stimuli[5].payload
    l06_observation = observations.observations[5].payload
    assert isinstance(l06_stimulus, L06RevocationPropagationStimulusV1)
    assert isinstance(l06_observation, L06RevocationPropagationObservationV1)
    wrong_point = l06_observation.model_copy(
        update={"point_results": (RevocationPointResultV1(component_id="wrong"),)}
    )
    with pytest.raises(ValueError, match="point-result inventory"):
        validate_revocation_observation(l06_stimulus, wrong_point, plan)
    pre_bound = l06_observation.timed_attempts[0].model_copy(
        update={"sent_elapsed_ns": 10_000_000}
    )
    with pytest.raises(ValueError, match="per enforcement point"):
        validate_revocation_observation(
            l06_stimulus,
            l06_observation.model_copy(update={"timed_attempts": (pre_bound,)}),
            plan,
        )
    extra_handle_stimulus = l06_stimulus.model_copy(
        update={"child_delegation_handles": ("child",)}
    )
    with pytest.raises(ValueError, match="per declared handle"):
        validate_revocation_observation(extra_handle_stimulus, l06_observation, plan)
    bad_attempt = l06_observation.timed_attempts[0].model_copy(
        update={"credential_or_child_handle": "unknown"}
    )
    with pytest.raises(ValueError, match="undeclared reference"):
        validate_revocation_observation(
            l06_stimulus,
            l06_observation.model_copy(
                update={
                    "timed_attempts": (*l06_observation.timed_attempts, bad_attempt)
                }
            ),
            plan,
        )
    no_handles = l06_stimulus.model_copy(
        update={"issued_credential_handles": (), "child_delegation_handles": ()}
    )
    with pytest.raises(ValueError, match="credential or child"):
        validate_revocation_observation(no_handles, l06_observation, plan)

    with pytest.raises(ValueError, match="result inventory"):
        validate_dependency_results(
            stimuli,
            observations.model_copy(update={"dependency_fault_results": ()}),
            evidence,
        )
    wrong_dependency = observations.dependency_fault_results[0].model_copy(
        update={"dependency_component_id": "wrong"}
    )
    with pytest.raises(ValueError, match="wrong dependency"):
        validate_dependency_results(
            stimuli,
            observations.model_copy(
                update={"dependency_fault_results": (wrong_dependency,)}
            ),
            evidence,
        )

    overlap = observations.model_copy(
        update={
            "operational_coverage_gaps": (
                *observations.operational_coverage_gaps,
                OperationalCoverageGapV1(
                    stage_id="baseline-a",
                    reason="overlap",
                ),
            )
        }
    )
    with pytest.raises(ValueError, match="measurements and a gap"):
        validate_operational_inventory(plan, overlap, evidence)
    missing = observations.model_copy(
        update={"operational_coverage_gaps": observations.operational_coverage_gaps[:1]}
    )
    with pytest.raises(ValueError, match="stage inventory"):
        validate_operational_inventory(plan, missing, evidence)

    measurements = observations.operational_measurements
    without_p95 = tuple(
        item
        for item in measurements
        if not (
            item.stage_id == "baseline-a"
            and isinstance(item.payload, LatencyMeasurementV1)
            and item.payload.statistic is LatencyStatistic.P95
        )
    )
    with pytest.raises(ValueError, match="latency statistics"):
        validate_operational_inventory(
            plan,
            observations.model_copy(update={"operational_measurements": without_p95}),
            evidence,
        )
    without_throughput = tuple(
        item
        for item in measurements
        if not (
            item.stage_id == "baseline-a"
            and isinstance(item.payload, ThroughputMeasurementV1)
        )
    )
    with pytest.raises(ValueError, match="one failure-rate and one throughput"):
        validate_operational_inventory(
            plan,
            observations.model_copy(
                update={"operational_measurements": without_throughput}
            ),
            evidence,
        )
    changed_sample = measurements[1].model_copy(update={"sample_count": 99})
    with pytest.raises(ValueError, match="one sample count"):
        validate_operational_inventory(
            plan,
            observations.model_copy(
                update={
                    "operational_measurements": (
                        measurements[0],
                        changed_sample,
                        *measurements[2:],
                    )
                }
            ),
            evidence,
        )
    failure_payload = measurements[0].payload
    assert isinstance(failure_payload, FailureRateMeasurementV1)
    wrong_total = measurements[0].model_copy(
        update={"payload": failure_payload.model_copy(update={"total_count": 99})}
    )
    with pytest.raises(ValueError, match="total must equal"):
        validate_operational_inventory(
            plan,
            observations.model_copy(
                update={"operational_measurements": (wrong_total, *measurements[1:])}
            ),
            evidence,
        )
    throughput_index = next(
        index
        for index, item in enumerate(measurements)
        if item.stage_id == "baseline-a"
        and isinstance(item.payload, ThroughputMeasurementV1)
    )
    throughput_payload = measurements[throughput_index].payload
    assert isinstance(throughput_payload, ThroughputMeasurementV1)
    too_many = measurements[throughput_index].model_copy(
        update={
            "payload": throughput_payload.model_copy(update={"completed_count": 101})
        }
    )
    too_many_rows = list(measurements)
    too_many_rows[throughput_index] = too_many
    with pytest.raises(ValueError, match="completions exceed"):
        validate_operational_inventory(
            plan,
            observations.model_copy(
                update={"operational_measurements": tuple(too_many_rows)}
            ),
            evidence,
        )
    unknown_evidence = measurements[0].model_copy(
        update={"evidence_refs": ("evidence:unknown",)}
    )
    unknown_rows = (unknown_evidence, *measurements[1:])
    with pytest.raises(ValueError, match="undeclared evidence"):
        validate_operational_inventory(
            plan,
            observations.model_copy(update={"operational_measurements": unknown_rows}),
            evidence,
        )

    missing_target = observations.model_copy(
        update={"target_compatibility": observations.target_compatibility[:-1]}
    )
    with pytest.raises(ValueError, match="target inventory"):
        validate_compatibility_inventory(plan, missing_target, evidence)
    wrong_target = observations.target_compatibility[0].model_copy(
        update={"target_handle": "wrong"}
    )
    with pytest.raises(ValueError, match="differs from the plan"):
        validate_compatibility_inventory(
            plan,
            observations.model_copy(
                update={
                    "target_compatibility": (
                        wrong_target,
                        *observations.target_compatibility[1:],
                    )
                }
            ),
            evidence,
        )
    wrong_minima = observations.target_compatibility[0].model_copy(
        update={"nondominated_minima": ("candidate-wide",)}
    )
    with pytest.raises(ValueError, match="minima do not recompute"):
        validate_compatibility_inventory(
            plan,
            observations.model_copy(
                update={
                    "target_compatibility": (
                        wrong_minima,
                        *observations.target_compatibility[1:],
                    )
                }
            ),
            evidence,
        )
    not_attempted = observations.target_compatibility[3]
    with_result = not_attempted.model_copy(
        update={
            "candidate_results": (
                observations.target_compatibility[0].candidate_results[0],
            )
        }
    )
    with pytest.raises(ValueError, match="not-attempted"):
        validate_compatibility_inventory(
            plan,
            observations.model_copy(
                update={
                    "target_compatibility": (
                        *observations.target_compatibility[:3],
                        with_result,
                    )
                }
            ),
            evidence,
        )
    incomplete = observations.target_compatibility[2]
    missing_candidate = incomplete.model_copy(
        update={"candidate_results": incomplete.candidate_results[:1]}
    )
    with pytest.raises(ValueError, match="candidate result inventory"):
        validate_compatibility_inventory(
            plan,
            observations.model_copy(
                update={
                    "target_compatibility": (
                        *observations.target_compatibility[:2],
                        missing_candidate,
                        observations.target_compatibility[3],
                    )
                }
            ),
            evidence,
        )


def test_evidence_handles_are_strict_and_marker_neutral() -> None:
    handle = EvidenceHandleV1(
        handle="evidence:test",
        kind=EvidenceKind.MEMORY,
        digest=DigestV2(value="a" * 64),
        collection_status=CollectionStatus.FAILED,
        redaction_status=RedactionStatus.REDACTED,
    )
    assert "synthetic" not in handle.model_dump()
    with pytest.raises(ValidationError):
        EvidenceHandleV1.model_validate(_document(handle) | {"body": "forbidden"})
