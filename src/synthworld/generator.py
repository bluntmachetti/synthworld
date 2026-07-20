from __future__ import annotations

import re
from datetime import UTC, date, datetime, time, timedelta
from random import Random

from faker import Faker

from synthworld.models import (
    Address,
    Education,
    EmailAddress,
    Employment,
    EvidenceSignal,
    NationalId,
    Persona,
    PhoneNumber,
    RelationshipEdge,
    RelationshipEvidence,
    RelationshipKind,
    SynthWorld,
    Username,
)

MIN_PERSONAS = 2
MAX_PERSONAS = 1_000
_RELATIONSHIP_CYCLE = tuple(RelationshipKind)
_ROLES = (
    "Example Analyst",
    "Test Engineer",
    "Synthetic Researcher",
    "Fixture Designer",
)
_EARLIEST_BIRTH_DATE = date(1956, 7, 20)
_LATEST_BIRTH_DATE = date(2005, 7, 19)
_UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_EARLIEST_BIRTH_SECOND = int(
    (
        datetime.combine(_EARLIEST_BIRTH_DATE, time.min, tzinfo=UTC) - _UNIX_EPOCH
    ).total_seconds()
)
_LATEST_BIRTH_SECOND = int(
    (
        datetime.combine(_LATEST_BIRTH_DATE, time.min, tzinfo=UTC) - _UNIX_EPOCH
    ).total_seconds()
)
_CANONICAL_PRE_EPOCH_OFFSET = timedelta(hours=1)


def generate_world(*, seed: int, persona_count: int = 10) -> SynthWorld:
    """Generate a deterministic, connected synthetic identity world."""

    if not MIN_PERSONAS <= persona_count <= MAX_PERSONAS:
        message = f"persona_count must be between {MIN_PERSONAS} and {MAX_PERSONAS}"
        raise ValueError(message)

    faker = Faker("en_GB")
    faker.seed_instance(seed)
    rng = Random(seed)  # noqa: S311 - deterministic fixture data, never security
    personas = [
        _base_persona(faker=faker, rng=rng, seed=seed, index=index)
        for index in range(persona_count)
    ]
    relationships: list[RelationshipEdge] = []

    for index in range(persona_count - 1):
        kind = _RELATIONSHIP_CYCLE[index % len(_RELATIONSHIP_CYCLE)]
        source = personas[index]
        target, evidence = _plant_relationship(
            kind=kind,
            source=source,
            target=personas[index + 1],
        )
        personas[index + 1] = target
        relationships.append(
            RelationshipEdge(
                id=f"relationship-{index + 1:04d}",
                source_person_id=source.id,
                target_person_id=target.id,
                kind=kind,
                evidence=evidence,
            )
        )

    return SynthWorld(
        seed=seed,
        personas=tuple(personas),
        relationships=tuple(relationships),
    )


def _base_persona(*, faker: Faker, rng: Random, seed: int, index: int) -> Persona:
    given_name = faker.first_name()
    family_name = faker.last_name()
    username = _safe_username(given_name, family_name, index)
    birth_date = _deterministic_birth_date(faker)

    return Persona(
        id=f"persona-{index + 1:04d}",
        given_name=given_name,
        family_name=family_name,
        date_of_birth=birth_date,
        emails=(EmailAddress(value=f"{username}@example.test"),),
        usernames=(Username(value=username),),
        phones=(PhoneNumber(value=_fictional_phone(index)),),
        addresses=(
            Address(
                house_number=100 + index,
                street_name=f"{(index % 25) + 1} Example Avenue",
                city="Testville",
                postal_code="00000",
            ),
        ),
        employment=(
            Employment(
                organization=f"Example Works {index + 1:04d}",
                role=_ROLES[rng.randrange(len(_ROLES))],
            ),
        ),
        education=(
            Education(
                institution=f"Test University {index + 1:04d}",
                graduation_year=birth_date.year + 22,
            ),
        ),
        national_ids=(NationalId(value=_invalid_national_id(seed, index)),),
    )


def _deterministic_birth_date(faker: Faker) -> date:
    """Project Faker's draw through one fixed, host-independent timestamp rule."""

    timestamp = faker.random.uniform(
        _EARLIEST_BIRTH_SECOND,
        _LATEST_BIRTH_SECOND,
    )
    if timestamp < 0:
        instant = _UNIX_EPOCH + timedelta(seconds=int(timestamp))
        instant -= _CANONICAL_PRE_EPOCH_OFFSET
    else:
        instant = _UNIX_EPOCH + timedelta(seconds=timestamp)
    return instant.date()


def _safe_username(given_name: str, family_name: str, index: int) -> str:
    name = re.sub(
        r"[^a-z0-9]+",
        "_",
        f"{given_name}_{family_name}".lower(),
    ).strip("_")
    return f"synth_{name or 'persona'}_{index + 1:04d}"


def _fictional_phone(index: int) -> str:
    area_code = 200 + (index // 100)
    subscriber = 100 + (index % 100)
    return f"+1-{area_code:03d}-555-{subscriber:04d}"


def _invalid_national_id(seed: int, index: int) -> str:
    payload_number = ((abs(seed) % 100_000_000) + index) % 100_000_000
    payload = f"{payload_number:08d}"
    valid_digit = next(
        candidate for candidate in range(10) if _luhn_valid(f"{payload}{candidate}")
    )
    invalid_digit = (valid_digit + 1) % 10
    return f"SYN-{payload}{invalid_digit}"


def _luhn_valid(digits: str) -> bool:
    total = 0
    parity = len(digits) % 2
    for index, character in enumerate(digits):
        digit = int(character)
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def _plant_relationship(
    *,
    kind: RelationshipKind,
    source: Persona,
    target: Persona,
) -> tuple[Persona, tuple[RelationshipEvidence, ...]]:
    evidence: tuple[RelationshipEvidence, ...]
    if kind is RelationshipKind.FAMILY:
        updated = target.model_copy(
            update={
                "family_name": source.family_name,
                "addresses": source.addresses,
            }
        )
        evidence = (
            RelationshipEvidence(
                signal=EvidenceSignal.SHARED_SURNAME,
                value=source.family_name,
            ),
            RelationshipEvidence(
                signal=EvidenceSignal.SHARED_ADDRESS,
                value=_address_key(source.addresses[0]),
            ),
        )
    elif kind is RelationshipKind.COLLEAGUE:
        updated = target.model_copy(update={"employment": source.employment})
        evidence = (
            RelationshipEvidence(
                signal=EvidenceSignal.SHARED_EMPLOYER,
                value=source.employment[0].organization,
            ),
        )
    elif kind is RelationshipKind.CLASSMATE:
        updated = target.model_copy(update={"education": source.education})
        shared_education = source.education[0]
        evidence = (
            RelationshipEvidence(
                signal=EvidenceSignal.SHARED_SCHOOL_YEAR,
                value=(
                    f"{shared_education.institution}|{shared_education.graduation_year}"
                ),
            ),
        )
    elif kind is RelationshipKind.NEIGHBOR:
        source_address = source.addresses[0]
        target_address = target.addresses[0].model_copy(
            update={
                "street_name": source_address.street_name,
                "city": source_address.city,
                "postal_code": source_address.postal_code,
            }
        )
        updated = target.model_copy(update={"addresses": (target_address,)})
        evidence = (
            RelationshipEvidence(
                signal=EvidenceSignal.SHARED_STREET,
                value=_street_key(source_address),
            ),
        )
    else:
        updated = target
        evidence = (
            RelationshipEvidence(
                signal=EvidenceSignal.MUTUAL_PROFILE_LINK,
                value=f"synth://profiles/{source.id}/{target.id}",
            ),
        )

    return updated, evidence


def _address_key(address: Address) -> str:
    return "|".join(
        (
            str(address.house_number),
            address.street_name,
            address.city,
            address.postal_code,
        )
    )


def _street_key(address: Address) -> str:
    return "|".join((address.street_name, address.city, address.postal_code))
