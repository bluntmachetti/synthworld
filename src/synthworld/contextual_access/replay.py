"""Deterministic contextual fact replay on the repository's integer tick axis."""

from __future__ import annotations

from synthworld.contextual_access.models import (
    BusinessJustificationContextV1,
    CaseAssignmentContextV1,
    ContextDeliveryAttemptV1,
    ContextualAccessEventV1,
    ContextualCheckpointV1,
    ContextualFactV1,
    ContextualReplayStateV1,
    DevicePostureContextV1,
    OnCallContextV1,
    RiskSignalContextV1,
    canonical_model_tuple_bytes,
)
from synthworld.enterprise.canonical import synthetic_digest


class ContextualReplayError(ValueError):
    """Raised when a contextual history is incomplete or contradictory."""


def materialize_contextual_state(
    initial_facts: tuple[ContextualFactV1, ...],
    events: tuple[ContextualAccessEventV1, ...],
    *,
    as_of_tick: int | None = None,
    event_count: int | None = None,
) -> ContextualReplayStateV1:
    """Replay a canonical event prefix; requests at tick ``t`` see all events at t."""

    if as_of_tick is not None and event_count is not None:
        raise ContextualReplayError("choose an as-of tick or an event count, not both")
    if as_of_tick is not None and as_of_tick < 0:
        raise ContextualReplayError("contextual as-of tick cannot be negative")
    if event_count is not None and not 0 <= event_count <= len(events):
        raise ContextualReplayError("contextual event count is outside the schedule")
    _require_canonical_events(events)
    selected = (
        events[:event_count]
        if event_count is not None
        else tuple(
            event
            for event in events
            if as_of_tick is None or event.effective_tick <= as_of_tick
        )
    )
    latest, history, fact_ids = _initial_state(initial_facts)
    processed: list[str] = []
    for event in selected:
        fact = event.payload.fact
        if _fact_start(fact) != event.effective_tick:
            raise ContextualReplayError(
                "contextual event effective tick differs from its fact revision"
            )
        previous = latest.get(fact.fact_key)
        expected_revision = 0 if previous is None else previous.revision + 1
        if fact.revision != expected_revision:
            raise ContextualReplayError(
                "contextual fact revisions must be contiguous from zero"
            )
        if previous is not None and previous.fact_type is not fact.fact_type:
            raise ContextualReplayError(
                "contextual fact key changes type across revisions"
            )
        if fact.fact_id in fact_ids:
            raise ContextualReplayError("contextual fact ids must be unique")
        fact_ids.add(fact.fact_id)
        latest[fact.fact_key] = fact
        history.append(fact)
        processed.append(event.id)
    return ContextualReplayStateV1(
        processed_event_ids=tuple(processed),
        latest_facts=tuple(latest.values()),
        fact_history=tuple(history),
    )


def active_contextual_facts(
    state: ContextualReplayStateV1, *, at_tick: int
) -> tuple[ContextualFactV1, ...]:
    """Return only latest, non-tombstoned facts active in their half-open interval."""

    if at_tick < 0:
        raise ContextualReplayError("contextual active-state tick cannot be negative")
    return tuple(
        fact for fact in state.latest_facts if _fact_is_active(fact, at_tick=at_tick)
    )


def contextual_checkpoints(
    initial_facts: tuple[ContextualFactV1, ...],
    events: tuple[ContextualAccessEventV1, ...],
) -> tuple[ContextualCheckpointV1, ...]:
    """Materialize the exact state after every contiguous canonical prefix."""

    return tuple(
        _checkpoint(
            materialize_contextual_state(
                initial_facts,
                events,
                event_count=count,
            ),
            count=count,
        )
        for count in range(len(events) + 1)
    )


def presented_contextual_state(
    initial_facts: tuple[ContextualFactV1, ...],
    events: tuple[ContextualAccessEventV1, ...],
    attempts: tuple[ContextDeliveryAttemptV1, ...],
    *,
    as_of_tick: int,
) -> ContextualReplayStateV1:
    """Fold uniquely presented events canonically, never in delivery order."""

    if as_of_tick < 0:
        raise ContextualReplayError("contextual presentation tick cannot be negative")
    _require_canonical_events(events)
    _require_delivery_inventory(events, attempts)
    available = {item.event_id for item in attempts if item.delivery_tick <= as_of_tick}
    selected = tuple(event for event in events if event.id in available)
    return materialize_contextual_state(initial_facts, selected)


def _initial_state(
    initial_facts: tuple[ContextualFactV1, ...],
) -> tuple[dict[str, ContextualFactV1], list[ContextualFactV1], set[str]]:
    if any(
        fact.revision != 0 or fact.tombstone or _fact_start(fact) != 0
        for fact in initial_facts
    ):
        raise ContextualReplayError(
            "initial contextual facts must be live revision zero at tick zero"
        )
    keys = tuple(fact.fact_key for fact in initial_facts)
    identifiers = tuple(fact.fact_id for fact in initial_facts)
    if len(keys) != len(set(keys)) or len(identifiers) != len(set(identifiers)):
        raise ContextualReplayError(
            "initial contextual fact keys and ids must be unique"
        )
    return (
        {fact.fact_key: fact for fact in initial_facts},
        list(initial_facts),
        set(identifiers),
    )


def _require_canonical_events(events: tuple[ContextualAccessEventV1, ...]) -> None:
    identifiers = tuple(item.id for item in events)
    keys = tuple((item.effective_tick, item.id) for item in events)
    if len(identifiers) != len(set(identifiers)) or keys != tuple(sorted(keys)):
        raise ContextualReplayError(
            "contextual events must be unique and ordered by effective tick then id"
        )


def _require_delivery_inventory(
    events: tuple[ContextualAccessEventV1, ...],
    attempts: tuple[ContextDeliveryAttemptV1, ...],
) -> None:
    event_ids = {item.id for item in events}
    if any(item.event_id not in event_ids for item in attempts):
        raise ContextualReplayError("delivery attempt references an unknown event")
    ordered = tuple(
        sorted(
            attempts,
            key=lambda item: (
                item.delivery_tick,
                item.delivery_order,
                item.event_id,
                item.attempt_index,
            ),
        )
    )
    if attempts != ordered:
        raise ContextualReplayError("delivery attempts are not in presentation order")
    attempt_ids = tuple(item.attempt_id for item in attempts)
    if len(attempt_ids) != len(set(attempt_ids)):
        raise ContextualReplayError("delivery attempt ids must be unique")
    by_event: dict[str, list[int]] = {}
    for attempt in attempts:
        by_event.setdefault(attempt.event_id, []).append(attempt.attempt_index)
    if any(indices != list(range(len(indices))) for indices in by_event.values()):
        raise ContextualReplayError(
            "delivery attempt indices must be contiguous per event"
        )


def _checkpoint(
    state: ContextualReplayStateV1, *, count: int
) -> ContextualCheckpointV1:
    return ContextualCheckpointV1(
        event_count=count,
        event_ids=state.processed_event_ids,
        latest_facts=state.latest_facts,
        state_digest=synthetic_digest(canonical_model_tuple_bytes(state.latest_facts)),
    )


def _fact_start(fact: ContextualFactV1) -> int:
    if isinstance(fact, DevicePostureContextV1):
        return fact.observed_at_tick
    if isinstance(fact, RiskSignalContextV1):
        return fact.effective_from_tick
    if isinstance(
        fact,
        (
            CaseAssignmentContextV1,
            OnCallContextV1,
            BusinessJustificationContextV1,
        ),
    ):
        return fact.valid_from_tick
    raise ContextualReplayError("unsupported contextual fact type")


def _fact_end(fact: ContextualFactV1) -> int | None:
    if isinstance(fact, (DevicePostureContextV1, RiskSignalContextV1)):
        return fact.expires_at_tick
    if isinstance(
        fact,
        (
            CaseAssignmentContextV1,
            OnCallContextV1,
            BusinessJustificationContextV1,
        ),
    ):
        return fact.valid_until_tick
    raise ContextualReplayError("unsupported contextual fact type")


def _fact_is_active(fact: ContextualFactV1, *, at_tick: int) -> bool:
    end = _fact_end(fact)
    return (
        not fact.tombstone
        and _fact_start(fact) <= at_tick
        and (end is None or at_tick < end)
    )


__all__ = [
    "ContextualReplayError",
    "active_contextual_facts",
    "contextual_checkpoints",
    "materialize_contextual_state",
    "presented_contextual_state",
]
