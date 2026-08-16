"""Deliberately weak public-only adversarial authorization baselines."""

from __future__ import annotations

from collections.abc import Callable

from synthworld.enterprise.authorization.adversarial.common import (
    AdversarialAuthorizationMechanism,
)
from synthworld.enterprise.authorization.adversarial.models import (
    AdversarialAttemptPredictionV1,
    EnterpriseAdversarialAuthorizationPredictionV1,
    EnterpriseAdversarialAuthorizationPublicV1,
)
from synthworld.enterprise.authorization.adversarial.reference import (
    evaluate_adversarial_attempt,
    resolve_adversarial_credential,
)
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.rbac.common import AuthorizationDecision, BindingStatus

type AdversarialAuthorizationBaseline = Callable[
    [EnterpriseAdversarialAuthorizationPublicV1],
    EnterpriseAdversarialAuthorizationPredictionV1,
]


def tenant_blind_authorization_baseline(
    public: EnterpriseAdversarialAuthorizationPublicV1,
) -> EnterpriseAdversarialAuthorizationPredictionV1:
    return _control_blind_prediction(
        public, ignored=AdversarialAuthorizationMechanism.TENANT
    )


def scope_blind_authorization_baseline(
    public: EnterpriseAdversarialAuthorizationPublicV1,
) -> EnterpriseAdversarialAuthorizationPredictionV1:
    return _control_blind_prediction(
        public, ignored=AdversarialAuthorizationMechanism.SCOPE
    )


def binding_blind_authorization_baseline(
    public: EnterpriseAdversarialAuthorizationPublicV1,
) -> EnterpriseAdversarialAuthorizationPredictionV1:
    return _control_blind_prediction(
        public, ignored=AdversarialAuthorizationMechanism.BINDING
    )


def time_blind_authorization_baseline(
    public: EnterpriseAdversarialAuthorizationPublicV1,
) -> EnterpriseAdversarialAuthorizationPredictionV1:
    return _control_blind_prediction(
        public, ignored=AdversarialAuthorizationMechanism.TIME
    )


def clearance_blind_authorization_baseline(
    public: EnterpriseAdversarialAuthorizationPublicV1,
) -> EnterpriseAdversarialAuthorizationPredictionV1:
    return _control_blind_prediction(
        public, ignored=AdversarialAuthorizationMechanism.CLEARANCE
    )


def rbac_only_authorization_baseline(
    public: EnterpriseAdversarialAuthorizationPublicV1,
) -> EnterpriseAdversarialAuthorizationPredictionV1:
    return _control_blind_prediction(
        public, ignored=AdversarialAuthorizationMechanism.COMPOSITION
    )


def identifier_memorization_baseline(
    public: EnterpriseAdversarialAuthorizationPublicV1,
) -> EnterpriseAdversarialAuthorizationPredictionV1:
    """Guess by canonical public order instead of evaluating policy facts."""

    return EnterpriseAdversarialAuthorizationPredictionV1(
        public_digest=synthetic_digest(canonical_json_bytes(public)),
        attempts=tuple(
            AdversarialAttemptPredictionV1(
                attempt_id=item.attempt_id,
                resolved_principal_id=(
                    resolved := resolve_adversarial_credential(
                        public, item.credential_id
                    )
                ),
                binding_status=_binding_status(item.presented_principal_id, resolved),
                decision=(
                    AuthorizationDecision.ALLOW
                    if index % 2 == 0
                    else AuthorizationDecision.DENY
                ),
            )
            for index, item in enumerate(public.attempts)
        ),
    )


ENTERPRISE_ADVERSARIAL_AUTHORIZATION_BASELINES: tuple[
    tuple[str, AdversarialAuthorizationBaseline], ...
] = (
    ("Tenant blind", tenant_blind_authorization_baseline),
    ("Scope blind", scope_blind_authorization_baseline),
    ("Binding blind", binding_blind_authorization_baseline),
    ("Time blind", time_blind_authorization_baseline),
    ("Clearance blind", clearance_blind_authorization_baseline),
    ("RBAC only", rbac_only_authorization_baseline),
    ("Identifier/order memorization", identifier_memorization_baseline),
)


def _control_blind_prediction(
    public: EnterpriseAdversarialAuthorizationPublicV1,
    *,
    ignored: AdversarialAuthorizationMechanism,
) -> EnterpriseAdversarialAuthorizationPredictionV1:
    rows = []
    for item in public.attempts:
        resolved = (
            item.presented_principal_id
            if ignored is AdversarialAuthorizationMechanism.BINDING
            else resolve_adversarial_credential(public, item.credential_id)
        )
        rows.append(
            AdversarialAttemptPredictionV1(
                attempt_id=item.attempt_id,
                resolved_principal_id=resolved,
                binding_status=_binding_status(item.presented_principal_id, resolved),
                decision=evaluate_adversarial_attempt(
                    public,
                    item,
                    resolved_principal_id=resolved,
                    ignored_mechanism=(
                        None
                        if ignored is AdversarialAuthorizationMechanism.BINDING
                        else ignored
                    ),
                ),
            )
        )
    return EnterpriseAdversarialAuthorizationPredictionV1(
        public_digest=synthetic_digest(canonical_json_bytes(public)),
        attempts=tuple(rows),
    )


def _binding_status(presented_principal_id: str, resolved: str | None) -> BindingStatus:
    if resolved is None:
        return BindingStatus.MISSING
    if presented_principal_id == resolved:
        return BindingStatus.MATCHES_CANONICAL
    return BindingStatus.MISMATCH


__all__ = [
    "ENTERPRISE_ADVERSARIAL_AUTHORIZATION_BASELINES",
    "AdversarialAuthorizationBaseline",
    "binding_blind_authorization_baseline",
    "clearance_blind_authorization_baseline",
    "identifier_memorization_baseline",
    "rbac_only_authorization_baseline",
    "scope_blind_authorization_baseline",
    "tenant_blind_authorization_baseline",
    "time_blind_authorization_baseline",
]
