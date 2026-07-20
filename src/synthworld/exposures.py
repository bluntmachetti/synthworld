from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import Field

from synthworld.models import SyntheticModel, SynthWorld


class DataClass(StrEnum):
    EMAIL = "email"
    USERNAME = "username"
    PHONE = "phone"
    ADDRESS = "address"
    DATE_OF_BIRTH = "date_of_birth"
    EMPLOYER = "employer"
    EDUCATION = "education"
    NATIONAL_ID = "national_id"
    PASSWORD = "password"  # noqa: S105 - data-class label, never a credential


class ExposureSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class LifecycleState(StrEnum):
    FOUND = "found"
    REMOVAL_REQUESTED = "removal_requested"
    CONFIRMED_REMOVED = "confirmed_removed"
    REAPPEARED = "reappeared"


class SearchMatchKind(StrEnum):
    TRUE_MATCH = "true_match"
    NAME_COLLISION = "name_collision"


class SearchResultKind(StrEnum):
    CONFERENCE = "conference"
    DIRECTORY = "directory"
    COMMUNITY = "community"


class BreachExposure(SyntheticModel):
    id: str
    breach_name: str
    occurred_on: date
    severity: ExposureSeverity
    exposed_data: tuple[DataClass, ...] = Field(min_length=1)


class BrokerLifecycleEvent(SyntheticModel):
    state: LifecycleState
    at: date


class BrokerExposure(SyntheticModel):
    id: str
    broker_name: str
    exposed_data: tuple[DataClass, ...] = Field(min_length=1)
    lifecycle: tuple[BrokerLifecycleEvent, ...] = Field(min_length=1)


class SearchExposure(SyntheticModel):
    id: str
    result_kind: SearchResultKind
    title: str
    locator: str
    match_kind: SearchMatchKind
    actual_persona_id: str
    exposed_data: tuple[DataClass, ...] = Field(min_length=1)


class SocialExposure(SyntheticModel):
    id: str
    platform: Literal["Example Social"] = "Example Social"
    username: str
    locator: str
    exposed_data: tuple[DataClass, ...] = Field(min_length=1)
    connected_person_ids: tuple[str, ...]


class ExposureScript(SyntheticModel):
    persona_id: str
    breaches: tuple[BreachExposure, ...]
    brokers: tuple[BrokerExposure, ...]
    searches: tuple[SearchExposure, ...]
    social_profiles: tuple[SocialExposure, ...]

    @property
    def exposure_count(self) -> int:
        return sum(
            map(
                len,
                (self.breaches, self.brokers, self.searches, self.social_profiles),
            )
        )


class ExposureCorpus(SyntheticModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    seed: int
    world: SynthWorld
    exposure_scripts: tuple[ExposureScript, ...]


class CorpusMetrics(SyntheticModel):
    persona_count: int = Field(ge=0)
    script_count: int = Field(ge=0)
    script_coverage: float = Field(ge=0.0, le=1.0)
    exposure_reference_integrity: float = Field(ge=0.0, le=1.0)
    safely_fake_record_rate: float = Field(ge=0.0, le=1.0)
    zero_exposure_persona_count: int = Field(ge=0)
    name_collision_false_positive_count: int = Field(ge=0)
    broker_reappearance_count: int = Field(ge=0)
