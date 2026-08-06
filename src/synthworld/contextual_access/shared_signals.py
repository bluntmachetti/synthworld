"""Pure custom Shared Signals projection for contextual-access changes.

This module emits no SET and performs no transmission.  It declares that every
contextual event uses a SynthWorld custom event profile rather than mislabeling a
domain change as a standardized CAEP event type.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from synthworld.contextual_access.models import (
    ContextualAccessPublicV1,
    ContextualFactKind,
)
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.models import SyntheticDigestV1
from synthworld.enterprise.rbac.common import canonical_synthetic_records
from synthworld.models import SyntheticModel
from synthworld.temporal_schedule import TemporalPayloadFamilyV1

CONTEXTUAL_SHARED_SIGNALS_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
CONTEXTUAL_SHARED_SIGNALS_PROFILE_VERSION: Literal[
    "synthworld-contextual-shared-signals-1.0.0"
] = "synthworld-contextual-shared-signals-1.0.0"

_CUSTOM_EVENT_TYPES = {
    ContextualFactKind.CASE_ASSIGNMENT: (
        "urn:synthworld:event:contextual-case-assignment-change:1.0"
    ),
    ContextualFactKind.ON_CALL: "urn:synthworld:event:contextual-on-call-change:1.0",
    ContextualFactKind.DEVICE_POSTURE: (
        "urn:synthworld:event:contextual-device-posture-change:1.0"
    ),
    ContextualFactKind.RISK_SIGNAL: (
        "urn:synthworld:event:contextual-risk-signal-change:1.0"
    ),
    ContextualFactKind.BUSINESS_JUSTIFICATION: (
        "urn:synthworld:event:contextual-business-justification-change:1.0"
    ),
}


class ContextualSharedSignalsMappingV1(SyntheticModel):
    fact_type: ContextualFactKind
    custom_event_type: str = Field(min_length=1)
    standardized_caep_event_type: None = None
    classification: Literal["custom_profile"] = "custom_profile"
    semantic_delta: str = Field(min_length=1)


class ContextualSharedSignalsMappingProfileV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = CONTEXTUAL_SHARED_SIGNALS_SCHEMA_VERSION
    profile_version: Literal["synthworld-contextual-shared-signals-1.0.0"] = (
        CONTEXTUAL_SHARED_SIGNALS_PROFILE_VERSION
    )
    selected_temporal_base: Literal["synthworld-temporal-1.2.0"] = (
        "synthworld-temporal-1.2.0"
    )
    schedule_view_version: Literal["1.0.0"] = "1.0.0"
    mappings: tuple[ContextualSharedSignalsMappingV1, ...]

    @field_validator("mappings")
    @classmethod
    def complete_canonical_mappings(
        cls, value: tuple[ContextualSharedSignalsMappingV1, ...]
    ) -> tuple[ContextualSharedSignalsMappingV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.fact_type.value,) for item in value),
            description="contextual_shared_signals_fact_type",
        )

    @model_validator(mode="after")
    def complete_fact_vocabulary(self) -> Self:
        if tuple(item.fact_type for item in self.mappings) != tuple(
            sorted(ContextualFactKind, key=lambda item: item.value)
        ):
            raise ValueError("contextual shared-signals mapping profile is incomplete")
        if any(
            item.custom_event_type != _CUSTOM_EVENT_TYPES[item.fact_type]
            for item in self.mappings
        ):
            raise ValueError("contextual shared-signals custom event type differs")
        return self


class ContextualSharedSignalsEventV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = CONTEXTUAL_SHARED_SIGNALS_SCHEMA_VERSION
    profile_version: Literal["synthworld-contextual-shared-signals-1.0.0"] = (
        CONTEXTUAL_SHARED_SIGNALS_PROFILE_VERSION
    )
    event_id: str = Field(min_length=1)
    event_index: int = Field(ge=0)
    payload_family: Literal[TemporalPayloadFamilyV1.CONTEXTUAL_ACCESS_1_0] = (
        TemporalPayloadFamilyV1.CONTEXTUAL_ACCESS_1_0
    )
    native_fact_type: ContextualFactKind
    subject_id: str = Field(min_length=1)
    custom_event_type: str = Field(min_length=1)
    standardized_caep_event_type: None = None
    effective_tick: int = Field(ge=0)
    projected_event_tick: int = Field(ge=0)
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def pure_tick_projection(self) -> Self:
        if self.projected_event_tick != self.effective_tick:
            raise ValueError("shared-signals projection cannot change effective tick")
        if self.custom_event_type != _CUSTOM_EVENT_TYPES[self.native_fact_type]:
            raise ValueError("shared-signals projection custom event type differs")
        return self


class ContextualSharedSignalsProjectionV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = CONTEXTUAL_SHARED_SIGNALS_SCHEMA_VERSION
    profile_version: Literal["synthworld-contextual-shared-signals-1.0.0"] = (
        CONTEXTUAL_SHARED_SIGNALS_PROFILE_VERSION
    )
    selected_temporal_base: Literal["synthworld-temporal-1.2.0"] = (
        "synthworld-temporal-1.2.0"
    )
    source_public_digest: SyntheticDigestV1
    mapping_profile_digest: SyntheticDigestV1
    event_schedule_version: str = Field(min_length=1)
    events: tuple[ContextualSharedSignalsEventV1, ...]

    @field_validator("events")
    @classmethod
    def canonical_events(
        cls, value: tuple[ContextualSharedSignalsEventV1, ...]
    ) -> tuple[ContextualSharedSignalsEventV1, ...]:
        ordered = tuple(sorted(value, key=lambda item: item.event_index))
        if tuple(item.event_index for item in ordered) != tuple(range(len(ordered))):
            raise ValueError("contextual shared-signals event index differs")
        if len({item.event_id for item in ordered}) != len(ordered):
            raise ValueError("contextual shared-signals event id is duplicated")
        return ordered


def contextual_shared_signals_mapping_profile_v1() -> (
    ContextualSharedSignalsMappingProfileV1
):
    """Return the complete custom-event mapping declaration."""

    return ContextualSharedSignalsMappingProfileV1(
        mappings=tuple(
            ContextualSharedSignalsMappingV1(
                fact_type=fact_type,
                custom_event_type=event_type,
                semantic_delta=(
                    "This is a versioned SynthWorld contextual event, not a "
                    "standardized CAEP event type."
                ),
            )
            for fact_type, event_type in sorted(
                _CUSTOM_EVENT_TYPES.items(), key=lambda item: item[0].value
            )
        )
    )


def project_contextual_shared_signals(
    public: ContextualAccessPublicV1,
    *,
    profile: ContextualSharedSignalsMappingProfileV1 | None = None,
) -> ContextualSharedSignalsProjectionV1:
    """Project public events without creating SET issue or delivery timestamps."""

    selected_profile = profile or contextual_shared_signals_mapping_profile_v1()
    envelopes = {item.event_id: item for item in public.schedule}
    mappings = {item.fact_type: item for item in selected_profile.mappings}
    events = tuple(
        ContextualSharedSignalsEventV1(
            event_id=event.id,
            event_index=envelopes[event.id].event_index,
            native_fact_type=event.payload.fact.fact_type,
            subject_id=event.payload.fact.subject_id,
            custom_event_type=mappings[event.payload.fact.fact_type].custom_event_type,
            effective_tick=event.effective_tick,
            projected_event_tick=event.effective_tick,
            payload_sha256=envelopes[event.id].payload_sha256,
        )
        for event in public.events
    )
    return ContextualSharedSignalsProjectionV1(
        source_public_digest=synthetic_digest(canonical_json_bytes(public)),
        mapping_profile_digest=synthetic_digest(canonical_json_bytes(selected_profile)),
        event_schedule_version=public.benchmark.event_schedule_version,
        events=events,
    )


__all__ = [
    "CONTEXTUAL_SHARED_SIGNALS_PROFILE_VERSION",
    "CONTEXTUAL_SHARED_SIGNALS_SCHEMA_VERSION",
    "ContextualSharedSignalsEventV1",
    "ContextualSharedSignalsMappingProfileV1",
    "ContextualSharedSignalsMappingV1",
    "ContextualSharedSignalsProjectionV1",
    "contextual_shared_signals_mapping_profile_v1",
    "project_contextual_shared_signals",
]
