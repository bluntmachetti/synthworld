from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SyntheticModel(BaseModel):
    """Immutable base for records that can never be mistaken for live data."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    synthetic: Literal[True] = True


class EmailKind(StrEnum):
    PRIMARY = "primary"
    MANAGED_ALIAS = "managed_alias"


class RelationshipKind(StrEnum):
    FAMILY = "family"
    COLLEAGUE = "colleague"
    CLASSMATE = "classmate"
    NEIGHBOR = "neighbor"
    SOCIAL = "social"


class EvidenceSignal(StrEnum):
    SHARED_SURNAME = "shared_surname"
    SHARED_ADDRESS = "shared_address"
    SHARED_EMPLOYER = "shared_employer"
    SHARED_SCHOOL_YEAR = "shared_school_year"
    SHARED_STREET = "shared_street"
    MUTUAL_PROFILE_LINK = "mutual_profile_link"


class EmailAddress(SyntheticModel):
    value: str
    kind: EmailKind = EmailKind.PRIMARY


class Username(SyntheticModel):
    value: str


class PhoneNumber(SyntheticModel):
    value: str


class Address(SyntheticModel):
    house_number: int = Field(ge=1)
    street_name: str
    city: str
    postal_code: str
    country_code: Literal["ZZ"] = "ZZ"


class Employment(SyntheticModel):
    organization: str
    role: str


class Education(SyntheticModel):
    institution: str
    graduation_year: int = Field(ge=1900, le=2200)


class NationalId(SyntheticModel):
    value: str
    checksum_valid: Literal[False] = False


class Persona(SyntheticModel):
    id: str
    given_name: str
    family_name: str
    date_of_birth: date
    emails: tuple[EmailAddress, ...]
    usernames: tuple[Username, ...]
    phones: tuple[PhoneNumber, ...]
    addresses: tuple[Address, ...]
    employment: tuple[Employment, ...]
    education: tuple[Education, ...]
    national_ids: tuple[NationalId, ...]


class RelationshipEvidence(SyntheticModel):
    signal: EvidenceSignal
    value: str


class RelationshipEdge(SyntheticModel):
    id: str
    source_person_id: str
    target_person_id: str
    kind: RelationshipKind
    evidence: tuple[RelationshipEvidence, ...]


class SynthWorld(SyntheticModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    seed: int
    personas: tuple[Persona, ...]
    relationships: tuple[RelationshipEdge, ...]


class WorldMetrics(SyntheticModel):
    persona_count: int = Field(ge=0)
    relationship_count: int = Field(ge=0)
    safely_fake_record_rate: float = Field(ge=0.0, le=1.0)
    relationship_evidence_integrity: float = Field(ge=0.0, le=1.0)
    graph_connected: bool
