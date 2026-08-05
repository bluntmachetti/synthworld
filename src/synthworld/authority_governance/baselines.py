"""Deliberately weak public-only authority-governance baselines."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

from synthworld.authority_governance.models import (
    AuthorityGovernancePredictionRowV1,
    AuthorityGovernancePredictionV1,
    AuthorityGovernancePublicV1,
    GovernanceAuditEventV1,
    GovernanceDecisionOutcome,
    GovernanceEnactmentEventV1,
    GovernanceRequestEventV1,
)
from synthworld.authority_governance.replay import (
    controlling_governance_decision,
    validate_authority_governance_public,
)

type AuthorityGovernanceBaseline = Callable[
    [AuthorityGovernancePublicV1], AuthorityGovernancePredictionV1
]


def final_state_implies_valid_baseline(
    public: AuthorityGovernancePublicV1,
) -> AuthorityGovernancePredictionV1:
    """Incorrectly infer governance validity solely from resulting state."""

    return _observed_prediction(public, mode="final_state")


def trust_recorded_approval_baseline(
    public: AuthorityGovernancePublicV1,
) -> AuthorityGovernancePredictionV1:
    """Incorrectly trust a recorded approval without checking its authority."""

    return _observed_prediction(public, mode="trust_approval")


def latest_policy_baseline(
    public: AuthorityGovernancePublicV1,
) -> AuthorityGovernancePredictionV1:
    """Incorrectly evaluate every historical decision under the latest policy."""

    return _observed_prediction(public, mode="latest_policy")


AUTHORITY_GOVERNANCE_BASELINES: tuple[tuple[str, AuthorityGovernanceBaseline], ...] = (
    ("Final state implies valid", final_state_implies_valid_baseline),
    ("Trust recorded approval", trust_recorded_approval_baseline),
    ("Use latest policy", latest_policy_baseline),
)


def _observed_prediction(
    public: AuthorityGovernancePublicV1,
    *,
    mode: str,
) -> AuthorityGovernancePredictionV1:
    validate_authority_governance_public(public)
    events = {item.id: item for item in public.events}
    latest_policy = max(
        public.policies,
        key=lambda item: (item.active_from_tick, item.policy_version_id),
    )
    rows = []
    for case in public.cases:
        request = cast(GovernanceRequestEventV1, events[case.request_event_id])
        enactment = cast(GovernanceEnactmentEventV1, events[case.enactment_event_id])
        audit = cast(GovernanceAuditEventV1, events[case.audit_event_id])
        decision = controlling_governance_decision(
            public, authority_change_id=case.authority_change_id
        )
        policy_version_id = decision.policy_version_id
        policy_rule_ids = decision.policy_rule_ids
        control_ids = decision.control_ids
        rationale_code = decision.rationale_code
        if mode == "latest_policy":
            policy_version_id = latest_policy.policy_version_id
            deny = decision.outcome is GovernanceDecisionOutcome.DENIED
            selected = next(
                item
                for item in latest_policy.rules
                if (item.effect.value == "deny") is deny
            )
            policy_rule_ids = (selected.rule_id,)
            control_ids = selected.control_ids
            rationale_code = selected.rationale_codes[0]
        if mode == "final_state":
            governance_authorised = (
                enactment.enacted_after_state != request.observed_before_state
            )
        else:
            governance_authorised = decision.outcome in {
                GovernanceDecisionOutcome.APPROVED,
                GovernanceDecisionOutcome.PARTIALLY_APPROVED,
            }
        rows.append(
            AuthorityGovernancePredictionRowV1(
                authority_change_id=case.authority_change_id,
                change_type=request.change_type,
                canonical_before_state=request.observed_before_state,
                canonical_after_state=enactment.enacted_after_state,
                governance_decision_authorised=governance_authorised,
                approver_authorised_at_decision=True,
                requester_principal_id=request.requester_principal_id,
                approval_chain=decision.approval_chain,
                accountable_owner_chain=decision.accountable_owner_chain,
                policy_version_id=policy_version_id,
                policy_rule_ids=policy_rule_ids,
                control_ids=control_ids,
                rationale_code=rationale_code,
                exception_id=decision.exception_id,
                decision_evidence_refs=decision.evidence_refs,
                controlling_decision_id=decision.decision_id,
                decision_outcome=decision.outcome,
                effective_tick=enactment.effective_tick,
                superseded_authority_change_id=(request.supersedes_authority_change_id),
                enactment_consistent=True,
                audit_reconstructable=bool(audit.retained_evidence_refs),
            )
        )
    return AuthorityGovernancePredictionV1(rows=tuple(rows))


__all__ = [
    "AUTHORITY_GOVERNANCE_BASELINES",
    "AuthorityGovernanceBaseline",
    "final_state_implies_valid_baseline",
    "latest_policy_baseline",
    "trust_recorded_approval_baseline",
]
