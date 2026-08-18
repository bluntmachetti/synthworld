from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from synthworld.agentic import generate_asteria_agentic_v1
from synthworld.agentic.models import ActionAttempted, DelegationGranted
from synthworld.explorer import (
    EVALUATOR_WATERMARK,
    ExplorerCoordinateV1,
    ExplorerEdgeKind,
    ExplorerEvaluatorAnnotationV1,
    ExplorerEvaluatorOverlayV1,
    ExplorerLayoutManifestV1,
    ExplorerLayoutManifestV2,
    ExplorerLayoutOptionsV1,
    ExplorerNodeKind,
    ExplorerPropertyV1,
    ExplorerPublicProjectionV1,
    ExplorerViewportV1,
    canonical_json_bytes,
    explorer_digest,
    project_asteria_agent_authority_v1,
    validate_evaluator_overlay,
    validate_layout_manifest,
)

_PUBLIC_DIGEST = "a" * 64


def _projection() -> ExplorerPublicProjectionV1:
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
        event for event in projection.timeline if event.kind == "delegation_revoked"
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


def test_projection_preserves_granted_delegation_chain_semantics() -> None:
    public = generate_asteria_agentic_v1().public
    source_event = next(
        event for event in public.events if event.id == "evt-009-child-delegated"
    )
    assert isinstance(source_event.payload, DelegationGranted)
    source_delegation = source_event.payload.delegation
    assert source_delegation.parent_delegation_id is not None
    projection = project_asteria_agent_authority_v1(
        public,
        public_artifact_set_digest=_PUBLIC_DIGEST,
    )
    timeline_event = next(
        event
        for event in projection.timeline
        if event.source_event_id == source_event.id
    )
    delegation_node = next(
        node
        for node in projection.nodes
        if node.kind == ExplorerNodeKind.DELEGATION
        and node.source_id == source_delegation.id
    )
    parent_node = next(
        node
        for node in projection.nodes
        if node.kind == ExplorerNodeKind.DELEGATION
        and node.source_id == source_delegation.parent_delegation_id
    )
    properties = {item.key: item.value for item in delegation_node.properties}

    assert properties["parent_delegation_id"] == (
        source_delegation.parent_delegation_id
    )
    assert (
        properties["may_delegate"]
        == str(source_delegation.capability.may_delegate).lower()
    )
    parent_edge = next(
        edge
        for edge in projection.edges
        if edge.kind == ExplorerEdgeKind.PARENT_DELEGATION
        and edge.source_node_id == parent_node.id
        and edge.target_node_id == delegation_node.id
    )
    assert parent_edge.id in timeline_event.related_edge_ids


def test_projection_preserves_proposed_delegation_payload() -> None:
    public = generate_asteria_agentic_v1().public
    source_event = next(
        event
        for event in public.events
        if event.id == "evt-012-overprivileged-delegation"
    )
    assert isinstance(source_event.payload, ActionAttempted)
    proposed = source_event.payload.attempt.proposed_delegation
    assert proposed is not None
    assert proposed.parent_delegation_id is not None
    projection = project_asteria_agent_authority_v1(
        public,
        public_artifact_set_digest=_PUBLIC_DIGEST,
    )
    timeline_event = next(
        event
        for event in projection.timeline
        if event.source_event_id == source_event.id
    )
    action_node = next(
        node
        for node in projection.nodes
        if node.kind == ExplorerNodeKind.ACTION_ATTEMPT
        and node.source_id == source_event.id
    )
    proposed_node = next(
        node
        for node in projection.nodes
        if node.kind == ExplorerNodeKind.PROPOSED_DELEGATION
        and node.source_id == proposed.id
    )
    properties = {item.key: item.value for item in proposed_node.properties}

    assert proposed_node.id in timeline_event.related_node_ids
    assert properties == {
        "actions": proposed.capability.actions,
        "delegator_principal_id": proposed.delegator_principal_id,
        "expires_at": proposed.expires_at.isoformat(),
        "grantee_agent_id": proposed.grantee_agent_id,
        "may_delegate": str(proposed.capability.may_delegate).lower(),
        "originating_principal_id": proposed.originating_principal_id,
        "parent_delegation_id": proposed.parent_delegation_id,
        "policy_version": proposed.policy_version,
        "purpose": proposed.capability.purpose,
        "resource_ids": proposed.capability.resource_ids,
        "scopes": proposed.capability.scopes,
        "valid_from": proposed.valid_from.isoformat(),
    }
    proposed_edge = next(
        edge
        for edge in projection.edges
        if edge.kind == ExplorerEdgeKind.PROPOSES_DELEGATION
        and edge.source_node_id == action_node.id
        and edge.target_node_id == proposed_node.id
    )
    parent_edge = next(
        edge
        for edge in projection.edges
        if edge.kind == ExplorerEdgeKind.PARENT_DELEGATION
        and edge.target_node_id == proposed_node.id
    )
    assert proposed_edge.id in timeline_event.related_edge_ids
    assert parent_edge.id in timeline_event.related_edge_ids

    proposed_without_parent = proposed.model_copy(update={"parent_delegation_id": None})
    attempt_without_parent = source_event.payload.attempt.model_copy(
        update={"proposed_delegation": proposed_without_parent}
    )
    event_without_parent = source_event.model_copy(
        update={
            "payload": source_event.payload.model_copy(
                update={"attempt": attempt_without_parent}
            )
        }
    )
    public_without_parent = public.model_copy(
        update={
            "events": tuple(
                event_without_parent if event.id == source_event.id else event
                for event in public.events
            )
        }
    )
    projection_without_parent = project_asteria_agent_authority_v1(
        public_without_parent,
        public_artifact_set_digest=_PUBLIC_DIGEST,
    )
    proposed_node_without_parent = next(
        node
        for node in projection_without_parent.nodes
        if node.kind == ExplorerNodeKind.PROPOSED_DELEGATION
        and node.source_id == proposed.id
    )
    assert not any(
        edge.kind == ExplorerEdgeKind.PARENT_DELEGATION
        and edge.target_node_id == proposed_node_without_parent.id
        for edge in projection_without_parent.edges
    )


def test_projection_contract_rejects_open_or_ambiguous_graphs() -> None:
    projection = _projection()
    projection_data = projection.model_dump(mode="json")
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
    repeated_index["timeline"][1]["source_event_index"] = repeated_index["timeline"][0][
        "source_event_index"
    ]
    mutations.append((repeated_index, "indices must be strictly increasing"))

    repeated_time = deepcopy(projection_data)
    repeated_time["timeline"][1]["occurred_at"] = repeated_time["timeline"][0][
        "occurred_at"
    ]
    mutations.append((repeated_time, "times must be strictly increasing"))

    repeated_source_event_id = deepcopy(projection_data)
    repeated_source_event_id["timeline"][1]["source_event_id"] = (
        repeated_source_event_id["timeline"][0]["source_event_id"]
    )
    mutations.append(
        (repeated_source_event_id, "timeline source event IDs must be unique")
    )

    parent_cycle = deepcopy(projection_data)
    parent_cycle["nodes"][0]["parent_node_id"] = parent_cycle["nodes"][1]["id"]
    parent_cycle["nodes"][1]["parent_node_id"] = parent_cycle["nodes"][0]["id"]
    mutations.append((parent_cycle, "parents must be acyclic"))

    non_utc = deepcopy(projection_data)
    non_utc["timeline"][0]["occurred_at"] = datetime(
        2026,
        1,
        1,
        tzinfo=timezone(timedelta(hours=1)),
    )
    mutations.append((non_utc, "timestamps must use UTC"))

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
    with pytest.raises(ValidationError, match="values must be nonblank"):
        ExplorerPropertyV1(key="member", value=" ")
    first_collection = ExplorerPropertyV1(key="members", value=("a", "b|c"))
    second_collection = ExplorerPropertyV1(key="members", value=("a|b", "c"))
    assert first_collection.value == ("a", "b|c")
    assert first_collection != second_collection
    with pytest.raises(ValidationError, match="collections must be nonempty"):
        ExplorerPropertyV1(key="members", value=())
    with pytest.raises(ValidationError, match="event references must be unique"):
        projection.timeline[0].__class__(
            **projection.timeline[0].model_dump(exclude={"related_node_ids"}),
            related_node_ids=(projection.nodes[0].id,) * 2,
        )


def test_evaluator_overlay_is_separate_watermarked_and_digest_bound() -> None:
    projection = _projection()
    action_event_id = next(
        event.source_event_id
        for event in projection.timeline
        if event.kind == "action_attempted"
    )
    annotation = ExplorerEvaluatorAnnotationV1(
        id="annotation-1",
        source_action_event_id=action_event_id,
        target_id=action_event_id,
        kind="authority_decision",
        label="Expected authority decision",
        value="allow",
        properties=(ExplorerPropertyV1(key="source", value="oracle"),),
    )
    overlay = ExplorerEvaluatorOverlayV1(
        public_projection_digest=explorer_digest(projection),
        evaluator_artifact_set_digest="b" * 64,
        annotations=(annotation,),
    )

    assert overlay.visibility == "evaluator"
    assert overlay.watermark == EVALUATOR_WATERMARK
    assert b"Expected authority decision" in canonical_json_bytes(overlay)
    validate_evaluator_overlay(projection, overlay)
    with pytest.raises(ValueError, match="does not bind"):
        validate_evaluator_overlay(
            projection,
            overlay.model_copy(update={"public_projection_digest": "c" * 64}),
        )
    with pytest.raises(ValueError, match="unknown action event"):
        validate_evaluator_overlay(
            projection,
            overlay.model_copy(
                update={
                    "annotations": (
                        annotation.model_copy(
                            update={"source_action_event_id": "missing"}
                        ),
                    )
                }
            ),
        )
    with pytest.raises(ValueError, match="unknown target"):
        validate_evaluator_overlay(
            projection,
            overlay.model_copy(
                update={
                    "annotations": (
                        annotation.model_copy(update={"target_id": "missing"}),
                    )
                }
            ),
        )
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
    validate_layout_manifest(projection, layout)
    with pytest.raises(ValueError, match="does not bind"):
        validate_layout_manifest(
            projection,
            layout.model_copy(update={"public_projection_digest": "c" * 64}),
        )
    with pytest.raises(ValueError, match="cover exactly"):
        validate_layout_manifest(
            projection,
            layout.model_copy(update={"coordinates": layout.coordinates[:-1]}),
        )
    with pytest.raises(ValidationError, match="coordinates must be finite"):
        ExplorerCoordinateV1(
            node_id=projection.nodes[0].id,
            x=float("nan"),
            y=0.0,
            width=1.0,
            height=1.0,
        )
    for dimension in ("width", "height"):
        values = {
            "node_id": projection.nodes[0].id,
            "x": 0.0,
            "y": 0.0,
            "width": 1.0,
            "height": 1.0,
        }
        values[dimension] = float("inf")
        with pytest.raises(ValidationError, match="coordinates must be finite"):
            ExplorerCoordinateV1.model_validate(values)
    with pytest.raises(ValidationError, match="layout node IDs must be unique"):
        ExplorerLayoutManifestV1(
            public_projection_digest=explorer_digest(projection),
            options=ExplorerLayoutOptionsV1(engine_version="0.9.3"),
            viewport=ExplorerViewportV1(width=1440, height=900),
            coordinates=(coordinates[0], coordinates[0]),
        )


def test_layout_v2_carries_and_validates_explicit_projection_identity() -> None:
    projection = _projection()
    layout = ExplorerLayoutManifestV2(
        public_projection_digest=explorer_digest(projection),
        world_seed=projection.source.seed,
        world_schema_version=projection.source.world_schema_version,
        options=ExplorerLayoutOptionsV1(engine_version="0.9.3"),
        viewport=ExplorerViewportV1(width=1440, height=900),
        coordinates=tuple(
            ExplorerCoordinateV1(
                node_id=node.id,
                x=float(index),
                y=float(index),
                width=180.0,
                height=56.0,
            )
            for index, node in enumerate(projection.nodes)
        ),
    )

    assert layout.schema_version == "2.0.0"
    assert layout.visualisation_profile == "agent-authority"
    assert layout.visualisation_profile_version == "1.0.0"
    validate_layout_manifest(projection, layout)
    with pytest.raises(ValueError, match="identity does not match"):
        validate_layout_manifest(
            projection,
            layout.model_copy(update={"world_seed": projection.source.seed + 1}),
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


def test_asteria_adapter_handles_optional_parents_and_unresolved_claims() -> None:
    public = generate_asteria_agentic_v1().public
    principals = list(public.snapshot.principals)
    principal_index = next(
        index
        for index, principal in enumerate(principals)
        if principal.organisation_id is not None
    )
    principal = principals[principal_index]
    principals[principal_index] = principal.model_copy(update={"department_id": None})
    organisation_parented = public.model_copy(
        update={
            "snapshot": public.snapshot.model_copy(
                update={"principals": tuple(principals)}
            )
        }
    )
    projection = project_asteria_agent_authority_v1(
        organisation_parented,
        public_artifact_set_digest=_PUBLIC_DIGEST,
    )
    projected_principal = next(
        node
        for node in projection.nodes
        if node.kind == ExplorerNodeKind.PRINCIPAL and node.source_id == principal.id
    )
    assert projected_principal.parent_node_id is not None

    principals[principal_index] = principal.model_copy(
        update={"department_id": None, "organisation_id": None}
    )
    unparented = public.model_copy(
        update={
            "snapshot": public.snapshot.model_copy(
                update={"principals": tuple(principals)}
            )
        }
    )
    projection = project_asteria_agent_authority_v1(
        unparented,
        public_artifact_set_digest=_PUBLIC_DIGEST,
    )
    projected_principal = next(
        node
        for node in projection.nodes
        if node.kind == ExplorerNodeKind.PRINCIPAL and node.source_id == principal.id
    )
    assert projected_principal.parent_node_id is None

    events = list(public.events)
    event_index = next(
        index
        for index, event in enumerate(events)
        if isinstance(event.payload, ActionAttempted)
    )
    action_event = events[event_index]
    assert isinstance(action_event.payload, ActionAttempted)
    altered_attempt = action_event.payload.attempt.model_copy(
        update={"originating_principal_claim": "principal-unresolved"}
    )
    events[event_index] = action_event.model_copy(
        update={
            "payload": action_event.payload.model_copy(
                update={"attempt": altered_attempt}
            )
        }
    )
    unresolved_claim = public.model_copy(update={"events": tuple(events)})
    projection = project_asteria_agent_authority_v1(
        unresolved_claim,
        public_artifact_set_digest=_PUBLIC_DIGEST,
    )
    action_node = next(
        node
        for node in projection.nodes
        if node.source_id == action_event.id
        and node.kind == ExplorerNodeKind.ACTION_ATTEMPT
    )
    properties = {item.key: item.value for item in action_node.properties}
    assert properties["originating_principal_claim"] == "principal-unresolved"
