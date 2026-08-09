"""Independent C08 evidence-quality metrics with honest offline scope."""

from __future__ import annotations

import hashlib

from synthworld.enterprise.canonical import canonical_json_bytes

from synthworld.agentic.c08_v2.models import (
    C08_METRIC_NAMES,
    C08AsteriaBenchmarkV2,
    C08AsteriaSubmissionV2,
    C08MetricV2,
    C08MetricsReportV2,
)


class C08EvaluationError(ValueError):
    """Raised when a submission cannot be aligned to the public action universe."""


def _metric(
    name: str,
    passed: tuple[bool, ...],
    denominator_meaning: str,
) -> C08MetricV2:
    denominator = len(passed)
    numerator = sum(passed)
    return C08MetricV2(
        name=name,
        numerator=numerator,
        denominator=denominator,
        value=numerator / denominator if denominator else None,
        denominator_meaning=denominator_meaning,
        undefined_reason="no submitted evidence-bearing action rows"
        if not denominator
        else None,
    )


def evaluate_c08_submission(
    benchmark: C08AsteriaBenchmarkV2,
    submission: C08AsteriaSubmissionV2,
) -> C08MetricsReportV2:
    """Evaluate only what offline public/evaluator artifacts can establish."""

    if submission.benchmark_id != benchmark.benchmark_id:
        raise C08EvaluationError("C08 submission benchmark id differs")
    public_digest = hashlib.sha256(canonical_json_bytes(benchmark.public)).hexdigest()
    if submission.public_input_digest != public_digest:
        raise C08EvaluationError("C08 submission/public digest binding differs")
    action_ids = tuple(item.action_event_id for item in benchmark.public.actions)
    rows = {item.action_event_id: set(item.retained_observation_ids) for item in submission.rows}
    expected = set(action_ids)
    actual = set(rows)
    if actual != expected:
        raise C08EvaluationError(
            f"C08 submission must cover each public action once; missing={sorted(expected - actual)}, "
            f"unknown={sorted(actual - expected)}"
        )
    bindings = {item.action_event_id: item for item in benchmark.evaluator.bindings}
    observations = {
        item.observation_id: item for item in benchmark.public.evidence_observations
    }
    active_ids = tuple(action_id for action_id in action_ids if rows[action_id])

    exact = tuple(
        rows[action_id] == set(bindings[action_id].required_observation_ids)
        for action_id in action_ids
    )
    missing_or_discarded = tuple(
        set(bindings[action_id].required_observation_ids) <= rows[action_id]
        for action_id in action_ids
    )
    fabricated_free = tuple(
        rows[action_id] <= observations.keys() for action_id in active_ids
    )
    wrong_action_free = tuple(
        all(observations[item].action_event_id == action_id for item in rows[action_id] if item in observations)
        for action_id in active_ids
    )
    extra_free = tuple(
        not (
            (
                rows[action_id]
                & {
                    item.observation_id
                    for item in benchmark.public.evidence_observations
                    if item.action_event_id == action_id
                }
            )
            - set(bindings[action_id].required_observation_ids)
        )
        for action_id in active_ids
    )
    metrics = (
        _metric("exact_evidence_match", exact, "all public action events"),
        _metric(
            "missing_or_discarded_free",
            missing_or_discarded,
            "all public action events with evaluator-required observations",
        ),
        _metric(
            "fabricated_evidence_free",
            fabricated_free,
            "action rows containing at least one submitted observation id",
        ),
        _metric(
            "wrong_action_evidence_free",
            wrong_action_free,
            "action rows containing at least one submitted observation id",
        ),
        _metric(
            "extra_evidence_free",
            extra_free,
            "action rows containing at least one submitted observation id",
        ),
    )
    if tuple(item.name for item in metrics) != C08_METRIC_NAMES:
        raise AssertionError("C08 metric construction order changed")
    return C08MetricsReportV2(
        public_input_digest=hashlib.sha256(
            canonical_json_bytes(benchmark.public)
        ).hexdigest(),
        measurement_scope=benchmark.public.measurement_scope,
        metrics=metrics,
    )


__all__ = ["C08EvaluationError", "evaluate_c08_submission"]
