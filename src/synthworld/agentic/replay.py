from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise
from typing import Protocol

from synthworld.agentic.models import (
    ActionAttempt,
    ActionAttempted,
    AgenticEvent,
    AgenticWorldSnapshot,
    AgenticWorldState,
    AuthorityFailureReason,
    CanonicalBinding,
    Capability,
    Credential,
    CredentialIssued,
    Decision,
    Delegation,
    DelegationGranted,
    DelegationRevoked,
    EvidenceDiscarded,
    Runtime,
    RuntimeSpawned,
)


class AgenticReplayError(ValueError):
    """Raised when an agentic event stream is structurally invalid."""


@dataclass(frozen=True)
class AuthorityDecision:
    decision: Decision
    failure_reasons: tuple[AuthorityFailureReason, ...]
    delegation_chain_ids: tuple[str, ...]
    required_evidence_refs: tuple[str, ...]
    expected_side_effect: str


def materialize_agentic_world(
    snapshot: AgenticWorldSnapshot,
    events: tuple[AgenticEvent, ...],
    *,
    at_event_index: int | None = None,
    at_timestamp: datetime | None = None,
) -> AgenticWorldState:
    """Replay a validated prefix into an immutable world state.

    Events use one-based indices; index zero is the untouched initial snapshot.
    Grant, issue, spawn, revocation, and evidence-loss events are effective from
    their own index. Authorization for an action is evaluated against the prefix
    strictly before the action's index.
    """

    if at_event_index is not None and at_timestamp is not None:
        raise AgenticReplayError("choose either an event index or a timestamp")
    if at_event_index is not None and at_event_index < 0:
        raise AgenticReplayError("event index cannot be negative")
    if at_timestamp is not None:
        _require_utc(at_timestamp)

    _validate_order(events)
    full_state = _reduce(snapshot, events)
    if at_event_index is None and at_timestamp is None:
        return full_state

    if at_event_index is not None:
        if at_event_index > len(events):
            raise AgenticReplayError("event index is outside the event stream")
        prefix = tuple(item for item in events if item.event_index <= at_event_index)
    elif at_timestamp is not None:
        prefix = tuple(item for item in events if item.occurred_at <= at_timestamp)
    else:  # pragma: no cover - guarded by the full-state return above
        raise AgenticReplayError("missing replay cursor")
    if len(prefix) == len(events):
        return full_state
    return _reduce(snapshot, prefix)


def evaluate_action_authority(
    state: AgenticWorldState,
    attempt: ActionAttempt,
    binding: CanonicalBinding,
    *,
    decision_time: datetime,
) -> AuthorityDecision:
    """Evaluate the deliberately small Asteria capability model."""

    _require_utc(decision_time)
    failures: set[AuthorityFailureReason] = set()
    runtime = _by_id(state.runtimes, binding.runtime_id)
    credential = _by_id(state.credentials, attempt.presented_credential_id)
    agent = _by_id(state.snapshot.agents, binding.logical_agent_id)
    resource = _by_id(state.snapshot.resources, attempt.resource_id)

    if runtime is None or (
        runtime.logical_agent_id != binding.logical_agent_id
        or runtime.runtime_principal_id != binding.runtime_principal_id
    ):
        failures.add(AuthorityFailureReason.WRONG_RUNTIME)
    if credential is None or (
        credential.subject_principal_id != binding.credential_subject_id
        or not credential.valid_from <= decision_time < credential.expires_at
    ):
        failures.add(AuthorityFailureReason.CREDENTIAL_INVALID)
    elif binding.runtime_principal_id not in (credential.allowed_runtime_principal_ids):
        failures.add(AuthorityFailureReason.WRONG_RUNTIME)
    if agent is None or resource is None:
        failures.add(AuthorityFailureReason.NO_ACTIVE_DELEGATION)
    elif agent.organisation_id != resource.organisation_id:
        failures.add(AuthorityFailureReason.TENANT_MISMATCH)
    if attempt.policy_version not in {item.version for item in state.snapshot.policies}:
        failures.add(AuthorityFailureReason.POLICY_VERSION_MISMATCH)

    chain, delegation_failure = _effective_chain(
        state,
        attempt,
        binding,
        decision_time,
    )
    if delegation_failure is not None:
        failures.add(delegation_failure)
    if attempt.proposed_delegation is not None and chain:
        parent = _by_id(state.delegations, chain[-1])
        if parent is None or not _delegation_is_attenuated(
            attempt.proposed_delegation, parent
        ):
            failures.add(AuthorityFailureReason.OVERPRIVILEGED_SUBDELEGATION)

    required_evidence = {
        f"evidence:policy:{attempt.policy_version}",
        f"evidence:credential:{attempt.presented_credential_id}",
        f"evidence:runtime:{binding.runtime_id}",
        *(f"evidence:delegation:{item}" for item in chain),
    }
    ordered_failures = tuple(sorted(failures, key=lambda item: item.value))
    decision = Decision.DENY if ordered_failures else Decision.ALLOW
    return AuthorityDecision(
        decision=decision,
        failure_reasons=ordered_failures,
        delegation_chain_ids=chain,
        required_evidence_refs=tuple(sorted(required_evidence)),
        expected_side_effect=(
            _side_effect_for(attempt.action) if decision is Decision.ALLOW else "none"
        ),
    )


def _reduce(
    snapshot: AgenticWorldSnapshot,
    events: tuple[AgenticEvent, ...],
) -> AgenticWorldState:
    state = AgenticWorldState(
        snapshot=snapshot,
        through_event_index=0,
        as_of=None,
        runtimes=(),
        credentials=(),
        delegations=(),
        revoked_delegation_ids=(),
        retained_evidence_refs=tuple(sorted(snapshot.initial_evidence_refs)),
        action_event_ids=(),
        audit_event_ids=(),
    )
    for event in events:
        state = _apply_event(state, event)
    return state


def _apply_event(state: AgenticWorldState, event: AgenticEvent) -> AgenticWorldState:
    payload = event.payload
    retained = set(state.retained_evidence_refs) | set(event.evidence_refs)
    runtimes = state.runtimes
    credentials = state.credentials
    delegations = state.delegations
    revoked = state.revoked_delegation_ids
    actions = state.action_event_ids
    audits = state.audit_event_ids

    if isinstance(payload, DelegationGranted):
        _validate_delegation(state, payload.delegation, event.occurred_at)
        delegations = (*delegations, payload.delegation)
    elif isinstance(payload, CredentialIssued):
        _validate_credential(state, payload.credential, event.occurred_at)
        credentials = (*credentials, payload.credential)
    elif isinstance(payload, RuntimeSpawned):
        _validate_runtime(state, payload.runtime)
        runtimes = (*runtimes, payload.runtime)
    elif isinstance(payload, ActionAttempted):
        _validate_action(state, payload.attempt)
        actions = (*actions, event.id)
    elif isinstance(payload, DelegationRevoked):
        delegation = _by_id(state.delegations, payload.delegation_id)
        if delegation is None or payload.delegation_id in state.revoked_delegation_ids:
            raise AgenticReplayError("cannot revoke an unknown or inactive delegation")
        revoked = tuple(
            sorted(
                {
                    *revoked,
                    payload.delegation_id,
                    *(
                        item.id
                        for item in state.delegations
                        if _has_ancestor(item, payload.delegation_id, state.delegations)
                    ),
                }
            )
        )
    elif isinstance(payload, EvidenceDiscarded):
        if not set(payload.evidence_refs) <= retained:
            raise AgenticReplayError("cannot discard evidence that is not retained")
        retained -= set(payload.evidence_refs)
    else:
        audits = (*audits, event.id)

    return AgenticWorldState(
        snapshot=state.snapshot,
        through_event_index=event.event_index,
        as_of=event.occurred_at,
        runtimes=runtimes,
        credentials=credentials,
        delegations=delegations,
        revoked_delegation_ids=revoked,
        retained_evidence_refs=tuple(sorted(retained)),
        action_event_ids=actions,
        audit_event_ids=audits,
    )


def _validate_order(events: tuple[AgenticEvent, ...]) -> None:
    if tuple(item.event_index for item in events) != tuple(range(1, len(events) + 1)):
        raise AgenticReplayError("event indices must be contiguous and one-based")
    ids = tuple(item.id for item in events)
    if len(ids) != len(set(ids)):
        raise AgenticReplayError("event IDs must be unique")
    timestamps = tuple(item.occurred_at for item in events)
    if any(current <= previous for previous, current in pairwise(timestamps)):
        raise AgenticReplayError("event timestamps must be strictly increasing")


def _validate_delegation(
    state: AgenticWorldState,
    delegation: Delegation,
    event_time: datetime,
) -> None:
    if _by_id(state.delegations, delegation.id) is not None:
        raise AgenticReplayError("delegation IDs must be unique")
    principal_ids = {item.id for item in state.snapshot.principals}
    if delegation.originating_principal_id not in principal_ids or (
        delegation.delegator_principal_id not in principal_ids
    ):
        raise AgenticReplayError("delegation references an unknown principal")
    if _by_id(state.snapshot.agents, delegation.grantee_agent_id) is None:
        raise AgenticReplayError("delegation references an unknown agent")
    if not set(delegation.capability.resource_ids) <= {
        item.id for item in state.snapshot.resources
    }:
        raise AgenticReplayError("delegation references an unknown resource")
    if delegation.policy_version not in {
        item.version for item in state.snapshot.policies
    }:
        raise AgenticReplayError("delegation references an unknown policy")
    if not delegation.valid_from <= event_time < delegation.expires_at:
        raise AgenticReplayError("delegation grant event is outside its validity")
    if delegation.parent_delegation_id is not None:
        parent = _by_id(state.delegations, delegation.parent_delegation_id)
        if parent is None or parent.id in state.revoked_delegation_ids:
            raise AgenticReplayError("child delegation requires an active parent")
        if not _delegation_is_attenuated(delegation, parent):
            raise AgenticReplayError("granted child delegation must be attenuated")


def _validate_credential(
    state: AgenticWorldState,
    credential: Credential,
    event_time: datetime,
) -> None:
    if _by_id(state.credentials, credential.id) is not None:
        raise AgenticReplayError("credential IDs must be unique")
    principal_ids = {item.id for item in state.snapshot.principals}
    if credential.issuer_principal_id not in principal_ids or (
        credential.subject_principal_id not in principal_ids
    ):
        raise AgenticReplayError("credential references an unknown principal")
    if not set(credential.allowed_runtime_principal_ids) <= principal_ids:
        raise AgenticReplayError("credential references an unknown runtime principal")
    if not credential.valid_from <= event_time < credential.expires_at:
        raise AgenticReplayError("credential issue event is outside its validity")


def _validate_runtime(state: AgenticWorldState, runtime: Runtime) -> None:
    if _by_id(state.runtimes, runtime.id) is not None:
        raise AgenticReplayError("runtime IDs must be unique")
    agent = _by_id(state.snapshot.agents, runtime.logical_agent_id)
    principal_ids = {item.id for item in state.snapshot.principals}
    organisation_ids = {item.id for item in state.snapshot.organisations}
    if (
        agent is None
        or runtime.runtime_principal_id not in principal_ids
        or (runtime.owner_principal_id not in principal_ids)
    ):
        raise AgenticReplayError("runtime references an unknown identity")
    if runtime.organisation_id not in organisation_ids or (
        agent.organisation_id != runtime.organisation_id
    ):
        raise AgenticReplayError("runtime organisation must match its agent")


def _validate_action(state: AgenticWorldState, attempt: ActionAttempt) -> None:
    if _by_id(state.credentials, attempt.presented_credential_id) is None:
        raise AgenticReplayError("action references a credential not yet issued")
    resource = _by_id(state.snapshot.resources, attempt.resource_id)
    if resource is None or attempt.action not in resource.actions:
        raise AgenticReplayError("action references an unknown resource action")
    principal_ids = {item.id for item in state.snapshot.principals}
    agent_ids = {item.id for item in state.snapshot.agents}
    for claim in (
        attempt.originating_principal_claim,
        attempt.runtime_principal_claim,
        attempt.attributed_actor_claim,
    ):
        if claim is not None and claim not in principal_ids:
            raise AgenticReplayError("action contains an unknown principal claim")
    if attempt.logical_agent_claim is not None and (
        attempt.logical_agent_claim not in agent_ids
    ):
        raise AgenticReplayError("action contains an unknown agent claim")
    if not set(attempt.evidence_refs) <= set(state.retained_evidence_refs):
        raise AgenticReplayError("action cites evidence unavailable at action time")
    proposed = attempt.proposed_delegation
    if proposed is not None and (
        proposed.grantee_agent_id not in agent_ids
        or proposed.originating_principal_id not in principal_ids
    ):
        raise AgenticReplayError("proposed delegation has broken references")


def _effective_chain(
    state: AgenticWorldState,
    attempt: ActionAttempt,
    binding: CanonicalBinding,
    decision_time: datetime,
) -> tuple[tuple[str, ...], AuthorityFailureReason | None]:
    candidates = tuple(
        item
        for item in state.delegations
        if item.grantee_agent_id == binding.logical_agent_id
        and item.originating_principal_id == binding.originating_principal_id
    )
    time_valid = tuple(
        item
        for item in candidates
        if item.valid_from <= decision_time < item.expires_at
    )
    active = tuple(
        item for item in time_valid if item.id not in state.revoked_delegation_ids
    )
    capable = tuple(
        item
        for item in active
        if item.policy_version == attempt.policy_version
        and _capability_allows(item.capability, attempt)
    )
    if capable:
        selected = sorted(capable, key=lambda item: item.id)[0]
        return _delegation_chain(selected, state.delegations), None
    if any(
        item.policy_version != attempt.policy_version
        and _capability_allows(item.capability, attempt)
        for item in active
    ):
        return (), AuthorityFailureReason.POLICY_VERSION_MISMATCH
    if any(
        item.policy_version == attempt.policy_version
        and _capability_allows(item.capability, attempt)
        and item.id in state.revoked_delegation_ids
        for item in time_valid
    ):
        return (), AuthorityFailureReason.DELEGATION_REVOKED
    if active:
        return (), AuthorityFailureReason.CAPABILITY_EXCEEDED
    return (), AuthorityFailureReason.NO_ACTIVE_DELEGATION


def _capability_allows(capability: Capability, attempt: ActionAttempt) -> bool:
    return (
        attempt.resource_id in capability.resource_ids
        and attempt.action in capability.actions
        and set(attempt.requested_scope) <= set(capability.scopes)
        and attempt.purpose == capability.purpose
    )


def _delegation_is_attenuated(child: Delegation, parent: Delegation) -> bool:
    return (
        parent.capability.may_delegate
        and child.originating_principal_id == parent.originating_principal_id
        and child.parent_delegation_id == parent.id
        and set(child.capability.resource_ids) <= set(parent.capability.resource_ids)
        and set(child.capability.actions) <= set(parent.capability.actions)
        and set(child.capability.scopes) <= set(parent.capability.scopes)
        and child.capability.purpose == parent.capability.purpose
        and parent.valid_from <= child.valid_from
        and child.expires_at <= parent.expires_at
    )


def _delegation_chain(
    delegation: Delegation,
    delegations: tuple[Delegation, ...],
) -> tuple[str, ...]:
    chain = [delegation.id]
    current = delegation
    while current.parent_delegation_id is not None:
        parent = _by_id(delegations, current.parent_delegation_id)
        if parent is None:
            raise AgenticReplayError("delegation chain references a missing parent")
        chain.append(parent.id)
        current = parent
    return tuple(reversed(chain))


def _has_ancestor(
    delegation: Delegation,
    ancestor_id: str,
    delegations: tuple[Delegation, ...],
) -> bool:
    parent_id = delegation.parent_delegation_id
    while parent_id is not None:
        if parent_id == ancestor_id:
            return True
        parent = _by_id(delegations, parent_id)
        if parent is None:
            return False
        parent_id = parent.parent_delegation_id
    return False


class _HasId(Protocol):
    id: str


def _by_id[ItemT: _HasId](items: tuple[ItemT, ...], identifier: str) -> ItemT | None:
    return next((item for item in items if item.id == identifier), None)


def _side_effect_for(action: str) -> str:
    return {
        "read": "read_recorded",
        "request_quotation": "quotation_requested",
        "compare": "comparison_recorded",
        "create_draft": "draft_created",
        "create_delegation": "delegation_created",
    }.get(action, "action_recorded")


def _require_utc(value: datetime) -> None:
    offset = value.utcoffset()
    if value.tzinfo is None or offset is None or offset.total_seconds() != 0:
        raise AgenticReplayError("materialization timestamps must use UTC")


__all__ = [
    "AgenticReplayError",
    "AuthorityDecision",
    "evaluate_action_authority",
    "materialize_agentic_world",
]
