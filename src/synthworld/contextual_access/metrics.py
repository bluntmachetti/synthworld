"""Independent denominator-bearing metrics for contextual-access predictions."""

from __future__ import annotations

from collections.abc import Callable, Collection

from synthworld.contextual_access.models import (
    ContextualAccessCaseTruthV1,
    ContextualAccessEvaluatorV1,
    ContextualAccessMetricsV1,
    ContextualAccessPredictionV1,
    ContextualAccessPublicV1,
    ContextualAccessTraceRowV1,
    ContextualCaseKind,
    ContextualPredicatePredictionV1,
    HasActiveCaseAssignmentV1,
    HasValidBusinessJustificationV1,
)
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.rbac.common import MetricEmptyBehaviour
from synthworld.enterprise.rbac.metrics import EnterpriseAuthorizationMetricV1


class ContextualAccessEvaluationError(ValueError):
    """Raised when a prediction cannot be scored against bound truth."""


def perfect_contextual_access_prediction(
    *,
    public: ContextualAccessPublicV1,
    evaluator: ContextualAccessEvaluatorV1,
) -> ContextualAccessPredictionV1:
    """Build a full reference prediction for scorer and schema conformance."""

    benchmark_digest = evaluator.truth.benchmark_digest
    requests = {item.request_id: item for item in public.requests}
    rows = tuple(
        ContextualAccessTraceRowV1(
            benchmark_digest=benchmark_digest,
            request_id=case.request_id,
            decision=case.canonical.decision,
            predicate_outcomes=tuple(
                ContextualPredicatePredictionV1(
                    predicate_id=item.predicate_id,
                    outcome=item.outcome,
                )
                for item in case.canonical.predicate_outcomes
            ),
            applied_event_ids=tuple(
                event.id
                for event in public.events
                if event.effective_tick <= requests[case.request_id].request_tick
            ),
            evidence_refs=case.required_evidence_refs,
        )
        for case in evaluator.truth.cases
    )
    return ContextualAccessPredictionV1(
        benchmark_digest=benchmark_digest,
        rows=rows,
    )


def evaluate_contextual_access_prediction(
    *,
    public: ContextualAccessPublicV1,
    evaluator: ContextualAccessEvaluatorV1,
    prediction: ContextualAccessPredictionV1,
) -> ContextualAccessMetricsV1:
    """Score decisions, predicate semantics, freshness, idempotency, and evidence."""

    expected_digest = evaluator.truth.benchmark_digest
    if prediction.benchmark_digest != expected_digest or any(
        item.benchmark_digest != expected_digest for item in prediction.rows
    ):
        raise ContextualAccessEvaluationError(
            "contextual prediction benchmark digest differs"
        )
    truth = {item.request_id: item for item in evaluator.truth.cases}
    rows = {item.request_id: item for item in prediction.rows}
    requests = {item.request_id: item for item in public.requests}
    labels = {item.request_id: item.kind for item in evaluator.truth.case_labels}
    if set(rows) != set(truth):
        raise ContextualAccessEvaluationError(
            "contextual prediction must cover every request exactly once"
        )
    if set(requests) != set(truth) or set(labels) != set(truth):
        raise ContextualAccessEvaluationError(
            "contextual public/evaluator request inventory differs"
        )
    request_ids = tuple(sorted(truth))
    stale = tuple(item for item in request_ids if truth[item].stale_context)
    transitions = tuple(
        item
        for item in request_ids
        if labels[item]
        not in {ContextualCaseKind.STATIC_ALLOW, ContextualCaseKind.STATIC_DENY}
    )
    idempotency = tuple(
        item
        for item in request_ids
        if labels[item]
        in {
            ContextualCaseKind.DUPLICATE_DELIVERY,
            ContextualCaseKind.OUT_OF_ORDER_DELIVERY,
        }
    )
    expected_events = {
        request_id: {
            event.id
            for event in public.events
            if event.effective_tick <= requests[request_id].request_tick
        }
        for request_id in request_ids
    }
    metrics = [
        _accuracy(
            family="decision",
            name="decision_accuracy",
            items=request_ids,
            check=lambda request_id: (
                rows[request_id].decision == truth[request_id].canonical.decision
            ),
            meaning="contextual requests with canonical expected decisions",
        ),
        _accuracy(
            family="decision",
            name="transition_decision_accuracy",
            items=transitions,
            check=lambda request_id: (
                rows[request_id].decision == truth[request_id].canonical.decision
            ),
            meaning="contextual requests attached to a transition case",
        ),
        _accuracy(
            family="freshness",
            name="stale_context_decision_accuracy",
            items=stale,
            check=lambda request_id: (
                rows[request_id].decision == truth[request_id].canonical.decision
            ),
            meaning="requests where presented-feed and canonical decisions differ",
        ),
        _accuracy(
            family="freshness",
            name="canonical_event_application_exact_match",
            items=request_ids,
            check=lambda request_id: (
                set(rows[request_id].applied_event_ids) == expected_events[request_id]
            ),
            meaning="requests with a canonical effective event-prefix truth",
        ),
        _accuracy(
            family="delivery",
            name="idempotent_or_reordered_decision_accuracy",
            items=idempotency,
            check=lambda request_id: (
                rows[request_id].decision == truth[request_id].canonical.decision
            ),
            meaning="duplicate-delivery and out-of-order-delivery requests",
        ),
    ]
    metrics.extend(_predicate_metrics(public, request_ids, rows, truth))
    metrics.extend(_evidence_metrics(request_ids, rows, truth))
    return ContextualAccessMetricsV1(
        benchmark_digest=expected_digest,
        truth_digest=synthetic_digest(canonical_json_bytes(evaluator.truth)),
        metrics=tuple(metrics),
    )


def _predicate_metrics(
    public: ContextualAccessPublicV1,
    request_ids: tuple[str, ...],
    rows: dict[str, ContextualAccessTraceRowV1],
    truth: dict[str, ContextualAccessCaseTruthV1],
) -> tuple[EnterpriseAuthorizationMetricV1, ...]:
    expected = {
        request_id: {
            item.predicate_id: item.outcome
            for item in truth[request_id].canonical.predicate_outcomes
        }
        for request_id in request_ids
    }
    predicted = {
        request_id: {
            item.predicate_id: item.outcome
            for item in rows[request_id].predicate_outcomes
        }
        for request_id in request_ids
    }
    pairs = tuple(
        (request_id, predicate_id)
        for request_id in request_ids
        for predicate_id in expected[request_id]
    )
    relationship_ids = {
        predicate.predicate_id
        for policy in public.policies
        for rule in policy.rules
        for predicate in rule.predicates
        if isinstance(
            predicate,
            (HasActiveCaseAssignmentV1, HasValidBusinessJustificationV1),
        )
    }
    relationship_pairs = tuple(item for item in pairs if item[1] in relationship_ids)
    return (
        _accuracy(
            family="predicate",
            name="predicate_outcome_accuracy",
            items=pairs,
            check=lambda item: (
                predicted[item[0]].get(item[1]) == expected[item[0]][item[1]]
            ),
            meaning="applicable public contextual predicate evaluations",
        ),
        _accuracy(
            family="relationship",
            name="relationship_predicate_accuracy",
            items=relationship_pairs,
            check=lambda item: (
                predicted[item[0]].get(item[1]) == expected[item[0]][item[1]]
            ),
            meaning="assignment and justification relationship predicates",
        ),
    )


def _evidence_metrics(
    request_ids: tuple[str, ...],
    rows: dict[str, ContextualAccessTraceRowV1],
    truth: dict[str, ContextualAccessCaseTruthV1],
) -> tuple[EnterpriseAuthorizationMetricV1, ...]:
    completeness = _accuracy(
        family="evidence",
        name="evidence_continuity",
        items=request_ids,
        check=lambda request_id: (
            set(truth[request_id].required_evidence_refs)
            <= set(rows[request_id].evidence_refs)
        ),
        meaning="contextual requests with required evidence-reference truth",
    )
    submitted = sum(len(set(rows[item].evidence_refs)) for item in request_ids)
    correct = sum(
        len(set(rows[item].evidence_refs) & set(truth[item].required_evidence_refs))
        for item in request_ids
    )
    precision = _ratio(
        family="evidence",
        name="evidence_precision",
        numerator=correct,
        denominator=submitted,
        meaning="distinct submitted contextual evidence references",
    )
    return completeness, precision


def _accuracy[ItemT](
    *,
    family: str,
    name: str,
    items: Collection[ItemT],
    check: Callable[[ItemT], bool],
    meaning: str,
) -> EnterpriseAuthorizationMetricV1:
    return _ratio(
        family=family,
        name=name,
        numerator=sum(check(item) for item in items),
        denominator=len(items),
        meaning=meaning,
    )


def _ratio(
    *,
    family: str,
    name: str,
    numerator: int,
    denominator: int,
    meaning: str,
) -> EnterpriseAuthorizationMetricV1:
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


__all__ = [
    "ContextualAccessEvaluationError",
    "evaluate_contextual_access_prediction",
    "perfect_contextual_access_prediction",
]
