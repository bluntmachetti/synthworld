"""Native directory/RBAC oracle semantics and invariance tests."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from typing import cast

import pytest
from pydantic import ValidationError

import synthworld.enterprise.rbac.reference as rbac_reference
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.compiler import EnterpriseCompileError
from synthworld.enterprise.models import (
    EnterpriseCanonicalBindingTruthV1,
    EnterpriseCompileOuterSafetyV1,
    EnterpriseIdentityAccessCompileBudgetV1,
    EnterpriseIdentityAccessCompileConfigV1,
    EnterpriseIdentityAccessCompileResultV1,
    EnterpriseIdentityAccessImportV1,
    EnterpriseIdentityAccessUniverseV1,
)
from synthworld.enterprise.rbac.common import (
    ActivationOutcome,
    AuthorizationDecision,
    BindingStatus,
    EmploymentType,
    LifecycleStatus,
    ReconciliationOutcome,
)
from synthworld.enterprise.rbac.compiler import (
    compile_enterprise_directory_rbac_truth,
)
from synthworld.enterprise.rbac.corpus_models import EnterpriseEvaluationCorpusV1
from synthworld.enterprise.rbac.models import (
    AccountKindIsV1,
    ApprovedAccessExceptionV1,
    CompiledEnterpriseDirectoryRbacTruthV1,
    DynamicSodConstraintV1,
    EmploymentTypeIsV1,
    EnterpriseDirectoryRbacIntentOverlayV1,
    EnterpriseDirectoryRbacKernelV1,
    EnterpriseRbacSessionStateInputV1,
    IntendedSubjectGroupMembershipV1,
    ObservedRbacSessionStateV1,
    PrincipalKindIsV1,
    StaticSodConstraintV1,
    TenantIsV1,
)
from synthworld.enterprise.rbac.reference import (
    ReferenceEnterpriseRbacInputsV1,
    reference_enterprise_rbac_inputs,
)


def _truth() -> tuple[
    ReferenceEnterpriseRbacInputsV1, CompiledEnterpriseDirectoryRbacTruthV1
]:
    reference = reference_enterprise_rbac_inputs()
    return reference, compile_enterprise_directory_rbac_truth(
        universe=reference.universe_result.public_universe,
        canonical_binding_truth=reference.universe_result.evaluator_canonical_binding_truth,
        corpus=reference.corpus_result.public_corpus,
        directory_rbac_kernel=reference.kernel,
        session_state=reference.session_state,
        directory_rbac_intent=reference.intent,
    )


def _compile_changed(
    reference: ReferenceEnterpriseRbacInputsV1,
    *,
    universe: EnterpriseIdentityAccessUniverseV1 | None = None,
    binding: EnterpriseCanonicalBindingTruthV1 | None = None,
    corpus: EnterpriseEvaluationCorpusV1 | None = None,
    kernel: EnterpriseDirectoryRbacKernelV1 | None = None,
    intent: EnterpriseDirectoryRbacIntentOverlayV1 | None = None,
    session: EnterpriseRbacSessionStateInputV1 | None = None,
    config: EnterpriseIdentityAccessCompileConfigV1 | None = None,
) -> CompiledEnterpriseDirectoryRbacTruthV1:
    return compile_enterprise_directory_rbac_truth(
        universe=universe or reference.universe_result.public_universe,
        canonical_binding_truth=(
            binding or reference.universe_result.evaluator_canonical_binding_truth
        ),
        corpus=corpus or reference.corpus_result.public_corpus,
        directory_rbac_kernel=kernel or reference.kernel,
        session_state=session or reference.session_state,
        directory_rbac_intent=intent or reference.intent,
        compile_config=config,
    )


def _bind_changed_universe(
    reference: ReferenceEnterpriseRbacInputsV1,
    universe: EnterpriseIdentityAccessUniverseV1,
) -> tuple[
    EnterpriseCanonicalBindingTruthV1,
    EnterpriseEvaluationCorpusV1,
    EnterpriseDirectoryRbacKernelV1,
    EnterpriseDirectoryRbacIntentOverlayV1,
    EnterpriseRbacSessionStateInputV1,
]:
    universe_digest = synthetic_digest(canonical_json_bytes(universe))
    binding = reference.universe_result.evaluator_canonical_binding_truth.model_copy(
        update={"identity_access_universe_digest": universe_digest}
    )
    corpus = reference.corpus_result.public_corpus.model_copy(
        update={"identity_access_universe_digest": universe_digest}
    )
    corpus_digest = synthetic_digest(canonical_json_bytes(corpus))
    kernel = reference.kernel.model_copy(
        update={"identity_access_universe_digest": universe_digest}
    )
    intent = reference.intent.model_copy(
        update={
            "identity_access_universe_digest": universe_digest,
            "evaluation_corpus_digest": corpus_digest,
        }
    )
    session = reference.session_state.model_copy(
        update={"evaluation_corpus_digest": corpus_digest}
    )
    return binding, corpus, kernel, intent, session


def _bind_changed_corpus(
    reference: ReferenceEnterpriseRbacInputsV1,
    corpus: EnterpriseEvaluationCorpusV1,
) -> tuple[EnterpriseDirectoryRbacIntentOverlayV1, EnterpriseRbacSessionStateInputV1]:
    corpus_digest = synthetic_digest(canonical_json_bytes(corpus))
    return (
        reference.intent.model_copy(update={"evaluation_corpus_digest": corpus_digest}),
        reference.session_state.model_copy(
            update={"evaluation_corpus_digest": corpus_digest}
        ),
    )


def _bind_changed_config(
    reference: ReferenceEnterpriseRbacInputsV1,
    config: EnterpriseIdentityAccessCompileConfigV1,
) -> tuple[
    EnterpriseEvaluationCorpusV1,
    EnterpriseDirectoryRbacKernelV1,
    EnterpriseDirectoryRbacIntentOverlayV1,
    EnterpriseRbacSessionStateInputV1,
]:
    config_digest = synthetic_digest(canonical_json_bytes(config))
    corpus = reference.corpus_result.public_corpus.model_copy(
        update={"compile_config_digest": config_digest}
    )
    kernel = reference.kernel.model_copy(
        update={"compile_config_digest": config_digest}
    )
    intent, session = _bind_changed_corpus(reference, corpus)
    return corpus, kernel, intent, session


def test_reference_truth_is_deterministic_complete_and_cell_invariant() -> None:
    reference, truth = _truth()
    second = compile_enterprise_directory_rbac_truth(
        universe=reference.universe_result.public_universe,
        canonical_binding_truth=reference.universe_result.evaluator_canonical_binding_truth,
        corpus=reference.corpus_result.public_corpus,
        directory_rbac_kernel=reference.kernel,
        session_state=reference.session_state,
        directory_rbac_intent=reference.intent,
    )
    assert canonical_json_bytes(second) == canonical_json_bytes(truth)
    assert tuple(item.cell_id for item in truth.cells) == tuple(
        item.cell_id for item in reference.corpus_result.public_corpus.evaluation_cells
    )
    assert len(truth.cells) == 19
    assert Counter(item.reconciliation for item in truth.cells) == {
        ReconciliationOutcome.ALIGNED_ALLOW: 14,
        ReconciliationOutcome.ALIGNED_DENY: 1,
        ReconciliationOutcome.EXCESSIVE: 3,
        ReconciliationOutcome.MISSING: 1,
    }


def test_toggling_intent_and_sod_changes_truth_only_inside_frozen_cells() -> None:
    reference = reference_enterprise_rbac_inputs()
    universe_before = canonical_json_bytes(reference.universe_result.public_universe)
    corpus_before = canonical_json_bytes(reference.corpus_result.public_corpus)
    stripped = reference.intent.model_copy(
        update={
            "birthright_rules": (),
            "approved_exceptions": (),
            "intended_memberships": (),
            "intended_group_nesting": (),
            "intended_group_role_assignments": (),
            "intended_subject_role_assignments": (),
            "intended_role_hierarchy": (),
            "intended_role_grants": (),
            "ssd_constraints": (),
            "dsd_constraints": (),
        }
    )
    truth = _compile_changed(reference, intent=stripped)
    assert (
        canonical_json_bytes(reference.universe_result.public_universe)
        == universe_before
    )
    assert canonical_json_bytes(reference.corpus_result.public_corpus) == corpus_before
    assert tuple(item.cell_id for item in truth.cells) == tuple(
        item.cell_id for item in reference.corpus_result.public_corpus.evaluation_cells
    )
    assert truth.birthright_assignments == ()
    assert truth.ssd_evaluations == ()
    assert truth.dsd_evaluations == ()


def test_group_nesting_role_hierarchy_and_diamond_paths_remain_distinct() -> None:
    _reference, truth = _truth()
    role_sets = {item.subject_id: item.role_ids for item in truth.authorized_role_sets}
    agent_rows = tuple(
        row for row in truth.activation_decisions if not row.unauthorized_role_requested
    )
    assert len(agent_rows) == 1
    agent = agent_rows[0]
    assert len(role_sets[agent.subject_id]) == 2
    employee = next(
        row for row in truth.activation_decisions if row.unauthorized_role_requested
    )
    assert len(role_sets[employee.subject_id]) == 1
    redundant = tuple(item for item in truth.cells if len(item.effective_path_ids) >= 3)
    assert redundant
    assert all(
        len({path_id for path_id in item.effective_path_ids})
        == len(item.effective_path_ids)
        for item in redundant
    )


def test_activation_authorization_and_dsd_reasons_are_independent() -> None:
    reference, truth = _truth()
    reasons = {
        (item.unauthorized_role_requested, item.dsd_cardinality_met)
        for item in truth.activation_decisions
    }
    assert reasons == {(True, False), (False, True)}
    assert all(
        item.expected_outcome is ActivationOutcome.REJECTED
        for item in truth.activation_decisions
    )
    assert all(
        item.observed_outcome is ActivationOutcome.ACCEPTED
        for item in truth.observed_sessions
    )
    dsd_invalid = next(
        item for item in truth.observed_sessions if not item.dsd_compliant
    )
    dsd_corpus_cell = next(
        item
        for item in reference.corpus_result.public_corpus.evaluation_cells
        if item.session_state_id == dsd_invalid.session_state_id
    )
    dsd_cell = next(
        item for item in truth.cells if item.cell_id == dsd_corpus_cell.cell_id
    )
    assert dsd_cell.effective_decision is AuthorizationDecision.ALLOW
    unauthorized = next(
        item for item in truth.observed_sessions if item.unauthorized_activated_role_ids
    )
    assert unauthorized.usable_activated_role_ids == ()


def test_binding_and_lifecycle_are_gates_not_policy_rewrites() -> None:
    _reference, truth = _truth()
    account_cells = tuple(
        item
        for item in truth.cells
        if item.binding_status is not BindingStatus.NOT_APPLICABLE
    )
    statuses = {(item.binding_status, item.lifecycle_status) for item in account_cells}
    assert (BindingStatus.MATCHES_CANONICAL, LifecycleStatus.ACTIVE) in statuses
    assert (BindingStatus.MATCHES_CANONICAL, LifecycleStatus.INACTIVE) in statuses
    assert (BindingStatus.MISMATCH, LifecycleStatus.ACTIVE) in statuses
    assert (BindingStatus.MISSING, LifecycleStatus.ACTIVE) in statuses
    gated = tuple(
        item
        for item in account_cells
        if item.effective_decision is AuthorizationDecision.ALLOW
        and item.final_decision is AuthorizationDecision.DENY
    )
    assert len(gated) >= 3


def test_birthright_exception_ssd_and_half_open_truth_are_separate() -> None:
    _reference, truth = _truth()
    assert {item.result for item in truth.birthright_predicates} == {False, True}
    assert {item.eligible for item in truth.birthright_eligibility} == {False, True}
    assert any(item.assignment_satisfied for item in truth.birthright_assignments)
    assert any(not item.assignment_satisfied for item in truth.birthright_assignments)
    assert any(item.active for item in truth.approved_exceptions)
    assert sum(item.violated for item in truth.ssd_evaluations) == 2
    expired = next(item for item in truth.cells if item.tick == 20)
    assert expired.lifecycle_status is LifecycleStatus.EXPIRED
    assert expired.effective_decision is AuthorizationDecision.DENY


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("binding", "canonical_binding_universe_digest_mismatch"),
        ("corpus", "rbac_corpus_universe_digest_mismatch"),
        ("kernel", "rbac_kernel_universe_digest_mismatch"),
        ("intent_universe", "rbac_intent_universe_digest_mismatch"),
        ("intent_corpus", "rbac_intent_corpus_digest_mismatch"),
        ("session", "rbac_session_corpus_digest_mismatch"),
    ],
)
def test_digest_mismatches_fail_before_semantic_evaluation(
    field: str, code: str
) -> None:
    reference = reference_enterprise_rbac_inputs()
    binding = reference.universe_result.evaluator_canonical_binding_truth
    corpus = reference.corpus_result.public_corpus
    kernel = reference.kernel
    intent = reference.intent
    session = reference.session_state
    bad_digest = binding.identity_access_universe_digest.model_copy(
        update={"value": "0" * 64}
    )
    if field == "binding":
        binding = binding.model_copy(
            update={"identity_access_universe_digest": bad_digest}
        )
    elif field == "corpus":
        corpus = corpus.model_copy(
            update={"identity_access_universe_digest": bad_digest}
        )
    elif field == "kernel":
        kernel = kernel.model_copy(
            update={"identity_access_universe_digest": bad_digest}
        )
    elif field == "intent_universe":
        intent = intent.model_copy(
            update={"identity_access_universe_digest": bad_digest}
        )
    elif field == "intent_corpus":
        intent = intent.model_copy(update={"evaluation_corpus_digest": bad_digest})
    else:
        session = session.model_copy(update={"evaluation_corpus_digest": bad_digest})
    with pytest.raises(EnterpriseCompileError, match=code):
        compile_enterprise_directory_rbac_truth(
            universe=reference.universe_result.public_universe,
            canonical_binding_truth=binding,
            corpus=corpus,
            directory_rbac_kernel=kernel,
            session_state=session,
            directory_rbac_intent=intent,
        )


def test_intent_and_session_models_reject_unsafe_or_ambiguous_shapes() -> None:
    reference = reference_enterprise_rbac_inputs()
    principal_kind = reference.universe_result.public_universe.principals[
        0
    ].principal_kind
    with pytest.raises(ValidationError, match="duplicate_principal_kind"):
        PrincipalKindIsV1(values=(principal_kind, principal_kind))
    with pytest.raises(ValidationError, match="duplicate_employment_type"):
        EmploymentTypeIsV1(values=(EmploymentType.EMPLOYEE,) * 2)
    with pytest.raises(ValidationError, match="duplicate_account_kind"):
        AccountKindIsV1(
            values=(reference.universe_result.public_universe.accounts[0].account_kind,)
            * 2
        )
    with pytest.raises(ValidationError, match="cardinality_exceeds"):
        StaticSodConstraintV1(
            constraint_id="bad-ssd",
            tenant_id="tenant",
            role_ids=("one", "two"),
            cardinality=3,
            subject_ids=("subject",),
        )
    with pytest.raises(ValidationError, match="cardinality_exceeds"):
        DynamicSodConstraintV1(
            constraint_id="bad-dsd",
            tenant_id="tenant",
            role_ids=("one", "two"),
            cardinality=3,
            subject_ids=("subject",),
        )
    with pytest.raises(ValidationError, match="exception_validity"):
        ApprovedAccessExceptionV1(
            exception_id="bad-exception",
            subject_id="subject",
            access_atom_ids=("atom",),
            owner_principal_id="owner",
            reason=reference.intent.approved_exceptions[0].reason,
            valid_from_tick=1,
            valid_until_tick=1,
        )
    with pytest.raises(ValidationError, match="rejected_session_has"):
        ObservedRbacSessionStateV1(
            session_state_id="session",
            observed_outcome=ActivationOutcome.REJECTED,
            activated_role_ids=("role",),
            observed_at_tick=0,
            revision_id="revision",
        )
    account_observation = reference.kernel.account_observations[0].model_dump()
    account_observation["valid_until_tick"] = account_observation["valid_from_tick"]
    with pytest.raises(ValidationError, match="directory_account_validity"):
        type(reference.kernel.account_observations[0]).model_validate(
            account_observation
        )
    entitlement = reference.kernel.direct_entitlements[0].model_dump()
    entitlement["valid_until_tick"] = entitlement["valid_from_tick"]
    with pytest.raises(ValidationError, match="directory_entitlement_validity"):
        type(reference.kernel.direct_entitlements[0]).model_validate(entitlement)
    with pytest.raises(ValidationError, match="observed_session_validity"):
        ObservedRbacSessionStateV1(
            session_state_id="session",
            observed_outcome=ActivationOutcome.ACCEPTED,
            observed_at_tick=2,
            valid_until_tick=2,
            revision_id="revision",
        )


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("unknown_account", "unknown_kernel_account"),
        ("unknown_principal", "unknown_kernel_observed_principal"),
        ("cross_tenant_binding", "cross_tenant_kernel_binding"),
        ("unknown_relation", "unknown_kernel_membership_reference"),
        ("cross_tenant_relation", "cross_tenant_kernel_relation"),
    ],
)
def test_compiler_rejects_invalid_opaque_kernel_references(
    mutation: str, code: str
) -> None:
    reference = reference_enterprise_rbac_inputs()
    universe = reference.universe_result.public_universe
    binding = reference.universe_result.evaluator_canonical_binding_truth
    corpus = reference.corpus_result.public_corpus
    kernel = reference.kernel
    intent = reference.intent
    session = reference.session_state
    if mutation == "unknown_account":
        observation = kernel.account_observations[0].model_copy(
            update={"account_id": "unknown"}
        )
        kernel = kernel.model_copy(
            update={
                "account_observations": (observation, *kernel.account_observations[1:])
            }
        )
    elif mutation == "unknown_principal":
        observation = next(
            item
            for item in kernel.account_observations
            if item.observed_principal_id is not None
        ).model_copy(update={"observed_principal_id": "unknown"})
        kernel = kernel.model_copy(
            update={
                "account_observations": tuple(
                    observation if item.account_id == observation.account_id else item
                    for item in kernel.account_observations
                )
            }
        )
    elif mutation == "cross_tenant_binding":
        observed_id = next(
            item.observed_principal_id
            for item in kernel.account_observations
            if item.observed_principal_id is not None
        )
        principals = tuple(
            item.model_copy(update={"tenant_id": "other-tenant"})
            if item.principal_id == observed_id
            else item
            for item in universe.principals
        )
        universe = universe.model_copy(update={"principals": principals})
        binding, corpus, kernel, intent, session = _bind_changed_universe(
            reference, universe
        )
    elif mutation == "unknown_relation":
        membership = kernel.memberships[0].model_copy(update={"group_id": "unknown"})
        kernel = kernel.model_copy(
            update={"memberships": (membership, *kernel.memberships[1:])}
        )
    else:
        group_id = kernel.memberships[0].group_id
        groups = tuple(
            item.model_copy(update={"tenant_id": "other-tenant"})
            if item.group_id == group_id
            else item
            for item in universe.groups
        )
        universe = universe.model_copy(update={"groups": groups})
        binding, corpus, kernel, intent, session = _bind_changed_universe(
            reference, universe
        )
    with pytest.raises(EnterpriseCompileError, match=code):
        _compile_changed(
            reference,
            universe=universe,
            binding=binding,
            corpus=corpus,
            kernel=kernel,
            intent=intent,
            session=session,
        )


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("unknown_predicate_tenant", "unknown_predicate_tenant"),
        ("unknown_target", "unknown_birthright_assignment_target"),
        ("permission_scope", "birthright_permission_scope_mismatch"),
        ("unknown_exception", "unknown_approved_exception_reference"),
        ("exception_subject", "approved_exception_subject_mismatch"),
        ("unknown_intended", "unknown_intended_rbac_reference"),
    ],
)
def test_compiler_rejects_invalid_intent_references(mutation: str, code: str) -> None:
    reference = reference_enterprise_rbac_inputs()
    intent = reference.intent
    if mutation == "unknown_predicate_tenant":
        rule = next(
            item
            for item in intent.birthright_rules
            if any(
                isinstance(predicate, TenantIsV1)
                for predicate in item.condition.predicates
            )
        )
        predicates = tuple(
            item.model_copy(update={"tenant_ids": ("unknown",)})
            if isinstance(item, TenantIsV1)
            else item
            for item in rule.condition.predicates
        )
        rule = rule.model_copy(
            update={
                "condition": rule.condition.model_copy(
                    update={"predicates": predicates}
                )
            }
        )
        intent = intent.model_copy(
            update={
                "birthright_rules": tuple(
                    rule if item.rule_id == rule.rule_id else item
                    for item in intent.birthright_rules
                )
            }
        )
    elif mutation in {"unknown_target", "permission_scope"}:
        rule = next(
            item
            for item in intent.birthright_rules
            if item.assignments[0].target_kind.value == "permission"
        )
        assignment = rule.assignments[0]
        target_id = "unknown"
        if mutation == "permission_scope":
            target_id = next(
                item.permission_id
                for item in reference.universe_result.public_universe.permissions
                if item.permission_id != assignment.target_id
            )
        rule = rule.model_copy(
            update={
                "assignments": (assignment.model_copy(update={"target_id": target_id}),)
            }
        )
        intent = intent.model_copy(
            update={
                "birthright_rules": tuple(
                    rule if item.rule_id == rule.rule_id else item
                    for item in intent.birthright_rules
                )
            }
        )
    elif mutation in {"unknown_exception", "exception_subject"}:
        exception = intent.approved_exceptions[0]
        subject_id = "unknown"
        if mutation == "exception_subject":
            atom_subject = next(
                item.subject_id
                for item in reference.universe_result.public_universe.access_atoms
                if item.access_atom_id == exception.access_atom_ids[0]
            )
            subject_id = next(
                item.subject_id
                for item in reference.universe_result.public_universe.access_subjects
                if item.subject_id != atom_subject
            )
        intent = intent.model_copy(
            update={
                "approved_exceptions": (
                    exception.model_copy(update={"subject_id": subject_id}),
                )
            }
        )
    else:
        relation = intent.intended_memberships[0].model_copy(
            update={"group_id": "unknown"}
        )
        intent = intent.model_copy(
            update={
                "intended_memberships": (relation, *intent.intended_memberships[1:])
            }
        )
    with pytest.raises(EnterpriseCompileError, match=code):
        _compile_changed(reference, intent=intent)


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("birthright", "cross_tenant_birthright_assignment"),
        ("exception", "cross_tenant_approved_exception"),
        ("intended", "cross_tenant_intended_rbac_relation"),
    ],
)
def test_compiler_rejects_cross_tenant_intent_edges(mutation: str, code: str) -> None:
    reference = reference_enterprise_rbac_inputs()
    universe = reference.universe_result.public_universe
    intent = reference.intent
    if mutation in {"birthright", "intended"}:
        source_group = universe.groups[0]
        other_group = source_group.model_copy(
            update={"group_id": "other-tenant-group", "tenant_id": "other-tenant"}
        )
        universe = universe.model_copy(
            update={"groups": (*universe.groups, other_group)}
        )
    else:
        source_owner = universe.principals[0]
        other_owner = source_owner.model_copy(
            update={
                "principal_id": "other-tenant-owner",
                "tenant_id": "other-tenant",
            }
        )
        universe = universe.model_copy(
            update={"principals": (*universe.principals, other_owner)}
        )
    binding, corpus, kernel, bound_intent, session = _bind_changed_universe(
        reference, universe
    )
    if mutation == "birthright":
        rule = next(
            item
            for item in bound_intent.birthright_rules
            if item.assignments[0].target_kind.value == "group"
        )
        assignment = rule.assignments[0].model_copy(
            update={"target_id": "other-tenant-group"}
        )
        rule = rule.model_copy(update={"assignments": (assignment,)})
        intent = bound_intent.model_copy(
            update={
                "birthright_rules": tuple(
                    rule if item.rule_id == rule.rule_id else item
                    for item in bound_intent.birthright_rules
                )
            }
        )
    elif mutation == "exception":
        exception = bound_intent.approved_exceptions[0].model_copy(
            update={"owner_principal_id": "other-tenant-owner"}
        )
        intent = bound_intent.model_copy(update={"approved_exceptions": (exception,)})
    else:
        membership = IntendedSubjectGroupMembershipV1(
            subject_id=bound_intent.intended_memberships[0].subject_id,
            group_id="other-tenant-group",
        )
        intent = bound_intent.model_copy(
            update={
                "intended_memberships": (
                    membership,
                    *bound_intent.intended_memberships,
                )
            }
        )
    with pytest.raises(EnterpriseCompileError, match=code):
        _compile_changed(
            reference,
            universe=universe,
            binding=binding,
            corpus=corpus,
            kernel=kernel,
            intent=intent,
            session=session,
        )


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("constraint_count", "sod_constraint_budget_exceeded"),
        ("role_width", "sod_role_set_width_budget_exceeded"),
        ("unknown_tenant", "unknown_sod_tenant"),
        ("unknown_role", "unknown_sod_role"),
        ("evaluation_count", "sod_evaluation_budget_exceeded"),
    ],
)
def test_sod_constraints_have_independent_validation_and_budgets(
    mutation: str, code: str
) -> None:
    reference = reference_enterprise_rbac_inputs()
    intent = reference.intent
    config = EnterpriseIdentityAccessCompileConfigV1()
    if mutation == "unknown_tenant":
        constraint = intent.ssd_constraints[0].model_copy(
            update={"tenant_id": "unknown"}
        )
        intent = intent.model_copy(update={"ssd_constraints": (constraint,)})
    elif mutation == "unknown_role":
        constraint = intent.ssd_constraints[0].model_copy(
            update={"role_ids": ("unknown", intent.ssd_constraints[0].role_ids[1])}
        )
        intent = intent.model_copy(update={"ssd_constraints": (constraint,)})
    else:
        budget_update = {
            "constraint_count": {"max_sod_constraints": 1},
            "role_width": {"max_sod_role_set_width": 1},
            "evaluation_count": {"max_sod_evaluations": 1},
        }[mutation]
        config = config.model_copy(
            update={
                "budget": config.budget.model_copy(update=budget_update),
            }
        )
    if mutation in {"constraint_count", "role_width", "evaluation_count"}:
        corpus, kernel, bound_intent, session = _bind_changed_config(reference, config)
        if intent is reference.intent:
            intent = bound_intent
        with pytest.raises(EnterpriseCompileError, match=code):
            _compile_changed(
                reference,
                corpus=corpus,
                kernel=kernel,
                intent=intent,
                session=session,
                config=config,
            )
    else:
        with pytest.raises(EnterpriseCompileError, match=code):
            _compile_changed(reference, intent=intent)


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("cardinality", "observed_session_state_cardinality"),
        ("tick", "observed_session_tick_mismatch"),
        ("slot_validity", "observed_session_exceeds_slot_validity"),
        ("slot_unbounded", "observed_session_exceeds_slot_validity"),
        ("unknown_role", "unknown_observed_activated_role"),
        ("cell_unknown", "cell_session_state_not_observed"),
        ("cell_expired", "cell_at_or_after_observed_session_expiry"),
    ],
)
def test_observed_session_state_is_bounded_by_the_frozen_corpus(
    mutation: str, code: str
) -> None:
    reference = reference_enterprise_rbac_inputs()
    corpus = reference.corpus_result.public_corpus
    intent = reference.intent
    session = reference.session_state
    if mutation == "cardinality":
        session = session.model_copy(update={"sessions": session.sessions[1:]})
    elif mutation in {"tick", "slot_validity", "slot_unbounded", "unknown_role"}:
        observation = session.sessions[0]
        if mutation == "tick":
            update: dict[str, object] = {
                "observed_at_tick": observation.observed_at_tick + 1
            }
        elif mutation == "slot_validity":
            update = {"valid_until_tick": 11}
        elif mutation == "slot_unbounded":
            update = {"valid_until_tick": None}
        else:
            update = {"activated_role_ids": ("unknown",)}
        observation = observation.model_copy(update=update)
        session = session.model_copy(
            update={"sessions": (observation, *session.sessions[1:])}
        )
    else:
        target_cell = next(
            item
            for item in corpus.evaluation_cells
            if item.session_state_id is not None
        )
        if mutation == "cell_unknown":
            target_cell = target_cell.model_copy(
                update={"session_state_id": "unknown-session"}
            )
        else:
            target_cell = target_cell.model_copy(update={"tick": 6})
            observation = next(
                item
                for item in session.sessions
                if item.session_state_id == target_cell.session_state_id
            ).model_copy(update={"valid_until_tick": 6})
            session = session.model_copy(
                update={
                    "sessions": tuple(
                        observation
                        if item.session_state_id == observation.session_state_id
                        else item
                        for item in session.sessions
                    )
                }
            )
        corpus = corpus.model_copy(
            update={
                "evaluation_cells": tuple(
                    target_cell if item.cell_id == target_cell.cell_id else item
                    for item in corpus.evaluation_cells
                )
            }
        )
        intent, bound_session = _bind_changed_corpus(reference, corpus)
        if mutation == "cell_unknown":
            session = bound_session
        else:
            session = session.model_copy(
                update={
                    "evaluation_corpus_digest": bound_session.evaluation_corpus_digest
                }
            )
    with pytest.raises(EnterpriseCompileError, match=code):
        _compile_changed(reference, corpus=corpus, intent=intent, session=session)


def test_cross_tenant_sod_and_observed_activation_are_separate_failures() -> None:
    reference = reference_enterprise_rbac_inputs()
    universe = reference.universe_result.public_universe
    other_role = universe.roles[0].model_copy(
        update={"role_id": "other-tenant-role", "tenant_id": "other-tenant"}
    )
    universe = universe.model_copy(update={"roles": (*universe.roles, other_role)})
    binding, corpus, kernel, intent, session = _bind_changed_universe(
        reference, universe
    )
    constraint = intent.ssd_constraints[0].model_copy(
        update={
            "role_ids": (
                intent.ssd_constraints[0].role_ids[0],
                other_role.role_id,
            )
        }
    )
    cross_sod = intent.model_copy(update={"ssd_constraints": (constraint,)})
    with pytest.raises(EnterpriseCompileError, match="cross_tenant_sod_constraint"):
        _compile_changed(
            reference,
            universe=universe,
            binding=binding,
            corpus=corpus,
            kernel=kernel,
            intent=cross_sod,
            session=session,
        )

    observation = session.sessions[0].model_copy(
        update={"activated_role_ids": (other_role.role_id,)}
    )
    cross_session = session.model_copy(
        update={"sessions": (observation, *session.sessions[1:])}
    )
    with pytest.raises(
        EnterpriseCompileError, match="cross_tenant_observed_activated_role"
    ):
        _compile_changed(
            reference,
            universe=universe,
            binding=binding,
            corpus=corpus,
            kernel=kernel,
            intent=intent,
            session=cross_session,
        )


def test_directory_rbac_semantic_work_uses_the_named_independent_budget() -> None:
    reference = reference_enterprise_rbac_inputs()
    config = EnterpriseIdentityAccessCompileConfigV1(
        budget=EnterpriseIdentityAccessCompileBudgetV1(max_directory_rbac_relations=23)
    )
    corpus, kernel, intent, session = _bind_changed_config(reference, config)
    with pytest.raises(
        EnterpriseCompileError, match="directory_rbac_semantic_budget_exceeded"
    ):
        _compile_changed(
            reference,
            corpus=corpus,
            kernel=kernel,
            intent=intent,
            session=session,
            config=config,
        )


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("max_group_depth", "intended_group_depth_budget_exceeded"),
        ("max_role_depth", "intended_role_depth_budget_exceeded"),
    ],
)
def test_intended_graphs_use_their_independent_depth_budgets(
    field: str, code: str
) -> None:
    reference = reference_enterprise_rbac_inputs()
    budget = EnterpriseIdentityAccessCompileBudgetV1().model_copy(update={field: 1})
    config = EnterpriseIdentityAccessCompileConfigV1(budget=budget)
    corpus, kernel, intent, session = _bind_changed_config(reference, config)
    with pytest.raises(EnterpriseCompileError, match=code):
        _compile_changed(
            reference,
            corpus=corpus,
            kernel=kernel,
            intent=intent,
            session=session,
            config=config,
        )


@pytest.mark.parametrize(
    ("limit", "code"),
    [
        ("role_paths", "directory_rbac_total_derivation_budget_exceeded"),
        ("cell_paths", "directory_rbac_cell_derivation_budget_exceeded"),
        ("total_paths", "directory_rbac_total_derivation_budget_exceeded"),
        ("records", "directory_rbac_truth_outer_record_limit_exceeded"),
        ("bytes", "directory_rbac_truth_outer_byte_limit_exceeded"),
    ],
)
def test_truth_path_and_outer_limits_are_independent(limit: str, code: str) -> None:
    reference = reference_enterprise_rbac_inputs()
    budget = EnterpriseIdentityAccessCompileBudgetV1()
    safety = EnterpriseCompileOuterSafetyV1()
    if limit == "role_paths":
        budget = budget.model_copy(update={"max_total_derivations": 25})
    elif limit == "cell_paths":
        budget = budget.model_copy(update={"max_derivations_per_cell": 4})
    elif limit == "total_paths":
        budget = budget.model_copy(update={"max_total_derivations": 98})
    elif limit == "records":
        safety = safety.model_copy(update={"max_serialized_records": 103})
    else:
        safety = safety.model_copy(update={"max_canonical_bytes": 1})
    config = EnterpriseIdentityAccessCompileConfigV1(
        budget=budget,
        outer_safety=safety,
    )
    corpus, kernel, intent, session = _bind_changed_config(reference, config)
    with pytest.raises(EnterpriseCompileError, match=code):
        _compile_changed(
            reference,
            corpus=corpus,
            kernel=kernel,
            intent=intent,
            session=session,
            config=config,
        )


def test_ineligible_birthright_inactive_exception_scoped_ssd_and_accepted_session() -> (
    None
):
    reference = reference_enterprise_rbac_inputs()
    intent = reference.intent
    employee_rule = next(
        item
        for item in intent.birthright_rules
        if item.rule_id == "employee-reader-birthright"
    )
    agent_kind = next(
        item.principal_kind
        for item in reference.universe_result.public_universe.principals
        if item.principal_kind.value == "agent"
    )
    employee_rule = employee_rule.model_copy(
        update={
            "condition": employee_rule.condition.model_copy(
                update={"predicates": (PrincipalKindIsV1(values=(agent_kind,)),)}
            )
        }
    )
    exception = intent.approved_exceptions[0].model_copy(
        update={"valid_from_tick": 1, "valid_until_tick": 2}
    )
    scoped_ssd = intent.ssd_constraints[0].model_copy(
        update={
            "subject_ids": (
                reference.universe_result.public_universe.access_subjects[0].subject_id,
            )
        }
    )
    intent = intent.model_copy(
        update={
            "birthright_rules": tuple(
                employee_rule if item.rule_id == employee_rule.rule_id else item
                for item in intent.birthright_rules
            ),
            "approved_exceptions": (exception,),
            "ssd_constraints": (scoped_ssd,),
            "dsd_constraints": (),
        }
    )
    truth = _compile_changed(reference, intent=intent)
    assert any(not item.eligible for item in truth.birthright_assignments)
    assert any(not item.active for item in truth.approved_exceptions)
    assert any(
        item.expected_outcome is ActivationOutcome.ACCEPTED
        for item in truth.activation_decisions
    )
    assert len(truth.ssd_evaluations) == 1


@pytest.mark.parametrize("lifecycle", ["missing", "not_yet_valid"])
def test_missing_and_not_yet_valid_account_observations_are_explicit(
    lifecycle: str,
) -> None:
    reference = reference_enterprise_rbac_inputs()
    kernel = reference.kernel
    account_id = kernel.account_observations[0].account_id
    if lifecycle == "missing":
        kernel = kernel.model_copy(
            update={
                "account_observations": tuple(
                    item
                    for item in kernel.account_observations
                    if item.account_id != account_id
                )
            }
        )
        expected = LifecycleStatus.INACTIVE
    else:
        observation = kernel.account_observations[0].model_copy(
            update={"valid_from_tick": 1}
        )
        kernel = kernel.model_copy(
            update={
                "account_observations": (
                    observation,
                    *kernel.account_observations[1:],
                )
            }
        )
        expected = LifecycleStatus.NOT_YET_VALID
    truth = _compile_changed(reference, kernel=kernel)
    assert any(
        item.subject_id == account_id and item.lifecycle_status is expected
        for item in truth.cells
    )


def test_reference_builder_guards_the_frozen_pr2_universe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = cast(
        Callable[..., EnterpriseIdentityAccessCompileResultV1],
        vars(rbac_reference)["compile_enterprise_identity_access_universe"],
    )
    calls = 0

    def divergent_compile(
        *,
        import_model: EnterpriseIdentityAccessImportV1,
        seed: int,
        config: EnterpriseIdentityAccessCompileConfigV1 | None = None,
    ) -> EnterpriseIdentityAccessCompileResultV1:
        nonlocal calls
        calls += 1
        result = original(import_model=import_model, seed=seed, config=config)
        if calls == 2:
            return EnterpriseIdentityAccessCompileResultV1(
                public_universe=result.public_universe.model_copy(
                    update={"seed": seed + 1}
                ),
                evaluator_canonical_binding_truth=(
                    result.evaluator_canonical_binding_truth
                ),
            )
        return result

    monkeypatch.setattr(
        rbac_reference,
        "compile_enterprise_identity_access_universe",
        divergent_compile,
    )
    with pytest.raises(RuntimeError, match="changed the frozen PR2 universe"):
        rbac_reference.reference_enterprise_rbac_inputs()
