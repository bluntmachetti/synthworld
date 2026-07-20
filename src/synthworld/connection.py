from __future__ import annotations

from enum import StrEnum
from typing import Literal
from urllib.parse import urlparse
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from synthworld.models import SyntheticModel


class PublicIdentityAttributeKind(StrEnum):
    EMAIL = "email"
    FAMILY_NAME = "family_name"
    USERNAME = "username"
    PHONE = "phone"
    FULL_ADDRESS = "full_address"
    DATE_OF_BIRTH = "date_of_birth"
    EMPLOYER = "employer"
    SCHOOL_YEAR = "school_year"
    SOCIAL_PROFILE = "social_profile"


class PublicIdentitySourceType(StrEnum):
    DIRECTORY = "directory"
    CONFERENCE = "conference"
    ALUMNI = "alumni"
    BROKER = "broker"
    SOCIAL = "social"


class PublicAssociationKind(StrEnum):
    PROPERTY_ADJACENCY = "property_adjacency"
    PROFILE_LINK = "profile_link"


class AdversarialPackKind(StrEnum):
    COMMON_NAME = "common_name"
    UNICODE_DIACRITICS = "unicode_diacritics"
    TWINS_SHARED_ADDRESS = "twins_shared_address"
    MAIDEN_NAME = "maiden_name"
    MISSPELLING_ALIAS = "misspelling_alias"


class PublicTruthRelationshipKind(StrEnum):
    NEIGHBOR = "neighbor"
    SOCIAL = "social"


class PublicIdentityAttribute(SyntheticModel):
    kind: PublicIdentityAttributeKind
    value: str
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("value")
    @classmethod
    def require_nonblank_value(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("public identity attribute values must be nonblank")
        return normalized


class PublicIdentityRecord(SyntheticModel):
    id: UUID
    source_type: PublicIdentitySourceType
    source_url: str
    display_name: str
    confidence: float = Field(ge=0.0, le=1.0)
    attributes: tuple[PublicIdentityAttribute, ...] = Field(min_length=1)

    @field_validator("source_url")
    @classmethod
    def require_reserved_source_url(cls, value: str) -> str:
        return _reserved_url(value)

    @field_validator("display_name")
    @classmethod
    def require_nonblank_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("public identity display names must be nonblank")
        return normalized

    @field_validator("attributes")
    @classmethod
    def sort_unique_attributes(
        cls,
        value: tuple[PublicIdentityAttribute, ...],
    ) -> tuple[PublicIdentityAttribute, ...]:
        keys = [(item.kind.value, item.value) for item in value]
        if len(keys) != len(set(keys)):
            raise ValueError("public identity attributes must be unique")
        return tuple(sorted(value, key=lambda item: (item.kind.value, item.value)))


class PublicAssociationRecord(SyntheticModel):
    id: UUID
    kind: PublicAssociationKind
    source_url: str
    source_reference: str
    target_reference: str
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("source_url")
    @classmethod
    def require_reserved_source_url(cls, value: str) -> str:
        return _reserved_url(value)

    @field_validator("source_reference", "target_reference")
    @classmethod
    def require_nonblank_reference(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("public association references must be nonblank")
        return normalized

    @model_validator(mode="after")
    def require_distinct_references(self) -> PublicAssociationRecord:
        if self.source_reference == self.target_reference:
            raise ValueError("public associations require distinct references")
        return self


class PublicConnectionCorpus(SyntheticModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    seed: int
    identity_records: tuple[PublicIdentityRecord, ...]
    association_records: tuple[PublicAssociationRecord, ...]

    @field_validator("identity_records")
    @classmethod
    def sort_unique_identity_records(
        cls,
        value: tuple[PublicIdentityRecord, ...],
    ) -> tuple[PublicIdentityRecord, ...]:
        _require_unique_ids(tuple(item.id for item in value), "identity records")
        return tuple(sorted(value, key=lambda item: item.id.int))

    @field_validator("association_records")
    @classmethod
    def sort_unique_association_records(
        cls,
        value: tuple[PublicAssociationRecord, ...],
    ) -> tuple[PublicAssociationRecord, ...]:
        _require_unique_ids(tuple(item.id for item in value), "association records")
        return tuple(sorted(value, key=lambda item: item.id.int))


class RecordMembership(SyntheticModel):
    record_id: UUID
    entity_id: str

    @field_validator("entity_id")
    @classmethod
    def require_nonblank_entity(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("record memberships require an entity ID")
        return normalized


class AdversarialCase(SyntheticModel):
    pack: AdversarialPackKind
    record_ids: tuple[UUID, ...] = Field(min_length=1)
    entity_ids: tuple[str, ...] = Field(min_length=1)

    @field_validator("record_ids")
    @classmethod
    def sort_unique_record_ids(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        _require_unique_ids(value, "adversarial case records")
        return tuple(sorted(value, key=lambda item: item.int))

    @field_validator("entity_ids")
    @classmethod
    def sort_unique_entity_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(item.strip() for item in value)
        if not all(normalized) or len(normalized) != len(set(normalized)):
            raise ValueError("adversarial case entity IDs must be nonblank and unique")
        return tuple(sorted(normalized))


class PublicRelationshipTruth(SyntheticModel):
    source_record_id: UUID
    target_record_id: UUID
    kind: PublicTruthRelationshipKind
    reciprocal_association_ids: tuple[UUID, UUID]

    @field_validator("reciprocal_association_ids")
    @classmethod
    def sort_distinct_association_ids(
        cls,
        value: tuple[UUID, UUID],
    ) -> tuple[UUID, UUID]:
        if value[0] == value[1]:
            raise ValueError("relationship truth requires two association records")
        return tuple(sorted(value, key=lambda item: item.int))  # type: ignore[return-value]

    @model_validator(mode="after")
    def order_endpoints(self) -> PublicRelationshipTruth:
        if self.source_record_id.int > self.target_record_id.int:
            raise ValueError("relationship truth endpoints must use canonical order")
        if self.source_record_id == self.target_record_id:
            raise ValueError("relationship truth requires distinct identity records")
        return self


class UnilateralAssociationControl(SyntheticModel):
    association_id: UUID
    kind: PublicAssociationKind


class ConnectionAnswerKey(SyntheticModel):
    record_memberships: tuple[RecordMembership, ...]
    adversarial_cases: tuple[AdversarialCase, ...]
    relationships: tuple[PublicRelationshipTruth, ...]
    unilateral_controls: tuple[UnilateralAssociationControl, ...]

    @field_validator("record_memberships")
    @classmethod
    def sort_memberships(
        cls,
        value: tuple[RecordMembership, ...],
    ) -> tuple[RecordMembership, ...]:
        record_ids = tuple(item.record_id for item in value)
        _require_unique_ids(record_ids, "record memberships")
        return tuple(sorted(value, key=lambda item: item.record_id.int))

    @field_validator("adversarial_cases")
    @classmethod
    def sort_cases(
        cls,
        value: tuple[AdversarialCase, ...],
    ) -> tuple[AdversarialCase, ...]:
        packs = tuple(item.pack for item in value)
        if len(packs) != len(set(packs)):
            raise ValueError("adversarial cases require unique pack labels")
        return tuple(sorted(value, key=lambda item: item.pack.value))

    @field_validator("relationships")
    @classmethod
    def sort_relationships(
        cls,
        value: tuple[PublicRelationshipTruth, ...],
    ) -> tuple[PublicRelationshipTruth, ...]:
        keys = tuple(
            (item.source_record_id, item.target_record_id, item.kind) for item in value
        )
        if len(keys) != len(set(keys)):
            raise ValueError("relationship answer keys must be unique")
        return tuple(
            sorted(
                value,
                key=lambda item: (
                    item.source_record_id.int,
                    item.target_record_id.int,
                    item.kind.value,
                ),
            )
        )

    @field_validator("unilateral_controls")
    @classmethod
    def sort_controls(
        cls,
        value: tuple[UnilateralAssociationControl, ...],
    ) -> tuple[UnilateralAssociationControl, ...]:
        ids = tuple(item.association_id for item in value)
        _require_unique_ids(ids, "unilateral controls")
        return tuple(sorted(value, key=lambda item: item.association_id.int))


class ConnectionBenchmark(SyntheticModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    seed: int
    public: PublicConnectionCorpus
    answer_key: ConnectionAnswerKey

    @model_validator(mode="after")
    def require_matching_seed(self) -> ConnectionBenchmark:
        if self.public.seed != self.seed:
            raise ValueError("connection benchmark seeds must match")
        return self


def _reserved_url(value: str) -> str:
    normalized = value.strip()
    parsed = urlparse(normalized)
    if parsed.scheme != "https" or not (
        parsed.hostname == "example.test"
        or (parsed.hostname or "").endswith(".example.test")
    ):
        raise ValueError("public fixture URLs must use reserved HTTPS domains")
    return normalized


def _require_unique_ids(ids: tuple[UUID, ...], label: str) -> None:
    if len(ids) != len(set(ids)):
        raise ValueError(f"{label} require unique IDs")


__all__ = [
    "AdversarialCase",
    "AdversarialPackKind",
    "ConnectionAnswerKey",
    "ConnectionBenchmark",
    "PublicAssociationKind",
    "PublicAssociationRecord",
    "PublicConnectionCorpus",
    "PublicIdentityAttribute",
    "PublicIdentityAttributeKind",
    "PublicIdentityRecord",
    "PublicIdentitySourceType",
    "PublicRelationshipTruth",
    "PublicTruthRelationshipKind",
    "RecordMembership",
    "UnilateralAssociationControl",
]
