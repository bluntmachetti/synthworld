"""Vendor-neutral JSONL parsing and public-only validation for PR6 traces."""

from __future__ import annotations

import json

from pydantic import ValidationError

from synthworld.agentic.enterprise.errors import EnterpriseAgenticEvaluationError
from synthworld.agentic.enterprise.models import (
    EnterpriseAgenticPredictionV1,
    EnterpriseAgenticPublicInputV1,
    EnterpriseAgenticTraceRowV1,
    EnterpriseAgenticTraceValidationIssueV1,
    EnterpriseAgenticTraceValidationReportV1,
)
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest


def enterprise_agentic_trace_to_jsonl(
    prediction: EnterpriseAgenticPredictionV1,
) -> str:
    """Serialize canonical rows with UTF-8-safe JSON and one trailing LF each."""

    return "".join(f"{item.model_dump_json()}\n" for item in prediction.rows)


def enterprise_agentic_trace_from_jsonl(
    serialized: str,
) -> EnterpriseAgenticPredictionV1:
    """Parse a trace for scoring, failing at the first invalid nonblank row."""

    rows: list[EnterpriseAgenticTraceRowV1] = []
    for line_number, line in enumerate(serialized.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(EnterpriseAgenticTraceRowV1.model_validate_json(line))
        except ValidationError as error:
            raise EnterpriseAgenticEvaluationError(
                f"invalid enterprise-agentic trace row {line_number}: {error}"
            ) from error
    if not rows:
        raise EnterpriseAgenticEvaluationError("enterprise-agentic trace is empty")
    digests = {item.benchmark_digest for item in rows}
    if len(digests) != 1:
        raise EnterpriseAgenticEvaluationError(
            "enterprise-agentic trace rows bind different benchmarks"
        )
    return EnterpriseAgenticPredictionV1(
        benchmark_digest=next(iter(digests)),
        rows=tuple(rows),
    )


def validate_enterprise_agentic_trace_jsonl(
    serialized: str,
    *,
    public: EnterpriseAgenticPublicInputV1,
) -> EnterpriseAgenticTraceValidationReportV1:
    """Diagnose every trace line using public case IDs and benchmark digest only."""

    expected = {item.case_id for item in public.benchmark.cases}
    benchmark_digest = synthetic_digest(canonical_json_bytes(public.benchmark))
    issues: list[EnterpriseAgenticTraceValidationIssueV1] = []
    rows: list[EnterpriseAgenticTraceRowV1] = []
    seen: dict[str, int] = {}
    recovered: set[str] = set()
    for line_number, line in enumerate(serialized.splitlines(), start=1):
        if not line.strip():
            continue
        recovered_case = _recover_case_id(line)
        if recovered_case is not None:
            recovered.add(recovered_case)
        try:
            row = EnterpriseAgenticTraceRowV1.model_validate_json(line)
        except ValidationError as error:
            issues.append(
                EnterpriseAgenticTraceValidationIssueV1(
                    severity="error",
                    code="invalid_row",
                    message=str(error),
                    line=line_number,
                    case_id=recovered_case,
                )
            )
            continue
        if row.case_id in seen:
            issues.append(
                EnterpriseAgenticTraceValidationIssueV1(
                    severity="error",
                    code="duplicate_case_id",
                    message=(f"{row.case_id} also appears on line {seen[row.case_id]}"),
                    line=line_number,
                    case_id=row.case_id,
                )
            )
            continue
        seen[row.case_id] = line_number
        rows.append(row)
        if row.benchmark_digest != benchmark_digest:
            issues.append(
                EnterpriseAgenticTraceValidationIssueV1(
                    severity="error",
                    code="benchmark_digest_mismatch",
                    message="row does not bind the supplied public benchmark",
                    line=line_number,
                    case_id=row.case_id,
                )
            )
    for case_id in sorted(recovered - expected):
        issues.append(
            EnterpriseAgenticTraceValidationIssueV1(
                severity="error",
                code="unexpected_case_id",
                message=f"{case_id} is not a case in this benchmark",
                case_id=case_id,
            )
        )
    for case_id in sorted(expected - recovered):
        issues.append(
            EnterpriseAgenticTraceValidationIssueV1(
                severity="error",
                code="missing_case_id",
                message=f"{case_id} is absent from the submission",
                case_id=case_id,
            )
        )
    return EnterpriseAgenticTraceValidationReportV1(
        valid=not any(item.severity == "error" for item in issues),
        row_count=len(rows),
        expected_case_count=len(expected),
        issues=tuple(issues),
    )


def _recover_case_id(line: str) -> str | None:
    try:
        value = json.loads(line)
    except ValueError:
        return None
    if not isinstance(value, dict):
        return None
    case_id = value.get("case_id")
    return case_id if isinstance(case_id, str) else None


__all__ = [
    "enterprise_agentic_trace_from_jsonl",
    "enterprise_agentic_trace_to_jsonl",
    "validate_enterprise_agentic_trace_jsonl",
]
