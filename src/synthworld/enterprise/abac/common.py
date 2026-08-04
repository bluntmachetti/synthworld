"""Versions and closed ABAC vocabulary."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

ENTERPRISE_ABAC_STATE_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_ABAC_INTENT_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_ABAC_TRUTH_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_ABAC_COMPILER_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_ABAC_METRICS_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"


class AttributeCategory(StrEnum):
    SUBJECT = "subject"
    RESOURCE = "resource"
    ACTION = "action"
    ENVIRONMENT = "environment"


class AttributeValueState(StrEnum):
    KNOWN = "known"
    UNKNOWN = "unknown"


class AbacEmploymentType(StrEnum):
    EMPLOYEE = "employee"
    CONTRACTOR = "contractor"
    SUPPLIER = "supplier"
    PARTNER = "partner"
    NOT_APPLICABLE = "not_applicable"


class InformationClassification(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class ActionClass(StrEnum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    ADMIN = "admin"


class AssuranceLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class NetworkZone(StrEnum):
    INTERNAL = "internal"
    PARTNER = "partner"
    PUBLIC = "public"


__all__ = [
    "ENTERPRISE_ABAC_COMPILER_VERSION",
    "ENTERPRISE_ABAC_INTENT_SCHEMA_VERSION",
    "ENTERPRISE_ABAC_METRICS_SCHEMA_VERSION",
    "ENTERPRISE_ABAC_STATE_SCHEMA_VERSION",
    "ENTERPRISE_ABAC_TRUTH_SCHEMA_VERSION",
    "AbacEmploymentType",
    "ActionClass",
    "AssuranceLevel",
    "AttributeCategory",
    "AttributeValueState",
    "InformationClassification",
    "NetworkZone",
]
