from __future__ import annotations

import os
import subprocess
import sys
from collections import defaultdict, deque
from pathlib import Path

import pytest

from synthworld import RelationshipKind, generate_world, world_to_json

TRANCHE_SEED = 20_260_719


def test_generation_is_byte_deterministic_for_a_fixed_seed() -> None:
    first = world_to_json(generate_world(seed=TRANCHE_SEED, persona_count=10))
    second = world_to_json(generate_world(seed=TRANCHE_SEED, persona_count=10))

    assert first == second


def test_generation_is_byte_deterministic_across_host_timezones() -> None:
    project_root = Path(__file__).parents[1]
    command = (
        "from synthworld import generate_world, world_to_json; "
        "print(world_to_json(generate_world(seed=20260719, persona_count=10)))"
    )
    outputs = []
    for timezone_name in ("UTC", "Europe/London", "America/New_York"):
        environment = os.environ.copy()
        environment["TZ"] = timezone_name
        result = subprocess.run(  # noqa: S603 - fixed interpreter and arguments
            [sys.executable, "-c", command],
            cwd=project_root,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        outputs.append(result.stdout)

    assert len(set(outputs)) == 1


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
