from __future__ import annotations

from synthworld import RelationshipKind, evaluate_world, generate_world


def test_ground_truth_metrics_are_perfect() -> None:
    metrics = evaluate_world(generate_world(seed=20_260_719, persona_count=10))

    assert metrics.safely_fake_record_rate == 1.0
    assert metrics.relationship_evidence_integrity == 1.0
    assert metrics.graph_connected is True
    assert metrics.persona_count == 10
    assert metrics.relationship_count == 9


def test_metrics_detect_tampered_safety_and_duplicate_evidence() -> None:
    world = generate_world(seed=20_260_719, persona_count=10)
    first_edge = world.relationships[0]
    assert first_edge.kind is RelationshipKind.FAMILY
    duplicate_evidence = first_edge.model_copy(
        update={"evidence": (*first_edge.evidence, first_edge.evidence[0])}
    )
    tampered_world = world.model_copy(
        update={
            "synthetic": False,
            "relationships": (duplicate_evidence, *world.relationships[1:]),
        }
    )

    metrics = evaluate_world(tampered_world)

    assert metrics.safely_fake_record_rate < 1.0
    assert metrics.relationship_evidence_integrity < 1.0


def test_metrics_detect_empty_and_dangling_graphs() -> None:
    world = generate_world(seed=20_260_719, persona_count=10)
    empty_world = world.model_copy(update={"personas": (), "relationships": ()})
    dangling_edge = world.relationships[0].model_copy(
        update={"target_person_id": "persona-missing"}
    )
    dangling_world = world.model_copy(
        update={"relationships": (dangling_edge, *world.relationships[1:])}
    )

    assert evaluate_world(empty_world).graph_connected is False
    assert evaluate_world(dangling_world).graph_connected is False
