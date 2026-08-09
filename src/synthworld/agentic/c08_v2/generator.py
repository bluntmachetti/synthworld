"""Deterministic Asteria C08 v2 public/evaluator generation."""

from __future__ import annotations

import hashlib
from uuid import UUID, uuid5

from synthworld.enterprise.canonical import canonical_json_bytes

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
    C08MeasurementScopeV2,
    C08PublicActionV2,
    C08ScenarioKind,
    C08SubmissionRowV2,
)

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
    "whether an omitted required observation was missing or discarded from the submission alone",
)


def _stable_id(seed: int, kind: str, ordinal: int) -> str:
    return str(uuid5(_NAMESPACE, f"{seed}:{kind}:{ordinal}"))


def _payload_digest(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _scope() -> C08MeasurementScopeV2:
    return C08MeasurementScopeV2(proves=_PROVES, does_not_prove=_DOES_NOT_PROVE)


def generate_c08_asteria_v2(seed: int = 20260809) -> C08AsteriaBenchmarkV2:
    """Generate one deterministic synthetic benchmark with hidden evidence truth."""

    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("C08 seed must be an integer")
    if seed < 0:
        raise ValueError("C08 seed must be nonnegative")

    benchmark_id = C08_BENCHMARK_ID
    action_specs = (
        ("read", "resource-001", ("read",), C08ScenarioKind.EXACT, (C08EvidenceKind.AUTHORITY_RECORD, C08EvidenceKind.POLICY_RECORD)),
        ("read", "resource-002", ("read",), C08ScenarioKind.MISSING, (C08EvidenceKind.AUTHORITY_RECORD, C08EvidenceKind.POLICY_RECORD)),
        ("write", "resource-003", ("write",), C08ScenarioKind.FABRICATED, (C08EvidenceKind.AUTHORITY_RECORD,)),
        ("delete", "resource-004", ("delete",), C08ScenarioKind.WRONG_ACTION, (C08EvidenceKind.AUTHORITY_RECORD,)),
        ("export", "resource-005", ("export",), C08ScenarioKind.EXTRA, (C08EvidenceKind.AUTHORITY_RECORD,)),
        ("read", "resource-006", ("read",), C08ScenarioKind.DISCARDED, (C08EvidenceKind.AUTHORITY_RECORD,)),
    )
    public_actions: list[C08PublicActionV2] = []
    observations: list[C08EvidenceObservationV2] = []
    bindings: list[C08EvidenceBindingV2] = []
    observation_order = 0

    for action_index, (
        action,
        resource_id,
        scope,
        scenario,
        required_kinds,
    ) in enumerate(
        action_specs, start=1
    ):
        action_id = _stable_id(seed, "action", action_index)
        public_actions.append(
            C08PublicActionV2(
                action_event_id=action_id,
                event_order=action_index,
                action=action,
                resource_id=resource_id,
                requested_scope=scope,
                required_evidence_kinds=required_kinds,
            )
        )
        observation_count = 3 if scenario in {C08ScenarioKind.EXTRA, C08ScenarioKind.DISCARDED} else 2
        action_observation_ids: list[str] = []
        required_count = 2 if scenario in {C08ScenarioKind.EXACT, C08ScenarioKind.MISSING} else 1
        for local_index in range(1, observation_count + 1):
            observation_order += 1
            observation_id = _stable_id(
                seed, "observation", action_index * 10 + local_index
            )
            kind = (
                C08EvidenceKind.AUTHORITY_RECORD
                if local_index == 1
                else C08EvidenceKind.POLICY_RECORD
            )
            observations.append(
                C08EvidenceObservationV2(
                    observation_id=observation_id,
                    action_event_id=action_id,
                    observation_order=observation_order,
                    evidence_kind=kind,
                    payload_digest=_payload_digest(
                        benchmark_id,
                        str(seed),
                        action_id,
                        observation_id,
                    ),
                )
            )
            if local_index <= required_count:
                action_observation_ids.append(observation_id)
        bindings.append(
            C08EvidenceBindingV2(
                action_event_id=action_id,
                required_observation_ids=tuple(action_observation_ids),
                scenario_kind=scenario,
            )
        )

    public = C08AsteriaPublicInputV2(
        schema_version=C08_SCHEMA_VERSION,
        benchmark_id=benchmark_id,
        measurement_scope=_scope(),
        actions=tuple(public_actions),
        evidence_observations=tuple(observations),
    )
    public_digest = hashlib.sha256(canonical_json_bytes(public)).hexdigest()
    evaluator = C08AsteriaEvaluatorV2(
        schema_version=C08_SCHEMA_VERSION,
        benchmark_id=benchmark_id,
        public_input_digest=public_digest,
        measurement_scope=_scope(),
        bindings=tuple(bindings),
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
                retained_observation_ids=binding.required_observation_ids,
            )
            for binding in benchmark.evaluator.bindings
        ),
    )


def semantic_c08_submission(
    public: C08AsteriaPublicInputV2,
) -> C08AsteriaSubmissionV2:
    """Construct a submission from public requirement kinds, not evaluator truth."""

    observations_by_action: dict[str, list[C08EvidenceObservationV2]] = {}
    for observation in public.evidence_observations:
        observations_by_action.setdefault(observation.action_event_id, []).append(
            observation
        )
    rows: list[C08SubmissionRowV2] = []
    for action in public.actions:
        selected: list[str] = []
        action_observations = observations_by_action.get(action.action_event_id, [])
        for kind in action.required_evidence_kinds:
            matches = [
                item for item in action_observations if item.evidence_kind is kind
            ]
            if len(matches) != 1:
                raise ValueError(
                    "public evidence requirement is not uniquely solvable for "
                    f"{action.action_event_id}:{kind.value}"
                )
            selected.append(matches[0].observation_id)
        rows.append(
            C08SubmissionRowV2(
                action_event_id=action.action_event_id,
                retained_observation_ids=tuple(selected),
            )
        )
    return C08AsteriaSubmissionV2(
        public_input_digest=hashlib.sha256(canonical_json_bytes(public)).hexdigest(),
        rows=tuple(rows),
    )


__all__ = [
    "generate_c08_asteria_v2",
    "reference_c08_submission",
    "semantic_c08_submission",
]
