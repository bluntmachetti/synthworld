"""Deterministic compiler for the fixed enterprise identity/access universe."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from synthworld.enterprise.canonical import (
    ENTERPRISE_ACCESS_ATOM_NAMESPACE_V1,
    ENTERPRISE_ACCOUNT_NAMESPACE_V1,
    ENTERPRISE_GROUP_NAMESPACE_V1,
    ENTERPRISE_ORGANISATION_NAMESPACE_V1,
    ENTERPRISE_PERMISSION_NAMESPACE_V1,
    ENTERPRISE_PRINCIPAL_NAMESPACE_V1,
    ENTERPRISE_RELATIONSHIP_ANCHOR_NAMESPACE_V1,
    ENTERPRISE_ROLE_NAMESPACE_V1,
    ENTERPRISE_TARGET_NAMESPACE_V1,
    ENTERPRISE_TENANT_NAMESPACE_V1,
    ENTERPRISE_UNIT_NAMESPACE_V1,
    blueprint_namespace_uuid,
    canonical_json_bytes,
    encode_parts,
    stable_enterprise_id,
    synthetic_digest,
)
from synthworld.enterprise.models import (
    ENTERPRISE_SELECTOR_ALGORITHM_VERSION,
    AccessAtomV1,
    AccessSubjectKind,
    AccountAllocationTemplateV1,
    EnterpriseAccessSubjectV1,
    EnterpriseAccountV1,
    EnterpriseAuthorizationTargetV1,
    EnterpriseCanonicalAccountBindingV1,
    EnterpriseCanonicalBindingTruthV1,
    EnterpriseCompileOuterSafetyV1,
    EnterpriseGroupV1,
    EnterpriseIdentityAccessCompileBudgetV1,
    EnterpriseIdentityAccessCompileConfigV1,
    EnterpriseIdentityAccessCompileResultV1,
    EnterpriseIdentityAccessImportV1,
    EnterpriseIdentityAccessUniverseV1,
    EnterpriseOrganisationV1,
    EnterprisePermissionV1,
    EnterprisePrincipalV1,
    EnterpriseRelationshipAnchorV1,
    EnterpriseRoleV1,
    EnterpriseTenantV1,
    EnterpriseUnitV1,
    PopulationTemplateV1,
    RelationshipAnchorKind,
    ResourceSetTemplateV1,
    SelectorV1,
)
from synthworld.enterprise.validation import (
    dag_max_depth,
    ensure_valid_enterprise_identity_access,
    selector_count,
)


class EnterpriseCompileError(ValueError):
    """Atomic compile failure with a stable code and optional measured limit."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        measured: int | None = None,
        allowed: int | None = None,
    ) -> None:
        self.code = code
        self.measured = measured
        self.allowed = allowed
        suffix = (
            f" (measured={measured}, allowed={allowed})"
            if measured is not None and allowed is not None
            else ""
        )
        super().__init__(f"{code}: {message}{suffix}")


@dataclass(frozen=True, slots=True)
class _PrincipalSlot:
    population_key: str
    slot: int
    principal: EnterprisePrincipalV1


@dataclass(frozen=True, slots=True)
class _TargetSlot:
    resource_set_key: str
    slot: int
    target: EnterpriseAuthorizationTargetV1


@dataclass(frozen=True, slots=True)
class _AllocatedAccount:
    allocation_key: str
    principal_id: str
    account: EnterpriseAccountV1


def compile_enterprise_identity_access_universe(
    *,
    import_model: EnterpriseIdentityAccessImportV1,
    seed: int,
    config: EnterpriseIdentityAccessCompileConfigV1 | None = None,
) -> EnterpriseIdentityAccessCompileResultV1:
    """Compile fixed opaque records and separate canonical account binding truth."""

    ensure_valid_enterprise_identity_access(import_model)
    selected_config = config or EnterpriseIdentityAccessCompileConfigV1()
    blueprint = import_model.blueprint
    extension = import_model.iam_universe_extension
    namespace = blueprint_namespace_uuid(blueprint.id_namespace_salt)

    _preflight_budget(import_model, selected_config.budget)

    tenant_ids = {
        item.key: stable_enterprise_id(
            ENTERPRISE_TENANT_NAMESPACE_V1, namespace, item.key
        )
        for item in blueprint.tenants
    }
    organisation_ids = {
        item.key: stable_enterprise_id(
            ENTERPRISE_ORGANISATION_NAMESPACE_V1,
            namespace,
            item.tenant_key,
            item.key,
        )
        for item in blueprint.organisations
    }
    unit_ids = {
        item.key: stable_enterprise_id(
            ENTERPRISE_UNIT_NAMESPACE_V1,
            namespace,
            item.tenant_key,
            item.organisation_key,
            item.key,
        )
        for item in blueprint.units
    }

    tenants = tuple(
        EnterpriseTenantV1(
            tenant_id=tenant_ids[item.key],
            display_label=f"Example Tenant {index:03d}",
        )
        for index, item in enumerate(blueprint.tenants, start=1)
    )
    organisations = tuple(
        EnterpriseOrganisationV1(
            organisation_id=organisation_ids[item.key],
            tenant_id=tenant_ids[item.tenant_key],
            display_label=f"Example Organisation {index:03d}",
        )
        for index, item in enumerate(blueprint.organisations, start=1)
    )
    units = tuple(
        EnterpriseUnitV1(
            unit_id=unit_ids[item.key],
            tenant_id=tenant_ids[item.tenant_key],
            organisation_id=organisation_ids[item.organisation_key],
            unit_kind=item.unit_kind,
            parent_unit_id=(
                unit_ids[item.parent_unit_key]
                if item.parent_unit_key is not None
                else None
            ),
            display_label=f"Example Organisational Unit {index:03d}",
        )
        for index, item in enumerate(blueprint.units, start=1)
    )

    principal_slots = _compile_principals(
        blueprint.populations,
        namespace,
        tenant_ids,
        organisation_ids,
        unit_ids,
    )
    principals = tuple(
        sorted(
            (slot.principal for slot in principal_slots),
            key=lambda item: item.principal_id,
        )
    )
    principals_by_population = _group_principals(principal_slots)

    targets_by_resource_set = _compile_targets(
        blueprint.resource_sets,
        namespace,
        tenant_ids,
        organisation_ids,
        unit_ids,
    )
    targets = tuple(
        sorted(
            (
                slot.target
                for slots in targets_by_resource_set.values()
                for slot in slots
            ),
            key=lambda item: item.authorization_target_id,
        )
    )
    groups = tuple(
        sorted(
            (
                EnterpriseGroupV1(
                    group_id=stable_enterprise_id(
                        ENTERPRISE_GROUP_NAMESPACE_V1,
                        namespace,
                        item.tenant_key,
                        item.organisation_key,
                        item.key,
                    ),
                    tenant_id=tenant_ids[item.tenant_key],
                    organisation_id=organisation_ids[item.organisation_key],
                    owner_unit_id=(
                        unit_ids[item.owner_unit_key]
                        if item.owner_unit_key is not None
                        else None
                    ),
                    display_label=f"Example Access Group {index:03d}",
                )
                for index, item in enumerate(blueprint.groups, start=1)
            ),
            key=lambda item: item.group_id,
        )
    )
    roles = tuple(
        sorted(
            (
                EnterpriseRoleV1(
                    role_id=stable_enterprise_id(
                        ENTERPRISE_ROLE_NAMESPACE_V1,
                        namespace,
                        item.tenant_key,
                        item.organisation_key,
                        item.key,
                    ),
                    tenant_id=tenant_ids[item.tenant_key],
                    organisation_id=organisation_ids[item.organisation_key],
                    owner_unit_id=(
                        unit_ids[item.owner_unit_key]
                        if item.owner_unit_key is not None
                        else None
                    ),
                    display_label=f"Example Access Role {index:03d}",
                )
                for index, item in enumerate(blueprint.roles, start=1)
            ),
            key=lambda item: item.role_id,
        )
    )

    allocated_accounts = _compile_accounts(
        extension.account_allocations,
        namespace,
        seed,
        principals_by_population,
        targets_by_resource_set,
    )
    accounts = tuple(
        sorted(
            (item.account for item in allocated_accounts),
            key=lambda item: item.account_id,
        )
    )
    accounts_by_allocation = _group_accounts(allocated_accounts)
    bindings = tuple(
        sorted(
            (
                EnterpriseCanonicalAccountBindingV1(
                    account_id=item.account.account_id,
                    principal_id=item.principal_id,
                )
                for item in allocated_accounts
            ),
            key=lambda item: item.account_id,
        )
    )

    permissions = _compile_permissions(
        blueprint.resource_sets, namespace, targets_by_resource_set
    )
    access_atoms = _compile_atoms(
        import_model,
        namespace,
        seed,
        principals_by_population,
        targets_by_resource_set,
        accounts_by_allocation,
    )
    access_subjects = tuple(
        sorted(
            (
                *(
                    EnterpriseAccessSubjectV1(
                        subject_id=item.principal_id,
                        tenant_id=item.tenant_id,
                        subject_kind=AccessSubjectKind.PRINCIPAL,
                    )
                    for item in principals
                ),
                *(
                    EnterpriseAccessSubjectV1(
                        subject_id=item.account_id,
                        tenant_id=item.tenant_id,
                        subject_kind=AccessSubjectKind.ACCOUNT,
                    )
                    for item in accounts
                ),
            ),
            key=lambda item: item.subject_id,
        )
    )
    anchors = _compile_anchors(namespace, principals, accounts, groups, units, targets)

    universe = EnterpriseIdentityAccessUniverseV1(
        seed=seed,
        tenants=tuple(sorted(tenants, key=lambda item: item.tenant_id)),
        organisations=tuple(
            sorted(organisations, key=lambda item: item.organisation_id)
        ),
        units=tuple(sorted(units, key=lambda item: item.unit_id)),
        principals=principals,
        accounts=accounts,
        access_subjects=access_subjects,
        groups=groups,
        roles=roles,
        authorization_targets=targets,
        permissions=permissions,
        relationship_anchors=anchors,
        access_atoms=access_atoms,
    )
    universe_bytes = canonical_json_bytes(universe)
    truth = EnterpriseCanonicalBindingTruthV1(
        identity_access_universe_digest=synthetic_digest(universe_bytes),
        bindings=bindings,
    )
    _validate_post_freeze_state(import_model, universe)
    _check_outer_safety(
        selected_config.outer_safety,
        import_model,
        universe,
        truth,
        len(universe_bytes) + len(canonical_json_bytes(truth)),
    )
    return EnterpriseIdentityAccessCompileResultV1(universe, truth)


def _preflight_budget(
    import_model: EnterpriseIdentityAccessImportV1,
    budget: EnterpriseIdentityAccessCompileBudgetV1,
) -> None:
    blueprint = import_model.blueprint
    extension = import_model.iam_universe_extension
    state = import_model.directory_rbac_state
    populations = {item.key: item for item in blueprint.populations}
    resources = {item.key: item for item in blueprint.resource_sets}
    principal_count = sum(item.count for item in blueprint.populations)
    target_count = sum(item.instance_count for item in blueprint.resource_sets)
    action_count = sum(
        item.instance_count * len(item.actions) for item in blueprint.resource_sets
    )
    account_counts = {
        item.key: selector_count(item.selector, populations[item.population_key].count)
        * resources[item.resource_set_key].instance_count
        * item.accounts_per_selected_subject
        for item in extension.account_allocations
    }
    account_count = sum(account_counts.values())
    atom_count = sum(
        selector_count(rule.selector, populations[rule.population_key].count)
        * resources[rule.resource_set_key].instance_count
        for rule in blueprint.principal_access_atom_rules
    ) + sum(
        account_counts[rule.account_allocation_key]
        for rule in extension.account_access_atom_rules
    )
    checks = (
        ("max_principals", principal_count),
        ("max_accounts", account_count),
        ("max_groups", len(blueprint.groups)),
        ("max_roles", len(blueprint.roles)),
        ("max_authorization_targets", target_count),
        ("max_declared_actions", action_count),
        ("max_access_atoms", atom_count),
    )
    for field_name, measured in checks:
        _check_limit(
            "universe_budget_exceeded",
            field_name,
            measured,
            getattr(budget, field_name),
        )

    relation_count = sum(
        len(items)
        for items in (
            state.account_observations,
            state.memberships,
            state.group_nesting,
            state.group_role_assignments,
            state.population_role_assignments,
            state.role_hierarchy,
            state.role_grants,
            state.direct_entitlements,
        )
    )
    _check_limit(
        "directory_rbac_budget_exceeded",
        "max_directory_rbac_relations",
        relation_count,
        budget.max_directory_rbac_relations,
    )
    _, group_depth = dag_max_depth(
        {item.key for item in blueprint.groups},
        tuple(
            (item.child_group_key, item.parent_group_key)
            for item in state.group_nesting
        ),
    )
    _check_limit(
        "directory_rbac_budget_exceeded",
        "max_group_depth",
        group_depth,
        budget.max_group_depth,
    )
    _, role_depth = dag_max_depth(
        {item.key for item in blueprint.roles},
        tuple(
            (item.senior_role_key, item.junior_role_key)
            for item in state.role_hierarchy
        ),
    )
    _check_limit(
        "directory_rbac_budget_exceeded",
        "max_role_depth",
        role_depth,
        budget.max_role_depth,
    )


def _compile_principals(
    populations: tuple[PopulationTemplateV1, ...],
    namespace: UUID,
    tenant_ids: dict[str, str],
    organisation_ids: dict[str, str],
    unit_ids: dict[str, str],
) -> tuple[_PrincipalSlot, ...]:
    rows: list[_PrincipalSlot] = []
    label_index = 0
    for population in populations:
        for slot in range(population.count):
            label_index += 1
            principal_id = stable_enterprise_id(
                ENTERPRISE_PRINCIPAL_NAMESPACE_V1,
                namespace,
                population.key,
                str(slot),
            )
            rows.append(
                _PrincipalSlot(
                    population_key=population.key,
                    slot=slot,
                    principal=EnterprisePrincipalV1(
                        principal_id=principal_id,
                        tenant_id=tenant_ids[population.tenant_key],
                        organisation_id=organisation_ids[population.organisation_key],
                        unit_id=unit_ids[population.unit_key],
                        principal_kind=population.population_kind,
                        display_label=(
                            f"Example {population.population_kind.value.title()} "
                            f"Principal {label_index:06d}"
                        ),
                    ),
                )
            )
    return tuple(rows)


def _group_principals(
    slots: tuple[_PrincipalSlot, ...],
) -> dict[str, tuple[_PrincipalSlot, ...]]:
    grouped: dict[str, list[_PrincipalSlot]] = {}
    for slot in slots:
        grouped.setdefault(slot.population_key, []).append(slot)
    return {key: tuple(value) for key, value in grouped.items()}


def _compile_targets(
    resource_sets: tuple[ResourceSetTemplateV1, ...],
    namespace: UUID,
    tenant_ids: dict[str, str],
    organisation_ids: dict[str, str],
    unit_ids: dict[str, str],
) -> dict[str, tuple[_TargetSlot, ...]]:
    grouped: dict[str, tuple[_TargetSlot, ...]] = {}
    label_index = 0
    for resource_set in resource_sets:
        rows: list[_TargetSlot] = []
        for slot in range(resource_set.instance_count):
            label_index += 1
            target_id = stable_enterprise_id(
                ENTERPRISE_TARGET_NAMESPACE_V1,
                namespace,
                resource_set.key,
                str(slot),
            )
            rows.append(
                _TargetSlot(
                    resource_set_key=resource_set.key,
                    slot=slot,
                    target=EnterpriseAuthorizationTargetV1(
                        authorization_target_id=target_id,
                        tenant_id=tenant_ids[resource_set.tenant_key],
                        organisation_id=organisation_ids[resource_set.organisation_key],
                        target_kind=resource_set.target_kind,
                        owner_unit_id=(
                            unit_ids[resource_set.owner_unit_key]
                            if resource_set.owner_unit_key is not None
                            else None
                        ),
                        actions=resource_set.actions,
                        display_label=f"Example Authorization Target {label_index:06d}",
                    ),
                )
            )
        grouped[resource_set.key] = tuple(rows)
    return grouped


def _compile_accounts(
    allocations: tuple[AccountAllocationTemplateV1, ...],
    namespace: UUID,
    seed: int,
    principals: dict[str, tuple[_PrincipalSlot, ...]],
    targets: dict[str, tuple[_TargetSlot, ...]],
) -> tuple[_AllocatedAccount, ...]:
    rows: list[_AllocatedAccount] = []
    label_index = 0
    for allocation in allocations:
        selected = _select_principals(
            principals[allocation.population_key],
            allocation.selector,
            seed=seed,
            namespace=namespace,
            selection_key=allocation.key,
        )
        for principal_slot in selected:
            for target_slot in targets[allocation.resource_set_key]:
                for account_slot in range(allocation.accounts_per_selected_subject):
                    label_index += 1
                    account_id = stable_enterprise_id(
                        ENTERPRISE_ACCOUNT_NAMESPACE_V1,
                        namespace,
                        allocation.key,
                        allocation.population_key,
                        str(principal_slot.slot),
                        allocation.resource_set_key,
                        str(target_slot.slot),
                        str(account_slot),
                    )
                    rows.append(
                        _AllocatedAccount(
                            allocation_key=allocation.key,
                            principal_id=principal_slot.principal.principal_id,
                            account=EnterpriseAccountV1(
                                account_id=account_id,
                                tenant_id=principal_slot.principal.tenant_id,
                                authorization_target_id=(
                                    target_slot.target.authorization_target_id
                                ),
                                account_kind=allocation.account_kind,
                                display_label=f"Example Account {label_index:06d}",
                            ),
                        )
                    )
    return tuple(rows)


def _group_accounts(
    accounts: tuple[_AllocatedAccount, ...],
) -> dict[str, tuple[_AllocatedAccount, ...]]:
    grouped: dict[str, list[_AllocatedAccount]] = {}
    for account in accounts:
        grouped.setdefault(account.allocation_key, []).append(account)
    return {key: tuple(value) for key, value in grouped.items()}


def _compile_permissions(
    resource_sets: tuple[ResourceSetTemplateV1, ...],
    namespace: UUID,
    targets: dict[str, tuple[_TargetSlot, ...]],
) -> tuple[EnterprisePermissionV1, ...]:
    rows = (
        EnterprisePermissionV1(
            permission_id=stable_enterprise_id(
                ENTERPRISE_PERMISSION_NAMESPACE_V1,
                namespace,
                target.target.authorization_target_id,
                action,
            ),
            authorization_target_id=target.target.authorization_target_id,
            action=action,
        )
        for resource_set in resource_sets
        for target in targets[resource_set.key]
        for action in resource_set.actions
    )
    return tuple(sorted(rows, key=lambda item: item.permission_id))


def _compile_atoms(
    import_model: EnterpriseIdentityAccessImportV1,
    namespace: UUID,
    seed: int,
    principals: dict[str, tuple[_PrincipalSlot, ...]],
    targets: dict[str, tuple[_TargetSlot, ...]],
    accounts: dict[str, tuple[_AllocatedAccount, ...]],
) -> tuple[AccessAtomV1, ...]:
    semantic_rows: dict[tuple[str, str, str], str] = {}
    for principal_rule in import_model.blueprint.principal_access_atom_rules:
        selected = _select_principals(
            principals[principal_rule.population_key],
            principal_rule.selector,
            seed=seed,
            namespace=namespace,
            selection_key=principal_rule.rule_key,
        )
        for principal in selected:
            for target in targets[principal_rule.resource_set_key]:
                _declare_atom(
                    semantic_rows,
                    principal.principal.principal_id,
                    target.target.authorization_target_id,
                    principal_rule.action,
                    principal_rule.rule_key,
                )
    for account_rule in import_model.iam_universe_extension.account_access_atom_rules:
        for account in accounts[account_rule.account_allocation_key]:
            _declare_atom(
                semantic_rows,
                account.account.account_id,
                account.account.authorization_target_id,
                account_rule.action,
                account_rule.rule_key,
            )
    return tuple(
        sorted(
            (
                AccessAtomV1(
                    access_atom_id=stable_enterprise_id(
                        ENTERPRISE_ACCESS_ATOM_NAMESPACE_V1,
                        namespace,
                        subject_id,
                        target_id,
                        action,
                    ),
                    subject_id=subject_id,
                    authorization_target_id=target_id,
                    action=action,
                )
                for subject_id, target_id, action in semantic_rows
            ),
            key=lambda item: item.access_atom_id,
        )
    )


def _declare_atom(
    rows: dict[tuple[str, str, str], str],
    subject_id: str,
    target_id: str,
    action: str,
    rule_key: str,
) -> None:
    semantic_key = (subject_id, target_id, action)
    prior = rows.get(semantic_key)
    if prior is not None:
        raise EnterpriseCompileError(
            "duplicate_access_atom_declaration",
            f"rules {prior!r} and {rule_key!r} declare the same access atom",
        )
    rows[semantic_key] = rule_key


def _compile_anchors(
    namespace: UUID,
    principals: tuple[EnterprisePrincipalV1, ...],
    accounts: tuple[EnterpriseAccountV1, ...],
    groups: tuple[EnterpriseGroupV1, ...],
    units: tuple[EnterpriseUnitV1, ...],
    targets: tuple[EnterpriseAuthorizationTargetV1, ...],
) -> tuple[EnterpriseRelationshipAnchorV1, ...]:
    rows: list[EnterpriseRelationshipAnchorV1] = []
    sources: tuple[tuple[RelationshipAnchorKind, Iterable[tuple[str, str]]], ...] = (
        (
            RelationshipAnchorKind.PRINCIPAL,
            ((item.principal_id, item.tenant_id) for item in principals),
        ),
        (
            RelationshipAnchorKind.ACCOUNT,
            ((item.account_id, item.tenant_id) for item in accounts),
        ),
        (
            RelationshipAnchorKind.GROUP,
            ((item.group_id, item.tenant_id) for item in groups),
        ),
        (
            RelationshipAnchorKind.UNIT,
            ((item.unit_id, item.tenant_id) for item in units),
        ),
        (
            RelationshipAnchorKind.AUTHORIZATION_TARGET,
            ((item.authorization_target_id, item.tenant_id) for item in targets),
        ),
    )
    for kind, entities in sources:
        for entity_id, tenant_id in entities:
            rows.append(
                EnterpriseRelationshipAnchorV1(
                    anchor_id=stable_enterprise_id(
                        ENTERPRISE_RELATIONSHIP_ANCHOR_NAMESPACE_V1,
                        namespace,
                        kind.value,
                        entity_id,
                    ),
                    tenant_id=tenant_id,
                    entity_kind=kind,
                    entity_id=entity_id,
                )
            )
    return tuple(sorted(rows, key=lambda item: item.anchor_id))


def _select_principals(
    population: tuple[_PrincipalSlot, ...],
    selector: SelectorV1,
    *,
    seed: int,
    namespace: UUID,
    selection_key: str,
) -> tuple[_PrincipalSlot, ...]:
    count = selector_count(selector, len(population))
    ranked = sorted(
        population,
        key=lambda item: (
            hashlib.sha256(
                encode_parts(
                    (
                        ENTERPRISE_SELECTOR_ALGORITHM_VERSION,
                        str(seed),
                        str(namespace),
                        item.population_key,
                        selection_key,
                        str(item.slot),
                    )
                ).encode("utf-8")
            ).digest(),
            item.principal.principal_id,
        ),
    )
    return tuple(sorted(ranked[:count], key=lambda item: item.principal.principal_id))


def _validate_post_freeze_state(
    import_model: EnterpriseIdentityAccessImportV1,
    universe: EnterpriseIdentityAccessUniverseV1,
) -> None:
    accounts = {item.account_id: item for item in universe.accounts}
    principals = {item.principal_id: item for item in universe.principals}
    subjects = {item.subject_id: item for item in universe.access_subjects}
    targets = {
        item.authorization_target_id: item for item in universe.authorization_targets
    }
    atoms = {
        (item.subject_id, item.authorization_target_id, item.action)
        for item in universe.access_atoms
    }
    for observation in import_model.directory_rbac_state.account_observations:
        account = accounts.get(observation.account_id)
        if account is None:
            raise EnterpriseCompileError(
                "unknown_account_observation", "account observation does not resolve"
            )
        if observation.observed_principal_id is not None:
            principal = principals.get(observation.observed_principal_id)
            if principal is None:
                raise EnterpriseCompileError(
                    "unknown_observed_principal",
                    "observed account binding does not resolve",
                )
            if principal.tenant_id != account.tenant_id:
                raise EnterpriseCompileError(
                    "cross_tenant_observed_binding",
                    "observed account binding cannot cross tenant boundaries",
                )
    for entitlement in import_model.directory_rbac_state.direct_entitlements:
        subject = subjects.get(entitlement.subject_id)
        target = targets.get(entitlement.authorization_target_id)
        if subject is None or target is None:
            raise EnterpriseCompileError(
                "unknown_direct_entitlement_reference",
                "direct entitlement subject or target does not resolve",
            )
        if subject.tenant_id != target.tenant_id:
            raise EnterpriseCompileError(
                "cross_tenant_direct_entitlement",
                "direct entitlement cannot cross tenant boundaries",
            )
        if (
            entitlement.subject_id,
            entitlement.authorization_target_id,
            entitlement.action,
        ) not in atoms:
            raise EnterpriseCompileError(
                "undeclared_access_atom",
                "direct entitlement falls outside the frozen access-atom inventory",
            )


def _check_outer_safety(
    safety: EnterpriseCompileOuterSafetyV1,
    import_model: EnterpriseIdentityAccessImportV1,
    universe: EnterpriseIdentityAccessUniverseV1,
    truth: EnterpriseCanonicalBindingTruthV1,
    canonical_bytes: int,
) -> None:
    collections = (
        universe.tenants,
        universe.organisations,
        universe.units,
        universe.principals,
        universe.accounts,
        universe.access_subjects,
        universe.groups,
        universe.roles,
        universe.authorization_targets,
        universe.permissions,
        universe.relationship_anchors,
        universe.access_atoms,
        truth.bindings,
    )
    records = sum(len(items) for items in collections)
    state = import_model.directory_rbac_state
    relations = len(truth.bindings) + sum(
        len(items)
        for items in (
            state.account_observations,
            state.memberships,
            state.group_nesting,
            state.group_role_assignments,
            state.population_role_assignments,
            state.role_hierarchy,
            state.role_grants,
            state.direct_entitlements,
        )
    )
    expanded_steps = len(universe.access_atoms) + len(universe.permissions)
    work_units = records + relations + expanded_steps
    for field_name, measured in (
        ("max_serialized_records", records),
        ("max_relations", relations),
        ("max_expanded_steps", expanded_steps),
        ("max_canonical_bytes", canonical_bytes),
        ("max_work_units", work_units),
    ):
        _check_limit(
            "outer_safety_exceeded", field_name, measured, getattr(safety, field_name)
        )


def _check_limit(code: str, field_name: str, measured: int, allowed: int) -> None:
    if measured > allowed:
        raise EnterpriseCompileError(
            code,
            f"{field_name} exceeded",
            measured=measured,
            allowed=allowed,
        )


__all__ = [
    "EnterpriseCompileError",
    "compile_enterprise_identity_access_universe",
]
