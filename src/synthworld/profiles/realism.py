"""Realism and leakage metrics for generated profiles, derived from artifacts.

Issue #43 asks for these to be "calculated from artifacts rather than echoed from
configuration", and the distinction is the whole point. A metric read back from the
configuration that requested it reports what was asked for, not what was produced,
so it agrees with the manifest no matter what the generator did. This module is
therefore given a :class:`~synthworld.models.SynthWorld` and nothing else - it
cannot see the configuration, so it cannot echo it.

The same reasoning already appears in ``tests/test_design_intent_coverage_table.py``,
which refuses to import the renderer it checks so that the read path cannot collapse
into the write path.

:func:`validate_realism` is the gate. It takes the measured report and the declared
minimums separately and compares them, which is the one place the two meet.
"""

from __future__ import annotations

import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping

from synthworld.leakage import FieldRecoverability, world_recoverability
from synthworld.models import Address, Persona, SyntheticModel, SynthWorld


class RealismReport(SyntheticModel):
    """What a generated world actually contains."""

    person_count: int
    edge_count: int
    component_count: int
    #: Descending, so the first entry is the largest component. A single giant
    #: component beside singletons is the shape issue #43 rejects.
    component_sizes: tuple[int, ...]
    isolated_person_count: int
    cycle_rank: int
    distinct_degrees: int
    max_degree: int
    household_sizes: tuple[int, ...]
    workplace_sizes: tuple[int, ...]
    school_sizes: tuple[int, ...]
    #: People whose normalised name is shared with someone else. Collisions are
    #: wanted - they are what makes resolution non-trivial - but they must be
    #: measured rather than assumed.
    normalised_name_collisions: int
    shared_address_people: int
    distinct_email_domains: int
    non_ascii_name_people: int
    #: Issue #43 asks for missing and multi-valued attribute prevalence, so sparse
    #: personas are expected input rather than an edge case. `Persona` puts no
    #: minimum length on any of these tuples, and an earlier revision indexed [0]
    #: unconditionally - it raised IndexError on a model-valid world instead of
    #: measuring it.
    missing_attribute_people: Mapping[str, int]
    multi_valued_attribute_people: Mapping[str, int]
    leakage: tuple[FieldRecoverability, ...]


class RealismMinimums(SyntheticModel):
    """Declared floors. Compared against a report, never used to compute one."""

    min_component_count: int = 4
    #: A component holding most of the population makes structure uninformative,
    #: which is precisely the defect measured in the frozen core profile.
    max_largest_component_fraction: float = 0.6
    min_distinct_degrees: int = 5
    min_household_sizes: int = 2
    require_no_leaking_field: bool = True


class RealismError(ValueError):
    """Raised when a generated world does not meet its declared minimums."""


def _address_key(address: Address) -> str:
    return "|".join(
        (
            str(address.house_number),
            address.street_name,
            address.city,
            address.postal_code,
        )
    )


def _primary_email(person: Persona) -> str:
    return person.emails[0].value


def _normalised_name(person: Persona) -> str:
    combined = f"{person.given_name} {person.family_name}".casefold()
    stripped = unicodedata.normalize("NFKD", combined)
    return "".join(item for item in stripped if not unicodedata.combining(item))


def _component_sizes(world: SynthWorld) -> tuple[int, ...]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in world.relationships:
        adjacency[edge.source_person_id].add(edge.target_person_id)
        adjacency[edge.target_person_id].add(edge.source_person_id)
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
    return tuple(sorted(sizes, reverse=True))


def _group_sizes(values: Iterable[str]) -> tuple[int, ...]:
    return tuple(sorted(Counter(values).values()))


_COUNTED_ATTRIBUTES = (
    "addresses",
    "emails",
    "usernames",
    "phones",
    "national_ids",
    "employment",
    "education",
)


def measure_realism(world: SynthWorld) -> RealismReport:
    """Measure a world. Takes no configuration, so it cannot echo one."""

    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in world.relationships:
        adjacency[edge.source_person_id].add(edge.target_person_id)
        adjacency[edge.target_person_id].add(edge.source_person_id)

    degrees = Counter(len(adjacency[item.id]) for item in world.personas)
    sizes = _component_sizes(world)
    names = Counter(_normalised_name(item) for item in world.personas)
    address_keys = [
        _address_key(item.addresses[0]) for item in world.personas if item.addresses
    ]
    addresses = Counter(address_keys)

    def field(name: str, project: Callable[[Persona], str]) -> list[str]:
        return [project(item) for item in world.personas if getattr(item, name)]

    return RealismReport(
        person_count=len(world.personas),
        edge_count=len(world.relationships),
        component_count=len(sizes),
        component_sizes=sizes,
        isolated_person_count=degrees[0],
        cycle_rank=len(world.relationships) - len(world.personas) + len(sizes),
        distinct_degrees=len(degrees),
        max_degree=max(degrees) if degrees else 0,
        household_sizes=_group_sizes(address_keys),
        workplace_sizes=_group_sizes(
            item.employment[0].organization
            for item in world.personas
            if item.employment
        ),
        school_sizes=_group_sizes(
            item.education[0].institution for item in world.personas if item.education
        ),
        normalised_name_collisions=sum(count for count in names.values() if count > 1),
        shared_address_people=sum(count for count in addresses.values() if count > 1),
        distinct_email_domains=len(
            {value.split("@")[-1] for value in field("emails", _primary_email)}
        ),
        missing_attribute_people={
            name: sum(1 for item in world.personas if not getattr(item, name))
            for name in _COUNTED_ATTRIBUTES
        },
        multi_valued_attribute_people={
            name: sum(1 for item in world.personas if len(getattr(item, name)) > 1)
            for name in _COUNTED_ATTRIBUTES
        },
        non_ascii_name_people=sum(
            1
            for item in world.personas
            if not f"{item.given_name}{item.family_name}".isascii()
        ),
        # Leakage is scored only over personas that carry the field. A shorter
        # sequence measures fewer people; a placeholder would invent a constant and
        # read as structure nobody generated.
        leakage=world_recoverability(
            {
                "email": field("emails", _primary_email),
                "username": field("usernames", lambda item: item.usernames[0].value),
                "phone": field("phones", lambda item: item.phones[0].value),
                "national_id": field(
                    "national_ids", lambda item: item.national_ids[0].value
                ),
                "date_of_birth": [
                    item.date_of_birth.isoformat() for item in world.personas
                ],
                "address": address_keys,
            }
        ),
    )


def validate_realism(report: RealismReport, minimums: RealismMinimums) -> None:
    """Raise when a measured world falls short of what was declared."""

    failures: list[str] = []
    if report.component_count < minimums.min_component_count:
        failures.append(
            f"component_count {report.component_count} < {minimums.min_component_count}"
        )
    if report.component_sizes and report.person_count:
        fraction = report.component_sizes[0] / report.person_count
        if fraction > minimums.max_largest_component_fraction:
            failures.append(
                f"largest component holds {fraction:.2f} of the population, "
                f"above {minimums.max_largest_component_fraction}"
            )
    if report.distinct_degrees < minimums.min_distinct_degrees:
        failures.append(
            f"distinct_degrees {report.distinct_degrees} < "
            f"{minimums.min_distinct_degrees}"
        )
    if len(report.household_sizes) < minimums.min_household_sizes:
        failures.append("too few distinct addresses to form households")
    if minimums.require_no_leaking_field:
        leaking = [item.field for item in report.leakage if item.verdict == "leaking"]
        if leaking:
            failures.append(f"fields leak the generation index: {sorted(leaking)}")
    if failures:
        raise RealismError("; ".join(failures))


__all__ = [
    "RealismError",
    "RealismMinimums",
    "RealismReport",
    "measure_realism",
    "validate_realism",
]
