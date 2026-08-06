"""Structural validation and tick replay for authority-governance artifacts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from synthworld.authority_governance.models import (
    ApproverMandateV1,
    AuthorityGovernanceCaseV1,
    AuthorityGovernanceEvaluatorV1,
    AuthorityGovernancePublicV1,
    AuthorityStateV1,
    GovernanceAuditEventV1,
    GovernanceDecisionEventV1,
    GovernanceEnactmentEventV1,
    GovernancePolicyVersionV1,
    GovernanceRequestEventV1,
)
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.temporal_schedule import (
    validate_governance_temporal_schedule,
)


class AuthorityGovernanceIntegrityError(ValueError):
    """Raised when a governance artifact is structurally inconsistent."""


def validate_authority_governance_public(
    public: AuthorityGovernancePublicV1,
) -> None:
    """Reject broken structure while retaining scoreable governance failures."""

    try:
        validate_governance_temporal_schedule(
            events=public.events,
            envelopes=public.schedule,
            event_schedule_version=public.event_schedule_version,
        )
    except ValueError as error:
        raise AuthorityGovernanceIntegrityError(
            "governance temporal schedule binding differs"
        ) from error
    policy_index = {item.policy_version_id: item for item in public.policies}
    mandate_ids = {item.mandate_id for item in public.approver_mandates}
    evidence_ids = {item.evidence_ref for item in public.evidence}
    case_index = {item.authority_change_id: item for item in public.cases}
    event_index = {item.id: item for item in public.events}
    decision_ids: set[str] = set()
    for event in public.events:
        if event.authority_change_id not in case_index:
            raise AuthorityGovernanceIntegrityError(
                "governance event references an unknown change"
            )
        if isinstance(event, GovernanceDecisionEventV1):
            if event.decision_id in decision_ids:
                raise AuthorityGovernanceIntegrityError(
                    "governance decision identifiers must be unique"
                )
            decision_ids.add(event.decision_id)
            policy = policy_index.get(event.policy_version_id)
            if policy is None:
                raise AuthorityGovernanceIntegrityError(
                    "governance decision references an unknown policy version"
                )
            rules = {item.rule_id: item for item in policy.rules}
            if not set(event.policy_rule_ids) <= set(rules):
                raise AuthorityGovernanceIntegrityError(
                    "governance decision references an unknown policy rule"
                )
            available_controls = {
                control
                for rule_id in event.policy_rule_ids
                for control in rules[rule_id].control_ids
            }
            if not set(event.control_ids) <= available_controls:
                raise AuthorityGovernanceIntegrityError(
                    "governance decision references an unknown policy control"
                )
            if not set(event.mandate_ids) <= mandate_ids:
                raise AuthorityGovernanceIntegrityError(
                    "governance decision references an unknown mandate"
                )
            if not set(event.evidence_refs) <= evidence_ids:
                raise AuthorityGovernanceIntegrityError(
                    "governance decision references unknown evidence"
                )
        elif (
            isinstance(event, GovernanceAuditEventV1)
            and not set(event.retained_evidence_refs) <= evidence_ids
        ):
            raise AuthorityGovernanceIntegrityError(
                "governance audit references unknown evidence"
            )

    consumed: set[str] = set()
    for case in public.cases:
        _validate_case(case, event_index)
        case_events = {
            case.request_event_id,
            *case.decision_event_ids,
            case.enactment_event_id,
            case.audit_event_id,
        }
        if consumed & case_events:
            raise AuthorityGovernanceIntegrityError(
                "governance event belongs to more than one case"
            )
        consumed |= case_events
    if consumed != set(event_index):
        raise AuthorityGovernanceIntegrityError(
            "governance event inventory differs from its cases"
        )


def validate_authority_governance_evaluator(
    public: AuthorityGovernancePublicV1,
    evaluator: AuthorityGovernanceEvaluatorV1,
) -> None:
    """Validate physical binding and evaluator-only reference integrity."""

    validate_authority_governance_public(public)
    if evaluator.public_digest != synthetic_digest(canonical_json_bytes(public)):
        raise AuthorityGovernanceIntegrityError(
            "governance evaluator public digest differs"
        )
    public_ids = tuple(item.authority_change_id for item in public.cases)
    truth_ids = tuple(item.authority_change_id for item in evaluator.truth)
    if truth_ids != public_ids:
        raise AuthorityGovernanceIntegrityError(
            "governance evaluator inventory differs from public cases"
        )
    cases = {item.authority_change_id: item for item in public.cases}
    events = {item.id: item for item in public.events}
    policy_index = {item.policy_version_id: item for item in public.policies}
    evidence_ids = {item.evidence_ref for item in public.evidence}
    public_change_ids = set(public_ids)
    for truth in evaluator.truth:
        case = cases[truth.authority_change_id]
        decisions = tuple(
            _require_event(events[item], GovernanceDecisionEventV1, "decision")
            for item in case.decision_event_ids
        )
        if truth.controlling_decision_id not in {
            item.decision_id for item in decisions
        }:
            raise AuthorityGovernanceIntegrityError(
                "governance truth references an unknown controlling decision"
            )
        policy = policy_index.get(truth.applicable_policy_version_id)
        if policy is None:
            raise AuthorityGovernanceIntegrityError(
                "governance truth references an unknown policy version"
            )
        rules = {item.rule_id: item for item in policy.rules}
        if not set(truth.applicable_policy_rule_ids) <= set(rules):
            raise AuthorityGovernanceIntegrityError(
                "governance truth references an unknown policy rule"
            )
        available_controls = {
            control
            for rule_id in truth.applicable_policy_rule_ids
            for control in rules[rule_id].control_ids
        }
        if not set(truth.applicable_control_ids) <= available_controls:
            raise AuthorityGovernanceIntegrityError(
                "governance truth references an unknown policy control"
            )
        if not set(truth.required_decision_evidence_refs) <= evidence_ids:
            raise AuthorityGovernanceIntegrityError(
                "governance truth references unknown evidence"
            )
        if (
            truth.superseded_authority_change_id is not None
            and truth.superseded_authority_change_id not in public_change_ids
        ):
            raise AuthorityGovernanceIntegrityError(
                "governance truth references an unknown superseded change"
            )


def materialize_authority_state(
    public: AuthorityGovernancePublicV1, *, as_of_tick: int
) -> AuthorityStateV1:
    """Replay observed enactments through one inclusive integer-tick checkpoint."""

    if as_of_tick < 0:
        raise AuthorityGovernanceIntegrityError(
            "governance replay tick must be nonnegative"
        )
    validate_authority_governance_public(public)
    requests = {
        item.authority_change_id: item
        for item in public.events
        if isinstance(item, GovernanceRequestEventV1)
    }
    state = {item.authority_id: item for item in public.initial_state.authorities}
    for event in public.events:
        if not isinstance(event, GovernanceEnactmentEventV1):
            continue
        if event.effective_tick > as_of_tick:
            break
        affected = requests[event.authority_change_id].affected_authority_id
        state.pop(affected, None)
        state.update(
            {item.authority_id: item for item in event.enacted_after_state.authorities}
        )
    return AuthorityStateV1(
        authorities=tuple(state[item] for item in sorted(state)),
    )


def controlling_governance_decision(
    public: AuthorityGovernancePublicV1, *, authority_change_id: str
) -> GovernanceDecisionEventV1:
    """Return the last canonical decision no later than enactment."""

    validate_authority_governance_public(public)
    case = next(
        (
            item
            for item in public.cases
            if item.authority_change_id == authority_change_id
        ),
        None,
    )
    if case is None:
        raise AuthorityGovernanceIntegrityError("governance change is unknown")
    events = {item.id: item for item in public.events}
    decisions = tuple(
        _require_event(events[item], GovernanceDecisionEventV1, "decision")
        for item in case.decision_event_ids
    )
    return max(decisions, key=lambda item: (item.effective_tick, item.id))


def active_governance_policies(
    policies: Iterable[GovernancePolicyVersionV1], *, at_tick: int
) -> tuple[GovernancePolicyVersionV1, ...]:
    """Select policy versions active at a decision tick using half-open validity."""

    if at_tick < 0:
        raise AuthorityGovernanceIntegrityError(
            "policy lookup tick must be nonnegative"
        )
    return tuple(
        sorted(
            (
                item
                for item in policies
                if item.active_from_tick <= at_tick
                and (
                    item.inactive_from_tick is None or at_tick < item.inactive_from_tick
                )
            ),
            key=lambda item: item.policy_version_id,
        )
    )


def active_approver_mandates(
    mandates: Iterable[ApproverMandateV1], *, at_tick: int
) -> tuple[ApproverMandateV1, ...]:
    """Select approver mandates valid at a decision tick."""

    if at_tick < 0:
        raise AuthorityGovernanceIntegrityError(
            "mandate lookup tick must be nonnegative"
        )
    return tuple(
        sorted(
            (
                item
                for item in mandates
                if item.valid_from_tick <= at_tick
                and (item.valid_until_tick is None or at_tick < item.valid_until_tick)
            ),
            key=lambda item: item.mandate_id,
        )
    )


def _validate_case(
    case: AuthorityGovernanceCaseV1, events: Mapping[str, object]
) -> None:
    referenced = (
        case.request_event_id,
        *case.decision_event_ids,
        case.enactment_event_id,
        case.audit_event_id,
    )
    if not set(referenced) <= set(events):
        raise AuthorityGovernanceIntegrityError(
            "governance case references an unknown event"
        )
    request = _require_event(
        events[case.request_event_id], GovernanceRequestEventV1, "request"
    )
    decisions = tuple(
        _require_event(events[item], GovernanceDecisionEventV1, "decision")
        for item in case.decision_event_ids
    )
    enactment = _require_event(
        events[case.enactment_event_id], GovernanceEnactmentEventV1, "enactment"
    )
    audit = _require_event(events[case.audit_event_id], GovernanceAuditEventV1, "audit")
    typed = (request, *decisions, enactment, audit)
    if any(item.authority_change_id != case.authority_change_id for item in typed):
        raise AuthorityGovernanceIntegrityError(
            "governance case and event change identifiers differ"
        )
    keys = tuple((item.effective_tick, item.id) for item in typed)
    if keys != tuple(sorted(keys)):
        raise AuthorityGovernanceIntegrityError(
            "governance request/decision/effective/audit order differs"
        )
    decision_ids = {item.decision_id for item in decisions}
    if enactment.decision_id not in decision_ids:
        raise AuthorityGovernanceIntegrityError(
            "governance enactment references an unknown case decision"
        )


def _require_event[EventT](
    event: object, expected: type[EventT], description: str
) -> EventT:
    if not isinstance(event, expected):
        raise AuthorityGovernanceIntegrityError(
            f"governance case {description} event has the wrong type"
        )
    return event


__all__ = [
    "AuthorityGovernanceIntegrityError",
    "active_approver_mandates",
    "active_governance_policies",
    "controlling_governance_decision",
    "materialize_authority_state",
    "validate_authority_governance_evaluator",
    "validate_authority_governance_public",
]
