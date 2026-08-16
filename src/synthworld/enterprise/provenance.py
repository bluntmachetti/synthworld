"""Operator-side mappings from authored enterprise rows to compiled identifiers."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Self
from uuid import UUID, uuid5

from pydantic import Field, field_validator, model_validator

from synthworld.enterprise.canonical import (
    ENTERPRISE_ACCESS_ATOM_NAMESPACE_V1,
    ENTERPRISE_ACCOUNT_NAMESPACE_V1,
    ENTERPRISE_GROUP_NAMESPACE_V1,
    ENTERPRISE_ORGANISATION_NAMESPACE_V1,
    ENTERPRISE_PERMISSION_NAMESPACE_V1,
    ENTERPRISE_PRINCIPAL_NAMESPACE_V1,
    ENTERPRISE_ROLE_NAMESPACE_V1,
    ENTERPRISE_TARGET_NAMESPACE_V1,
    ENTERPRISE_TENANT_NAMESPACE_V1,
    ENTERPRISE_UNIT_NAMESPACE_V1,
    blueprint_namespace_uuid,
    encode_parts,
    stable_enterprise_id,
)
from synthworld.enterprise.digests import digest_enterprise_model
from synthworld.enterprise.models import (
    ENTERPRISE_COMPILER_VERSION,
    ENTERPRISE_SELECTOR_ALGORITHM_VERSION,
    EnterpriseIdentityAccessCompileResultV1,
    EnterpriseIdentityAccessImportV1,
    EnterpriseIdentityAccessUniverseV1,
    EnterpriseOperatorModel,
    LogicalKey,
    SelectorV1,
    SyntheticDigestV1,
)
from synthworld.enterprise.rbac.common import (
    ENTERPRISE_DIRECTORY_RBAC_COMPILER_VERSION,
    canonical_operator_records,
)
from synthworld.enterprise.rbac.kernel import (
    ENTERPRISE_DIRECTORY_RBAC_RECORD_NAMESPACE_V1,
)
from synthworld.enterprise.rbac.models import EnterpriseDirectoryRbacKernelV1
from synthworld.enterprise.selection import select_principal_slot_indices

ENTERPRISE_COMPILER_PROVENANCE_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"


class EnterpriseCompilerSourceKind(StrEnum):
    """Closed authored-row vocabulary for compiler provenance v1."""

    TENANT = "tenant"
    ORGANISATION = "organisation"
    UNIT = "unit"
    POPULATION = "population"
    GROUP = "group"
    ROLE = "role"
    RESOURCE_SET = "resource_set"
    PRINCIPAL_ACCESS_RULE = "principal_access_rule"
    ACCOUNT_ALLOCATION = "account_allocation"
    ACCOUNT_ACCESS_RULE = "account_access_rule"
    ACCOUNT_OBSERVATION = "account_observation"
    MEMBERSHIP_RULE = "membership_rule"
    GROUP_NESTING = "group_nesting"
    GROUP_ROLE_ASSIGNMENT = "group_role_assignment"
    POPULATION_ROLE_ASSIGNMENT = "population_role_assignment"
    ROLE_HIERARCHY = "role_hierarchy"
    ROLE_GRANT = "role_grant"
    DIRECT_ENTITLEMENT = "direct_entitlement"


class EnterpriseCompiledObjectKind(StrEnum):
    """Closed compiled-record vocabulary for compiler provenance v1."""

    TENANT = "tenant"
    ORGANISATION = "organisation"
    UNIT = "unit"
    PRINCIPAL = "principal"
    GROUP = "group"
    ROLE = "role"
    AUTHORIZATION_TARGET = "authorization_target"
    PERMISSION = "permission"
    ACCOUNT = "account"
    ACCESS_ATOM = "access_atom"
    ACCOUNT_OBSERVATION = "account_observation"
    MEMBERSHIP_EDGE = "membership_edge"
    GROUP_NESTING_EDGE = "group_nesting_edge"
    GROUP_ROLE_ASSIGNMENT = "group_role_assignment"
    SUBJECT_ROLE_ASSIGNMENT = "subject_role_assignment"
    ROLE_HIERARCHY_EDGE = "role_hierarchy_edge"
    ROLE_GRANT = "role_grant"
    DIRECT_ENTITLEMENT = "direct_entitlement"


class EnterpriseCompiledObjectReferenceV1(EnterpriseOperatorModel):
    """One opaque compiled record produced from an authored source row."""

    object_kind: EnterpriseCompiledObjectKind
    stable_id: str = Field(min_length=1)
    slot: int | None = Field(default=None, ge=0)
    action: LogicalKey | None = None


class EnterpriseCompilerProvenanceEntryV1(EnterpriseOperatorModel):
    """Canonical source location and the records it produced."""

    source_kind: EnterpriseCompilerSourceKind
    logical_key: tuple[LogicalKey, ...] = Field(min_length=1)
    source_path: str = Field(
        pattern=r"^/(blueprint|iam_universe_extension|directory_rbac_state)/"
    )
    compiled_objects: tuple[EnterpriseCompiledObjectReferenceV1, ...] = Field(
        min_length=1
    )

    @field_validator("compiled_objects")
    @classmethod
    def canonical_objects(
        cls, value: tuple[EnterpriseCompiledObjectReferenceV1, ...]
    ) -> tuple[EnterpriseCompiledObjectReferenceV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple(
                (
                    item.object_kind.value,
                    item.stable_id,
                    str(item.slot) if item.slot is not None else "",
                    item.action or "",
                )
                for item in value
            ),
            description="compiler_provenance_compiled_object",
        )


class EnterpriseCompilerProvenanceV1(EnterpriseOperatorModel):
    """Private/operator artifact linking canonical authored rows to outputs."""

    schema_version: Literal["1.0.0"] = ENTERPRISE_COMPILER_PROVENANCE_SCHEMA_VERSION
    compiler_version: Literal["1.0.0"] = ENTERPRISE_COMPILER_VERSION
    selector_algorithm_version: Literal["1.0.0"] = ENTERPRISE_SELECTOR_ALGORITHM_VERSION
    directory_rbac_compiler_version: Literal["1.0.0"] = (
        ENTERPRISE_DIRECTORY_RBAC_COMPILER_VERSION
    )
    seed: int
    source_import_digest: SyntheticDigestV1
    public_universe_digest: SyntheticDigestV1
    directory_rbac_kernel_digest: SyntheticDigestV1
    entries: tuple[EnterpriseCompilerProvenanceEntryV1, ...] = Field(min_length=1)

    @field_validator("entries")
    @classmethod
    def canonical_entries(
        cls, value: tuple[EnterpriseCompilerProvenanceEntryV1, ...]
    ) -> tuple[EnterpriseCompilerProvenanceEntryV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple((item.source_path,) for item in value),
            description="compiler_provenance_source_path",
        )

    @model_validator(mode="after")
    def one_entry_per_source_key(self) -> Self:
        keys = tuple((item.source_kind, item.logical_key) for item in self.entries)
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate_compiler_provenance_source_key")
        return self


def build_enterprise_compiler_provenance(
    *,
    import_model: EnterpriseIdentityAccessImportV1,
    compile_result: EnterpriseIdentityAccessCompileResultV1,
    directory_rbac_kernel: EnterpriseDirectoryRbacKernelV1,
) -> EnterpriseCompilerProvenanceV1:
    """Map every authored topology and directory-policy row to compiled IDs.

    ``source_path`` values are JSON Pointers into the canonical validated import,
    not line numbers in a source YAML/CSV file. The result is deliberately not
    included in either the public product-input tree or evaluator truth tree.
    """

    universe = compile_result.public_universe
    universe_digest = digest_enterprise_model(universe)
    if directory_rbac_kernel.identity_access_universe_digest != universe_digest:
        raise ValueError("compiler_provenance_kernel_universe_digest_mismatch")
    state_digest = digest_enterprise_model(import_model.directory_rbac_state)
    if directory_rbac_kernel.directory_rbac_state_input_digest != state_digest:
        raise ValueError("compiler_provenance_kernel_source_digest_mismatch")

    blueprint = import_model.blueprint
    extension = import_model.iam_universe_extension
    state = import_model.directory_rbac_state
    namespace = blueprint_namespace_uuid(blueprint.id_namespace_salt)

    principal_ids = {
        item.key: tuple(
            stable_enterprise_id(
                ENTERPRISE_PRINCIPAL_NAMESPACE_V1, namespace, item.key, str(slot)
            )
            for slot in range(item.count)
        )
        for item in blueprint.populations
    }
    target_ids = {
        item.key: tuple(
            stable_enterprise_id(
                ENTERPRISE_TARGET_NAMESPACE_V1, namespace, item.key, str(slot)
            )
            for slot in range(item.instance_count)
        )
        for item in blueprint.resource_sets
    }
    group_ids = {
        item.key: stable_enterprise_id(
            ENTERPRISE_GROUP_NAMESPACE_V1,
            namespace,
            item.tenant_key,
            item.organisation_key,
            item.key,
        )
        for item in blueprint.groups
    }
    role_ids = {
        item.key: stable_enterprise_id(
            ENTERPRISE_ROLE_NAMESPACE_V1,
            namespace,
            item.tenant_key,
            item.organisation_key,
            item.key,
        )
        for item in blueprint.roles
    }
    population_counts = {item.key: item.count for item in blueprint.populations}
    accounts_by_allocation: dict[str, tuple[tuple[str, str, int], ...]] = {}
    for allocation in extension.account_allocations:
        selected_slots = _selected_slots(
            population_key=allocation.population_key,
            population_count=population_counts[allocation.population_key],
            selector=allocation.selector,
            seed=universe.seed,
            namespace=namespace,
            selection_key=allocation.key,
        )
        rows: list[tuple[str, str, int]] = []
        for principal_slot in selected_slots:
            for target_slot, target_id in enumerate(
                target_ids[allocation.resource_set_key]
            ):
                for account_slot in range(allocation.accounts_per_selected_subject):
                    account_id = stable_enterprise_id(
                        ENTERPRISE_ACCOUNT_NAMESPACE_V1,
                        namespace,
                        allocation.key,
                        allocation.population_key,
                        str(principal_slot),
                        allocation.resource_set_key,
                        str(target_slot),
                        str(account_slot),
                    )
                    rows.append((account_id, target_id, account_slot))
        accounts_by_allocation[allocation.key] = tuple(rows)

    entries: list[EnterpriseCompilerProvenanceEntryV1] = []
    inventories = _compiled_inventories(universe, directory_rbac_kernel)

    def add(
        source_kind: EnterpriseCompilerSourceKind,
        logical_key: tuple[str, ...],
        source_path: str,
        references: tuple[EnterpriseCompiledObjectReferenceV1, ...],
    ) -> None:
        _require_compiled_references(inventories, references)
        entries.append(
            EnterpriseCompilerProvenanceEntryV1(
                source_kind=source_kind,
                logical_key=logical_key,
                source_path=source_path,
                compiled_objects=references,
            )
        )

    for index, tenant in enumerate(blueprint.tenants):
        add(
            EnterpriseCompilerSourceKind.TENANT,
            (tenant.key,),
            f"/blueprint/tenants/{index}",
            (
                _reference(
                    EnterpriseCompiledObjectKind.TENANT,
                    stable_enterprise_id(
                        ENTERPRISE_TENANT_NAMESPACE_V1, namespace, tenant.key
                    ),
                ),
            ),
        )
    for index, organisation in enumerate(blueprint.organisations):
        add(
            EnterpriseCompilerSourceKind.ORGANISATION,
            (organisation.key,),
            f"/blueprint/organisations/{index}",
            (
                _reference(
                    EnterpriseCompiledObjectKind.ORGANISATION,
                    stable_enterprise_id(
                        ENTERPRISE_ORGANISATION_NAMESPACE_V1,
                        namespace,
                        organisation.tenant_key,
                        organisation.key,
                    ),
                ),
            ),
        )
    for index, unit in enumerate(blueprint.units):
        add(
            EnterpriseCompilerSourceKind.UNIT,
            (unit.key,),
            f"/blueprint/units/{index}",
            (
                _reference(
                    EnterpriseCompiledObjectKind.UNIT,
                    stable_enterprise_id(
                        ENTERPRISE_UNIT_NAMESPACE_V1,
                        namespace,
                        unit.tenant_key,
                        unit.organisation_key,
                        unit.key,
                    ),
                ),
            ),
        )
    for index, population in enumerate(blueprint.populations):
        add(
            EnterpriseCompilerSourceKind.POPULATION,
            (population.key,),
            f"/blueprint/populations/{index}",
            tuple(
                _reference(
                    EnterpriseCompiledObjectKind.PRINCIPAL, identifier, slot=slot
                )
                for slot, identifier in enumerate(principal_ids[population.key])
            ),
        )
    for index, group in enumerate(blueprint.groups):
        add(
            EnterpriseCompilerSourceKind.GROUP,
            (group.key,),
            f"/blueprint/groups/{index}",
            (_reference(EnterpriseCompiledObjectKind.GROUP, group_ids[group.key]),),
        )
    for index, role in enumerate(blueprint.roles):
        add(
            EnterpriseCompilerSourceKind.ROLE,
            (role.key,),
            f"/blueprint/roles/{index}",
            (_reference(EnterpriseCompiledObjectKind.ROLE, role_ids[role.key]),),
        )
    for index, resource_set in enumerate(blueprint.resource_sets):
        references = [
            _reference(
                EnterpriseCompiledObjectKind.AUTHORIZATION_TARGET,
                identifier,
                slot=slot,
            )
            for slot, identifier in enumerate(target_ids[resource_set.key])
        ]
        references.extend(
            _reference(
                EnterpriseCompiledObjectKind.PERMISSION,
                stable_enterprise_id(
                    ENTERPRISE_PERMISSION_NAMESPACE_V1, namespace, target_id, action
                ),
                slot=slot,
                action=action,
            )
            for slot, target_id in enumerate(target_ids[resource_set.key])
            for action in resource_set.actions
        )
        add(
            EnterpriseCompilerSourceKind.RESOURCE_SET,
            (resource_set.key,),
            f"/blueprint/resource_sets/{index}",
            tuple(references),
        )
    for index, principal_rule in enumerate(blueprint.principal_access_atom_rules):
        slots = _selected_slots(
            population_key=principal_rule.population_key,
            population_count=population_counts[principal_rule.population_key],
            selector=principal_rule.selector,
            seed=universe.seed,
            namespace=namespace,
            selection_key=principal_rule.rule_key,
        )
        add(
            EnterpriseCompilerSourceKind.PRINCIPAL_ACCESS_RULE,
            (principal_rule.rule_key,),
            f"/blueprint/principal_access_atom_rules/{index}",
            tuple(
                _reference(
                    EnterpriseCompiledObjectKind.ACCESS_ATOM,
                    stable_enterprise_id(
                        ENTERPRISE_ACCESS_ATOM_NAMESPACE_V1,
                        namespace,
                        principal_ids[principal_rule.population_key][slot],
                        target_id,
                        principal_rule.action,
                    ),
                    slot=slot,
                    action=principal_rule.action,
                )
                for slot in slots
                for target_id in target_ids[principal_rule.resource_set_key]
            ),
        )
    for index, allocation in enumerate(extension.account_allocations):
        add(
            EnterpriseCompilerSourceKind.ACCOUNT_ALLOCATION,
            (allocation.key,),
            f"/iam_universe_extension/account_allocations/{index}",
            tuple(
                _reference(EnterpriseCompiledObjectKind.ACCOUNT, account_id, slot=slot)
                for account_id, _, slot in accounts_by_allocation[allocation.key]
            ),
        )
    for index, account_rule in enumerate(extension.account_access_atom_rules):
        add(
            EnterpriseCompilerSourceKind.ACCOUNT_ACCESS_RULE,
            (account_rule.rule_key,),
            f"/iam_universe_extension/account_access_atom_rules/{index}",
            tuple(
                _reference(
                    EnterpriseCompiledObjectKind.ACCESS_ATOM,
                    stable_enterprise_id(
                        ENTERPRISE_ACCESS_ATOM_NAMESPACE_V1,
                        namespace,
                        account_id,
                        target_id,
                        account_rule.action,
                    ),
                    slot=slot,
                    action=account_rule.action,
                )
                for account_id, target_id, slot in accounts_by_allocation[
                    account_rule.account_allocation_key
                ]
            ),
        )

    for index, observation in enumerate(state.account_observations):
        add(
            EnterpriseCompilerSourceKind.ACCOUNT_OBSERVATION,
            (observation.account_id, observation.revision_id),
            f"/directory_rbac_state/account_observations/{index}",
            (
                _reference(
                    EnterpriseCompiledObjectKind.ACCOUNT_OBSERVATION,
                    observation.account_id,
                ),
            ),
        )
    for index, membership in enumerate(state.memberships):
        subject_ids = _selected_principal_ids(
            membership.population_key,
            population_counts[membership.population_key],
            membership.selector,
            universe.seed,
            namespace,
            membership.rule_key,
        )
        group_id = group_ids[membership.group_key]
        add(
            EnterpriseCompilerSourceKind.MEMBERSHIP_RULE,
            (membership.rule_key,),
            f"/directory_rbac_state/memberships/{index}",
            tuple(
                _reference(
                    EnterpriseCompiledObjectKind.MEMBERSHIP_EDGE,
                    _kernel_record_id(
                        universe_digest.value, "membership", subject_id, group_id
                    ),
                )
                for subject_id in subject_ids
            ),
        )
    for index, nesting in enumerate(state.group_nesting):
        child_id = group_ids[nesting.child_group_key]
        parent_id = group_ids[nesting.parent_group_key]
        add(
            EnterpriseCompilerSourceKind.GROUP_NESTING,
            (nesting.child_group_key, nesting.parent_group_key),
            f"/directory_rbac_state/group_nesting/{index}",
            (
                _reference(
                    EnterpriseCompiledObjectKind.GROUP_NESTING_EDGE,
                    _kernel_record_id(
                        universe_digest.value, "group-nesting", child_id, parent_id
                    ),
                ),
            ),
        )
    for index, group_role in enumerate(state.group_role_assignments):
        group_id = group_ids[group_role.group_key]
        role_id = role_ids[group_role.role_key]
        add(
            EnterpriseCompilerSourceKind.GROUP_ROLE_ASSIGNMENT,
            (group_role.group_key, group_role.role_key),
            f"/directory_rbac_state/group_role_assignments/{index}",
            (
                _reference(
                    EnterpriseCompiledObjectKind.GROUP_ROLE_ASSIGNMENT,
                    _kernel_record_id(
                        universe_digest.value, "group-role", group_id, role_id
                    ),
                ),
            ),
        )
    for index, population_role in enumerate(state.population_role_assignments):
        role_id = role_ids[population_role.role_key]
        subject_ids = _selected_principal_ids(
            population_role.population_key,
            population_counts[population_role.population_key],
            population_role.selector,
            universe.seed,
            namespace,
            population_role.rule_key,
        )
        add(
            EnterpriseCompilerSourceKind.POPULATION_ROLE_ASSIGNMENT,
            (population_role.rule_key,),
            f"/directory_rbac_state/population_role_assignments/{index}",
            tuple(
                _reference(
                    EnterpriseCompiledObjectKind.SUBJECT_ROLE_ASSIGNMENT,
                    _kernel_record_id(
                        universe_digest.value, "subject-role", subject_id, role_id
                    ),
                )
                for subject_id in subject_ids
            ),
        )
    for index, hierarchy in enumerate(state.role_hierarchy):
        senior_id = role_ids[hierarchy.senior_role_key]
        junior_id = role_ids[hierarchy.junior_role_key]
        add(
            EnterpriseCompilerSourceKind.ROLE_HIERARCHY,
            (hierarchy.senior_role_key, hierarchy.junior_role_key),
            f"/directory_rbac_state/role_hierarchy/{index}",
            (
                _reference(
                    EnterpriseCompiledObjectKind.ROLE_HIERARCHY_EDGE,
                    _kernel_record_id(
                        universe_digest.value,
                        "role-hierarchy",
                        senior_id,
                        junior_id,
                    ),
                ),
            ),
        )
    for index, grant in enumerate(state.role_grants):
        role_id = role_ids[grant.role_key]
        add(
            EnterpriseCompilerSourceKind.ROLE_GRANT,
            (grant.role_key, grant.resource_set_key, grant.action),
            f"/directory_rbac_state/role_grants/{index}",
            tuple(
                _reference(
                    EnterpriseCompiledObjectKind.ROLE_GRANT,
                    _kernel_record_id(
                        universe_digest.value,
                        "role-grant",
                        role_id,
                        stable_enterprise_id(
                            ENTERPRISE_PERMISSION_NAMESPACE_V1,
                            namespace,
                            target_id,
                            grant.action,
                        ),
                    ),
                    action=grant.action,
                )
                for target_id in target_ids[grant.resource_set_key]
            ),
        )
    for index, entitlement in enumerate(state.direct_entitlements):
        add(
            EnterpriseCompilerSourceKind.DIRECT_ENTITLEMENT,
            (
                entitlement.subject_id,
                entitlement.authorization_target_id,
                entitlement.action,
                entitlement.revision_id,
            ),
            f"/directory_rbac_state/direct_entitlements/{index}",
            (
                _reference(
                    EnterpriseCompiledObjectKind.DIRECT_ENTITLEMENT,
                    _kernel_record_id(
                        universe_digest.value,
                        "direct-entitlement",
                        entitlement.subject_id,
                        entitlement.authorization_target_id,
                        entitlement.action,
                        entitlement.revision_id,
                    ),
                    action=entitlement.action,
                ),
            ),
        )

    return EnterpriseCompilerProvenanceV1(
        seed=universe.seed,
        source_import_digest=digest_enterprise_model(import_model),
        public_universe_digest=universe_digest,
        directory_rbac_kernel_digest=digest_enterprise_model(directory_rbac_kernel),
        entries=tuple(entries),
    )


def _reference(
    kind: EnterpriseCompiledObjectKind,
    stable_id: str,
    *,
    slot: int | None = None,
    action: str | None = None,
) -> EnterpriseCompiledObjectReferenceV1:
    return EnterpriseCompiledObjectReferenceV1(
        object_kind=kind, stable_id=stable_id, slot=slot, action=action
    )


def _selected_slots(
    *,
    population_key: str,
    population_count: int,
    selector: SelectorV1,
    seed: int,
    namespace: UUID,
    selection_key: str,
) -> tuple[int, ...]:
    return select_principal_slot_indices(
        population_key=population_key,
        population_count=population_count,
        selector=selector,
        seed=seed,
        blueprint_namespace=namespace,
        selection_key=selection_key,
    )


def _selected_principal_ids(
    population_key: str,
    population_count: int,
    selector: SelectorV1,
    seed: int,
    namespace: UUID,
    selection_key: str,
) -> tuple[str, ...]:
    selected = _selected_slots(
        population_key=population_key,
        population_count=population_count,
        selector=selector,
        seed=seed,
        namespace=namespace,
        selection_key=selection_key,
    )
    return tuple(
        stable_enterprise_id(
            ENTERPRISE_PRINCIPAL_NAMESPACE_V1,
            namespace,
            population_key,
            str(slot),
        )
        for slot in selected
    )


def _kernel_record_id(universe_digest: str, kind: str, *parts: str) -> str:
    return str(
        uuid5(
            ENTERPRISE_DIRECTORY_RBAC_RECORD_NAMESPACE_V1,
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


def _compiled_inventories(
    universe: EnterpriseIdentityAccessUniverseV1,
    kernel: EnterpriseDirectoryRbacKernelV1,
) -> dict[EnterpriseCompiledObjectKind, set[str]]:
    return {
        EnterpriseCompiledObjectKind.TENANT: {
            item.tenant_id for item in universe.tenants
        },
        EnterpriseCompiledObjectKind.ORGANISATION: {
            item.organisation_id for item in universe.organisations
        },
        EnterpriseCompiledObjectKind.UNIT: {item.unit_id for item in universe.units},
        EnterpriseCompiledObjectKind.PRINCIPAL: {
            item.principal_id for item in universe.principals
        },
        EnterpriseCompiledObjectKind.GROUP: {item.group_id for item in universe.groups},
        EnterpriseCompiledObjectKind.ROLE: {item.role_id for item in universe.roles},
        EnterpriseCompiledObjectKind.AUTHORIZATION_TARGET: {
            item.authorization_target_id for item in universe.authorization_targets
        },
        EnterpriseCompiledObjectKind.PERMISSION: {
            item.permission_id for item in universe.permissions
        },
        EnterpriseCompiledObjectKind.ACCOUNT: {
            item.account_id for item in universe.accounts
        },
        EnterpriseCompiledObjectKind.ACCESS_ATOM: {
            item.access_atom_id for item in universe.access_atoms
        },
        EnterpriseCompiledObjectKind.ACCOUNT_OBSERVATION: {
            item.account_id for item in kernel.account_observations
        },
        EnterpriseCompiledObjectKind.MEMBERSHIP_EDGE: {
            item.edge_id for item in kernel.memberships
        },
        EnterpriseCompiledObjectKind.GROUP_NESTING_EDGE: {
            item.edge_id for item in kernel.group_nesting
        },
        EnterpriseCompiledObjectKind.GROUP_ROLE_ASSIGNMENT: {
            item.edge_id for item in kernel.group_role_assignments
        },
        EnterpriseCompiledObjectKind.SUBJECT_ROLE_ASSIGNMENT: {
            item.edge_id for item in kernel.subject_role_assignments
        },
        EnterpriseCompiledObjectKind.ROLE_HIERARCHY_EDGE: {
            item.edge_id for item in kernel.role_hierarchy
        },
        EnterpriseCompiledObjectKind.ROLE_GRANT: {
            item.edge_id for item in kernel.role_grants
        },
        EnterpriseCompiledObjectKind.DIRECT_ENTITLEMENT: {
            item.entitlement_id for item in kernel.direct_entitlements
        },
    }


def _require_compiled_references(
    inventories: dict[EnterpriseCompiledObjectKind, set[str]],
    references: tuple[EnterpriseCompiledObjectReferenceV1, ...],
) -> None:
    for reference in references:
        if reference.stable_id not in inventories[reference.object_kind]:
            raise ValueError("compiler_provenance_compiled_reference_missing")


__all__ = [
    "ENTERPRISE_COMPILER_PROVENANCE_SCHEMA_VERSION",
    "EnterpriseCompiledObjectKind",
    "EnterpriseCompiledObjectReferenceV1",
    "EnterpriseCompilerProvenanceEntryV1",
    "EnterpriseCompilerProvenanceV1",
    "EnterpriseCompilerSourceKind",
    "build_enterprise_compiler_provenance",
]
