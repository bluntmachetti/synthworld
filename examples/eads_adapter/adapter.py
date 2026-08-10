"""Deterministic repository-only EADS-shaped fixture adapter.

This module performs no network operations and makes no real-EADS compatibility
claim. It converts only the repository-owned source vintages in ``models.py``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import re
import stat
import tempfile
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Final, Literal, Self, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from examples.eads_adapter.models import (
    MAX_SOURCE_BYTES,
    MAX_SOURCE_DEPTH,
    MAX_SOURCE_NODES,
    MAX_SOURCE_TEXT_BYTES,
    CanonicalDomain,
    CanonicalOrganisation,
    SourceVintage,
    parse_source,
)
from synthworld.enterprise.canonical import (
    canonical_json_bytes,
    canonical_json_value_bytes,
)
from synthworld.enterprise.compiler import (
    EnterpriseCompileError,
    compile_enterprise_identity_access_universe,
)
from synthworld.enterprise.models import (
    AllSelectorV1,
    EnterpriseDirectoryRbacStateInputV1,
    EnterpriseIamUniverseExtensionV1,
    EnterpriseIdentityAccessBlueprintV1,
    EnterpriseIdentityAccessCompileBudgetV1,
    EnterpriseIdentityAccessCompileConfigV1,
    EnterpriseIdentityAccessCompileResultV1,
    EnterpriseIdentityAccessImportV1,
    GroupRoleAssignmentV1,
    GroupTemplateV1,
    OrganisationTemplateV1,
    PopulationGroupMembershipRuleV1,
    PopulationTemplateV1,
    PrincipalKind,
    PrincipalSubjectAccessAtomRuleV1,
    ResourceSetTemplateV1,
    RoleGrantV1,
    RoleTemplateV1,
    TargetKind,
    TenantTemplateV1,
    UnitKind,
    UnitTemplateV1,
)
from synthworld.enterprise.serialization import (
    EVALUATOR_BINDING_PATH,
    EVALUATOR_MANIFEST_PATH,
    PUBLIC_MANIFEST_PATH,
    PUBLIC_UNIVERSE_PATH,
    export_enterprise_identity_access_compile_result,
)
from synthworld.enterprise.validation import validate_enterprise_identity_access

type AdapterSchemaVersion = Literal["2.0.0"]
type AdapterVersion = Literal["repository-eads-shaped-structure-v1"]
type MappingVersion = Literal["eads-enterprise-mapping-v1"]
type PopulationPolicyVersion = Literal["eads-human-population-policy-v1"]
type SourceContract = Literal["repository-fictional-eads-shaped-v1"]
type ArtifactDigestProfile = Literal["path-bound-artifact-records-v1"]

REPORT_SCHEMA_VERSION: Final[AdapterSchemaVersion] = "2.0.0"
ADAPTER_VERSION: Final[AdapterVersion] = "repository-eads-shaped-structure-v1"
MAPPING_VERSION: Final[MappingVersion] = "eads-enterprise-mapping-v1"
POPULATION_POLICY_VERSION: Final[PopulationPolicyVersion] = (
    "eads-human-population-policy-v1"
)
SOURCE_CONTRACT: Final[SourceContract] = "repository-fictional-eads-shaped-v1"
ARTIFACT_DIGEST_PROFILE: Final[ArtifactDigestProfile] = "path-bound-artifact-records-v1"
REPORT_PATH = "private/reports/eads-adapter-gap-report.json"
MAX_SEED = (1 << 63) - 1

# This value is retained only to preserve PR 105's deterministic enterprise IDs.
# It is not an external compatibility or source-schema claim.
_IDENTIFIER_DERIVATION_VERSION = "eads-phase-1-v1"
_INVALID_SOURCE_DIGEST = hashlib.sha256(b"invalid-json-native-payload").hexdigest()
_TOKEN_SEPARATOR = re.compile(r"[^a-z0-9]+", flags=re.ASCII)

_SCALE_BASE = {
    "micro": 4,
    "small": 8,
    "medium": 16,
    "large": 32,
    "enterprise": 64,
}
_TEAM_FACTORS = {
    "product": (3, 2),
    "operations": (5, 4),
    "control": (1, 1),
    "platform": (3, 2),
}
_TEAM_ALIASES = {
    "controls": "control",
    "ops": "operations",
    "product_team": "product",
    "platform_team": "platform",
}
_INDUSTRY_FACTORS = {
    "banking": (5, 4),
    "financial_services": (5, 4),
    "healthcare": (5, 4),
    "logistics": (1, 1),
    "public_services": (1, 1),
    "research": (1, 1),
    "technology": (3, 2),
}
_GENERAL_FACTOR = (1, 1)

_SERVICE_TYPES = {
    "api": TargetKind.API,
    "application": TargetKind.APPLICATION,
    "data_store": TargetKind.DATA_STORE,
    "environment": TargetKind.ENVIRONMENT,
    "tool": TargetKind.TOOL,
}
_SERVICE_ALIASES = {
    "app": "application",
    "data": "data_store",
    "database": "data_store",
    "datastore": "data_store",
    "env": "environment",
}
_ACTIONS = {
    TargetKind.APPLICATION: ("administer", "approve", "use"),
    TargetKind.API: ("administer", "approve", "invoke"),
    TargetKind.TOOL: ("administer", "approve", "use"),
    TargetKind.DATA_STORE: ("administer", "approve", "read", "write"),
    TargetKind.ENVIRONMENT: ("administer", "approve", "deploy", "read"),
}
_OWNERSHIP_ACTION = {"owner": "administer", "approver": "approve"}


class ArtifactVisibility(StrEnum):
    EVALUATOR = "evaluator"
    PRIVATE = "private"
    PUBLIC = "public"


class ArtifactKind(StrEnum):
    EVALUATOR_MANIFEST = "evaluator_manifest"
    EVALUATOR_TRUTH = "evaluator_truth"
    PRIVATE_IMPORT = "private_import"
    PUBLIC_INPUT = "public_input"
    PUBLIC_MANIFEST = "public_manifest"


class AdapterCode(StrEnum):
    ADAPTER_MODEL_VALIDATION_FAILED = "adapter_model_validation_failed"
    DECLARED_OWNER_DIVERGES = "declared_owner_diverges_from_owning_team"
    DEEP_HIERARCHY_COLLAPSED = "deep_hierarchy_collapsed"
    DUPLICATE_DOMAIN_ID = "duplicate_domain_id"
    DUPLICATE_NORMALIZED_OWNERSHIP = "duplicate_normalized_ownership"
    DUPLICATE_ORGANISATION_ID = "duplicate_organisation_id"
    DUPLICATE_REGION_ID = "duplicate_region_id"
    DUPLICATE_SERVICE_ID = "duplicate_service_id"
    DUPLICATE_TEAM_ID = "duplicate_team_id"
    ENTERPRISE_COMPILE_FAILED = "enterprise_compile_failed"
    ENTERPRISE_VALIDATION_FAILED = "enterprise_validation_failed"
    IGNORED_SOURCE_POPULATION_FIELD = "ignored_source_population_field"
    NO_ORGANISATIONS_COMPILED = "no_organisations_compiled"
    NO_SUPPORTED_ACCESS_MAPPING = "no_supported_access_mapping"
    ORGANISATION_FAILURES_PRESENT = "organisation_failures_present"
    OUTPUT_PARENT_NOT_DIRECTORY = "output_parent_not_directory"
    OUTPUT_PARENT_SYMLINK = "output_parent_symlink"
    OUTPUT_ROOT_EXISTS = "output_root_exists"
    PATH_SAFETY_UNAVAILABLE = "path_safety_unavailable"
    POPULATION_CAP_BELOW_TEAM_COUNT = "population_cap_below_team_count"
    SOURCE_BYTE_LIMIT_EXCEEDED = "source_byte_limit_exceeded"
    SOURCE_DEPTH_LIMIT_EXCEEDED = "source_depth_limit_exceeded"
    SOURCE_NODE_LIMIT_EXCEEDED = "source_node_limit_exceeded"
    SOURCE_PAYLOAD_NOT_JSON_COMPATIBLE = "source_payload_not_json_compatible"
    SOURCE_TEXT_BYTE_LIMIT_EXCEEDED = "source_text_byte_limit_exceeded"
    SOURCE_TEXT_NOT_NFC = "source_text_not_nfc"
    SOURCE_VALIDATION_FAILED = "source_validation_failed"
    UNKNOWN_INDUSTRY = "unknown_industry"
    UNKNOWN_SCALE = "unknown_scale"
    UNKNOWN_TEAM_TYPE = "unknown_team_type"
    UNEXPRESSED_REGION_METADATA = "unexpressed_region_metadata"
    UNEXPRESSED_SERVICE_CLASSIFICATION = "unexpressed_service_classification"
    UNMAPPED_SERVICE_TYPE = "unmapped_service_type"
    UNSUPPORTED_OWNERSHIP_SEMANTICS = "unsupported_ownership_semantics"
    DANGLING_DOMAIN_REFERENCE = "dangling_domain_reference"
    DANGLING_REGION_REFERENCE = "dangling_region_reference"
    DANGLING_SERVICE_REFERENCE = "dangling_service_reference"
    DANGLING_TEAM_REFERENCE = "dangling_team_reference"
    NULL_CLASSIFICATION = "null_classification"
    OWNERSHIP_WIDENED_TO_TEAM_POPULATION = "ownership_widened_to_team_population"


class RunStatus(StrEnum):
    FAILED = "failed"
    SUCCEEDED = "succeeded"


class OrganisationStatus(StrEnum):
    COMPILED = "compiled"
    FAILED = "failed"


class CompileStatus(StrEnum):
    FAILED = "failed"
    NOT_RUN = "not_run"
    SUCCEEDED = "succeeded"


class _StrictFrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class AdapterConfig(_StrictFrozenModel):
    """Explicit deterministic adapter controls."""

    seed: int = Field(ge=0, le=MAX_SEED)
    namespace_salt: str = Field(pattern=r"^[0-9a-f]{64}$")
    max_principals_per_organisation: int = Field(
        default=10_000,
        gt=0,
        le=1_000_000,
    )


class AdapterGap(_StrictFrozenModel):
    code: AdapterCode
    organisation_ref: str = Field(min_length=1)
    subject_ref: str | None = Field(default=None, min_length=1)


class DownscaleDeclaration(_StrictFrozenModel):
    applied: bool
    raw_total: int = Field(ge=0)
    emitted_total: int = Field(ge=0)
    numerator: int = Field(gt=0)
    denominator: int = Field(gt=0)

    @model_validator(mode="after")
    def valid_ratio(self) -> Self:
        if self.emitted_total > self.raw_total:
            raise ValueError("downscale_emitted_exceeds_raw")
        if not self.applied:
            if (
                self.raw_total != self.emitted_total
                or self.numerator != 1
                or self.denominator != 1
            ):
                raise ValueError("inactive_downscale_inconsistent")
        elif (
            self.emitted_total >= self.raw_total
            or self.emitted_total * self.denominator != self.raw_total * self.numerator
            or math.gcd(self.numerator, self.denominator) != 1
        ):
            raise ValueError("active_downscale_inconsistent")
        return self


class ArtifactRecord(_StrictFrozenModel):
    path: str = Field(min_length=1)
    visibility: ArtifactVisibility
    kind: ArtifactKind
    byte_size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("path")
    @classmethod
    def safe_relative_path(cls, value: str) -> str:
        parsed = PurePosixPath(value)
        if (
            value.startswith("/")
            or "\\" in value
            or value != parsed.as_posix()
            or any(part in {"", ".", ".."} for part in parsed.parts)
        ):
            raise ValueError("artifact_path_not_safe_relative_posix")
        return value

    @model_validator(mode="after")
    def visibility_matches_path(self) -> Self:
        if self.visibility is ArtifactVisibility.PRIVATE:
            valid = self.path.startswith("private/")
        elif self.visibility is ArtifactVisibility.PUBLIC:
            valid = "/public/" in self.path and self.path.startswith("artifacts/")
        else:
            valid = "/evaluator/" in self.path and self.path.startswith("artifacts/")
        if not valid:
            raise ValueError("artifact_visibility_path_mismatch")
        return self


def _require_canonical_artifacts(
    value: tuple[ArtifactRecord, ...],
) -> tuple[ArtifactRecord, ...]:
    paths = tuple(item.path for item in value)
    if len(paths) != len(set(paths)):
        raise ValueError("duplicate_adapter_artifact")
    if paths != tuple(sorted(paths)):
        raise ValueError("adapter_artifacts_not_canonical")
    return value


class OrganisationOutcome(_StrictFrozenModel):
    organisation_ref: str = Field(min_length=1)
    status: OrganisationStatus
    compile_status: CompileStatus
    error_code: AdapterCode | None = None
    artifacts: tuple[ArtifactRecord, ...] = ()
    raw_population: int = Field(ge=0)
    emitted_population: int = Field(ge=0)
    downscale: DownscaleDeclaration | None = None

    _canonical_artifacts = field_validator("artifacts")(_require_canonical_artifacts)

    @model_validator(mode="after")
    def coherent_status(self) -> Self:
        if self.status is OrganisationStatus.COMPILED:
            if (
                self.compile_status is not CompileStatus.SUCCEEDED
                or self.error_code is not None
                or len(self.artifacts) != 5
                or self.downscale is None
                or self.emitted_population <= 0
            ):
                raise ValueError("compiled_outcome_inconsistent")
        elif (
            self.compile_status is CompileStatus.SUCCEEDED
            or self.error_code is None
            or self.artifacts
        ):
            raise ValueError("failed_outcome_inconsistent")
        return self


class AdapterRunReport(_StrictFrozenModel):
    """Private, path-bound report for one repository-only adapter invocation."""

    schema_version: AdapterSchemaVersion = REPORT_SCHEMA_VERSION
    adapter_version: AdapterVersion = ADAPTER_VERSION
    source_contract: SourceContract = SOURCE_CONTRACT
    source_vintage: SourceVintage
    canonical_source_payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    mapping_version: MappingVersion = MAPPING_VERSION
    population_policy_version: PopulationPolicyVersion = POPULATION_POLICY_VERSION
    seed: int = Field(ge=0, le=MAX_SEED)
    max_principals_per_organisation: int = Field(gt=0, le=1_000_000)
    namespace_salt_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    adapter_config_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    repository_only: Literal[True] = True
    network_access: Literal[False] = False
    real_eads_compatibility: Literal[False] = False
    status: RunStatus
    error_code: AdapterCode | None = None
    gaps: tuple[AdapterGap, ...] = ()
    outcomes: tuple[OrganisationOutcome, ...] = ()
    private_artifacts: tuple[ArtifactRecord, ...] = ()
    public_artifacts: tuple[ArtifactRecord, ...] = ()
    evaluator_artifacts: tuple[ArtifactRecord, ...] = ()
    artifact_set_digest_profile: ArtifactDigestProfile = ARTIFACT_DIGEST_PROFILE
    artifact_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_set_excludes: tuple[
        Literal["private/reports/eads-adapter-gap-report.json"], ...
    ] = ("private/reports/eads-adapter-gap-report.json",)

    @field_validator("gaps")
    @classmethod
    def canonical_gaps(cls, value: tuple[AdapterGap, ...]) -> tuple[AdapterGap, ...]:
        keys = tuple(
            (item.organisation_ref, item.code.value, item.subject_ref or "")
            for item in value
        )
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate_adapter_gap")
        if keys != tuple(sorted(keys)):
            raise ValueError("adapter_gaps_not_canonical")
        return value

    @field_validator("outcomes")
    @classmethod
    def canonical_outcomes(
        cls,
        value: tuple[OrganisationOutcome, ...],
    ) -> tuple[OrganisationOutcome, ...]:
        identities = tuple(item.organisation_ref for item in value)
        if len(identities) != len(set(identities)):
            raise ValueError("duplicate_organisation_outcome")
        if identities != tuple(sorted(identities)):
            raise ValueError("organisation_outcomes_not_canonical")
        return value

    _canonical_private = field_validator("private_artifacts")(
        _require_canonical_artifacts
    )
    _canonical_public = field_validator("public_artifacts")(
        _require_canonical_artifacts
    )
    _canonical_evaluator = field_validator("evaluator_artifacts")(
        _require_canonical_artifacts
    )

    @model_validator(mode="after")
    def coherent_report(self) -> Self:
        expected_config_digest = _adapter_config_digest_values(
            seed=self.seed,
            max_principals_per_organisation=self.max_principals_per_organisation,
            namespace_salt_fingerprint=self.namespace_salt_fingerprint,
        )
        if self.adapter_config_digest != expected_config_digest:
            raise ValueError("adapter_config_digest_mismatch")

        inventories = (
            self.private_artifacts + self.public_artifacts + self.evaluator_artifacts
        )
        inventory_paths = tuple(item.path for item in inventories)
        if len(inventory_paths) != len(set(inventory_paths)):
            raise ValueError("cross_visibility_artifact_duplicate")
        outcome_artifacts = tuple(
            sorted(
                (
                    artifact
                    for outcome in self.outcomes
                    for artifact in outcome.artifacts
                ),
                key=lambda item: item.path,
            )
        )
        if tuple(sorted(inventories, key=lambda item: item.path)) != outcome_artifacts:
            raise ValueError("outcome_artifact_inventory_mismatch")
        if self.artifact_set_digest != _artifact_set_digest(inventories):
            raise ValueError("artifact_set_digest_mismatch")

        compiled = any(
            outcome.status is OrganisationStatus.COMPILED for outcome in self.outcomes
        )
        failed = any(
            outcome.status is OrganisationStatus.FAILED for outcome in self.outcomes
        )
        if self.status is RunStatus.SUCCEEDED:
            if not compiled or failed or self.error_code is not None:
                raise ValueError("successful_report_inconsistent")
        elif self.error_code is None:
            raise ValueError("failed_report_error_required")
        return self


@dataclass(frozen=True, slots=True)
class _DomainEntry:
    domain: CanonicalDomain
    parent_id: str | None
    depth: int


@dataclass(frozen=True, slots=True)
class _PreparedOrganisation:
    imported: EnterpriseIdentityAccessImportV1
    gaps: tuple[AdapterGap, ...]
    raw_population: int
    emitted_population: int
    downscale: DownscaleDeclaration


class SourcePayloadError(ValueError):
    def __init__(self, code: AdapterCode) -> None:
        super().__init__(code.value)
        self.code = code


class AdapterPathError(ValueError):
    def __init__(self, code: AdapterCode) -> None:
        super().__init__(code.value)
        self.code = code


class _AdapterError(Exception):
    def __init__(
        self,
        code: AdapterCode,
        gaps: Sequence[AdapterGap] = (),
    ) -> None:
        super().__init__(code.value)
        self.code = code
        self.gaps = tuple(gaps)


def _snapshot_source_payload(payload: Mapping[str, object]) -> bytes:
    """Return one immutable canonical snapshot for digesting and model parsing."""
    nodes = 0

    def snapshot(value: object, depth: int) -> object:
        nonlocal nodes
        nodes += 1
        if nodes > MAX_SOURCE_NODES:
            raise SourcePayloadError(AdapterCode.SOURCE_NODE_LIMIT_EXCEEDED)
        if depth > MAX_SOURCE_DEPTH:
            raise SourcePayloadError(AdapterCode.SOURCE_DEPTH_LIMIT_EXCEEDED)
        if value is None or isinstance(value, bool | int):
            return value
        if isinstance(value, float):
            if not math.isfinite(value):
                raise SourcePayloadError(AdapterCode.SOURCE_PAYLOAD_NOT_JSON_COMPATIBLE)
            return value
        if isinstance(value, str):
            if unicodedata.normalize("NFC", value) != value:
                raise SourcePayloadError(AdapterCode.SOURCE_TEXT_NOT_NFC)
            if len(value.encode("utf-8")) > MAX_SOURCE_TEXT_BYTES:
                raise SourcePayloadError(AdapterCode.SOURCE_TEXT_BYTE_LIMIT_EXCEEDED)
            return value
        if isinstance(value, Mapping):
            result: dict[str, object] = {}
            for key, nested in value.items():
                if not isinstance(key, str):
                    raise SourcePayloadError(
                        AdapterCode.SOURCE_PAYLOAD_NOT_JSON_COMPATIBLE
                    )
                if unicodedata.normalize("NFC", key) != key:
                    raise SourcePayloadError(AdapterCode.SOURCE_TEXT_NOT_NFC)
                if len(key.encode("utf-8")) > MAX_SOURCE_TEXT_BYTES:
                    raise SourcePayloadError(
                        AdapterCode.SOURCE_TEXT_BYTE_LIMIT_EXCEEDED
                    )
                if key in result:
                    raise SourcePayloadError(
                        AdapterCode.SOURCE_PAYLOAD_NOT_JSON_COMPATIBLE
                    )
                result[key] = snapshot(nested, depth + 1)
            return result
        if isinstance(value, list | tuple):
            return [snapshot(item, depth + 1) for item in value]
        raise SourcePayloadError(AdapterCode.SOURCE_PAYLOAD_NOT_JSON_COMPATIBLE)

    plain = snapshot(payload, 0)
    if not isinstance(plain, dict):
        raise SourcePayloadError(AdapterCode.SOURCE_PAYLOAD_NOT_JSON_COMPATIBLE)
    try:
        canonical_bytes = canonical_json_value_bytes(plain)
    except (TypeError, ValueError) as error:
        raise SourcePayloadError(
            AdapterCode.SOURCE_PAYLOAD_NOT_JSON_COMPATIBLE
        ) from error
    if len(canonical_bytes) > MAX_SOURCE_BYTES:
        raise SourcePayloadError(AdapterCode.SOURCE_BYTE_LIMIT_EXCEEDED)
    return canonical_bytes


def run_adapter(
    *,
    payload: Mapping[str, object],
    vintage: SourceVintage | str,
    output_dir: Path,
    config: AdapterConfig,
) -> AdapterRunReport:
    """Adapt one repository fixture through a staged, non-replacing promotion.

    Promotion is an atomic same-filesystem rename when the destination remains
    absent and the parent is not concurrently mutated. This repository example is
    not a hostile multi-writer filesystem isolation primitive.
    """
    selected_vintage = SourceVintage(vintage)
    output_root = Path(os.path.abspath(output_dir))
    _prepare_output_parent(output_root)
    with tempfile.TemporaryDirectory(
        dir=output_root.parent,
        prefix=f".{output_root.name}.eads-shaped-adapter-",
    ) as temporary:
        staged_output = Path(temporary) / "result"
        report = _run_adapter(
            payload=payload,
            vintage=selected_vintage,
            output_dir=staged_output,
            config=config,
        )
        _promote_staged_output(staged_output, output_root)
    return report


def _run_adapter(
    *,
    payload: Mapping[str, object],
    vintage: SourceVintage,
    output_dir: Path,
    config: AdapterConfig,
) -> AdapterRunReport:
    try:
        snapshot_bytes = _snapshot_source_payload(payload)
    except SourcePayloadError as error:
        report = _build_report(
            config=config,
            source_vintage=vintage,
            source_digest=_INVALID_SOURCE_DIGEST,
            status=RunStatus.FAILED,
            error_code=error.code,
        )
        _write_report(output_dir, report)
        return report

    source_digest = hashlib.sha256(snapshot_bytes).hexdigest()
    try:
        parsed_snapshot = json.loads(snapshot_bytes)
        if not isinstance(parsed_snapshot, dict):
            raise TypeError("source snapshot must decode to a mapping")
        source = parse_source(
            cast(dict[str, object], parsed_snapshot),
            vintage,
        )
    except (json.JSONDecodeError, TypeError, ValueError, ValidationError):
        report = _build_report(
            config=config,
            source_vintage=vintage,
            source_digest=source_digest,
            status=RunStatus.FAILED,
            error_code=AdapterCode.SOURCE_VALIDATION_FAILED,
        )
        _write_report(output_dir, report)
        return report

    gaps: list[AdapterGap] = []
    outcomes: list[OrganisationOutcome] = []

    def opaque(kind: str, *parts: str) -> str:
        return _opaque(config.namespace_salt, kind, *parts)

    id_counts = Counter(item.organisation_id for item in source.organisations)
    duplicate_ids = {key for key, count in id_counts.items() if count > 1}
    organisations = sorted(
        (
            item
            for item in source.organisations
            if item.organisation_id not in duplicate_ids
        ),
        key=lambda item: opaque("organisation", item.organisation_id),
    )

    for duplicate_id in sorted(duplicate_ids):
        organisation_ref = opaque("organisation", duplicate_id)
        gaps.append(
            AdapterGap(
                code=AdapterCode.DUPLICATE_ORGANISATION_ID,
                organisation_ref=organisation_ref,
            )
        )
        outcomes.append(
            _failed_outcome(
                organisation_ref,
                AdapterCode.DUPLICATE_ORGANISATION_ID,
            )
        )

    for organisation in organisations:
        organisation_ref = opaque("organisation", organisation.organisation_id)
        try:
            prepared = _prepare_organisation(organisation, organisation_ref, config)
        except _AdapterError as error:
            gaps.extend(error.gaps)
            gaps.append(AdapterGap(code=error.code, organisation_ref=organisation_ref))
            outcomes.append(_failed_outcome(organisation_ref, error.code))
            continue
        except (TypeError, ValueError, ValidationError):
            code = AdapterCode.ADAPTER_MODEL_VALIDATION_FAILED
            gaps.append(AdapterGap(code=code, organisation_ref=organisation_ref))
            outcomes.append(_failed_outcome(organisation_ref, code))
            continue

        gaps.extend(prepared.gaps)
        validation = validate_enterprise_identity_access(prepared.imported)
        if not validation.valid:
            code = AdapterCode.ENTERPRISE_VALIDATION_FAILED
            gaps.append(AdapterGap(code=code, organisation_ref=organisation_ref))
            outcomes.append(
                _failed_outcome(
                    organisation_ref,
                    code,
                    raw_population=prepared.raw_population,
                    emitted_population=prepared.emitted_population,
                    downscale=prepared.downscale,
                )
            )
            continue

        try:
            compiled = compile_enterprise_identity_access_universe(
                import_model=prepared.imported,
                seed=config.seed,
                config=EnterpriseIdentityAccessCompileConfigV1(
                    budget=EnterpriseIdentityAccessCompileBudgetV1(
                        max_principals=config.max_principals_per_organisation
                    )
                ),
            )
        except (EnterpriseCompileError, ValidationError):
            code = AdapterCode.ENTERPRISE_COMPILE_FAILED
            gaps.append(AdapterGap(code=code, organisation_ref=organisation_ref))
            outcomes.append(
                _failed_outcome(
                    organisation_ref,
                    code,
                    raw_population=prepared.raw_population,
                    emitted_population=prepared.emitted_population,
                    downscale=prepared.downscale,
                    compile_failed=True,
                )
            )
            continue

        artifacts = _write_organisation_artifacts(
            output_dir=output_dir,
            organisation_ref=organisation_ref,
            imported=prepared.imported,
            compiled=compiled,
        )
        outcomes.append(
            OrganisationOutcome(
                organisation_ref=organisation_ref,
                status=OrganisationStatus.COMPILED,
                compile_status=CompileStatus.SUCCEEDED,
                artifacts=artifacts,
                raw_population=prepared.raw_population,
                emitted_population=prepared.emitted_population,
                downscale=prepared.downscale,
            )
        )

    compiled_any = any(item.status is OrganisationStatus.COMPILED for item in outcomes)
    has_failures = any(item.status is OrganisationStatus.FAILED for item in outcomes)
    failed = has_failures or not compiled_any
    report = _build_report(
        config=config,
        source_vintage=vintage,
        source_digest=source_digest,
        status=RunStatus.FAILED if failed else RunStatus.SUCCEEDED,
        error_code=(
            AdapterCode.ORGANISATION_FAILURES_PRESENT
            if has_failures
            else AdapterCode.NO_ORGANISATIONS_COMPILED
            if not compiled_any
            else None
        ),
        gaps=tuple(gaps),
        outcomes=tuple(outcomes),
    )
    _write_report(output_dir, report)
    return report


def _prepare_organisation(
    organisation: CanonicalOrganisation,
    organisation_ref: str,
    config: AdapterConfig,
) -> _PreparedOrganisation:
    gaps: list[AdapterGap] = []

    def opaque(kind: str, *parts: str) -> str:
        return _opaque(config.namespace_salt, kind, *parts)

    scale = _token(organisation.scale)
    if scale not in _SCALE_BASE:
        raise _AdapterError(AdapterCode.UNKNOWN_SCALE)

    domains = _flatten_domains(organisation.domains)
    _require_unique(
        (item.domain.domain_id for item in domains),
        AdapterCode.DUPLICATE_DOMAIN_ID,
    )
    _require_unique(
        (item.region_id for item in organisation.regions),
        AdapterCode.DUPLICATE_REGION_ID,
    )
    _require_unique(
        (item.team_id for item in organisation.teams),
        AdapterCode.DUPLICATE_TEAM_ID,
    )
    _require_unique(
        (item.service_id for item in organisation.services),
        AdapterCode.DUPLICATE_SERVICE_ID,
    )
    _require_unique(
        (
            f"{item.team_id}\x00{item.service_id}\x00{_token(item.relationship)}"
            for item in organisation.ownerships
        ),
        AdapterCode.DUPLICATE_NORMALIZED_OWNERSHIP,
    )

    domain_ids = {item.domain.domain_id for item in domains}
    region_ids = {item.region_id for item in organisation.regions}
    teams_by_id = {item.team_id: item for item in organisation.teams}
    services_by_id = {item.service_id: item for item in organisation.services}
    for team in organisation.teams:
        if team.domain_id not in domain_ids:
            raise _AdapterError(AdapterCode.DANGLING_DOMAIN_REFERENCE)
        if any(region_id not in region_ids for region_id in team.region_ids):
            raise _AdapterError(AdapterCode.DANGLING_REGION_REFERENCE)
    for service in organisation.services:
        if service.owning_team_id not in teams_by_id:
            raise _AdapterError(AdapterCode.DANGLING_TEAM_REFERENCE)
    for ownership in organisation.ownerships:
        if ownership.team_id not in teams_by_id:
            raise _AdapterError(AdapterCode.DANGLING_TEAM_REFERENCE)
        if ownership.service_id not in services_by_id:
            raise _AdapterError(AdapterCode.DANGLING_SERVICE_REFERENCE)

    for service in organisation.services:
        gaps.append(
            AdapterGap(
                code=(
                    AdapterCode.NULL_CLASSIFICATION
                    if service.classification is None
                    else AdapterCode.UNEXPRESSED_SERVICE_CLASSIFICATION
                ),
                organisation_ref=organisation_ref,
                subject_ref=opaque(
                    "service",
                    organisation.organisation_id,
                    service.service_id,
                ),
            )
        )
    for ownership in organisation.ownerships:
        relationship = _token(ownership.relationship)
        ownership_ref = opaque(
            "ownership",
            organisation.organisation_id,
            ownership.team_id,
            ownership.service_id,
            relationship,
        )
        if relationship not in _OWNERSHIP_ACTION:
            gaps.append(
                AdapterGap(
                    code=AdapterCode.UNSUPPORTED_OWNERSHIP_SEMANTICS,
                    organisation_ref=organisation_ref,
                    subject_ref=ownership_ref,
                )
            )
        elif (
            relationship == "owner"
            and services_by_id[ownership.service_id].owning_team_id != ownership.team_id
        ):
            gaps.append(
                AdapterGap(
                    code=AdapterCode.DECLARED_OWNER_DIVERGES,
                    organisation_ref=organisation_ref,
                    subject_ref=ownership_ref,
                )
            )

    if organisation.regions or any(team.region_ids for team in organisation.teams):
        gaps.append(
            AdapterGap(
                code=AdapterCode.UNEXPRESSED_REGION_METADATA,
                organisation_ref=organisation_ref,
            )
        )

    tenant_key = opaque("tenant", organisation.organisation_id)
    organisation_key = organisation_ref
    domain_unit_keys = {
        item.domain.domain_id: opaque(
            "domain-unit", organisation.organisation_id, item.domain.domain_id
        )
        for item in domains
    }
    units: list[UnitTemplateV1] = []
    for item in sorted(
        domains,
        key=lambda entry: domain_unit_keys[entry.domain.domain_id],
    ):
        if item.depth > 1:
            gaps.append(
                AdapterGap(
                    code=AdapterCode.DEEP_HIERARCHY_COLLAPSED,
                    organisation_ref=organisation_ref,
                    subject_ref=opaque(
                        "domain", organisation.organisation_id, item.domain.domain_id
                    ),
                )
            )
        units.append(
            UnitTemplateV1(
                key=domain_unit_keys[item.domain.domain_id],
                tenant_key=tenant_key,
                organisation_key=organisation_key,
                unit_kind=UnitKind.DIVISION if item.depth == 0 else UnitKind.DEPARTMENT,
                parent_unit_key=(
                    domain_unit_keys[item.parent_id]
                    if item.parent_id is not None
                    else None
                ),
            )
        )

    sorted_teams = sorted(
        organisation.teams,
        key=lambda item: opaque("team", organisation.organisation_id, item.team_id),
    )
    team_unit_keys: dict[str, str] = {}
    population_keys: dict[str, str] = {}
    group_keys: dict[str, str] = {}
    role_keys: dict[str, str] = {}
    raw_counts: dict[str, int] = {}
    industry = _token(organisation.industry)
    industry_factor = _INDUSTRY_FACTORS.get(industry)
    if industry_factor is None:
        industry_factor = _GENERAL_FACTOR
        gaps.append(
            AdapterGap(
                code=AdapterCode.UNKNOWN_INDUSTRY,
                organisation_ref=organisation_ref,
            )
        )

    for team in sorted_teams:
        team_ref = opaque("team", organisation.organisation_id, team.team_id)
        team_unit_keys[team.team_id] = opaque(
            "team-unit", organisation.organisation_id, team.team_id
        )
        population_keys[team.team_id] = opaque(
            "population", organisation.organisation_id, team.team_id
        )
        group_keys[team.team_id] = opaque(
            "group", organisation.organisation_id, team.team_id
        )
        role_keys[team.team_id] = opaque(
            "role", organisation.organisation_id, team.team_id
        )
        team_type = _TEAM_ALIASES.get(_token(team.team_type), _token(team.team_type))
        team_factor = _TEAM_FACTORS.get(team_type)
        if team_factor is None:
            team_factor = _GENERAL_FACTOR
            gaps.append(
                AdapterGap(
                    code=AdapterCode.UNKNOWN_TEAM_TYPE,
                    organisation_ref=organisation_ref,
                    subject_ref=team_ref,
                )
            )
        raw_counts[team.team_id] = _population_count(
            scale_base=_SCALE_BASE[scale],
            team_factor=team_factor,
            industry_factor=industry_factor,
        )
        if team.ignored_source_measurements:
            gaps.append(
                AdapterGap(
                    code=AdapterCode.IGNORED_SOURCE_POPULATION_FIELD,
                    organisation_ref=organisation_ref,
                    subject_ref=team_ref,
                )
            )

    try:
        emitted_counts, downscale = _downscale_counts(
            raw_counts,
            config.max_principals_per_organisation,
            order_keys={
                team.team_id: opaque(
                    "team",
                    organisation.organisation_id,
                    team.team_id,
                )
                for team in sorted_teams
            },
        )
    except _AdapterError as error:
        raise _AdapterError(error.code, gaps) from error
    for team in sorted_teams:
        units.append(
            UnitTemplateV1(
                key=team_unit_keys[team.team_id],
                tenant_key=tenant_key,
                organisation_key=organisation_key,
                unit_kind=UnitKind.TEAM,
                parent_unit_key=domain_unit_keys[team.domain_id],
            )
        )

    populations = tuple(
        PopulationTemplateV1(
            key=population_keys[team.team_id],
            tenant_key=tenant_key,
            organisation_key=organisation_key,
            unit_key=team_unit_keys[team.team_id],
            population_kind=PrincipalKind.EMPLOYEE,
            count=emitted_counts[team.team_id],
        )
        for team in sorted_teams
    )
    groups = tuple(
        GroupTemplateV1(
            key=group_keys[team.team_id],
            tenant_key=tenant_key,
            organisation_key=organisation_key,
            owner_unit_key=team_unit_keys[team.team_id],
        )
        for team in sorted_teams
    )
    roles = tuple(
        RoleTemplateV1(
            key=role_keys[team.team_id],
            tenant_key=tenant_key,
            organisation_key=organisation_key,
            owner_unit_key=team_unit_keys[team.team_id],
        )
        for team in sorted_teams
    )

    resource_keys: dict[str, str] = {}
    resources: list[ResourceSetTemplateV1] = []
    for service in sorted(
        organisation.services,
        key=lambda item: opaque(
            "service", organisation.organisation_id, item.service_id
        ),
    ):
        target_kind = _service_target_kind(service.service_type)
        if target_kind is None:
            raise _AdapterError(AdapterCode.UNMAPPED_SERVICE_TYPE, gaps)
        resource_key = opaque(
            "resource-set", organisation.organisation_id, service.service_id
        )
        resource_keys[service.service_id] = resource_key
        resources.append(
            ResourceSetTemplateV1(
                key=resource_key,
                tenant_key=tenant_key,
                organisation_key=organisation_key,
                target_kind=target_kind,
                owner_unit_key=team_unit_keys[service.owning_team_id],
                instance_count=1,
                actions=_ACTIONS[target_kind],
            )
        )

    grants: list[RoleGrantV1] = []
    atom_rules: list[PrincipalSubjectAccessAtomRuleV1] = []
    for ownership in sorted(
        organisation.ownerships,
        key=lambda item: (
            opaque("team", organisation.organisation_id, item.team_id),
            opaque("service", organisation.organisation_id, item.service_id),
            _token(item.relationship),
        ),
    ):
        relationship = _token(ownership.relationship)
        action = _OWNERSHIP_ACTION.get(relationship)
        if action is None:
            continue
        gaps.append(
            AdapterGap(
                code=AdapterCode.OWNERSHIP_WIDENED_TO_TEAM_POPULATION,
                organisation_ref=organisation_ref,
                subject_ref=opaque(
                    "ownership",
                    organisation.organisation_id,
                    ownership.team_id,
                    ownership.service_id,
                    relationship,
                ),
            )
        )
        grants.append(
            RoleGrantV1(
                role_key=role_keys[ownership.team_id],
                resource_set_key=resource_keys[ownership.service_id],
                action=action,
            )
        )
        atom_rules.append(
            PrincipalSubjectAccessAtomRuleV1(
                rule_key=opaque(
                    "access-atom-rule",
                    organisation.organisation_id,
                    ownership.team_id,
                    ownership.service_id,
                    action,
                ),
                population_key=population_keys[ownership.team_id],
                resource_set_key=resource_keys[ownership.service_id],
                action=action,
                selector=AllSelectorV1(),
            )
        )

    if not atom_rules:
        raise _AdapterError(AdapterCode.NO_SUPPORTED_ACCESS_MAPPING, gaps)

    blueprint = EnterpriseIdentityAccessBlueprintV1(
        blueprint_key=opaque("blueprint", organisation.organisation_id),
        id_namespace_salt=_namespace_salt(
            config.namespace_salt,
            config.seed,
            organisation_ref,
        ),
        tenants=(TenantTemplateV1(key=tenant_key),),
        organisations=(
            OrganisationTemplateV1(key=organisation_key, tenant_key=tenant_key),
        ),
        units=tuple(units),
        populations=populations,
        groups=groups,
        roles=roles,
        resource_sets=tuple(resources),
        principal_access_atom_rules=tuple(atom_rules),
    )
    directory = EnterpriseDirectoryRbacStateInputV1(
        memberships=tuple(
            PopulationGroupMembershipRuleV1(
                rule_key=opaque(
                    "membership", organisation.organisation_id, team.team_id
                ),
                population_key=population_keys[team.team_id],
                group_key=group_keys[team.team_id],
                selector=AllSelectorV1(),
            )
            for team in sorted_teams
        ),
        group_role_assignments=tuple(
            GroupRoleAssignmentV1(
                group_key=group_keys[team.team_id],
                role_key=role_keys[team.team_id],
            )
            for team in sorted_teams
        ),
        role_grants=tuple(grants),
    )
    imported = EnterpriseIdentityAccessImportV1(
        blueprint=blueprint,
        iam_universe_extension=EnterpriseIamUniverseExtensionV1(),
        directory_rbac_state=directory,
    )
    return _PreparedOrganisation(
        imported=imported,
        gaps=tuple(gaps),
        raw_population=sum(raw_counts.values()),
        emitted_population=sum(emitted_counts.values()),
        downscale=downscale,
    )


def _flatten_domains(domains: Sequence[CanonicalDomain]) -> tuple[_DomainEntry, ...]:
    entries: list[_DomainEntry] = []

    def visit(domain: CanonicalDomain, parent_id: str | None, depth: int) -> None:
        entries.append(_DomainEntry(domain=domain, parent_id=parent_id, depth=depth))
        for child in sorted(domain.children, key=lambda item: item.domain_id):
            visit(child, domain.domain_id, depth + 1)

    for root in sorted(domains, key=lambda item: item.domain_id):
        visit(root, None, 0)
    return tuple(entries)


def _population_count(
    *,
    scale_base: int,
    team_factor: tuple[int, int],
    industry_factor: tuple[int, int],
) -> int:
    numerator = scale_base * team_factor[0] * industry_factor[0]
    denominator = team_factor[1] * industry_factor[1]
    return max(1, (numerator + denominator // 2) // denominator)


def _downscale_counts(
    raw_counts: Mapping[str, int],
    cap: int,
    *,
    order_keys: Mapping[str, str],
) -> tuple[dict[str, int], DownscaleDeclaration]:
    ordered = sorted(raw_counts, key=order_keys.__getitem__)
    raw_total = sum(raw_counts.values())
    if raw_total <= cap:
        return dict(raw_counts), DownscaleDeclaration(
            applied=False,
            raw_total=raw_total,
            emitted_total=raw_total,
            numerator=1,
            denominator=1,
        )
    if cap < len(ordered):
        raise _AdapterError(AdapterCode.POPULATION_CAP_BELOW_TEAM_COUNT)

    remaining = cap - len(ordered)
    weights = {key: raw_counts[key] - 1 for key in ordered}
    weight_total = sum(weights.values())
    extras = {key: (remaining * weights[key]) // weight_total for key in ordered}
    leftovers = remaining - sum(extras.values())
    remainder_order = sorted(
        ordered,
        key=lambda key: (
            -(remaining * weights[key] % weight_total),
            order_keys[key],
        ),
    )
    for key in remainder_order[:leftovers]:
        extras[key] += 1
    emitted = {key: 1 + extras[key] for key in ordered}
    divisor = math.gcd(cap, raw_total)
    return emitted, DownscaleDeclaration(
        applied=True,
        raw_total=raw_total,
        emitted_total=cap,
        numerator=cap // divisor,
        denominator=raw_total // divisor,
    )


def _service_target_kind(value: str) -> TargetKind | None:
    token = _token(value)
    canonical = _SERVICE_ALIASES.get(token, token)
    return _SERVICE_TYPES.get(canonical)


def _token(value: str) -> str:
    if not value.isascii():
        raise ValueError("semantic_text_ascii_required")
    return _TOKEN_SEPARATOR.sub("_", value.lower()).strip("_")


def _opaque(namespace_salt: str, kind: str, *source_ids: str) -> str:
    digest = hmac.new(bytes.fromhex(namespace_salt), digestmod=hashlib.sha256)
    for part in (kind, *source_ids):
        encoded = part.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return f"{kind}-{digest.hexdigest()}"


def _namespace_salt(
    namespace_salt: str,
    seed: int,
    organisation_ref: str,
) -> str:
    return hmac.new(
        bytes.fromhex(namespace_salt),
        (f"{_IDENTIFIER_DERIVATION_VERSION}\x00{seed}\x00{organisation_ref}").encode(),
        hashlib.sha256,
    ).hexdigest()


def _require_unique(values: Iterable[str], code: AdapterCode) -> None:
    materialized = tuple(values)
    if len(materialized) != len(set(materialized)):
        raise _AdapterError(code)


def _failed_outcome(
    organisation_ref: str,
    code: AdapterCode,
    *,
    raw_population: int = 0,
    emitted_population: int = 0,
    downscale: DownscaleDeclaration | None = None,
    compile_failed: bool = False,
) -> OrganisationOutcome:
    return OrganisationOutcome(
        organisation_ref=organisation_ref,
        status=OrganisationStatus.FAILED,
        compile_status=(
            CompileStatus.FAILED if compile_failed else CompileStatus.NOT_RUN
        ),
        error_code=code,
        raw_population=raw_population,
        emitted_population=emitted_population,
        downscale=downscale,
    )


def _artifact_specs(
    organisation_ref: str,
) -> tuple[tuple[str, ArtifactVisibility, ArtifactKind], ...]:
    root = f"artifacts/{organisation_ref}"
    return (
        (
            f"private/imports/{organisation_ref}/enterprise-import.json",
            ArtifactVisibility.PRIVATE,
            ArtifactKind.PRIVATE_IMPORT,
        ),
        (
            f"{root}/{PUBLIC_UNIVERSE_PATH}",
            ArtifactVisibility.PUBLIC,
            ArtifactKind.PUBLIC_INPUT,
        ),
        (
            f"{root}/{PUBLIC_MANIFEST_PATH}",
            ArtifactVisibility.PUBLIC,
            ArtifactKind.PUBLIC_MANIFEST,
        ),
        (
            f"{root}/{EVALUATOR_BINDING_PATH}",
            ArtifactVisibility.EVALUATOR,
            ArtifactKind.EVALUATOR_TRUTH,
        ),
        (
            f"{root}/{EVALUATOR_MANIFEST_PATH}",
            ArtifactVisibility.EVALUATOR,
            ArtifactKind.EVALUATOR_MANIFEST,
        ),
    )


def _write_organisation_artifacts(
    *,
    output_dir: Path,
    organisation_ref: str,
    imported: EnterpriseIdentityAccessImportV1,
    compiled: EnterpriseIdentityAccessCompileResultV1,
) -> tuple[ArtifactRecord, ...]:
    _write_new(
        output_dir
        / "private"
        / "imports"
        / organisation_ref
        / "enterprise-import.json",
        canonical_json_bytes(imported),
    )
    export_enterprise_identity_access_compile_result(
        output_dir / "artifacts" / organisation_ref,
        compiled,
    )
    records = []
    for relative_path, visibility, kind in _artifact_specs(organisation_ref):
        payload = (output_dir / relative_path).read_bytes()
        records.append(
            ArtifactRecord(
                path=relative_path,
                visibility=visibility,
                kind=kind,
                byte_size=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(),
            )
        )
    return tuple(sorted(records, key=lambda item: item.path))


def _build_report(
    *,
    config: AdapterConfig,
    source_vintage: SourceVintage,
    source_digest: str,
    status: RunStatus,
    error_code: AdapterCode | None,
    gaps: tuple[AdapterGap, ...] = (),
    outcomes: tuple[OrganisationOutcome, ...] = (),
) -> AdapterRunReport:
    canonical_gaps = tuple(
        sorted(
            gaps,
            key=lambda item: (
                item.organisation_ref,
                item.code.value,
                item.subject_ref or "",
            ),
        )
    )
    canonical_outcomes = tuple(sorted(outcomes, key=lambda item: item.organisation_ref))
    all_artifacts = tuple(
        sorted(
            (
                artifact
                for outcome in canonical_outcomes
                for artifact in outcome.artifacts
            ),
            key=lambda item: item.path,
        )
    )
    private_artifacts = tuple(
        item for item in all_artifacts if item.visibility is ArtifactVisibility.PRIVATE
    )
    public_artifacts = tuple(
        item for item in all_artifacts if item.visibility is ArtifactVisibility.PUBLIC
    )
    evaluator_artifacts = tuple(
        item
        for item in all_artifacts
        if item.visibility is ArtifactVisibility.EVALUATOR
    )
    salt_fingerprint = hashlib.sha256(bytes.fromhex(config.namespace_salt)).hexdigest()
    config_digest = _adapter_config_digest_values(
        seed=config.seed,
        max_principals_per_organisation=config.max_principals_per_organisation,
        namespace_salt_fingerprint=salt_fingerprint,
    )
    return AdapterRunReport(
        source_vintage=source_vintage,
        canonical_source_payload_digest=source_digest,
        seed=config.seed,
        max_principals_per_organisation=config.max_principals_per_organisation,
        namespace_salt_fingerprint=salt_fingerprint,
        adapter_config_digest=config_digest,
        status=status,
        error_code=error_code,
        gaps=canonical_gaps,
        outcomes=canonical_outcomes,
        private_artifacts=private_artifacts,
        public_artifacts=public_artifacts,
        evaluator_artifacts=evaluator_artifacts,
        artifact_set_digest=_artifact_set_digest(all_artifacts),
    )


def _adapter_config_digest_values(
    *,
    seed: int,
    max_principals_per_organisation: int,
    namespace_salt_fingerprint: str,
) -> str:
    payload = {
        "adapter_version": ADAPTER_VERSION,
        "max_principals_per_organisation": max_principals_per_organisation,
        "namespace_salt_fingerprint": namespace_salt_fingerprint,
        "seed": seed,
    }
    return hashlib.sha256(canonical_json_value_bytes(payload)).hexdigest()


def _artifact_set_digest(artifacts: Sequence[ArtifactRecord]) -> str:
    records = [
        {
            "byte_size": item.byte_size,
            "kind": item.kind.value,
            "path": item.path,
            "sha256": item.sha256,
            "visibility": item.visibility.value,
        }
        for item in sorted(artifacts, key=lambda item: item.path)
    ]
    return hashlib.sha256(canonical_json_value_bytes(records)).hexdigest()


def _write_report(output_dir: Path, report: AdapterRunReport) -> None:
    _write_new(output_dir / REPORT_PATH, canonical_json_bytes(report))


def _write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as destination:
        destination.write(payload)


def _prepare_output_parent(output_root: Path) -> None:
    _require_path_safety_primitives()
    try:
        output_root.lstat()
    except FileNotFoundError:
        pass
    else:
        raise AdapterPathError(AdapterCode.OUTPUT_ROOT_EXISTS)
    _reject_symlinked_components(output_root.parent)
    output_root.parent.mkdir(parents=True, exist_ok=True)
    _reject_symlinked_components(output_root.parent)


def _promote_staged_output(staged_output: Path, output_root: Path) -> None:
    _reject_symlinked_components(output_root.parent)
    try:
        output_root.lstat()
    except FileNotFoundError:
        pass
    else:
        raise AdapterPathError(AdapterCode.OUTPUT_ROOT_EXISTS)
    staged_output.rename(output_root)


def _require_path_safety_primitives() -> None:
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_NONBLOCK"):
        raise AdapterPathError(AdapterCode.PATH_SAFETY_UNAVAILABLE)


def _reject_symlinked_components(path: Path) -> None:
    absolute = Path(os.path.abspath(path))
    chain = tuple(reversed((absolute, *absolute.parents)))
    for component in chain:
        try:
            metadata = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode):
            raise AdapterPathError(AdapterCode.OUTPUT_PARENT_SYMLINK)
        if not stat.S_ISDIR(metadata.st_mode):
            raise AdapterPathError(AdapterCode.OUTPUT_PARENT_NOT_DIRECTORY)


__all__ = [
    "ADAPTER_VERSION",
    "AdapterCode",
    "AdapterConfig",
    "AdapterGap",
    "AdapterPathError",
    "AdapterRunReport",
    "ArtifactKind",
    "ArtifactRecord",
    "ArtifactVisibility",
    "DownscaleDeclaration",
    "OrganisationOutcome",
    "SourcePayloadError",
    "run_adapter",
]
