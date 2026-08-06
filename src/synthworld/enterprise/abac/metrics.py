"""Independent denominator-bearing ABAC component metrics."""

from __future__ import annotations

from typing import Literal

from pydantic import field_validator

from synthworld.enterprise.abac.common import ENTERPRISE_ABAC_METRICS_SCHEMA_VERSION
from synthworld.enterprise.abac.models import CompiledEnterpriseAbacTruthV1
from synthworld.enterprise.authorization_common import (
    MechanismOutcome,
    PredicateOutcome,
)
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.models import EnterpriseOperatorModel, SyntheticDigestV1
from synthworld.enterprise.rbac.common import (
    MetricEmptyBehaviour,
    canonical_operator_records,
    canonical_synthetic_records,
)
from synthworld.enterprise.rbac.metrics import EnterpriseAuthorizationMetricV1
from synthworld.models import SyntheticModel


class AbacCellPredictionV1(EnterpriseOperatorModel):
    cell_id: str
    actual_outcome: MechanismOutcome
    intended_outcome: MechanismOutcome


class AbacPredicatePredictionV1(EnterpriseOperatorModel):
    truth_id: str
    outcome: PredicateOutcome


class EnterpriseAbacPredictionV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    cells: tuple[AbacCellPredictionV1, ...] = ()
    predicates: tuple[AbacPredicatePredictionV1, ...] = ()

    @field_validator("cells", "predicates")
    @classmethod
    def canonical_predictions(
        cls,
        value: tuple[AbacCellPredictionV1 | AbacPredicatePredictionV1, ...],
    ) -> tuple[AbacCellPredictionV1 | AbacPredicatePredictionV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple(
                (
                    item.cell_id
                    if isinstance(item, AbacCellPredictionV1)
                    else item.truth_id,
                )
                for item in value
            ),
            description="abac_prediction_id",
        )


class EnterpriseAbacMetricsV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = ENTERPRISE_ABAC_METRICS_SCHEMA_VERSION
    abac_truth_digest: SyntheticDigestV1
    metrics: tuple[EnterpriseAuthorizationMetricV1, ...]

    @field_validator("metrics")
    @classmethod
    def canonical_metrics(
        cls, value: tuple[EnterpriseAuthorizationMetricV1, ...]
    ) -> tuple[EnterpriseAuthorizationMetricV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.family, item.name) for item in value),
            description="abac_metric_name",
        )


def evaluate_enterprise_abac(
    *, truth: CompiledEnterpriseAbacTruthV1, predictions: EnterpriseAbacPredictionV1
) -> EnterpriseAbacMetricsV1:
    cells = {item.cell_id: item for item in predictions.cells}
    predicates = {item.truth_id: item for item in predictions.predicates}
    expected_cell_ids = {item.cell_id for item in truth.cells}
    expected_predicate_ids = {item.truth_id for item in truth.predicate_truth}
    if (
        not set(cells) <= expected_cell_ids
        or not set(predicates) <= expected_predicate_ids
    ):
        raise ValueError("unknown_abac_prediction_id")
    cell_correct = sum(
        prediction is not None
        and prediction.actual_outcome is item.actual_outcome
        and prediction.intended_outcome is item.intended_outcome
        for item in truth.cells
        for prediction in (cells.get(item.cell_id),)
    )
    predicate_correct = sum(
        prediction is not None and prediction.outcome is item.outcome
        for item in truth.predicate_truth
        for prediction in (predicates.get(item.truth_id),)
    )
    return EnterpriseAbacMetricsV1(
        abac_truth_digest=synthetic_digest(canonical_json_bytes(truth)),
        metrics=(
            _metric(
                "abac_decision_accuracy",
                cell_correct,
                len(truth.cells),
                "all frozen cells in the ABAC component truth",
                nonempty=True,
            ),
            _metric(
                "predicate_outcome_accuracy",
                predicate_correct,
                len(truth.predicate_truth),
                "all evaluated named ABAC predicates",
                nonempty=False,
            ),
        ),
    )


def perfect_enterprise_abac_prediction(
    truth: CompiledEnterpriseAbacTruthV1,
) -> EnterpriseAbacPredictionV1:
    return EnterpriseAbacPredictionV1(
        cells=tuple(
            AbacCellPredictionV1(
                cell_id=item.cell_id,
                actual_outcome=item.actual_outcome,
                intended_outcome=item.intended_outcome,
            )
            for item in truth.cells
        ),
        predicates=tuple(
            AbacPredicatePredictionV1(truth_id=item.truth_id, outcome=item.outcome)
            for item in truth.predicate_truth
        ),
    )


def _metric(
    name: str,
    numerator: int,
    denominator: int,
    meaning: str,
    *,
    nonempty: bool,
) -> EnterpriseAuthorizationMetricV1:
    return EnterpriseAuthorizationMetricV1(
        family="abac",
        name=name,
        numerator=numerator,
        denominator=denominator,
        support=denominator,
        denominator_meaning=meaning,
        empty_behaviour=(
            MetricEmptyBehaviour.NONEMPTY
            if nonempty
            else MetricEmptyBehaviour.NULL_IF_EMPTY
        ),
        value=numerator / denominator if denominator else None,
    )


__all__ = [
    "EnterpriseAbacMetricsV1",
    "EnterpriseAbacPredictionV1",
    "evaluate_enterprise_abac",
    "perfect_enterprise_abac_prediction",
]
