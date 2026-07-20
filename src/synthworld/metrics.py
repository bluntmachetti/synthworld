from __future__ import annotations

import re
from collections import defaultdict, deque
from collections.abc import Iterator

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
    SyntheticModel,
    SynthWorld,
    Username,
    WorldMetrics,
)

_PHONE_PATTERN = re.compile(r"^\+1-\d{3}-555-01\d{2}$")
_NATIONAL_ID_PATTERN = re.compile(r"^SYN-(\d{9})$")


def evaluate_world(world: SynthWorld) -> WorldMetrics:
    """Measure the safety and graph-ground-truth claims for a world."""

    records = tuple(_iter_records(world))
    safe_records = sum(_record_is_safely_fake(record) for record in records)
    personas = {persona.id: persona for persona in world.personas}
    matching_edges = sum(
        relationship_evidence_matches(
            edge,
            personas[edge.source_person_id],
            personas[edge.target_person_id],
        )
        for edge in world.relationships
        if edge.source_person_id in personas and edge.target_person_id in personas
    )

    return WorldMetrics(
        persona_count=len(world.personas),
        relationship_count=len(world.relationships),
        safely_fake_record_rate=_rate(safe_records, len(records)),
        relationship_evidence_integrity=_rate(
            matching_edges,
            len(world.relationships),
        ),
        graph_connected=_graph_is_connected(world),
    )


def relationship_evidence_matches(
    edge: RelationshipEdge,
    source: Persona,
    target: Persona,
) -> bool:
    """Check that a labelled edge is justified by its planted evidence."""

    observed = {item.signal: item.value for item in edge.evidence}
    if len(observed) != len(edge.evidence):
        return False

    if edge.kind is RelationshipKind.FAMILY:
        expected = {
            EvidenceSignal.SHARED_SURNAME: source.family_name,
            EvidenceSignal.SHARED_ADDRESS: _address_key(source.addresses[0]),
        }
        return (
            source.family_name == target.family_name
            and source.addresses[0] == target.addresses[0]
            and observed == expected
        )
    if edge.kind is RelationshipKind.COLLEAGUE:
        expected = {EvidenceSignal.SHARED_EMPLOYER: source.employment[0].organization}
        return source.employment[0] == target.employment[0] and observed == expected
    if edge.kind is RelationshipKind.CLASSMATE:
        education = source.education[0]
        expected = {
            EvidenceSignal.SHARED_SCHOOL_YEAR: (
                f"{education.institution}|{education.graduation_year}"
            )
        }
        return source.education[0] == target.education[0] and observed == expected
    if edge.kind is RelationshipKind.NEIGHBOR:
        source_address = source.addresses[0]
        target_address = target.addresses[0]
        expected = {EvidenceSignal.SHARED_STREET: _street_key(source_address)}
        return (
            source_address.house_number != target_address.house_number
            and _street_key(source_address) == _street_key(target_address)
            and observed == expected
        )

    expected = {
        EvidenceSignal.MUTUAL_PROFILE_LINK: (
            f"synth://profiles/{source.id}/{target.id}"
        )
    }
    return edge.kind is RelationshipKind.SOCIAL and observed == expected


def _iter_records(world: SynthWorld) -> Iterator[SyntheticModel]:
    yield world
    for persona in world.personas:
        yield persona
        yield from persona.emails
        yield from persona.usernames
        yield from persona.phones
        yield from persona.addresses
        yield from persona.employment
        yield from persona.education
        yield from persona.national_ids
    for edge in world.relationships:
        yield edge
        yield from edge.evidence


def _record_is_safely_fake(record: SyntheticModel) -> bool:
    if record.synthetic is not True:
        return False
    if isinstance(record, EmailAddress):
        return record.value.endswith("@example.test")
    if isinstance(record, Username):
        return record.value.startswith("synth_")
    if isinstance(record, PhoneNumber):
        return _PHONE_PATTERN.fullmatch(record.value) is not None
    if isinstance(record, Address):
        return (
            record.street_name.endswith("Example Avenue")
            and record.city == "Testville"
            and record.postal_code == "00000"
            and record.country_code == "ZZ"
        )
    if isinstance(record, Employment):
        return record.organization.startswith("Example Works ")
    if isinstance(record, Education):
        return record.institution.startswith("Test University ")
    if isinstance(record, NationalId):
        match = _NATIONAL_ID_PATTERN.fullmatch(record.value)
        return (
            match is not None
            and record.checksum_valid is False
            and not _luhn_valid(match.group(1))
        )
    if isinstance(record, RelationshipEvidence):
        return bool(record.value)
    return True


def _graph_is_connected(world: SynthWorld) -> bool:
    if not world.personas:
        return False
    persona_ids = {persona.id for persona in world.personas}
    neighbors: dict[str, set[str]] = defaultdict(set)
    for edge in world.relationships:
        if (
            edge.source_person_id not in persona_ids
            or edge.target_person_id not in persona_ids
        ):
            return False
        neighbors[edge.source_person_id].add(edge.target_person_id)
        neighbors[edge.target_person_id].add(edge.source_person_id)

    visited = {world.personas[0].id}
    queue = deque(visited)
    while queue:
        current = queue.popleft()
        for neighbor in neighbors[current] - visited:
            visited.add(neighbor)
            queue.append(neighbor)
    return visited == persona_ids


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


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
