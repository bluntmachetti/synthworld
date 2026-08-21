"""Public-only policy views for the enterprise-agentic identity pilot.

These policies are experiment-owned examples, not SynthWorld authorization
contracts.  They consume only :class:`AgenticPublicBundle`, replay its public event
stream, and emit decision-only observations.  In particular, this module never
loads evaluator truth or claims identity, accountability, or provenance fields
that a decision-only policy did not return.

The four strategies deliberately divide responsibility as follows:

* RBAC supplies a coarse ``agent_reader`` entitlement.
* ABAC guards runtime, credential, and request attributes.
* ReBAC follows active delegation and runtime relationships.
* combined requires every one of those independently evaluated controls.

That separation makes the generated smoke cases discriminating without presenting
one mechanism as a complete production authorization design.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from synthworld.agentic.models import (
    ActionAttempt,
    ActionAttempted,
    AgenticEvent,
    AgenticPublicBundle,
    AgenticTraceSubmission,
    AgenticWorldSnapshot,
    AgenticWorldState,
    AuditPerformed,
    Decision,
    ObservedActionTrace,
)
from synthworld.agentic.replay import materialize_agentic_world

_READER_ACTION = "read"
_READER_ROLE = "agent_reader"
_REQUIRED_SCOPE = ("tenant:primary",)
_REQUIRED_PURPOSE = "enterprise-agentic-evaluation"
_REQUIRED_POLICY_VERSION = "enterprise-agentic-policy-v1"


class PolicyStrategy(StrEnum):
    """The fixed policy comparison order used by the pilot."""

    RBAC = "rbac"
    ABAC = "abac"
    REBAC = "rebac"
    COMBINED = "combined"


@dataclass(frozen=True, slots=True)
class _DirectoryRbacOverlay:
    assignments: frozenset[tuple[str, str]]
    permissions: frozenset[tuple[str, str, str]]


@dataclass(frozen=True, slots=True)
class _PolicyContext:
    attempt: ActionAttempt
    state: AgenticWorldState
    decision_time: datetime
    rbac: _DirectoryRbacOverlay


type _Policy = Callable[[_PolicyContext], bool]


def build_policy_traces(
    public: AgenticPublicBundle,
) -> tuple[tuple[str, AgenticTraceSubmission], ...]:
    """Run every public-only policy in one stable, presentation-ready order."""

    return (
        (PolicyStrategy.RBAC.value, build_rbac_trace(public)),
        (PolicyStrategy.ABAC.value, build_abac_trace(public)),
        (PolicyStrategy.REBAC.value, build_rebac_trace(public)),
        (PolicyStrategy.COMBINED.value, build_combined_trace(public)),
    )


def build_rbac_trace(public: AgenticPublicBundle) -> AgenticTraceSubmission:
    """Apply the coarse reader-role policy to every public action."""

    return _build_trace(public, _rbac_allows)


def build_abac_trace(public: AgenticPublicBundle) -> AgenticTraceSubmission:
    """Apply the runtime, credential, and request-attribute policy."""

    return _build_trace(public, _abac_allows)


def build_rebac_trace(public: AgenticPublicBundle) -> AgenticTraceSubmission:
    """Apply the active delegation and runtime-relationship policy."""

    return _build_trace(public, _rebac_allows)


def build_combined_trace(public: AgenticPublicBundle) -> AgenticTraceSubmission:
    """Require the RBAC ceiling, ReBAC authority, and ABAC guard together."""

    return _build_trace(public, _combined_allows)


def _build_trace(
    public: AgenticPublicBundle,
    allows: _Policy,
) -> AgenticTraceSubmission:
    events = public.events
    # Replay once without a cursor first.  Besides producing no private data, this
    # enforces the public stream's contiguous indices, unique IDs, and time order.
    materialize_agentic_world(public.snapshot, events)
    rbac = _compile_directory_rbac_overlay(public.snapshot)

    audit = _audit_event(public)
    audit_state = materialize_agentic_world(
        public.snapshot,
        events,
        at_event_index=audit.event_index - 1,
    )
    action_events = {
        event.id: event
        for event in events
        if isinstance(event.payload, ActionAttempted)
    }

    rows: list[ObservedActionTrace] = []
    for event_id in public.scenario.action_event_ids:
        event = action_events.get(event_id)
        if event is None:
            raise ValueError("public scenario references a non-action event")
        if event.event_index >= audit.event_index:
            raise ValueError("public action events must precede the scenario audit")
        payload = event.payload
        if not isinstance(payload, ActionAttempted):
            raise ValueError("public action payload has an unexpected type")
        action_state = materialize_agentic_world(
            public.snapshot,
            events,
            at_event_index=event.event_index - 1,
        )
        rows.append(
            ObservedActionTrace(
                event_id=event.id,
                decision=_decision(
                    allows(
                        _PolicyContext(
                            attempt=payload.attempt,
                            state=action_state,
                            decision_time=event.occurred_at,
                            rbac=rbac,
                        )
                    )
                ),
                decision_at_audit=_decision(
                    allows(
                        _PolicyContext(
                            attempt=payload.attempt,
                            state=audit_state,
                            decision_time=audit.occurred_at,
                            rbac=rbac,
                        )
                    )
                ),
            )
        )
    return AgenticTraceSubmission(rows=tuple(rows))


def _audit_event(public: AgenticPublicBundle) -> AgenticEvent:
    matches = tuple(
        event for event in public.events if event.id == public.scenario.audit_event_id
    )
    if len(matches) != 1 or not isinstance(matches[0].payload, AuditPerformed):
        raise ValueError("public scenario must reference exactly one audit event")
    return matches[0]


def _compile_directory_rbac_overlay(
    snapshot: AgenticWorldSnapshot,
) -> _DirectoryRbacOverlay:
    """Provision the deliberately broad reader role used as the baseline."""

    return _DirectoryRbacOverlay(
        assignments=frozenset((agent.id, _READER_ROLE) for agent in snapshot.agents),
        permissions=frozenset(
            (_READER_ROLE, resource.id, _READER_ACTION)
            for resource in snapshot.resources
        ),
    )


def _rbac_allows(context: _PolicyContext) -> bool:
    """Check the compiled ``agent_reader`` assignment and resource permission."""

    attempt = context.attempt
    if attempt.logical_agent_claim is None:
        return False
    agent = next(
        (
            item
            for item in context.state.snapshot.agents
            if item.id == attempt.logical_agent_claim
        ),
        None,
    )
    resource = next(
        (
            item
            for item in context.state.snapshot.resources
            if item.id == attempt.resource_id
        ),
        None,
    )
    return (
        agent is not None
        and resource is not None
        and agent.organisation_id == resource.organisation_id
        and (agent.id, _READER_ROLE) in context.rbac.assignments
        and (_READER_ROLE, resource.id, attempt.action) in context.rbac.permissions
    )


def _abac_allows(context: _PolicyContext) -> bool:
    """Evaluate attributes without consulting delegation relationships."""

    attempt = context.attempt
    if attempt.logical_agent_claim is None or attempt.runtime_principal_claim is None:
        return False
    agent = next(
        (
            item
            for item in context.state.snapshot.agents
            if item.id == attempt.logical_agent_claim
        ),
        None,
    )
    resource = next(
        (
            item
            for item in context.state.snapshot.resources
            if item.id == attempt.resource_id
        ),
        None,
    )
    runtime_matches = tuple(
        item
        for item in context.state.runtimes
        if item.runtime_principal_id == attempt.runtime_principal_claim
    )
    credential = next(
        (
            item
            for item in context.state.credentials
            if item.id == attempt.presented_credential_id
        ),
        None,
    )
    if (
        agent is None
        or resource is None
        or len(runtime_matches) != 1
        or credential is None
    ):
        return False
    runtime = runtime_matches[0]
    return (
        runtime.logical_agent_id == agent.id
        and runtime.organisation_id == agent.organisation_id == resource.organisation_id
        and credential.valid_from <= context.decision_time < credential.expires_at
        and runtime.runtime_principal_id in credential.allowed_runtime_principal_ids
        and attempt.action == _READER_ACTION
        and attempt.requested_scope == _REQUIRED_SCOPE
        and attempt.purpose == _REQUIRED_PURPOSE
        and attempt.policy_version == _REQUIRED_POLICY_VERSION
    )


def _rebac_allows(context: _PolicyContext) -> bool:
    """Evaluate the authority path while leaving credential facts to ABAC."""

    attempt = context.attempt
    if (
        attempt.originating_principal_claim is None
        or attempt.logical_agent_claim is None
        or attempt.runtime_principal_claim is None
    ):
        return False
    agent = next(
        (
            item
            for item in context.state.snapshot.agents
            if item.id == attempt.logical_agent_claim
        ),
        None,
    )
    resource = next(
        (
            item
            for item in context.state.snapshot.resources
            if item.id == attempt.resource_id
        ),
        None,
    )
    runtime_matches = tuple(
        item
        for item in context.state.runtimes
        if item.runtime_principal_id == attempt.runtime_principal_claim
    )
    if agent is None or resource is None or len(runtime_matches) != 1:
        return False
    runtime = runtime_matches[0]
    if runtime.logical_agent_id != agent.id or not (
        runtime.organisation_id == agent.organisation_id == resource.organisation_id
    ):
        return False

    revoked = set(context.state.revoked_delegation_ids)
    return any(
        delegation.id not in revoked
        and delegation.grantee_agent_id == agent.id
        and delegation.originating_principal_id == attempt.originating_principal_claim
        and delegation.valid_from <= context.decision_time < delegation.expires_at
        and attempt.resource_id in delegation.capability.resource_ids
        and attempt.action in delegation.capability.actions
        and set(attempt.requested_scope) <= set(delegation.capability.scopes)
        and attempt.purpose == delegation.capability.purpose
        and attempt.policy_version == delegation.policy_version
        for delegation in context.state.delegations
    )


def _combined_allows(context: _PolicyContext) -> bool:
    return _rbac_allows(context) and _rebac_allows(context) and _abac_allows(context)


def _decision(allowed: bool) -> Decision:
    return Decision.ALLOW if allowed else Decision.DENY


__all__ = [
    "PolicyStrategy",
    "build_abac_trace",
    "build_combined_trace",
    "build_policy_traces",
    "build_rbac_trace",
    "build_rebac_trace",
]
