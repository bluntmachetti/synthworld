"""Digest-bound composition and aggregate enterprise access-state contracts."""

from __future__ import annotations

from typing import Literal, Self, cast

from pydantic import Field, ValidationInfo, field_validator, model_validator

from synthworld.enterprise.authorization_common import (
    ENTERPRISE_AUTHORIZATION_COMPILER_VERSION,
    ENTERPRISE_AUTHORIZATION_COMPOSITION_SCHEMA_VERSION,
    ENTERPRISE_AUTHORIZATION_KERNEL_SCHEMA_VERSION,
    ENTERPRISE_AUTHORIZATION_PROFILE_SCHEMA_VERSION,
    ENTERPRISE_COMPILED_ACCESS_STATE_SCHEMA_VERSION,
    AuthorizationEvaluationProfileKind,
    MechanismOutcome,
)
from synthworld.enterprise.models import (
    EnterpriseOperatorModel,
    SyntheticDigestV1,
)
from synthworld.enterprise.rbac.common import (
    AuthorizationDecision,
    BindingStatus,
    LifecycleStatus,
    ReconciliationOutcome,
    canonical_operator_records,
    canonical_strings,
    canonical_synthetic_records,
)
from synthworld.models import SyntheticModel


class DirectoryRbacComponentReferenceV1(SyntheticModel):
    family: Literal["directory_rbac"] = "directory_rbac"
    component_schema_version: Literal["1.0.0"] = "1.0.0"
    component_digest: SyntheticDigestV1


class AbacComponentReferenceV1(SyntheticModel):
    family: Literal["abac"] = "abac"
    component_schema_version: Literal["1.0.0"] = "1.0.0"
    component_digest: SyntheticDigestV1


class RebacComponentReferenceV1(SyntheticModel):
    family: Literal["rebac"] = "rebac"
    component_schema_version: Literal["1.0.0"] = "1.0.0"
    component_digest: SyntheticDigestV1


class EnterpriseAuthorizationCompositionV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = (
        ENTERPRISE_AUTHORIZATION_COMPOSITION_SCHEMA_VERSION
    )
    identity_access_universe_digest: SyntheticDigestV1
    evaluation_corpus_digest: SyntheticDigestV1
    directory_rbac: DirectoryRbacComponentReferenceV1
    abac: AbacComponentReferenceV1 | None = None
    rebac: RebacComponentReferenceV1 | None = None


class AuthorizationCellProfileV1(EnterpriseOperatorModel):
    cell_id: str = Field(min_length=1)
    profile: AuthorizationEvaluationProfileKind


class AuthorizationEvaluationProfileV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = ENTERPRISE_AUTHORIZATION_PROFILE_SCHEMA_VERSION
    evaluation_corpus_digest: SyntheticDigestV1
    cells: tuple[AuthorizationCellProfileV1, ...] = Field(min_length=1)

    @field_validator("cells")
    @classmethod
    def canonical_cells(
        cls, value: tuple[AuthorizationCellProfileV1, ...]
    ) -> tuple[AuthorizationCellProfileV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple((item.cell_id,) for item in value),
            description="authorization_profile_cell_id",
        )


class AuthorizationKernelCellV1(SyntheticModel):
    cell_id: str
    profile: AuthorizationEvaluationProfileKind


class EnterpriseAuthorizationKernelV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = ENTERPRISE_AUTHORIZATION_KERNEL_SCHEMA_VERSION
    compiler_version: Literal["1.0.0"] = ENTERPRISE_AUTHORIZATION_COMPILER_VERSION
    identity_access_universe_digest: SyntheticDigestV1
    evaluation_corpus_digest: SyntheticDigestV1
    composition_digest: SyntheticDigestV1
    evaluation_profile_digest: SyntheticDigestV1
    cells: tuple[AuthorizationKernelCellV1, ...]

    @field_validator("cells")
    @classmethod
    def canonical_cells(
        cls, value: tuple[AuthorizationKernelCellV1, ...]
    ) -> tuple[AuthorizationKernelCellV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.cell_id,) for item in value),
            description="authorization_kernel_cell_id",
        )


class MechanismOutcomeSetV1(SyntheticModel):
    rbac: MechanismOutcome | None = None
    abac: MechanismOutcome | None = None
    rebac: MechanismOutcome | None = None

    @model_validator(mode="after")
    def nonempty(self) -> Self:
        if self.rbac is None and self.abac is None and self.rebac is None:
            raise ValueError("mechanism_outcome_set_empty")
        return self


class PolicyConflictTruthV1(SyntheticModel):
    conflict_id: str
    cell_id: str
    actual_conflict: bool
    intended_conflict: bool
    actual_allowing_mechanisms: tuple[str, ...]
    actual_denying_mechanisms: tuple[str, ...]
    intended_allowing_mechanisms: tuple[str, ...]
    intended_denying_mechanisms: tuple[str, ...]

    @field_validator(
        "actual_allowing_mechanisms",
        "actual_denying_mechanisms",
        "intended_allowing_mechanisms",
        "intended_denying_mechanisms",
    )
    @classmethod
    def canonical_mechanisms(
        cls, value: tuple[str, ...], info: ValidationInfo
    ) -> tuple[str, ...]:
        return canonical_strings(value, cast(str, info.field_name))

    @model_validator(mode="after")
    def flags_match_sets(self) -> Self:
        actual = bool(
            self.actual_allowing_mechanisms and self.actual_denying_mechanisms
        )
        intended = bool(
            self.intended_allowing_mechanisms and self.intended_denying_mechanisms
        )
        if actual != self.actual_conflict or intended != self.intended_conflict:
            raise ValueError("policy_conflict_flag_mismatch")
        return self


class CompiledEnterpriseAccessCellV1(SyntheticModel):
    cell_id: str
    profile: AuthorizationEvaluationProfileKind
    actual_mechanism_outcomes: MechanismOutcomeSetV1
    intended_mechanism_outcomes: MechanismOutcomeSetV1
    intended_decision: AuthorizationDecision
    effective_decision: AuthorizationDecision
    final_decision: AuthorizationDecision
    reconciliation: ReconciliationOutcome
    binding_status: BindingStatus
    lifecycle_status: LifecycleStatus
    policy_conflict_id: str
    directory_rbac_cell_id: str
    abac_cell_id: str | None
    rebac_cell_id: str | None


class CompiledEnterpriseAccessStateV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = ENTERPRISE_COMPILED_ACCESS_STATE_SCHEMA_VERSION
    compiler_version: Literal["1.0.0"] = ENTERPRISE_AUTHORIZATION_COMPILER_VERSION
    identity_access_universe_digest: SyntheticDigestV1
    canonical_binding_truth_digest: SyntheticDigestV1
    evaluation_corpus_digest: SyntheticDigestV1
    composition_digest: SyntheticDigestV1
    authorization_kernel_digest: SyntheticDigestV1
    directory_rbac_truth_digest: SyntheticDigestV1
    abac_truth_digest: SyntheticDigestV1 | None
    rebac_truth_digest: SyntheticDigestV1 | None
    policy_conflicts: tuple[PolicyConflictTruthV1, ...]
    cells: tuple[CompiledEnterpriseAccessCellV1, ...]

    @field_validator("policy_conflicts", "cells")
    @classmethod
    def canonical_truth(
        cls, value: tuple[SyntheticModel, ...], info: ValidationInfo
    ) -> tuple[SyntheticModel, ...]:
        field_name = cast(str, info.field_name)
        keys = (
            tuple((cast(PolicyConflictTruthV1, item).conflict_id,) for item in value)
            if field_name == "policy_conflicts"
            else tuple(
                (cast(CompiledEnterpriseAccessCellV1, item).cell_id,) for item in value
            )
        )
        return canonical_synthetic_records(
            value, keys=keys, description=f"aggregate_{field_name}"
        )


__all__ = [name for name in globals() if name.endswith("V1")]
