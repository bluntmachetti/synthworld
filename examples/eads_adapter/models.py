"""Bounded repository fixture contracts for an EADS-shaped source example.

These models describe two repository-owned fictional source vintages. They are not
official EADS schemas and do not establish compatibility with a real EADS export.
Population-like source fields are retained only as ignored measurements.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from enum import StrEnum
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

MAX_SOURCE_BYTES = 50 * 1024 * 1024
MAX_SOURCE_DEPTH = 64
MAX_SOURCE_NODES = 100_000
MAX_SOURCE_TEXT_BYTES = 1_024
MAX_ORGANISATIONS = 1_000
MAX_REGIONS_PER_ORGANISATION = 10_000
MAX_DOMAINS_PER_LEVEL = 10_000
MAX_TEAMS_PER_ORGANISATION = 25_000
MAX_SERVICES_PER_ORGANISATION = 25_000
MAX_OWNERSHIPS_PER_ORGANISATION = 100_000
MAX_REGIONS_PER_TEAM = 1_000
MAX_IGNORED_SOURCE_MEASUREMENT = 1_000_000_000


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _validated_source_text(value: str) -> str:
    if not value.strip():
        raise ValueError("source_text_blank")
    if unicodedata.normalize("NFC", value) != value:
        raise ValueError("source_text_not_nfc")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError("source_text_control_character")
    if len(value.encode("utf-8")) > MAX_SOURCE_TEXT_BYTES:
        raise ValueError("source_text_byte_limit_exceeded")
    return value


def _validated_semantic_text(value: str) -> str:
    _validated_source_text(value)
    if not value.isascii():
        raise ValueError("semantic_text_ascii_required")
    return value


SourceText = Annotated[
    str,
    Field(strict=True, min_length=1),
    AfterValidator(_validated_source_text),
]
SemanticText = Annotated[
    str,
    Field(strict=True, min_length=1),
    AfterValidator(_validated_semantic_text),
]


class SourceVintage(StrEnum):
    """Repository fixture shapes, not externally governed EADS versions."""

    SDK_SIZE_V1 = "sdk-size-v1"
    TOPOLOGY_HEADCOUNT_V1 = "topology-headcount-v1"


class CanonicalRegion(_ImmutableModel):
    region_id: SourceText
    name: SourceText


class CanonicalDomain(_ImmutableModel):
    domain_id: SourceText
    name: SourceText
    children: tuple[CanonicalDomain, ...] = Field(
        default=(),
        max_length=MAX_DOMAINS_PER_LEVEL,
    )


class CanonicalService(_ImmutableModel):
    service_id: SourceText
    name: SourceText
    service_type: SemanticText
    classification: SemanticText | None = None
    owning_team_id: SourceText


class CanonicalOwnership(_ImmutableModel):
    team_id: SourceText
    service_id: SourceText
    relationship: SemanticText


class IgnoredSourceMeasurement(_ImmutableModel):
    field: str = Field(pattern=r"^(size|headcount)$")
    value: int = Field(
        strict=True,
        ge=0,
        le=MAX_IGNORED_SOURCE_MEASUREMENT,
    )


class CanonicalTeam(_ImmutableModel):
    team_id: SourceText
    name: SourceText
    team_type: SemanticText
    domain_id: SourceText
    region_ids: tuple[SourceText, ...] = Field(
        default=(),
        max_length=MAX_REGIONS_PER_TEAM,
    )
    ignored_source_measurements: tuple[IgnoredSourceMeasurement, ...] = Field(
        min_length=1,
        max_length=1,
    )


class CanonicalOrganisation(_ImmutableModel):
    organisation_id: SourceText
    name: SourceText
    industry: SemanticText
    scale: SemanticText
    regions: tuple[CanonicalRegion, ...] = Field(
        default=(),
        max_length=MAX_REGIONS_PER_ORGANISATION,
    )
    domains: tuple[CanonicalDomain, ...] = Field(
        default=(),
        max_length=MAX_DOMAINS_PER_LEVEL,
    )
    teams: tuple[CanonicalTeam, ...] = Field(
        default=(),
        max_length=MAX_TEAMS_PER_ORGANISATION,
    )
    services: tuple[CanonicalService, ...] = Field(
        default=(),
        max_length=MAX_SERVICES_PER_ORGANISATION,
    )
    ownerships: tuple[CanonicalOwnership, ...] = Field(
        default=(),
        max_length=MAX_OWNERSHIPS_PER_ORGANISATION,
    )


class CanonicalEadsSource(_ImmutableModel):
    source_vintage: SourceVintage
    organisations: tuple[CanonicalOrganisation, ...] = Field(
        min_length=1,
        max_length=MAX_ORGANISATIONS,
    )


class _RegionInput(_ImmutableModel):
    region_id: SourceText
    name: SourceText

    def canonical(self) -> CanonicalRegion:
        return CanonicalRegion(region_id=self.region_id, name=self.name)


class _DomainInput(_ImmutableModel):
    domain_id: SourceText
    name: SourceText
    children: tuple[_DomainInput, ...] = Field(
        default=(),
        max_length=MAX_DOMAINS_PER_LEVEL,
    )

    def canonical(self) -> CanonicalDomain:
        return CanonicalDomain(
            domain_id=self.domain_id,
            name=self.name,
            children=tuple(child.canonical() for child in self.children),
        )


class _ServiceInput(_ImmutableModel):
    service_id: SourceText
    name: SourceText
    service_type: SemanticText
    classification: SemanticText | None = None
    owning_team_id: SourceText

    def canonical(self) -> CanonicalService:
        return CanonicalService(**self.model_dump())


class _OwnershipInput(_ImmutableModel):
    team_id: SourceText
    service_id: SourceText
    relationship: SemanticText

    def canonical(self) -> CanonicalOwnership:
        return CanonicalOwnership(**self.model_dump())


class _SdkTeamInput(_ImmutableModel):
    team_id: SourceText
    name: SourceText
    team_type: SemanticText
    domain_id: SourceText
    region_ids: tuple[SourceText, ...] = Field(
        default=(),
        max_length=MAX_REGIONS_PER_TEAM,
    )
    size: int = Field(
        strict=True,
        ge=0,
        le=MAX_IGNORED_SOURCE_MEASUREMENT,
    )

    def canonical(self) -> CanonicalTeam:
        return CanonicalTeam(
            team_id=self.team_id,
            name=self.name,
            team_type=self.team_type,
            domain_id=self.domain_id,
            region_ids=self.region_ids,
            ignored_source_measurements=(
                IgnoredSourceMeasurement(field="size", value=self.size),
            ),
        )


class _TopologyTeamInput(_ImmutableModel):
    team_id: SourceText
    name: SourceText
    team_type: SemanticText
    domain_id: SourceText
    region_ids: tuple[SourceText, ...] = Field(
        default=(),
        max_length=MAX_REGIONS_PER_TEAM,
    )
    headcount: int = Field(
        strict=True,
        ge=0,
        le=MAX_IGNORED_SOURCE_MEASUREMENT,
    )

    def canonical(self) -> CanonicalTeam:
        return CanonicalTeam(
            team_id=self.team_id,
            name=self.name,
            team_type=self.team_type,
            domain_id=self.domain_id,
            region_ids=self.region_ids,
            ignored_source_measurements=(
                IgnoredSourceMeasurement(field="headcount", value=self.headcount),
            ),
        )


class _OrganisationInput(_ImmutableModel):
    organisation_id: SourceText
    name: SourceText
    industry: SemanticText
    scale: SemanticText
    regions: tuple[_RegionInput, ...] = Field(
        default=(),
        max_length=MAX_REGIONS_PER_ORGANISATION,
    )
    domains: tuple[_DomainInput, ...] = Field(
        default=(),
        max_length=MAX_DOMAINS_PER_LEVEL,
    )
    services: tuple[_ServiceInput, ...] = Field(
        default=(),
        max_length=MAX_SERVICES_PER_ORGANISATION,
    )
    ownerships: tuple[_OwnershipInput, ...] = Field(
        default=(),
        max_length=MAX_OWNERSHIPS_PER_ORGANISATION,
    )


class _SdkOrganisationInput(_OrganisationInput):
    teams: tuple[_SdkTeamInput, ...] = Field(
        default=(),
        max_length=MAX_TEAMS_PER_ORGANISATION,
    )

    def canonical(self) -> CanonicalOrganisation:
        return CanonicalOrganisation(
            organisation_id=self.organisation_id,
            name=self.name,
            industry=self.industry,
            scale=self.scale,
            regions=tuple(region.canonical() for region in self.regions),
            domains=tuple(domain.canonical() for domain in self.domains),
            teams=tuple(team.canonical() for team in self.teams),
            services=tuple(service.canonical() for service in self.services),
            ownerships=tuple(item.canonical() for item in self.ownerships),
        )


class _TopologyOrganisationInput(_OrganisationInput):
    teams: tuple[_TopologyTeamInput, ...] = Field(
        default=(),
        max_length=MAX_TEAMS_PER_ORGANISATION,
    )

    def canonical(self) -> CanonicalOrganisation:
        return CanonicalOrganisation(
            organisation_id=self.organisation_id,
            name=self.name,
            industry=self.industry,
            scale=self.scale,
            regions=tuple(region.canonical() for region in self.regions),
            domains=tuple(domain.canonical() for domain in self.domains),
            teams=tuple(team.canonical() for team in self.teams),
            services=tuple(service.canonical() for service in self.services),
            ownerships=tuple(item.canonical() for item in self.ownerships),
        )


class _SdkSizeSource(_ImmutableModel):
    organisations: tuple[_SdkOrganisationInput, ...] = Field(
        min_length=1,
        max_length=MAX_ORGANISATIONS,
    )


class _TopologyHeadcountSource(_ImmutableModel):
    organisations: tuple[_TopologyOrganisationInput, ...] = Field(
        min_length=1,
        max_length=MAX_ORGANISATIONS,
    )


def parse_source(
    payload: Mapping[str, object],
    vintage: SourceVintage | str,
) -> CanonicalEadsSource:
    """Validate one explicitly selected repository fixture source shape."""
    selected_vintage = SourceVintage(vintage)
    if selected_vintage is SourceVintage.SDK_SIZE_V1:
        organisations = tuple(
            item.canonical()
            for item in _SdkSizeSource.model_validate(payload).organisations
        )
    else:
        organisations = tuple(
            item.canonical()
            for item in _TopologyHeadcountSource.model_validate(payload).organisations
        )
    return CanonicalEadsSource(
        source_vintage=selected_vintage,
        organisations=organisations,
    )


__all__ = (
    "CanonicalDomain",
    "CanonicalEadsSource",
    "CanonicalOrganisation",
    "CanonicalOwnership",
    "CanonicalRegion",
    "CanonicalService",
    "CanonicalTeam",
    "IgnoredSourceMeasurement",
    "MAX_SOURCE_BYTES",
    "MAX_SOURCE_DEPTH",
    "MAX_SOURCE_NODES",
    "MAX_SOURCE_TEXT_BYTES",
    "SourceVintage",
    "parse_source",
)
