from __future__ import annotations

from datetime import timedelta

import pytest

from synthworld.agentic import (
    generate_asteria_agentic_v1,
    materialize_agentic_world,
    replay,
)
from synthworld.agentic.models import (
    ActionAttempted,
    AuthorityFailureReason,
    CredentialIssued,
    DelegationGranted,
    DelegationRevoked,
    EvidenceDiscarded,
    PolicyVersion,
    RuntimeSpawned,
)
from synthworld.agentic.replay import AgenticReplayError, evaluate_action_authority


def _materialize_replaced(index: int, payload: object) -> None:
    benchmark = generate_asteria_agentic_v1()
    events = list(benchmark.public.events[: index + 1])
    events[index] = events[index].model_copy(update={"payload": payload})
    materialize_agentic_world(benchmark.public.snapshot, tuple(events))


@pytest.mark.parametrize(
    ("change", "message"),
    (
        ("duplicate", "IDs must be unique"),
        ("origin", "unknown principal"),
        ("delegator", "unknown principal"),
        ("agent", "unknown agent"),
        ("resource", "unknown resource"),
        ("policy", "unknown policy"),
        ("time", "outside its validity"),
    ),
)
def test_delegation_event_validation(change: str, message: str) -> None:
    benchmark = generate_asteria_agentic_v1()
    first = benchmark.public.events[0]
    second = benchmark.public.events[1]
    assert isinstance(first.payload, DelegationGranted)
    assert isinstance(second.payload, DelegationGranted)
    delegation = first.payload.delegation
    index = 0
    if change == "duplicate":
        delegation = second.payload.delegation.model_copy(update={"id": delegation.id})
        index = 1
    elif change == "origin":
        delegation = delegation.model_copy(
            update={"originating_principal_id": "principal-unknown"}
        )
    elif change == "delegator":
        delegation = delegation.model_copy(
            update={"delegator_principal_id": "principal-unknown"}
        )
    elif change == "agent":
        delegation = delegation.model_copy(update={"grantee_agent_id": "agent-bad"})
    elif change == "resource":
        capability = delegation.capability.model_copy(
            update={"resource_ids": ("resource-bad",)}
        )
        delegation = delegation.model_copy(update={"capability": capability})
    elif change == "policy":
        delegation = delegation.model_copy(update={"policy_version": "policy-bad"})
    else:
        delegation = delegation.model_copy(
            update={"valid_from": first.occurred_at + timedelta(minutes=1)}
        )
    with pytest.raises(AgenticReplayError, match=message):
        _materialize_replaced(index, DelegationGranted(delegation=delegation))


def test_child_delegation_requires_an_active_attenuating_parent() -> None:
    benchmark = generate_asteria_agentic_v1()
    child_event = benchmark.public.events[8]
    assert isinstance(child_event.payload, DelegationGranted)
    child = child_event.payload.delegation

    missing = child.model_copy(update={"parent_delegation_id": "delegation-bad"})
    with pytest.raises(AgenticReplayError, match="active parent"):
        _materialize_replaced(8, DelegationGranted(delegation=missing))

    events = list(benchmark.public.events[:9])
    assert child.parent_delegation_id is not None
    events[7] = events[7].model_copy(
        update={"payload": DelegationRevoked(delegation_id=child.parent_delegation_id)}
    )
    with pytest.raises(AgenticReplayError, match="active parent"):
        materialize_agentic_world(benchmark.public.snapshot, tuple(events))

    broader = child.model_copy(
        update={
            "capability": child.capability.model_copy(
                update={"resource_ids": ("resource-payroll",)}
            )
        }
    )
    with pytest.raises(AgenticReplayError, match="must be attenuated"):
        _materialize_replaced(8, DelegationGranted(delegation=broader))


@pytest.mark.parametrize(
    ("change", "message"),
    (
        ("duplicate", "IDs must be unique"),
        ("issuer", "unknown principal"),
        ("subject", "unknown principal"),
        ("runtime", "unknown runtime principal"),
        ("time", "outside its validity"),
    ),
)
def test_credential_event_validation(change: str, message: str) -> None:
    benchmark = generate_asteria_agentic_v1()
    parent_event = benchmark.public.events[2]
    child_event = benchmark.public.events[3]
    assert isinstance(parent_event.payload, CredentialIssued)
    assert isinstance(child_event.payload, CredentialIssued)
    credential = child_event.payload.credential
    if change == "duplicate":
        credential = credential.model_copy(
            update={"id": parent_event.payload.credential.id}
        )
    elif change == "issuer":
        credential = credential.model_copy(
            update={"issuer_principal_id": "principal-bad"}
        )
    elif change == "subject":
        credential = credential.model_copy(
            update={"subject_principal_id": "principal-bad"}
        )
    elif change == "runtime":
        credential = credential.model_copy(
            update={"allowed_runtime_principal_ids": ("principal-bad",)}
        )
    else:
        credential = credential.model_copy(
            update={"valid_from": child_event.occurred_at + timedelta(minutes=1)}
        )
    with pytest.raises(AgenticReplayError, match=message):
        _materialize_replaced(3, CredentialIssued(credential=credential))


@pytest.mark.parametrize(
    ("change", "message"),
    (
        ("duplicate", "IDs must be unique"),
        ("agent", "unknown identity"),
        ("principal", "unknown identity"),
        ("owner", "unknown identity"),
        ("organisation", "organisation must match"),
        ("mismatch", "organisation must match"),
    ),
)
def test_runtime_event_validation(change: str, message: str) -> None:
    benchmark = generate_asteria_agentic_v1()
    parent_event = benchmark.public.events[5]
    child_event = benchmark.public.events[6]
    assert isinstance(parent_event.payload, RuntimeSpawned)
    assert isinstance(child_event.payload, RuntimeSpawned)
    runtime = child_event.payload.runtime
    if change == "duplicate":
        runtime = runtime.model_copy(update={"id": parent_event.payload.runtime.id})
    elif change == "agent":
        runtime = runtime.model_copy(update={"logical_agent_id": "agent-bad"})
    elif change == "principal":
        runtime = runtime.model_copy(update={"runtime_principal_id": "principal-bad"})
    elif change == "owner":
        runtime = runtime.model_copy(update={"owner_principal_id": "principal-bad"})
    elif change == "organisation":
        runtime = runtime.model_copy(update={"organisation_id": "org-bad"})
    else:
        runtime = runtime.model_copy(update={"organisation_id": "org-orion"})
    with pytest.raises(AgenticReplayError, match=message):
        _materialize_replaced(6, RuntimeSpawned(runtime=runtime))


@pytest.mark.parametrize(
    ("change", "message"),
    (
        ("credential", "not yet issued"),
        ("resource", "unknown resource action"),
        ("action", "unknown resource action"),
        ("principal", "unknown principal claim"),
        ("agent", "unknown agent claim"),
        ("evidence", "evidence unavailable"),
        ("proposal_agent", "broken references"),
        ("proposal_origin", "broken references"),
    ),
)
def test_action_event_validation(change: str, message: str) -> None:
    benchmark = generate_asteria_agentic_v1()
    action_event = benchmark.public.events[9]
    proposal_event = benchmark.public.events[11]
    assert isinstance(action_event.payload, ActionAttempted)
    assert isinstance(proposal_event.payload, ActionAttempted)
    attempt = action_event.payload.attempt
    if change == "credential":
        attempt = attempt.model_copy(update={"presented_credential_id": "cred-bad"})
    elif change == "resource":
        attempt = attempt.model_copy(update={"resource_id": "resource-bad"})
    elif change == "action":
        attempt = attempt.model_copy(update={"action": "bad"})
    elif change == "principal":
        attempt = attempt.model_copy(
            update={"originating_principal_claim": "principal-bad"}
        )
    elif change == "agent":
        attempt = attempt.model_copy(update={"logical_agent_claim": "agent-bad"})
    elif change == "evidence":
        attempt = attempt.model_copy(update={"evidence_refs": ("evidence:bad",)})
    else:
        proposal = proposal_event.payload.attempt.proposed_delegation
        assert proposal is not None
        field = (
            "grantee_agent_id"
            if change == "proposal_agent"
            else "originating_principal_id"
        )
        proposal = proposal.model_copy(update={field: "bad"})
        attempt = attempt.model_copy(update={"proposed_delegation": proposal})
    with pytest.raises(AgenticReplayError, match=message):
        _materialize_replaced(9, ActionAttempted(attempt=attempt))


def test_action_claims_may_be_absent_and_replay_still_scores_them() -> None:
    benchmark = generate_asteria_agentic_v1()
    action_event = benchmark.public.events[9]
    assert isinstance(action_event.payload, ActionAttempted)
    attempt = action_event.payload.attempt.model_copy(
        update={
            "originating_principal_claim": None,
            "logical_agent_claim": None,
            "runtime_principal_claim": None,
            "attributed_actor_claim": None,
        }
    )
    _materialize_replaced(9, ActionAttempted(attempt=attempt))


def test_replay_rejects_unknown_revocation_and_missing_evidence_discard() -> None:
    benchmark = generate_asteria_agentic_v1()
    with pytest.raises(AgenticReplayError, match="unknown or inactive"):
        _materialize_replaced(18, DelegationRevoked(delegation_id="delegation-bad"))
    events = list(benchmark.public.events)
    events[-1] = events[-1].model_copy(
        update={
            "payload": DelegationRevoked(
                delegation_id="delegation-procurement-task-001"
            )
        }
    )
    with pytest.raises(AgenticReplayError, match="unknown or inactive"):
        materialize_agentic_world(benchmark.public.snapshot, tuple(events))
    with pytest.raises(AgenticReplayError, match="not retained"):
        _materialize_replaced(22, EvidenceDiscarded(evidence_refs=("evidence:bad",)))


def test_authority_evaluation_classifies_broken_bindings_and_policy() -> None:
    benchmark = generate_asteria_agentic_v1()
    event = benchmark.public.events[9]
    assert isinstance(event.payload, ActionAttempted)
    binding = benchmark.evaluator.bindings[0]
    state = materialize_agentic_world(
        benchmark.public.snapshot,
        benchmark.public.events,
        at_event_index=9,
    )
    cases = (
        (
            event.payload.attempt,
            binding.model_copy(update={"runtime_id": "runtime-bad"}),
            AuthorityFailureReason.WRONG_RUNTIME,
        ),
        (
            event.payload.attempt,
            binding.model_copy(update={"credential_subject_id": "principal-bad"}),
            AuthorityFailureReason.CREDENTIAL_INVALID,
        ),
        (
            event.payload.attempt.model_copy(update={"resource_id": "resource-bad"}),
            binding,
            AuthorityFailureReason.NO_ACTIVE_DELEGATION,
        ),
        (
            event.payload.attempt.model_copy(update={"policy_version": "policy-bad"}),
            binding,
            AuthorityFailureReason.POLICY_VERSION_MISMATCH,
        ),
    )
    for attempt, changed_binding, reason in cases:
        result = evaluate_action_authority(
            state,
            attempt,
            changed_binding,
            decision_time=event.occurred_at,
        )
        assert reason in result.failure_reasons
    with pytest.raises(AgenticReplayError, match="UTC"):
        evaluate_action_authority(
            state,
            event.payload.attempt,
            binding,
            decision_time=event.occurred_at.replace(tzinfo=None),
        )

    policy_v2 = PolicyVersion(id="policy-asteria-v2", version="asteria-policy-v2")
    v2_state = state.model_copy(
        update={
            "snapshot": state.snapshot.model_copy(
                update={"policies": (*state.snapshot.policies, policy_v2)}
            )
        }
    )
    v2_attempt = event.payload.attempt.model_copy(
        update={"policy_version": policy_v2.version}
    )
    v2_result = evaluate_action_authority(
        v2_state,
        v2_attempt,
        binding,
        decision_time=event.occurred_at,
    )
    assert AuthorityFailureReason.POLICY_VERSION_MISMATCH in v2_result.failure_reasons


def test_attenuated_proposal_is_not_misclassified_as_overprivileged() -> None:
    benchmark = generate_asteria_agentic_v1()
    event = benchmark.public.events[11]
    child_event = benchmark.public.events[8]
    assert isinstance(event.payload, ActionAttempted)
    assert isinstance(child_event.payload, DelegationGranted)
    state = materialize_agentic_world(
        benchmark.public.snapshot,
        benchmark.public.events,
        at_event_index=11,
    )
    attempt = event.payload.attempt.model_copy(
        update={"proposed_delegation": child_event.payload.delegation}
    )
    result = evaluate_action_authority(
        state,
        attempt,
        benchmark.evaluator.bindings[2],
        decision_time=event.occurred_at,
    )
    assert AuthorityFailureReason.OVERPRIVILEGED_SUBDELEGATION not in (
        result.failure_reasons
    )


def test_defensive_chain_helpers_handle_missing_parents_and_unknown_actions() -> None:
    benchmark = generate_asteria_agentic_v1()
    parent_event = benchmark.public.events[0]
    child_event = benchmark.public.events[8]
    assert isinstance(parent_event.payload, DelegationGranted)
    assert isinstance(child_event.payload, DelegationGranted)
    parent = parent_event.payload.delegation
    child = child_event.payload.delegation
    with pytest.raises(AgenticReplayError, match="missing parent"):
        replay._delegation_chain(child, (child,))
    assert replay._has_ancestor(child, "other", (child,)) is False
    assert replay._has_ancestor(child, "other", (parent, child)) is False
    assert replay._side_effect_for("custom_action") == "action_recorded"


def test_timestamp_cursor_at_end_reuses_fully_validated_state() -> None:
    benchmark = generate_asteria_agentic_v1()
    by_index = materialize_agentic_world(
        benchmark.public.snapshot,
        benchmark.public.events,
        at_event_index=len(benchmark.public.events),
    )
    by_time = materialize_agentic_world(
        benchmark.public.snapshot,
        benchmark.public.events,
        at_timestamp=benchmark.public.events[-1].occurred_at + timedelta(minutes=1),
    )
    assert by_index == by_time
