"""End-to-end tests for bounded longitudinal identity assurance."""

from __future__ import annotations

from collections.abc import Iterable

import pytest

from synthworld.continuous_assurance import (
    CONTINUOUS_ASSURANCE_BASELINES,
    AssuranceDriftKind,
    ContinuousAssuranceCaseKind,
    ContinuousAssuranceConfigV1,
    ContinuousAssurancePredictionRowV1,
    ContinuousAssurancePredictionV1,
    ContinuousAssuranceSourceFamily,
    ContinuousAssuranceTier,
    FindingLifecycleState,
    canonical_signals_as_of,
    evaluate_continuous_assurance_prediction,
    expected_finding_state_at,
    observed_remediations_as_of,
    observed_signals_as_of,
    perfect_continuous_assurance_prediction,
    reference_continuous_assurance,
    validate_continuous_assurance_evaluator,
    validate_continuous_assurance_public,
)
from synthworld.continuous_assurance.models import (
    ContinuousAssuranceMetricV1,
)


def _metrics(
    metrics: Iterable[ContinuousAssuranceMetricV1],
) -> dict[str, ContinuousAssuranceMetricV1]:
    return {item.name: item for item in metrics}


def _value(metric: ContinuousAssuranceMetricV1) -> float:
    assert metric.value is not None
    return metric.value


def test_reference_pack_is_deterministic_digest_bound_and_oracle_split() -> None:
    first = reference_continuous_assurance(seed=20260804)
    second = reference_continuous_assurance(seed=20260804)
    changed = reference_continuous_assurance(seed=20260805)

    assert first == second
    assert first != changed
    validate_continuous_assurance_public(first.public)
    validate_continuous_assurance_evaluator(first.public, first.evaluator)
    assert {item.family for item in first.public.source_bindings} == set(
        ContinuousAssuranceSourceFamily
    )
    assert {item.source.family for item in first.public.signals} == set(
        ContinuousAssuranceSourceFamily
    )
    assert first.public.benchmark.tier is ContinuousAssuranceTier.SMOKE
    assert len(first.public.cases) == 8
    assert len(first.evaluator.truth) == 8

    public_json = first.public.model_dump_json()
    for oracle_name in (
        "case_kind",
        "finding_required",
        "expected_finding",
        "failure_reasons",
        "private_config_digest",
    ):
        assert oracle_name not in public_json
    assert '"seed"' not in public_json
    assert "case_kind" in first.evaluator.model_dump_json()


@pytest.mark.parametrize(
    ("tier", "expected_cases"),
    [
        (ContinuousAssuranceTier.SMOKE, 8),
        (ContinuousAssuranceTier.STANDARD, 24),
        (ContinuousAssuranceTier.LONGITUDINAL, 48),
        (ContinuousAssuranceTier.HELD_OUT, 24),
    ],
)
def test_tiers_are_explicit_bounded_profiles(
    tier: ContinuousAssuranceTier, expected_cases: int
) -> None:
    benchmark = reference_continuous_assurance(
        tier=tier,
        seed=99,
        risk_threshold=73,
        justification_kind="case_assignment",
    )
    assert len(benchmark.public.cases) == expected_cases
    assert len(benchmark.evaluator.truth) == expected_cases
    assert benchmark.config == ContinuousAssuranceConfigV1(
        tier=tier,
        seed=99,
        risk_threshold=73,
        justification_kind="case_assignment",
    )
    assert benchmark.public.benchmark.tier is tier
    assert benchmark.public.horizon_tick == benchmark.public.checkpoints[-1].tick


def test_policy_variants_change_semantics_without_resizing_the_profile() -> None:
    baseline = reference_continuous_assurance(
        seed=101,
        risk_threshold=70,
        justification_kind="business_need",
    )
    changed_risk = reference_continuous_assurance(
        seed=101,
        risk_threshold=85,
        justification_kind="business_need",
    )
    changed_justification = reference_continuous_assurance(
        seed=101,
        risk_threshold=70,
        justification_kind="emergency_access",
    )
    packs = (baseline, changed_risk, changed_justification)
    assert len({item.public.benchmark.policy_profile_id for item in packs}) == 3
    assert len({item.public for item in packs}) == 3
    assert {
        (
            len(item.public.cases),
            len(item.public.signals),
            len(item.public.remediations),
            len(item.public.feed_windows),
        )
        for item in packs
    } == {(8, 11, 6, 1)}


def test_outage_changes_observation_only_on_the_shared_tick_axis() -> None:
    benchmark = reference_continuous_assurance()
    feed_truth = next(
        item
        for item in benchmark.evaluator.truth
        if item.case_kind is ContinuousAssuranceCaseKind.FEED_OUTAGE_DELAY
    )
    case = next(
        item for item in benchmark.public.cases if item.case_id == feed_truth.case_id
    )
    signal = next(
        item for item in benchmark.public.signals if item.signal_id in case.signal_ids
    )
    window = next(
        item
        for item in benchmark.public.feed_windows
        if item.feed_window_id == case.feed_window_id
    )

    assert (
        signal.action_tick
        <= signal.decision_tick
        <= signal.effective_tick
        < window.restored_at_tick
        <= signal.observation_tick
        <= signal.audit_tick
    )
    assert signal in canonical_signals_as_of(
        benchmark.public, tick=signal.effective_tick
    )
    assert signal not in observed_signals_as_of(
        benchmark.public, tick=signal.effective_tick
    )
    assert signal in observed_signals_as_of(
        benchmark.public, tick=signal.observation_tick
    )
    assert observed_remediations_as_of(benchmark.public, tick=0) == ()
    assert (
        observed_remediations_as_of(
            benchmark.public, tick=benchmark.public.horizon_tick
        )
        == benchmark.public.remediations
    )


def test_later_policy_and_late_evidence_are_not_retroactive() -> None:
    benchmark = reference_continuous_assurance()
    by_kind = {item.case_kind: item for item in benchmark.evaluator.truth}

    policy = by_kind[ContinuousAssuranceCaseKind.POLICY_LATER_VERSION]
    policy_case = next(
        item for item in benchmark.public.cases if item.case_id == policy.case_id
    )
    policy_signals = tuple(
        item
        for item in benchmark.public.signals
        if item.signal_id in policy_case.signal_ids
    )
    assert len({item.policy_version_id for item in policy_signals}) == 2
    assert policy.canonical_policy_version_id == policy_signals[0].policy_version_id
    assert (
        expected_finding_state_at(policy, tick=benchmark.public.horizon_tick)
        is FindingLifecycleState.OPEN
    )

    evidence = by_kind[ContinuousAssuranceCaseKind.EVIDENCE_LATE_ARRIVAL]
    assert evidence.expected_evidence_continuous is False
    assert len(evidence.expected_finding_cleared_ticks) == 1
    assert (
        expected_finding_state_at(
            evidence, tick=evidence.expected_finding_opened_tick or 0
        )
        is FindingLifecycleState.OPEN
    )
    assert (
        expected_finding_state_at(
            evidence, tick=evidence.expected_finding_cleared_ticks[0]
        )
        is FindingLifecycleState.CLEAR
    )


def test_perfect_prediction_scores_each_metric_independently() -> None:
    benchmark = reference_continuous_assurance()
    prediction = perfect_continuous_assurance_prediction(benchmark.evaluator)
    report = evaluate_continuous_assurance_prediction(
        public=benchmark.public,
        evaluator=benchmark.evaluator,
        prediction=prediction,
    )
    metrics = _metrics(report.metrics)
    assert len(metrics) == 16
    assert all(
        all(
            (
                finding.detection_correct,
                finding.classification_correct,
                finding.opening_tick_correct,
                finding.clearing_tick_correct,
                finding.recurrence_correct,
                finding.remediation_correct,
                finding.evidence_continuity_correct,
                finding.checkpoint_state_correct,
            )
        )
        for finding in report.findings
    )
    for name in (
        "drift_classification_accuracy",
        "checkpoint_finding_state_accuracy",
        "finding_detection_recall",
        "finding_open_tick_accuracy",
        "finding_precision",
        "evidence_continuity_accuracy",
        "recurrence_precision",
        "recurrence_recall",
        "remediation_completeness_accuracy",
        "finding_clear_tick_accuracy",
    ):
        assert metrics[name].value == 1.0
    for name in (
        "detection_latency_mean_ticks",
        "false_negative_rate",
        "false_positive_rate",
        "pre_observation_opening_rate",
        "premature_clear_rate",
        "stale_finding_duration_mean_ticks",
    ):
        assert metrics[name].value == 0.0


def test_public_only_baselines_discriminate_different_failures() -> None:
    benchmark = reference_continuous_assurance()
    reports = {
        name: evaluate_continuous_assurance_prediction(
            public=benchmark.public,
            evaluator=benchmark.evaluator,
            prediction=baseline(benchmark.public),
        )
        for name, baseline in CONTINUOUS_ASSURANCE_BASELINES
    }
    latest = _metrics(reports["Latest observed state"].metrics)
    effective = _metrics(reports["Effective time is detection time"].metrics)
    never_clear = _metrics(reports["Never clear findings"].metrics)

    assert _value(latest["finding_detection_recall"]) < 1.0
    assert _value(effective["pre_observation_opening_rate"]) > 0.0
    assert effective["finding_detection_recall"].value == 0.0
    assert _value(never_clear["stale_finding_duration_mean_ticks"]) > 0.0
    assert never_clear["finding_clear_tick_accuracy"].value == 0.0


def test_missing_findings_publish_explicit_null_empty_denominators() -> None:
    benchmark = reference_continuous_assurance()
    prediction = ContinuousAssurancePredictionV1(
        rows=tuple(
            ContinuousAssurancePredictionRowV1(case_id=item.case_id)
            for item in benchmark.evaluator.truth
        )
    )
    report = evaluate_continuous_assurance_prediction(
        public=benchmark.public,
        evaluator=benchmark.evaluator,
        prediction=prediction,
    )
    metrics = _metrics(report.metrics)
    for name in (
        "detection_latency_mean_ticks",
        "finding_precision",
        "recurrence_precision",
    ):
        metric = metrics[name]
        assert metric.denominator == 0
        assert metric.numerator == 0
        assert metric.support == 0
        assert metric.value is None
    assert metrics["false_negative_rate"].value == 1.0
    assert _value(metrics["stale_finding_duration_mean_ticks"]) > 0.0


def test_wrong_lifecycle_is_visible_without_an_aggregate_score() -> None:
    benchmark = reference_continuous_assurance()
    perfect = perfect_continuous_assurance_prediction(benchmark.evaluator)
    recurrence_truth = next(
        item
        for item in benchmark.evaluator.truth
        if item.case_kind is ContinuousAssuranceCaseKind.DELEGATION_RECURRENCE
    )
    stable_truth = next(
        item
        for item in benchmark.evaluator.truth
        if item.case_kind is ContinuousAssuranceCaseKind.STABLE_CONTROL
    )
    rows = []
    first_observable_tick = recurrence_truth.first_observable_tick
    assert first_observable_tick is not None
    for row in perfect.rows:
        if row.case_id == recurrence_truth.case_id:
            first_clear = recurrence_truth.expected_finding_cleared_ticks[0]
            rows.append(
                row.model_copy(
                    update={
                        "predicted_drift_kind": AssuranceDriftKind.CREDENTIAL,
                        "finding_opened_tick": first_observable_tick + 2,
                        "finding_cleared_ticks": (
                            first_clear - 1,
                            recurrence_truth.expected_finding_cleared_ticks[1] + 2,
                        ),
                        "recurrence_opened_ticks": (
                            recurrence_truth.expected_recurrence_opened_ticks[0] + 1,
                        ),
                        "remediation_complete": False,
                        "evidence_continuous": False,
                    }
                )
            )
        elif row.case_id == stable_truth.case_id:
            rows.append(
                ContinuousAssurancePredictionRowV1(
                    case_id=row.case_id,
                    predicted_drift_kind=AssuranceDriftKind.POLICY,
                    finding_opened_tick=1,
                    evidence_continuous=True,
                )
            )
        else:
            rows.append(row)
    prediction = ContinuousAssurancePredictionV1(rows=tuple(rows))
    report = evaluate_continuous_assurance_prediction(
        public=benchmark.public,
        evaluator=benchmark.evaluator,
        prediction=prediction,
    )
    metrics = _metrics(report.metrics)
    assert metrics["false_positive_rate"].numerator == 1
    assert _value(metrics["drift_classification_accuracy"]) < 1.0
    assert metrics["premature_clear_rate"].numerator == 1
    assert metrics["stale_finding_duration_mean_ticks"].numerator == 2
    assert metrics["recurrence_recall"].value == 0.0
    assert _value(metrics["remediation_completeness_accuracy"]) < 1.0
    assert _value(metrics["evidence_continuity_accuracy"]) < 1.0
    assert not hasattr(report, "aggregate_score")
