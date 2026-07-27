"""Bounded v1 identity and delegation relationships for agentic worlds."""

from __future__ import annotations

from synthworld.agentic.errors import AgenticReplayError
from synthworld.agentic.models import (
    AgenticWorldSnapshot,
    AgenticWorldState,
    Credential,
    Delegation,
    LogicalAgent,
    Principal,
    PrincipalKind,
    Resource,
    Runtime,
)


def derive_principal_owner_chain(
    snapshot: AgenticWorldSnapshot,
    principal_id: str,
) -> tuple[str, ...]:
    """Return an inclusive principal-to-ultimate-owner chain."""

    principals = {item.id: item for item in snapshot.principals}
    chain: list[str] = []
    seen: set[str] = set()
    current_id: str | None = principal_id
    while current_id is not None:
        if current_id in seen:
            raise AgenticReplayError("principal ownership chain contains a cycle")
        principal = principals.get(current_id)
        if principal is None:
            raise AgenticReplayError(
                "principal ownership chain references an unknown principal"
            )
        seen.add(current_id)
        chain.append(current_id)
        current_id = principal.owner_principal_id
    return tuple(chain)


def derive_agent_owner_chain(
    snapshot: AgenticWorldSnapshot,
    logical_agent_id: str,
) -> tuple[str, ...]:
    """Return the agent's exact accountable-owner chain."""

    agent = _by_id(snapshot.agents, logical_agent_id)
    if agent is None:
        raise AgenticReplayError("agent owner chain references an unknown agent")
    chain = derive_principal_owner_chain(snapshot, agent.owner_principal_id)
    _require_chain_organisation(
        snapshot,
        chain,
        agent.organisation_id,
        "agent owner chain",
    )
    return chain


def derive_resource_owner_chain(
    snapshot: AgenticWorldSnapshot,
    resource_id: str,
) -> tuple[str, ...]:
    """Return the resource owner's inclusive authority chain."""

    resource = _by_id(snapshot.resources, resource_id)
    if resource is None:
        raise AgenticReplayError("resource owner chain references an unknown resource")
    chain = derive_principal_owner_chain(snapshot, resource.owner_principal_id)
    _require_chain_organisation(
        snapshot,
        chain,
        resource.organisation_id,
        "resource owner chain",
    )
    return chain


def derive_runtime_principal_path(
    snapshot: AgenticWorldSnapshot,
    runtime: Runtime,
) -> tuple[str, ...]:
    """Return the runtime-principal path through its declared accountable owner."""

    agent = _by_id(snapshot.agents, runtime.logical_agent_id)
    runtime_principal = _by_id(snapshot.principals, runtime.runtime_principal_id)
    runtime_owner = _by_id(snapshot.principals, runtime.owner_principal_id)
    if agent is None or runtime_principal is None or runtime_owner is None:
        raise AgenticReplayError("runtime references an unknown identity")
    if runtime.organisation_id not in {
        item.id for item in snapshot.organisations
    } or not (
        agent.organisation_id
        == runtime_principal.organisation_id
        == runtime_owner.organisation_id
        == runtime.organisation_id
    ):
        raise AgenticReplayError(
            "runtime organisation must match its agent and identity graph"
        )
    if runtime.owner_principal_id != agent.owner_principal_id:
        raise AgenticReplayError("runtime owner must match its logical agent owner")

    principals = {item.id: item for item in snapshot.principals}
    path: list[str] = []
    seen: set[str] = set()
    current_id: str | None = runtime.runtime_principal_id
    while current_id is not None:
        if current_id in seen:
            raise AgenticReplayError("runtime principal path contains a cycle")
        principal = principals.get(current_id)
        if principal is None:
            raise AgenticReplayError(
                "runtime principal path references an unknown owner"
            )
        if principal.organisation_id != runtime.organisation_id:
            raise AgenticReplayError(
                "runtime principal path crosses organisation boundaries"
            )
        seen.add(current_id)
        path.append(current_id)
        if current_id == runtime.owner_principal_id:
            return tuple(path)
        current_id = principal.owner_principal_id
    raise AgenticReplayError("runtime principal path does not reach its declared owner")


def derive_attributed_actor_candidates(
    snapshot: AgenticWorldSnapshot,
    runtime: Runtime,
    credential: Credential,
) -> frozenset[str]:
    """Return the actors admissible under the bounded v1 attribution convention.

    V1 has no explicit actor relation. A mismatched credential/runtime negative can
    canonically follow either identity path, so integrity validation can constrain
    the actor to these public paths but cannot choose between them.
    """

    runtime_path = derive_runtime_principal_path(snapshot, runtime)
    credential_path = derive_principal_owner_chain(
        snapshot, credential.subject_principal_id
    )
    subject = _by_id(snapshot.principals, credential.subject_principal_id)
    if subject is None or subject.organisation_id is None:
        raise AgenticReplayError("credential subject lacks an organisation")
    _require_chain_organisation(
        snapshot,
        credential_path,
        subject.organisation_id,
        "credential subject chain",
    )
    return frozenset(
        {
            _first_non_workload(snapshot, runtime_path),
            _first_non_workload(snapshot, credential_path),
        }
    )


def derive_authorised_delegator_ids(
    state: AgenticWorldState,
    delegation: Delegation,
    parent: Delegation | None,
) -> frozenset[str]:
    """Return delegators authorised by SynthWorld's bounded agentic-v1 rule."""

    snapshot = state.snapshot
    grantee = _by_id(snapshot.agents, delegation.grantee_agent_id)
    origin = _by_id(snapshot.principals, delegation.originating_principal_id)
    delegator = _by_id(snapshot.principals, delegation.delegator_principal_id)
    resources = tuple(
        _by_id(snapshot.resources, resource_id)
        for resource_id in delegation.capability.resource_ids
    )
    if (
        grantee is None
        or origin is None
        or delegator is None
        or any(resource is None for resource in resources)
    ):
        return frozenset()
    if not _delegation_organisation_is_coherent(
        grantee,
        origin,
        delegator,
        tuple(resource for resource in resources if resource is not None),
    ):
        return frozenset()

    if parent is None:
        resource_chains = tuple(
            set(derive_resource_owner_chain(snapshot, resource_id))
            for resource_id in delegation.capability.resource_ids
        )
        common_resource_owners = set.intersection(*resource_chains)
        return frozenset({delegation.originating_principal_id, *common_resource_owners})

    parent_agent = _by_id(snapshot.agents, parent.grantee_agent_id)
    if (
        parent_agent is None
        or parent_agent.organisation_id != grantee.organisation_id
        or grantee.parent_agent_id != parent.grantee_agent_id
    ):
        return frozenset()
    candidates = {
        parent.originating_principal_id,
        parent.delegator_principal_id,
        *derive_agent_owner_chain(snapshot, parent.grantee_agent_id),
    }
    for runtime in state.runtimes:
        if runtime.logical_agent_id == parent.grantee_agent_id:
            candidates.update(derive_runtime_principal_path(snapshot, runtime))
    return frozenset(
        principal_id
        for principal_id in candidates
        if _principal_has_organisation(snapshot, principal_id, grantee.organisation_id)
    )


def delegator_is_authorised(
    state: AgenticWorldState,
    delegation: Delegation,
    parent: Delegation | None,
) -> bool:
    """Return whether a declared delegator is related to the delegated authority."""

    return delegation.delegator_principal_id in derive_authorised_delegator_ids(
        state, delegation, parent
    )


def _first_non_workload(
    snapshot: AgenticWorldSnapshot,
    chain: tuple[str, ...],
) -> str:
    principals = {item.id: item for item in snapshot.principals}
    for principal_id in chain:
        principal = principals[principal_id]
        if principal.kind is not PrincipalKind.WORKLOAD:
            return principal_id
    raise AgenticReplayError("principal path has no non-workload attributed actor")


def _require_chain_organisation(
    snapshot: AgenticWorldSnapshot,
    chain: tuple[str, ...],
    organisation_id: str,
    label: str,
) -> None:
    principals = {item.id: item for item in snapshot.principals}
    if any(
        principals[principal_id].organisation_id != organisation_id
        for principal_id in chain
    ):
        raise AgenticReplayError(f"{label} crosses organisation boundaries")


def _delegation_organisation_is_coherent(
    grantee: LogicalAgent,
    origin: Principal,
    delegator: Principal,
    resources: tuple[Resource, ...],
) -> bool:
    organisation_id = grantee.organisation_id
    return (
        origin.organisation_id == organisation_id
        and delegator.organisation_id == organisation_id
        and all(resource.organisation_id == organisation_id for resource in resources)
    )


def _principal_has_organisation(
    snapshot: AgenticWorldSnapshot,
    principal_id: str,
    organisation_id: str,
) -> bool:
    principal = _by_id(snapshot.principals, principal_id)
    return principal is not None and principal.organisation_id == organisation_id


def _by_id[ItemT](items: tuple[ItemT, ...], identifier: str) -> ItemT | None:
    return next(
        (item for item in items if getattr(item, "id", None) == identifier), None
    )


__all__ = [
    "delegator_is_authorised",
    "derive_agent_owner_chain",
    "derive_attributed_actor_candidates",
    "derive_authorised_delegator_ids",
    "derive_principal_owner_chain",
    "derive_resource_owner_chain",
    "derive_runtime_principal_path",
]
