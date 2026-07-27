"""Semantic integrity checks for public/evaluator agentic benchmark joins."""

from __future__ import annotations

from typing import Protocol

from synthworld.agentic.errors import (
    AgenticBenchmarkIntegrityError,
    AgenticReplayError,
)
from synthworld.agentic.models import (
    ActionAttempted,
    AgenticEvent,
    AgenticWorldState,
    CanonicalBinding,
)
from synthworld.agentic.relationships import (
    derive_agent_owner_chain,
    derive_attributed_actor_candidates,
)


def validate_canonical_binding(
    state: AgenticWorldState,
    event: AgenticEvent,
    binding: CanonicalBinding,
) -> None:
    """Reject a canonical binding that contradicts action-time public records."""

    if not isinstance(event.payload, ActionAttempted):
        raise AgenticBenchmarkIntegrityError(
            "canonical binding must refer to an action event"
        )
    if binding.action_event_id != event.id:
        raise AgenticBenchmarkIntegrityError(
            "canonical binding action event does not match the public action"
        )

    snapshot = state.snapshot
    origin = _by_id(snapshot.principals, binding.originating_principal_id)
    agent = _by_id(snapshot.agents, binding.logical_agent_id)
    runtime = _by_id(state.runtimes, binding.runtime_id)
    credential = _by_id(
        state.credentials, event.payload.attempt.presented_credential_id
    )
    actor = _by_id(snapshot.principals, binding.attributed_actor_id)
    if origin is None:
        raise AgenticBenchmarkIntegrityError(
            "canonical binding references an unknown originating principal"
        )
    if agent is None:
        raise AgenticBenchmarkIntegrityError(
            "canonical binding references an unknown logical agent"
        )
    if runtime is None:
        raise AgenticBenchmarkIntegrityError(
            "canonical binding references a runtime unavailable at action time"
        )
    if credential is None:
        raise AgenticBenchmarkIntegrityError(
            "canonical binding references a credential unavailable at action time"
        )
    if actor is None:
        raise AgenticBenchmarkIntegrityError(
            "canonical binding references an unknown attributed actor"
        )
    if runtime.logical_agent_id != binding.logical_agent_id:
        raise AgenticBenchmarkIntegrityError(
            "canonical runtime belongs to a different logical agent"
        )
    if origin.organisation_id != agent.organisation_id:
        raise AgenticBenchmarkIntegrityError(
            "canonical originating principal crosses the logical agent tenant"
        )
    if runtime.runtime_principal_id != binding.runtime_principal_id:
        raise AgenticBenchmarkIntegrityError(
            "canonical runtime principal differs from the runtime record"
        )
    if credential.subject_principal_id != binding.credential_subject_id:
        raise AgenticBenchmarkIntegrityError(
            "canonical credential subject differs from the presented credential"
        )

    try:
        owner_chain = derive_agent_owner_chain(snapshot, binding.logical_agent_id)
        actors = derive_attributed_actor_candidates(snapshot, runtime, credential)
    except AgenticReplayError as error:
        raise AgenticBenchmarkIntegrityError(str(error)) from error
    if binding.accountable_owner_chain != owner_chain:
        raise AgenticBenchmarkIntegrityError(
            "canonical accountable owner chain differs from the ownership graph"
        )
    if binding.attributed_actor_id not in actors:
        raise AgenticBenchmarkIntegrityError(
            "canonical attributed actor is unrelated to runtime and credential paths"
        )


class _HasId(Protocol):
    id: str


def _by_id[ItemT: _HasId](items: tuple[ItemT, ...], identifier: str) -> ItemT | None:
    return next((item for item in items if item.id == identifier), None)


__all__ = ["AgenticBenchmarkIntegrityError", "validate_canonical_binding"]
