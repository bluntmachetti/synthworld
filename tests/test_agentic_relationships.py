from __future__ import annotations

from datetime import timedelta

import pytest

from synthworld.agentic import (
    generate_asteria_agentic_v1,
    materialize_agentic_world,
    relationships,
)
from synthworld.agentic.models import (
    CredentialIssued,
    DelegationGranted,
    RuntimeSpawned,
)
from synthworld.agentic.relationships import (
    delegator_is_authorised,
    derive_agent_owner_chain,
    derive_attributed_actor_candidates,
    derive_authorised_delegator_ids,
    derive_principal_owner_chain,
    derive_resource_owner_chain,
    derive_runtime_principal_path,
)
from synthworld.agentic.replay import AgenticReplayError


def test_owner_runtime_and_actor_relationships_are_derived_from_public_graph() -> None:
    benchmark = generate_asteria_agentic_v1()
    snapshot = benchmark.public.snapshot
    parent_runtime_event = benchmark.public.events[5]
    child_runtime_event = benchmark.public.events[6]
    parent_credential_event = benchmark.public.events[2]
    assert isinstance(parent_runtime_event.payload, RuntimeSpawned)
    assert isinstance(child_runtime_event.payload, RuntimeSpawned)
    assert isinstance(parent_credential_event.payload, CredentialIssued)

    assert derive_principal_owner_chain(
        snapshot, "principal-runtime-quotation-001"
    ) == (
        "principal-runtime-quotation-001",
        "principal-quotation-service",
        "principal-procurement-manager",
        "principal-asteria",
    )
    assert derive_agent_owner_chain(snapshot, "agent-quotation") == (
        "principal-procurement-manager",
        "principal-asteria",
    )
    assert derive_resource_owner_chain(snapshot, "resource-payroll") == (
        "principal-payroll-owner",
        "principal-asteria",
    )
    assert derive_runtime_principal_path(
        snapshot, parent_runtime_event.payload.runtime
    ) == (
        "principal-runtime-quotation-001",
        "principal-quotation-service",
        "principal-procurement-manager",
    )
    assert derive_attributed_actor_candidates(
        snapshot,
        child_runtime_event.payload.runtime,
        parent_credential_event.payload.credential,
    ) == {
        "principal-comparison-service",
        "principal-quotation-service",
    }


def test_asteria_root_and_child_delegators_follow_bounded_v1_authority() -> None:
    benchmark = generate_asteria_agentic_v1()
    task_event = benchmark.public.events[0]
    child_event = benchmark.public.events[8]
    later_event = benchmark.public.events[21]
    assert isinstance(task_event.payload, DelegationGranted)
    assert isinstance(child_event.payload, DelegationGranted)
    assert isinstance(later_event.payload, DelegationGranted)

    initial = materialize_agentic_world(
        benchmark.public.snapshot, benchmark.public.events, at_event_index=0
    )
    before_child = materialize_agentic_world(
        benchmark.public.snapshot, benchmark.public.events, at_event_index=8
    )
    before_later = materialize_agentic_world(
        benchmark.public.snapshot, benchmark.public.events, at_event_index=21
    )
    assert delegator_is_authorised(initial, task_event.payload.delegation, None)
    assert delegator_is_authorised(before_later, later_event.payload.delegation, None)

    parent = before_child.delegations[0]
    candidates = derive_authorised_delegator_ids(
        before_child, child_event.payload.delegation, parent
    )
    assert {
        "principal-runtime-quotation-001",
        "principal-quotation-service",
        "principal-procurement-manager",
        "principal-asteria",
    } <= candidates
    assert "principal-comparison-service" not in candidates
    assert "principal-payroll-owner" not in candidates


@pytest.mark.parametrize(
    "delegator_id",
    (
        "principal-quotation-service",
        "principal-runtime-quotation-001",
        "principal-procurement-manager",
        "principal-asteria",
    ),
)
def test_child_delegation_accepts_service_runtime_human_and_organisation(
    delegator_id: str,
) -> None:
    benchmark = generate_asteria_agentic_v1()
    child_event = benchmark.public.events[8]
    assert isinstance(child_event.payload, DelegationGranted)
    child = child_event.payload.delegation.model_copy(
        update={"delegator_principal_id": delegator_id}
    )
    events = list(benchmark.public.events[:9])
    events[8] = child_event.model_copy(
        update={"payload": DelegationGranted(delegation=child)}
    )
    state = materialize_agentic_world(benchmark.public.snapshot, tuple(events))
    assert state.delegations[-1].delegator_principal_id == delegator_id


def test_root_delegation_accepts_common_owner_and_rejects_unrelated_principal() -> None:
    benchmark = generate_asteria_agentic_v1()
    first_event = benchmark.public.events[0]
    later_event = benchmark.public.events[21]
    assert isinstance(first_event.payload, DelegationGranted)
    assert isinstance(later_event.payload, DelegationGranted)

    organisation_grant = first_event.payload.delegation.model_copy(
        update={"delegator_principal_id": "principal-asteria"}
    )
    state = materialize_agentic_world(
        benchmark.public.snapshot,
        (
            first_event.model_copy(
                update={"payload": DelegationGranted(delegation=organisation_grant)}
            ),
        ),
    )
    assert state.delegations[0].delegator_principal_id == "principal-asteria"

    unrelated = later_event.payload.delegation.model_copy(
        update={"delegator_principal_id": "principal-comparison-service"}
    )
    events = list(benchmark.public.events[:22])
    events[21] = later_event.model_copy(
        update={"payload": DelegationGranted(delegation=unrelated)}
    )
    with pytest.raises(AgenticReplayError, match="outside the bounded v1"):
        materialize_agentic_world(benchmark.public.snapshot, tuple(events))


@pytest.mark.parametrize(
    "delegator_id",
    ("principal-comparison-service", "principal-orion-service"),
)
def test_valid_attenuation_does_not_authorise_an_unrelated_child_delegator(
    delegator_id: str,
) -> None:
    benchmark = generate_asteria_agentic_v1()
    child_event = benchmark.public.events[8]
    assert isinstance(child_event.payload, DelegationGranted)
    changed = child_event.payload.delegation.model_copy(
        update={"delegator_principal_id": delegator_id}
    )
    events = list(benchmark.public.events[:9])
    events[8] = child_event.model_copy(
        update={"payload": DelegationGranted(delegation=changed)}
    )

    with pytest.raises(AgenticReplayError, match="outside the bounded v1"):
        materialize_agentic_world(benchmark.public.snapshot, tuple(events))


def test_parent_delegator_is_an_explicit_child_authority_without_a_runtime() -> None:
    benchmark = generate_asteria_agentic_v1()
    root_template_event = benchmark.public.events[0]
    later_event = benchmark.public.events[21]
    child_template_event = benchmark.public.events[8]
    assert isinstance(root_template_event.payload, DelegationGranted)
    assert isinstance(later_event.payload, DelegationGranted)
    assert isinstance(child_template_event.payload, DelegationGranted)

    event_one_time = root_template_event.occurred_at
    parent = later_event.payload.delegation.model_copy(
        update={
            "id": "delegation-payroll-parent",
            "capability": later_event.payload.delegation.capability.model_copy(
                update={"may_delegate": True}
            ),
            "valid_from": event_one_time - timedelta(minutes=1),
        }
    )
    child = parent.model_copy(
        update={
            "id": "delegation-payroll-child",
            "grantee_agent_id": (
                child_template_event.payload.delegation.grantee_agent_id
            ),
            "parent_delegation_id": parent.id,
            "capability": parent.capability.model_copy(update={"may_delegate": False}),
            "valid_from": event_one_time + timedelta(minutes=1),
        }
    )
    events = (
        root_template_event.model_copy(
            update={"payload": DelegationGranted(delegation=parent)}
        ),
        benchmark.public.events[1].model_copy(
            update={
                "id": "evt-002-payroll-child",
                "payload": DelegationGranted(delegation=child),
            }
        ),
    )

    state = materialize_agentic_world(benchmark.public.snapshot, events)
    assert tuple(item.id for item in state.delegations) == (parent.id, child.id)


def test_relationship_helpers_reject_unknown_cycles_and_cross_org_paths() -> None:
    benchmark = generate_asteria_agentic_v1()
    snapshot = benchmark.public.snapshot
    with pytest.raises(AgenticReplayError, match="unknown principal"):
        derive_principal_owner_chain(snapshot, "principal-unknown")
    with pytest.raises(AgenticReplayError, match="unknown agent"):
        derive_agent_owner_chain(snapshot, "agent-unknown")
    with pytest.raises(AgenticReplayError, match="unknown resource"):
        derive_resource_owner_chain(snapshot, "resource-unknown")

    principals = list(snapshot.principals)
    manager_index = next(
        index
        for index, principal in enumerate(principals)
        if principal.id == "principal-procurement-manager"
    )
    principals[manager_index] = principals[manager_index].model_copy(
        update={"owner_principal_id": "principal-quotation-service"}
    )
    cyclic = snapshot.model_copy(update={"principals": tuple(principals)})
    with pytest.raises(AgenticReplayError, match="cycle"):
        derive_principal_owner_chain(cyclic, "principal-procurement-manager")

    principals = list(snapshot.principals)
    principals[manager_index] = principals[manager_index].model_copy(
        update={"organisation_id": "org-orion"}
    )
    cross_org = snapshot.model_copy(update={"principals": tuple(principals)})
    with pytest.raises(AgenticReplayError, match="crosses organisation"):
        derive_agent_owner_chain(cross_org, "agent-quotation")

    with pytest.raises(AgenticReplayError, match="no non-workload"):
        relationships._first_non_workload(
            snapshot, ("principal-runtime-quotation-001",)
        )


def test_runtime_path_rejects_defensive_cycle_unknown_owner_and_cross_org_hop() -> None:
    benchmark = generate_asteria_agentic_v1()
    snapshot = benchmark.public.snapshot
    runtime_event = benchmark.public.events[5]
    assert isinstance(runtime_event.payload, RuntimeSpawned)
    runtime = runtime_event.payload.runtime
    with pytest.raises(AgenticReplayError, match="unknown identity"):
        derive_runtime_principal_path(
            snapshot, runtime.model_copy(update={"logical_agent_id": "agent-unknown"})
        )

    workload_index = next(
        index
        for index, principal in enumerate(snapshot.principals)
        if principal.id == runtime.runtime_principal_id
    )
    service_index = next(
        index
        for index, principal in enumerate(snapshot.principals)
        if principal.id == "principal-quotation-service"
    )
    for owner_id, message in (
        (runtime.runtime_principal_id, "cycle"),
        ("principal-unknown", "unknown owner"),
    ):
        principals = list(snapshot.principals)
        principals[workload_index] = principals[workload_index].model_copy(
            update={"owner_principal_id": owner_id}
        )
        changed = snapshot.model_copy(update={"principals": tuple(principals)})
        with pytest.raises(AgenticReplayError, match=message):
            derive_runtime_principal_path(changed, runtime)

    principals = list(snapshot.principals)
    principals[service_index] = principals[service_index].model_copy(
        update={"organisation_id": "org-orion"}
    )
    changed = snapshot.model_copy(update={"principals": tuple(principals)})
    with pytest.raises(AgenticReplayError, match="crosses organisation"):
        derive_runtime_principal_path(changed, runtime)


def test_actor_and_delegator_helpers_reject_unusable_public_relationships() -> None:
    benchmark = generate_asteria_agentic_v1()
    snapshot = benchmark.public.snapshot
    child_runtime_event = benchmark.public.events[6]
    parent_credential_event = benchmark.public.events[2]
    child_event = benchmark.public.events[8]
    assert isinstance(child_runtime_event.payload, RuntimeSpawned)
    assert isinstance(parent_credential_event.payload, CredentialIssued)
    assert isinstance(child_event.payload, DelegationGranted)

    subject_id = parent_credential_event.payload.credential.subject_principal_id
    principals = tuple(
        principal.model_copy(update={"organisation_id": None})
        if principal.id == subject_id
        else principal
        for principal in snapshot.principals
    )
    no_subject_org = snapshot.model_copy(update={"principals": principals})
    with pytest.raises(AgenticReplayError, match="lacks an organisation"):
        derive_attributed_actor_candidates(
            no_subject_org,
            child_runtime_event.payload.runtime,
            parent_credential_event.payload.credential,
        )

    before_child = materialize_agentic_world(
        snapshot, benchmark.public.events, at_event_index=8
    )
    child = child_event.payload.delegation
    assert not derive_authorised_delegator_ids(
        before_child,
        child.model_copy(update={"delegator_principal_id": "principal-unknown"}),
        before_child.delegations[0],
    )
    assert not derive_authorised_delegator_ids(
        before_child,
        child.model_copy(update={"delegator_principal_id": "principal-orion-service"}),
        before_child.delegations[0],
    )
    wrong_parent = before_child.delegations[0].model_copy(
        update={"grantee_agent_id": "agent-comparison"}
    )
    assert not derive_authorised_delegator_ids(before_child, child, wrong_parent)


@pytest.mark.parametrize(
    ("update", "message"),
    (
        ({"owner_principal_id": "principal-asteria"}, "owner must match"),
        ({"runtime_principal_id": "principal-payroll-owner"}, "does not reach"),
        (
            {"runtime_principal_id": "principal-orion-service"},
            "organisation must match",
        ),
    ),
)
def test_runtime_relationship_rejects_incoherent_identity_paths(
    update: dict[str, str], message: str
) -> None:
    benchmark = generate_asteria_agentic_v1()
    runtime_event = benchmark.public.events[5]
    assert isinstance(runtime_event.payload, RuntimeSpawned)
    runtime = runtime_event.payload.runtime.model_copy(update=update)
    with pytest.raises(AgenticReplayError, match=message):
        derive_runtime_principal_path(benchmark.public.snapshot, runtime)
