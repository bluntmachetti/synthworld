"""Deterministic Phase 1 EADS-to-enterprise adapter."""

from __future__ import annotations

import hashlib
import hmac
import math
import re
import tempfile
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from examples.eads_adapter.models import (
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

ADAPTER_VERSION: Literal["eads-phase-1-v1"] = "eads-phase-1-v1"
MAPPING_VERSION: Literal["eads-enterprise-mapping-v1"] = "eads-enterprise-mapping-v1"
POPULATION_POLICY_VERSION: Literal["eads-human-population-policy-v1"] = (
    "eads-human-population-policy-v1"
)
REPORT_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
_INVALID_SOURCE_DIGEST = hashlib.sha256(b"invalid-json-native-payload").hexdigest()

_TOKEN_SEPARATOR = re.compile(r"[^a-z0-9]+")
_BIAN_MARKER = re.compile(
    r"(?<![a-z0-9])bian(?![a-z0-9])|banking industry architecture network",
    re.I,
)

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


class _StrictFrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class AdapterConfig(_StrictFrozenModel):
    """Explicit deterministic adapter controls."""

    seed: int
    namespace_salt: str = Field(pattern=r"^[0-9a-f]{64}$")
    max_principals_per_organisation: int = Field(
        default=10_000,
        gt=0,
        le=1_000_000,
    )


class AdapterGap(_StrictFrozenModel):
    code: str = Field(min_length=1)
    organisation_ref: str = Field(min_length=1)
    subject_ref: str | None = Field(default=None, min_length=1)


class DownscaleDeclaration(_StrictFrozenModel):
    applied: bool
    raw_total: int = Field(ge=0)
    emitted_total: int = Field(ge=0)
    numerator: int = Field(gt=0)
    denominator: int = Field(gt=0)


class OrganisationOutcome(_StrictFrozenModel):
    organisation_ref: str = Field(min_length=1)
    status: Literal["compiled", "excluded", "failed"]
    compile_status: Literal["succeeded", "not_run", "failed"]
    error_code: str | None = Field(default=None, min_length=1)
    artifacts: tuple[str, ...] = ()
    raw_population: int = Field(ge=0)
    emitted_population: int = Field(ge=0)
    downscale: DownscaleDeclaration | None = None

    @field_validator("artifacts")
    @classmethod
    def canonical_artifacts(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        ordered = tuple(sorted(value))
        if len(ordered) != len(set(ordered)):
            raise ValueError("duplicate_adapter_artifact")
        return ordered


class AdapterRunReport(_StrictFrozenModel):
    """Sanitized deterministic report for one adapter invocation."""

    schema_version: Literal["1.0.0"] = REPORT_SCHEMA_VERSION
    adapter_version: Literal["eads-phase-1-v1"] = ADAPTER_VERSION
    source_vintage: SourceVintage
    canonical_source_payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    mapping_version: Literal["eads-enterprise-mapping-v1"] = MAPPING_VERSION
    population_policy_version: Literal["eads-human-population-policy-v1"] = (
        POPULATION_POLICY_VERSION
    )
    status: Literal["succeeded", "failed"]
    error_code: str | None = Field(default=None, min_length=1)
    gaps: tuple[AdapterGap, ...] = ()
    outcomes: tuple[OrganisationOutcome, ...] = ()

    @field_validator("gaps")
    @classmethod
    def canonical_gaps(cls, value: tuple[AdapterGap, ...]) -> tuple[AdapterGap, ...]:
        return tuple(
            sorted(
                value,
                key=lambda item: (
                    item.organisation_ref,
                    item.code,
                    item.subject_ref or "",
                ),
            )
        )

    @field_validator("outcomes")
    @classmethod
    def canonical_outcomes(
        cls, value: tuple[OrganisationOutcome, ...]
    ) -> tuple[OrganisationOutcome, ...]:
        return tuple(sorted(value, key=lambda item: item.organisation_ref))


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


class _AdapterError(Exception):
    def __init__(self, code: str, gaps: Sequence[AdapterGap] = ()) -> None:
        super().__init__(code)
        self.code = code
        self.gaps = tuple(gaps)


def run_adapter(
    *,
    payload: Mapping[str, object],
    vintage: SourceVintage | str,
    output_dir: Path,
    config: AdapterConfig,
) -> AdapterRunReport:
    """Adapt, validate, compile, and serialize each source organisation."""

    output_root_is_empty = False
    if output_dir.exists():
        if not output_dir.is_dir() or any(output_dir.iterdir()):
            raise FileExistsError(
                "eads adapter output root must be absent or an empty directory"
            )
        output_root_is_empty = True
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        dir=output_dir.parent,
        prefix=f".{output_dir.name}.eads-adapter-",
    ) as temporary:
        staged_output = Path(temporary) / "result"
        report = _run_adapter(
            payload=payload,
            vintage=vintage,
            output_dir=staged_output,
            config=config,
        )
        if output_root_is_empty:
            output_dir.rmdir()
        staged_output.rename(output_dir)
    return report


def _run_adapter(
    *,
    payload: Mapping[str, object],
    vintage: SourceVintage | str,
    output_dir: Path,
    config: AdapterConfig,
) -> AdapterRunReport:
    """Build one complete adapter run in an unpublished staging directory."""

    selected_vintage = SourceVintage(vintage)
    try:
        source_bytes = canonical_json_value_bytes(dict(payload))
        source_digest = hashlib.sha256(source_bytes).hexdigest()
    except (TypeError, ValueError):
        report = AdapterRunReport(
            source_vintage=selected_vintage,
            canonical_source_payload_digest=_INVALID_SOURCE_DIGEST,
            status="failed",
            error_code="source_payload_not_json_compatible",
        )
        _write_report(output_dir, report)
        return report
    try:
        source = parse_source(payload, selected_vintage)
    except (TypeError, ValueError, ValidationError):
        report = AdapterRunReport(
            source_vintage=selected_vintage,
            canonical_source_payload_digest=source_digest,
            status="failed",
            error_code="source_validation_failed",
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
                code="duplicate_organisation_id",
                organisation_ref=organisation_ref,
            )
        )
        outcomes.append(_failed_outcome(organisation_ref, "duplicate_organisation_id"))

    for organisation in organisations:
        organisation_ref = opaque("organisation", organisation.organisation_id)
        if _is_bian_like(organisation):
            gaps.append(
                AdapterGap(
                    code="bian_framework_excluded",
                    organisation_ref=organisation_ref,
                )
            )
            outcomes.append(
                OrganisationOutcome(
                    organisation_ref=organisation_ref,
                    status="excluded",
                    compile_status="not_run",
                    error_code="bian_framework_excluded",
                    raw_population=0,
                    emitted_population=0,
                )
            )
            continue

        try:
            prepared = _prepare_organisation(organisation, organisation_ref, config)
        except _AdapterError as error:
            gaps.extend(error.gaps)
            gaps.append(AdapterGap(code=error.code, organisation_ref=organisation_ref))
            outcomes.append(_failed_outcome(organisation_ref, error.code))
            continue
        except (TypeError, ValueError, ValidationError):
            gaps.append(
                AdapterGap(
                    code="adapter_model_validation_failed",
                    organisation_ref=organisation_ref,
                )
            )
            outcomes.append(
                _failed_outcome(organisation_ref, "adapter_model_validation_failed")
            )
            continue

        gaps.extend(prepared.gaps)
        validation = validate_enterprise_identity_access(prepared.imported)
        if not validation.valid:
            gaps.append(
                AdapterGap(
                    code="enterprise_validation_failed",
                    organisation_ref=organisation_ref,
                )
            )
            outcomes.append(
                _failed_outcome(
                    organisation_ref,
                    "enterprise_validation_failed",
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
            gaps.append(
                AdapterGap(
                    code="enterprise_compile_failed",
                    organisation_ref=organisation_ref,
                )
            )
            outcomes.append(
                _failed_outcome(
                    organisation_ref,
                    "enterprise_compile_failed",
                    raw_population=prepared.raw_population,
                    emitted_population=prepared.emitted_population,
                    downscale=prepared.downscale,
                    compile_failed=True,
                )
            )
            continue

        artifact_names = _artifact_names(organisation_ref)
        _write_organisation_artifacts(
            output_dir=output_dir,
            organisation_ref=organisation_ref,
            imported=prepared.imported,
            compiled=compiled,
        )

        outcomes.append(
            OrganisationOutcome(
                organisation_ref=organisation_ref,
                status="compiled",
                compile_status="succeeded",
                artifacts=artifact_names,
                raw_population=prepared.raw_population,
                emitted_population=prepared.emitted_population,
                downscale=prepared.downscale,
            )
        )

    compiled_any = any(item.status == "compiled" for item in outcomes)
    has_failures = any(item.status == "failed" for item in outcomes)
    failed = has_failures or not compiled_any
    report = AdapterRunReport(
        source_vintage=selected_vintage,
        canonical_source_payload_digest=source_digest,
        status="failed" if failed else "succeeded",
        error_code=(
            "organisation_failures_present"
            if has_failures
            else "no_organisations_compiled"
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
        raise _AdapterError("unknown_scale")

    domains = _flatten_domains(organisation.domains)
    _require_unique((item.domain.domain_id for item in domains), "duplicate_domain_id")
    _require_unique(
        (item.region_id for item in organisation.regions), "duplicate_region_id"
    )
    _require_unique((item.team_id for item in organisation.teams), "duplicate_team_id")
    _require_unique(
        (item.service_id for item in organisation.services), "duplicate_service_id"
    )
    _require_unique(
        (
            f"{item.team_id}\x00{item.service_id}\x00{_token(item.relationship)}"
            for item in organisation.ownerships
        ),
        "duplicate_normalized_ownership",
    )

    domain_ids = {item.domain.domain_id for item in domains}
    region_ids = {item.region_id for item in organisation.regions}
    teams_by_id = {item.team_id: item for item in organisation.teams}
    services_by_id = {item.service_id: item for item in organisation.services}
    for team in organisation.teams:
        if team.domain_id not in domain_ids:
            raise _AdapterError("dangling_domain_reference")
        if any(region_id not in region_ids for region_id in team.region_ids):
            raise _AdapterError("dangling_region_reference")
    for service in organisation.services:
        if service.owning_team_id not in teams_by_id:
            raise _AdapterError("dangling_team_reference")
    for ownership in organisation.ownerships:
        if ownership.team_id not in teams_by_id:
            raise _AdapterError("dangling_team_reference")
        if ownership.service_id not in services_by_id:
            raise _AdapterError("dangling_service_reference")

    for service in organisation.services:
        gaps.append(
            AdapterGap(
                code=(
                    "null_classification"
                    if service.classification is None
                    else "unexpressed_service_classification"
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
                    code="unsupported_ownership_semantics",
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
                    code="declared_owner_diverges_from_owning_team",
                    organisation_ref=organisation_ref,
                    subject_ref=ownership_ref,
                )
            )

    if organisation.regions or any(team.region_ids for team in organisation.teams):
        gaps.append(
            AdapterGap(
                code="unexpressed_region_metadata",
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
                    code="deep_hierarchy_collapsed",
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
                code="unknown_industry",
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
                    code="unknown_team_type",
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
                    code="ignored_source_population_field",
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
            raise _AdapterError("unmapped_service_type", gaps)
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
                code="ownership_widened_to_team_population",
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
        raise _AdapterError("no_supported_access_mapping", gaps)

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
        raise _AdapterError("population_cap_below_team_count")

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
    return _TOKEN_SEPARATOR.sub("_", value.casefold()).strip("_")


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
        f"{ADAPTER_VERSION}\x00{seed}\x00{organisation_ref}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _is_bian_like(organisation: CanonicalOrganisation) -> bool:
    candidates = [
        organisation.organisation_id,
        organisation.name,
        organisation.industry,
    ]
    candidates.extend(region.region_id for region in organisation.regions)
    candidates.extend(region.name for region in organisation.regions)
    for entry in _flatten_domains(organisation.domains):
        candidates.extend((entry.domain.domain_id, entry.domain.name))
    for team in organisation.teams:
        candidates.extend((team.team_id, team.name, team.team_type))
    for service in organisation.services:
        candidates.extend(
            (
                service.service_id,
                service.name,
                service.service_type,
                service.classification or "",
            )
        )
    candidates.extend(item.relationship for item in organisation.ownerships)
    return any(_BIAN_MARKER.search(value) is not None for value in candidates)


def _require_unique(values: Iterable[str], code: str) -> None:
    materialized = tuple(values)
    if len(materialized) != len(set(materialized)):
        raise _AdapterError(code)


def _failed_outcome(
    organisation_ref: str,
    code: str,
    *,
    raw_population: int = 0,
    emitted_population: int = 0,
    downscale: DownscaleDeclaration | None = None,
    compile_failed: bool = False,
) -> OrganisationOutcome:
    return OrganisationOutcome(
        organisation_ref=organisation_ref,
        status="failed",
        compile_status="failed" if compile_failed else "not_run",
        error_code=code,
        raw_population=raw_population,
        emitted_population=emitted_population,
        downscale=downscale,
    )


def _artifact_names(organisation_ref: str) -> tuple[str, ...]:
    root = f"artifacts/{organisation_ref}"
    return (
        f"private/imports/{organisation_ref}/enterprise-import.json",
        f"{root}/{PUBLIC_UNIVERSE_PATH}",
        f"{root}/{PUBLIC_MANIFEST_PATH}",
        f"{root}/{EVALUATOR_BINDING_PATH}",
        f"{root}/{EVALUATOR_MANIFEST_PATH}",
    )


def _write_organisation_artifacts(
    *,
    output_dir: Path,
    organisation_ref: str,
    imported: EnterpriseIdentityAccessImportV1,
    compiled: EnterpriseIdentityAccessCompileResultV1,
) -> None:
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


def _write_report(output_dir: Path, report: AdapterRunReport) -> None:
    _write_new(
        output_dir / "private" / "reports" / "eads-adapter-gap-report.json",
        canonical_json_bytes(report),
    )


def _write_new(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as destination:
        destination.write(payload)


__all__ = ["AdapterConfig", "AdapterRunReport", "run_adapter"]
