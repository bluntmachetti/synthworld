"""Deterministic standard and longitudinal enterprise-agentic generation."""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Literal, cast
from uuid import UUID, uuid5

from synthworld.agentic.enterprise.generated_models import (
    EnterpriseAgenticCountMetricV1,
    EnterpriseAgenticDistributionBinV1,
)
from synthworld.agentic.enterprise.generated_scale_models import (
    ENTERPRISE_AGENTIC_LONGITUDINAL_EVENT_SCHEDULE_VERSION,
    EnterpriseAgenticAgentLifecycleStateV2,
    EnterpriseAgenticAgentStatusChangedV2,
    EnterpriseAgenticCredentialLifecycleStateV2,
    EnterpriseAgenticCredentialProfileV2,
    EnterpriseAgenticCredentialRotatedV2,
    EnterpriseAgenticCredentialStatusChangedV2,
    EnterpriseAgenticDelegationPropagationV2,
    EnterpriseAgenticGeneratedBenchmarkV2,
    EnterpriseAgenticGenerationConfigV2,
    EnterpriseAgenticIntegrityMetricsV2,
    EnterpriseAgenticLifecycleCaseKindV2,
    EnterpriseAgenticLifecycleCaseV2,
    EnterpriseAgenticLifecycleEventV2,
    EnterpriseAgenticLifecyclePayloadV2,
    EnterpriseAgenticLongitudinalScheduleV2,
    EnterpriseAgenticPersonLifecycleStateV2,
    EnterpriseAgenticPersonProfileV2,
    EnterpriseAgenticPersonStatusChangedV2,
    EnterpriseAgenticPolicyActivatedV2,
    EnterpriseAgenticPopulationKindV2,
    EnterpriseAgenticResourceProfileV2,
    EnterpriseAgenticScaleIdentityV2,
    EnterpriseAgenticScaleTierV2,
    EnterpriseAgenticScenarioPrevalenceV2,
    EnterpriseAgenticTeamV2,
    EnterpriseAgenticTopologyMetadataV2,
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

_ENTERPRISE_AGENTIC_SCALE_NAMESPACE_V2 = UUID("86da57ab-0488-5b59-a807-309599866fd5")
_POLICY_V1 = "enterprise-agentic-policy-v1"
_POLICY_V2 = "enterprise-agentic-policy-v2"
_PURPOSE = "enterprise-agentic-evaluation"
_ACTIONS = ("read", "write")


@dataclass(frozen=True, slots=True)
class _ScaleRows:
    snapshot: AgenticWorldSnapshot
    topology: EnterpriseAgenticTopologyMetadataV2
    runtimes: tuple[Runtime, ...]
    ordinary_credentials: tuple[Credential, ...]
    control_credentials: tuple[Credential, ...]
    rotation_credentials: tuple[Credential, ...]
    delegations: tuple[Delegation, ...]
    replacement_policy_delegation: Delegation
    late_delegation_id: str


def default_enterprise_agentic_generation_config_v2(
    tier: EnterpriseAgenticScaleTierV2,
    *,
    seed: int = 20_260_821,
) -> EnterpriseAgenticGenerationConfigV2:
    """Return the documented, fully resolved defaults for one V2 tier."""

    if tier is EnterpriseAgenticScaleTierV2.STANDARD:
        return EnterpriseAgenticGenerationConfigV2(seed=seed, tier=tier)
    return EnterpriseAgenticGenerationConfigV2(
        seed=seed,
        tier=tier,
        event_schedule_version=(ENTERPRISE_AGENTIC_LONGITUDINAL_EVENT_SCHEDULE_VERSION),
        prevalence=EnterpriseAgenticScenarioPrevalenceV2(
            rotated_credential_reuse=2,
            suspended_credential=2,
            agent_offboarding_active_credential=2,
            revocation_propagation_failure=2,
        ),
        longitudinal=EnterpriseAgenticLongitudinalScheduleV2(),
    )


def generate_enterprise_agentic_scale_world(
    config: EnterpriseAgenticGenerationConfigV2,
) -> EnterpriseAgenticGeneratedBenchmarkV2:
    """Generate a deterministic standard or longitudinal benchmark world."""

    config_sha256 = hashlib.sha256(canonical_json_bytes(config)).hexdigest()

    def identifier(kind: str, *parts: str) -> str:
        return str(
            uuid5(
                _ENTERPRISE_AGENTIC_SCALE_NAMESPACE_V2,
                encode_parts(
                    (
                        config.profile_version,
                        config.generator_version,
                        str(config.seed),
                        config_sha256,
                        kind,
                        *parts,
                    )
                ),
            )
        )

    world_id = identifier("world", config.tier.value)
    rows = _build_scale_topology(config, identifier, world_id)
    events, bindings, cases, lifecycle_cases, lifecycle_events, scenario = (
        _build_scale_events(config, identifier, rows)
    )
    benchmark = build_agentic_benchmark(
        rows.snapshot,
        events,
        scenario,
        bindings,
        cases,
    )
    identity = EnterpriseAgenticScaleIdentityV2(
        event_schedule_version=config.event_schedule_version,
        tier=config.tier,
        seed=config.seed,
        configuration_sha256=config_sha256,
        world_id=world_id,
    )
    metrics = derive_enterprise_agentic_scale_integrity_metrics(
        benchmark,
        rows.topology,
        lifecycle_events,
        lifecycle_cases,
    )
    return EnterpriseAgenticGeneratedBenchmarkV2(
        config=config,
        identity=identity,
        public=benchmark.public,
        topology=rows.topology,
        lifecycle_events=lifecycle_events,
        evaluator=benchmark.evaluator,
        lifecycle_cases=lifecycle_cases,
        metrics=metrics,
    )


def _build_scale_topology(
    config: EnterpriseAgenticGenerationConfigV2,
    identifier: Callable[..., str],
    world_id: str,
) -> _ScaleRows:
    make_id = identifier
    selected = config.topology
    start = _start_time(config.seed)
    audit_time = start + timedelta(
        days=(
            config.longitudinal.virtual_duration_days
            if config.longitudinal is not None
            else 30
        )
    )
    organisations = tuple(
        Organisation(
            id=make_id("organisation", str(index)),
            display_name=f"Synthetic Enterprise {index + 1:02d}",
            tenant_id=make_id("tenant", str(index)),
        )
        for index in range(selected.organisation_count)
    )
    organisation_principals = tuple(
        Principal(
            id=make_id("principal", "organisation", str(index)),
            kind=PrincipalKind.ORGANISATION,
            display_name=f"Synthetic Enterprise Principal {index + 1:02d}",
            organisation_id=organisation.id,
        )
        for index, organisation in enumerate(organisations)
    )
    departments = tuple(
        Department(
            id=make_id("department", str(org_index), str(department_index)),
            organisation_id=organisation.id,
            display_name=(
                f"Synthetic Department {org_index + 1:02d}-{department_index + 1:02d}"
            ),
        )
        for org_index, organisation in enumerate(organisations)
        for department_index in range(selected.departments_per_organisation)
    )
    departments_by_org = {
        organisation.id: tuple(
            item for item in departments if item.organisation_id == organisation.id
        )
        for organisation in organisations
    }
    teams = tuple(
        EnterpriseAgenticTeamV2(
            id=make_id("team", department.id, str(team_index)),
            department_id=department.id,
            display_name=f"Synthetic Team {team_index + 1:02d}",
        )
        for department in departments
        for team_index in range(selected.teams_per_department)
    )
    teams_by_department = {
        department.id: tuple(
            item for item in teams if item.department_id == department.id
        )
        for department in departments
    }
    population = (
        *((EnterpriseAgenticPopulationKindV2.EMPLOYEE,) * selected.employee_count),
        *((EnterpriseAgenticPopulationKindV2.CONTRACTOR,) * selected.contractor_count),
        *((EnterpriseAgenticPopulationKindV2.SUPPLIER,) * selected.supplier_count),
        *(
            (EnterpriseAgenticPopulationKindV2.EXTERNAL_PARTNER,)
            * selected.external_partner_count
        ),
    )
    humans: list[Principal] = []
    person_profiles: list[EnterpriseAgenticPersonProfileV2] = []
    for index, population_kind in enumerate(population):
        organisation_index = index % len(organisations)
        organisation = organisations[organisation_index]
        organisation_departments = departments_by_org[organisation.id]
        department = organisation_departments[
            (index // len(organisations)) % len(organisation_departments)
        ]
        department_teams = teams_by_department[department.id]
        team_index = index % len(department_teams)
        memberships = [department_teams[team_index].id]
        if index % 10 == 0 and len(department_teams) > 1:
            memberships.append(
                department_teams[(team_index + 1) % len(department_teams)].id
            )
        principal = Principal(
            id=make_id("principal", "human", str(index)),
            kind=PrincipalKind.HUMAN,
            display_name=f"Synthetic {population_kind.value.title()} {index + 1:04d}",
            organisation_id=organisation.id,
            department_id=department.id,
            owner_principal_id=organisation_principals[organisation_index].id,
        )
        humans.append(principal)
        person_profiles.append(
            EnterpriseAgenticPersonProfileV2(
                principal_id=principal.id,
                population_kind=population_kind,
                team_ids=tuple(sorted(memberships)),
            )
        )
    humans_by_org = {
        organisation.id: tuple(
            item for item in humans if item.organisation_id == organisation.id
        )
        for organisation in organisations
    }
    agent_ids = tuple(
        make_id("agent", str(index)) for index in range(selected.logical_agent_count)
    )
    child_count = max(
        len(organisations),
        round(
            selected.logical_agent_count * config.authority.agent_subdelegation_ratio
        ),
    )
    parent_indices: list[int | None] = []
    for index in range(selected.logical_agent_count):
        layer = index // len(organisations)
        is_child = index >= len(organisations) and index < (
            len(organisations) + child_count
        )
        if is_child and layer < config.authority.maximum_delegation_depth:
            parent_indices.append(index - len(organisations))
        elif is_child:
            parent_indices.append(index % len(organisations))
        else:
            parent_indices.append(None)
    agents: list[LogicalAgent] = []
    services: list[Principal] = []
    for index, agent_id in enumerate(agent_ids):
        organisation = organisations[index % len(organisations)]
        organisation_humans = humans_by_org[organisation.id]
        owner = organisation_humans[
            (index // len(organisations)) % len(organisation_humans)
        ]
        parent_index = parent_indices[index]
        agents.append(
            LogicalAgent(
                id=agent_id,
                display_name=f"Synthetic Enterprise Agent {index + 1:03d}",
                organisation_id=organisation.id,
                owner_principal_id=owner.id,
                parent_agent_id=(
                    agent_ids[parent_index] if parent_index is not None else None
                ),
            )
        )
        services.append(
            Principal(
                id=make_id("principal", "service", str(index)),
                kind=PrincipalKind.SERVICE_ACCOUNT,
                display_name=f"Synthetic Agent Service {index + 1:03d}",
                organisation_id=organisation.id,
                department_id=owner.department_id,
                owner_principal_id=owner.id,
            )
        )
    workloads: list[Principal] = []
    runtimes: list[Runtime] = []
    for index in range(selected.runtime_count):
        agent_index = index % len(agents)
        agent = agents[agent_index]
        service = services[agent_index]
        workload = Principal(
            id=make_id("principal", "workload", str(index)),
            kind=PrincipalKind.WORKLOAD,
            display_name=f"Synthetic Runtime Principal {index + 1:04d}",
            organisation_id=agent.organisation_id,
            department_id=service.department_id,
            owner_principal_id=service.id,
        )
        workloads.append(workload)
        runtimes.append(
            Runtime(
                id=make_id("runtime", str(index)),
                logical_agent_id=agent.id,
                runtime_principal_id=workload.id,
                owner_principal_id=agent.owner_principal_id,
                organisation_id=agent.organisation_id,
            )
        )
    resources: list[Resource] = []
    resource_profiles: list[EnterpriseAgenticResourceProfileV2] = []
    categories = ("application", "tool", "environment", "protected_data")
    criticalities = ("ordinary", "sensitive", "critical")
    for index in range(selected.resource_count):
        organisation = organisations[index % len(organisations)]
        owner = humans_by_org[organisation.id][
            (index // len(organisations)) % len(humans_by_org[organisation.id])
        ]
        resource = Resource(
            id=make_id("resource", str(index)),
            display_name=f"Synthetic Protected Resource {index + 1:04d}",
            organisation_id=organisation.id,
            owner_principal_id=owner.id,
            actions=_ACTIONS,
        )
        resources.append(resource)
        resource_profiles.append(
            EnterpriseAgenticResourceProfileV2(
                resource_id=resource.id,
                category=cast(
                    Literal["application", "tool", "environment", "protected_data"],
                    categories[index % len(categories)],
                ),
                criticality=cast(
                    Literal["ordinary", "sensitive", "critical"],
                    criticalities[index % len(criticalities)],
                ),
            )
        )
    resources_by_org = {
        organisation.id: tuple(
            item for item in resources if item.organisation_id == organisation.id
        )
        for organisation in organisations
    }
    delegation_ids = tuple(
        make_id("delegation", str(index)) for index in range(len(agents))
    )
    children_by_parent = Counter(
        parent for parent in parent_indices if parent is not None
    )
    delegations: list[Delegation] = []
    direct_cutoff = round(len(agents) * config.authority.direct_human_delegation_ratio)
    organisation_cutoff = direct_cutoff + round(
        len(agents) * config.authority.organisation_delegation_ratio
    )
    for index, agent in enumerate(agents):
        parent_index = parent_indices[index]
        organisation_index = index % len(organisations)
        organisation_principal = organisation_principals[organisation_index]
        if parent_index is not None:
            parent = delegations[parent_index]
            origin_id = parent.originating_principal_id
            delegator_id = agents[parent_index].owner_principal_id
            parent_id = parent.id
            resource_ids = parent.capability.resource_ids[:1]
        elif index < direct_cutoff or index >= organisation_cutoff:
            origin_id = agent.owner_principal_id
            delegator_id = agent.owner_principal_id
            parent_id = None
            owned = tuple(
                item.id
                for item in resources_by_org[agent.organisation_id]
                if item.owner_principal_id == agent.owner_principal_id
            )
            resource_ids = (
                owned
                or tuple(item.id for item in resources_by_org[agent.organisation_id])
            )[:1]
        else:
            origin_id = organisation_principal.id
            delegator_id = organisation_principal.id
            parent_id = None
            resource_ids = tuple(
                item.id for item in resources_by_org[agent.organisation_id]
            )[: config.authority.capability_resource_breadth]
        scopes = tuple(
            f"tenant:{organisation_index}:scope:{scope_index}"
            for scope_index in range(config.authority.capability_scope_density)
        )
        delegations.append(
            Delegation(
                id=delegation_ids[index],
                originating_principal_id=origin_id,
                delegator_principal_id=delegator_id,
                grantee_agent_id=agent.id,
                parent_delegation_id=parent_id,
                capability=Capability(
                    resource_ids=resource_ids,
                    actions=("read",),
                    scopes=scopes,
                    purpose=_PURPOSE,
                    may_delegate=bool(children_by_parent[index]),
                ),
                policy_version=_POLICY_V1,
                valid_from=start,
                expires_at=audit_time + timedelta(days=30),
            )
        )
    policy_agent_index = min(5, len(agents) - 1)
    old_policy_delegation = delegations[policy_agent_index]
    replacement_policy_delegation = old_policy_delegation.model_copy(
        update={
            "id": make_id("delegation", "policy-replacement"),
            "parent_delegation_id": None,
            "originating_principal_id": agents[policy_agent_index].owner_principal_id,
            "delegator_principal_id": agents[policy_agent_index].owner_principal_id,
            "capability": old_policy_delegation.capability.model_copy(
                update={"may_delegate": False}
            ),
            "policy_version": _POLICY_V2,
            "valid_from": (
                start
                + timedelta(
                    days=(
                        config.longitudinal.policy_change_day
                        if config.longitudinal is not None
                        else 5
                    )
                )
            ),
        }
    )
    validity_end = audit_time + timedelta(days=config.credentials.validity_days)
    shared_count = max(
        int(config.prevalence.shared_credential_reuse > 0),
        round(len(runtimes) * config.credentials.shared_identity_prevalence),
    )
    ordinary_credentials = tuple(
        Credential(
            id=make_id("credential", "ordinary", str(index)),
            issuer_principal_id=organisation_principals[index % len(organisations)].id,
            subject_principal_id=services[index % len(services)].id,
            allowed_runtime_principal_ids=tuple(
                sorted(
                    tuple(
                        runtimes[
                            (index + (offset * len(agents))) % len(runtimes)
                        ].runtime_principal_id
                        for offset in range(
                            config.credentials.allowed_runtimes_per_shared_credential
                        )
                    )
                    if index < shared_count
                    else (runtimes[index].runtime_principal_id,)
                )
            ),
            valid_from=start,
            expires_at=validity_end,
        )
        for index in range(len(runtimes))
    )
    wrong_runtime_credential = Credential(
        id=make_id("credential", "wrong-runtime-control"),
        issuer_principal_id=organisation_principals[0].id,
        subject_principal_id=services[0].id,
        allowed_runtime_principal_ids=(
            runtimes[len(organisations)].runtime_principal_id,
        ),
        valid_from=start,
        expires_at=validity_end,
    )
    expired_credential = Credential(
        id=make_id("credential", "expired-control"),
        issuer_principal_id=organisation_principals[0].id,
        subject_principal_id=services[0].id,
        allowed_runtime_principal_ids=(runtimes[0].runtime_principal_id,),
        valid_from=start,
        expires_at=start + timedelta(days=2),
    )
    suspended_credential = Credential(
        id=make_id("credential", "suspended-control"),
        issuer_principal_id=organisation_principals[0].id,
        subject_principal_id=services[min(7, len(services) - 1)].id,
        allowed_runtime_principal_ids=(
            runtimes[min(7, len(runtimes) - 1)].runtime_principal_id,
        ),
        valid_from=start,
        expires_at=(
            start
            + timedelta(
                days=(
                    config.longitudinal.credential_rotation_interval_days + 10
                    if config.longitudinal is not None
                    else 10
                )
            )
        ),
    )
    control_credentials = (
        wrong_runtime_credential,
        expired_credential,
        *((suspended_credential,) if config.longitudinal is not None else ()),
    )
    rotation_credentials: tuple[Credential, ...] = ()
    if config.longitudinal is not None:
        rotation_count = (
            config.longitudinal.virtual_duration_days - 1
        ) // config.longitudinal.credential_rotation_interval_days
        rotation_credentials = tuple(
            Credential(
                id=make_id("credential", "rotation", str(index)),
                issuer_principal_id=organisation_principals[0].id,
                subject_principal_id=services[min(6, len(services) - 1)].id,
                allowed_runtime_principal_ids=(
                    runtimes[min(6, len(runtimes) - 1)].runtime_principal_id,
                ),
                valid_from=(
                    start
                    + timedelta(
                        days=(
                            index
                            * config.longitudinal.credential_rotation_interval_days
                        )
                    )
                ),
                expires_at=(
                    start
                    + timedelta(
                        days=(
                            min(
                                index + 1,
                                rotation_count,
                            )
                            * config.longitudinal.credential_rotation_interval_days
                            if index < rotation_count
                            else config.longitudinal.virtual_duration_days + 30
                        )
                    )
                ),
            )
            for index in range(rotation_count + 1)
        )
    snapshot = AgenticWorldSnapshot(
        world_id=world_id,
        world_version=config.profile_version,
        seed=config.seed,
        organisations=tuple(sorted(organisations, key=lambda item: item.id)),
        departments=tuple(sorted(departments, key=lambda item: item.id)),
        principals=tuple(
            sorted(
                (
                    *organisation_principals,
                    *humans,
                    *services,
                    *workloads,
                ),
                key=lambda item: item.id,
            )
        ),
        agents=tuple(sorted(agents, key=lambda item: item.id)),
        resources=tuple(sorted(resources, key=lambda item: item.id)),
        policies=(
            PolicyVersion(id=make_id("policy", "v1"), version=_POLICY_V1),
            PolicyVersion(id=make_id("policy", "v2"), version=_POLICY_V2),
        ),
        initial_evidence_refs=(
            f"evidence:policy:{_POLICY_V1}",
            f"evidence:policy:{_POLICY_V2}",
        ),
    )
    metadata = EnterpriseAgenticTopologyMetadataV2(
        teams=tuple(sorted(teams, key=lambda item: item.id)),
        people=tuple(sorted(person_profiles, key=lambda item: item.principal_id)),
        resources=tuple(sorted(resource_profiles, key=lambda item: item.resource_id)),
        credentials=tuple(
            sorted(
                (
                    *(
                        EnterpriseAgenticCredentialProfileV2(
                            credential_id=credential.id,
                            credential_kind=(
                                "shared_workload_handle"
                                if index < shared_count
                                else "workload_handle"
                            ),
                        )
                        for index, credential in enumerate(ordinary_credentials)
                    ),
                    *(
                        EnterpriseAgenticCredentialProfileV2(
                            credential_id=credential.id,
                            credential_kind="lifecycle_control_handle",
                        )
                        for credential in (
                            *control_credentials,
                            *rotation_credentials,
                        )
                    ),
                ),
                key=lambda item: item.credential_id,
            )
        ),
        isolated_tenant_ids=tuple(sorted(item.tenant_id for item in organisations[1:])),
    )
    return _ScaleRows(
        snapshot=snapshot,
        topology=metadata,
        runtimes=tuple(runtimes),
        ordinary_credentials=ordinary_credentials,
        control_credentials=control_credentials,
        rotation_credentials=rotation_credentials,
        delegations=tuple(delegations),
        replacement_policy_delegation=replacement_policy_delegation,
        late_delegation_id=delegations[-1].id,
    )


def _build_scale_events(
    config: EnterpriseAgenticGenerationConfigV2,
    identifier: Callable[..., str],
    rows: _ScaleRows,
) -> tuple[
    tuple[AgenticEvent, ...],
    tuple[CanonicalBinding, ...],
    tuple[AgenticCase, ...],
    tuple[EnterpriseAgenticLifecycleCaseV2, ...],
    tuple[EnterpriseAgenticLifecycleEventV2, ...],
    PublicScenario,
]:
    make_id = identifier
    start = _start_time(config.seed)
    events: list[AgenticEvent] = []
    bindings: list[CanonicalBinding] = []
    cases: list[AgenticCase] = []
    lifecycle_cases: list[EnterpriseAgenticLifecycleCaseV2] = []
    lifecycle_events: list[EnterpriseAgenticLifecycleEventV2] = []
    clock = start

    def add_event(
        label: str,
        payload: AgenticEventPayload,
        evidence_refs: tuple[str, ...] = (),
        *,
        not_before: datetime | None = None,
    ) -> AgenticEvent:
        nonlocal clock
        next_minute = clock + timedelta(minutes=1)
        clock = next_minute if not_before is None else max(next_minute, not_before)
        event = AgenticEvent(
            id=make_id("event", label),
            event_index=len(events) + 1,
            occurred_at=clock,
            evidence_refs=evidence_refs,
            payload=payload,
        )
        events.append(event)
        return event

    def add_lifecycle(
        label: str,
        payload: EnterpriseAgenticLifecyclePayloadV2,
        occurred_at: datetime,
        related_event_id: str | None = None,
    ) -> None:
        lifecycle_events.append(
            EnterpriseAgenticLifecycleEventV2(
                id=make_id("lifecycle-event", label),
                sequence_index=len(lifecycle_events) + 1,
                occurred_at=occurred_at,
                related_agentic_event_id=related_event_id,
                payload=payload,
            )
        )

    for runtime in rows.runtimes:
        add_event(
            f"runtime-{runtime.id}",
            RuntimeSpawned(runtime=runtime),
            (f"evidence:runtime:{runtime.id}",),
        )
    initially_issued = (
        *rows.ordinary_credentials,
        *rows.control_credentials,
        *(rows.rotation_credentials[:1]),
    )
    for credential in initially_issued:
        add_event(
            f"credential-{credential.id}",
            CredentialIssued(credential=credential),
            (f"evidence:credential:{credential.id}",),
        )
    delegation_by_id = {item.id: item for item in rows.delegations}
    late_delegation = delegation_by_id[rows.late_delegation_id]
    for delegation in rows.delegations:
        if delegation.id != rows.late_delegation_id:
            add_event(
                f"delegation-{delegation.id}",
                DelegationGranted(delegation=delegation),
                (f"evidence:delegation:{delegation.id}",),
            )
    snapshot_principals = {item.id: item for item in rows.snapshot.principals}
    snapshot_resources = {item.id: item for item in rows.snapshot.resources}
    agents_in_generation_order = tuple(
        sorted(
            rows.snapshot.agents,
            key=lambda item: int(item.display_name.rsplit(" ", 1)[-1]),
        )
    )
    runtime_by_agent: dict[str, Runtime] = {}
    for runtime in rows.runtimes:
        runtime_by_agent.setdefault(runtime.logical_agent_id, runtime)
    credential_by_runtime = {
        runtime.runtime_principal_id: credential
        for runtime, credential in zip(
            rows.runtimes, rows.ordinary_credentials, strict=True
        )
    }

    def add_action(
        label: str,
        lifecycle_kind: EnterpriseAgenticLifecycleCaseKindV2,
        core_kind: AgenticCaseKind,
        *,
        agent_index: int,
        credential: Credential | None = None,
        resource: Resource | None = None,
        action: str = "read",
        policy_version: str = _POLICY_V1,
        proposed_delegation: Delegation | None = None,
        attributed_actor_claim: str | None = None,
        cite_delegation: bool = True,
        not_before: datetime | None = None,
    ) -> AgenticEvent:
        agent = agents_in_generation_order[
            agent_index % len(agents_in_generation_order)
        ]
        delegation = next(
            item for item in rows.delegations if item.grantee_agent_id == agent.id
        )
        if cite_delegation and delegation.id == rows.late_delegation_id:
            agent = agents_in_generation_order[
                (agent_index - 1) % len(agents_in_generation_order)
            ]
            delegation = next(
                item for item in rows.delegations if item.grantee_agent_id == agent.id
            )
        runtime = runtime_by_agent[agent.id]
        chosen_credential = (
            credential or credential_by_runtime[runtime.runtime_principal_id]
        )
        chosen_resource = (
            resource or snapshot_resources[delegation.capability.resource_ids[0]]
        )
        service_actor = cast(
            str,
            snapshot_principals[runtime.runtime_principal_id].owner_principal_id,
        )
        evidence_refs = {
            f"evidence:policy:{policy_version}",
            f"evidence:runtime:{runtime.id}",
            f"evidence:credential:{chosen_credential.id}",
        }
        if cite_delegation:
            evidence_refs.add(f"evidence:delegation:{delegation.id}")
        event = add_event(
            label,
            ActionAttempted(
                attempt=ActionAttempt(
                    originating_principal_claim=delegation.originating_principal_id,
                    logical_agent_claim=agent.id,
                    runtime_principal_claim=runtime.runtime_principal_id,
                    presented_credential_id=chosen_credential.id,
                    attributed_actor_claim=(attributed_actor_claim or service_actor),
                    resource_id=chosen_resource.id,
                    action=action,
                    requested_scope=delegation.capability.scopes[:1],
                    purpose=_PURPOSE,
                    policy_version=policy_version,
                    evidence_refs=tuple(sorted(evidence_refs)),
                    proposed_delegation=proposed_delegation,
                )
            ),
            not_before=not_before,
        )
        bindings.append(
            CanonicalBinding(
                action_event_id=event.id,
                originating_principal_id=delegation.originating_principal_id,
                logical_agent_id=agent.id,
                runtime_id=runtime.id,
                runtime_principal_id=runtime.runtime_principal_id,
                credential_subject_id=chosen_credential.subject_principal_id,
                attributed_actor_id=service_actor,
                accountable_owner_chain=derive_agent_owner_chain(
                    rows.snapshot, agent.id
                ),
            )
        )
        cases.append(AgenticCase(action_event_id=event.id, kind=core_kind))
        lifecycle_cases.append(
            EnterpriseAgenticLifecycleCaseV2(
                action_event_id=event.id,
                kind=lifecycle_kind,
            )
        )
        return event

    prevalence = config.prevalence

    def repeat(count: int, callback: Callable[[int], object]) -> None:
        for occurrence in range(count):
            callback(occurrence)

    repeat(
        prevalence.authorised_action,
        lambda occurrence: add_action(
            f"action-authorised-{occurrence}",
            EnterpriseAgenticLifecycleCaseKindV2.AUTHORISED_ACTION,
            AgenticCaseKind.AUTHORISED_ACTION,
            agent_index=(occurrence + 8),
        ),
    )
    repeat(
        prevalence.excessive_capability,
        lambda occurrence: add_action(
            f"action-excessive-{occurrence}",
            EnterpriseAgenticLifecycleCaseKindV2.EXCESSIVE_CAPABILITY,
            AgenticCaseKind.OUTSIDE_CAPABILITY,
            agent_index=(occurrence + 8),
            action="write",
        ),
    )

    def overprivileged(occurrence: int) -> None:
        agent_index = 2 + (occurrence % max(1, len(agents_in_generation_order) - 2))
        agent = agents_in_generation_order[agent_index]
        delegation = next(
            item for item in rows.delegations if item.grantee_agent_id == agent.id
        )
        proposal = delegation.model_copy(
            update={
                "id": make_id("proposed-delegation", str(occurrence)),
                "capability": delegation.capability.model_copy(
                    update={"actions": _ACTIONS}
                ),
            }
        )
        add_action(
            f"action-overprivileged-{occurrence}",
            EnterpriseAgenticLifecycleCaseKindV2.OVERPRIVILEGED_CHILD_DELEGATION,
            AgenticCaseKind.OVERPRIVILEGED_SUBDELEGATION,
            agent_index=agent_index,
            proposed_delegation=proposal,
        )

    repeat(prevalence.overprivileged_child_delegation, overprivileged)
    wrong_runtime = rows.control_credentials[0]
    repeat(
        prevalence.wrong_runtime,
        lambda occurrence: add_action(
            f"action-wrong-runtime-{occurrence}",
            EnterpriseAgenticLifecycleCaseKindV2.WRONG_RUNTIME,
            AgenticCaseKind.WRONG_RUNTIME,
            agent_index=0,
            credential=wrong_runtime,
        ),
    )
    shared_credential = rows.ordinary_credentials[0]
    repeat(
        prevalence.shared_credential_reuse,
        lambda occurrence: add_action(
            f"action-shared-credential-{occurrence}",
            EnterpriseAgenticLifecycleCaseKindV2.SHARED_CREDENTIAL_REUSE,
            AgenticCaseKind.SHARED_CREDENTIAL,
            agent_index=1,
            credential=shared_credential,
        ),
    )
    if prevalence.cross_tenant_confusion:
        other_tenant_resource = next(
            item
            for item in rows.snapshot.resources
            if item.organisation_id != agents_in_generation_order[1].organisation_id
        )
        repeat(
            prevalence.cross_tenant_confusion,
            lambda occurrence: add_action(
                f"action-cross-tenant-{occurrence}",
                EnterpriseAgenticLifecycleCaseKindV2.CROSS_TENANT_CONFUSION,
                AgenticCaseKind.CROSS_TENANT_CONFUSION,
                agent_index=1,
                resource=other_tenant_resource,
            ),
        )
    unrelated_actor = next(
        item.id
        for item in rows.snapshot.principals
        if item.kind is PrincipalKind.HUMAN
        and item.organisation_id == agents_in_generation_order[3].organisation_id
        and item.id != agents_in_generation_order[3].owner_principal_id
    )
    repeat(
        prevalence.incorrect_attribution,
        lambda occurrence: add_action(
            f"action-attribution-{occurrence}",
            EnterpriseAgenticLifecycleCaseKindV2.INCORRECT_ATTRIBUTION,
            AgenticCaseKind.INCORRECT_ATTRIBUTION,
            agent_index=3,
            attributed_actor_claim=unrelated_actor,
        ),
    )
    valid_revoke_agent_index = min(4, len(agents_in_generation_order) - 1)
    repeat(
        prevalence.valid_then_revoked,
        lambda occurrence: add_action(
            f"action-valid-then-revoked-{occurrence}",
            EnterpriseAgenticLifecycleCaseKindV2.VALID_THEN_REVOKED,
            AgenticCaseKind.VALID_THEN_REVOKED,
            agent_index=valid_revoke_agent_index,
        ),
    )
    late_agent_index = next(
        index
        for index, agent in enumerate(agents_in_generation_order)
        if next(
            item for item in rows.delegations if item.grantee_agent_id == agent.id
        ).id
        == rows.late_delegation_id
    )
    repeat(
        prevalence.invalid_then_later_granted,
        lambda occurrence: add_action(
            f"action-invalid-before-grant-{occurrence}",
            EnterpriseAgenticLifecycleCaseKindV2.INVALID_THEN_LATER_GRANTED,
            AgenticCaseKind.INVALID_THEN_LATER_GRANTED,
            agent_index=late_agent_index,
            cite_delegation=False,
        ),
    )
    evidence_agent_index = min(3, len(agents_in_generation_order) - 1)
    repeat(
        prevalence.evidence_loss,
        lambda occurrence: add_action(
            f"action-evidence-loss-{occurrence}",
            EnterpriseAgenticLifecycleCaseKindV2.EVIDENCE_LOSS,
            AgenticCaseKind.MISSING_RETAINED_EVIDENCE,
            agent_index=evidence_agent_index,
        ),
    )
    expired_credential = rows.control_credentials[1]
    repeat(
        prevalence.expired_credential,
        lambda occurrence: add_action(
            f"action-expired-{occurrence}",
            EnterpriseAgenticLifecycleCaseKindV2.EXPIRED_CREDENTIAL,
            AgenticCaseKind.CREDENTIAL_INVALID,
            agent_index=0,
            credential=expired_credential,
            not_before=start + timedelta(days=3),
        ),
    )
    if config.longitudinal is None:
        repeat(
            prevalence.policy_version_drift,
            lambda occurrence: add_action(
                f"action-policy-drift-{occurrence}",
                EnterpriseAgenticLifecycleCaseKindV2.POLICY_VERSION_DRIFT,
                AgenticCaseKind.POLICY_VERSION_MISMATCH,
                agent_index=min(5, len(agents_in_generation_order) - 1),
                policy_version=_POLICY_V2,
            ),
        )
    add_event(
        "late-delegation-granted",
        DelegationGranted(delegation=late_delegation),
        (f"evidence:delegation:{late_delegation.id}",),
    )
    if prevalence.valid_then_revoked:
        valid_revoke_agent = agents_in_generation_order[valid_revoke_agent_index]
        valid_revoke_delegation = next(
            item
            for item in rows.delegations
            if item.grantee_agent_id == valid_revoke_agent.id
        )
        add_event(
            "valid-delegation-revoked",
            DelegationRevoked(delegation_id=valid_revoke_delegation.id),
            (f"evidence:revocation:{valid_revoke_delegation.id}",),
        )
    evidence_agent = agents_in_generation_order[evidence_agent_index]
    evidence_delegation = next(
        item for item in rows.delegations if item.grantee_agent_id == evidence_agent.id
    )

    if config.longitudinal is not None:
        _append_longitudinal_events(
            config,
            rows,
            add_event,
            add_lifecycle,
            add_action,
            agents_in_generation_order,
            start,
        )
        evidence_not_before = start + timedelta(
            days=config.longitudinal.evidence_retention_days
        )
    else:
        evidence_not_before = None
    if prevalence.evidence_loss:
        add_event(
            "delegation-evidence-discarded",
            EvidenceDiscarded(
                evidence_refs=(f"evidence:delegation:{evidence_delegation.id}",)
            ),
            not_before=evidence_not_before,
        )
    audit_time = start + timedelta(
        days=(
            config.longitudinal.virtual_duration_days
            if config.longitudinal is not None
            else 30
        )
    )
    audit_id = make_id("audit", config.tier.value)
    audit = add_event(
        "audit",
        AuditPerformed(audit_id=audit_id),
        (f"evidence:audit:{audit_id}",),
        not_before=audit_time,
    )
    scenario = PublicScenario(
        id=make_id("scenario", config.tier.value),
        title=f"Generated enterprise agent authority {config.tier.value} benchmark",
        description=(
            "A deterministic fictional enterprise workload covering scale, "
            "identity, credential, delegation, tenant, lifecycle, and audit controls."
        ),
        action_event_ids=tuple(item.action_event_id for item in cases),
        audit_event_id=audit.id,
        tool_schema_paths=("tool_schemas/enterprise-agentic-actions-v1.json",),
    )
    if len(events) > config.limits.max_events:
        raise ValueError("generated events exceed the generation limit")
    ordered_lifecycle_events = tuple(
        item.model_copy(update={"sequence_index": sequence_index})
        for sequence_index, item in enumerate(
            sorted(
                lifecycle_events,
                key=lambda item: (item.occurred_at, item.sequence_index),
            ),
            start=1,
        )
    )
    return (
        tuple(events),
        tuple(bindings),
        tuple(cases),
        tuple(lifecycle_cases),
        ordered_lifecycle_events,
        scenario,
    )


def _append_longitudinal_events(
    config: EnterpriseAgenticGenerationConfigV2,
    rows: _ScaleRows,
    add_event: Callable[..., AgenticEvent],
    add_lifecycle: Callable[
        [str, EnterpriseAgenticLifecyclePayloadV2, datetime, str | None], None
    ],
    add_action: Callable[..., AgenticEvent],
    agents: tuple[LogicalAgent, ...],
    start: datetime,
) -> None:
    schedule = cast(EnterpriseAgenticLongitudinalScheduleV2, config.longitudinal)
    people = rows.topology.people
    departments = rows.snapshot.departments
    add_lifecycle(
        "person-joined",
        EnterpriseAgenticPersonStatusChangedV2(
            principal_id=people[0].principal_id,
            state=EnterpriseAgenticPersonLifecycleStateV2.JOINED,
            department_id=departments[0].id,
        ),
        start + timedelta(days=10),
        None,
    )
    add_lifecycle(
        "person-moved",
        EnterpriseAgenticPersonStatusChangedV2(
            principal_id=people[1].principal_id,
            state=EnterpriseAgenticPersonLifecycleStateV2.MOVED,
            previous_department_id=departments[0].id,
            department_id=departments[1].id,
        ),
        start + timedelta(days=30),
        None,
    )
    add_lifecycle(
        "person-left",
        EnterpriseAgenticPersonStatusChangedV2(
            principal_id=people[2].principal_id,
            state=EnterpriseAgenticPersonLifecycleStateV2.LEFT,
            previous_department_id=departments[1].id,
        ),
        start + timedelta(days=60),
        None,
    )

    def rotate(index: int, credential: Credential) -> None:
        rotation_time = start + timedelta(
            days=index * schedule.credential_rotation_interval_days
        )
        issued = add_event(
            f"rotation-credential-issued-{index}",
            CredentialIssued(credential=credential),
            (f"evidence:credential:{credential.id}",),
            not_before=rotation_time,
        )
        previous = rows.rotation_credentials[index - 1]
        add_lifecycle(
            f"credential-rotated-{index}",
            EnterpriseAgenticCredentialRotatedV2(
                old_credential_id=previous.id,
                new_credential_id=credential.id,
            ),
            issued.occurred_at,
            issued.id,
        )
        add_lifecycle(
            f"credential-revoked-{index}",
            EnterpriseAgenticCredentialStatusChangedV2(
                credential_id=previous.id,
                state=EnterpriseAgenticCredentialLifecycleStateV2.REVOKED,
            ),
            issued.occurred_at,
            issued.id,
        )
        if index <= config.prevalence.rotated_credential_reuse:
            add_action(
                f"action-rotated-credential-{index}",
                EnterpriseAgenticLifecycleCaseKindV2.ROTATED_CREDENTIAL_REUSE,
                AgenticCaseKind.CREDENTIAL_INVALID,
                agent_index=min(6, len(agents) - 1),
                credential=previous,
            )

    def suspend() -> None:
        suspension_index = min(7, len(agents) - 1)
        suspended_credential = rows.control_credentials[-1]
        suspension_time = start + timedelta(
            days=schedule.credential_rotation_interval_days + 10
        )
        add_lifecycle(
            "credential-suspended",
            EnterpriseAgenticCredentialStatusChangedV2(
                credential_id=suspended_credential.id,
                state=EnterpriseAgenticCredentialLifecycleStateV2.SUSPENDED,
            ),
            suspension_time,
            None,
        )
        for occurrence in range(config.prevalence.suspended_credential):
            add_action(
                f"action-suspended-credential-{occurrence}",
                EnterpriseAgenticLifecycleCaseKindV2.SUSPENDED_CREDENTIAL,
                AgenticCaseKind.CREDENTIAL_INVALID,
                agent_index=suspension_index,
                credential=suspended_credential,
                not_before=suspension_time,
            )

    def activate_policy() -> None:
        policy_agent_index = min(5, len(agents) - 1)
        policy_agent = agents[policy_agent_index]
        old_policy_delegation = next(
            item
            for item in rows.delegations
            if item.grantee_agent_id == policy_agent.id
        )
        policy_time = start + timedelta(days=schedule.policy_change_day)
        add_event(
            "old-policy-delegation-revoked",
            DelegationRevoked(delegation_id=old_policy_delegation.id),
            (f"evidence:revocation:{old_policy_delegation.id}",),
            not_before=policy_time,
        )
        replacement = add_event(
            "new-policy-delegation-granted",
            DelegationGranted(delegation=rows.replacement_policy_delegation),
            (f"evidence:delegation:{rows.replacement_policy_delegation.id}",),
        )
        add_lifecycle(
            "policy-activated",
            EnterpriseAgenticPolicyActivatedV2(
                previous_policy_version=_POLICY_V1,
                policy_version=_POLICY_V2,
            ),
            replacement.occurred_at,
            replacement.id,
        )
        for occurrence in range(config.prevalence.policy_version_drift):
            add_action(
                f"action-longitudinal-policy-drift-{occurrence}",
                EnterpriseAgenticLifecycleCaseKindV2.POLICY_VERSION_DRIFT,
                AgenticCaseKind.POLICY_VERSION_MISMATCH,
                agent_index=policy_agent_index,
                policy_version=_POLICY_V1,
            )

    def offboard_agent() -> None:
        offboard_agent_index = min(8, len(agents) - 1)
        offboard_agent = agents[offboard_agent_index]
        offboard_delegation = next(
            item
            for item in rows.delegations
            if item.grantee_agent_id == offboard_agent.id
        )
        offboard_time = start + timedelta(days=schedule.agent_offboarding_day)
        offboard_revocation = add_event(
            "offboard-agent-delegation-revoked",
            DelegationRevoked(delegation_id=offboard_delegation.id),
            (f"evidence:revocation:{offboard_delegation.id}",),
            not_before=offboard_time,
        )
        offboard_runtime = next(
            item for item in rows.runtimes if item.logical_agent_id == offboard_agent.id
        )
        offboard_credential = next(
            item
            for item in rows.ordinary_credentials
            if offboard_runtime.runtime_principal_id
            in item.allowed_runtime_principal_ids
        )
        add_lifecycle(
            "agent-offboarded",
            EnterpriseAgenticAgentStatusChangedV2(
                agent_id=offboard_agent.id,
                state=EnterpriseAgenticAgentLifecycleStateV2.OFFBOARDED,
                active_credential_ids=(offboard_credential.id,),
            ),
            offboard_revocation.occurred_at,
            offboard_revocation.id,
        )
        for occurrence in range(config.prevalence.agent_offboarding_active_credential):
            add_action(
                f"action-offboarded-agent-{occurrence}",
                EnterpriseAgenticLifecycleCaseKindV2.AGENT_OFFBOARDING_ACTIVE_CREDENTIAL,
                AgenticCaseKind.POST_REVOCATION_ACTION,
                agent_index=offboard_agent_index,
                credential=offboard_credential,
            )

    def propagate_revocation() -> None:
        child_index = next(
            index
            for index, item in enumerate(agents)
            if item.parent_agent_id is not None
        )
        child_agent = agents[child_index]
        child_delegation = next(
            item for item in rows.delegations if item.grantee_agent_id == child_agent.id
        )
        parent_id = cast(str, child_delegation.parent_delegation_id)
        propagation_time = start + timedelta(days=schedule.agent_offboarding_day + 10)
        parent_revocation = add_event(
            "parent-delegation-revoked",
            DelegationRevoked(delegation_id=parent_id),
            (f"evidence:revocation:{parent_id}",),
            not_before=propagation_time,
        )
        add_lifecycle(
            "delegation-revocation-propagated",
            EnterpriseAgenticDelegationPropagationV2(
                parent_delegation_id=parent_id,
                descendant_delegation_ids=(child_delegation.id,),
            ),
            parent_revocation.occurred_at,
            parent_revocation.id,
        )
        for occurrence in range(config.prevalence.revocation_propagation_failure):
            add_action(
                f"action-revocation-propagation-{occurrence}",
                EnterpriseAgenticLifecycleCaseKindV2.REVOCATION_PROPAGATION_FAILURE,
                AgenticCaseKind.POST_REVOCATION_ACTION,
                agent_index=child_index,
            )

    scheduled: list[tuple[int, int, Callable[[], None]]] = [
        (
            index * schedule.credential_rotation_interval_days,
            0,
            partial(rotate, index, credential),
        )
        for index, credential in enumerate(rows.rotation_credentials[1:], start=1)
    ]
    scheduled.extend(
        (
            (
                schedule.credential_rotation_interval_days + 10,
                1,
                suspend,
            ),
            (schedule.policy_change_day, 2, activate_policy),
            (schedule.agent_offboarding_day, 3, offboard_agent),
            (schedule.agent_offboarding_day + 10, 4, propagate_revocation),
        )
    )
    for _, _, operation in sorted(scheduled, key=lambda item: (item[0], item[1])):
        operation()


def derive_enterprise_agentic_scale_integrity_metrics(
    benchmark: AgenticBenchmark,
    topology: EnterpriseAgenticTopologyMetadataV2,
    lifecycle_events: tuple[EnterpriseAgenticLifecycleEventV2, ...],
    lifecycle_cases: tuple[EnterpriseAgenticLifecycleCaseV2, ...],
) -> EnterpriseAgenticIntegrityMetricsV2:
    """Derive scale and integrity observations from generated records."""

    snapshot = benchmark.public.snapshot
    state = materialize_agentic_world(snapshot, benchmark.public.events)
    principals = snapshot.principals
    actions = benchmark.evaluator.authority_truth
    principal_count = len(principals)
    action_count = len(actions)
    population_counts = Counter(item.population_kind.value for item in topology.people)
    lifecycle_counts: Counter[str] = Counter(
        str(item.payload.event_type) for item in lifecycle_events
    )
    case_counts = Counter(item.kind.value for item in lifecycle_cases)
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
        "isolated_tenant_count": (
            len(topology.isolated_tenant_ids),
            len(snapshot.organisations),
            "generated organisations",
        ),
        "lifecycle_event_count": (
            len(lifecycle_events),
            len(lifecycle_events),
            "generated lifecycle events",
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
        "team_count": (len(topology.teams), len(topology.teams), "generated teams"),
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
    child_counts = Counter(
        sum(child.parent_delegation_id == delegation.id for child in state.delegations)
        for delegation in state.delegations
    )
    return EnterpriseAgenticIntegrityMetricsV2(
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
        delegation_branching_distribution=_distribution(
            child_counts, len(state.delegations), "generated delegations"
        ),
        case_kind_distribution=_distribution(
            case_counts, len(lifecycle_cases), "generated action cases"
        ),
        population_kind_distribution=_distribution(
            population_counts, len(topology.people), "generated human principals"
        ),
        lifecycle_event_kind_distribution=_distribution(
            lifecycle_counts, len(lifecycle_events), "generated lifecycle events"
        ),
        principal_graph_component_count=_principal_component_count(principals),
    )


def _start_time(seed: int) -> datetime:
    return datetime(2035, 1, 1, 9, 0, tzinfo=UTC) + timedelta(days=seed % 365)


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
    "default_enterprise_agentic_generation_config_v2",
    "derive_enterprise_agentic_scale_integrity_metrics",
    "generate_enterprise_agentic_scale_world",
]
