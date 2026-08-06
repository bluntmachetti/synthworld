"""Structural validation for enterprise identity/access imports."""

from __future__ import annotations

from collections import defaultdict, deque
from itertools import chain

from synthworld.enterprise.models import (
    AllSelectorV1,
    CountSelectorV1,
    EnterpriseIdentityAccessImportLimitsV1,
    EnterpriseIdentityAccessImportV1,
    EnterpriseIdentityAccessValidationReportV1,
    EnterpriseImportDiagnosticV1,
    GroupTemplateV1,
    OrganisationTemplateV1,
    PopulationTemplateV1,
    ResourceSetTemplateV1,
    RoleTemplateV1,
    SelectorV1,
)


class EnterpriseImportError(ValueError):
    """Raised when an untrusted enterprise import cannot be accepted."""

    def __init__(self, diagnostics: tuple[EnterpriseImportDiagnosticV1, ...]) -> None:
        self.diagnostics = diagnostics
        joined = "; ".join(f"{item.code}: {item.message}" for item in diagnostics[:5])
        super().__init__(joined or "enterprise identity/access import is invalid")


class _Diagnostics:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.items: list[EnterpriseImportDiagnosticV1] = []
        self.total = 0

    def add(
        self,
        code: str,
        message: str,
        *,
        logical_key: str | None = None,
        file: str | None = None,
        row: int | None = None,
        column: str | None = None,
        hint: str = "Correct the declared identity/access structure.",
        measured: int | None = None,
        allowed: int | None = None,
    ) -> None:
        self.total += 1
        if len(self.items) < self.limit:
            self.items.append(
                EnterpriseImportDiagnosticV1(
                    code=code,
                    message=message,
                    file=file,
                    row=row,
                    column=column,
                    logical_key=logical_key,
                    remediation_hint=hint,
                    measured=measured,
                    allowed=allowed,
                )
            )

    def finish(self) -> tuple[EnterpriseImportDiagnosticV1, ...]:
        if self.total > self.limit:
            self.items[-1:] = [
                EnterpriseImportDiagnosticV1(
                    code="diagnostics_truncated",
                    message="additional diagnostics were suppressed",
                    remediation_hint="Fix the reported errors and validate again.",
                    measured=self.total,
                    allowed=self.limit,
                )
            ]
        return tuple(
            sorted(
                self.items,
                key=lambda item: (
                    item.code,
                    item.file or "",
                    item.row or 0,
                    item.column or "",
                    item.logical_key or "",
                    item.message,
                ),
            )
        )


def validate_enterprise_identity_access(
    import_model: EnterpriseIdentityAccessImportV1,
    *,
    limits: EnterpriseIdentityAccessImportLimitsV1 | None = None,
) -> EnterpriseIdentityAccessValidationReportV1:
    """Return every independently detectable structural error canonically."""

    selected_limits = limits or EnterpriseIdentityAccessImportLimitsV1()
    found = _Diagnostics(selected_limits.max_diagnostics)
    blueprint = import_model.blueprint
    extension = import_model.iam_universe_extension
    state = import_model.directory_rbac_state

    tenants = {item.key: item for item in blueprint.tenants}
    organisations = {item.key: item for item in blueprint.organisations}
    units = {item.key: item for item in blueprint.units}
    populations = {item.key: item for item in blueprint.populations}
    groups = {item.key: item for item in blueprint.groups}
    roles = {item.key: item for item in blueprint.roles}
    resource_sets = {item.key: item for item in blueprint.resource_sets}
    allocations = {item.key: item for item in extension.account_allocations}

    for organisation in blueprint.organisations:
        if organisation.tenant_key not in tenants:
            found.add(
                "unknown_tenant",
                "organisation references an unknown tenant",
                logical_key=organisation.key,
            )

    for unit in blueprint.units:
        unit_organisation = organisations.get(unit.organisation_key)
        _check_scope(
            found,
            logical_key=unit.key,
            tenant_key=unit.tenant_key,
            organisation=unit_organisation,
        )
        if unit.parent_unit_key is not None:
            parent = units.get(unit.parent_unit_key)
            if parent is None:
                found.add(
                    "unknown_parent_unit",
                    "unit references an unknown parent unit",
                    logical_key=unit.key,
                )
            elif (
                parent.tenant_key != unit.tenant_key
                or parent.organisation_key != unit.organisation_key
            ):
                found.add(
                    "cross_scope_unit_parent",
                    "a parent unit must share tenant and organisation scope",
                    logical_key=unit.key,
                )

    _check_dag(
        found,
        nodes=set(units),
        edges=tuple(
            (item.key, item.parent_unit_key)
            for item in blueprint.units
            if item.parent_unit_key in units
        ),
        code="unit_cycle",
        description="organisational unit hierarchy contains a cycle",
    )

    for population in blueprint.populations:
        population_organisation = organisations.get(population.organisation_key)
        _check_scope(
            found,
            logical_key=population.key,
            tenant_key=population.tenant_key,
            organisation=population_organisation,
        )
        population_unit = units.get(population.unit_key)
        if population_unit is None:
            found.add(
                "unknown_population_unit",
                "population references an unknown unit",
                logical_key=population.key,
            )
        elif (
            population_unit.tenant_key != population.tenant_key
            or population_unit.organisation_key != population.organisation_key
        ):
            found.add(
                "cross_scope_population_unit",
                "population unit must share tenant and organisation scope",
                logical_key=population.key,
            )

    owned_records: tuple[
        GroupTemplateV1 | RoleTemplateV1 | ResourceSetTemplateV1, ...
    ] = tuple(chain(blueprint.groups, blueprint.roles, blueprint.resource_sets))
    for owned_record in owned_records:
        owned_organisation = organisations.get(owned_record.organisation_key)
        _check_scope(
            found,
            logical_key=owned_record.key,
            tenant_key=owned_record.tenant_key,
            organisation=owned_organisation,
        )
        if owned_record.owner_unit_key is not None:
            owner = units.get(owned_record.owner_unit_key)
            if owner is None:
                found.add(
                    "unknown_owner_unit",
                    "owner unit does not resolve",
                    logical_key=owned_record.key,
                )
            elif (
                owner.tenant_key != owned_record.tenant_key
                or owner.organisation_key != owned_record.organisation_key
            ):
                found.add(
                    "cross_scope_owner_unit",
                    "owner unit must share tenant and organisation scope",
                    logical_key=owned_record.key,
                )

    for principal_rule in blueprint.principal_access_atom_rules:
        rule_population = populations.get(principal_rule.population_key)
        rule_resource_set = resource_sets.get(principal_rule.resource_set_key)
        _check_population_selector(
            found,
            principal_rule.rule_key,
            rule_population,
            principal_rule.selector,
        )
        _check_population_resource_scope(
            found, principal_rule.rule_key, rule_population, rule_resource_set
        )
        _check_action(
            found,
            principal_rule.rule_key,
            rule_resource_set,
            principal_rule.action,
        )

    for allocation in extension.account_allocations:
        allocation_population = populations.get(allocation.population_key)
        allocation_resource = resource_sets.get(allocation.resource_set_key)
        _check_population_selector(
            found, allocation.key, allocation_population, allocation.selector
        )
        _check_population_resource_scope(
            found, allocation.key, allocation_population, allocation_resource
        )

    seen_allocation_actions: set[tuple[str, str]] = set()
    for account_rule in extension.account_access_atom_rules:
        rule_allocation = allocations.get(account_rule.account_allocation_key)
        if rule_allocation is None:
            found.add(
                "unknown_account_allocation",
                "account access-atom rule references an unknown allocation",
                logical_key=account_rule.rule_key,
            )
            continue
        pair = (account_rule.account_allocation_key, account_rule.action)
        if pair in seen_allocation_actions:
            found.add(
                "duplicate_account_allocation_action",
                "an allocation/action pair may be declared only once",
                logical_key=account_rule.rule_key,
            )
        seen_allocation_actions.add(pair)
        _check_action(
            found,
            account_rule.rule_key,
            resource_sets.get(rule_allocation.resource_set_key),
            account_rule.action,
        )

    if not (
        blueprint.principal_access_atom_rules or extension.account_access_atom_rules
    ):
        found.add(
            "access_atom_rule_required",
            "at least one principal or account access-atom rule is required",
        )

    for membership_rule in state.memberships:
        membership_population = populations.get(membership_rule.population_key)
        membership_group = groups.get(membership_rule.group_key)
        _check_population_selector(
            found,
            membership_rule.rule_key,
            membership_population,
            membership_rule.selector,
        )
        _check_population_group_scope(
            found,
            membership_rule.rule_key,
            membership_population,
            membership_group,
        )

    valid_group_edges: list[tuple[str, str]] = []
    for group_edge in state.group_nesting:
        child_group = groups.get(group_edge.child_group_key)
        parent_group = groups.get(group_edge.parent_group_key)
        if child_group is None or parent_group is None:
            found.add(
                "unknown_group_nesting_reference",
                "group nesting references an unknown group",
                logical_key=group_edge.child_group_key,
            )
        elif (
            child_group.tenant_key != parent_group.tenant_key
            or child_group.organisation_key != parent_group.organisation_key
        ):
            found.add(
                "cross_tenant_group_nesting",
                "nested groups must share tenant and organisation scope",
                logical_key=group_edge.child_group_key,
            )
        else:
            valid_group_edges.append(
                (group_edge.child_group_key, group_edge.parent_group_key)
            )
    _check_dag(
        found,
        nodes=set(groups),
        edges=tuple(valid_group_edges),
        code="group_nesting_cycle",
        description="group nesting contains a cycle",
    )

    for assignment in state.group_role_assignments:
        group = groups.get(assignment.group_key)
        role = roles.get(assignment.role_key)
        _check_group_role_scope(found, assignment.group_key, group, role)

    for role_rule in state.population_role_assignments:
        role_population = populations.get(role_rule.population_key)
        assigned_role = roles.get(role_rule.role_key)
        _check_population_selector(
            found, role_rule.rule_key, role_population, role_rule.selector
        )
        _check_population_role_scope(
            found, role_rule.rule_key, role_population, assigned_role
        )

    valid_role_edges: list[tuple[str, str]] = []
    for role_edge in state.role_hierarchy:
        senior = roles.get(role_edge.senior_role_key)
        junior = roles.get(role_edge.junior_role_key)
        if senior is None or junior is None:
            found.add(
                "unknown_role_hierarchy_reference",
                "role hierarchy references an unknown role",
                logical_key=role_edge.senior_role_key,
            )
        elif (
            senior.tenant_key != junior.tenant_key
            or senior.organisation_key != junior.organisation_key
        ):
            found.add(
                "cross_tenant_role_hierarchy",
                "role hierarchy edges must share tenant and organisation scope",
                logical_key=role_edge.senior_role_key,
            )
        else:
            valid_role_edges.append(
                (role_edge.senior_role_key, role_edge.junior_role_key)
            )
    _check_dag(
        found,
        nodes=set(roles),
        edges=tuple(valid_role_edges),
        code="role_hierarchy_cycle",
        description="role hierarchy contains a cycle",
    )

    for grant in state.role_grants:
        role = roles.get(grant.role_key)
        resource_set = resource_sets.get(grant.resource_set_key)
        if role is None:
            found.add(
                "unknown_role_grant_role",
                "role grant references an unknown role",
                logical_key=grant.role_key,
            )
        elif resource_set is not None and role.tenant_key != resource_set.tenant_key:
            found.add(
                "cross_tenant_role_grant",
                "role grants cannot cross tenant boundaries",
                logical_key=grant.role_key,
            )
        if resource_set is None:
            found.add(
                "unknown_resource_set",
                "role grant references an unknown resource set",
                logical_key=grant.role_key,
            )
        _check_action(found, grant.role_key, resource_set, grant.action)

    diagnostics = found.finish()
    return EnterpriseIdentityAccessValidationReportV1(
        valid=not diagnostics,
        diagnostics=diagnostics,
    )


def ensure_valid_enterprise_identity_access(
    import_model: EnterpriseIdentityAccessImportV1,
    *,
    limits: EnterpriseIdentityAccessImportLimitsV1 | None = None,
) -> None:
    report = validate_enterprise_identity_access(import_model, limits=limits)
    if not report.valid:
        raise EnterpriseImportError(report.diagnostics)


def dag_max_depth(
    nodes: set[str], edges: tuple[tuple[str, str], ...]
) -> tuple[bool, int]:
    """Return ``(acyclic, longest node-count path)`` for a bounded DAG."""

    outgoing: dict[str, list[str]] = defaultdict(list)
    indegree = dict.fromkeys(nodes, 0)
    for source, target in edges:
        outgoing[source].append(target)
        indegree[target] += 1
    queue = deque(sorted(node for node, degree in indegree.items() if degree == 0))
    depth = dict.fromkeys(nodes, 1)
    visited = 0
    while queue:
        source = queue.popleft()
        visited += 1
        for target in sorted(outgoing[source]):
            depth[target] = max(depth[target], depth[source] + 1)
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    return visited == len(nodes), max(depth.values(), default=0)


def selector_count(selector: SelectorV1, population_count: int) -> int:
    if isinstance(selector, AllSelectorV1):
        return population_count
    if isinstance(selector, CountSelectorV1):
        return selector.count
    return population_count * selector.numerator // selector.denominator


def _check_scope(
    found: _Diagnostics,
    *,
    logical_key: str,
    tenant_key: str,
    organisation: OrganisationTemplateV1 | None,
) -> None:
    if organisation is None:
        found.add(
            "unknown_organisation",
            "record references an unknown organisation",
            logical_key=logical_key,
        )
    elif organisation.tenant_key != tenant_key:
        found.add(
            "organisation_tenant_mismatch",
            "record tenant differs from its organisation tenant",
            logical_key=logical_key,
        )


def _check_population_selector(
    found: _Diagnostics,
    logical_key: str,
    population: PopulationTemplateV1 | None,
    selector: SelectorV1,
) -> None:
    if population is None:
        found.add(
            "unknown_population",
            "selection rule references an unknown population",
            logical_key=logical_key,
        )
        return
    count = selector_count(selector, population.count)
    if count < 1 or count > population.count:
        found.add(
            "selector_population_bound",
            "selector count must be between one and the population count",
            logical_key=logical_key,
            measured=count,
            allowed=population.count,
        )


def _check_population_resource_scope(
    found: _Diagnostics,
    logical_key: str,
    population: PopulationTemplateV1 | None,
    resource_set: ResourceSetTemplateV1 | None,
) -> None:
    if resource_set is None:
        found.add(
            "unknown_resource_set",
            "record references an unknown resource set",
            logical_key=logical_key,
        )
    elif population is not None and (
        population.tenant_key != resource_set.tenant_key
        or population.organisation_key != resource_set.organisation_key
    ):
        found.add(
            "cross_tenant_access_declaration",
            "access declarations must remain in one tenant and organisation",
            logical_key=logical_key,
        )


def _check_population_group_scope(
    found: _Diagnostics,
    logical_key: str,
    population: PopulationTemplateV1 | None,
    group: GroupTemplateV1 | None,
) -> None:
    if group is None:
        found.add(
            "unknown_group",
            "membership references an unknown group",
            logical_key=logical_key,
        )
    elif population is not None and (
        population.tenant_key != group.tenant_key
        or population.organisation_key != group.organisation_key
    ):
        found.add(
            "cross_tenant_membership",
            "membership cannot cross tenant or organisation scope",
            logical_key=logical_key,
        )


def _check_population_role_scope(
    found: _Diagnostics,
    logical_key: str,
    population: PopulationTemplateV1 | None,
    role: RoleTemplateV1 | None,
) -> None:
    if role is None:
        found.add(
            "unknown_role",
            "assignment references an unknown role",
            logical_key=logical_key,
        )
    elif population is not None and (
        population.tenant_key != role.tenant_key
        or population.organisation_key != role.organisation_key
    ):
        found.add(
            "cross_tenant_role_assignment",
            "role assignment cannot cross tenant or organisation scope",
            logical_key=logical_key,
        )


def _check_group_role_scope(
    found: _Diagnostics,
    logical_key: str,
    group: GroupTemplateV1 | None,
    role: RoleTemplateV1 | None,
) -> None:
    if group is None or role is None:
        found.add(
            "unknown_group_role_reference",
            "group-role assignment references an unknown record",
            logical_key=logical_key,
        )
    elif (
        group.tenant_key != role.tenant_key
        or group.organisation_key != role.organisation_key
    ):
        found.add(
            "cross_tenant_group_role_assignment",
            "group-role assignment cannot cross tenant or organisation scope",
            logical_key=logical_key,
        )


def _check_action(
    found: _Diagnostics,
    logical_key: str,
    resource_set: ResourceSetTemplateV1 | None,
    action: str,
) -> None:
    if resource_set is not None and action not in resource_set.actions:
        found.add(
            "undeclared_action",
            "access declaration names an action absent from its resource set",
            logical_key=logical_key,
        )


def _check_dag(
    found: _Diagnostics,
    *,
    nodes: set[str],
    edges: tuple[tuple[str, str], ...],
    code: str,
    description: str,
) -> None:
    acyclic, _depth = dag_max_depth(nodes, edges)
    if not acyclic:
        found.add(code, description)


__all__ = [
    "EnterpriseImportError",
    "dag_max_depth",
    "ensure_valid_enterprise_identity_access",
    "selector_count",
    "validate_enterprise_identity_access",
]
