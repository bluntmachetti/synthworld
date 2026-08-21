"""Explorer adapter for released generated enterprise-agentic packages."""

from __future__ import annotations

from typing import Final

from synthworld.agentic.enterprise.generated_models import (
    ENTERPRISE_AGENTIC_CANONICAL_SERIALIZATION_VERSION,
    ENTERPRISE_AGENTIC_GENERATED_PROFILE_VERSION,
    ENTERPRISE_AGENTIC_GENERATOR_VERSION,
    ENTERPRISE_AGENTIC_SMOKE_EVENT_SCHEDULE_VERSION,
    EnterpriseAgenticGeneratedPublicV1,
    EnterpriseAgenticScaleTier,
)
from synthworld.agentic.enterprise.generated_serialization import (
    generated_enterprise_agentic_public_artifact_set_sha256,
)
from synthworld.agentic.models import AgenticEvaluatorBundle
from synthworld.explorer.agentic_graph import (
    ProjectionBuilder,
    build_evaluator_annotations,
    project_events,
    project_snapshot,
)
from synthworld.explorer.models import (
    EXPLORER_ENTERPRISE_GENERATED_PROFILE,
    ExplorerCoordinateV1,
    ExplorerEnterpriseGeneratedLayoutOptionsV1,
    ExplorerEnterpriseGeneratedLayoutV1,
    ExplorerEnterpriseGeneratedProjectionV1,
    ExplorerEnterpriseGeneratedSourceV1,
    ExplorerEvaluatorOverlayV1,
    ExplorerNodeKind,
    ExplorerViewportV1,
)
from synthworld.explorer.serialization import explorer_digest

_SUPPORTED_PACKAGE_IDENTITY: Final = (
    ENTERPRISE_AGENTIC_GENERATED_PROFILE_VERSION,
    ENTERPRISE_AGENTIC_GENERATOR_VERSION,
    ENTERPRISE_AGENTIC_CANONICAL_SERIALIZATION_VERSION,
    ENTERPRISE_AGENTIC_SMOKE_EVENT_SCHEDULE_VERSION,
    EnterpriseAgenticScaleTier.SMOKE,
)
_KIND_COLUMNS: Final[dict[ExplorerNodeKind, int]] = {
    ExplorerNodeKind.ORGANISATION: 0,
    ExplorerNodeKind.DEPARTMENT: 1,
    ExplorerNodeKind.PRINCIPAL: 2,
    ExplorerNodeKind.LOGICAL_AGENT: 3,
    ExplorerNodeKind.RUNTIME: 4,
    ExplorerNodeKind.CREDENTIAL: 5,
    ExplorerNodeKind.DELEGATION: 6,
    ExplorerNodeKind.PROPOSED_DELEGATION: 7,
    ExplorerNodeKind.RESOURCE: 8,
    ExplorerNodeKind.ACTION_ATTEMPT: 9,
}
_NODE_WIDTH: Final = 180.0
_NODE_HEIGHT: Final = 56.0
_NODE_SPACING: Final = 40
_LAYER_SPACING: Final = 80


def is_supported_generated_projection(
    projection: ExplorerEnterpriseGeneratedProjectionV1,
) -> bool:
    """Report whether a projection records the released supported identity."""

    source = projection.source
    return (
        projection.profile == EXPLORER_ENTERPRISE_GENERATED_PROFILE
        and (
            source.profile_version,
            source.generator_version,
            source.canonical_serialization_version,
            source.event_schedule_version,
            source.tier,
        )
        == _SUPPORTED_PACKAGE_IDENTITY
    )


def project_generated_enterprise_agentic_v1(
    public: EnterpriseAgenticGeneratedPublicV1,
) -> ExplorerEnterpriseGeneratedProjectionV1:
    """Project one verified generated public package without evaluator truth."""

    identity = public.identity
    actual_identity = (
        identity.profile_version,
        identity.generator_version,
        identity.canonical_serialization_version,
        identity.event_schedule_version,
        identity.tier,
    )
    if actual_identity != _SUPPORTED_PACKAGE_IDENTITY:
        raise ValueError(
            "Explorer supports only the released generated enterprise-agentic "
            "smoke profile"
        )
    builder = ProjectionBuilder()
    project_snapshot(builder, public.benchmark)
    project_events(builder, public.benchmark)
    snapshot = public.benchmark.snapshot
    return ExplorerEnterpriseGeneratedProjectionV1(
        source=ExplorerEnterpriseGeneratedSourceV1(
            profile_version=identity.profile_version,
            generator_version=identity.generator_version,
            canonical_serialization_version=(identity.canonical_serialization_version),
            event_schedule_version=identity.event_schedule_version,
            tier=identity.tier.value,
            seed=identity.seed,
            configuration_sha256=identity.configuration_sha256,
            world_id=identity.world_id,
            world_version=snapshot.world_version,
            world_schema_version=snapshot.schema_version,
            public_artifact_set_sha256=(
                generated_enterprise_agentic_public_artifact_set_sha256(public)
            ),
        ),
        nodes=tuple(builder.nodes),
        edges=tuple(builder.edges),
        timeline=tuple(builder.timeline),
    )


def project_generated_enterprise_agentic_evaluator_v1(
    projection: ExplorerEnterpriseGeneratedProjectionV1,
    evaluator: AgenticEvaluatorBundle,
    *,
    evaluator_artifact_set_digest: str,
) -> ExplorerEvaluatorOverlayV1:
    """Project generated evaluator truth without merging it into public records."""

    if (
        projection.source.world_id != evaluator.world_id
        or projection.source.world_version != evaluator.world_version
        or projection.source.seed != evaluator.seed
    ):
        raise ValueError(
            "generated enterprise-agentic evaluator identity does not match "
            "the projection"
        )
    action_nodes = {
        node.source_id: node.id
        for node in projection.nodes
        if node.kind is ExplorerNodeKind.ACTION_ATTEMPT
    }
    annotations = build_evaluator_annotations(
        action_nodes, evaluator, subject="generated enterprise-agentic"
    )
    return ExplorerEvaluatorOverlayV1(
        public_projection_digest=explorer_digest(projection),
        evaluator_artifact_set_digest=evaluator_artifact_set_digest,
        annotations=annotations,
    )


def compute_generated_enterprise_agentic_layout(
    projection: ExplorerEnterpriseGeneratedProjectionV1,
) -> ExplorerEnterpriseGeneratedLayoutV1:
    """Compute deterministic kind-layered grid coordinates from the projection.

    Columns follow the authority chain by node kind; rows follow a pre-order
    walk of the containment forest so each parent's descendants stay vertically
    contiguous. Every input is the projection itself - no filesystem order,
    locale, host state, wall-clock time, or evaluator answer can change bytes.
    """

    if not projection.nodes:
        raise ValueError("generated Explorer layout requires at least one node")
    children: dict[str | None, list[str]] = {}
    for node in projection.nodes:
        children.setdefault(node.parent_node_id, []).append(node.id)
    walk_order: dict[str, int] = {}
    stack = list(reversed(children.get(None, [])))
    while stack:
        node_id = stack.pop()
        walk_order[node_id] = len(walk_order)
        stack.extend(reversed(children.get(node_id, [])))
    rows: dict[str, int] = {}
    column_depths: dict[int, int] = {}
    for node in sorted(projection.nodes, key=lambda item: walk_order[item.id]):
        column = _KIND_COLUMNS[node.kind]
        rows[node.id] = column_depths.get(column, 0)
        column_depths[column] = rows[node.id] + 1
    coordinates = tuple(
        ExplorerCoordinateV1(
            node_id=node.id,
            x=round(_KIND_COLUMNS[node.kind] * (_NODE_WIDTH + _LAYER_SPACING), 3),
            y=round(rows[node.id] * (_NODE_HEIGHT + _NODE_SPACING), 3),
            width=_NODE_WIDTH,
            height=_NODE_HEIGHT,
        )
        for node in projection.nodes
    )
    return ExplorerEnterpriseGeneratedLayoutV1(
        public_projection_digest=explorer_digest(projection),
        world_id=projection.source.world_id,
        world_seed=projection.source.seed,
        world_schema_version=projection.source.world_schema_version,
        options=ExplorerEnterpriseGeneratedLayoutOptionsV1(
            node_spacing=_NODE_SPACING,
            layer_spacing=_LAYER_SPACING,
        ),
        viewport=ExplorerViewportV1(
            width=int(
                max(column_depths) * (_NODE_WIDTH + _LAYER_SPACING) + _NODE_WIDTH
            ),
            height=int(
                (max(column_depths.values()) - 1) * (_NODE_HEIGHT + _NODE_SPACING)
                + _NODE_HEIGHT
            ),
        ),
        coordinates=coordinates,
    )
