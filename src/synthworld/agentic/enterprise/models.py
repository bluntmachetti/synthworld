"""Public input, evaluator truth, trace, and metric contracts for PR6."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Protocol, Self, cast

from pydantic import Field, ValidationInfo, field_validator, model_validator

from synthworld.agentic.enterprise.common import (
    ENTERPRISE_AGENTIC_AIIM_PROFILE_VERSION,
    ENTERPRISE_AGENTIC_AIIM_SOURCE_ID,
    ENTERPRISE_AGENTIC_BENCHMARK_SCHEMA_VERSION,
    ENTERPRISE_AGENTIC_COMPILER_VERSION,
    ENTERPRISE_AGENTIC_CONFIG_SCHEMA_VERSION,
    ENTERPRISE_AGENTIC_METRICS_SCHEMA_VERSION,
    ENTERPRISE_AGENTIC_PREDICTION_SCHEMA_VERSION,
    ENTERPRISE_AGENTIC_PROFILE_VERSION,
    ENTERPRISE_AGENTIC_PUBLIC_INPUT_SCHEMA_VERSION,
    ENTERPRISE_AGENTIC_TRACE_VALIDATION_SCHEMA_VERSION,
    ENTERPRISE_AGENTIC_TRUTH_SCHEMA_VERSION,
)
from synthworld.enterprise.abac.models import (
    CompiledEnterpriseAbacTruthV1,
    EnterpriseAbacIntentOverlayV1,
    EnterpriseAbacStateOverlayV1,
)
from synthworld.enterprise.authorization.models import (
    AuthorizationEvaluationProfileV1,
    CompiledEnterpriseAccessStateV1,
    EnterpriseAuthorizationCompositionV1,
    EnterpriseAuthorizationKernelV1,
)
from synthworld.enterprise.canonical import (
    canonical_json_bytes,
    canonical_json_value_bytes,
    synthetic_digest,
)
from synthworld.enterprise.models import (
    EnterpriseCanonicalBindingTruthV1,
    EnterpriseIdentityAccessUniverseV1,
    EnterpriseOperatorModel,
    SyntheticDigestV1,
)
from synthworld.enterprise.rbac.common import (
    AuthorizationDecision,
    canonical_operator_records,
    canonical_strings,
    canonical_synthetic_records,
)
from synthworld.enterprise.rbac.corpus_models import EnterpriseEvaluationCorpusV1
from synthworld.enterprise.rbac.metrics import EnterpriseAuthorizationMetricV1
from synthworld.enterprise.rbac.models import (
    CompiledEnterpriseDirectoryRbacTruthV1,
    EnterpriseDirectoryRbacIntentOverlayV1,
    EnterpriseDirectoryRbacKernelV1,
    EnterpriseRbacSessionStateInputV1,
)
from synthworld.enterprise.rebac.models import (
    CompiledEnterpriseRebacTruthV1,
    EnterpriseRebacIntentOverlayV1,
    EnterpriseRebacStateOverlayV1,
)
from synthworld.models import SyntheticModel


class EnterpriseAgenticTier(StrEnum):
    SMOKE = "smoke"


class AgentAuthorizationMappingKind(StrEnum):
    AGENT_AS_PRINCIPAL = "agent_as_principal"
    HUMAN_SUBJECT_AGENT_CONTEXT = "human_subject_agent_context"


class AgenticAdministrativeState(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DISABLED = "disabled"


class AgenticGateOutcome(StrEnum):
    SATISFIED = "satisfied"
    UNSATISFIED = "unsatisfied"
    NOT_APPLICABLE = "not_applicable"


class AgenticFailureReason(StrEnum):
    ENTERPRISE_DENIED = "enterprise_denied"
    SUBJECT_MISMATCH = "subject_mismatch"
    TENANT_MISMATCH = "tenant_mismatch"
    AGENT_ACCOUNT_INACTIVE = "agent_account_inactive"
    AGENT_ACCOUNT_BINDING_MISMATCH = "agent_account_binding_mismatch"
    WRONG_RUNTIME = "wrong_runtime"
    CREDENTIAL_INVALID = "credential_invalid"
    CAPABILITY_EXCEEDED = "capability_exceeded"
    NO_ACTIVE_DELEGATION = "no_active_delegation"
    DELEGATION_MISMATCH = "delegation_mismatch"


class EnterpriseAgenticCaseKind(StrEnum):
    VALID_AGENT_PRINCIPAL = "valid_agent_principal"
    ENTERPRISE_DENIED_AGENT = "enterprise_denied_agent"
    HUMAN_AUTHORITY_NOT_UNIONED = "human_authority_not_unioned"
    WRONG_SUBJECT_AGENT = "wrong_subject_agent"
    WRONG_RUNTIME_AGENT = "wrong_runtime_agent"
    INVALID_CREDENTIAL_AGENT = "invalid_credential_agent"
    SHARED_CREDENTIAL_AGENT = "shared_credential_agent"
    WRONG_SCOPE_AGENT = "wrong_scope_agent"
    CROSS_TENANT_AGENT = "cross_tenant_agent"
    SUSPENDED_AGENT_ACCOUNT = "suspended_agent_account"
    VALID_HUMAN_CONTEXT = "valid_human_context"
    ENTERPRISE_DENIED_HUMAN = "enterprise_denied_human"
    SAME_HUMAN_DIFFERENT_AGENT = "same_human_different_agent"
    SAME_AGENT_DIFFERENT_HUMAN = "same_agent_different_human"
    MISSING_DELEGATION = "missing_delegation"
    REVOKED_DELEGATION = "revoked_delegation"
    WRONG_RUNTIME_HUMAN = "wrong_runtime_human"
    WRONG_SCOPE_HUMAN = "wrong_scope_human"
    CROSS_TENANT_HUMAN = "cross_tenant_human"
    EVIDENCE_DISCARDED = "evidence_discarded"


class _Identified(Protocol):
    id: str


class _CaseIdentified(Protocol):
    case_id: str


class EnterpriseAgenticProjectionLimitsV1(EnterpriseOperatorModel):
    max_accounts: int = Field(default=64, gt=0, le=10_000)
    max_runtimes: int = Field(default=64, gt=0, le=10_000)
    max_credentials: int = Field(default=128, gt=0, le=20_000)
    max_capabilities: int = Field(default=128, gt=0, le=20_000)
    max_delegations: int = Field(default=128, gt=0, le=20_000)
    max_events: int = Field(default=512, gt=0, le=100_000)
    max_cases: int = Field(default=128, gt=0, le=20_000)


class EnterpriseAgenticProjectionConfigV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = ENTERPRISE_AGENTIC_CONFIG_SCHEMA_VERSION
    seed: int
    tier: Literal[EnterpriseAgenticTier.SMOKE] = EnterpriseAgenticTier.SMOKE
    limits: EnterpriseAgenticProjectionLimitsV1 = Field(
        default_factory=EnterpriseAgenticProjectionLimitsV1
    )


class EnterpriseAgenticAccessPublicInputV1(EnterpriseOperatorModel):
    """Everything public needed to evaluate immutable enterprise decision ``F``."""

    universe: EnterpriseIdentityAccessUniverseV1
    corpus: EnterpriseEvaluationCorpusV1
    directory_rbac_kernel: EnterpriseDirectoryRbacKernelV1
    directory_rbac_intent: EnterpriseDirectoryRbacIntentOverlayV1
    rbac_session_state: EnterpriseRbacSessionStateInputV1
    abac_state: EnterpriseAbacStateOverlayV1
    abac_intent: EnterpriseAbacIntentOverlayV1
    rebac_state: EnterpriseRebacStateOverlayV1
    rebac_intent: EnterpriseRebacIntentOverlayV1
    composition: EnterpriseAuthorizationCompositionV1
    evaluation_profile: AuthorizationEvaluationProfileV1
    authorization_kernel: EnterpriseAuthorizationKernelV1


class EnterpriseAgentAccountV1(SyntheticModel):
    id: str
    tenant_id: str
    agent_principal_id: str
    administrative_state: AgenticAdministrativeState
    valid_from_tick: int = Field(ge=0)
    valid_until_tick: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def valid_interval(self) -> Self:
        if (
            self.valid_until_tick is not None
            and self.valid_until_tick <= self.valid_from_tick
        ):
            raise ValueError("enterprise_agent_account_validity_interval_invalid")
        return self


class EnterpriseAgentRuntimeV1(SyntheticModel):
    id: str
    tenant_id: str
    agent_principal_id: str
    agent_account_id: str


class EnterpriseAgentCredentialV1(SyntheticModel):
    id: str
    opaque_handle: str
    tenant_id: str
    agent_principal_id: str
    agent_account_id: str
    allowed_runtime_ids: tuple[str, ...] = Field(min_length=1)
    valid_from_tick: int = Field(ge=0)
    valid_until_tick: int | None = Field(default=None, ge=0)

    @field_validator("allowed_runtime_ids")
    @classmethod
    def canonical_runtimes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "enterprise_agentic_credential_runtime_id")

    @model_validator(mode="after")
    def valid_interval(self) -> Self:
        if (
            self.valid_until_tick is not None
            and self.valid_until_tick <= self.valid_from_tick
        ):
            raise ValueError("enterprise_agent_credential_validity_interval_invalid")
        return self


class EnterpriseAgentCapabilityV1(SyntheticModel):
    id: str
    tenant_id: str
    agent_principal_id: str
    authorization_target_ids: tuple[str, ...] = Field(min_length=1)
    actions: tuple[str, ...] = Field(min_length=1)
    scopes: tuple[str, ...] = Field(min_length=1)

    @field_validator("authorization_target_ids", "actions", "scopes")
    @classmethod
    def canonical_members(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "enterprise_agentic_capability_member")


class EnterpriseAgentDelegationV1(SyntheticModel):
    id: str
    tenant_id: str
    human_principal_id: str
    agent_principal_id: str
    agent_account_id: str
    capability_id: str
    valid_from_tick: int = Field(ge=0)
    valid_until_tick: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def valid_interval(self) -> Self:
        if (
            self.valid_until_tick is not None
            and self.valid_until_tick <= self.valid_from_tick
        ):
            raise ValueError("enterprise_agent_delegation_validity_interval_invalid")
        return self


class EnterpriseAgenticSnapshotV1(SyntheticModel):
    accounts: tuple[EnterpriseAgentAccountV1, ...]
    runtimes: tuple[EnterpriseAgentRuntimeV1, ...]
    credentials: tuple[EnterpriseAgentCredentialV1, ...]
    capabilities: tuple[EnterpriseAgentCapabilityV1, ...]
    delegations: tuple[EnterpriseAgentDelegationV1, ...]
    initial_evidence_refs: tuple[str, ...]

    @field_validator(
        "accounts", "runtimes", "credentials", "capabilities", "delegations"
    )
    @classmethod
    def canonical_records(
        cls, value: tuple[SyntheticModel, ...], info: ValidationInfo
    ) -> tuple[SyntheticModel, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((cast(_Identified, item).id,) for item in value),
            description=f"enterprise_agentic_{info.field_name}_id",
        )

    @field_validator("initial_evidence_refs")
    @classmethod
    def canonical_evidence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "enterprise_agentic_initial_evidence_ref")


class AgentAsPrincipalV1(SyntheticModel):
    mapping_kind: Literal[AgentAuthorizationMappingKind.AGENT_AS_PRINCIPAL] = (
        AgentAuthorizationMappingKind.AGENT_AS_PRINCIPAL
    )
    enterprise_subject_id: str
    agent_principal_id: str
    agent_account_id: str
    runtime_id: str
    owner_human_principal_id: str | None = None
    provenance_delegation_id: str | None = None


class HumanSubjectAgentContextV1(SyntheticModel):
    mapping_kind: Literal[AgentAuthorizationMappingKind.HUMAN_SUBJECT_AGENT_CONTEXT] = (
        AgentAuthorizationMappingKind.HUMAN_SUBJECT_AGENT_CONTEXT
    )
    enterprise_subject_id: str
    human_principal_id: str
    agent_principal_id: str
    agent_account_id: str
    runtime_id: str
    delegation_id: str | None = None


AgentAuthorizationMappingProfileV1 = Annotated[
    AgentAsPrincipalV1 | HumanSubjectAgentContextV1,
    Field(discriminator="mapping_kind"),
]


class EnterpriseAgenticActionAttemptV1(SyntheticModel):
    case_id: str
    access_request_id: str
    cell_id: str
    access_atom_id: str
    mapping: AgentAuthorizationMappingProfileV1
    credential_id: str
    capability_id: str
    authorization_target_id: str
    action: str
    requested_scopes: tuple[str, ...] = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)

    @field_validator("requested_scopes", "evidence_refs")
    @classmethod
    def canonical_strings_fields(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "enterprise_agentic_attempt_member")


class EnterpriseAgenticActionAttemptedV1(SyntheticModel):
    event_type: Literal["action_attempted"] = "action_attempted"
    attempt: EnterpriseAgenticActionAttemptV1


class EnterpriseAgenticCredentialRevokedV1(SyntheticModel):
    event_type: Literal["credential_revoked"] = "credential_revoked"
    credential_id: str


class EnterpriseAgenticDelegationRevokedV1(SyntheticModel):
    event_type: Literal["delegation_revoked"] = "delegation_revoked"
    delegation_id: str


class EnterpriseAgenticEvidenceDiscardedV1(SyntheticModel):
    event_type: Literal["evidence_discarded"] = "evidence_discarded"
    evidence_refs: tuple[str, ...] = Field(min_length=1)

    @field_validator("evidence_refs")
    @classmethod
    def canonical_evidence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "enterprise_agentic_discarded_evidence_ref")


class EnterpriseAgenticAuditPerformedV1(SyntheticModel):
    event_type: Literal["audit_performed"] = "audit_performed"
    audit_id: str


EnterpriseAgenticEventPayloadV1 = Annotated[
    EnterpriseAgenticActionAttemptedV1
    | EnterpriseAgenticCredentialRevokedV1
    | EnterpriseAgenticDelegationRevokedV1
    | EnterpriseAgenticEvidenceDiscardedV1
    | EnterpriseAgenticAuditPerformedV1,
    Field(discriminator="event_type"),
]


class EnterpriseAgenticEventV1(SyntheticModel):
    id: str
    tick: int = Field(ge=0)
    payload: EnterpriseAgenticEventPayloadV1


class EnterpriseAgenticReplayStateV1(SyntheticModel):
    processed_event_ids: tuple[str, ...]
    revoked_credential_ids: tuple[str, ...]
    revoked_delegation_ids: tuple[str, ...]
    discarded_evidence_refs: tuple[str, ...]
    action_event_ids: tuple[str, ...]
    audit_event_ids: tuple[str, ...]

    @field_validator(
        "revoked_credential_ids",
        "revoked_delegation_ids",
        "discarded_evidence_refs",
        "action_event_ids",
        "audit_event_ids",
    )
    @classmethod
    def canonical_sets(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "enterprise_agentic_replay_member")


class EnterpriseAgenticCaseReferenceV1(SyntheticModel):
    case_id: str
    action_event_id: str
    mapping_kind: AgentAuthorizationMappingKind


class EnterpriseAgenticBenchmarkV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = ENTERPRISE_AGENTIC_BENCHMARK_SCHEMA_VERSION
    compiler_version: Literal["1.0.0"] = ENTERPRISE_AGENTIC_COMPILER_VERSION
    profile_version: Literal["enterprise-agentic-smoke-1.0.0"] = (
        ENTERPRISE_AGENTIC_PROFILE_VERSION
    )
    aiim_source_id: Literal["openid-aiim-mcp-interop-2026-07-14"] = (
        ENTERPRISE_AGENTIC_AIIM_SOURCE_ID
    )
    aiim_profile_version: Literal["0.1.0-experimental"] = (
        ENTERPRISE_AGENTIC_AIIM_PROFILE_VERSION
    )
    seed: int
    tier: Literal[EnterpriseAgenticTier.SMOKE] = EnterpriseAgenticTier.SMOKE
    config_digest: SyntheticDigestV1
    identity_access_universe_digest: SyntheticDigestV1
    evaluation_corpus_digest: SyntheticDigestV1
    access_input_digest: SyntheticDigestV1
    snapshot_digest: SyntheticDigestV1
    events_digest: SyntheticDigestV1
    audit_event_id: str
    cases: tuple[EnterpriseAgenticCaseReferenceV1, ...] = Field(min_length=1)

    @field_validator("cases")
    @classmethod
    def canonical_cases(
        cls, value: tuple[EnterpriseAgenticCaseReferenceV1, ...]
    ) -> tuple[EnterpriseAgenticCaseReferenceV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.case_id,) for item in value),
            description="enterprise_agentic_case_id",
        )


class EnterpriseAgenticPublicInputV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = ENTERPRISE_AGENTIC_PUBLIC_INPUT_SCHEMA_VERSION
    config: EnterpriseAgenticProjectionConfigV1
    access: EnterpriseAgenticAccessPublicInputV1
    snapshot: EnterpriseAgenticSnapshotV1
    events: tuple[EnterpriseAgenticEventV1, ...]
    benchmark: EnterpriseAgenticBenchmarkV1

    @field_validator("events")
    @classmethod
    def canonical_events(
        cls, value: tuple[EnterpriseAgenticEventV1, ...]
    ) -> tuple[EnterpriseAgenticEventV1, ...]:
        ordered = tuple(sorted(value, key=lambda item: (item.tick, item.id)))
        if len({item.id for item in ordered}) != len(ordered):
            raise ValueError("duplicate_enterprise_agentic_event_id")
        return ordered

    @model_validator(mode="after")
    def benchmark_binds_public_inputs(self) -> Self:
        expected = (
            synthetic_digest(canonical_json_bytes(self.config)),
            synthetic_digest(canonical_json_bytes(self.access)),
            synthetic_digest(canonical_json_bytes(self.snapshot)),
            synthetic_digest(canonical_json_bytes_value(self.events)),
        )
        actual = (
            self.benchmark.config_digest,
            self.benchmark.access_input_digest,
            self.benchmark.snapshot_digest,
            self.benchmark.events_digest,
        )
        if actual != expected:
            raise ValueError("enterprise_agentic_public_digest_binding_mismatch")
        return self


def canonical_json_bytes_value(value: tuple[SyntheticModel, ...]) -> bytes:
    """Serialize a generated tuple as one canonical JSON array."""

    return canonical_json_value_bytes([item.model_dump(mode="json") for item in value])


class AgenticExpectedDecisionV1(SyntheticModel):
    enterprise_decision: AuthorizationDecision
    subject_gate: AgenticGateOutcome
    tenant_gate: AgenticGateOutcome
    agent_account_gate: AgenticGateOutcome
    runtime_gate: AgenticGateOutcome
    credential_gate: AgenticGateOutcome
    capability_gate: AgenticGateOutcome
    delegation_gate: AgenticGateOutcome
    final_decision: AuthorizationDecision
    failure_reasons: tuple[AgenticFailureReason, ...]


class EnterpriseAgenticAttributionTruthV1(SyntheticModel):
    human_principal_id: str | None
    agent_principal_id: str
    agent_account_id: str
    runtime_id: str


class EnterpriseAgenticCaseTruthV1(SyntheticModel):
    case_id: str
    action_event_id: str
    expected_decision: AgenticExpectedDecisionV1
    attribution: EnterpriseAgenticAttributionTruthV1
    required_evidence_refs: tuple[str, ...]
    reconstructable_at_audit: bool

    @field_validator("required_evidence_refs")
    @classmethod
    def canonical_evidence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "enterprise_agentic_required_evidence_ref")


class EnterpriseAgenticCaseLabelV1(SyntheticModel):
    case_id: str
    kind: EnterpriseAgenticCaseKind
    scenario_tags: tuple[str, ...] = Field(min_length=1)

    @field_validator("scenario_tags")
    @classmethod
    def canonical_tags(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "enterprise_agentic_scenario_tag")


class EnterpriseAgenticTruthV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = ENTERPRISE_AGENTIC_TRUTH_SCHEMA_VERSION
    compiler_version: Literal["1.0.0"] = ENTERPRISE_AGENTIC_COMPILER_VERSION
    public_input_digest: SyntheticDigestV1
    benchmark_digest: SyntheticDigestV1
    access_state_digest: SyntheticDigestV1
    cases: tuple[EnterpriseAgenticCaseTruthV1, ...]
    case_labels: tuple[EnterpriseAgenticCaseLabelV1, ...]

    @field_validator("cases", "case_labels")
    @classmethod
    def canonical_truth(
        cls, value: tuple[SyntheticModel, ...], info: ValidationInfo
    ) -> tuple[SyntheticModel, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((cast(_CaseIdentified, item).case_id,) for item in value),
            description=f"enterprise_agentic_{info.field_name}_case_id",
        )


class EnterpriseAgenticEvaluatorArtifactsV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = ENTERPRISE_AGENTIC_TRUTH_SCHEMA_VERSION
    public_input_digest: SyntheticDigestV1
    canonical_binding_truth: EnterpriseCanonicalBindingTruthV1
    directory_rbac_truth: CompiledEnterpriseDirectoryRbacTruthV1
    abac_truth: CompiledEnterpriseAbacTruthV1
    rebac_truth: CompiledEnterpriseRebacTruthV1
    access_state: CompiledEnterpriseAccessStateV1
    truth: EnterpriseAgenticTruthV1

    @model_validator(mode="after")
    def truth_binds_artifacts(self) -> Self:
        if self.truth.public_input_digest != self.public_input_digest:
            raise ValueError("enterprise_agentic_truth_public_digest_mismatch")
        if self.truth.access_state_digest != synthetic_digest(
            canonical_json_bytes(self.access_state)
        ):
            raise ValueError("enterprise_agentic_truth_access_state_digest_mismatch")
        return self


class AgenticGatePredictionV1(EnterpriseOperatorModel):
    subject_gate: AgenticGateOutcome
    tenant_gate: AgenticGateOutcome
    agent_account_gate: AgenticGateOutcome
    runtime_gate: AgenticGateOutcome
    credential_gate: AgenticGateOutcome
    capability_gate: AgenticGateOutcome
    delegation_gate: AgenticGateOutcome


class EnterpriseAgenticTraceRowV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = ENTERPRISE_AGENTIC_PREDICTION_SCHEMA_VERSION
    benchmark_digest: SyntheticDigestV1
    case_id: str = Field(min_length=1)
    enterprise_decision: AuthorizationDecision
    gates: AgenticGatePredictionV1
    final_decision: AuthorizationDecision
    failure_reasons: tuple[AgenticFailureReason, ...]
    human_principal_id: str | None = Field(default=None, min_length=1)
    agent_principal_id: str = Field(min_length=1)
    agent_account_id: str = Field(min_length=1)
    runtime_id: str = Field(min_length=1)
    evidence_refs: tuple[str, ...]
    reconstructable_at_audit: bool

    @field_validator("evidence_refs")
    @classmethod
    def canonical_evidence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "predicted_enterprise_agentic_evidence_ref")


class EnterpriseAgenticPredictionV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = ENTERPRISE_AGENTIC_PREDICTION_SCHEMA_VERSION
    benchmark_digest: SyntheticDigestV1
    rows: tuple[EnterpriseAgenticTraceRowV1, ...] = Field(min_length=1)

    @field_validator("rows")
    @classmethod
    def canonical_rows(
        cls, value: tuple[EnterpriseAgenticTraceRowV1, ...]
    ) -> tuple[EnterpriseAgenticTraceRowV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple((item.case_id,) for item in value),
            description="enterprise_agentic_prediction_case_id",
        )

    @model_validator(mode="after")
    def rows_bind_benchmark(self) -> Self:
        if any(item.benchmark_digest != self.benchmark_digest for item in self.rows):
            raise ValueError("enterprise_agentic_prediction_row_digest_mismatch")
        return self


class EnterpriseAgenticMetricsV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = ENTERPRISE_AGENTIC_METRICS_SCHEMA_VERSION
    benchmark_digest: SyntheticDigestV1
    truth_digest: SyntheticDigestV1
    metrics: tuple[EnterpriseAuthorizationMetricV1, ...]

    @field_validator("metrics")
    @classmethod
    def canonical_metrics(
        cls, value: tuple[EnterpriseAuthorizationMetricV1, ...]
    ) -> tuple[EnterpriseAuthorizationMetricV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.family, item.name) for item in value),
            description="enterprise_agentic_metric_name",
        )


class EnterpriseAgenticTraceValidationIssueV1(SyntheticModel):
    severity: Literal["error", "warning"]
    code: str
    message: str
    line: int | None = Field(default=None, ge=1)
    case_id: str | None = None


class EnterpriseAgenticTraceValidationReportV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = (
        ENTERPRISE_AGENTIC_TRACE_VALIDATION_SCHEMA_VERSION
    )
    valid: bool
    row_count: int = Field(ge=0)
    expected_case_count: int = Field(ge=0)
    issues: tuple[EnterpriseAgenticTraceValidationIssueV1, ...]

    @model_validator(mode="after")
    def validity_matches_issues(self) -> Self:
        if self.valid is any(item.severity == "error" for item in self.issues):
            raise ValueError("enterprise_agentic_trace_validity_mismatch")
        return self


__all__ = [name for name in globals() if name.endswith("V1")]
