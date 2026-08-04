"""Independent denominator-bearing ReBAC component metrics."""

from __future__ import annotations

from typing import Literal

from pydantic import field_validator

from synthworld.enterprise.authorization_common import MechanismOutcome
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.models import EnterpriseOperatorModel, SyntheticDigestV1
from synthworld.enterprise.rbac.common import (
    MetricEmptyBehaviour,
    canonical_operator_records,
    canonical_strings,
    canonical_synthetic_records,
)
from synthworld.enterprise.rbac.metrics import EnterpriseAuthorizationMetricV1
from synthworld.enterprise.rebac.common import ENTERPRISE_REBAC_METRICS_SCHEMA_VERSION
from synthworld.enterprise.rebac.models import CompiledEnterpriseRebacTruthV1
from synthworld.models import SyntheticModel


class RebacCellPredictionV1(EnterpriseOperatorModel):
    cell_id: str
    actual_outcome: MechanismOutcome
    intended_outcome: MechanismOutcome
    actual_path_ids: tuple[str, ...] = ()
    intended_path_ids: tuple[str, ...] = ()

    @field_validator("actual_path_ids", "intended_path_ids")
    @classmethod
    def canonical_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "rebac_predicted_path_id")


class EnterpriseRebacPredictionV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    cells: tuple[RebacCellPredictionV1, ...] = ()

    @field_validator("cells")
    @classmethod
    def canonical_cells(
        cls, value: tuple[RebacCellPredictionV1, ...]
    ) -> tuple[RebacCellPredictionV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple((item.cell_id,) for item in value),
            description="rebac_prediction_cell_id",
        )


class EnterpriseRebacMetricsV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = ENTERPRISE_REBAC_METRICS_SCHEMA_VERSION
    rebac_truth_digest: SyntheticDigestV1
    metrics: tuple[EnterpriseAuthorizationMetricV1, ...]

    @field_validator("metrics")
    @classmethod
    def canonical_metrics(
        cls, value: tuple[EnterpriseAuthorizationMetricV1, ...]
    ) -> tuple[EnterpriseAuthorizationMetricV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.family, item.name) for item in value),
            description="rebac_metric_name",
        )


def evaluate_enterprise_rebac(
    *, truth: CompiledEnterpriseRebacTruthV1, predictions: EnterpriseRebacPredictionV1
) -> EnterpriseRebacMetricsV1:
    cells = {item.cell_id: item for item in predictions.cells}
    expected_ids = {item.cell_id for item in truth.cells}
    if not set(cells) <= expected_ids:
        raise ValueError("unknown_rebac_prediction_cell_id")
    decision_correct = sum(
        prediction is not None
        and prediction.actual_outcome is item.actual_outcome
        and prediction.intended_outcome is item.intended_outcome
        for item in truth.cells
        for prediction in (cells.get(item.cell_id),)
    )
    path_cells = tuple(
        item for item in truth.cells if item.actual_path_ids or item.intended_path_ids
    )
    path_correct = sum(
        prediction is not None
        and prediction.actual_path_ids == item.actual_path_ids
        and prediction.intended_path_ids == item.intended_path_ids
        for item in path_cells
        for prediction in (cells.get(item.cell_id),)
    )
    return EnterpriseRebacMetricsV1(
        rebac_truth_digest=synthetic_digest(canonical_json_bytes(truth)),
        metrics=(
            _metric(
                "rebac_decision_accuracy",
                decision_correct,
                len(truth.cells),
                "all frozen cells in the ReBAC component truth",
                nonempty=True,
            ),
            _metric(
                "relationship_path_exact_match_rate",
                path_correct,
                len(path_cells),
                "cells with at least one canonical ReBAC path",
                nonempty=False,
            ),
        ),
    )


def perfect_enterprise_rebac_prediction(
    truth: CompiledEnterpriseRebacTruthV1,
) -> EnterpriseRebacPredictionV1:
    return EnterpriseRebacPredictionV1(
        cells=tuple(
            RebacCellPredictionV1(
                cell_id=item.cell_id,
                actual_outcome=item.actual_outcome,
                intended_outcome=item.intended_outcome,
                actual_path_ids=item.actual_path_ids,
                intended_path_ids=item.intended_path_ids,
            )
            for item in truth.cells
        )
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
        family="rebac",
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
    "EnterpriseRebacMetricsV1",
    "EnterpriseRebacPredictionV1",
    "evaluate_enterprise_rebac",
    "perfect_enterprise_rebac_prediction",
]
