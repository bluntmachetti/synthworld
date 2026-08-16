"""Publicly keyed composed enterprise authorization predictions and metrics."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from synthworld.enterprise.authorization.models import (
    CompiledEnterpriseAccessCellV1,
    CompiledEnterpriseAccessStateV1,
    MechanismOutcomeSetV1,
)
from synthworld.enterprise.authorization_common import MechanismOutcome
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.models import EnterpriseOperatorModel, SyntheticDigestV1
from synthworld.enterprise.rbac.common import (
    AuthorizationDecision,
    BindingStatus,
    LifecycleStatus,
    MetricEmptyBehaviour,
    canonical_operator_records,
    canonical_synthetic_records,
)
from synthworld.enterprise.rbac.metrics import EnterpriseAuthorizationMetricV1
from synthworld.models import SyntheticModel

ENTERPRISE_AUTHORIZATION_PREDICTION_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_AUTHORIZATION_METRICS_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_AUTHORIZATION_EVALUATION_SCOPE_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"


class AuthorizationScoredDimension(StrEnum):
    EFFECTIVE_DECISION = "effective_decision"
    FINAL_DECISION = "final_decision"
    POLICY_CONFLICT = "policy_conflict"
    BINDING_STATUS = "binding_status"
    LIFECYCLE_STATUS = "lifecycle_status"


class EnterpriseAuthorizationScopeCellV1(SyntheticModel):
    cell_id: str = Field(min_length=1)
    scored_dimensions: tuple[AuthorizationScoredDimension, ...] = Field(min_length=1)

    @field_validator("scored_dimensions")
    @classmethod
    def canonical_dimensions(
        cls, value: tuple[AuthorizationScoredDimension, ...]
    ) -> tuple[AuthorizationScoredDimension, ...]:
        ordered = tuple(sorted(value, key=lambda item: item.value))
        if len(ordered) != len(set(ordered)):
            raise ValueError("duplicate_authorization_scored_dimension")
        return ordered


class EnterpriseAuthorizationEvaluationScopeV1(SyntheticModel):
    """Public declaration of the dimensions eligible for scoring per cell."""

    schema_version: Literal["1.0.0"] = (
        ENTERPRISE_AUTHORIZATION_EVALUATION_SCOPE_SCHEMA_VERSION
    )
    evaluation_corpus_digest: SyntheticDigestV1
    authorization_kernel_digest: SyntheticDigestV1
    cells: tuple[EnterpriseAuthorizationScopeCellV1, ...] = Field(min_length=1)

    @field_validator("cells")
    @classmethod
    def canonical_cells(
        cls, value: tuple[EnterpriseAuthorizationScopeCellV1, ...]
    ) -> tuple[EnterpriseAuthorizationScopeCellV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.cell_id,) for item in value),
            description="enterprise_authorization_scope_cell_id",
        )


class EnterpriseAuthorizationExecutionMetadataV1(EnterpriseOperatorModel):
    """Deterministic product and adapter identity supplied with one prediction."""

    synthworld_package_version: str = Field(min_length=1)
    adapter_name: str = Field(min_length=1)
    adapter_version: str = Field(min_length=1)
    system_name: str = Field(min_length=1)
    system_version: str = Field(min_length=1)
    policy_name: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class EnterpriseAuthorizationMechanismPredictionV1(EnterpriseOperatorModel):
    rbac: MechanismOutcome | None = None
    abac: MechanismOutcome | None = None
    rebac: MechanismOutcome | None = None

    @model_validator(mode="after")
    def nonempty(self) -> Self:
        if self.rbac is None and self.abac is None and self.rebac is None:
            raise ValueError("authorization_mechanism_prediction_empty")
        return self


class EnterpriseAuthorizationCellPredictionV1(EnterpriseOperatorModel):
    """One public-cell keyed observation from the system under test."""

    cell_id: str = Field(min_length=1)
    mechanism_outcomes: EnterpriseAuthorizationMechanismPredictionV1
    effective_decision: AuthorizationDecision | None = None
    final_decision: AuthorizationDecision | None = None
    policy_conflict: bool | None = None
    binding_status: BindingStatus | None = None
    lifecycle_status: LifecycleStatus | None = None


class EnterpriseAuthorizationPredictionV1(EnterpriseOperatorModel):
    """Digest-bound composed authorization submission with exact cell coverage."""

    schema_version: Literal["1.0.0"] = (
        ENTERPRISE_AUTHORIZATION_PREDICTION_SCHEMA_VERSION
    )
    identity_access_universe_digest: SyntheticDigestV1
    evaluation_corpus_digest: SyntheticDigestV1
    composition_digest: SyntheticDigestV1
    authorization_kernel_digest: SyntheticDigestV1
    evaluation_scope_digest: SyntheticDigestV1
    execution: EnterpriseAuthorizationExecutionMetadataV1
    cells: tuple[EnterpriseAuthorizationCellPredictionV1, ...] = Field(min_length=1)

    @field_validator("cells")
    @classmethod
    def canonical_cells(
        cls, value: tuple[EnterpriseAuthorizationCellPredictionV1, ...]
    ) -> tuple[EnterpriseAuthorizationCellPredictionV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple((item.cell_id,) for item in value),
            description="enterprise_authorization_prediction_cell_id",
        )


class EnterpriseAuthorizationEvaluatedSystemV1(SyntheticModel):
    """Evaluator-retained copy of the submitted product and policy identity."""

    synthworld_package_version: str
    adapter_name: str
    adapter_version: str
    system_name: str
    system_version: str
    policy_name: str
    policy_version: str
    policy_sha256: str


class EnterpriseAuthorizationMetricsV1(SyntheticModel):
    """Independent composed and per-mechanism metrics; never an aggregate."""

    schema_version: Literal["1.0.0"] = ENTERPRISE_AUTHORIZATION_METRICS_SCHEMA_VERSION
    evaluation_scope_schema_version: str = Field(min_length=1)
    access_state_schema_version: str = Field(min_length=1)
    prediction_schema_version: str = Field(min_length=1)
    identity_access_universe_digest: SyntheticDigestV1
    evaluation_corpus_digest: SyntheticDigestV1
    composition_digest: SyntheticDigestV1
    authorization_kernel_digest: SyntheticDigestV1
    evaluation_scope_digest: SyntheticDigestV1
    access_state_digest: SyntheticDigestV1
    prediction_digest: SyntheticDigestV1
    evaluated_system: EnterpriseAuthorizationEvaluatedSystemV1
    metrics: tuple[EnterpriseAuthorizationMetricV1, ...]

    @field_validator("metrics")
    @classmethod
    def canonical_metrics(
        cls, value: tuple[EnterpriseAuthorizationMetricV1, ...]
    ) -> tuple[EnterpriseAuthorizationMetricV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.family, item.name) for item in value),
            description="composed_enterprise_authorization_metric_name",
        )


def evaluate_enterprise_authorization(
    *,
    scope: EnterpriseAuthorizationEvaluationScopeV1,
    truth: CompiledEnterpriseAccessStateV1,
    predictions: EnterpriseAuthorizationPredictionV1,
) -> EnterpriseAuthorizationMetricsV1:
    """Score exact public-cell observations against aggregate evaluator truth."""

    dimensions_by_cell = _validate_evaluation_scope(truth, scope)
    _validate_prediction_binding(truth, scope, predictions)
    prediction_by_cell = {item.cell_id: item for item in predictions.cells}
    expected_cell_ids = {item.cell_id for item in truth.cells}
    if set(prediction_by_cell) != expected_cell_ids:
        raise ValueError("enterprise_authorization_prediction_cell_inventory_mismatch")

    conflict_by_cell = {item.cell_id: item for item in truth.policy_conflicts}
    metrics = [
        _accuracy(
            family="composed",
            name="effective_decision_accuracy",
            truth=_selected_cells(
                truth.cells,
                dimensions_by_cell,
                AuthorizationScoredDimension.EFFECTIVE_DECISION,
            ),
            predictions=prediction_by_cell,
            matches=lambda expected, observed: (
                observed.effective_decision is expected.effective_decision
            ),
            denominator_meaning="all aggregate enterprise authorization cells",
            nonempty=True,
        ),
        _accuracy(
            family="composed",
            name="final_decision_accuracy",
            truth=_selected_cells(
                truth.cells,
                dimensions_by_cell,
                AuthorizationScoredDimension.FINAL_DECISION,
            ),
            predictions=prediction_by_cell,
            matches=lambda expected, observed: (
                observed.final_decision is expected.final_decision
            ),
            denominator_meaning="all aggregate enterprise authorization cells",
            nonempty=True,
        ),
        _accuracy(
            family="mechanism",
            name="mechanism_outcome_exact_match_rate",
            truth=truth.cells,
            predictions=prediction_by_cell,
            matches=lambda expected, observed: _mechanisms_match(
                expected.actual_mechanism_outcomes, observed.mechanism_outcomes
            ),
            denominator_meaning=(
                "all aggregate cells, comparing every selected mechanism outcome"
            ),
            nonempty=True,
        ),
        _accuracy(
            family="mechanism",
            name="profile_mechanism_inventory_exact_match_rate",
            truth=truth.cells,
            predictions=prediction_by_cell,
            matches=lambda expected, observed: (
                _mechanism_inventory(expected.actual_mechanism_outcomes)
                == _mechanism_inventory(observed.mechanism_outcomes)
            ),
            denominator_meaning=(
                "all aggregate cells, comparing the mechanisms selected by the profile"
            ),
            nonempty=True,
        ),
    ]
    metrics.extend(
        (
            _mechanism_metric(truth.cells, prediction_by_cell, "rbac"),
            _mechanism_metric(truth.cells, prediction_by_cell, "abac"),
            _mechanism_metric(truth.cells, prediction_by_cell, "rebac"),
        )
    )
    metrics.extend(
        (
            _accuracy(
                family="conflict",
                name="policy_conflict_detection_accuracy",
                truth=_selected_cells(
                    truth.cells,
                    dimensions_by_cell,
                    AuthorizationScoredDimension.POLICY_CONFLICT,
                ),
                predictions=prediction_by_cell,
                matches=lambda expected, observed: (
                    observed.policy_conflict
                    is conflict_by_cell[expected.cell_id].actual_conflict
                ),
                denominator_meaning="all aggregate enterprise authorization cells",
                nonempty=True,
            ),
            _accuracy(
                family="conflict",
                name="conflict_resolution_accuracy",
                truth=tuple(
                    item
                    for item in truth.cells
                    if conflict_by_cell[item.cell_id].actual_conflict
                    and AuthorizationScoredDimension.POLICY_CONFLICT
                    in dimensions_by_cell[item.cell_id]
                    and AuthorizationScoredDimension.EFFECTIVE_DECISION
                    in dimensions_by_cell[item.cell_id]
                ),
                predictions=prediction_by_cell,
                matches=lambda expected, observed: (
                    observed.effective_decision is expected.effective_decision
                ),
                denominator_meaning="aggregate cells with an actual policy conflict",
            ),
            _accuracy(
                family="binding",
                name="binding_status_accuracy",
                truth=tuple(
                    item
                    for item in truth.cells
                    if AuthorizationScoredDimension.BINDING_STATUS
                    in dimensions_by_cell[item.cell_id]
                ),
                predictions=prediction_by_cell,
                matches=lambda expected, observed: (
                    observed.binding_status is expected.binding_status
                ),
                denominator_meaning="aggregate cells with an applicable binding gate",
            ),
            _accuracy(
                family="lifecycle",
                name="lifecycle_status_accuracy",
                truth=tuple(
                    item
                    for item in truth.cells
                    if AuthorizationScoredDimension.LIFECYCLE_STATUS
                    in dimensions_by_cell[item.cell_id]
                ),
                predictions=prediction_by_cell,
                matches=lambda expected, observed: (
                    observed.lifecycle_status is expected.lifecycle_status
                ),
                denominator_meaning="aggregate cells with an applicable lifecycle gate",
            ),
            _accuracy(
                family="runtime_gate",
                name="runtime_gate_decision_accuracy",
                truth=tuple(
                    item
                    for item in truth.cells
                    if item.final_decision is not item.effective_decision
                    and AuthorizationScoredDimension.FINAL_DECISION
                    in dimensions_by_cell[item.cell_id]
                ),
                predictions=prediction_by_cell,
                matches=lambda expected, observed: (
                    observed.final_decision is expected.final_decision
                ),
                denominator_meaning=(
                    "aggregate cells whose binding or lifecycle gate changes the "
                    "decision"
                ),
            ),
        )
    )
    execution = predictions.execution
    return EnterpriseAuthorizationMetricsV1(
        evaluation_scope_schema_version=scope.schema_version,
        access_state_schema_version=truth.schema_version,
        prediction_schema_version=predictions.schema_version,
        identity_access_universe_digest=truth.identity_access_universe_digest,
        evaluation_corpus_digest=truth.evaluation_corpus_digest,
        composition_digest=truth.composition_digest,
        authorization_kernel_digest=truth.authorization_kernel_digest,
        evaluation_scope_digest=synthetic_digest(canonical_json_bytes(scope)),
        access_state_digest=synthetic_digest(canonical_json_bytes(truth)),
        prediction_digest=synthetic_digest(canonical_json_bytes(predictions)),
        evaluated_system=EnterpriseAuthorizationEvaluatedSystemV1(
            synthworld_package_version=execution.synthworld_package_version,
            adapter_name=execution.adapter_name,
            adapter_version=execution.adapter_version,
            system_name=execution.system_name,
            system_version=execution.system_version,
            policy_name=execution.policy_name,
            policy_version=execution.policy_version,
            policy_sha256=execution.policy_sha256,
        ),
        metrics=tuple(metrics),
    )


def perfect_enterprise_authorization_prediction(
    truth: CompiledEnterpriseAccessStateV1,
    *,
    scope: EnterpriseAuthorizationEvaluationScopeV1,
    execution: EnterpriseAuthorizationExecutionMetadataV1,
) -> EnterpriseAuthorizationPredictionV1:
    """Project aggregate truth into the exact candidate contract for tests."""

    dimensions_by_cell = _validate_evaluation_scope(truth, scope)
    conflicts = {item.cell_id: item.actual_conflict for item in truth.policy_conflicts}
    return EnterpriseAuthorizationPredictionV1(
        identity_access_universe_digest=truth.identity_access_universe_digest,
        evaluation_corpus_digest=truth.evaluation_corpus_digest,
        composition_digest=truth.composition_digest,
        authorization_kernel_digest=truth.authorization_kernel_digest,
        evaluation_scope_digest=synthetic_digest(canonical_json_bytes(scope)),
        execution=execution,
        cells=tuple(
            EnterpriseAuthorizationCellPredictionV1(
                cell_id=item.cell_id,
                mechanism_outcomes=EnterpriseAuthorizationMechanismPredictionV1(
                    rbac=item.actual_mechanism_outcomes.rbac,
                    abac=item.actual_mechanism_outcomes.abac,
                    rebac=item.actual_mechanism_outcomes.rebac,
                ),
                effective_decision=(
                    item.effective_decision
                    if AuthorizationScoredDimension.EFFECTIVE_DECISION
                    in dimensions_by_cell[item.cell_id]
                    else None
                ),
                final_decision=(
                    item.final_decision
                    if AuthorizationScoredDimension.FINAL_DECISION
                    in dimensions_by_cell[item.cell_id]
                    else None
                ),
                policy_conflict=(
                    conflicts[item.cell_id]
                    if AuthorizationScoredDimension.POLICY_CONFLICT
                    in dimensions_by_cell[item.cell_id]
                    else None
                ),
                binding_status=(
                    item.binding_status
                    if AuthorizationScoredDimension.BINDING_STATUS
                    in dimensions_by_cell[item.cell_id]
                    else None
                ),
                lifecycle_status=(
                    item.lifecycle_status
                    if AuthorizationScoredDimension.LIFECYCLE_STATUS
                    in dimensions_by_cell[item.cell_id]
                    else None
                ),
            )
            for item in truth.cells
        ),
    )


def _validate_prediction_binding(
    truth: CompiledEnterpriseAccessStateV1,
    scope: EnterpriseAuthorizationEvaluationScopeV1,
    predictions: EnterpriseAuthorizationPredictionV1,
) -> None:
    bindings = (
        (
            "universe",
            predictions.identity_access_universe_digest,
            truth.identity_access_universe_digest,
        ),
        (
            "corpus",
            predictions.evaluation_corpus_digest,
            truth.evaluation_corpus_digest,
        ),
        ("composition", predictions.composition_digest, truth.composition_digest),
        (
            "kernel",
            predictions.authorization_kernel_digest,
            truth.authorization_kernel_digest,
        ),
        (
            "scope",
            predictions.evaluation_scope_digest,
            synthetic_digest(canonical_json_bytes(scope)),
        ),
    )
    for name, submitted, expected in bindings:
        if submitted != expected:
            raise ValueError(
                f"enterprise_authorization_prediction_{name}_digest_mismatch"
            )


def _validate_evaluation_scope(
    truth: CompiledEnterpriseAccessStateV1,
    scope: EnterpriseAuthorizationEvaluationScopeV1,
) -> dict[str, frozenset[AuthorizationScoredDimension]]:
    if scope.evaluation_corpus_digest != truth.evaluation_corpus_digest:
        raise ValueError("enterprise_authorization_scope_corpus_digest_mismatch")
    if scope.authorization_kernel_digest != truth.authorization_kernel_digest:
        raise ValueError("enterprise_authorization_scope_kernel_digest_mismatch")
    expected_cell_ids = {item.cell_id for item in truth.cells}
    if {item.cell_id for item in scope.cells} != expected_cell_ids:
        raise ValueError("enterprise_authorization_scope_cell_inventory_mismatch")
    return {item.cell_id: frozenset(item.scored_dimensions) for item in scope.cells}


def _selected_cells(
    truth: tuple[CompiledEnterpriseAccessCellV1, ...],
    dimensions_by_cell: dict[str, frozenset[AuthorizationScoredDimension]],
    dimension: AuthorizationScoredDimension,
) -> tuple[CompiledEnterpriseAccessCellV1, ...]:
    return tuple(
        item for item in truth if dimension in dimensions_by_cell[item.cell_id]
    )


def _mechanism_metric(
    truth: tuple[CompiledEnterpriseAccessCellV1, ...],
    predictions: dict[str, EnterpriseAuthorizationCellPredictionV1],
    family: Literal["rbac", "abac", "rebac"],
) -> EnterpriseAuthorizationMetricV1:
    selected = tuple(
        item
        for item in truth
        if getattr(item.actual_mechanism_outcomes, family) is not None
    )
    return _accuracy(
        family=family,
        name=f"{family}_outcome_accuracy",
        truth=selected,
        predictions=predictions,
        matches=lambda expected, observed: (
            getattr(observed.mechanism_outcomes, family)
            is getattr(expected.actual_mechanism_outcomes, family)
        ),
        denominator_meaning=f"aggregate cells whose profile selects {family.upper()}",
    )


def _mechanisms_match(
    expected: MechanismOutcomeSetV1,
    observed: EnterpriseAuthorizationMechanismPredictionV1,
) -> bool:
    return all(
        getattr(expected, family) is getattr(observed, family)
        for family in ("rbac", "abac", "rebac")
    )


def _mechanism_inventory(
    outcomes: MechanismOutcomeSetV1 | EnterpriseAuthorizationMechanismPredictionV1,
) -> tuple[str, ...]:
    return tuple(
        family
        for family in ("rbac", "abac", "rebac")
        if getattr(outcomes, family) is not None
    )


def _accuracy(
    *,
    family: str,
    name: str,
    truth: tuple[CompiledEnterpriseAccessCellV1, ...],
    predictions: dict[str, EnterpriseAuthorizationCellPredictionV1],
    matches: Callable[
        [CompiledEnterpriseAccessCellV1, EnterpriseAuthorizationCellPredictionV1],
        bool,
    ],
    denominator_meaning: str,
    nonempty: bool = False,
) -> EnterpriseAuthorizationMetricV1:
    numerator = sum(
        matches(expected, predictions[expected.cell_id]) for expected in truth
    )
    denominator = len(truth)
    if nonempty and denominator == 0:
        raise ValueError(f"{name} requires nonempty selected coverage")
    return EnterpriseAuthorizationMetricV1(
        family=family,
        name=name,
        numerator=numerator,
        denominator=denominator,
        support=denominator,
        denominator_meaning=denominator_meaning,
        empty_behaviour=(
            MetricEmptyBehaviour.NONEMPTY
            if nonempty
            else MetricEmptyBehaviour.NULL_IF_EMPTY
        ),
        value=numerator / denominator if denominator else None,
    )


__all__ = [name for name in globals() if name.endswith("V1")]
__all__ += [
    "AuthorizationScoredDimension",
    "evaluate_enterprise_authorization",
    "perfect_enterprise_authorization_prediction",
]
