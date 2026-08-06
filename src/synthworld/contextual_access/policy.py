"""Closed three-valued policy evaluation for contextual-access v1."""

from __future__ import annotations

from synthworld.contextual_access.models import (
    BusinessJustificationContextV1,
    CaseAssignmentContextV1,
    CaseAssignmentState,
    ContextualAccessRequestV1,
    ContextualDecisionTruthV1,
    ContextualFactV1,
    ContextualPolicyV1,
    ContextualPredicateOutcomeV1,
    ContextualPredicateTruth,
    ContextualPredicateV1,
    ContextualRuleComposition,
    ContextualRuleEffect,
    ContextualRuleOutcomeV1,
    DevicePosture,
    DevicePostureContextV1,
    DevicePostureIsV1,
    HasActiveCaseAssignmentV1,
    HasValidBusinessJustificationV1,
    IsOnCallV1,
    OnCallContextV1,
    OnCallState,
    RiskAtMostV1,
    RiskLevel,
    RiskSignalContextV1,
)
from synthworld.enterprise.rbac.common import AuthorizationDecision

_RISK_ORDER = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
}


def evaluate_contextual_request(
    *,
    active_facts: tuple[ContextualFactV1, ...],
    policies: tuple[ContextualPolicyV1, ...],
    request: ContextualAccessRequestV1,
) -> ContextualDecisionTruthV1:
    """Evaluate public policy intent without consulting any case label."""

    applicable = tuple(
        policy
        for policy in policies
        if request.asset_id in policy.target_handles
        and request.action in policy.actions
    )
    predicate_outcomes: list[ContextualPredicateOutcomeV1] = []
    rule_outcomes: list[ContextualRuleOutcomeV1] = []
    allow_matched = False
    deny_matched = False
    for policy in applicable:
        for rule in policy.rules:
            outcomes = tuple(
                _evaluate_predicate(
                    predicate=predicate,
                    facts=active_facts,
                    request=request,
                )
                for predicate in rule.predicates
            )
            predicate_outcomes.extend(
                ContextualPredicateOutcomeV1(
                    policy_id=policy.policy_id,
                    rule_id=rule.rule_id,
                    predicate_id=predicate.predicate_id,
                    outcome=outcome,
                )
                for predicate, outcome in zip(rule.predicates, outcomes, strict=True)
            )
            outcome = _compose(outcomes, rule.composition)
            matched = outcome is ContextualPredicateTruth.TRUE
            rule_outcomes.append(
                ContextualRuleOutcomeV1(
                    policy_id=policy.policy_id,
                    rule_id=rule.rule_id,
                    effect=rule.effect,
                    outcome=outcome,
                    matched=matched,
                )
            )
            if matched and rule.effect is ContextualRuleEffect.ALLOW:
                allow_matched = True
            if matched and rule.effect is ContextualRuleEffect.DENY:
                deny_matched = True
    decision = (
        AuthorizationDecision.DENY
        if deny_matched or not allow_matched
        else AuthorizationDecision.ALLOW
    )
    return ContextualDecisionTruthV1(
        decision=decision,
        applicable_policy_ids=tuple(item.policy_id for item in applicable),
        predicate_outcomes=tuple(predicate_outcomes),
        rule_outcomes=tuple(rule_outcomes),
        deny_override_conflict=allow_matched and deny_matched,
    )


def _evaluate_predicate(
    *,
    predicate: ContextualPredicateV1,
    facts: tuple[ContextualFactV1, ...],
    request: ContextualAccessRequestV1,
) -> ContextualPredicateTruth:
    if isinstance(predicate, HasActiveCaseAssignmentV1):
        return _boolean(
            any(
                isinstance(fact, CaseAssignmentContextV1)
                and fact.subject_id == request.subject_id
                and fact.asset_id == request.asset_id
                and fact.assignment_state is CaseAssignmentState.ASSIGNED
                for fact in facts
            )
        )
    if isinstance(predicate, IsOnCallV1):
        return _boolean(
            any(
                isinstance(fact, OnCallContextV1)
                and fact.subject_id == request.subject_id
                and fact.duty_scope_id == predicate.duty_scope_id
                and fact.duty_state is OnCallState.ON_CALL
                for fact in facts
            )
        )
    if isinstance(predicate, DevicePostureIsV1):
        if request.device_id is None:
            # Defensive invalid-input semantics. Public projection rejects a missing
            # device whenever this predicate is applicable; the branch remains
            # explicit so direct evaluator callers fail closed as unknown.
            return ContextualPredicateTruth.UNKNOWN
        posture = next(
            (
                fact.posture
                for fact in facts
                if isinstance(fact, DevicePostureContextV1)
                and fact.subject_id == request.subject_id
                and fact.device_id == request.device_id
            ),
            None,
        )
        if posture is None or posture is DevicePosture.UNKNOWN:
            return ContextualPredicateTruth.UNKNOWN
        return _boolean(posture is predicate.required_posture)
    if isinstance(predicate, RiskAtMostV1):
        level = next(
            (
                fact.risk_level
                for fact in facts
                if isinstance(fact, RiskSignalContextV1)
                and fact.subject_id == request.subject_id
                and fact.signal_source_id == predicate.signal_source_id
            ),
            None,
        )
        if level is None or level is RiskLevel.UNKNOWN:
            return ContextualPredicateTruth.UNKNOWN
        return _boolean(_RISK_ORDER[level] <= _RISK_ORDER[predicate.maximum_level])
    if isinstance(predicate, HasValidBusinessJustificationV1):
        return _boolean(
            any(
                isinstance(fact, BusinessJustificationContextV1)
                and fact.subject_id == request.subject_id
                and fact.asset_id == request.asset_id
                and fact.action == request.action
                and fact.justification_kind is predicate.justification_kind
                for fact in facts
            )
        )
    raise TypeError("unsupported contextual predicate")


def _compose(
    values: tuple[ContextualPredicateTruth, ...],
    composition: ContextualRuleComposition,
) -> ContextualPredicateTruth:
    if composition is ContextualRuleComposition.ALL:
        if ContextualPredicateTruth.FALSE in values:
            return ContextualPredicateTruth.FALSE
        if all(item is ContextualPredicateTruth.TRUE for item in values):
            return ContextualPredicateTruth.TRUE
        return ContextualPredicateTruth.UNKNOWN
    if ContextualPredicateTruth.TRUE in values:
        return ContextualPredicateTruth.TRUE
    if all(item is ContextualPredicateTruth.FALSE for item in values):
        return ContextualPredicateTruth.FALSE
    return ContextualPredicateTruth.UNKNOWN


def _boolean(value: bool) -> ContextualPredicateTruth:
    return ContextualPredicateTruth.TRUE if value else ContextualPredicateTruth.FALSE


__all__ = ["evaluate_contextual_request"]
