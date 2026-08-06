"""Directory/RBAC intent, compiled state, and evaluator-truth contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self, cast

from pydantic import Field, ValidationInfo, field_validator, model_validator

from synthworld.enterprise.models import (
    AccountKind,
    AdministrativeState,
    EnterpriseOperatorModel,
    LogicalKey,
    PrincipalKind,
    SyntheticDigestV1,
)
from synthworld.enterprise.rbac.common import (
    ENTERPRISE_DIRECTORY_RBAC_COMPILER_VERSION,
    ENTERPRISE_DIRECTORY_RBAC_INTENT_SCHEMA_VERSION,
    ENTERPRISE_DIRECTORY_RBAC_KERNEL_SCHEMA_VERSION,
    ENTERPRISE_DIRECTORY_RBAC_TRUTH_SCHEMA_VERSION,
    ENTERPRISE_RBAC_SESSION_STATE_SCHEMA_VERSION,
    ActivationOutcome,
    ApprovedExceptionReason,
    AssignmentTargetKind,
    AuthorizationDecision,
    BindingStatus,
    BirthrightConditionOperator,
    DerivationMechanism,
    EmploymentType,
    LifecycleStatus,
    ReconciliationOutcome,
    canonical_operator_records,
    canonical_strings,
    canonical_synthetic_records,
)
from synthworld.models import SyntheticModel


class PrincipalKindIsV1(EnterpriseOperatorModel):
    kind: Literal["principal_kind_is"] = "principal_kind_is"
    values: tuple[PrincipalKind, ...] = Field(min_length=1)

    @field_validator("values")
    @classmethod
    def canonical_values(
        cls, value: tuple[PrincipalKind, ...]
    ) -> tuple[PrincipalKind, ...]:
        ordered = tuple(sorted(value, key=lambda item: item.value))
        if len(ordered) != len(set(ordered)):
            raise ValueError("duplicate_principal_kind")
        return ordered


class EmploymentTypeIsV1(EnterpriseOperatorModel):
    kind: Literal["employment_type_is"] = "employment_type_is"
    values: tuple[EmploymentType, ...] = Field(min_length=1)

    @field_validator("values")
    @classmethod
    def canonical_values(
        cls, value: tuple[EmploymentType, ...]
    ) -> tuple[EmploymentType, ...]:
        ordered = tuple(sorted(value, key=lambda item: item.value))
        if len(ordered) != len(set(ordered)):
            raise ValueError("duplicate_employment_type")
        return ordered


class TenantIsV1(EnterpriseOperatorModel):
    kind: Literal["tenant_is"] = "tenant_is"
    tenant_ids: tuple[str, ...] = Field(min_length=1)

    @field_validator("tenant_ids")
    @classmethod
    def canonical_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "predicate_tenant_id")


class UnitIsV1(EnterpriseOperatorModel):
    kind: Literal["unit_is"] = "unit_is"
    unit_ids: tuple[str, ...] = Field(min_length=1)

    @field_validator("unit_ids")
    @classmethod
    def canonical_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "predicate_unit_id")


class AccountKindIsV1(EnterpriseOperatorModel):
    kind: Literal["account_kind_is"] = "account_kind_is"
    values: tuple[AccountKind, ...] = Field(min_length=1)

    @field_validator("values")
    @classmethod
    def canonical_values(
        cls, value: tuple[AccountKind, ...]
    ) -> tuple[AccountKind, ...]:
        ordered = tuple(sorted(value, key=lambda item: item.value))
        if len(ordered) != len(set(ordered)):
            raise ValueError("duplicate_account_kind")
        return ordered


BirthrightPredicateV1 = Annotated[
    PrincipalKindIsV1 | EmploymentTypeIsV1 | TenantIsV1 | UnitIsV1 | AccountKindIsV1,
    Field(discriminator="kind"),
]


class BirthrightConditionV1(EnterpriseOperatorModel):
    operator: BirthrightConditionOperator
    predicates: tuple[BirthrightPredicateV1, ...] = Field(min_length=1)

    @field_validator("predicates")
    @classmethod
    def canonical_predicates(
        cls, value: tuple[BirthrightPredicateV1, ...]
    ) -> tuple[BirthrightPredicateV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple(
                (item.kind, item.model_dump_json(exclude_defaults=False))
                for item in value
            ),
            description="birthright_predicate",
        )


class BirthrightAssignmentV1(EnterpriseOperatorModel):
    assignment_id: LogicalKey
    target_kind: AssignmentTargetKind
    target_id: str = Field(min_length=1)
    access_atom_ids: tuple[str, ...] = Field(min_length=1)

    @field_validator("access_atom_ids")
    @classmethod
    def canonical_atoms(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "birthright_access_atom_id")


class BirthrightRuleV1(EnterpriseOperatorModel):
    rule_id: LogicalKey
    condition: BirthrightConditionV1
    assignments: tuple[BirthrightAssignmentV1, ...] = Field(min_length=1)

    @field_validator("assignments")
    @classmethod
    def canonical_assignments(
        cls, value: tuple[BirthrightAssignmentV1, ...]
    ) -> tuple[BirthrightAssignmentV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple((item.assignment_id,) for item in value),
            description="birthright_assignment_id",
        )


class ApprovedAccessExceptionV1(EnterpriseOperatorModel):
    exception_id: LogicalKey
    subject_id: str = Field(min_length=1)
    access_atom_ids: tuple[str, ...] = Field(min_length=1)
    owner_principal_id: str = Field(min_length=1)
    reason: ApprovedExceptionReason
    valid_from_tick: int = Field(ge=0)
    valid_until_tick: int | None = Field(default=None, ge=0)

    @field_validator("access_atom_ids")
    @classmethod
    def canonical_atoms(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "exception_access_atom_id")

    @model_validator(mode="after")
    def valid_interval(self) -> Self:
        if (
            self.valid_until_tick is not None
            and self.valid_until_tick <= self.valid_from_tick
        ):
            raise ValueError("exception_validity_interval_invalid")
        return self


class IntendedSubjectGroupMembershipV1(EnterpriseOperatorModel):
    subject_id: str = Field(min_length=1)
    group_id: str = Field(min_length=1)


class IntendedGroupNestingV1(EnterpriseOperatorModel):
    child_group_id: str = Field(min_length=1)
    parent_group_id: str = Field(min_length=1)


class IntendedGroupRoleAssignmentV1(EnterpriseOperatorModel):
    group_id: str = Field(min_length=1)
    role_id: str = Field(min_length=1)


class IntendedSubjectRoleAssignmentV1(EnterpriseOperatorModel):
    subject_id: str = Field(min_length=1)
    role_id: str = Field(min_length=1)


class IntendedRoleHierarchyV1(EnterpriseOperatorModel):
    senior_role_id: str = Field(min_length=1)
    junior_role_id: str = Field(min_length=1)


class IntendedRoleGrantV1(EnterpriseOperatorModel):
    role_id: str = Field(min_length=1)
    permission_id: str = Field(min_length=1)


class StaticSodConstraintV1(EnterpriseOperatorModel):
    constraint_id: LogicalKey
    tenant_id: str = Field(min_length=1)
    role_ids: tuple[str, ...] = Field(min_length=2)
    cardinality: int = Field(ge=2)
    subject_ids: tuple[str, ...] = ()

    @field_validator("role_ids")
    @classmethod
    def canonical_roles(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "ssd_role_id")

    @field_validator("subject_ids")
    @classmethod
    def canonical_subjects(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "ssd_subject_id")

    @model_validator(mode="after")
    def valid_cardinality(self) -> Self:
        if self.cardinality > len(self.role_ids):
            raise ValueError("ssd_cardinality_exceeds_role_set")
        return self


class DynamicSodConstraintV1(EnterpriseOperatorModel):
    constraint_id: LogicalKey
    tenant_id: str = Field(min_length=1)
    role_ids: tuple[str, ...] = Field(min_length=2)
    cardinality: int = Field(ge=2)
    subject_ids: tuple[str, ...] = ()

    @field_validator("role_ids")
    @classmethod
    def canonical_roles(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "dsd_role_id")

    @field_validator("subject_ids")
    @classmethod
    def canonical_subjects(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "dsd_subject_id")

    @model_validator(mode="after")
    def valid_cardinality(self) -> Self:
        if self.cardinality > len(self.role_ids):
            raise ValueError("dsd_cardinality_exceeds_role_set")
        return self


class EnterpriseDirectoryRbacIntentOverlayV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = ENTERPRISE_DIRECTORY_RBAC_INTENT_SCHEMA_VERSION
    identity_access_universe_digest: SyntheticDigestV1
    evaluation_corpus_digest: SyntheticDigestV1
    birthright_rules: tuple[BirthrightRuleV1, ...] = ()
    approved_exceptions: tuple[ApprovedAccessExceptionV1, ...] = ()
    intended_memberships: tuple[IntendedSubjectGroupMembershipV1, ...] = ()
    intended_group_nesting: tuple[IntendedGroupNestingV1, ...] = ()
    intended_group_role_assignments: tuple[IntendedGroupRoleAssignmentV1, ...] = ()
    intended_subject_role_assignments: tuple[IntendedSubjectRoleAssignmentV1, ...] = ()
    intended_role_hierarchy: tuple[IntendedRoleHierarchyV1, ...] = ()
    intended_role_grants: tuple[IntendedRoleGrantV1, ...] = ()
    ssd_constraints: tuple[StaticSodConstraintV1, ...] = ()
    dsd_constraints: tuple[DynamicSodConstraintV1, ...] = ()

    @field_validator("birthright_rules")
    @classmethod
    def canonical_birthright_rules(
        cls, value: tuple[BirthrightRuleV1, ...]
    ) -> tuple[BirthrightRuleV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple((item.rule_id,) for item in value),
            description="birthright_rule_id",
        )

    @field_validator("approved_exceptions")
    @classmethod
    def canonical_exceptions(
        cls, value: tuple[ApprovedAccessExceptionV1, ...]
    ) -> tuple[ApprovedAccessExceptionV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple((item.exception_id,) for item in value),
            description="approved_exception_id",
        )

    @field_validator("intended_memberships")
    @classmethod
    def canonical_memberships(
        cls, value: tuple[IntendedSubjectGroupMembershipV1, ...]
    ) -> tuple[IntendedSubjectGroupMembershipV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple((item.subject_id, item.group_id) for item in value),
            description="intended_membership",
        )

    @field_validator("intended_group_nesting")
    @classmethod
    def canonical_group_nesting(
        cls, value: tuple[IntendedGroupNestingV1, ...]
    ) -> tuple[IntendedGroupNestingV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple((item.child_group_id, item.parent_group_id) for item in value),
            description="intended_group_nesting",
        )

    @field_validator("intended_group_role_assignments")
    @classmethod
    def canonical_group_roles(
        cls, value: tuple[IntendedGroupRoleAssignmentV1, ...]
    ) -> tuple[IntendedGroupRoleAssignmentV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple((item.group_id, item.role_id) for item in value),
            description="intended_group_role_assignment",
        )

    @field_validator("intended_subject_role_assignments")
    @classmethod
    def canonical_subject_roles(
        cls, value: tuple[IntendedSubjectRoleAssignmentV1, ...]
    ) -> tuple[IntendedSubjectRoleAssignmentV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple((item.subject_id, item.role_id) for item in value),
            description="intended_subject_role_assignment",
        )

    @field_validator("intended_role_hierarchy")
    @classmethod
    def canonical_role_hierarchy(
        cls, value: tuple[IntendedRoleHierarchyV1, ...]
    ) -> tuple[IntendedRoleHierarchyV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple((item.senior_role_id, item.junior_role_id) for item in value),
            description="intended_role_hierarchy",
        )

    @field_validator("intended_role_grants")
    @classmethod
    def canonical_role_grants(
        cls, value: tuple[IntendedRoleGrantV1, ...]
    ) -> tuple[IntendedRoleGrantV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple((item.role_id, item.permission_id) for item in value),
            description="intended_role_grant",
        )

    @field_validator("ssd_constraints")
    @classmethod
    def canonical_ssd(
        cls, value: tuple[StaticSodConstraintV1, ...]
    ) -> tuple[StaticSodConstraintV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple((item.constraint_id,) for item in value),
            description="ssd_constraint_id",
        )

    @field_validator("dsd_constraints")
    @classmethod
    def canonical_dsd(
        cls, value: tuple[DynamicSodConstraintV1, ...]
    ) -> tuple[DynamicSodConstraintV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple((item.constraint_id,) for item in value),
            description="dsd_constraint_id",
        )


class ObservedRbacSessionStateV1(EnterpriseOperatorModel):
    session_state_id: str = Field(min_length=1)
    observed_outcome: ActivationOutcome
    activated_role_ids: tuple[str, ...] = ()
    observed_at_tick: int = Field(ge=0)
    valid_until_tick: int | None = Field(default=None, ge=0)
    revision_id: LogicalKey

    @field_validator("activated_role_ids")
    @classmethod
    def canonical_roles(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "activated_role_id")

    @model_validator(mode="after")
    def valid_observation(self) -> Self:
        if (
            self.observed_outcome is ActivationOutcome.REJECTED
            and self.activated_role_ids
        ):
            raise ValueError("rejected_session_has_activated_roles")
        if (
            self.valid_until_tick is not None
            and self.valid_until_tick <= self.observed_at_tick
        ):
            raise ValueError("observed_session_validity_interval_invalid")
        return self


class EnterpriseRbacSessionStateInputV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = ENTERPRISE_RBAC_SESSION_STATE_SCHEMA_VERSION
    evaluation_corpus_digest: SyntheticDigestV1
    sessions: tuple[ObservedRbacSessionStateV1, ...] = ()

    @field_validator("sessions")
    @classmethod
    def canonical_sessions(
        cls, value: tuple[ObservedRbacSessionStateV1, ...]
    ) -> tuple[ObservedRbacSessionStateV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple((item.session_state_id,) for item in value),
            description="observed_session_state_id",
        )


class DirectoryAccountObservationV1(SyntheticModel):
    account_id: str
    observed_principal_id: str | None
    administrative_state: AdministrativeState
    valid_from_tick: int = Field(ge=0)
    valid_until_tick: int | None = Field(default=None, ge=0)
    revision_id: str

    @model_validator(mode="after")
    def valid_interval(self) -> Self:
        if (
            self.valid_until_tick is not None
            and self.valid_until_tick <= self.valid_from_tick
        ):
            raise ValueError("directory_account_validity_interval_invalid")
        return self


class DirectoryMembershipEdgeV1(SyntheticModel):
    edge_id: str
    subject_id: str
    group_id: str


class DirectoryGroupNestingEdgeV1(SyntheticModel):
    edge_id: str
    child_group_id: str
    parent_group_id: str


class DirectoryGroupRoleAssignmentV1(SyntheticModel):
    edge_id: str
    group_id: str
    role_id: str


class DirectorySubjectRoleAssignmentV1(SyntheticModel):
    edge_id: str
    subject_id: str
    role_id: str


class DirectoryRoleHierarchyEdgeV1(SyntheticModel):
    edge_id: str
    senior_role_id: str
    junior_role_id: str


class DirectoryRoleGrantV1(SyntheticModel):
    edge_id: str
    role_id: str
    permission_id: str


class DirectoryDirectEntitlementV1(SyntheticModel):
    entitlement_id: str
    subject_id: str
    permission_id: str
    valid_from_tick: int = Field(ge=0)
    valid_until_tick: int | None = Field(default=None, ge=0)
    revision_id: str

    @model_validator(mode="after")
    def valid_interval(self) -> Self:
        if (
            self.valid_until_tick is not None
            and self.valid_until_tick <= self.valid_from_tick
        ):
            raise ValueError("directory_entitlement_validity_interval_invalid")
        return self


class EnterpriseDirectoryRbacKernelV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = ENTERPRISE_DIRECTORY_RBAC_KERNEL_SCHEMA_VERSION
    compiler_version: Literal["1.0.0"] = ENTERPRISE_DIRECTORY_RBAC_COMPILER_VERSION
    identity_access_universe_digest: SyntheticDigestV1
    directory_rbac_state_input_digest: SyntheticDigestV1
    compile_config_digest: SyntheticDigestV1
    account_observations: tuple[DirectoryAccountObservationV1, ...]
    memberships: tuple[DirectoryMembershipEdgeV1, ...]
    group_nesting: tuple[DirectoryGroupNestingEdgeV1, ...]
    group_role_assignments: tuple[DirectoryGroupRoleAssignmentV1, ...]
    subject_role_assignments: tuple[DirectorySubjectRoleAssignmentV1, ...]
    role_hierarchy: tuple[DirectoryRoleHierarchyEdgeV1, ...]
    role_grants: tuple[DirectoryRoleGrantV1, ...]
    direct_entitlements: tuple[DirectoryDirectEntitlementV1, ...]

    @field_validator(
        "account_observations",
        "memberships",
        "group_nesting",
        "group_role_assignments",
        "subject_role_assignments",
        "role_hierarchy",
        "role_grants",
        "direct_entitlements",
    )
    @classmethod
    def canonical_records(
        cls, value: tuple[SyntheticModel, ...]
    ) -> tuple[SyntheticModel, ...]:
        first_field = (
            next(
                name
                for name in (
                    "account_id",
                    "edge_id",
                    "entitlement_id",
                )
                if hasattr(value[0], name)
            )
            if value
            else ""
        )
        return canonical_synthetic_records(
            value,
            keys=tuple((str(getattr(item, first_field)),) for item in value),
            description=first_field or "empty_kernel_record",
        )


class MembershipPathTruthV1(SyntheticModel):
    path_id: str
    subject_id: str
    group_id: str
    group_path: tuple[str, ...] = Field(min_length=1)


class RoleAssignmentSourceKind(StrEnum):
    SUBJECT = "subject"
    GROUP = "group"


class AuthorizedRolePathTruthV1(SyntheticModel):
    path_id: str
    subject_id: str
    role_id: str
    assignment_source_kind: RoleAssignmentSourceKind
    assignment_source_id: str
    group_path: tuple[str, ...]
    role_path: tuple[str, ...] = Field(min_length=1)


class AuthorizedRoleSetTruthV1(SyntheticModel):
    subject_id: str
    role_ids: tuple[str, ...]

    @field_validator("role_ids")
    @classmethod
    def canonical_roles(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "authorized_role_id")


class AccessDerivationPathTruthV1(SyntheticModel):
    path_id: str
    cell_id: str
    mechanism: DerivationMechanism
    subject_id: str
    permission_id: str
    membership_group_path: tuple[str, ...]
    role_path: tuple[str, ...]
    source_record_id: str


class BirthrightPredicateTruthV1(SyntheticModel):
    rule_id: str
    subject_id: str
    predicate_index: int = Field(ge=0)
    result: bool


class BirthrightEligibilityTruthV1(SyntheticModel):
    rule_id: str
    subject_id: str
    eligible: bool


class BirthrightAssignmentTruthV1(SyntheticModel):
    rule_id: str
    assignment_id: str
    cell_id: str
    subject_id: str
    access_atom_id: str
    eligible: bool
    assignment_satisfied: bool


class ApprovedExceptionTruthV1(SyntheticModel):
    exception_id: str
    cell_id: str
    active: bool


class SsdConstraintTruthV1(SyntheticModel):
    constraint_id: str
    subject_id: str
    role_ids: tuple[str, ...]
    intersection_role_ids: tuple[str, ...]
    cardinality: int = Field(ge=2)
    violated: bool

    @field_validator("role_ids", "intersection_role_ids")
    @classmethod
    def canonical_roles(
        cls, value: tuple[str, ...], info: ValidationInfo
    ) -> tuple[str, ...]:
        return canonical_strings(value, cast(str, info.field_name))


class DsdConstraintTruthV1(SyntheticModel):
    constraint_id: str
    activation_request_id: str
    session_state_id: str
    requested_intersection_role_ids: tuple[str, ...]
    actual_intersection_role_ids: tuple[str, ...]
    cardinality: int = Field(ge=2)
    request_violated: bool
    observed_session_violated: bool

    @field_validator("requested_intersection_role_ids", "actual_intersection_role_ids")
    @classmethod
    def canonical_roles(
        cls, value: tuple[str, ...], info: ValidationInfo
    ) -> tuple[str, ...]:
        return canonical_strings(value, cast(str, info.field_name))


class ActivationDecisionTruthV1(SyntheticModel):
    activation_request_id: str
    session_state_id: str
    subject_id: str
    requested_role_ids: tuple[str, ...]
    authorized_role_ids: tuple[str, ...]
    expected_outcome: ActivationOutcome
    unauthorized_role_requested: bool
    dsd_cardinality_met: bool

    @field_validator("requested_role_ids", "authorized_role_ids")
    @classmethod
    def canonical_roles(
        cls, value: tuple[str, ...], info: ValidationInfo
    ) -> tuple[str, ...]:
        return canonical_strings(value, cast(str, info.field_name))


class ObservedSessionTruthV1(SyntheticModel):
    session_state_id: str
    expected_outcome: ActivationOutcome
    observed_outcome: ActivationOutcome
    actual_activated_role_ids: tuple[str, ...]
    unauthorized_activated_role_ids: tuple[str, ...]
    usable_activated_role_ids: tuple[str, ...]
    observed_outcome_correct: bool
    dsd_compliant: bool

    @field_validator(
        "actual_activated_role_ids",
        "unauthorized_activated_role_ids",
        "usable_activated_role_ids",
    )
    @classmethod
    def canonical_roles(
        cls, value: tuple[str, ...], info: ValidationInfo
    ) -> tuple[str, ...]:
        return canonical_strings(value, cast(str, info.field_name))


class DirectoryRbacCellTruthV1(SyntheticModel):
    cell_id: str
    subject_id: str
    tick: int = Field(ge=0)
    birthright_decision: AuthorizationDecision
    intended_decision: AuthorizationDecision
    effective_decision: AuthorizationDecision
    final_decision: AuthorizationDecision
    reconciliation: ReconciliationOutcome
    binding_status: BindingStatus
    lifecycle_status: LifecycleStatus
    birthright_assignment_ids: tuple[str, ...]
    approved_exception_ids: tuple[str, ...]
    intended_path_ids: tuple[str, ...]
    effective_path_ids: tuple[str, ...]

    @field_validator(
        "birthright_assignment_ids",
        "approved_exception_ids",
        "intended_path_ids",
        "effective_path_ids",
    )
    @classmethod
    def canonical_ids(
        cls, value: tuple[str, ...], info: ValidationInfo
    ) -> tuple[str, ...]:
        return canonical_strings(value, cast(str, info.field_name))


_TRUTH_KEY_FIELDS: dict[str, tuple[str, ...]] = {
    "membership_paths": ("path_id",),
    "authorized_role_paths": ("path_id",),
    "authorized_role_sets": ("subject_id",),
    "access_derivation_paths": ("path_id",),
    "intended_derivation_paths": ("path_id",),
    "birthright_predicates": ("rule_id", "subject_id", "predicate_index"),
    "birthright_eligibility": ("rule_id", "subject_id"),
    "birthright_assignments": ("rule_id", "assignment_id", "cell_id"),
    "approved_exceptions": ("exception_id", "cell_id"),
    "ssd_evaluations": ("constraint_id", "subject_id"),
    "dsd_evaluations": ("activation_request_id", "constraint_id"),
    "activation_decisions": ("activation_request_id",),
    "observed_sessions": ("session_state_id",),
    "cells": ("cell_id",),
}


class CompiledEnterpriseDirectoryRbacTruthV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = ENTERPRISE_DIRECTORY_RBAC_TRUTH_SCHEMA_VERSION
    compiler_version: Literal["1.0.0"] = ENTERPRISE_DIRECTORY_RBAC_COMPILER_VERSION
    identity_access_universe_digest: SyntheticDigestV1
    canonical_binding_truth_digest: SyntheticDigestV1
    evaluation_corpus_digest: SyntheticDigestV1
    directory_rbac_kernel_digest: SyntheticDigestV1
    directory_rbac_intent_digest: SyntheticDigestV1
    rbac_session_state_digest: SyntheticDigestV1
    membership_paths: tuple[MembershipPathTruthV1, ...]
    authorized_role_paths: tuple[AuthorizedRolePathTruthV1, ...]
    authorized_role_sets: tuple[AuthorizedRoleSetTruthV1, ...]
    access_derivation_paths: tuple[AccessDerivationPathTruthV1, ...]
    intended_derivation_paths: tuple[AccessDerivationPathTruthV1, ...]
    birthright_predicates: tuple[BirthrightPredicateTruthV1, ...]
    birthright_eligibility: tuple[BirthrightEligibilityTruthV1, ...]
    birthright_assignments: tuple[BirthrightAssignmentTruthV1, ...]
    approved_exceptions: tuple[ApprovedExceptionTruthV1, ...]
    ssd_evaluations: tuple[SsdConstraintTruthV1, ...]
    dsd_evaluations: tuple[DsdConstraintTruthV1, ...]
    activation_decisions: tuple[ActivationDecisionTruthV1, ...]
    observed_sessions: tuple[ObservedSessionTruthV1, ...]
    cells: tuple[DirectoryRbacCellTruthV1, ...]

    @field_validator(*_TRUTH_KEY_FIELDS)
    @classmethod
    def canonical_truth_records(
        cls, value: tuple[SyntheticModel, ...], info: ValidationInfo
    ) -> tuple[SyntheticModel, ...]:
        field_name = cast(str, info.field_name)
        key_fields = _TRUTH_KEY_FIELDS[field_name]
        return canonical_synthetic_records(
            value,
            keys=tuple(
                tuple(str(getattr(item, field)) for field in key_fields)
                for item in value
            ),
            description=field_name,
        )


__all__ = [name for name in globals() if name.startswith("Enterprise")]
__all__ += [
    "AccountKindIsV1",
    "ActivationDecisionTruthV1",
    "ApprovedAccessExceptionV1",
    "ApprovedExceptionTruthV1",
    "AuthorizedRolePathTruthV1",
    "AuthorizedRoleSetTruthV1",
    "BirthrightAssignmentTruthV1",
    "BirthrightAssignmentV1",
    "BirthrightConditionV1",
    "BirthrightEligibilityTruthV1",
    "BirthrightPredicateTruthV1",
    "BirthrightPredicateV1",
    "BirthrightRuleV1",
    "CompiledEnterpriseDirectoryRbacTruthV1",
    "DirectoryRbacCellTruthV1",
    "DsdConstraintTruthV1",
    "DynamicSodConstraintV1",
    "EmploymentTypeIsV1",
    "IntendedGroupNestingV1",
    "IntendedGroupRoleAssignmentV1",
    "IntendedRoleGrantV1",
    "IntendedRoleHierarchyV1",
    "IntendedSubjectGroupMembershipV1",
    "IntendedSubjectRoleAssignmentV1",
    "MembershipPathTruthV1",
    "ObservedRbacSessionStateV1",
    "ObservedSessionTruthV1",
    "PrincipalKindIsV1",
    "RoleAssignmentSourceKind",
    "SsdConstraintTruthV1",
    "StaticSodConstraintV1",
    "TenantIsV1",
    "UnitIsV1",
]
