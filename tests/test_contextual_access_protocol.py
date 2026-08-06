"""Cross-artifact and scoring edge cases for the contextual run protocol."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from typing import cast

import pytest
from pydantic import BaseModel, ValidationError

from synthworld.agent_authority.common import EvidenceKind, ObservedDecision
from synthworld.assurance.models_v2 import DigestV2
from synthworld.contextual_access.models import ContextualMappingKind
from synthworld.contextual_access.protocol import (
    CONTEXTUAL_OBSERVATIONS_PATH,
    CONTEXTUAL_REPORT_PATH,
    CONTEXTUAL_RUN_PLAN_PATH,
    CONTEXTUAL_RUN_TRUTH_PATH,
    AccessDecisionObservationV1,
    AccessDecisionProbeV1,
    AccessDecisionRunTruthV1,
    ContextDeliveryAcceptanceObservationV1,
    ContextualAccessObservationsV1,
    ContextualAccessReportV1,
    ContextualAccessRunPlanV1,
    ContextualAccessRunTruthV1,
    ContextualControlCoverageV1,
    ContextualControlId,
    ContextualCoverageDisposition,
    ContextualDecisionAttemptV1,
    ContextualFaultV1,
    ContextualObservationV1,
    ContextualProbeV1,
    ContextualProtocolError,
    ContextualProtocolFindingV1,
    DeliveryAcceptanceProbeV1,
    EvidenceCorrelationObservationV1,
    MappingIngestionObservationV1,
    MappingIngestionProbeV1,
    MappingIngestionStatus,
    ProtectedEnforcementObservationV1,
    ProtectedEnforcementProbeV1,
    SynchronizationFaultObservationV1,
    SynchronizationFaultProbeV1,
    SynchronizationFaultStatus,
    compile_contextual_run_truth,
    evaluate_contextual_access_run,
    validate_contextual_observations,
    validate_contextual_run_plan,
)
from synthworld.contextual_access.protocol_reference import (
    REFERENCE_CONTEXT_FEED_COMPONENT_ID,
    REFERENCE_CONTEXTUAL_SUT_COMPONENT_ID,
    ReferenceContextualRunV1,
    reference_contextual_access_run,
)
from synthworld.enterprise.rbac.common import AuthorizationDecision


def test_reference_protocol_is_complete_publicly_staged_and_independently_scored() -> (
    None
):
    run = reference_contextual_access_run()
    assert len(run.plan.probes) == len(run.observations.observations) == 46
    assert len(run.truth.rows) == len(run.report.findings) == 46
    assert all(item.passed for item in run.report.findings)
    assert all(item.value == 1.0 for item in run.report.metrics)
    assert Counter(item.control_id for item in run.plan.probes) == {
        ContextualControlId.MAPPING_INGESTION: 5,
        ContextualControlId.ACCESS_DECISION: 10,
        ContextualControlId.PROTECTED_ENFORCEMENT: 10,
        ContextualControlId.DELIVERY_ACCEPTANCE: 8,
        ContextualControlId.SYNCHRONIZATION_FAULT: 3,
        ContextualControlId.EVIDENCE_CORRELATION: 10,
    }
    assert run.plan.sut_component_ids == (REFERENCE_CONTEXTUAL_SUT_COMPONENT_ID,)
    assert run.plan.context_feed_component_ids == (REFERENCE_CONTEXT_FEED_COMPONENT_ID,)
    assert (
        CONTEXTUAL_RUN_PLAN_PATH,
        CONTEXTUAL_OBSERVATIONS_PATH,
        CONTEXTUAL_RUN_TRUTH_PATH,
        CONTEXTUAL_REPORT_PATH,
    ) == (
        "context/contextual-access-run-plan.json",
        "observations/contextual-access.json",
        "evaluator/contextual-access-run-truth.json",
        "evaluation/contextual-access-report.json",
    )
    plan_json = run.plan.model_dump_json()
    observations_json = run.observations.model_dump_json()
    assert '"synthetic"' not in plan_json
    assert '"synthetic"' not in observations_json
    assert '"case_id"' not in plan_json
    assert '"case_labels"' not in plan_json
    assert '"expected_decision"' not in plan_json
    assert run.truth.synthetic
    assert run.report.synthetic


def test_coverage_fault_and_string_validators_reject_ambiguous_shapes() -> None:
    with pytest.raises(ValidationError, match="forbid a rationale"):
        ContextualControlCoverageV1(
            control_id=ContextualControlId.ACCESS_DECISION,
            disposition=ContextualCoverageDisposition.SELECTED,
            applicability_rationale="selected anyway",
        )
    for rationale in (None, "  "):
        with pytest.raises(ValidationError, match="require a rationale"):
            ContextualControlCoverageV1(
                control_id=ContextualControlId.ACCESS_DECISION,
                disposition=ContextualCoverageDisposition.NOT_APPLICABLE,
                applicability_rationale=rationale,
            )
    assert ContextualControlCoverageV1(
        control_id=ContextualControlId.ACCESS_DECISION,
        disposition=ContextualCoverageDisposition.NOT_APPLICABLE,
        applicability_rationale="The adapter exposes no decision interface.",
    ).applicability_rationale

    fault = reference_contextual_access_run().plan.faults[-1]
    with pytest.raises(ValidationError, match="precedes injection"):
        _revalidate(
            ContextualFaultV1,
            fault,
            recovery_tick=fault.injection_tick - 1,
        )
    with pytest.raises(ValidationError, match="must be nonblank"):
        _revalidate(ContextualFaultV1, fault, event_ids=("",))
    with pytest.raises(ValidationError, match="must be unique"):
        _revalidate(
            ContextualFaultV1,
            fault,
            event_ids=(fault.event_ids[0], fault.event_ids[0]),
        )
    with pytest.raises(ValidationError, match="canonically ordered"):
        _revalidate(
            ContextualFaultV1,
            fault,
            event_ids=tuple(reversed(fault.event_ids)),
        )


def test_run_plan_model_rejects_noncanonical_or_inconsistent_inventory() -> None:
    plan = reference_contextual_access_run().plan
    invalid: tuple[tuple[dict[str, object], str], ...] = (
        ({"request_ids": ("", *plan.request_ids[1:])}, "must be nonblank"),
        (
            {"request_ids": (plan.request_ids[0], plan.request_ids[0])},
            "must be unique",
        ),
        (
            {
                "sut_component_ids": tuple(
                    reversed(
                        (
                            REFERENCE_CONTEXTUAL_SUT_COMPONENT_ID,
                            "z-component",
                        )
                    )
                )
            },
            "canonically ordered",
        ),
        (
            {"required_evidence_kinds": (EvidenceKind.TRACE, EvidenceKind.TRACE)},
            "evidence kinds",
        ),
        ({"control_coverage": plan.control_coverage[:-1]}, "every control"),
        ({"faults": (*plan.faults, plan.faults[0])}, "faults must be sorted"),
        ({"probes": (*plan.probes, plan.probes[0])}, "probes must be sorted"),
        (
            {
                "control_coverage": (
                    plan.control_coverage[0].model_copy(
                        update={
                            "disposition": (
                                ContextualCoverageDisposition.NOT_APPLICABLE
                            ),
                            "applicability_rationale": "not selected",
                        }
                    ),
                    *plan.control_coverage[1:],
                )
            },
            "selected controls must match",
        ),
    )
    for updates, message in invalid:
        with pytest.raises(ValidationError, match=message):
            _revalidate(ContextualAccessRunPlanV1, plan, **updates)


def test_observation_models_reject_incomplete_time_and_inventory_coordinates() -> None:
    run = reference_contextual_access_run()
    transition = _observation(run, AccessDecisionObservationV1, transition=True)
    static = _observation(run, AccessDecisionObservationV1, transition=False)
    with pytest.raises(ValidationError, match="coordinates are incomplete"):
        _revalidate(
            AccessDecisionObservationV1,
            transition,
            accepted_delivery_attempt_id=None,
        )
    bad_latency = transition.attempts[0].model_copy(
        update={"elapsed_ns_from_acceptance": None}
    )
    with pytest.raises(ValidationError, match="latency coordinates"):
        _revalidate(
            AccessDecisionObservationV1,
            transition,
            attempts=(bad_latency,),
        )
    unexpected_latency = static.attempts[0].model_copy(
        update={"elapsed_ns_from_acceptance": 1}
    )
    with pytest.raises(ValidationError, match="latency coordinates"):
        _revalidate(
            AccessDecisionObservationV1,
            static,
            attempts=(unexpected_latency,),
        )
    later = transition.attempts[0].model_copy(
        update={"decision_tick": transition.attempts[0].decision_tick + 1}
    )
    with pytest.raises(ValidationError, match="tick ordered"):
        _revalidate(
            AccessDecisionObservationV1,
            transition,
            attempts=(later, transition.attempts[0]),
        )

    delivery = _observation(run, ContextDeliveryAcceptanceObservationV1)
    with pytest.raises(ValidationError, match="requires acceptance latency"):
        _revalidate(
            ContextDeliveryAcceptanceObservationV1,
            delivery,
            acceptance_elapsed_ns=None,
        )
    with pytest.raises(ValidationError, match="requires acceptance latency"):
        _revalidate(
            ContextDeliveryAcceptanceObservationV1,
            delivery,
            accepted=False,
        )
    with pytest.raises(ValidationError, match="ticks are out of order"):
        _revalidate(
            ContextDeliveryAcceptanceObservationV1,
            delivery,
            projected_event_tick=delivery.set_issue_tick + 1,
        )

    synchronization = _observation(run, SynchronizationFaultObservationV1)
    with pytest.raises(ValidationError, match="requires recovery latency"):
        _revalidate(
            SynchronizationFaultObservationV1,
            synchronization,
            recovery_elapsed_ns=None,
        )
    with pytest.raises(ValidationError, match="requires recovery latency"):
        _revalidate(
            SynchronizationFaultObservationV1,
            synchronization,
            status=SynchronizationFaultStatus.FAILED,
        )


def test_observation_truth_finding_and_report_models_are_canonical() -> None:
    run = reference_contextual_access_run()
    observations = run.observations
    second = observations.observations[1].model_copy(
        update={"probe_id": observations.observations[0].probe_id}
    )
    replaced = _replace_tuple(observations.observations, 1, second)
    invalid_observations: tuple[tuple[dict[str, object], str], ...] = (
        ({"limitations": ("z", "a")}, "canonically ordered"),
        (
            {"observations": tuple(reversed(observations.observations))},
            "observations must be sorted",
        ),
        ({"observations": replaced}, "unique per probe"),
        (
            {
                "evidence_handles": (
                    *observations.evidence_handles,
                    observations.evidence_handles[0],
                )
            },
            "handles must be sorted",
        ),
    )
    for updates, message in invalid_observations:
        with pytest.raises(ValidationError, match=message):
            _revalidate(ContextualAccessObservationsV1, observations, **updates)

    with pytest.raises(ValidationError, match="truth must be sorted"):
        _revalidate(
            ContextualAccessRunTruthV1,
            run.truth,
            rows=tuple(reversed(run.truth.rows)),
        )
    with pytest.raises(ValidationError, match="forbid failure metadata"):
        ContextualProtocolFindingV1(
            probe_id="probe",
            control_id=ContextualControlId.ACCESS_DECISION,
            passed=True,
            right_censored=True,
        )
    with pytest.raises(ValidationError, match="require a failure code"):
        ContextualProtocolFindingV1(
            probe_id="probe",
            control_id=ContextualControlId.ACCESS_DECISION,
            passed=False,
        )
    with pytest.raises(ValidationError, match="findings must be sorted"):
        _revalidate(
            ContextualAccessReportV1,
            run.report,
            findings=tuple(reversed(run.report.findings)),
        )
    with pytest.raises(ValidationError, match="metrics must be sorted"):
        _revalidate(
            ContextualAccessReportV1,
            run.report,
            metrics=tuple(reversed(run.report.metrics)),
        )


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (
            lambda r: r.plan.model_copy(update={"sut_component_ids": ("unknown",)}),
            "unknown components",
        ),
        (
            lambda r: r.plan.model_copy(
                update={
                    "benchmark": r.plan.benchmark.model_copy(
                        update={"request_digest": DigestV2(value="0" * 64)}
                    )
                }
            ),
            "benchmark binding",
        ),
        (
            lambda r: r.plan.model_copy(
                update={"mapping_profile_digest": DigestV2(value="0" * 64)}
            ),
            "mapping digest",
        ),
        (
            lambda r: r.plan.model_copy(update={"event_schedule_version": "wrong"}),
            "schedule version",
        ),
        (
            lambda r: r.plan.model_copy(
                update={"request_ids": r.plan.request_ids[:-1]}
            ),
            "public inventory",
        ),
        (lambda r: _fault_component_unknown(r), "fault component"),
        (lambda r: _fault_reference_unknown(r), "fault public reference"),
        (lambda r: _fault_attempt_binding_wrong(r), "attempt/event binding"),
        (lambda r: _probe_component_unknown(r), "probe component"),
        (lambda r: _mapping_probe_wrong(r), "probe public reference"),
        (lambda r: _request_probe_wrong(r), "probe public reference"),
        (lambda r: _trigger_probe_wrong(r), "probe public reference"),
        (lambda r: _delivery_probe_wrong(r), "probe public reference"),
        (lambda r: _synchronization_probe_wrong(r), "probe public reference"),
    ),
)
def test_run_plan_cross_artifact_validation_rejects_every_binding_class(
    mutate: Callable[[ReferenceContextualRunV1], ContextualAccessRunPlanV1],
    message: str,
) -> None:
    run = reference_contextual_access_run()
    with pytest.raises(ContextualProtocolError, match=message):
        validate_contextual_run_plan(
            mutate(run),
            public=run.benchmark.public,
            systems_under_test=run.systems_under_test,
        )


def test_observation_cross_artifact_validation_rejects_envelope_failures() -> None:
    run = reference_contextual_access_run()
    first = run.observations.observations[0]
    other_component = (
        REFERENCE_CONTEXT_FEED_COMPONENT_ID
        if first.component_id == REFERENCE_CONTEXTUAL_SUT_COMPONENT_ID
        else REFERENCE_CONTEXTUAL_SUT_COMPONENT_ID
    )
    invalid: tuple[
        tuple[ContextualAccessRunPlanV1, ContextualAccessObservationsV1, str], ...
    ] = (
        (
            run.plan,
            run.observations.model_copy(update={"run_id": "other-run"}),
            "run id",
        ),
        (
            run.plan,
            _observations_with(run, first.model_copy(update={"probe_id": "unknown"})),
            "probe differs",
        ),
        (
            run.plan,
            _observations_with(
                run,
                first.model_copy(
                    update={"probe_id": _probe(run, DeliveryAcceptanceProbeV1).probe_id}
                ),
            ),
            "probe differs",
        ),
        (
            run.plan,
            _observations_with(
                run,
                first.model_copy(update={"component_id": other_component}),
            ),
            "component differs",
        ),
        _unknown_observation_component(run),
        (
            run.plan,
            _observations_with(
                run, first.model_copy(update={"evidence_refs": ("unknown",)})
            ),
            "evidence is unknown",
        ),
    )
    for plan, observations, message in invalid:
        with pytest.raises(ContextualProtocolError, match=message):
            validate_contextual_observations(plan, observations)


@pytest.mark.parametrize(
    ("observation_type", "mutate"),
    (
        (
            MappingIngestionObservationV1,
            lambda item: cast(MappingIngestionObservationV1, item).model_copy(
                update={"mapping_kind": ContextualMappingKind.SUBJECT_ATTRIBUTE}
            ),
        ),
        (
            AccessDecisionObservationV1,
            lambda item: cast(AccessDecisionObservationV1, item).model_copy(
                update={"request_id": "unknown"}
            ),
        ),
        (
            ProtectedEnforcementObservationV1,
            lambda item: cast(ProtectedEnforcementObservationV1, item).model_copy(
                update={"request_id": "unknown"}
            ),
        ),
        (
            ContextDeliveryAcceptanceObservationV1,
            lambda item: cast(ContextDeliveryAcceptanceObservationV1, item).model_copy(
                update={"event_id": "unknown"}
            ),
        ),
        (
            SynchronizationFaultObservationV1,
            lambda item: cast(SynchronizationFaultObservationV1, item).model_copy(
                update={"fault_id": "unknown"}
            ),
        ),
        (
            EvidenceCorrelationObservationV1,
            lambda item: cast(EvidenceCorrelationObservationV1, item).model_copy(
                update={"evidence_kind": EvidenceKind.LOG}
            ),
        ),
    ),
)
def test_observation_cross_artifact_validation_checks_each_public_reference(
    observation_type: type[BaseModel],
    mutate: Callable[[ContextualObservationV1], ContextualObservationV1],
) -> None:
    run = reference_contextual_access_run()
    original = cast(ContextualObservationV1, _observation(run, observation_type))
    with pytest.raises(ContextualProtocolError, match="public reference differs"):
        validate_contextual_observations(
            run.plan, _observations_with(run, mutate(original))
        )


def test_truth_compilation_and_evaluation_reject_cross_run_drift() -> None:
    run = reference_contextual_access_run()
    evaluator = run.benchmark.evaluator.model_copy(
        update={
            "public_digest": run.benchmark.evaluator.public_digest.model_copy(
                update={"value": "0" * 64}
            )
        }
    )
    with pytest.raises(ContextualProtocolError, match="does not bind public"):
        compile_contextual_run_truth(
            run.plan,
            public=run.benchmark.public,
            evaluator=evaluator,
        )
    with pytest.raises(ContextualProtocolError, match="truth identifier"):
        evaluate_contextual_access_run(
            run.plan,
            run.observations,
            run.truth.model_copy(update={"run_id": "other-run"}),
        )
    with pytest.raises(ContextualProtocolError, match="truth probe inventory"):
        evaluate_contextual_access_run(
            run.plan,
            run.observations,
            run.truth.model_copy(update={"rows": run.truth.rows[:-1]}),
        )


def test_missing_observations_fail_without_collapsing_independent_metrics() -> None:
    run = reference_contextual_access_run()
    missing = run.observations.model_copy(update={"observations": ()})
    report = evaluate_contextual_access_run(run.plan, missing, run.truth)
    assert all(not item.passed for item in report.findings)
    assert {item.failure_code for item in report.findings} == {"missing_observation"}
    assert all(item.value == 0.0 for item in report.metrics)
    assert len(report.metrics) == 8


@pytest.mark.parametrize(
    ("observation_type", "mutate", "failure_code"),
    (
        (
            MappingIngestionObservationV1,
            lambda item: cast(MappingIngestionObservationV1, item).model_copy(
                update={"status": MappingIngestionStatus.ERROR}
            ),
            "mapping_ingestion_mismatch",
        ),
        (
            ProtectedEnforcementObservationV1,
            lambda item: _wrong_enforcement(
                cast(ProtectedEnforcementObservationV1, item)
            ),
            "protected_enforcement_mismatch",
        ),
        (
            ContextDeliveryAcceptanceObservationV1,
            lambda item: cast(ContextDeliveryAcceptanceObservationV1, item).model_copy(
                update={"accepted": False, "acceptance_elapsed_ns": None}
            ),
            "delivery_or_acceptance_bound_failed",
        ),
        (
            SynchronizationFaultObservationV1,
            lambda item: cast(SynchronizationFaultObservationV1, item).model_copy(
                update={
                    "status": SynchronizationFaultStatus.FAILED,
                    "recovery_elapsed_ns": None,
                }
            ),
            "synchronization_fault_not_recovered",
        ),
        (
            EvidenceCorrelationObservationV1,
            lambda item: cast(EvidenceCorrelationObservationV1, item).model_copy(
                update={"correlated": False}
            ),
            "required_evidence_not_correlated",
        ),
    ),
)
def test_each_nondecision_control_has_an_independent_failure(
    observation_type: type[BaseModel],
    mutate: Callable[[ContextualObservationV1], ContextualObservationV1],
    failure_code: str,
) -> None:
    run = reference_contextual_access_run()
    original = cast(ContextualObservationV1, _observation(run, observation_type))
    changed = mutate(original)
    report = evaluate_contextual_access_run(
        run.plan, _observations_with(run, changed), run.truth
    )
    finding = _finding(report, changed.probe_id)
    assert not finding.passed
    assert finding.failure_code == failure_code


def test_decision_scoring_distinguishes_mismatch_binding_and_censoring() -> None:
    run = reference_contextual_access_run()
    static = _observation(run, AccessDecisionObservationV1, transition=False)
    static_truth = cast(AccessDecisionRunTruthV1, _truth(run, static.probe_id))
    wrong_static = _decision_with(
        static,
        decision=_opposite(static_truth.expected_decision),
        elapsed_ns=None,
    )
    report = _evaluate_changed(run, wrong_static)
    assert _finding(report, static.probe_id).failure_code == (
        "decision_or_policy_mismatch"
    )

    transition = _observation(run, AccessDecisionObservationV1, transition=True)
    transition_truth = cast(AccessDecisionRunTruthV1, _truth(run, transition.probe_id))
    wrong_attempt = transition.model_copy(
        update={"accepted_delivery_attempt_id": "different-attempt"}
    )
    report = _evaluate_changed(run, wrong_attempt)
    assert _finding(report, transition.probe_id).failure_code == (
        "accepted_delivery_attempt_mismatch"
    )

    censored = _decision_with(
        transition,
        decision=_opposite(transition_truth.expected_decision),
        elapsed_ns=1,
    )
    report = _evaluate_changed(run, censored)
    finding = _finding(report, transition.probe_id)
    assert finding.failure_code == "correct_post_acceptance_decision_not_observed"
    assert finding.right_censored
    propagation = next(
        item
        for item in report.metrics
        if item.name == "post_acceptance_decision_propagation"
    )
    assert propagation.numerator < propagation.denominator

    late = _decision_with(
        transition,
        decision=transition_truth.expected_decision,
        elapsed_ns=run.plan.bounds.post_acceptance_decision_bound_ns + 1,
    )
    report = _evaluate_changed(run, late)
    finding = _finding(report, transition.probe_id)
    assert finding.failure_code == "post_acceptance_decision_bound_or_policy_failed"
    assert not finding.right_censored

    missing_policy = transition.model_copy(update={"policy_version_ids": ()})
    report = _evaluate_changed(run, missing_policy)
    assert not _finding(report, transition.probe_id).passed


def test_delivery_and_evidence_metrics_keep_bounds_and_correlation_separate() -> None:
    run = reference_contextual_access_run()
    delivery = next(
        item
        for item in run.observations.observations
        if isinstance(item, ContextDeliveryAcceptanceObservationV1)
        and item.projected_event_tick > 0
    )
    slow = delivery.model_copy(
        update={"acceptance_elapsed_ns": run.plan.bounds.sut_acceptance_bound_ns + 1}
    )
    slow_report = _evaluate_changed(run, slow)
    values = {item.name: item.value for item in slow_report.metrics}
    assert values["feed_delay_within_bound"] == 1.0
    acceptance_value = values["sut_acceptance_within_bound"]
    assert acceptance_value is not None and acceptance_value < 1.0

    shifted = delivery.model_copy(
        update={
            "projected_event_tick": max(0, delivery.projected_event_tick - 1),
            "set_issue_tick": max(0, delivery.projected_event_tick - 1),
        }
    )
    shifted_report = _evaluate_changed(run, shifted)
    values = {item.name: item.value for item in shifted_report.metrics}
    feed_value = values["feed_delay_within_bound"]
    assert feed_value is not None and feed_value < 1.0
    assert values["sut_acceptance_within_bound"] == 1.0

    evidence = _observation(run, EvidenceCorrelationObservationV1)
    wrong_handle = run.observations.evidence_handles[0].model_copy(
        update={"kind": EvidenceKind.LOG}
    )
    observations = _observations_with(run, evidence).model_copy(
        update={"evidence_handles": (wrong_handle,)}
    )
    report = evaluate_contextual_access_run(run.plan, observations, run.truth)
    assert _finding(report, evidence.probe_id).failure_code == (
        "required_evidence_not_correlated"
    )


def _revalidate[ModelT: BaseModel](
    model: type[ModelT], value: BaseModel, **updates: object
) -> ModelT:
    document = value.model_dump(mode="python")
    document.update(updates)
    return model.model_validate(document)


def _replace_tuple[ItemT](
    values: tuple[ItemT, ...], index: int, replacement: ItemT
) -> tuple[ItemT, ...]:
    changed = list(values)
    changed[index] = replacement
    return tuple(changed)


def _replace_probe(
    plan: ContextualAccessRunPlanV1,
    original: ContextualProbeV1,
    replacement: ContextualProbeV1,
) -> ContextualAccessRunPlanV1:
    index = plan.probes.index(original)
    return plan.model_copy(
        update={"probes": _replace_tuple(plan.probes, index, replacement)}
    )


def _replace_fault(
    plan: ContextualAccessRunPlanV1,
    original: ContextualFaultV1,
    replacement: ContextualFaultV1,
) -> ContextualAccessRunPlanV1:
    index = plan.faults.index(original)
    return plan.model_copy(
        update={"faults": _replace_tuple(plan.faults, index, replacement)}
    )


def _fault_component_unknown(
    run: ReferenceContextualRunV1,
) -> ContextualAccessRunPlanV1:
    fault = run.plan.faults[0]
    return _replace_fault(
        run.plan, fault, fault.model_copy(update={"component_id": "unknown"})
    )


def _fault_reference_unknown(
    run: ReferenceContextualRunV1,
) -> ContextualAccessRunPlanV1:
    fault = run.plan.faults[0]
    return _replace_fault(
        run.plan, fault, fault.model_copy(update={"event_ids": ("unknown",)})
    )


def _fault_attempt_binding_wrong(
    run: ReferenceContextualRunV1,
) -> ContextualAccessRunPlanV1:
    fault = run.plan.faults[0]
    attempt = next(
        item
        for item in run.benchmark.public.delivery_attempts
        if item.attempt_id == fault.delivery_attempt_ids[0]
    )
    other_event = next(item for item in run.plan.event_ids if item != attempt.event_id)
    return _replace_fault(
        run.plan, fault, fault.model_copy(update={"event_ids": (other_event,)})
    )


def _probe_component_unknown(
    run: ReferenceContextualRunV1,
) -> ContextualAccessRunPlanV1:
    probe = run.plan.probes[0]
    return _replace_probe(
        run.plan, probe, probe.model_copy(update={"component_id": "unknown"})
    )


def _mapping_probe_wrong(run: ReferenceContextualRunV1) -> ContextualAccessRunPlanV1:
    probe = _probe(run, MappingIngestionProbeV1)
    alternatives = tuple(
        item for item in ContextualMappingKind if item is not probe.mapping_kind
    )
    return _replace_probe(
        run.plan, probe, probe.model_copy(update={"mapping_kind": alternatives[0]})
    )


def _request_probe_wrong(run: ReferenceContextualRunV1) -> ContextualAccessRunPlanV1:
    probe = _probe(run, ProtectedEnforcementProbeV1)
    return _replace_probe(
        run.plan, probe, probe.model_copy(update={"request_id": "unknown"})
    )


def _trigger_probe_wrong(run: ReferenceContextualRunV1) -> ContextualAccessRunPlanV1:
    probe = _probe(run, AccessDecisionProbeV1, transition=True)
    return _replace_probe(
        run.plan, probe, probe.model_copy(update={"trigger_event_id": "unknown"})
    )


def _delivery_probe_wrong(run: ReferenceContextualRunV1) -> ContextualAccessRunPlanV1:
    probe = _probe(run, DeliveryAcceptanceProbeV1)
    other_event = next(item for item in run.plan.event_ids if item != probe.event_id)
    return _replace_probe(
        run.plan, probe, probe.model_copy(update={"event_id": other_event})
    )


def _synchronization_probe_wrong(
    run: ReferenceContextualRunV1,
) -> ContextualAccessRunPlanV1:
    probe = _probe(run, SynchronizationFaultProbeV1)
    return _replace_probe(
        run.plan, probe, probe.model_copy(update={"fault_id": "unknown"})
    )


def _probe[ProbeT: BaseModel](
    run: ReferenceContextualRunV1,
    probe_type: type[ProbeT],
    *,
    transition: bool | None = None,
) -> ProbeT:
    return next(
        item
        for item in run.plan.probes
        if isinstance(item, probe_type)
        and (
            transition is None
            or (
                isinstance(item, AccessDecisionProbeV1)
                and (item.trigger_event_id is not None) is transition
            )
        )
    )


def _observation[ObservationT: BaseModel](
    run: ReferenceContextualRunV1,
    observation_type: type[ObservationT],
    *,
    transition: bool | None = None,
) -> ObservationT:
    return next(
        item
        for item in run.observations.observations
        if isinstance(item, observation_type)
        and (
            transition is None
            or (
                isinstance(item, AccessDecisionObservationV1)
                and (item.trigger_event_id is not None) is transition
            )
        )
    )


def _observations_with(
    run: ReferenceContextualRunV1,
    replacement: ContextualObservationV1,
) -> ContextualAccessObservationsV1:
    index = next(
        index
        for index, item in enumerate(run.observations.observations)
        if item.probe_id == replacement.probe_id
        or item.observation_id == replacement.observation_id
    )
    return run.observations.model_copy(
        update={
            "observations": _replace_tuple(
                run.observations.observations, index, replacement
            )
        }
    )


def _unknown_observation_component(
    run: ReferenceContextualRunV1,
) -> tuple[ContextualAccessRunPlanV1, ContextualAccessObservationsV1, str]:
    observation = run.observations.observations[0]
    probe = next(
        item for item in run.plan.probes if item.probe_id == observation.probe_id
    )
    changed_probe = probe.model_copy(update={"component_id": "unknown"})
    changed_plan = _replace_probe(run.plan, probe, changed_probe)
    changed_observation = observation.model_copy(update={"component_id": "unknown"})
    return (
        changed_plan,
        _observations_with(run, changed_observation),
        "component is unknown",
    )


def _truth(run: ReferenceContextualRunV1, probe_id: str) -> BaseModel:
    return next(item for item in run.truth.rows if item.probe_id == probe_id)


def _finding(
    report: ContextualAccessReportV1, probe_id: str
) -> ContextualProtocolFindingV1:
    return next(item for item in report.findings if item.probe_id == probe_id)


def _evaluate_changed(
    run: ReferenceContextualRunV1,
    observation: ContextualObservationV1,
) -> ContextualAccessReportV1:
    return evaluate_contextual_access_run(
        run.plan, _observations_with(run, observation), run.truth
    )


def _opposite(decision: AuthorizationDecision) -> ObservedDecision:
    return (
        ObservedDecision.DENY
        if decision is AuthorizationDecision.ALLOW
        else ObservedDecision.ALLOW
    )


def _decision_with(
    observation: AccessDecisionObservationV1,
    *,
    decision: AuthorizationDecision | ObservedDecision,
    elapsed_ns: int | None,
) -> AccessDecisionObservationV1:
    return observation.model_copy(
        update={
            "attempts": (
                ContextualDecisionAttemptV1(
                    decision_tick=observation.attempts[0].decision_tick,
                    decision=ObservedDecision(decision.value),
                    elapsed_ns_from_acceptance=elapsed_ns,
                ),
            )
        }
    )


def _wrong_enforcement(
    observation: ProtectedEnforcementObservationV1,
) -> ProtectedEnforcementObservationV1:
    return observation.model_copy(
        update={
            "decision": (
                ObservedDecision.DENY
                if observation.decision is ObservedDecision.ALLOW
                else ObservedDecision.ALLOW
            )
        }
    )
