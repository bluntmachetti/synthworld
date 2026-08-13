from __future__ import annotations

import json
from copy import deepcopy

import pytest
from pydantic import ValidationError

from synthworld.agentic import generate_asteria_agentic_v1
from synthworld.explorer import (
    EVALUATOR_WATERMARK,
    ExplorerCoordinateV1,
    ExplorerEvaluatorAnnotationV1,
    ExplorerEvaluatorOverlayV1,
    ExplorerLayoutManifestV1,
    ExplorerLayoutOptionsV1,
    ExplorerNodeKind,
    ExplorerPropertyV1,
    ExplorerViewportV1,
    canonical_json_bytes,
    explorer_digest,
    project_asteria_agent_authority_v1,
)

_PUBLIC_DIGEST = "a" * 64


def _projection():  # type: ignore[no-untyped-def]
    return project_asteria_agent_authority_v1(
        generate_asteria_agentic_v1().public,
        public_artifact_set_digest=_PUBLIC_DIGEST,
    )


def test_asteria_projection_is_deterministic_public_and_answer_independent() -> None:
    projection = _projection()
    repeated = _projection()

    assert projection == repeated
    assert projection.visibility == "public"
    assert projection.source.benchmark_id == "asteria-agentic-v1"
    assert projection.source.lifecycle == "published"
    assert projection.source.public_artifact_set_digest == _PUBLIC_DIGEST
    assert tuple(node.id for node in projection.nodes) == tuple(
        sorted(node.id for node in projection.nodes)
    )
    assert tuple(edge.id for edge in projection.edges) == tuple(
        sorted(edge.id for edge in projection.edges)
    )
    assert tuple(event.source_event_index for event in projection.timeline) == tuple(
        range(1, len(projection.timeline) + 1)
    )
    assert set(ExplorerNodeKind) == {node.kind for node in projection.nodes}

    serialized = canonical_json_bytes(projection)
    parsed = json.loads(serialized)
    assert serialized.endswith(b"\n")
    assert serialized.count(b"\n") == 1
    assert parsed["visibility"] == "public"
    assert explorer_digest(projection) == explorer_digest(repeated)
    for forbidden in (
        b"authority_truth",
        b"canonical_binding",
        b"case_kind",
        b"expected_decision",
        b"failure_reason",
    ):
        assert forbidden not in serialized


def test_projection_exposes_public_authority_and_revocation_replay() -> None:
    projection = _projection()
    revocation = next(
        event
        for event in projection.timeline
        if event.kind == "delegation_revoked"
    )
    action = next(
        event for event in projection.timeline if event.kind == "action_attempted"
    )

    assert revocation.related_node_ids
    assert action.related_node_ids
    assert action.related_edge_ids
    action_node = next(
        node
        for node in projection.nodes
        if node.id in action.related_node_ids
        and node.kind == ExplorerNodeKind.ACTION_ATTEMPT
    )
    action_properties = {item.key: item.value for item in action_node.properties}
    assert action_properties["presented_credential_id"]
    assert "expected_decision" not in action_properties


def test_projection_contract_rejects_open_or_ambiguous_graphs() -> None:
    projection_data = _projection().model_dump(mode="json")
    mutations = []

    duplicate_node = deepcopy(projection_data)
    duplicate_node["nodes"].append(deepcopy(duplicate_node["nodes"][0]))
    mutations.append((duplicate_node, "node IDs"))

    unknown_parent = deepcopy(projection_data)
    unknown_parent["nodes"][0]["parent_node_id"] = "missing"
    mutations.append((unknown_parent, "unknown parent"))

    unknown_edge_node = deepcopy(projection_data)
    unknown_edge_node["edges"][0]["target_node_id"] = "missing"
    mutations.append((unknown_edge_node, "unknown node"))

    unknown_event_node = deepcopy(projection_data)
    unknown_event_node["timeline"][0]["related_node_ids"] = ["missing"]
    mutations.append((unknown_event_node, "event references an unknown node"))

    unknown_event_edge = deepcopy(projection_data)
    unknown_event_edge["timeline"][0]["related_edge_ids"] = ["missing"]
    mutations.append((unknown_event_edge, "event references an unknown edge"))

    repeated_index = deepcopy(projection_data)
    repeated_index["timeline"][1]["source_event_index"] = repeated_index["timeline"][
        0
    ]["source_event_index"]
    mutations.append((repeated_index, "indices must be strictly increasing"))

    repeated_time = deepcopy(projection_data)
    repeated_time["timeline"][1]["occurred_at"] = repeated_time["timeline"][0][
        "occurred_at"
    ]
    mutations.append((repeated_time, "times must be strictly increasing"))

    for mutation, message in mutations:
        with pytest.raises(ValidationError, match=message):
            projection.__class__.model_validate(mutation)


def test_properties_and_event_references_are_canonical_and_unique() -> None:
    projection = _projection()
    node = projection.nodes[0]
    ordered = node.__class__(
        **node.model_dump(exclude={"properties"}),
        properties=(
            ExplorerPropertyV1(key="z", value="last"),
            ExplorerPropertyV1(key="a", value="first"),
        ),
    )
    assert tuple(item.key for item in ordered.properties) == ("a", "z")

    with pytest.raises(ValidationError, match="property keys must be unique"):
        node.__class__(
            **node.model_dump(exclude={"properties"}),
            properties=(
                ExplorerPropertyV1(key="same", value="one"),
                ExplorerPropertyV1(key="same", value="two"),
            ),
        )
    with pytest.raises(ValidationError, match="nonblank"):
        ExplorerPropertyV1(key=" ", value="value")
    with pytest.raises(ValidationError, match="event references must be unique"):
        projection.timeline[0].__class__(
            **projection.timeline[0].model_dump(exclude={"related_node_ids"}),
            related_node_ids=(projection.nodes[0].id,) * 2,
        )


def test_evaluator_overlay_is_separate_watermarked_and_digest_bound() -> None:
    projection = _projection()
    annotation = ExplorerEvaluatorAnnotationV1(
        id="annotation-1",
        source_action_event_id="evt-004-authorised-action",
        target_id="evt-004-authorised-action",
        kind="authority_decision",
        label="Expected authority decision",
        value="allow",
    )
    overlay = ExplorerEvaluatorOverlayV1(
        public_projection_digest=explorer_digest(projection),
        evaluator_artifact_set_digest="b" * 64,
        annotations=(annotation,),
    )

    assert overlay.visibility == "evaluator"
    assert overlay.watermark == EVALUATOR_WATERMARK
    assert b"Expected authority decision" in canonical_json_bytes(overlay)
    with pytest.raises(ValidationError, match="annotation IDs must be unique"):
        ExplorerEvaluatorOverlayV1(
            public_projection_digest=explorer_digest(projection),
            evaluator_artifact_set_digest="b" * 64,
            annotations=(annotation, annotation),
        )


def test_layout_contract_pins_engine_viewport_precision_and_coordinates() -> None:
    projection = _projection()
    coordinates = tuple(
        ExplorerCoordinateV1(
            node_id=node.id,
            x=float(index),
            y=float(index * 2),
            width=180.0,
            height=56.0,
        )
        for index, node in enumerate(reversed(projection.nodes))
    )
    layout = ExplorerLayoutManifestV1(
        public_projection_digest=explorer_digest(projection),
        options=ExplorerLayoutOptionsV1(engine_version="0.9.3"),
        viewport=ExplorerViewportV1(width=1440, height=900),
        coordinates=coordinates,
    )

    assert tuple(item.node_id for item in layout.coordinates) == tuple(
        sorted(item.node_id for item in layout.coordinates)
    )
    assert layout.options.engine == "elk"
    assert layout.coordinate_precision == 3
    with pytest.raises(ValidationError, match="coordinates must be finite"):
        ExplorerCoordinateV1(
            node_id=projection.nodes[0].id,
            x=float("nan"),
            y=0.0,
            width=1.0,
            height=1.0,
        )
    with pytest.raises(ValidationError, match="layout node IDs must be unique"):
        ExplorerLayoutManifestV1(
            public_projection_digest=explorer_digest(projection),
            options=ExplorerLayoutOptionsV1(engine_version="0.9.3"),
            viewport=ExplorerViewportV1(width=1440, height=900),
            coordinates=(coordinates[0], coordinates[0]),
        )


def test_asteria_adapter_rejects_unpublished_world_identity() -> None:
    public = generate_asteria_agentic_v1().public
    altered = public.model_copy(
        update={
            "snapshot": public.snapshot.model_copy(update={"world_version": "2.0.0"})
        }
    )
    with pytest.raises(ValueError, match="only the published Asteria v1"):
        project_asteria_agent_authority_v1(
            altered,
            public_artifact_set_digest=_PUBLIC_DIGEST,
        )
