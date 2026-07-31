"""The ``households_and_workplaces`` profile: overlapping social context.

Issue #43 in one sentence: the core world is a path graph whose identifiers spell
out the persona ordinal, so it tests nothing about resolving identity. This profile
replaces both properties without touching the frozen one.

Two rules govern every value here, and they are what the leakage detector in
:mod:`synthworld.leakage` exists to enforce.

**No value may be derived from the generation index.** Not literally, and not
through an encoding. A design proposed during review rendered national identifiers
as ``(39_916_801 * index + offset) mod 10**8``: no ordinal, not monotone, and
recoverable by anyone who takes first differences. Values here derive from either
the person's own content - their name - or from a keyed hash whose output has no
algebraic relationship to the index at all.

**Structure comes from membership, not from decoration.** Households, workplaces
and schools are shared registries, so people who share one share a real attribute.
Edges follow from those memberships, which is where branching, cycles and multiple
components come from - rather than from adding random edges to a path and calling
it a graph.

One consequence is deliberate and easy to get wrong. If everyone in a household
shared an address *and* a surname, then relationship inference and entity
resolution would collapse into the same task and the adversarial cases in #4 would
be testing nothing. So household membership is not a surname rule: partners keep
their own names, and a shared surname is evidence, never a definition.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from hashlib import blake2b
from typing import Literal, Self

from faker import Faker
from pydantic import Field, model_validator

from synthworld.models import (
    Address,
    Education,
    EmailAddress,
    EmailKind,
    Employment,
    EvidenceSignal,
    NationalId,
    Persona,
    PhoneNumber,
    RelationshipEdge,
    RelationshipEvidence,
    RelationshipKind,
    SyntheticModel,
    SynthWorld,
    Username,
)

PROFILE_NAME = "households_and_workplaces"
PROFILE_VERSION: Literal["1.0.0"] = "1.0.0"

#: Enumerated product spaces. Registries are drawn from these without replacement,
#: so an institution is a shared name rather than a per-person string. The core
#: profile emits 80 distinct employers across 100 people, at most two each, which
#: is a per-person string wearing an institution's name.
_ORG_MARKERS = ("Example", "Test", "Sample", "Fictional")
_ORG_STEMS = (
    "Harbour",
    "Lantern",
    "Meridian",
    "Quarry",
    "Thicket",
    "Verdant",
    "Kestrel",
    "Bramble",
    "Cinder",
    "Fathom",
    "Granite",
    "Willow",
)
_ORG_FORMS = ("Works", "Logistics", "Analytics", "Foundry")
_SCHOOL_STEMS = ("Northgate", "Southfield", "Eastmoor", "Westbrook", "Fenwick", "Ashby")
_SCHOOL_FORMS = ("Academy", "College", "Institute")
_ROLES = ("Analyst", "Engineer", "Coordinator", "Technician", "Registrar")
_STREETS = (
    "Example Avenue",
    "Test Lane",
    "Sample Row",
    "Fictional Way",
    "Placeholder Close",
    "Specimen Street",
)
_CITIES = ("Testville", "Sampleton", "Exampleford", "Fictionbury")
_EMAIL_DOMAINS = ("example.test", "example.invalid", "mail.example.test")

#: Handle shapes. Several, so that two people with the same normalised name usually
#: still differ - collisions must be planted and counted, not accidental.
_HANDLE_STYLES = (
    "{given}.{family}",
    "{initial}{family}",
    "{given}{family}",
    "{given}_{family}",
    "{family}.{given}",
    "{family}{initial}",
)


class HouseholdsConfig(SyntheticModel):
    """Explicit configuration. Part of the reproducibility tuple, so it is hashed.

    Same profile version, schema version, seed and configuration must give
    byte-identical artifacts; anything not recorded here cannot influence output.
    """

    profile_version: Literal["1.0.0"] = PROFILE_VERSION
    person_count: int = Field(default=100, ge=8, le=2_000)
    household_count: int = Field(default=34, ge=2)
    workplace_count: int = Field(default=14, ge=2)
    school_count: int = Field(default=9, ge=1)
    isolated_person_count: int = Field(default=6, ge=0)
    colleagues_per_person: int = Field(default=3, ge=1, le=8)

    @model_validator(mode="after")
    def require_room_for_structure(self) -> Self:
        if self.isolated_person_count >= self.person_count:
            raise ValueError("isolated people cannot be the whole population")
        if self.household_count > self.person_count - self.isolated_person_count:
            raise ValueError("more households than people to put in them")
        if self.workplace_count > len(_ORG_MARKERS) * len(_ORG_STEMS) * len(_ORG_FORMS):
            raise ValueError("workplace_count exceeds the enumerated registry")
        if self.school_count > len(_ORG_MARKERS) * len(_SCHOOL_STEMS) * len(
            _SCHOOL_FORMS
        ):
            raise ValueError("school_count exceeds the enumerated registry")
        return self

    def digest(self) -> str:
        """Canonical digest of the configuration, stable under key ordering."""

        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True)
        return blake2b(canonical.encode("utf-8"), digest_size=16).hexdigest()


def _draw(*, seed: int, digest: str, purpose: str, index: int) -> int:
    """A keyed-hash draw.

    Keyed on the index, but not *derived* from it in any recoverable sense: blake2b
    output is neither monotone nor affine in its input, so first differences of
    anything drawn this way are as unstructured as the values themselves. That is
    the property :mod:`synthworld.leakage` measures.
    """

    material = f"{PROFILE_NAME}|{PROFILE_VERSION}|{seed}|{digest}|{purpose}|{index}"
    return int.from_bytes(
        blake2b(material.encode("utf-8"), digest_size=8).digest(), "big"
    )


def _pick(
    pool: Sequence[str], *, seed: int, digest: str, purpose: str, index: int
) -> str:
    return pool[
        _draw(seed=seed, digest=digest, purpose=purpose, index=index) % len(pool)
    ]


def _registry(count: int, *, kind: Literal["workplace", "school"]) -> tuple[str, ...]:
    """Enumerate a shared registry deterministically, without replacement.

    Product-space enumeration rather than sampling: membership is what varies
    between seeds, while the registry itself stays a fixed, inspectable list.
    """

    stems = _ORG_STEMS if kind == "workplace" else _SCHOOL_STEMS
    forms = _ORG_FORMS if kind == "workplace" else _SCHOOL_FORMS
    names = [
        f"{marker} {stem} {form}"
        for marker in _ORG_MARKERS
        for stem in stems
        for form in forms
    ]
    return tuple(sorted(names)[:count])


def _handle(*, given: str, family: str, seed: int, digest: str, index: int) -> str:
    style = _pick(
        _HANDLE_STYLES, seed=seed, digest=digest, purpose="handle", index=index
    )
    rendered = style.format(
        given=given.lower(), family=family.lower(), initial=given[:1].lower()
    )
    return "".join(
        character for character in rendered if character.isalnum() or character in "._"
    )


def _national_id(*, seed: int, digest: str, index: int) -> NationalId:
    """Deliberately invalid, and deliberately not an arithmetic progression."""

    payload = _draw(seed=seed, digest=digest, purpose="national-id", index=index)
    body = f"{payload % 10**9:09d}"
    return NationalId(value=f"SYN-{body}-X", checksum_valid=False)


def _phone(*, seed: int, digest: str, index: int) -> PhoneNumber:
    """Fictional range. Subscriber digits are drawn, not counted."""

    drawn = _draw(seed=seed, digest=digest, purpose="phone", index=index)
    return PhoneNumber(value=f"+1-555-01{drawn % 100:02d}-{drawn // 100 % 10_000:04d}")


def generate_households_world(
    *, seed: int, config: HouseholdsConfig | None = None
) -> SynthWorld:
    """Generate a world with overlapping households, workplaces and schools."""

    settings = config if config is not None else HouseholdsConfig()
    digest = settings.digest()
    faker = Faker("en_GB")
    faker.seed_instance(seed)

    count = settings.person_count
    social_count = count - settings.isolated_person_count
    workplaces = _registry(settings.workplace_count, kind="workplace")
    schools = _registry(settings.school_count, kind="school")

    # Household addresses first: members share one, which is what makes a household
    # observable without making it a surname rule.
    addresses = tuple(
        Address(
            house_number=1
            + _draw(seed=seed, digest=digest, purpose="house", index=index) % 400,
            street_name=_pick(
                _STREETS, seed=seed, digest=digest, purpose="street", index=index
            ),
            city=_pick(_CITIES, seed=seed, digest=digest, purpose="city", index=index),
            postal_code="ZZ0 0ZZ",
        )
        for index in range(settings.household_count)
    )

    personas: list[Persona] = []
    household_of: dict[str, int] = {}
    workplace_of: dict[str, str] = {}
    school_of: dict[str, str] = {}

    for index in range(count):
        given = faker.first_name()
        family = faker.last_name()
        person_id = (
            "person-"
            + f"{_draw(seed=seed, digest=digest, purpose='id', index=index):016x}"
        )
        isolated = index >= social_count
        handle = _handle(
            given=given, family=family, seed=seed, digest=digest, index=index
        )
        domain = _pick(
            _EMAIL_DOMAINS, seed=seed, digest=digest, purpose="domain", index=index
        )
        household = (
            _draw(seed=seed, digest=digest, purpose="household", index=index)
            % settings.household_count
        )
        # Isolated controls are deliberate, not leftovers: no household, no
        # workplace, no school, so they appear as genuine zero-degree nodes.
        address = (
            Address(
                house_number=1
                + _draw(seed=seed, digest=digest, purpose="solo-house", index=index)
                % 400,
                street_name=_pick(
                    _STREETS,
                    seed=seed,
                    digest=digest,
                    purpose="solo-street",
                    index=index,
                ),
                city=_pick(
                    _CITIES, seed=seed, digest=digest, purpose="solo-city", index=index
                ),
                postal_code="ZZ0 0ZZ",
            )
            if isolated
            else addresses[household]
        )
        employment: tuple[Employment, ...] = ()
        education: tuple[Education, ...] = ()
        if not isolated:
            household_of[person_id] = household
            employer = _pick(
                workplaces, seed=seed, digest=digest, purpose="employer", index=index
            )
            school = _pick(
                schools, seed=seed, digest=digest, purpose="school", index=index
            )
            workplace_of[person_id] = employer
            school_of[person_id] = school
            employment = (
                Employment(
                    organization=employer,
                    role="Example "
                    + _pick(
                        _ROLES, seed=seed, digest=digest, purpose="role", index=index
                    ),
                ),
            )
            education = (
                Education(
                    institution=school,
                    graduation_year=1990
                    + _draw(seed=seed, digest=digest, purpose="year", index=index) % 35,
                ),
            )
        personas.append(
            Persona(
                id=person_id,
                given_name=given,
                family_name=family,
                date_of_birth=faker.date_of_birth(minimum_age=19, maximum_age=79),
                addresses=(address,),
                emails=(
                    EmailAddress(value=f"{handle}@{domain}", kind=EmailKind.PRIMARY),
                ),
                phones=(_phone(seed=seed, digest=digest, index=index),),
                usernames=(Username(value=handle),),
                national_ids=(_national_id(seed=seed, digest=digest, index=index),),
                employment=employment,
                education=education,
            )
        )

    return SynthWorld(
        seed=seed,
        personas=tuple(personas),
        relationships=_relationships(
            personas=personas,
            household_of=household_of,
            workplace_of=workplace_of,
            school_of=school_of,
            settings=settings,
            seed=seed,
            digest=digest,
        ),
    )


def _relationships(
    *,
    personas: Sequence[Persona],
    household_of: dict[str, int],
    workplace_of: dict[str, str],
    school_of: dict[str, str],
    settings: HouseholdsConfig,
    seed: int,
    digest: str,
) -> tuple[RelationshipEdge, ...]:
    """Edges follow membership, so branching and cycles are structural.

    A person sharing a household with one group and a workplace with another is
    what closes a cycle. Nothing here adds an edge to reach a target count.
    """

    edges: list[RelationshipEdge] = []
    seen: set[tuple[str, str]] = set()

    def add(
        left: Persona,
        right: Persona,
        kind: RelationshipKind,
        signal: EvidenceSignal,
        value: str,
    ) -> None:
        key = (left.id, right.id) if left.id < right.id else (right.id, left.id)
        if key in seen:
            return
        seen.add(key)
        edges.append(
            RelationshipEdge(
                id=f"edge-{blake2b('|'.join(key).encode(), digest_size=8).hexdigest()}",
                source_person_id=key[0],
                target_person_id=key[1],
                kind=kind,
                evidence=(RelationshipEvidence(signal=signal, value=value),),
            )
        )

    by_household: dict[int, list[Persona]] = {}
    by_workplace: dict[str, list[Persona]] = {}
    by_school: dict[str, list[Persona]] = {}
    for person in personas:
        if person.id in household_of:
            by_household.setdefault(household_of[person.id], []).append(person)
            by_workplace.setdefault(workplace_of[person.id], []).append(person)
            by_school.setdefault(school_of[person.id], []).append(person)

    for members in by_household.values():
        for position, left in enumerate(members):
            for right in members[position + 1 :]:
                add(
                    left,
                    right,
                    RelationshipKind.FAMILY,
                    EvidenceSignal.SHARED_ADDRESS,
                    left.addresses[0].street_name,
                )

    # Bounded fan-out inside large groups: connecting every pair in a sixteen-person
    # workplace would swamp the graph and flatten the degree distribution.
    for group, kind, signal in (
        (by_workplace, RelationshipKind.COLLEAGUE, EvidenceSignal.SHARED_EMPLOYER),
        (by_school, RelationshipKind.CLASSMATE, EvidenceSignal.SHARED_SCHOOL_YEAR),
    ):
        for key, members in group.items():
            for position, left in enumerate(members):
                for offset in range(1, settings.colleagues_per_person + 1):
                    partner = members[
                        (
                            position
                            + offset
                            + _draw(
                                seed=seed, digest=digest, purpose=key, index=position
                            )
                            % max(1, len(members) - 1)
                        )
                        % len(members)
                    ]
                    if partner.id != left.id:
                        add(left, partner, kind, signal, key)

    return tuple(sorted(edges, key=lambda edge: edge.id))


__all__ = [
    "PROFILE_NAME",
    "PROFILE_VERSION",
    "HouseholdsConfig",
    "generate_households_world",
]
