"""Strict contracts for enterprise identity and access universe compilation.

The input records in this module describe operator-owned structure.  They are
deliberately marker-neutral: importing a real organisation does not make that
input synthetic.  Generated universe and evaluator records inherit
``SyntheticModel`` and are always safely fictional.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from synthworld.models import SyntheticModel

ENTERPRISE_IMPORT_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_BLUEPRINT_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_UNIVERSE_EXTENSION_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_DIRECTORY_RBAC_STATE_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_UNIVERSE_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_CANONICAL_BINDING_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_COMPILER_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_SELECTOR_ALGORITHM_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_SERIALIZATION_VERSION: Literal["canonical-json-v1"] = "canonical-json-v1"

_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


class EnterpriseOperatorModel(BaseModel):
    """Immutable strict base for operator-owned input and local reports."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _normalise_logical_key(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("logical_key_type")
    normalised = unicodedata.normalize("NFC", value)
    if not normalised or normalised != normalised.strip():
        raise ValueError("logical_key_nonempty_unpadded")
    if len(normalised.encode("utf-8")) > 256:
        raise ValueError("logical_key_too_long")
    if _EMAIL.fullmatch(normalised):
        raise ValueError("person_level_email_forbidden")
    return normalised


LogicalKey = Annotated[str, BeforeValidator(_normalise_logical_key)]


def _canonical_records[RecordT](
    value: tuple[RecordT, ...],
    *,
    key: Callable[[RecordT], tuple[str, ...]],
    description: str,
) -> tuple[RecordT, ...]:
    ordered = tuple(sorted(value, key=key))
    keys = tuple(key(item) for item in ordered)
    if len(keys) != len(set(keys)):
        raise ValueError(f"duplicate_{description}")
    return ordered


def _canonical_strings(value: tuple[str, ...], description: str) -> tuple[str, ...]:
    ordered = tuple(sorted(value))
    if len(ordered) != len(set(ordered)):
        raise ValueError(f"duplicate_{description}")
    return ordered


class UnitKind(StrEnum):
    DIVISION = "division"
    DEPARTMENT = "department"
    TEAM = "team"


class PrincipalKind(StrEnum):
    EMPLOYEE = "employee"
    CONTRACTOR = "contractor"
    SUPPLIER = "supplier"
    PARTNER = "partner"
    SERVICE = "service"
    WORKLOAD = "workload"
    AGENT = "agent"


class AccountKind(StrEnum):
    WORKFORCE = "workforce"
    SERVICE = "service"
    WORKLOAD = "workload"
    AGENT = "agent"


class TargetKind(StrEnum):
    APPLICATION = "application"
    API = "api"
    TOOL = "tool"
    DATA_STORE = "data_store"
    ENVIRONMENT = "environment"


class AdministrativeState(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DISABLED = "disabled"


class AccessSubjectKind(StrEnum):
    PRINCIPAL = "principal"
    ACCOUNT = "account"


class RelationshipAnchorKind(StrEnum):
    PRINCIPAL = "principal"
    ACCOUNT = "account"
    GROUP = "group"
    UNIT = "unit"
    AUTHORIZATION_TARGET = "authorization_target"


class AllSelectorV1(EnterpriseOperatorModel):
    kind: Literal["all"] = "all"


class CountSelectorV1(EnterpriseOperatorModel):
    kind: Literal["count"] = "count"
    count: int = Field(gt=0)


class FractionSelectorV1(EnterpriseOperatorModel):
    kind: Literal["fraction"] = "fraction"
    numerator: int = Field(gt=0)
    denominator: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_fraction(self) -> Self:
        if self.numerator > self.denominator:
            raise ValueError("selector_fraction_out_of_range")
        if _greatest_common_divisor(self.numerator, self.denominator) != 1:
            raise ValueError("selector_fraction_not_reduced")
        return self


SelectorV1 = Annotated[
    AllSelectorV1 | CountSelectorV1 | FractionSelectorV1,
    Field(discriminator="kind"),
]


def _greatest_common_divisor(left: int, right: int) -> int:
    while right:
        left, right = right, left % right
    return left


class TenantTemplateV1(EnterpriseOperatorModel):
    key: LogicalKey


class OrganisationTemplateV1(EnterpriseOperatorModel):
    key: LogicalKey
    tenant_key: LogicalKey


class UnitTemplateV1(EnterpriseOperatorModel):
    key: LogicalKey
    tenant_key: LogicalKey
    organisation_key: LogicalKey
    unit_kind: UnitKind
    parent_unit_key: LogicalKey | None = None


class PopulationTemplateV1(EnterpriseOperatorModel):
    key: LogicalKey
    tenant_key: LogicalKey
    organisation_key: LogicalKey
    unit_key: LogicalKey
    population_kind: PrincipalKind
    count: int = Field(gt=0)


class GroupTemplateV1(EnterpriseOperatorModel):
    key: LogicalKey
    tenant_key: LogicalKey
    organisation_key: LogicalKey
    owner_unit_key: LogicalKey | None = None


class RoleTemplateV1(EnterpriseOperatorModel):
    key: LogicalKey
    tenant_key: LogicalKey
    organisation_key: LogicalKey
    owner_unit_key: LogicalKey | None = None


class ResourceSetTemplateV1(EnterpriseOperatorModel):
    key: LogicalKey
    tenant_key: LogicalKey
    organisation_key: LogicalKey
    target_kind: TargetKind
    owner_unit_key: LogicalKey | None = None
    instance_count: int = Field(gt=0)
    actions: tuple[LogicalKey, ...] = Field(min_length=1)

    @field_validator("actions")
    @classmethod
    def canonical_actions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_strings(value, "resource_action")


class PrincipalSubjectAccessAtomRuleV1(EnterpriseOperatorModel):
    rule_key: LogicalKey
    population_key: LogicalKey
    resource_set_key: LogicalKey
    action: LogicalKey
    selector: SelectorV1


class EnterpriseIdentityAccessBlueprintV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = ENTERPRISE_BLUEPRINT_SCHEMA_VERSION
    blueprint_key: LogicalKey
    id_namespace_salt: str = Field(pattern=r"^[0-9a-f]{64}$")
    tenants: tuple[TenantTemplateV1, ...] = Field(min_length=1)
    organisations: tuple[OrganisationTemplateV1, ...] = Field(min_length=1)
    units: tuple[UnitTemplateV1, ...] = ()
    populations: tuple[PopulationTemplateV1, ...] = ()
    groups: tuple[GroupTemplateV1, ...] = ()
    roles: tuple[RoleTemplateV1, ...] = ()
    resource_sets: tuple[ResourceSetTemplateV1, ...] = ()
    principal_access_atom_rules: tuple[PrincipalSubjectAccessAtomRuleV1, ...] = ()

    @field_validator("id_namespace_salt", mode="before")
    @classmethod
    def valid_salt(cls, value: object) -> object:
        if not isinstance(value, str) or not _HEX_64.fullmatch(value):
            raise ValueError("id_namespace_salt_invalid")
        return value

    @field_validator("tenants")
    @classmethod
    def canonical_tenants(
        cls, value: tuple[TenantTemplateV1, ...]
    ) -> tuple[TenantTemplateV1, ...]:
        return _canonical_records(
            value, key=lambda item: (item.key,), description="tenant_key"
        )

    @field_validator("organisations")
    @classmethod
    def canonical_organisations(
        cls, value: tuple[OrganisationTemplateV1, ...]
    ) -> tuple[OrganisationTemplateV1, ...]:
        return _canonical_records(
            value, key=lambda item: (item.key,), description="organisation_key"
        )

    @field_validator("units")
    @classmethod
    def canonical_units(
        cls, value: tuple[UnitTemplateV1, ...]
    ) -> tuple[UnitTemplateV1, ...]:
        return _canonical_records(
            value, key=lambda item: (item.key,), description="unit_key"
        )

    @field_validator("populations")
    @classmethod
    def canonical_populations(
        cls, value: tuple[PopulationTemplateV1, ...]
    ) -> tuple[PopulationTemplateV1, ...]:
        return _canonical_records(
            value, key=lambda item: (item.key,), description="population_key"
        )

    @field_validator("groups")
    @classmethod
    def canonical_groups(
        cls, value: tuple[GroupTemplateV1, ...]
    ) -> tuple[GroupTemplateV1, ...]:
        return _canonical_records(
            value, key=lambda item: (item.key,), description="group_key"
        )

    @field_validator("roles")
    @classmethod
    def canonical_roles(
        cls, value: tuple[RoleTemplateV1, ...]
    ) -> tuple[RoleTemplateV1, ...]:
        return _canonical_records(
            value, key=lambda item: (item.key,), description="role_key"
        )

    @field_validator("resource_sets")
    @classmethod
    def canonical_resource_sets(
        cls, value: tuple[ResourceSetTemplateV1, ...]
    ) -> tuple[ResourceSetTemplateV1, ...]:
        return _canonical_records(
            value, key=lambda item: (item.key,), description="resource_set_key"
        )

    @field_validator("principal_access_atom_rules")
    @classmethod
    def canonical_atom_rules(
        cls, value: tuple[PrincipalSubjectAccessAtomRuleV1, ...]
    ) -> tuple[PrincipalSubjectAccessAtomRuleV1, ...]:
        return _canonical_records(
            value,
            key=lambda item: (item.rule_key,),
            description="principal_access_atom_rule_key",
        )


class AccountAllocationTemplateV1(EnterpriseOperatorModel):
    key: LogicalKey
    population_key: LogicalKey
    resource_set_key: LogicalKey
    account_kind: AccountKind
    selector: SelectorV1
    accounts_per_selected_subject: int = Field(gt=0)


class AccountSubjectAccessAtomRuleV1(EnterpriseOperatorModel):
    rule_key: LogicalKey
    account_allocation_key: LogicalKey
    action: LogicalKey


class EnterpriseIamUniverseExtensionV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = ENTERPRISE_UNIVERSE_EXTENSION_SCHEMA_VERSION
    account_allocations: tuple[AccountAllocationTemplateV1, ...] = ()
    account_access_atom_rules: tuple[AccountSubjectAccessAtomRuleV1, ...] = ()

    @field_validator("account_allocations")
    @classmethod
    def canonical_allocations(
        cls, value: tuple[AccountAllocationTemplateV1, ...]
    ) -> tuple[AccountAllocationTemplateV1, ...]:
        return _canonical_records(
            value,
            key=lambda item: (item.key,),
            description="account_allocation_key",
        )

    @field_validator("account_access_atom_rules")
    @classmethod
    def canonical_atom_rules(
        cls, value: tuple[AccountSubjectAccessAtomRuleV1, ...]
    ) -> tuple[AccountSubjectAccessAtomRuleV1, ...]:
        return _canonical_records(
            value,
            key=lambda item: (item.rule_key,),
            description="account_access_atom_rule_key",
        )


class PopulationGroupMembershipRuleV1(EnterpriseOperatorModel):
    rule_key: LogicalKey
    population_key: LogicalKey
    group_key: LogicalKey
    selector: SelectorV1


class GroupNestingV1(EnterpriseOperatorModel):
    child_group_key: LogicalKey
    parent_group_key: LogicalKey


class GroupRoleAssignmentV1(EnterpriseOperatorModel):
    group_key: LogicalKey
    role_key: LogicalKey


class PopulationRoleAssignmentRuleV1(EnterpriseOperatorModel):
    rule_key: LogicalKey
    population_key: LogicalKey
    role_key: LogicalKey
    selector: SelectorV1


class RoleHierarchyV1(EnterpriseOperatorModel):
    senior_role_key: LogicalKey
    junior_role_key: LogicalKey


class RoleGrantV1(EnterpriseOperatorModel):
    role_key: LogicalKey
    resource_set_key: LogicalKey
    action: LogicalKey


class AccountObservationV1(EnterpriseOperatorModel):
    account_id: str = Field(min_length=1)
    observed_principal_id: str | None = Field(default=None, min_length=1)
    administrative_state: AdministrativeState
    valid_from_tick: int = Field(ge=0)
    valid_until_tick: int | None = Field(default=None, ge=0)
    revision_id: LogicalKey

    @model_validator(mode="after")
    def validate_interval(self) -> Self:
        if (
            self.valid_until_tick is not None
            and self.valid_until_tick <= self.valid_from_tick
        ):
            raise ValueError("validity_interval_invalid")
        return self


class DirectEntitlementV1(EnterpriseOperatorModel):
    subject_id: str = Field(min_length=1)
    authorization_target_id: str = Field(min_length=1)
    action: LogicalKey
    valid_from_tick: int = Field(ge=0)
    valid_until_tick: int | None = Field(default=None, ge=0)
    revision_id: LogicalKey

    @model_validator(mode="after")
    def validate_interval(self) -> Self:
        if (
            self.valid_until_tick is not None
            and self.valid_until_tick <= self.valid_from_tick
        ):
            raise ValueError("validity_interval_invalid")
        return self


class EnterpriseDirectoryRbacStateInputV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = ENTERPRISE_DIRECTORY_RBAC_STATE_SCHEMA_VERSION
    account_observations: tuple[AccountObservationV1, ...] = ()
    memberships: tuple[PopulationGroupMembershipRuleV1, ...] = ()
    group_nesting: tuple[GroupNestingV1, ...] = ()
    group_role_assignments: tuple[GroupRoleAssignmentV1, ...] = ()
    population_role_assignments: tuple[PopulationRoleAssignmentRuleV1, ...] = ()
    role_hierarchy: tuple[RoleHierarchyV1, ...] = ()
    role_grants: tuple[RoleGrantV1, ...] = ()
    direct_entitlements: tuple[DirectEntitlementV1, ...] = ()

    @field_validator("account_observations")
    @classmethod
    def canonical_account_observations(
        cls, value: tuple[AccountObservationV1, ...]
    ) -> tuple[AccountObservationV1, ...]:
        return _canonical_records(
            value,
            key=lambda item: (item.account_id,),
            description="account_observation",
        )

    @field_validator("memberships")
    @classmethod
    def canonical_memberships(
        cls, value: tuple[PopulationGroupMembershipRuleV1, ...]
    ) -> tuple[PopulationGroupMembershipRuleV1, ...]:
        return _canonical_records(
            value,
            key=lambda item: (item.rule_key,),
            description="membership_rule_key",
        )

    @field_validator("group_nesting")
    @classmethod
    def canonical_group_nesting(
        cls, value: tuple[GroupNestingV1, ...]
    ) -> tuple[GroupNestingV1, ...]:
        return _canonical_records(
            value,
            key=lambda item: (item.child_group_key, item.parent_group_key),
            description="group_nesting_edge",
        )

    @field_validator("group_role_assignments")
    @classmethod
    def canonical_group_roles(
        cls, value: tuple[GroupRoleAssignmentV1, ...]
    ) -> tuple[GroupRoleAssignmentV1, ...]:
        return _canonical_records(
            value,
            key=lambda item: (item.group_key, item.role_key),
            description="group_role_assignment",
        )

    @field_validator("population_role_assignments")
    @classmethod
    def canonical_population_roles(
        cls, value: tuple[PopulationRoleAssignmentRuleV1, ...]
    ) -> tuple[PopulationRoleAssignmentRuleV1, ...]:
        return _canonical_records(
            value,
            key=lambda item: (item.rule_key,),
            description="population_role_assignment_rule_key",
        )

    @field_validator("role_hierarchy")
    @classmethod
    def canonical_role_hierarchy(
        cls, value: tuple[RoleHierarchyV1, ...]
    ) -> tuple[RoleHierarchyV1, ...]:
        return _canonical_records(
            value,
            key=lambda item: (item.senior_role_key, item.junior_role_key),
            description="role_hierarchy_edge",
        )

    @field_validator("role_grants")
    @classmethod
    def canonical_role_grants(
        cls, value: tuple[RoleGrantV1, ...]
    ) -> tuple[RoleGrantV1, ...]:
        return _canonical_records(
            value,
            key=lambda item: (item.role_key, item.resource_set_key, item.action),
            description="role_grant",
        )

    @field_validator("direct_entitlements")
    @classmethod
    def canonical_direct_entitlements(
        cls, value: tuple[DirectEntitlementV1, ...]
    ) -> tuple[DirectEntitlementV1, ...]:
        return _canonical_records(
            value,
            key=lambda item: (
                item.subject_id,
                item.authorization_target_id,
                item.action,
                item.revision_id,
            ),
            description="direct_entitlement",
        )


class EnterpriseIdentityAccessImportV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = ENTERPRISE_IMPORT_SCHEMA_VERSION
    blueprint: EnterpriseIdentityAccessBlueprintV1
    iam_universe_extension: EnterpriseIamUniverseExtensionV1
    directory_rbac_state: EnterpriseDirectoryRbacStateInputV1


class EnterpriseIdentityAccessImportLimitsV1(EnterpriseOperatorModel):
    max_input_bytes: int = Field(default=50 * 1024 * 1024, gt=0, le=50 * 1024 * 1024)
    max_decompressed_bytes: int = Field(
        default=100 * 1024 * 1024, gt=0, le=100 * 1024 * 1024
    )
    max_compression_ratio: int = Field(default=100, gt=0, le=100)
    max_csv_files: int = Field(default=20, gt=0, le=20)
    max_rows_per_file: int = Field(default=250_000, gt=0, le=250_000)
    max_total_rows: int = Field(default=1_000_000, gt=0, le=1_000_000)
    max_cell_bytes: int = Field(default=65_536, gt=0, le=65_536)
    max_diagnostics: int = Field(default=1_000, gt=0, le=1_000)


_COMPILE_CEILINGS = {
    "max_principals": 1_000_000,
    "max_accounts": 1_000_000,
    "max_groups": 100_000,
    "max_roles": 100_000,
    "max_authorization_targets": 250_000,
    "max_declared_actions": 1_000_000,
    "max_access_atoms": 5_000_000,
    "max_native_contexts": 100_000,
    "max_session_state_slots": 1_000_000,
    "max_evaluation_cells": 5_000_000,
    "max_role_activation_requests": 1_000_000,
    "max_access_requests": 5_000_000,
    "max_evaluator_cases": 5_000_000,
    "max_directory_rbac_relations": 500_000,
    "max_group_depth": 256,
    "max_role_depth": 256,
    "max_attribute_facts": 5_000_000,
    "max_total_abac_rules": 100_000,
    "max_total_abac_predicates": 1_000_000,
    "max_rebac_tuples": 5_000_000,
    "max_rebac_rules": 100_000,
    "max_rebac_paths_per_cell": 256,
    "max_rebac_path_expansions": 2_000_000,
    "max_sod_constraints": 100_000,
    "max_sod_role_set_width": 256,
    "max_sod_evaluations": 5_000_000,
    "max_derivations_per_cell": 256,
    "max_total_derivations": 10_000_000,
    "max_scenario_deltas": 5_000_000,
    "max_temporal_events": 5_000_000,
}


class EnterpriseIdentityAccessCompileBudgetV1(EnterpriseOperatorModel):
    max_principals: int = Field(default=100_000, gt=0)
    max_accounts: int = Field(default=100_000, gt=0)
    max_groups: int = Field(default=10_000, gt=0)
    max_roles: int = Field(default=10_000, gt=0)
    max_authorization_targets: int = Field(default=50_000, gt=0)
    max_declared_actions: int = Field(default=100_000, gt=0)
    max_access_atoms: int = Field(default=500_000, gt=0)
    max_native_contexts: int = Field(default=10_000, gt=0)
    max_session_state_slots: int = Field(default=100_000, gt=0)
    max_evaluation_cells: int = Field(default=1_000_000, gt=0)
    max_role_activation_requests: int = Field(default=100_000, gt=0)
    max_access_requests: int = Field(default=1_000_000, gt=0)
    max_evaluator_cases: int = Field(default=1_000_000, gt=0)
    max_directory_rbac_relations: int = Field(default=50_000, gt=0)
    max_group_depth: int = Field(default=64, gt=0)
    max_role_depth: int = Field(default=64, gt=0)
    max_attribute_facts: int = Field(default=1_000_000, gt=0)
    max_total_abac_rules: int = Field(default=10_000, gt=0)
    max_total_abac_predicates: int = Field(default=100_000, gt=0)
    max_rebac_tuples: int = Field(default=500_000, gt=0)
    max_rebac_rules: int = Field(default=10_000, gt=0)
    max_rebac_paths_per_cell: int = Field(default=64, gt=0)
    max_rebac_path_expansions: int = Field(default=100_000, gt=0)
    max_sod_constraints: int = Field(default=10_000, gt=0)
    max_sod_role_set_width: int = Field(default=32, gt=0)
    max_sod_evaluations: int = Field(default=1_000_000, gt=0)
    max_derivations_per_cell: int = Field(default=64, gt=0)
    max_total_derivations: int = Field(default=2_000_000, gt=0)
    max_scenario_deltas: int = Field(default=1_000_000, gt=0)
    max_temporal_events: int = Field(default=1_000_000, gt=0)

    @model_validator(mode="after")
    def enforce_hard_ceilings(self) -> Self:
        for field_name, ceiling in _COMPILE_CEILINGS.items():
            if getattr(self, field_name) > ceiling:
                raise ValueError(f"compile_budget_hard_ceiling:{field_name}")
        return self


_OUTER_CEILINGS = {
    "max_serialized_records": 25_000_000,
    "max_relations": 25_000_000,
    "max_expanded_steps": 100_000_000,
    "max_canonical_bytes": 25 * 1024 * 1024 * 1024,
    "max_work_units": 500_000_000,
}


class EnterpriseCompileOuterSafetyV1(EnterpriseOperatorModel):
    max_serialized_records: int = Field(default=10_000_000, gt=0)
    max_relations: int = Field(default=10_000_000, gt=0)
    max_expanded_steps: int = Field(default=25_000_000, gt=0)
    max_canonical_bytes: int = Field(default=10 * 1024 * 1024 * 1024, gt=0)
    max_work_units: int = Field(default=100_000_000, gt=0)

    @model_validator(mode="after")
    def enforce_hard_ceilings(self) -> Self:
        for field_name, ceiling in _OUTER_CEILINGS.items():
            if getattr(self, field_name) > ceiling:
                raise ValueError(f"outer_safety_hard_ceiling:{field_name}")
        return self


class EnterpriseIdentityAccessCompileConfigV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    budget: EnterpriseIdentityAccessCompileBudgetV1 = Field(
        default_factory=EnterpriseIdentityAccessCompileBudgetV1
    )
    outer_safety: EnterpriseCompileOuterSafetyV1 = Field(
        default_factory=EnterpriseCompileOuterSafetyV1
    )


class EnterpriseImportDiagnosticV1(EnterpriseOperatorModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    file: str | None = None
    row: int | None = Field(default=None, ge=1)
    column: str | None = None
    logical_key: str | None = None
    remediation_hint: str = Field(min_length=1)
    measured: int | None = Field(default=None, ge=0)
    allowed: int | None = Field(default=None, ge=0)


class EnterpriseIdentityAccessValidationReportV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    valid: bool
    diagnostics: tuple[EnterpriseImportDiagnosticV1, ...] = ()

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        if self.valid is bool(self.diagnostics):
            raise ValueError("validation_status_mismatch")
        return self


class SyntheticDigestV1(SyntheticModel):
    algorithm: Literal["sha256"] = "sha256"
    value: str = Field(pattern=r"^[0-9a-f]{64}$")


class EnterpriseTenantV1(SyntheticModel):
    tenant_id: str
    display_label: str


class EnterpriseOrganisationV1(SyntheticModel):
    organisation_id: str
    tenant_id: str
    display_label: str


class EnterpriseUnitV1(SyntheticModel):
    unit_id: str
    tenant_id: str
    organisation_id: str
    unit_kind: UnitKind
    parent_unit_id: str | None
    display_label: str


class EnterprisePrincipalV1(SyntheticModel):
    principal_id: str
    tenant_id: str
    organisation_id: str
    unit_id: str
    principal_kind: PrincipalKind
    display_label: str


class EnterpriseAccountV1(SyntheticModel):
    account_id: str
    tenant_id: str
    authorization_target_id: str
    account_kind: AccountKind
    display_label: str


class EnterpriseAccessSubjectV1(SyntheticModel):
    subject_id: str
    tenant_id: str
    subject_kind: AccessSubjectKind


class EnterpriseGroupV1(SyntheticModel):
    group_id: str
    tenant_id: str
    organisation_id: str
    owner_unit_id: str | None
    display_label: str


class EnterpriseRoleV1(SyntheticModel):
    role_id: str
    tenant_id: str
    organisation_id: str
    owner_unit_id: str | None
    display_label: str


class EnterpriseAuthorizationTargetV1(SyntheticModel):
    authorization_target_id: str
    tenant_id: str
    organisation_id: str
    target_kind: TargetKind
    owner_unit_id: str | None
    actions: tuple[str, ...]
    display_label: str


class EnterprisePermissionV1(SyntheticModel):
    permission_id: str
    authorization_target_id: str
    action: str


class EnterpriseRelationshipAnchorV1(SyntheticModel):
    anchor_id: str
    tenant_id: str
    entity_kind: RelationshipAnchorKind
    entity_id: str


class AccessAtomV1(SyntheticModel):
    access_atom_id: str
    subject_id: str
    authorization_target_id: str
    action: str


class EnterpriseIdentityAccessUniverseV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = ENTERPRISE_UNIVERSE_SCHEMA_VERSION
    compiler_version: Literal["1.0.0"] = ENTERPRISE_COMPILER_VERSION
    selector_algorithm_version: Literal["1.0.0"] = ENTERPRISE_SELECTOR_ALGORITHM_VERSION
    seed: int
    tenants: tuple[EnterpriseTenantV1, ...]
    organisations: tuple[EnterpriseOrganisationV1, ...]
    units: tuple[EnterpriseUnitV1, ...]
    principals: tuple[EnterprisePrincipalV1, ...]
    accounts: tuple[EnterpriseAccountV1, ...]
    access_subjects: tuple[EnterpriseAccessSubjectV1, ...]
    groups: tuple[EnterpriseGroupV1, ...]
    roles: tuple[EnterpriseRoleV1, ...]
    authorization_targets: tuple[EnterpriseAuthorizationTargetV1, ...]
    permissions: tuple[EnterprisePermissionV1, ...]
    relationship_anchors: tuple[EnterpriseRelationshipAnchorV1, ...]
    access_atoms: tuple[AccessAtomV1, ...]


class EnterpriseCanonicalAccountBindingV1(SyntheticModel):
    account_id: str
    principal_id: str


class EnterpriseCanonicalBindingTruthV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = ENTERPRISE_CANONICAL_BINDING_SCHEMA_VERSION
    identity_access_universe_digest: SyntheticDigestV1
    bindings: tuple[EnterpriseCanonicalAccountBindingV1, ...]


@dataclass(frozen=True, slots=True)
class EnterpriseIdentityAccessCompileResultV1:
    """In-memory visibility split; this object is never serialized as one file."""

    public_universe: EnterpriseIdentityAccessUniverseV1
    evaluator_canonical_binding_truth: EnterpriseCanonicalBindingTruthV1


class EnterpriseArtifactDescriptorV1(SyntheticModel):
    path: str
    schema_version: str
    digest: SyntheticDigestV1
    byte_size: int = Field(ge=0)


class EnterpriseArtifactManifestV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    visibility: Literal["public", "evaluator"]
    artifacts: tuple[EnterpriseArtifactDescriptorV1, ...]


class EnterprisePrivateCompilationReceiptV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    publication_consent: Literal[True]
    blueprint_semantic_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_artifact_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


__all__ = [name for name in globals() if name.startswith("Enterprise")]
__all__ += [
    "AccessAtomV1",
    "AccessSubjectKind",
    "AccountAllocationTemplateV1",
    "AccountKind",
    "AccountObservationV1",
    "AccountSubjectAccessAtomRuleV1",
    "AdministrativeState",
    "AllSelectorV1",
    "CountSelectorV1",
    "DirectEntitlementV1",
    "FractionSelectorV1",
    "GroupNestingV1",
    "GroupRoleAssignmentV1",
    "GroupTemplateV1",
    "LogicalKey",
    "OrganisationTemplateV1",
    "PopulationGroupMembershipRuleV1",
    "PopulationRoleAssignmentRuleV1",
    "PopulationTemplateV1",
    "PrincipalKind",
    "PrincipalSubjectAccessAtomRuleV1",
    "RelationshipAnchorKind",
    "ResourceSetTemplateV1",
    "RoleGrantV1",
    "RoleHierarchyV1",
    "RoleTemplateV1",
    "SelectorV1",
    "SyntheticDigestV1",
    "TargetKind",
    "TenantTemplateV1",
    "UnitKind",
    "UnitTemplateV1",
]
