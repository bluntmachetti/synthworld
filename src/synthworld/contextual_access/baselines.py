"""Deliberately weak contextual-access baselines for discrimination tests."""

from __future__ import annotations

from collections.abc import Callable

from synthworld.contextual_access.metrics import perfect_contextual_access_prediction
from synthworld.contextual_access.models import (
    ContextualAccessEvaluatorV1,
    ContextualAccessPredictionV1,
    ContextualAccessPublicV1,
    ContextualAccessTraceRowV1,
    ContextualPredicatePredictionV1,
    ContextualPredicateTruth,
)
from synthworld.contextual_access.policy import evaluate_contextual_request
from synthworld.contextual_access.replay import (
    active_contextual_facts,
    materialize_contextual_state,
)


def ignore_context_prediction(
    *,
    public: ContextualAccessPublicV1,
    evaluator: ContextualAccessEvaluatorV1,
) -> ContextualAccessPredictionV1:
    """Return canonical decisions but ignore all contextual predicate evidence."""

    perfect = perfect_contextual_access_prediction(public=public, evaluator=evaluator)
    return _replace_rows(
        perfect,
        lambda row: row.model_copy(
            update={
                "predicate_outcomes": tuple(
                    item.model_copy(
                        update={"outcome": ContextualPredicateTruth.UNKNOWN}
                    )
                    for item in row.predicate_outcomes
                )
            }
        ),
    )


def trust_presented_feed_prediction(
    *,
    public: ContextualAccessPublicV1,
    evaluator: ContextualAccessEvaluatorV1,
) -> ContextualAccessPredictionV1:
    """Treat the delivered feed as canonical even when delivery is stale."""

    perfect = perfect_contextual_access_prediction(public=public, evaluator=evaluator)
    cases = {item.request_id: item for item in evaluator.truth.cases}
    return _replace_rows(
        perfect,
        lambda row: row.model_copy(
            update={
                "decision": cases[row.request_id].presented_feed.decision,
                "predicate_outcomes": tuple(
                    ContextualPredicatePredictionV1(
                        predicate_id=item.predicate_id,
                        outcome=item.outcome,
                    )
                    for item in cases[row.request_id].presented_feed.predicate_outcomes
                ),
            }
        ),
    )


def initial_snapshot_only_prediction(
    *,
    public: ContextualAccessPublicV1,
    evaluator: ContextualAccessEvaluatorV1,
) -> ContextualAccessPredictionV1:
    """Evaluate validity at each request tick but never apply scheduled changes."""

    perfect = perfect_contextual_access_prediction(public=public, evaluator=evaluator)
    requests = {item.request_id: item for item in public.requests}
    initial_state = materialize_contextual_state(public.initial_facts, ())

    def transform(row: ContextualAccessTraceRowV1) -> ContextualAccessTraceRowV1:
        request = requests[row.request_id]
        decision = evaluate_contextual_request(
            active_facts=active_contextual_facts(
                initial_state,
                at_tick=request.request_tick,
            ),
            policies=public.policies,
            request=request,
        )
        return row.model_copy(
            update={
                "decision": decision.decision,
                "predicate_outcomes": tuple(
                    ContextualPredicatePredictionV1(
                        predicate_id=item.predicate_id,
                        outcome=item.outcome,
                    )
                    for item in decision.predicate_outcomes
                ),
                "applied_event_ids": (),
            }
        )

    return _replace_rows(perfect, transform)


def drop_delayed_events_prediction(
    *,
    public: ContextualAccessPublicV1,
    evaluator: ContextualAccessEvaluatorV1,
) -> ContextualAccessPredictionV1:
    """Permanently discard every event whose first delivery trails effective time."""

    first_delivery = {
        event.id: min(
            item.delivery_tick
            for item in public.delivery_attempts
            if item.event_id == event.id
        )
        for event in public.events
    }
    delayed_ids = {
        event.id
        for event in public.events
        if first_delivery[event.id] > event.effective_tick
    }
    retained = tuple(item for item in public.events if item.id not in delayed_ids)
    requests = {item.request_id: item for item in public.requests}
    perfect = perfect_contextual_access_prediction(public=public, evaluator=evaluator)

    def transform(row: ContextualAccessTraceRowV1) -> ContextualAccessTraceRowV1:
        request = requests[row.request_id]
        state = materialize_contextual_state(
            public.initial_facts,
            retained,
            as_of_tick=request.request_tick,
        )
        decision = evaluate_contextual_request(
            active_facts=active_contextual_facts(state, at_tick=request.request_tick),
            policies=public.policies,
            request=request,
        )
        return row.model_copy(
            update={
                "decision": decision.decision,
                "predicate_outcomes": tuple(
                    ContextualPredicatePredictionV1(
                        predicate_id=item.predicate_id,
                        outcome=item.outcome,
                    )
                    for item in decision.predicate_outcomes
                ),
                "applied_event_ids": tuple(
                    item.id
                    for item in retained
                    if item.effective_tick <= request.request_tick
                ),
            }
        )

    return _replace_rows(perfect, transform)


CONTEXTUAL_ACCESS_BASELINES: tuple[
    tuple[
        str,
        Callable[
            ...,
            ContextualAccessPredictionV1,
        ],
    ],
    ...,
] = (
    ("Ignore contextual predicates", ignore_context_prediction),
    ("Trust presented feed", trust_presented_feed_prediction),
    ("Initial snapshot only", initial_snapshot_only_prediction),
    ("Drop delayed events", drop_delayed_events_prediction),
)


def _replace_rows(
    prediction: ContextualAccessPredictionV1,
    transform: Callable[[ContextualAccessTraceRowV1], ContextualAccessTraceRowV1],
) -> ContextualAccessPredictionV1:
    return ContextualAccessPredictionV1(
        benchmark_digest=prediction.benchmark_digest,
        rows=tuple(transform(item) for item in prediction.rows),
    )


__all__ = [
    "CONTEXTUAL_ACCESS_BASELINES",
    "drop_delayed_events_prediction",
    "ignore_context_prediction",
    "initial_snapshot_only_prediction",
    "trust_presented_feed_prediction",
]
