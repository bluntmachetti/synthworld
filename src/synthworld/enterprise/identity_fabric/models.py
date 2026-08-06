"""Public inputs, evaluator truth, predictions, and metrics for issue #7."""

from __future__ import annotations

from typing import Literal, Protocol, Self, cast

from pydantic import Field, ValidationInfo, field_validator, model_validator

from synthworld.enterprise.abac.metrics import (
    EnterpriseAbacMetricsV1,
    EnterpriseAbacPredictionV1,
)
from synthworld.enterprise.abac.models import (
    CompiledEnterpriseAbacTruthV1,
    EnterpriseAbacIntentOverlayV1,
    EnterpriseAbacStateOverlayV1,
)
from synthworld.enterprise.authorization.models import (
    AuthorizationEvaluationProfileV1,
    CompiledEnterpriseAccessStateV1,
    EnterpriseAuthorizationCompositionV1,
    EnterpriseAuthorizationKernelV1,
    MechanismOutcomeSetV1,
)
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.identity_fabric.common import (
    IDENTITY_FABRIC_BENCHMARK_SCHEMA_VERSION,
    IDENTITY_FABRIC_COMPILER_VERSION,
    IDENTITY_FABRIC_METRICS_SCHEMA_VERSION,
    IDENTITY_FABRIC_PREDICTION_SCHEMA_VERSION,
    IDENTITY_FABRIC_PROFILE_VERSION,
    IDENTITY_FABRIC_PUBLIC_INPUT_SCHEMA_VERSION,
    IDENTITY_FABRIC_TRUTH_SCHEMA_VERSION,
)
from synthworld.enterprise.models import (
    EnterpriseCanonicalBindingTruthV1,
    EnterpriseIdentityAccessUniverseV1,
    EnterpriseOperatorModel,
    LogicalKey,
    SyntheticDigestV1,
)
from synthworld.enterprise.rbac.common import (
    AuthorizationDecision,
    BindingStatus,
    LifecycleStatus,
    canonical_operator_records,
    canonical_strings,
    canonical_synthetic_records,
)
from synthworld.enterprise.rbac.corpus_models import EnterpriseEvaluationCorpusV1
from synthworld.enterprise.rbac.metrics import (
    EnterpriseAuthorizationMetricV1,
    EnterpriseDirectoryRbacMetricsV1,
    EnterpriseDirectoryRbacPredictionV1,
)
from synthworld.enterprise.rbac.models import (
    CompiledEnterpriseDirectoryRbacTruthV1,
    EnterpriseDirectoryRbacIntentOverlayV1,
    EnterpriseDirectoryRbacKernelV1,
    EnterpriseRbacSessionStateInputV1,
)
from synthworld.enterprise.rebac.metrics import (
    EnterpriseRebacMetricsV1,
    EnterpriseRebacPredictionV1,
)
from synthworld.enterprise.rebac.models import (
    CompiledEnterpriseRebacTruthV1,
    EnterpriseRebacIntentOverlayV1,
    EnterpriseRebacStateOverlayV1,
)
from synthworld.models import SyntheticModel


class _QueryIdRecord(Protocol):
    query_id: str


class EnterpriseIdentityFabricProjectionLimitsV1(EnterpriseOperatorModel):
    max_checkpoints: int = Field(default=16, gt=0, le=64)
    max_membership_queries: int = Field(default=1_000_000, gt=0, le=5_000_000)
    max_role_queries: int = Field(default=1_000_000, gt=0, le=5_000_000)
    max_account_queries: int = Field(default=1_000_000, gt=0, le=5_000_000)
    max_access_queries: int = Field(default=5_000_000, gt=0, le=10_000_000)
    max_accumulation_queries: int = Field(default=1_000_000, gt=0, le=5_000_000)
    max_total_queries: int = Field(default=10_000_000, gt=0, le=25_000_000)


class IdentityFabricInvariantPublicInputV1(EnterpriseOperatorModel):
    profile_version: Literal["identity-fabric-smoke-1.0.0"] = (
        IDENTITY_FABRIC_PROFILE_VERSION
    )
    universe: EnterpriseIdentityAccessUniverseV1
    corpus: EnterpriseEvaluationCorpusV1
    directory_rbac_intent: EnterpriseDirectoryRbacIntentOverlayV1
    rbac_session_state: EnterpriseRbacSessionStateInputV1
    abac_intent: EnterpriseAbacIntentOverlayV1
    rebac_intent: EnterpriseRebacIntentOverlayV1
    evaluation_profile: AuthorizationEvaluationProfileV1


class IdentityFabricCheckpointPublicInputV1(EnterpriseOperatorModel):
    checkpoint_id: LogicalKey
    sequence: int = Field(ge=0)
    directory_rbac_kernel: EnterpriseDirectoryRbacKernelV1
    abac_state: EnterpriseAbacStateOverlayV1
    rebac_state: EnterpriseRebacStateOverlayV1
    composition: EnterpriseAuthorizationCompositionV1
    authorization_kernel: EnterpriseAuthorizationKernelV1


class IdentityFabricCheckpointReferenceV1(SyntheticModel):
    checkpoint_id: str
    sequence: int = Field(ge=0)
    checkpoint_input_digest: SyntheticDigestV1


class IdentityFabricMembershipQueryV1(SyntheticModel):
    query_id: str
    checkpoint_id: str
    subject_id: str
    group_id: str


class IdentityFabricRoleQueryV1(SyntheticModel):
    query_id: str
    checkpoint_id: str
    subject_id: str
    role_id: str


class IdentityFabricAccountQueryV1(SyntheticModel):
    query_id: str
    checkpoint_id: str
    account_id: str
    tick: int = Field(ge=0)


class IdentityFabricAccessQueryV1(SyntheticModel):
    query_id: str
    checkpoint_id: str
    cell_id: str


class IdentityFabricAccumulationQueryV1(SyntheticModel):
    query_id: str
    subject_id: str
    from_checkpoint_id: str
    to_checkpoint_id: str


class EnterpriseIdentityFabricBenchmarkV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = IDENTITY_FABRIC_BENCHMARK_SCHEMA_VERSION
    compiler_version: Literal["1.0.0"] = IDENTITY_FABRIC_COMPILER_VERSION
    profile_version: Literal["identity-fabric-smoke-1.0.0"] = (
        IDENTITY_FABRIC_PROFILE_VERSION
    )
    identity_access_universe_digest: SyntheticDigestV1
    evaluation_corpus_digest: SyntheticDigestV1
    invariant_input_digest: SyntheticDigestV1
    checkpoints: tuple[IdentityFabricCheckpointReferenceV1, ...] = Field(min_length=2)
    membership_queries: tuple[IdentityFabricMembershipQueryV1, ...]
    role_queries: tuple[IdentityFabricRoleQueryV1, ...]
    account_queries: tuple[IdentityFabricAccountQueryV1, ...]
    access_queries: tuple[IdentityFabricAccessQueryV1, ...]
    accumulation_queries: tuple[IdentityFabricAccumulationQueryV1, ...]

    @field_validator("checkpoints")
    @classmethod
    def canonical_checkpoints(
        cls, value: tuple[IdentityFabricCheckpointReferenceV1, ...]
    ) -> tuple[IdentityFabricCheckpointReferenceV1, ...]:
        ordered = tuple(sorted(value, key=lambda item: item.sequence))
        if tuple(item.sequence for item in ordered) != tuple(range(len(ordered))):
            raise ValueError("identity_fabric_checkpoint_sequence_not_contiguous")
        if len({item.checkpoint_id for item in ordered}) != len(ordered):
            raise ValueError("duplicate_identity_fabric_checkpoint_id")
        return ordered

    @field_validator(
        "membership_queries",
        "role_queries",
        "account_queries",
        "access_queries",
        "accumulation_queries",
    )
    @classmethod
    def canonical_queries(
        cls, value: tuple[SyntheticModel, ...], info: ValidationInfo
    ) -> tuple[SyntheticModel, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((cast(_QueryIdRecord, item).query_id,) for item in value),
            description=f"identity_fabric_{info.field_name}_query_id",
        )


class EnterpriseIdentityFabricPublicInputV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = IDENTITY_FABRIC_PUBLIC_INPUT_SCHEMA_VERSION
    invariant: IdentityFabricInvariantPublicInputV1
    checkpoints: tuple[IdentityFabricCheckpointPublicInputV1, ...] = Field(min_length=2)
    benchmark: EnterpriseIdentityFabricBenchmarkV1

    @field_validator("checkpoints")
    @classmethod
    def ordered_checkpoints(
        cls, value: tuple[IdentityFabricCheckpointPublicInputV1, ...]
    ) -> tuple[IdentityFabricCheckpointPublicInputV1, ...]:
        ordered = tuple(sorted(value, key=lambda item: item.sequence))
        if tuple(item.sequence for item in ordered) != tuple(range(len(ordered))):
            raise ValueError(
                "identity_fabric_public_checkpoint_sequence_not_contiguous"
            )
        if len({item.checkpoint_id for item in ordered}) != len(ordered):
            raise ValueError("duplicate_identity_fabric_public_checkpoint_id")
        return ordered

    @model_validator(mode="after")
    def benchmark_binds_inputs(self) -> Self:
        if self.benchmark.invariant_input_digest != synthetic_digest(
            canonical_json_bytes(self.invariant)
        ):
            raise ValueError("identity_fabric_invariant_input_digest_mismatch")
        expected = tuple(
            (
                item.checkpoint_id,
                item.sequence,
                synthetic_digest(canonical_json_bytes(item)),
            )
            for item in self.checkpoints
        )
        actual = tuple(
            (item.checkpoint_id, item.sequence, item.checkpoint_input_digest)
            for item in self.benchmark.checkpoints
        )
        if actual != expected:
            raise ValueError("identity_fabric_checkpoint_input_digest_mismatch")
        return self


class IdentityFabricMembershipTruthV1(SyntheticModel):
    query_id: str
    direct_member: bool
    effective_member: bool
    membership_path_ids: tuple[str, ...]

    @field_validator("membership_path_ids")
    @classmethod
    def canonical_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "identity_fabric_membership_path_id")


class IdentityFabricRoleTruthV1(SyntheticModel):
    query_id: str
    direct_role_assignment: bool
    group_derived_role: bool
    hierarchy_inherited_role: bool
    effective_role: bool
    authorized_role_path_ids: tuple[str, ...]

    @field_validator("authorized_role_path_ids")
    @classmethod
    def canonical_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "identity_fabric_authorized_role_path_id")


class IdentityFabricAccountTruthV1(SyntheticModel):
    query_id: str
    canonical_principal_id: str
    observed_principal_id: str | None
    binding_status: BindingStatus
    lifecycle_status: LifecycleStatus
    orphaned: bool
    inactive: bool


class IdentityFabricAccessTruthV1(SyntheticModel):
    query_id: str
    direct_entitlement: bool
    role_entitlement: bool
    birthright_access: bool
    approved_exception: bool
    intended_decision: AuthorizationDecision
    effective_decision: AuthorizationDecision
    final_decision: AuthorizationDecision
    mechanism_outcomes: MechanismOutcomeSetV1
    policy_conflict: bool
    redundant_derivation: bool
    outside_birthright: bool
    outside_intent: bool


class IdentityFabricCheckpointTruthV1(SyntheticModel):
    checkpoint_id: str
    sequence: int = Field(ge=0)
    membership: tuple[IdentityFabricMembershipTruthV1, ...]
    roles: tuple[IdentityFabricRoleTruthV1, ...]
    accounts: tuple[IdentityFabricAccountTruthV1, ...]
    access: tuple[IdentityFabricAccessTruthV1, ...]

    @field_validator("membership", "roles", "accounts", "access")
    @classmethod
    def canonical_truth(
        cls, value: tuple[SyntheticModel, ...], info: ValidationInfo
    ) -> tuple[SyntheticModel, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((cast(_QueryIdRecord, item).query_id,) for item in value),
            description=f"identity_fabric_{info.field_name}_truth_id",
        )


class IdentityFabricAccumulationTruthV1(SyntheticModel):
    query_id: str
    accumulated_cell_ids: tuple[str, ...]

    @field_validator("accumulated_cell_ids")
    @classmethod
    def canonical_cells(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "identity_fabric_accumulated_cell_id")


class IdentityFabricCaseLabelV1(SyntheticModel):
    query_id: str
    labels: tuple[str, ...] = Field(min_length=1)

    @field_validator("labels")
    @classmethod
    def canonical_labels(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "identity_fabric_case_label")


class EnterpriseIdentityFabricTruthV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = IDENTITY_FABRIC_TRUTH_SCHEMA_VERSION
    compiler_version: Literal["1.0.0"] = IDENTITY_FABRIC_COMPILER_VERSION
    public_input_digest: SyntheticDigestV1
    benchmark_digest: SyntheticDigestV1
    canonical_binding_truth_digest: SyntheticDigestV1
    checkpoints: tuple[IdentityFabricCheckpointTruthV1, ...]
    accumulation: tuple[IdentityFabricAccumulationTruthV1, ...]
    case_labels: tuple[IdentityFabricCaseLabelV1, ...]

    @field_validator("checkpoints")
    @classmethod
    def canonical_checkpoint_truth(
        cls, value: tuple[IdentityFabricCheckpointTruthV1, ...]
    ) -> tuple[IdentityFabricCheckpointTruthV1, ...]:
        ordered = tuple(sorted(value, key=lambda item: item.sequence))
        if tuple(item.sequence for item in ordered) != tuple(range(len(ordered))):
            raise ValueError("identity_fabric_truth_sequence_not_contiguous")
        if len({item.checkpoint_id for item in ordered}) != len(ordered):
            raise ValueError("duplicate_identity_fabric_truth_checkpoint_id")
        return ordered

    @field_validator("accumulation", "case_labels")
    @classmethod
    def canonical_cross_truth(
        cls, value: tuple[SyntheticModel, ...], info: ValidationInfo
    ) -> tuple[SyntheticModel, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((cast(_QueryIdRecord, item).query_id,) for item in value),
            description=f"identity_fabric_{info.field_name}_id",
        )


class IdentityFabricCheckpointEvaluatorArtifactV1(SyntheticModel):
    checkpoint_id: str
    sequence: int = Field(ge=0)
    directory_rbac_truth: CompiledEnterpriseDirectoryRbacTruthV1
    abac_truth: CompiledEnterpriseAbacTruthV1
    rebac_truth: CompiledEnterpriseRebacTruthV1
    access_state: CompiledEnterpriseAccessStateV1


class EnterpriseIdentityFabricEvaluatorArtifactsV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = IDENTITY_FABRIC_TRUTH_SCHEMA_VERSION
    public_input_digest: SyntheticDigestV1
    canonical_binding_truth: EnterpriseCanonicalBindingTruthV1
    checkpoints: tuple[IdentityFabricCheckpointEvaluatorArtifactV1, ...]
    truth: EnterpriseIdentityFabricTruthV1

    @field_validator("checkpoints")
    @classmethod
    def canonical_evaluator_checkpoints(
        cls, value: tuple[IdentityFabricCheckpointEvaluatorArtifactV1, ...]
    ) -> tuple[IdentityFabricCheckpointEvaluatorArtifactV1, ...]:
        ordered = tuple(sorted(value, key=lambda item: item.sequence))
        if tuple(item.sequence for item in ordered) != tuple(range(len(ordered))):
            raise ValueError("identity_fabric_evaluator_sequence_not_contiguous")
        if len({item.checkpoint_id for item in ordered}) != len(ordered):
            raise ValueError("duplicate_identity_fabric_evaluator_checkpoint_id")
        return ordered

    @model_validator(mode="after")
    def truth_binds_artifacts(self) -> Self:
        if self.truth.public_input_digest != self.public_input_digest:
            raise ValueError("identity_fabric_truth_public_input_digest_mismatch")
        if self.truth.canonical_binding_truth_digest != synthetic_digest(
            canonical_json_bytes(self.canonical_binding_truth)
        ):
            raise ValueError("identity_fabric_truth_binding_digest_mismatch")
        if tuple(item.checkpoint_id for item in self.checkpoints) != tuple(
            item.checkpoint_id for item in self.truth.checkpoints
        ):
            raise ValueError("identity_fabric_truth_checkpoint_inventory_mismatch")
        return self


class IdentityFabricMembershipPredictionV1(EnterpriseOperatorModel):
    query_id: str = Field(min_length=1)
    direct_member: bool
    effective_member: bool


class IdentityFabricRolePredictionV1(EnterpriseOperatorModel):
    query_id: str = Field(min_length=1)
    direct_role_assignment: bool
    group_derived_role: bool
    hierarchy_inherited_role: bool
    effective_role: bool


class IdentityFabricAccountPredictionV1(EnterpriseOperatorModel):
    query_id: str = Field(min_length=1)
    canonical_principal_id: str | None = Field(default=None, min_length=1)
    binding_status: BindingStatus
    lifecycle_status: LifecycleStatus
    orphaned: bool
    inactive: bool


class IdentityFabricAccessPredictionV1(EnterpriseOperatorModel):
    query_id: str = Field(min_length=1)
    direct_entitlement: bool
    role_entitlement: bool
    birthright_access: bool
    approved_exception: bool
    intended_decision: AuthorizationDecision
    effective_decision: AuthorizationDecision
    final_decision: AuthorizationDecision
    policy_conflict: bool
    redundant_derivation: bool
    outside_birthright: bool
    outside_intent: bool


class IdentityFabricCheckpointPredictionV1(EnterpriseOperatorModel):
    checkpoint_id: str = Field(min_length=1)
    directory_rbac: EnterpriseDirectoryRbacPredictionV1 = Field(
        default_factory=EnterpriseDirectoryRbacPredictionV1
    )
    abac: EnterpriseAbacPredictionV1 = Field(default_factory=EnterpriseAbacPredictionV1)
    rebac: EnterpriseRebacPredictionV1 = Field(
        default_factory=EnterpriseRebacPredictionV1
    )
    membership: tuple[IdentityFabricMembershipPredictionV1, ...] = ()
    roles: tuple[IdentityFabricRolePredictionV1, ...] = ()
    accounts: tuple[IdentityFabricAccountPredictionV1, ...] = ()
    access: tuple[IdentityFabricAccessPredictionV1, ...] = ()

    @field_validator("membership", "roles", "accounts", "access")
    @classmethod
    def canonical_predictions(
        cls, value: tuple[EnterpriseOperatorModel, ...], info: ValidationInfo
    ) -> tuple[EnterpriseOperatorModel, ...]:
        return canonical_operator_records(
            value,
            keys=tuple((cast(_QueryIdRecord, item).query_id,) for item in value),
            description=f"identity_fabric_{info.field_name}_prediction_id",
        )


class IdentityFabricAccumulationPredictionV1(EnterpriseOperatorModel):
    query_id: str = Field(min_length=1)
    accumulated_cell_ids: tuple[str, ...] = ()

    @field_validator("accumulated_cell_ids")
    @classmethod
    def canonical_cells(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "predicted_identity_fabric_accumulated_cell_id")


class EnterpriseIdentityFabricPredictionV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = IDENTITY_FABRIC_PREDICTION_SCHEMA_VERSION
    benchmark_digest: SyntheticDigestV1
    checkpoints: tuple[IdentityFabricCheckpointPredictionV1, ...] = ()
    accumulation: tuple[IdentityFabricAccumulationPredictionV1, ...] = ()

    @field_validator("checkpoints")
    @classmethod
    def canonical_checkpoint_predictions(
        cls, value: tuple[IdentityFabricCheckpointPredictionV1, ...]
    ) -> tuple[IdentityFabricCheckpointPredictionV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple((item.checkpoint_id,) for item in value),
            description="identity_fabric_checkpoint_prediction_id",
        )

    @field_validator("accumulation")
    @classmethod
    def canonical_accumulation_predictions(
        cls, value: tuple[IdentityFabricAccumulationPredictionV1, ...]
    ) -> tuple[IdentityFabricAccumulationPredictionV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple((item.query_id,) for item in value),
            description="identity_fabric_accumulation_prediction_id",
        )


class IdentityFabricCheckpointMetricsV1(SyntheticModel):
    checkpoint_id: str
    directory_rbac: EnterpriseDirectoryRbacMetricsV1
    abac: EnterpriseAbacMetricsV1
    rebac: EnterpriseRebacMetricsV1
    identity_fabric_metrics: tuple[EnterpriseAuthorizationMetricV1, ...]

    @field_validator("identity_fabric_metrics")
    @classmethod
    def canonical_metrics(
        cls, value: tuple[EnterpriseAuthorizationMetricV1, ...]
    ) -> tuple[EnterpriseAuthorizationMetricV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.family, item.name) for item in value),
            description="identity_fabric_checkpoint_metric_name",
        )


class EnterpriseIdentityFabricMetricsV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = IDENTITY_FABRIC_METRICS_SCHEMA_VERSION
    benchmark_digest: SyntheticDigestV1
    truth_digest: SyntheticDigestV1
    checkpoints: tuple[IdentityFabricCheckpointMetricsV1, ...]
    cross_checkpoint_metrics: tuple[EnterpriseAuthorizationMetricV1, ...]

    @field_validator("checkpoints")
    @classmethod
    def canonical_checkpoint_metrics(
        cls, value: tuple[IdentityFabricCheckpointMetricsV1, ...]
    ) -> tuple[IdentityFabricCheckpointMetricsV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.checkpoint_id,) for item in value),
            description="identity_fabric_checkpoint_metric_id",
        )

    @field_validator("cross_checkpoint_metrics")
    @classmethod
    def canonical_cross_metrics(
        cls, value: tuple[EnterpriseAuthorizationMetricV1, ...]
    ) -> tuple[EnterpriseAuthorizationMetricV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.family, item.name) for item in value),
            description="identity_fabric_cross_metric_name",
        )


__all__ = [name for name in globals() if name.endswith("V1")]
