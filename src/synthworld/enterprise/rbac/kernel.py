"""Compile PR2 logical directory state into opaque fixed-universe RBAC records."""

from __future__ import annotations

from uuid import UUID, uuid5

from synthworld.enterprise.canonical import (
    ENTERPRISE_GROUP_NAMESPACE_V1,
    ENTERPRISE_PERMISSION_NAMESPACE_V1,
    ENTERPRISE_PRINCIPAL_NAMESPACE_V1,
    ENTERPRISE_ROLE_NAMESPACE_V1,
    ENTERPRISE_TARGET_NAMESPACE_V1,
    blueprint_namespace_uuid,
    canonical_json_bytes,
    encode_parts,
    stable_enterprise_id,
    synthetic_digest,
)
from synthworld.enterprise.compiler import (
    EnterpriseCompileError,
    compile_enterprise_identity_access_universe,
)
from synthworld.enterprise.models import (
    EnterpriseIdentityAccessCompileConfigV1,
    EnterpriseIdentityAccessImportV1,
    EnterpriseIdentityAccessUniverseV1,
    SelectorV1,
)
from synthworld.enterprise.rbac.common import (
    ENTERPRISE_DIRECTORY_RBAC_COMPILER_VERSION,
)
from synthworld.enterprise.rbac.models import (
    DirectoryAccountObservationV1,
    DirectoryDirectEntitlementV1,
    DirectoryGroupNestingEdgeV1,
    DirectoryGroupRoleAssignmentV1,
    DirectoryMembershipEdgeV1,
    DirectoryRoleGrantV1,
    DirectoryRoleHierarchyEdgeV1,
    DirectorySubjectRoleAssignmentV1,
    EnterpriseDirectoryRbacKernelV1,
)
from synthworld.enterprise.selection import select_principal_slot_indices
from synthworld.enterprise.validation import (
    ensure_valid_enterprise_identity_access,
    selector_count,
)

ENTERPRISE_DIRECTORY_RBAC_RECORD_NAMESPACE_V1 = UUID(
    "1f5c0753-3047-514a-a041-cf6a9d7c07d1"
)


def compile_enterprise_directory_rbac_kernel(
    *,
    import_model: EnterpriseIdentityAccessImportV1,
    universe: EnterpriseIdentityAccessUniverseV1,
    compile_config: EnterpriseIdentityAccessCompileConfigV1 | None = None,
) -> EnterpriseDirectoryRbacKernelV1:
    """Resolve high-level selection rules without changing the frozen universe."""

    ensure_valid_enterprise_identity_access(import_model)
    selected_config = compile_config or EnterpriseIdentityAccessCompileConfigV1()
    expected_universe = compile_enterprise_identity_access_universe(
        import_model=import_model,
        seed=universe.seed,
        config=selected_config,
    ).public_universe
    if canonical_json_bytes(expected_universe) != canonical_json_bytes(universe):
        raise EnterpriseCompileError(
            "kernel_universe_mapping_mismatch",
            "source import does not compile to the supplied frozen universe",
        )
    _preflight_kernel_budget(import_model, selected_config)
    universe_digest = synthetic_digest(canonical_json_bytes(universe))
    namespace = blueprint_namespace_uuid(import_model.blueprint.id_namespace_salt)
    maps = _OpaqueMaps(import_model, universe, namespace)
    state = import_model.directory_rbac_state

    account_observations = tuple(
        DirectoryAccountObservationV1(
            account_id=item.account_id,
            observed_principal_id=item.observed_principal_id,
            administrative_state=item.administrative_state,
            valid_from_tick=item.valid_from_tick,
            valid_until_tick=item.valid_until_tick,
            revision_id=_record_id(
                universe_digest.value,
                "account-observation-revision",
                item.account_id,
                item.revision_id,
            ),
        )
        for item in state.account_observations
    )

    memberships: list[DirectoryMembershipEdgeV1] = []
    for membership_rule in state.memberships:
        group_id = maps.group_ids[membership_rule.group_key]
        for principal_id in maps.selected_principal_ids(
            population_key=membership_rule.population_key,
            selector=membership_rule.selector,
            selection_key=membership_rule.rule_key,
        ):
            memberships.append(
                DirectoryMembershipEdgeV1(
                    edge_id=_record_id(
                        universe_digest.value,
                        "membership",
                        principal_id,
                        group_id,
                    ),
                    subject_id=principal_id,
                    group_id=group_id,
                )
            )

    group_nesting = tuple(
        DirectoryGroupNestingEdgeV1(
            edge_id=_record_id(
                universe_digest.value,
                "group-nesting",
                maps.group_ids[item.child_group_key],
                maps.group_ids[item.parent_group_key],
            ),
            child_group_id=maps.group_ids[item.child_group_key],
            parent_group_id=maps.group_ids[item.parent_group_key],
        )
        for item in state.group_nesting
    )
    group_role_assignments = tuple(
        DirectoryGroupRoleAssignmentV1(
            edge_id=_record_id(
                universe_digest.value,
                "group-role",
                maps.group_ids[item.group_key],
                maps.role_ids[item.role_key],
            ),
            group_id=maps.group_ids[item.group_key],
            role_id=maps.role_ids[item.role_key],
        )
        for item in state.group_role_assignments
    )
    subject_role_assignments: list[DirectorySubjectRoleAssignmentV1] = []
    for role_rule in state.population_role_assignments:
        role_id = maps.role_ids[role_rule.role_key]
        for principal_id in maps.selected_principal_ids(
            population_key=role_rule.population_key,
            selector=role_rule.selector,
            selection_key=role_rule.rule_key,
        ):
            subject_role_assignments.append(
                DirectorySubjectRoleAssignmentV1(
                    edge_id=_record_id(
                        universe_digest.value,
                        "subject-role",
                        principal_id,
                        role_id,
                    ),
                    subject_id=principal_id,
                    role_id=role_id,
                )
            )
    role_hierarchy = tuple(
        DirectoryRoleHierarchyEdgeV1(
            edge_id=_record_id(
                universe_digest.value,
                "role-hierarchy",
                maps.role_ids[item.senior_role_key],
                maps.role_ids[item.junior_role_key],
            ),
            senior_role_id=maps.role_ids[item.senior_role_key],
            junior_role_id=maps.role_ids[item.junior_role_key],
        )
        for item in state.role_hierarchy
    )
    role_grants = tuple(
        DirectoryRoleGrantV1(
            edge_id=_record_id(
                universe_digest.value,
                "role-grant",
                maps.role_ids[item.role_key],
                maps.permission_ids[(target_id, item.action)],
            ),
            role_id=maps.role_ids[item.role_key],
            permission_id=maps.permission_ids[(target_id, item.action)],
        )
        for item in state.role_grants
        for target_id in maps.target_ids[item.resource_set_key]
    )
    direct_entitlements = tuple(
        DirectoryDirectEntitlementV1(
            entitlement_id=_record_id(
                universe_digest.value,
                "direct-entitlement",
                item.subject_id,
                item.authorization_target_id,
                item.action,
                item.revision_id,
            ),
            subject_id=item.subject_id,
            permission_id=maps.permission_ids[
                (item.authorization_target_id, item.action)
            ],
            valid_from_tick=item.valid_from_tick,
            valid_until_tick=item.valid_until_tick,
            revision_id=_record_id(
                universe_digest.value,
                "direct-entitlement-revision",
                item.revision_id,
            ),
        )
        for item in state.direct_entitlements
    )
    _reject_duplicate_semantic_edges(
        memberships,
        subject_role_assignments,
    )
    kernel = EnterpriseDirectoryRbacKernelV1(
        identity_access_universe_digest=universe_digest,
        directory_rbac_state_input_digest=synthetic_digest(canonical_json_bytes(state)),
        compile_config_digest=synthetic_digest(canonical_json_bytes(selected_config)),
        account_observations=account_observations,
        memberships=tuple(memberships),
        group_nesting=group_nesting,
        group_role_assignments=group_role_assignments,
        subject_role_assignments=tuple(subject_role_assignments),
        role_hierarchy=role_hierarchy,
        role_grants=role_grants,
        direct_entitlements=direct_entitlements,
    )
    _check_kernel_outer_safety(kernel, selected_config)
    return kernel


class _OpaqueMaps:
    def __init__(
        self,
        import_model: EnterpriseIdentityAccessImportV1,
        universe: EnterpriseIdentityAccessUniverseV1,
        namespace: UUID,
    ) -> None:
        self.import_model = import_model
        self.universe = universe
        self.namespace = namespace
        blueprint = import_model.blueprint
        self.population_counts = {
            item.key: item.count for item in blueprint.populations
        }
        self.group_ids = {
            item.key: stable_enterprise_id(
                ENTERPRISE_GROUP_NAMESPACE_V1,
                namespace,
                item.tenant_key,
                item.organisation_key,
                item.key,
            )
            for item in blueprint.groups
        }
        self.role_ids = {
            item.key: stable_enterprise_id(
                ENTERPRISE_ROLE_NAMESPACE_V1,
                namespace,
                item.tenant_key,
                item.organisation_key,
                item.key,
            )
            for item in blueprint.roles
        }
        self.target_ids = {
            item.key: tuple(
                stable_enterprise_id(
                    ENTERPRISE_TARGET_NAMESPACE_V1,
                    namespace,
                    item.key,
                    str(slot),
                )
                for slot in range(item.instance_count)
            )
            for item in blueprint.resource_sets
        }
        self.permission_ids = {
            (target_id, action): stable_enterprise_id(
                ENTERPRISE_PERMISSION_NAMESPACE_V1,
                namespace,
                target_id,
                action,
            )
            for item in blueprint.resource_sets
            for target_id in self.target_ids[item.key]
            for action in item.actions
        }

    def selected_principal_ids(
        self,
        *,
        population_key: str,
        selector: SelectorV1,
        selection_key: str,
    ) -> tuple[str, ...]:
        slots = select_principal_slot_indices(
            population_key=population_key,
            population_count=self.population_counts[population_key],
            selector=selector,
            seed=self.universe.seed,
            blueprint_namespace=self.namespace,
            selection_key=selection_key,
        )
        return tuple(
            stable_enterprise_id(
                ENTERPRISE_PRINCIPAL_NAMESPACE_V1,
                self.namespace,
                population_key,
                str(slot),
            )
            for slot in slots
        )


def _preflight_kernel_budget(
    import_model: EnterpriseIdentityAccessImportV1,
    config: EnterpriseIdentityAccessCompileConfigV1,
) -> None:
    blueprint = import_model.blueprint
    state = import_model.directory_rbac_state
    populations = {item.key: item for item in blueprint.populations}
    resource_sets = {item.key: item for item in blueprint.resource_sets}
    relation_count = (
        len(state.account_observations)
        + sum(
            selector_count(item.selector, populations[item.population_key].count)
            for item in state.memberships
        )
        + len(state.group_nesting)
        + len(state.group_role_assignments)
        + sum(
            selector_count(item.selector, populations[item.population_key].count)
            for item in state.population_role_assignments
        )
        + len(state.role_hierarchy)
        + sum(
            resource_sets[item.resource_set_key].instance_count
            for item in state.role_grants
        )
        + len(state.direct_entitlements)
    )
    budget = config.budget
    if relation_count > budget.max_directory_rbac_relations:
        raise EnterpriseCompileError(
            "directory_rbac_relation_budget_exceeded",
            "directory/RBAC state exceeds its independent relation budget",
            measured=relation_count,
            allowed=budget.max_directory_rbac_relations,
        )


def _reject_duplicate_semantic_edges(
    memberships: list[DirectoryMembershipEdgeV1],
    subject_roles: list[DirectorySubjectRoleAssignmentV1],
) -> None:
    for code, identifiers in (
        ("duplicate_compiled_membership", [item.edge_id for item in memberships]),
        (
            "duplicate_compiled_subject_role_assignment",
            [item.edge_id for item in subject_roles],
        ),
    ):
        if len(identifiers) != len(set(identifiers)):
            raise EnterpriseCompileError(
                code,
                "overlapping selection rules compile to the same semantic edge",
            )


def _check_kernel_outer_safety(
    kernel: EnterpriseDirectoryRbacKernelV1,
    config: EnterpriseIdentityAccessCompileConfigV1,
) -> None:
    collections = (
        kernel.account_observations,
        kernel.memberships,
        kernel.group_nesting,
        kernel.group_role_assignments,
        kernel.subject_role_assignments,
        kernel.role_hierarchy,
        kernel.role_grants,
        kernel.direct_entitlements,
    )
    records = 1 + sum(len(items) for items in collections)
    if records > config.outer_safety.max_serialized_records:
        raise EnterpriseCompileError(
            "directory_rbac_outer_record_limit_exceeded",
            "compiled directory/RBAC kernel exceeds the outer record cap",
            measured=records,
            allowed=config.outer_safety.max_serialized_records,
        )
    canonical_size = len(canonical_json_bytes(kernel))
    if canonical_size > config.outer_safety.max_canonical_bytes:
        raise EnterpriseCompileError(
            "directory_rbac_outer_byte_limit_exceeded",
            "compiled directory/RBAC kernel exceeds the outer byte cap",
            measured=canonical_size,
            allowed=config.outer_safety.max_canonical_bytes,
        )


def _record_id(universe_digest: str, kind: str, *parts: str) -> str:
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


__all__ = ["compile_enterprise_directory_rbac_kernel"]
