"""Independent scoring for adversarial enterprise authorization cases."""

from __future__ import annotations

from collections.abc import Callable

from synthworld.enterprise.authorization.adversarial.common import (
    AdversarialAuthorizationMechanism,
)
from synthworld.enterprise.authorization.adversarial.models import (
    AdversarialAttemptPredictionV1,
    AdversarialAttemptTruthV1,
    AdversarialCohortSummaryV1,
    AdversarialCounterfactualPairTruthV1,
    EnterpriseAdversarialAuthorizationEvaluatorV1,
    EnterpriseAdversarialAuthorizationMetricsV1,
    EnterpriseAdversarialAuthorizationPredictionV1,
    EnterpriseAdversarialAuthorizationPublicV1,
)
from synthworld.enterprise.authorization.adversarial.reference import (
    validate_adversarial_authorization_artifacts,
)
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.rbac.common import MetricEmptyBehaviour
from synthworld.enterprise.rbac.metrics import EnterpriseAuthorizationMetricV1


def evaluate_enterprise_adversarial_authorization(
    *,
    public: EnterpriseAdversarialAuthorizationPublicV1,
    evaluator: EnterpriseAdversarialAuthorizationEvaluatorV1,
    prediction: EnterpriseAdversarialAuthorizationPredictionV1,
) -> EnterpriseAdversarialAuthorizationMetricsV1:
    """Score exact attempt coverage without combining independent metrics."""

    validate_adversarial_authorization_artifacts(public, evaluator)
    if prediction.public_digest != evaluator.public_digest:
        raise ValueError("adversarial_prediction_public_digest_mismatch")
    prediction_by_attempt = {item.attempt_id: item for item in prediction.attempts}
    truth_by_attempt = {item.attempt_id: item for item in evaluator.cases}
    if set(prediction_by_attempt) != set(truth_by_attempt):
        raise ValueError("adversarial_prediction_attempt_inventory_mismatch")

    cohorts = tuple(
        AdversarialCohortSummaryV1(
            mechanism=mechanism,
            total_scenarios=sum(
                item.mechanism is mechanism for item in evaluator.cases
            ),
            discriminating_denominator=sum(
                item.mechanism is mechanism
                and item.expected_decision is not item.mechanism_ignored_decision
                for item in evaluator.cases
            ),
        )
        for mechanism in AdversarialAuthorizationMechanism
    )
    metrics = [
        _attempt_accuracy(
            family="decision",
            name="final_decision_accuracy",
            truth=evaluator.cases,
            predictions=prediction_by_attempt,
            matches=lambda expected, observed: (
                observed.decision is expected.expected_decision
            ),
            denominator_meaning="all adversarial action attempts",
        )
    ]
    metrics.extend(
        _attempt_accuracy(
            family="mechanism",
            name=f"{mechanism.value}_decision_accuracy",
            truth=tuple(
                item
                for item in evaluator.cases
                if item.mechanism is mechanism
                and item.expected_decision is not item.mechanism_ignored_decision
            ),
            predictions=prediction_by_attempt,
            matches=lambda expected, observed: (
                observed.decision is expected.expected_decision
            ),
            denominator_meaning=(
                f"{mechanism.value} cases whose verdict changes when that "
                "mechanism is ignored"
            ),
        )
        for mechanism in AdversarialAuthorizationMechanism
    )
    binding_truth = tuple(
        item
        for item in evaluator.cases
        if item.mechanism is AdversarialAuthorizationMechanism.BINDING
    )
    metrics.append(
        _attempt_accuracy(
            family="binding",
            name="resolved_principal_accuracy",
            truth=binding_truth,
            predictions=prediction_by_attempt,
            matches=lambda expected, observed: (
                observed.resolved_principal_id == expected.resolved_principal_id
            ),
            denominator_meaning="all binding counterfactual attempts",
        )
    )
    metrics.append(
        _attempt_accuracy(
            family="binding",
            name="binding_status_accuracy",
            truth=binding_truth,
            predictions=prediction_by_attempt,
            matches=lambda expected, observed: (
                observed.binding_status is expected.binding_status
            ),
            denominator_meaning="all binding counterfactual attempts",
        )
    )
    temporal_pairs = tuple(
        item
        for item in evaluator.pairs
        if item.mechanism is AdversarialAuthorizationMechanism.TIME
        and item.expected_transition
    )
    metrics.append(
        _pair_accuracy(
            temporal_pairs,
            truth_by_attempt,
            prediction_by_attempt,
        )
    )
    metrics.append(
        _attempt_accuracy(
            family="robustness",
            name="identifier_independent_decision_accuracy",
            truth=tuple(item for item in evaluator.cases if item.identifier_probe),
            predictions=prediction_by_attempt,
            matches=lambda expected, observed: (
                observed.decision is expected.expected_decision
            ),
            denominator_meaning=(
                "hidden identifier/order probes across single-factor pairs"
            ),
        )
    )
    return EnterpriseAdversarialAuthorizationMetricsV1(
        public_digest=evaluator.public_digest,
        evaluator_digest=synthetic_digest(canonical_json_bytes(evaluator)),
        prediction_digest=synthetic_digest(canonical_json_bytes(prediction)),
        cohorts=cohorts,
        metrics=tuple(metrics),
    )


def perfect_enterprise_adversarial_authorization_prediction(
    evaluator: EnterpriseAdversarialAuthorizationEvaluatorV1,
) -> EnterpriseAdversarialAuthorizationPredictionV1:
    """Project evaluator truth into the vendor-neutral prediction contract."""

    return EnterpriseAdversarialAuthorizationPredictionV1(
        public_digest=evaluator.public_digest,
        attempts=tuple(
            AdversarialAttemptPredictionV1(
                attempt_id=item.attempt_id,
                resolved_principal_id=item.resolved_principal_id,
                binding_status=item.binding_status,
                decision=item.expected_decision,
            )
            for item in evaluator.cases
        ),
    )


def _attempt_accuracy(
    *,
    family: str,
    name: str,
    truth: tuple[AdversarialAttemptTruthV1, ...],
    predictions: dict[str, AdversarialAttemptPredictionV1],
    matches: Callable[
        [AdversarialAttemptTruthV1, AdversarialAttemptPredictionV1], bool
    ],
    denominator_meaning: str,
) -> EnterpriseAuthorizationMetricV1:
    denominator = len(truth)
    numerator = sum(matches(item, predictions[item.attempt_id]) for item in truth)
    return EnterpriseAuthorizationMetricV1(
        family=family,
        name=name,
        numerator=numerator,
        denominator=denominator,
        support=denominator,
        denominator_meaning=denominator_meaning,
        empty_behaviour=MetricEmptyBehaviour.NULL_IF_EMPTY,
        value=numerator / denominator if denominator else None,
    )


def _pair_accuracy(
    pairs: tuple[AdversarialCounterfactualPairTruthV1, ...],
    truth: dict[str, AdversarialAttemptTruthV1],
    predictions: dict[str, AdversarialAttemptPredictionV1],
) -> EnterpriseAuthorizationMetricV1:
    denominator = len(pairs)
    numerator = sum(
        predictions[item.from_attempt_id].decision
        is truth[item.from_attempt_id].expected_decision
        and predictions[item.to_attempt_id].decision
        is truth[item.to_attempt_id].expected_decision
        and predictions[item.from_attempt_id].decision
        is not predictions[item.to_attempt_id].decision
        for item in pairs
    )
    return EnterpriseAuthorizationMetricV1(
        family="temporal",
        name="expected_transition_accuracy",
        numerator=numerator,
        denominator=denominator,
        support=denominator,
        denominator_meaning=(
            "scheduled temporal pairs explicitly expected to change authority"
        ),
        empty_behaviour=MetricEmptyBehaviour.NULL_IF_EMPTY,
        value=numerator / denominator if denominator else None,
    )


__all__ = [
    "evaluate_enterprise_adversarial_authorization",
    "perfect_enterprise_adversarial_authorization_prediction",
]
