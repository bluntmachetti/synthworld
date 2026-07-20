from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from uuid import UUID, uuid5

from synthworld.connection import (
    AdversarialCase,
    AdversarialPackKind,
    ConnectionAnswerKey,
    ConnectionBenchmark,
    PublicAssociationKind,
    PublicAssociationRecord,
    PublicConnectionCorpus,
    PublicIdentityAttribute,
    PublicIdentityAttributeKind,
    PublicIdentityRecord,
    PublicIdentitySourceType,
    PublicRelationshipTruth,
    PublicTruthRelationshipKind,
    RecordMembership,
    UnilateralAssociationControl,
)
from synthworld.generator import generate_world
from synthworld.models import Address, Persona, RelationshipKind

_CONNECTION_NAMESPACE = UUID("87de1b4b-cb17-54ea-b7a8-64afc75f162d")


@dataclass(frozen=True)
class _RecordDraft:
    pack: AdversarialPackKind
    entity_number: int
    display_name: str
    source_type: PublicIdentitySourceType
    attributes: tuple[PublicIdentityAttribute, ...]


def generate_adversarial_connection_benchmark(*, seed: int) -> ConnectionBenchmark:
    """Generate the frozen tiny-set entity-resolution input benchmark."""

    drafts = _adversarial_drafts()
    records = tuple(
        _identity_record(
            seed=seed,
            key=f"adversarial:{index}",
            source_type=draft.source_type,
            display_name=draft.display_name,
            attributes=draft.attributes,
        )
        for index, draft in enumerate(drafts, start=1)
    )
    memberships = tuple(
        RecordMembership(
            record_id=record.id,
            entity_id=f"entity-{draft.entity_number:04d}",
        )
        for record, draft in zip(records, drafts, strict=True)
    )
    cases = tuple(
        AdversarialCase(
            pack=pack,
            record_ids=tuple(
                record.id
                for record, draft in zip(records, drafts, strict=True)
                if draft.pack is pack
            ),
            entity_ids=tuple(
                {
                    f"entity-{draft.entity_number:04d}"
                    for draft in drafts
                    if draft.pack is pack
                }
            ),
        )
        for pack in AdversarialPackKind
    )
    return ConnectionBenchmark(
        seed=seed,
        public=PublicConnectionCorpus(
            seed=seed,
            identity_records=records,
            association_records=(),
        ),
        answer_key=ConnectionAnswerKey(
            record_memberships=memberships,
            adversarial_cases=cases,
            relationships=(),
            unilateral_controls=(),
        ),
    )


def generate_relationship_connection_benchmark(
    *,
    seed: int,
    persona_count: int,
) -> ConnectionBenchmark:
    """Derive public relationship evidence and its physically separate truth."""

    if persona_count < 3:
        raise ValueError("public connection corpora require at least 3 personas")
    world = generate_world(seed=seed, persona_count=persona_count)
    records_by_persona = {
        persona.id: _world_identity_record(seed=seed, persona=persona)
        for persona in world.personas
    }
    records = tuple(records_by_persona[persona.id] for persona in world.personas)
    associations: list[PublicAssociationRecord] = []
    relationships: list[PublicRelationshipTruth] = []

    for edge in world.relationships:
        if edge.kind not in {RelationshipKind.NEIGHBOR, RelationshipKind.SOCIAL}:
            continue
        source = next(
            persona for persona in world.personas if persona.id == edge.source_person_id
        )
        target = next(
            persona for persona in world.personas if persona.id == edge.target_person_id
        )
        association_kind, truth_kind, source_reference, target_reference = (
            _relationship_references(
                seed=seed, source=source, target=target, kind=edge.kind
            )
        )
        forward = _association_record(
            seed=seed,
            key=f"{edge.id}:forward",
            kind=association_kind,
            source_reference=source_reference,
            target_reference=target_reference,
        )
        reverse = _association_record(
            seed=seed,
            key=f"{edge.id}:reverse",
            kind=association_kind,
            source_reference=target_reference,
            target_reference=source_reference,
        )
        associations.extend((forward, reverse))
        source_record_id, target_record_id = _ordered_ids(
            records_by_persona[source.id].id,
            records_by_persona[target.id].id,
        )
        relationships.append(
            PublicRelationshipTruth(
                source_record_id=source_record_id,
                target_record_id=target_record_id,
                kind=truth_kind,
                reciprocal_association_ids=(forward.id, reverse.id),
            )
        )

    edge_pairs = {
        frozenset((edge.source_person_id, edge.target_person_id))
        for edge in world.relationships
    }
    control_pairs = tuple(
        (source, target)
        for source, target in combinations(world.personas, 2)
        if frozenset((source.id, target.id)) not in edge_pairs
    )
    address_counts = {
        reference: sum(
            _address_reference(persona.addresses[0]) == reference
            for persona in world.personas
        )
        for reference in {
            _address_reference(persona.addresses[0]) for persona in world.personas
        }
    }
    property_source, property_target = next(
        (
            (source, target)
            for source, target in control_pairs
            if address_counts[_address_reference(source.addresses[0])] == 1
            and address_counts[_address_reference(target.addresses[0])] == 1
        ),
        control_pairs[0],
    )
    profile_source, profile_target = control_pairs[0]
    property_control = _association_record(
        seed=seed,
        key="unilateral:property",
        kind=PublicAssociationKind.PROPERTY_ADJACENCY,
        source_reference=_address_reference(property_source.addresses[0]),
        target_reference=_address_reference(property_target.addresses[0]),
    )
    profile_control = _association_record(
        seed=seed,
        key="unilateral:profile",
        kind=PublicAssociationKind.PROFILE_LINK,
        source_reference=_profile_reference(seed, profile_source),
        target_reference=_profile_reference(seed, profile_target),
    )
    associations.extend((property_control, profile_control))
    controls = (
        UnilateralAssociationControl(
            association_id=property_control.id,
            kind=property_control.kind,
        ),
        UnilateralAssociationControl(
            association_id=profile_control.id,
            kind=profile_control.kind,
        ),
    )
    return ConnectionBenchmark(
        seed=seed,
        public=PublicConnectionCorpus(
            seed=seed,
            identity_records=records,
            association_records=tuple(associations),
        ),
        answer_key=ConnectionAnswerKey(
            record_memberships=tuple(
                RecordMembership(record_id=record.id, entity_id=persona.id)
                for persona, record in zip(world.personas, records, strict=True)
            ),
            adversarial_cases=(),
            relationships=tuple(relationships),
            unilateral_controls=controls,
        ),
    )


def generate_public_relationship_connection_corpus(
    *,
    seed: int,
    persona_count: int,
) -> PublicConnectionCorpus:
    """Generate only the product-safe relationship evidence projection."""

    return generate_relationship_connection_benchmark(
        seed=seed,
        persona_count=persona_count,
    ).public


def _world_identity_record(*, seed: int, persona: Persona) -> PublicIdentityRecord:
    education = persona.education[0]
    return _identity_record(
        seed=seed,
        key=f"world:{persona.id}",
        source_type=PublicIdentitySourceType.DIRECTORY,
        display_name=f"{persona.given_name} {persona.family_name}",
        attributes=(
            _attribute(PublicIdentityAttributeKind.EMAIL, persona.emails[0].value),
            _attribute(
                PublicIdentityAttributeKind.FAMILY_NAME,
                persona.family_name,
            ),
            _attribute(
                PublicIdentityAttributeKind.USERNAME,
                persona.usernames[0].value,
            ),
            _attribute(PublicIdentityAttributeKind.PHONE, persona.phones[0].value),
            _attribute(
                PublicIdentityAttributeKind.FULL_ADDRESS,
                _address_reference(persona.addresses[0]),
            ),
            _attribute(
                PublicIdentityAttributeKind.DATE_OF_BIRTH,
                persona.date_of_birth.isoformat(),
            ),
            _attribute(
                PublicIdentityAttributeKind.EMPLOYER,
                persona.employment[0].organization,
            ),
            _attribute(
                PublicIdentityAttributeKind.SCHOOL_YEAR,
                f"{education.institution}|{education.graduation_year}",
            ),
            _attribute(
                PublicIdentityAttributeKind.SOCIAL_PROFILE,
                _profile_reference(seed, persona),
            ),
        ),
    )


def _relationship_references(
    *,
    seed: int,
    source: Persona,
    target: Persona,
    kind: RelationshipKind,
) -> tuple[PublicAssociationKind, PublicTruthRelationshipKind, str, str]:
    if kind is RelationshipKind.NEIGHBOR:
        return (
            PublicAssociationKind.PROPERTY_ADJACENCY,
            PublicTruthRelationshipKind.NEIGHBOR,
            _address_reference(source.addresses[0]),
            _address_reference(target.addresses[0]),
        )
    return (
        PublicAssociationKind.PROFILE_LINK,
        PublicTruthRelationshipKind.SOCIAL,
        _profile_reference(seed, source),
        _profile_reference(seed, target),
    )


def _identity_record(
    *,
    seed: int,
    key: str,
    source_type: PublicIdentitySourceType,
    display_name: str,
    attributes: tuple[PublicIdentityAttribute, ...],
) -> PublicIdentityRecord:
    record_id = _opaque_id(seed, f"identity:{key}")
    return PublicIdentityRecord(
        id=record_id,
        source_type=source_type,
        source_url=f"https://records.example.test/identity/{record_id}",
        display_name=display_name,
        confidence=1.0,
        attributes=attributes,
    )


def _association_record(
    *,
    seed: int,
    key: str,
    kind: PublicAssociationKind,
    source_reference: str,
    target_reference: str,
) -> PublicAssociationRecord:
    record_id = _opaque_id(seed, f"association:{key}")
    return PublicAssociationRecord(
        id=record_id,
        kind=kind,
        source_url=f"https://associations.example.test/records/{record_id}",
        source_reference=source_reference,
        target_reference=target_reference,
        confidence=1.0,
    )


def _profile_reference(seed: int, persona: Persona) -> str:
    profile_id = _opaque_id(seed, f"profile:{persona.id}")
    return f"https://social.example.test/profiles/{profile_id}"


def _address_reference(address: Address) -> str:
    return "|".join(
        (
            str(address.house_number),
            address.street_name,
            address.city,
            address.postal_code,
            address.country_code,
        )
    )


def _opaque_id(seed: int, key: str) -> UUID:
    return uuid5(_CONNECTION_NAMESPACE, f"{seed}:{key}")


def _ordered_ids(first: UUID, second: UUID) -> tuple[UUID, UUID]:
    return (first, second) if first.int < second.int else (second, first)


def _attribute(
    kind: PublicIdentityAttributeKind,
    value: str,
) -> PublicIdentityAttribute:
    return PublicIdentityAttribute(kind=kind, value=value, confidence=1.0)


def _adversarial_drafts() -> tuple[_RecordDraft, ...]:
    common_one = (
        _attribute(PublicIdentityAttributeKind.EMAIL, "jordan.atlas@example.test"),
        _attribute(PublicIdentityAttributeKind.EMPLOYER, "Example Atlas Works"),
        _attribute(PublicIdentityAttributeKind.FULL_ADDRESS, _safe_address(101)),
    )
    common_two = (
        _attribute(PublicIdentityAttributeKind.EMAIL, "jordan.birch@example.test"),
        _attribute(PublicIdentityAttributeKind.EMPLOYER, "Example Birch Works"),
        _attribute(PublicIdentityAttributeKind.FULL_ADDRESS, _safe_address(202)),
    )
    unicode_positive = (
        _attribute(PublicIdentityAttributeKind.EMPLOYER, "Example Gamma Works"),
        _attribute(PublicIdentityAttributeKind.FULL_ADDRESS, _safe_address(303)),
    )
    twin_address = _safe_address(505)
    maiden_address = _safe_address(606)
    alias_address = _safe_address(707)
    return (
        _draft(
            AdversarialPackKind.COMMON_NAME,
            1,
            "Jordan Smith",
            PublicIdentitySourceType.DIRECTORY,
            common_one,
        ),
        _draft(
            AdversarialPackKind.COMMON_NAME,
            1,
            "Jordan Smith",
            PublicIdentitySourceType.CONFERENCE,
            (
                *common_one[1:],
                _attribute(PublicIdentityAttributeKind.USERNAME, "synth_jordan_atlas"),
            ),
        ),
        _draft(
            AdversarialPackKind.COMMON_NAME,
            2,
            "Jordan Smith",
            PublicIdentitySourceType.DIRECTORY,
            common_two,
        ),
        _draft(
            AdversarialPackKind.COMMON_NAME,
            2,
            "Jordan Smith",
            PublicIdentitySourceType.CONFERENCE,
            (
                *common_two[1:],
                _attribute(PublicIdentityAttributeKind.USERNAME, "synth_jordan_birch"),
            ),
        ),
        _draft(
            AdversarialPackKind.UNICODE_DIACRITICS,
            3,
            "Zoë García",
            PublicIdentitySourceType.ALUMNI,
            unicode_positive,
        ),
        _draft(
            AdversarialPackKind.UNICODE_DIACRITICS,
            3,
            "Zoe Garcia",
            PublicIdentitySourceType.CONFERENCE,
            unicode_positive,
        ),
        _draft(
            AdversarialPackKind.UNICODE_DIACRITICS,
            4,
            "Zoe Garcia",
            PublicIdentitySourceType.DIRECTORY,
            (
                _attribute(PublicIdentityAttributeKind.EMAIL, "zoe.delta@example.test"),
                _attribute(PublicIdentityAttributeKind.EMPLOYER, "Example Delta Works"),
                _attribute(
                    PublicIdentityAttributeKind.FULL_ADDRESS, _safe_address(404)
                ),
            ),
        ),
        _draft(
            AdversarialPackKind.TWINS_SHARED_ADDRESS,
            5,
            "Lina Mercer",
            PublicIdentitySourceType.DIRECTORY,
            (
                _attribute(
                    PublicIdentityAttributeKind.EMAIL, "lina.mercer@example.test"
                ),
                _attribute(PublicIdentityAttributeKind.FULL_ADDRESS, twin_address),
                _attribute(PublicIdentityAttributeKind.DATE_OF_BIRTH, "2000-01-01"),
            ),
        ),
        _draft(
            AdversarialPackKind.TWINS_SHARED_ADDRESS,
            5,
            "Lina Mercer",
            PublicIdentitySourceType.BROKER,
            (
                _attribute(
                    PublicIdentityAttributeKind.EMAIL, "lina.mercer@example.test"
                ),
                _attribute(PublicIdentityAttributeKind.FULL_ADDRESS, twin_address),
            ),
        ),
        _draft(
            AdversarialPackKind.TWINS_SHARED_ADDRESS,
            6,
            "Mina Mercer",
            PublicIdentitySourceType.DIRECTORY,
            (
                _attribute(
                    PublicIdentityAttributeKind.EMAIL, "mina.mercer@example.test"
                ),
                _attribute(PublicIdentityAttributeKind.FULL_ADDRESS, twin_address),
                _attribute(PublicIdentityAttributeKind.DATE_OF_BIRTH, "2000-01-01"),
            ),
        ),
        _draft(
            AdversarialPackKind.TWINS_SHARED_ADDRESS,
            6,
            "Mina Mercer",
            PublicIdentitySourceType.BROKER,
            (
                _attribute(
                    PublicIdentityAttributeKind.EMAIL, "mina.mercer@example.test"
                ),
                _attribute(PublicIdentityAttributeKind.FULL_ADDRESS, twin_address),
            ),
        ),
        _draft(
            AdversarialPackKind.MAIDEN_NAME,
            7,
            "Amina Okafor",
            PublicIdentitySourceType.DIRECTORY,
            (
                _attribute(PublicIdentityAttributeKind.PHONE, "+1-212-555-0101"),
                _attribute(
                    PublicIdentityAttributeKind.EMPLOYER, "Example Harbor Works"
                ),
                _attribute(PublicIdentityAttributeKind.FULL_ADDRESS, maiden_address),
            ),
        ),
        _draft(
            AdversarialPackKind.MAIDEN_NAME,
            7,
            "Amina Mensah",
            PublicIdentitySourceType.ALUMNI,
            (
                _attribute(PublicIdentityAttributeKind.PHONE, "+1-212-555-0101"),
                _attribute(
                    PublicIdentityAttributeKind.EMPLOYER, "Example Harbor Works"
                ),
            ),
        ),
        _draft(
            AdversarialPackKind.MAIDEN_NAME,
            8,
            "Amina Mensah",
            PublicIdentitySourceType.DIRECTORY,
            (
                _attribute(PublicIdentityAttributeKind.PHONE, "+1-212-555-0102"),
                _attribute(
                    PublicIdentityAttributeKind.EMPLOYER, "Example Indigo Works"
                ),
                _attribute(PublicIdentityAttributeKind.FULL_ADDRESS, maiden_address),
            ),
        ),
        _draft(
            AdversarialPackKind.MISSPELLING_ALIAS,
            9,
            "Katherine O'Connor",
            PublicIdentitySourceType.SOCIAL,
            (
                _attribute(PublicIdentityAttributeKind.USERNAME, "synth_koconnor"),
                _attribute(
                    PublicIdentityAttributeKind.EMPLOYER, "Example Lantern Works"
                ),
                _attribute(PublicIdentityAttributeKind.FULL_ADDRESS, alias_address),
            ),
        ),
        _draft(
            AdversarialPackKind.MISSPELLING_ALIAS,
            9,
            "Katie Oconnor",
            PublicIdentitySourceType.DIRECTORY,
            (
                _attribute(PublicIdentityAttributeKind.USERNAME, "synth_koconnor"),
                _attribute(PublicIdentityAttributeKind.FULL_ADDRESS, alias_address),
            ),
        ),
        _draft(
            AdversarialPackKind.MISSPELLING_ALIAS,
            9,
            "Katherin Oconor",
            PublicIdentitySourceType.CONFERENCE,
            (
                _attribute(
                    PublicIdentityAttributeKind.EMPLOYER, "Example Lantern Works"
                ),
                _attribute(PublicIdentityAttributeKind.FULL_ADDRESS, alias_address),
            ),
        ),
        _draft(
            AdversarialPackKind.MISSPELLING_ALIAS,
            10,
            "Kathryn O'Connor",
            PublicIdentitySourceType.CONFERENCE,
            (
                _attribute(
                    PublicIdentityAttributeKind.EMPLOYER, "Example Lantern Works"
                ),
                _attribute(
                    PublicIdentityAttributeKind.FULL_ADDRESS, _safe_address(808)
                ),
            ),
        ),
    )


def _draft(
    pack: AdversarialPackKind,
    entity_number: int,
    display_name: str,
    source_type: PublicIdentitySourceType,
    attributes: tuple[PublicIdentityAttribute, ...],
) -> _RecordDraft:
    return _RecordDraft(pack, entity_number, display_name, source_type, attributes)


def _safe_address(house_number: int) -> str:
    return f"{house_number}|Adversarial Example Avenue|Testville|00000|ZZ"


__all__ = [
    "generate_adversarial_connection_benchmark",
    "generate_public_relationship_connection_corpus",
    "generate_relationship_connection_benchmark",
]
