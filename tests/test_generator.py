from __future__ import annotations

from collections import defaultdict, deque

import pytest

from synthworld import RelationshipKind, generate_world, world_to_json

TRANCHE_SEED = 20_260_719


def test_generation_is_byte_deterministic_for_a_fixed_seed() -> None:
    first = world_to_json(generate_world(seed=TRANCHE_SEED, persona_count=10))
    second = world_to_json(generate_world(seed=TRANCHE_SEED, persona_count=10))

    assert first == second


def test_changing_the_seed_changes_the_serialized_world() -> None:
    first = world_to_json(generate_world(seed=TRANCHE_SEED, persona_count=10))
    second = world_to_json(generate_world(seed=TRANCHE_SEED + 1, persona_count=10))

    assert first != second


def test_generated_world_has_a_connected_labelled_relationship_graph() -> None:
    world = generate_world(seed=TRANCHE_SEED, persona_count=10)
    persona_ids = {persona.id for persona in world.personas}
    neighbors: dict[str, set[str]] = defaultdict(set)
    unordered_edges: set[frozenset[str]] = set()

    assert len(world.personas) == 10
    assert len(world.relationships) == 9
    assert {edge.kind for edge in world.relationships} == set(RelationshipKind)

    for edge in world.relationships:
        assert edge.source_person_id in persona_ids
        assert edge.target_person_id in persona_ids
        assert edge.source_person_id != edge.target_person_id
        assert edge.evidence
        pair = frozenset((edge.source_person_id, edge.target_person_id))
        assert pair not in unordered_edges
        unordered_edges.add(pair)
        neighbors[edge.source_person_id].add(edge.target_person_id)
        neighbors[edge.target_person_id].add(edge.source_person_id)

    visited = {world.personas[0].id}
    queue = deque(visited)
    while queue:
        current = queue.popleft()
        for neighbor in neighbors[current] - visited:
            visited.add(neighbor)
            queue.append(neighbor)

    assert visited == persona_ids


@pytest.mark.parametrize("persona_count", [0, 1, 1_001])
def test_persona_count_outside_supported_world_size_is_rejected(
    persona_count: int,
) -> None:
    with pytest.raises(ValueError, match="persona_count"):
        generate_world(seed=TRANCHE_SEED, persona_count=persona_count)
