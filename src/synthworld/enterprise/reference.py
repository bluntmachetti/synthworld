"""Small safely fictional cross-format enterprise import vector."""

from __future__ import annotations

import csv
import io
import json

import yaml

from synthworld.enterprise.models import (
    AccountAllocationTemplateV1,
    AccountKind,
    AccountSubjectAccessAtomRuleV1,
    AllSelectorV1,
    CountSelectorV1,
    EnterpriseDirectoryRbacStateInputV1,
    EnterpriseIamUniverseExtensionV1,
    EnterpriseIdentityAccessBlueprintV1,
    EnterpriseIdentityAccessImportV1,
    GroupNestingV1,
    GroupRoleAssignmentV1,
    GroupTemplateV1,
    OrganisationTemplateV1,
    PopulationGroupMembershipRuleV1,
    PopulationRoleAssignmentRuleV1,
    PopulationTemplateV1,
    PrincipalKind,
    PrincipalSubjectAccessAtomRuleV1,
    ResourceSetTemplateV1,
    RoleGrantV1,
    RoleHierarchyV1,
    RoleTemplateV1,
    SelectorV1,
    TargetKind,
    TenantTemplateV1,
    UnitKind,
    UnitTemplateV1,
)
from synthworld.enterprise.parsers import CSV_HEADERS

REFERENCE_NAMESPACE_SALT = "0123456789abcdef" * 4


def reference_enterprise_identity_access_import(
    *, id_namespace_salt: str = REFERENCE_NAMESPACE_SALT
) -> EnterpriseIdentityAccessImportV1:
    blueprint = EnterpriseIdentityAccessBlueprintV1(
        blueprint_key="example-enterprise",
        id_namespace_salt=id_namespace_salt,
        tenants=(TenantTemplateV1(key="tenant-main"),),
        organisations=(
            OrganisationTemplateV1(key="organisation-main", tenant_key="tenant-main"),
        ),
        units=(
            UnitTemplateV1(
                key="division-operations",
                tenant_key="tenant-main",
                organisation_key="organisation-main",
                unit_kind=UnitKind.DIVISION,
            ),
            UnitTemplateV1(
                key="team-platform",
                tenant_key="tenant-main",
                organisation_key="organisation-main",
                unit_kind=UnitKind.TEAM,
                parent_unit_key="division-operations",
            ),
        ),
        populations=(
            PopulationTemplateV1(
                key="population-agents",
                tenant_key="tenant-main",
                organisation_key="organisation-main",
                unit_key="team-platform",
                population_kind=PrincipalKind.AGENT,
                count=2,
            ),
            PopulationTemplateV1(
                key="population-employees",
                tenant_key="tenant-main",
                organisation_key="organisation-main",
                unit_key="team-platform",
                population_kind=PrincipalKind.EMPLOYEE,
                count=4,
            ),
        ),
        groups=(
            GroupTemplateV1(
                key="group-platform",
                tenant_key="tenant-main",
                organisation_key="organisation-main",
                owner_unit_key="team-platform",
            ),
            GroupTemplateV1(
                key="group-workforce",
                tenant_key="tenant-main",
                organisation_key="organisation-main",
                owner_unit_key="division-operations",
            ),
        ),
        roles=(
            RoleTemplateV1(
                key="role-api-admin",
                tenant_key="tenant-main",
                organisation_key="organisation-main",
                owner_unit_key="team-platform",
            ),
            RoleTemplateV1(
                key="role-api-reader",
                tenant_key="tenant-main",
                organisation_key="organisation-main",
                owner_unit_key="team-platform",
            ),
        ),
        resource_sets=(
            ResourceSetTemplateV1(
                key="resource-customer-api",
                tenant_key="tenant-main",
                organisation_key="organisation-main",
                target_kind=TargetKind.API,
                owner_unit_key="team-platform",
                instance_count=2,
                actions=("read", "write"),
            ),
        ),
        principal_access_atom_rules=(
            PrincipalSubjectAccessAtomRuleV1(
                rule_key="atom-agent-read",
                population_key="population-agents",
                resource_set_key="resource-customer-api",
                action="read",
                selector=AllSelectorV1(),
            ),
            PrincipalSubjectAccessAtomRuleV1(
                rule_key="atom-employee-read",
                population_key="population-employees",
                resource_set_key="resource-customer-api",
                action="read",
                selector=AllSelectorV1(),
            ),
        ),
    )
    extension = EnterpriseIamUniverseExtensionV1(
        account_allocations=(
            AccountAllocationTemplateV1(
                key="allocation-workforce-api",
                population_key="population-employees",
                resource_set_key="resource-customer-api",
                account_kind=AccountKind.WORKFORCE,
                selector=CountSelectorV1(count=2),
                accounts_per_selected_subject=1,
            ),
        ),
        account_access_atom_rules=(
            AccountSubjectAccessAtomRuleV1(
                rule_key="atom-workforce-account-write",
                account_allocation_key="allocation-workforce-api",
                action="write",
            ),
        ),
    )
    state = EnterpriseDirectoryRbacStateInputV1(
        memberships=(
            PopulationGroupMembershipRuleV1(
                rule_key="membership-platform-employees",
                population_key="population-employees",
                group_key="group-platform",
                selector=AllSelectorV1(),
            ),
        ),
        group_nesting=(
            GroupNestingV1(
                child_group_key="group-platform",
                parent_group_key="group-workforce",
            ),
        ),
        group_role_assignments=(
            GroupRoleAssignmentV1(
                group_key="group-workforce", role_key="role-api-reader"
            ),
        ),
        population_role_assignments=(
            PopulationRoleAssignmentRuleV1(
                rule_key="assignment-agent-admin",
                population_key="population-agents",
                role_key="role-api-admin",
                selector=AllSelectorV1(),
            ),
        ),
        role_hierarchy=(
            RoleHierarchyV1(
                senior_role_key="role-api-admin",
                junior_role_key="role-api-reader",
            ),
        ),
        role_grants=(
            RoleGrantV1(
                role_key="role-api-reader",
                resource_set_key="resource-customer-api",
                action="read",
            ),
            RoleGrantV1(
                role_key="role-api-admin",
                resource_set_key="resource-customer-api",
                action="write",
            ),
        ),
    )
    return EnterpriseIdentityAccessImportV1(
        blueprint=blueprint,
        iam_universe_extension=extension,
        directory_rbac_state=state,
    )


def reference_enterprise_json() -> str:
    return (
        json.dumps(
            reference_enterprise_identity_access_import().model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )


def reference_enterprise_yaml() -> str:
    return yaml.safe_dump(
        reference_enterprise_identity_access_import().model_dump(mode="json"),
        allow_unicode=True,
        sort_keys=False,
    )


def reference_enterprise_csv_bundle(
    *, id_namespace_salt: str = REFERENCE_NAMESPACE_SALT
) -> dict[str, str]:
    model = reference_enterprise_identity_access_import(
        id_namespace_salt=id_namespace_salt
    )
    blueprint = model.blueprint
    extension = model.iam_universe_extension
    state = model.directory_rbac_state
    rows: dict[str, list[tuple[object, ...]]] = {name: [] for name in CSV_HEADERS}
    rows["blueprint.csv"] = [
        (blueprint.schema_version, blueprint.blueprint_key, blueprint.id_namespace_salt)
    ]
    rows["tenants.csv"] = [(item.key,) for item in blueprint.tenants]
    rows["organisations.csv"] = [
        (item.key, item.tenant_key) for item in blueprint.organisations
    ]
    rows["units.csv"] = [
        (
            item.key,
            item.tenant_key,
            item.organisation_key,
            item.unit_kind.value,
            item.parent_unit_key or "",
        )
        for item in blueprint.units
    ]
    rows["populations.csv"] = [
        (
            item.key,
            item.tenant_key,
            item.organisation_key,
            item.unit_key,
            item.population_kind.value,
            item.count,
        )
        for item in blueprint.populations
    ]
    rows["groups.csv"] = [
        (
            item.key,
            item.tenant_key,
            item.organisation_key,
            item.owner_unit_key or "",
        )
        for item in blueprint.groups
    ]
    rows["roles.csv"] = [
        (
            item.key,
            item.tenant_key,
            item.organisation_key,
            item.owner_unit_key or "",
        )
        for item in blueprint.roles
    ]
    rows["resource_sets.csv"] = [
        (
            item.key,
            item.tenant_key,
            item.organisation_key,
            item.target_kind.value,
            item.owner_unit_key or "",
            item.instance_count,
        )
        for item in blueprint.resource_sets
    ]
    rows["resource_actions.csv"] = [
        (item.key, action)
        for item in blueprint.resource_sets
        for action in item.actions
    ]
    rows["universe_extension.csv"] = [(extension.schema_version,)]
    rows["account_allocations.csv"] = [
        (
            item.key,
            item.population_key,
            item.resource_set_key,
            item.account_kind.value,
            *_selector_cells(item.selector),
            item.accounts_per_selected_subject,
        )
        for item in extension.account_allocations
    ]
    rows["directory_rbac_state.csv"] = [(state.schema_version,)]
    rows["memberships.csv"] = [
        (
            item.rule_key,
            item.population_key,
            item.group_key,
            *_selector_cells(item.selector),
        )
        for item in state.memberships
    ]
    rows["group_nesting.csv"] = [
        (item.child_group_key, item.parent_group_key) for item in state.group_nesting
    ]
    rows["group_role_assignments.csv"] = [
        (item.group_key, item.role_key) for item in state.group_role_assignments
    ]
    rows["population_role_assignments.csv"] = [
        (
            item.rule_key,
            item.population_key,
            item.role_key,
            *_selector_cells(item.selector),
        )
        for item in state.population_role_assignments
    ]
    rows["role_hierarchy.csv"] = [
        (item.senior_role_key, item.junior_role_key) for item in state.role_hierarchy
    ]
    rows["role_grants.csv"] = [
        (item.role_key, item.resource_set_key, item.action)
        for item in state.role_grants
    ]
    rows["principal_access_atom_rules.csv"] = [
        (
            item.rule_key,
            item.population_key,
            item.resource_set_key,
            item.action,
            *_selector_cells(item.selector),
        )
        for item in blueprint.principal_access_atom_rules
    ]
    rows["account_access_atom_rules.csv"] = [
        (item.rule_key, item.account_allocation_key, item.action)
        for item in extension.account_access_atom_rules
    ]
    return {name: _csv_text(CSV_HEADERS[name], rows[name]) for name in CSV_HEADERS}


def _selector_cells(selector: SelectorV1) -> tuple[object, object, object, object]:
    document = selector.model_dump(mode="json")
    return (
        document["kind"],
        document.get("count", ""),
        document.get("numerator", ""),
        document.get("denominator", ""),
    )


def _csv_text(header: tuple[str, ...], rows: list[tuple[object, ...]]) -> str:
    destination = io.StringIO(newline="")
    writer = csv.writer(destination, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return destination.getvalue()


__all__ = [
    "REFERENCE_NAMESPACE_SALT",
    "reference_enterprise_csv_bundle",
    "reference_enterprise_identity_access_import",
    "reference_enterprise_json",
    "reference_enterprise_yaml",
]
