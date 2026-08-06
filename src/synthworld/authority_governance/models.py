"""Strict contracts for bounded authority-change governance conformance."""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, ValidationInfo, field_validator, model_validator

from synthworld.enterprise.models import SyntheticDigestV1
from synthworld.models import SyntheticModel
from synthworld.temporal_schedule import TemporalEventEnvelopeV2

AUTHORITY_GOVERNANCE_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
AUTHORITY_GOVERNANCE_BENCHMARK_VERSION: Literal["1.0.0"] = "1.0.0"
AUTHORITY_GOVERNANCE_SCORING_VERSION: Literal["1.0.0"] = "1.0.0"


class AuthorityChangeType(StrEnum):
    GRANT = "grant"
    AMEND = "amend"
    ATTENUATE = "attenuate"
    SUSPEND = "suspend"
    REVOKE = "revoke"
    EXPIRE = "expire"
    SUPERSEDE = "supersede"


class GovernanceDecisionOutcome(StrEnum):
    APPROVED = "approved"
    DENIED = "denied"
    PARTIALLY_APPROVED = "partially_approved"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"


class GovernancePolicyEffect(StrEnum):
    PERMIT = "permit"
    DENY = "deny"


class GovernanceEvidenceKind(StrEnum):
    REQUEST = "request"
    APPROVAL = "approval"
    POLICY = "policy"
    CONTROL = "control"
    EXCEPTION = "exception"
    ENACTMENT = "enactment"
    AUDIT = "audit"


class AuthorityGovernanceCaseKind(StrEnum):
    PROPERLY_APPROVED_GRANT = "properly_approved_grant"
    WRONG_APPROVER = "wrong_approver"
    APPROVED_SCOPE_DIFFERS = "approved_scope_differs"
    DENIED_REQUEST_ENACTED = "denied_request_enacted"
    VALID_EMERGENCY_EXCEPTION = "valid_emergency_exception"
    EXPIRED_APPROVER_AUTHORITY = "expired_approver_authority"
    POLICY_CHANGED_AFTER_DECISION = "policy_changed_after_decision"
    MISSING_RETAINED_APPROVAL_EVIDENCE = "missing_retained_approval_evidence"
    UNLINKED_SUPERSESSION = "unlinked_supersession"
    REVOCATION_EFFECTIVE_TIME_DRIFT = "revocation_effective_time_drift"
    CONFLICTING_DECISIONS = "conflicting_decisions"
    UNAUTHORISED_WELL_FORMED_CHANGE = "unauthorised_well_formed_change"


class GovernanceMetricFamily(StrEnum):
    STATE = "state"
    GOVERNANCE_AUTHORITY = "governance_authority"
    POLICY_RATIONALE = "policy_rationale"
    EVIDENCE_OBSERVABILITY = "evidence_observability"
    ENACTMENT = "enactment"


class GovernedAuthorityV1(SyntheticModel):
    authority_id: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    capability_id: str = Field(min_length=1)
    resource_id: str = Field(min_length=1)
    actions: tuple[str, ...] = Field(min_length=1)
    scopes: tuple[str, ...] = Field(min_length=1)
    purpose: str = Field(min_length=1)
    valid_from_tick: int = Field(ge=0)
    valid_until_tick: int | None = Field(default=None, ge=0)

    @field_validator("actions", "scopes")
    @classmethod
    def canonical_members(
        cls, value: tuple[str, ...], info: ValidationInfo
    ) -> tuple[str, ...]:
        return _canonical_strings(value, f"governed authority {info.field_name}")

    @model_validator(mode="after")
    def forward_validity(self) -> Self:
        if (
            self.valid_until_tick is not None
            and self.valid_until_tick <= self.valid_from_tick
        ):
            raise ValueError("governed authority validity must be forward")
        return self


class AuthorityStateV1(SyntheticModel):
    authorities: tuple[GovernedAuthorityV1, ...] = ()

    @field_validator("authorities")
    @classmethod
    def canonical_authorities(
        cls, value: tuple[GovernedAuthorityV1, ...]
    ) -> tuple[GovernedAuthorityV1, ...]:
        identifiers = tuple(item.authority_id for item in value)
        if identifiers != tuple(sorted(set(identifiers))):
            raise ValueError("authority state must be sorted and unique")
        return value


class GovernancePolicyRuleV1(SyntheticModel):
    rule_id: str = Field(min_length=1)
    effect: GovernancePolicyEffect
    change_types: tuple[AuthorityChangeType, ...] = Field(min_length=1)
    approver_ids: tuple[str, ...] = Field(min_length=1)
    rationale_codes: tuple[str, ...] = Field(min_length=1)
    required_evidence_kinds: tuple[GovernanceEvidenceKind, ...] = Field(min_length=1)
    control_ids: tuple[str, ...] = Field(min_length=1)
    exception_ids: tuple[str, ...] = ()

    @field_validator("change_types", "required_evidence_kinds")
    @classmethod
    def canonical_enums(cls, value: tuple[StrEnum, ...]) -> tuple[StrEnum, ...]:
        if value != tuple(sorted(set(value), key=str)):
            raise ValueError("governance policy enum members must be sorted and unique")
        return value

    @field_validator("approver_ids", "rationale_codes", "control_ids", "exception_ids")
    @classmethod
    def canonical_strings(
        cls, value: tuple[str, ...], info: ValidationInfo
    ) -> tuple[str, ...]:
        return _canonical_strings(value, f"governance policy {info.field_name}")


class GovernancePolicyVersionV1(SyntheticModel):
    policy_version_id: str = Field(min_length=1)
    active_from_tick: int = Field(ge=0)
    inactive_from_tick: int | None = Field(default=None, ge=0)
    rules: tuple[GovernancePolicyRuleV1, ...] = Field(min_length=1)

    @field_validator("rules")
    @classmethod
    def canonical_rules(
        cls, value: tuple[GovernancePolicyRuleV1, ...]
    ) -> tuple[GovernancePolicyRuleV1, ...]:
        identifiers = tuple(item.rule_id for item in value)
        if identifiers != tuple(sorted(set(identifiers))):
            raise ValueError("governance policy rules must be sorted and unique")
        return value

    @model_validator(mode="after")
    def forward_activation(self) -> Self:
        if (
            self.inactive_from_tick is not None
            and self.inactive_from_tick <= self.active_from_tick
        ):
            raise ValueError("governance policy activation must be forward")
        return self


class ApproverMandateV1(SyntheticModel):
    mandate_id: str = Field(min_length=1)
    approver_principal_id: str = Field(min_length=1)
    valid_from_tick: int = Field(ge=0)
    valid_until_tick: int | None = Field(default=None, ge=0)
    change_types: tuple[AuthorityChangeType, ...] = Field(min_length=1)
    affected_authority_ids: tuple[str, ...] = Field(min_length=1)

    @field_validator("change_types")
    @classmethod
    def canonical_change_types(
        cls, value: tuple[AuthorityChangeType, ...]
    ) -> tuple[AuthorityChangeType, ...]:
        if value != tuple(sorted(set(value), key=str)):
            raise ValueError("mandate change types must be sorted and unique")
        return value

    @field_validator("affected_authority_ids")
    @classmethod
    def canonical_targets(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_strings(value, "mandate affected authorities")

    @model_validator(mode="after")
    def forward_validity(self) -> Self:
        if (
            self.valid_until_tick is not None
            and self.valid_until_tick <= self.valid_from_tick
        ):
            raise ValueError("approver mandate validity must be forward")
        return self


class GovernanceEvidenceRecordV1(SyntheticModel):
    evidence_ref: str = Field(min_length=1)
    kind: GovernanceEvidenceKind
    available_from_tick: int = Field(ge=0)
    retained_until_tick: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def forward_retention(self) -> Self:
        if (
            self.retained_until_tick is not None
            and self.retained_until_tick <= self.available_from_tick
        ):
            raise ValueError("governance evidence retention must be forward")
        return self


class _GovernanceEventBaseV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = AUTHORITY_GOVERNANCE_SCHEMA_VERSION
    id: str = Field(min_length=1)
    effective_tick: int = Field(ge=0)
    authority_change_id: str = Field(min_length=1)


class GovernanceRequestEventV1(_GovernanceEventBaseV1):
    event_type: Literal["request"] = "request"
    change_type: AuthorityChangeType
    affected_authority_id: str = Field(min_length=1)
    requester_principal_id: str = Field(min_length=1)
    observed_before_state: AuthorityStateV1
    requested_after_state: AuthorityStateV1
    supersedes_authority_change_id: str | None = Field(default=None, min_length=1)


class GovernanceDecisionEventV1(_GovernanceEventBaseV1):
    event_type: Literal["decision"] = "decision"
    decision_id: str = Field(min_length=1)
    outcome: GovernanceDecisionOutcome
    approval_chain: tuple[str, ...] = Field(min_length=1)
    accountable_owner_chain: tuple[str, ...] = Field(min_length=1)
    approved_after_state: AuthorityStateV1
    policy_version_id: str = Field(min_length=1)
    policy_rule_ids: tuple[str, ...] = Field(min_length=1)
    control_ids: tuple[str, ...] = Field(min_length=1)
    rationale_code: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    exception_id: str | None = Field(default=None, min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    mandate_ids: tuple[str, ...] = ()

    @field_validator(
        "approval_chain",
        "accountable_owner_chain",
        "policy_rule_ids",
        "control_ids",
        "evidence_refs",
        "mandate_ids",
    )
    @classmethod
    def canonical_references(
        cls, value: tuple[str, ...], info: ValidationInfo
    ) -> tuple[str, ...]:
        return _canonical_strings(value, f"governance decision {info.field_name}")


class GovernanceEnactmentEventV1(_GovernanceEventBaseV1):
    event_type: Literal["enactment"] = "enactment"
    decision_id: str = Field(min_length=1)
    enacted_after_state: AuthorityStateV1


class GovernanceAuditEventV1(_GovernanceEventBaseV1):
    event_type: Literal["audit"] = "audit"
    retained_evidence_refs: tuple[str, ...]

    @field_validator("retained_evidence_refs")
    @classmethod
    def canonical_evidence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_strings(value, "governance audit retained evidence")


AuthorityGovernanceEventV1 = Annotated[
    GovernanceRequestEventV1
    | GovernanceDecisionEventV1
    | GovernanceEnactmentEventV1
    | GovernanceAuditEventV1,
    Field(discriminator="event_type"),
]


class AuthorityGovernanceCaseV1(SyntheticModel):
    authority_change_id: str = Field(min_length=1)
    request_event_id: str = Field(min_length=1)
    decision_event_ids: tuple[str, ...] = Field(min_length=1)
    enactment_event_id: str = Field(min_length=1)
    audit_event_id: str = Field(min_length=1)

    @field_validator("decision_event_ids")
    @classmethod
    def canonical_decisions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_strings(value, "governance case decisions")


class AuthorityGovernancePublicV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = AUTHORITY_GOVERNANCE_SCHEMA_VERSION
    benchmark_family: Literal["authority_governance"] = "authority_governance"
    benchmark_version: Literal["1.0.0"] = AUTHORITY_GOVERNANCE_BENCHMARK_VERSION
    event_schedule_version: str = Field(min_length=1)
    policies: tuple[GovernancePolicyVersionV1, ...] = Field(min_length=1)
    approver_mandates: tuple[ApproverMandateV1, ...] = Field(min_length=1)
    evidence: tuple[GovernanceEvidenceRecordV1, ...] = Field(min_length=1)
    initial_state: AuthorityStateV1
    cases: tuple[AuthorityGovernanceCaseV1, ...] = Field(min_length=1)
    events: tuple[AuthorityGovernanceEventV1, ...] = Field(min_length=1)
    schedule: tuple[TemporalEventEnvelopeV2, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def canonical_inventories(self) -> Self:
        _require_model_order(self.policies, "policy_version_id", "governance policies")
        _require_model_order(
            self.approver_mandates, "mandate_id", "governance mandates"
        )
        _require_model_order(self.evidence, "evidence_ref", "governance evidence")
        _require_model_order(self.cases, "authority_change_id", "governance cases")
        event_keys = tuple((item.effective_tick, item.id) for item in self.events)
        if event_keys != tuple(sorted(set(event_keys))):
            raise ValueError("governance events must be canonically ordered and unique")
        return self


class AuthorityGovernanceTruthRowV1(SyntheticModel):
    authority_change_id: str = Field(min_length=1)
    case_kind: AuthorityGovernanceCaseKind
    change_type: AuthorityChangeType
    canonical_before_state: AuthorityStateV1
    canonical_after_state: AuthorityStateV1
    governance_decision_authorised: bool
    approver_authorised_at_decision: bool
    canonical_requester_principal_id: str = Field(min_length=1)
    canonical_approval_chain: tuple[str, ...] = Field(min_length=1)
    canonical_accountable_owner_chain: tuple[str, ...] = Field(min_length=1)
    applicable_policy_version_id: str = Field(min_length=1)
    applicable_policy_rule_ids: tuple[str, ...] = Field(min_length=1)
    applicable_control_ids: tuple[str, ...] = Field(min_length=1)
    expected_rationale_code: str = Field(min_length=1)
    expected_exception_id: str | None = Field(default=None, min_length=1)
    required_decision_evidence_refs: tuple[str, ...] = Field(min_length=1)
    controlling_decision_id: str = Field(min_length=1)
    expected_decision_outcome: GovernanceDecisionOutcome
    expected_effective_tick: int = Field(ge=0)
    superseded_authority_change_id: str | None = Field(default=None, min_length=1)
    enactment_consistent: bool
    audit_reconstructable: bool
    failure_reasons: tuple[str, ...]

    @field_validator(
        "canonical_approval_chain",
        "canonical_accountable_owner_chain",
        "applicable_policy_rule_ids",
        "applicable_control_ids",
        "required_decision_evidence_refs",
        "failure_reasons",
    )
    @classmethod
    def canonical_truth_references(
        cls, value: tuple[str, ...], info: ValidationInfo
    ) -> tuple[str, ...]:
        return _canonical_strings(value, f"governance truth {info.field_name}")


class AuthorityGovernanceEvaluatorV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = AUTHORITY_GOVERNANCE_SCHEMA_VERSION
    public_digest: SyntheticDigestV1
    truth: tuple[AuthorityGovernanceTruthRowV1, ...] = Field(min_length=1)

    @field_validator("truth")
    @classmethod
    def canonical_truth(
        cls, value: tuple[AuthorityGovernanceTruthRowV1, ...]
    ) -> tuple[AuthorityGovernanceTruthRowV1, ...]:
        _require_model_order(value, "authority_change_id", "governance truth")
        return value


class AuthorityGovernancePredictionRowV1(SyntheticModel):
    authority_change_id: str = Field(min_length=1)
    change_type: AuthorityChangeType
    canonical_before_state: AuthorityStateV1
    canonical_after_state: AuthorityStateV1
    governance_decision_authorised: bool
    approver_authorised_at_decision: bool
    requester_principal_id: str = Field(min_length=1)
    approval_chain: tuple[str, ...] = Field(min_length=1)
    accountable_owner_chain: tuple[str, ...] = Field(min_length=1)
    policy_version_id: str = Field(min_length=1)
    policy_rule_ids: tuple[str, ...] = Field(min_length=1)
    control_ids: tuple[str, ...] = Field(min_length=1)
    rationale_code: str = Field(min_length=1)
    exception_id: str | None = Field(default=None, min_length=1)
    decision_evidence_refs: tuple[str, ...] = Field(min_length=1)
    controlling_decision_id: str = Field(min_length=1)
    decision_outcome: GovernanceDecisionOutcome
    effective_tick: int = Field(ge=0)
    superseded_authority_change_id: str | None = Field(default=None, min_length=1)
    enactment_consistent: bool
    audit_reconstructable: bool

    @field_validator(
        "approval_chain",
        "accountable_owner_chain",
        "policy_rule_ids",
        "control_ids",
        "decision_evidence_refs",
    )
    @classmethod
    def canonical_prediction_references(
        cls, value: tuple[str, ...], info: ValidationInfo
    ) -> tuple[str, ...]:
        return _canonical_strings(value, f"governance prediction {info.field_name}")


class AuthorityGovernancePredictionV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = AUTHORITY_GOVERNANCE_SCHEMA_VERSION
    rows: tuple[AuthorityGovernancePredictionRowV1, ...] = Field(min_length=1)

    @field_validator("rows")
    @classmethod
    def canonical_rows(
        cls, value: tuple[AuthorityGovernancePredictionRowV1, ...]
    ) -> tuple[AuthorityGovernancePredictionRowV1, ...]:
        _require_model_order(value, "authority_change_id", "governance predictions")
        return value


class AuthorityGovernanceCaseFindingV1(SyntheticModel):
    authority_change_id: str = Field(min_length=1)
    state_correct: bool
    governance_authority_correct: bool
    policy_rationale_correct: bool
    evidence_observability_correct: bool
    enactment_correct: bool


class AuthorityGovernanceMetricV1(SyntheticModel):
    family: GovernanceMetricFamily
    name: str = Field(min_length=1)
    value: float
    numerator: int = Field(ge=0)
    denominator: int = Field(gt=0)
    support: int = Field(ge=0)
    denominator_meaning: str = Field(min_length=1)

    @model_validator(mode="after")
    def exact_ratio(self) -> Self:
        if self.numerator > self.denominator or self.support > self.denominator:
            raise ValueError("governance metric counts exceed the denominator")
        if not math.isclose(
            self.value,
            self.numerator / self.denominator,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise ValueError("governance metric value differs from its ratio")
        return self


class AuthorityGovernanceReportV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = AUTHORITY_GOVERNANCE_SCHEMA_VERSION
    scoring_version: Literal["1.0.0"] = AUTHORITY_GOVERNANCE_SCORING_VERSION
    findings: tuple[AuthorityGovernanceCaseFindingV1, ...] = Field(min_length=1)
    metrics: tuple[AuthorityGovernanceMetricV1, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def canonical_results(self) -> Self:
        _require_model_order(
            self.findings, "authority_change_id", "governance findings"
        )
        keys = tuple((item.family.value, item.name) for item in self.metrics)
        if keys != tuple(sorted(set(keys))):
            raise ValueError("governance metrics must be sorted and unique")
        return self


def _canonical_strings(value: tuple[str, ...], description: str) -> tuple[str, ...]:
    if any(not item.strip() for item in value):
        raise ValueError(f"{description} must be nonblank")
    if value != tuple(sorted(set(value))):
        raise ValueError(f"{description} must be sorted and unique")
    return value


def _require_model_order(
    values: tuple[object, ...], attribute: str, description: str
) -> None:
    keys = tuple(str(getattr(item, attribute)) for item in values)
    if keys != tuple(sorted(set(keys))):
        raise ValueError(f"{description} must be sorted and unique")


__all__ = [
    "AUTHORITY_GOVERNANCE_BENCHMARK_VERSION",
    "AUTHORITY_GOVERNANCE_SCHEMA_VERSION",
    "AUTHORITY_GOVERNANCE_SCORING_VERSION",
    "ApproverMandateV1",
    "AuthorityChangeType",
    "AuthorityGovernanceCaseFindingV1",
    "AuthorityGovernanceCaseKind",
    "AuthorityGovernanceCaseV1",
    "AuthorityGovernanceEvaluatorV1",
    "AuthorityGovernanceEventV1",
    "AuthorityGovernanceMetricV1",
    "AuthorityGovernancePredictionRowV1",
    "AuthorityGovernancePredictionV1",
    "AuthorityGovernancePublicV1",
    "AuthorityGovernanceReportV1",
    "AuthorityGovernanceTruthRowV1",
    "AuthorityStateV1",
    "GovernanceAuditEventV1",
    "GovernanceDecisionEventV1",
    "GovernanceDecisionOutcome",
    "GovernanceEnactmentEventV1",
    "GovernanceEvidenceKind",
    "GovernanceEvidenceRecordV1",
    "GovernanceMetricFamily",
    "GovernancePolicyEffect",
    "GovernancePolicyRuleV1",
    "GovernancePolicyVersionV1",
    "GovernanceRequestEventV1",
    "GovernedAuthorityV1",
]
