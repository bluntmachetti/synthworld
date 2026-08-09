"""Deterministic fictional reference fixture for the enterprise C08 v2 surface."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import UUID, uuid5

from synthworld.agentic.enterprise.c08_v2.models import (
    C08EvaluatorTruthV2,
    C08EvidenceEventV2,
    C08EvidenceKindV2,
    C08EvidenceObservationV2,
    C08EvidenceRequirementV2,
    C08PublicInputV2,
    C08SourceWorldV2,
    C08SubmissionV2,
)
from synthworld.agentic.enterprise.c08_v2.projection import (
    c08_public_input_digest,
    c08_public_observation_id,
    compile_c08_truth,
    project_c08_public,
)

C08_REFERENCE_NAMESPACE = UUID("9d4e2cc4-9a27-5fc2-8f30-cf5a5c4f9d7e")
DEFAULT_C08_REFERENCE_SEED = 20260809
_REFERENCE_ACTIONS = (
    ("read", (C08EvidenceKindV2.AUTHORITY, C08EvidenceKindV2.IDENTITY)),
    ("write", (C08EvidenceKindV2.IDENTITY, C08EvidenceKindV2.POLICY)),
    ("delete", (C08EvidenceKindV2.AUTHORITY, C08EvidenceKindV2.POLICY)),
)


@dataclass(frozen=True, slots=True)
class C08ReferenceBundleV2:
    """Separate source, public, evaluator, and reference-submission artifacts."""

    seed: int
    source: C08SourceWorldV2
    public: C08PublicInputV2
    evaluator: C08EvaluatorTruthV2
    reference_submission: C08SubmissionV2


def _reference_id(seed: int, category: str, index: int) -> str:
    value = uuid5(
        C08_REFERENCE_NAMESPACE,
        f"seed={seed};category={category};index={index}",
    )
    return f"{category}-{value.hex[:16]}"


def _evidence_id(
    seed: int,
    action_index: int,
    kind_index: int,
    candidate_index: int,
    kind: C08EvidenceKindV2,
) -> str:
    suffix = _reference_id(
        seed,
        "evidence",
        action_index * 100 + kind_index * 10 + candidate_index,
    ).split("-", 1)[1]
    return f"evidence-{kind.value}-{suffix}"


def _binding_handle(
    seed: int,
    action_index: int,
    kind_index: int,
    candidate_index: int,
) -> str:
    value = uuid5(
        C08_REFERENCE_NAMESPACE,
        f"binding-handle:{seed}:{action_index}:{kind_index}:{candidate_index}",
    )
    return f"c08h_{value.hex}"


def _build_source(seed: int) -> C08SourceWorldV2:
    actions = []
    events = []
    for index, (action_name, required_kinds) in enumerate(_REFERENCE_ACTIONS):
        action_id = _reference_id(seed, "action", index)
        tenant_id = _reference_id(seed, "tenant", index)
        resource_id = _reference_id(seed, "resource", index)
        tick = index + 1
        requirements = tuple(
            C08EvidenceRequirementV2(
                kind=kind,
                binding_handle=_binding_handle(seed, index, kind_index, 0),
            )
            for kind_index, kind in enumerate(required_kinds)
        )
        required_ids = tuple(
            sorted(
                _evidence_id(seed, index, kind_index, 0, kind)
                for kind_index, kind in enumerate(required_kinds)
            )
        )
        actions.append(
            {
                "action_id": action_id,
                "tenant_id": tenant_id,
                "resource_id": resource_id,
                "action": action_name,
                "tick": tick,
                "required_evidence": requirements,
                "required_evidence_ids": required_ids,
            }
        )
        for kind_index, kind in enumerate(required_kinds):
            for candidate_index in (0, 1):
                evidence_id = _evidence_id(
                    seed,
                    index,
                    kind_index,
                    candidate_index,
                    kind,
                )
                events.append(
                    {
                        "sequence": 0,
                        "evidence_id": evidence_id,
                        "action_id": action_id,
                        "tenant_id": tenant_id,
                        "resource_id": resource_id,
                        "action": action_name,
                        "tick": tick,
                        "kind": kind,
                        "binding_handle": _binding_handle(
                            seed,
                            index,
                            kind_index,
                            candidate_index,
                        ),
                        "payload_digest": hashlib.sha256(
                            f"{seed}:{evidence_id}:payload".encode()
                        ).hexdigest(),
                    }
                )
    ordered_events = sorted(
        events,
        key=lambda item: c08_public_observation_id(str(item["evidence_id"])),
    )
    for sequence, event in enumerate(ordered_events):
        event["sequence"] = sequence
    return C08SourceWorldV2(
        actions=tuple(actions),
        evidence_events=tuple(ordered_events),
    )


def reference_submission_from_public(public: C08PublicInputV2) -> C08SubmissionV2:
    """Construct the exact reference submission using only public evidence semantics."""

    events_by_semantics: dict[
        tuple[str, C08EvidenceKindV2, str], C08EvidenceEventV2
    ] = {}
    for event in public.evidence_events:
        key = (event.action_id, event.kind, event.binding_handle)
        if key in events_by_semantics:
            raise ValueError(
                "C08 public evidence is ambiguous for an action/kind/handle"
            )
        events_by_semantics[key] = event
    rows = tuple(
        (
            action.action_id,
            action.tenant_id,
            events_by_semantics[
                (action.action_id, requirement.kind, requirement.binding_handle)
            ],
        )
        for action in public.actions
        for requirement in action.required_evidence
    )
    return C08SubmissionV2(
        public_input_digest=c08_public_input_digest(public),
        observations=tuple(
            C08EvidenceObservationV2(
                observation_id=f"reference-observation-{index}",
                sequence=index,
                action_id=action_id,
                tenant_id=tenant_id,
                evidence_id=event.evidence_id,
            )
            for index, (action_id, tenant_id, event) in enumerate(rows)
        ),
    )


def generate_c08_reference(
    seed: int = DEFAULT_C08_REFERENCE_SEED,
) -> C08ReferenceBundleV2:
    """Generate a bounded, deterministic C08 v2 reference bundle."""

    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("C08 reference seed must be a nonnegative integer")
    source = _build_source(seed)
    public = project_c08_public(source)
    evaluator = compile_c08_truth(source, public)
    return C08ReferenceBundleV2(
        seed=seed,
        source=source,
        public=public,
        evaluator=evaluator,
        reference_submission=reference_submission_from_public(public),
    )


__all__ = [
    "C08_REFERENCE_NAMESPACE",
    "DEFAULT_C08_REFERENCE_SEED",
    "C08ReferenceBundleV2",
    "generate_c08_reference",
    "reference_submission_from_public",
]
