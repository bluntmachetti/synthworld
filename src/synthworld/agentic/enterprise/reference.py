"""Deterministic enterprise-agentic smoke pack over the fixed PR4 universe."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from pydantic import BaseModel

from synthworld.agentic.enterprise.common import stable_enterprise_agentic_id
from synthworld.agentic.enterprise.models import (
    AgentAsPrincipalV1,
    AgenticAdministrativeState,
    EnterpriseAgentAccountV1,
    EnterpriseAgentCapabilityV1,
    EnterpriseAgentCredentialV1,
    EnterpriseAgentDelegationV1,
    EnterpriseAgenticAccessPublicInputV1,
    EnterpriseAgenticActionAttemptedV1,
    EnterpriseAgenticActionAttemptV1,
    EnterpriseAgenticAuditPerformedV1,
    EnterpriseAgenticCaseKind,
    EnterpriseAgenticCredentialRevokedV1,
    EnterpriseAgenticDelegationRevokedV1,
    EnterpriseAgenticEvaluatorArtifactsV1,
    EnterpriseAgenticEventV1,
    EnterpriseAgenticEvidenceDiscardedV1,
    EnterpriseAgenticProjectionConfigV1,
    EnterpriseAgenticPublicInputV1,
    EnterpriseAgenticSnapshotV1,
    EnterpriseAgentRuntimeV1,
    HumanSubjectAgentContextV1,
)
from synthworld.agentic.enterprise.projection import (
    compile_enterprise_agentic_truth,
    project_enterprise_agentic_public,
)
from synthworld.enterprise.authorization.models import CompiledEnterpriseAccessCellV1
from synthworld.enterprise.authorization.reference import (
    ReferenceEnterpriseAuthorizationInputsV1,
    reference_enterprise_authorization_inputs,
)
from synthworld.enterprise.canonical import canonical_json_bytes
from synthworld.enterprise.models import AccessAtomV1, PrincipalKind
from synthworld.enterprise.rbac.common import AuthorizationDecision

REFERENCE_ENTERPRISE_AGENTIC_SEED = 20_260_804
REFERENCE_ENTERPRISE_AGENTIC_UNIVERSE_SHA256 = (
    "b4eae423689ede98d98858cae004f98d07fa5b0ac4774858500a4ba257946f4a"
)
REFERENCE_ENTERPRISE_AGENTIC_CORPUS_SHA256 = (
    "1293dc2a22820f1e0b72f85c7c17028872c424b7483223f50b6f4dd822acf1d6"
)


@dataclass(frozen=True, slots=True)
class ReferenceEnterpriseAgenticV1:
    authorization: ReferenceEnterpriseAuthorizationInputsV1
    public: EnterpriseAgenticPublicInputV1
    evaluator: EnterpriseAgenticEvaluatorArtifactsV1


@dataclass(frozen=True, slots=True)
class _CellSelection:
    cell: CompiledEnterpriseAccessCellV1
    atom: AccessAtomV1
    request_id: str


@dataclass(frozen=True, slots=True)
class _OverlayInventory:
    accounts: dict[tuple[str, str], EnterpriseAgentAccountV1]
    runtimes: dict[tuple[str, str], EnterpriseAgentRuntimeV1]
    credentials: dict[tuple[str, str], EnterpriseAgentCredentialV1]
    capabilities: dict[tuple[str, str, str, str], EnterpriseAgentCapabilityV1]
    delegations: dict[str, EnterpriseAgentDelegationV1]
    external_tenant_id: str
    revoked_credential_id: str
    revoked_delegation_id: str


def reference_enterprise_agentic(
    *, seed: int = REFERENCE_ENTERPRISE_AGENTIC_SEED
) -> ReferenceEnterpriseAgenticV1:
    """Build the full smoke pack without adding an enterprise entity, atom, or cell."""

    authorization = reference_enterprise_authorization_inputs()
    rbac = authorization.rbac
    universe = rbac.universe_result.public_universe
    corpus = rbac.corpus_result.public_corpus
    _require_frozen_access_inputs(universe, corpus)
    access = EnterpriseAgenticAccessPublicInputV1(
        universe=universe,
        corpus=corpus,
        directory_rbac_kernel=rbac.kernel,
        directory_rbac_intent=rbac.intent,
        rbac_session_state=rbac.session_state,
        abac_state=authorization.abac_state,
        abac_intent=authorization.abac_intent,
        rebac_state=authorization.rebac_state,
        rebac_intent=authorization.rebac_intent,
        composition=authorization.composition,
        evaluation_profile=authorization.evaluation_profile,
        authorization_kernel=authorization.authorization_kernel,
    )
    principals = tuple(sorted(universe.principals, key=lambda item: item.principal_id))
    agents = tuple(
        item.principal_id
        for item in principals
        if item.principal_kind is PrincipalKind.AGENT
    )
    humans = tuple(
        item.principal_id
        for item in principals
        if item.principal_kind is PrincipalKind.EMPLOYEE
        and _has_both_decisions(item.principal_id, authorization)
    )
    primary_agent = agents[seed % len(agents)]
    other_agent = next(item for item in agents if item != primary_agent)
    primary_human = humans[seed % len(humans)]
    other_human = humans[(seed + 1) % len(humans)]
    agent_allow = _select_cell(
        authorization, subject_id=primary_agent, decision=AuthorizationDecision.ALLOW
    )
    agent_deny = _select_any_agent_denial(authorization, set(agents))
    human_allow = _select_cell(
        authorization, subject_id=primary_human, decision=AuthorizationDecision.ALLOW
    )
    human_deny = _select_cell(
        authorization, subject_id=primary_human, decision=AuthorizationDecision.DENY
    )
    other_human_allow = _select_cell(
        authorization,
        subject_id=other_human,
        decision=AuthorizationDecision.ALLOW,
        target_id=human_allow.atom.authorization_target_id,
        action=human_allow.atom.action,
    )
    inventory = _build_overlay_inventory(
        authorization=authorization,
        agents=agents,
        primary_agent=primary_agent,
        primary_human=primary_human,
        other_human=other_human,
        cells=(agent_allow, agent_deny, human_allow, human_deny, other_human_allow),
    )
    snapshot, events = _build_snapshot_and_events(
        inventory=inventory,
        primary_agent=primary_agent,
        other_agent=other_agent,
        primary_human=primary_human,
        other_human=other_human,
        agent_allow=agent_allow,
        agent_deny=agent_deny,
        human_allow=human_allow,
        human_deny=human_deny,
        other_human_allow=other_human_allow,
    )
    public = project_enterprise_agentic_public(
        access=access,
        snapshot=snapshot,
        events=events,
        config=EnterpriseAgenticProjectionConfigV1(seed=seed),
    )
    evaluator = compile_enterprise_agentic_truth(
        public=public,
        canonical_binding_truth=rbac.universe_result.evaluator_canonical_binding_truth,
        directory_rbac_truth=authorization.directory_rbac_truth,
        abac_truth=authorization.abac_truth,
        rebac_truth=authorization.rebac_truth,
        access_state=authorization.access_state,
    )
    _require_case_inventory(evaluator)
    return ReferenceEnterpriseAgenticV1(
        authorization=authorization,
        public=public,
        evaluator=evaluator,
    )


def _build_overlay_inventory(
    *,
    authorization: ReferenceEnterpriseAuthorizationInputsV1,
    agents: tuple[str, ...],
    primary_agent: str,
    primary_human: str,
    other_human: str,
    cells: tuple[_CellSelection, ...],
) -> _OverlayInventory:
    tenant_id = authorization.rbac.universe_result.public_universe.tenants[0].tenant_id
    external_tenant = stable_enterprise_agentic_id("tenant", "external-example")
    accounts: dict[tuple[str, str], EnterpriseAgentAccountV1] = {}
    runtimes: dict[tuple[str, str], EnterpriseAgentRuntimeV1] = {}
    credentials: dict[tuple[str, str], EnterpriseAgentCredentialV1] = {}
    for agent in agents:
        for variant, state, variant_tenant in (
            ("active", AgenticAdministrativeState.ACTIVE, tenant_id),
            ("suspended", AgenticAdministrativeState.SUSPENDED, tenant_id),
            ("cross_tenant", AgenticAdministrativeState.ACTIVE, external_tenant),
        ):
            account = EnterpriseAgentAccountV1(
                id=stable_enterprise_agentic_id("account", agent, variant),
                tenant_id=variant_tenant,
                agent_principal_id=agent,
                administrative_state=state,
                valid_from_tick=0,
                valid_until_tick=100,
            )
            runtime = EnterpriseAgentRuntimeV1(
                id=stable_enterprise_agentic_id("runtime", agent, variant),
                tenant_id=variant_tenant,
                agent_principal_id=agent,
                agent_account_id=account.id,
            )
            credential = EnterpriseAgentCredentialV1(
                id=stable_enterprise_agentic_id("credential", agent, variant),
                opaque_handle=stable_enterprise_agentic_id(
                    "opaque-credential-handle", agent, variant
                ),
                tenant_id=variant_tenant,
                agent_principal_id=agent,
                agent_account_id=account.id,
                allowed_runtime_ids=(runtime.id,),
                valid_from_tick=0,
                valid_until_tick=100,
            )
            accounts[(agent, variant)] = account
            runtimes[(agent, variant)] = runtime
            credentials[(agent, variant)] = credential
    revoked_credentials: dict[str, EnterpriseAgentCredentialV1] = {}
    for agent in agents:
        other_agent = next(item for item in agents if item != agent)
        wrong_runtime = runtimes[(other_agent, "active")]
        credentials[(agent, "wrong_runtime")] = EnterpriseAgentCredentialV1(
            id=stable_enterprise_agentic_id("credential", agent, "wrong-runtime"),
            opaque_handle=stable_enterprise_agentic_id(
                "opaque-credential-handle", agent, "wrong-runtime"
            ),
            tenant_id=tenant_id,
            agent_principal_id=agent,
            agent_account_id=accounts[(agent, "active")].id,
            allowed_runtime_ids=(wrong_runtime.id,),
            valid_from_tick=0,
            valid_until_tick=100,
        )
        revoked = EnterpriseAgentCredentialV1(
            id=stable_enterprise_agentic_id("credential", agent, "revoked"),
            opaque_handle=stable_enterprise_agentic_id(
                "opaque-credential-handle", agent, "revoked"
            ),
            tenant_id=tenant_id,
            agent_principal_id=agent,
            agent_account_id=accounts[(agent, "active")].id,
            allowed_runtime_ids=(runtimes[(agent, "active")].id,),
            valid_from_tick=0,
            valid_until_tick=100,
        )
        credentials[(agent, "revoked")] = revoked
        revoked_credentials[agent] = revoked
    capabilities: dict[tuple[str, str, str, str], EnterpriseAgentCapabilityV1] = {}
    for agent in agents:
        for selected in cells:
            key = (
                agent,
                tenant_id,
                selected.atom.authorization_target_id,
                selected.atom.action,
            )
            capabilities[key] = _capability(*key)
            cross_key = (
                agent,
                external_tenant,
                selected.atom.authorization_target_id,
                selected.atom.action,
            )
            capabilities[cross_key] = _capability(*cross_key)
    delegations: dict[str, EnterpriseAgentDelegationV1] = {}
    primary_allow_capability = capabilities[
        (
            primary_agent,
            tenant_id,
            cells[2].atom.authorization_target_id,
            cells[2].atom.action,
        )
    ]
    revoked_delegation = _delegation(
        "revoked",
        tenant_id,
        primary_human,
        primary_agent,
        accounts[(primary_agent, "active")].id,
        primary_allow_capability.id,
    )
    delegations[revoked_delegation.id] = revoked_delegation
    for human in (primary_human, other_human):
        for agent in agents:
            for selected in cells:
                capability = capabilities[
                    (
                        agent,
                        tenant_id,
                        selected.atom.authorization_target_id,
                        selected.atom.action,
                    )
                ]
                delegation = _delegation(
                    "standard",
                    tenant_id,
                    human,
                    agent,
                    accounts[(agent, "active")].id,
                    capability.id,
                )
                delegations[delegation.id] = delegation
    return _OverlayInventory(
        accounts=accounts,
        runtimes=runtimes,
        credentials=credentials,
        capabilities=capabilities,
        delegations=delegations,
        external_tenant_id=external_tenant,
        revoked_credential_id=revoked_credentials[primary_agent].id,
        revoked_delegation_id=revoked_delegation.id,
    )


def _build_snapshot_and_events(
    *,
    inventory: _OverlayInventory,
    primary_agent: str,
    other_agent: str,
    primary_human: str,
    other_human: str,
    agent_allow: _CellSelection,
    agent_deny: _CellSelection,
    human_allow: _CellSelection,
    human_deny: _CellSelection,
    other_human_allow: _CellSelection,
) -> tuple[EnterpriseAgenticSnapshotV1, tuple[EnterpriseAgenticEventV1, ...]]:
    evidence: list[str] = []
    events: list[EnterpriseAgenticEventV1] = [
        EnterpriseAgenticEventV1(
            id=stable_enterprise_agentic_id(
                "event", "credential-revoked", inventory.revoked_credential_id
            ),
            tick=2,
            payload=EnterpriseAgenticCredentialRevokedV1(
                credential_id=inventory.revoked_credential_id
            ),
        ),
        EnterpriseAgenticEventV1(
            id=stable_enterprise_agentic_id(
                "event", "delegation-revoked", inventory.revoked_delegation_id
            ),
            tick=3,
            payload=EnterpriseAgenticDelegationRevokedV1(
                delegation_id=inventory.revoked_delegation_id
            ),
        ),
    ]

    def add_agent_case(
        *,
        kind: str,
        tick: int,
        selected: _CellSelection,
        agent: str,
        enterprise_subject_id: str | None = None,
        account_variant: str = "active",
        runtime_agent: str | None = None,
        credential_agent: str | None = None,
        credential_variant: str = "active",
        capability_tenant: str | None = None,
        owner_human: str | None = None,
        provenance_delegation_id: str | None = None,
        scopes: tuple[str, ...] = ("scope:standard",),
    ) -> None:
        runtime_owner = runtime_agent or agent
        runtime = inventory.runtimes[(runtime_owner, account_variant)]
        credential_key = (credential_agent or agent, credential_variant)
        credential = inventory.credentials[credential_key]
        capability = inventory.capabilities[
            (
                agent,
                capability_tenant or _tenant(inventory, agent, account_variant),
                selected.atom.authorization_target_id,
                selected.atom.action,
            )
        ]
        account = inventory.accounts[(agent, account_variant)]
        mapping = AgentAsPrincipalV1(
            enterprise_subject_id=enterprise_subject_id or selected.atom.subject_id,
            agent_principal_id=agent,
            agent_account_id=account.id,
            runtime_id=runtime.id,
            owner_human_principal_id=owner_human,
            provenance_delegation_id=provenance_delegation_id,
        )
        _append_action(
            events,
            evidence,
            kind=kind,
            tick=tick,
            selected=selected,
            mapping=mapping,
            credential_id=credential.id,
            capability_id=capability.id,
            scopes=scopes,
        )

    def add_human_case(
        *,
        kind: str,
        tick: int,
        selected: _CellSelection,
        human: str,
        agent: str,
        account_variant: str = "active",
        runtime_agent: str | None = None,
        credential_variant: str = "active",
        capability_tenant: str | None = None,
        delegation_id: str | None,
        scopes: tuple[str, ...] = ("scope:standard",),
    ) -> None:
        runtime_owner = runtime_agent or agent
        runtime = inventory.runtimes[(runtime_owner, account_variant)]
        credential = inventory.credentials[(agent, credential_variant)]
        capability = inventory.capabilities[
            (
                agent,
                capability_tenant or _tenant(inventory, agent, account_variant),
                selected.atom.authorization_target_id,
                selected.atom.action,
            )
        ]
        account = inventory.accounts[(agent, account_variant)]
        mapping = HumanSubjectAgentContextV1(
            enterprise_subject_id=selected.atom.subject_id,
            human_principal_id=human,
            agent_principal_id=agent,
            agent_account_id=account.id,
            runtime_id=runtime.id,
            delegation_id=delegation_id,
        )
        _append_action(
            events,
            evidence,
            kind=kind,
            tick=tick,
            selected=selected,
            mapping=mapping,
            credential_id=credential.id,
            capability_id=capability.id,
            scopes=scopes,
        )

    active_agent_delegation = _find_delegation(
        inventory,
        human=primary_human,
        agent=primary_agent,
        selected=human_allow,
    )
    denied_human_delegation = _find_delegation(
        inventory,
        human=primary_human,
        agent=primary_agent,
        selected=human_deny,
    )
    owner_delegation = _find_delegation(
        inventory,
        human=primary_human,
        agent=agent_deny.atom.subject_id,
        selected=agent_deny,
    )
    add_agent_case(
        kind="valid-agent",
        tick=10,
        selected=agent_allow,
        agent=primary_agent,
    )
    add_agent_case(
        kind="enterprise-denied-agent",
        tick=11,
        selected=agent_deny,
        agent=agent_deny.atom.subject_id,
    )
    add_agent_case(
        kind="human-authority-not-unioned",
        tick=12,
        selected=agent_deny,
        agent=agent_deny.atom.subject_id,
        owner_human=primary_human,
        provenance_delegation_id=owner_delegation.id,
    )
    wrong_runtime_agent = other_agent if primary_agent != other_agent else primary_agent
    add_agent_case(
        kind="wrong-runtime-agent",
        tick=13,
        selected=agent_allow,
        agent=primary_agent,
        runtime_agent=wrong_runtime_agent,
        credential_variant="wrong_runtime",
    )
    add_agent_case(
        kind="wrong-subject-agent",
        tick=29,
        selected=agent_allow,
        agent=primary_agent,
        enterprise_subject_id=other_agent,
    )
    add_agent_case(
        kind="invalid-credential-agent",
        tick=14,
        selected=agent_allow,
        agent=primary_agent,
        credential_variant="revoked",
    )
    add_agent_case(
        kind="shared-credential-agent",
        tick=30,
        selected=agent_allow,
        agent=primary_agent,
        credential_agent=other_agent,
    )
    add_agent_case(
        kind="wrong-scope-agent",
        tick=15,
        selected=agent_allow,
        agent=primary_agent,
        scopes=("scope:restricted",),
    )
    add_agent_case(
        kind="cross-tenant-agent",
        tick=16,
        selected=agent_allow,
        agent=primary_agent,
        account_variant="cross_tenant",
        credential_variant="cross_tenant",
        capability_tenant=inventory.external_tenant_id,
    )
    add_agent_case(
        kind="suspended-agent-account",
        tick=17,
        selected=agent_allow,
        agent=primary_agent,
        account_variant="suspended",
        credential_variant="suspended",
    )
    add_human_case(
        kind="valid-human-context",
        tick=18,
        selected=human_allow,
        human=primary_human,
        agent=primary_agent,
        delegation_id=active_agent_delegation.id,
    )
    add_human_case(
        kind="enterprise-denied-human",
        tick=19,
        selected=human_deny,
        human=primary_human,
        agent=primary_agent,
        delegation_id=denied_human_delegation.id,
    )
    wrong_agent_capability = inventory.capabilities[
        (
            other_agent,
            _tenant(inventory, other_agent, "active"),
            human_allow.atom.authorization_target_id,
            human_allow.atom.action,
        )
    ]
    wrong_agent_delegation = _delegation(
        "wrong-agent",
        _tenant(inventory, primary_agent, "active"),
        primary_human,
        primary_agent,
        inventory.accounts[(primary_agent, "active")].id,
        wrong_agent_capability.id,
    )
    inventory.delegations[wrong_agent_delegation.id] = wrong_agent_delegation
    add_human_case(
        kind="same-human-different-agent",
        tick=20,
        selected=human_allow,
        human=primary_human,
        agent=other_agent,
        delegation_id=wrong_agent_delegation.id,
    )
    wrong_human_delegation = active_agent_delegation
    add_human_case(
        kind="same-agent-different-human",
        tick=21,
        selected=other_human_allow,
        human=other_human,
        agent=primary_agent,
        delegation_id=wrong_human_delegation.id,
    )
    add_human_case(
        kind="missing-delegation",
        tick=22,
        selected=human_allow,
        human=primary_human,
        agent=primary_agent,
        delegation_id=None,
    )
    add_human_case(
        kind="revoked-delegation",
        tick=23,
        selected=human_allow,
        human=primary_human,
        agent=primary_agent,
        delegation_id=inventory.revoked_delegation_id,
    )
    add_human_case(
        kind="wrong-runtime-human",
        tick=24,
        selected=human_allow,
        human=primary_human,
        agent=primary_agent,
        runtime_agent=other_agent,
        credential_variant="wrong_runtime",
        delegation_id=active_agent_delegation.id,
    )
    add_human_case(
        kind="wrong-scope-human",
        tick=25,
        selected=human_allow,
        human=primary_human,
        agent=primary_agent,
        delegation_id=active_agent_delegation.id,
        scopes=("scope:restricted",),
    )
    cross_capability = inventory.capabilities[
        (
            primary_agent,
            inventory.external_tenant_id,
            human_allow.atom.authorization_target_id,
            human_allow.atom.action,
        )
    ]
    cross_delegation = _delegation(
        "cross-tenant",
        inventory.external_tenant_id,
        primary_human,
        primary_agent,
        inventory.accounts[(primary_agent, "cross_tenant")].id,
        cross_capability.id,
    )
    inventory.delegations[cross_delegation.id] = cross_delegation
    add_human_case(
        kind="cross-tenant-human",
        tick=26,
        selected=human_allow,
        human=primary_human,
        agent=primary_agent,
        account_variant="cross_tenant",
        credential_variant="cross_tenant",
        capability_tenant=inventory.external_tenant_id,
        delegation_id=cross_delegation.id,
    )
    add_human_case(
        kind="evidence-discarded",
        tick=27,
        selected=human_allow,
        human=primary_human,
        agent=primary_agent,
        delegation_id=active_agent_delegation.id,
    )
    evidence_case_id = stable_enterprise_agentic_id(
        "case",
        "evidence-discarded",
        human_allow.cell.cell_id,
        primary_human,
        primary_agent,
    )
    discarded_ref = stable_enterprise_agentic_id("evidence", evidence_case_id)
    events.extend(
        (
            EnterpriseAgenticEventV1(
                id=stable_enterprise_agentic_id(
                    "event", "evidence-discarded", discarded_ref
                ),
                tick=28,
                payload=EnterpriseAgenticEvidenceDiscardedV1(
                    evidence_refs=(discarded_ref,)
                ),
            ),
            EnterpriseAgenticEventV1(
                id=stable_enterprise_agentic_id("event", "audit", "smoke"),
                tick=40,
                payload=EnterpriseAgenticAuditPerformedV1(
                    audit_id=stable_enterprise_agentic_id("audit", "smoke")
                ),
            ),
        )
    )
    snapshot = EnterpriseAgenticSnapshotV1(
        accounts=tuple(inventory.accounts.values()),
        runtimes=tuple(inventory.runtimes.values()),
        credentials=tuple(inventory.credentials.values()),
        capabilities=tuple(inventory.capabilities.values()),
        delegations=tuple(inventory.delegations.values()),
        initial_evidence_refs=tuple(evidence),
    )
    return snapshot, tuple(sorted(events, key=lambda item: (item.tick, item.id)))


def _append_action(
    events: list[EnterpriseAgenticEventV1],
    evidence: list[str],
    *,
    kind: str,
    tick: int,
    selected: _CellSelection,
    mapping: AgentAsPrincipalV1 | HumanSubjectAgentContextV1,
    credential_id: str,
    capability_id: str,
    scopes: tuple[str, ...],
) -> None:
    case_id = stable_enterprise_agentic_id(
        "case",
        kind,
        selected.cell.cell_id,
        mapping.enterprise_subject_id,
        mapping.agent_principal_id,
    )
    evidence_ref = stable_enterprise_agentic_id("evidence", case_id)
    evidence.append(evidence_ref)
    events.append(
        EnterpriseAgenticEventV1(
            id=stable_enterprise_agentic_id("event", "action", case_id),
            tick=tick,
            payload=EnterpriseAgenticActionAttemptedV1(
                attempt=EnterpriseAgenticActionAttemptV1(
                    case_id=case_id,
                    access_request_id=selected.request_id,
                    cell_id=selected.cell.cell_id,
                    access_atom_id=selected.atom.access_atom_id,
                    mapping=mapping,
                    credential_id=credential_id,
                    capability_id=capability_id,
                    authorization_target_id=selected.atom.authorization_target_id,
                    action=selected.atom.action,
                    requested_scopes=scopes,
                    evidence_refs=(evidence_ref,),
                )
            ),
        )
    )


def _capability(
    agent_id: str, tenant_id: str, target_id: str, action: str
) -> EnterpriseAgentCapabilityV1:
    return EnterpriseAgentCapabilityV1(
        id=stable_enterprise_agentic_id(
            "capability", agent_id, tenant_id, target_id, action
        ),
        tenant_id=tenant_id,
        agent_principal_id=agent_id,
        authorization_target_ids=(target_id,),
        actions=(action,),
        scopes=("scope:standard",),
    )


def _delegation(
    variant: str,
    tenant_id: str,
    human_id: str,
    agent_id: str,
    account_id: str,
    capability_id: str,
) -> EnterpriseAgentDelegationV1:
    return EnterpriseAgentDelegationV1(
        id=stable_enterprise_agentic_id(
            "delegation",
            variant,
            tenant_id,
            human_id,
            agent_id,
            account_id,
            capability_id,
        ),
        tenant_id=tenant_id,
        human_principal_id=human_id,
        agent_principal_id=agent_id,
        agent_account_id=account_id,
        capability_id=capability_id,
        valid_from_tick=0,
        valid_until_tick=100,
    )


def _find_delegation(
    inventory: _OverlayInventory,
    *,
    human: str,
    agent: str,
    selected: _CellSelection,
) -> EnterpriseAgentDelegationV1:
    capability = inventory.capabilities[
        (
            agent,
            _tenant(inventory, agent, "active"),
            selected.atom.authorization_target_id,
            selected.atom.action,
        )
    ]
    return next(
        item
        for item in inventory.delegations.values()
        if item.human_principal_id == human
        and item.agent_principal_id == agent
        and item.agent_account_id == inventory.accounts[(agent, "active")].id
        and item.capability_id == capability.id
        and item.id != inventory.revoked_delegation_id
    )


def _tenant(inventory: _OverlayInventory, agent: str, variant: str) -> str:
    return inventory.accounts[(agent, variant)].tenant_id


def _select_cell(
    authorization: ReferenceEnterpriseAuthorizationInputsV1,
    *,
    subject_id: str,
    decision: AuthorizationDecision,
    target_id: str | None = None,
    action: str | None = None,
) -> _CellSelection:
    universe = authorization.rbac.universe_result.public_universe
    corpus = authorization.rbac.corpus_result.public_corpus
    atoms = {item.access_atom_id: item for item in universe.access_atoms}
    corpus_cells = {item.cell_id: item for item in corpus.evaluation_cells}
    requests = {item.cell_id: item.access_request_id for item in corpus.access_requests}
    candidates: list[_CellSelection] = []
    for cell in authorization.access_state.cells:
        atom = atoms[corpus_cells[cell.cell_id].access_atom_id]
        if (
            atom.subject_id == subject_id
            and cell.final_decision is decision
            and (target_id is None or atom.authorization_target_id == target_id)
            and (action is None or atom.action == action)
        ):
            candidates.append(
                _CellSelection(cell=cell, atom=atom, request_id=requests[cell.cell_id])
            )
    if not candidates:
        raise RuntimeError("reference enterprise-agentic cell selection is empty")
    return min(candidates, key=lambda item: item.cell.cell_id)


def _select_any_agent_denial(
    authorization: ReferenceEnterpriseAuthorizationInputsV1, agents: set[str]
) -> _CellSelection:
    selections = tuple(
        _select_cell(
            authorization,
            subject_id=agent,
            decision=AuthorizationDecision.DENY,
        )
        for agent in sorted(agents)
        if _has_decision(agent, AuthorizationDecision.DENY, authorization)
    )
    return min(selections, key=lambda item: item.cell.cell_id)


def _has_both_decisions(
    subject_id: str, authorization: ReferenceEnterpriseAuthorizationInputsV1
) -> bool:
    return all(
        _has_decision(subject_id, decision, authorization)
        for decision in (AuthorizationDecision.ALLOW, AuthorizationDecision.DENY)
    )


def _has_decision(
    subject_id: str,
    decision: AuthorizationDecision,
    authorization: ReferenceEnterpriseAuthorizationInputsV1,
) -> bool:
    universe = authorization.rbac.universe_result.public_universe
    corpus = authorization.rbac.corpus_result.public_corpus
    atom_by_cell = {
        cell.cell_id: next(
            atom
            for atom in universe.access_atoms
            if atom.access_atom_id == cell.access_atom_id
        )
        for cell in corpus.evaluation_cells
    }
    return any(
        atom_by_cell[cell.cell_id].subject_id == subject_id
        and cell.final_decision is decision
        for cell in authorization.access_state.cells
    )


def _require_frozen_access_inputs(universe: BaseModel, corpus: BaseModel) -> None:
    if hashlib.sha256(canonical_json_bytes(universe)).hexdigest() != (
        REFERENCE_ENTERPRISE_AGENTIC_UNIVERSE_SHA256
    ) or hashlib.sha256(canonical_json_bytes(corpus)).hexdigest() != (
        REFERENCE_ENTERPRISE_AGENTIC_CORPUS_SHA256
    ):
        raise RuntimeError("enterprise-agentic reference inputs changed")


def _require_case_inventory(
    evaluator: EnterpriseAgenticEvaluatorArtifactsV1,
) -> None:
    actual = {item.kind for item in evaluator.truth.case_labels}
    expected = set(EnterpriseAgenticCaseKind)
    if actual != expected or len(evaluator.truth.case_labels) != len(expected):
        missing = sorted(item.value for item in expected - actual)
        repeated = len(evaluator.truth.case_labels) - len(actual)
        raise RuntimeError(
            "enterprise-agentic smoke case inventory is incomplete; "
            f"missing={missing}, repeated={repeated}"
        )


__all__ = [
    "REFERENCE_ENTERPRISE_AGENTIC_CORPUS_SHA256",
    "REFERENCE_ENTERPRISE_AGENTIC_SEED",
    "REFERENCE_ENTERPRISE_AGENTIC_UNIVERSE_SHA256",
    "ReferenceEnterpriseAgenticV1",
    "reference_enterprise_agentic",
]
