"""The unified evaluation contract: prediction schemas, scorers, and reports.

A system consumes only product-safe public input, emits predictions in a
versioned oracle-free schema, and `evaluate_*` scores those predictions
against the physically separate answer key it loads itself. Every scorer
returns one `EvaluationReport` — task metrics plus failure slices, tied to the
exact benchmark bytes by checksum — so scores are comparable across systems
and across time.
"""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import Field, model_validator

from synthworld.exposures import DataClass
from synthworld.extraction import ExtractionSourceType
from synthworld.extraction_generator import generate_extraction_benchmark
from synthworld.extraction_serialization import (
    extraction_answers_to_json,
    public_extraction_corpus_to_json,
)
from synthworld.models import SyntheticModel

EVALUATION_SCHEMA_VERSION = "1.0.0"


class TaskMetric(SyntheticModel):
    """One named scalar metric in an evaluation report."""

    name: str
    value: float


class FailureSlice(SyntheticModel):
    """A counted slice of where a system failed, for error analysis."""

    label: str
    count: int = Field(ge=0)
    note: str


class EvaluationReport(SyntheticModel):
    """The uniform result of scoring one task's predictions against truth."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    task: str
    seed: int
    persona_count: int = Field(ge=0)
    benchmark_version: str
    artifact_checksums: tuple[tuple[str, str], ...]
    metrics: tuple[TaskMetric, ...]
    slices: tuple[FailureSlice, ...]


class PredictedSpan(SyntheticModel):
    """One predicted PII occurrence a system claims to have found."""

    data_class: DataClass
    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def require_forward_range(self) -> PredictedSpan:
        if self.end <= self.start:
            raise ValueError("predicted span end must follow start")
        return self


class ExtractionPagePrediction(SyntheticModel):
    """A system's predicted spans for one public page."""

    source_type: ExtractionSourceType
    source_record_id: str
    spans: tuple[PredictedSpan, ...]


class ExtractionPredictionSet(SyntheticModel):
    """Oracle-free extraction predictions submitted for scoring."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    predictions: tuple[ExtractionPagePrediction, ...]


_PageKey = tuple[str, str]
_Span = tuple[_PageKey, DataClass, int, int]


def evaluate_extraction(
    predictions: ExtractionPredictionSet,
    *,
    seed: int,
    persona_count: int = 10,
) -> EvaluationReport:
    """Score exact-span PII predictions against the separate answer key."""

    benchmark = generate_extraction_benchmark(seed=seed, persona_count=persona_count)
    gold: set[_Span] = {
        (
            (answer.source_type.value, answer.source_record_id),
            span.data_class,
            span.start,
            span.end,
        )
        for answer in benchmark.answers.answers
        for span in answer.answer_key.spans
    }
    predicted: set[_Span] = {
        (
            (page.source_type.value, page.source_record_id),
            span.data_class,
            span.start,
            span.end,
        )
        for page in predictions.predictions
        for span in page.spans
    }

    exact_precision, exact_recall, exact_f1 = _prf(predicted, gold)
    relaxed_matched_predictions, relaxed_recalled_gold = _relaxed_overlap(
        predicted, gold
    )
    relaxed_precision = _rate(relaxed_matched_predictions, len(predicted))
    relaxed_recall = _rate(relaxed_recalled_gold, len(gold))
    relaxed_f1 = _harmonic_mean(relaxed_precision, relaxed_recall)

    metrics = (
        TaskMetric(name="exact_precision", value=exact_precision),
        TaskMetric(name="exact_recall", value=exact_recall),
        TaskMetric(name="exact_f1", value=exact_f1),
        TaskMetric(name="relaxed_precision", value=relaxed_precision),
        TaskMetric(name="relaxed_recall", value=relaxed_recall),
        TaskMetric(name="relaxed_f1", value=relaxed_f1),
    )
    return EvaluationReport(
        task="extraction",
        seed=seed,
        persona_count=persona_count,
        benchmark_version=benchmark.schema_version,
        artifact_checksums=(
            ("public", _sha256(public_extraction_corpus_to_json(benchmark.public))),
            ("answers", _sha256(extraction_answers_to_json(benchmark.answers))),
        ),
        metrics=metrics,
        slices=_extraction_slices(predicted, gold),
    )


def _relaxed_overlap(predicted: set[_Span], gold: set[_Span]) -> tuple[int, int]:
    matched_predictions = sum(
        any(_overlaps(prediction, truth) for truth in gold) for prediction in predicted
    )
    recalled_gold = sum(
        any(_overlaps(prediction, truth) for prediction in predicted) for truth in gold
    )
    return matched_predictions, recalled_gold


def _overlaps(left: _Span, right: _Span) -> bool:
    left_key, left_class, left_start, left_end = left
    right_key, right_class, right_start, right_end = right
    if left_key != right_key or left_class is not right_class:
        return False
    return left_start < right_end and right_start < left_end


def _extraction_slices(
    predicted: set[_Span],
    gold: set[_Span],
) -> tuple[FailureSlice, ...]:
    missed = gold - predicted
    spurious = predicted - gold
    by_class: dict[DataClass, int] = {}
    for _key, data_class, _start, _end in missed:
        by_class[data_class] = by_class.get(data_class, 0) + 1
    class_slices = tuple(
        FailureSlice(
            label=f"missed:{data_class.value}",
            count=by_class[data_class],
            note="gold spans of this class with no exact prediction",
        )
        for data_class in sorted(by_class, key=lambda item: item.value)
    )
    spurious_slice = FailureSlice(
        label="spurious",
        count=len(spurious),
        note="predicted spans that match no gold span exactly",
    )
    return (*class_slices, spurious_slice)


def _prf[Item](predicted: set[Item], gold: set[Item]) -> tuple[float, float, float]:
    true_positive = len(predicted & gold)
    precision = _rate(true_positive, len(predicted))
    recall = _rate(true_positive, len(gold))
    return precision, recall, _harmonic_mean(precision, recall)


def _harmonic_mean(precision: float, recall: float) -> float:
    denominator = precision + recall
    return 2 * precision * recall / denominator if denominator else 0.0


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


__all__ = [
    "EVALUATION_SCHEMA_VERSION",
    "EvaluationReport",
    "ExtractionPagePrediction",
    "ExtractionPredictionSet",
    "FailureSlice",
    "PredictedSpan",
    "TaskMetric",
    "evaluate_extraction",
]
