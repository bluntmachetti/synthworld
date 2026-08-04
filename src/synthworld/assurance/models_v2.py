"""Marker-neutral models for the explicit assurance receipt v2 transition.

Receipt v1 is frozen and recursively inherits ``SyntheticModel``.  That is useful
for its historical byte contract but misleading for real vendor provenance.  The
models in this module deliberately use a separate strict base and never serialize
``synthetic``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from synthworld.assurance.models import (
    ArtifactPhase,
    ArtifactSerialization,
    EvaluationStatus,
    ExecutionStatus,
    TreeState,
)

RUN_RECEIPT_SCHEMA_VERSION_V2: Literal["2.0.0"] = "2.0.0"
EXECUTION_RECEIPT_SCHEMA_VERSION_V2: Literal["2.0.0"] = "2.0.0"


class ReceiptModelV2(BaseModel):
    """Immutable, strict base for real receipt-v2 records."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class DigestV2(ReceiptModelV2):
    algorithm: Literal["sha256"] = "sha256"
    value: str = Field(pattern=r"^[0-9a-f]{64}$")


class ConfigurationEntryV2(ReceiptModelV2):
    name: str = Field(min_length=1)
    value: str


class VersionBindingV2(ReceiptModelV2):
    role: str = Field(min_length=1)
    version: str = Field(min_length=1)


class SerializationConventionV2(ReceiptModelV2):
    name: Literal["synthworld-canonical-json-v1"] = "synthworld-canonical-json-v1"
    encoding: Literal["UTF-8"] = "UTF-8"
    object_key_order: Literal["lexicographic"] = "lexicographic"
    line_endings: Literal["LF"] = "LF"
    trailing_newline_count: Literal[1] = 1
    raw_product_output_preserved: Literal[True] = True


class EvidenceClaimV2(StrEnum):
    CANONICAL_CONFORMANCE = "canonical_conformance"
    VARIANT_ROBUSTNESS = "variant_robustness"
    GENERATED_TRANSFER_EVIDENCE = "generated_transfer_evidence"
    LIVE_LAB_CONFORMANCE = "live_lab_conformance"


class ReplayabilityV2(StrEnum):
    EXACT = "exact"
    CONFIGURATION_ONLY = "configuration_only"
    LIMITED = "limited"
    NOT_REPLAYABLE = "not_replayable"


class ConfigurationObservabilityV2(StrEnum):
    OBSERVED = "observed"
    PARTIAL = "partial"
    NOT_EXPOSED = "not_exposed"


class VersionObservabilityV2(StrEnum):
    OBSERVED = "observed"
    NOT_EXPOSED = "not_exposed"


class ComponentArtifactKindV2(StrEnum):
    SOURCE = "source"
    IMAGE = "image"
    PACKAGE = "package"
    EXECUTABLE = "executable"


class _HostedComponentFields(ReceiptModelV2):
    component_id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    artifact_kind: ComponentArtifactKindV2
    artifact_digest: DigestV2
    dependency_lock_digest: DigestV2
    configuration_digest: DigestV2
    tree_state: TreeState
    tree_digest: DigestV2 | None = None
    replayability: ReplayabilityV2
    replayability_limitation: str | None = None

    @model_validator(mode="after")
    def validate_hosted_provenance(self) -> Self:
        if (self.tree_state is TreeState.DIRTY) is not (self.tree_digest is not None):
            raise ValueError("only a dirty hosted component carries a tree digest")
        if self.replayability is ReplayabilityV2.EXACT:
            if self.replayability_limitation is not None:
                raise ValueError("exact replayability forbids a limitation")
        elif not _present(self.replayability_limitation):
            raise ValueError("non-exact replayability requires a limitation")
        return self


class SelfHostedComponentProvenanceV2(_HostedComponentFields):
    component_type: Literal["self_hosted"] = "self_hosted"


class ReferenceComponentProvenanceV2(_HostedComponentFields):
    component_type: Literal["reference"] = "reference"
    is_reference_implementation: Literal[True] = True


class ManagedServiceComponentProvenanceV2(ReceiptModelV2):
    component_type: Literal["managed_service"] = "managed_service"
    component_id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    product: str = Field(min_length=1)
    release_identifier: str | None = None
    build_identifier: str | None = None
    cell_identifier: str | None = None
    region_identifier: str | None = None
    configuration_observability: ConfigurationObservabilityV2
    configuration_digest: DigestV2 | None = None
    observed_configuration_fields: tuple[str, ...] = ()
    configuration_evidence_refs: tuple[str, ...] = ()
    configuration_capture_limitation: str | None = None
    version_observability: VersionObservabilityV2
    version_evidence_refs: tuple[str, ...] = ()
    replayability: Literal[
        ReplayabilityV2.CONFIGURATION_ONLY,
        ReplayabilityV2.LIMITED,
        ReplayabilityV2.NOT_REPLAYABLE,
    ]
    replayability_limitation: str = Field(min_length=1)

    @field_validator(
        "observed_configuration_fields",
        "configuration_evidence_refs",
        "version_evidence_refs",
    )
    @classmethod
    def require_canonical_unique_values(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_unique(value, "managed-service evidence/field values")

    @model_validator(mode="after")
    def validate_observability(self) -> Self:
        status = self.configuration_observability
        has_digest = self.configuration_digest is not None
        has_fields = bool(self.observed_configuration_fields)
        has_evidence = bool(self.configuration_evidence_refs)
        has_limitation = _present(self.configuration_capture_limitation)
        if status is ConfigurationObservabilityV2.OBSERVED:
            if not has_digest or not has_evidence:
                raise ValueError(
                    "observed configuration requires a complete digest and evidence"
                )
            if has_fields or self.configuration_capture_limitation is not None:
                raise ValueError(
                    "observed configuration forbids partial fields and a limitation"
                )
        elif status is ConfigurationObservabilityV2.PARTIAL:
            if not all((has_digest, has_fields, has_evidence, has_limitation)):
                raise ValueError(
                    "partial configuration requires digest, fields, evidence, "
                    "and limitation"
                )
        else:
            if has_digest or has_fields:
                raise ValueError(
                    "not-exposed configuration forbids a digest and observed fields"
                )
            if not has_limitation:
                raise ValueError(
                    "not-exposed configuration requires a capture limitation"
                )

        version_ids = (self.release_identifier, self.build_identifier)
        if self.version_observability is VersionObservabilityV2.OBSERVED:
            if not any(_present(item) for item in version_ids):
                raise ValueError(
                    "observed version requires a release or build identifier"
                )
            if not self.version_evidence_refs:
                raise ValueError("observed version requires evidence")
        elif any(item is not None for item in version_ids):
            raise ValueError(
                "not-exposed version forbids release and build identifiers"
            )
        return self


SystemComponentProvenanceV2 = Annotated[
    SelfHostedComponentProvenanceV2
    | ManagedServiceComponentProvenanceV2
    | ReferenceComponentProvenanceV2,
    Field(discriminator="component_type"),
]


class AdapterProvenanceV2(ReceiptModelV2):
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    source_digest: DigestV2
    boundary: str = Field(min_length=1)


class RepositoryProvenanceV2(ReceiptModelV2):
    name: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    tree_state: TreeState
    tree_digest: DigestV2 | None = None

    @model_validator(mode="after")
    def bind_dirty_state_to_digest(self) -> Self:
        if (self.tree_state is TreeState.DIRTY) is not (self.tree_digest is not None):
            raise ValueError("only a dirty source tree carries a tree digest")
        return self


class BenchmarkIdentityV2(ReceiptModelV2):
    family: str = Field(min_length=1)
    version: str = Field(min_length=1)
    package_version: str = Field(min_length=1)
    public_root_digest: DigestV2
    evaluator_root_digest: DigestV2
    identity_access_universe_digest: DigestV2 | None = None
    policy_digest: DigestV2 | None = None
    cell_digest: DigestV2 | None = None


class BuildEnvironmentV2(ReceiptModelV2):
    synthworld: RepositoryProvenanceV2
    dependency_lock_digest: DigestV2
    runtime_identifier: str = Field(min_length=1)
    platform_identifier: str = Field(min_length=1)


class RunMetadataV2(ReceiptModelV2):
    run_id: str = Field(min_length=1)
    operator_id: str = Field(min_length=1)
    started_at: datetime
    completed_at: datetime

    @field_validator("started_at", "completed_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("run timestamps must be UTC")
        return value

    @model_validator(mode="after")
    def require_forward_time(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("run completion cannot precede its start")
        return self


class ArtifactDescriptorV2(ReceiptModelV2):
    path: str = Field(min_length=1)
    role: str = Field(min_length=1)
    phase: ArtifactPhase
    media_type: str = Field(min_length=1)
    serialization: ArtifactSerialization
    digest: DigestV2
    byte_size: int = Field(ge=0)
    schema_version: str | None = None

    @field_validator("path")
    @classmethod
    def require_safe_canonical_relative_path(cls, value: str) -> str:
        parsed = PurePosixPath(value)
        if (
            value == "."
            or parsed.is_absolute()
            or ".." in parsed.parts
            or parsed.as_posix() != value
        ):
            raise ValueError("artifact paths must be canonical safe relative paths")
        return value


class ExecutionReceiptV2(ReceiptModelV2):
    schema_version: Literal["2.0.0"] = EXECUTION_RECEIPT_SCHEMA_VERSION_V2
    boundary: str = Field(min_length=1)
    callable_identifier: str = Field(min_length=1)
    adapter_name: str = Field(min_length=1)
    adapter_version: str = Field(min_length=1)
    adapter_source_digest: DigestV2
    systems_under_test: tuple[str, ...] = Field(min_length=1)
    run_plan_digest: DigestV2
    stimulus_digest: DigestV2
    source_public_digest: DigestV2
    product_input_digest: DigestV2
    product_output_digest: DigestV2
    exit_code: int
    status: ExecutionStatus

    @field_validator("systems_under_test")
    @classmethod
    def require_canonical_system_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_unique(value, "execution system identifiers")

    @model_validator(mode="after")
    def status_matches_exit_code(self) -> Self:
        expected = (
            ExecutionStatus.SUCCEEDED if self.exit_code == 0 else ExecutionStatus.FAILED
        )
        if self.status is not expected:
            raise ValueError("execution status must agree with the exit code")
        return self


class RunReceiptManifestV2(ReceiptModelV2):
    schema_version: Literal["2.0.0"] = RUN_RECEIPT_SCHEMA_VERSION_V2
    benchmark: BenchmarkIdentityV2
    build_environment: BuildEnvironmentV2
    run: RunMetadataV2
    schema_versions: tuple[VersionBindingV2, ...] = Field(min_length=1)
    scoring_formula_versions: tuple[VersionBindingV2, ...] = Field(min_length=1)
    generator_configuration: tuple[ConfigurationEntryV2, ...] = ()
    event_schedule: tuple[ConfigurationEntryV2, ...] = ()
    adapter: AdapterProvenanceV2
    systems_under_test: tuple[SystemComponentProvenanceV2, ...] = Field(min_length=1)
    digest_algorithm: Literal["sha256"] = "sha256"
    serialization: SerializationConventionV2 = SerializationConventionV2()
    artifacts: tuple[ArtifactDescriptorV2, ...] = Field(min_length=1)
    execution_status: ExecutionStatus
    evaluation_status: EvaluationStatus
    evidence_claim: EvidenceClaimV2

    @model_validator(mode="after")
    def validate_index(self) -> Self:
        _unique(tuple(item.path for item in self.artifacts), "artifact paths")
        _unique(tuple(item.role for item in self.artifacts), "artifact roles")
        _unique(
            tuple(item.role for item in self.schema_versions), "schema binding roles"
        )
        _unique(
            tuple(item.role for item in self.scoring_formula_versions),
            "scoring binding roles",
        )
        _unique(
            tuple(item.component_id for item in self.systems_under_test),
            "system component identifiers",
        )
        if "manifest.json" in {item.path for item in self.artifacts}:
            raise ValueError("manifest.json cannot contain its own digest")
        return self


def _present(value: str | None) -> bool:
    return value is not None and bool(value.strip())


def _unique(values: tuple[str, ...], description: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{description} must be unique")


def _canonical_unique(values: tuple[str, ...], description: str) -> tuple[str, ...]:
    if any(not value.strip() for value in values):
        raise ValueError(f"{description} must be nonblank")
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{description} must be sorted and unique")
    return values


__all__ = [
    "EXECUTION_RECEIPT_SCHEMA_VERSION_V2",
    "RUN_RECEIPT_SCHEMA_VERSION_V2",
    "AdapterProvenanceV2",
    "ArtifactDescriptorV2",
    "BenchmarkIdentityV2",
    "BuildEnvironmentV2",
    "ComponentArtifactKindV2",
    "ConfigurationEntryV2",
    "ConfigurationObservabilityV2",
    "DigestV2",
    "EvidenceClaimV2",
    "ExecutionReceiptV2",
    "ManagedServiceComponentProvenanceV2",
    "ReceiptModelV2",
    "ReferenceComponentProvenanceV2",
    "ReplayabilityV2",
    "RepositoryProvenanceV2",
    "RunMetadataV2",
    "RunReceiptManifestV2",
    "SelfHostedComponentProvenanceV2",
    "SerializationConventionV2",
    "SystemComponentProvenanceV2",
    "VersionBindingV2",
    "VersionObservabilityV2",
]
