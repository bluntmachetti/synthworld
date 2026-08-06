"""Closed shared semantics for bounded enterprise authorization components."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

ENTERPRISE_AUTHORIZATION_COMPOSITION_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_AUTHORIZATION_KERNEL_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_AUTHORIZATION_PROFILE_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_COMPILED_ACCESS_STATE_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_AUTHORIZATION_COMPILER_VERSION: Literal["1.0.0"] = "1.0.0"


class AuthorizationSourceLayer(StrEnum):
    """Whether a component row came from observed or intended policy state."""

    ACTUAL = "actual"
    INTENDED = "intended"


class MechanismOutcome(StrEnum):
    """Native outcome retained before benchmark default-deny normalization."""

    ALLOW = "allow"
    DENY = "deny"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


class PredicateOutcome(StrEnum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"


class RuleEffect(StrEnum):
    ALLOW = "allow"
    DENY = "deny"


class FlatRuleOperator(StrEnum):
    ALL = "all"
    ANY = "any"


class AuthorizationEvaluationProfileKind(StrEnum):
    RBAC = "rbac"
    ABAC = "abac"
    REBAC = "rebac"
    RBAC_WITH_ABAC_GUARD = "rbac_with_abac_guard"
    REBAC_WITH_ABAC_GUARD = "rebac_with_abac_guard"


__all__ = [
    "ENTERPRISE_AUTHORIZATION_COMPILER_VERSION",
    "ENTERPRISE_AUTHORIZATION_COMPOSITION_SCHEMA_VERSION",
    "ENTERPRISE_AUTHORIZATION_KERNEL_SCHEMA_VERSION",
    "ENTERPRISE_AUTHORIZATION_PROFILE_SCHEMA_VERSION",
    "ENTERPRISE_COMPILED_ACCESS_STATE_SCHEMA_VERSION",
    "AuthorizationEvaluationProfileKind",
    "AuthorizationSourceLayer",
    "FlatRuleOperator",
    "MechanismOutcome",
    "PredicateOutcome",
    "RuleEffect",
]
