"""Shared strict types for the agent-authority run protocol."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from synthworld.assurance.models_v2 import DigestV2
from synthworld.models import SyntheticModel

AGENT_AUTHORITY_RUN_PLAN_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
AGENT_AUTHORITY_OBSERVATIONS_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
AGENT_AUTHORITY_TRUTH_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
AGENT_AUTHORITY_REPORT_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
AGENT_AUTHORITY_PRODUCT_INPUT_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
AGENT_AUTHORITY_PROTOCOL_VERSION: Literal["1.0.0"] = "1.0.0"


class AgentAuthorityOperatorModel(BaseModel):
    """Strict base for real plans, provenance, and observations."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class AgentAuthorityControlId(StrEnum):
    C01 = "SW-AA-C01"
    C02 = "SW-AA-C02"
    C03 = "SW-AA-C03"
    C04 = "SW-AA-C04"
    C05 = "SW-AA-C05"
    C06 = "SW-AA-C06"
    C07 = "SW-AA-C07"
    C08 = "SW-AA-C08"
    C09 = "SW-AA-C09"
    C10 = "SW-AA-C10"
    C11 = "SW-AA-C11"
    C12 = "SW-AA-C12"
    C13 = "SW-AA-C13"
    C14 = "SW-AA-C14"
    C15 = "SW-AA-C15"
    C16 = "SW-AA-C16"
    L01 = "SW-AA-L01"
    L02 = "SW-AA-L02"
    L03 = "SW-AA-L03"
    L04 = "SW-AA-L04"
    L05 = "SW-AA-L05"
    L06 = "SW-AA-L06"
    L07 = "SW-AA-L07"
    L08 = "SW-AA-L08"


CONTROL_ORDER = tuple(AgentAuthorityControlId)
LAB_CONTROL_IDS = (
    AgentAuthorityControlId.L01,
    AgentAuthorityControlId.L02,
    AgentAuthorityControlId.L03,
    AgentAuthorityControlId.L04,
    AgentAuthorityControlId.L05,
    AgentAuthorityControlId.L06,
)
OPERATIONAL_CONTROL_IDS = (
    AgentAuthorityControlId.L07,
    AgentAuthorityControlId.L08,
)


class ControlLayer(StrEnum):
    CORE = "core"
    LAB = "lab"
    OPERATIONAL = "operational"


CONTROL_LAYERS = {
    **{
        control: ControlLayer.CORE
        for control in CONTROL_ORDER
        if control.value.startswith("SW-AA-C")
    },
    **{control: ControlLayer.LAB for control in LAB_CONTROL_IDS},
    **{control: ControlLayer.OPERATIONAL for control in OPERATIONAL_CONTROL_IDS},
}


class RunLayer(StrEnum):
    CORE = "core"
    LAB = "lab"
    COMBINED = "combined"


class CoverageDisposition(StrEnum):
    SELECTED = "selected"
    NOT_APPLICABLE = "not_applicable"


class DeploymentPattern(StrEnum):
    PROXY_INJECTION = "proxy_injection"
    SHORT_LIVED_MINTING = "short_lived_minting"
    STATIC_BEARER = "static_bearer"


class DirectPathReachability(StrEnum):
    BLOCKED = "blocked"
    REACHABLE = "reachable"
    UNKNOWN = "unknown"


class ObservedDecision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    ERROR = "error"
    TIMEOUT = "timeout"
    UNOBSERVED = "unobserved"


class ObservedSideEffect(StrEnum):
    OCCURRED = "occurred"
    NOT_OBSERVED = "not_observed"
    UNKNOWN = "unknown"


class CollectionStatus(StrEnum):
    COLLECTED = "collected"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class FindingStatus(StrEnum):
    PASS = "pass"  # noqa: S105 - verdict vocabulary, not a credential
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"
    NOT_EXECUTED = "not_executed"


class EvidenceKind(StrEnum):
    TARGET = "target"
    GATEWAY = "gateway"
    POLICY = "policy"
    CREDENTIAL_STORE = "credential_store"
    RUNTIME = "runtime"
    NETWORK = "network"
    LOG = "log"
    TRACE = "trace"
    MEMORY = "memory"


class RedactionStatus(StrEnum):
    NOT_REQUIRED = "not_required"
    REDACTED = "redacted"


class AttributionKind(StrEnum):
    SPECIFIC = "specific"
    MULTIPLE = "multiple"
    AMBIGUOUS = "ambiguous"
    UNOBSERVED = "unobserved"


class BoundMetric(StrEnum):
    REVOCATION_PROPAGATION = "revocation_propagation"
    DECISION_LATENCY = "decision_latency"
    RECOVERY_TIME = "recovery_time"


class BoundUnit(StrEnum):
    NS = "ns"
    US = "us"
    MS = "ms"
    S = "s"


BOUND_UNIT_NS = {
    BoundUnit.NS: 1,
    BoundUnit.US: 1_000,
    BoundUnit.MS: 1_000_000,
    BoundUnit.S: 1_000_000_000,
}


class ControlCoverageEntryV1(AgentAuthorityOperatorModel):
    control_id: AgentAuthorityControlId
    catalogue_layer: ControlLayer
    disposition: CoverageDisposition
    applicability_rationale: str | None = None

    @model_validator(mode="after")
    def validate_coverage(self) -> Self:
        if self.catalogue_layer is not CONTROL_LAYERS[self.control_id]:
            raise ValueError("control coverage layer differs from the catalogue")
        if self.disposition is CoverageDisposition.SELECTED:
            if self.applicability_rationale is not None:
                raise ValueError("selected controls forbid an applicability rationale")
        elif not present(self.applicability_rationale):
            raise ValueError("not-applicable controls require a rationale")
        return self


class AgentAuthorityBenchmarkBindingV1(AgentAuthorityOperatorModel):
    benchmark_family: str = Field(min_length=1)
    benchmark_version: str = Field(min_length=1)
    public_root_digest: DigestV2
    evaluator_root_digest: DigestV2
    identity_access_universe_digest: DigestV2
    policy_digest: DigestV2
    cell_digest: DigestV2


class DeclaredBoundV1(AgentAuthorityOperatorModel):
    bound_id: str = Field(min_length=1)
    control_id: Literal[AgentAuthorityControlId.L06] = AgentAuthorityControlId.L06
    metric: Literal[BoundMetric.REVOCATION_PROPAGATION] = (
        BoundMetric.REVOCATION_PROPAGATION
    )
    value: int = Field(gt=0)
    unit: BoundUnit

    @property
    def value_ns(self) -> int:
        return self.value * BOUND_UNIT_NS[self.unit]


class ObservationAttributionV1(AgentAuthorityOperatorModel):
    kind: AttributionKind
    component_ids: tuple[str, ...] = ()
    reason: str | None = None

    @field_validator("component_ids")
    @classmethod
    def canonical_components(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_unique(value, "attribution component identifiers")

    @model_validator(mode="after")
    def validate_shape(self) -> Self:
        count = len(self.component_ids)
        if self.kind is AttributionKind.SPECIFIC:
            if count != 1 or self.reason is not None:
                raise ValueError("specific attribution requires exactly one component")
        elif self.kind is AttributionKind.MULTIPLE:
            if count < 2 or self.reason is not None:
                raise ValueError(
                    "multiple attribution requires at least two components"
                )
        elif self.kind is AttributionKind.AMBIGUOUS:
            if count == 1 or not present(self.reason):
                raise ValueError(
                    "ambiguous attribution requires a reason and zero or "
                    "two-plus candidates"
                )
        elif count or self.reason is not None:
            raise ValueError("unobserved attribution forbids components and a reason")
        return self


class EvidenceHandleV1(AgentAuthorityOperatorModel):
    handle: str = Field(min_length=1)
    kind: EvidenceKind
    digest: DigestV2
    collection_status: CollectionStatus
    redaction_status: RedactionStatus


class SyntheticSecretHandleV1(SyntheticModel):
    """Opaque fictional canary/credential handle; never credential material."""

    handle: str = Field(pattern=r"^synthetic-secret:[a-z0-9][a-z0-9._:-]*$")


def require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("timestamp must be UTC")
    return value


def present(value: str | None) -> bool:
    return value is not None and bool(value.strip())


def canonical_unique(values: tuple[str, ...], description: str) -> tuple[str, ...]:
    if any(not value.strip() for value in values):
        raise ValueError(f"{description} must be nonblank")
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{description} must be sorted and unique")
    return values


def unique(values: tuple[str, ...], description: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{description} must be unique")


__all__ = [
    "AGENT_AUTHORITY_OBSERVATIONS_SCHEMA_VERSION",
    "AGENT_AUTHORITY_PRODUCT_INPUT_SCHEMA_VERSION",
    "AGENT_AUTHORITY_PROTOCOL_VERSION",
    "AGENT_AUTHORITY_REPORT_SCHEMA_VERSION",
    "AGENT_AUTHORITY_RUN_PLAN_SCHEMA_VERSION",
    "AGENT_AUTHORITY_TRUTH_SCHEMA_VERSION",
    "BOUND_UNIT_NS",
    "CONTROL_LAYERS",
    "CONTROL_ORDER",
    "LAB_CONTROL_IDS",
    "OPERATIONAL_CONTROL_IDS",
    "AgentAuthorityBenchmarkBindingV1",
    "AgentAuthorityControlId",
    "AgentAuthorityOperatorModel",
    "AttributionKind",
    "BoundMetric",
    "BoundUnit",
    "CollectionStatus",
    "ControlCoverageEntryV1",
    "ControlLayer",
    "CoverageDisposition",
    "DeclaredBoundV1",
    "DeploymentPattern",
    "DirectPathReachability",
    "EvidenceHandleV1",
    "EvidenceKind",
    "FindingStatus",
    "ObservationAttributionV1",
    "ObservedDecision",
    "ObservedSideEffect",
    "RedactionStatus",
    "RunLayer",
    "SyntheticSecretHandleV1",
    "canonical_unique",
    "present",
    "require_utc",
    "unique",
]
