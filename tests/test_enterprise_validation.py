"""Cross-reference, DAG, and diagnostic tests for enterprise imports."""

from __future__ import annotations

import pytest

from synthworld.enterprise.models import (
    AccountSubjectAccessAtomRuleV1,
    AllSelectorV1,
    CountSelectorV1,
    EnterpriseIdentityAccessImportLimitsV1,
    FractionSelectorV1,
    GroupNestingV1,
    GroupRoleAssignmentV1,
    PopulationGroupMembershipRuleV1,
    PopulationRoleAssignmentRuleV1,
    PrincipalSubjectAccessAtomRuleV1,
    RoleGrantV1,
    RoleHierarchyV1,
    TenantTemplateV1,
)
from synthworld.enterprise.reference import reference_enterprise_identity_access_import
from synthworld.enterprise.validation import (
    EnterpriseImportError,
    dag_max_depth,
    ensure_valid_enterprise_identity_access,
    selector_count,
    validate_enterprise_identity_access,
)


def _codes(imported: object) -> set[str]:
    return {
        item.code
        for item in validate_enterprise_identity_access(imported).diagnostics  # type: ignore[arg-type]
    }


def test_reference_import_is_valid_and_ensure_valid_is_noop() -> None:
    imported = reference_enterprise_identity_access_import()
    report = validate_enterprise_identity_access(imported)
    assert report.valid is True
    assert report.diagnostics == ()
    ensure_valid_enterprise_identity_access(imported)
    empty_error = EnterpriseImportError(())
    assert str(empty_error) == "enterprise identity/access import is invalid"


def test_unknown_tenant_organisation_and_unit_references_are_distinct() -> None:
    imported = reference_enterprise_identity_access_import()
    organisation = imported.blueprint.organisations[0].model_copy(
        update={"tenant_key": "missing"}
    )
    unit = imported.blueprint.units[0].model_copy(
        update={"organisation_key": "missing"}
    )
    population = imported.blueprint.populations[0].model_copy(
        update={"unit_key": "missing"}
    )
    blueprint = imported.blueprint.model_copy(
        update={
            "organisations": (organisation,),
            "units": (unit, *imported.blueprint.units[1:]),
            "populations": (population, *imported.blueprint.populations[1:]),
        }
    )
    codes = _codes(imported.model_copy(update={"blueprint": blueprint}))
    assert {
        "unknown_tenant",
        "unknown_organisation",
        "unknown_population_unit",
    } <= codes


def test_scope_mismatch_parent_and_population_unit_diagnostics() -> None:
    imported = reference_enterprise_identity_access_import()
    blueprint = imported.blueprint
    tenants = (*blueprint.tenants, TenantTemplateV1(key="tenant-other"))
    organisation = blueprint.organisations[0].model_copy(
        update={"tenant_key": "tenant-other"}
    )
    first_unit = blueprint.units[0].model_copy(update={"tenant_key": "tenant-other"})
    second_unit = blueprint.units[1]
    population = blueprint.populations[0].model_copy(
        update={"tenant_key": "tenant-other", "unit_key": second_unit.key}
    )
    changed = blueprint.model_copy(
        update={
            "tenants": tenants,
            "organisations": (organisation,),
            "units": (first_unit, second_unit),
            "populations": (population, *blueprint.populations[1:]),
        }
    )
    codes = _codes(imported.model_copy(update={"blueprint": changed}))
    assert {
        "organisation_tenant_mismatch",
        "cross_scope_unit_parent",
        "cross_scope_population_unit",
    } <= codes


def test_unknown_parent_and_unit_cycle_are_reported() -> None:
    imported = reference_enterprise_identity_access_import()
    units = imported.blueprint.units
    unknown = units[0].model_copy(update={"parent_unit_key": "missing"})
    unknown_blueprint = imported.blueprint.model_copy(
        update={"units": (unknown, units[1])}
    )
    assert "unknown_parent_unit" in _codes(
        imported.model_copy(update={"blueprint": unknown_blueprint})
    )

    cycle_a = units[0].model_copy(update={"parent_unit_key": units[1].key})
    cycle_b = units[1].model_copy(update={"parent_unit_key": units[0].key})
    cycle_blueprint = imported.blueprint.model_copy(
        update={"units": (cycle_a, cycle_b)}
    )
    assert "unit_cycle" in _codes(
        imported.model_copy(update={"blueprint": cycle_blueprint})
    )


@pytest.mark.parametrize("kind", ["group", "role", "resource"])
def test_owner_reference_must_resolve_in_same_scope(kind: str) -> None:
    imported = reference_enterprise_identity_access_import()
    blueprint = imported.blueprint
    field = {"group": "groups", "role": "roles", "resource": "resource_sets"}[kind]
    records = list(getattr(blueprint, field))
    records[0] = records[0].model_copy(update={"owner_unit_key": "missing"})
    changed = blueprint.model_copy(update={field: tuple(records)})
    assert "unknown_owner_unit" in _codes(
        imported.model_copy(update={"blueprint": changed})
    )

    wrong_owner = blueprint.units[0].model_copy(update={"tenant_key": "other"})
    changed = blueprint.model_copy(
        update={
            field: tuple(getattr(blueprint, field)),
            "units": (wrong_owner, *blueprint.units[1:]),
        }
    )
    assert "cross_scope_owner_unit" in _codes(
        imported.model_copy(update={"blueprint": changed})
    )


@pytest.mark.parametrize("owner", ["principal", "allocation"])
def test_atom_and_allocation_rules_validate_population_resource_scope_and_selector(
    owner: str,
) -> None:
    imported = reference_enterprise_identity_access_import()
    if owner == "principal":
        rule = imported.blueprint.principal_access_atom_rules[0]
        unknown_population = rule.model_copy(update={"population_key": "missing"})
        unknown_resource = rule.model_copy(update={"resource_set_key": "missing"})
        bad_action = rule.model_copy(update={"action": "delete"})
        too_many = rule.model_copy(update={"selector": CountSelectorV1(count=99)})
        changed_blueprint = imported.blueprint.model_copy(
            update={
                "principal_access_atom_rules": (
                    unknown_population,
                    unknown_resource,
                    bad_action,
                    too_many,
                )
            }
        )
        changed = imported.model_copy(update={"blueprint": changed_blueprint})
    else:
        allocation = imported.iam_universe_extension.account_allocations[0]
        unknown_allocation_population = allocation.model_copy(
            update={"population_key": "missing"}
        )
        unknown_allocation_resource = allocation.model_copy(
            update={"resource_set_key": "missing"}
        )
        oversized_allocation = allocation.model_copy(
            update={"selector": CountSelectorV1(count=99)}
        )
        extension = imported.iam_universe_extension.model_copy(
            update={
                "account_allocations": (
                    unknown_allocation_population,
                    unknown_allocation_resource,
                    oversized_allocation,
                )
            }
        )
        changed = imported.model_copy(update={"iam_universe_extension": extension})
    codes = _codes(changed)
    assert {
        "unknown_population",
        "unknown_resource_set",
        "selector_population_bound",
    } <= codes
    if owner == "principal":
        assert "undeclared_action" in codes


def test_cross_tenant_access_declaration_is_malformed() -> None:
    imported = reference_enterprise_identity_access_import()
    resource = imported.blueprint.resource_sets[0].model_copy(
        update={"tenant_key": "other"}
    )
    blueprint = imported.blueprint.model_copy(update={"resource_sets": (resource,)})
    assert "cross_tenant_access_declaration" in _codes(
        imported.model_copy(update={"blueprint": blueprint})
    )


def test_account_atom_rules_require_one_known_allocation_action_pair() -> None:
    imported = reference_enterprise_identity_access_import()
    original = imported.iam_universe_extension.account_access_atom_rules[0]
    unknown = original.model_copy(update={"account_allocation_key": "missing"})
    duplicate = original.model_copy(update={"rule_key": "duplicate-rule"})
    bad_action = original.model_copy(
        update={"rule_key": "bad-action-rule", "action": "delete"}
    )
    extension = imported.iam_universe_extension.model_copy(
        update={"account_access_atom_rules": (unknown, original, duplicate, bad_action)}
    )
    codes = _codes(imported.model_copy(update={"iam_universe_extension": extension}))
    assert {
        "unknown_account_allocation",
        "duplicate_account_allocation_action",
        "undeclared_action",
    } <= codes


def test_at_least_one_sparse_atom_rule_is_required() -> None:
    imported = reference_enterprise_identity_access_import()
    blueprint = imported.blueprint.model_copy(
        update={"principal_access_atom_rules": ()}
    )
    extension = imported.iam_universe_extension.model_copy(
        update={"account_access_atom_rules": ()}
    )
    changed = imported.model_copy(
        update={"blueprint": blueprint, "iam_universe_extension": extension}
    )
    assert "access_atom_rule_required" in _codes(changed)


def test_membership_unknown_and_cross_scope_cases_are_reported() -> None:
    imported = reference_enterprise_identity_access_import()
    original = imported.directory_rbac_state.memberships[0]
    unknown = original.model_copy(update={"group_key": "missing"})
    too_many = original.model_copy(
        update={"rule_key": "too-many", "selector": CountSelectorV1(count=99)}
    )
    cross_group = imported.blueprint.groups[0].model_copy(
        update={"tenant_key": "other"}
    )
    blueprint = imported.blueprint.model_copy(
        update={"groups": (cross_group, *imported.blueprint.groups[1:])}
    )
    state = imported.directory_rbac_state.model_copy(
        update={"memberships": (unknown, too_many, original)}
    )
    codes = _codes(
        imported.model_copy(
            update={"blueprint": blueprint, "directory_rbac_state": state}
        )
    )
    assert {
        "unknown_group",
        "selector_population_bound",
        "cross_tenant_membership",
    } <= codes


def test_group_nesting_unknown_cross_tenant_and_cycle_cases_are_distinct() -> None:
    imported = reference_enterprise_identity_access_import()
    original = imported.directory_rbac_state.group_nesting[0]
    unknown = original.model_copy(update={"parent_group_key": "missing"})
    state = imported.directory_rbac_state.model_copy(
        update={"group_nesting": (unknown,)}
    )
    assert "unknown_group_nesting_reference" in _codes(
        imported.model_copy(update={"directory_rbac_state": state})
    )

    group = imported.blueprint.groups[1].model_copy(update={"tenant_key": "other"})
    blueprint = imported.blueprint.model_copy(
        update={"groups": (imported.blueprint.groups[0], group)}
    )
    assert "cross_tenant_group_nesting" in _codes(
        imported.model_copy(update={"blueprint": blueprint})
    )

    reverse = GroupNestingV1(
        child_group_key=original.parent_group_key,
        parent_group_key=original.child_group_key,
    )
    state = imported.directory_rbac_state.model_copy(
        update={"group_nesting": (original, reverse)}
    )
    assert "group_nesting_cycle" in _codes(
        imported.model_copy(update={"directory_rbac_state": state})
    )


def test_group_and_population_role_assignment_reference_and_scope_errors() -> None:
    imported = reference_enterprise_identity_access_import()
    group_assignment = GroupRoleAssignmentV1(group_key="missing", role_key="missing")
    population_assignment = PopulationRoleAssignmentRuleV1(
        rule_key="missing-role",
        population_key="population-employees",
        role_key="missing",
        selector=AllSelectorV1(),
    )
    state = imported.directory_rbac_state.model_copy(
        update={
            "group_role_assignments": (group_assignment,),
            "population_role_assignments": (population_assignment,),
        }
    )
    codes = _codes(imported.model_copy(update={"directory_rbac_state": state}))
    assert {"unknown_group_role_reference", "unknown_role"} <= codes

    role = imported.blueprint.roles[0].model_copy(update={"tenant_key": "other"})
    blueprint = imported.blueprint.model_copy(
        update={"roles": (role, *imported.blueprint.roles[1:])}
    )
    cross_group = GroupRoleAssignmentV1(group_key="group-platform", role_key=role.key)
    cross_population = PopulationRoleAssignmentRuleV1(
        rule_key="cross-role",
        population_key="population-agents",
        role_key=role.key,
        selector=AllSelectorV1(),
    )
    state = imported.directory_rbac_state.model_copy(
        update={
            "group_role_assignments": (cross_group,),
            "population_role_assignments": (cross_population,),
        }
    )
    codes = _codes(
        imported.model_copy(
            update={"blueprint": blueprint, "directory_rbac_state": state}
        )
    )
    assert {
        "cross_tenant_group_role_assignment",
        "cross_tenant_role_assignment",
    } <= codes


def test_role_hierarchy_unknown_cross_tenant_and_cycle_cases_are_distinct() -> None:
    imported = reference_enterprise_identity_access_import()
    original = imported.directory_rbac_state.role_hierarchy[0]
    unknown = original.model_copy(update={"junior_role_key": "missing"})
    state = imported.directory_rbac_state.model_copy(
        update={"role_hierarchy": (unknown,)}
    )
    assert "unknown_role_hierarchy_reference" in _codes(
        imported.model_copy(update={"directory_rbac_state": state})
    )

    role = imported.blueprint.roles[1].model_copy(update={"tenant_key": "other"})
    blueprint = imported.blueprint.model_copy(
        update={"roles": (imported.blueprint.roles[0], role)}
    )
    assert "cross_tenant_role_hierarchy" in _codes(
        imported.model_copy(update={"blueprint": blueprint})
    )

    reverse = RoleHierarchyV1(
        senior_role_key=original.junior_role_key,
        junior_role_key=original.senior_role_key,
    )
    state = imported.directory_rbac_state.model_copy(
        update={"role_hierarchy": (original, reverse)}
    )
    assert "role_hierarchy_cycle" in _codes(
        imported.model_copy(update={"directory_rbac_state": state})
    )


def test_role_grants_validate_role_resource_action_and_tenant() -> None:
    imported = reference_enterprise_identity_access_import()
    grants = (
        RoleGrantV1(
            role_key="missing", resource_set_key="resource-customer-api", action="read"
        ),
        RoleGrantV1(
            role_key="role-api-reader", resource_set_key="missing", action="read"
        ),
        RoleGrantV1(
            role_key="role-api-admin",
            resource_set_key="resource-customer-api",
            action="delete",
        ),
    )
    state = imported.directory_rbac_state.model_copy(update={"role_grants": grants})
    codes = _codes(imported.model_copy(update={"directory_rbac_state": state}))
    assert {
        "unknown_role_grant_role",
        "unknown_resource_set",
        "undeclared_action",
    } <= codes

    resource = imported.blueprint.resource_sets[0].model_copy(
        update={"tenant_key": "other"}
    )
    blueprint = imported.blueprint.model_copy(update={"resource_sets": (resource,)})
    assert "cross_tenant_role_grant" in _codes(
        imported.model_copy(update={"blueprint": blueprint})
    )


def test_diagnostics_are_canonical_and_capped() -> None:
    imported = reference_enterprise_identity_access_import()
    blueprint = imported.blueprint.model_copy(
        update={"organisations": (), "units": (), "populations": ()}
    )
    invalid = imported.model_copy(update={"blueprint": blueprint})
    limits = EnterpriseIdentityAccessImportLimitsV1(max_diagnostics=1)
    report = validate_enterprise_identity_access(invalid, limits=limits)
    assert report.valid is False
    assert len(report.diagnostics) == 1
    assert report.diagnostics[0].code == "diagnostics_truncated"
    assert report.diagnostics[0].measured is not None
    with pytest.raises(EnterpriseImportError) as raised:
        ensure_valid_enterprise_identity_access(invalid, limits=limits)
    assert raised.value.diagnostics == report.diagnostics


def test_dag_depth_and_selector_count_helpers_cover_all_closed_shapes() -> None:
    assert dag_max_depth(set(), ()) == (True, 0)
    assert dag_max_depth({"a", "b", "c"}, (("a", "b"), ("b", "c"))) == (
        True,
        3,
    )
    assert dag_max_depth({"a", "b", "c"}, (("a", "c"), ("b", "c"))) == (
        True,
        2,
    )
    assert dag_max_depth({"a", "b"}, (("a", "b"), ("b", "a")))[0] is False
    assert selector_count(AllSelectorV1(), 7) == 7
    assert selector_count(CountSelectorV1(count=3), 7) == 3
    assert selector_count(FractionSelectorV1(numerator=2, denominator=3), 7) == 4


def test_rule_types_remain_owned_by_their_declared_components() -> None:
    principal = PrincipalSubjectAccessAtomRuleV1(
        rule_key="principal",
        population_key="population",
        resource_set_key="resource",
        action="read",
        selector=AllSelectorV1(),
    )
    account = AccountSubjectAccessAtomRuleV1(
        rule_key="account", account_allocation_key="allocation", action="read"
    )
    membership = PopulationGroupMembershipRuleV1(
        rule_key="membership",
        population_key="population",
        group_key="group",
        selector=AllSelectorV1(),
    )
    assert principal.model_dump()["population_key"] == "population"
    assert account.model_dump()["account_allocation_key"] == "allocation"
    assert membership.model_dump()["group_key"] == "group"
