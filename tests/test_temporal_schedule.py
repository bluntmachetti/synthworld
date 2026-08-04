"""Additive temporal schedule view compatibility and failure tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from synthworld.contextual_access.reference import reference_contextual_access
from synthworld.enterprise.canonical import canonical_json_bytes
from synthworld.temporal import TEMPORAL_SCHEMA_VERSION, materialise
from synthworld.temporal_generator import generate_temporal_world
from synthworld.temporal_schedule import (
    SELECTED_PRIVACY_TEMPORAL_SCHEMA_VERSION,
    ContextualTemporalPayloadV1,
    TemporalEventEnvelopeV1,
    TemporalPayloadFamilyV1,
    TemporalScheduleError,
    TemporalScheduleV1,
    compile_contextual_temporal_schedule,
    load_temporal_schedule_v1,
    project_privacy_temporal_schedule,
    temporal_schedule_bytes,
    validate_contextual_temporal_schedule,
    validate_privacy_temporal_schedule,
)

TEMPORAL_SOURCE_SHA256 = (
    "c994fa6fdfea7b77ac7c3c35b524da6c3538bc04c84af0c192f366bfd17c8f59"
)


def test_selected_temporal_base_is_byte_preserved_and_prefix_equivalent() -> None:
    assert (
        TEMPORAL_SCHEMA_VERSION == SELECTED_PRIVACY_TEMPORAL_SCHEMA_VERSION == "1.2.0"
    )
    assert (
        hashlib.sha256(Path("src/synthworld/temporal.py").read_bytes()).hexdigest()
        == TEMPORAL_SOURCE_SHA256
    )
    world = generate_temporal_world(seed=13)
    schedule = project_privacy_temporal_schedule(
        world=world,
        event_schedule_version="privacy-reference-1",
    )
    validate_privacy_temporal_schedule(
        events=world.events,
        envelopes=schedule,
        event_schedule_version="privacy-reference-1",
    )
    assert tuple(item.payload_family for item in schedule) == (
        TemporalPayloadFamilyV1.PRIVACY_1_2,
    ) * len(schedule)
    assert tuple(item.event_index for item in schedule) == tuple(range(len(schedule)))
    for tick in range(world.horizon + 1):
        native = tuple(item.id for item in materialise(world, as_of=tick).events)
        projected = tuple(
            item.event_id for item in schedule if item.effective_tick <= tick
        )
        assert projected == native


def test_contextual_schedule_round_trip_and_separately_typed_payload_binding() -> None:
    reference = reference_contextual_access()
    schedule = compile_contextual_temporal_schedule(
        events=reference.public.events,
        event_schedule_version=reference.public.benchmark.event_schedule_version,
    )
    assert schedule == reference.public.schedule
    assert all(
        item.payload_family is TemporalPayloadFamilyV1.CONTEXTUAL_ACCESS_1_0
        for item in schedule
    )
    validate_contextual_temporal_schedule(
        events=reference.public.events,
        envelopes=schedule,
        event_schedule_version=reference.public.benchmark.event_schedule_version,
    )
    payload = temporal_schedule_bytes(
        schedule,
        event_schedule_version=reference.public.benchmark.event_schedule_version,
    )
    parsed = load_temporal_schedule_v1(payload)
    assert parsed.events == schedule
    assert payload == canonical_json_bytes(parsed)
    assert b"UTC" not in payload and b"timestamp" not in payload


def test_schedule_compiler_and_loader_reject_wrong_bindings() -> None:
    reference = reference_contextual_access()
    event = reference.public.events[0]
    with pytest.raises(TemporalScheduleError, match="version must not be empty"):
        compile_contextual_temporal_schedule(events=(event,), event_schedule_version="")
    with pytest.raises(TemporalScheduleError, match="ids must be unique"):
        compile_contextual_temporal_schedule(
            events=(event, event),
            event_schedule_version="duplicate",
        )
    with pytest.raises(TemporalScheduleError, match="differs"):
        validate_contextual_temporal_schedule(
            events=(event,),
            envelopes=(),
            event_schedule_version="mismatch",
        )
    world = generate_temporal_world(seed=14)
    wrong_world = world.model_copy(update={"schema_version": "1.1.0"})
    with pytest.raises(TemporalScheduleError, match=r"selected 1\.2\.0"):
        project_privacy_temporal_schedule(
            world=wrong_world,
            event_schedule_version="privacy-reference-1",
        )
    with pytest.raises(TemporalScheduleError, match="differs"):
        validate_privacy_temporal_schedule(
            events=world.events,
            envelopes=(),
            event_schedule_version="privacy-reference-1",
        )
    with pytest.raises(TemporalScheduleError, match="invalid"):
        load_temporal_schedule_v1(b"{")
    valid = temporal_schedule_bytes((), event_schedule_version="empty-v1")
    with pytest.raises(TemporalScheduleError, match="not canonical"):
        load_temporal_schedule_v1(b" " + valid)


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"events": None}, "input"),
        ({"events": "duplicate"}, "duplicate_event_id"),
        ({"events": "order"}, "event_order_mismatch"),
        ({"events": "index"}, "event_index_mismatch"),
        ({"events": "version"}, "version_binding_mismatch"),
    ],
)
def test_schedule_model_rejects_each_structural_corruption(
    update: dict[str, object], message: str
) -> None:
    reference = reference_contextual_access()
    schedule = TemporalScheduleV1(
        event_schedule_version=reference.public.benchmark.event_schedule_version,
        events=reference.public.schedule,
    )
    value = schedule.model_dump(mode="json")
    mutation = update["events"]
    events = list(value["events"])
    if mutation == "duplicate":
        events[1]["event_id"] = events[0]["event_id"]
    elif mutation == "order":
        events[0], events[1] = events[1], events[0]
    elif mutation == "index":
        events[0]["event_index"] = 9
    elif mutation == "version":
        events[0]["event_schedule_version"] = "other"
    else:
        value["events"] = mutation
    if mutation is not None:
        value["events"] = events
    with pytest.raises(ValidationError, match=message):
        TemporalScheduleV1.model_validate(value)


def test_envelope_closed_family_and_protocol_shape() -> None:
    assert set(TemporalPayloadFamilyV1) == {
        TemporalPayloadFamilyV1.PRIVACY_1_2,
        TemporalPayloadFamilyV1.CONTEXTUAL_ACCESS_1_0,
    }
    envelope = reference_contextual_access().public.schedule[0]
    invalid = envelope.model_dump(mode="json") | {"payload_family": "governance_1_0"}
    with pytest.raises(ValidationError):
        TemporalEventEnvelopeV1.model_validate(invalid)
    event: ContextualTemporalPayloadV1 = reference_contextual_access().public.events[0]
    assert event.id and event.effective_tick >= 0
