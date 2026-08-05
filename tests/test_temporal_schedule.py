"""Additive temporal schedule view compatibility and failure tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from synthworld.authority_governance.reference import (
    reference_authority_governance,
)
from synthworld.contextual_access.reference import reference_contextual_access
from synthworld.enterprise.canonical import canonical_json_bytes
from synthworld.temporal import TEMPORAL_SCHEMA_VERSION, materialise
from synthworld.temporal_generator import generate_temporal_world
from synthworld.temporal_schedule import (
    SELECTED_PRIVACY_TEMPORAL_SCHEMA_VERSION,
    ContextualTemporalPayloadV1,
    GovernanceTemporalPayloadV1,
    TemporalEventEnvelopeV1,
    TemporalPayloadFamilyV1,
    TemporalPayloadFamilyV2,
    TemporalScheduleError,
    TemporalScheduleV1,
    TemporalScheduleV2,
    compile_contextual_temporal_schedule,
    compile_contextual_temporal_schedule_v2,
    compile_governance_temporal_schedule,
    load_temporal_schedule,
    load_temporal_schedule_v1,
    load_temporal_schedule_v2,
    project_privacy_temporal_schedule,
    project_privacy_temporal_schedule_v2,
    temporal_schedule_bytes,
    temporal_schedule_v2_bytes,
    validate_contextual_temporal_schedule,
    validate_governance_temporal_schedule,
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


def test_v2_adds_only_governance_and_dispatches_without_relabeling_v1() -> None:
    governance = reference_authority_governance()
    assert set(TemporalPayloadFamilyV2) == {
        TemporalPayloadFamilyV2.PRIVACY_1_2,
        TemporalPayloadFamilyV2.CONTEXTUAL_ACCESS_1_0,
        TemporalPayloadFamilyV2.GOVERNANCE_1_0,
    }
    schedule = compile_governance_temporal_schedule(
        events=governance.public.events,
        event_schedule_version=governance.public.event_schedule_version,
    )
    assert schedule == governance.public.schedule
    assert all(
        item.payload_family is TemporalPayloadFamilyV2.GOVERNANCE_1_0
        for item in schedule
    )
    validate_governance_temporal_schedule(
        events=governance.public.events,
        envelopes=schedule,
        event_schedule_version=governance.public.event_schedule_version,
    )
    payload = temporal_schedule_v2_bytes(
        schedule,
        event_schedule_version=governance.public.event_schedule_version,
    )
    assert load_temporal_schedule_v2(payload).events == schedule
    assert load_temporal_schedule(payload).events == schedule
    event: GovernanceTemporalPayloadV1 = governance.public.events[0]
    assert event.id and event.effective_tick >= 0
    with pytest.raises(ValidationError):
        TemporalEventEnvelopeV1.model_validate(schedule[0].model_dump(mode="json"))

    contextual = reference_contextual_access()
    contextual_v2 = compile_contextual_temporal_schedule_v2(
        events=contextual.public.events,
        event_schedule_version="explicit-contextual-v2",
    )
    assert all(
        item.payload_family is TemporalPayloadFamilyV2.CONTEXTUAL_ACCESS_1_0
        for item in contextual_v2
    )
    world = generate_temporal_world(seed=15)
    privacy_v2 = project_privacy_temporal_schedule_v2(
        world=world,
        event_schedule_version="explicit-privacy-v2",
    )
    assert all(
        item.payload_family is TemporalPayloadFamilyV2.PRIVACY_1_2
        for item in privacy_v2
    )
    v1_payload = temporal_schedule_bytes((), event_schedule_version="still-v1")
    assert isinstance(load_temporal_schedule(v1_payload), TemporalScheduleV1)


def test_v2_compiler_loader_and_dispatch_reject_invalid_inputs() -> None:
    governance = reference_authority_governance()
    event = governance.public.events[0]
    with pytest.raises(TemporalScheduleError, match="version must not be empty"):
        compile_governance_temporal_schedule(events=(event,), event_schedule_version="")
    with pytest.raises(TemporalScheduleError, match="ids must be unique"):
        compile_governance_temporal_schedule(
            events=(event, event), event_schedule_version="duplicate-v2"
        )
    with pytest.raises(TemporalScheduleError, match="differs"):
        validate_governance_temporal_schedule(
            events=(event,),
            envelopes=(),
            event_schedule_version="mismatch-v2",
        )
    with pytest.raises(TemporalScheduleError, match="invalid"):
        load_temporal_schedule_v2(b"{")
    valid = temporal_schedule_v2_bytes((), event_schedule_version="empty-v2")
    with pytest.raises(TemporalScheduleError, match="not canonical"):
        load_temporal_schedule_v2(b" " + valid)
    for payload, message in (
        (b"\xff", "not a JSON object"),
        (b"[]\n", "no string schema_version"),
        (b'{"schema_version":1}\n', "no string schema_version"),
        (b'{"schema_version":"3.0.0"}\n', "unsupported"),
    ):
        with pytest.raises(TemporalScheduleError, match=message):
            load_temporal_schedule(payload)
    world = generate_temporal_world(seed=16).model_copy(
        update={"schema_version": "1.1.0"}
    )
    with pytest.raises(TemporalScheduleError, match=r"selected 1\.2\.0"):
        project_privacy_temporal_schedule_v2(
            world=world,
            event_schedule_version="wrong-privacy-v2",
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("duplicate", "duplicate_event_id"),
        ("order", "event_order_mismatch"),
        ("index", "event_index_mismatch"),
        ("version", "version_binding_mismatch"),
    ],
)
def test_v2_schedule_model_rejects_each_structural_corruption(
    mutation: str, message: str
) -> None:
    governance = reference_authority_governance()
    schedule = TemporalScheduleV2(
        event_schedule_version=governance.public.event_schedule_version,
        events=governance.public.schedule,
    )
    value = schedule.model_dump(mode="json")
    events = list(value["events"])
    if mutation == "duplicate":
        events[1]["event_id"] = events[0]["event_id"]
    elif mutation == "order":
        events[0], events[1] = events[1], events[0]
    elif mutation == "index":
        events[0]["event_index"] = 4
    else:
        events[0]["event_schedule_version"] = "other"
    value["events"] = events
    with pytest.raises(ValidationError, match=message):
        TemporalScheduleV2.model_validate(value)


def test_temporal_v1_generated_schema_bytes_remain_unchanged() -> None:
    expected = {
        "temporal-event-envelope-v1.schema.json": (
            "63174bf57b2bac46626b981dda0ed80e0edbb0e9651a917b322243dbcb0e0d3a"
        ),
        "temporal-schedule-v1.schema.json": (
            "4d5196d8e1e30aa7f06b1c3a3c57666c903095c08ba4318101a491a5c01abc0e"
        ),
    }
    for name, digest in expected.items():
        payload = Path("contextual-access-contract/schemas") / name
        assert hashlib.sha256(payload.read_bytes()).hexdigest() == digest
