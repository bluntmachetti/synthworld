"""Field-by-field C08 public projection and evaluator binding."""

from __future__ import annotations

from uuid import UUID, uuid5

from synthworld.agentic.enterprise.c08_v2.errors import C08ProjectionError
from synthworld.agentic.enterprise.c08_v2.models import (
    C08EvaluatorTruthV2,
    C08EvidenceBindingV2,
    C08EvidenceEventV2,
    C08PublicActionV2,
    C08PublicInputV2,
    C08SourceActionV2,
    C08SourceWorldV2,
)
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest

_PUBLIC_OBSERVATION_NAMESPACE = UUID("ce4f822e-c4a5-57dd-87ee-74d7cb385ba8")


def c08_public_observation_id(source_evidence_id: str) -> str:
    """Derive an opaque stable public identity without exposing the source ID."""

    return f"observation-{uuid5(_PUBLIC_OBSERVATION_NAMESPACE, source_evidence_id).hex}"


def _public_action(source: C08SourceActionV2) -> C08PublicActionV2:
    return C08PublicActionV2(
        action_id=source.action_id,
        tenant_id=source.tenant_id,
        resource_id=source.resource_id,
        action=source.action,
        tick=source.tick,
        required_evidence=source.required_evidence,
    )


def project_c08_public(source: C08SourceWorldV2) -> C08PublicInputV2:
    """Construct public actions and non-oracle evidence observations field by
    field.
    """

    return C08PublicInputV2(
        actions=tuple(_public_action(item) for item in source.actions),
        evidence_events=tuple(
            C08EvidenceEventV2(
                sequence=sequence,
                evidence_id=c08_public_observation_id(event.evidence_id),
                action_id=event.action_id,
                tenant_id=event.tenant_id,
                resource_id=event.resource_id,
                action=event.action,
                tick=event.tick,
                kind=event.kind,
                binding_handle=event.binding_handle,
                payload_digest=event.payload_digest,
            )
            for sequence, event in enumerate(
                sorted(
                    source.evidence_events,
                    key=lambda item: c08_public_observation_id(item.evidence_id),
                )
            )
        ),
    )


def c08_public_input_digest(public: C08PublicInputV2) -> str:
    """Return the canonical digest bound by evaluator truth and submissions."""

    return synthetic_digest(canonical_json_bytes(public)).value


def compile_c08_truth(
    source: C08SourceWorldV2, public: C08PublicInputV2
) -> C08EvaluatorTruthV2:
    """Bind source-only required evidence to the independently projected public
    input.
    """

    expected_public = project_c08_public(source)
    if public != expected_public:
        raise C08ProjectionError(
            "C08 public projection differs from source actions and evidence"
        )
    truth = C08EvaluatorTruthV2(
        public_input_digest=c08_public_input_digest(public),
        bindings=tuple(
            C08EvidenceBindingV2(
                action_id=action.action_id,
                tenant_id=action.tenant_id,
                required_evidence=action.required_evidence,
                required_observation_ids=tuple(
                    sorted(
                        c08_public_observation_id(item)
                        for item in action.required_evidence_ids
                    )
                ),
            )
            for action in sorted(source.actions, key=lambda item: item.action_id)
        ),
    )
    validate_c08_truth_against_public(public, truth)
    return truth


def validate_c08_truth_against_public(
    public: C08PublicInputV2,
    evaluator: C08EvaluatorTruthV2,
) -> None:
    """Validate evaluator-only IDs against the public evidence observations."""

    actions_by_id = {action.action_id: action for action in public.actions}
    events_by_id = {event.evidence_id: event for event in public.evidence_events}
    bindings_by_id = {binding.action_id: binding for binding in evaluator.bindings}
    if set(actions_by_id) != set(bindings_by_id):
        raise C08ProjectionError("C08 evaluator bindings do not cover public actions")
    for action_id, action in actions_by_id.items():
        binding = bindings_by_id[action_id]
        if binding.tenant_id != action.tenant_id:
            raise C08ProjectionError(
                "C08 evaluator tenant binding differs from public action"
            )
        if binding.required_evidence != action.required_evidence:
            raise C08ProjectionError(
                "C08 evaluator evidence kinds differ from public action"
            )
        bound_events: list[C08EvidenceEventV2] = []
        for evidence_id in binding.required_observation_ids:
            event = events_by_id.get(evidence_id)
            if event is None:
                raise C08ProjectionError(
                    "C08 evaluator binding references missing public evidence"
                )
            if (
                event.action_id != action.action_id
                or event.tenant_id != action.tenant_id
                or event.resource_id != action.resource_id
                or event.action != action.action
                or event.tick != action.tick
            ):
                raise C08ProjectionError(
                    "C08 evaluator evidence does not match its public action"
                )
            bound_events.append(event)
        bound_requirements = {
            (event.kind, event.binding_handle) for event in bound_events
        }
        expected_requirements = {
            (item.kind, item.binding_handle) for item in binding.required_evidence
        }
        if bound_requirements != expected_requirements:
            raise C08ProjectionError(
                "C08 evaluator evidence kinds do not match bound public evidence"
            )


__all__ = [
    "c08_public_input_digest",
    "c08_public_observation_id",
    "compile_c08_truth",
    "project_c08_public",
    "validate_c08_truth_against_public",
]
