"""Separated contracts for adversarial enterprise authorization cases."""

from __future__ import annotations

from typing import Literal, Self, cast

from pydantic import Field, ValidationInfo, field_validator, model_validator

from synthworld.enterprise.abac.common import InformationClassification
from synthworld.enterprise.authorization.adversarial.common import (
    ADVERSARIAL_AUTHORIZATION_EVALUATOR_SCHEMA_VERSION,
    ADVERSARIAL_AUTHORIZATION_METRICS_SCHEMA_VERSION,
    ADVERSARIAL_AUTHORIZATION_PREDICTION_SCHEMA_VERSION,
    ADVERSARIAL_AUTHORIZATION_PROFILE_VERSION,
    ADVERSARIAL_AUTHORIZATION_PUBLIC_SCHEMA_VERSION,
    AdversarialAuthoritySource,
    AdversarialAuthorizationMechanism,
    AdversarialCaseCategory,
    AuthorityCombinationPolicy,
    TenantComparisonOperator,
)
from synthworld.enterprise.authorization_common import RuleEffect
from synthworld.enterprise.models import EnterpriseOperatorModel, SyntheticDigestV1
from synthworld.enterprise.rbac.common import (
    AuthorizationDecision,
    BindingStatus,
    canonical_operator_records,
    canonical_strings,
    canonical_synthetic_records,
)
from synthworld.enterprise.rbac.metrics import EnterpriseAuthorizationMetricV1
from synthworld.models import SyntheticModel


class AdversarialTenantRuleV1(SyntheticModel):
    rule_id: str = Field(min_length=1)
    operator: TenantComparisonOperator
    effect: RuleEffect


class EnterpriseAdversarialAuthorizationPolicyV1(SyntheticModel):
    """Bounded public policy semantics without vendor policy syntax."""

    authority_combination: Literal[AuthorityCombinationPolicy.RBAC_OR_REBAC] = (
        AuthorityCombinationPolicy.RBAC_OR_REBAC
    )
    default_tenant_decision: AuthorizationDecision
    tenant_rules: tuple[AdversarialTenantRuleV1, ...] = Field(min_length=1)
    scope_evaluation: Literal["requested_scope_must_be_granted"] = (
        "requested_scope_must_be_granted"
    )
    time_evaluation: Literal["half_open_grant_interval"] = "half_open_grant_interval"
    clearance_evaluation: Literal["principal_at_least_resource"] = (
        "principal_at_least_resource"
    )
    binding_evaluation: Literal["credential_evidence_resolves_principal"] = (
        "credential_evidence_resolves_principal"
    )

    @field_validator("tenant_rules")
    @classmethod
    def canonical_tenant_rules(
        cls, value: tuple[AdversarialTenantRuleV1, ...]
    ) -> tuple[AdversarialTenantRuleV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.rule_id,) for item in value),
            description="adversarial_tenant_rule_id",
        )


class AdversarialPrincipalV1(SyntheticModel):
    principal_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    directory_alias: str = Field(min_length=1)
    clearance: InformationClassification


class AdversarialCredentialEvidenceV1(SyntheticModel):
    credential_id: str = Field(min_length=1)
    issuer_subject_alias: str = Field(min_length=1)
    device_owner_alias: str = Field(min_length=1)


class AdversarialResourceV1(SyntheticModel):
    resource_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    resource_kind: str = Field(min_length=1)
    classification: InformationClassification


class AdversarialAuthorityGrantV1(SyntheticModel):
    grant_id: str = Field(min_length=1)
    principal_id: str = Field(min_length=1)
    resource_kind: str = Field(min_length=1)
    action: str = Field(min_length=1)
    allowed_scopes: tuple[str, ...] = Field(min_length=1)
    valid_from_tick: int = Field(ge=0)
    valid_until_tick: int = Field(gt=0)
    source: AdversarialAuthoritySource

    @field_validator("allowed_scopes")
    @classmethod
    def canonical_scopes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_strings(value, "adversarial_grant_scope")

    @model_validator(mode="after")
    def valid_interval(self) -> Self:
        if self.valid_until_tick <= self.valid_from_tick:
            raise ValueError("adversarial_grant_interval_not_positive")
        return self


class AdversarialActionAttemptV1(SyntheticModel):
    """A candidate action; cross-tenant attempts remain structurally valid."""

    attempt_id: str = Field(min_length=1)
    presented_principal_id: str = Field(min_length=1)
    credential_id: str = Field(min_length=1)
    resource_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    requested_scope: str = Field(min_length=1)
    tick: int = Field(ge=0)


class EnterpriseAdversarialAuthorizationPublicV1(SyntheticModel):
    """Public facts and attempts, without counterfactual labels or verdicts."""

    schema_version: Literal["1.0.0"] = ADVERSARIAL_AUTHORIZATION_PUBLIC_SCHEMA_VERSION
    profile_version: Literal["enterprise-authorization-adversarial-1.0.0"] = (
        ADVERSARIAL_AUTHORIZATION_PROFILE_VERSION
    )
    seed: int
    policy: EnterpriseAdversarialAuthorizationPolicyV1
    principals: tuple[AdversarialPrincipalV1, ...] = Field(min_length=1)
    credentials: tuple[AdversarialCredentialEvidenceV1, ...] = Field(min_length=1)
    resources: tuple[AdversarialResourceV1, ...] = Field(min_length=1)
    grants: tuple[AdversarialAuthorityGrantV1, ...] = Field(min_length=1)
    attempts: tuple[AdversarialActionAttemptV1, ...] = Field(min_length=1)

    @field_validator("principals", "credentials", "resources", "grants", "attempts")
    @classmethod
    def canonical_records(
        cls, value: tuple[SyntheticModel, ...], info: ValidationInfo
    ) -> tuple[SyntheticModel, ...]:
        field_name = cast(str, info.field_name)
        attribute = {
            "principals": "principal_id",
            "credentials": "credential_id",
            "resources": "resource_id",
            "grants": "grant_id",
            "attempts": "attempt_id",
        }[field_name]
        return canonical_synthetic_records(
            value,
            keys=tuple((cast(str, getattr(item, attribute)),) for item in value),
            description=f"adversarial_{field_name}_id",
        )

    @model_validator(mode="after")
    def references_are_closed(self) -> Self:
        principal_ids = {item.principal_id for item in self.principals}
        aliases = {item.directory_alias for item in self.principals}
        if len(aliases) != len(self.principals):
            raise ValueError("duplicate_adversarial_principal_alias")
        if any(
            item.issuer_subject_alias not in aliases
            or item.device_owner_alias not in aliases
            for item in self.credentials
        ):
            raise ValueError("unknown_adversarial_credential_alias")
        resource_ids = {item.resource_id for item in self.resources}
        resource_kinds = {item.resource_kind for item in self.resources}
        if any(
            item.principal_id not in principal_ids
            or item.resource_kind not in resource_kinds
            for item in self.grants
        ):
            raise ValueError("unknown_adversarial_grant_reference")
        credential_ids = {item.credential_id for item in self.credentials}
        if any(
            item.presented_principal_id not in principal_ids
            or item.credential_id not in credential_ids
            or item.resource_id not in resource_ids
            for item in self.attempts
        ):
            raise ValueError("unknown_adversarial_attempt_reference")
        return self


class AdversarialCredentialBindingTruthV1(SyntheticModel):
    credential_id: str = Field(min_length=1)
    principal_id: str = Field(min_length=1)


class AdversarialAttemptTruthV1(SyntheticModel):
    attempt_id: str = Field(min_length=1)
    pair_id: str = Field(min_length=1)
    mechanism: AdversarialAuthorizationMechanism
    category: AdversarialCaseCategory
    resolved_principal_id: str = Field(min_length=1)
    binding_status: BindingStatus
    expected_decision: AuthorizationDecision
    mechanism_ignored_decision: AuthorizationDecision
    identifier_probe: bool


class AdversarialCounterfactualPairTruthV1(SyntheticModel):
    pair_id: str = Field(min_length=1)
    mechanism: AdversarialAuthorizationMechanism
    category: AdversarialCaseCategory
    from_attempt_id: str = Field(min_length=1)
    to_attempt_id: str = Field(min_length=1)
    expected_transition: bool

    @model_validator(mode="after")
    def distinct_attempts(self) -> Self:
        if self.from_attempt_id == self.to_attempt_id:
            raise ValueError("adversarial_pair_attempts_must_differ")
        return self


class EnterpriseAdversarialAuthorizationEvaluatorV1(SyntheticModel):
    """Hidden bindings, pair labels, mechanisms, and expected decisions."""

    schema_version: Literal["1.0.0"] = (
        ADVERSARIAL_AUTHORIZATION_EVALUATOR_SCHEMA_VERSION
    )
    profile_version: Literal["enterprise-authorization-adversarial-1.0.0"] = (
        ADVERSARIAL_AUTHORIZATION_PROFILE_VERSION
    )
    public_digest: SyntheticDigestV1
    canonical_bindings: tuple[AdversarialCredentialBindingTruthV1, ...]
    cases: tuple[AdversarialAttemptTruthV1, ...]
    pairs: tuple[AdversarialCounterfactualPairTruthV1, ...]

    @field_validator("canonical_bindings", "cases", "pairs")
    @classmethod
    def canonical_truth(
        cls, value: tuple[SyntheticModel, ...], info: ValidationInfo
    ) -> tuple[SyntheticModel, ...]:
        field_name = cast(str, info.field_name)
        attribute = {
            "canonical_bindings": "credential_id",
            "cases": "attempt_id",
            "pairs": "pair_id",
        }[field_name]
        return canonical_synthetic_records(
            value,
            keys=tuple((cast(str, getattr(item, attribute)),) for item in value),
            description=f"adversarial_evaluator_{field_name}_id",
        )


class AdversarialAttemptPredictionV1(EnterpriseOperatorModel):
    attempt_id: str = Field(min_length=1)
    resolved_principal_id: str | None = Field(default=None, min_length=1)
    binding_status: BindingStatus
    decision: AuthorizationDecision


class EnterpriseAdversarialAuthorizationPredictionV1(EnterpriseOperatorModel):
    schema_version: Literal["1.0.0"] = (
        ADVERSARIAL_AUTHORIZATION_PREDICTION_SCHEMA_VERSION
    )
    public_digest: SyntheticDigestV1
    attempts: tuple[AdversarialAttemptPredictionV1, ...] = Field(min_length=1)

    @field_validator("attempts")
    @classmethod
    def canonical_attempts(
        cls, value: tuple[AdversarialAttemptPredictionV1, ...]
    ) -> tuple[AdversarialAttemptPredictionV1, ...]:
        return canonical_operator_records(
            value,
            keys=tuple((item.attempt_id,) for item in value),
            description="adversarial_prediction_attempt_id",
        )


class AdversarialCohortSummaryV1(SyntheticModel):
    mechanism: AdversarialAuthorizationMechanism
    total_scenarios: int = Field(ge=0)
    discriminating_denominator: int = Field(ge=0)

    @model_validator(mode="after")
    def denominator_within_total(self) -> Self:
        if self.discriminating_denominator > self.total_scenarios:
            raise ValueError("adversarial_denominator_exceeds_cohort_total")
        return self


class EnterpriseAdversarialAuthorizationMetricsV1(SyntheticModel):
    """Independent metrics plus explicit total and discriminating cohorts."""

    schema_version: Literal["1.0.0"] = ADVERSARIAL_AUTHORIZATION_METRICS_SCHEMA_VERSION
    profile_version: Literal["enterprise-authorization-adversarial-1.0.0"] = (
        ADVERSARIAL_AUTHORIZATION_PROFILE_VERSION
    )
    public_digest: SyntheticDigestV1
    evaluator_digest: SyntheticDigestV1
    prediction_digest: SyntheticDigestV1
    cohorts: tuple[AdversarialCohortSummaryV1, ...]
    metrics: tuple[EnterpriseAuthorizationMetricV1, ...]

    @field_validator("cohorts")
    @classmethod
    def canonical_cohorts(
        cls, value: tuple[AdversarialCohortSummaryV1, ...]
    ) -> tuple[AdversarialCohortSummaryV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.mechanism.value,) for item in value),
            description="adversarial_metric_cohort",
        )

    @field_validator("metrics")
    @classmethod
    def canonical_metrics(
        cls, value: tuple[EnterpriseAuthorizationMetricV1, ...]
    ) -> tuple[EnterpriseAuthorizationMetricV1, ...]:
        return canonical_synthetic_records(
            value,
            keys=tuple((item.family, item.name) for item in value),
            description="adversarial_metric_name",
        )


__all__ = [name for name in globals() if name.endswith("V1")]
