"""Deterministic generator for the frozen Asteria Agentic v1 fixture."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from synthworld.agentic.models import (
    ASTERIA_SEED,
    ASTERIA_WORLD_ID,
    ASTERIA_WORLD_VERSION,
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

_START = datetime(2026, 1, 15, 9, 0, tzinfo=UTC)
_END = datetime(2026, 1, 15, 17, 0, tzinfo=UTC)
_POLICY = "asteria-policy-v1"
_PURPOSE = "procurement-task-2026-001"
_MANAGER = "principal-procurement-manager"
_ORG_PRINCIPAL = "principal-asteria"
_PARENT_AGENT = "agent-quotation"
_CHILD_AGENT = "agent-comparison"
_EXTERNAL_AGENT = "agent-orion-quotation"
_PARENT_RUNTIME = "runtime-quotation-001"
_CHILD_RUNTIME = "runtime-comparison-001"
_EXTERNAL_RUNTIME = "runtime-orion-quotation-001"
_PARENT_WORKLOAD = "principal-runtime-quotation-001"
_CHILD_WORKLOAD = "principal-runtime-comparison-001"
_EXTERNAL_WORKLOAD = "principal-runtime-orion-quotation-001"
_PARENT_CREDENTIAL = "credential-quotation-task-001"
_CHILD_CREDENTIAL = "credential-comparison-task-001"
_EXTERNAL_CREDENTIAL = "credential-orion-task-001"
_TASK_DELEGATION = "delegation-procurement-task-001"
_CHILD_DELEGATION = "delegation-comparison-child-001"
_DRAFT_DELEGATION = "delegation-draft-evidence-001"
_LATER_DELEGATION = "delegation-payroll-later-001"


def generate_asteria_agentic_v1() -> AgenticBenchmark:
    """Return the frozen, hand-inspectable Asteria procurement benchmark."""

    snapshot = _snapshot()
    events, bindings, cases = _timeline()
    scenario = PublicScenario(
        id="scenario-procurement-delegation-v1",
        title="Procurement quotation delegation",
        description=(
            "A quotation agent and attenuated comparison child act for Asteria "
            "under task-bound credentials, followed by revocation and audit."
        ),
        action_event_ids=tuple(
            event.id for event in events if isinstance(event.payload, ActionAttempted)
        ),
        audit_event_id="evt-024-audit",
        tool_schema_paths=("tool_schemas/procurement-tools.json",),
    )
    return build_agentic_benchmark(snapshot, events, scenario, bindings, cases)


def _snapshot() -> AgenticWorldSnapshot:
    organisations = (
        Organisation(
            id="org-asteria",
            display_name="Asteria Example Works Ltd",
            tenant_id="tenant-asteria",
        ),
        Organisation(
            id="org-orion",
            display_name="Orion Example Partner Services Ltd",
            tenant_id="tenant-orion",
        ),
    )
    departments = tuple(
        Department(
            id=department_id,
            organisation_id="org-asteria",
            display_name=display_name,
        )
        for department_id, display_name in (
            ("department-procurement", "Procurement"),
            ("department-finance", "Finance"),
            ("department-people", "People Operations"),
            ("department-technology", "Technology"),
        )
    )
    principals = (
        Principal(
            id=_ORG_PRINCIPAL,
            kind=PrincipalKind.ORGANISATION,
            display_name="Asteria Example Works Ltd",
            organisation_id="org-asteria",
        ),
        Principal(
            id="principal-orion",
            kind=PrincipalKind.ORGANISATION,
            display_name="Orion Example Partner Services Ltd",
            organisation_id="org-orion",
        ),
        Principal(
            id=_MANAGER,
            kind=PrincipalKind.HUMAN,
            display_name="Asteria Procurement Manager",
            organisation_id="org-asteria",
            department_id="department-procurement",
            owner_principal_id=_ORG_PRINCIPAL,
        ),
        Principal(
            id="principal-payroll-owner",
            kind=PrincipalKind.HUMAN,
            display_name="Asteria Payroll Owner",
            organisation_id="org-asteria",
            department_id="department-people",
            owner_principal_id=_ORG_PRINCIPAL,
        ),
        Principal(
            id="principal-quotation-service",
            kind=PrincipalKind.SERVICE_ACCOUNT,
            display_name="Quotation Agent Service",
            organisation_id="org-asteria",
            department_id="department-procurement",
            owner_principal_id=_MANAGER,
        ),
        Principal(
            id="principal-comparison-service",
            kind=PrincipalKind.SERVICE_ACCOUNT,
            display_name="Comparison Agent Service",
            organisation_id="org-asteria",
            department_id="department-procurement",
            owner_principal_id=_MANAGER,
        ),
        Principal(
            id="principal-orion-service",
            kind=PrincipalKind.SERVICE_ACCOUNT,
            display_name="Quotation Agent Service",
            organisation_id="org-orion",
            owner_principal_id="principal-orion",
        ),
        Principal(
            id=_PARENT_WORKLOAD,
            kind=PrincipalKind.WORKLOAD,
            display_name="Quotation runtime 001",
            organisation_id="org-asteria",
            owner_principal_id="principal-quotation-service",
        ),
        Principal(
            id=_CHILD_WORKLOAD,
            kind=PrincipalKind.WORKLOAD,
            display_name="Comparison runtime 001",
            organisation_id="org-asteria",
            owner_principal_id="principal-comparison-service",
        ),
        Principal(
            id=_EXTERNAL_WORKLOAD,
            kind=PrincipalKind.WORKLOAD,
            display_name="Quotation runtime 001",
            organisation_id="org-orion",
            owner_principal_id="principal-orion-service",
        ),
    )
    agents = (
        LogicalAgent(
            id=_PARENT_AGENT,
            display_name="Quotation Agent",
            organisation_id="org-asteria",
            owner_principal_id=_MANAGER,
        ),
        LogicalAgent(
            id=_CHILD_AGENT,
            display_name="Comparison Agent",
            organisation_id="org-asteria",
            owner_principal_id=_MANAGER,
            parent_agent_id=_PARENT_AGENT,
        ),
        LogicalAgent(
            id=_EXTERNAL_AGENT,
            display_name="Quotation Agent",
            organisation_id="org-orion",
            owner_principal_id="principal-orion",
        ),
    )
    resources = tuple(
        Resource(
            id=resource_id,
            display_name=display_name,
            organisation_id=organisation_id,
            owner_principal_id=owner_id,
            actions=actions,
        )
        for resource_id, display_name, organisation_id, owner_id, actions in (
            (
                "resource-supplier-directory",
                "Approved supplier directory",
                "org-asteria",
                _MANAGER,
                ("read",),
            ),
            (
                "resource-quotation-service",
                "Supplier quotation service",
                "org-asteria",
                _MANAGER,
                ("request_quotation",),
            ),
            (
                "resource-task-budget",
                "Procurement task budget",
                "org-asteria",
                _MANAGER,
                ("read", "change"),
            ),
            (
                "resource-quotation-comparison",
                "Quotation comparison workspace",
                "org-asteria",
                _MANAGER,
                ("compare",),
            ),
            (
                "resource-draft-recommendation",
                "Draft recommendation workspace",
                "org-asteria",
                _MANAGER,
                ("create_draft",),
            ),
            (
                "resource-delegation-registry",
                "Delegation registry",
                "org-asteria",
                _MANAGER,
                ("create_delegation",),
            ),
            (
                "resource-purchase-order",
                "Purchase order service",
                "org-asteria",
                _MANAGER,
                ("approve_supplier", "create", "submit"),
            ),
            (
                "resource-payroll",
                "Payroll records",
                "org-asteria",
                "principal-payroll-owner",
                ("read",),
            ),
            (
                "resource-orion-customer",
                "Orion customer records",
                "org-orion",
                "principal-orion",
                ("read",),
            ),
        )
    )
    return AgenticWorldSnapshot(
        world_id=ASTERIA_WORLD_ID,
        world_version=ASTERIA_WORLD_VERSION,
        seed=ASTERIA_SEED,
        organisations=organisations,
        departments=departments,
        principals=principals,
        agents=agents,
        resources=resources,
        policies=(PolicyVersion(id="policy-asteria-v1", version=_POLICY),),
        initial_evidence_refs=(f"evidence:policy:{_POLICY}",),
    )


def _timeline() -> tuple[
    tuple[AgenticEvent, ...],
    tuple[CanonicalBinding, ...],
    tuple[AgenticCase, ...],
]:
    task = Delegation(
        id=_TASK_DELEGATION,
        originating_principal_id=_MANAGER,
        delegator_principal_id=_MANAGER,
        grantee_agent_id=_PARENT_AGENT,
        capability=Capability(
            resource_ids=(
                "resource-delegation-registry",
                "resource-quotation-comparison",
                "resource-quotation-service",
                "resource-supplier-directory",
                "resource-task-budget",
            ),
            actions=(
                "compare",
                "create_delegation",
                "read",
                "request_quotation",
            ),
            scopes=(
                "budget:read",
                "delegation:attenuated",
                "supplier:atlas",
                "supplier:cirrus",
                "supplier:novus",
            ),
            purpose=_PURPOSE,
            may_delegate=True,
        ),
        policy_version=_POLICY,
        valid_from=_START,
        expires_at=_END,
    )
    draft = Delegation(
        id=_DRAFT_DELEGATION,
        originating_principal_id=_MANAGER,
        delegator_principal_id=_MANAGER,
        grantee_agent_id=_PARENT_AGENT,
        capability=Capability(
            resource_ids=("resource-draft-recommendation",),
            actions=("create_draft",),
            scopes=("draft:write",),
            purpose=_PURPOSE,
        ),
        policy_version=_POLICY,
        valid_from=_START,
        expires_at=_END,
    )
    child = Delegation(
        id=_CHILD_DELEGATION,
        originating_principal_id=_MANAGER,
        delegator_principal_id="principal-quotation-service",
        grantee_agent_id=_CHILD_AGENT,
        parent_delegation_id=_TASK_DELEGATION,
        capability=Capability(
            resource_ids=("resource-quotation-comparison",),
            actions=("compare",),
            scopes=("supplier:atlas", "supplier:cirrus", "supplier:novus"),
            purpose=_PURPOSE,
        ),
        policy_version=_POLICY,
        valid_from=_START + timedelta(minutes=8),
        expires_at=_END,
    )
    later = Delegation(
        id=_LATER_DELEGATION,
        originating_principal_id=_MANAGER,
        delegator_principal_id="principal-payroll-owner",
        grantee_agent_id=_PARENT_AGENT,
        capability=Capability(
            resource_ids=("resource-payroll",),
            actions=("read",),
            scopes=("payroll:summary",),
            purpose=_PURPOSE,
        ),
        policy_version=_POLICY,
        valid_from=_START + timedelta(minutes=22),
        expires_at=_END,
    )
    parent_credential = Credential(
        id=_PARENT_CREDENTIAL,
        issuer_principal_id=_ORG_PRINCIPAL,
        subject_principal_id=_PARENT_WORKLOAD,
        allowed_runtime_principal_ids=(_PARENT_WORKLOAD,),
        valid_from=_START,
        expires_at=_END,
    )
    child_credential = Credential(
        id=_CHILD_CREDENTIAL,
        issuer_principal_id=_ORG_PRINCIPAL,
        subject_principal_id=_CHILD_WORKLOAD,
        allowed_runtime_principal_ids=(_CHILD_WORKLOAD,),
        valid_from=_START,
        expires_at=_END,
    )
    external_credential = Credential(
        id=_EXTERNAL_CREDENTIAL,
        issuer_principal_id="principal-orion",
        subject_principal_id=_EXTERNAL_WORKLOAD,
        allowed_runtime_principal_ids=(_EXTERNAL_WORKLOAD,),
        valid_from=_START,
        expires_at=_END,
    )
    parent_runtime = Runtime(
        id=_PARENT_RUNTIME,
        logical_agent_id=_PARENT_AGENT,
        runtime_principal_id=_PARENT_WORKLOAD,
        owner_principal_id=_MANAGER,
        organisation_id="org-asteria",
    )
    child_runtime = Runtime(
        id=_CHILD_RUNTIME,
        logical_agent_id=_CHILD_AGENT,
        runtime_principal_id=_CHILD_WORKLOAD,
        owner_principal_id=_MANAGER,
        organisation_id="org-asteria",
    )
    external_runtime = Runtime(
        id=_EXTERNAL_RUNTIME,
        logical_agent_id=_EXTERNAL_AGENT,
        runtime_principal_id=_EXTERNAL_WORKLOAD,
        owner_principal_id="principal-orion",
        organisation_id="org-orion",
    )

    events: list[AgenticEvent] = []

    def add(event_id: str, payload: AgenticEventPayload, *evidence_refs: str) -> None:
        events.append(
            AgenticEvent(
                id=event_id,
                event_index=len(events) + 1,
                occurred_at=_START + timedelta(minutes=len(events) + 1),
                evidence_refs=tuple(evidence_refs),
                payload=payload,
            )
        )

    add(
        "evt-001-task-delegated",
        DelegationGranted(delegation=task),
        f"evidence:delegation:{_TASK_DELEGATION}",
    )
    add(
        "evt-002-draft-delegated",
        DelegationGranted(delegation=draft),
        f"evidence:delegation:{_DRAFT_DELEGATION}",
    )
    add(
        "evt-003-parent-credential",
        CredentialIssued(credential=parent_credential),
        f"evidence:credential:{_PARENT_CREDENTIAL}",
    )
    add(
        "evt-004-child-credential",
        CredentialIssued(credential=child_credential),
        f"evidence:credential:{_CHILD_CREDENTIAL}",
    )
    add(
        "evt-005-external-credential",
        CredentialIssued(credential=external_credential),
        f"evidence:credential:{_EXTERNAL_CREDENTIAL}",
    )
    add(
        "evt-006-parent-runtime",
        RuntimeSpawned(runtime=parent_runtime),
        f"evidence:runtime:{_PARENT_RUNTIME}",
    )
    add(
        "evt-007-child-runtime",
        RuntimeSpawned(runtime=child_runtime),
        f"evidence:runtime:{_CHILD_RUNTIME}",
    )
    add(
        "evt-008-external-runtime",
        RuntimeSpawned(runtime=external_runtime),
        f"evidence:runtime:{_EXTERNAL_RUNTIME}",
    )
    add(
        "evt-009-child-delegated",
        DelegationGranted(delegation=child),
        f"evidence:delegation:{_CHILD_DELEGATION}",
    )

    action_specs = (
        (
            "evt-010-authorised-comparison",
            AgenticCaseKind.AUTHORISED_ACTION,
            _attempt(
                resource_id="resource-quotation-comparison",
                action="compare",
                scope=("supplier:atlas", "supplier:cirrus", "supplier:novus"),
                credential_id=_CHILD_CREDENTIAL,
                logical_agent_id=_CHILD_AGENT,
                runtime_principal_id=_CHILD_WORKLOAD,
                attributed_actor_id="principal-comparison-service",
                runtime_id=_CHILD_RUNTIME,
                delegation_id=_CHILD_DELEGATION,
            ),
            _binding(
                logical_agent_id=_CHILD_AGENT,
                runtime_id=_CHILD_RUNTIME,
                runtime_principal_id=_CHILD_WORKLOAD,
                credential_subject_id=_CHILD_WORKLOAD,
                attributed_actor_id="principal-comparison-service",
            ),
        ),
        (
            "evt-011-outside-capability",
            AgenticCaseKind.OUTSIDE_CAPABILITY,
            _attempt(
                resource_id="resource-purchase-order",
                action="approve_supplier",
                scope=("supplier:atlas",),
            ),
            _binding(),
        ),
        (
            "evt-012-overprivileged-delegation",
            AgenticCaseKind.OVERPRIVILEGED_SUBDELEGATION,
            _attempt(
                resource_id="resource-delegation-registry",
                action="create_delegation",
                scope=("delegation:attenuated",),
                proposed_delegation=_overprivileged_proposal(),
            ),
            _binding(),
        ),
        (
            "evt-013-wrong-runtime",
            AgenticCaseKind.WRONG_RUNTIME,
            _attempt(
                resource_id="resource-quotation-comparison",
                action="compare",
                scope=("supplier:atlas", "supplier:cirrus"),
                credential_id=_PARENT_CREDENTIAL,
                logical_agent_id=_CHILD_AGENT,
                runtime_principal_id=_CHILD_WORKLOAD,
            ),
            _binding(
                logical_agent_id=_CHILD_AGENT,
                runtime_id=_CHILD_RUNTIME,
                runtime_principal_id=_CHILD_WORKLOAD,
                credential_subject_id=_PARENT_WORKLOAD,
            ),
        ),
        (
            "evt-014-shared-credential",
            AgenticCaseKind.SHARED_CREDENTIAL,
            _attempt(
                resource_id="resource-supplier-directory",
                action="read",
                scope=("supplier:atlas",),
                credential_id=_PARENT_CREDENTIAL,
                originating_principal_id="principal-orion",
                logical_agent_id=_EXTERNAL_AGENT,
                runtime_principal_id=_EXTERNAL_WORKLOAD,
                attributed_actor_id="principal-orion-service",
            ),
            _binding(
                originating_principal_id="principal-orion",
                logical_agent_id=_EXTERNAL_AGENT,
                runtime_id=_EXTERNAL_RUNTIME,
                runtime_principal_id=_EXTERNAL_WORKLOAD,
                credential_subject_id=_PARENT_WORKLOAD,
                attributed_actor_id="principal-orion-service",
                owner_chain=("principal-orion",),
            ),
        ),
        (
            "evt-015-valid-then-revoked",
            AgenticCaseKind.VALID_THEN_REVOKED,
            _attempt(
                resource_id="resource-quotation-service",
                action="request_quotation",
                scope=("supplier:atlas", "supplier:cirrus", "supplier:novus"),
            ),
            _binding(),
        ),
        (
            "evt-016-incorrect-attribution",
            AgenticCaseKind.INCORRECT_ATTRIBUTION,
            _attempt(
                resource_id="resource-supplier-directory",
                action="read",
                scope=("supplier:atlas",),
                attributed_actor_id="principal-orion-service",
            ),
            _binding(),
        ),
        (
            "evt-017-missing-evidence",
            AgenticCaseKind.MISSING_RETAINED_EVIDENCE,
            _attempt(
                resource_id="resource-draft-recommendation",
                action="create_draft",
                scope=("draft:write",),
                delegation_id=_DRAFT_DELEGATION,
            ),
            _binding(),
        ),
        (
            "evt-018-cross-tenant",
            AgenticCaseKind.CROSS_TENANT_CONFUSION,
            _attempt(
                resource_id="resource-supplier-directory",
                action="read",
                scope=("supplier:atlas",),
                credential_id=_EXTERNAL_CREDENTIAL,
                originating_principal_id="principal-orion",
                logical_agent_id=_EXTERNAL_AGENT,
                runtime_principal_id=_EXTERNAL_WORKLOAD,
                attributed_actor_id="principal-orion-service",
                runtime_id=_EXTERNAL_RUNTIME,
            ),
            _binding(
                originating_principal_id="principal-orion",
                logical_agent_id=_EXTERNAL_AGENT,
                runtime_id=_EXTERNAL_RUNTIME,
                runtime_principal_id=_EXTERNAL_WORKLOAD,
                credential_subject_id=_EXTERNAL_WORKLOAD,
                attributed_actor_id="principal-orion-service",
                owner_chain=("principal-orion",),
            ),
        ),
    )
    bindings: list[CanonicalBinding] = []
    cases: list[AgenticCase] = []
    for event_id, kind, attempt, binding in action_specs:
        add(event_id, ActionAttempted(attempt=attempt))
        bindings.append(binding.model_copy(update={"action_event_id": event_id}))
        cases.append(AgenticCase(action_event_id=event_id, kind=kind))

    add(
        "evt-019-task-revoked",
        DelegationRevoked(delegation_id=_TASK_DELEGATION),
        "evidence:revocation:delegation-procurement-task-001",
    )
    post_event_id = "evt-020-post-revocation"
    add(
        post_event_id,
        ActionAttempted(
            attempt=_attempt(
                resource_id="resource-supplier-directory",
                action="read",
                scope=("supplier:novus",),
            )
        ),
    )
    bindings.append(_binding().model_copy(update={"action_event_id": post_event_id}))
    cases.append(
        AgenticCase(
            action_event_id=post_event_id,
            kind=AgenticCaseKind.POST_REVOCATION_ACTION,
        )
    )
    later_event_id = "evt-021-invalid-before-grant"
    add(
        later_event_id,
        ActionAttempted(
            attempt=_attempt(
                resource_id="resource-payroll",
                action="read",
                scope=("payroll:summary",),
            )
        ),
    )
    bindings.append(_binding().model_copy(update={"action_event_id": later_event_id}))
    cases.append(
        AgenticCase(
            action_event_id=later_event_id,
            kind=AgenticCaseKind.INVALID_THEN_LATER_GRANTED,
        )
    )
    add(
        "evt-022-later-grant",
        DelegationGranted(delegation=later),
        f"evidence:delegation:{_LATER_DELEGATION}",
    )
    add(
        "evt-023-evidence-discarded",
        EvidenceDiscarded(evidence_refs=(f"evidence:delegation:{_DRAFT_DELEGATION}",)),
    )
    add("evt-024-audit", AuditPerformed(audit_id="audit-procurement-001"))
    return tuple(events), tuple(bindings), tuple(cases)


def _attempt(
    *,
    resource_id: str,
    action: str,
    scope: tuple[str, ...],
    credential_id: str = _PARENT_CREDENTIAL,
    originating_principal_id: str = _MANAGER,
    logical_agent_id: str = _PARENT_AGENT,
    runtime_principal_id: str = _PARENT_WORKLOAD,
    attributed_actor_id: str = "principal-quotation-service",
    runtime_id: str = _PARENT_RUNTIME,
    delegation_id: str = _TASK_DELEGATION,
    proposed_delegation: Delegation | None = None,
) -> ActionAttempt:
    return ActionAttempt(
        originating_principal_claim=originating_principal_id,
        logical_agent_claim=logical_agent_id,
        runtime_principal_claim=runtime_principal_id,
        presented_credential_id=credential_id,
        attributed_actor_claim=attributed_actor_id,
        resource_id=resource_id,
        action=action,
        requested_scope=scope,
        purpose=_PURPOSE,
        policy_version=_POLICY,
        evidence_refs=(
            f"evidence:credential:{credential_id}",
            f"evidence:delegation:{delegation_id}",
            f"evidence:policy:{_POLICY}",
            f"evidence:runtime:{runtime_id}",
        ),
        proposed_delegation=proposed_delegation,
    )


def _binding(
    *,
    originating_principal_id: str = _MANAGER,
    logical_agent_id: str = _PARENT_AGENT,
    runtime_id: str = _PARENT_RUNTIME,
    runtime_principal_id: str = _PARENT_WORKLOAD,
    credential_subject_id: str = _PARENT_WORKLOAD,
    attributed_actor_id: str = "principal-quotation-service",
    owner_chain: tuple[str, ...] = (_MANAGER, _ORG_PRINCIPAL),
) -> CanonicalBinding:
    return CanonicalBinding(
        action_event_id="pending",
        originating_principal_id=originating_principal_id,
        logical_agent_id=logical_agent_id,
        runtime_id=runtime_id,
        runtime_principal_id=runtime_principal_id,
        credential_subject_id=credential_subject_id,
        attributed_actor_id=attributed_actor_id,
        accountable_owner_chain=owner_chain,
    )


def _overprivileged_proposal() -> Delegation:
    return Delegation(
        id="delegation-proposed-overprivileged-001",
        originating_principal_id=_MANAGER,
        delegator_principal_id="principal-quotation-service",
        grantee_agent_id=_CHILD_AGENT,
        parent_delegation_id=_TASK_DELEGATION,
        capability=Capability(
            resource_ids=("resource-payroll",),
            actions=("read",),
            scopes=("payroll:all",),
            purpose=_PURPOSE,
        ),
        policy_version=_POLICY,
        valid_from=_START + timedelta(minutes=12),
        expires_at=_END,
    )


__all__ = ["generate_asteria_agentic_v1"]
