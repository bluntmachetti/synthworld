"""Closed vocabulary and versions for adversarial enterprise authorization."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

ADVERSARIAL_AUTHORIZATION_PROFILE_VERSION: Literal[
    "enterprise-authorization-adversarial-1.0.0"
] = "enterprise-authorization-adversarial-1.0.0"
ADVERSARIAL_AUTHORIZATION_PUBLIC_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ADVERSARIAL_AUTHORIZATION_EVALUATOR_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ADVERSARIAL_AUTHORIZATION_PREDICTION_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ADVERSARIAL_AUTHORIZATION_METRICS_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"


class AdversarialAuthorizationMechanism(StrEnum):
    TENANT = "tenant"
    SCOPE = "scope"
    BINDING = "binding"
    TIME = "time"
    CLEARANCE = "clearance"
    COMPOSITION = "composition"


class AdversarialAuthoritySource(StrEnum):
    RBAC = "rbac"
    REBAC = "rebac"


class AdversarialCaseCategory(StrEnum):
    SINGLE_FACTOR = "single_factor"
    INTERACTION = "interaction"


class TenantComparisonOperator(StrEnum):
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"


class AuthorityCombinationPolicy(StrEnum):
    RBAC_OR_REBAC = "rbac_or_rebac"


__all__ = [
    "ADVERSARIAL_AUTHORIZATION_EVALUATOR_SCHEMA_VERSION",
    "ADVERSARIAL_AUTHORIZATION_METRICS_SCHEMA_VERSION",
    "ADVERSARIAL_AUTHORIZATION_PREDICTION_SCHEMA_VERSION",
    "ADVERSARIAL_AUTHORIZATION_PROFILE_VERSION",
    "ADVERSARIAL_AUTHORIZATION_PUBLIC_SCHEMA_VERSION",
    "AdversarialAuthoritySource",
    "AdversarialAuthorizationMechanism",
    "AdversarialCaseCategory",
    "AuthorityCombinationPolicy",
    "TenantComparisonOperator",
]
