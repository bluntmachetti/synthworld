"""JSONL parsing and public-only validation for contextual-access predictions."""

from __future__ import annotations

import json

from pydantic import ValidationError

from synthworld.contextual_access.metrics import ContextualAccessEvaluationError
from synthworld.contextual_access.models import (
    ContextualAccessPredictionV1,
    ContextualAccessPublicV1,
    ContextualAccessTraceRowV1,
    ContextualTraceValidationIssueV1,
    ContextualTraceValidationReportV1,
)
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest


def contextual_access_trace_to_jsonl(
    prediction: ContextualAccessPredictionV1,
) -> str:
    """Serialize one compact JSON object and LF per canonical prediction row."""

    return "".join(f"{item.model_dump_json()}\n" for item in prediction.rows)


def contextual_access_trace_from_jsonl(
    serialized: str,
) -> ContextualAccessPredictionV1:
    """Parse a scoreable trace, failing at the first invalid nonblank row."""

    rows: list[ContextualAccessTraceRowV1] = []
    for line_number, line in enumerate(serialized.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(ContextualAccessTraceRowV1.model_validate_json(line))
        except ValidationError as error:
            raise ContextualAccessEvaluationError(
                f"invalid contextual-access trace row {line_number}: {error}"
            ) from error
    if not rows:
        raise ContextualAccessEvaluationError("contextual-access trace is empty")
    digests = {item.benchmark_digest for item in rows}
    if len(digests) != 1:
        raise ContextualAccessEvaluationError(
            "contextual-access trace rows bind different benchmarks"
        )
    return ContextualAccessPredictionV1(
        benchmark_digest=next(iter(digests)),
        rows=tuple(rows),
    )


def validate_contextual_access_trace_jsonl(
    serialized: str,
    *,
    public: ContextualAccessPublicV1,
) -> ContextualTraceValidationReportV1:
    """Diagnose all rows using only public request IDs and benchmark identity."""

    expected = {item.request_id for item in public.requests}
    benchmark_digest = synthetic_digest(canonical_json_bytes(public.benchmark))
    issues: list[ContextualTraceValidationIssueV1] = []
    rows: list[ContextualAccessTraceRowV1] = []
    seen: dict[str, int] = {}
    recovered: set[str] = set()
    for line_number, line in enumerate(serialized.splitlines(), start=1):
        if not line.strip():
            continue
        recovered_request = _recover_request_id(line)
        if recovered_request is not None:
            recovered.add(recovered_request)
        try:
            row = ContextualAccessTraceRowV1.model_validate_json(line)
        except ValidationError as error:
            issues.append(
                ContextualTraceValidationIssueV1(
                    code="invalid_row",
                    message=str(error),
                    line=line_number,
                    request_id=recovered_request,
                )
            )
            continue
        if row.request_id in seen:
            issues.append(
                ContextualTraceValidationIssueV1(
                    code="duplicate_request_id",
                    message=(
                        f"{row.request_id} also appears on line {seen[row.request_id]}"
                    ),
                    line=line_number,
                    request_id=row.request_id,
                )
            )
            continue
        seen[row.request_id] = line_number
        rows.append(row)
        if row.benchmark_digest != benchmark_digest:
            issues.append(
                ContextualTraceValidationIssueV1(
                    code="benchmark_digest_mismatch",
                    message="row does not bind the supplied public benchmark",
                    line=line_number,
                    request_id=row.request_id,
                )
            )
    for request_id in sorted(recovered - expected):
        issues.append(
            ContextualTraceValidationIssueV1(
                code="unexpected_request_id",
                message=f"{request_id} is not a request in this benchmark",
                request_id=request_id,
            )
        )
    for request_id in sorted(expected - recovered):
        issues.append(
            ContextualTraceValidationIssueV1(
                code="missing_request_id",
                message=f"{request_id} is absent from the submission",
                request_id=request_id,
            )
        )
    return ContextualTraceValidationReportV1(
        valid=not issues,
        row_count=len(rows),
        expected_request_count=len(expected),
        issues=tuple(issues),
    )


def _recover_request_id(line: str) -> str | None:
    try:
        value = json.loads(line)
    except ValueError:
        return None
    if not isinstance(value, dict):
        return None
    request_id = value.get("request_id")
    return request_id if isinstance(request_id, str) else None


__all__ = [
    "contextual_access_trace_from_jsonl",
    "contextual_access_trace_to_jsonl",
    "validate_contextual_access_trace_jsonl",
]
