"""Predeclared L07/L08 coverage and marker-neutral operational observations."""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated, Literal, Self, cast

from pydantic import Field, field_validator, model_validator

from synthworld.agent_authority.common import (
    AgentAuthorityControlId,
    AgentAuthorityOperatorModel,
    DeploymentPattern,
    canonical_unique,
    present,
    unique,
)
from synthworld.models import SyntheticModel


class PerformanceStageRole(StrEnum):
    BASELINE = "baseline"
    SUT = "sut"


class ArrivalModel(StrEnum):
    FIXED_RATE = "fixed_rate"
    CLOSED_LOOP = "closed_loop"


class LatencyStatistic(StrEnum):
    P50 = "p50"
    P95 = "p95"
    P99 = "p99"


class LoadProfileV1(AgentAuthorityOperatorModel):
    request_count: int = Field(gt=0)
    max_concurrency: int = Field(gt=0)
    arrival_model: ArrivalModel
    rate_numerator: int | None = Field(default=None, gt=0)
    rate_denominator: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_rate(self) -> Self:
        values = (self.rate_numerator, self.rate_denominator)
        if self.arrival_model is ArrivalModel.FIXED_RATE:
            if any(value is None for value in values):
                raise ValueError("fixed-rate load requires a rational rate")
            numerator, denominator = values
            if math.gcd(cast(int, numerator), cast(int, denominator)) != 1:
                raise ValueError("fixed-rate load must use a reduced rational rate")
        elif any(value is not None for value in values):
            raise ValueError("closed-loop load forbids a fixed rate")
        return self


class PerformanceStageV1(AgentAuthorityOperatorModel):
    stage_id: str = Field(min_length=1)
    role: PerformanceStageRole
    component_id: str = Field(min_length=1)
    target_handle: str = Field(min_length=1)
    action_handle: str = Field(min_length=1)
    load_profile: LoadProfileV1
    measurement_window_ns: int = Field(gt=0)
    statistics: tuple[LatencyStatistic, ...] = Field(min_length=1)
    baseline_stage_id: str | None = None

    @field_validator("statistics")
    @classmethod
    def canonical_statistics(
        cls, value: tuple[LatencyStatistic, ...]
    ) -> tuple[LatencyStatistic, ...]:
        if value != tuple(sorted(set(value), key=str)):
            raise ValueError("latency statistics must be sorted and unique")
        return value

    @model_validator(mode="after")
    def validate_baseline_reference(self) -> Self:
        if self.role is PerformanceStageRole.SUT:
            if not present(self.baseline_stage_id):
                raise ValueError("a SUT stage requires a baseline stage")
        elif self.baseline_stage_id is not None:
            raise ValueError("a baseline stage forbids a baseline reference")
        return self


class CredentialKind(StrEnum):
    BEARER = "bearer"
    DPOP = "dpop"
    MTLS = "mtls"
    WORKLOAD_IDENTITY = "workload_identity"
    PROPRIETARY = "proprietary"


class SenderConstraint(StrEnum):
    BOUND = "bound"
    UNBOUND = "unbound"


class AuthorityCapabilityV1(AgentAuthorityOperatorModel):
    candidate_id: str = Field(min_length=1)
    credential_kind: CredentialKind
    actions: tuple[str, ...] = Field(min_length=1)
    scopes: tuple[str, ...] = Field(min_length=1)
    audiences: tuple[str, ...] = Field(min_length=1)
    sender_constraint: SenderConstraint
    maximum_lifetime_ns: int | None = Field(default=None, gt=0)

    @field_validator("actions", "scopes", "audiences")
    @classmethod
    def canonical_constraints(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_unique(value, "capability constraints")


class CompatibilityTargetV1(AgentAuthorityOperatorModel):
    coverage_key: str = Field(min_length=1)
    component_id: str = Field(min_length=1)
    target_handle: str = Field(min_length=1)
    applicable_patterns: tuple[DeploymentPattern, ...] = Field(min_length=1)
    action_universe: tuple[str, ...] = Field(min_length=1)
    scope_universe: tuple[str, ...] = Field(min_length=1)
    audience_universe: tuple[str, ...] = Field(min_length=1)
    probe_candidates: tuple[AuthorityCapabilityV1, ...] = Field(min_length=1)

    @field_validator("applicable_patterns")
    @classmethod
    def canonical_patterns(
        cls, value: tuple[DeploymentPattern, ...]
    ) -> tuple[DeploymentPattern, ...]:
        allowed = {
            DeploymentPattern.PROXY_INJECTION,
            DeploymentPattern.SHORT_LIVED_MINTING,
        }
        if not set(value) <= allowed:
            raise ValueError("compatibility targets accept only minting/proxy patterns")
        if value != tuple(sorted(set(value), key=str)):
            raise ValueError("compatibility patterns must be sorted and unique")
        return value

    @field_validator("action_universe", "scope_universe", "audience_universe")
    @classmethod
    def canonical_universe(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_unique(value, "compatibility target universe")

    @model_validator(mode="after")
    def validate_candidates(self) -> Self:
        unique(
            tuple(candidate.candidate_id for candidate in self.probe_candidates),
            "compatibility candidate identifiers",
        )
        if self.probe_candidates != tuple(
            sorted(self.probe_candidates, key=lambda item: item.candidate_id)
        ):
            raise ValueError("compatibility candidates must be canonically ordered")
        for candidate in self.probe_candidates:
            if not set(candidate.actions) <= set(self.action_universe):
                raise ValueError("candidate actions exceed the declared universe")
            if not set(candidate.scopes) <= set(self.scope_universe):
                raise ValueError("candidate scopes exceed the declared universe")
            if not set(candidate.audiences) <= set(self.audience_universe):
                raise ValueError("candidate audiences exceed the declared universe")
        return self


class OperationalCoveragePlanV1(AgentAuthorityOperatorModel):
    performance_stages: tuple[PerformanceStageV1, ...] = ()
    compatibility_targets: tuple[CompatibilityTargetV1, ...] = ()

    @model_validator(mode="after")
    def validate_inventory(self) -> Self:
        stages = tuple(item.stage_id for item in self.performance_stages)
        targets = tuple(item.coverage_key for item in self.compatibility_targets)
        unique(stages, "performance stage identifiers")
        unique(targets, "compatibility coverage keys")
        if stages != tuple(sorted(stages)):
            raise ValueError("performance stages must be canonically ordered")
        if targets != tuple(sorted(targets)):
            raise ValueError("compatibility targets must be canonically ordered")
        stage_index = {item.stage_id: item for item in self.performance_stages}
        for stage in self.performance_stages:
            if stage.role is not PerformanceStageRole.SUT:
                continue
            baseline = stage_index.get(stage.baseline_stage_id or "")
            if baseline is None or baseline.role is not PerformanceStageRole.BASELINE:
                raise ValueError("a SUT stage must reference a declared baseline")
            comparable = (
                baseline.target_handle,
                baseline.action_handle,
                baseline.load_profile,
                baseline.measurement_window_ns,
                baseline.statistics,
            )
            observed = (
                stage.target_handle,
                stage.action_handle,
                stage.load_profile,
                stage.measurement_window_ns,
                stage.statistics,
            )
            if observed != comparable:
                raise ValueError("a SUT stage must be comparable with its baseline")
        return self


class LatencyMeasurementV1(AgentAuthorityOperatorModel):
    measurement_kind: Literal["latency"] = "latency"
    statistic: LatencyStatistic
    value_ns: int = Field(ge=0)


class FailureRateMeasurementV1(AgentAuthorityOperatorModel):
    measurement_kind: Literal["failure_rate"] = "failure_rate"
    failed_count: int = Field(ge=0)
    total_count: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_count(self) -> Self:
        if self.failed_count > self.total_count:
            raise ValueError("failed count cannot exceed total count")
        return self


class ThroughputMeasurementV1(AgentAuthorityOperatorModel):
    measurement_kind: Literal["throughput"] = "throughput"
    completed_count: int = Field(ge=0)
    duration_ns: int = Field(gt=0)


OperationalMeasurementPayloadV1 = Annotated[
    LatencyMeasurementV1 | FailureRateMeasurementV1 | ThroughputMeasurementV1,
    Field(discriminator="measurement_kind"),
]


class OperationalMeasurementV1(AgentAuthorityOperatorModel):
    control_id: Literal[AgentAuthorityControlId.L07] = AgentAuthorityControlId.L07
    stage_id: str = Field(min_length=1)
    sample_count: int = Field(gt=0)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    payload: OperationalMeasurementPayloadV1

    @field_validator("evidence_refs")
    @classmethod
    def canonical_evidence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_unique(value, "operational evidence references")


class OperationalCoverageGapV1(AgentAuthorityOperatorModel):
    control_id: Literal[AgentAuthorityControlId.L07] = AgentAuthorityControlId.L07
    stage_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = ()

    @field_validator("evidence_refs")
    @classmethod
    def canonical_evidence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_unique(value, "operational gap evidence references")


class CandidateProbeOutcome(StrEnum):
    OBTAINED = "obtained"
    REJECTED = "rejected"
    FAILED = "failed"
    UNOBSERVED = "unobserved"


class CapabilityProbeResultV1(AgentAuthorityOperatorModel):
    candidate_id: str = Field(min_length=1)
    outcome: CandidateProbeOutcome
    evidence_refs: tuple[str, ...] = ()
    reason: str | None = None

    @field_validator("evidence_refs")
    @classmethod
    def canonical_evidence(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_unique(value, "candidate evidence references")

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.outcome in {
            CandidateProbeOutcome.REJECTED,
            CandidateProbeOutcome.FAILED,
            CandidateProbeOutcome.UNOBSERVED,
        }:
            if not present(self.reason):
                raise ValueError("non-obtained probes require a reason")
        elif self.reason is not None:
            raise ValueError("obtained probes forbid a failure reason")
        return self


class CompatibilityStatus(StrEnum):
    MEASURED = "measured"
    UNSUPPORTED = "unsupported"
    INCOMPLETE = "incomplete"
    NOT_ATTEMPTED = "not_attempted"


class TargetCompatibilityV1(AgentAuthorityOperatorModel):
    control_id: Literal[AgentAuthorityControlId.L08] = AgentAuthorityControlId.L08
    coverage_key: str = Field(min_length=1)
    component_id: str = Field(min_length=1)
    target_handle: str = Field(min_length=1)
    status: CompatibilityStatus
    candidate_results: tuple[CapabilityProbeResultV1, ...] = ()
    nondominated_minima: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    limitation: str | None = None

    @field_validator("nondominated_minima", "evidence_refs")
    @classmethod
    def canonical_values(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return canonical_unique(value, "compatibility values")

    @model_validator(mode="after")
    def validate_status_shape(self) -> Self:
        result_ids = tuple(item.candidate_id for item in self.candidate_results)
        unique(result_ids, "candidate result identifiers")
        if result_ids != tuple(sorted(result_ids)):
            raise ValueError("candidate results must be canonically ordered")
        outcomes = {item.outcome for item in self.candidate_results}
        if self.status is CompatibilityStatus.MEASURED:
            if (
                not self.candidate_results
                or CandidateProbeOutcome.OBTAINED not in outcomes
            ):
                raise ValueError(
                    "measured compatibility requires an obtained candidate"
                )
            if outcomes - {
                CandidateProbeOutcome.OBTAINED,
                CandidateProbeOutcome.REJECTED,
            }:
                raise ValueError("measured compatibility requires terminal results")
            if not self.nondominated_minima or self.limitation is not None:
                raise ValueError(
                    "measured compatibility requires minima and no limitation"
                )
        elif self.status is CompatibilityStatus.UNSUPPORTED:
            if (
                not self.candidate_results
                or outcomes != {CandidateProbeOutcome.REJECTED}
                or self.nondominated_minima
                or not self.evidence_refs
                or not present(self.limitation)
            ):
                raise ValueError(
                    "unsupported compatibility requires rejected candidates, evidence, "
                    "and a limitation"
                )
        elif self.status is CompatibilityStatus.INCOMPLETE:
            if (
                not self.candidate_results
                or not outcomes
                & {CandidateProbeOutcome.FAILED, CandidateProbeOutcome.UNOBSERVED}
                or self.nondominated_minima
                or not present(self.limitation)
            ):
                raise ValueError(
                    "incomplete compatibility requires a failed/unobserved result"
                )
        elif (
            self.candidate_results
            or self.nondominated_minima
            or not present(self.limitation)
        ):
            raise ValueError("not-attempted compatibility carries only a limitation")
        return self


class RationalValueV1(AgentAuthorityOperatorModel):
    numerator: int
    denominator: int = Field(gt=0)
    numerator_meaning: str = Field(min_length=1)
    denominator_meaning: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_reduced(self) -> Self:
        if math.gcd(abs(self.numerator), self.denominator) != 1:
            raise ValueError("rational values must be reduced")
        return self


class AddedLatencyMeasurementV1(SyntheticModel):
    sut_stage_id: str = Field(min_length=1)
    baseline_stage_id: str = Field(min_length=1)
    statistic: LatencyStatistic
    added_latency_ns: int


def capability_no_broader(
    candidate: AuthorityCapabilityV1, other: AuthorityCapabilityV1
) -> bool:
    if candidate.credential_kind is not other.credential_kind:
        return False
    if not set(candidate.actions) <= set(other.actions):
        return False
    if not set(candidate.scopes) <= set(other.scopes):
        return False
    if not set(candidate.audiences) <= set(other.audiences):
        return False
    if (
        candidate.sender_constraint is SenderConstraint.UNBOUND
        and other.sender_constraint is SenderConstraint.BOUND
    ):
        return False
    if other.maximum_lifetime_ns is None:
        return True
    return (
        candidate.maximum_lifetime_ns is not None
        and candidate.maximum_lifetime_ns <= other.maximum_lifetime_ns
    )


def capability_strictly_dominates(
    candidate: AuthorityCapabilityV1, other: AuthorityCapabilityV1
) -> bool:
    if not capability_no_broader(candidate, other):
        return False
    return (
        candidate.actions != other.actions
        or candidate.scopes != other.scopes
        or candidate.audiences != other.audiences
        or candidate.sender_constraint is not other.sender_constraint
        or candidate.maximum_lifetime_ns != other.maximum_lifetime_ns
    )


def nondominated_candidate_ids(
    candidates: tuple[AuthorityCapabilityV1, ...], obtained_ids: set[str]
) -> tuple[str, ...]:
    obtained = tuple(item for item in candidates if item.candidate_id in obtained_ids)
    return tuple(
        sorted(
            candidate.candidate_id
            for candidate in obtained
            if not any(
                other.candidate_id != candidate.candidate_id
                and capability_strictly_dominates(other, candidate)
                for other in obtained
            )
        )
    )


__all__ = [
    "AddedLatencyMeasurementV1",
    "ArrivalModel",
    "AuthorityCapabilityV1",
    "CandidateProbeOutcome",
    "CapabilityProbeResultV1",
    "CompatibilityStatus",
    "CompatibilityTargetV1",
    "CredentialKind",
    "FailureRateMeasurementV1",
    "LatencyMeasurementV1",
    "LatencyStatistic",
    "LoadProfileV1",
    "OperationalCoverageGapV1",
    "OperationalCoveragePlanV1",
    "OperationalMeasurementPayloadV1",
    "OperationalMeasurementV1",
    "PerformanceStageRole",
    "PerformanceStageV1",
    "RationalValueV1",
    "SenderConstraint",
    "TargetCompatibilityV1",
    "ThroughputMeasurementV1",
    "capability_no_broader",
    "capability_strictly_dominates",
    "nondominated_candidate_ids",
]
