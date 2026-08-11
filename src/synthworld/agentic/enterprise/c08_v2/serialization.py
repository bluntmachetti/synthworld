"""Canonical, physically separate C08 v2 artifact serialization."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from synthworld.agentic.enterprise.c08_v2.errors import C08SerializationError
from synthworld.agentic.enterprise.c08_v2.models import (
    C08EvaluationReportV2,
    C08EvaluatorTruthV2,
    C08PublicInputV2,
    C08SubmissionV2,
)
from synthworld.agentic.enterprise.c08_v2.projection import c08_public_input_digest
from synthworld.enterprise.canonical import canonical_json_bytes

PUBLIC_DIR = "public"
EVALUATOR_DIR = "evaluator"
SUBMISSION_DIR = "submission"
PUBLIC_FILE = "public-input.json"
EVALUATOR_FILE = "truth.json"
SUBMISSION_FILE = "submission.json"
REPORT_FILE = "report.json"


def serialize_c08_public(model: C08PublicInputV2) -> bytes:
    return canonical_json_bytes(model)


def serialize_c08_evaluator(model: C08EvaluatorTruthV2) -> bytes:
    return canonical_json_bytes(model)


def serialize_c08_submission(model: C08SubmissionV2) -> bytes:
    return canonical_json_bytes(model)


def serialize_c08_report(model: C08EvaluationReportV2) -> bytes:
    return canonical_json_bytes(model)


def require_c08_canonical_json_bytes(payload: bytes, label: str) -> None:
    """Reject malformed or noncanonical JSON before typed model validation."""

    try:
        value = json.loads(payload)
        canonical = (
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
        )
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise C08SerializationError(f"invalid C08 {label} artifact") from error
    if payload != canonical:
        raise C08SerializationError(f"C08 {label} artifact is not canonical JSON")


def _parse[ModelT: BaseModel](
    payload: bytes, model: type[ModelT], label: str
) -> ModelT:
    require_c08_canonical_json_bytes(payload, label)
    try:
        parsed = model.model_validate_json(payload)
    except (TypeError, ValueError) as error:
        raise C08SerializationError(f"invalid C08 {label} artifact") from error
    if payload != canonical_json_bytes(parsed):
        raise C08SerializationError(f"C08 {label} artifact is not canonical JSON")
    return parsed


def _read[ModelT: BaseModel](path: Path, model: type[ModelT], label: str) -> ModelT:
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise C08SerializationError(f"C08 {label} artifact is unreadable") from error
    return _parse(payload, model, label)


def load_c08_public(path: Path) -> C08PublicInputV2:
    return _read(path, C08PublicInputV2, "public")


def load_c08_evaluator(path: Path) -> C08EvaluatorTruthV2:
    return _read(path, C08EvaluatorTruthV2, "evaluator")


def load_c08_submission(path: Path) -> C08SubmissionV2:
    return _read(path, C08SubmissionV2, "submission")


def export_c08_artifacts(
    root: Path,
    *,
    public: C08PublicInputV2,
    evaluator: C08EvaluatorTruthV2,
    submission: C08SubmissionV2,
    report: C08EvaluationReportV2 | None = None,
) -> None:
    """Write public, evaluator, and submission roots without overwriting files."""

    public_digest = c08_public_input_digest(public)
    if evaluator.public_input_digest != public_digest:
        raise C08SerializationError(
            "evaluator truth binds to a different C08 public input"
        )
    if submission.public_input_digest != public_digest:
        raise C08SerializationError("submission binds to a different C08 public input")
    if report is not None and report.public_input_digest != public_digest:
        raise C08SerializationError("report binds to a different C08 public input")
    if root.exists():
        raise C08SerializationError("C08 artifact root already exists")
    try:
        (root / PUBLIC_DIR).mkdir(parents=True)
        (root / EVALUATOR_DIR).mkdir()
        (root / SUBMISSION_DIR).mkdir()
        (root / PUBLIC_DIR / PUBLIC_FILE).write_bytes(serialize_c08_public(public))
        (root / EVALUATOR_DIR / EVALUATOR_FILE).write_bytes(
            serialize_c08_evaluator(evaluator)
        )
        (root / SUBMISSION_DIR / SUBMISSION_FILE).write_bytes(
            serialize_c08_submission(submission)
        )
        if report is not None:
            (root / EVALUATOR_DIR / REPORT_FILE).write_bytes(
                serialize_c08_report(report)
            )
    except OSError as error:
        raise C08SerializationError("C08 artifact export failed") from error


__all__ = [
    "EVALUATOR_DIR",
    "EVALUATOR_FILE",
    "PUBLIC_DIR",
    "PUBLIC_FILE",
    "REPORT_FILE",
    "SUBMISSION_DIR",
    "SUBMISSION_FILE",
    "export_c08_artifacts",
    "load_c08_evaluator",
    "load_c08_public",
    "load_c08_submission",
    "require_c08_canonical_json_bytes",
    "serialize_c08_evaluator",
    "serialize_c08_public",
    "serialize_c08_report",
    "serialize_c08_submission",
]
