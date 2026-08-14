"""Versioned contracts for generated enterprise-agentic benchmark worlds."""

from __future__ import annotations

import hashlib
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, model_validator

from synthworld.agentic.models import (
    AgenticBenchmark,
    AgenticEvaluatorBundle,
    AgenticPublicBundle,
)
from synthworld.enterprise.canonical import canonical_json_bytes
from synthworld.models import SyntheticModel

ENTERPRISE_AGENTIC_GENERATION_CONFIG_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_AGENTIC_GENERATED_PROFILE_VERSION: Literal[
    "enterprise-agentic-generated-1.0.0"
] = "enterprise-agentic-generated-1.0.0"
ENTERPRISE_AGENTIC_GENERATOR_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_AGENTIC_CANONICAL_SERIALIZATION_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_AGENTIC_SMOKE_EVENT_SCHEDULE_VERSION: Literal["smoke-1.0.0"] = "smoke-1.0.0"
ENTERPRISE_AGENTIC_GENERATED_ARTIFACT_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_AGENTIC_GENERATED_METRICS_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"


class EnterpriseAgenticScaleTier(StrEnum):
    """Generated scale tiers implemented by this contract version."""

    SMOKE = "smoke"


class EnterpriseAgenticSmokeTopologyV1(SyntheticModel):
    """Bounded topology knobs for the first generated vertical."""

    organisation_count: Literal[1] = 1
    department_count: int = Field(default=4, strict=True, ge=2, le=8)
    human_principal_count: int = Field(default=25, strict=True, ge=4, le=100)
    logical_agent_count: int = Field(default=5, strict=True, ge=3, le=12)
    runtime_count: int = Field(default=8, strict=True, ge=3, le=24)
    resource_count: int = Field(default=6, strict=True, ge=3, le=24)

    @model_validator(mode="after")
    def require_representable_topology(self) -> Self:
        if self.logical_agent_count > self.human_principal_count:
            raise ValueError("logical agents cannot outnumber accountable humans")
        if self.runtime_count < self.logical_agent_count:
            raise ValueError("every logical agent requires at least one runtime")
        return self


class EnterpriseAgenticGenerationConfigV1(SyntheticModel):
    """Every explicit input that identifies a generated smoke world."""

    schema_version: Literal["1.0.0"] = (
        ENTERPRISE_AGENTIC_GENERATION_CONFIG_SCHEMA_VERSION
    )
    profile_version: Literal["enterprise-agentic-generated-1.0.0"] = (
        ENTERPRISE_AGENTIC_GENERATED_PROFILE_VERSION
    )
    generator_version: Literal["1.0.0"] = ENTERPRISE_AGENTIC_GENERATOR_VERSION
    canonical_serialization_version: Literal["1.0.0"] = (
        ENTERPRISE_AGENTIC_CANONICAL_SERIALIZATION_VERSION
    )
    event_schedule_version: Literal["smoke-1.0.0"] = (
        ENTERPRISE_AGENTIC_SMOKE_EVENT_SCHEDULE_VERSION
    )
    seed: int = Field(default=20_260_814, strict=True, ge=0, le=2**63 - 1)
    tier: Literal[EnterpriseAgenticScaleTier.SMOKE] = EnterpriseAgenticScaleTier.SMOKE
    topology: EnterpriseAgenticSmokeTopologyV1 = Field(
        default_factory=EnterpriseAgenticSmokeTopologyV1
    )


class EnterpriseAgenticBenchmarkIdentityV1(SyntheticModel):
    """Deterministic identity, excluding host/runtime observations."""

    profile_version: Literal["enterprise-agentic-generated-1.0.0"] = (
        ENTERPRISE_AGENTIC_GENERATED_PROFILE_VERSION
    )
    generator_version: Literal["1.0.0"] = ENTERPRISE_AGENTIC_GENERATOR_VERSION
    canonical_serialization_version: Literal["1.0.0"] = (
        ENTERPRISE_AGENTIC_CANONICAL_SERIALIZATION_VERSION
    )
    event_schedule_version: Literal["smoke-1.0.0"] = (
        ENTERPRISE_AGENTIC_SMOKE_EVENT_SCHEDULE_VERSION
    )
    tier: Literal[EnterpriseAgenticScaleTier.SMOKE] = EnterpriseAgenticScaleTier.SMOKE
    seed: int = Field(strict=True, ge=0, le=2**63 - 1)
    configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    world_id: str


class EnterpriseAgenticCountMetricV1(SyntheticModel):
    """A derived count with the collection used as its denominator."""

    name: str
    count: int = Field(ge=0)
    denominator: int = Field(ge=0)
    denominator_meaning: str

    @model_validator(mode="after")
    def require_supported_count(self) -> Self:
        if self.count > self.denominator:
            raise ValueError("metric count cannot exceed its denominator")
        if not self.denominator_meaning.strip():
            raise ValueError("metric denominator meaning must be nonblank")
        return self


class EnterpriseAgenticDistributionBinV1(SyntheticModel):
    """One derived distribution bucket with explicit support."""

    value: str
    count: int = Field(ge=0)
    denominator: int = Field(gt=0)
    denominator_meaning: str

    @model_validator(mode="after")
    def require_supported_count(self) -> Self:
        if self.count > self.denominator:
            raise ValueError("distribution count cannot exceed its denominator")
        if not self.denominator_meaning.strip():
            raise ValueError("distribution denominator meaning must be nonblank")
        return self


class EnterpriseAgenticIntegrityMetricsV1(SyntheticModel):
    """Independent topology, case, and integrity observations."""

    schema_version: Literal["1.0.0"] = (
        ENTERPRISE_AGENTIC_GENERATED_METRICS_SCHEMA_VERSION
    )
    counts: tuple[EnterpriseAgenticCountMetricV1, ...]
    owner_chain_depth_distribution: tuple[EnterpriseAgenticDistributionBinV1, ...]
    runtimes_per_agent_distribution: tuple[EnterpriseAgenticDistributionBinV1, ...]
    credential_runtime_binding_distribution: tuple[
        EnterpriseAgenticDistributionBinV1, ...
    ]
    delegation_depth_distribution: tuple[EnterpriseAgenticDistributionBinV1, ...]
    case_kind_distribution: tuple[EnterpriseAgenticDistributionBinV1, ...]
    principal_graph_component_count: int = Field(ge=0)
    referential_integrity: Literal[True] = True
    canonical_binding_integrity: Literal[True] = True


class EnterpriseAgenticGeneratedBenchmarkV1(SyntheticModel):
    """In-memory generated benchmark plus its identity and derived report."""

    config: EnterpriseAgenticGenerationConfigV1
    identity: EnterpriseAgenticBenchmarkIdentityV1
    public: AgenticPublicBundle
    evaluator: AgenticEvaluatorBundle
    metrics: EnterpriseAgenticIntegrityMetricsV1

    @model_validator(mode="after")
    def require_identity_binding(self) -> Self:
        _require_config_identity(self.config, self.identity)
        AgenticBenchmark(public=self.public, evaluator=self.evaluator)
        _require_world_identity(
            self.identity,
            self.public.snapshot.world_id,
            self.public.snapshot.seed,
        )
        return self


class EnterpriseAgenticGeneratedPublicV1(SyntheticModel):
    """Public product input with no evaluator answer-key fields."""

    schema_version: Literal["1.0.0"] = (
        ENTERPRISE_AGENTIC_GENERATED_ARTIFACT_SCHEMA_VERSION
    )
    config: EnterpriseAgenticGenerationConfigV1
    identity: EnterpriseAgenticBenchmarkIdentityV1
    benchmark: AgenticPublicBundle

    @model_validator(mode="after")
    def require_identity_binding(self) -> Self:
        _require_config_identity(self.config, self.identity)
        _require_world_identity(
            self.identity,
            self.benchmark.snapshot.world_id,
            self.benchmark.snapshot.seed,
        )
        return self


class EnterpriseAgenticGeneratedEvaluatorV1(SyntheticModel):
    """Evaluator-only truth bound to the complete public artifact set."""

    schema_version: Literal["1.0.0"] = (
        ENTERPRISE_AGENTIC_GENERATED_ARTIFACT_SCHEMA_VERSION
    )
    identity: EnterpriseAgenticBenchmarkIdentityV1
    public_artifact_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    benchmark: AgenticEvaluatorBundle
    metrics: EnterpriseAgenticIntegrityMetricsV1

    @model_validator(mode="after")
    def require_identity_binding(self) -> Self:
        _require_world_identity(
            self.identity,
            self.benchmark.world_id,
            self.benchmark.seed,
        )
        return self


class EnterpriseAgenticArtifactDescriptorV1(SyntheticModel):
    path: str
    byte_size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class EnterpriseAgenticGeneratedPublicManifestV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = (
        ENTERPRISE_AGENTIC_GENERATED_ARTIFACT_SCHEMA_VERSION
    )
    visibility: Literal["public"] = "public"
    artifact_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifacts: tuple[EnterpriseAgenticArtifactDescriptorV1, ...]
    oracle_free: Literal[True] = True


class EnterpriseAgenticGeneratedEvaluatorManifestV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = (
        ENTERPRISE_AGENTIC_GENERATED_ARTIFACT_SCHEMA_VERSION
    )
    visibility: Literal["evaluator"] = "evaluator"
    artifact_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    public_artifact_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifacts: tuple[EnterpriseAgenticArtifactDescriptorV1, ...]


def _require_config_identity(
    config: EnterpriseAgenticGenerationConfigV1,
    identity: EnterpriseAgenticBenchmarkIdentityV1,
) -> None:
    expected = (
        config.profile_version,
        config.generator_version,
        config.canonical_serialization_version,
        config.event_schedule_version,
        config.tier,
        config.seed,
        hashlib.sha256(canonical_json_bytes(config)).hexdigest(),
    )
    actual = (
        identity.profile_version,
        identity.generator_version,
        identity.canonical_serialization_version,
        identity.event_schedule_version,
        identity.tier,
        identity.seed,
        identity.configuration_sha256,
    )
    if actual != expected:
        raise ValueError("generated enterprise-agentic configuration identity differs")


def _require_world_identity(
    identity: EnterpriseAgenticBenchmarkIdentityV1,
    world_id: str,
    seed: int,
) -> None:
    if (world_id, seed) != (identity.world_id, identity.seed):
        raise ValueError("generated enterprise-agentic world identity differs")


__all__ = [name for name in globals() if name.startswith("EnterpriseAgentic")]
