"""Shared constants and closed vocabularies for directory/RBAC v1."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from synthworld.enterprise.models import EnterpriseOperatorModel
from synthworld.models import SyntheticModel

ENTERPRISE_CORPUS_CONFIG_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_CORPUS_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_CORPUS_COMPILER_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_EVALUATOR_CASE_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_DIRECTORY_RBAC_INTENT_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_RBAC_SESSION_STATE_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_DIRECTORY_RBAC_KERNEL_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_DIRECTORY_RBAC_COMPILER_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_DIRECTORY_RBAC_TRUTH_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_DIRECTORY_RBAC_METRICS_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"


class AuthorizationDecision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"


class ActivationOutcome(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ReconciliationOutcome(StrEnum):
    ALIGNED_ALLOW = "aligned_allow"
    ALIGNED_DENY = "aligned_deny"
    EXCESSIVE = "excessive"
    MISSING = "missing"


class BindingStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    MATCHES_CANONICAL = "matches_canonical"
    MISSING = "missing"
    MISMATCH = "mismatch"


class LifecycleStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    ACTIVE = "active"
    INACTIVE = "inactive"
    NOT_YET_VALID = "not_yet_valid"
    EXPIRED = "expired"


class AssignmentTargetKind(StrEnum):
    GROUP = "group"
    ROLE = "role"
    PERMISSION = "permission"


class ApprovedExceptionReason(StrEnum):
    BUSINESS_NEED = "business_need"
    EMERGENCY = "emergency"
    MIGRATION = "migration"
    REMEDIATION_PENDING = "remediation_pending"


class BirthrightConditionOperator(StrEnum):
    ALL = "all"
    ANY = "any"


class EmploymentType(StrEnum):
    EMPLOYEE = "employee"
    CONTRACTOR = "contractor"
    SUPPLIER = "supplier"
    PARTNER = "partner"


class DerivationMechanism(StrEnum):
    DIRECT_ENTITLEMENT = "direct_entitlement"
    ROLE = "role"


class MetricEmptyBehaviour(StrEnum):
    NONEMPTY = "nonempty"
    NULL_IF_EMPTY = "null_if_empty"


class EvaluationCaseTargetKind(StrEnum):
    ACCESS_CELL = "access_cell"
    ACTIVATION_REQUEST = "activation_request"


def canonical_operator_records[OperatorT: EnterpriseOperatorModel](
    value: tuple[OperatorT, ...],
    *,
    keys: tuple[tuple[str, ...], ...],
    description: str,
) -> tuple[OperatorT, ...]:
    """Sort strict input records and reject semantic duplicate keys."""

    paired = sorted(zip(keys, value, strict=True), key=lambda item: item[0])
    ordered_keys = tuple(item[0] for item in paired)
    if len(ordered_keys) != len(set(ordered_keys)):
        raise ValueError(f"duplicate_{description}")
    return tuple(item[1] for item in paired)


def canonical_synthetic_records[SyntheticT: SyntheticModel](
    value: tuple[SyntheticT, ...],
    *,
    keys: tuple[tuple[str, ...], ...],
    description: str,
) -> tuple[SyntheticT, ...]:
    """Sort generated records and reject semantic duplicate keys."""

    paired = sorted(zip(keys, value, strict=True), key=lambda item: item[0])
    ordered_keys = tuple(item[0] for item in paired)
    if len(ordered_keys) != len(set(ordered_keys)):
        raise ValueError(f"duplicate_{description}")
    return tuple(item[1] for item in paired)


def canonical_strings(value: tuple[str, ...], description: str) -> tuple[str, ...]:
    ordered = tuple(sorted(value))
    if len(ordered) != len(set(ordered)):
        raise ValueError(f"duplicate_{description}")
    return ordered


__all__ = [name for name in globals() if name.startswith("ENTERPRISE_")]
__all__ += [
    "ActivationOutcome",
    "ApprovedExceptionReason",
    "AssignmentTargetKind",
    "AuthorizationDecision",
    "BindingStatus",
    "BirthrightConditionOperator",
    "DerivationMechanism",
    "EmploymentType",
    "EvaluationCaseTargetKind",
    "LifecycleStatus",
    "MetricEmptyBehaviour",
    "ReconciliationOutcome",
    "canonical_operator_records",
    "canonical_strings",
    "canonical_synthetic_records",
]
