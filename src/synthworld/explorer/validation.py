from __future__ import annotations

from synthworld.explorer.models import (
    ExplorerEvaluatorOverlayV1,
    ExplorerLayoutManifestV1,
    ExplorerPublicProjectionV1,
    ExplorerTimelineEventKind,
)
from synthworld.explorer.serialization import explorer_digest


def validate_evaluator_overlay(
    projection: ExplorerPublicProjectionV1,
    overlay: ExplorerEvaluatorOverlayV1,
) -> None:
    """Validate evaluator bindings without merging truth into public data."""

    if overlay.public_projection_digest != explorer_digest(projection):
        raise ValueError("Evaluator overlay does not bind this public projection")
    action_event_ids = {
        event.source_event_id
        for event in projection.timeline
        if event.kind == ExplorerTimelineEventKind.ACTION_ATTEMPTED
    }
    target_ids = (
        {node.id for node in projection.nodes}
        | {edge.id for edge in projection.edges}
        | {event.source_event_id for event in projection.timeline}
    )
    for annotation in overlay.annotations:
        if annotation.source_action_event_id not in action_event_ids:
            raise ValueError("Evaluator annotation references an unknown action event")
        if annotation.target_id not in target_ids:
            raise ValueError("Evaluator annotation references an unknown target")


def validate_layout_manifest(
    projection: ExplorerPublicProjectionV1,
    layout: ExplorerLayoutManifestV1,
) -> None:
    """Require one coordinate for every node in the bound public projection."""

    if layout.public_projection_digest != explorer_digest(projection):
        raise ValueError("Layout manifest does not bind this public projection")
    projection_node_ids = {node.id for node in projection.nodes}
    coordinate_node_ids = {item.node_id for item in layout.coordinates}
    if coordinate_node_ids != projection_node_ids:
        raise ValueError("Layout coordinates must cover exactly the projection nodes")
