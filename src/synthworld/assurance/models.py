"""Consumer-neutral provenance models for reproducible assurance receipts."""

from __future__ import annotations

from enum import StrEnum
from pathlib import PurePosixPath
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from synthworld.models import SyntheticModel

RUN_RECEIPT_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
EXECUTION_RECEIPT_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"


class TreeState(StrEnum):
    """Whether source provenance names a clean, dirty, or unavailable tree."""

    CLEAN = "clean"
    DIRTY = "dirty"
    UNKNOWN = "unknown"


class EvidenceClaim(StrEnum):
    """The population-level claim a receipt is allowed to support."""

    CANONICAL_CONFORMANCE = "canonical_conformance"
    VARIANT_ROBUSTNESS = "variant_robustness"
    GENERATED_TRANSFER_EVIDENCE = "generated_transfer_evidence"


class ArtifactPhase(StrEnum):
    PRODUCT = "product"
    EVALUATION = "evaluation"


class ArtifactSerialization(StrEnum):
    CANONICAL_JSON_V1 = "canonical_json_v1"
    RAW_BYTES = "raw_bytes"


class ExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class EvaluationStatus(StrEnum):
    EVALUATED = "evaluated"
    INVALID_SUBMISSION = "invalid_submission"
    NOT_EVALUATED = "not_evaluated"


class Digest(SyntheticModel):
    algorithm: Literal["sha256"] = "sha256"
    value: str = Field(pattern=r"^[0-9a-f]{64}$")


class ConfigurationEntry(SyntheticModel):
    name: str = Field(min_length=1)
    value: str


class VersionBinding(SyntheticModel):
    role: str = Field(min_length=1)
    version: str = Field(min_length=1)


class SerializationConvention(SyntheticModel):
    name: Literal["synthworld-canonical-json-v1"] = "synthworld-canonical-json-v1"
    encoding: Literal["UTF-8"] = "UTF-8"
    object_key_order: Literal["lexicographic"] = "lexicographic"
    line_endings: Literal["LF"] = "LF"
    trailing_newline_count: Literal[1] = 1
    raw_product_output_preserved: Literal[True] = True


class RepositoryProvenance(SyntheticModel):
    name: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    tree_state: TreeState
    tree_digest: Digest | None = None

    @model_validator(mode="after")
    def bind_dirty_state_to_digest(self) -> Self:
        if (self.tree_state is TreeState.DIRTY) is not (self.tree_digest is not None):
            raise ValueError("only a dirty source tree carries a tree digest")
        return self


class AdapterProvenance(SyntheticModel):
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    source_digest: Digest
    boundary: str = Field(min_length=1)


class SystemUnderTestProvenance(SyntheticModel):
    name: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    package_or_executable_digest: Digest
    dependency_lock_digest: Digest
    tree_state: TreeState
    tree_digest: Digest | None = None
    replayability: str = Field(min_length=1)

    @model_validator(mode="after")
    def bind_dirty_state_to_digest(self) -> Self:
        if (self.tree_state is TreeState.DIRTY) is not (self.tree_digest is not None):
            raise ValueError("only a dirty system source tree carries a tree digest")
        return self


class SeedPopulation(SyntheticModel):
    seeds: tuple[int, ...] = Field(min_length=1)
    description: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_seeds(self) -> Self:
        if len(self.seeds) != len(set(self.seeds)):
            raise ValueError("the declared seed population must not contain duplicates")
        return self


class ArtifactDescriptor(SyntheticModel):
    path: str = Field(min_length=1)
    role: str = Field(min_length=1)
    phase: ArtifactPhase
    media_type: str = Field(min_length=1)
    serialization: ArtifactSerialization
    digest: Digest
    byte_size: int = Field(ge=0)
    schema_version: str | None = None

    @field_validator("path")
    @classmethod
    def require_safe_canonical_relative_path(cls, value: str) -> str:
        parsed = PurePosixPath(value)
        if parsed.is_absolute() or ".." in parsed.parts or parsed.as_posix() != value:
            raise ValueError("artifact paths must be canonical safe relative paths")
        return value


class ExecutionReceipt(SyntheticModel):
    schema_version: Literal["1.0.0"] = EXECUTION_RECEIPT_SCHEMA_VERSION
    boundary: str = Field(min_length=1)
    callable_identifier: str = Field(min_length=1)
    adapter_name: str = Field(min_length=1)
    adapter_version: str = Field(min_length=1)
    adapter_source_digest: Digest
    source_public_digest: Digest
    product_input_digest: Digest
    product_output_digest: Digest
    exit_code: int
    status: ExecutionStatus

    @model_validator(mode="after")
    def status_matches_exit_code(self) -> Self:
        expected = (
            ExecutionStatus.SUCCEEDED if self.exit_code == 0 else ExecutionStatus.FAILED
        )
        if self.status is not expected:
            raise ValueError("execution status must agree with the exit code")
        return self


class RunReceiptManifest(SyntheticModel):
    schema_version: Literal["1.0.0"] = RUN_RECEIPT_SCHEMA_VERSION
    benchmark_family: str = Field(min_length=1)
    benchmark_version: str = Field(min_length=1)
    schema_versions: tuple[VersionBinding, ...] = Field(min_length=1)
    scoring_formula_versions: tuple[VersionBinding, ...] = Field(min_length=1)
    seed: int
    generator_configuration: tuple[ConfigurationEntry, ...]
    event_schedule: tuple[ConfigurationEntry, ...]
    synthworld: RepositoryProvenance
    adapter: AdapterProvenance
    system_under_test: SystemUnderTestProvenance
    digest_algorithm: Literal["sha256"] = "sha256"
    serialization: SerializationConvention = SerializationConvention()
    artifacts: tuple[ArtifactDescriptor, ...] = Field(min_length=1)
    execution_status: ExecutionStatus
    evaluation_status: EvaluationStatus
    seed_population: SeedPopulation
    evidence_claim: EvidenceClaim

    @model_validator(mode="after")
    def validate_index(self) -> Self:
        paths = tuple(item.path for item in self.artifacts)
        roles = tuple(item.role for item in self.artifacts)
        schema_roles = tuple(item.role for item in self.schema_versions)
        scoring_roles = tuple(item.role for item in self.scoring_formula_versions)
        if len(paths) != len(set(paths)):
            raise ValueError("manifest artifact paths must be unique")
        if len(roles) != len(set(roles)):
            raise ValueError("manifest artifact roles must be unique")
        if "manifest.json" in paths:
            raise ValueError("manifest.json cannot contain its own digest")
        if len(schema_roles) != len(set(schema_roles)):
            raise ValueError("manifest schema roles must be unique")
        if len(scoring_roles) != len(set(scoring_roles)):
            raise ValueError("manifest scoring roles must be unique")
        if self.seed not in self.seed_population.seeds:
            raise ValueError("the run seed must belong to the declared seed population")
        return self


__all__ = [
    "EXECUTION_RECEIPT_SCHEMA_VERSION",
    "RUN_RECEIPT_SCHEMA_VERSION",
    "AdapterProvenance",
    "ArtifactDescriptor",
    "ArtifactPhase",
    "ArtifactSerialization",
    "ConfigurationEntry",
    "Digest",
    "EvaluationStatus",
    "EvidenceClaim",
    "ExecutionReceipt",
    "ExecutionStatus",
    "RepositoryProvenance",
    "RunReceiptManifest",
    "SeedPopulation",
    "SerializationConvention",
    "SystemUnderTestProvenance",
    "TreeState",
    "VersionBinding",
]
