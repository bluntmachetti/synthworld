"""Standard-derived conformance vectors and bounded interaction manifests."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from synthworld.enterprise.models import EnterpriseOperatorModel, LogicalKey
from synthworld.enterprise.rbac.common import (
    canonical_operator_records,
    canonical_strings,
    canonical_synthetic_records,
)
from synthworld.models import SyntheticModel

POLICY_COVERAGE_MANIFEST_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"


class AuthorizationConformanceVectorV1(EnterpriseOperatorModel):
    vector_id: LogicalKey
    standards_source_id: LogicalKey
    native_feature: str = Field(min_length=1)
    expected_semantics: str = Field(min_length=1)


class CoverageFactorV1(SyntheticModel):
    name: str
    levels: tuple[str, ...] = Field(min_length=1)

    @field_validator("levels")
    @classmethod
    def canonical_levels(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "coverage_factor_level")


class CoverageFactorValueV1(SyntheticModel):
    factor: str
    value: str


class CoverageTupleV1(SyntheticModel):
    tuple_id: str
    factor_values: tuple[CoverageFactorValueV1, ...] = Field(min_length=1)

    @field_validator("factor_values")
    @classmethod
    def canonical_values(
        cls, value: tuple[CoverageFactorValueV1, ...]
    ) -> tuple[CoverageFactorValueV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.factor,) for item in value),
            description="coverage_tuple_factor",
        )


class CoverageConstraintV1(SyntheticModel):
    constraint_id: str
    unreachable_tuple_ids: tuple[str, ...] = Field(min_length=1)
    rationale: str = Field(min_length=1)

    @field_validator("unreachable_tuple_ids")
    @classmethod
    def canonical_tuples(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "constraint_unreachable_tuple_id")


class PolicyCoverageManifestV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = POLICY_COVERAGE_MANIFEST_SCHEMA_VERSION
    suite_id: str
    seed: int
    interaction_strength: int = Field(ge=1)
    factors: tuple[CoverageFactorV1, ...] = Field(min_length=1)
    constraints: tuple[CoverageConstraintV1, ...]
    covered_tuples: tuple[CoverageTupleV1, ...]
    unreachable_tuples: tuple[CoverageTupleV1, ...]
    conformance_vector_ids: tuple[str, ...] = Field(min_length=1)
    exhaustive: Literal[False] = False

    @field_validator("factors")
    @classmethod
    def canonical_factors(
        cls, value: tuple[CoverageFactorV1, ...]
    ) -> tuple[CoverageFactorV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.name,) for item in value),
            description="coverage_factor_name",
        )

    @field_validator("constraints")
    @classmethod
    def canonical_constraints(
        cls, value: tuple[CoverageConstraintV1, ...]
    ) -> tuple[CoverageConstraintV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.constraint_id,) for item in value),
            description="coverage_constraint_id",
        )

    @field_validator("covered_tuples", "unreachable_tuples")
    @classmethod
    def canonical_tuples(
        cls, value: tuple[CoverageTupleV1, ...]
    ) -> tuple[CoverageTupleV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.tuple_id,) for item in value),
            description="coverage_tuple_id",
        )

    @field_validator("conformance_vector_ids")
    @classmethod
    def canonical_vectors(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "coverage_conformance_vector_id")

    @model_validator(mode="after")
    def validate_coverage_space(self) -> Self:
        if self.interaction_strength > len(self.factors):
            raise ValueError("coverage_strength_exceeds_factor_count")
        factor_levels = {item.name: set(item.levels) for item in self.factors}
        covered = {item.tuple_id for item in self.covered_tuples}
        unreachable = {item.tuple_id for item in self.unreachable_tuples}
        if covered & unreachable:
            raise ValueError("coverage_tuple_both_covered_and_unreachable")
        for item in (*self.covered_tuples, *self.unreachable_tuples):
            if len(item.factor_values) != self.interaction_strength:
                raise ValueError("coverage_tuple_strength_mismatch")
            for pair in item.factor_values:
                if pair.factor not in factor_levels:
                    raise ValueError("coverage_tuple_unknown_factor")
                if pair.value not in factor_levels[pair.factor]:
                    raise ValueError("coverage_tuple_unknown_level")
        constrained = {
            tuple_id
            for constraint in self.constraints
            for tuple_id in constraint.unreachable_tuple_ids
        }
        if constrained != unreachable:
            raise ValueError("coverage_constraint_inventory_mismatch")
        return self


def validate_conformance_vectors(
    vectors: tuple[AuthorizationConformanceVectorV1, ...],
    *,
    standards_source_ids: set[str],
) -> tuple[AuthorizationConformanceVectorV1, ...]:
    ordered = canonical_operator_records(
        vectors,
        keys=tuple((item.vector_id,) for item in vectors),
        description="authorization_conformance_vector_id",
    )
    if any(item.standards_source_id not in standards_source_ids for item in ordered):
        raise ValueError("conformance_vector_unknown_standards_source")
    return ordered


__all__ = [name for name in globals() if name.endswith("V1")]
__all__ += ["validate_conformance_vectors"]
