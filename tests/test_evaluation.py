from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from synthworld import DataClass, generate_extraction_benchmark
from synthworld.evaluation import (
    EvaluationReport,
    ExtractionPagePrediction,
    ExtractionPredictionSet,
    PredictedSpan,
    _overlaps,
    evaluate_extraction,
)

_SEED = 20_260_719
_EMAIL = re.compile(r"[a-z0-9][a-z0-9._%+-]*@example\.test")
_PHONE = re.compile(r"\+1-[0-9]{3}-555-01[0-9]{2}")
_NATIONAL_ID = re.compile(r"SYN-[0-9]+")


def _regex_prediction() -> ExtractionPredictionSet:
    benchmark = generate_extraction_benchmark(seed=_SEED, persona_count=10)
    pages = []
    for page in benchmark.public.pages:
        spans = [
            PredictedSpan(data_class=data_class, start=match.start(), end=match.end())
            for pattern, data_class in (
                (_EMAIL, DataClass.EMAIL),
                (_PHONE, DataClass.PHONE),
                (_NATIONAL_ID, DataClass.NATIONAL_ID),
            )
            for match in pattern.finditer(page.content)
        ]
        pages.append(
            ExtractionPagePrediction(
                source_type=page.source_type,
                source_record_id=page.source_record_id,
                spans=tuple(spans),
            )
        )
    return ExtractionPredictionSet(predictions=tuple(pages))


def _perfect_prediction() -> ExtractionPredictionSet:
    benchmark = generate_extraction_benchmark(seed=_SEED, persona_count=10)
    return ExtractionPredictionSet(
        predictions=tuple(
            ExtractionPagePrediction(
                source_type=answer.source_type,
                source_record_id=answer.source_record_id,
                spans=tuple(
                    PredictedSpan(
                        data_class=span.data_class,
                        start=span.start,
                        end=span.end,
                    )
                    for span in answer.answer_key.spans
                ),
            )
            for answer in benchmark.answers.answers
        )
    )


def _metric(report: EvaluationReport, name: str) -> float:
    return next(metric.value for metric in report.metrics if metric.name == name)


def test_regex_prediction_reproduces_the_reference_extraction_score() -> None:
    report = evaluate_extraction(_regex_prediction(), seed=_SEED, persona_count=10)

    assert report.task == "extraction"
    assert report.benchmark_version == "1.0.0"
    assert round(_metric(report, "exact_precision"), 4) == 1.0
    assert round(_metric(report, "exact_recall"), 4) == 0.46
    assert round(_metric(report, "exact_f1"), 4) == 0.6301
    assert dict(report.artifact_checksums)["answers"] == (
        "ffc6503df8cbb9d8f99161ee29324e8d0a0187901118e8eeaa590b49e7598f78"
    )
    missed = {
        failure.label: failure.count
        for failure in report.slices
        if failure.label.startswith("missed:")
    }
    assert missed == {
        "missed:address": 15,
        "missed:date_of_birth": 6,
        "missed:education": 13,
        "missed:employer": 34,
        "missed:username": 13,
    }
    assert next(s.count for s in report.slices if s.label == "spurious") == 0


def test_perfect_prediction_scores_one_with_no_missed_slices() -> None:
    report = evaluate_extraction(_perfect_prediction(), seed=_SEED, persona_count=10)

    for name in ("exact_f1", "relaxed_f1", "exact_precision", "exact_recall"):
        assert _metric(report, name) == 1.0
    assert not [s for s in report.slices if s.label.startswith("missed:")]
    assert next(s.count for s in report.slices if s.label == "spurious") == 0


def test_empty_prediction_scores_zero_across_every_metric() -> None:
    report = evaluate_extraction(
        ExtractionPredictionSet(predictions=()),
        seed=_SEED,
        persona_count=10,
    )

    assert {metric.value for metric in report.metrics} == {0.0}
    assert next(s.count for s in report.slices if s.label == "spurious") == 0


def test_predicted_span_rejects_a_non_forward_range() -> None:
    with pytest.raises(ValidationError, match="end must follow start"):
        PredictedSpan(data_class=DataClass.EMAIL, start=5, end=5)


def test_overlaps_requires_the_same_page_class_and_a_shared_range() -> None:
    base = (("breach", "breach-0001-01"), DataClass.EMAIL, 10, 20)
    assert _overlaps(base, (("breach", "breach-0001-01"), DataClass.EMAIL, 15, 25))
    assert not _overlaps(base, (("breach", "breach-0001-01"), DataClass.EMAIL, 20, 30))
    assert not _overlaps(base, (("breach", "breach-0001-01"), DataClass.PHONE, 10, 20))
    assert not _overlaps(base, (("broker", "broker-0001-01"), DataClass.EMAIL, 10, 20))
