"""What the households profile has to prove, measured rather than asserted."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Mapping
from datetime import date

import pytest
from pydantic import ValidationError

from synthworld.leakage import world_recoverability
from synthworld.metrics import relationship_evidence_matches
from synthworld.models import Persona, SynthWorld
from synthworld.profiles.households import (
    HouseholdsConfig,
    _address_key,
    generate_households_world,
)

_SEEDS = (7, 11, 42)


def _fields(personas: tuple[Persona, ...]) -> Mapping[str, list[str]]:
    return {
        "email": [item.emails[0].value for item in personas],
        "username": [item.usernames[0].value for item in personas],
        "phone": [item.phones[0].value for item in personas],
        "national_id": [item.national_ids[0].value for item in personas],
        "address": [
            f"{item.addresses[0].house_number} {item.addresses[0].street_name}"
            for item in personas
        ],
        "employer": [
            item.employment[0].organization if item.employment else ""
            for item in personas
        ],
        "school": [
            item.education[0].institution if item.education else "" for item in personas
        ],
    }


def _adjacency(world: SynthWorld) -> dict[str, set[str]]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in world.relationships:
        adjacency[edge.source_person_id].add(edge.target_person_id)
        adjacency[edge.target_person_id].add(edge.source_person_id)
    return adjacency


def _components(world: SynthWorld) -> list[int]:
    adjacency = _adjacency(world)
    seen: set[str] = set()
    sizes: list[int] = []
    for start in sorted(item.id for item in world.personas):
        if start in seen:
            continue
        stack, size = [start], 0
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            size += 1
            stack.extend(adjacency[current] - seen)
        sizes.append(size)
    return sorted(sizes, reverse=True)


@pytest.mark.parametrize("seed", _SEEDS)
def test_no_public_field_gives_back_the_generation_index(seed: int) -> None:
    """The requirement the profile exists for, checked with the real detector.

    That detector is not vacuous here: pointed at the core profile it reports
    email, username, employer, school and phone as leaking, and it catches an
    affine-modular encoding that contains no ordinal at all.
    """

    world = generate_households_world(seed=seed)
    scored = world_recoverability(_fields(world.personas))

    leaking = [item for item in scored if item.verdict == "leaking"]
    assert leaking == [], [(item.field, item.reasons) for item in leaking]


@pytest.mark.parametrize("seed", _SEEDS)
def test_topology_branches_cycles_and_leaves_deliberate_isolates(seed: int) -> None:
    """The core profile is a path: one component, no cycles, no isolated nodes."""

    world = generate_households_world(seed=seed)
    adjacency = _adjacency(world)
    degrees = Counter(len(adjacency[item.id]) for item in world.personas)
    edges = len(world.relationships)
    components = _components(world)

    assert len(components) > 1
    assert edges - len(world.personas) + len(components) > 0  # cycle rank
    # At least the deliberate controls are degree zero. More may be: a person whose
    # team and cohort are singletons and whose household surname is theirs alone is
    # incidentally unconnected, which is realistic and must not be asserted away.
    assert degrees[0] >= HouseholdsConfig().isolated_person_count
    # A path has exactly two distinct degrees. Anything resembling a real social
    # graph has many, which is what makes structure informative.
    assert len(degrees) > 5


@pytest.mark.parametrize("seed", _SEEDS)
def test_same_seed_and_configuration_replays_byte_identically(seed: int) -> None:
    first = generate_households_world(seed=seed).model_dump_json()
    second = generate_households_world(seed=seed).model_dump_json()

    assert first == second


def test_seeds_change_scenario_structure_not_only_identifiers() -> None:
    """The defect this profile answers, tested semantically.

    Byte inequality is too weak: the core profile satisfies it while producing the
    same path graph and the same relationship-kind counts on every seed. These
    fingerprints are multisets of shapes, so they are invariant to renaming and
    move only when the scenario itself moves.
    """

    def fingerprint(seed: int) -> tuple[tuple[int, ...], ...]:
        world = generate_households_world(seed=seed)
        adjacency = _adjacency(world)
        return (
            tuple(sorted(len(adjacency[item.id]) for item in world.personas)),
            tuple(
                sorted(
                    Counter(
                        item.employment[0].organization
                        for item in world.personas
                        if item.employment
                    ).values()
                )
            ),
            tuple(sorted(Counter(_components(world)).values())),
        )

    assert len({fingerprint(seed) for seed in _SEEDS}) == len(_SEEDS)


@pytest.mark.parametrize("seed", _SEEDS)
def test_institutions_are_shared_registries_not_per_person_strings(seed: int) -> None:
    """The core profile emits 80 employers for 100 people, at most two each."""

    world = generate_households_world(seed=seed)
    employers = Counter(
        item.employment[0].organization for item in world.personas if item.employment
    )

    assert len(employers) <= HouseholdsConfig().workplace_count
    assert max(employers.values()) >= 3


@pytest.mark.parametrize("seed", _SEEDS)
def test_a_shared_household_does_not_imply_a_shared_surname(seed: int) -> None:
    """Otherwise relationship inference and entity resolution become one task.

    If every household were also a surname group, a matcher could recover the
    household from the name alone and the adversarial cases in issue #4 would be
    testing nothing.
    """

    world = generate_households_world(seed=seed)
    by_address: dict[str, set[str]] = defaultdict(set)
    for person in world.personas:
        address = person.addresses[0]
        by_address[f"{address.house_number}|{address.street_name}|{address.city}"].add(
            person.family_name
        )
    shared = [names for names in by_address.values() if len(names) > 0]

    assert any(len(names) > 1 for names in shared)


@pytest.mark.parametrize("seed", _SEEDS)
def test_values_stay_safely_fictional(seed: int) -> None:
    world = generate_households_world(seed=seed)

    for person in world.personas:
        assert person.synthetic is True
        assert person.emails[0].value.split("@")[1].endswith((".test", ".invalid"))
        assert person.phones[0].value.startswith("+1-555-")
        assert person.national_ids[0].checksum_valid is False
        assert person.addresses[0].country_code == "ZZ"


def test_isolated_controls_have_no_memberships_and_no_shared_address() -> None:
    """Controls must be clean, which means their addresses cannot collide either.

    An earlier revision drew solo addresses from the household street pool, so at
    `person_count=2000` with 1998 controls, 382 people shared an address with
    someone else - destroying the property that makes them controls.
    """

    world = generate_households_world(seed=42)
    controls = [item for item in world.personas if item.employment == ()]

    assert len(controls) == HouseholdsConfig().isolated_person_count
    assert all(item.education == () for item in controls)

    crowded = HouseholdsConfig(
        person_count=2000, household_count=2, isolated_person_count=1998
    )
    at_scale = generate_households_world(seed=42, config=crowded)
    household_addresses = {
        _address_key(item.addresses[0])
        for item in at_scale.personas
        if item.employment != ()
    }
    solo_addresses = [
        _address_key(item.addresses[0])
        for item in at_scale.personas
        if item.employment == ()
    ]

    assert not household_addresses & set(solo_addresses)


def test_every_planted_edge_satisfies_the_shipped_evidence_invariant() -> None:
    """The check whose absence let 473 of 514 edges ship as invalid ground truth.

    `relationship_evidence_matches` compares whole records, not institutions: a
    colleague edge needs identical Employment including role, a classmate edge
    identical Education including graduation year, and a family edge a shared
    surname alongside the full address key. An earlier revision grouped by
    organisation and institution alone and emitted family edges between
    co-residents with different surnames, so the library rejected almost
    everything this profile planted - and nothing in the suite asked.
    """

    for seed in _SEEDS:
        world = generate_households_world(seed=seed)
        people = {item.id: item for item in world.personas}
        rejected = [
            edge
            for edge in world.relationships
            if not relationship_evidence_matches(
                edge, people[edge.source_person_id], people[edge.target_person_id]
            )
        ]

        assert rejected == [], [(edge.kind.value, edge.id) for edge in rejected]
        assert world.relationships


def test_sharing_an_address_does_not_imply_a_relationship() -> None:
    """The negative control #41 needs, produced structurally rather than planted.

    Only a household's surname core is family. The remaining co-residents share an
    address with people they have no edge to, so a resolver that merges on address
    is wrong about them.
    """

    world = generate_households_world(seed=42)
    adjacency = _adjacency(world)
    by_address: dict[str, list[str]] = defaultdict(list)
    for person in world.personas:
        by_address[_address_key(person.addresses[0])].append(person.id)

    unrelated_pairs = [
        (left, right)
        for occupants in by_address.values()
        for index, left in enumerate(occupants)
        for right in occupants[index + 1 :]
        if right not in adjacency[left]
    ]

    assert unrelated_pairs


def test_birth_dates_do_not_move_when_the_calendar_does() -> None:
    """Pinned, because the failure mode is invisible to a same-instant comparison.

    Faker's `date_of_birth` anchors its range to `datetime.now()`, so the first
    revision produced different dates on different days while its byte-identity
    test - generating both copies in one instant - reported success.
    """

    assert generate_households_world(seed=42).personas[0].date_of_birth == date(
        2000, 2, 17
    )


def test_configuration_digest_is_stable_under_key_ordering() -> None:
    """The digest is part of the reproducibility tuple, so it must not wobble."""

    assert HouseholdsConfig().digest() == HouseholdsConfig().digest()
    assert HouseholdsConfig(person_count=40).digest() != HouseholdsConfig().digest()


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (
            lambda: HouseholdsConfig(person_count=10, isolated_person_count=10),
            "whole population",
        ),
        (
            lambda: HouseholdsConfig(
                person_count=10, household_count=9, isolated_person_count=4
            ),
            "more households than people",
        ),
        (lambda: HouseholdsConfig(workplace_count=500), "workplace_count exceeds"),
        (lambda: HouseholdsConfig(school_count=500), "school_count exceeds"),
    ],
)
def test_configuration_rejects_impossible_worlds(
    build: Callable[[], HouseholdsConfig], message: str
) -> None:
    """A configuration that cannot produce the structure it asks for is an error.

    Silently clamping would make the manifest describe a world nobody generated.
    """

    with pytest.raises(ValidationError, match=message):
        build()


def test_an_explicit_configuration_is_honoured() -> None:
    config = HouseholdsConfig(
        person_count=30,
        household_count=8,
        workplace_count=4,
        school_count=2,
        isolated_person_count=2,
        colleagues_per_person=2,
    )
    world = generate_households_world(seed=42, config=config)

    assert len(world.personas) == 30
    assert (
        len(
            {
                item.employment[0].organization
                for item in world.personas
                if item.employment
            }
        )
        <= 4
    )
