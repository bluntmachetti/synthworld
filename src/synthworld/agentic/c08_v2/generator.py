"""Deterministic Asteria C08 v2 public/evaluator generation."""

from __future__ import annotations

import hashlib
from uuid import UUID, uuid5

from synthworld.agentic.c08_v2.models import (
    C08_BENCHMARK_ID,
    C08_SCHEMA_VERSION,
    C08AsteriaBenchmarkV2,
    C08AsteriaEvaluatorV2,
    C08AsteriaPublicInputV2,
    C08AsteriaSubmissionV2,
    C08EvidenceBindingV2,
    C08EvidenceKind,
    C08EvidenceObservationV2,
    C08EvidenceRequirementV2,
    C08MeasurementScopeV2,
    C08PublicActionV2,
    C08ScenarioKind,
    C08SubmissionRowV2,
)
from synthworld.enterprise.canonical import canonical_json_bytes

_NAMESPACE = UUID("4d0df8e1-9f0d-5d21-9a10-4c5d10afc816")
_PROVES = (
    "offline comparison of submitted observation ids with evaluator bindings",
    "deterministic separation of public observations and evaluator requirements",
    "independent evidence-quality denominators over the generated action set",
)
_DOES_NOT_PROVE = (
    "live enforcement or production logging behavior",
    "compatibility with a real Asteria or EADS export",
    "secrecy against a reader who receives the evaluator artifact",
    "whether an omitted required observation was missing or "
    "discarded from the submission alone",
)


def _stable_named_id(seed: int, kind: str, stable_key: str) -> str:
    return str(uuid5(_NAMESPACE, f"{seed}:{kind}:{stable_key}"))


def _payload_digest(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _scope() -> C08MeasurementScopeV2:
    return C08MeasurementScopeV2(
        proves=tuple(sorted(_PROVES)),
        does_not_prove=tuple(sorted(_DOES_NOT_PROVE)),
    )


def generate_c08_asteria_v2(seed: int = 20260809) -> C08AsteriaBenchmarkV2:
    """Generate one deterministic synthetic benchmark with hidden evidence truth."""

    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("C08 seed must be an integer")
    if seed < 0:
        raise ValueError("C08 seed must be nonnegative")

    benchmark_id = C08_BENCHMARK_ID
    public_action_specs = (
        (
            "ledger-read",
            "read",
            ("read",),
            (C08EvidenceKind.AUTHORITY_RECORD, C08EvidenceKind.POLICY_RECORD),
        ),
        (
            "archive-read",
            "read",
            ("read",),
            (C08EvidenceKind.AUTHORITY_RECORD, C08EvidenceKind.POLICY_RECORD),
        ),
        (
            "register-write",
            "write",
            ("write",),
            (C08EvidenceKind.AUTHORITY_RECORD,),
        ),
        (
            "record-delete",
            "delete",
            ("delete",),
            (C08EvidenceKind.AUTHORITY_RECORD,),
        ),
        (
            "bundle-export",
            "export",
            ("export",),
            (C08EvidenceKind.AUTHORITY_RECORD,),
        ),
        (
            "catalogue-read",
            "read",
            ("read",),
            (C08EvidenceKind.AUTHORITY_RECORD,),
        ),
    )
    evaluator_scenarios = {
        "archive-read": C08ScenarioKind.MISSING,
        "bundle-export": C08ScenarioKind.EXTRA,
        "catalogue-read": C08ScenarioKind.DISCARDED,
        "ledger-read": C08ScenarioKind.EXACT,
        "record-delete": C08ScenarioKind.WRONG_ACTION,
        "register-write": C08ScenarioKind.FABRICATED,
    }
    ordered_action_specs = tuple(
        sorted(
            public_action_specs,
            key=lambda item: (
                _payload_digest(str(seed), "action-order", item[0]),
                item[0],
            ),
        )
    )
    public_actions: list[C08PublicActionV2] = []
    observation_specs: list[tuple[str, str, C08EvidenceKind, str, str]] = []
    bindings: list[C08EvidenceBindingV2] = []

    for action_index, (
        stable_key,
        action,
        scope,
        required_kinds,
    ) in enumerate(ordered_action_specs, start=1):
        action_id = _stable_named_id(seed, "action", stable_key)
        resource_id = _stable_named_id(seed, "resource", stable_key)
        requirements: list[C08EvidenceRequirementV2] = []
        action_observation_ids: list[str] = []
        for local_index, kind in enumerate(required_kinds, start=1):
            requirement_key = f"{stable_key}:{kind.value}:{local_index}"
            binding_handle = _stable_named_id(seed, "binding-handle", requirement_key)
            distractor_handle = _stable_named_id(
                seed, "distractor-binding-handle", requirement_key
            )
            requirements.append(
                C08EvidenceRequirementV2(
                    evidence_kind=kind,
                    binding_handle=binding_handle,
                )
            )
            required_observation_id = _stable_named_id(
                seed, "required-observation", requirement_key
            )
            distractor_observation_id = _stable_named_id(
                seed, "distractor-observation", requirement_key
            )
            action_observation_ids.append(required_observation_id)
            for observation_id, candidate_handle in (
                (required_observation_id, binding_handle),
                (distractor_observation_id, distractor_handle),
            ):
                ordering_key = _payload_digest(
                    str(seed), "candidate-order", observation_id
                )
                observation_specs.append(
                    (
                        ordering_key,
                        action_id,
                        kind,
                        candidate_handle,
                        observation_id,
                    )
                )
        public_actions.append(
            C08PublicActionV2(
                action_event_id=action_id,
                event_order=action_index,
                action=action,
                resource_id=resource_id,
                requested_scope=tuple(sorted(scope)),
                required_evidence=tuple(
                    sorted(
                        requirements,
                        key=lambda item: (
                            item.evidence_kind.value,
                            item.binding_handle,
                        ),
                    )
                ),
            )
        )
        bindings.append(
            C08EvidenceBindingV2(
                action_event_id=action_id,
                required_observation_ids=tuple(sorted(action_observation_ids)),
                scenario_kind=evaluator_scenarios[stable_key],
            )
        )

    observations = tuple(
        C08EvidenceObservationV2(
            observation_id=observation_id,
            action_event_id=action_id,
            observation_order=observation_order,
            evidence_kind=kind,
            binding_handle=binding_handle,
            payload_digest=_payload_digest(
                benchmark_id,
                str(seed),
                action_id,
                kind.value,
                binding_handle,
                observation_id,
            ),
        )
        for observation_order, (
            _,
            action_id,
            kind,
            binding_handle,
            observation_id,
        ) in enumerate(sorted(observation_specs), start=1)
    )

    public = C08AsteriaPublicInputV2(
        schema_version=C08_SCHEMA_VERSION,
        benchmark_id=benchmark_id,
        measurement_scope=_scope(),
        actions=tuple(public_actions),
        evidence_observations=observations,
    )
    public_digest = hashlib.sha256(canonical_json_bytes(public)).hexdigest()
    evaluator = C08AsteriaEvaluatorV2(
        schema_version=C08_SCHEMA_VERSION,
        benchmark_id=benchmark_id,
        public_input_digest=public_digest,
        measurement_scope=_scope(),
        bindings=tuple(sorted(bindings, key=lambda item: item.action_event_id)),
    )
    return C08AsteriaBenchmarkV2(
        schema_version=C08_SCHEMA_VERSION,
        benchmark_id=benchmark_id,
        public=public,
        evaluator=evaluator,
    )


def reference_c08_submission(
    benchmark: C08AsteriaBenchmarkV2,
) -> C08AsteriaSubmissionV2:
    """Build evaluator-side reference output; its bindings are never public input."""

    return C08AsteriaSubmissionV2(
        schema_version=C08_SCHEMA_VERSION,
        benchmark_id=benchmark.benchmark_id,
        public_input_digest=hashlib.sha256(
            canonical_json_bytes(benchmark.public)
        ).hexdigest(),
        rows=tuple(
            C08SubmissionRowV2(
                action_event_id=binding.action_event_id,
                retained_observation_ids=tuple(
                    sorted(binding.required_observation_ids)
                ),
            )
            for binding in sorted(
                benchmark.evaluator.bindings,
                key=lambda item: item.action_event_id,
            )
        ),
    )


def semantic_c08_submission(
    public: C08AsteriaPublicInputV2,
) -> C08AsteriaSubmissionV2:
    """Construct a submission from public correlation semantics alone."""

    observations_by_action: dict[str, list[C08EvidenceObservationV2]] = {}
    for observation in public.evidence_observations:
        observations_by_action.setdefault(observation.action_event_id, []).append(
            observation
        )
    rows: list[C08SubmissionRowV2] = []
    for action in public.actions:
        selected: list[str] = []
        action_observations = observations_by_action.get(action.action_event_id, [])
        for requirement in action.required_evidence:
            matches = [
                item
                for item in action_observations
                if item.evidence_kind is requirement.evidence_kind
                and item.binding_handle == requirement.binding_handle
            ]
            if len(matches) != 1:
                raise ValueError(
                    "public evidence requirement is not uniquely solvable for "
                    f"{action.action_event_id}:"
                    f"{requirement.evidence_kind.value}:"
                    f"{requirement.binding_handle}"
                )
            selected.append(matches[0].observation_id)
        rows.append(
            C08SubmissionRowV2(
                action_event_id=action.action_event_id,
                retained_observation_ids=tuple(sorted(selected)),
            )
        )
    return C08AsteriaSubmissionV2(
        public_input_digest=hashlib.sha256(canonical_json_bytes(public)).hexdigest(),
        rows=tuple(sorted(rows, key=lambda item: item.action_event_id)),
    )


__all__ = [
    "generate_c08_asteria_v2",
    "reference_c08_submission",
    "semantic_c08_submission",
]
