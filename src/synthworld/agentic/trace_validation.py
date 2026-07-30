"""Diagnose an observed-action trace without any evaluator truth.

The scorer reports how well a system did. This module reports whether the system's
submission is even shaped correctly, and it does so with no access to answer-key
truth: the caller supplies the expected action-event identifiers, which are readable
from the public bundle alone.

The promise is one-directional. If :func:`validate_trace_jsonl` reports ``valid``,
then :func:`synthworld.agentic.evaluate_agentic_trace` will not raise
``EvaluationInputError`` for the same document. The converse does not hold: this
module deliberately rejects a submission in which every row is empty, which the
scorer would accept (and on which it would award a perfect
``least_privilege_accuracy``, because only explicit false allows count against that
metric).

This module must not import :mod:`synthworld.agentic.evaluation` or
:mod:`synthworld.agentic.serialization`. A test asserts that by inspecting the
import graph.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Collection, Iterable
from typing import Literal, Self

from pydantic import Field, ValidationError, model_validator

from synthworld.agentic.models import ObservedActionTrace
from synthworld.models import SyntheticModel

# Fields the scorer actually reads. Kept explicit because a row carrying only
# unscored fields is structurally valid yet scores nothing, which is worth warning
# about - and that judgement cannot be derived at runtime from the scorer's check
# lambdas. Correctness is pinned by a perturbation test rather than by this comment:
# see tests/test_agentic_trace_validator.py. Cross-reference evaluation.py's `checks`
# mapping when adding a field. Deliberately excluded because no metric reads them:
# timestamp, resource_id, action, requested_scope.
_SCORED_FIELDS: tuple[str, ...] = (
    "originating_principal_id",
    "logical_agent_id",
    "runtime_principal_id",
    "credential_subject_id",
    "attributed_actor_id",
    "decision",
    "decision_at_audit",
    "side_effect",
    "policy_version",
    "delegation_chain_ids",
    "accountable_owner_chain",
    "evidence_refs",
    "reconstructable_from_retained_evidence",
)


class TraceValidationIssue(SyntheticModel):
    """One finding about a submitted trace."""

    severity: Literal["error", "warning"]
    code: str
    message: str
    line: int | None = None
    event_id: str | None = None


class TraceValidationReport(SyntheticModel):
    """The outcome of validating one observed-action trace document."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    valid: bool
    row_count: int = Field(ge=0)
    expected_action_count: int = Field(ge=0)
    issues: tuple[TraceValidationIssue, ...]

    @model_validator(mode="after")
    def require_validity_matches_issues(self) -> Self:
        has_error = any(item.severity == "error" for item in self.issues)
        if self.valid is has_error:
            raise ValueError("trace validation validity must match its error issues")
        return self

    @property
    def error_count(self) -> int:
        return sum(1 for item in self.issues if item.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for item in self.issues if item.severity == "warning")


def validate_trace_jsonl(
    serialized: str, *, expected_event_ids: Collection[str]
) -> TraceValidationReport:
    """Diagnose observed-action JSONL against the expected action-event set.

    Every line is examined, so one malformed row does not hide the rest. Errors make
    the document invalid; warnings describe submissions that are accepted but
    probably not what the author intended.
    """

    issues: list[TraceValidationIssue] = []
    rows: list[ObservedActionTrace] = []
    seen_lines: dict[str, int] = {}
    recovered: Counter[str] = Counter()

    for number, line in enumerate(serialized.splitlines(), start=1):
        if not line.strip():
            continue
        json_ok, recovered_id = _recover_event_id(line)
        if recovered_id is None:
            issues.append(
                TraceValidationIssue(
                    severity="warning",
                    code="cardinality_unchecked",
                    message=(
                        "line has no recoverable event_id, so it cannot be matched "
                        "against the expected action events"
                    ),
                    line=number,
                )
            )
        else:
            recovered[recovered_id] += 1
        parsed = _parse_row(line, number, json_ok, recovered_id, issues)
        if parsed is None:
            continue
        first_seen = seen_lines.get(parsed.event_id)
        if first_seen is None:
            seen_lines[parsed.event_id] = number
            rows.append(parsed)
        else:
            issues.append(
                TraceValidationIssue(
                    severity="error",
                    code="duplicate_event_id",
                    message=f"{parsed.event_id} also appears on line {first_seen}",
                    line=number,
                    event_id=parsed.event_id,
                )
            )

    expected = set(expected_event_ids)
    issues.extend(_cardinality_issues(expected, recovered))
    issues.extend(_quality_issues(rows))
    return TraceValidationReport(
        valid=not any(item.severity == "error" for item in issues),
        row_count=len(rows),
        expected_action_count=len(expected),
        issues=tuple(issues),
    )


def _recover_event_id(line: str) -> tuple[bool, str | None]:
    """Read ``event_id`` without pydantic, so cardinality survives a bad row.

    Returns whether the line is syntactically valid JSON and the recovered
    identifier. The two are separate because a line can be perfectly good JSON and
    still carry no usable identifier - a bare array, or an object without the field -
    and calling that "malformed JSON" would send the author looking for the wrong
    problem.
    """

    try:
        document = json.loads(line)
    except ValueError:
        return False, None
    if not isinstance(document, dict):
        return True, None
    candidate = document.get("event_id")
    if isinstance(candidate, str):
        # Blank and whitespace-only identifiers are recovered deliberately. The model
        # accepts them, so such a row reaches the scorer, which then rejects the
        # submission for covering an unknown event. Discarding them here would let
        # this report say "valid" for a document evaluate refuses - breaking the one
        # guarantee the command makes.
        return True, candidate
    return True, None


def _parse_row(
    line: str,
    number: int,
    json_ok: bool,
    recovered_id: str | None,
    issues: list[TraceValidationIssue],
) -> ObservedActionTrace | None:
    try:
        return ObservedActionTrace.model_validate_json(line)
    except ValidationError as error:
        # Deliberately not discriminating pydantic error types. Syntactically broken
        # JSON is already distinguished by _recover_event_id, so branching on
        # json_invalid would add an arm reachable only through contrived input, and
        # every remaining type maps to the same code anyway.
        issues.append(
            TraceValidationIssue(
                severity="error",
                code="invalid_row" if json_ok else "malformed_json",
                message=_render_errors(error),
                line=number,
                event_id=recovered_id,
            )
        )
        return None


def _render_errors(error: ValidationError) -> str:
    """Render pydantic errors compactly, tolerating root-level empty locations."""

    rendered: list[str] = []
    for detail in error.errors():
        location = ".".join(str(part) for part in detail["loc"])
        rendered.append(f"{location}: {detail['msg']}" if location else detail["msg"])
    return "; ".join(rendered)


def _cardinality_issues(
    expected: set[str], recovered: Counter[str]
) -> Iterable[TraceValidationIssue]:
    for event_id in sorted(set(recovered) - expected):
        yield TraceValidationIssue(
            severity="error",
            code="unexpected_event_id",
            message=f"{event_id} is not an action event in this benchmark",
            event_id=event_id,
        )
    for event_id in sorted(expected - set(recovered)):
        yield TraceValidationIssue(
            severity="error",
            code="missing_event_id",
            message=f"{event_id} is absent from the submission",
            event_id=event_id,
        )


def _quality_issues(
    rows: list[ObservedActionTrace],
) -> Iterable[TraceValidationIssue]:
    """Report submissions that parse but probably do not say what was intended.

    The three row-level codes are mutually exclusive by construction so that a
    single row never produces two overlapping warnings.
    """

    empty = [row for row in rows if _carries_no_signal(row)]
    if rows and len(empty) == len(rows):
        yield TraceValidationIssue(
            severity="error",
            code="all_rows_null",
            message=(
                f"every one of the {len(rows)} rows is empty; this is a misconfigured "
                "adapter rather than a submission. The scorer would accept it and "
                "award a perfect least_privilege_accuracy, which is why it is "
                "rejected here"
            ),
        )
        return
    for row in rows:
        if _is_all_null(row):
            yield TraceValidationIssue(
                severity="warning",
                code="all_null_row",
                message="every observed field is null",
                event_id=row.event_id,
            )
        elif all(getattr(row, name) is None for name in _SCORED_FIELDS):
            yield TraceValidationIssue(
                severity="warning",
                code="no_scored_fields",
                message=(
                    "only fields the scorer does not read are set, so this row "
                    "scores nothing"
                ),
                event_id=row.event_id,
            )
        if row.evidence_refs == ():
            yield TraceValidationIssue(
                severity="warning",
                code="empty_evidence_refs",
                message=(
                    "evidence_refs is an empty tuple, which asserts that evidence "
                    "capture ran and found nothing; use null to assert that nothing "
                    "was captured. Asteria v1 scores the two identically, so this is "
                    "about stating what you mean rather than about the score"
                ),
                event_id=row.event_id,
            )


def _is_all_null(row: ObservedActionTrace) -> bool:
    """True when a row carries nothing but its event identifier."""

    return row == ObservedActionTrace(event_id=row.event_id)


def _carries_no_signal(row: ObservedActionTrace) -> bool:
    """True when a row tells the scorer nothing, however it spells that.

    Broader than :func:`_is_all_null` on purpose. An empty tuple is not null, so a
    submission of rows carrying only ``evidence_refs: []`` would otherwise slip past
    the all-empty rejection while being exactly as uninformative.
    """

    return all(getattr(row, name) in (None, ()) for name in _SCORED_FIELDS)
