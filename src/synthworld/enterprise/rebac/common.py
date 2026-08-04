"""Versions and closed native ReBAC vocabulary."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

ENTERPRISE_REBAC_STATE_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_REBAC_INTENT_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_REBAC_TRUTH_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_REBAC_COMPILER_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_REBAC_METRICS_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"


class RebacRelation(StrEnum):
    MEMBER_OF = "member_of"
    OWNS = "owns"
    MANAGES = "manages"
    COLLABORATES_ON = "collaborates_on"


class RebacTemplateKind(StrEnum):
    DIRECT_SUBJECT_RELATION = "direct_subject_relation"
    GROUP_COLLABORATION = "group_collaboration"
    MANAGER_OF_OWNER = "manager_of_owner"


__all__ = [
    "ENTERPRISE_REBAC_COMPILER_VERSION",
    "ENTERPRISE_REBAC_INTENT_SCHEMA_VERSION",
    "ENTERPRISE_REBAC_METRICS_SCHEMA_VERSION",
    "ENTERPRISE_REBAC_STATE_SCHEMA_VERSION",
    "ENTERPRISE_REBAC_TRUTH_SCHEMA_VERSION",
    "RebacRelation",
    "RebacTemplateKind",
]
