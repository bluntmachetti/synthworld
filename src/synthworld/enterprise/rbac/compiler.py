"""Offline bounded directory/RBAC reference semantics over a fixed corpus."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import cast
from uuid import UUID, uuid5

from synthworld.enterprise.canonical import (
    canonical_json_bytes,
    encode_parts,
    synthetic_digest,
)
from synthworld.enterprise.compiler import EnterpriseCompileError
from synthworld.enterprise.models import (
    AccessAtomV1,
    AccessSubjectKind,
    AdministrativeState,
    EnterpriseAccountV1,
    EnterpriseCanonicalBindingTruthV1,
    EnterpriseGroupV1,
    EnterpriseIdentityAccessCompileConfigV1,
    EnterpriseIdentityAccessUniverseV1,
    EnterprisePermissionV1,
    EnterprisePrincipalV1,
    EnterpriseRoleV1,
    SyntheticDigestV1,
)
from synthworld.enterprise.rbac.common import (
    ENTERPRISE_DIRECTORY_RBAC_COMPILER_VERSION,
    ActivationOutcome,
    AssignmentTargetKind,
    AuthorizationDecision,
    BindingStatus,
    BirthrightConditionOperator,
    DerivationMechanism,
    LifecycleStatus,
    ReconciliationOutcome,
)
from synthworld.enterprise.rbac.corpus_models import (
    AccessEvaluationCellV1,
    EnterpriseEvaluationCorpusV1,
)
from synthworld.enterprise.rbac.graph import bounded_paths, canonical_adjacency
from synthworld.enterprise.rbac.models import (
    AccessDerivationPathTruthV1,
    ActivationDecisionTruthV1,
    ApprovedAccessExceptionV1,
    ApprovedExceptionTruthV1,
    AuthorizedRolePathTruthV1,
    AuthorizedRoleSetTruthV1,
    BirthrightAssignmentTruthV1,
    BirthrightAssignmentV1,
    BirthrightEligibilityTruthV1,
    BirthrightPredicateTruthV1,
    BirthrightPredicateV1,
    BirthrightRuleV1,
    CompiledEnterpriseDirectoryRbacTruthV1,
    DirectoryDirectEntitlementV1,
    DirectoryRbacCellTruthV1,
    DsdConstraintTruthV1,
    DynamicSodConstraintV1,
    EmploymentTypeIsV1,
    EnterpriseDirectoryRbacIntentOverlayV1,
    EnterpriseDirectoryRbacKernelV1,
    EnterpriseRbacSessionStateInputV1,
    MembershipPathTruthV1,
    ObservedSessionTruthV1,
    PrincipalKindIsV1,
    RoleAssignmentSourceKind,
    SsdConstraintTruthV1,
    StaticSodConstraintV1,
    TenantIsV1,
    UnitIsV1,
)
from synthworld.enterprise.validation import dag_max_depth

ENTERPRISE_DIRECTORY_RBAC_TRUTH_RECORD_NAMESPACE_V1 = UUID(
    "a23e5b3e-5d4c-5011-8110-0d54ae876a71"
)


@dataclass(frozen=True, slots=True)
class _SubjectProfile:
    subject_id: str
    tenant_id: str
    principal: EnterprisePrincipalV1 | None
    account: EnterpriseAccountV1 | None


@dataclass(frozen=True, slots=True)
class _RoleFacts:
    membership_paths: tuple[MembershipPathTruthV1, ...]
    role_paths: tuple[AuthorizedRolePathTruthV1, ...]
    role_sets: tuple[AuthorizedRoleSetTruthV1, ...]
    role_dag_paths: Mapping[str, tuple[tuple[str, ...], ...]]


@dataclass(frozen=True, slots=True)
class _SessionFacts:
    activation_decisions: tuple[ActivationDecisionTruthV1, ...]
    dsd_evaluations: tuple[DsdConstraintTruthV1, ...]
    observed_sessions: tuple[ObservedSessionTruthV1, ...]


def _role_fact_derivation_count(facts: _RoleFacts) -> int:
    return len(facts.membership_paths) + len(facts.role_paths)


def _require_derivation_capacity(measured: int, allowed: int) -> None:
    if measured > allowed:
        raise EnterpriseCompileError(
            "directory_rbac_total_derivation_budget_exceeded",
            "directory/RBAC derivations exceed their independent total budget",
            measured=measured,
            allowed=allowed,
        )


def compile_enterprise_directory_rbac_truth(
    *,
    universe: EnterpriseIdentityAccessUniverseV1,
    canonical_binding_truth: EnterpriseCanonicalBindingTruthV1,
    corpus: EnterpriseEvaluationCorpusV1,
    directory_rbac_kernel: EnterpriseDirectoryRbacKernelV1,
    session_state: EnterpriseRbacSessionStateInputV1,
    directory_rbac_intent: EnterpriseDirectoryRbacIntentOverlayV1,
    compile_config: EnterpriseIdentityAccessCompileConfigV1 | None = None,
) -> CompiledEnterpriseDirectoryRbacTruthV1:
    """Compile explainable B/I/E/F truth without adding an atom or cell."""

    selected_config = compile_config or EnterpriseIdentityAccessCompileConfigV1()
    digests = _validate_bindings(
        universe=universe,
        binding_truth=canonical_binding_truth,
        corpus=corpus,
        kernel=directory_rbac_kernel,
        session_state=session_state,
        intent=directory_rbac_intent,
        compile_config=selected_config,
    )
    indexes = _UniverseIndexes(universe, canonical_binding_truth, directory_rbac_kernel)
    _validate_kernel_references(directory_rbac_kernel, indexes)
    _validate_intent_references(
        directory_rbac_intent,
        directory_rbac_kernel,
        corpus,
        indexes,
        selected_config,
    )
    _validate_session_state(session_state, corpus, indexes)

    actual_profiles = indexes.actual_subject_profiles()
    canonical_profiles = indexes.canonical_subject_profiles()
    derivation_budget = selected_config.budget.max_total_derivations
    actual_roles = _compile_actual_role_facts(
        directory_rbac_kernel,
        indexes,
        actual_profiles,
        selected_config,
        universe_digest=digests.universe.value,
        max_output_derivations=derivation_budget,
    )
    remaining_derivations = derivation_budget - _role_fact_derivation_count(
        actual_roles
    )
    intended_roles = _compile_intended_role_facts(
        directory_rbac_intent,
        indexes,
        canonical_profiles,
        selected_config,
        universe_digest=digests.universe.value,
        intent_digest=digests.intent.value,
        max_output_derivations=remaining_derivations,
    )
    remaining_derivations -= _role_fact_derivation_count(intended_roles)
    ssd = _compile_ssd_truth(
        directory_rbac_intent,
        actual_roles.role_sets,
        indexes,
        digests.intent.value,
    )
    session_facts = _compile_session_truth(
        corpus,
        session_state,
        directory_rbac_intent,
        actual_roles,
        indexes,
        digests.intent.value,
    )
    predicate_truth, eligibility_truth, eligible = _compile_birthright_eligibility(
        corpus,
        directory_rbac_intent,
        indexes,
        canonical_profiles,
        digests.intent.value,
    )
    (
        cells,
        actual_derivations,
        intended_derivations,
        assignment_truth,
        exception_truth,
    ) = _compile_cells(
        corpus=corpus,
        kernel=directory_rbac_kernel,
        intent=directory_rbac_intent,
        indexes=indexes,
        actual_roles=actual_roles,
        intended_roles=intended_roles,
        session_facts=session_facts,
        eligible=eligible,
        intent_digest=digests.intent.value,
        universe_digest=digests.universe.value,
        config=selected_config,
        max_total_derivations=remaining_derivations,
    )
    truth = CompiledEnterpriseDirectoryRbacTruthV1(
        identity_access_universe_digest=digests.universe,
        canonical_binding_truth_digest=digests.binding,
        evaluation_corpus_digest=digests.corpus,
        directory_rbac_kernel_digest=digests.kernel,
        directory_rbac_intent_digest=digests.intent,
        rbac_session_state_digest=digests.session,
        membership_paths=actual_roles.membership_paths,
        authorized_role_paths=actual_roles.role_paths,
        authorized_role_sets=actual_roles.role_sets,
        access_derivation_paths=actual_derivations,
        intended_derivation_paths=intended_derivations,
        birthright_predicates=predicate_truth,
        birthright_eligibility=eligibility_truth,
        birthright_assignments=assignment_truth,
        approved_exceptions=exception_truth,
        ssd_evaluations=ssd,
        dsd_evaluations=session_facts.dsd_evaluations,
        activation_decisions=session_facts.activation_decisions,
        observed_sessions=session_facts.observed_sessions,
        cells=cells,
    )
    _check_truth_outer_safety(truth, selected_config)
    return truth


@dataclass(frozen=True, slots=True)
class _InputDigests:
    universe: SyntheticDigestV1
    binding: SyntheticDigestV1
    corpus: SyntheticDigestV1
    kernel: SyntheticDigestV1
    intent: SyntheticDigestV1
    session: SyntheticDigestV1


def _validate_bindings(
    *,
    universe: EnterpriseIdentityAccessUniverseV1,
    binding_truth: EnterpriseCanonicalBindingTruthV1,
    corpus: EnterpriseEvaluationCorpusV1,
    kernel: EnterpriseDirectoryRbacKernelV1,
    session_state: EnterpriseRbacSessionStateInputV1,
    intent: EnterpriseDirectoryRbacIntentOverlayV1,
    compile_config: EnterpriseIdentityAccessCompileConfigV1,
) -> _InputDigests:
    universe_digest = synthetic_digest(canonical_json_bytes(universe))
    corpus_digest = synthetic_digest(canonical_json_bytes(corpus))
    config_digest = synthetic_digest(canonical_json_bytes(compile_config))
    checks = (
        (
            binding_truth.identity_access_universe_digest == universe_digest,
            "canonical_binding_universe_digest_mismatch",
        ),
        (
            corpus.identity_access_universe_digest == universe_digest,
            "rbac_corpus_universe_digest_mismatch",
        ),
        (
            kernel.identity_access_universe_digest == universe_digest,
            "rbac_kernel_universe_digest_mismatch",
        ),
        (
            intent.identity_access_universe_digest == universe_digest,
            "rbac_intent_universe_digest_mismatch",
        ),
        (
            intent.evaluation_corpus_digest == corpus_digest,
            "rbac_intent_corpus_digest_mismatch",
        ),
        (
            session_state.evaluation_corpus_digest == corpus_digest,
            "rbac_session_corpus_digest_mismatch",
        ),
        (
            corpus.compile_config_digest == config_digest,
            "rbac_corpus_compile_config_digest_mismatch",
        ),
        (
            kernel.compile_config_digest == config_digest,
            "rbac_kernel_compile_config_digest_mismatch",
        ),
    )
    for valid, code in checks:
        if not valid:
            raise EnterpriseCompileError(
                code, "directory/RBAC input digest binding differs"
            )
    return _InputDigests(
        universe=universe_digest,
        binding=synthetic_digest(canonical_json_bytes(binding_truth)),
        corpus=corpus_digest,
        kernel=synthetic_digest(canonical_json_bytes(kernel)),
        intent=synthetic_digest(canonical_json_bytes(intent)),
        session=synthetic_digest(canonical_json_bytes(session_state)),
    )


class _UniverseIndexes:
    def __init__(
        self,
        universe: EnterpriseIdentityAccessUniverseV1,
        bindings: EnterpriseCanonicalBindingTruthV1,
        kernel: EnterpriseDirectoryRbacKernelV1,
    ) -> None:
        self.tenants = {item.tenant_id: item for item in universe.tenants}
        self.units = {item.unit_id: item for item in universe.units}
        self.principals = {item.principal_id: item for item in universe.principals}
        self.accounts = {item.account_id: item for item in universe.accounts}
        self.subjects = {item.subject_id: item for item in universe.access_subjects}
        self.groups = {item.group_id: item for item in universe.groups}
        self.roles = {item.role_id: item for item in universe.roles}
        self.permissions = {item.permission_id: item for item in universe.permissions}
        self.targets = {
            item.authorization_target_id: item
            for item in universe.authorization_targets
        }
        self.atoms = {item.access_atom_id: item for item in universe.access_atoms}
        self.permission_by_target_action = {
            (item.authorization_target_id, item.action): item
            for item in universe.permissions
        }
        self.canonical_principal_by_account = {
            item.account_id: item.principal_id for item in bindings.bindings
        }
        self.observation_by_account = {
            item.account_id: item for item in kernel.account_observations
        }

    def canonical_subject_profiles(self) -> dict[str, _SubjectProfile]:
        return self._subject_profiles(use_canonical_binding=True)

    def actual_subject_profiles(self) -> dict[str, _SubjectProfile]:
        return self._subject_profiles(use_canonical_binding=False)

    def _subject_profiles(
        self, *, use_canonical_binding: bool
    ) -> dict[str, _SubjectProfile]:
        profiles: dict[str, _SubjectProfile] = {}
        for subject_id, subject in self.subjects.items():
            if subject.subject_kind is AccessSubjectKind.PRINCIPAL:
                profiles[subject_id] = _SubjectProfile(
                    subject_id=subject_id,
                    tenant_id=subject.tenant_id,
                    principal=self.principals[subject_id],
                    account=None,
                )
                continue
            account = self.accounts[subject_id]
            principal_id = (
                self.canonical_principal_by_account.get(subject_id)
                if use_canonical_binding
                else (
                    self.observation_by_account[subject_id].observed_principal_id
                    if subject_id in self.observation_by_account
                    else None
                )
            )
            profiles[subject_id] = _SubjectProfile(
                subject_id=subject_id,
                tenant_id=subject.tenant_id,
                principal=(
                    self.principals.get(principal_id)
                    if principal_id is not None
                    else None
                ),
                account=account,
            )
        return profiles


def _validate_kernel_references(
    kernel: EnterpriseDirectoryRbacKernelV1, indexes: _UniverseIndexes
) -> None:
    for observation in kernel.account_observations:
        account = indexes.accounts.get(observation.account_id)
        principal = (
            indexes.principals.get(observation.observed_principal_id)
            if observation.observed_principal_id is not None
            else None
        )
        if account is None:
            raise EnterpriseCompileError(
                "unknown_kernel_account", "kernel account observation does not resolve"
            )
        if observation.observed_principal_id is not None and principal is None:
            raise EnterpriseCompileError(
                "unknown_kernel_observed_principal",
                "kernel observed principal does not resolve",
            )
        if principal is not None and principal.tenant_id != account.tenant_id:
            raise EnterpriseCompileError(
                "cross_tenant_kernel_binding", "kernel binding crosses tenants"
            )
    relation_specs = (
        (
            kernel.memberships,
            lambda item: (
                indexes.subjects.get(item.subject_id),
                indexes.groups.get(item.group_id),
            ),
            "unknown_kernel_membership_reference",
        ),
        (
            kernel.group_nesting,
            lambda item: (
                indexes.groups.get(item.child_group_id),
                indexes.groups.get(item.parent_group_id),
            ),
            "unknown_kernel_group_nesting_reference",
        ),
        (
            kernel.group_role_assignments,
            lambda item: (
                indexes.groups.get(item.group_id),
                indexes.roles.get(item.role_id),
            ),
            "unknown_kernel_group_role_reference",
        ),
        (
            kernel.subject_role_assignments,
            lambda item: (
                indexes.subjects.get(item.subject_id),
                indexes.roles.get(item.role_id),
            ),
            "unknown_kernel_subject_role_reference",
        ),
        (
            kernel.role_hierarchy,
            lambda item: (
                indexes.roles.get(item.senior_role_id),
                indexes.roles.get(item.junior_role_id),
            ),
            "unknown_kernel_role_hierarchy_reference",
        ),
        (
            kernel.role_grants,
            lambda item: (
                indexes.roles.get(item.role_id),
                indexes.permissions.get(item.permission_id),
            ),
            "unknown_kernel_role_grant_reference",
        ),
        (
            kernel.direct_entitlements,
            lambda item: (
                indexes.subjects.get(item.subject_id),
                indexes.permissions.get(item.permission_id),
            ),
            "unknown_kernel_direct_entitlement_reference",
        ),
    )
    for records, resolver, code in relation_specs:
        for item in records:
            left, right = resolver(item)
            if left is None or right is None:
                raise EnterpriseCompileError(code, "kernel relation does not resolve")
            if left.tenant_id != _tenant_id(right, indexes):
                raise EnterpriseCompileError(
                    "cross_tenant_kernel_relation", "kernel relation crosses tenants"
                )
    canonical_adjacency(
        indexes.groups,
        ((item.child_group_id, item.parent_group_id) for item in kernel.group_nesting),
    )
    canonical_adjacency(
        indexes.roles,
        ((item.senior_role_id, item.junior_role_id) for item in kernel.role_hierarchy),
    )


def _tenant_id(
    item: EnterpriseGroupV1 | EnterpriseRoleV1 | EnterprisePermissionV1,
    indexes: _UniverseIndexes,
) -> str:
    if isinstance(item, EnterprisePermissionV1):
        return indexes.targets[item.authorization_target_id].tenant_id
    return item.tenant_id


def _birthright_target(
    kind: AssignmentTargetKind,
    target_id: str,
    indexes: _UniverseIndexes,
) -> EnterpriseGroupV1 | EnterpriseRoleV1 | EnterprisePermissionV1 | None:
    if kind is AssignmentTargetKind.GROUP:
        return indexes.groups.get(target_id)
    if kind is AssignmentTargetKind.ROLE:
        return indexes.roles.get(target_id)
    return indexes.permissions.get(target_id)


def _validate_intent_references(
    intent: EnterpriseDirectoryRbacIntentOverlayV1,
    kernel: EnterpriseDirectoryRbacKernelV1,
    corpus: EnterpriseEvaluationCorpusV1,
    indexes: _UniverseIndexes,
    config: EnterpriseIdentityAccessCompileConfigV1,
) -> None:
    corpus_atom_ids = {
        indexes.atoms[cell.access_atom_id].access_atom_id
        for cell in corpus.evaluation_cells
    }
    for rule in intent.birthright_rules:
        for predicate in rule.condition.predicates:
            if isinstance(predicate, TenantIsV1):
                _require_known_ids(
                    predicate.tenant_ids, indexes.tenants, "predicate_tenant"
                )
            elif isinstance(predicate, UnitIsV1):
                _require_known_ids(predicate.unit_ids, indexes.units, "predicate_unit")
        for assignment in rule.assignments:
            _require_known_ids(
                assignment.access_atom_ids,
                corpus_atom_ids,
                "birthright_access_atom",
            )
            target = _birthright_target(
                assignment.target_kind, assignment.target_id, indexes
            )
            if target is None:
                raise EnterpriseCompileError(
                    "unknown_birthright_assignment_target",
                    "birthright assignment target does not resolve",
                )
            for atom_id in assignment.access_atom_ids:
                atom = indexes.atoms[atom_id]
                if indexes.subjects[atom.subject_id].tenant_id != _tenant_id(
                    target, indexes
                ):
                    raise EnterpriseCompileError(
                        "cross_tenant_birthright_assignment",
                        "birthright assignment target and atom must share a tenant",
                    )
                if (
                    assignment.target_kind is AssignmentTargetKind.PERMISSION
                    and indexes.permission_by_target_action[
                        (atom.authorization_target_id, atom.action)
                    ].permission_id
                    != assignment.target_id
                ):
                    raise EnterpriseCompileError(
                        "birthright_permission_scope_mismatch",
                        "permission assignment must match every scoped atom",
                    )
    for exception in intent.approved_exceptions:
        subject = indexes.subjects.get(exception.subject_id)
        owner = indexes.principals.get(exception.owner_principal_id)
        if subject is None or owner is None:
            raise EnterpriseCompileError(
                "unknown_approved_exception_reference",
                "approved exception subject or owner does not resolve",
            )
        if subject.tenant_id != owner.tenant_id:
            raise EnterpriseCompileError(
                "cross_tenant_approved_exception",
                "approved exception owner and subject must share a tenant",
            )
        _require_known_ids(
            exception.access_atom_ids,
            corpus_atom_ids,
            "approved_exception_access_atom",
        )
        if any(
            indexes.atoms[atom_id].subject_id != exception.subject_id
            for atom_id in exception.access_atom_ids
        ):
            raise EnterpriseCompileError(
                "approved_exception_subject_mismatch",
                "approved exception atoms must belong to its subject",
            )
    intended_relation_count = _validate_intended_relations(intent, indexes, config)
    _check_directory_rbac_semantic_budget(
        kernel=kernel,
        intent=intent,
        corpus=corpus,
        indexes=indexes,
        intended_relation_count=intended_relation_count,
        config=config,
    )
    _validate_sod_constraints(intent, indexes, corpus, config)


def _validate_intended_relations(
    intent: EnterpriseDirectoryRbacIntentOverlayV1,
    indexes: _UniverseIndexes,
    config: EnterpriseIdentityAccessCompileConfigV1,
) -> int:
    relation_specs = (
        (
            intent.intended_memberships,
            lambda item: (
                indexes.subjects.get(item.subject_id),
                indexes.groups.get(item.group_id),
            ),
        ),
        (
            intent.intended_group_nesting,
            lambda item: (
                indexes.groups.get(item.child_group_id),
                indexes.groups.get(item.parent_group_id),
            ),
        ),
        (
            intent.intended_group_role_assignments,
            lambda item: (
                indexes.groups.get(item.group_id),
                indexes.roles.get(item.role_id),
            ),
        ),
        (
            intent.intended_subject_role_assignments,
            lambda item: (
                indexes.subjects.get(item.subject_id),
                indexes.roles.get(item.role_id),
            ),
        ),
        (
            intent.intended_role_hierarchy,
            lambda item: (
                indexes.roles.get(item.senior_role_id),
                indexes.roles.get(item.junior_role_id),
            ),
        ),
        (
            intent.intended_role_grants,
            lambda item: (
                indexes.roles.get(item.role_id),
                indexes.permissions.get(item.permission_id),
            ),
        ),
    )
    relation_count = sum(len(records) for records, _resolver in relation_specs)
    for records, resolver in relation_specs:
        for record in records:
            left, right = resolver(record)
            if left is None or right is None:
                raise EnterpriseCompileError(
                    "unknown_intended_rbac_reference",
                    "intended directory/RBAC relation does not resolve",
                )
            if left.tenant_id != _tenant_id(right, indexes):
                raise EnterpriseCompileError(
                    "cross_tenant_intended_rbac_relation",
                    "intended directory/RBAC relation crosses tenants",
                )
    group_edges = tuple(
        (item.child_group_id, item.parent_group_id)
        for item in intent.intended_group_nesting
    )
    role_edges = tuple(
        (item.senior_role_id, item.junior_role_id)
        for item in intent.intended_role_hierarchy
    )
    canonical_adjacency(
        indexes.groups,
        group_edges,
    )
    canonical_adjacency(
        indexes.roles,
        role_edges,
    )
    _require_intended_graph_depth(
        nodes=set(indexes.groups),
        edges=group_edges,
        allowed=config.budget.max_group_depth,
        code="intended_group_depth_budget_exceeded",
    )
    _require_intended_graph_depth(
        nodes=set(indexes.roles),
        edges=role_edges,
        allowed=config.budget.max_role_depth,
        code="intended_role_depth_budget_exceeded",
    )
    return relation_count


def _require_intended_graph_depth(
    *,
    nodes: set[str],
    edges: tuple[tuple[str, str], ...],
    allowed: int,
    code: str,
) -> None:
    _acyclic, measured = dag_max_depth(nodes, edges)
    if measured > allowed:
        raise EnterpriseCompileError(
            code,
            "intended directory/RBAC graph exceeds its depth budget",
            measured=measured,
            allowed=allowed,
        )


def _check_directory_rbac_semantic_budget(
    *,
    kernel: EnterpriseDirectoryRbacKernelV1,
    intent: EnterpriseDirectoryRbacIntentOverlayV1,
    corpus: EnterpriseEvaluationCorpusV1,
    indexes: _UniverseIndexes,
    intended_relation_count: int,
    config: EnterpriseIdentityAccessCompileConfigV1,
) -> None:
    actual_relation_count = sum(
        len(records)
        for records in (
            kernel.account_observations,
            kernel.memberships,
            kernel.group_nesting,
            kernel.group_role_assignments,
            kernel.subject_role_assignments,
            kernel.role_hierarchy,
            kernel.role_grants,
            kernel.direct_entitlements,
        )
    )
    subject_ids = {
        indexes.atoms[cell.access_atom_id].subject_id
        for cell in corpus.evaluation_cells
    }
    cells_by_atom: dict[str, int] = defaultdict(int)
    for cell in corpus.evaluation_cells:
        cells_by_atom[cell.access_atom_id] += 1
    birthright_evaluations = sum(
        len(subject_ids) * (len(rule.condition.predicates) + 1)
        + sum(
            sum(cells_by_atom[atom_id] for atom_id in assignment.access_atom_ids)
            for assignment in rule.assignments
        )
        for rule in intent.birthright_rules
    )
    exception_evaluations = sum(
        sum(cells_by_atom[atom_id] for atom_id in exception.access_atom_ids)
        for exception in intent.approved_exceptions
    )
    measured = (
        actual_relation_count
        + intended_relation_count
        + birthright_evaluations
        + exception_evaluations
    )
    allowed = config.budget.max_directory_rbac_relations
    if measured > allowed:
        raise EnterpriseCompileError(
            "directory_rbac_semantic_budget_exceeded",
            "directory/RBAC relations and projected policy rows exceed their budget",
            measured=measured,
            allowed=allowed,
        )


def _validate_sod_constraints(
    intent: EnterpriseDirectoryRbacIntentOverlayV1,
    indexes: _UniverseIndexes,
    corpus: EnterpriseEvaluationCorpusV1,
    config: EnterpriseIdentityAccessCompileConfigV1,
) -> None:
    constraints: tuple[StaticSodConstraintV1 | DynamicSodConstraintV1, ...] = (
        *intent.ssd_constraints,
        *intent.dsd_constraints,
    )
    budget = config.budget
    if len(constraints) > budget.max_sod_constraints:
        raise EnterpriseCompileError(
            "sod_constraint_budget_exceeded",
            "SoD constraint count exceeds its independent budget",
            measured=len(constraints),
            allowed=budget.max_sod_constraints,
        )
    for constraint in constraints:
        if len(constraint.role_ids) > budget.max_sod_role_set_width:
            raise EnterpriseCompileError(
                "sod_role_set_width_budget_exceeded",
                "SoD role-set width exceeds its independent budget",
                measured=len(constraint.role_ids),
                allowed=budget.max_sod_role_set_width,
            )
        if constraint.tenant_id not in indexes.tenants:
            raise EnterpriseCompileError(
                "unknown_sod_tenant", "SoD constraint tenant does not resolve"
            )
        _require_known_ids(constraint.role_ids, indexes.roles, "sod_role")
        _require_known_ids(constraint.subject_ids, indexes.subjects, "sod_subject")
        if any(
            indexes.roles[role_id].tenant_id != constraint.tenant_id
            for role_id in constraint.role_ids
        ) or any(
            indexes.subjects[subject_id].tenant_id != constraint.tenant_id
            for subject_id in constraint.subject_ids
        ):
            raise EnterpriseCompileError(
                "cross_tenant_sod_constraint", "SoD constraint crosses tenants"
            )
    evaluation_count = sum(
        sum(
            subject.tenant_id == constraint.tenant_id
            and (not constraint.subject_ids or subject_id in constraint.subject_ids)
            for subject_id, subject in indexes.subjects.items()
        )
        for constraint in intent.ssd_constraints
    ) + sum(
        sum(
            indexes.subjects[request.subject_id].tenant_id == constraint.tenant_id
            and (
                not constraint.subject_ids
                or request.subject_id in constraint.subject_ids
            )
            for request in corpus.role_activation_requests
        )
        for constraint in intent.dsd_constraints
    )
    if evaluation_count > budget.max_sod_evaluations:
        raise EnterpriseCompileError(
            "sod_evaluation_budget_exceeded",
            "SoD evaluation count exceeds its independent budget",
            measured=evaluation_count,
            allowed=budget.max_sod_evaluations,
        )


def _validate_session_state(
    session_state: EnterpriseRbacSessionStateInputV1,
    corpus: EnterpriseEvaluationCorpusV1,
    indexes: _UniverseIndexes,
) -> None:
    slots = {item.session_state_id: item for item in corpus.session_slots}
    observations = {item.session_state_id: item for item in session_state.sessions}
    if set(slots) != set(observations):
        raise EnterpriseCompileError(
            "observed_session_state_cardinality",
            "each frozen session slot must have exactly one observed state",
        )
    for session_id, observation in observations.items():
        slot = slots[session_id]
        if observation.observed_at_tick != slot.activation_tick:
            raise EnterpriseCompileError(
                "observed_session_tick_mismatch",
                "observed session tick must equal its activation tick",
            )
        if slot.valid_until_tick is not None and (
            observation.valid_until_tick is None
            or observation.valid_until_tick > slot.valid_until_tick
        ):
            raise EnterpriseCompileError(
                "observed_session_exceeds_slot_validity",
                "observed session cannot outlive its frozen slot",
            )
        subject = indexes.subjects[slot.subject_id]
        for role_id in observation.activated_role_ids:
            role = indexes.roles.get(role_id)
            if role is None:
                raise EnterpriseCompileError(
                    "unknown_observed_activated_role",
                    "observed session contains an unknown role",
                )
            if role.tenant_id != subject.tenant_id:
                raise EnterpriseCompileError(
                    "cross_tenant_observed_activated_role",
                    "observed session role crosses tenants",
                )
    for cell in corpus.evaluation_cells:
        if cell.session_state_id is None:
            continue
        cell_observation = observations.get(cell.session_state_id)
        if cell_observation is None:
            raise EnterpriseCompileError(
                "cell_session_state_not_observed",
                "session cell does not resolve a frozen observed session",
            )
        if (
            cell_observation.valid_until_tick is not None
            and cell.tick >= cell_observation.valid_until_tick
        ):
            raise EnterpriseCompileError(
                "cell_at_or_after_observed_session_expiry",
                "session cell must fall inside observed session validity",
            )


def _compile_actual_role_facts(
    kernel: EnterpriseDirectoryRbacKernelV1,
    indexes: _UniverseIndexes,
    profiles: Mapping[str, _SubjectProfile],
    config: EnterpriseIdentityAccessCompileConfigV1,
    *,
    universe_digest: str,
    max_output_derivations: int,
) -> _RoleFacts:
    group_adjacency = canonical_adjacency(
        indexes.groups,
        ((item.child_group_id, item.parent_group_id) for item in kernel.group_nesting),
    )
    group_paths = bounded_paths(
        adjacency=group_adjacency,
        starts=(item.group_id for item in kernel.memberships),
        max_paths_per_start=config.budget.max_derivations_per_cell,
        max_total_paths=config.budget.max_total_derivations,
        budget_code="membership_path_budget_exceeded",
    )
    membership_path_count = sum(
        len(group_paths[edge.group_id]) for edge in kernel.memberships
    )
    _require_derivation_capacity(
        membership_path_count,
        max_output_derivations,
    )
    membership_paths = tuple(
        MembershipPathTruthV1(
            path_id=_truth_id(
                universe_digest,
                "membership-path",
                edge.edge_id,
                *path,
            ),
            subject_id=edge.subject_id,
            group_id=path[-1],
            group_path=path,
        )
        for edge in kernel.memberships
        for path in group_paths[edge.group_id]
    )
    role_adjacency = canonical_adjacency(
        indexes.roles,
        ((item.senior_role_id, item.junior_role_id) for item in kernel.role_hierarchy),
    )
    role_paths = bounded_paths(
        adjacency=role_adjacency,
        starts=indexes.roles,
        max_paths_per_start=config.budget.max_derivations_per_cell,
        max_total_paths=config.budget.max_total_derivations,
        budget_code="authorized_role_path_budget_exceeded",
    )
    membership_by_group: dict[str, list[MembershipPathTruthV1]] = defaultdict(list)
    for membership in membership_paths:
        membership_by_group[membership.group_id].append(membership)
    principal_path_counts: dict[str, int] = defaultdict(int)
    for subject_assignment in kernel.subject_role_assignments:
        principal_path_counts[subject_assignment.subject_id] += len(
            role_paths[subject_assignment.role_id]
        )
    for group_assignment in kernel.group_role_assignments:
        for membership in membership_by_group[group_assignment.group_id]:
            principal_path_counts[membership.subject_id] += len(
                role_paths[group_assignment.role_id]
            )
    authorized_path_count = sum(principal_path_counts.values()) + sum(
        principal_path_counts[profile.principal.principal_id]
        for profile in profiles.values()
        if profile.account is not None and profile.principal is not None
    )
    _require_derivation_capacity(
        membership_path_count + authorized_path_count,
        max_output_derivations,
    )
    compiled_paths: list[AuthorizedRolePathTruthV1] = []
    for subject_assignment in kernel.subject_role_assignments:
        for role_chain in role_paths[subject_assignment.role_id]:
            compiled_paths.append(
                _authorized_path(
                    universe_digest,
                    subject_id=subject_assignment.subject_id,
                    source_kind=RoleAssignmentSourceKind.SUBJECT,
                    source_id=subject_assignment.edge_id,
                    group_path=(),
                    role_path=role_chain,
                )
            )
    for group_assignment in kernel.group_role_assignments:
        for membership in membership_by_group[group_assignment.group_id]:
            for role_chain in role_paths[group_assignment.role_id]:
                compiled_paths.append(
                    _authorized_path(
                        universe_digest,
                        subject_id=membership.subject_id,
                        source_kind=RoleAssignmentSourceKind.GROUP,
                        source_id=group_assignment.edge_id,
                        group_path=membership.group_path,
                        role_path=role_chain,
                    )
                )
    principal_paths: dict[str, list[AuthorizedRolePathTruthV1]] = defaultdict(list)
    for authorized_record in compiled_paths:
        principal_paths[authorized_record.subject_id].append(authorized_record)
    for subject_id, profile in profiles.items():
        if profile.account is None or profile.principal is None:
            continue
        for source in principal_paths[profile.principal.principal_id]:
            compiled_paths.append(
                _authorized_path(
                    universe_digest,
                    subject_id=subject_id,
                    source_kind=source.assignment_source_kind,
                    source_id=source.path_id,
                    group_path=source.group_path,
                    role_path=source.role_path,
                )
            )
    ordered_paths = tuple(sorted(compiled_paths, key=lambda item: item.path_id))
    roles_by_subject: dict[str, set[str]] = defaultdict(set)
    for authorized_record in ordered_paths:
        roles_by_subject[authorized_record.subject_id].add(authorized_record.role_id)
    role_sets = tuple(
        AuthorizedRoleSetTruthV1(
            subject_id=subject_id,
            role_ids=tuple(sorted(roles_by_subject[subject_id])),
        )
        for subject_id in sorted(indexes.subjects)
    )
    return _RoleFacts(
        membership_paths=tuple(sorted(membership_paths, key=lambda item: item.path_id)),
        role_paths=ordered_paths,
        role_sets=role_sets,
        role_dag_paths=role_paths,
    )


def _compile_intended_role_facts(
    intent: EnterpriseDirectoryRbacIntentOverlayV1,
    indexes: _UniverseIndexes,
    profiles: Mapping[str, _SubjectProfile],
    config: EnterpriseIdentityAccessCompileConfigV1,
    *,
    universe_digest: str,
    intent_digest: str,
    max_output_derivations: int,
) -> _RoleFacts:
    group_adjacency = canonical_adjacency(
        indexes.groups,
        (
            (item.child_group_id, item.parent_group_id)
            for item in intent.intended_group_nesting
        ),
    )
    group_paths = bounded_paths(
        adjacency=group_adjacency,
        starts=(item.group_id for item in intent.intended_memberships),
        max_paths_per_start=config.budget.max_derivations_per_cell,
        max_total_paths=config.budget.max_total_derivations,
        budget_code="intended_membership_path_budget_exceeded",
    )
    membership_path_count = sum(
        len(group_paths[item.group_id]) for item in intent.intended_memberships
    )
    _require_derivation_capacity(
        membership_path_count,
        max_output_derivations,
    )
    membership_paths = tuple(
        MembershipPathTruthV1(
            path_id=_truth_id(
                universe_digest,
                "intended-membership-path",
                intent_digest,
                item.subject_id,
                *path,
            ),
            subject_id=item.subject_id,
            group_id=path[-1],
            group_path=path,
        )
        for item in intent.intended_memberships
        for path in group_paths[item.group_id]
    )
    role_adjacency = canonical_adjacency(
        indexes.roles,
        (
            (item.senior_role_id, item.junior_role_id)
            for item in intent.intended_role_hierarchy
        ),
    )
    role_paths = bounded_paths(
        adjacency=role_adjacency,
        starts=indexes.roles,
        max_paths_per_start=config.budget.max_derivations_per_cell,
        max_total_paths=config.budget.max_total_derivations,
        budget_code="intended_authorized_role_path_budget_exceeded",
    )
    membership_by_group: dict[str, list[MembershipPathTruthV1]] = defaultdict(list)
    for membership in membership_paths:
        membership_by_group[membership.group_id].append(membership)
    principal_path_counts: dict[str, int] = defaultdict(int)
    for item in intent.intended_subject_role_assignments:
        principal_path_counts[item.subject_id] += len(role_paths[item.role_id])
    for group_assignment in intent.intended_group_role_assignments:
        for membership in membership_by_group[group_assignment.group_id]:
            principal_path_counts[membership.subject_id] += len(
                role_paths[group_assignment.role_id]
            )
    authorized_path_count = sum(principal_path_counts.values()) + sum(
        principal_path_counts[profile.principal.principal_id]
        for profile in profiles.values()
        if profile.account is not None and profile.principal is not None
    )
    _require_derivation_capacity(
        membership_path_count + authorized_path_count,
        max_output_derivations,
    )
    compiled: list[AuthorizedRolePathTruthV1] = []
    for item in intent.intended_subject_role_assignments:
        source_id = _truth_id(
            universe_digest,
            "intended-subject-role-source",
            intent_digest,
            item.subject_id,
            item.role_id,
        )
        for role_chain in role_paths[item.role_id]:
            compiled.append(
                _authorized_path(
                    universe_digest,
                    subject_id=item.subject_id,
                    source_kind=RoleAssignmentSourceKind.SUBJECT,
                    source_id=source_id,
                    group_path=(),
                    role_path=role_chain,
                )
            )
    for group_assignment in intent.intended_group_role_assignments:
        source_id = _truth_id(
            universe_digest,
            "intended-group-role-source",
            intent_digest,
            group_assignment.group_id,
            group_assignment.role_id,
        )
        for membership in membership_by_group[group_assignment.group_id]:
            for role_chain in role_paths[group_assignment.role_id]:
                compiled.append(
                    _authorized_path(
                        universe_digest,
                        subject_id=membership.subject_id,
                        source_kind=RoleAssignmentSourceKind.GROUP,
                        source_id=source_id,
                        group_path=membership.group_path,
                        role_path=role_chain,
                    )
                )
    principal_paths: dict[str, list[AuthorizedRolePathTruthV1]] = defaultdict(list)
    for authorized_record in compiled:
        principal_paths[authorized_record.subject_id].append(authorized_record)
    for subject_id, profile in profiles.items():
        if profile.account is None or profile.principal is None:
            continue
        for source in principal_paths[profile.principal.principal_id]:
            compiled.append(
                _authorized_path(
                    universe_digest,
                    subject_id=subject_id,
                    source_kind=source.assignment_source_kind,
                    source_id=source.path_id,
                    group_path=source.group_path,
                    role_path=source.role_path,
                )
            )
    ordered = tuple(sorted(compiled, key=lambda item: item.path_id))
    roles_by_subject: dict[str, set[str]] = defaultdict(set)
    for authorized_record in ordered:
        roles_by_subject[authorized_record.subject_id].add(authorized_record.role_id)
    return _RoleFacts(
        membership_paths=tuple(sorted(membership_paths, key=lambda item: item.path_id)),
        role_paths=ordered,
        role_sets=tuple(
            AuthorizedRoleSetTruthV1(
                subject_id=subject_id,
                role_ids=tuple(sorted(roles_by_subject[subject_id])),
            )
            for subject_id in sorted(indexes.subjects)
        ),
        role_dag_paths=role_paths,
    )


def _authorized_path(
    universe_digest: str,
    *,
    subject_id: str,
    source_kind: RoleAssignmentSourceKind,
    source_id: str,
    group_path: tuple[str, ...],
    role_path: tuple[str, ...],
) -> AuthorizedRolePathTruthV1:
    return AuthorizedRolePathTruthV1(
        path_id=_truth_id(
            universe_digest,
            "authorized-role-path",
            subject_id,
            source_kind.value,
            source_id,
            *group_path,
            *role_path,
        ),
        subject_id=subject_id,
        role_id=role_path[-1],
        assignment_source_kind=source_kind,
        assignment_source_id=source_id,
        group_path=group_path,
        role_path=role_path,
    )


def _compile_ssd_truth(
    intent: EnterpriseDirectoryRbacIntentOverlayV1,
    role_sets: tuple[AuthorizedRoleSetTruthV1, ...],
    indexes: _UniverseIndexes,
    intent_digest: str,
) -> tuple[SsdConstraintTruthV1, ...]:
    result: list[SsdConstraintTruthV1] = []
    for constraint in intent.ssd_constraints:
        constraint_id = _intent_id(intent_digest, "ssd", constraint.constraint_id)
        scoped_subjects = (
            set(constraint.subject_ids) if constraint.subject_ids else None
        )
        for role_set in role_sets:
            subject = indexes.subjects[role_set.subject_id]
            if subject.tenant_id != constraint.tenant_id or (
                scoped_subjects is not None
                and role_set.subject_id not in scoped_subjects
            ):
                continue
            intersection = tuple(
                sorted(set(role_set.role_ids) & set(constraint.role_ids))
            )
            result.append(
                SsdConstraintTruthV1(
                    constraint_id=constraint_id,
                    subject_id=role_set.subject_id,
                    role_ids=constraint.role_ids,
                    intersection_role_ids=intersection,
                    cardinality=constraint.cardinality,
                    violated=len(intersection) >= constraint.cardinality,
                )
            )
    return tuple(sorted(result, key=lambda item: (item.constraint_id, item.subject_id)))


def _compile_session_truth(
    corpus: EnterpriseEvaluationCorpusV1,
    session_state: EnterpriseRbacSessionStateInputV1,
    intent: EnterpriseDirectoryRbacIntentOverlayV1,
    role_facts: _RoleFacts,
    indexes: _UniverseIndexes,
    intent_digest: str,
) -> _SessionFacts:
    role_sets = {item.subject_id: set(item.role_ids) for item in role_facts.role_sets}
    observations = {item.session_state_id: item for item in session_state.sessions}
    dsd_rows: list[DsdConstraintTruthV1] = []
    activation_rows: list[ActivationDecisionTruthV1] = []
    session_rows: list[ObservedSessionTruthV1] = []
    for request in corpus.role_activation_requests:
        authorized = role_sets[request.subject_id]
        requested = set(request.requested_role_ids)
        unauthorized = not requested <= authorized
        applicable = tuple(
            item
            for item in intent.dsd_constraints
            if item.tenant_id == indexes.subjects[request.subject_id].tenant_id
            and (not item.subject_ids or request.subject_id in item.subject_ids)
        )
        observation = observations[request.session_state_id]
        actual = set(observation.activated_role_ids)
        request_dsd_violation = False
        actual_dsd_violation = False
        for constraint in applicable:
            requested_intersection = tuple(sorted(requested & set(constraint.role_ids)))
            actual_intersection = tuple(sorted(actual & set(constraint.role_ids)))
            request_violated = len(requested_intersection) >= constraint.cardinality
            observed_violated = len(actual_intersection) >= constraint.cardinality
            request_dsd_violation |= request_violated
            actual_dsd_violation |= observed_violated
            dsd_rows.append(
                DsdConstraintTruthV1(
                    constraint_id=_intent_id(
                        intent_digest, "dsd", constraint.constraint_id
                    ),
                    activation_request_id=request.activation_request_id,
                    session_state_id=request.session_state_id,
                    requested_intersection_role_ids=requested_intersection,
                    actual_intersection_role_ids=actual_intersection,
                    cardinality=constraint.cardinality,
                    request_violated=request_violated,
                    observed_session_violated=observed_violated,
                )
            )
        expected = (
            ActivationOutcome.REJECTED
            if unauthorized or request_dsd_violation
            else ActivationOutcome.ACCEPTED
        )
        activation_rows.append(
            ActivationDecisionTruthV1(
                activation_request_id=request.activation_request_id,
                session_state_id=request.session_state_id,
                subject_id=request.subject_id,
                requested_role_ids=request.requested_role_ids,
                authorized_role_ids=tuple(sorted(authorized)),
                expected_outcome=expected,
                unauthorized_role_requested=unauthorized,
                dsd_cardinality_met=request_dsd_violation,
            )
        )
        unauthorized_actual = tuple(sorted(actual - authorized))
        usable = tuple(sorted(actual & authorized))
        session_rows.append(
            ObservedSessionTruthV1(
                session_state_id=request.session_state_id,
                expected_outcome=expected,
                observed_outcome=observation.observed_outcome,
                actual_activated_role_ids=observation.activated_role_ids,
                unauthorized_activated_role_ids=unauthorized_actual,
                usable_activated_role_ids=usable,
                observed_outcome_correct=observation.observed_outcome is expected,
                dsd_compliant=not actual_dsd_violation,
            )
        )
    return _SessionFacts(
        activation_decisions=tuple(
            sorted(activation_rows, key=lambda item: item.activation_request_id)
        ),
        dsd_evaluations=tuple(
            sorted(
                dsd_rows,
                key=lambda item: (item.activation_request_id, item.constraint_id),
            )
        ),
        observed_sessions=tuple(
            sorted(session_rows, key=lambda item: item.session_state_id)
        ),
    )


def _compile_birthright_eligibility(
    corpus: EnterpriseEvaluationCorpusV1,
    intent: EnterpriseDirectoryRbacIntentOverlayV1,
    indexes: _UniverseIndexes,
    profiles: Mapping[str, _SubjectProfile],
    intent_digest: str,
) -> tuple[
    tuple[BirthrightPredicateTruthV1, ...],
    tuple[BirthrightEligibilityTruthV1, ...],
    dict[tuple[str, str], bool],
]:
    subject_ids = sorted(
        {
            indexes.atoms[cell.access_atom_id].subject_id
            for cell in corpus.evaluation_cells
        }
    )
    predicate_rows: list[BirthrightPredicateTruthV1] = []
    eligibility_rows: list[BirthrightEligibilityTruthV1] = []
    eligible: dict[tuple[str, str], bool] = {}
    for rule in intent.birthright_rules:
        rule_id = _intent_id(intent_digest, "birthright-rule", rule.rule_id)
        for subject_id in subject_ids:
            outcomes = tuple(
                _evaluate_birthright_predicate(predicate, profiles[subject_id])
                for predicate in rule.condition.predicates
            )
            for index, outcome in enumerate(outcomes):
                predicate_rows.append(
                    BirthrightPredicateTruthV1(
                        rule_id=rule_id,
                        subject_id=subject_id,
                        predicate_index=index,
                        result=outcome,
                    )
                )
            result = (
                all(outcomes)
                if rule.condition.operator is BirthrightConditionOperator.ALL
                else any(outcomes)
            )
            eligible[(rule.rule_id, subject_id)] = result
            eligibility_rows.append(
                BirthrightEligibilityTruthV1(
                    rule_id=rule_id,
                    subject_id=subject_id,
                    eligible=result,
                )
            )
    return (
        tuple(
            sorted(
                predicate_rows,
                key=lambda item: (item.rule_id, item.subject_id, item.predicate_index),
            )
        ),
        tuple(
            sorted(
                eligibility_rows,
                key=lambda item: (item.rule_id, item.subject_id),
            )
        ),
        eligible,
    )


def _evaluate_birthright_predicate(
    predicate: BirthrightPredicateV1, profile: _SubjectProfile
) -> bool:
    if isinstance(predicate, PrincipalKindIsV1):
        return profile.principal is not None and profile.principal.principal_kind in (
            predicate.values
        )
    if isinstance(predicate, EmploymentTypeIsV1):
        return (
            profile.principal is not None
            and profile.principal.principal_kind.value
            in {item.value for item in predicate.values}
        )
    if isinstance(predicate, TenantIsV1):
        return profile.tenant_id in predicate.tenant_ids
    if isinstance(predicate, UnitIsV1):
        return (
            profile.principal is not None
            and profile.principal.unit_id in predicate.unit_ids
        )
    return profile.account is not None and profile.account.account_kind in (
        predicate.values
    )


def _compile_cells(
    *,
    corpus: EnterpriseEvaluationCorpusV1,
    kernel: EnterpriseDirectoryRbacKernelV1,
    intent: EnterpriseDirectoryRbacIntentOverlayV1,
    indexes: _UniverseIndexes,
    actual_roles: _RoleFacts,
    intended_roles: _RoleFacts,
    session_facts: _SessionFacts,
    eligible: Mapping[tuple[str, str], bool],
    intent_digest: str,
    universe_digest: str,
    config: EnterpriseIdentityAccessCompileConfigV1,
    max_total_derivations: int,
) -> tuple[
    tuple[DirectoryRbacCellTruthV1, ...],
    tuple[AccessDerivationPathTruthV1, ...],
    tuple[AccessDerivationPathTruthV1, ...],
    tuple[BirthrightAssignmentTruthV1, ...],
    tuple[ApprovedExceptionTruthV1, ...],
]:
    actual_paths_by_subject = _group_role_paths(actual_roles.role_paths)
    intended_paths_by_subject = _group_role_paths(intended_roles.role_paths)
    actual_grants = _group_grants(
        (item.role_id, item.permission_id, item.edge_id) for item in kernel.role_grants
    )
    intended_grants = _group_grants(
        (
            item.role_id,
            item.permission_id,
            _truth_id(
                universe_digest,
                "intended-role-grant",
                intent_digest,
                item.role_id,
                item.permission_id,
            ),
        )
        for item in intent.intended_role_grants
    )
    observed_sessions = {
        item.session_state_id: item for item in session_facts.observed_sessions
    }
    activation_by_session = {
        item.session_state_id: item for item in session_facts.activation_decisions
    }
    direct_by_subject_permission: dict[
        tuple[str, str], list[DirectoryDirectEntitlementV1]
    ] = defaultdict(list)
    for item in kernel.direct_entitlements:
        direct_by_subject_permission[(item.subject_id, item.permission_id)].append(item)
    actual_derivations: list[AccessDerivationPathTruthV1] = []
    intended_derivations: list[AccessDerivationPathTruthV1] = []
    cell_rows: list[DirectoryRbacCellTruthV1] = []
    assignment_rows: list[BirthrightAssignmentTruthV1] = []
    exception_rows: list[ApprovedExceptionTruthV1] = []
    actual_membership_sets: dict[str, set[str]] = defaultdict(set)
    for path in actual_roles.membership_paths:
        actual_membership_sets[path.subject_id].add(path.group_id)
    actual_role_sets = {
        item.subject_id: set(item.role_ids) for item in actual_roles.role_sets
    }
    assignments_by_atom: dict[
        str, list[tuple[BirthrightRuleV1, BirthrightAssignmentV1]]
    ] = defaultdict(list)
    for rule in intent.birthright_rules:
        for assignment in rule.assignments:
            for atom_id in assignment.access_atom_ids:
                assignments_by_atom[atom_id].append((rule, assignment))
    exceptions_by_subject_atom: dict[
        tuple[str, str], list[ApprovedAccessExceptionV1]
    ] = defaultdict(list)
    for exception in intent.approved_exceptions:
        for atom_id in exception.access_atom_ids:
            exceptions_by_subject_atom[(exception.subject_id, atom_id)].append(
                exception
            )
    emitted_derivations = 0
    for cell in corpus.evaluation_cells:
        atom = indexes.atoms[cell.access_atom_id]
        permission = indexes.permission_by_target_action[
            (atom.authorization_target_id, atom.action)
        ]
        actual_cell_paths = _actual_cell_paths(
            cell=cell,
            atom=atom,
            permission=permission,
            role_paths=actual_paths_by_subject.get(atom.subject_id, ()),
            role_dag_paths=actual_roles.role_dag_paths,
            grants=actual_grants,
            direct_entitlements=direct_by_subject_permission[
                (atom.subject_id, permission.permission_id)
            ],
            observed_session=(
                observed_sessions.get(cell.session_state_id)
                if cell.session_state_id is not None
                else None
            ),
            universe_digest=universe_digest,
            max_paths=config.budget.max_derivations_per_cell,
            prior_paths=0,
        )
        intended_cell_paths = _intended_cell_paths(
            cell=cell,
            atom=atom,
            permission=permission,
            role_paths=intended_paths_by_subject.get(atom.subject_id, ()),
            role_dag_paths=intended_roles.role_dag_paths,
            grants=intended_grants,
            activation=(
                activation_by_session.get(cell.session_state_id)
                if cell.session_state_id is not None
                else None
            ),
            universe_digest=universe_digest,
            intent_digest=intent_digest,
            max_paths=config.budget.max_derivations_per_cell,
            prior_paths=len(actual_cell_paths),
        )
        emitted_derivations += len(actual_cell_paths) + len(intended_cell_paths)
        _require_derivation_capacity(
            emitted_derivations,
            max_total_derivations,
        )
        actual_derivations.extend(actual_cell_paths)
        intended_derivations.extend(intended_cell_paths)

        active_assignment_ids: list[str] = []
        for rule, assignment in assignments_by_atom.get(atom.access_atom_id, ()):
            rule_id = _intent_id(intent_digest, "birthright-rule", rule.rule_id)
            is_eligible = eligible[(rule.rule_id, atom.subject_id)]
            assignment_id = _intent_id(
                intent_digest,
                "birthright-assignment",
                rule.rule_id,
                assignment.assignment_id,
            )
            if is_eligible:
                active_assignment_ids.append(assignment_id)
            assignment_rows.append(
                BirthrightAssignmentTruthV1(
                    rule_id=rule_id,
                    assignment_id=assignment_id,
                    cell_id=cell.cell_id,
                    subject_id=atom.subject_id,
                    access_atom_id=atom.access_atom_id,
                    eligible=is_eligible,
                    assignment_satisfied=_assignment_satisfied(
                        assignment.target_kind,
                        assignment.target_id,
                        permission.permission_id,
                        atom.subject_id,
                        actual_membership_sets,
                        actual_role_sets,
                        bool(actual_cell_paths),
                    ),
                )
            )
        active_exception_ids: list[str] = []
        for exception in exceptions_by_subject_atom.get(
            (atom.subject_id, atom.access_atom_id), ()
        ):
            exception_id = _intent_id(
                intent_digest, "approved-exception", exception.exception_id
            )
            active = _active(
                cell.tick, exception.valid_from_tick, exception.valid_until_tick
            )
            exception_rows.append(
                ApprovedExceptionTruthV1(
                    exception_id=exception_id,
                    cell_id=cell.cell_id,
                    active=active,
                )
            )
            if active:
                active_exception_ids.append(exception_id)
        birthright = _decision(bool(active_assignment_ids))
        intended = _decision(
            bool(active_assignment_ids or active_exception_ids or intended_cell_paths)
        )
        effective = _decision(bool(actual_cell_paths))
        binding_status, lifecycle_status = _runtime_gates(
            atom.subject_id, cell.tick, indexes
        )
        runtime_allowed = (
            effective is AuthorizationDecision.ALLOW
            and binding_status
            in (BindingStatus.NOT_APPLICABLE, BindingStatus.MATCHES_CANONICAL)
            and lifecycle_status
            in (LifecycleStatus.NOT_APPLICABLE, LifecycleStatus.ACTIVE)
        )
        cell_rows.append(
            DirectoryRbacCellTruthV1(
                cell_id=cell.cell_id,
                subject_id=atom.subject_id,
                tick=cell.tick,
                birthright_decision=birthright,
                intended_decision=intended,
                effective_decision=effective,
                final_decision=_decision(runtime_allowed),
                reconciliation=_reconciliation(intended, effective),
                binding_status=binding_status,
                lifecycle_status=lifecycle_status,
                birthright_assignment_ids=tuple(sorted(active_assignment_ids)),
                approved_exception_ids=tuple(sorted(active_exception_ids)),
                intended_path_ids=tuple(
                    sorted(item.path_id for item in intended_cell_paths)
                ),
                effective_path_ids=tuple(
                    sorted(item.path_id for item in actual_cell_paths)
                ),
            )
        )
    return (
        tuple(sorted(cell_rows, key=lambda item: item.cell_id)),
        tuple(sorted(actual_derivations, key=lambda item: item.path_id)),
        tuple(sorted(intended_derivations, key=lambda item: item.path_id)),
        tuple(
            sorted(
                assignment_rows,
                key=lambda item: (
                    item.rule_id,
                    item.assignment_id,
                    item.cell_id,
                ),
            )
        ),
        tuple(
            sorted(
                exception_rows,
                key=lambda item: (item.exception_id, item.cell_id),
            )
        ),
    )


def _group_role_paths(
    paths: Iterable[AuthorizedRolePathTruthV1],
) -> dict[str, tuple[AuthorizedRolePathTruthV1, ...]]:
    grouped: dict[str, list[AuthorizedRolePathTruthV1]] = defaultdict(list)
    for path in paths:
        grouped[path.subject_id].append(path)
    return {
        key: tuple(sorted(value, key=lambda item: item.path_id))
        for key, value in grouped.items()
    }


def _group_grants(
    grants: Iterable[tuple[str, str, str]],
) -> dict[str, tuple[tuple[str, str], ...]]:
    grouped: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for role_id, permission_id, source_id in grants:
        grouped[role_id].append((permission_id, source_id))
    return {key: tuple(sorted(value)) for key, value in grouped.items()}


def _actual_cell_paths(
    *,
    cell: AccessEvaluationCellV1,
    atom: AccessAtomV1,
    permission: EnterprisePermissionV1,
    role_paths: tuple[AuthorizedRolePathTruthV1, ...],
    role_dag_paths: Mapping[str, tuple[tuple[str, ...], ...]],
    grants: Mapping[str, tuple[tuple[str, str], ...]],
    direct_entitlements: list[DirectoryDirectEntitlementV1],
    observed_session: ObservedSessionTruthV1 | None,
    universe_digest: str,
    max_paths: int,
    prior_paths: int,
) -> tuple[AccessDerivationPathTruthV1, ...]:
    result: list[AccessDerivationPathTruthV1] = []
    for entitlement in direct_entitlements:
        if _active(
            cell.tick,
            entitlement.valid_from_tick,
            entitlement.valid_until_tick,
        ):
            source_id = entitlement.entitlement_id
            _append_bounded_cell_path(
                result,
                _access_path(
                    universe_digest,
                    cell=cell,
                    atom=atom,
                    permission=permission,
                    mechanism=DerivationMechanism.DIRECT_ENTITLEMENT,
                    membership_path=(),
                    role_path=(),
                    source_id=source_id,
                ),
                prior_paths=prior_paths,
                max_paths=max_paths,
            )
    if cell.session_state_id is None:
        for authorized in role_paths:
            if any(
                permission_id == permission.permission_id
                for permission_id, _source_id in grants.get(authorized.role_id, ())
            ):
                source_id = next(
                    source_id
                    for permission_id, source_id in grants[authorized.role_id]
                    if permission_id == permission.permission_id
                )
                _append_bounded_cell_path(
                    result,
                    _access_path(
                        universe_digest,
                        cell=cell,
                        atom=atom,
                        permission=permission,
                        mechanism=DerivationMechanism.ROLE,
                        membership_path=authorized.group_path,
                        role_path=authorized.role_path,
                        source_id=f"{authorized.path_id}:{source_id}",
                    ),
                    prior_paths=prior_paths,
                    max_paths=max_paths,
                )
        return _deduplicate_paths(result)
    session = cast(ObservedSessionTruthV1, observed_session)
    for activated_role in session.usable_activated_role_ids:
        proofs = tuple(item for item in role_paths if item.role_id == activated_role)
        for proof in proofs:
            for suffix in role_dag_paths[activated_role]:
                grant_role = suffix[-1]
                for permission_id, grant_source_id in grants.get(grant_role, ()):
                    if permission_id != permission.permission_id:
                        continue
                    _append_bounded_cell_path(
                        result,
                        _access_path(
                            universe_digest,
                            cell=cell,
                            atom=atom,
                            permission=permission,
                            mechanism=DerivationMechanism.ROLE,
                            membership_path=proof.group_path,
                            role_path=(*proof.role_path, *suffix[1:]),
                            source_id=f"{proof.path_id}:{grant_source_id}",
                        ),
                        prior_paths=prior_paths,
                        max_paths=max_paths,
                    )
    return _deduplicate_paths(result)


def _intended_cell_paths(
    *,
    cell: AccessEvaluationCellV1,
    atom: AccessAtomV1,
    permission: EnterprisePermissionV1,
    role_paths: tuple[AuthorizedRolePathTruthV1, ...],
    role_dag_paths: Mapping[str, tuple[tuple[str, ...], ...]],
    grants: Mapping[str, tuple[tuple[str, str], ...]],
    activation: ActivationDecisionTruthV1 | None,
    universe_digest: str,
    intent_digest: str,
    max_paths: int,
    prior_paths: int,
) -> tuple[AccessDerivationPathTruthV1, ...]:
    if cell.session_state_id is None:
        usable_roles: set[str] | None = None
    elif (
        activation is not None
        and activation.expected_outcome is ActivationOutcome.ACCEPTED
    ):
        usable_roles = set(activation.requested_role_ids)
    else:
        usable_roles = set()
    result: list[AccessDerivationPathTruthV1] = []
    for proof in role_paths:
        if usable_roles is None:
            if any(
                permission_id == permission.permission_id
                for permission_id, _source_id in grants.get(proof.role_id, ())
            ):
                source_id = next(
                    source_id
                    for permission_id, source_id in grants[proof.role_id]
                    if permission_id == permission.permission_id
                )
                _append_bounded_cell_path(
                    result,
                    _access_path(
                        universe_digest,
                        cell=cell,
                        atom=atom,
                        permission=permission,
                        mechanism=DerivationMechanism.ROLE,
                        membership_path=proof.group_path,
                        role_path=proof.role_path,
                        source_id=f"{intent_digest}:{proof.path_id}:{source_id}",
                    ),
                    prior_paths=prior_paths,
                    max_paths=max_paths,
                )
            continue
        if proof.role_id not in usable_roles:
            continue
        for suffix in role_dag_paths[proof.role_id]:
            grant_role = suffix[-1]
            for permission_id, source_id in grants.get(grant_role, ()):
                if permission_id == permission.permission_id:
                    _append_bounded_cell_path(
                        result,
                        _access_path(
                            universe_digest,
                            cell=cell,
                            atom=atom,
                            permission=permission,
                            mechanism=DerivationMechanism.ROLE,
                            membership_path=proof.group_path,
                            role_path=(*proof.role_path, *suffix[1:]),
                            source_id=f"{intent_digest}:{proof.path_id}:{source_id}",
                        ),
                        prior_paths=prior_paths,
                        max_paths=max_paths,
                    )
    return _deduplicate_paths(result)


def _access_path(
    universe_digest: str,
    *,
    cell: AccessEvaluationCellV1,
    atom: AccessAtomV1,
    permission: EnterprisePermissionV1,
    mechanism: DerivationMechanism,
    membership_path: tuple[str, ...],
    role_path: tuple[str, ...],
    source_id: str,
) -> AccessDerivationPathTruthV1:
    path_id = _truth_id(
        universe_digest,
        "access-derivation",
        cell.cell_id,
        mechanism.value,
        source_id,
        *membership_path,
        *role_path,
    )
    return AccessDerivationPathTruthV1(
        path_id=path_id,
        cell_id=cell.cell_id,
        mechanism=mechanism,
        subject_id=atom.subject_id,
        permission_id=permission.permission_id,
        membership_group_path=membership_path,
        role_path=role_path,
        source_record_id=source_id,
    )


def _append_bounded_cell_path(
    paths: list[AccessDerivationPathTruthV1],
    path: AccessDerivationPathTruthV1,
    *,
    prior_paths: int,
    max_paths: int,
) -> None:
    measured = prior_paths + len(paths) + 1
    if measured > max_paths:
        raise EnterpriseCompileError(
            "directory_rbac_cell_derivation_budget_exceeded",
            "one cell exceeds its derivation budget",
            measured=measured,
            allowed=max_paths,
        )
    paths.append(path)


def _deduplicate_paths(
    paths: Iterable[AccessDerivationPathTruthV1],
) -> tuple[AccessDerivationPathTruthV1, ...]:
    by_id = {item.path_id: item for item in paths}
    return tuple(sorted(by_id.values(), key=lambda item: item.path_id))


def _assignment_satisfied(
    kind: AssignmentTargetKind,
    target_id: str,
    permission_id: str,
    subject_id: str,
    memberships: Mapping[str, set[str]],
    role_sets: Mapping[str, set[str]],
    has_access_path: bool,
) -> bool:
    if kind is AssignmentTargetKind.GROUP:
        return target_id in memberships[subject_id]
    if kind is AssignmentTargetKind.ROLE:
        return target_id in role_sets[subject_id]
    return target_id == permission_id and has_access_path


def _runtime_gates(
    subject_id: str, tick: int, indexes: _UniverseIndexes
) -> tuple[BindingStatus, LifecycleStatus]:
    subject = indexes.subjects[subject_id]
    if subject.subject_kind is AccessSubjectKind.PRINCIPAL:
        return BindingStatus.NOT_APPLICABLE, LifecycleStatus.NOT_APPLICABLE
    canonical = indexes.canonical_principal_by_account.get(subject_id)
    observation = indexes.observation_by_account.get(subject_id)
    if observation is None:
        return BindingStatus.MISSING, LifecycleStatus.INACTIVE
    if observation.observed_principal_id is None:
        binding = BindingStatus.MISSING
    elif observation.observed_principal_id == canonical:
        binding = BindingStatus.MATCHES_CANONICAL
    else:
        binding = BindingStatus.MISMATCH
    if tick < observation.valid_from_tick:
        lifecycle = LifecycleStatus.NOT_YET_VALID
    elif (
        observation.valid_until_tick is not None
        and tick >= observation.valid_until_tick
    ):
        lifecycle = LifecycleStatus.EXPIRED
    elif observation.administrative_state is not AdministrativeState.ACTIVE:
        lifecycle = LifecycleStatus.INACTIVE
    else:
        lifecycle = LifecycleStatus.ACTIVE
    return binding, lifecycle


def _reconciliation(
    intended: AuthorizationDecision, effective: AuthorizationDecision
) -> ReconciliationOutcome:
    if intended is AuthorizationDecision.ALLOW:
        return (
            ReconciliationOutcome.ALIGNED_ALLOW
            if effective is AuthorizationDecision.ALLOW
            else ReconciliationOutcome.MISSING
        )
    return (
        ReconciliationOutcome.EXCESSIVE
        if effective is AuthorizationDecision.ALLOW
        else ReconciliationOutcome.ALIGNED_DENY
    )


def _decision(value: bool) -> AuthorizationDecision:
    return AuthorizationDecision.ALLOW if value else AuthorizationDecision.DENY


def _active(tick: int, start: int, end: int | None) -> bool:
    return tick >= start and (end is None or tick < end)


def _require_known_ids(
    values: Iterable[str], known: Mapping[str, object] | set[str], description: str
) -> None:
    if any(value not in known for value in values):
        raise EnterpriseCompileError(
            f"unknown_{description}",
            f"{description.replace('_', ' ')} does not resolve",
        )


def _check_truth_outer_safety(
    truth: CompiledEnterpriseDirectoryRbacTruthV1,
    config: EnterpriseIdentityAccessCompileConfigV1,
) -> None:
    records = 1 + sum(
        len(getattr(truth, field_name))
        for field_name in type(truth).model_fields
        if isinstance(getattr(truth, field_name), tuple)
    )
    if records > config.outer_safety.max_serialized_records:
        raise EnterpriseCompileError(
            "directory_rbac_truth_outer_record_limit_exceeded",
            "directory/RBAC truth exceeds the outer record cap",
            measured=records,
            allowed=config.outer_safety.max_serialized_records,
        )
    canonical_size = len(canonical_json_bytes(truth))
    if canonical_size > config.outer_safety.max_canonical_bytes:
        raise EnterpriseCompileError(
            "directory_rbac_truth_outer_byte_limit_exceeded",
            "directory/RBAC truth exceeds the outer byte cap",
            measured=canonical_size,
            allowed=config.outer_safety.max_canonical_bytes,
        )


def _truth_id(universe_digest: str, kind: str, *parts: str) -> str:
    return str(
        uuid5(
            ENTERPRISE_DIRECTORY_RBAC_TRUTH_RECORD_NAMESPACE_V1,
            encode_parts(
                (
                    ENTERPRISE_DIRECTORY_RBAC_COMPILER_VERSION,
                    universe_digest,
                    kind,
                    *parts,
                )
            ),
        )
    )


def _intent_id(intent_digest: str, kind: str, *logical_parts: str) -> str:
    return _truth_id(intent_digest, kind, *logical_parts)


__all__ = ["compile_enterprise_directory_rbac_truth"]
