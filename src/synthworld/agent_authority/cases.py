"""Closed L01-L06 stimulus and observation variants."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from synthworld.agent_authority.common import (
    AgentAuthorityOperatorModel,
    CollectionStatus,
    ObservationAttributionV1,
    ObservedDecision,
    ObservedSideEffect,
    SyntheticSecretHandleV1,
    canonical_unique,
    require_utc,
    unique,
)
from synthworld.models import SyntheticModel


class ExtractionVector(StrEnum):
    PROMPT = "prompt"
    TOOL_OUTPUT = "tool_output"
    ENVIRONMENT = "environment"
    MEMORY_RECALL = "memory_recall"


class EvidenceChannel(StrEnum):
    CONTEXT = "context"
    LOG = "log"
    TRACE = "trace"
    MEMORY = "memory"


class ReplayKind(StrEnum):
    DIFFERENT_SENDER = "different_sender"
    WRONG_AUDIENCE = "wrong_audience"
    AFTER_EXPIRY = "after_expiry"


class FaultMode(StrEnum):
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    CORRUPT_RESPONSE = "corrupt_response"
    STALE_RESPONSE = "stale_response"


class L01SecretExposureStimulusV1(SyntheticModel):
    variant: Literal["l01_secret_exposure"] = "l01_secret_exposure"
    canary_handle: SyntheticSecretHandleV1
    runtime_handle: str = Field(min_length=1)
    extraction_vectors: tuple[ExtractionVector, ...] = Field(min_length=1)
    required_channels: tuple[EvidenceChannel, ...] = Field(min_length=1)

    @field_validator("extraction_vectors", "required_channels")
    @classmethod
    def canonical_enums[EnumT: StrEnum](
        cls, value: tuple[EnumT, ...]
    ) -> tuple[EnumT, ...]:
        if value != tuple(sorted(set(value), key=str)):
            raise ValueError("L01 enum values must be sorted and unique")
        return value


class L02CredentialReplayStimulusV1(SyntheticModel):
    variant: Literal["l02_credential_replay"] = "l02_credential_replay"
    replay_kind: ReplayKind
    credential_handle: SyntheticSecretHandleV1
    original_sender_handle: str = Field(min_length=1)
    replay_sender_handle: str = Field(min_length=1)
    intended_audience_handle: str = Field(min_length=1)
    attempted_audience_handle: str = Field(min_length=1)
    expiry_tick: int = Field(ge=0)
    target_handle: str = Field(min_length=1)
    action_handle: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_named_mismatch(self) -> Self:
        if (
            self.replay_kind is ReplayKind.DIFFERENT_SENDER
            and self.original_sender_handle == self.replay_sender_handle
        ):
            raise ValueError("different-sender replay requires distinct senders")
        if (
            self.replay_kind is ReplayKind.WRONG_AUDIENCE
            and self.intended_audience_handle == self.attempted_audience_handle
        ):
            raise ValueError("wrong-audience replay requires distinct audiences")
        return self


class L03DirectPathBypassStimulusV1(SyntheticModel):
    variant: Literal["l03_direct_path_bypass"] = "l03_direct_path_bypass"
    actor_handle: str = Field(min_length=1)
    target_handle: str = Field(min_length=1)
    action_handle: str = Field(min_length=1)
    sanctioned_path_component_ids: tuple[str, ...] = Field(min_length=1)
    bypass_route_id: str = Field(min_length=1)
    expected_enforcement_point_ids: tuple[str, ...] = Field(min_length=1)

    @field_validator("sanctioned_path_component_ids")
    @classmethod
    def unique_ordered_path(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        unique(value, "sanctioned-path component identifiers")
        if any(not item.strip() for item in value):
            raise ValueError("sanctioned-path components must be nonblank")
        return value

    @field_validator("expected_enforcement_point_ids")
    @classmethod
    def canonical_points(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_unique(value, "L03 enforcement points")


class L04NetworkPolicyStimulusV1(SyntheticModel):
    variant: Literal["l04_network_policy"] = "l04_network_policy"
    source_handle: str = Field(min_length=1)
    target_handle: str = Field(min_length=1)
    action_handle: str = Field(min_length=1)
    network_policy_handle: str = Field(min_length=1)
    forbidden_route_id: str = Field(min_length=1)
    enforcement_point_ids: tuple[str, ...] = Field(min_length=1)

    @field_validator("enforcement_point_ids")
    @classmethod
    def canonical_points(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_unique(value, "L04 enforcement points")


class L05CriticalDependencyFailureStimulusV1(SyntheticModel):
    variant: Literal["l05_critical_dependency_failure"] = (
        "l05_critical_dependency_failure"
    )
    dependency_component_id: str = Field(min_length=1)
    fault_mode: FaultMode
    action_handle: str = Field(min_length=1)
    target_handle: str = Field(min_length=1)
    enforcement_point_ids: tuple[str, ...] = Field(min_length=1)
    injection_tick: int = Field(ge=0)
    recovery_tick: int = Field(ge=0)

    @field_validator("enforcement_point_ids")
    @classmethod
    def canonical_points(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_unique(value, "L05 enforcement points")

    @model_validator(mode="after")
    def require_forward_fault_window(self) -> Self:
        if self.recovery_tick <= self.injection_tick:
            raise ValueError("fault recovery must follow injection")
        return self


class L06RevocationPropagationStimulusV1(SyntheticModel):
    variant: Literal["l06_revocation_propagation"] = "l06_revocation_propagation"
    authority_handle: str = Field(min_length=1)
    delegation_handle: str = Field(min_length=1)
    revocation_tick: int = Field(ge=0)
    traffic_ticks: tuple[int, ...] = Field(min_length=1)
    enforcement_point_ids: tuple[str, ...] = Field(min_length=1)
    child_delegation_handles: tuple[str, ...] = ()
    issued_credential_handles: tuple[SyntheticSecretHandleV1, ...] = Field(min_length=1)
    declared_bound_id: str = Field(min_length=1)

    @field_validator("traffic_ticks")
    @classmethod
    def canonical_ticks(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if any(item < 0 for item in value) or value != tuple(sorted(set(value))):
            raise ValueError("traffic ticks must be non-negative, sorted, and unique")
        return value

    @field_validator("enforcement_point_ids", "child_delegation_handles")
    @classmethod
    def canonical_strings(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_unique(value, "L06 references")

    @model_validator(mode="after")
    def validate_traffic(self) -> Self:
        if not any(tick > self.revocation_tick for tick in self.traffic_ticks):
            raise ValueError("revocation traffic requires a post-revocation tick")
        credential_handles = tuple(
            item.handle for item in self.issued_credential_handles
        )
        unique(credential_handles, "issued credential handles")
        return self


AgentAuthorityStimulusPayloadV1 = Annotated[
    L01SecretExposureStimulusV1
    | L02CredentialReplayStimulusV1
    | L03DirectPathBypassStimulusV1
    | L04NetworkPolicyStimulusV1
    | L05CriticalDependencyFailureStimulusV1
    | L06RevocationPropagationStimulusV1,
    Field(discriminator="variant"),
]


class AgentAuthorityStimulusV1(SyntheticModel):
    stimulus_id: str = Field(min_length=1)
    schedule_tick: int = Field(ge=0)
    payload: AgentAuthorityStimulusPayloadV1

    @model_validator(mode="after")
    def validate_tick_specific_payload(self) -> Self:
        if (
            isinstance(self.payload, L02CredentialReplayStimulusV1)
            and self.payload.replay_kind is ReplayKind.AFTER_EXPIRY
            and self.schedule_tick <= self.payload.expiry_tick
        ):
            raise ValueError("after-expiry replay must be scheduled after expiry")
        return self


class AgentAuthorityStimulusSetV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    stimuli: tuple[AgentAuthorityStimulusV1, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        identifiers = tuple(item.stimulus_id for item in self.stimuli)
        unique(identifiers, "stimulus identifiers")
        expected = tuple(
            sorted(
                self.stimuli,
                key=lambda item: (item.schedule_tick, item.stimulus_id),
            )
        )
        if self.stimuli != expected:
            raise ValueError("stimuli must be ordered by schedule tick and identifier")
        return self


class ConstraintCheckStatus(StrEnum):
    SATISFIED = "satisfied"
    VIOLATED = "violated"
    UNOBSERVED = "unobserved"


class ReachabilityObservation(StrEnum):
    BLOCKED = "blocked"
    REACHABLE = "reachable"
    UNKNOWN = "unknown"


class ConnectivityObservation(StrEnum):
    BLOCKED = "blocked"
    CONNECTED = "connected"
    UNKNOWN = "unknown"


class FaultConfirmation(StrEnum):
    CONFIRMED = "confirmed"
    UNCONFIRMED = "unconfirmed"


class ChannelScanV1(AgentAuthorityOperatorModel):
    channel: EvidenceChannel
    collection_status: CollectionStatus
    canary_match: bool | None
    evidence_handle_ref: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_collection(self) -> Self:
        if (self.collection_status is CollectionStatus.COLLECTED) is not (
            self.canary_match is not None
        ):
            raise ValueError("canary match exists exactly when a channel was collected")
        return self


class L01SecretExposureObservationV1(AgentAuthorityOperatorModel):
    variant: Literal["l01_secret_exposure"] = "l01_secret_exposure"
    channel_scans: tuple[ChannelScanV1, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_channels(self) -> Self:
        channels = tuple(item.channel.value for item in self.channel_scans)
        unique(channels, "channel scan channels")
        if channels != tuple(sorted(channels)):
            raise ValueError("channel scans must be canonically ordered")
        return self


class L02CredentialReplayObservationV1(AgentAuthorityOperatorModel):
    variant: Literal["l02_credential_replay"] = "l02_credential_replay"
    target_decision: ObservedDecision
    side_effect: ObservedSideEffect
    sender_constraint_status: ConstraintCheckStatus
    audience_check_status: ConstraintCheckStatus
    target_evidence_refs: tuple[str, ...] = ()

    @field_validator("target_evidence_refs")
    @classmethod
    def canonical_evidence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_unique(value, "L02 target evidence")


class L03DirectPathBypassObservationV1(AgentAuthorityOperatorModel):
    variant: Literal["l03_direct_path_bypass"] = "l03_direct_path_bypass"
    reachability: ReachabilityObservation
    target_decision: ObservedDecision
    side_effect: ObservedSideEffect
    traversed_component_ids: tuple[str, ...] = ()
    network_evidence_refs: tuple[str, ...] = ()
    target_evidence_refs: tuple[str, ...] = ()

    @field_validator(
        "traversed_component_ids", "network_evidence_refs", "target_evidence_refs"
    )
    @classmethod
    def canonical_values(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_unique(value, "L03 observation values")


class L04NetworkPolicyObservationV1(AgentAuthorityOperatorModel):
    variant: Literal["l04_network_policy"] = "l04_network_policy"
    connectivity: ConnectivityObservation
    target_decision: ObservedDecision
    side_effect: ObservedSideEffect
    network_evidence_refs: tuple[str, ...] = ()
    target_evidence_refs: tuple[str, ...] = ()

    @field_validator("network_evidence_refs", "target_evidence_refs")
    @classmethod
    def canonical_evidence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_unique(value, "L04 evidence references")


class EnforcementOutcomeV1(AgentAuthorityOperatorModel):
    component_id: str = Field(min_length=1)
    decision: ObservedDecision
    side_effect: ObservedSideEffect
    evidence_refs: tuple[str, ...] = ()

    @field_validator("evidence_refs")
    @classmethod
    def canonical_evidence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_unique(value, "enforcement outcome evidence")


class L05CriticalDependencyFailureObservationV1(AgentAuthorityOperatorModel):
    variant: Literal["l05_critical_dependency_failure"] = (
        "l05_critical_dependency_failure"
    )
    fault_confirmation: FaultConfirmation
    enforcement_outcomes: tuple[EnforcementOutcomeV1, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def canonical_outcomes(self) -> Self:
        ids = tuple(item.component_id for item in self.enforcement_outcomes)
        unique(ids, "L05 enforcement outcome components")
        if ids != tuple(sorted(ids)):
            raise ValueError("L05 enforcement outcomes must be canonically ordered")
        return self


class RevocationPointResultV1(AgentAuthorityOperatorModel):
    component_id: str = Field(min_length=1)
    ack_elapsed_ns: int | None = Field(default=None, ge=0)
    evidence_refs: tuple[str, ...] = ()

    @field_validator("evidence_refs")
    @classmethod
    def canonical_evidence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_unique(value, "revocation acknowledgement evidence")


class TimedAttemptV1(AgentAuthorityOperatorModel):
    enforcement_point_id: str = Field(min_length=1)
    credential_or_child_handle: str = Field(min_length=1)
    sent_elapsed_ns: int = Field(ge=0)
    completed_elapsed_ns: int = Field(ge=0)
    decision: ObservedDecision
    side_effect: ObservedSideEffect
    evidence_refs: tuple[str, ...] = ()

    @field_validator("evidence_refs")
    @classmethod
    def canonical_evidence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_unique(value, "timed-attempt evidence")

    @model_validator(mode="after")
    def validate_timing(self) -> Self:
        if self.completed_elapsed_ns < self.sent_elapsed_ns:
            raise ValueError("attempt completion cannot precede send")
        return self


class L06RevocationPropagationObservationV1(AgentAuthorityOperatorModel):
    variant: Literal["l06_revocation_propagation"] = "l06_revocation_propagation"
    revocation_epoch_ns: int = Field(ge=0)
    point_results: tuple[RevocationPointResultV1, ...] = Field(min_length=1)
    timed_attempts: tuple[TimedAttemptV1, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_inventory(self) -> Self:
        points = tuple(item.component_id for item in self.point_results)
        unique(points, "revocation point-result components")
        if points != tuple(sorted(points)):
            raise ValueError("revocation point results must be canonically ordered")
        attempt_keys = tuple(
            (
                item.enforcement_point_id,
                item.credential_or_child_handle,
                item.sent_elapsed_ns,
            )
            for item in self.timed_attempts
        )
        if len(attempt_keys) != len(set(attempt_keys)):
            raise ValueError("timed attempts must be unique")
        if attempt_keys != tuple(sorted(attempt_keys)):
            raise ValueError("timed attempts must be canonically ordered")
        return self


AgentAuthorityObservationPayloadV1 = Annotated[
    L01SecretExposureObservationV1
    | L02CredentialReplayObservationV1
    | L03DirectPathBypassObservationV1
    | L04NetworkPolicyObservationV1
    | L05CriticalDependencyFailureObservationV1
    | L06RevocationPropagationObservationV1,
    Field(discriminator="variant"),
]


class AgentAuthorityObservationV1(AgentAuthorityOperatorModel):
    stimulus_id: str = Field(min_length=1)
    attribution: ObservationAttributionV1
    elapsed_ns: int = Field(ge=0)
    evidence_handle_refs: tuple[str, ...] = ()
    observed_at: datetime | None = None
    payload: AgentAuthorityObservationPayloadV1

    @field_validator("evidence_handle_refs")
    @classmethod
    def canonical_evidence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_unique(value, "observation evidence handles")

    @field_validator("observed_at")
    @classmethod
    def utc_observed_at(cls, value: datetime | None) -> datetime | None:
        return None if value is None else require_utc(value)


class DependencyFaultResultV1(AgentAuthorityOperatorModel):
    stimulus_id: str = Field(min_length=1)
    dependency_component_id: str = Field(min_length=1)
    fault_confirmation: FaultConfirmation
    evidence_refs: tuple[str, ...] = ()

    @field_validator("evidence_refs")
    @classmethod
    def canonical_evidence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_unique(value, "dependency-fault evidence")


__all__ = [
    "AgentAuthorityObservationPayloadV1",
    "AgentAuthorityObservationV1",
    "AgentAuthorityStimulusPayloadV1",
    "AgentAuthorityStimulusSetV1",
    "AgentAuthorityStimulusV1",
    "ChannelScanV1",
    "ConnectivityObservation",
    "ConstraintCheckStatus",
    "DependencyFaultResultV1",
    "EnforcementOutcomeV1",
    "EvidenceChannel",
    "ExtractionVector",
    "FaultConfirmation",
    "FaultMode",
    "L01SecretExposureObservationV1",
    "L01SecretExposureStimulusV1",
    "L02CredentialReplayObservationV1",
    "L02CredentialReplayStimulusV1",
    "L03DirectPathBypassObservationV1",
    "L03DirectPathBypassStimulusV1",
    "L04NetworkPolicyObservationV1",
    "L04NetworkPolicyStimulusV1",
    "L05CriticalDependencyFailureObservationV1",
    "L05CriticalDependencyFailureStimulusV1",
    "L06RevocationPropagationObservationV1",
    "L06RevocationPropagationStimulusV1",
    "ReachabilityObservation",
    "ReplayKind",
    "RevocationPointResultV1",
    "TimedAttemptV1",
]
