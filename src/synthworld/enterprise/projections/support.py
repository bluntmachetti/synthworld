"""Versioned feature-support matrices shared by pure standards projections."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.models import (
    EnterpriseOperatorModel,
    LogicalKey,
    SyntheticDigestV1,
)
from synthworld.enterprise.rbac.common import (
    MetricEmptyBehaviour,
    canonical_operator_records,
    canonical_strings,
    canonical_synthetic_records,
)
from synthworld.enterprise.rbac.metrics import EnterpriseAuthorizationMetricV1
from synthworld.models import SyntheticModel

PROJECTION_MAPPING_PROFILE_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
PROJECTION_SUPPORT_MATRIX_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
PROJECTION_FIDELITY_METRICS_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"


class ProjectionTarget(StrEnum):
    SCIM = "scim"
    AUTHZEN = "authzen"
    OPENFGA = "openfga"
    SHARED_SIGNALS = "shared_signals"


class ProjectionSupportClassification(StrEnum):
    EXACT = "exact"
    APPROXIMATED = "approximated"
    UNSUPPORTED = "unsupported"


class ProjectionMappingDefinitionV1(EnterpriseOperatorModel):
    mapping_id: LogicalKey
    native_source_feature: str = Field(min_length=1)
    target_construct: str = Field(min_length=1)
    classification: ProjectionSupportClassification
    semantic_delta: str | None = None
    conformance_vector_ids: tuple[LogicalKey, ...] = Field(min_length=1)

    @field_validator("conformance_vector_ids")
    @classmethod
    def canonical_vectors(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "projection_conformance_vector_id")

    @model_validator(mode="after")
    def semantic_delta_matches_support(self) -> Self:
        if self.classification is ProjectionSupportClassification.EXACT:
            if self.semantic_delta is not None:
                raise ValueError("exact_projection_has_semantic_delta")
        elif self.semantic_delta is None or not self.semantic_delta.strip():
            raise ValueError("nonexact_projection_requires_semantic_delta")
        return self


class ProjectionMappingProfileV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = PROJECTION_MAPPING_PROFILE_SCHEMA_VERSION
    profile_id: LogicalKey
    target: ProjectionTarget
    native_profile_version: str = Field(min_length=1)
    target_profile_version: str = Field(min_length=1)
    definitions: tuple[ProjectionMappingDefinitionV1, ...] = Field(min_length=1)

    @field_validator("definitions")
    @classmethod
    def canonical_definitions(
        cls, value: tuple[ProjectionMappingDefinitionV1, ...]
    ) -> tuple[ProjectionMappingDefinitionV1, ...]:
        ordered = canonical_operator_records(
            value,
            keys=tuple((item.native_source_feature,) for item in value),
            description="projection_native_source_feature",
        )
        mapping_ids = tuple(item.mapping_id for item in ordered)
        if len(mapping_ids) != len(set(mapping_ids)):
            raise ValueError("duplicate_projection_mapping_id")
        return ordered


class ProjectionSupportRowV1(SyntheticModel):
    mapping_id: str
    native_source_feature: str
    target_construct: str
    classification: ProjectionSupportClassification
    semantic_delta: str | None
    native_profile_version: str
    target_profile_version: str
    mapping_digest: SyntheticDigestV1
    conformance_vector_ids: tuple[str, ...]

    @field_validator("conformance_vector_ids")
    @classmethod
    def canonical_vectors(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "support_conformance_vector_id")

    @model_validator(mode="after")
    def semantic_delta_matches_support(self) -> Self:
        if self.classification is ProjectionSupportClassification.EXACT:
            if self.semantic_delta is not None:
                raise ValueError("exact_support_row_has_semantic_delta")
        elif self.semantic_delta is None or not self.semantic_delta.strip():
            raise ValueError("nonexact_support_row_requires_semantic_delta")
        return self


class ProjectionSupportMatrixV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = PROJECTION_SUPPORT_MATRIX_SCHEMA_VERSION
    profile_id: str
    target: ProjectionTarget
    native_profile_version: str
    target_profile_version: str
    mapping_digest: SyntheticDigestV1
    exercised_native_features: tuple[str, ...] = Field(min_length=1)
    rows: tuple[ProjectionSupportRowV1, ...] = Field(min_length=1)

    @field_validator("exercised_native_features")
    @classmethod
    def canonical_features(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "exercised_native_feature")

    @field_validator("rows")
    @classmethod
    def canonical_rows(
        cls, value: tuple[ProjectionSupportRowV1, ...]
    ) -> tuple[ProjectionSupportRowV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.native_source_feature,) for item in value),
            description="projection_support_feature",
        )

    @model_validator(mode="after")
    def complete_and_digest_bound(self) -> Self:
        row_features = tuple(item.native_source_feature for item in self.rows)
        if row_features != self.exercised_native_features:
            raise ValueError("projection_support_inventory_mismatch")
        if any(item.mapping_digest != self.mapping_digest for item in self.rows):
            raise ValueError("projection_support_mapping_digest_mismatch")
        if any(
            item.native_profile_version != self.native_profile_version
            or item.target_profile_version != self.target_profile_version
            for item in self.rows
        ):
            raise ValueError("projection_support_profile_version_mismatch")
        return self


class ProjectionFidelityMetricsV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = PROJECTION_FIDELITY_METRICS_SCHEMA_VERSION
    support_matrix_digest: SyntheticDigestV1
    metrics: tuple[EnterpriseAuthorizationMetricV1, ...]

    @field_validator("metrics")
    @classmethod
    def canonical_metrics(
        cls, value: tuple[EnterpriseAuthorizationMetricV1, ...]
    ) -> tuple[EnterpriseAuthorizationMetricV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.family, item.name) for item in value),
            description="projection_fidelity_metric_name",
        )


def compile_projection_support_matrix(
    *, profile: ProjectionMappingProfileV1, exercised_native_features: tuple[str, ...]
) -> ProjectionSupportMatrixV1:
    """Require exactly one explicit support row for every exercised feature."""

    features = canonical_strings(
        exercised_native_features, "requested_projection_native_feature"
    )
    definitions = {item.native_source_feature: item for item in profile.definitions}
    if set(features) != set(definitions):
        missing = sorted(set(features) - set(definitions))
        extra = sorted(set(definitions) - set(features))
        raise ValueError(
            "projection_support_preflight_mismatch:"
            f"missing={','.join(missing)};extra={','.join(extra)}"
        )
    mapping_digest = synthetic_digest(canonical_json_bytes(profile))
    return ProjectionSupportMatrixV1(
        profile_id=profile.profile_id,
        target=profile.target,
        native_profile_version=profile.native_profile_version,
        target_profile_version=profile.target_profile_version,
        mapping_digest=mapping_digest,
        exercised_native_features=features,
        rows=tuple(
            ProjectionSupportRowV1(
                mapping_id=item.mapping_id,
                native_source_feature=item.native_source_feature,
                target_construct=item.target_construct,
                classification=item.classification,
                semantic_delta=item.semantic_delta,
                native_profile_version=profile.native_profile_version,
                target_profile_version=profile.target_profile_version,
                mapping_digest=mapping_digest,
                conformance_vector_ids=item.conformance_vector_ids,
            )
            for item in profile.definitions
        ),
    )


def evaluate_projection_fidelity(
    matrix: ProjectionSupportMatrixV1,
) -> ProjectionFidelityMetricsV1:
    """Expose each support class independently; emit no combined fidelity score."""

    denominator = len(matrix.rows)
    metrics = tuple(
        EnterpriseAuthorizationMetricV1(
            family=f"projection:{matrix.target.value}",
            name=f"{classification.value}_feature_rate",
            numerator=sum(
                item.classification is classification for item in matrix.rows
            ),
            denominator=denominator,
            support=denominator,
            denominator_meaning="all native features exercised by this projection",
            empty_behaviour=MetricEmptyBehaviour.NONEMPTY,
            value=(
                sum(item.classification is classification for item in matrix.rows)
                / denominator
            ),
        )
        for classification in ProjectionSupportClassification
    )
    return ProjectionFidelityMetricsV1(
        support_matrix_digest=synthetic_digest(canonical_json_bytes(matrix)),
        metrics=metrics,
    )


__all__ = [
    "PROJECTION_FIDELITY_METRICS_SCHEMA_VERSION",
    "PROJECTION_MAPPING_PROFILE_SCHEMA_VERSION",
    "PROJECTION_SUPPORT_MATRIX_SCHEMA_VERSION",
    "ProjectionFidelityMetricsV1",
    "ProjectionMappingDefinitionV1",
    "ProjectionMappingProfileV1",
    "ProjectionSupportClassification",
    "ProjectionSupportMatrixV1",
    "ProjectionSupportRowV1",
    "ProjectionTarget",
    "compile_projection_support_matrix",
    "evaluate_projection_fidelity",
]
