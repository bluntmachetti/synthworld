"""Hand-inspectable twelve-case authority-governance conformance fixture."""

from __future__ import annotations

from dataclasses import dataclass

from synthworld.authority_governance.models import (
    ApproverMandateV1,
    AuthorityChangeType,
    AuthorityGovernanceCaseKind,
    AuthorityGovernanceCaseV1,
    AuthorityGovernanceEvaluatorV1,
    AuthorityGovernanceEventV1,
    AuthorityGovernancePublicV1,
    AuthorityGovernanceTruthRowV1,
    AuthorityStateV1,
    GovernanceAuditEventV1,
    GovernanceDecisionEventV1,
    GovernanceDecisionOutcome,
    GovernanceEnactmentEventV1,
    GovernanceEvidenceKind,
    GovernanceEvidenceRecordV1,
    GovernancePolicyEffect,
    GovernancePolicyRuleV1,
    GovernancePolicyVersionV1,
    GovernanceRequestEventV1,
    GovernedAuthorityV1,
)
from synthworld.authority_governance.replay import (
    validate_authority_governance_evaluator,
)
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.temporal_schedule import compile_governance_temporal_schedule

REFERENCE_GOVERNANCE_SCHEDULE_VERSION = "authority-governance-reference-1.0.0"


@dataclass(frozen=True, slots=True)
class ReferenceAuthorityGovernanceV1:
    public: AuthorityGovernancePublicV1
    evaluator: AuthorityGovernanceEvaluatorV1


@dataclass(frozen=True, slots=True)
class _CaseSpec:
    change_id: str
    kind: AuthorityGovernanceCaseKind
    change_type: AuthorityChangeType
    request_tick: int
    decision_tick: int
    enactment_tick: int
    audit_tick: int
    expected_effective_tick: int
    before: AuthorityStateV1
    requested: AuthorityStateV1
    approved: AuthorityStateV1
    enacted: AuthorityStateV1
    outcome: GovernanceDecisionOutcome
    policy_version_id: str
    policy_rule_id: str
    control_id: str
    rationale_code: str
    approver_id: str
    mandate_ids: tuple[str, ...]
    governance_authorised: bool
    approver_authorised: bool
    enactment_consistent: bool
    audit_reconstructable: bool = True
    exception_id: str | None = None
    observed_supersedes: str | None = None
    canonical_supersedes: str | None = None
    conflicting_decisions: bool = False
    failure_reasons: tuple[str, ...] = ()


def reference_authority_governance() -> ReferenceAuthorityGovernanceV1:
    """Build the deterministic conformance fixture without freezing a golden."""

    initial_state = AuthorityStateV1(
        authorities=(_authority("03", broad=True), _authority("10", broad=True))
    )
    specs = _case_specs()
    evidence = _evidence_records(specs)
    events = tuple(
        sorted(
            (event for spec in specs for event in _events_for_case(spec)),
            key=lambda item: (item.effective_tick, item.id),
        )
    )
    cases = tuple(_case_record(spec) for spec in specs)
    schedule = compile_governance_temporal_schedule(
        events=events,
        event_schedule_version=REFERENCE_GOVERNANCE_SCHEDULE_VERSION,
    )
    public = AuthorityGovernancePublicV1(
        event_schedule_version=REFERENCE_GOVERNANCE_SCHEDULE_VERSION,
        policies=_policies(),
        approver_mandates=_mandates(),
        evidence=evidence,
        initial_state=initial_state,
        cases=cases,
        events=events,
        schedule=schedule,
    )
    evaluator = AuthorityGovernanceEvaluatorV1(
        public_digest=synthetic_digest(canonical_json_bytes(public)),
        truth=tuple(_truth_for_case(spec) for spec in specs),
    )
    validate_authority_governance_evaluator(public, evaluator)
    return ReferenceAuthorityGovernanceV1(public=public, evaluator=evaluator)


def _case_specs() -> tuple[_CaseSpec, ...]:
    empty = AuthorityStateV1()
    broad_03 = _state(_authority("03", broad=True))
    narrow_03 = _state(_authority("03"))
    broad_10 = _state(_authority("10", broad=True))
    changed_01 = _state(_authority("01", actions=("approve", "read")))
    return (
        _CaseSpec(
            "change-01",
            AuthorityGovernanceCaseKind.PROPERLY_APPROVED_GRANT,
            AuthorityChangeType.GRANT,
            1,
            2,
            3,
            4,
            3,
            empty,
            _state(_authority("01")),
            _state(_authority("01")),
            _state(_authority("01")),
            GovernanceDecisionOutcome.APPROVED,
            "policy-v1",
            "rule-standard",
            "control:change-approval",
            "business_need",
            "principal:approver-valid",
            ("mandate-valid",),
            True,
            True,
            True,
        ),
        _CaseSpec(
            "change-02",
            AuthorityGovernanceCaseKind.WRONG_APPROVER,
            AuthorityChangeType.GRANT,
            11,
            12,
            13,
            14,
            13,
            empty,
            _state(_authority("02")),
            _state(_authority("02")),
            _state(_authority("02")),
            GovernanceDecisionOutcome.APPROVED,
            "policy-v1",
            "rule-standard",
            "control:change-approval",
            "business_need",
            "principal:approver-wrong",
            (),
            False,
            False,
            True,
            failure_reasons=("approver_not_authorised",),
        ),
        _CaseSpec(
            "change-03",
            AuthorityGovernanceCaseKind.APPROVED_SCOPE_DIFFERS,
            AuthorityChangeType.ATTENUATE,
            21,
            22,
            23,
            24,
            23,
            broad_03,
            narrow_03,
            narrow_03,
            broad_03,
            GovernanceDecisionOutcome.PARTIALLY_APPROVED,
            "policy-v1",
            "rule-standard",
            "control:change-approval",
            "business_need",
            "principal:approver-valid",
            ("mandate-valid",),
            True,
            True,
            False,
            failure_reasons=("approved_scope_differs_from_enacted_scope",),
        ),
        _CaseSpec(
            "change-04",
            AuthorityGovernanceCaseKind.DENIED_REQUEST_ENACTED,
            AuthorityChangeType.GRANT,
            31,
            32,
            33,
            34,
            33,
            empty,
            _state(_authority("04")),
            empty,
            _state(_authority("04")),
            GovernanceDecisionOutcome.DENIED,
            "policy-v1",
            "rule-deny",
            "control:deny",
            "prohibited_scope",
            "principal:approver-valid",
            ("mandate-valid",),
            False,
            True,
            False,
            failure_reasons=("denied_request_enacted",),
        ),
        _CaseSpec(
            "change-05",
            AuthorityGovernanceCaseKind.VALID_EMERGENCY_EXCEPTION,
            AuthorityChangeType.GRANT,
            41,
            42,
            43,
            44,
            43,
            empty,
            _state(_authority("05", valid_until_tick=48)),
            _state(_authority("05", valid_until_tick=48)),
            _state(_authority("05", valid_until_tick=48)),
            GovernanceDecisionOutcome.APPROVED,
            "policy-v1",
            "rule-emergency",
            "control:emergency-exception",
            "emergency_response",
            "principal:approver-emergency",
            ("mandate-emergency",),
            True,
            True,
            True,
            exception_id="exception:emergency-05",
        ),
        _CaseSpec(
            "change-06",
            AuthorityGovernanceCaseKind.EXPIRED_APPROVER_AUTHORITY,
            AuthorityChangeType.GRANT,
            56,
            60,
            61,
            62,
            61,
            empty,
            _state(_authority("06")),
            _state(_authority("06")),
            _state(_authority("06")),
            GovernanceDecisionOutcome.APPROVED,
            "policy-v1",
            "rule-standard",
            "control:change-approval",
            "business_need",
            "principal:approver-expired",
            ("mandate-expired",),
            False,
            False,
            True,
            failure_reasons=("approver_authority_expired",),
        ),
        _CaseSpec(
            "change-07",
            AuthorityGovernanceCaseKind.POLICY_CHANGED_AFTER_DECISION,
            AuthorityChangeType.GRANT,
            64,
            65,
            66,
            75,
            66,
            empty,
            _state(_authority("07")),
            _state(_authority("07")),
            _state(_authority("07")),
            GovernanceDecisionOutcome.APPROVED,
            "policy-v1",
            "rule-standard",
            "control:change-approval",
            "business_need",
            "principal:approver-valid",
            ("mandate-valid",),
            True,
            True,
            True,
        ),
        _CaseSpec(
            "change-08",
            AuthorityGovernanceCaseKind.MISSING_RETAINED_APPROVAL_EVIDENCE,
            AuthorityChangeType.GRANT,
            76,
            77,
            78,
            90,
            78,
            empty,
            _state(_authority("08")),
            _state(_authority("08")),
            _state(_authority("08")),
            GovernanceDecisionOutcome.APPROVED,
            "policy-v2",
            "rule-standard-v2",
            "control:change-approval-v2",
            "business_need_v2",
            "principal:approver-valid",
            ("mandate-valid",),
            True,
            True,
            True,
            audit_reconstructable=False,
            failure_reasons=("required_approval_evidence_not_retained",),
        ),
        _CaseSpec(
            "change-09",
            AuthorityGovernanceCaseKind.UNLINKED_SUPERSESSION,
            AuthorityChangeType.SUPERSEDE,
            91,
            92,
            93,
            94,
            93,
            _state(_authority("01")),
            changed_01,
            changed_01,
            changed_01,
            GovernanceDecisionOutcome.APPROVED,
            "policy-v2",
            "rule-standard-v2",
            "control:change-approval-v2",
            "business_need_v2",
            "principal:approver-valid",
            ("mandate-valid",),
            False,
            True,
            True,
            canonical_supersedes="change-01",
            failure_reasons=("supersession_link_missing",),
        ),
        _CaseSpec(
            "change-10",
            AuthorityGovernanceCaseKind.REVOCATION_EFFECTIVE_TIME_DRIFT,
            AuthorityChangeType.REVOKE,
            100,
            101,
            108,
            110,
            102,
            broad_10,
            empty,
            empty,
            empty,
            GovernanceDecisionOutcome.APPROVED,
            "policy-v2",
            "rule-standard-v2",
            "control:change-approval-v2",
            "business_need_v2",
            "principal:approver-valid",
            ("mandate-valid",),
            True,
            True,
            False,
            failure_reasons=("revocation_effective_time_drift",),
        ),
        _CaseSpec(
            "change-11",
            AuthorityGovernanceCaseKind.CONFLICTING_DECISIONS,
            AuthorityChangeType.GRANT,
            111,
            112,
            114,
            115,
            114,
            empty,
            _state(_authority("11")),
            empty,
            _state(_authority("11")),
            GovernanceDecisionOutcome.DENIED,
            "policy-v2",
            "rule-deny-v2",
            "control:deny-v2",
            "prohibited_scope_v2",
            "principal:approver-valid",
            ("mandate-valid",),
            False,
            True,
            False,
            conflicting_decisions=True,
            failure_reasons=(
                "conflicting_decisions",
                "controlling_denial_not_honoured",
            ),
        ),
        _CaseSpec(
            "change-12",
            AuthorityGovernanceCaseKind.UNAUTHORISED_WELL_FORMED_CHANGE,
            AuthorityChangeType.GRANT,
            121,
            122,
            123,
            124,
            123,
            empty,
            _state(_authority("12")),
            _state(_authority("12")),
            _state(_authority("12")),
            GovernanceDecisionOutcome.APPROVED,
            "policy-v2",
            "rule-deny-v2",
            "control:deny-v2",
            "prohibited_scope_v2",
            "principal:approver-valid",
            ("mandate-valid",),
            False,
            True,
            True,
            failure_reasons=("governance_policy_denied_change",),
        ),
    )


def _events_for_case(spec: _CaseSpec) -> tuple[AuthorityGovernanceEventV1, ...]:
    request_id = f"{spec.change_id}-01-request"
    decision_a_id = f"{spec.change_id}-02-decision-a"
    decision_b_id = f"{spec.change_id}-02-decision-b"
    enactment_id = f"{spec.change_id}-03-enactment"
    audit_id = f"{spec.change_id}-04-audit"
    evidence_refs = _required_evidence_refs(spec)
    request = GovernanceRequestEventV1(
        id=request_id,
        effective_tick=spec.request_tick,
        authority_change_id=spec.change_id,
        change_type=spec.change_type,
        affected_authority_id=_affected_authority_id(spec),
        requester_principal_id=f"principal:requester-{spec.change_id[-2:]}",
        observed_before_state=spec.before,
        requested_after_state=spec.requested,
        supersedes_authority_change_id=spec.observed_supersedes,
    )
    if spec.conflicting_decisions:
        decision_a = GovernanceDecisionEventV1(
            id=decision_a_id,
            effective_tick=spec.decision_tick,
            authority_change_id=spec.change_id,
            decision_id=f"decision:{spec.change_id}:a",
            outcome=GovernanceDecisionOutcome.APPROVED,
            approval_chain=(spec.approver_id,),
            accountable_owner_chain=("principal:owner",),
            approved_after_state=spec.requested,
            policy_version_id="policy-v2",
            policy_rule_ids=("rule-standard-v2",),
            control_ids=("control:change-approval-v2",),
            rationale_code="business_need_v2",
            purpose="bounded governance conformance",
            evidence_refs=evidence_refs,
            mandate_ids=spec.mandate_ids,
        )
        decision_b = _decision_event(
            spec,
            event_id=decision_b_id,
            decision_id=f"decision:{spec.change_id}:b",
            effective_tick=spec.decision_tick + 1,
        )
        decisions: tuple[GovernanceDecisionEventV1, ...] = (
            decision_a,
            decision_b,
        )
        enactment_decision_id = decision_a.decision_id
    else:
        decision = _decision_event(
            spec,
            event_id=decision_a_id,
            decision_id=f"decision:{spec.change_id}:a",
            effective_tick=spec.decision_tick,
        )
        decisions = (decision,)
        enactment_decision_id = decision.decision_id
    enactment = GovernanceEnactmentEventV1(
        id=enactment_id,
        effective_tick=spec.enactment_tick,
        authority_change_id=spec.change_id,
        decision_id=enactment_decision_id,
        enacted_after_state=spec.enacted,
    )
    retained = evidence_refs
    if not spec.audit_reconstructable:
        retained = tuple(item for item in retained if not item.endswith(":approval"))
    audit = GovernanceAuditEventV1(
        id=audit_id,
        effective_tick=spec.audit_tick,
        authority_change_id=spec.change_id,
        retained_evidence_refs=retained,
    )
    return (request, *decisions, enactment, audit)


def _decision_event(
    spec: _CaseSpec, *, event_id: str, decision_id: str, effective_tick: int
) -> GovernanceDecisionEventV1:
    return GovernanceDecisionEventV1(
        id=event_id,
        effective_tick=effective_tick,
        authority_change_id=spec.change_id,
        decision_id=decision_id,
        outcome=spec.outcome,
        approval_chain=(spec.approver_id,),
        accountable_owner_chain=("principal:owner",),
        approved_after_state=spec.approved,
        policy_version_id=spec.policy_version_id,
        policy_rule_ids=(spec.policy_rule_id,),
        control_ids=(spec.control_id,),
        rationale_code=spec.rationale_code,
        purpose="bounded governance conformance",
        exception_id=spec.exception_id,
        evidence_refs=_required_evidence_refs(spec),
        mandate_ids=spec.mandate_ids,
    )


def _case_record(spec: _CaseSpec) -> AuthorityGovernanceCaseV1:
    decision_ids: tuple[str, ...] = (f"{spec.change_id}-02-decision-a",)
    if spec.conflicting_decisions:
        decision_ids += (f"{spec.change_id}-02-decision-b",)
    return AuthorityGovernanceCaseV1(
        authority_change_id=spec.change_id,
        request_event_id=f"{spec.change_id}-01-request",
        decision_event_ids=decision_ids,
        enactment_event_id=f"{spec.change_id}-03-enactment",
        audit_event_id=f"{spec.change_id}-04-audit",
    )


def _truth_for_case(spec: _CaseSpec) -> AuthorityGovernanceTruthRowV1:
    controlling_suffix = "b" if spec.conflicting_decisions else "a"
    return AuthorityGovernanceTruthRowV1(
        authority_change_id=spec.change_id,
        case_kind=spec.kind,
        change_type=spec.change_type,
        canonical_before_state=spec.before,
        canonical_after_state=spec.enacted,
        governance_decision_authorised=spec.governance_authorised,
        approver_authorised_at_decision=spec.approver_authorised,
        canonical_requester_principal_id=(f"principal:requester-{spec.change_id[-2:]}"),
        canonical_approval_chain=(spec.approver_id,),
        canonical_accountable_owner_chain=("principal:owner",),
        applicable_policy_version_id=spec.policy_version_id,
        applicable_policy_rule_ids=(spec.policy_rule_id,),
        applicable_control_ids=(spec.control_id,),
        expected_rationale_code=spec.rationale_code,
        expected_exception_id=spec.exception_id,
        required_decision_evidence_refs=_required_evidence_refs(spec),
        controlling_decision_id=f"decision:{spec.change_id}:{controlling_suffix}",
        expected_decision_outcome=spec.outcome,
        expected_effective_tick=spec.expected_effective_tick,
        superseded_authority_change_id=spec.canonical_supersedes,
        enactment_consistent=spec.enactment_consistent,
        audit_reconstructable=spec.audit_reconstructable,
        failure_reasons=spec.failure_reasons,
    )


def _policies() -> tuple[GovernancePolicyVersionV1, ...]:
    common_changes = tuple(sorted(AuthorityChangeType, key=str))
    common_evidence = (
        GovernanceEvidenceKind.APPROVAL,
        GovernanceEvidenceKind.POLICY,
        GovernanceEvidenceKind.REQUEST,
    )
    return (
        GovernancePolicyVersionV1(
            policy_version_id="policy-v1",
            active_from_tick=0,
            inactive_from_tick=70,
            rules=(
                GovernancePolicyRuleV1(
                    rule_id="rule-deny",
                    effect=GovernancePolicyEffect.DENY,
                    change_types=common_changes,
                    approver_ids=("principal:approver-valid",),
                    rationale_codes=("prohibited_scope",),
                    required_evidence_kinds=common_evidence,
                    control_ids=("control:deny",),
                ),
                GovernancePolicyRuleV1(
                    rule_id="rule-emergency",
                    effect=GovernancePolicyEffect.PERMIT,
                    change_types=(AuthorityChangeType.GRANT,),
                    approver_ids=("principal:approver-emergency",),
                    rationale_codes=("emergency_response",),
                    required_evidence_kinds=(
                        GovernanceEvidenceKind.APPROVAL,
                        GovernanceEvidenceKind.EXCEPTION,
                        GovernanceEvidenceKind.POLICY,
                        GovernanceEvidenceKind.REQUEST,
                    ),
                    control_ids=("control:emergency-exception",),
                    exception_ids=("exception:emergency-05",),
                ),
                GovernancePolicyRuleV1(
                    rule_id="rule-standard",
                    effect=GovernancePolicyEffect.PERMIT,
                    change_types=common_changes,
                    approver_ids=("principal:approver-valid",),
                    rationale_codes=("business_need",),
                    required_evidence_kinds=common_evidence,
                    control_ids=("control:change-approval",),
                ),
            ),
        ),
        GovernancePolicyVersionV1(
            policy_version_id="policy-v2",
            active_from_tick=70,
            rules=(
                GovernancePolicyRuleV1(
                    rule_id="rule-deny-v2",
                    effect=GovernancePolicyEffect.DENY,
                    change_types=common_changes,
                    approver_ids=("principal:approver-valid",),
                    rationale_codes=("prohibited_scope_v2",),
                    required_evidence_kinds=common_evidence,
                    control_ids=("control:deny-v2",),
                ),
                GovernancePolicyRuleV1(
                    rule_id="rule-standard-v2",
                    effect=GovernancePolicyEffect.PERMIT,
                    change_types=common_changes,
                    approver_ids=("principal:approver-valid",),
                    rationale_codes=("business_need_v2",),
                    required_evidence_kinds=common_evidence,
                    control_ids=("control:change-approval-v2",),
                ),
            ),
        ),
    )


def _mandates() -> tuple[ApproverMandateV1, ...]:
    common_changes = tuple(sorted(AuthorityChangeType, key=str))
    all_authorities = tuple(f"authority-{index:02d}" for index in range(1, 13))
    return (
        ApproverMandateV1(
            mandate_id="mandate-emergency",
            approver_principal_id="principal:approver-emergency",
            valid_from_tick=40,
            valid_until_tick=50,
            change_types=(AuthorityChangeType.GRANT,),
            affected_authority_ids=("authority-05",),
        ),
        ApproverMandateV1(
            mandate_id="mandate-expired",
            approver_principal_id="principal:approver-expired",
            valid_from_tick=0,
            valid_until_tick=55,
            change_types=(AuthorityChangeType.GRANT,),
            affected_authority_ids=("authority-06",),
        ),
        ApproverMandateV1(
            mandate_id="mandate-valid",
            approver_principal_id="principal:approver-valid",
            valid_from_tick=0,
            change_types=common_changes,
            affected_authority_ids=all_authorities,
        ),
    )


def _evidence_records(
    specs: tuple[_CaseSpec, ...],
) -> tuple[GovernanceEvidenceRecordV1, ...]:
    records = []
    for spec in specs:
        kinds = {
            "approval": GovernanceEvidenceKind.APPROVAL,
            "policy": GovernanceEvidenceKind.POLICY,
            "request": GovernanceEvidenceKind.REQUEST,
        }
        if spec.exception_id is not None:
            kinds["exception"] = GovernanceEvidenceKind.EXCEPTION
        for suffix, kind in kinds.items():
            retained_until_tick = None
            if spec.change_id == "change-08" and suffix == "approval":
                retained_until_tick = 85
            records.append(
                GovernanceEvidenceRecordV1(
                    evidence_ref=f"evidence:{spec.change_id}:{suffix}",
                    kind=kind,
                    available_from_tick=spec.request_tick,
                    retained_until_tick=retained_until_tick,
                )
            )
    return tuple(sorted(records, key=lambda item: item.evidence_ref))


def _required_evidence_refs(spec: _CaseSpec) -> tuple[str, ...]:
    suffixes = ["approval", "policy", "request"]
    if spec.exception_id is not None:
        suffixes.append("exception")
    return tuple(sorted(f"evidence:{spec.change_id}:{item}" for item in suffixes))


def _affected_authority_id(spec: _CaseSpec) -> str:
    if spec.change_id == "change-09":
        return "authority-01"
    return f"authority-{spec.change_id[-2:]}"


def _authority(
    suffix: str,
    *,
    broad: bool = False,
    actions: tuple[str, ...] | None = None,
    valid_until_tick: int | None = None,
) -> GovernedAuthorityV1:
    selected_actions = actions or (("read", "write") if broad else ("read",))
    return GovernedAuthorityV1(
        authority_id=f"authority-{suffix}",
        subject_id=f"principal:subject-{suffix}",
        capability_id=f"capability:{suffix}",
        resource_id=f"resource:{suffix}",
        actions=selected_actions,
        scopes=("scope:global",) if broad else ("scope:regional",),
        purpose="bounded governance conformance",
        valid_from_tick=0,
        valid_until_tick=valid_until_tick,
    )


def _state(*authorities: GovernedAuthorityV1) -> AuthorityStateV1:
    return AuthorityStateV1(
        authorities=tuple(sorted(authorities, key=lambda item: item.authority_id))
    )


__all__ = [
    "REFERENCE_GOVERNANCE_SCHEDULE_VERSION",
    "ReferenceAuthorityGovernanceV1",
    "reference_authority_governance",
]
