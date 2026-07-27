from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, field_validator, model_validator

from synthworld.models import SyntheticModel

AGENTIC_SCHEMA_VERSION = "1.0.0"
ASTERIA_WORLD_ID = "asteria-agentic"
ASTERIA_WORLD_VERSION = "1.0.0"
ASTERIA_SEED = 20_260_719


class PrincipalKind(StrEnum):
    ORGANISATION = "organisation"
    HUMAN = "human"
    SERVICE_ACCOUNT = "service_account"
    WORKLOAD = "workload"


class Decision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"


class AuthorityFailureReason(StrEnum):
    NO_ACTIVE_DELEGATION = "no_active_delegation"
    DELEGATION_REVOKED = "delegation_revoked"
    CAPABILITY_EXCEEDED = "capability_exceeded"
    OVERPRIVILEGED_SUBDELEGATION = "overprivileged_subdelegation"
    WRONG_RUNTIME = "wrong_runtime"
    CREDENTIAL_INVALID = "credential_invalid"
    TENANT_MISMATCH = "tenant_mismatch"
    POLICY_VERSION_MISMATCH = "policy_version_mismatch"


class AgenticCaseKind(StrEnum):
    AUTHORISED_ACTION = "authorised_action"
    OUTSIDE_CAPABILITY = "outside_capability"
    OVERPRIVILEGED_SUBDELEGATION = "overprivileged_subdelegation"
    WRONG_RUNTIME = "wrong_runtime"
    SHARED_CREDENTIAL = "shared_credential"
    VALID_THEN_REVOKED = "valid_then_revoked"
    POST_REVOCATION_ACTION = "post_revocation_action"
    INVALID_THEN_LATER_GRANTED = "invalid_then_later_granted"
    MISSING_RETAINED_EVIDENCE = "missing_retained_evidence"
    INCORRECT_ATTRIBUTION = "incorrect_attribution"
    CROSS_TENANT_CONFUSION = "cross_tenant_confusion"


class Organisation(SyntheticModel):
    id: str
    display_name: str
    tenant_id: str


class Department(SyntheticModel):
    id: str
    organisation_id: str
    display_name: str


class Principal(SyntheticModel):
    id: str
    kind: PrincipalKind
    display_name: str
    organisation_id: str | None = None
    department_id: str | None = None
    owner_principal_id: str | None = None


class LogicalAgent(SyntheticModel):
    id: str
    display_name: str
    organisation_id: str
    owner_principal_id: str
    parent_agent_id: str | None = None


class Resource(SyntheticModel):
    id: str
    display_name: str
    organisation_id: str
    owner_principal_id: str
    actions: tuple[str, ...] = Field(min_length=1)

    @field_validator("actions")
    @classmethod
    def sort_unique_actions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _sorted_unique_nonblank(value, "resource actions")


class PolicyVersion(SyntheticModel):
    id: str
    version: str
    default_decision: Literal[Decision.DENY] = Decision.DENY
    require_active_delegation: Literal[True] = True


class Capability(SyntheticModel):
    resource_ids: tuple[str, ...] = Field(min_length=1)
    actions: tuple[str, ...] = Field(min_length=1)
    scopes: tuple[str, ...] = Field(min_length=1)
    purpose: str
    may_delegate: bool = False

    @field_validator("resource_ids", "actions", "scopes")
    @classmethod
    def sort_unique_members(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _sorted_unique_nonblank(value, "capability members")

    @field_validator("purpose")
    @classmethod
    def require_nonblank_purpose(cls, value: str) -> str:
        return _nonblank(value, "capability purpose")


class Credential(SyntheticModel):
    id: str
    issuer_principal_id: str
    subject_principal_id: str
    allowed_runtime_principal_ids: tuple[str, ...] = Field(min_length=1)
    valid_from: datetime
    expires_at: datetime

    @field_validator("allowed_runtime_principal_ids")
    @classmethod
    def sort_unique_runtimes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _sorted_unique_nonblank(value, "credential runtime principals")

    @field_validator("valid_from", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc_datetime(value)

    @model_validator(mode="after")
    def require_forward_validity(self) -> Self:
        if self.expires_at <= self.valid_from:
            raise ValueError("credential expiry must follow its valid-from time")
        return self


class Delegation(SyntheticModel):
    id: str
    originating_principal_id: str
    delegator_principal_id: str
    grantee_agent_id: str
    parent_delegation_id: str | None = None
    capability: Capability
    policy_version: str
    valid_from: datetime
    expires_at: datetime

    @field_validator("valid_from", "expires_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc_datetime(value)

    @model_validator(mode="after")
    def require_forward_validity(self) -> Self:
        if self.expires_at <= self.valid_from:
            raise ValueError("delegation expiry must follow its valid-from time")
        return self


class Runtime(SyntheticModel):
    id: str
    logical_agent_id: str
    runtime_principal_id: str
    owner_principal_id: str
    organisation_id: str


class ActionAttempt(SyntheticModel):
    originating_principal_claim: str | None
    logical_agent_claim: str | None
    runtime_principal_claim: str | None
    presented_credential_id: str
    attributed_actor_claim: str | None
    resource_id: str
    action: str
    requested_scope: tuple[str, ...] = Field(min_length=1)
    purpose: str
    policy_version: str
    evidence_refs: tuple[str, ...]
    proposed_delegation: Delegation | None = None

    @field_validator("requested_scope", "evidence_refs")
    @classmethod
    def sort_unique_members(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _sorted_unique_nonblank(value, "action attempt members")

    @field_validator("action", "purpose", "policy_version")
    @classmethod
    def require_nonblank_values(cls, value: str) -> str:
        return _nonblank(value, "action attempt value")


class DelegationGranted(SyntheticModel):
    event_type: Literal["delegation_granted"] = "delegation_granted"
    delegation: Delegation


class CredentialIssued(SyntheticModel):
    event_type: Literal["credential_issued"] = "credential_issued"
    credential: Credential


class RuntimeSpawned(SyntheticModel):
    event_type: Literal["runtime_spawned"] = "runtime_spawned"
    runtime: Runtime


class ActionAttempted(SyntheticModel):
    event_type: Literal["action_attempted"] = "action_attempted"
    attempt: ActionAttempt


class DelegationRevoked(SyntheticModel):
    event_type: Literal["delegation_revoked"] = "delegation_revoked"
    delegation_id: str


class EvidenceDiscarded(SyntheticModel):
    event_type: Literal["evidence_discarded"] = "evidence_discarded"
    evidence_refs: tuple[str, ...] = Field(min_length=1)

    @field_validator("evidence_refs")
    @classmethod
    def sort_unique_evidence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _sorted_unique_nonblank(value, "discarded evidence")


class AuditPerformed(SyntheticModel):
    event_type: Literal["audit_performed"] = "audit_performed"
    audit_id: str


AgenticEventPayload = Annotated[
    DelegationGranted
    | CredentialIssued
    | RuntimeSpawned
    | ActionAttempted
    | DelegationRevoked
    | EvidenceDiscarded
    | AuditPerformed,
    Field(discriminator="event_type"),
]


class AgenticEvent(SyntheticModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    id: str
    event_index: int = Field(ge=1)
    occurred_at: datetime
    evidence_refs: tuple[str, ...]
    payload: AgenticEventPayload

    @field_validator("occurred_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        return _utc_datetime(value)

    @field_validator("evidence_refs")
    @classmethod
    def sort_unique_evidence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _sorted_unique_nonblank(value, "event evidence")


class AgenticWorldSnapshot(SyntheticModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    world_id: str
    world_version: str
    seed: int
    organisations: tuple[Organisation, ...]
    departments: tuple[Department, ...]
    principals: tuple[Principal, ...]
    agents: tuple[LogicalAgent, ...]
    resources: tuple[Resource, ...]
    policies: tuple[PolicyVersion, ...]
    initial_evidence_refs: tuple[str, ...]

    @model_validator(mode="after")
    def require_referential_integrity(self) -> Self:
        _require_unique_strings(
            tuple(item.id for item in self.organisations), "organisations"
        )
        _require_unique_strings(
            tuple(item.id for item in self.departments), "departments"
        )
        _require_unique_strings(
            tuple(item.id for item in self.principals), "principals"
        )
        _require_unique_strings(tuple(item.id for item in self.agents), "agents")
        _require_unique_strings(tuple(item.id for item in self.resources), "resources")
        _require_unique_strings(
            tuple(item.version for item in self.policies), "policies"
        )
        organisation_ids = {item.id for item in self.organisations}
        department_ids = {item.id for item in self.departments}
        principal_ids = {item.id for item in self.principals}
        agent_ids = {item.id for item in self.agents}
        for department in self.departments:
            if department.organisation_id not in organisation_ids:
                raise ValueError("department references an unknown organisation")
        for principal in self.principals:
            if principal.organisation_id is not None and (
                principal.organisation_id not in organisation_ids
            ):
                raise ValueError("principal references an unknown organisation")
            if principal.department_id is not None and (
                principal.department_id not in department_ids
            ):
                raise ValueError("principal references an unknown department")
            if principal.owner_principal_id is not None and (
                principal.owner_principal_id not in principal_ids
            ):
                raise ValueError("principal references an unknown owner")
        for agent in self.agents:
            if agent.organisation_id not in organisation_ids:
                raise ValueError("agent references an unknown organisation")
            if agent.owner_principal_id not in principal_ids:
                raise ValueError("agent references an unknown owner")
            if (
                agent.parent_agent_id is not None
                and agent.parent_agent_id not in agent_ids
            ):
                raise ValueError("agent references an unknown parent")
        for resource in self.resources:
            if resource.organisation_id not in organisation_ids:
                raise ValueError("resource references an unknown organisation")
            if resource.owner_principal_id not in principal_ids:
                raise ValueError("resource references an unknown owner")
        _require_unique_strings(self.initial_evidence_refs, "initial evidence")
        return self


class PublicScenario(SyntheticModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    id: str
    title: str
    description: str
    action_event_ids: tuple[str, ...] = Field(min_length=1)
    audit_event_id: str
    tool_schema_paths: tuple[str, ...] = Field(min_length=1)

    @field_validator("action_event_ids", "tool_schema_paths")
    @classmethod
    def require_unique_members(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        _require_unique_strings(value, "scenario members")
        return value


class AgenticPublicBundle(SyntheticModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    snapshot: AgenticWorldSnapshot
    events: tuple[AgenticEvent, ...]
    scenario: PublicScenario

    @model_validator(mode="after")
    def require_scenario_event_integrity(self) -> Self:
        event_ids = {item.id for item in self.events}
        action_ids = {
            item.id for item in self.events if isinstance(item.payload, ActionAttempted)
        }
        if set(self.scenario.action_event_ids) != action_ids:
            raise ValueError("scenario must list exactly the public action events")
        if self.scenario.audit_event_id not in event_ids:
            raise ValueError("scenario audit event is missing")
        return self


class CanonicalBinding(SyntheticModel):
    action_event_id: str
    originating_principal_id: str
    logical_agent_id: str
    runtime_id: str
    runtime_principal_id: str
    credential_subject_id: str
    attributed_actor_id: str
    accountable_owner_chain: tuple[str, ...] = Field(min_length=1)


class AuthorityTruth(SyntheticModel):
    action_event_id: str
    decision_at_action: Decision
    decision_at_audit: Decision
    failure_reasons_at_action: tuple[AuthorityFailureReason, ...]
    failure_reasons_at_audit: tuple[AuthorityFailureReason, ...]
    delegation_chain_ids: tuple[str, ...]
    expected_policy_version: str
    required_evidence_refs: tuple[str, ...]
    reconstructable_at_audit: bool
    expected_side_effect: str


class AgenticCase(SyntheticModel):
    action_event_id: str
    kind: str

    @field_validator("kind")
    @classmethod
    def require_nonblank_kind(cls, value: str) -> str:
        return _nonblank(value, "agentic case kind")


class AgenticEvaluatorBundle(SyntheticModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    world_id: str
    world_version: str
    seed: int
    audit_event_id: str
    bindings: tuple[CanonicalBinding, ...]
    authority_truth: tuple[AuthorityTruth, ...]
    cases: tuple[AgenticCase, ...]

    @model_validator(mode="after")
    def require_exact_action_keys(self) -> Self:
        binding_ids = tuple(item.action_event_id for item in self.bindings)
        truth_ids = tuple(item.action_event_id for item in self.authority_truth)
        case_ids = tuple(item.action_event_id for item in self.cases)
        _require_unique_strings(binding_ids, "canonical bindings")
        _require_unique_strings(truth_ids, "authority truth")
        _require_unique_strings(case_ids, "agentic cases")
        if set(binding_ids) != set(truth_ids) or set(binding_ids) != set(case_ids):
            raise ValueError("agentic evaluator action keys must match exactly")
        return self


class AgenticBenchmark(SyntheticModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    public: AgenticPublicBundle
    evaluator: AgenticEvaluatorBundle

    @model_validator(mode="after")
    def require_public_evaluator_integrity(self) -> Self:
        snapshot = self.public.snapshot
        evaluator = self.evaluator
        if (
            snapshot.world_id != evaluator.world_id
            or snapshot.world_version != evaluator.world_version
            or snapshot.seed != evaluator.seed
        ):
            raise ValueError("agentic public and evaluator metadata must match")
        if self.public.scenario.audit_event_id != evaluator.audit_event_id:
            raise ValueError("agentic public and evaluator audit events must match")
        if set(self.public.scenario.action_event_ids) != {
            item.action_event_id for item in evaluator.bindings
        }:
            raise ValueError("agentic public and evaluator action events must match")
        return self


class AgenticWorldState(SyntheticModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    snapshot: AgenticWorldSnapshot
    through_event_index: int = Field(ge=0)
    as_of: datetime | None
    runtimes: tuple[Runtime, ...]
    credentials: tuple[Credential, ...]
    delegations: tuple[Delegation, ...]
    revoked_delegation_ids: tuple[str, ...]
    retained_evidence_refs: tuple[str, ...]
    action_event_ids: tuple[str, ...]
    audit_event_ids: tuple[str, ...]


class ObservedActionTrace(SyntheticModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    event_id: str
    timestamp: datetime | None = None
    originating_principal_id: str | None = None
    logical_agent_id: str | None = None
    runtime_principal_id: str | None = None
    credential_subject_id: str | None = None
    attributed_actor_id: str | None = None
    resource_id: str | None = None
    action: str | None = None
    requested_scope: tuple[str, ...] | None = None
    decision: Decision | None = None
    decision_at_audit: Decision | None = None
    side_effect: str | None = None
    policy_version: str | None = None
    delegation_chain_ids: tuple[str, ...] | None = None
    accountable_owner_chain: tuple[str, ...] | None = None
    evidence_refs: tuple[str, ...] | None = None
    reconstructable_from_retained_evidence: bool | None = None

    @field_validator("timestamp")
    @classmethod
    def require_utc_timestamp(cls, value: datetime | None) -> datetime | None:
        return _utc_datetime(value) if value is not None else None


class AgenticTraceSubmission(SyntheticModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    rows: tuple[ObservedActionTrace, ...]

    @model_validator(mode="after")
    def reject_duplicate_events(self) -> Self:
        _require_unique_strings(
            tuple(item.event_id for item in self.rows), "trace rows"
        )
        return self


def _nonblank(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} must be nonblank")
    return normalized


def _sorted_unique_nonblank(value: tuple[str, ...], label: str) -> tuple[str, ...]:
    normalized = tuple(_nonblank(item, label) for item in value)
    _require_unique_strings(normalized, label)
    return tuple(sorted(normalized))


def _require_unique_strings(value: tuple[object, ...], label: str) -> None:
    if len(value) != len(set(value)):
        raise ValueError(f"{label} must be unique")


def _utc_datetime(value: datetime) -> datetime:
    offset = value.utcoffset()
    if value.tzinfo is None or offset is None:
        raise ValueError("agentic timestamps must be timezone-aware UTC values")
    if offset.total_seconds() != 0:
        raise ValueError("agentic timestamps must use UTC")
    return value


__all__ = [
    "AGENTIC_SCHEMA_VERSION",
    "ASTERIA_SEED",
    "ASTERIA_WORLD_ID",
    "ASTERIA_WORLD_VERSION",
    "ActionAttempt",
    "ActionAttempted",
    "AgenticBenchmark",
    "AgenticCase",
    "AgenticCaseKind",
    "AgenticEvaluatorBundle",
    "AgenticEvent",
    "AgenticEventPayload",
    "AgenticPublicBundle",
    "AgenticTraceSubmission",
    "AgenticWorldSnapshot",
    "AgenticWorldState",
    "AuditPerformed",
    "AuthorityFailureReason",
    "AuthorityTruth",
    "CanonicalBinding",
    "Capability",
    "Credential",
    "CredentialIssued",
    "Decision",
    "Delegation",
    "DelegationGranted",
    "DelegationRevoked",
    "Department",
    "EvidenceDiscarded",
    "LogicalAgent",
    "ObservedActionTrace",
    "Organisation",
    "PolicyVersion",
    "Principal",
    "PrincipalKind",
    "PublicScenario",
    "Resource",
    "Runtime",
    "RuntimeSpawned",
]
