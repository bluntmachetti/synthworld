"""Determinism, freeze, and complexity-firewall tests for universe compilation."""

from __future__ import annotations

from collections.abc import Iterable

import pytest

from synthworld.enterprise.canonical import canonical_json_bytes
from synthworld.enterprise.compiler import (
    EnterpriseCompileError,
    _validate_post_freeze_state,
    compile_enterprise_identity_access_universe,
)
from synthworld.enterprise.models import (
    AccountAllocationTemplateV1,
    AccountKind,
    AccountObservationV1,
    AccountSubjectAccessAtomRuleV1,
    AdministrativeState,
    CountSelectorV1,
    DirectEntitlementV1,
    EnterpriseCompileOuterSafetyV1,
    EnterpriseIdentityAccessCompileBudgetV1,
    EnterpriseIdentityAccessCompileConfigV1,
    EnterpriseIdentityAccessCompileResultV1,
    EnterpriseIdentityAccessImportV1,
    FractionSelectorV1,
    PrincipalKind,
    TargetKind,
    TenantTemplateV1,
    UnitKind,
)
from synthworld.enterprise.reference import (
    REFERENCE_NAMESPACE_SALT,
    reference_enterprise_identity_access_import,
)


def _compile(
    imported: EnterpriseIdentityAccessImportV1 | None = None,
    *,
    seed: int = 20_260_804,
    config: EnterpriseIdentityAccessCompileConfigV1 | None = None,
) -> EnterpriseIdentityAccessCompileResultV1:
    return compile_enterprise_identity_access_universe(
        import_model=imported or reference_enterprise_identity_access_import(),
        seed=seed,
        config=config,
    )


def _assert_recursive_synthetic(value: object) -> None:
    if isinstance(value, dict):
        assert value["synthetic"] is True
        for nested in value.values():
            if isinstance(nested, dict | list):
                _assert_recursive_synthetic(nested)
    elif isinstance(value, list):
        for nested in value:
            if isinstance(nested, dict | list):
                _assert_recursive_synthetic(nested)


def test_reference_universe_is_pinned_sparse_and_visibility_safe() -> None:
    imported = reference_enterprise_identity_access_import()
    result = _compile(imported)
    universe = result.public_universe
    truth = result.evaluator_canonical_binding_truth

    assert len(universe.principals) == 6
    assert len(universe.accounts) == 4
    assert len(universe.groups) == 2
    assert len(universe.roles) == 2
    assert len(universe.authorization_targets) == 2
    assert len(universe.permissions) == 4
    assert len(universe.access_atoms) == 16
    assert len(universe.access_subjects) == 10
    assert len(universe.relationship_anchors) == 16
    assert len(truth.bindings) == 4
    assert universe.tenants[0].tenant_id == "701dfa93-9a42-5fd7-9e66-f93f0c004730"
    assert universe.principals[0].principal_id == (
        "27bec596-b170-53f1-9d25-8031a404dbb9"
    )
    assert universe.accounts[0].account_id == "873fd7d6-15e2-5511-8136-eda36b6f43bf"
    assert universe.authorization_targets[0].authorization_target_id == (
        "a8f29d5c-4d89-575d-8709-8b3a55b148f4"
    )
    assert (
        truth.identity_access_universe_digest.value
        == "b4eae423689ede98d98858cae004f98d07fa5b0ac4774858500a4ba257946f4a"
    )
    assert all(
        "principal" not in item.model_dump(mode="json") for item in universe.accounts
    )
    assert {item.account_id for item in truth.bindings} == {
        item.account_id for item in universe.accounts
    }

    public_bytes = canonical_json_bytes(universe)
    evaluator_bytes = canonical_json_bytes(truth)
    forbidden = {
        imported.blueprint.blueprint_key,
        imported.blueprint.id_namespace_salt,
        *(item.key for item in imported.blueprint.tenants),
        *(item.key for item in imported.blueprint.organisations),
        *(item.key for item in imported.blueprint.units),
        *(item.key for item in imported.blueprint.populations),
        *(item.key for item in imported.blueprint.groups),
        *(item.key for item in imported.blueprint.roles),
        *(item.key for item in imported.blueprint.resource_sets),
    }
    assert b"id_namespace_salt" not in public_bytes + evaluator_bytes
    for value in forbidden:
        assert value.encode() not in public_bytes + evaluator_bytes
    _assert_recursive_synthetic(universe.model_dump(mode="json"))
    _assert_recursive_synthetic(truth.model_dump(mode="json"))


def test_compilation_is_deterministic_and_selection_is_seeded_without_remapping() -> (
    None
):
    first = _compile(seed=1)
    repeated = _compile(seed=1)
    second_seed = _compile(seed=2)
    assert canonical_json_bytes(first.public_universe) == canonical_json_bytes(
        repeated.public_universe
    )
    assert first.evaluator_canonical_binding_truth == (
        repeated.evaluator_canonical_binding_truth
    )
    assert first.public_universe != second_seed.public_universe

    first_principals = {item.principal_id for item in first.public_universe.principals}
    second_principals = {
        item.principal_id for item in second_seed.public_universe.principals
    }
    assert first_principals == second_principals
    first_accounts = {item.account_id for item in first.public_universe.accounts}
    second_accounts = {item.account_id for item in second_seed.public_universe.accounts}
    assert first_accounts & second_accounts
    first_bindings = {
        item.account_id: item.principal_id
        for item in first.evaluator_canonical_binding_truth.bindings
    }
    second_bindings = {
        item.account_id: item.principal_id
        for item in second_seed.evaluator_canonical_binding_truth.bindings
    }
    assert all(
        first_bindings[account_id] == second_bindings[account_id]
        for account_id in first_accounts & second_accounts
    )


def test_unrelated_template_addition_does_not_remap_existing_ids() -> None:
    imported = reference_enterprise_identity_access_import()
    baseline = _compile(imported)
    changed_blueprint = imported.blueprint.model_copy(
        update={
            "tenants": (
                *imported.blueprint.tenants,
                TenantTemplateV1(key="tenant-unrelated"),
            )
        }
    )
    changed = _compile(imported.model_copy(update={"blueprint": changed_blueprint}))

    def identifiers(result: object) -> set[str]:
        universe = result.public_universe  # type: ignore[attr-defined]
        return {
            *(item.tenant_id for item in universe.tenants),
            *(item.organisation_id for item in universe.organisations),
            *(item.unit_id for item in universe.units),
            *(item.principal_id for item in universe.principals),
            *(item.account_id for item in universe.accounts),
            *(item.group_id for item in universe.groups),
            *(item.role_id for item in universe.roles),
            *(item.authorization_target_id for item in universe.authorization_targets),
            *(item.permission_id for item in universe.permissions),
            *(item.access_atom_id for item in universe.access_atoms),
        }

    assert identifiers(baseline) < identifiers(changed)


def test_fraction_atom_selection_is_exact_and_does_not_resize_other_records() -> None:
    imported = reference_enterprise_identity_access_import()
    employee_rule = imported.blueprint.principal_access_atom_rules[1].model_copy(
        update={"selector": FractionSelectorV1(numerator=1, denominator=2)}
    )
    blueprint = imported.blueprint.model_copy(
        update={
            "principal_access_atom_rules": (
                imported.blueprint.principal_access_atom_rules[0],
                employee_rule,
            )
        }
    )
    changed = _compile(imported.model_copy(update={"blueprint": blueprint}))
    baseline = _compile(imported)
    assert len(changed.public_universe.access_atoms) == 12
    assert len(changed.public_universe.principals) == len(
        baseline.public_universe.principals
    )
    assert len(changed.public_universe.authorization_targets) == len(
        baseline.public_universe.authorization_targets
    )


def test_duplicate_atom_declarations_fail_before_output() -> None:
    imported = reference_enterprise_identity_access_import()
    original = imported.blueprint.principal_access_atom_rules[0]
    duplicate = original.model_copy(update={"rule_key": "second-rule"})
    blueprint = imported.blueprint.model_copy(
        update={
            "principal_access_atom_rules": (
                *imported.blueprint.principal_access_atom_rules,
                duplicate,
            )
        }
    )
    with pytest.raises(
        EnterpriseCompileError, match="duplicate_access_atom_declaration"
    ):
        _compile(imported.model_copy(update={"blueprint": blueprint}))


@pytest.mark.parametrize(
    "field",
    [
        "max_principals",
        "max_accounts",
        "max_groups",
        "max_roles",
        "max_authorization_targets",
        "max_declared_actions",
        "max_access_atoms",
    ],
)
def test_universe_sub_budgets_fail_in_canonical_family(field: str) -> None:
    budget = EnterpriseIdentityAccessCompileBudgetV1().model_copy(update={field: 1})
    config = EnterpriseIdentityAccessCompileConfigV1(budget=budget)
    with pytest.raises(EnterpriseCompileError) as raised:
        _compile(config=config)
    assert raised.value.code == "universe_budget_exceeded"
    assert raised.value.measured is not None
    assert raised.value.allowed == 1


@pytest.mark.parametrize(
    "field",
    ["max_directory_rbac_relations", "max_group_depth", "max_role_depth"],
)
def test_directory_rbac_sub_budgets_are_independent(field: str) -> None:
    budget = EnterpriseIdentityAccessCompileBudgetV1().model_copy(update={field: 1})
    with pytest.raises(EnterpriseCompileError) as raised:
        _compile(config=EnterpriseIdentityAccessCompileConfigV1(budget=budget))
    assert raised.value.code == "directory_rbac_budget_exceeded"
    assert raised.value.allowed == 1


@pytest.mark.parametrize(
    "field",
    [
        "max_serialized_records",
        "max_relations",
        "max_expanded_steps",
        "max_canonical_bytes",
        "max_work_units",
    ],
)
def test_outer_safety_limits_do_not_substitute_for_semantic_budgets(field: str) -> None:
    safety = EnterpriseCompileOuterSafetyV1().model_copy(update={field: 1})
    config = EnterpriseIdentityAccessCompileConfigV1(outer_safety=safety)
    with pytest.raises(EnterpriseCompileError) as raised:
        _compile(config=config)
    assert raised.value.code == "outer_safety_exceeded"
    assert raised.value.allowed == 1


def test_unit_owner_and_target_classifications_have_executable_compiled_semantics() -> (
    None
):
    imported = reference_enterprise_identity_access_import()
    baseline = _compile(imported).public_universe
    units = list(imported.blueprint.units)
    units[1] = units[1].model_copy(update={"unit_kind": UnitKind.DEPARTMENT})
    groups = list(imported.blueprint.groups)
    groups[0] = groups[0].model_copy(update={"owner_unit_key": None})
    resources = list(imported.blueprint.resource_sets)
    resources[0] = resources[0].model_copy(update={"target_kind": TargetKind.TOOL})
    blueprint = imported.blueprint.model_copy(
        update={
            "units": tuple(units),
            "groups": tuple(groups),
            "resource_sets": tuple(resources),
        }
    )
    changed = _compile(
        EnterpriseIdentityAccessImportV1.model_validate_json(
            canonical_json_bytes(imported.model_copy(update={"blueprint": blueprint}))
        )
    ).public_universe
    assert {item.unit_id for item in baseline.units} == {
        item.unit_id for item in changed.units
    }
    assert {item.target_kind for item in baseline.authorization_targets} != {
        item.target_kind for item in changed.authorization_targets
    }
    changed_group = next(item for item in changed.groups if item.owner_unit_id is None)
    assert changed_group.group_id in {item.group_id for item in baseline.groups}
    assert any(item.unit_kind is UnitKind.DEPARTMENT for item in changed.units)


def test_optional_account_extension_can_be_empty_without_resizing_principal_atoms() -> (
    None
):
    imported = reference_enterprise_identity_access_import()
    extension = imported.iam_universe_extension.model_copy(
        update={"account_allocations": (), "account_access_atom_rules": ()}
    )
    result = _compile(imported.model_copy(update={"iam_universe_extension": extension}))
    assert result.public_universe.accounts == ()
    assert result.evaluator_canonical_binding_truth.bindings == ()
    assert len(result.public_universe.access_atoms) == 12


def test_account_atoms_expand_only_their_named_allocations_and_declared_slots() -> None:
    imported = reference_enterprise_identity_access_import()
    workforce = imported.iam_universe_extension.account_allocations[0].model_copy(
        update={"accounts_per_selected_subject": 2}
    )
    service = AccountAllocationTemplateV1(
        key="allocation-service-api",
        population_key="population-employees",
        resource_set_key="resource-customer-api",
        account_kind=AccountKind.SERVICE,
        selector=CountSelectorV1(count=1),
        accounts_per_selected_subject=1,
    )
    service_rule = AccountSubjectAccessAtomRuleV1(
        rule_key="atom-service-account-write",
        account_allocation_key=service.key,
        action="write",
    )
    extension = imported.iam_universe_extension.model_copy(
        update={
            "account_allocations": (workforce, service),
            "account_access_atom_rules": (
                imported.iam_universe_extension.account_access_atom_rules[0],
                service_rule,
            ),
        }
    )
    result = _compile(imported.model_copy(update={"iam_universe_extension": extension}))
    universe = result.public_universe
    accounts = {item.account_id: item for item in universe.accounts}
    account_atoms = tuple(
        item for item in universe.access_atoms if item.subject_id in accounts
    )

    assert len(universe.accounts) == 10
    assert (
        sum(item.account_kind is AccountKind.WORKFORCE for item in accounts.values())
        == 8
    )
    assert (
        sum(item.account_kind is AccountKind.SERVICE for item in accounts.values()) == 2
    )
    assert len(account_atoms) == 10
    assert len(universe.access_atoms) == 22
    assert {item.subject_id for item in account_atoms} == set(accounts)
    assert all(
        item.authorization_target_id
        == accounts[item.subject_id].authorization_target_id
        for item in account_atoms
    )
    principal_kinds = {
        item.principal_id: item.principal_kind for item in universe.principals
    }
    assert {
        principal_kinds[item.principal_id]
        for item in result.evaluator_canonical_binding_truth.bindings
    } == {PrincipalKind.EMPLOYEE}


def test_observed_bindings_and_direct_entitlements_validate_after_freeze() -> None:
    imported = reference_enterprise_identity_access_import()
    result = _compile(imported)
    binding = result.evaluator_canonical_binding_truth.bindings[0]
    atom = result.public_universe.access_atoms[0]
    state = imported.directory_rbac_state.model_copy(
        update={
            "account_observations": (
                AccountObservationV1(
                    account_id=binding.account_id,
                    observed_principal_id=binding.principal_id,
                    administrative_state=AdministrativeState.ACTIVE,
                    valid_from_tick=0,
                    revision_id="revision-observed",
                ),
            ),
            "direct_entitlements": (
                DirectEntitlementV1(
                    subject_id=atom.subject_id,
                    authorization_target_id=atom.authorization_target_id,
                    action=atom.action,
                    valid_from_tick=0,
                    revision_id="revision-direct",
                ),
            ),
        }
    )
    changed = _compile(imported.model_copy(update={"directory_rbac_state": state}))
    assert changed.public_universe == result.public_universe
    assert changed.evaluator_canonical_binding_truth == (
        result.evaluator_canonical_binding_truth
    )

    different_same_tenant = next(
        item
        for item in result.public_universe.principals
        if item.principal_id != binding.principal_id
    )
    observed_wrong = state.account_observations[0].model_copy(
        update={"observed_principal_id": different_same_tenant.principal_id}
    )
    wrong_state = state.model_copy(update={"account_observations": (observed_wrong,)})
    _compile(imported.model_copy(update={"directory_rbac_state": wrong_state}))

    unbound_observation = state.account_observations[0].model_copy(
        update={"observed_principal_id": None}
    )
    unbound_state = state.model_copy(
        update={"account_observations": (unbound_observation,)}
    )
    _compile(imported.model_copy(update={"directory_rbac_state": unbound_state}))


@pytest.mark.parametrize(
    ("case", "code"),
    [
        ("unknown_account", "unknown_account_observation"),
        ("unknown_principal", "unknown_observed_principal"),
        ("cross_binding", "cross_tenant_observed_binding"),
        ("unknown_entitlement", "unknown_direct_entitlement_reference"),
        ("cross_entitlement", "cross_tenant_direct_entitlement"),
        ("undeclared_atom", "undeclared_access_atom"),
    ],
)
def test_post_freeze_state_rejects_only_malformed_references(
    case: str, code: str
) -> None:
    imported = reference_enterprise_identity_access_import()
    result = _compile(imported)
    universe = result.public_universe
    binding = result.evaluator_canonical_binding_truth.bindings[0]
    observation = AccountObservationV1(
        account_id=binding.account_id,
        observed_principal_id=binding.principal_id,
        administrative_state=AdministrativeState.ACTIVE,
        valid_from_tick=0,
        revision_id="revision-observed",
    )
    atom = universe.access_atoms[0]
    entitlement = DirectEntitlementV1(
        subject_id=atom.subject_id,
        authorization_target_id=atom.authorization_target_id,
        action=atom.action,
        valid_from_tick=0,
        revision_id="revision-direct",
    )
    changed_universe = universe
    if case == "unknown_account":
        observation = observation.model_copy(update={"account_id": "unknown"})
    elif case == "unknown_principal":
        observation = observation.model_copy(
            update={"observed_principal_id": "unknown"}
        )
    elif case == "cross_binding":
        principals = tuple(
            item.model_copy(update={"tenant_id": "other"})
            if item.principal_id == binding.principal_id
            else item
            for item in universe.principals
        )
        changed_universe = universe.model_copy(update={"principals": principals})
    elif case == "unknown_entitlement":
        entitlement = entitlement.model_copy(update={"subject_id": "unknown"})
    elif case == "cross_entitlement":
        targets = tuple(
            item.model_copy(update={"tenant_id": "other"})
            if item.authorization_target_id == entitlement.authorization_target_id
            else item
            for item in universe.authorization_targets
        )
        changed_universe = universe.model_copy(
            update={"authorization_targets": targets}
        )
    else:
        entitlement = entitlement.model_copy(update={"action": "not-declared"})
    state = imported.directory_rbac_state.model_copy(
        update={
            "account_observations": (observation,),
            "direct_entitlements": (entitlement,),
        }
    )
    changed_import = imported.model_copy(update={"directory_rbac_state": state})
    with pytest.raises(EnterpriseCompileError) as raised:
        _validate_post_freeze_state(changed_import, changed_universe)
    assert raised.value.code == code


def test_each_generated_identifier_inventory_is_unique() -> None:
    universe = _compile().public_universe
    inventories: Iterable[tuple[str, ...]] = (
        tuple(item.tenant_id for item in universe.tenants),
        tuple(item.organisation_id for item in universe.organisations),
        tuple(item.unit_id for item in universe.units),
        tuple(item.principal_id for item in universe.principals),
        tuple(item.account_id for item in universe.accounts),
        tuple(item.group_id for item in universe.groups),
        tuple(item.role_id for item in universe.roles),
        tuple(item.authorization_target_id for item in universe.authorization_targets),
        tuple(item.permission_id for item in universe.permissions),
        tuple(item.anchor_id for item in universe.relationship_anchors),
        tuple(item.access_atom_id for item in universe.access_atoms),
    )
    for identifiers in inventories:
        assert len(identifiers) == len(set(identifiers))
    all_ids = [identifier for inventory in inventories for identifier in inventory]
    assert len(all_ids) == len(set(all_ids))
    assert REFERENCE_NAMESPACE_SALT not in canonical_json_bytes(universe).decode()
