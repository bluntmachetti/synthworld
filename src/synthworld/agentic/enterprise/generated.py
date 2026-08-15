"""Deterministic generation for the bounded enterprise-agentic smoke tier."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid5

from synthworld.agentic.enterprise.generated_models import (
    EnterpriseAgenticBenchmarkIdentityV1,
    EnterpriseAgenticCountMetricV1,
    EnterpriseAgenticDistributionBinV1,
    EnterpriseAgenticGeneratedBenchmarkV1,
    EnterpriseAgenticGenerationConfigV1,
    EnterpriseAgenticIntegrityMetricsV1,
)
from synthworld.agentic.models import (
    ActionAttempt,
    ActionAttempted,
    AgenticBenchmark,
    AgenticCase,
    AgenticCaseKind,
    AgenticEvent,
    AgenticEventPayload,
    AgenticWorldSnapshot,
    AuditPerformed,
    CanonicalBinding,
    Capability,
    Credential,
    CredentialIssued,
    Decision,
    Delegation,
    DelegationGranted,
    DelegationRevoked,
    Department,
    EvidenceDiscarded,
    LogicalAgent,
    Organisation,
    PolicyVersion,
    Principal,
    PrincipalKind,
    PublicScenario,
    Resource,
    Runtime,
    RuntimeSpawned,
)
from synthworld.agentic.projection import build_agentic_benchmark
from synthworld.agentic.relationships import derive_agent_owner_chain
from synthworld.agentic.replay import materialize_agentic_world
from synthworld.enterprise.canonical import canonical_json_bytes, encode_parts

_GENERATED_ENTERPRISE_AGENTIC_NAMESPACE_V1 = UUID(
    "0e56d078-256d-50f9-8077-9ab7fdcd97ee"
)
_POLICY_VERSION = "enterprise-agentic-policy-v1"
_PURPOSE = "enterprise-agentic-evaluation"
_SCOPE = "tenant:primary"


def generate_enterprise_agentic_world(
    config: EnterpriseAgenticGenerationConfigV1 | None = None,
) -> EnterpriseAgenticGeneratedBenchmarkV1:
    """Generate one deterministic, #26-validated enterprise-agentic smoke world."""

    selected = config or EnterpriseAgenticGenerationConfigV1()
    config_sha256 = hashlib.sha256(canonical_json_bytes(selected)).hexdigest()

    def identifier(kind: str, *parts: str) -> str:
        return str(
            uuid5(
                _GENERATED_ENTERPRISE_AGENTIC_NAMESPACE_V1,
                encode_parts(
                    (
                        selected.profile_version,
                        selected.generator_version,
                        str(selected.seed),
                        config_sha256,
                        kind,
                        *parts,
                    )
                ),
            )
        )

    world_id = identifier("world", selected.tier.value)
    snapshot, runtime_rows, credential_rows, delegation_rows = _build_topology(
        selected, identifier, world_id
    )
    events, bindings, cases, scenario = _build_events(
        selected,
        identifier,
        snapshot,
        runtime_rows,
        credential_rows,
        delegation_rows,
    )
    benchmark = build_agentic_benchmark(snapshot, events, scenario, bindings, cases)
    identity = EnterpriseAgenticBenchmarkIdentityV1(
        seed=selected.seed,
        tier=selected.tier,
        configuration_sha256=config_sha256,
        world_id=world_id,
    )
    return EnterpriseAgenticGeneratedBenchmarkV1(
        config=selected,
        identity=identity,
        public=benchmark.public,
        evaluator=benchmark.evaluator,
        metrics=derive_enterprise_agentic_integrity_metrics(benchmark),
    )


def derive_enterprise_agentic_integrity_metrics(
    benchmark: AgenticBenchmark,
) -> EnterpriseAgenticIntegrityMetricsV1:
    """Derive all scale observations from a constructed benchmark."""

    snapshot = benchmark.public.snapshot
    state = materialize_agentic_world(snapshot, benchmark.public.events)
    principals = snapshot.principals
    actions = benchmark.evaluator.authority_truth
    cases = benchmark.evaluator.cases
    principal_count = len(principals)
    action_count = len(actions)

    counts = {
        "action_event_count": (action_count, action_count, "generated action events"),
        "allowed_action_count": (
            sum(item.decision_at_action is Decision.ALLOW for item in actions),
            action_count,
            "generated action events",
        ),
        "credential_count": (
            len(state.credentials),
            len(state.credentials),
            "generated credentials",
        ),
        "denied_action_count": (
            sum(item.decision_at_action is Decision.DENY for item in actions),
            action_count,
            "generated action events",
        ),
        "department_count": (
            len(snapshot.departments),
            len(snapshot.departments),
            "generated departments",
        ),
        "delegation_count": (
            len(state.delegations),
            len(state.delegations),
            "generated delegations",
        ),
        "evidence_loss_event_count": (
            sum(
                isinstance(item.payload, EvidenceDiscarded)
                for item in benchmark.public.events
            ),
            len(benchmark.public.events),
            "generated events",
        ),
        "human_principal_count": (
            sum(item.kind is PrincipalKind.HUMAN for item in principals),
            principal_count,
            "generated principals",
        ),
        "logical_agent_count": (
            len(snapshot.agents),
            len(snapshot.agents),
            "generated logical agents",
        ),
        "organisation_count": (
            len(snapshot.organisations),
            len(snapshot.organisations),
            "generated organisations",
        ),
        "principal_count": (principal_count, principal_count, "generated principals"),
        "resource_count": (
            len(snapshot.resources),
            len(snapshot.resources),
            "generated resources",
        ),
        "revoked_delegation_count": (
            len(state.revoked_delegation_ids),
            len(state.delegations),
            "generated delegations",
        ),
        "runtime_count": (
            len(state.runtimes),
            len(state.runtimes),
            "generated runtimes",
        ),
        "service_account_principal_count": (
            sum(item.kind is PrincipalKind.SERVICE_ACCOUNT for item in principals),
            principal_count,
            "generated principals",
        ),
        "workload_principal_count": (
            sum(item.kind is PrincipalKind.WORKLOAD for item in principals),
            principal_count,
            "generated principals",
        ),
    }
    owner_depths = Counter(
        len(derive_agent_owner_chain(snapshot, item.id)) for item in snapshot.agents
    )
    runtime_counts = Counter(
        sum(runtime.logical_agent_id == item.id for runtime in state.runtimes)
        for item in snapshot.agents
    )
    credential_binding_counts = Counter(
        len(item.allowed_runtime_principal_ids) for item in state.credentials
    )
    delegation_depths = Counter(
        _delegation_depth(item, state.delegations) for item in state.delegations
    )
    case_kinds = Counter(item.kind.value for item in cases)
    return EnterpriseAgenticIntegrityMetricsV1(
        counts=tuple(
            EnterpriseAgenticCountMetricV1(
                name=name,
                count=value[0],
                denominator=value[1],
                denominator_meaning=value[2],
            )
            for name, value in sorted(counts.items())
        ),
        owner_chain_depth_distribution=_distribution(
            owner_depths, len(snapshot.agents), "generated logical agents"
        ),
        runtimes_per_agent_distribution=_distribution(
            runtime_counts, len(snapshot.agents), "generated logical agents"
        ),
        credential_runtime_binding_distribution=_distribution(
            credential_binding_counts,
            len(state.credentials),
            "generated credentials",
        ),
        delegation_depth_distribution=_distribution(
            delegation_depths, len(state.delegations), "generated delegations"
        ),
        case_kind_distribution=_distribution(
            case_kinds, len(cases), "generated action cases"
        ),
        principal_graph_component_count=_principal_component_count(principals),
    )


def _build_topology(
    config: EnterpriseAgenticGenerationConfigV1,
    identifier: Callable[..., str],
    world_id: str,
) -> tuple[
    AgenticWorldSnapshot,
    tuple[Runtime, ...],
    tuple[Credential, ...],
    tuple[Delegation, ...],
]:
    make_id = identifier
    topology = config.topology
    organisation_id = make_id("organisation", "primary")
    organisation_principal_id = make_id("principal", "organisation", "primary")
    organisation = Organisation(
        id=organisation_id,
        display_name="Northstar Example Systems Ltd",
        tenant_id=make_id("tenant", "primary"),
    )
    departments = tuple(
        Department(
            id=make_id("department", str(index)),
            organisation_id=organisation_id,
            display_name=f"Example Department {index + 1:02d}",
        )
        for index in range(topology.department_count)
    )
    organisation_principal = Principal(
        id=organisation_principal_id,
        kind=PrincipalKind.ORGANISATION,
        display_name="Northstar Example Systems Ltd",
        organisation_id=organisation_id,
    )
    humans = tuple(
        Principal(
            id=make_id("principal", "human", str(index)),
            kind=PrincipalKind.HUMAN,
            display_name=f"Synthetic Accountable Person {index + 1:03d}",
            organisation_id=organisation_id,
            department_id=departments[index % len(departments)].id,
            owner_principal_id=organisation_principal_id,
        )
        for index in range(topology.human_principal_count)
    )
    services = tuple(
        Principal(
            id=make_id("principal", "service", str(index)),
            kind=PrincipalKind.SERVICE_ACCOUNT,
            display_name=f"Synthetic Agent Service {index + 1:02d}",
            organisation_id=organisation_id,
            department_id=departments[index % len(departments)].id,
            owner_principal_id=humans[index % len(humans)].id,
        )
        for index in range(topology.logical_agent_count)
    )
    workloads = tuple(
        Principal(
            id=make_id("principal", "workload", str(index)),
            kind=PrincipalKind.WORKLOAD,
            display_name=f"Synthetic Runtime Principal {index + 1:02d}",
            organisation_id=organisation_id,
            department_id=departments[index % len(departments)].id,
            owner_principal_id=services[index % len(services)].id,
        )
        for index in range(topology.runtime_count)
    )
    agent_ids = tuple(
        make_id("agent", str(index)) for index in range(topology.logical_agent_count)
    )
    agents = tuple(
        LogicalAgent(
            id=agent_ids[index],
            display_name=f"Synthetic Enterprise Agent {index + 1:02d}",
            organisation_id=organisation_id,
            owner_principal_id=humans[index % len(humans)].id,
            parent_agent_id=agent_ids[0] if index == 1 else None,
        )
        for index in range(topology.logical_agent_count)
    )
    resources = tuple(
        Resource(
            id=make_id("resource", str(index)),
            display_name=f"Synthetic Protected Resource {index + 1:02d}",
            organisation_id=organisation_id,
            owner_principal_id=humans[index % len(humans)].id,
            actions=("read", "write"),
        )
        for index in range(topology.resource_count)
    )
    runtimes = tuple(
        Runtime(
            id=make_id("runtime", str(index)),
            logical_agent_id=agents[index % len(agents)].id,
            runtime_principal_id=workloads[index].id,
            owner_principal_id=agents[index % len(agents)].owner_principal_id,
            organisation_id=organisation_id,
        )
        for index in range(topology.runtime_count)
    )
    start = _start_time(config.seed)
    ordinary_credentials = tuple(
        Credential(
            id=make_id("credential", "ordinary", str(index)),
            issuer_principal_id=organisation_principal_id,
            subject_principal_id=services[index % len(services)].id,
            allowed_runtime_principal_ids=(workloads[index].id,),
            valid_from=start,
            expires_at=start + timedelta(hours=12),
        )
        for index in range(topology.runtime_count)
    )
    wrong_runtime_credential = Credential(
        id=make_id("credential", "wrong-runtime-control"),
        issuer_principal_id=organisation_principal_id,
        subject_principal_id=services[0].id,
        allowed_runtime_principal_ids=(workloads[1].id,),
        valid_from=start,
        expires_at=start + timedelta(hours=12),
    )
    expired_credential = Credential(
        id=make_id("credential", "expired-control"),
        issuer_principal_id=organisation_principal_id,
        subject_principal_id=services[0].id,
        allowed_runtime_principal_ids=(workloads[0].id,),
        valid_from=start,
        expires_at=start + timedelta(minutes=(2 * topology.runtime_count) + 3),
    )
    credentials = (
        *ordinary_credentials,
        wrong_runtime_credential,
        expired_credential,
    )
    delegation_ids = tuple(
        make_id("delegation", str(index)) for index in range(len(agents))
    )
    delegations = tuple(
        Delegation(
            id=delegation_ids[index],
            originating_principal_id=(
                agents[0].owner_principal_id
                if index == 1
                else agents[index].owner_principal_id
            ),
            delegator_principal_id=(
                agents[0].owner_principal_id
                if index == 1
                else agents[index].owner_principal_id
            ),
            grantee_agent_id=agents[index].id,
            parent_delegation_id=delegation_ids[0] if index == 1 else None,
            capability=Capability(
                resource_ids=(
                    (resources[0].id, resources[1].id)
                    if index == 0
                    else (resources[index % len(resources)].id,)
                ),
                actions=("read",),
                scopes=(_SCOPE,),
                purpose=_PURPOSE,
                may_delegate=index == 0,
            ),
            policy_version=_POLICY_VERSION,
            valid_from=start,
            expires_at=start + timedelta(hours=12),
        )
        for index in range(len(agents))
    )
    snapshot = AgenticWorldSnapshot(
        world_id=world_id,
        world_version=config.profile_version,
        seed=config.seed,
        organisations=(organisation,),
        departments=tuple(sorted(departments, key=lambda item: item.id)),
        principals=tuple(
            sorted(
                (organisation_principal, *humans, *services, *workloads),
                key=lambda item: item.id,
            )
        ),
        agents=tuple(sorted(agents, key=lambda item: item.id)),
        resources=tuple(sorted(resources, key=lambda item: item.id)),
        policies=(PolicyVersion(id=make_id("policy", "v1"), version=_POLICY_VERSION),),
        initial_evidence_refs=(f"evidence:policy:{_POLICY_VERSION}",),
    )
    return snapshot, runtimes, credentials, delegations


def _build_events(
    config: EnterpriseAgenticGenerationConfigV1,
    identifier: Callable[..., str],
    snapshot: AgenticWorldSnapshot,
    runtimes: tuple[Runtime, ...],
    credentials: tuple[Credential, ...],
    delegations: tuple[Delegation, ...],
) -> tuple[
    tuple[AgenticEvent, ...],
    tuple[CanonicalBinding, ...],
    tuple[AgenticCase, ...],
    PublicScenario,
]:
    make_id = identifier
    start = _start_time(config.seed)
    events: list[AgenticEvent] = []
    bindings: list[CanonicalBinding] = []
    cases: list[AgenticCase] = []

    def add_event(
        label: str,
        payload: AgenticEventPayload,
        evidence_refs: tuple[str, ...] = (),
    ) -> AgenticEvent:
        event_index = len(events) + 1
        event = AgenticEvent(
            id=make_id("event", label),
            event_index=event_index,
            occurred_at=start + timedelta(minutes=event_index),
            evidence_refs=evidence_refs,
            payload=payload,
        )
        events.append(event)
        return event

    for runtime in runtimes:
        add_event(
            f"runtime-{runtime.id}",
            RuntimeSpawned(runtime=runtime),
            (f"evidence:runtime:{runtime.id}",),
        )
    for credential in credentials:
        add_event(
            f"credential-{credential.id}",
            CredentialIssued(credential=credential),
            (f"evidence:credential:{credential.id}",),
        )
    for delegation in delegations:
        add_event(
            f"delegation-{delegation.id}",
            DelegationGranted(delegation=delegation),
            (f"evidence:delegation:{delegation.id}",),
        )

    agents = {item.id: item for item in snapshot.agents}
    principals = {item.id: item for item in snapshot.principals}
    resources = {item.id: item for item in snapshot.resources}
    runtime_by_agent = {
        agent_id: next(item for item in runtimes if item.logical_agent_id == agent_id)
        for agent_id in agents
    }
    credential_by_runtime = {
        item.allowed_runtime_principal_ids[0]: item
        for item in credentials[: len(runtimes)]
    }

    def add_action(
        label: str,
        case_kind: AgenticCaseKind,
        *,
        delegation: Delegation,
        runtime: Runtime,
        credential: Credential,
        action: str = "read",
        attributed_actor_claim: str | None = None,
    ) -> None:
        agent = agents[delegation.grantee_agent_id]
        resource = resources[delegation.capability.resource_ids[0]]
        service_principal_id = cast(
            str, principals[runtime.runtime_principal_id].owner_principal_id
        )
        cited_evidence = tuple(
            sorted(
                (
                    f"evidence:policy:{_POLICY_VERSION}",
                    f"evidence:runtime:{runtime.id}",
                    f"evidence:credential:{credential.id}",
                    f"evidence:delegation:{delegation.id}",
                )
            )
        )
        event = add_event(
            label,
            ActionAttempted(
                attempt=ActionAttempt(
                    originating_principal_claim=delegation.originating_principal_id,
                    logical_agent_claim=agent.id,
                    runtime_principal_claim=runtime.runtime_principal_id,
                    presented_credential_id=credential.id,
                    attributed_actor_claim=(
                        attributed_actor_claim or service_principal_id
                    ),
                    resource_id=resource.id,
                    action=action,
                    requested_scope=(_SCOPE,),
                    purpose=_PURPOSE,
                    policy_version=_POLICY_VERSION,
                    evidence_refs=cited_evidence,
                )
            ),
        )
        bindings.append(
            CanonicalBinding(
                action_event_id=event.id,
                originating_principal_id=delegation.originating_principal_id,
                logical_agent_id=agent.id,
                runtime_id=runtime.id,
                runtime_principal_id=runtime.runtime_principal_id,
                credential_subject_id=credential.subject_principal_id,
                attributed_actor_id=service_principal_id,
                accountable_owner_chain=derive_agent_owner_chain(snapshot, agent.id),
            )
        )
        cases.append(AgenticCase(action_event_id=event.id, kind=case_kind))

    agent_ids = tuple(item.grantee_agent_id for item in delegations[:3])
    first, second, third = (agents[item] for item in agent_ids[:3])
    first_runtime = runtime_by_agent[first.id]
    second_runtime = runtime_by_agent[second.id]
    third_runtime = runtime_by_agent[third.id]
    first_delegation = next(
        item for item in delegations if item.grantee_agent_id == first.id
    )
    second_delegation = next(
        item for item in delegations if item.grantee_agent_id == second.id
    )
    third_delegation = next(
        item for item in delegations if item.grantee_agent_id == third.id
    )
    first_credential = credential_by_runtime[first_runtime.runtime_principal_id]
    second_credential = credential_by_runtime[second_runtime.runtime_principal_id]
    third_credential = credential_by_runtime[third_runtime.runtime_principal_id]
    wrong_runtime_credential = credentials[-2]
    expired_credential = credentials[-1]

    add_action(
        "action-authorised",
        AgenticCaseKind.AUTHORISED_ACTION,
        delegation=first_delegation,
        runtime=first_runtime,
        credential=first_credential,
    )
    add_action(
        "action-outside-capability",
        AgenticCaseKind.OUTSIDE_CAPABILITY,
        delegation=first_delegation,
        runtime=first_runtime,
        credential=first_credential,
        action="write",
    )
    add_action(
        "action-wrong-runtime",
        AgenticCaseKind.WRONG_RUNTIME,
        delegation=first_delegation,
        runtime=first_runtime,
        credential=wrong_runtime_credential,
    )
    add_action(
        "action-expired-credential",
        AgenticCaseKind.CREDENTIAL_INVALID,
        delegation=first_delegation,
        runtime=first_runtime,
        credential=expired_credential,
    )
    add_action(
        "action-valid-then-revoked",
        AgenticCaseKind.VALID_THEN_REVOKED,
        delegation=second_delegation,
        runtime=second_runtime,
        credential=second_credential,
    )
    unrelated_human = next(
        item
        for item in snapshot.principals
        if item.kind is PrincipalKind.HUMAN and item.id != third.owner_principal_id
    )
    add_action(
        "action-incorrect-attribution",
        AgenticCaseKind.INCORRECT_ATTRIBUTION,
        delegation=third_delegation,
        runtime=third_runtime,
        credential=third_credential,
        attributed_actor_claim=unrelated_human.id,
    )
    add_event(
        "revoke-second-delegation",
        DelegationRevoked(delegation_id=second_delegation.id),
        (f"evidence:revocation:{second_delegation.id}",),
    )
    add_action(
        "action-post-revocation",
        AgenticCaseKind.POST_REVOCATION_ACTION,
        delegation=second_delegation,
        runtime=second_runtime,
        credential=second_credential,
    )
    add_event(
        "discard-revoked-delegation-evidence",
        EvidenceDiscarded(
            evidence_refs=(f"evidence:delegation:{second_delegation.id}",)
        ),
    )
    audit_id = make_id("audit", "smoke")
    audit_event = add_event(
        "audit-smoke",
        AuditPerformed(audit_id=audit_id),
        (f"evidence:audit:{audit_id}",),
    )
    scenario = PublicScenario(
        id=make_id("scenario", "smoke"),
        title="Generated enterprise agent authority smoke benchmark",
        description=(
            "A deterministic fictional enterprise workload covering authorised and "
            "adversarial agent identity, runtime, credential, delegation, revocation, "
            "attribution, and audit behavior."
        ),
        action_event_ids=tuple(item.action_event_id for item in cases),
        audit_event_id=audit_event.id,
        tool_schema_paths=("tool_schemas/enterprise-agentic-actions-v1.json",),
    )
    return tuple(events), tuple(bindings), tuple(cases), scenario


def _start_time(seed: int) -> datetime:
    return datetime(2030, 1, 1, 9, 0, tzinfo=UTC) + timedelta(days=seed % 365)


def _distribution(
    values: Counter[int] | Counter[str],
    denominator: int,
    denominator_meaning: str,
) -> tuple[EnterpriseAgenticDistributionBinV1, ...]:
    return tuple(
        EnterpriseAgenticDistributionBinV1(
            value=str(value),
            count=count,
            denominator=denominator,
            denominator_meaning=denominator_meaning,
        )
        for value, count in sorted(values.items(), key=lambda item: str(item[0]))
    )


def _delegation_depth(
    delegation: Delegation,
    delegations: tuple[Delegation, ...],
) -> int:
    by_id = {item.id: item for item in delegations}
    depth = 1
    current = delegation
    while current.parent_delegation_id is not None:
        depth += 1
        current = by_id[current.parent_delegation_id]
    return depth


def _principal_component_count(principals: tuple[Principal, ...]) -> int:
    neighbours: dict[str, set[str]] = {item.id: set() for item in principals}
    for principal in principals:
        owner_id = principal.owner_principal_id
        if owner_id is not None:
            neighbours[principal.id].add(owner_id)
            neighbours[owner_id].add(principal.id)
    unseen = set(neighbours)
    components = 0
    while unseen:
        components += 1
        pending = [min(unseen)]
        while pending:
            current = pending.pop()
            unseen.remove(current)
            pending.extend(sorted(neighbours[current] & unseen))
    return components


__all__ = [
    "derive_enterprise_agentic_integrity_metrics",
    "generate_enterprise_agentic_world",
]
