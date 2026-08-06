"""Additive schedule views over the shipped privacy tick contract.

This module does not introduce time.  ``effective_tick`` is a projection of the
selected family's existing integer tick and ``event_index`` is only the derived
position in canonical ``(effective_tick, event_id)`` order.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from enum import StrEnum
from typing import Literal, Protocol, Self, cast

from pydantic import BaseModel, Field, ValidationError, model_validator

from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.models import SyntheticModel
from synthworld.temporal import PrivacyEvent, TemporalWorld

TEMPORAL_SCHEDULE_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
TEMPORAL_SCHEDULE_SCHEMA_VERSION_V2: Literal["2.0.0"] = "2.0.0"
SELECTED_PRIVACY_TEMPORAL_SCHEMA_VERSION: Literal["1.2.0"] = "1.2.0"


class TemporalPayloadFamilyV1(StrEnum):
    """The two concrete payload families that justify schedule view v1."""

    PRIVACY_1_2 = "privacy_1_2"
    CONTEXTUAL_ACCESS_1_0 = "contextual_access_1_0"


class ContextualTemporalPayloadV1(Protocol):
    """Structural input boundary used without importing the contextual package."""

    id: str
    effective_tick: int


class GovernanceTemporalPayloadV1(Protocol):
    """Structural governance-event boundary without importing its package."""

    id: str
    effective_tick: int


class TemporalEventEnvelopeV1(SyntheticModel):
    """One payload digest positioned on the sole integer-tick schedule."""

    schema_version: Literal["1.0.0"] = TEMPORAL_SCHEDULE_SCHEMA_VERSION
    event_id: str = Field(min_length=1)
    effective_tick: int = Field(ge=0)
    event_index: int = Field(ge=0)
    event_schedule_version: str = Field(min_length=1)
    payload_family: TemporalPayloadFamilyV1
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class TemporalScheduleV1(SyntheticModel):
    """Canonical persisted wrapper for a v1 schedule view."""

    schema_version: Literal["1.0.0"] = TEMPORAL_SCHEDULE_SCHEMA_VERSION
    event_schedule_version: str = Field(min_length=1)
    events: tuple[TemporalEventEnvelopeV1, ...]

    @model_validator(mode="after")
    def require_derived_canonical_positions(self) -> Self:
        identifiers = tuple(item.event_id for item in self.events)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("temporal_schedule_duplicate_event_id")
        keys = tuple((item.effective_tick, item.event_id) for item in self.events)
        if keys != tuple(sorted(keys)):
            raise ValueError("temporal_schedule_event_order_mismatch")
        if tuple(item.event_index for item in self.events) != tuple(
            range(len(self.events))
        ):
            raise ValueError("temporal_schedule_event_index_mismatch")
        if any(
            item.event_schedule_version != self.event_schedule_version
            for item in self.events
        ):
            raise ValueError("temporal_schedule_version_binding_mismatch")
        return self


class TemporalPayloadFamilyV2(StrEnum):
    """The v1 families plus the independently typed governance family."""

    PRIVACY_1_2 = "privacy_1_2"
    CONTEXTUAL_ACCESS_1_0 = "contextual_access_1_0"
    GOVERNANCE_1_0 = "governance_1_0"


class TemporalEventEnvelopeV2(SyntheticModel):
    """Versioned schedule position adding only the governance family."""

    schema_version: Literal["2.0.0"] = TEMPORAL_SCHEDULE_SCHEMA_VERSION_V2
    event_id: str = Field(min_length=1)
    effective_tick: int = Field(ge=0)
    event_index: int = Field(ge=0)
    event_schedule_version: str = Field(min_length=1)
    payload_family: TemporalPayloadFamilyV2
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class TemporalScheduleV2(SyntheticModel):
    """Canonical persisted wrapper for the explicit v2 schedule view."""

    schema_version: Literal["2.0.0"] = TEMPORAL_SCHEDULE_SCHEMA_VERSION_V2
    event_schedule_version: str = Field(min_length=1)
    events: tuple[TemporalEventEnvelopeV2, ...]

    @model_validator(mode="after")
    def require_derived_canonical_positions(self) -> Self:
        identifiers = tuple(item.event_id for item in self.events)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("temporal_schedule_duplicate_event_id")
        keys = tuple((item.effective_tick, item.event_id) for item in self.events)
        if keys != tuple(sorted(keys)):
            raise ValueError("temporal_schedule_event_order_mismatch")
        if tuple(item.event_index for item in self.events) != tuple(
            range(len(self.events))
        ):
            raise ValueError("temporal_schedule_event_index_mismatch")
        if any(
            item.event_schedule_version != self.event_schedule_version
            for item in self.events
        ):
            raise ValueError("temporal_schedule_version_binding_mismatch")
        return self


class TemporalScheduleError(ValueError):
    """Raised when a schedule view or its payload binding is invalid."""


def project_privacy_temporal_schedule(
    *, world: TemporalWorld, event_schedule_version: str
) -> tuple[TemporalEventEnvelopeV1, ...]:
    """Project privacy v1.2 events without modifying or relabeling their bytes."""

    if world.schema_version != SELECTED_PRIVACY_TEMPORAL_SCHEMA_VERSION:
        raise TemporalScheduleError(
            "privacy temporal world does not match the selected 1.2.0 contract"
        )
    return _compile_records(
        ((event.id, event.tick, event) for event in world.events),
        family=TemporalPayloadFamilyV1.PRIVACY_1_2,
        event_schedule_version=event_schedule_version,
    )


def compile_contextual_temporal_schedule(
    *,
    events: Iterable[ContextualTemporalPayloadV1],
    event_schedule_version: str,
) -> tuple[TemporalEventEnvelopeV1, ...]:
    """Compile separately typed contextual events into the shared schedule view."""

    return _compile_records(
        ((event.id, event.effective_tick, cast(BaseModel, event)) for event in events),
        family=TemporalPayloadFamilyV1.CONTEXTUAL_ACCESS_1_0,
        event_schedule_version=event_schedule_version,
    )


def validate_privacy_temporal_schedule(
    *,
    events: tuple[PrivacyEvent, ...],
    envelopes: tuple[TemporalEventEnvelopeV1, ...],
    event_schedule_version: str,
) -> None:
    """Verify every privacy envelope against its separately typed payload."""

    expected = _compile_records(
        ((event.id, event.tick, event) for event in events),
        family=TemporalPayloadFamilyV1.PRIVACY_1_2,
        event_schedule_version=event_schedule_version,
    )
    _require_same_schedule(expected, envelopes)


def validate_contextual_temporal_schedule(
    *,
    events: Iterable[ContextualTemporalPayloadV1],
    envelopes: tuple[TemporalEventEnvelopeV1, ...],
    event_schedule_version: str,
) -> None:
    """Verify every contextual envelope against its separately typed payload."""

    expected = compile_contextual_temporal_schedule(
        events=events,
        event_schedule_version=event_schedule_version,
    )
    _require_same_schedule(expected, envelopes)


def temporal_schedule_bytes(
    events: tuple[TemporalEventEnvelopeV1, ...], *, event_schedule_version: str
) -> bytes:
    """Serialize the canonical schedule wrapper as UTF-8 JSON with one LF."""

    return canonical_json_bytes(
        TemporalScheduleV1(
            event_schedule_version=event_schedule_version,
            events=events,
        )
    )


def load_temporal_schedule_v1(payload: bytes) -> TemporalScheduleV1:
    """Load only schedule v1 and reject non-canonical or cross-version bytes."""

    try:
        schedule = TemporalScheduleV1.model_validate_json(payload)
    except (ValueError, ValidationError) as error:
        raise TemporalScheduleError("temporal schedule v1 is invalid") from error
    if payload != canonical_json_bytes(schedule):
        raise TemporalScheduleError("temporal schedule v1 is not canonical JSON")
    return schedule


def project_privacy_temporal_schedule_v2(
    *, world: TemporalWorld, event_schedule_version: str
) -> tuple[TemporalEventEnvelopeV2, ...]:
    """Explicitly project privacy v1.2 events into schedule-view v2."""

    if world.schema_version != SELECTED_PRIVACY_TEMPORAL_SCHEMA_VERSION:
        raise TemporalScheduleError(
            "privacy temporal world does not match the selected 1.2.0 contract"
        )
    return _compile_records_v2(
        ((event.id, event.tick, event) for event in world.events),
        family=TemporalPayloadFamilyV2.PRIVACY_1_2,
        event_schedule_version=event_schedule_version,
    )


def compile_contextual_temporal_schedule_v2(
    *,
    events: Iterable[ContextualTemporalPayloadV1],
    event_schedule_version: str,
) -> tuple[TemporalEventEnvelopeV2, ...]:
    """Explicitly project contextual events into schedule-view v2."""

    return _compile_records_v2(
        ((event.id, event.effective_tick, cast(BaseModel, event)) for event in events),
        family=TemporalPayloadFamilyV2.CONTEXTUAL_ACCESS_1_0,
        event_schedule_version=event_schedule_version,
    )


def compile_governance_temporal_schedule(
    *,
    events: Iterable[GovernanceTemporalPayloadV1],
    event_schedule_version: str,
) -> tuple[TemporalEventEnvelopeV2, ...]:
    """Compile independently typed governance events into schedule-view v2."""

    return _compile_records_v2(
        ((event.id, event.effective_tick, cast(BaseModel, event)) for event in events),
        family=TemporalPayloadFamilyV2.GOVERNANCE_1_0,
        event_schedule_version=event_schedule_version,
    )


def validate_governance_temporal_schedule(
    *,
    events: Iterable[GovernanceTemporalPayloadV1],
    envelopes: tuple[TemporalEventEnvelopeV2, ...],
    event_schedule_version: str,
) -> None:
    """Verify every governance envelope against its separate payload."""

    expected = compile_governance_temporal_schedule(
        events=events,
        event_schedule_version=event_schedule_version,
    )
    _require_same_schedule_v2(expected, envelopes)


def temporal_schedule_v2_bytes(
    events: tuple[TemporalEventEnvelopeV2, ...], *, event_schedule_version: str
) -> bytes:
    """Serialize a canonical schedule-v2 wrapper with one trailing LF."""

    return canonical_json_bytes(
        TemporalScheduleV2(
            event_schedule_version=event_schedule_version,
            events=events,
        )
    )


def load_temporal_schedule_v2(payload: bytes) -> TemporalScheduleV2:
    """Load only schedule v2 and reject non-canonical or cross-version bytes."""

    try:
        schedule = TemporalScheduleV2.model_validate_json(payload)
    except (ValueError, ValidationError) as error:
        raise TemporalScheduleError("temporal schedule v2 is invalid") from error
    if payload != canonical_json_bytes(schedule):
        raise TemporalScheduleError("temporal schedule v2 is not canonical JSON")
    return schedule


def load_temporal_schedule(payload: bytes) -> TemporalScheduleV1 | TemporalScheduleV2:
    """Dispatch only the two explicitly supported schedule-view versions."""

    try:
        parsed = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise TemporalScheduleError("temporal schedule is not a JSON object") from error
    if not isinstance(parsed, dict) or not isinstance(
        parsed.get("schema_version"), str
    ):
        raise TemporalScheduleError("temporal schedule has no string schema_version")
    version = parsed["schema_version"]
    if version == TEMPORAL_SCHEDULE_SCHEMA_VERSION:
        return load_temporal_schedule_v1(payload)
    if version == TEMPORAL_SCHEDULE_SCHEMA_VERSION_V2:
        return load_temporal_schedule_v2(payload)
    raise TemporalScheduleError(f"unsupported temporal schedule version: {version}")


def _compile_records(
    records: Iterable[tuple[str, int, BaseModel]],
    *,
    family: TemporalPayloadFamilyV1,
    event_schedule_version: str,
) -> tuple[TemporalEventEnvelopeV1, ...]:
    if not event_schedule_version:
        raise TemporalScheduleError("event schedule version must not be empty")
    materialized = tuple(records)
    identifiers = tuple(item[0] for item in materialized)
    if len(identifiers) != len(set(identifiers)):
        raise TemporalScheduleError("temporal schedule event ids must be unique")
    ordered = tuple(sorted(materialized, key=lambda item: (item[1], item[0])))
    envelopes = tuple(
        TemporalEventEnvelopeV1(
            event_id=event_id,
            effective_tick=effective_tick,
            event_index=index,
            event_schedule_version=event_schedule_version,
            payload_family=family,
            payload_sha256=synthetic_digest(canonical_json_bytes(payload)).value,
        )
        for index, (event_id, effective_tick, payload) in enumerate(ordered)
    )
    TemporalScheduleV1(
        event_schedule_version=event_schedule_version,
        events=envelopes,
    )
    return envelopes


def _require_same_schedule(
    expected: tuple[TemporalEventEnvelopeV1, ...],
    actual: tuple[TemporalEventEnvelopeV1, ...],
) -> None:
    if actual != expected:
        raise TemporalScheduleError(
            "temporal schedule differs from canonical payload bindings"
        )


def _compile_records_v2(
    records: Iterable[tuple[str, int, BaseModel]],
    *,
    family: TemporalPayloadFamilyV2,
    event_schedule_version: str,
) -> tuple[TemporalEventEnvelopeV2, ...]:
    if not event_schedule_version:
        raise TemporalScheduleError("event schedule version must not be empty")
    materialized = tuple(records)
    identifiers = tuple(item[0] for item in materialized)
    if len(identifiers) != len(set(identifiers)):
        raise TemporalScheduleError("temporal schedule event ids must be unique")
    ordered = tuple(sorted(materialized, key=lambda item: (item[1], item[0])))
    envelopes = tuple(
        TemporalEventEnvelopeV2(
            event_id=event_id,
            effective_tick=effective_tick,
            event_index=index,
            event_schedule_version=event_schedule_version,
            payload_family=family,
            payload_sha256=synthetic_digest(canonical_json_bytes(payload)).value,
        )
        for index, (event_id, effective_tick, payload) in enumerate(ordered)
    )
    TemporalScheduleV2(
        event_schedule_version=event_schedule_version,
        events=envelopes,
    )
    return envelopes


def _require_same_schedule_v2(
    expected: tuple[TemporalEventEnvelopeV2, ...],
    actual: tuple[TemporalEventEnvelopeV2, ...],
) -> None:
    if actual != expected:
        raise TemporalScheduleError(
            "temporal schedule differs from canonical payload bindings"
        )


__all__ = [
    "SELECTED_PRIVACY_TEMPORAL_SCHEMA_VERSION",
    "TEMPORAL_SCHEDULE_SCHEMA_VERSION",
    "TEMPORAL_SCHEDULE_SCHEMA_VERSION_V2",
    "ContextualTemporalPayloadV1",
    "GovernanceTemporalPayloadV1",
    "TemporalEventEnvelopeV1",
    "TemporalEventEnvelopeV2",
    "TemporalPayloadFamilyV1",
    "TemporalPayloadFamilyV2",
    "TemporalScheduleError",
    "TemporalScheduleV1",
    "TemporalScheduleV2",
    "compile_contextual_temporal_schedule",
    "compile_contextual_temporal_schedule_v2",
    "compile_governance_temporal_schedule",
    "load_temporal_schedule",
    "load_temporal_schedule_v1",
    "load_temporal_schedule_v2",
    "project_privacy_temporal_schedule",
    "project_privacy_temporal_schedule_v2",
    "temporal_schedule_bytes",
    "temporal_schedule_v2_bytes",
    "validate_contextual_temporal_schedule",
    "validate_governance_temporal_schedule",
    "validate_privacy_temporal_schedule",
]
