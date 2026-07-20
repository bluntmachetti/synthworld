from __future__ import annotations

from synthworld import RelationshipKind, generate_world
from synthworld.metrics import relationship_evidence_matches


def test_every_relationship_label_agrees_with_persona_attributes() -> None:
    world = generate_world(seed=20_260_719, persona_count=10)
    personas = {persona.id: persona for persona in world.personas}

    for edge in world.relationships:
        assert relationship_evidence_matches(
            edge,
            personas[edge.source_person_id],
            personas[edge.target_person_id],
        ), edge.id


def test_relationship_types_plant_the_expected_shared_signals() -> None:
    world = generate_world(seed=20_260_719, persona_count=10)
    personas = {persona.id: persona for persona in world.personas}

    for edge in world.relationships:
        source = personas[edge.source_person_id]
        target = personas[edge.target_person_id]
        signals = {evidence.signal for evidence in edge.evidence}

        if edge.kind is RelationshipKind.FAMILY:
            assert source.family_name == target.family_name
            assert source.addresses[0] == target.addresses[0]
            assert signals == {"shared_surname", "shared_address"}
        elif edge.kind is RelationshipKind.COLLEAGUE:
            assert source.employment[0] == target.employment[0]
            assert signals == {"shared_employer"}
        elif edge.kind is RelationshipKind.CLASSMATE:
            assert source.education[0] == target.education[0]
            assert signals == {"shared_school_year"}
        elif edge.kind is RelationshipKind.NEIGHBOR:
            source_address = source.addresses[0]
            target_address = target.addresses[0]
            assert source_address.house_number != target_address.house_number
            assert source_address.street_name == target_address.street_name
            assert source_address.city == target_address.city
            assert source_address.postal_code == target_address.postal_code
            assert signals == {"shared_street"}
        else:
            assert edge.kind is RelationshipKind.SOCIAL
            assert signals == {"mutual_profile_link"}
