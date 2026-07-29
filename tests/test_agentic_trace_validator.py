"""Tests for oracle-free observed-action trace validation."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from synthworld.agentic import (
    TraceValidationIssue,
    TraceValidationReport,
    evaluate_agentic_trace,
    generate_asteria_agentic_v1,
    reference_agentic_trace,
    trace_submission_from_jsonl,
    trace_submission_to_jsonl,
    validate_trace_jsonl,
)
from synthworld.agentic.models import ObservedActionTrace

BENCHMARK = generate_asteria_agentic_v1()
EXPECTED_IDS = BENCHMARK.public.scenario.action_event_ids
REFERENCE_LINES = trace_submission_to_jsonl(
    reference_agentic_trace(BENCHMARK)
).splitlines()


def _document(lines: list[str]) -> str:
    return "\n".join(lines) + "\n"


def _codes(report: TraceValidationReport) -> list[str]:
    return [issue.code for issue in report.issues]


def _replace(index: int, line: str) -> str:
    edited = list(REFERENCE_LINES)
    edited[index] = line
    return _document(edited)


def _bare_row(event_id: str, **fields: object) -> str:
    return json.dumps({"event_id": event_id, **fields})


def test_reference_trace_is_valid_without_issues() -> None:
    report = validate_trace_jsonl(
        _document(REFERENCE_LINES), expected_event_ids=EXPECTED_IDS
    )

    assert report.valid
    assert report.issues == ()
    assert report.row_count == len(EXPECTED_IDS)
    assert report.expected_action_count == len(EXPECTED_IDS)
    assert report.error_count == 0
    assert report.warning_count == 0


def test_blank_lines_are_skipped() -> None:
    padded = f"\n\n{_document(REFERENCE_LINES)}\n   \n"

    report = validate_trace_jsonl(padded, expected_event_ids=EXPECTED_IDS)

    assert report.valid
    assert report.row_count == len(EXPECTED_IDS)


def test_malformed_json_reports_line_and_keeps_cardinality() -> None:
    report = validate_trace_jsonl(
        _replace(0, "{not json"), expected_event_ids=EXPECTED_IDS
    )

    assert not report.valid
    malformed = [item for item in report.issues if item.code == "malformed_json"]
    assert [item.line for item in malformed] == [1]
    # The genuine cardinality finding must survive the parse failure.
    assert "missing_event_id" in _codes(report)
    assert "cardinality_unchecked" in _codes(report)


@pytest.mark.parametrize(
    ("line", "fragment"),
    [
        (_bare_row(EXPECTED_IDS[0], bogus=1), "bogus"),
        (_bare_row(EXPECTED_IDS[0], timestamp="2026-07-29T12:00:00"), "timezone-aware"),
        (_bare_row(EXPECTED_IDS[0], decision="maybe"), "decision"),
        (_bare_row(EXPECTED_IDS[0], schema_version="9.9.9"), "schema_version"),
        (_bare_row(EXPECTED_IDS[0], synthetic=False), "synthetic"),
    ],
)
def test_field_violations_report_invalid_row(line: str, fragment: str) -> None:
    report = validate_trace_jsonl(_replace(0, line), expected_event_ids=EXPECTED_IDS)

    assert not report.valid
    invalid = [item for item in report.issues if item.code == "invalid_row"]
    assert len(invalid) == 1
    assert invalid[0].line == 1
    assert invalid[0].event_id == EXPECTED_IDS[0]
    assert fragment in invalid[0].message


def test_valid_json_without_event_id_is_not_called_malformed() -> None:
    report = validate_trace_jsonl(
        _replace(0, json.dumps({"decision": "allow"})),
        expected_event_ids=EXPECTED_IDS,
    )

    assert not report.valid
    assert "invalid_row" in _codes(report)
    assert "malformed_json" not in _codes(report)


@pytest.mark.parametrize("payload", ["[]", "null", "42", '"text"'])
def test_non_object_json_is_reported_without_a_location(payload: str) -> None:
    report = validate_trace_jsonl(_replace(0, payload), expected_event_ids=EXPECTED_IDS)

    assert not report.valid
    invalid = [item for item in report.issues if item.code == "invalid_row"]
    assert len(invalid) == 1
    # Root-level pydantic errors carry an empty loc; the renderer must not emit ": ".
    assert not invalid[0].message.startswith(":")


def test_duplicate_event_id_names_the_first_line() -> None:
    report = validate_trace_jsonl(
        _document([*REFERENCE_LINES, REFERENCE_LINES[1]]),
        expected_event_ids=EXPECTED_IDS,
    )

    assert not report.valid
    duplicates = [item for item in report.issues if item.code == "duplicate_event_id"]
    assert len(duplicates) == 1
    assert "line 2" in duplicates[0].message


def test_renamed_event_id_reports_unexpected_and_missing() -> None:
    report = validate_trace_jsonl(
        _replace(0, _bare_row("evt-999-typo")), expected_event_ids=EXPECTED_IDS
    )

    codes = _codes(report)
    assert not report.valid
    assert "unexpected_event_id" in codes
    assert "missing_event_id" in codes


def test_dropped_row_reports_missing_only() -> None:
    report = validate_trace_jsonl(
        _document(REFERENCE_LINES[1:]), expected_event_ids=EXPECTED_IDS
    )

    codes = _codes(report)
    assert not report.valid
    assert codes.count("missing_event_id") == 1
    assert "unexpected_event_id" not in codes


def test_empty_document_reports_every_expected_event() -> None:
    report = validate_trace_jsonl("", expected_event_ids=EXPECTED_IDS)

    assert not report.valid
    assert report.row_count == 0
    assert _codes(report).count("missing_event_id") == len(EXPECTED_IDS)


def test_single_all_null_row_warns_but_stays_valid() -> None:
    report = validate_trace_jsonl(
        _replace(0, _bare_row(EXPECTED_IDS[0])), expected_event_ids=EXPECTED_IDS
    )

    assert report.valid
    assert _codes(report) == ["all_null_row"]
    assert report.warning_count == 1


def test_row_with_only_unscored_fields_warns_no_scored_fields() -> None:
    line = _bare_row(EXPECTED_IDS[0], resource_id="res-1", action="read")

    report = validate_trace_jsonl(_replace(0, line), expected_event_ids=EXPECTED_IDS)

    assert report.valid
    assert _codes(report) == ["no_scored_fields"]


def test_every_row_null_is_an_error_not_a_warning() -> None:
    document = _document([_bare_row(event_id) for event_id in EXPECTED_IDS])

    report = validate_trace_jsonl(document, expected_event_ids=EXPECTED_IDS)

    assert not report.valid
    assert _codes(report) == ["all_rows_null"]
    assert "least_privilege_accuracy" in report.issues[0].message


def test_empty_evidence_refs_warns() -> None:
    line = _bare_row(EXPECTED_IDS[0], decision="allow", evidence_refs=[])

    report = validate_trace_jsonl(_replace(0, line), expected_event_ids=EXPECTED_IDS)

    assert report.valid
    assert _codes(report) == ["empty_evidence_refs"]


def test_report_rejects_validity_that_contradicts_its_issues() -> None:
    error = TraceValidationIssue(severity="error", code="x", message="y")

    with pytest.raises(ValidationError, match="validity must match"):
        TraceValidationReport(
            valid=True, row_count=0, expected_action_count=0, issues=(error,)
        )

    with pytest.raises(ValidationError, match="validity must match"):
        TraceValidationReport(
            valid=False, row_count=0, expected_action_count=0, issues=()
        )


def test_valid_report_means_the_scorer_accepts_the_same_document() -> None:
    """The one-directional promise: valid implies evaluate will not reject."""

    document = _document(REFERENCE_LINES)
    assert validate_trace_jsonl(document, expected_event_ids=EXPECTED_IDS).valid

    report = evaluate_agentic_trace(
        trace_submission_from_jsonl(document), benchmark=BENCHMARK
    )

    assert report.task == "agentic_authority"


def test_scored_field_constant_matches_what_the_scorer_reads() -> None:
    """Pin the field classification behaviourally rather than trusting a comment."""

    from synthworld.agentic.trace_validation import _SCORED_FIELDS

    baseline = evaluate_agentic_trace(
        reference_agentic_trace(BENCHMARK), benchmark=BENCHMARK
    )
    baseline_values = {metric.name: metric.value for metric in baseline.metrics}
    ignored = {"event_id", "schema_version", "synthetic"}
    candidates = [
        name for name in ObservedActionTrace.model_fields if name not in ignored
    ]
    assert set(_SCORED_FIELDS) <= set(candidates)

    for name in candidates:
        rows = tuple(
            row.model_copy(update={name: None})
            for row in reference_agentic_trace(BENCHMARK).rows
        )
        perturbed = evaluate_agentic_trace(
            reference_agentic_trace(BENCHMARK).model_copy(update={"rows": rows}),
            benchmark=BENCHMARK,
        )
        moved = any(
            metric.value != baseline_values[metric.name] for metric in perturbed.metrics
        )
        assert moved is (name in _SCORED_FIELDS), (
            f"{name}: metrics moved={moved} but _SCORED_FIELDS membership="
            f"{name in _SCORED_FIELDS}"
        )


def test_validator_does_not_import_evaluator_or_loader_modules() -> None:
    """Oracle isolation, asserted over the import graph.

    Module absence from ``sys.modules`` cannot be asserted: ``synthworld/__init__``
    eagerly imports ``synthworld.agentic``, whose package init imports both
    ``evaluation`` and ``serialization``. The enforceable property is that this
    module itself reaches for neither.
    """

    source = Path("src/synthworld/agentic/trace_validation.py").read_text(
        encoding="utf-8"
    )
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)

    assert not {name for name in imported if "evaluation" in name}
    assert not {name for name in imported if "serialization" in name}
