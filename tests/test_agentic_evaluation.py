from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from synthworld.agentic import (
    always_deny_agentic_trace,
    baselines,
    current_state_agentic_trace,
    evaluate_agentic_trace,
    generate_asteria_agentic_v1,
    reference_agentic_trace,
    trace_submission_from_jsonl,
    trace_submission_to_jsonl,
)
from synthworld.agentic.models import (
    ActionAttempted,
    AgenticCaseKind,
    AgenticPublicBundle,
    AgenticTraceSubmission,
    Decision,
    ObservedActionTrace,
)
from synthworld.agentic.replay import AgenticReplayError
from synthworld.evaluation import EvaluationInputError, EvaluationReport


def test_reference_trace_scores_every_independent_dimension() -> None:
    benchmark = generate_asteria_agentic_v1()
    submission = reference_agentic_trace(benchmark)
    report = evaluate_agentic_trace(submission, benchmark=benchmark)
    metrics = {item.name: item.value for item in report.metrics}

    assert report.task == "agentic_authority"
    assert report.scoring_version == "0.3.0"
    assert report.checksum_scheme == "sha256-artifact-set-v1"
    assert metrics["excess_authority_rate"] == 0.0
    assert all(
        value == 1.0
        for name, value in metrics.items()
        if name != "excess_authority_rate"
    )
    assert len(report.slices) == 11 * 13
    assert not any(item.count for item in report.slices)
    assert dict(report.artifact_checksums).keys() == {"public", "evaluator"}


def test_jsonl_round_trip_and_default_frozen_evaluator() -> None:
    benchmark = generate_asteria_agentic_v1()
    serialized = trace_submission_to_jsonl(reference_agentic_trace(benchmark))
    parsed = trace_submission_from_jsonl(f"\n{serialized}\n")
    assert parsed == reference_agentic_trace(benchmark)
    assert evaluate_agentic_trace(parsed).task == "agentic_authority"


def test_naive_baselines_expose_decision_temporal_and_provenance_failures() -> None:
    benchmark = generate_asteria_agentic_v1()
    deny = evaluate_agentic_trace(
        always_deny_agentic_trace(benchmark.public), benchmark=benchmark
    )
    current = evaluate_agentic_trace(
        current_state_agentic_trace(benchmark.public), benchmark=benchmark
    )
    deny_metrics = {item.name: item.value for item in deny.metrics}
    current_metrics = {item.name: item.value for item in current.metrics}

    assert deny_metrics["authorization_decision_recall"] == 0.0
    assert deny_metrics["authorization_decision_precision"] is None
    assert deny_metrics["authorization_decision_f1"] is None
    assert deny_metrics["accountable_owner_chain_integrity"] == 0.0
    assert current_metrics["temporal_validity_accuracy"] == 1.0
    decision_accuracy = current_metrics["authorization_decision_accuracy"]
    attribution_accuracy = current_metrics["attribution_integrity"]
    assert decision_accuracy is not None and decision_accuracy < 1.0
    assert attribution_accuracy is not None and attribution_accuracy < 1.0
    assert any(item.count for item in current.slices)


def test_missing_provenance_does_not_hide_a_correct_decision() -> None:
    benchmark = generate_asteria_agentic_v1()
    perfect = reference_agentic_trace(benchmark)
    first = perfect.rows[0].model_copy(update={"evidence_refs": ()})
    report = evaluate_agentic_trace(
        perfect.model_copy(update={"rows": (first, *perfect.rows[1:])}),
        benchmark=benchmark,
    )
    metrics = {item.name: item.value for item in report.metrics}
    assert metrics["authorization_decision_accuracy"] == 1.0
    provenance = metrics["provenance_completeness"]
    assert provenance is not None and provenance < 1.0
    exact = metrics["provenance_exact_match"]
    assert exact is not None and exact < 1.0


def test_fabricated_provenance_lowers_exact_match_and_micro_precision() -> None:
    benchmark = generate_asteria_agentic_v1()
    perfect = reference_agentic_trace(benchmark)
    expected_support = sum(len(row.evidence_refs or ()) for row in perfect.rows)
    first = perfect.rows[0].model_copy(
        update={
            "evidence_refs": (
                *(perfect.rows[0].evidence_refs or ()),
                "evidence:fabricated",
            )
        }
    )
    second = perfect.rows[1].model_copy(
        update={
            "evidence_refs": (
                *(perfect.rows[1].evidence_refs or ()),
                "evidence:fabricated",
            )
        }
    )
    report = evaluate_agentic_trace(
        perfect.model_copy(update={"rows": (first, second, *perfect.rows[2:])}),
        benchmark=benchmark,
    )
    metrics = {item.name: item for item in report.metrics}
    assert metrics["provenance_completeness"].value == 1.0
    assert metrics["provenance_exact_match"].value == 9 / 11
    assert metrics["provenance_precision"].value == expected_support / (
        expected_support + 2
    )
    assert metrics["provenance_precision"].support == expected_support + 2


def test_empty_provenance_has_zero_precision_support() -> None:
    benchmark = generate_asteria_agentic_v1()
    perfect = reference_agentic_trace(benchmark)
    empty = perfect.model_copy(
        update={
            "rows": tuple(
                row.model_copy(update={"evidence_refs": None}) for row in perfect.rows
            )
        }
    )
    report = evaluate_agentic_trace(empty, benchmark=benchmark)
    metrics = {item.name: item for item in report.metrics}
    assert metrics["provenance_completeness"].value == 0.0
    assert metrics["provenance_exact_match"].value == 0.0
    assert metrics["provenance_precision"].value is None
    assert metrics["provenance_precision"].support == 0


def test_non_temporal_and_all_allow_world_have_defined_empty_support() -> None:
    """A metric with no applicable case must read ``None``/0, never 0.0.

    Relabelling every case to a non-temporal kind empties ``_TEMPORAL_CASES``. An
    earlier revision used an invented ``"custom_case"`` label for this, which stopped
    being constructible once ``AgenticCase.kind`` became a closed vocabulary - and an
    arbitrary string was never what the test needed, only a world with no temporal
    cases in it.
    """

    benchmark = generate_asteria_agentic_v1()
    custom_cases = tuple(
        item.model_copy(update={"kind": AgenticCaseKind.AUTHORISED_ACTION})
        for item in benchmark.evaluator.cases
    )
    all_allow_truth = tuple(
        item.model_copy(
            update={
                "decision_at_action": Decision.ALLOW,
                "decision_at_audit": Decision.ALLOW,
            }
        )
        for item in benchmark.evaluator.authority_truth
    )
    custom = benchmark.model_copy(
        update={
            "evaluator": benchmark.evaluator.model_copy(
                update={"cases": custom_cases, "authority_truth": all_allow_truth}
            )
        }
    )
    report = evaluate_agentic_trace(reference_agentic_trace(custom), benchmark=custom)
    metrics = {item.name: item for item in report.metrics}
    assert metrics["temporal_validity_accuracy"].value is None
    assert metrics["temporal_validity_accuracy"].support == 0
    assert metrics["least_privilege_accuracy"].value is None
    assert metrics["excess_authority_rate"].value is None


def test_agentic_evaluator_rejects_missing_unknown_and_duplicate_rows() -> None:
    benchmark = generate_asteria_agentic_v1()
    perfect = reference_agentic_trace(benchmark)
    with pytest.raises(EvaluationInputError, match="missing"):
        evaluate_agentic_trace(
            perfect.model_copy(update={"rows": perfect.rows[1:]}), benchmark=benchmark
        )
    unknown = perfect.rows[0].model_copy(update={"event_id": "evt-unknown"})
    with pytest.raises(EvaluationInputError, match="unknown"):
        evaluate_agentic_trace(
            perfect.model_copy(update={"rows": (unknown, *perfect.rows[1:])}),
            benchmark=benchmark,
        )
    with pytest.raises(ValidationError, match="unique"):
        AgenticTraceSubmission(rows=(perfect.rows[0], perfect.rows[0]))


def test_jsonl_parser_reports_the_bad_line() -> None:
    with pytest.raises(EvaluationInputError, match="row 2"):
        trace_submission_from_jsonl('{"event_id":"evt-ok"}\n{"event_id": 12}\n')


def test_observed_trace_requires_utc_when_timestamp_is_present() -> None:
    with pytest.raises(ValidationError, match="UTC"):
        ObservedActionTrace.model_validate(
            {"event_id": "evt-test", "timestamp": "2026-01-01T12:00:00"}
        )
    assert ObservedActionTrace(event_id="evt-none", timestamp=None).timestamp is None


def test_public_baselines_reject_incomplete_claims_and_nonactions() -> None:
    benchmark = generate_asteria_agentic_v1()
    events = list(benchmark.public.events)
    action = events[9]
    assert isinstance(action.payload, ActionAttempted)
    attempt = action.payload.attempt.model_copy(update={"logical_agent_claim": None})
    events[9] = action.model_copy(
        update={"payload": action.payload.model_copy(update={"attempt": attempt})}
    )
    public = AgenticPublicBundle(
        snapshot=benchmark.public.snapshot,
        events=tuple(events),
        scenario=benchmark.public.scenario,
    )
    with pytest.raises(AgenticReplayError, match="complete public identity"):
        current_state_agentic_trace(public)
    with pytest.raises(AgenticReplayError, match="non-action"):
        baselines._public_row(
            benchmark.public.events[0], benchmark.public, decision=Decision.DENY
        )


def test_every_metric_names_its_family_and_denominator() -> None:
    """A report a reader cannot re-derive is one they have to trust.

    Ambiguity, search and broker scoring all publish denominators; the agentic
    surface predates that convention and shipped twenty metrics as one flat list with
    nothing saying what `support` counted. An external reviewer had to reverse-engineer
    `temporal_validity_accuracy` by diffing scores between two agent policies.
    """

    benchmark = generate_asteria_agentic_v1()
    report = evaluate_agentic_trace(
        reference_agentic_trace(benchmark), benchmark=benchmark
    )

    assert report.metrics
    for metric in report.metrics:
        assert metric.family, metric.name
        assert metric.support_meaning, metric.name
        if metric.value is not None:
            assert 0.0 <= metric.value <= 1.0

    # For every metric but F1, support really is the denominator, so the numerator is
    # an integer. F1 is excluded because it is computed from precision and recall -
    # which is exactly why the field is named for support rather than for a denominator.
    for metric in report.metrics:
        if metric.name == "authorization_decision_f1" or not metric.support:
            continue
        if metric.value is not None:
            numerator = metric.value * metric.support
            assert abs(numerator - round(numerator)) < 1e-9, metric.name


def _named(report: EvaluationReport) -> dict[str, float | None]:
    return {metric.name: metric.value for metric in report.metrics}


def test_metrics_separate_deciding_well_from_recording_well() -> None:
    """The split the families exist for, demonstrated rather than asserted.

    An earlier version checked only that family *labels* appeared, which would have
    passed with every metric assigned to the wrong family. A second averaged each
    family, which is unsound: `least_privilege_accuracy` and `excess_authority_rate`
    are exact complements, so any family holding both averages to 0.5 whatever the
    trace does. This asserts on named metrics.
    """

    benchmark = generate_asteria_agentic_v1()
    reference = reference_agentic_trace(benchmark)

    # Records nothing, decides exactly as truth does.
    silent = reference.model_copy(
        update={
            "rows": tuple(
                row.model_copy(update={"evidence_refs": (), "side_effect": None})
                for row in reference.rows
            )
        }
    )
    # Records everything faithfully, decides the opposite of truth every time.
    reckless = reference.model_copy(
        update={
            "rows": tuple(
                row.model_copy(
                    update={
                        "decision": (
                            Decision.DENY
                            if row.decision is Decision.ALLOW
                            else Decision.ALLOW
                        )
                    }
                )
                for row in reference.rows
            )
        }
    )

    quiet = _named(evaluate_agentic_trace(silent, benchmark=benchmark))
    loud = _named(evaluate_agentic_trace(reckless, benchmark=benchmark))

    # Recording badly costs observability and leaves the verdict metrics untouched.
    assert quiet["provenance_completeness"] == 0.0
    assert quiet["expected_side_effect_accuracy"] == 0.0
    assert quiet["authorization_decision_accuracy"] == 1.0
    assert quiet["principal_resolution_accuracy"] == 1.0
    # Deciding badly costs authorization and leaves the recording metrics untouched.
    assert loud["authorization_decision_accuracy"] == 0.0
    assert loud["excess_authority_rate"] == 1.0
    assert loud["provenance_completeness"] == 1.0
    assert loud["expected_side_effect_accuracy"] == 1.0


def test_the_glossary_documents_every_metric_the_scorer_emits() -> None:
    """Documentation that drifts from the code is worse than none.

    Four of these metrics had zero mentions across every document in the repository
    before this test existed.
    """

    benchmark = generate_asteria_agentic_v1()
    report = evaluate_agentic_trace(
        reference_agentic_trace(benchmark), benchmark=benchmark
    )
    documented = (
        Path(__file__).parents[1].joinpath("AGENTIC_BENCHMARK.md").read_text("utf-8")
    )

    for metric in report.metrics:
        assert f"`{metric.name}`" in documented, metric.name
