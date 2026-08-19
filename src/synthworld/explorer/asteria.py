from __future__ import annotations

from synthworld.agentic.models import (
    ASTERIA_SEED,
    ASTERIA_WORLD_ID,
    ASTERIA_WORLD_VERSION,
    AgenticEvaluatorBundle,
    AgenticPublicBundle,
)
from synthworld.explorer.agentic_graph import (
    ProjectionBuilder,
    build_evaluator_annotations,
    project_events,
    project_snapshot,
)
from synthworld.explorer.models import (
    ExplorerEvaluatorOverlayV1,
    ExplorerNodeKind,
    ExplorerPublicProjectionV1,
    ExplorerSourceV1,
)


def project_asteria_agent_authority_evaluator_v1(
    projection: ExplorerPublicProjectionV1,
    evaluator: AgenticEvaluatorBundle,
    *,
    evaluator_artifact_set_digest: str,
) -> ExplorerEvaluatorOverlayV1:
    """Project Asteria evaluator truth without merging it into public records."""

    if (
        projection.source.world_id != evaluator.world_id
        or projection.source.world_schema_version != evaluator.world_version
        or projection.source.seed != evaluator.seed
    ):
        raise ValueError("Asteria evaluator identity does not match the projection")
    action_nodes = {
        node.source_id: node.id
        for node in projection.nodes
        if node.kind is ExplorerNodeKind.ACTION_ATTEMPT
    }
    annotations = build_evaluator_annotations(
        action_nodes, evaluator, subject="Asteria"
    )
    from synthworld.explorer.serialization import explorer_digest

    return ExplorerEvaluatorOverlayV1(
        public_projection_digest=explorer_digest(projection),
        evaluator_artifact_set_digest=evaluator_artifact_set_digest,
        annotations=annotations,
    )


def project_asteria_agent_authority_v1(
    public: AgenticPublicBundle,
    *,
    public_artifact_set_digest: str,
) -> ExplorerPublicProjectionV1:
    """Project the published Asteria v1 public package without evaluator truth."""

    snapshot = public.snapshot
    if (
        snapshot.world_id != ASTERIA_WORLD_ID
        or snapshot.world_version != ASTERIA_WORLD_VERSION
        or snapshot.seed != ASTERIA_SEED
    ):
        raise ValueError("Explorer v0.1 accepts only the published Asteria v1 world")
    builder = ProjectionBuilder()
    project_snapshot(builder, public)
    project_events(builder, public)
    return ExplorerPublicProjectionV1(
        source=ExplorerSourceV1(
            benchmark_id="asteria-agentic-v1",
            benchmark_version="1.0.0",
            world_id=snapshot.world_id,
            world_schema_version=snapshot.schema_version,
            seed=snapshot.seed,
            public_artifact_set_digest=public_artifact_set_digest,
        ),
        nodes=tuple(builder.nodes),
        edges=tuple(builder.edges),
        timeline=tuple(builder.timeline),
    )
