from __future__ import annotations

import math
from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from synthworld.models import SyntheticModel

EXPLORER_PROJECTION_SCHEMA_VERSION = "1.0.0"
EXPLORER_LAYOUT_SCHEMA_VERSION = "1.0.0"
EVALUATOR_WATERMARK = "EVALUATOR VIEW - CONTAINS REFERENCE TRUTH"


class ExplorerNodeKind(StrEnum):
    ORGANISATION = "organisation"
    DEPARTMENT = "department"
    PRINCIPAL = "principal"
    LOGICAL_AGENT = "logical_agent"
    RUNTIME = "runtime"
    CREDENTIAL = "credential"
    DELEGATION = "delegation"
    RESOURCE = "resource"
    ACTION_ATTEMPT = "action_attempt"


class ExplorerEdgeKind(StrEnum):
    CONTAINS = "contains"
    OWNS = "owns"
    PARENT_AGENT = "parent_agent"
    ORIGINATES = "originates"
    DELEGATES = "delegates"
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


class ExplorerPropertyV1(SyntheticModel):
    key: str
    value: str

    @field_validator("key", "value")
    @classmethod
    def require_nonblank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Explorer properties must be nonblank")
        return stripped


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
        node_ids = tuple(item.id for item in self.nodes)
        edge_ids = tuple(item.id for item in self.edges)
        _require_unique(node_ids, "Explorer node IDs")
        _require_unique(edge_ids, "Explorer edge IDs")
        known_nodes = set(node_ids)
        known_edges = set(edge_ids)
        for node in self.nodes:
            if node.parent_node_id is not None and node.parent_node_id not in known_nodes:
                raise ValueError("Explorer node references an unknown parent")
        for edge in self.edges:
            if (
                edge.source_node_id not in known_nodes
                or edge.target_node_id not in known_nodes
            ):
                raise ValueError("Explorer edge references an unknown node")
        previous_index = 0
        previous_time: datetime | None = None
        for event in self.timeline:
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
    schema_version: Literal["1.0.0"] = EXPLORER_PROJECTION_SCHEMA_VERSION
    visibility: Literal["evaluator"] = "evaluator"
    watermark: Literal[
        "EVALUATOR VIEW - CONTAINS REFERENCE TRUTH"
    ] = EVALUATOR_WATERMARK
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
        if not all(math.isfinite(value) for value in (self.x, self.y)):
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
        node_ids = tuple(item.node_id for item in value)
        _require_unique(node_ids, "Explorer layout node IDs")
        return tuple(sorted(value, key=lambda item: item.node_id))
