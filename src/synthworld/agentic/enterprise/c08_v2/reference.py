"""Deterministic fictional reference fixture for the enterprise C08 v2 surface."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid5

from synthworld.agentic.enterprise.c08_v2.models import (
    C08EvaluatorTruthV2,
    C08EvidenceKindV2,
    C08EvidenceObservationV2,
    C08PublicInputV2,
    C08SourceWorldV2,
    C08SubmissionV2,
)
from synthworld.agentic.enterprise.c08_v2.projection import (
    c08_public_input_digest,
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
_EXTRA_EVIDENCE_KIND = C08EvidenceKindV2.REVOCATION


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
    kind: C08EvidenceKindV2,
) -> str:
    suffix = _reference_id(
        seed, "evidence", action_index * 10 + kind_index
    ).split("-", 1)[1]
    return f"evidence-{kind.value}-{suffix}"


def _build_source(seed: int) -> C08SourceWorldV2:
    actions = []
    events = []
    sequence = 0
    for index, (action_name, required_kinds) in enumerate(_REFERENCE_ACTIONS):
        action_id = _reference_id(seed, "action", index)
        tenant_id = _reference_id(seed, "tenant", index)
        resource_id = _reference_id(seed, "resource", index)
        tick = index + 1
        required_ids = tuple(
            _evidence_id(seed, index, kind_index, kind)
            for kind_index, kind in enumerate(required_kinds)
        )
        actions.append(
            {
                "action_id": action_id,
                "tenant_id": tenant_id,
                "resource_id": resource_id,
                "action": action_name,
                "tick": tick,
                "required_evidence_kinds": required_kinds,
                "required_evidence_ids": required_ids,
            }
        )
        for kind_index, kind in enumerate((*required_kinds, _EXTRA_EVIDENCE_KIND)):
            extra_id = _reference_id(seed, "extra", index).split("-", 1)[1]
            evidence_id = (
                required_ids[kind_index]
                if kind_index < len(required_kinds)
                else f"evidence-{kind.value}-{extra_id}"
            )
            payload_digest = _reference_id(
                seed, "payload", index * 10 + kind_index
            ).split("-", 1)[1].ljust(64, "0")
            events.append(
                {
                    "sequence": sequence,
                    "evidence_id": evidence_id,
                    "action_id": action_id,
                    "tenant_id": tenant_id,
                    "resource_id": resource_id,
                    "action": action_name,
                    "tick": tick,
                    "kind": kind,
                    "payload_digest": payload_digest,
                }
            )
            sequence += 1
    return C08SourceWorldV2(actions=tuple(actions), evidence_events=tuple(events))


def reference_submission_from_public(public: C08PublicInputV2) -> C08SubmissionV2:
    """Construct the exact reference submission using only public evidence semantics."""

    events_by_semantics = {
        (event.action_id, event.kind): event for event in public.evidence_events
    }
    rows = tuple(
        (
            action.action_id,
            action.tenant_id,
            events_by_semantics[(action.action_id, kind)],
        )
        for action in public.actions
        for kind in action.required_evidence_kinds
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
