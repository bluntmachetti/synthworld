"""Small safely fictional reference inputs for the native directory/RBAC slice."""

from __future__ import annotations

from dataclasses import dataclass

from synthworld.enterprise.canonical import (
    ENTERPRISE_ROLE_NAMESPACE_V1,
    blueprint_namespace_uuid,
    canonical_json_bytes,
    stable_enterprise_id,
    synthetic_digest,
)
from synthworld.enterprise.compiler import compile_enterprise_identity_access_universe
from synthworld.enterprise.models import (
    AccountObservationV1,
    AdministrativeState,
    DirectEntitlementV1,
    EnterpriseIdentityAccessCompileResultV1,
    EnterpriseIdentityAccessImportV1,
    GroupRoleAssignmentV1,
    PrincipalKind,
)
from synthworld.enterprise.rbac.common import (
    ActivationOutcome,
    ApprovedExceptionReason,
    AssignmentTargetKind,
    BirthrightConditionOperator,
    EmploymentType,
    EvaluationCaseTargetKind,
)
from synthworld.enterprise.rbac.corpus import compile_enterprise_evaluation_corpus
from synthworld.enterprise.rbac.corpus_models import (
    AccessEvaluationCellTemplateV1,
    AuthorizationSessionSlotTemplateV1,
    EnterpriseAccessRequestTemplateV1,
    EnterpriseContextTemplateV1,
    EnterpriseEvaluationCorpusCompileResultV1,
    EnterpriseEvaluationCorpusConfigV1,
    EnterpriseEvaluatorCaseTemplateV1,
    RoleActivationRequestTemplateV1,
)
from synthworld.enterprise.rbac.kernel import compile_enterprise_directory_rbac_kernel
from synthworld.enterprise.rbac.models import (
    AccountKindIsV1,
    ApprovedAccessExceptionV1,
    BirthrightAssignmentV1,
    BirthrightConditionV1,
    BirthrightRuleV1,
    DynamicSodConstraintV1,
    EmploymentTypeIsV1,
    EnterpriseDirectoryRbacIntentOverlayV1,
    EnterpriseDirectoryRbacKernelV1,
    EnterpriseRbacSessionStateInputV1,
    IntendedGroupNestingV1,
    IntendedGroupRoleAssignmentV1,
    IntendedRoleGrantV1,
    IntendedRoleHierarchyV1,
    IntendedSubjectGroupMembershipV1,
    IntendedSubjectRoleAssignmentV1,
    ObservedRbacSessionStateV1,
    PrincipalKindIsV1,
    StaticSodConstraintV1,
    TenantIsV1,
    UnitIsV1,
)
from synthworld.enterprise.reference import reference_enterprise_identity_access_import

REFERENCE_ENTERPRISE_SEED = 20260804


@dataclass(frozen=True, slots=True)
class ReferenceEnterpriseRbacInputsV1:
    source_import: EnterpriseIdentityAccessImportV1
    universe_result: EnterpriseIdentityAccessCompileResultV1
    corpus_result: EnterpriseEvaluationCorpusCompileResultV1
    kernel: EnterpriseDirectoryRbacKernelV1
    intent: EnterpriseDirectoryRbacIntentOverlayV1
    session_state: EnterpriseRbacSessionStateInputV1


def reference_enterprise_evaluation_corpus_config() -> (
    EnterpriseEvaluationCorpusConfigV1
):
    """Declare a fixed corpus without deriving a Cartesian product."""

    imported = reference_enterprise_identity_access_import()
    compiled = compile_enterprise_identity_access_universe(
        import_model=imported,
        seed=REFERENCE_ENTERPRISE_SEED,
    )
    universe = compiled.public_universe
    digest = synthetic_digest(canonical_json_bytes(universe))
    agent_subject = next(
        item.principal_id
        for item in universe.principals
        if item.principal_kind is PrincipalKind.AGENT
    )
    employee_subject = next(
        item.principal_id
        for item in universe.principals
        if item.principal_kind is PrincipalKind.EMPLOYEE
    )
    namespace = blueprint_namespace_uuid(imported.blueprint.id_namespace_salt)
    admin_role_id = stable_enterprise_id(
        ENTERPRISE_ROLE_NAMESPACE_V1,
        namespace,
        "tenant-main",
        "organisation-main",
        "role-api-admin",
    )
    reader_role_id = stable_enterprise_id(
        ENTERPRISE_ROLE_NAMESPACE_V1,
        namespace,
        "tenant-main",
        "organisation-main",
        "role-api-reader",
    )
    cells: list[AccessEvaluationCellTemplateV1] = []
    requests: list[EnterpriseAccessRequestTemplateV1] = []
    cases: list[EnterpriseEvaluatorCaseTemplateV1] = []
    for index, atom in enumerate(universe.access_atoms, start=1):
        cell_key = f"static-cell-{index:03d}"
        request_key = f"static-request-{index:03d}"
        cells.append(
            AccessEvaluationCellTemplateV1(
                cell_key=cell_key,
                access_atom_id=atom.access_atom_id,
                context_key="static-context",
                tick=0,
            )
        )
        requests.append(
            EnterpriseAccessRequestTemplateV1(
                request_key=request_key,
                cell_key=cell_key,
            )
        )
        cases.append(
            EnterpriseEvaluatorCaseTemplateV1(
                case_key=f"static-case-{index:03d}",
                target_kind=EvaluationCaseTargetKind.ACCESS_CELL,
                target_key=cell_key,
                labels=("directory-rbac",),
            )
        )
    session_specs = (
        ("agent", agent_subject, (admin_role_id, reader_role_id)),
        ("employee", employee_subject, (admin_role_id,)),
    )
    slots = tuple(
        AuthorizationSessionSlotTemplateV1(
            session_state_key=f"{name}-session-state",
            session_key=f"{name}-session",
            subject_id=subject_id,
            activation_tick=5,
            valid_until_tick=10,
        )
        for name, subject_id, _roles in session_specs
    )
    activations = tuple(
        RoleActivationRequestTemplateV1(
            request_key=f"{name}-activation",
            session_state_key=f"{name}-session-state",
            requested_role_ids=requested_roles,
        )
        for name, _subject_id, requested_roles in session_specs
    )
    for name, subject_id, _roles in session_specs:
        atom = next(
            item for item in universe.access_atoms if item.subject_id == subject_id
        )
        cell_key = f"{name}-session-cell"
        cells.append(
            AccessEvaluationCellTemplateV1(
                cell_key=cell_key,
                access_atom_id=atom.access_atom_id,
                context_key="static-context",
                session_state_key=f"{name}-session-state",
                tick=5,
            )
        )
        requests.append(
            EnterpriseAccessRequestTemplateV1(
                request_key=f"{name}-session-request",
                cell_key=cell_key,
            )
        )
        cases.append(
            EnterpriseEvaluatorCaseTemplateV1(
                case_key=f"{name}-session-case",
                target_kind=EvaluationCaseTargetKind.ACCESS_CELL,
                target_key=cell_key,
                labels=("activated-role", "directory-rbac"),
            )
        )
        cases.append(
            EnterpriseEvaluatorCaseTemplateV1(
                case_key=f"{name}-activation-case",
                target_kind=EvaluationCaseTargetKind.ACTIVATION_REQUEST,
                target_key=f"{name}-activation",
                labels=("activation",),
            )
        )
    expiry_atom = next(
        item
        for item in reversed(universe.access_atoms)
        if item.subject_id in {account.account_id for account in universe.accounts}
    )
    cells.append(
        AccessEvaluationCellTemplateV1(
            cell_key="expired-account-cell",
            access_atom_id=expiry_atom.access_atom_id,
            context_key="static-context",
            tick=20,
        )
    )
    requests.append(
        EnterpriseAccessRequestTemplateV1(
            request_key="expired-account-request",
            cell_key="expired-account-cell",
        )
    )
    cases.append(
        EnterpriseEvaluatorCaseTemplateV1(
            case_key="expired-account-case",
            target_kind=EvaluationCaseTargetKind.ACCESS_CELL,
            target_key="expired-account-cell",
            labels=("half-open-expiry",),
        )
    )
    return EnterpriseEvaluationCorpusConfigV1(
        identity_access_universe_digest=digest,
        contexts=(EnterpriseContextTemplateV1(context_key="static-context"),),
        session_slots=slots,
        role_activation_requests=activations,
        evaluation_cells=tuple(cells),
        access_requests=tuple(requests),
        evaluator_cases=tuple(cases),
    )


def reference_enterprise_rbac_inputs() -> ReferenceEnterpriseRbacInputsV1:
    """Return a discriminating state/intent pair over the fixed reference universe."""

    base_import = reference_enterprise_identity_access_import()
    base_result = compile_enterprise_identity_access_universe(
        import_model=base_import,
        seed=REFERENCE_ENTERPRISE_SEED,
    )
    universe = base_result.public_universe
    binding_by_account = {
        item.account_id: item.principal_id
        for item in base_result.evaluator_canonical_binding_truth.bindings
    }
    accounts = tuple(sorted(universe.accounts, key=lambda item: item.account_id))
    employee_ids = tuple(
        item.principal_id
        for item in universe.principals
        if item.principal_kind is PrincipalKind.EMPLOYEE
    )
    observations = tuple(
        AccountObservationV1(
            account_id=account.account_id,
            observed_principal_id=(
                None
                if index == 3
                else (
                    employee_ids[-1]
                    if index == 2
                    else binding_by_account[account.account_id]
                )
            ),
            administrative_state=(
                AdministrativeState.SUSPENDED
                if index == 1
                else AdministrativeState.ACTIVE
            ),
            valid_from_tick=0,
            valid_until_tick=20,
            revision_id=f"account-observation-{index + 1}",
        )
        for index, account in enumerate(accounts)
    )
    account_atoms = {
        item.subject_id: item
        for item in universe.access_atoms
        if item.subject_id in {account.account_id for account in accounts}
    }
    direct_entitlements = [
        DirectEntitlementV1(
            subject_id=account.account_id,
            authorization_target_id=account_atoms[
                account.account_id
            ].authorization_target_id,
            action=account_atoms[account.account_id].action,
            valid_from_tick=0,
            valid_until_tick=20,
            revision_id=f"account-direct-{index + 1}",
        )
        for index, account in enumerate(accounts)
    ]
    session_employee_id = next(
        item.principal_id
        for item in universe.principals
        if item.principal_kind is PrincipalKind.EMPLOYEE
    )
    redundant_employee_id = next(
        item for item in employee_ids if item != session_employee_id
    )
    redundant_atom = next(
        item
        for item in universe.access_atoms
        if item.subject_id == redundant_employee_id and item.action == "read"
    )
    direct_entitlements.append(
        DirectEntitlementV1(
            subject_id=redundant_employee_id,
            authorization_target_id=redundant_atom.authorization_target_id,
            action=redundant_atom.action,
            valid_from_tick=0,
            revision_id="redundant-employee-read",
        )
    )
    state = base_import.directory_rbac_state.model_copy(
        update={
            "account_observations": observations,
            "group_role_assignments": (
                *base_import.directory_rbac_state.group_role_assignments,
                GroupRoleAssignmentV1(
                    group_key="group-platform", role_key="role-api-reader"
                ),
            ),
            "direct_entitlements": tuple(direct_entitlements),
        }
    )
    source_import = base_import.model_copy(update={"directory_rbac_state": state})
    result = compile_enterprise_identity_access_universe(
        import_model=source_import,
        seed=REFERENCE_ENTERPRISE_SEED,
    )
    if canonical_json_bytes(result.public_universe) != canonical_json_bytes(universe):
        raise RuntimeError("PR3 reference state changed the frozen PR2 universe")
    corpus_result = compile_enterprise_evaluation_corpus(
        universe=universe,
        corpus_config=reference_enterprise_evaluation_corpus_config(),
    )
    corpus = corpus_result.public_corpus
    kernel = compile_enterprise_directory_rbac_kernel(
        import_model=source_import,
        universe=universe,
    )
    permission_by_id = {item.permission_id: item for item in universe.permissions}
    reader_role_id = next(
        item.role_id
        for item in kernel.role_grants
        if permission_by_id[item.permission_id].action == "read"
    )
    admin_role_id = next(
        item.role_id
        for item in kernel.role_grants
        if permission_by_id[item.permission_id].action == "write"
    )
    platform_group_id = kernel.group_nesting[0].child_group_id
    tenant_id = universe.tenants[0].tenant_id
    employee_atoms = tuple(
        item.access_atom_id
        for item in universe.access_atoms
        if item.subject_id in set(employee_ids) and item.action == "read"
    )
    account_atom_values = tuple(
        sorted(account_atoms.values(), key=lambda item: item.access_atom_id)
    )
    first_account_atom = account_atom_values[0]
    first_account_permission = next(
        item.permission_id
        for item in universe.permissions
        if item.authorization_target_id == first_account_atom.authorization_target_id
        and item.action == first_account_atom.action
    )
    first_agent_atom = next(
        item
        for item in universe.access_atoms
        if any(
            principal.principal_id == item.subject_id
            and principal.principal_kind is PrincipalKind.AGENT
            for principal in universe.principals
        )
    )
    employee_unit_id = next(
        item.unit_id
        for item in universe.principals
        if item.principal_kind is PrincipalKind.EMPLOYEE
    )
    intent = EnterpriseDirectoryRbacIntentOverlayV1(
        identity_access_universe_digest=synthetic_digest(
            canonical_json_bytes(universe)
        ),
        evaluation_corpus_digest=synthetic_digest(canonical_json_bytes(corpus)),
        birthright_rules=(
            BirthrightRuleV1(
                rule_id="employee-reader-birthright",
                condition=BirthrightConditionV1(
                    operator=BirthrightConditionOperator.ALL,
                    predicates=(
                        PrincipalKindIsV1(values=(PrincipalKind.EMPLOYEE,)),
                        EmploymentTypeIsV1(values=(EmploymentType.EMPLOYEE,)),
                        TenantIsV1(tenant_ids=(tenant_id,)),
                        UnitIsV1(unit_ids=(employee_unit_id,)),
                    ),
                ),
                assignments=(
                    BirthrightAssignmentV1(
                        assignment_id="employee-reader-role",
                        target_kind=AssignmentTargetKind.ROLE,
                        target_id=reader_role_id,
                        access_atom_ids=employee_atoms,
                    ),
                ),
            ),
            BirthrightRuleV1(
                rule_id="one-workforce-account-birthright",
                condition=BirthrightConditionV1(
                    operator=BirthrightConditionOperator.ALL,
                    predicates=(AccountKindIsV1(values=(accounts[0].account_kind,)),),
                ),
                assignments=(
                    BirthrightAssignmentV1(
                        assignment_id="one-workforce-permission",
                        target_kind=AssignmentTargetKind.PERMISSION,
                        target_id=first_account_permission,
                        access_atom_ids=(first_account_atom.access_atom_id,),
                    ),
                ),
            ),
            BirthrightRuleV1(
                rule_id="agent-reader-any-birthright",
                condition=BirthrightConditionV1(
                    operator=BirthrightConditionOperator.ANY,
                    predicates=(
                        PrincipalKindIsV1(values=(PrincipalKind.AGENT,)),
                        AccountKindIsV1(values=(accounts[0].account_kind,)),
                    ),
                ),
                assignments=(
                    BirthrightAssignmentV1(
                        assignment_id="one-agent-platform-group",
                        target_kind=AssignmentTargetKind.GROUP,
                        target_id=platform_group_id,
                        access_atom_ids=(first_agent_atom.access_atom_id,),
                    ),
                ),
            ),
        ),
        approved_exceptions=(
            ApprovedAccessExceptionV1(
                exception_id="approved-account-write",
                subject_id=account_atom_values[1].subject_id,
                access_atom_ids=(account_atom_values[1].access_atom_id,),
                owner_principal_id=employee_ids[0],
                reason=ApprovedExceptionReason.BUSINESS_NEED,
                valid_from_tick=0,
                valid_until_tick=1,
            ),
        ),
        intended_memberships=tuple(
            IntendedSubjectGroupMembershipV1(
                subject_id=item.subject_id, group_id=item.group_id
            )
            for item in kernel.memberships
        ),
        intended_group_nesting=tuple(
            IntendedGroupNestingV1(
                child_group_id=item.child_group_id,
                parent_group_id=item.parent_group_id,
            )
            for item in kernel.group_nesting
        ),
        intended_group_role_assignments=tuple(
            IntendedGroupRoleAssignmentV1(group_id=item.group_id, role_id=item.role_id)
            for item in kernel.group_role_assignments
        ),
        intended_subject_role_assignments=tuple(
            IntendedSubjectRoleAssignmentV1(
                subject_id=item.subject_id, role_id=item.role_id
            )
            for item in kernel.subject_role_assignments
        ),
        intended_role_hierarchy=tuple(
            IntendedRoleHierarchyV1(
                senior_role_id=item.senior_role_id,
                junior_role_id=item.junior_role_id,
            )
            for item in kernel.role_hierarchy
        ),
        intended_role_grants=tuple(
            IntendedRoleGrantV1(role_id=item.role_id, permission_id=item.permission_id)
            for item in kernel.role_grants
        ),
        ssd_constraints=(
            StaticSodConstraintV1(
                constraint_id="admin-reader-ssd",
                tenant_id=tenant_id,
                role_ids=(admin_role_id, reader_role_id),
                cardinality=2,
            ),
        ),
        dsd_constraints=(
            DynamicSodConstraintV1(
                constraint_id="admin-reader-dsd",
                tenant_id=tenant_id,
                role_ids=(admin_role_id, reader_role_id),
                cardinality=2,
            ),
        ),
    )
    session_rows = []
    for slot in corpus.session_slots:
        subject = next(
            item for item in universe.principals if item.principal_id == slot.subject_id
        )
        roles = (
            (admin_role_id, reader_role_id)
            if subject.principal_kind is PrincipalKind.AGENT
            else (admin_role_id,)
        )
        session_rows.append(
            ObservedRbacSessionStateV1(
                session_state_id=slot.session_state_id,
                observed_outcome=ActivationOutcome.ACCEPTED,
                activated_role_ids=roles,
                observed_at_tick=slot.activation_tick,
                valid_until_tick=slot.valid_until_tick,
                revision_id=f"observed-{subject.principal_kind.value}-session",
            )
        )
    session_state = EnterpriseRbacSessionStateInputV1(
        evaluation_corpus_digest=synthetic_digest(canonical_json_bytes(corpus)),
        sessions=tuple(session_rows),
    )
    return ReferenceEnterpriseRbacInputsV1(
        source_import=source_import,
        universe_result=result,
        corpus_result=corpus_result,
        kernel=kernel,
        intent=intent,
        session_state=session_state,
    )


__all__ = [
    "REFERENCE_ENTERPRISE_SEED",
    "ReferenceEnterpriseRbacInputsV1",
    "reference_enterprise_evaluation_corpus_config",
    "reference_enterprise_rbac_inputs",
]
