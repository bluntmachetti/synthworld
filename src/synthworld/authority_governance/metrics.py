"""Independent metrics for authority-change governance reconstruction."""

from __future__ import annotations

from collections.abc import Callable

from synthworld.authority_governance.models import (
    AuthorityGovernanceCaseFindingV1,
    AuthorityGovernanceEvaluatorV1,
    AuthorityGovernanceMetricV1,
    AuthorityGovernancePredictionRowV1,
    AuthorityGovernancePredictionV1,
    AuthorityGovernancePublicV1,
    AuthorityGovernanceReportV1,
    AuthorityGovernanceTruthRowV1,
    GovernanceMetricFamily,
)
from synthworld.authority_governance.replay import (
    AuthorityGovernanceIntegrityError,
    validate_authority_governance_evaluator,
)


class AuthorityGovernanceEvaluationError(ValueError):
    """Raised when a governance prediction cannot be scored."""


def perfect_authority_governance_prediction(
    evaluator: AuthorityGovernanceEvaluatorV1,
) -> AuthorityGovernancePredictionV1:
    """Build the exact prediction used for scorer/schema conformance."""

    return AuthorityGovernancePredictionV1(
        rows=tuple(_prediction_from_truth(item) for item in evaluator.truth)
    )


def evaluate_authority_governance_prediction(
    *,
    public: AuthorityGovernancePublicV1,
    evaluator: AuthorityGovernanceEvaluatorV1,
    prediction: AuthorityGovernancePredictionV1,
) -> AuthorityGovernanceReportV1:
    """Score state, governance, policy, evidence, and enactment separately."""

    try:
        validate_authority_governance_evaluator(public, evaluator)
    except AuthorityGovernanceIntegrityError as error:
        raise AuthorityGovernanceEvaluationError(
            "authority-governance benchmark is invalid"
        ) from error
    truth_ids = tuple(item.authority_change_id for item in evaluator.truth)
    prediction_ids = tuple(item.authority_change_id for item in prediction.rows)
    if prediction_ids != truth_ids:
        raise AuthorityGovernanceEvaluationError(
            "governance prediction inventory differs from evaluator truth"
        )
    predicted = {item.authority_change_id: item for item in prediction.rows}
    pairs = tuple(
        (truth, predicted[truth.authority_change_id]) for truth in evaluator.truth
    )
    findings = tuple(_finding(truth, row) for truth, row in pairs)

    metrics: list[AuthorityGovernanceMetricV1] = []
    dimensions: tuple[
        tuple[
            GovernanceMetricFamily,
            str,
            str,
            Callable[
                [AuthorityGovernanceTruthRowV1, AuthorityGovernancePredictionRowV1],
                bool,
            ],
        ],
        ...,
    ] = (
        (
            GovernanceMetricFamily.STATE,
            "after_state_accuracy",
            "authority changes with canonical after-state truth",
            lambda truth, row: row.canonical_after_state == truth.canonical_after_state,
        ),
        (
            GovernanceMetricFamily.STATE,
            "before_state_accuracy",
            "authority changes with canonical before-state truth",
            lambda truth, row: (
                row.canonical_before_state == truth.canonical_before_state
            ),
        ),
        (
            GovernanceMetricFamily.STATE,
            "change_type_accuracy",
            "authority changes",
            lambda truth, row: row.change_type is truth.change_type,
        ),
        (
            GovernanceMetricFamily.STATE,
            "effective_tick_accuracy",
            "authority changes with a canonical effective tick",
            lambda truth, row: row.effective_tick == truth.expected_effective_tick,
        ),
        (
            GovernanceMetricFamily.STATE,
            "supersession_link_accuracy",
            "authority changes",
            lambda truth, row: (
                row.superseded_authority_change_id
                == truth.superseded_authority_change_id
            ),
        ),
        (
            GovernanceMetricFamily.GOVERNANCE_AUTHORITY,
            "accountable_owner_chain_integrity",
            "authority changes with accountable-owner truth",
            lambda truth, row: (
                row.accountable_owner_chain == truth.canonical_accountable_owner_chain
            ),
        ),
        (
            GovernanceMetricFamily.GOVERNANCE_AUTHORITY,
            "approval_chain_integrity",
            "authority changes with approval-chain truth",
            lambda truth, row: row.approval_chain == truth.canonical_approval_chain,
        ),
        (
            GovernanceMetricFamily.GOVERNANCE_AUTHORITY,
            "approver_authority_at_decision_accuracy",
            "authority changes with approver-authority truth",
            lambda truth, row: (
                row.approver_authorised_at_decision
                is truth.approver_authorised_at_decision
            ),
        ),
        (
            GovernanceMetricFamily.GOVERNANCE_AUTHORITY,
            "controlling_decision_accuracy",
            "authority changes with deterministic decision precedence",
            lambda truth, row: (
                row.controlling_decision_id == truth.controlling_decision_id
                and row.decision_outcome is truth.expected_decision_outcome
            ),
        ),
        (
            GovernanceMetricFamily.GOVERNANCE_AUTHORITY,
            "governance_authorisation_accuracy",
            "authority changes with governance-authorisation truth",
            lambda truth, row: (
                row.governance_decision_authorised
                is truth.governance_decision_authorised
            ),
        ),
        (
            GovernanceMetricFamily.GOVERNANCE_AUTHORITY,
            "requester_identity_accuracy",
            "authority changes with canonical requester truth",
            lambda truth, row: (
                row.requester_principal_id == truth.canonical_requester_principal_id
            ),
        ),
        (
            GovernanceMetricFamily.POLICY_RATIONALE,
            "exception_accuracy",
            "authority changes with exception-or-no-exception truth",
            lambda truth, row: row.exception_id == truth.expected_exception_id,
        ),
        (
            GovernanceMetricFamily.POLICY_RATIONALE,
            "policy_control_accuracy",
            "authority changes with applicable rule and control truth",
            lambda truth, row: (
                row.policy_rule_ids == truth.applicable_policy_rule_ids
                and row.control_ids == truth.applicable_control_ids
            ),
        ),
        (
            GovernanceMetricFamily.POLICY_RATIONALE,
            "policy_version_accuracy",
            "authority changes with decision-time policy truth",
            lambda truth, row: (
                row.policy_version_id == truth.applicable_policy_version_id
            ),
        ),
        (
            GovernanceMetricFamily.POLICY_RATIONALE,
            "structured_rationale_accuracy",
            "authority changes with structured-rationale truth",
            lambda truth, row: row.rationale_code == truth.expected_rationale_code,
        ),
        (
            GovernanceMetricFamily.EVIDENCE_OBSERVABILITY,
            "audit_reconstructability_accuracy",
            "authority changes audited at the declared audit tick",
            lambda truth, row: row.audit_reconstructable is truth.audit_reconstructable,
        ),
        (
            GovernanceMetricFamily.EVIDENCE_OBSERVABILITY,
            "decision_evidence_exact_match",
            "authority changes with required decision-evidence truth",
            lambda truth, row: (
                row.decision_evidence_refs == truth.required_decision_evidence_refs
            ),
        ),
        (
            GovernanceMetricFamily.ENACTMENT,
            "approval_to_enactment_consistency_accuracy",
            "authority changes with enactment-consistency truth",
            lambda truth, row: row.enactment_consistent is truth.enactment_consistent,
        ),
    )
    for family, name, meaning, check in dimensions:
        numerator = sum(check(truth, row) for truth, row in pairs)
        metrics.append(_metric(family, name, numerator, len(pairs), meaning))

    evidence_true = sum(
        len(
            set(truth.required_decision_evidence_refs) & set(row.decision_evidence_refs)
        )
        for truth, row in pairs
    )
    evidence_required = sum(
        len(truth.required_decision_evidence_refs) for truth, _ in pairs
    )
    evidence_submitted = sum(len(row.decision_evidence_refs) for _, row in pairs)
    metrics.extend(
        (
            _metric(
                GovernanceMetricFamily.EVIDENCE_OBSERVABILITY,
                "decision_evidence_precision",
                evidence_true,
                evidence_submitted,
                "submitted decision-evidence references",
            ),
            _metric(
                GovernanceMetricFamily.EVIDENCE_OBSERVABILITY,
                "decision_evidence_recall",
                evidence_true,
                evidence_required,
                "required decision-evidence references",
            ),
        )
    )
    return AuthorityGovernanceReportV1(
        findings=findings,
        metrics=tuple(sorted(metrics, key=lambda item: (item.family.value, item.name))),
    )


def _prediction_from_truth(
    truth: AuthorityGovernanceTruthRowV1,
) -> AuthorityGovernancePredictionRowV1:
    return AuthorityGovernancePredictionRowV1(
        authority_change_id=truth.authority_change_id,
        change_type=truth.change_type,
        canonical_before_state=truth.canonical_before_state,
        canonical_after_state=truth.canonical_after_state,
        governance_decision_authorised=truth.governance_decision_authorised,
        approver_authorised_at_decision=truth.approver_authorised_at_decision,
        requester_principal_id=truth.canonical_requester_principal_id,
        approval_chain=truth.canonical_approval_chain,
        accountable_owner_chain=truth.canonical_accountable_owner_chain,
        policy_version_id=truth.applicable_policy_version_id,
        policy_rule_ids=truth.applicable_policy_rule_ids,
        control_ids=truth.applicable_control_ids,
        rationale_code=truth.expected_rationale_code,
        exception_id=truth.expected_exception_id,
        decision_evidence_refs=truth.required_decision_evidence_refs,
        controlling_decision_id=truth.controlling_decision_id,
        decision_outcome=truth.expected_decision_outcome,
        effective_tick=truth.expected_effective_tick,
        superseded_authority_change_id=truth.superseded_authority_change_id,
        enactment_consistent=truth.enactment_consistent,
        audit_reconstructable=truth.audit_reconstructable,
    )


def _finding(
    truth: AuthorityGovernanceTruthRowV1,
    row: AuthorityGovernancePredictionRowV1,
) -> AuthorityGovernanceCaseFindingV1:
    return AuthorityGovernanceCaseFindingV1(
        authority_change_id=truth.authority_change_id,
        state_correct=(
            row.change_type is truth.change_type
            and row.canonical_before_state == truth.canonical_before_state
            and row.canonical_after_state == truth.canonical_after_state
            and row.effective_tick == truth.expected_effective_tick
            and row.superseded_authority_change_id
            == truth.superseded_authority_change_id
        ),
        governance_authority_correct=(
            row.governance_decision_authorised is truth.governance_decision_authorised
            and row.approver_authorised_at_decision
            is truth.approver_authorised_at_decision
            and row.requester_principal_id == truth.canonical_requester_principal_id
            and row.approval_chain == truth.canonical_approval_chain
            and row.accountable_owner_chain == truth.canonical_accountable_owner_chain
            and row.controlling_decision_id == truth.controlling_decision_id
            and row.decision_outcome is truth.expected_decision_outcome
        ),
        policy_rationale_correct=(
            row.policy_version_id == truth.applicable_policy_version_id
            and row.policy_rule_ids == truth.applicable_policy_rule_ids
            and row.control_ids == truth.applicable_control_ids
            and row.rationale_code == truth.expected_rationale_code
            and row.exception_id == truth.expected_exception_id
        ),
        evidence_observability_correct=(
            row.decision_evidence_refs == truth.required_decision_evidence_refs
            and row.audit_reconstructable is truth.audit_reconstructable
        ),
        enactment_correct=(row.enactment_consistent is truth.enactment_consistent),
    )


def _metric(
    family: GovernanceMetricFamily,
    name: str,
    numerator: int,
    denominator: int,
    denominator_meaning: str,
) -> AuthorityGovernanceMetricV1:
    return AuthorityGovernanceMetricV1(
        family=family,
        name=name,
        value=numerator / denominator,
        numerator=numerator,
        denominator=denominator,
        support=denominator,
        denominator_meaning=denominator_meaning,
    )


__all__ = [
    "AuthorityGovernanceEvaluationError",
    "evaluate_authority_governance_prediction",
    "perfect_authority_governance_prediction",
]
