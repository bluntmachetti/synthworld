"""Independent, denominator-bearing metrics for the #7 smoke pack."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Protocol

from synthworld.enterprise.abac.metrics import (
    evaluate_enterprise_abac,
    perfect_enterprise_abac_prediction,
)
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.identity_fabric.models import (
    EnterpriseIdentityFabricEvaluatorArtifactsV1,
    EnterpriseIdentityFabricMetricsV1,
    EnterpriseIdentityFabricPredictionV1,
    IdentityFabricAccessPredictionV1,
    IdentityFabricAccessTruthV1,
    IdentityFabricAccountPredictionV1,
    IdentityFabricAccountTruthV1,
    IdentityFabricAccumulationPredictionV1,
    IdentityFabricAccumulationTruthV1,
    IdentityFabricCheckpointEvaluatorArtifactV1,
    IdentityFabricCheckpointMetricsV1,
    IdentityFabricCheckpointPredictionV1,
    IdentityFabricCheckpointTruthV1,
    IdentityFabricMembershipPredictionV1,
    IdentityFabricRolePredictionV1,
    IdentityFabricRoleTruthV1,
)
from synthworld.enterprise.rbac.common import MetricEmptyBehaviour
from synthworld.enterprise.rbac.metrics import (
    EnterpriseAuthorizationMetricV1,
    evaluate_enterprise_directory_rbac,
    perfect_enterprise_directory_rbac_prediction,
)
from synthworld.enterprise.rebac.metrics import (
    evaluate_enterprise_rebac,
    perfect_enterprise_rebac_prediction,
)


class _QueryIdRecord(Protocol):
    query_id: str


def evaluate_enterprise_identity_fabric(
    *,
    artifacts: EnterpriseIdentityFabricEvaluatorArtifactsV1,
    predictions: EnterpriseIdentityFabricPredictionV1,
) -> EnterpriseIdentityFabricMetricsV1:
    """Score each mechanism and governance dimension without an aggregate."""

    truth = artifacts.truth
    if predictions.benchmark_digest != truth.benchmark_digest:
        raise ValueError("identity_fabric_prediction_benchmark_digest_mismatch")
    truth_by_checkpoint = {item.checkpoint_id: item for item in truth.checkpoints}
    artifact_by_checkpoint = {
        item.checkpoint_id: item for item in artifacts.checkpoints
    }
    prediction_by_checkpoint = {
        item.checkpoint_id: item for item in predictions.checkpoints
    }
    if not set(prediction_by_checkpoint) <= set(truth_by_checkpoint):
        raise ValueError("unknown_identity_fabric_prediction_checkpoint_id")

    checkpoint_metrics: list[IdentityFabricCheckpointMetricsV1] = []
    for checkpoint_id, checkpoint_truth in truth_by_checkpoint.items():
        component_truth = artifact_by_checkpoint[checkpoint_id]
        checkpoint_prediction = prediction_by_checkpoint.get(
            checkpoint_id,
            IdentityFabricCheckpointPredictionV1(checkpoint_id=checkpoint_id),
        )
        _reject_unknown_checkpoint_query_ids(checkpoint_truth, checkpoint_prediction)
        checkpoint_metrics.append(
            IdentityFabricCheckpointMetricsV1(
                checkpoint_id=checkpoint_id,
                directory_rbac=evaluate_enterprise_directory_rbac(
                    truth=component_truth.directory_rbac_truth,
                    predictions=checkpoint_prediction.directory_rbac,
                ),
                abac=evaluate_enterprise_abac(
                    truth=component_truth.abac_truth,
                    predictions=checkpoint_prediction.abac,
                ),
                rebac=evaluate_enterprise_rebac(
                    truth=component_truth.rebac_truth,
                    predictions=checkpoint_prediction.rebac,
                ),
                identity_fabric_metrics=_checkpoint_metrics(
                    checkpoint_truth, checkpoint_prediction
                ),
            )
        )

    predicted_accumulation = {item.query_id: item for item in predictions.accumulation}
    known_accumulation_ids = {item.query_id for item in truth.accumulation}
    known_cell_ids = {
        item.cell_id
        for checkpoint in artifacts.checkpoints
        for item in checkpoint.directory_rbac_truth.cells
    }
    if not set(predicted_accumulation) <= known_accumulation_ids or any(
        not set(item.accumulated_cell_ids) <= known_cell_ids
        for item in predicted_accumulation.values()
    ):
        raise ValueError("unknown_identity_fabric_accumulation_prediction_id")
    return EnterpriseIdentityFabricMetricsV1(
        benchmark_digest=truth.benchmark_digest,
        truth_digest=synthetic_digest(canonical_json_bytes(truth)),
        checkpoints=tuple(checkpoint_metrics),
        cross_checkpoint_metrics=_accumulation_metrics(
            truth.accumulation, predicted_accumulation
        ),
    )


def perfect_enterprise_identity_fabric_prediction(
    artifacts: EnterpriseIdentityFabricEvaluatorArtifactsV1,
) -> EnterpriseIdentityFabricPredictionV1:
    """Project evaluator truth into the vendor-neutral prediction contract."""

    component_by_checkpoint = {
        item.checkpoint_id: item for item in artifacts.checkpoints
    }
    return EnterpriseIdentityFabricPredictionV1(
        benchmark_digest=artifacts.truth.benchmark_digest,
        checkpoints=tuple(
            _perfect_checkpoint_prediction(
                checkpoint,
                component_by_checkpoint[checkpoint.checkpoint_id],
            )
            for checkpoint in artifacts.truth.checkpoints
        ),
        accumulation=tuple(
            IdentityFabricAccumulationPredictionV1(
                query_id=item.query_id,
                accumulated_cell_ids=item.accumulated_cell_ids,
            )
            for item in artifacts.truth.accumulation
        ),
    )


def _perfect_checkpoint_prediction(
    checkpoint: IdentityFabricCheckpointTruthV1,
    component: IdentityFabricCheckpointEvaluatorArtifactV1,
) -> IdentityFabricCheckpointPredictionV1:
    return IdentityFabricCheckpointPredictionV1(
        checkpoint_id=checkpoint.checkpoint_id,
        directory_rbac=perfect_enterprise_directory_rbac_prediction(
            component.directory_rbac_truth
        ),
        abac=perfect_enterprise_abac_prediction(component.abac_truth),
        rebac=perfect_enterprise_rebac_prediction(component.rebac_truth),
        membership=tuple(
            IdentityFabricMembershipPredictionV1(
                query_id=item.query_id,
                direct_member=item.direct_member,
                effective_member=item.effective_member,
            )
            for item in checkpoint.membership
        ),
        roles=tuple(
            IdentityFabricRolePredictionV1(
                query_id=item.query_id,
                direct_role_assignment=item.direct_role_assignment,
                group_derived_role=item.group_derived_role,
                hierarchy_inherited_role=item.hierarchy_inherited_role,
                effective_role=item.effective_role,
            )
            for item in checkpoint.roles
        ),
        accounts=tuple(
            IdentityFabricAccountPredictionV1(
                query_id=item.query_id,
                canonical_principal_id=item.canonical_principal_id,
                binding_status=item.binding_status,
                lifecycle_status=item.lifecycle_status,
                orphaned=item.orphaned,
                inactive=item.inactive,
            )
            for item in checkpoint.accounts
        ),
        access=tuple(
            IdentityFabricAccessPredictionV1(
                query_id=item.query_id,
                direct_entitlement=item.direct_entitlement,
                role_entitlement=item.role_entitlement,
                birthright_access=item.birthright_access,
                approved_exception=item.approved_exception,
                intended_decision=item.intended_decision,
                effective_decision=item.effective_decision,
                final_decision=item.final_decision,
                policy_conflict=item.policy_conflict,
                redundant_derivation=item.redundant_derivation,
                outside_birthright=item.outside_birthright,
                outside_intent=item.outside_intent,
            )
            for item in checkpoint.access
        ),
    )


def _checkpoint_metrics(
    truth: IdentityFabricCheckpointTruthV1,
    prediction: IdentityFabricCheckpointPredictionV1,
) -> tuple[EnterpriseAuthorizationMetricV1, ...]:
    memberships = {item.query_id: item for item in prediction.membership}
    roles = {item.query_id: item for item in prediction.roles}
    accounts = {item.query_id: item for item in prediction.accounts}
    access = {item.query_id: item for item in prediction.access}
    metrics: list[EnterpriseAuthorizationMetricV1] = []
    metrics.extend(
        (
            _accuracy(
                "membership",
                "direct_membership_accuracy",
                truth.membership,
                memberships,
                lambda expected, observed: (
                    observed.direct_member == expected.direct_member
                ),
                "all subject/group membership queries at this checkpoint",
            ),
            _accuracy(
                "membership",
                "effective_membership_accuracy",
                truth.membership,
                memberships,
                lambda expected, observed: (
                    observed.effective_member == expected.effective_member
                ),
                "all subject/group membership queries at this checkpoint",
            ),
        )
    )
    nested_truth = tuple(
        item
        for item in truth.membership
        if item.effective_member and not item.direct_member
    )
    metrics.extend(
        _detection_metrics(
            family="membership",
            stem="nested_membership",
            truth_rows=nested_truth,
            all_predictions=memberships.values(),
            truth_id=lambda item: item.query_id,
            predicted_id=lambda item: item.query_id,
            predicted_positive=lambda item: (
                item.effective_member and not item.direct_member
            ),
            denominator_meaning="effective nested-only membership queries",
            precision_meaning="predicted effective membership queries",
        )
    )
    role_specs: tuple[
        tuple[
            str,
            Callable[[IdentityFabricRoleTruthV1], bool],
            Callable[[IdentityFabricRolePredictionV1], bool],
        ],
        ...,
    ] = (
        (
            "direct_role_assignment_accuracy",
            lambda item: item.direct_role_assignment,
            lambda item: item.direct_role_assignment,
        ),
        (
            "group_derived_role_accuracy",
            lambda item: item.group_derived_role,
            lambda item: item.group_derived_role,
        ),
        (
            "hierarchy_inherited_role_accuracy",
            lambda item: item.hierarchy_inherited_role,
            lambda item: item.hierarchy_inherited_role,
        ),
        (
            "effective_role_accuracy",
            lambda item: item.effective_role,
            lambda item: item.effective_role,
        ),
    )
    metrics.extend(
        _accuracy(
            "role_resolution",
            name,
            truth.roles,
            roles,
            _value_matcher(truth_value, prediction_value),
            "all subject/role resolution queries at this checkpoint",
        )
        for name, truth_value, prediction_value in role_specs
    )
    account_specs: tuple[
        tuple[
            str,
            Callable[[IdentityFabricAccountTruthV1], object],
            Callable[[IdentityFabricAccountPredictionV1], object],
        ],
        ...,
    ] = (
        (
            "canonical_account_owner_accuracy",
            lambda item: item.canonical_principal_id,
            lambda item: item.canonical_principal_id,
        ),
        (
            "account_binding_status_accuracy",
            lambda item: item.binding_status,
            lambda item: item.binding_status,
        ),
        (
            "account_lifecycle_status_accuracy",
            lambda item: item.lifecycle_status,
            lambda item: item.lifecycle_status,
        ),
        (
            "orphan_account_accuracy",
            lambda item: item.orphaned,
            lambda item: item.orphaned,
        ),
        (
            "inactive_account_accuracy",
            lambda item: item.inactive,
            lambda item: item.inactive,
        ),
    )
    metrics.extend(
        _accuracy(
            "account",
            name,
            truth.accounts,
            accounts,
            _value_matcher(truth_value, prediction_value),
            "all account/tick observation queries at this checkpoint",
        )
        for name, truth_value, prediction_value in account_specs
    )
    account_detection_specs: tuple[
        tuple[
            str,
            Callable[[IdentityFabricAccountTruthV1], bool],
            Callable[[IdentityFabricAccountPredictionV1], bool],
        ],
        ...,
    ] = (
        (
            "orphan_account",
            lambda item: item.orphaned,
            lambda item: item.orphaned,
        ),
        (
            "inactive_account",
            lambda item: item.inactive,
            lambda item: item.inactive,
        ),
    )
    for stem, truth_positive, predicted_positive in account_detection_specs:
        metrics.extend(
            _detection_metrics(
                family="account",
                stem=stem,
                truth_rows=tuple(
                    item for item in truth.accounts if truth_positive(item)
                ),
                all_predictions=accounts.values(),
                truth_id=lambda item: item.query_id,
                predicted_id=lambda item: item.query_id,
                predicted_positive=predicted_positive,
                denominator_meaning=f"canonical {stem.replace('_', ' ')} queries",
                precision_meaning=f"predicted {stem.replace('_', ' ')} queries",
            )
        )
    access_specs: tuple[
        tuple[
            str,
            str,
            Callable[[IdentityFabricAccessTruthV1], object],
            Callable[[IdentityFabricAccessPredictionV1], object],
        ],
        ...,
    ] = (
        (
            "entitlement",
            "direct_entitlement_accuracy",
            lambda item: item.direct_entitlement,
            lambda item: item.direct_entitlement,
        ),
        (
            "entitlement",
            "role_entitlement_accuracy",
            lambda item: item.role_entitlement,
            lambda item: item.role_entitlement,
        ),
        (
            "birthright",
            "birthright_access_accuracy",
            lambda item: item.birthright_access,
            lambda item: item.birthright_access,
        ),
        (
            "approved_exception",
            "approved_exception_accuracy",
            lambda item: item.approved_exception,
            lambda item: item.approved_exception,
        ),
        (
            "intent",
            "intended_access_accuracy",
            lambda item: item.intended_decision,
            lambda item: item.intended_decision,
        ),
        (
            "effective_access",
            "effective_access_accuracy",
            lambda item: item.effective_decision,
            lambda item: item.effective_decision,
        ),
        (
            "final_access",
            "final_access_accuracy",
            lambda item: item.final_decision,
            lambda item: item.final_decision,
        ),
        (
            "conflict",
            "policy_conflict_accuracy",
            lambda item: item.policy_conflict,
            lambda item: item.policy_conflict,
        ),
        (
            "redundancy",
            "redundant_derivation_accuracy",
            lambda item: item.redundant_derivation,
            lambda item: item.redundant_derivation,
        ),
        (
            "birthright_breadth",
            "outside_birthright_accuracy",
            lambda item: item.outside_birthright,
            lambda item: item.outside_birthright,
        ),
        (
            "sprawl",
            "outside_intent_accuracy",
            lambda item: item.outside_intent,
            lambda item: item.outside_intent,
        ),
    )
    metrics.extend(
        _accuracy(
            family,
            name,
            truth.access,
            access,
            _value_matcher(truth_value, prediction_value),
            "all frozen access-cell queries at this checkpoint",
        )
        for family, name, truth_value, prediction_value in access_specs
    )
    for family, stem, truth_positive, predicted_positive in (
        (
            "redundancy",
            "redundant_derivation",
            lambda item: item.redundant_derivation,
            lambda item: item.redundant_derivation,
        ),
        (
            "birthright_breadth",
            "outside_birthright",
            lambda item: item.outside_birthright,
            lambda item: item.outside_birthright,
        ),
        (
            "sprawl",
            "outside_intent",
            lambda item: item.outside_intent,
            lambda item: item.outside_intent,
        ),
    ):
        metrics.extend(
            _detection_metrics(
                family=family,
                stem=stem,
                truth_rows=tuple(item for item in truth.access if truth_positive(item)),
                all_predictions=access.values(),
                truth_id=lambda item: item.query_id,
                predicted_id=lambda item: item.query_id,
                predicted_positive=predicted_positive,
                denominator_meaning=f"canonical {stem.replace('_', ' ')} cells",
                precision_meaning=f"predicted {stem.replace('_', ' ')} cells",
            )
        )
    return tuple(metrics)


def _accumulation_metrics(
    truth: tuple[IdentityFabricAccumulationTruthV1, ...],
    predictions: dict[str, IdentityFabricAccumulationPredictionV1],
) -> tuple[EnterpriseAuthorizationMetricV1, ...]:
    exact = sum(
        prediction is not None
        and prediction.accumulated_cell_ids == item.accumulated_cell_ids
        for item in truth
        for prediction in (predictions.get(item.query_id),)
    )
    expected_pairs = {
        (item.query_id, cell_id)
        for item in truth
        for cell_id in item.accumulated_cell_ids
    }
    predicted_pairs = {
        (item.query_id, cell_id)
        for item in predictions.values()
        for cell_id in item.accumulated_cell_ids
    }
    return (
        _metric(
            "accumulation",
            "privilege_accumulation_exact_match_rate",
            exact,
            len(truth),
            "all subject/adjacent-checkpoint accumulation queries",
            nonempty=True,
        ),
        _metric(
            "accumulation",
            "privilege_accumulation_detection_recall",
            len(expected_pairs & predicted_pairs),
            len(expected_pairs),
            "canonical newly accumulated outside-intent access cells",
        ),
        _metric(
            "accumulation",
            "privilege_accumulation_detection_precision",
            len(expected_pairs & predicted_pairs),
            len(predicted_pairs),
            "predicted newly accumulated outside-intent access cells",
        ),
    )


def _accuracy[TruthT: _QueryIdRecord, PredictionT](
    family: str,
    name: str,
    truth: tuple[TruthT, ...],
    predictions: dict[str, PredictionT],
    matches: Callable[[TruthT, PredictionT], bool],
    denominator_meaning: str,
) -> EnterpriseAuthorizationMetricV1:
    correct = sum(
        prediction is not None and matches(item, prediction)
        for item in truth
        for prediction in (predictions.get(item.query_id),)
    )
    return _metric(
        family,
        name,
        correct,
        len(truth),
        denominator_meaning,
        nonempty=True,
    )


def _value_matcher[TruthT, PredictionT, ValueT](
    truth_value: Callable[[TruthT], ValueT],
    prediction_value: Callable[[PredictionT], ValueT],
) -> Callable[[TruthT, PredictionT], bool]:
    return lambda expected, observed: (
        prediction_value(observed) == truth_value(expected)
    )


def _detection_metrics[TruthT, PredictionT](
    *,
    family: str,
    stem: str,
    truth_rows: tuple[TruthT, ...],
    all_predictions: Iterable[PredictionT],
    truth_id: Callable[[TruthT], str],
    predicted_id: Callable[[PredictionT], str],
    predicted_positive: Callable[[PredictionT], bool],
    denominator_meaning: str,
    precision_meaning: str,
) -> tuple[EnterpriseAuthorizationMetricV1, ...]:
    truth_ids = {truth_id(item) for item in truth_rows}
    positive_prediction_ids = {
        predicted_id(item) for item in all_predictions if predicted_positive(item)
    }
    true_positives = len(truth_ids & positive_prediction_ids)
    return (
        _metric(
            family,
            f"{stem}_detection_recall",
            true_positives,
            len(truth_ids),
            denominator_meaning,
        ),
        _metric(
            family,
            f"{stem}_detection_precision",
            true_positives,
            len(positive_prediction_ids),
            precision_meaning,
        ),
    )


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
        value=numerator / denominator if denominator else None,
    )


def _reject_unknown_checkpoint_query_ids(
    truth: IdentityFabricCheckpointTruthV1,
    prediction: IdentityFabricCheckpointPredictionV1,
) -> None:
    observed = (
        {item.query_id for item in prediction.membership},
        {item.query_id for item in prediction.roles},
        {item.query_id for item in prediction.accounts},
        {item.query_id for item in prediction.access},
    )
    expected = (
        {item.query_id for item in truth.membership},
        {item.query_id for item in truth.roles},
        {item.query_id for item in truth.accounts},
        {item.query_id for item in truth.access},
    )
    if any(
        not candidate <= known
        for candidate, known in zip(observed, expected, strict=True)
    ):
        raise ValueError("unknown_identity_fabric_prediction_query_id")


__all__ = [
    "evaluate_enterprise_identity_fabric",
    "perfect_enterprise_identity_fabric_prediction",
]
