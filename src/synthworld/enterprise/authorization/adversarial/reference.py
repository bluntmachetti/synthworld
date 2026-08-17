"""Deterministic single-factor reference pack for adversarial authorization."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid5

from synthworld.enterprise.abac.common import InformationClassification
from synthworld.enterprise.authorization.adversarial.common import (
    AdversarialAuthoritySource,
    AdversarialAuthorizationMechanism,
    AdversarialCaseCategory,
    TenantComparisonOperator,
)
from synthworld.enterprise.authorization.adversarial.models import (
    AdversarialActionAttemptV1,
    AdversarialAttemptTruthV1,
    AdversarialAuthorityGrantV1,
    AdversarialCounterfactualPairTruthV1,
    AdversarialCredentialBindingTruthV1,
    AdversarialCredentialEvidenceV1,
    AdversarialPrincipalV1,
    AdversarialResourceV1,
    AdversarialTenantRuleV1,
    EnterpriseAdversarialAuthorizationEvaluatorV1,
    EnterpriseAdversarialAuthorizationPolicyV1,
    EnterpriseAdversarialAuthorizationPublicV1,
)
from synthworld.enterprise.authorization_common import RuleEffect
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.rbac.common import AuthorizationDecision, BindingStatus

_ADVERSARIAL_AUTHORIZATION_NAMESPACE = UUID("13047291-eaaa-5da4-a6b2-414e1548567d")
_CLASSIFICATION_RANK = {
    InformationClassification.PUBLIC: 0,
    InformationClassification.INTERNAL: 1,
    InformationClassification.CONFIDENTIAL: 2,
    InformationClassification.RESTRICTED: 3,
}


@dataclass(frozen=True, slots=True)
class ReferenceEnterpriseAdversarialAuthorizationV1:
    public: EnterpriseAdversarialAuthorizationPublicV1
    evaluator: EnterpriseAdversarialAuthorizationEvaluatorV1


@dataclass(frozen=True, slots=True)
class _PairSpec:
    pair_id: str
    mechanism: AdversarialAuthorizationMechanism
    from_attempt_id: str
    to_attempt_id: str


def reference_enterprise_adversarial_authorization(
    *, seed: int = 20260816
) -> ReferenceEnterpriseAdversarialAuthorizationV1:
    """Build opaque, deterministic cases whose pair labels remain evaluator-only."""

    def opaque(label: str) -> str:
        return str(uuid5(_ADVERSARIAL_AUTHORIZATION_NAMESPACE, f"{seed}:{label}"))

    principal_authorized = AdversarialPrincipalV1(
        principal_id=opaque("principal-authorized"),
        tenant_id="tenant-a.example.invalid",
        directory_alias="authorized.operator@example.invalid",
        clearance=InformationClassification.CONFIDENTIAL,
    )
    principal_unprivileged = AdversarialPrincipalV1(
        principal_id=opaque("principal-unprivileged"),
        tenant_id="tenant-a.example.invalid",
        directory_alias="unprivileged.operator@example.invalid",
        clearance=InformationClassification.CONFIDENTIAL,
    )
    principal_related = AdversarialPrincipalV1(
        principal_id=opaque("principal-related"),
        tenant_id="tenant-a.example.invalid",
        directory_alias="related.operator@example.invalid",
        clearance=InformationClassification.CONFIDENTIAL,
    )
    credentials = tuple(
        AdversarialCredentialEvidenceV1(
            credential_id=opaque(f"credential-{label}"),
            issuer_subject_alias=principal.directory_alias,
            device_owner_alias=principal.directory_alias,
        )
        for label, principal in (
            ("authorized", principal_authorized),
            ("unprivileged", principal_unprivileged),
            ("related", principal_related),
        )
    )
    credential_by_alias = {
        item.issuer_subject_alias: item.credential_id for item in credentials
    }
    resources = (
        AdversarialResourceV1(
            resource_id=opaque("resource-document-tenant-a"),
            tenant_id="tenant-a.example.invalid",
            resource_kind="document",
            classification=InformationClassification.INTERNAL,
        ),
        AdversarialResourceV1(
            resource_id=opaque("resource-document-tenant-b"),
            tenant_id="tenant-b.example.invalid",
            resource_kind="document",
            classification=InformationClassification.INTERNAL,
        ),
        AdversarialResourceV1(
            resource_id=opaque("resource-document-restricted"),
            tenant_id="tenant-a.example.invalid",
            resource_kind="document",
            classification=InformationClassification.RESTRICTED,
        ),
        AdversarialResourceV1(
            resource_id=opaque("resource-repository-tenant-a"),
            tenant_id="tenant-a.example.invalid",
            resource_kind="repository",
            classification=InformationClassification.INTERNAL,
        ),
    )
    resource_by_kind_tenant_classification = {
        (item.resource_kind, item.tenant_id, item.classification): item.resource_id
        for item in resources
    }
    grants = (
        AdversarialAuthorityGrantV1(
            grant_id=opaque("grant-authorized-document"),
            principal_id=principal_authorized.principal_id,
            resource_kind="document",
            action="read",
            allowed_scopes=("document:read",),
            valid_from_tick=10,
            valid_until_tick=20,
            source=AdversarialAuthoritySource.RBAC,
        ),
        AdversarialAuthorityGrantV1(
            grant_id=opaque("grant-related-repository"),
            principal_id=principal_related.principal_id,
            resource_kind="repository",
            action="read",
            allowed_scopes=("repository:read",),
            valid_from_tick=10,
            valid_until_tick=20,
            source=AdversarialAuthoritySource.REBAC,
        ),
    )
    principal_by_label = {
        "authorized": principal_authorized,
        "unprivileged": principal_unprivileged,
        "related": principal_related,
    }

    def attempt(
        label: str,
        *,
        presented: str,
        credential: str,
        resource: str,
        scope: str,
        tick: int = 15,
    ) -> AdversarialActionAttemptV1:
        principal = principal_by_label[presented]
        credential_id = credential_by_alias[
            principal_by_label[credential].directory_alias
        ]
        return AdversarialActionAttemptV1(
            attempt_id=opaque(f"attempt-{label}"),
            presented_principal_id=principal.principal_id,
            credential_id=credential_id,
            resource_id=resource,
            action="read",
            requested_scope=scope,
            tick=tick,
        )

    document_a = resource_by_kind_tenant_classification[
        (
            "document",
            "tenant-a.example.invalid",
            InformationClassification.INTERNAL,
        )
    ]
    document_b = resource_by_kind_tenant_classification[
        (
            "document",
            "tenant-b.example.invalid",
            InformationClassification.INTERNAL,
        )
    ]
    document_restricted = resource_by_kind_tenant_classification[
        (
            "document",
            "tenant-a.example.invalid",
            InformationClassification.RESTRICTED,
        )
    ]
    repository_a = resource_by_kind_tenant_classification[
        (
            "repository",
            "tenant-a.example.invalid",
            InformationClassification.INTERNAL,
        )
    ]
    attempts = (
        attempt(
            "tenant-same",
            presented="authorized",
            credential="authorized",
            resource=document_a,
            scope="document:read",
        ),
        attempt(
            "tenant-different",
            presented="authorized",
            credential="authorized",
            resource=document_b,
            scope="document:read",
        ),
        attempt(
            "scope-within",
            presented="authorized",
            credential="authorized",
            resource=document_a,
            scope="document:read",
        ),
        attempt(
            "scope-exceeded",
            presented="authorized",
            credential="authorized",
            resource=document_a,
            scope="document:admin",
        ),
        attempt(
            "time-valid",
            presented="authorized",
            credential="authorized",
            resource=document_a,
            scope="document:read",
            tick=19,
        ),
        attempt(
            "time-expired",
            presented="authorized",
            credential="authorized",
            resource=document_a,
            scope="document:read",
            tick=20,
        ),
        attempt(
            "clearance-within",
            presented="authorized",
            credential="authorized",
            resource=document_a,
            scope="document:read",
        ),
        attempt(
            "clearance-exceeded",
            presented="authorized",
            credential="authorized",
            resource=document_restricted,
            scope="document:read",
        ),
        attempt(
            "binding-matches-authorized",
            presented="authorized",
            credential="authorized",
            resource=document_a,
            scope="document:read",
        ),
        attempt(
            "binding-resolves-unprivileged",
            presented="authorized",
            credential="unprivileged",
            resource=document_a,
            scope="document:read",
        ),
        attempt(
            "binding-matches-unprivileged",
            presented="unprivileged",
            credential="unprivileged",
            resource=document_a,
            scope="document:read",
        ),
        attempt(
            "binding-resolves-authorized",
            presented="unprivileged",
            credential="authorized",
            resource=document_a,
            scope="document:read",
        ),
        attempt(
            "composition-no-authority",
            presented="unprivileged",
            credential="unprivileged",
            resource=repository_a,
            scope="repository:read",
        ),
        attempt(
            "composition-rebac-authority",
            presented="related",
            credential="related",
            resource=repository_a,
            scope="repository:read",
        ),
    )
    attempts_by_label = {
        label: item
        for label, item in zip(
            (
                "tenant-same",
                "tenant-different",
                "scope-within",
                "scope-exceeded",
                "time-valid",
                "time-expired",
                "clearance-within",
                "clearance-exceeded",
                "binding-matches-authorized",
                "binding-resolves-unprivileged",
                "binding-matches-unprivileged",
                "binding-resolves-authorized",
                "composition-no-authority",
                "composition-rebac-authority",
            ),
            attempts,
            strict=True,
        )
    }
    pair_specs = tuple(
        _PairSpec(
            pair_id=opaque(f"pair-{label}"),
            mechanism=mechanism,
            from_attempt_id=attempts_by_label[from_label].attempt_id,
            to_attempt_id=attempts_by_label[to_label].attempt_id,
        )
        for label, mechanism, from_label, to_label in (
            (
                "tenant",
                AdversarialAuthorizationMechanism.TENANT,
                "tenant-same",
                "tenant-different",
            ),
            (
                "scope",
                AdversarialAuthorizationMechanism.SCOPE,
                "scope-within",
                "scope-exceeded",
            ),
            (
                "time",
                AdversarialAuthorizationMechanism.TIME,
                "time-valid",
                "time-expired",
            ),
            (
                "clearance",
                AdversarialAuthorizationMechanism.CLEARANCE,
                "clearance-within",
                "clearance-exceeded",
            ),
            (
                "binding-authorized",
                AdversarialAuthorizationMechanism.BINDING,
                "binding-matches-authorized",
                "binding-resolves-unprivileged",
            ),
            (
                "binding-inverse",
                AdversarialAuthorizationMechanism.BINDING,
                "binding-matches-unprivileged",
                "binding-resolves-authorized",
            ),
            (
                "composition",
                AdversarialAuthorizationMechanism.COMPOSITION,
                "composition-no-authority",
                "composition-rebac-authority",
            ),
        )
    )
    public = EnterpriseAdversarialAuthorizationPublicV1(
        seed=seed,
        policy=EnterpriseAdversarialAuthorizationPolicyV1(
            default_tenant_decision=AuthorizationDecision.ALLOW,
            tenant_rules=(
                AdversarialTenantRuleV1(
                    rule_id="deny-cross-tenant",
                    operator=TenantComparisonOperator.NOT_EQUALS,
                    effect=RuleEffect.DENY,
                ),
            ),
        ),
        principals=(
            principal_authorized,
            principal_unprivileged,
            principal_related,
        ),
        credentials=credentials,
        resources=resources,
        grants=grants,
        attempts=attempts,
    )
    canonical_bindings = tuple(
        AdversarialCredentialBindingTruthV1(
            credential_id=item.credential_id,
            principal_id=resolve_adversarial_credential(public, item.credential_id)
            or "unresolved",
        )
        for item in public.credentials
    )
    binding_by_credential = {
        item.credential_id: item.principal_id for item in canonical_bindings
    }
    pair_by_attempt = {
        attempt_id: pair
        for pair in pair_specs
        for attempt_id in (pair.from_attempt_id, pair.to_attempt_id)
    }
    case_truth: list[AdversarialAttemptTruthV1] = []
    for item in public.attempts:
        pair = pair_by_attempt[item.attempt_id]
        resolved_principal_id = binding_by_credential[item.credential_id]
        expected_decision = evaluate_adversarial_attempt(
            public, item, resolved_principal_id=resolved_principal_id
        )
        ignored_resolved_principal_id = (
            item.presented_principal_id
            if pair.mechanism is AdversarialAuthorizationMechanism.BINDING
            else resolved_principal_id
        )
        ignored_mechanism = (
            None
            if pair.mechanism is AdversarialAuthorizationMechanism.BINDING
            else pair.mechanism
        )
        case_truth.append(
            AdversarialAttemptTruthV1(
                attempt_id=item.attempt_id,
                pair_id=pair.pair_id,
                mechanism=pair.mechanism,
                category=AdversarialCaseCategory.SINGLE_FACTOR,
                resolved_principal_id=resolved_principal_id,
                binding_status=(
                    BindingStatus.MATCHES_CANONICAL
                    if item.presented_principal_id == resolved_principal_id
                    else BindingStatus.MISMATCH
                ),
                expected_decision=expected_decision,
                mechanism_ignored_decision=evaluate_adversarial_attempt(
                    public,
                    item,
                    resolved_principal_id=ignored_resolved_principal_id,
                    ignored_mechanism=ignored_mechanism,
                ),
                identifier_probe=item.attempt_id == pair.to_attempt_id,
            )
        )
    truth_by_attempt = {item.attempt_id: item for item in case_truth}
    pairs = tuple(
        AdversarialCounterfactualPairTruthV1(
            pair_id=item.pair_id,
            mechanism=item.mechanism,
            category=AdversarialCaseCategory.SINGLE_FACTOR,
            from_attempt_id=item.from_attempt_id,
            to_attempt_id=item.to_attempt_id,
            expected_transition=(
                truth_by_attempt[item.from_attempt_id].expected_decision
                is not truth_by_attempt[item.to_attempt_id].expected_decision
            ),
        )
        for item in pair_specs
    )
    if not all(item.expected_transition for item in pairs):
        raise AssertionError("reference adversarial pair failed to change decision")
    evaluator = EnterpriseAdversarialAuthorizationEvaluatorV1(
        public_digest=synthetic_digest(canonical_json_bytes(public)),
        canonical_bindings=canonical_bindings,
        cases=tuple(case_truth),
        pairs=pairs,
    )
    validate_adversarial_authorization_artifacts(public, evaluator)
    return ReferenceEnterpriseAdversarialAuthorizationV1(
        public=public,
        evaluator=evaluator,
    )


def resolve_adversarial_credential(
    public: EnterpriseAdversarialAuthorizationPublicV1, credential_id: str
) -> str | None:
    """Resolve agreeing public evidence without exposing canonical binding records."""

    credential = next(
        (item for item in public.credentials if item.credential_id == credential_id),
        None,
    )
    if credential is None:
        return None
    principal_by_alias = {
        item.directory_alias: item.principal_id for item in public.principals
    }
    issuer = principal_by_alias.get(credential.issuer_subject_alias)
    owner = principal_by_alias.get(credential.device_owner_alias)
    return issuer if issuer is not None and issuer == owner else None


def evaluate_adversarial_attempt(
    public: EnterpriseAdversarialAuthorizationPublicV1,
    attempt: AdversarialActionAttemptV1,
    *,
    resolved_principal_id: str | None,
    ignored_mechanism: AdversarialAuthorizationMechanism | None = None,
) -> AuthorizationDecision:
    """Apply the bounded public policy, optionally corrupting one mechanism."""

    principal = next(
        (
            item
            for item in public.principals
            if item.principal_id == resolved_principal_id
        ),
        None,
    )
    resource = next(
        item for item in public.resources if item.resource_id == attempt.resource_id
    )
    if principal is None:
        return AuthorizationDecision.DENY
    matching_grants = tuple(
        item
        for item in public.grants
        if item.principal_id == principal.principal_id
        and item.resource_kind == resource.resource_kind
        and item.action == attempt.action
    )
    grant_allowed = any(
        (
            item.source is AdversarialAuthoritySource.RBAC
            or (
                ignored_mechanism is not AdversarialAuthorizationMechanism.COMPOSITION
                and item.source is AdversarialAuthoritySource.REBAC
            )
        )
        and (
            ignored_mechanism is AdversarialAuthorizationMechanism.SCOPE
            or attempt.requested_scope in item.allowed_scopes
        )
        and (
            ignored_mechanism is AdversarialAuthorizationMechanism.TIME
            or item.valid_from_tick <= attempt.tick < item.valid_until_tick
        )
        for item in matching_grants
    )
    tenant_allowed = _tenant_allowed(public, principal.tenant_id, resource.tenant_id)
    clearance_allowed = (
        _CLASSIFICATION_RANK[principal.clearance]
        >= _CLASSIFICATION_RANK[resource.classification]
    )
    checks = {
        AdversarialAuthorizationMechanism.TENANT: tenant_allowed,
        AdversarialAuthorizationMechanism.CLEARANCE: clearance_allowed,
    }
    if ignored_mechanism in checks:
        checks[ignored_mechanism] = True
    allowed = grant_allowed and all(checks.values())
    return AuthorizationDecision.ALLOW if allowed else AuthorizationDecision.DENY


def validate_adversarial_authorization_artifacts(
    public: EnterpriseAdversarialAuthorizationPublicV1,
    evaluator: EnterpriseAdversarialAuthorizationEvaluatorV1,
) -> None:
    """Validate cross-boundary inventories without weakening their physical split."""

    if evaluator.public_digest != synthetic_digest(canonical_json_bytes(public)):
        raise ValueError("adversarial_evaluator_public_digest_mismatch")
    credential_ids = {item.credential_id for item in public.credentials}
    binding_by_credential = {
        item.credential_id: item.principal_id for item in evaluator.canonical_bindings
    }
    if set(binding_by_credential) != credential_ids:
        raise ValueError("adversarial_binding_inventory_mismatch")
    principal_ids = {item.principal_id for item in public.principals}
    if not set(binding_by_credential.values()) <= principal_ids:
        raise ValueError("adversarial_binding_principal_unknown")
    attempt_by_id = {item.attempt_id: item for item in public.attempts}
    case_by_attempt = {item.attempt_id: item for item in evaluator.cases}
    if set(case_by_attempt) != set(attempt_by_id):
        raise ValueError("adversarial_case_inventory_mismatch")
    if any(
        item.resolved_principal_id
        != binding_by_credential[attempt_by_id[item.attempt_id].credential_id]
        for item in evaluator.cases
    ):
        raise ValueError("adversarial_case_binding_mismatch")
    pair_by_id = {item.pair_id: item for item in evaluator.pairs}
    if any(
        item.pair_id not in pair_by_id
        or item.mechanism is not pair_by_id[item.pair_id].mechanism
        or item.category is not pair_by_id[item.pair_id].category
        for item in evaluator.cases
    ):
        raise ValueError("adversarial_case_pair_mismatch")
    paired_attempt_ids = tuple(
        attempt_id
        for item in evaluator.pairs
        for attempt_id in (item.from_attempt_id, item.to_attempt_id)
    )
    if len(paired_attempt_ids) != len(attempt_by_id) or set(paired_attempt_ids) != set(
        attempt_by_id
    ):
        raise ValueError("adversarial_pair_attempt_inventory_mismatch")
    if any(
        item.attempt_id
        not in (
            pair_by_id[item.pair_id].from_attempt_id,
            pair_by_id[item.pair_id].to_attempt_id,
        )
        for item in evaluator.cases
    ):
        raise ValueError("adversarial_case_not_in_declared_pair")
    for item in evaluator.cases:
        attempt = attempt_by_id[item.attempt_id]
        expected_identifier_probe = (
            item.attempt_id == pair_by_id[item.pair_id].to_attempt_id
        )
        if item.identifier_probe is not expected_identifier_probe:
            raise ValueError("adversarial_case_identifier_probe_mismatch")
        expected_binding_status = (
            BindingStatus.MATCHES_CANONICAL
            if attempt.presented_principal_id == item.resolved_principal_id
            else BindingStatus.MISMATCH
        )
        if item.binding_status is not expected_binding_status:
            raise ValueError("adversarial_case_binding_status_mismatch")
        if item.expected_decision is not evaluate_adversarial_attempt(
            public,
            attempt,
            resolved_principal_id=item.resolved_principal_id,
        ):
            raise ValueError("adversarial_case_expected_decision_mismatch")
        ignored_resolved_principal_id = (
            attempt.presented_principal_id
            if item.mechanism is AdversarialAuthorizationMechanism.BINDING
            else item.resolved_principal_id
        )
        ignored_mechanism = (
            None
            if item.mechanism is AdversarialAuthorizationMechanism.BINDING
            else item.mechanism
        )
        if item.mechanism_ignored_decision is not evaluate_adversarial_attempt(
            public,
            attempt,
            resolved_principal_id=ignored_resolved_principal_id,
            ignored_mechanism=ignored_mechanism,
        ):
            raise ValueError("adversarial_case_ignored_decision_mismatch")
    cases_by_attempt = {item.attempt_id: item for item in evaluator.cases}
    for pair in evaluator.pairs:
        expected_transition = (
            cases_by_attempt[pair.from_attempt_id].expected_decision
            is not cases_by_attempt[pair.to_attempt_id].expected_decision
        )
        if not expected_transition:
            raise ValueError("adversarial_pair_transition_required")
        if pair.expected_transition is not expected_transition:
            raise ValueError("adversarial_pair_transition_mismatch")
    if any(
        not any(
            cases_by_attempt[attempt_id].expected_decision
            is not cases_by_attempt[attempt_id].mechanism_ignored_decision
            for attempt_id in (item.from_attempt_id, item.to_attempt_id)
        )
        for item in evaluator.pairs
    ):
        raise ValueError("adversarial_pair_not_discriminating")


def _tenant_allowed(
    public: EnterpriseAdversarialAuthorizationPublicV1,
    principal_tenant_id: str,
    resource_tenant_id: str,
) -> bool:
    default = public.policy.default_tenant_decision
    matching_effects = tuple(
        item.effect
        for item in public.policy.tenant_rules
        if (
            item.operator is TenantComparisonOperator.EQUALS
            and principal_tenant_id == resource_tenant_id
        )
        or (
            item.operator is TenantComparisonOperator.NOT_EQUALS
            and principal_tenant_id != resource_tenant_id
        )
    )
    if RuleEffect.DENY in matching_effects:
        return False
    if RuleEffect.ALLOW in matching_effects:
        return True
    return default is AuthorizationDecision.ALLOW


__all__ = [
    "ReferenceEnterpriseAdversarialAuthorizationV1",
    "evaluate_adversarial_attempt",
    "reference_enterprise_adversarial_authorization",
    "resolve_adversarial_credential",
    "validate_adversarial_authorization_artifacts",
]
