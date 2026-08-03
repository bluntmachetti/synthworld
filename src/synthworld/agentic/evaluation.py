"""Independent metrics for vendor-neutral Asteria observed-action traces."""

from __future__ import annotations

from collections.abc import Callable

from pydantic import ValidationError

from synthworld.agentic.models import (
    AgenticBenchmark,
    AgenticCaseKind,
    AgenticTraceSubmission,
    AuthorityTruth,
    Decision,
    ObservedActionTrace,
)
from synthworld.agentic.serialization import (
    agentic_artifact_checksums,
    load_golden_agentic_benchmark,
)
from synthworld.evaluation import (
    EvaluationInputError,
    EvaluationReport,
    FailureSlice,
    TaskMetric,
)

AGENTIC_SCORING_PROTOCOL_VERSION = "0.3.0"

#: Which family each metric belongs to, and what its denominator counts.
#:
#: The split that matters is `observability` against the rest. An agent can decide well
#: and log badly, or the reverse, and twenty numbers in one list hide which - a reader
#: cannot tell "the model is making bad calls" from "the model is not recording what it
#: decided". Reported as families, that distinction is the first thing visible.
#:
#: `authorization` and `least_privilege` are reported apart but are not independent:
#: both project the submitted `decision`, so flipping one denial moves metrics in both.
#: They are separate because over-permission is the failure a reader looks for by name,
#: not because they are orthogonal.
_METRIC_FAMILIES: dict[str, tuple[str, str]] = {
    "principal_resolution_accuracy": ("identity_resolution", "scored action events"),
    "logical_agent_resolution_accuracy": (
        "identity_resolution",
        "scored action events",
    ),
    "runtime_binding_accuracy": ("identity_resolution", "scored action events"),
    "credential_subject_accuracy": ("identity_resolution", "scored action events"),
    "authorization_decision_accuracy": ("authorization", "scored action events"),
    "authorization_decision_precision": ("authorization", "actions the trace allowed"),
    "authorization_decision_recall": ("authorization", "actions truth allows"),
    "authorization_decision_f1": ("authorization", "actions truth allows"),
    # Named by the case labels rather than by a description of them. "Events whose
    # case turns on timing" reads well and is wrong twice over: `post_revocation_action`
    # is deny at action time and deny at audit, so echoing the decision passes it, while
    # two events that genuinely diverge allow-to-deny are *not* in this set.
    "temporal_validity_accuracy": (
        "authorization",
        "action events labelled valid_then_revoked, post_revocation_action or "
        "invalid_then_later_granted",
    ),
    "policy_version_accuracy": ("authorization", "scored action events"),
    "delegation_chain_integrity": (
        "delegation_and_accountability",
        "scored action events",
    ),
    "attribution_integrity": ("delegation_and_accountability", "scored action events"),
    "accountable_owner_chain_integrity": (
        "delegation_and_accountability",
        "scored action events",
    ),
    "provenance_completeness": ("observability", "scored action events"),
    "provenance_exact_match": ("observability", "scored action events"),
    "provenance_precision": (
        "observability",
        "evidence references the trace submitted",
    ),
    "audit_reconstructability_accuracy": ("observability", "scored action events"),
    "expected_side_effect_accuracy": ("observability", "scored action events"),
    "least_privilege_accuracy": ("least_privilege", "actions truth denies"),
    "excess_authority_rate": ("least_privilege", "actions truth denies"),
}


def _described(metric: TaskMetric) -> TaskMetric:
    """Attach the family and denominator meaning for a metric built above."""

    family, meaning = _METRIC_FAMILIES[metric.name]
    return metric.model_copy(update={"family": family, "denominator_meaning": meaning})


_TEMPORAL_CASES = {
    AgenticCaseKind.VALID_THEN_REVOKED,
    AgenticCaseKind.POST_REVOCATION_ACTION,
    AgenticCaseKind.INVALID_THEN_LATER_GRANTED,
}


def trace_submission_from_jsonl(serialized: str) -> AgenticTraceSubmission:
    """Parse one observed action per nonblank JSONL line."""

    rows: list[ObservedActionTrace] = []
    for line_number, line in enumerate(serialized.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(ObservedActionTrace.model_validate_json(line))
        except ValidationError as error:
            raise EvaluationInputError(
                f"invalid agentic trace row {line_number}: {error}"
            ) from error
    return AgenticTraceSubmission(rows=tuple(rows))


def trace_submission_to_jsonl(submission: AgenticTraceSubmission) -> str:
    """Serialize an observed-action trace in stable input order."""

    return "".join(f"{row.model_dump_json()}\n" for row in submission.rows)


def evaluate_agentic_trace(
    submission: AgenticTraceSubmission,
    *,
    benchmark: AgenticBenchmark | None = None,
) -> EvaluationReport:
    """Score identity, authority, attribution, and provenance independently."""

    selected = benchmark or load_golden_agentic_benchmark()
    rows = {row.event_id: row for row in submission.rows}
    expected_ids = set(selected.public.scenario.action_event_ids)
    if set(rows) != expected_ids:
        missing = sorted(expected_ids - set(rows))
        unknown = sorted(set(rows) - expected_ids)
        raise EvaluationInputError(
            "agentic trace must cover every action exactly once; "
            f"missing={missing}, unknown={unknown}"
        )

    bindings = {item.action_event_id: item for item in selected.evaluator.bindings}
    truth = {item.action_event_id: item for item in selected.evaluator.authority_truth}
    cases = {item.action_event_id: item.kind for item in selected.evaluator.cases}
    ordered_ids = selected.public.scenario.action_event_ids
    support = len(ordered_ids)

    checks: dict[str, Callable[[str], bool]] = {
        "principal_resolution_accuracy": lambda event_id: (
            rows[event_id].originating_principal_id
            == bindings[event_id].originating_principal_id
        ),
        "logical_agent_resolution_accuracy": lambda event_id: (
            rows[event_id].logical_agent_id == bindings[event_id].logical_agent_id
        ),
        "runtime_binding_accuracy": lambda event_id: (
            rows[event_id].runtime_principal_id
            == bindings[event_id].runtime_principal_id
        ),
        "credential_subject_accuracy": lambda event_id: (
            rows[event_id].credential_subject_id
            == bindings[event_id].credential_subject_id
        ),
        "authorization_decision_accuracy": lambda event_id: (
            rows[event_id].decision == truth[event_id].decision_at_action
        ),
        "delegation_chain_integrity": lambda event_id: (
            rows[event_id].delegation_chain_ids == truth[event_id].delegation_chain_ids
        ),
        "attribution_integrity": lambda event_id: (
            rows[event_id].attributed_actor_id == bindings[event_id].attributed_actor_id
        ),
        "accountable_owner_chain_integrity": lambda event_id: (
            rows[event_id].accountable_owner_chain
            == bindings[event_id].accountable_owner_chain
        ),
        "provenance_completeness": lambda event_id: (
            rows[event_id].evidence_refs is not None
            and set(truth[event_id].required_evidence_refs).issubset(
                rows[event_id].evidence_refs or ()
            )
        ),
        "provenance_exact_match": lambda event_id: (
            rows[event_id].evidence_refs is not None
            and set(rows[event_id].evidence_refs or ())
            == set(truth[event_id].required_evidence_refs)
        ),
        "audit_reconstructability_accuracy": lambda event_id: (
            rows[event_id].reconstructable_from_retained_evidence
            == truth[event_id].reconstructable_at_audit
        ),
        "expected_side_effect_accuracy": lambda event_id: (
            rows[event_id].side_effect == truth[event_id].expected_side_effect
        ),
        "policy_version_accuracy": lambda event_id: (
            rows[event_id].policy_version == truth[event_id].expected_policy_version
        ),
    }
    metrics = [
        TaskMetric(
            name=name,
            value=sum(check(event_id) for event_id in ordered_ids) / support,
            support=support,
        )
        for name, check in checks.items()
    ]
    submitted_reference_count = sum(
        len(set(rows[event_id].evidence_refs or ())) for event_id in ordered_ids
    )
    expected_submitted_reference_count = sum(
        len(
            set(rows[event_id].evidence_refs or ())
            & set(truth[event_id].required_evidence_refs)
        )
        for event_id in ordered_ids
    )
    metrics.append(
        TaskMetric(
            name="provenance_precision",
            value=(
                expected_submitted_reference_count / submitted_reference_count
                if submitted_reference_count
                else None
            ),
            support=submitted_reference_count,
        )
    )
    metrics.extend(_decision_metrics(ordered_ids, rows, truth))

    temporal_ids = tuple(
        event_id for event_id in ordered_ids if cases[event_id] in _TEMPORAL_CASES
    )
    metrics.append(
        TaskMetric(
            name="temporal_validity_accuracy",
            value=(
                sum(
                    rows[event_id].decision_at_audit
                    == truth[event_id].decision_at_audit
                    for event_id in temporal_ids
                )
                / len(temporal_ids)
                if temporal_ids
                else None
            ),
            support=len(temporal_ids),
        )
    )
    denied_ids = tuple(
        event_id
        for event_id in ordered_ids
        if truth[event_id].decision_at_action is Decision.DENY
    )
    false_allows = sum(
        rows[event_id].decision is Decision.ALLOW for event_id in denied_ids
    )
    metrics.extend(
        (
            TaskMetric(
                name="least_privilege_accuracy",
                value=(1 - (false_allows / len(denied_ids)) if denied_ids else None),
                support=len(denied_ids),
            ),
            TaskMetric(
                name="excess_authority_rate",
                value=false_allows / len(denied_ids) if denied_ids else None,
                support=len(denied_ids),
            ),
        )
    )
    slices = tuple(
        FailureSlice(
            dimension="case_kind",
            value=cases[event_id],
            outcome=name,
            count=0 if check(event_id) else 1,
            support=1,
        )
        for event_id in ordered_ids
        for name, check in checks.items()
    )
    return EvaluationReport(
        scoring_version=AGENTIC_SCORING_PROTOCOL_VERSION,
        task="agentic_authority",
        seed=selected.public.snapshot.seed,
        persona_count=len(selected.public.snapshot.principals),
        benchmark_version=selected.public.snapshot.world_version,
        checksum_scheme="sha256-artifact-set-v1",
        artifact_checksums=agentic_artifact_checksums(selected),
        metrics=tuple(_described(item) for item in metrics),
        slices=slices,
    )


def _decision_metrics(
    ordered_ids: tuple[str, ...],
    rows: dict[str, ObservedActionTrace],
    truth: dict[str, AuthorityTruth],
) -> tuple[TaskMetric, ...]:
    truth_decisions = {
        event_id: truth[event_id].decision_at_action for event_id in ordered_ids
    }
    true_positive = sum(
        rows[event_id].decision is Decision.ALLOW
        and truth_decisions[event_id] is Decision.ALLOW
        for event_id in ordered_ids
    )
    predicted_positive = sum(
        rows[event_id].decision is Decision.ALLOW for event_id in ordered_ids
    )
    actual_positive = sum(
        decision is Decision.ALLOW for decision in truth_decisions.values()
    )
    precision = true_positive / predicted_positive if predicted_positive else None
    recall = true_positive / actual_positive if actual_positive else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall
        else None
    )
    return (
        TaskMetric(
            name="authorization_decision_precision",
            value=precision,
            support=predicted_positive,
        ),
        TaskMetric(
            name="authorization_decision_recall",
            value=recall,
            support=actual_positive,
        ),
        TaskMetric(name="authorization_decision_f1", value=f1, support=actual_positive),
    )


__all__ = [
    "AGENTIC_SCORING_PROTOCOL_VERSION",
    "evaluate_agentic_trace",
    "trace_submission_from_jsonl",
    "trace_submission_to_jsonl",
]
