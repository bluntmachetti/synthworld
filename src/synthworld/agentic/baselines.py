"""Transparent reference baselines for the Asteria trace evaluator."""

from __future__ import annotations

from synthworld.agentic.models import (
    ActionAttempted,
    AgenticBenchmark,
    AgenticEvent,
    AgenticPublicBundle,
    AgenticTraceSubmission,
    CanonicalBinding,
    Decision,
    ObservedActionTrace,
)
from synthworld.agentic.relationships import derive_agent_owner_chain
from synthworld.agentic.replay import (
    AgenticReplayError,
    evaluate_action_authority,
    materialize_agentic_world,
)


def always_deny_agentic_trace(public: AgenticPublicBundle) -> AgenticTraceSubmission:
    """Return a public-only baseline that denies every attempted action."""

    return AgenticTraceSubmission(
        rows=tuple(
            _public_row(event, public, decision=Decision.DENY)
            for event in public.events
            if isinstance(event.payload, ActionAttempted)
        )
    )


def current_state_agentic_trace(
    public: AgenticPublicBundle,
) -> AgenticTraceSubmission:
    """Resolve public claims against audit-time state, exposing temporal errors."""

    audit_event = next(
        event for event in public.events if event.id == public.scenario.audit_event_id
    )
    audit_state = materialize_agentic_world(
        public.snapshot,
        public.events,
        at_event_index=audit_event.event_index - 1,
    )
    rows: list[ObservedActionTrace] = []
    for event in public.events:
        payload = event.payload
        if not isinstance(payload, ActionAttempted):
            continue
        attempt = payload.attempt
        runtime = next(
            (
                item
                for item in audit_state.runtimes
                if item.logical_agent_id == attempt.logical_agent_claim
                and item.runtime_principal_id == attempt.runtime_principal_claim
            ),
            None,
        )
        credential = next(
            (
                item
                for item in audit_state.credentials
                if item.id == attempt.presented_credential_id
            ),
            None,
        )
        if (
            runtime is None
            or credential is None
            or attempt.originating_principal_claim is None
            or attempt.logical_agent_claim is None
            or attempt.runtime_principal_claim is None
            or attempt.attributed_actor_claim is None
        ):
            raise AgenticReplayError(
                "current-state baseline requires complete public identity claims"
            )
        binding = CanonicalBinding(
            action_event_id=event.id,
            originating_principal_id=attempt.originating_principal_claim,
            logical_agent_id=attempt.logical_agent_claim,
            runtime_id=runtime.id,
            runtime_principal_id=attempt.runtime_principal_claim,
            credential_subject_id=credential.subject_principal_id,
            attributed_actor_id=attempt.attributed_actor_claim,
            accountable_owner_chain=derive_agent_owner_chain(
                public.snapshot, attempt.logical_agent_claim
            ),
        )
        decision = evaluate_action_authority(
            audit_state,
            attempt,
            binding,
            decision_time=audit_event.occurred_at,
        )
        rows.append(
            ObservedActionTrace(
                event_id=event.id,
                timestamp=event.occurred_at,
                originating_principal_id=binding.originating_principal_id,
                logical_agent_id=binding.logical_agent_id,
                runtime_principal_id=binding.runtime_principal_id,
                credential_subject_id=binding.credential_subject_id,
                attributed_actor_id=binding.attributed_actor_id,
                resource_id=attempt.resource_id,
                action=attempt.action,
                requested_scope=attempt.requested_scope,
                decision=decision.decision,
                decision_at_audit=decision.decision,
                side_effect=decision.expected_side_effect,
                policy_version=attempt.policy_version,
                delegation_chain_ids=decision.delegation_chain_ids,
                accountable_owner_chain=binding.accountable_owner_chain,
                evidence_refs=decision.required_evidence_refs,
                reconstructable_from_retained_evidence=set(
                    decision.required_evidence_refs
                ).issubset(audit_state.retained_evidence_refs),
            )
        )
    return AgenticTraceSubmission(rows=tuple(rows))


def reference_agentic_trace(benchmark: AgenticBenchmark) -> AgenticTraceSubmission:
    """Build the evaluator-only oracle ceiling used to validate metric behavior."""

    bindings = {item.action_event_id: item for item in benchmark.evaluator.bindings}
    truth = {item.action_event_id: item for item in benchmark.evaluator.authority_truth}
    rows: list[ObservedActionTrace] = []
    for event in benchmark.public.events:
        payload = event.payload
        if not isinstance(payload, ActionAttempted):
            continue
        binding = bindings[event.id]
        expected = truth[event.id]
        attempt = payload.attempt
        rows.append(
            ObservedActionTrace(
                event_id=event.id,
                timestamp=event.occurred_at,
                originating_principal_id=binding.originating_principal_id,
                logical_agent_id=binding.logical_agent_id,
                runtime_principal_id=binding.runtime_principal_id,
                credential_subject_id=binding.credential_subject_id,
                attributed_actor_id=binding.attributed_actor_id,
                resource_id=attempt.resource_id,
                action=attempt.action,
                requested_scope=attempt.requested_scope,
                decision=expected.decision_at_action,
                decision_at_audit=expected.decision_at_audit,
                side_effect=expected.expected_side_effect,
                policy_version=expected.expected_policy_version,
                delegation_chain_ids=expected.delegation_chain_ids,
                accountable_owner_chain=binding.accountable_owner_chain,
                evidence_refs=expected.required_evidence_refs,
                reconstructable_from_retained_evidence=(
                    expected.reconstructable_at_audit
                ),
            )
        )
    return AgenticTraceSubmission(rows=tuple(rows))


def _public_row(
    event: AgenticEvent,
    public: AgenticPublicBundle,
    *,
    decision: Decision,
) -> ObservedActionTrace:
    if not isinstance(event.payload, ActionAttempted):
        raise AgenticReplayError("always-deny baseline received a non-action event")
    attempt = event.payload.attempt
    credential = next(
        (
            item
            for item in materialize_agentic_world(
                public.snapshot, public.events
            ).credentials
            if item.id == attempt.presented_credential_id
        ),
        None,
    )
    return ObservedActionTrace(
        event_id=event.id,
        timestamp=event.occurred_at,
        originating_principal_id=attempt.originating_principal_claim,
        logical_agent_id=attempt.logical_agent_claim,
        runtime_principal_id=attempt.runtime_principal_claim,
        credential_subject_id=(
            credential.subject_principal_id if credential is not None else None
        ),
        attributed_actor_id=attempt.attributed_actor_claim,
        resource_id=attempt.resource_id,
        action=attempt.action,
        requested_scope=attempt.requested_scope,
        decision=decision,
        decision_at_audit=decision,
        side_effect="none",
        policy_version=attempt.policy_version,
        evidence_refs=attempt.evidence_refs,
    )


__all__ = [
    "always_deny_agentic_trace",
    "current_state_agentic_trace",
    "reference_agentic_trace",
]
