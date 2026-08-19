from __future__ import annotations

import math
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final, Literal, Self

from pydantic import Field, field_validator, model_validator

from synthworld.models import SyntheticModel

EXPLORER_PROJECTION_SCHEMA_VERSION: Final = "1.0.0"
EXPLORER_EVALUATOR_SCHEMA_VERSION: Final = "1.0.0"
EXPLORER_LAYOUT_SCHEMA_VERSION: Final = "1.0.0"
EXPLORER_LAYOUT_SCHEMA_VERSION_V2: Final = "2.0.0"
EXPLORER_VISUALISATION_PROFILE_VERSION: Final = "1.0.0"
EVALUATOR_WATERMARK: Final = "EVALUATOR VIEW - CONTAINS REFERENCE TRUTH"
EXPLORER_ENTERPRISE_GENERATED_PROJECTION_SCHEMA_VERSION: Final = "1.0.0"
EXPLORER_ENTERPRISE_GENERATED_PROFILE: Final = "enterprise-agentic-generated-v1"
EXPLORER_ENTERPRISE_GENERATED_LAYOUT_SCHEMA_VERSION: Final = "1.0.0"
EXPLORER_ENTERPRISE_GENERATED_VISUALISATION_PROFILE: Final = (
    "enterprise-agentic-generated-agent-authority"
)
EXPLORER_ENTERPRISE_GENERATED_VISUALISATION_PROFILE_VERSION: Final = "1.0.0"


class ExplorerNodeKind(StrEnum):
    ORGANISATION = "organisation"
    DEPARTMENT = "department"
    PRINCIPAL = "principal"
    LOGICAL_AGENT = "logical_agent"
    RUNTIME = "runtime"
    CREDENTIAL = "credential"
    DELEGATION = "delegation"
    PROPOSED_DELEGATION = "proposed_delegation"
    RESOURCE = "resource"
    ACTION_ATTEMPT = "action_attempt"


class ExplorerEdgeKind(StrEnum):
    CONTAINS = "contains"
    OWNS = "owns"
    PARENT_AGENT = "parent_agent"
    ORIGINATES = "originates"
    DELEGATES = "delegates"
    PARENT_DELEGATION = "parent_delegation"
    GRANTS_TO = "grants_to"
    TARGETS = "targets"
    ISSUES = "issues"
    SUBJECT = "subject"
    ALLOWS_RUNTIME = "allows_runtime"
    EXECUTES_ON = "executes_on"
    RUNS_AS = "runs_as"
    CLAIMS_ORIGINATOR = "claims_originator"
    CLAIMS_AGENT = "claims_agent"
    CLAIMS_RUNTIME = "claims_runtime"
    PRESENTS = "presents"
    ATTEMPTS = "attempts"
    PROPOSES_DELEGATION = "proposes_delegation"


class ExplorerTimelineEventKind(StrEnum):
    DELEGATION_GRANTED = "delegation_granted"
    CREDENTIAL_ISSUED = "credential_issued"
    RUNTIME_SPAWNED = "runtime_spawned"
    ACTION_ATTEMPTED = "action_attempted"
    DELEGATION_REVOKED = "delegation_revoked"
    EVIDENCE_DISCARDED = "evidence_discarded"
    AUDIT_PERFORMED = "audit_performed"


class ExplorerLayoutDirection(StrEnum):
    DOWN = "down"
    RIGHT = "right"


type _ExplorerPropertyValue = str | tuple[str, ...]


class ExplorerPropertyV1(SyntheticModel):
    key: str
    value: _ExplorerPropertyValue

    @field_validator("key")
    @classmethod
    def require_nonblank_key(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Explorer property keys must be nonblank")
        return stripped

    @field_validator("value")
    @classmethod
    def require_nonblank_value(
        cls, value: _ExplorerPropertyValue
    ) -> _ExplorerPropertyValue:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                raise ValueError("Explorer property values must be nonblank")
            return stripped
        stripped_items = tuple(item.strip() for item in value)
        if not stripped_items or any(not item for item in stripped_items):
            raise ValueError("Explorer property collections must be nonempty")
        return stripped_items


def _normalise_properties(
    properties: tuple[ExplorerPropertyV1, ...],
) -> tuple[ExplorerPropertyV1, ...]:
    keys = tuple(item.key for item in properties)
    if len(keys) != len(set(keys)):
        raise ValueError("Explorer property keys must be unique")
    return tuple(sorted(properties, key=lambda item: item.key))


class ExplorerSourceV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = EXPLORER_PROJECTION_SCHEMA_VERSION
    benchmark_id: str
    benchmark_version: str
    world_id: str
    world_schema_version: str
    seed: int
    lifecycle: Literal["published"] = "published"
    digest_algorithm: Literal["sha256"] = "sha256"
    public_artifact_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class ExplorerNodeV1(SyntheticModel):
    id: str
    source_id: str
    kind: ExplorerNodeKind
    label: str
    parent_node_id: str | None = None
    properties: tuple[ExplorerPropertyV1, ...] = ()

    @field_validator("properties")
    @classmethod
    def normalise_properties(
        cls, value: tuple[ExplorerPropertyV1, ...]
    ) -> tuple[ExplorerPropertyV1, ...]:
        return _normalise_properties(value)


class ExplorerEdgeV1(SyntheticModel):
    id: str
    kind: ExplorerEdgeKind
    source_node_id: str
    target_node_id: str
    label: str
    properties: tuple[ExplorerPropertyV1, ...] = ()

    @field_validator("properties")
    @classmethod
    def normalise_properties(
        cls, value: tuple[ExplorerPropertyV1, ...]
    ) -> tuple[ExplorerPropertyV1, ...]:
        return _normalise_properties(value)


class ExplorerTimelineEventV1(SyntheticModel):
    source_event_id: str
    source_event_index: int = Field(ge=1)
    occurred_at: datetime
    kind: ExplorerTimelineEventKind
    related_node_ids: tuple[str, ...] = ()
    related_edge_ids: tuple[str, ...] = ()
    properties: tuple[ExplorerPropertyV1, ...] = ()

    @field_validator("occurred_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.utcoffset() != timedelta(0):
            raise ValueError("Explorer timeline timestamps must use UTC")
        return value

    @field_validator("related_node_ids", "related_edge_ids")
    @classmethod
    def sort_unique_references(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("Explorer event references must be unique")
        return tuple(sorted(value))

    @field_validator("properties")
    @classmethod
    def normalise_properties(
        cls, value: tuple[ExplorerPropertyV1, ...]
    ) -> tuple[ExplorerPropertyV1, ...]:
        return _normalise_properties(value)


def _require_unique(values: tuple[str, ...], description: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{description} must be unique")


def _require_closed_projection_graph(
    nodes: tuple[ExplorerNodeV1, ...],
    edges: tuple[ExplorerEdgeV1, ...],
    timeline: tuple[ExplorerTimelineEventV1, ...],
) -> None:
    node_ids = tuple(item.id for item in nodes)
    edge_ids = tuple(item.id for item in edges)
    _require_unique(node_ids, "Explorer node IDs")
    _require_unique(edge_ids, "Explorer edge IDs")
    _require_unique(
        tuple(event.source_event_id for event in timeline),
        "Explorer timeline source event IDs",
    )
    known_nodes = set(node_ids)
    known_edges = set(edge_ids)
    parents = {node.id: node.parent_node_id for node in nodes}
    for node in nodes:
        if node.parent_node_id is not None and node.parent_node_id not in known_nodes:
            raise ValueError("Explorer node references an unknown parent")
    for node_id in node_ids:
        visited: set[str] = set()
        cursor = node_id
        while (parent := parents[cursor]) is not None:
            if parent == node_id or parent in visited:
                raise ValueError("Explorer node parents must be acyclic")
            visited.add(cursor)
            cursor = parent
    for edge in edges:
        if (
            edge.source_node_id not in known_nodes
            or edge.target_node_id not in known_nodes
        ):
            raise ValueError("Explorer edge references an unknown node")
    previous_index = 0
    previous_time: datetime | None = None
    for event in timeline:
        if event.source_event_index <= previous_index:
            raise ValueError("Explorer timeline indices must be strictly increasing")
        if previous_time is not None and event.occurred_at <= previous_time:
            raise ValueError("Explorer timeline times must be strictly increasing")
        if not set(event.related_node_ids) <= known_nodes:
            raise ValueError("Explorer event references an unknown node")
        if not set(event.related_edge_ids) <= known_edges:
            raise ValueError("Explorer event references an unknown edge")
        previous_index = event.source_event_index
        previous_time = event.occurred_at


class ExplorerPublicProjectionV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = EXPLORER_PROJECTION_SCHEMA_VERSION
    profile: Literal["agent-authority-v1"] = "agent-authority-v1"
    visibility: Literal["public"] = "public"
    source: ExplorerSourceV1
    nodes: tuple[ExplorerNodeV1, ...]
    edges: tuple[ExplorerEdgeV1, ...]
    timeline: tuple[ExplorerTimelineEventV1, ...]

    @field_validator("nodes")
    @classmethod
    def sort_nodes(
        cls, value: tuple[ExplorerNodeV1, ...]
    ) -> tuple[ExplorerNodeV1, ...]:
        return tuple(sorted(value, key=lambda item: item.id))

    @field_validator("edges")
    @classmethod
    def sort_edges(
        cls, value: tuple[ExplorerEdgeV1, ...]
    ) -> tuple[ExplorerEdgeV1, ...]:
        return tuple(sorted(value, key=lambda item: item.id))

    @field_validator("timeline")
    @classmethod
    def sort_timeline(
        cls, value: tuple[ExplorerTimelineEventV1, ...]
    ) -> tuple[ExplorerTimelineEventV1, ...]:
        return tuple(sorted(value, key=lambda item: item.source_event_index))

    @model_validator(mode="after")
    def require_closed_graph(self) -> Self:
        _require_closed_projection_graph(self.nodes, self.edges, self.timeline)
        return self


class ExplorerEnterpriseGeneratedSourceV1(SyntheticModel):
    """Generated enterprise-agentic package identity behind a projection."""

    schema_version: Literal["1.0.0"] = (
        EXPLORER_ENTERPRISE_GENERATED_PROJECTION_SCHEMA_VERSION
    )
    benchmark_id: Literal["enterprise-agentic-generated"] = (
        "enterprise-agentic-generated"
    )
    profile_version: str = Field(min_length=1)
    generator_version: str = Field(min_length=1)
    canonical_serialization_version: str = Field(min_length=1)
    event_schedule_version: str = Field(min_length=1)
    tier: str = Field(min_length=1)
    seed: int = Field(ge=0)
    configuration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    world_id: str = Field(min_length=1)
    world_version: str = Field(min_length=1)
    world_schema_version: str = Field(min_length=1)
    lifecycle: Literal["generated"] = "generated"
    digest_algorithm: Literal["sha256"] = "sha256"
    public_artifact_set_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ExplorerEnterpriseGeneratedProjectionV1(SyntheticModel):
    """Public agent-authority projection of one generated enterprise world.

    Independently versioned from ``ExplorerPublicProjectionV1`` so the frozen
    Asteria ``agent-authority-v1`` profile literal never widens in place.
    """

    schema_version: Literal["1.0.0"] = (
        EXPLORER_ENTERPRISE_GENERATED_PROJECTION_SCHEMA_VERSION
    )
    profile: Literal["enterprise-agentic-generated-v1"] = (
        EXPLORER_ENTERPRISE_GENERATED_PROFILE
    )
    visibility: Literal["public"] = "public"
    source: ExplorerEnterpriseGeneratedSourceV1
    nodes: tuple[ExplorerNodeV1, ...]
    edges: tuple[ExplorerEdgeV1, ...]
    timeline: tuple[ExplorerTimelineEventV1, ...]

    @field_validator("nodes")
    @classmethod
    def sort_nodes(
        cls, value: tuple[ExplorerNodeV1, ...]
    ) -> tuple[ExplorerNodeV1, ...]:
        return tuple(sorted(value, key=lambda item: item.id))

    @field_validator("edges")
    @classmethod
    def sort_edges(
        cls, value: tuple[ExplorerEdgeV1, ...]
    ) -> tuple[ExplorerEdgeV1, ...]:
        return tuple(sorted(value, key=lambda item: item.id))

    @field_validator("timeline")
    @classmethod
    def sort_timeline(
        cls, value: tuple[ExplorerTimelineEventV1, ...]
    ) -> tuple[ExplorerTimelineEventV1, ...]:
        return tuple(sorted(value, key=lambda item: item.source_event_index))

    @model_validator(mode="after")
    def require_closed_graph(self) -> Self:
        _require_closed_projection_graph(self.nodes, self.edges, self.timeline)
        return self


class ExplorerEvaluatorAnnotationV1(SyntheticModel):
    id: str
    source_action_event_id: str
    target_id: str
    kind: Literal[
        "authority_decision",
        "failure_reason",
        "canonical_binding",
        "case_kind",
    ]
    label: str
    value: str
    properties: tuple[ExplorerPropertyV1, ...] = ()

    @field_validator("properties")
    @classmethod
    def normalise_properties(
        cls, value: tuple[ExplorerPropertyV1, ...]
    ) -> tuple[ExplorerPropertyV1, ...]:
        return _normalise_properties(value)


class ExplorerEvaluatorOverlayV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = EXPLORER_EVALUATOR_SCHEMA_VERSION
    visibility: Literal["evaluator"] = "evaluator"
    watermark: Literal["EVALUATOR VIEW - CONTAINS REFERENCE TRUTH"] = (
        EVALUATOR_WATERMARK
    )
    digest_algorithm: Literal["sha256"] = "sha256"
    public_projection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluator_artifact_set_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    annotations: tuple[ExplorerEvaluatorAnnotationV1, ...]

    @field_validator("annotations")
    @classmethod
    def sort_annotations(
        cls, value: tuple[ExplorerEvaluatorAnnotationV1, ...]
    ) -> tuple[ExplorerEvaluatorAnnotationV1, ...]:
        ids = tuple(item.id for item in value)
        _require_unique(ids, "Explorer evaluator annotation IDs")
        return tuple(sorted(value, key=lambda item: item.id))


class ExplorerLayoutOptionsV1(SyntheticModel):
    engine: Literal["elk"] = "elk"
    engine_version: str
    algorithm: Literal["layered"] = "layered"
    direction: ExplorerLayoutDirection = ExplorerLayoutDirection.RIGHT
    node_spacing: int = Field(default=40, ge=0)
    layer_spacing: int = Field(default=80, ge=0)


class ExplorerCoordinateV1(SyntheticModel):
    node_id: str
    x: float
    y: float
    width: float = Field(gt=0.0)
    height: float = Field(gt=0.0)

    @model_validator(mode="after")
    def require_finite_coordinates(self) -> Self:
        if not all(
            math.isfinite(value) for value in (self.x, self.y, self.width, self.height)
        ):
            raise ValueError("Explorer coordinates must be finite")
        return self


class ExplorerViewportV1(SyntheticModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class ExplorerLayoutManifestV1(SyntheticModel):
    schema_version: Literal["1.0.0"] = EXPLORER_LAYOUT_SCHEMA_VERSION
    digest_algorithm: Literal["sha256"] = "sha256"
    public_projection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    options: ExplorerLayoutOptionsV1
    viewport: ExplorerViewportV1
    coordinate_precision: int = Field(default=3, ge=0, le=6)
    coordinates: tuple[ExplorerCoordinateV1, ...]

    @field_validator("coordinates")
    @classmethod
    def sort_coordinates(
        cls, value: tuple[ExplorerCoordinateV1, ...]
    ) -> tuple[ExplorerCoordinateV1, ...]:
        return _sorted_unique_coordinates(value)


def _sorted_unique_coordinates(
    value: tuple[ExplorerCoordinateV1, ...],
) -> tuple[ExplorerCoordinateV1, ...]:
    node_ids = tuple(item.node_id for item in value)
    _require_unique(node_ids, "Explorer layout node IDs")
    return tuple(sorted(value, key=lambda item: item.node_id))


class ExplorerEnterpriseGeneratedLayoutOptionsV1(SyntheticModel):
    """Deterministic in-package layout inputs for generated worlds.

    Generated packages have no build-time pinned coordinates, so the layout
    engine is a pure-Python grid computed from the projection alone.
    """

    engine: Literal["synthworld-grid"] = "synthworld-grid"
    engine_version: Literal["1.0.0"] = "1.0.0"
    algorithm: Literal["kind-layered"] = "kind-layered"
    direction: ExplorerLayoutDirection = ExplorerLayoutDirection.RIGHT
    node_spacing: int = Field(default=40, ge=0)
    layer_spacing: int = Field(default=80, ge=0)


class ExplorerEnterpriseGeneratedLayoutV1(SyntheticModel):
    """Layout manifest for the generated enterprise-agentic projection."""

    schema_version: Literal["1.0.0"] = (
        EXPLORER_ENTERPRISE_GENERATED_LAYOUT_SCHEMA_VERSION
    )
    digest_algorithm: Literal["sha256"] = "sha256"
    public_projection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    world_id: str = Field(min_length=1)
    world_seed: int = Field(ge=0)
    world_schema_version: str = Field(min_length=1)
    visualisation_profile: Literal["enterprise-agentic-generated-agent-authority"] = (
        EXPLORER_ENTERPRISE_GENERATED_VISUALISATION_PROFILE
    )
    visualisation_profile_version: Literal["1.0.0"] = (
        EXPLORER_ENTERPRISE_GENERATED_VISUALISATION_PROFILE_VERSION
    )
    options: ExplorerEnterpriseGeneratedLayoutOptionsV1
    viewport: ExplorerViewportV1
    coordinate_precision: int = Field(default=3, ge=0, le=6)
    coordinates: tuple[ExplorerCoordinateV1, ...]

    @field_validator("coordinates")
    @classmethod
    def sort_coordinates(
        cls, value: tuple[ExplorerCoordinateV1, ...]
    ) -> tuple[ExplorerCoordinateV1, ...]:
        return _sorted_unique_coordinates(value)


class ExplorerLayoutManifestV2(SyntheticModel):
    """Layout inputs with explicit world and visualisation-profile identity."""

    schema_version: Literal["2.0.0"] = EXPLORER_LAYOUT_SCHEMA_VERSION_V2
    digest_algorithm: Literal["sha256"] = "sha256"
    public_projection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    world_seed: int
    world_schema_version: str = Field(min_length=1)
    visualisation_profile: Literal["agent-authority"] = "agent-authority"
    visualisation_profile_version: Literal["1.0.0"] = (
        EXPLORER_VISUALISATION_PROFILE_VERSION
    )
    options: ExplorerLayoutOptionsV1
    viewport: ExplorerViewportV1
    coordinate_precision: int = Field(default=3, ge=0, le=6)
    coordinates: tuple[ExplorerCoordinateV1, ...]

    @field_validator("coordinates")
    @classmethod
    def sort_coordinates(
        cls, value: tuple[ExplorerCoordinateV1, ...]
    ) -> tuple[ExplorerCoordinateV1, ...]:
        return _sorted_unique_coordinates(value)
