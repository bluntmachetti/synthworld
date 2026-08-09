"""Strict source-vintage contracts for the EADS adapter example.

Callers must select a source vintage. Population-like source fields are retained
only as ignored measurements; downstream population policy must not consume them.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class _ImmutableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


SourceText = Annotated[str, Field(strict=True, min_length=1)]


class SourceVintage(StrEnum):
    SDK_SIZE_V1 = "sdk-size-v1"
    TOPOLOGY_HEADCOUNT_V1 = "topology-headcount-v1"


class CanonicalRegion(_ImmutableModel):
    region_id: SourceText
    name: SourceText


class CanonicalDomain(_ImmutableModel):
    domain_id: SourceText
    name: SourceText
    children: tuple[CanonicalDomain, ...] = ()


class CanonicalService(_ImmutableModel):
    service_id: SourceText
    name: SourceText
    service_type: SourceText
    classification: SourceText | None = None
    owning_team_id: SourceText


class CanonicalOwnership(_ImmutableModel):
    team_id: SourceText
    service_id: SourceText
    relationship: SourceText


class IgnoredSourceMeasurement(_ImmutableModel):
    field: Literal["size", "headcount"]
    value: int = Field(strict=True, ge=0)


class CanonicalTeam(_ImmutableModel):
    team_id: SourceText
    name: SourceText
    team_type: SourceText
    domain_id: SourceText
    region_ids: tuple[SourceText, ...] = ()
    ignored_source_measurements: tuple[IgnoredSourceMeasurement, ...]


class CanonicalOrganisation(_ImmutableModel):
    organisation_id: SourceText
    name: SourceText
    industry: SourceText
    scale: SourceText
    regions: tuple[CanonicalRegion, ...] = ()
    domains: tuple[CanonicalDomain, ...] = ()
    teams: tuple[CanonicalTeam, ...] = ()
    services: tuple[CanonicalService, ...] = ()
    ownerships: tuple[CanonicalOwnership, ...] = ()


class CanonicalEadsSource(_ImmutableModel):
    source_vintage: SourceVintage
    organisations: tuple[CanonicalOrganisation, ...] = Field(min_length=1)


class _RegionInput(_ImmutableModel):
    region_id: SourceText
    name: SourceText

    def canonical(self) -> CanonicalRegion:
        return CanonicalRegion(region_id=self.region_id, name=self.name)


class _DomainInput(_ImmutableModel):
    domain_id: SourceText
    name: SourceText
    children: tuple[_DomainInput, ...] = ()

    def canonical(self) -> CanonicalDomain:
        return CanonicalDomain(
            domain_id=self.domain_id,
            name=self.name,
            children=tuple(child.canonical() for child in self.children),
        )


class _ServiceInput(_ImmutableModel):
    service_id: SourceText
    name: SourceText
    service_type: SourceText
    classification: SourceText | None = None
    owning_team_id: SourceText

    def canonical(self) -> CanonicalService:
        return CanonicalService(**self.model_dump())


class _OwnershipInput(_ImmutableModel):
    team_id: SourceText
    service_id: SourceText
    relationship: SourceText

    def canonical(self) -> CanonicalOwnership:
        return CanonicalOwnership(**self.model_dump())


class _SdkTeamInput(_ImmutableModel):
    team_id: SourceText
    name: SourceText
    team_type: SourceText
    domain_id: SourceText
    region_ids: tuple[SourceText, ...] = ()
    size: int = Field(strict=True, ge=0)

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
    team_type: SourceText
    domain_id: SourceText
    region_ids: tuple[SourceText, ...] = ()
    headcount: int = Field(strict=True, ge=0)

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
    industry: SourceText
    scale: SourceText
    regions: tuple[_RegionInput, ...] = ()
    domains: tuple[_DomainInput, ...] = ()
    services: tuple[_ServiceInput, ...] = ()
    ownerships: tuple[_OwnershipInput, ...] = ()


class _SdkOrganisationInput(_OrganisationInput):
    teams: tuple[_SdkTeamInput, ...] = ()

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
    teams: tuple[_TopologyTeamInput, ...] = ()

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
    organisations: tuple[_SdkOrganisationInput, ...] = Field(min_length=1)


class _TopologyHeadcountSource(_ImmutableModel):
    organisations: tuple[_TopologyOrganisationInput, ...] = Field(min_length=1)


def parse_source(
    payload: Mapping[str, object], vintage: SourceVintage | str
) -> CanonicalEadsSource:
    """Validate and normalize one explicitly selected EADS source vintage."""
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
