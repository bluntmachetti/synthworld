"""Strict public, evaluator, trace, and metric contracts for contextual access."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Protocol, Self, cast

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

from synthworld.contextual_access.common import (
    CONTEXTUAL_ACCESS_COMPILER_VERSION,
    CONTEXTUAL_ACCESS_CONFIG_SCHEMA_VERSION,
    CONTEXTUAL_ACCESS_EVENT_SCHEDULE_VERSION,
    CONTEXTUAL_ACCESS_PROFILE_VERSION,
    CONTEXTUAL_ACCESS_SCHEMA_VERSION,
    stable_contextual_fact_key,
)
from synthworld.enterprise.canonical import (
    canonical_json_bytes,
    canonical_json_value_bytes,
    synthetic_digest,
)
from synthworld.enterprise.models import (
    EnterpriseIdentityAccessUniverseV1,
    EnterpriseOperatorModel,
    SyntheticDigestV1,
)
from synthworld.enterprise.rbac.common import (
    AuthorizationDecision,
    canonical_operator_records,
    canonical_strings,
    canonical_synthetic_records,
)
from synthworld.enterprise.rbac.metrics import EnterpriseAuthorizationMetricV1
from synthworld.models import SyntheticModel
from synthworld.temporal_schedule import TemporalEventEnvelopeV1


class ContextualAccessTier(StrEnum):
    SMOKE = "smoke"


class ContextualObjectKind(StrEnum):
    WORK_ITEM = "work_item"
    DUTY_SCOPE = "duty_scope"
    DEVICE = "device"
    SIGNAL_SOURCE = "signal_source"
    APPROVAL_EVIDENCE = "approval_evidence"


class ContextualFactKind(StrEnum):
    CASE_ASSIGNMENT = "case_assignment"
    ON_CALL = "on_call"
    DEVICE_POSTURE = "device_posture"
    RISK_SIGNAL = "risk_signal"
    BUSINESS_JUSTIFICATION = "business_justification"


class CaseAssignmentState(StrEnum):
    ASSIGNED = "assigned"
    UNASSIGNED = "unassigned"


class OnCallState(StrEnum):
    ON_CALL = "on_call"
    OFF_CALL = "off_call"


class DevicePosture(StrEnum):
    TRUSTED = "trusted"
    NONCOMPLIANT = "noncompliant"
    UNKNOWN = "unknown"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class BusinessJustificationKind(StrEnum):
    CASE_ASSIGNMENT = "case_assignment"
    CHANGE_APPROVAL = "change_approval"
    EMERGENCY_ACCESS = "emergency_access"


class ContextualPredicateTruth(StrEnum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"


class ContextualRuleEffect(StrEnum):
    ALLOW = "allow"
    DENY = "deny"


class ContextualRuleComposition(StrEnum):
    ALL = "all"
    ANY = "any"


class ContextualCaseKind(StrEnum):
    STATIC_ALLOW = "static_allow"
    STATIC_DENY = "static_deny"
    ASSIGNMENT_REMOVED = "assignment_removed"
    ON_CALL_EXPIRED = "on_call_expired"
    DEVICE_DEGRADED = "device_degraded"
    RISK_ELEVATED = "risk_elevated"
    JUSTIFICATION_EXPIRED = "justification_expired"
    DELAYED_DELIVERY = "delayed_delivery"
    DUPLICATE_DELIVERY = "duplicate_delivery"
    OUT_OF_ORDER_DELIVERY = "out_of_order_delivery"


class ContextualMappingKind(StrEnum):
    SUBJECT_ATTRIBUTE = "subject_attribute"
    RESOURCE_ATTRIBUTE = "resource_attribute"
    ACTION_ATTRIBUTE = "action_attribute"
    ENVIRONMENT_ATTRIBUTE = "environment_attribute"
    RELATIONSHIP_PREDICATE = "relationship_predicate"


class _Identified(Protocol):
    id: str


class _FactIdentified(Protocol):
    fact_id: str


class _RequestIdentified(Protocol):
    request_id: str


class ContextualObjectCountsV1(EnterpriseOperatorModel):
    work_items: int = Field(default=3, gt=0, le=64)
    duty_scopes: int = Field(default=2, gt=0, le=64)
    devices: int = Field(default=6, gt=0, le=64)
    signal_sources: int = Field(default=2, gt=0, le=64)
    approval_evidence: int = Field(default=3, gt=0, le=64)


class ContextualAccessLimitsV1(EnterpriseOperatorModel):
    max_registry_objects: int = Field(default=128, gt=0, le=10_000)
    max_initial_facts: int = Field(default=128, gt=0, le=20_000)
    max_events: int = Field(default=128, gt=0, le=20_000)
    max_delivery_attempts: int = Field(default=256, gt=0, le=40_000)
    max_requests: int = Field(default=128, gt=0, le=20_000)
    max_policies: int = Field(default=16, gt=0, le=256)
    max_rules_per_policy: int = Field(default=64, gt=0, le=256)
    max_predicates_per_rule: int = Field(default=16, gt=0, le=64)


class ContextualAccessConfigV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = CONTEXTUAL_ACCESS_CONFIG_SCHEMA_VERSION
    seed: int
    tier: Literal[ContextualAccessTier.SMOKE] = ContextualAccessTier.SMOKE
    enabled_fact_kinds: tuple[ContextualFactKind, ...] = tuple(ContextualFactKind)
    enabled_case_kinds: tuple[ContextualCaseKind, ...] = tuple(ContextualCaseKind)
    cases_per_kind: int = Field(default=1, gt=0, le=16)
    object_counts: ContextualObjectCountsV1 = Field(
        default_factory=ContextualObjectCountsV1
    )
    event_schedule_version: Literal["contextual-access-schedule-1.0.0"] = (
        CONTEXTUAL_ACCESS_EVENT_SCHEDULE_VERSION
    )
    limits: ContextualAccessLimitsV1 = Field(default_factory=ContextualAccessLimitsV1)

    @field_validator("enabled_fact_kinds", "enabled_case_kinds")
    @classmethod
    def canonical_enabled_values(
        cls, value: tuple[StrEnum, ...], info: ValidationInfo
    ) -> tuple[StrEnum, ...]:
        ordered = tuple(sorted(value, key=lambda item: item.value))
        if not ordered or len(ordered) != len(set(ordered)):
            raise ValueError(f"contextual_{info.field_name}_must_be_unique_nonempty")
        return ordered


class ContextualObjectV1(SyntheticModel):
    id: str = Field(min_length=1)
    kind: ContextualObjectKind
    tenant_id: str = Field(min_length=1)
    organisation_id: str = Field(min_length=1)
    display_label: str = Field(min_length=1)


class ContextualObjectRegistryV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = CONTEXTUAL_ACCESS_SCHEMA_VERSION
    objects: tuple[ContextualObjectV1, ...] = Field(min_length=1)

    @field_validator("objects")
    @classmethod
    def canonical_objects(
        cls, value: tuple[ContextualObjectV1, ...]
    ) -> tuple[ContextualObjectV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.kind.value, item.id) for item in value),
            description="contextual_registry_object",
        )


class ContextualFactBaseV1(SyntheticModel):
    fact_id: str = Field(min_length=1)
    fact_key: str = Field(min_length=1)
    revision: int = Field(ge=0)
    tombstone: bool = False


def _require_interval(start: int, end: int | None, description: str) -> None:
    if end is not None and end <= start:
        raise ValueError(f"{description}_validity_interval_invalid")


def _require_fact_key(
    actual: str,
    kind: ContextualFactKind,
    components: tuple[str, ...],
) -> None:
    if actual != stable_contextual_fact_key(kind.value, *components):
        raise ValueError(f"{kind.value}_fact_key_mismatch")


class CaseAssignmentContextV1(ContextualFactBaseV1):
    fact_type: Literal[ContextualFactKind.CASE_ASSIGNMENT] = (
        ContextualFactKind.CASE_ASSIGNMENT
    )
    subject_id: str
    work_item_id: str
    asset_id: str
    assignment_state: CaseAssignmentState
    valid_from_tick: int = Field(ge=0)
    valid_until_tick: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def valid_interval(self) -> Self:
        _require_interval(
            self.valid_from_tick,
            self.valid_until_tick,
            "case_assignment",
        )
        _require_fact_key(
            self.fact_key,
            self.fact_type,
            (self.subject_id, self.work_item_id, self.asset_id),
        )
        return self


class OnCallContextV1(ContextualFactBaseV1):
    fact_type: Literal[ContextualFactKind.ON_CALL] = ContextualFactKind.ON_CALL
    subject_id: str
    duty_scope_id: str
    duty_state: OnCallState
    valid_from_tick: int = Field(ge=0)
    valid_until_tick: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def valid_interval(self) -> Self:
        _require_interval(self.valid_from_tick, self.valid_until_tick, "on_call")
        _require_fact_key(
            self.fact_key,
            self.fact_type,
            (self.subject_id, self.duty_scope_id),
        )
        return self


class DevicePostureContextV1(ContextualFactBaseV1):
    fact_type: Literal[ContextualFactKind.DEVICE_POSTURE] = (
        ContextualFactKind.DEVICE_POSTURE
    )
    subject_id: str
    device_id: str
    posture: DevicePosture
    observed_at_tick: int = Field(ge=0)
    expires_at_tick: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def valid_interval(self) -> Self:
        _require_interval(
            self.observed_at_tick,
            self.expires_at_tick,
            "device_posture",
        )
        _require_fact_key(
            self.fact_key,
            self.fact_type,
            (self.subject_id, self.device_id),
        )
        return self


class RiskSignalContextV1(ContextualFactBaseV1):
    fact_type: Literal[ContextualFactKind.RISK_SIGNAL] = ContextualFactKind.RISK_SIGNAL
    subject_id: str
    signal_source_id: str
    risk_level: RiskLevel
    effective_from_tick: int = Field(ge=0)
    expires_at_tick: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def valid_interval(self) -> Self:
        _require_interval(
            self.effective_from_tick,
            self.expires_at_tick,
            "risk_signal",
        )
        _require_fact_key(
            self.fact_key,
            self.fact_type,
            (self.subject_id, self.signal_source_id),
        )
        return self


class BusinessJustificationContextV1(ContextualFactBaseV1):
    fact_type: Literal[ContextualFactKind.BUSINESS_JUSTIFICATION] = (
        ContextualFactKind.BUSINESS_JUSTIFICATION
    )
    subject_id: str
    asset_id: str
    action: str
    justification_kind: BusinessJustificationKind
    approval_evidence_id: str
    valid_from_tick: int = Field(ge=0)
    valid_until_tick: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def valid_interval(self) -> Self:
        _require_interval(
            self.valid_from_tick,
            self.valid_until_tick,
            "business_justification",
        )
        _require_fact_key(
            self.fact_key,
            self.fact_type,
            (
                self.subject_id,
                self.asset_id,
                self.action,
                self.justification_kind.value,
                self.approval_evidence_id,
            ),
        )
        return self


ContextualFactV1 = Annotated[
    CaseAssignmentContextV1
    | OnCallContextV1
    | DevicePostureContextV1
    | RiskSignalContextV1
    | BusinessJustificationContextV1,
    Field(discriminator="fact_type"),
]


class ContextualFactUpsertedV1(SyntheticModel):
    event_type: Literal["fact_upserted"] = "fact_upserted"
    fact: ContextualFactV1

    @model_validator(mode="after")
    def require_live_fact(self) -> Self:
        if self.fact.tombstone:
            raise ValueError("contextual_upsert_cannot_carry_tombstone")
        return self


class ContextualFactRemovedV1(SyntheticModel):
    event_type: Literal["fact_removed"] = "fact_removed"
    fact: ContextualFactV1

    @model_validator(mode="after")
    def require_tombstone(self) -> Self:
        if not self.fact.tombstone:
            raise ValueError("contextual_remove_must_carry_tombstone")
        return self


ContextualAccessEventPayloadV1 = Annotated[
    ContextualFactUpsertedV1 | ContextualFactRemovedV1,
    Field(discriminator="event_type"),
]


class ContextualAccessEventV1(SyntheticModel):
    id: str = Field(min_length=1)
    effective_tick: int = Field(ge=0)
    payload: ContextualAccessEventPayloadV1


class ContextDeliveryAttemptV1(SyntheticModel):
    attempt_id: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    attempt_index: int = Field(ge=0)
    delivery_tick: int = Field(ge=0)
    delivery_order: int = Field(ge=0)


class ContextualAccessRequestV1(SyntheticModel):
    request_id: str = Field(min_length=1)
    request_index: int = Field(ge=0)
    request_tick: int = Field(ge=0)
    subject_id: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    access_atom_id: str = Field(min_length=1)
    device_id: str | None = Field(default=None, min_length=1)


class HasActiveCaseAssignmentV1(SyntheticModel):
    predicate_type: Literal["has_active_case_assignment"] = "has_active_case_assignment"
    predicate_id: str = Field(min_length=1)


class IsOnCallV1(SyntheticModel):
    predicate_type: Literal["is_on_call"] = "is_on_call"
    predicate_id: str = Field(min_length=1)
    duty_scope_id: str = Field(min_length=1)


class DevicePostureIsV1(SyntheticModel):
    predicate_type: Literal["device_posture_is"] = "device_posture_is"
    predicate_id: str = Field(min_length=1)
    required_posture: Literal[DevicePosture.TRUSTED, DevicePosture.NONCOMPLIANT]


class RiskAtMostV1(SyntheticModel):
    predicate_type: Literal["risk_at_most"] = "risk_at_most"
    predicate_id: str = Field(min_length=1)
    signal_source_id: str = Field(min_length=1)
    maximum_level: Literal[RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH]


class HasValidBusinessJustificationV1(SyntheticModel):
    predicate_type: Literal["has_valid_business_justification"] = (
        "has_valid_business_justification"
    )
    predicate_id: str = Field(min_length=1)
    justification_kind: BusinessJustificationKind


ContextualPredicateV1 = Annotated[
    HasActiveCaseAssignmentV1
    | IsOnCallV1
    | DevicePostureIsV1
    | RiskAtMostV1
    | HasValidBusinessJustificationV1,
    Field(discriminator="predicate_type"),
]


class ContextualRuleV1(SyntheticModel):
    rule_id: str = Field(min_length=1)
    effect: ContextualRuleEffect
    composition: ContextualRuleComposition
    predicates: tuple[ContextualPredicateV1, ...] = Field(min_length=1, max_length=64)

    @field_validator("predicates")
    @classmethod
    def canonical_predicates(
        cls, value: tuple[ContextualPredicateV1, ...]
    ) -> tuple[ContextualPredicateV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.predicate_id,) for item in value),
            description="contextual_predicate_id",
        )


class ContextualPolicyV1(SyntheticModel):
    policy_id: str = Field(min_length=1)
    policy_version_id: str = Field(min_length=1)
    target_handles: tuple[str, ...] = Field(min_length=1)
    actions: tuple[str, ...] = Field(min_length=1)
    rules: tuple[ContextualRuleV1, ...] = Field(min_length=1, max_length=256)
    default_decision: Literal[AuthorizationDecision.DENY] = AuthorizationDecision.DENY
    combining_algorithm: Literal["deny_overrides"] = "deny_overrides"

    @field_validator("target_handles", "actions")
    @classmethod
    def canonical_scope(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "contextual_policy_scope_member")

    @field_validator("rules")
    @classmethod
    def canonical_rules(
        cls, value: tuple[ContextualRuleV1, ...]
    ) -> tuple[ContextualRuleV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.rule_id,) for item in value),
            description="contextual_rule_id",
        )


class ContextualFactMappingV1(SyntheticModel):
    fact_type: ContextualFactKind
    mapping_kind: ContextualMappingKind
    nist_category: Literal["subject", "resource", "action", "environment"] | None
    relationship_predicate: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def mapping_is_unambiguous(self) -> Self:
        if self.mapping_kind is ContextualMappingKind.RELATIONSHIP_PREDICATE:
            if self.relationship_predicate is None or self.nist_category is not None:
                raise ValueError("contextual_relationship_mapping_fields_invalid")
        elif self.nist_category is None or self.relationship_predicate is not None:
            raise ValueError("contextual_attribute_mapping_fields_invalid")
        return self


class ContextualFactMappingProfileV1(SyntheticModel):
    profile_id: str = Field(min_length=1)
    profile_version: Literal["1.0.0"] = CONTEXTUAL_ACCESS_SCHEMA_VERSION
    mappings: tuple[ContextualFactMappingV1, ...]

    @field_validator("mappings")
    @classmethod
    def canonical_complete_mappings(
        cls, value: tuple[ContextualFactMappingV1, ...]
    ) -> tuple[ContextualFactMappingV1, ...]:
        ordered = tuple(sorted(value, key=lambda item: item.fact_type.value))
        if tuple(item.fact_type for item in ordered) != tuple(
            sorted(ContextualFactKind, key=lambda item: item.value)
        ):
            raise ValueError("contextual_fact_mapping_profile_incomplete")
        return ordered


class ContextualReplayStateV1(SyntheticModel):
    processed_event_ids: tuple[str, ...]
    latest_facts: tuple[ContextualFactV1, ...]
    fact_history: tuple[ContextualFactV1, ...]

    @field_validator("latest_facts")
    @classmethod
    def canonical_latest(
        cls, value: tuple[ContextualFactV1, ...]
    ) -> tuple[ContextualFactV1, ...]:
        ordered = tuple(sorted(value, key=lambda item: item.fact_key))
        if len({item.fact_key for item in ordered}) != len(ordered):
            raise ValueError("contextual_latest_fact_key_duplicate")
        return ordered

    @field_validator("fact_history")
    @classmethod
    def canonical_history(
        cls, value: tuple[ContextualFactV1, ...]
    ) -> tuple[ContextualFactV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.fact_key, str(item.revision)) for item in value),
            description="contextual_fact_revision",
        )


class ContextualAccessBenchmarkV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = CONTEXTUAL_ACCESS_SCHEMA_VERSION
    compiler_version: Literal["1.0.0"] = CONTEXTUAL_ACCESS_COMPILER_VERSION
    profile_version: Literal["contextual-access-smoke-1.0.0"] = (
        CONTEXTUAL_ACCESS_PROFILE_VERSION
    )
    seed: int
    tier: Literal[ContextualAccessTier.SMOKE] = ContextualAccessTier.SMOKE
    event_schedule_version: Literal["contextual-access-schedule-1.0.0"] = (
        CONTEXTUAL_ACCESS_EVENT_SCHEDULE_VERSION
    )
    config_digest: SyntheticDigestV1
    identity_access_universe_digest: SyntheticDigestV1
    access_atom_digest: SyntheticDigestV1
    registry_digest: SyntheticDigestV1
    mapping_profile_digest: SyntheticDigestV1
    policy_digest: SyntheticDigestV1
    initial_fact_digest: SyntheticDigestV1
    event_digest: SyntheticDigestV1
    schedule_digest: SyntheticDigestV1
    delivery_attempt_digest: SyntheticDigestV1
    request_digest: SyntheticDigestV1


class ContextualAccessPublicV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = CONTEXTUAL_ACCESS_SCHEMA_VERSION
    universe: EnterpriseIdentityAccessUniverseV1
    registry: ContextualObjectRegistryV1
    mapping_profile: ContextualFactMappingProfileV1
    policies: tuple[ContextualPolicyV1, ...] = Field(min_length=1)
    initial_facts: tuple[ContextualFactV1, ...]
    events: tuple[ContextualAccessEventV1, ...]
    schedule: tuple[TemporalEventEnvelopeV1, ...]
    delivery_attempts: tuple[ContextDeliveryAttemptV1, ...]
    requests: tuple[ContextualAccessRequestV1, ...] = Field(min_length=1)
    benchmark: ContextualAccessBenchmarkV1

    @field_validator("policies")
    @classmethod
    def canonical_policies(
        cls, value: tuple[ContextualPolicyV1, ...]
    ) -> tuple[ContextualPolicyV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.policy_id,) for item in value),
            description="contextual_policy_id",
        )

    @field_validator("initial_facts")
    @classmethod
    def canonical_initial_facts(
        cls, value: tuple[ContextualFactV1, ...]
    ) -> tuple[ContextualFactV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.fact_key,) for item in value),
            description="contextual_initial_fact_key",
        )

    @field_validator("events")
    @classmethod
    def canonical_events(
        cls, value: tuple[ContextualAccessEventV1, ...]
    ) -> tuple[ContextualAccessEventV1, ...]:
        ordered = tuple(sorted(value, key=lambda item: (item.effective_tick, item.id)))
        if len({item.id for item in ordered}) != len(ordered):
            raise ValueError("contextual_event_id_duplicate")
        return ordered

    @field_validator("delivery_attempts")
    @classmethod
    def canonical_delivery_attempts(
        cls, value: tuple[ContextDeliveryAttemptV1, ...]
    ) -> tuple[ContextDeliveryAttemptV1, ...]:
        ordered = tuple(
            sorted(
                value,
                key=lambda item: (
                    item.delivery_tick,
                    item.delivery_order,
                    item.event_id,
                    item.attempt_index,
                ),
            )
        )
        if len({item.attempt_id for item in ordered}) != len(ordered):
            raise ValueError("contextual_delivery_attempt_id_duplicate")
        by_event: dict[str, list[int]] = {}
        for item in ordered:
            by_event.setdefault(item.event_id, []).append(item.attempt_index)
        if any(indices != list(range(len(indices))) for indices in by_event.values()):
            raise ValueError("contextual_delivery_attempt_index_gap")
        return ordered

    @field_validator("requests")
    @classmethod
    def canonical_requests(
        cls, value: tuple[ContextualAccessRequestV1, ...]
    ) -> tuple[ContextualAccessRequestV1, ...]:
        ordered = tuple(
            sorted(value, key=lambda item: (item.request_index, item.request_id))
        )
        if len({item.request_id for item in ordered}) != len(ordered):
            raise ValueError("contextual_request_id_duplicate")
        if tuple(item.request_index for item in ordered) != tuple(range(len(ordered))):
            raise ValueError("contextual_request_index_gap")
        return ordered

    @model_validator(mode="after")
    def benchmark_binds_public_components(self) -> Self:
        atom_bytes = canonical_json_value_bytes(
            [item.model_dump(mode="json") for item in self.universe.access_atoms]
        )
        expected = (
            synthetic_digest(canonical_json_bytes(self.universe)),
            synthetic_digest(atom_bytes),
            synthetic_digest(canonical_json_bytes(self.registry)),
            synthetic_digest(canonical_json_bytes(self.mapping_profile)),
            synthetic_digest(canonical_model_tuple_bytes(self.policies)),
            synthetic_digest(canonical_model_tuple_bytes(self.initial_facts)),
            synthetic_digest(canonical_model_tuple_bytes(self.events)),
            synthetic_digest(canonical_model_tuple_bytes(self.schedule)),
            synthetic_digest(canonical_model_tuple_bytes(self.delivery_attempts)),
            synthetic_digest(canonical_model_tuple_bytes(self.requests)),
        )
        actual = (
            self.benchmark.identity_access_universe_digest,
            self.benchmark.access_atom_digest,
            self.benchmark.registry_digest,
            self.benchmark.mapping_profile_digest,
            self.benchmark.policy_digest,
            self.benchmark.initial_fact_digest,
            self.benchmark.event_digest,
            self.benchmark.schedule_digest,
            self.benchmark.delivery_attempt_digest,
            self.benchmark.request_digest,
        )
        if actual != expected:
            raise ValueError("contextual_public_component_digest_mismatch")
        return self


def canonical_model_tuple_bytes(value: tuple[BaseModel, ...]) -> bytes:
    """Serialize a generated tuple as one canonical JSON array."""

    return canonical_json_value_bytes([item.model_dump(mode="json") for item in value])


class ContextualPredicateOutcomeV1(SyntheticModel):
    policy_id: str
    rule_id: str
    predicate_id: str
    outcome: ContextualPredicateTruth


class ContextualRuleOutcomeV1(SyntheticModel):
    policy_id: str
    rule_id: str
    effect: ContextualRuleEffect
    outcome: ContextualPredicateTruth
    matched: bool


class ContextualDecisionTruthV1(SyntheticModel):
    decision: AuthorizationDecision
    applicable_policy_ids: tuple[str, ...]
    predicate_outcomes: tuple[ContextualPredicateOutcomeV1, ...]
    rule_outcomes: tuple[ContextualRuleOutcomeV1, ...]
    deny_override_conflict: bool

    @field_validator("applicable_policy_ids")
    @classmethod
    def canonical_policy_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "contextual_applicable_policy_id")

    @field_validator("predicate_outcomes", "rule_outcomes")
    @classmethod
    def canonical_outcomes(
        cls, value: tuple[SyntheticModel, ...], info: ValidationInfo
    ) -> tuple[SyntheticModel, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple(
                (
                    cast(ContextualPredicateOutcomeV1, item).policy_id,
                    cast(ContextualPredicateOutcomeV1, item).rule_id,
                    getattr(item, "predicate_id", ""),
                )
                for item in value
            ),
            description=f"contextual_{info.field_name}",
        )


class ContextualCheckpointV1(SyntheticModel):
    event_count: int = Field(ge=0)
    event_ids: tuple[str, ...]
    latest_facts: tuple[ContextualFactV1, ...]
    state_digest: SyntheticDigestV1

    @field_validator("latest_facts")
    @classmethod
    def canonical_checkpoint_facts(
        cls, value: tuple[ContextualFactV1, ...]
    ) -> tuple[ContextualFactV1, ...]:
        ordered = tuple(sorted(value, key=lambda item: item.fact_key))
        if len({item.fact_key for item in ordered}) != len(ordered):
            raise ValueError("contextual_checkpoint_fact_key_duplicate")
        return ordered

    @model_validator(mode="after")
    def digest_matches_state(self) -> Self:
        if self.state_digest != synthetic_digest(
            canonical_model_tuple_bytes(self.latest_facts)
        ):
            raise ValueError("contextual_checkpoint_state_digest_mismatch")
        return self


class ContextualAccessCaseTruthV1(SyntheticModel):
    case_id: str
    request_id: str
    canonical: ContextualDecisionTruthV1
    presented_feed: ContextualDecisionTruthV1
    stale_context: bool
    required_evidence_refs: tuple[str, ...]

    @field_validator("required_evidence_refs")
    @classmethod
    def canonical_evidence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "contextual_required_evidence_ref")

    @model_validator(mode="after")
    def stale_label_matches_decisions(self) -> Self:
        if self.stale_context is (
            self.canonical.decision is self.presented_feed.decision
        ):
            raise ValueError("contextual_stale_context_label_mismatch")
        return self


class ContextualCaseLabelV1(SyntheticModel):
    case_id: str
    request_id: str
    kind: ContextualCaseKind
    transition_event_ids: tuple[str, ...]

    @field_validator("transition_event_ids")
    @classmethod
    def canonical_transition_events(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "contextual_transition_event_id")


class ContextualAccessTruthV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = CONTEXTUAL_ACCESS_SCHEMA_VERSION
    compiler_version: Literal["1.0.0"] = CONTEXTUAL_ACCESS_COMPILER_VERSION
    public_digest: SyntheticDigestV1
    benchmark_digest: SyntheticDigestV1
    checkpoints: tuple[ContextualCheckpointV1, ...]
    cases: tuple[ContextualAccessCaseTruthV1, ...]
    case_labels: tuple[ContextualCaseLabelV1, ...]

    @field_validator("checkpoints")
    @classmethod
    def canonical_checkpoints(
        cls, value: tuple[ContextualCheckpointV1, ...]
    ) -> tuple[ContextualCheckpointV1, ...]:
        ordered = tuple(sorted(value, key=lambda item: item.event_count))
        if tuple(item.event_count for item in ordered) != tuple(range(len(ordered))):
            raise ValueError("contextual_checkpoint_count_gap")
        return ordered

    @field_validator("cases", "case_labels")
    @classmethod
    def canonical_truth_rows(
        cls, value: tuple[SyntheticModel, ...], info: ValidationInfo
    ) -> tuple[SyntheticModel, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((cast(_RequestIdentified, item).request_id,) for item in value),
            description=f"contextual_{info.field_name}_request_id",
        )


class ContextualAccessEvaluatorV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = CONTEXTUAL_ACCESS_SCHEMA_VERSION
    public_digest: SyntheticDigestV1
    truth: ContextualAccessTruthV1

    @model_validator(mode="after")
    def truth_binds_public(self) -> Self:
        if self.truth.public_digest != self.public_digest:
            raise ValueError("contextual_evaluator_public_digest_mismatch")
        return self


class ContextualPredicatePredictionV1(EnterpriseOperatorModel):
    predicate_id: str = Field(min_length=1)
    outcome: ContextualPredicateTruth


class ContextualAccessTraceRowV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = CONTEXTUAL_ACCESS_SCHEMA_VERSION
    benchmark_digest: SyntheticDigestV1
    request_id: str = Field(min_length=1)
    decision: AuthorizationDecision
    predicate_outcomes: tuple[ContextualPredicatePredictionV1, ...]
    applied_event_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]

    @field_validator("predicate_outcomes")
    @classmethod
    def canonical_predicate_predictions(
        cls, value: tuple[ContextualPredicatePredictionV1, ...]
    ) -> tuple[ContextualPredicatePredictionV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple((item.predicate_id,) for item in value),
            description="contextual_predicate_prediction_id",
        )

    @field_validator("applied_event_ids", "evidence_refs")
    @classmethod
    def canonical_string_sets(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "contextual_trace_member")


class ContextualAccessPredictionV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = CONTEXTUAL_ACCESS_SCHEMA_VERSION
    benchmark_digest: SyntheticDigestV1
    rows: tuple[ContextualAccessTraceRowV1, ...] = Field(min_length=1)

    @field_validator("rows")
    @classmethod
    def canonical_rows(
        cls, value: tuple[ContextualAccessTraceRowV1, ...]
    ) -> tuple[ContextualAccessTraceRowV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple((item.request_id,) for item in value),
            description="contextual_prediction_request_id",
        )

    @model_validator(mode="after")
    def rows_bind_benchmark(self) -> Self:
        if any(item.benchmark_digest != self.benchmark_digest for item in self.rows):
            raise ValueError("contextual_prediction_row_digest_mismatch")
        return self


class ContextualTraceValidationIssueV1(EnterpriseOperatorModel):
    severity: Literal["error"] = "error"
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    line: int | None = Field(default=None, gt=0)
    request_id: str | None = Field(default=None, min_length=1)


class ContextualTraceValidationReportV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = CONTEXTUAL_ACCESS_SCHEMA_VERSION
    valid: bool
    row_count: int = Field(ge=0)
    expected_request_count: int = Field(ge=0)
    issues: tuple[ContextualTraceValidationIssueV1, ...]


class ContextualAccessMetricsV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = CONTEXTUAL_ACCESS_SCHEMA_VERSION
    benchmark_digest: SyntheticDigestV1
    truth_digest: SyntheticDigestV1
    metrics: tuple[EnterpriseAuthorizationMetricV1, ...]

    @field_validator("metrics")
    @classmethod
    def canonical_metrics(
        cls, value: tuple[EnterpriseAuthorizationMetricV1, ...]
    ) -> tuple[EnterpriseAuthorizationMetricV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.family, item.name) for item in value),
            description="contextual_metric_name",
        )


__all__ = [name for name in globals() if name.endswith("V1")]
