"""Build physically separate public and evaluator views of an agentic world."""

from __future__ import annotations

from typing import cast

from synthworld.agentic.errors import (
    AgenticBenchmarkIntegrityError,
    AgenticReplayError,
)
from synthworld.agentic.integrity import validate_canonical_binding
from synthworld.agentic.models import (
    ActionAttempted,
    AgenticBenchmark,
    AgenticCase,
    AgenticEvaluatorBundle,
    AgenticEvent,
    AgenticPublicBundle,
    AgenticWorldSnapshot,
    AuditPerformed,
    AuthorityTruth,
    CanonicalBinding,
    PublicScenario,
)
from synthworld.agentic.replay import (
    evaluate_action_authority,
    materialize_agentic_world,
)


def build_agentic_benchmark(
    snapshot: AgenticWorldSnapshot,
    events: tuple[AgenticEvent, ...],
    scenario: PublicScenario,
    bindings: tuple[CanonicalBinding, ...],
    cases: tuple[AgenticCase, ...],
) -> AgenticBenchmark:
    """Project public input field-by-field and derive evaluator-only truth."""

    public = AgenticPublicBundle(
        snapshot=snapshot,
        events=events,
        scenario=scenario,
    )
    materialize_agentic_world(snapshot, events)
    action_events = {
        event.id: event
        for event in events
        if isinstance(event.payload, ActionAttempted)
    }
    audit_events = tuple(
        event for event in events if isinstance(event.payload, AuditPerformed)
    )
    if len(audit_events) != 1 or audit_events[0].id != scenario.audit_event_id:
        raise AgenticReplayError(
            "scenario audit event must be an audit event and the only audit event"
        )
    audit_event = audit_events[0]

    binding_ids = tuple(item.action_event_id for item in bindings)
    case_ids = tuple(item.action_event_id for item in cases)
    action_ids = tuple(scenario.action_event_ids)
    _require_exact_action_keys(binding_ids, action_ids, "canonical bindings")
    _require_exact_action_keys(case_ids, action_ids, "agentic cases")
    binding_by_event = {item.action_event_id: item for item in bindings}

    audit_state = materialize_agentic_world(
        snapshot,
        events,
        at_event_index=audit_event.event_index - 1,
    )
    truth: list[AuthorityTruth] = []
    for event_id in scenario.action_event_ids:
        event = action_events[event_id]
        payload = cast(ActionAttempted, event.payload)
        binding = binding_by_event[event_id]
        action_state = materialize_agentic_world(
            snapshot,
            events,
            at_event_index=event.event_index - 1,
        )
        validate_canonical_binding(action_state, event, binding)
        action_decision = evaluate_action_authority(
            action_state,
            payload.attempt,
            binding,
            decision_time=event.occurred_at,
        )
        audit_decision = evaluate_action_authority(
            audit_state,
            payload.attempt,
            binding,
            decision_time=audit_event.occurred_at,
        )
        truth.append(
            AuthorityTruth(
                action_event_id=event.id,
                decision_at_action=action_decision.decision,
                decision_at_audit=audit_decision.decision,
                failure_reasons_at_action=action_decision.failure_reasons,
                failure_reasons_at_audit=audit_decision.failure_reasons,
                delegation_chain_ids=action_decision.delegation_chain_ids,
                # Action-time, matching `decision_at_action`. Six of Asteria's eleven
                # actions resolve a different delegation at audit time, so the two
                # evaluations genuinely disagree; the audit-time effective version is
                # deliberately discarded rather than absent by oversight.
                expected_policy_version=action_decision.effective_policy_version,
                required_evidence_refs=action_decision.required_evidence_refs,
                reconstructable_at_audit=set(
                    action_decision.required_evidence_refs
                ).issubset(audit_state.retained_evidence_refs),
                expected_side_effect=action_decision.expected_side_effect,
            )
        )

    evaluator = AgenticEvaluatorBundle(
        world_id=snapshot.world_id,
        world_version=snapshot.world_version,
        seed=snapshot.seed,
        audit_event_id=scenario.audit_event_id,
        bindings=bindings,
        authority_truth=tuple(truth),
        cases=cases,
    )
    return AgenticBenchmark(public=public, evaluator=evaluator)


def _require_exact_action_keys(
    provided: tuple[str, ...],
    expected: tuple[str, ...],
    label: str,
) -> None:
    if len(provided) != len(set(provided)):
        raise AgenticBenchmarkIntegrityError(f"{label} must be unique")
    missing = sorted(set(expected) - set(provided))
    unknown = sorted(set(provided) - set(expected))
    if missing or unknown:
        raise AgenticBenchmarkIntegrityError(
            f"{label} must cover every action exactly once; "
            f"missing={missing}, unknown={unknown}"
        )


__all__ = ["build_agentic_benchmark"]
