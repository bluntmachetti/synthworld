"""Independent, denominator-bearing directory/RBAC metrics."""

from __future__ import annotations

import math
from collections import defaultdict
from itertools import pairwise
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.models import EnterpriseOperatorModel, SyntheticDigestV1
from synthworld.enterprise.rbac.common import (
    ENTERPRISE_DIRECTORY_RBAC_METRICS_SCHEMA_VERSION,
    ActivationOutcome,
    AuthorizationDecision,
    MetricEmptyBehaviour,
    canonical_operator_records,
    canonical_strings,
    canonical_synthetic_records,
)
from synthworld.enterprise.rbac.models import (
    CompiledEnterpriseDirectoryRbacTruthV1,
    ObservedSessionTruthV1,
)
from synthworld.models import SyntheticModel


class DirectoryRbacCellPredictionV1(EnterpriseOperatorModel):
    cell_id: str = Field(min_length=1)
    birthright_decision: AuthorizationDecision
    intended_decision: AuthorizationDecision
    effective_decision: AuthorizationDecision
    final_decision: AuthorizationDecision
    effective_path_ids: tuple[str, ...] = ()

    @field_validator("effective_path_ids")
    @classmethod
    def canonical_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "predicted_effective_path_id")


class AuthorizedRoleSetPredictionV1(EnterpriseOperatorModel):
    subject_id: str = Field(min_length=1)
    role_ids: tuple[str, ...] = ()

    @field_validator("role_ids")
    @classmethod
    def canonical_roles(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "predicted_authorized_role_id")


class ActivationPredictionV1(EnterpriseOperatorModel):
    activation_request_id: str = Field(min_length=1)
    expected_outcome: ActivationOutcome
    observed_outcome: ActivationOutcome
    actual_activated_role_ids: tuple[str, ...] = ()
    usable_activated_role_ids: tuple[str, ...] = ()
    unauthorized_activated_role_ids: tuple[str, ...] = ()

    @field_validator(
        "actual_activated_role_ids",
        "usable_activated_role_ids",
        "unauthorized_activated_role_ids",
    )
    @classmethod
    def canonical_roles(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "predicted_activation_role_id")


class SsdPredictionV1(EnterpriseOperatorModel):
    constraint_id: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    violated: bool


class DsdPredictionV1(EnterpriseOperatorModel):
    constraint_id: str = Field(min_length=1)
    activation_request_id: str = Field(min_length=1)
    request_violated: bool
    observed_session_violated: bool


class BirthrightAssignmentPredictionV1(EnterpriseOperatorModel):
    rule_id: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    assignment_ids: tuple[str, ...] = ()

    @field_validator("assignment_ids")
    @classmethod
    def canonical_assignments(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "predicted_birthright_assignment_id")


class EnterpriseDirectoryRbacPredictionV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    cells: tuple[DirectoryRbacCellPredictionV1, ...] = ()
    authorized_role_sets: tuple[AuthorizedRoleSetPredictionV1, ...] = ()
    activations: tuple[ActivationPredictionV1, ...] = ()
    ssd_evaluations: tuple[SsdPredictionV1, ...] = ()
    dsd_evaluations: tuple[DsdPredictionV1, ...] = ()
    birthright_assignments: tuple[BirthrightAssignmentPredictionV1, ...] = ()

    @field_validator("cells")
    @classmethod
    def canonical_cells(
        cls, value: tuple[DirectoryRbacCellPredictionV1, ...]
    ) -> tuple[DirectoryRbacCellPredictionV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple((item.cell_id,) for item in value),
            description="predicted_cell_id",
        )

    @field_validator("authorized_role_sets")
    @classmethod
    def canonical_role_sets(
        cls, value: tuple[AuthorizedRoleSetPredictionV1, ...]
    ) -> tuple[AuthorizedRoleSetPredictionV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple((item.subject_id,) for item in value),
            description="predicted_authorized_role_subject",
        )

    @field_validator("activations")
    @classmethod
    def canonical_activations(
        cls, value: tuple[ActivationPredictionV1, ...]
    ) -> tuple[ActivationPredictionV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple((item.activation_request_id,) for item in value),
            description="predicted_activation_request_id",
        )

    @field_validator("ssd_evaluations")
    @classmethod
    def canonical_ssd(
        cls, value: tuple[SsdPredictionV1, ...]
    ) -> tuple[SsdPredictionV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple((item.constraint_id, item.subject_id) for item in value),
            description="predicted_ssd_evaluation",
        )

    @field_validator("dsd_evaluations")
    @classmethod
    def canonical_dsd(
        cls, value: tuple[DsdPredictionV1, ...]
    ) -> tuple[DsdPredictionV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple(
                (item.activation_request_id, item.constraint_id) for item in value
            ),
            description="predicted_dsd_evaluation",
        )

    @field_validator("birthright_assignments")
    @classmethod
    def canonical_birthright(
        cls, value: tuple[BirthrightAssignmentPredictionV1, ...]
    ) -> tuple[BirthrightAssignmentPredictionV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple((item.rule_id, item.subject_id) for item in value),
            description="predicted_birthright_rule_subject",
        )


class EnterpriseAuthorizationMetricV1(SyntheticModel):
    family: str = Field(min_length=1)
    name: str = Field(min_length=1)
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    support: int = Field(ge=0)
    denominator_meaning: str = Field(min_length=1)
    empty_behaviour: MetricEmptyBehaviour
    value: float | None

    @model_validator(mode="after")
    def valid_ratio(self) -> Self:
        if self.support != self.denominator:
            raise ValueError("metric_support_must_equal_denominator")
        if self.numerator > self.denominator:
            raise ValueError("metric_numerator_exceeds_denominator")
        if self.denominator == 0:
            if (
                self.empty_behaviour is not MetricEmptyBehaviour.NULL_IF_EMPTY
                or self.value is not None
            ):
                raise ValueError("empty_metric_must_be_null")
        elif self.value is None or not math.isclose(
            self.value,
            self.numerator / self.denominator,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise ValueError("metric_value_mismatch")
        return self


class EnterpriseDirectoryRbacMetricsV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = ENTERPRISE_DIRECTORY_RBAC_METRICS_SCHEMA_VERSION
    directory_rbac_truth_digest: SyntheticDigestV1
    metrics: tuple[EnterpriseAuthorizationMetricV1, ...]

    @field_validator("metrics")
    @classmethod
    def canonical_metrics(
        cls, value: tuple[EnterpriseAuthorizationMetricV1, ...]
    ) -> tuple[EnterpriseAuthorizationMetricV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.family, item.name) for item in value),
            description="enterprise_metric_name",
        )


def evaluate_enterprise_directory_rbac(
    *,
    truth: CompiledEnterpriseDirectoryRbacTruthV1,
    predictions: EnterpriseDirectoryRbacPredictionV1,
) -> EnterpriseDirectoryRbacMetricsV1:
    """Score independent semantic families; deliberately emit no aggregate."""

    cell_predictions = {item.cell_id: item for item in predictions.cells}
    role_predictions = {
        item.subject_id: item for item in predictions.authorized_role_sets
    }
    activation_predictions = {
        item.activation_request_id: item for item in predictions.activations
    }
    ssd_predictions = {
        (item.constraint_id, item.subject_id): item
        for item in predictions.ssd_evaluations
    }
    dsd_predictions = {
        (item.activation_request_id, item.constraint_id): item
        for item in predictions.dsd_evaluations
    }
    birthright_predictions = {
        (item.rule_id, item.subject_id): item
        for item in predictions.birthright_assignments
    }
    _reject_unknown_prediction_ids(
        truth,
        cells=set(cell_predictions),
        roles=set(role_predictions),
        activations=set(activation_predictions),
        ssd=set(ssd_predictions),
        dsd=set(dsd_predictions),
        birthright=set(birthright_predictions),
    )

    metrics: list[EnterpriseAuthorizationMetricV1] = []
    cell_fields = (
        ("birthright", "birthright_decision_accuracy", "birthright_decision"),
        ("intent", "intended_decision_accuracy", "intended_decision"),
        ("rbac", "effective_decision_accuracy", "effective_decision"),
        ("rbac", "rbac_decision_accuracy", "final_decision"),
    )
    for family, name, field_name in cell_fields:
        correct = sum(
            prediction is not None
            and getattr(prediction, field_name) == getattr(item, field_name)
            for item in truth.cells
            for prediction in (cell_predictions.get(item.cell_id),)
        )
        metrics.append(
            _metric(
                family,
                name,
                correct,
                len(truth.cells),
                "all frozen directory/RBAC evaluation cells",
                nonempty=True,
            )
        )
    metrics.append(
        _metric(
            "rbac",
            "rbac_derivation_path_exact_match_rate",
            sum(
                prediction is not None
                and prediction.effective_path_ids == item.effective_path_ids
                for item in truth.cells
                for prediction in (cell_predictions.get(item.cell_id),)
            ),
            len(truth.cells),
            "all frozen directory/RBAC evaluation cells",
            nonempty=True,
        )
    )
    metrics.append(
        _metric(
            "rbac",
            "authorized_role_exact_match_rate",
            sum(
                prediction is not None and prediction.role_ids == item.role_ids
                for item in truth.authorized_role_sets
                for prediction in (role_predictions.get(item.subject_id),)
            ),
            len(truth.authorized_role_sets),
            "subjects with a declared authorized-role truth row",
        )
    )
    sessions_by_id = {item.session_state_id: item for item in truth.observed_sessions}
    metrics.append(
        _metric(
            "activation",
            "activation_decision_accuracy",
            sum(
                prediction is not None
                and prediction.expected_outcome == item.expected_outcome
                for item in truth.activation_decisions
                for prediction in (
                    activation_predictions.get(item.activation_request_id),
                )
            ),
            len(truth.activation_decisions),
            "declared role-activation requests",
        )
    )
    metrics.append(
        _metric(
            "activation",
            "activated_role_exact_match_rate",
            sum(
                prediction is not None
                and prediction.observed_outcome == observed.observed_outcome
                and prediction.actual_activated_role_ids
                == observed.actual_activated_role_ids
                and prediction.usable_activated_role_ids
                == observed.usable_activated_role_ids
                for decision in truth.activation_decisions
                for observed in (sessions_by_id[decision.session_state_id],)
                for prediction in (
                    activation_predictions.get(decision.activation_request_id),
                )
            ),
            len(truth.activation_decisions),
            "declared observed session rows",
        )
    )
    metrics.extend(
        _sod_metrics(
            truth,
            ssd_predictions=ssd_predictions,
            dsd_predictions=dsd_predictions,
        )
    )
    metrics.extend(
        _unauthorized_activation_metrics(
            truth,
            activation_predictions=activation_predictions,
        )
    )
    expected_assignments: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in truth.birthright_assignments:
        if row.eligible:
            expected_assignments[(row.rule_id, row.subject_id)].add(row.assignment_id)
    metrics.append(
        _metric(
            "birthright",
            "birthright_assignment_exact_match_rate",
            sum(
                prediction is not None
                and prediction.assignment_ids
                == tuple(sorted(expected_assignments[(row.rule_id, row.subject_id)]))
                for row in truth.birthright_eligibility
                for prediction in (
                    birthright_predictions.get((row.rule_id, row.subject_id)),
                )
            ),
            len(truth.birthright_eligibility),
            "declared subject/rule birthright eligibility rows",
        )
    )
    effective_allows = tuple(
        item
        for item in truth.cells
        if item.effective_decision is AuthorizationDecision.ALLOW
    )
    intended_allows = tuple(
        item
        for item in truth.cells
        if item.intended_decision is AuthorizationDecision.ALLOW
    )
    metrics.extend(
        (
            _metric(
                "sprawl",
                "effective_outside_intent_rate",
                sum(
                    item.intended_decision is AuthorizationDecision.DENY
                    for item in effective_allows
                ),
                len(effective_allows),
                "effective-allow cells",
            ),
            _metric(
                "sprawl",
                "missing_intended_access_rate",
                sum(
                    item.effective_decision is AuthorizationDecision.DENY
                    for item in intended_allows
                ),
                len(intended_allows),
                "intended-allow cells",
            ),
            _metric(
                "birthright_breadth",
                "effective_outside_birthright_rate",
                sum(
                    item.birthright_decision is AuthorizationDecision.DENY
                    for item in effective_allows
                ),
                len(effective_allows),
                "effective-allow cells",
            ),
            _metric(
                "redundancy",
                "redundant_derivation_cell_rate",
                sum(len(item.effective_path_ids) > 1 for item in effective_allows),
                len(effective_allows),
                "effective-allow cells",
            ),
            _privilege_accumulation_metric(truth),
        )
    )
    return EnterpriseDirectoryRbacMetricsV1(
        directory_rbac_truth_digest=synthetic_digest(canonical_json_bytes(truth)),
        metrics=tuple(metrics),
    )


def perfect_enterprise_directory_rbac_prediction(
    truth: CompiledEnterpriseDirectoryRbacTruthV1,
) -> EnterpriseDirectoryRbacPredictionV1:
    """Project evaluator truth into the exact candidate-output contract for tests."""

    sessions = {item.session_state_id: item for item in truth.observed_sessions}
    assignment_ids: dict[tuple[str, str], set[str]] = defaultdict(set)
    for item in truth.birthright_assignments:
        if item.eligible:
            assignment_ids[(item.rule_id, item.subject_id)].add(item.assignment_id)
    return EnterpriseDirectoryRbacPredictionV1(
        cells=tuple(
            DirectoryRbacCellPredictionV1(
                cell_id=item.cell_id,
                birthright_decision=item.birthright_decision,
                intended_decision=item.intended_decision,
                effective_decision=item.effective_decision,
                final_decision=item.final_decision,
                effective_path_ids=item.effective_path_ids,
            )
            for item in truth.cells
        ),
        authorized_role_sets=tuple(
            AuthorizedRoleSetPredictionV1(
                subject_id=item.subject_id, role_ids=item.role_ids
            )
            for item in truth.authorized_role_sets
        ),
        activations=tuple(
            ActivationPredictionV1(
                activation_request_id=item.activation_request_id,
                expected_outcome=item.expected_outcome,
                observed_outcome=sessions[item.session_state_id].observed_outcome,
                actual_activated_role_ids=sessions[
                    item.session_state_id
                ].actual_activated_role_ids,
                usable_activated_role_ids=sessions[
                    item.session_state_id
                ].usable_activated_role_ids,
                unauthorized_activated_role_ids=sessions[
                    item.session_state_id
                ].unauthorized_activated_role_ids,
            )
            for item in truth.activation_decisions
        ),
        ssd_evaluations=tuple(
            SsdPredictionV1(
                constraint_id=item.constraint_id,
                subject_id=item.subject_id,
                violated=item.violated,
            )
            for item in truth.ssd_evaluations
        ),
        dsd_evaluations=tuple(
            DsdPredictionV1(
                constraint_id=item.constraint_id,
                activation_request_id=item.activation_request_id,
                request_violated=item.request_violated,
                observed_session_violated=item.observed_session_violated,
            )
            for item in truth.dsd_evaluations
        ),
        birthright_assignments=tuple(
            BirthrightAssignmentPredictionV1(
                rule_id=item.rule_id,
                subject_id=item.subject_id,
                assignment_ids=tuple(
                    sorted(assignment_ids[(item.rule_id, item.subject_id)])
                ),
            )
            for item in truth.birthright_eligibility
        ),
    )


def _sod_metrics(
    truth: CompiledEnterpriseDirectoryRbacTruthV1,
    *,
    ssd_predictions: dict[tuple[str, str], SsdPredictionV1],
    dsd_predictions: dict[tuple[str, str], DsdPredictionV1],
) -> tuple[EnterpriseAuthorizationMetricV1, ...]:
    ssd_violations = tuple(item for item in truth.ssd_evaluations if item.violated)
    ssd_nonviolations = tuple(
        item for item in truth.ssd_evaluations if not item.violated
    )
    dsd_rows = truth.dsd_evaluations
    return (
        _metric(
            "ssd",
            "ssd_violation_detection_rate",
            sum(
                (
                    prediction := ssd_predictions.get(
                        (item.constraint_id, item.subject_id)
                    )
                )
                is not None
                and prediction.violated
                for item in ssd_violations
            ),
            len(ssd_violations),
            "canonical subject/constraint SSD violations",
        ),
        _metric(
            "ssd",
            "ssd_violation_false_positive_rate",
            sum(
                (
                    prediction := ssd_predictions.get(
                        (item.constraint_id, item.subject_id)
                    )
                )
                is not None
                and prediction.violated
                for item in ssd_nonviolations
            ),
            len(ssd_nonviolations),
            "canonical subject/constraint SSD nonviolations",
        ),
        _metric(
            "dsd",
            "dsd_constraint_outcome_accuracy",
            sum(
                prediction is not None
                and prediction.request_violated == item.request_violated
                and prediction.observed_session_violated
                == item.observed_session_violated
                for item in dsd_rows
                for prediction in (
                    dsd_predictions.get(
                        (item.activation_request_id, item.constraint_id)
                    ),
                )
            ),
            len(dsd_rows),
            "declared request/session DSD evaluations",
        ),
    )


def _unauthorized_activation_metrics(
    truth: CompiledEnterpriseDirectoryRbacTruthV1,
    *,
    activation_predictions: dict[str, ActivationPredictionV1],
) -> tuple[EnterpriseAuthorizationMetricV1, ...]:
    decision_by_session = {
        item.session_state_id: item.activation_request_id
        for item in truth.activation_decisions
    }
    positives = tuple(
        item for item in truth.observed_sessions if item.unauthorized_activated_role_ids
    )
    negatives = tuple(
        item
        for item in truth.observed_sessions
        if not item.unauthorized_activated_role_ids
    )

    def predicted(item: ObservedSessionTruthV1) -> ActivationPredictionV1 | None:
        return activation_predictions.get(decision_by_session[item.session_state_id])

    return (
        _metric(
            "activation_safety",
            "unauthorized_activation_detection_rate",
            sum(
                (candidate := predicted(item)) is not None
                and candidate.unauthorized_activated_role_ids
                == item.unauthorized_activated_role_ids
                for item in positives
            ),
            len(positives),
            "canonical sessions with unauthorized activated roles",
        ),
        _metric(
            "activation_safety",
            "unauthorized_activation_false_positive_rate",
            sum(
                (candidate := predicted(item)) is not None
                and bool(candidate.unauthorized_activated_role_ids)
                for item in negatives
            ),
            len(negatives),
            "canonical sessions without unauthorized activated roles",
        ),
    )


def _privilege_accumulation_metric(
    truth: CompiledEnterpriseDirectoryRbacTruthV1,
) -> EnterpriseAuthorizationMetricV1:
    by_subject_tick: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for cell in truth.cells:
        if (
            cell.effective_decision is AuthorizationDecision.ALLOW
            and cell.intended_decision is AuthorizationDecision.DENY
        ):
            by_subject_tick[cell.subject_id][cell.tick] += 1
        else:
            by_subject_tick[cell.subject_id][cell.tick] += 0
    eligible = {
        subject_id: ticks
        for subject_id, ticks in by_subject_tick.items()
        if len(ticks) >= 2
    }
    accumulated = 0
    for ticks in eligible.values():
        values = tuple(value for _tick, value in sorted(ticks.items()))
        accumulated += any(later > earlier for earlier, later in pairwise(values))
    return _metric(
        "accumulation",
        "privilege_accumulation_subject_rate",
        accumulated,
        len(eligible),
        "subjects present at two or more declared checkpoints",
    )


def _reject_unknown_prediction_ids(
    truth: CompiledEnterpriseDirectoryRbacTruthV1,
    *,
    cells: set[str],
    roles: set[str],
    activations: set[str],
    ssd: set[tuple[str, str]],
    dsd: set[tuple[str, str]],
    birthright: set[tuple[str, str]],
) -> None:
    known = (
        {item.cell_id for item in truth.cells},
        {item.subject_id for item in truth.authorized_role_sets},
        {item.activation_request_id for item in truth.activation_decisions},
        {(item.constraint_id, item.subject_id) for item in truth.ssd_evaluations},
        {
            (item.activation_request_id, item.constraint_id)
            for item in truth.dsd_evaluations
        },
        {(item.rule_id, item.subject_id) for item in truth.birthright_eligibility},
    )
    if (
        not cells <= known[0]
        or not roles <= known[1]
        or not activations <= known[2]
        or not ssd <= known[3]
        or not dsd <= known[4]
        or not birthright <= known[5]
    ):
        raise ValueError("enterprise prediction references unknown truth rows")


def _metric(
    family: str,
    name: str,
    numerator: int,
    denominator: int,
    denominator_meaning: str,
    *,
    nonempty: bool = False,
) -> EnterpriseAuthorizationMetricV1:
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
        value=(numerator / denominator if denominator else None),
    )


__all__ = [name for name in globals() if name.startswith("Enterprise")]
__all__ += [
    "ActivationPredictionV1",
    "AuthorizedRoleSetPredictionV1",
    "BirthrightAssignmentPredictionV1",
    "DirectoryRbacCellPredictionV1",
    "DsdPredictionV1",
    "SsdPredictionV1",
    "evaluate_enterprise_directory_rbac",
    "perfect_enterprise_directory_rbac_prediction",
]
