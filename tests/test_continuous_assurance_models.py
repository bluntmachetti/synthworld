"""Contract-level invariant tests for continuous assurance models."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import pytest
from pydantic import ValidationError

from synthworld.continuous_assurance import (
    AssuranceDriftKind,
    ContinuousAssuranceMetricAggregation,
    ContinuousAssuranceMetricFamily,
    ContinuousAssuranceMetricV1,
    ContinuousAssurancePredictionRowV1,
    ContinuousAssurancePublicV1,
    ContinuousAssuranceTier,
    FindingLifecycleState,
    evaluate_continuous_assurance_prediction,
    perfect_continuous_assurance_prediction,
    reference_continuous_assurance,
)
from synthworld.models import SyntheticModel


def _revalidate[ModelT: SyntheticModel](
    model: ModelT, updates: Mapping[str, Any]
) -> ModelT:
    document = model.model_dump(mode="python")
    document.update(updates)
    return type(model).model_validate(document)


@pytest.mark.parametrize(
    ("target_name", "updates", "message"),
    [
        (
            "signal",
            {"evidence_refs": ("duplicate", "duplicate")},
            "sorted and unique",
        ),
        ("signal", {"evidence_refs": (" ",)}, "nonblank"),
        ("signal", {"action_tick": 99}, "coordinates must be ordered"),
        (
            "remediation",
            {"evidence_refs": ("duplicate", "duplicate")},
            "sorted and unique",
        ),
        ("remediation", {"decision_tick": 99}, "coordinates must be ordered"),
        (
            "window",
            {"delayed_signal_ids": ("duplicate", "duplicate")},
            "sorted and unique",
        ),
        ("window", {"restored_at_tick": 0}, "must be forward"),
        (
            "case",
            {"signal_ids": ("duplicate", "duplicate")},
            "sorted and unique",
        ),
        ("case", {"remediation_ids": ("",)}, "nonblank"),
        (
            "checkpoint",
            {"observed_signal_ids": ("duplicate", "duplicate")},
            "sorted and unique",
        ),
        ("checkpoint", {"available_evidence_refs": (" ",)}, "nonblank"),
    ],
)
def test_event_and_reference_models_reject_noncanonical_values(
    target_name: str, updates: dict[str, object], message: str
) -> None:
    public = reference_continuous_assurance().public
    targets = {
        "signal": public.signals[0],
        "remediation": public.remediations[0],
        "window": public.feed_windows[0],
        "case": public.cases[0],
        "checkpoint": public.checkpoints[-1],
    }
    with pytest.raises(ValidationError, match=message):
        _revalidate(targets[target_name], updates)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        (
            lambda public: {"source_bindings": tuple(reversed(public.source_bindings))},
            "source bindings",
        ),
        (lambda public: {"cases": tuple(reversed(public.cases))}, "cases must be"),
        (
            lambda public: {"feed_windows": tuple(reversed(public.feed_windows))},
            "feed windows",
        ),
        (
            lambda public: {"signals": (*public.signals, public.signals[0])},
            "signals must be",
        ),
        (
            lambda public: {
                "remediations": (*public.remediations, public.remediations[0])
            },
            "remediations must be",
        ),
        (
            lambda public: {
                "checkpoints": (*public.checkpoints, public.checkpoints[-1])
            },
            "checkpoints must be",
        ),
        (lambda public: {"horizon_tick": public.horizon_tick + 1}, "final checkpoint"),
    ],
)
def test_public_model_rejects_noncanonical_inventories(
    updates: Callable[[ContinuousAssurancePublicV1], dict[str, object]],
    message: str,
) -> None:
    public = reference_continuous_assurance(
        tier=ContinuousAssuranceTier.STANDARD
    ).public
    with pytest.raises(ValidationError, match=message):
        _revalidate(public, updates(public))


def test_evaluator_prediction_and_report_inventories_are_canonical() -> None:
    benchmark = reference_continuous_assurance()
    prediction = perfect_continuous_assurance_prediction(benchmark.evaluator)
    report = evaluate_continuous_assurance_prediction(
        public=benchmark.public,
        evaluator=benchmark.evaluator,
        prediction=prediction,
    )

    with pytest.raises(ValidationError, match="evaluator sources"):
        _revalidate(
            benchmark.evaluator,
            {"source_bindings": tuple(reversed(benchmark.evaluator.source_bindings))},
        )
    with pytest.raises(ValidationError, match="continuous-assurance truth"):
        _revalidate(
            benchmark.evaluator,
            {"truth": tuple(reversed(benchmark.evaluator.truth))},
        )
    with pytest.raises(ValidationError, match="predictions"):
        _revalidate(prediction, {"rows": tuple(reversed(prediction.rows))})
    with pytest.raises(ValidationError, match="findings"):
        _revalidate(report, {"findings": tuple(reversed(report.findings))})
    with pytest.raises(ValidationError, match="metrics must be sorted"):
        _revalidate(report, {"metrics": tuple(reversed(report.metrics))})


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        (
            {"expected_finding_cleared_ticks": (7, 7)},
            "sorted and unique",
        ),
        ({"failure_reasons": ("",)}, "must be nonblank"),
        (
            {"expected_evidence_continuous": None},
            "positive truth is incomplete",
        ),
        (
            {"first_observable_tick": 0},
            "truth coordinates must be ordered",
        ),
        (
            {"expected_finding_cleared_ticks": (0,)},
            "finding clear precedes",
        ),
        (
            {
                "lifecycle": (),
            },
            "positive truth is incomplete",
        ),
    ],
)
def test_positive_truth_rejects_incomplete_or_incoherent_fields(
    updates: dict[str, object], message: str
) -> None:
    truth = next(
        item
        for item in reference_continuous_assurance().evaluator.truth
        if item.expected_finding_cleared_ticks
    )
    with pytest.raises(ValidationError, match=message):
        _revalidate(truth, updates)


def test_truth_lifecycle_must_match_declared_transitions() -> None:
    truth = next(
        item
        for item in reference_continuous_assurance().evaluator.truth
        if item.expected_finding_cleared_ticks
        and not item.expected_recurrence_opened_ticks
    )
    duplicate_lifecycle = (*truth.lifecycle, truth.lifecycle[-1])
    with pytest.raises(ValidationError, match="ordered and unique"):
        _revalidate(truth, {"lifecycle": duplicate_lifecycle})

    changed_state = truth.lifecycle[-1].model_copy(
        update={"state": FindingLifecycleState.OPEN}
    )
    with pytest.raises(ValidationError, match="differs from expected transitions"):
        _revalidate(truth, {"lifecycle": (truth.lifecycle[0], changed_state)})

    negative = next(
        item
        for item in reference_continuous_assurance().evaluator.truth
        if not item.finding_required
    )
    with pytest.raises(ValidationError, match="negative truth carries"):
        _revalidate(
            negative,
            {"expected_recurrence_opened_ticks": (1,)},
        )
    with pytest.raises(ValidationError, match="negative truth carries"):
        _revalidate(negative, {"lifecycle": truth.lifecycle})


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"finding_cleared_ticks": (8, 8)}, "sorted and unique"),
        (
            {"predicted_drift_kind": AssuranceDriftKind.OWNER},
            "absent finding carries",
        ),
        (
            {"finding_opened_tick": 5},
            "opened finding needs a drift kind",
        ),
        (
            {
                "predicted_drift_kind": AssuranceDriftKind.OWNER,
                "finding_opened_tick": 5,
                "finding_cleared_ticks": (4,),
            },
            "clear precedes opening",
        ),
        (
            {
                "predicted_drift_kind": AssuranceDriftKind.OWNER,
                "finding_opened_tick": 5,
                "recurrence_opened_ticks": (5,),
            },
            "recurrence precedes",
        ),
        (
            {
                "predicted_drift_kind": AssuranceDriftKind.OWNER,
                "finding_opened_tick": 5,
                "finding_cleared_ticks": (8,),
                "recurrence_opened_ticks": (8,),
            },
            "lifecycle ticks must be unique",
        ),
    ],
)
def test_prediction_rows_reject_incoherent_lifecycles(
    updates: dict[str, object], message: str
) -> None:
    row = ContinuousAssurancePredictionRowV1(case_id="case")
    with pytest.raises(ValidationError, match=message):
        _revalidate(row, updates)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"support": 2, "denominator": 1}, "support exceeds"),
        ({"numerator": 2, "denominator": 1}, "numerator exceeds"),
        (
            {"value": 0.0, "numerator": 0, "denominator": 0, "support": 0},
            "empty metric",
        ),
        ({"value": None}, "value differs"),
        ({"value": 0.5}, "value differs"),
    ],
)
def test_metric_counts_determine_the_exact_value(
    updates: dict[str, object], message: str
) -> None:
    metric = ContinuousAssuranceMetricV1(
        family=ContinuousAssuranceMetricFamily.DETECTION,
        name="metric",
        aggregation=ContinuousAssuranceMetricAggregation.RATIO,
        value=1.0,
        numerator=1,
        denominator=1,
        support=1,
        denominator_meaning="cases",
    )
    with pytest.raises(ValidationError, match=message):
        _revalidate(metric, updates)


def test_empty_and_mean_tick_metrics_have_explicit_semantics() -> None:
    empty = ContinuousAssuranceMetricV1(
        family=ContinuousAssuranceMetricFamily.RECURRENCE,
        name="empty",
        aggregation=ContinuousAssuranceMetricAggregation.RATIO,
        value=None,
        numerator=0,
        denominator=0,
        support=0,
        denominator_meaning="submitted recurrences",
    )
    mean = ContinuousAssuranceMetricV1(
        family=ContinuousAssuranceMetricFamily.DETECTION,
        name="latency",
        aggregation=ContinuousAssuranceMetricAggregation.MEAN_TICKS,
        value=5.0,
        numerator=10,
        denominator=2,
        support=2,
        denominator_meaning="detections",
    )
    assert empty.value is None
    assert mean.value == 5.0
