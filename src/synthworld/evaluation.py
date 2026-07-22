"""The unified evaluation contract: prediction schemas, scorers, and reports.

A system consumes only product-safe public input, emits predictions in a
versioned oracle-free schema, and `evaluate_*` scores those predictions
against the physically separate answer key it loads itself. Every scorer
returns one `EvaluationReport` — task metrics plus failure slices, tied to the
scored benchmark bytes by content digest.

Threat model: SynthWorld's golden benchmark is committed in this repository, so
its answers are public. The public/oracle split is an **API-hygiene** guarantee
— it stops a pipeline from accidentally scoring against leaked labels — not an
anti-cheating measure. A benchmark-aware system can regenerate the answers, so
adversarial or leaderboard use requires held-out private seeds. These scores
are for honest, reproducible regression measurement.

Schema note: these evaluation schemas debut at `0.1.0` and may still change;
the generated-benchmark contracts they score against are the frozen `1.0.0`
ones. `scoring_version` versions the metric definitions independently of the
wire schema, so a change to (say) relaxed matching is visible in the report.
"""

from __future__ import annotations

import hashlib
import math
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

EVALUATION_SCHEMA_VERSION = "0.1.0"
SCORING_PROTOCOL_VERSION = "0.1.0"
CHECKSUM_SCHEME = "synthworld-json-v1"

_RELAXED_IOU_THRESHOLD = 0.5


class TaskMetric(SyntheticModel):
    """One named scalar metric. A null value marks the metric undefined here."""

    name: str
    value: float | None
    support: int = Field(ge=0)

    @model_validator(mode="after")
    def reject_non_finite(self) -> TaskMetric:
        if self.value is not None and not math.isfinite(self.value):
            raise ValueError("metric value must be finite")
        return self


class FailureSlice(SyntheticModel):
    """A counted slice of where a system failed, for error analysis."""

    regime: Literal["exact", "relaxed"]
    dimension: str
    value: str
    count: int = Field(ge=0)
    support: int = Field(ge=0)


class EvaluationReport(SyntheticModel):
    """The uniform result of scoring one task's predictions against truth."""

    schema_version: Literal["0.1.0"] = "0.1.0"
    scoring_version: str
    task: str
    seed: int
    persona_count: int = Field(ge=0)
    benchmark_version: str
    checksum_scheme: str
    artifact_checksums: tuple[tuple[str, str], ...]
    metrics: tuple[TaskMetric, ...]
    slices: tuple[FailureSlice, ...]


class PredictedSpan(SyntheticModel):
    """One predicted PII occurrence a system claims to have found."""

    data_class: DataClass
    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def require_forward_non_password_range(self) -> PredictedSpan:
        if self.end <= self.start:
            raise ValueError("predicted span end must follow start")
        if self.data_class is DataClass.PASSWORD:
            raise ValueError("password is outside the extraction label space")
        return self


class ExtractionPagePrediction(SyntheticModel):
    """A system's predicted spans for one public page."""

    source_type: ExtractionSourceType
    source_record_id: str
    spans: tuple[PredictedSpan, ...]


class ExtractionPredictionSet(SyntheticModel):
    """Oracle-free extraction predictions submitted for scoring."""

    schema_version: Literal["0.1.0"] = "0.1.0"
    predictions: tuple[ExtractionPagePrediction, ...]


_PageKey = tuple[str, str]
_Span = tuple[_PageKey, DataClass, int, int]
_Group = tuple[_PageKey, DataClass]


def evaluate_extraction(
    predictions: ExtractionPredictionSet,
    *,
    seed: int,
    persona_count: int = 10,
) -> EvaluationReport:
    """Score exact-span PII predictions against the separate answer key."""

    benchmark = generate_extraction_benchmark(seed=seed, persona_count=persona_count)
    gold = {
        (
            (answer.source_type.value, answer.source_record_id),
            span.data_class,
            span.start,
            span.end,
        )
        for answer in benchmark.answers.answers
        for span in answer.answer_key.spans
    }
    predicted = {
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
    relaxed_matches = _relaxed_match_count(predicted, gold)
    relaxed_precision = _rate(relaxed_matches, len(predicted))
    relaxed_recall = _rate(relaxed_matches, len(gold))
    relaxed_f1 = _harmonic_mean(relaxed_precision, relaxed_recall)

    metrics = (
        TaskMetric(
            name="exact_precision", value=exact_precision, support=len(predicted)
        ),
        TaskMetric(name="exact_recall", value=exact_recall, support=len(gold)),
        TaskMetric(name="exact_f1", value=exact_f1, support=len(gold)),
        TaskMetric(
            name="relaxed_precision", value=relaxed_precision, support=len(predicted)
        ),
        TaskMetric(name="relaxed_recall", value=relaxed_recall, support=len(gold)),
        TaskMetric(name="relaxed_f1", value=relaxed_f1, support=len(gold)),
    )
    return EvaluationReport(
        scoring_version=SCORING_PROTOCOL_VERSION,
        task="extraction",
        seed=seed,
        persona_count=persona_count,
        benchmark_version=benchmark.schema_version,
        checksum_scheme=CHECKSUM_SCHEME,
        artifact_checksums=(
            ("public", _sha256(public_extraction_corpus_to_json(benchmark.public))),
            ("answers", _sha256(extraction_answers_to_json(benchmark.answers))),
        ),
        metrics=metrics,
        slices=_extraction_slices(predicted, gold),
    )


def _relaxed_match_count(predicted: set[_Span], gold: set[_Span]) -> int:
    """Count one-to-one prediction/gold matches with IoU above the threshold.

    A prediction and a gold span are eligible only if they share a page and
    class and their intersection-over-union clears the threshold. Within each
    group a maximum-cardinality bipartite matching enforces one-to-one credit,
    so a single blanket span cannot claim several gold spans at once.
    """

    predicted_by_group = _group_spans(predicted)
    gold_by_group = _group_spans(gold)
    total = 0
    for group, predictions in predicted_by_group.items():
        golds = gold_by_group.get(group, [])
        if not golds:
            continue
        eligibility = [
            [
                index
                for index, truth in enumerate(golds)
                if _iou(span, truth) >= _RELAXED_IOU_THRESHOLD
            ]
            for span in predictions
        ]
        total += _max_bipartite_matching(eligibility, len(golds))
    return total


def _group_spans(spans: set[_Span]) -> dict[_Group, list[_Span]]:
    grouped: dict[_Group, list[_Span]] = {}
    for span in spans:
        grouped.setdefault((span[0], span[1]), []).append(span)
    for members in grouped.values():
        members.sort(key=lambda item: (item[2], item[3]))
    return grouped


def _iou(left: _Span, right: _Span) -> float:
    overlap = max(0, min(left[3], right[3]) - max(left[2], right[2]))
    union = (left[3] - left[2]) + (right[3] - right[2]) - overlap
    return overlap / union


def _max_bipartite_matching(adjacency: list[list[int]], right_size: int) -> int:
    match_right: list[int | None] = [None] * right_size
    matched = 0
    for left in range(len(adjacency)):
        if _augment(left, adjacency, match_right, [False] * right_size):
            matched += 1
    return matched


def _augment(
    left: int,
    adjacency: list[list[int]],
    match_right: list[int | None],
    seen: list[bool],
) -> bool:
    for right in adjacency[left]:
        if seen[right]:
            continue
        seen[right] = True
        current = match_right[right]
        if current is None or _augment(current, adjacency, match_right, seen):
            match_right[right] = left
            return True
    return False


def _extraction_slices(
    predicted: set[_Span],
    gold: set[_Span],
) -> tuple[FailureSlice, ...]:
    missed = gold - predicted
    spurious = predicted - gold
    gold_by_class: dict[DataClass, int] = {}
    for _key, data_class, _start, _end in gold:
        gold_by_class[data_class] = gold_by_class.get(data_class, 0) + 1
    missed_by_class: dict[DataClass, int] = {}
    for _key, data_class, _start, _end in missed:
        missed_by_class[data_class] = missed_by_class.get(data_class, 0) + 1
    class_slices = tuple(
        FailureSlice(
            regime="exact",
            dimension="data_class",
            value=data_class.value,
            count=missed_by_class[data_class],
            support=gold_by_class[data_class],
        )
        for data_class in sorted(missed_by_class, key=lambda item: item.value)
    )
    spurious_slice = FailureSlice(
        regime="exact",
        dimension="spurious",
        value="any",
        count=len(spurious),
        support=len(predicted),
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
    "CHECKSUM_SCHEME",
    "EVALUATION_SCHEMA_VERSION",
    "SCORING_PROTOCOL_VERSION",
    "EvaluationReport",
    "ExtractionPagePrediction",
    "ExtractionPredictionSet",
    "FailureSlice",
    "PredictedSpan",
    "TaskMetric",
    "evaluate_extraction",
]
