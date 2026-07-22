from __future__ import annotations

import re
from uuid import NAMESPACE_DNS, UUID, uuid5

import pytest
from pydantic import ValidationError

from synthworld import DataClass, generate_extraction_benchmark
from synthworld.connection import ConnectionBenchmark
from synthworld.connection_generator import generate_adversarial_connection_benchmark
from synthworld.evaluation import (
    EntityResolutionPrediction,
    EvaluationInputError,
    EvaluationReport,
    ExtractionPagePrediction,
    ExtractionPredictionSet,
    PredictedSpan,
    TaskMetric,
    _iou,
    _max_bipartite_matching,
    _relaxed_match_count,
    evaluate_entity_resolution,
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


def _metric(report: EvaluationReport, name: str) -> float | None:
    return next(metric.value for metric in report.metrics if metric.name == name)


def test_regex_prediction_reproduces_the_reference_extraction_score() -> None:
    report = evaluate_extraction(_regex_prediction(), seed=_SEED, persona_count=10)

    assert report.task == "extraction"
    assert report.benchmark_version == "1.0.0"
    assert report.scoring_version == "0.1.0"
    assert report.checksum_scheme == "synthworld-json-v1"
    assert round(_metric(report, "exact_precision") or 0.0, 4) == 1.0
    assert round(_metric(report, "exact_recall") or 0.0, 4) == 0.46
    assert round(_metric(report, "exact_f1") or 0.0, 4) == 0.6301
    # regex spans land exactly on gold, so IoU is 1.0 and relaxed equals exact.
    assert round(_metric(report, "relaxed_f1") or 0.0, 4) == 0.6301
    assert dict(report.artifact_checksums)["answers"] == (
        "ffc6503df8cbb9d8f99161ee29324e8d0a0187901118e8eeaa590b49e7598f78"
    )
    missed = {
        failure.value: failure.count
        for failure in report.slices
        if failure.dimension == "data_class"
    }
    assert missed == {
        "address": 15,
        "date_of_birth": 6,
        "education": 13,
        "employer": 34,
        "username": 13,
    }
    assert next(s.count for s in report.slices if s.outcome == "spurious") == 0


def test_perfect_prediction_scores_one_with_no_missed_slices() -> None:
    report = evaluate_extraction(_perfect_prediction(), seed=_SEED, persona_count=10)

    for name in ("exact_f1", "relaxed_f1", "exact_precision", "exact_recall"):
        assert _metric(report, name) == 1.0
    assert not [s for s in report.slices if s.dimension == "data_class"]
    assert next(s.count for s in report.slices if s.outcome == "spurious") == 0


def test_empty_prediction_scores_zero_across_every_metric() -> None:
    report = evaluate_extraction(
        ExtractionPredictionSet(predictions=()),
        seed=_SEED,
        persona_count=10,
    )

    assert {metric.value for metric in report.metrics} == {0.0}
    assert next(s.count for s in report.slices if s.outcome == "spurious") == 0


def test_predicted_span_rejects_bad_ranges_and_password() -> None:
    with pytest.raises(ValidationError, match="end must follow start"):
        PredictedSpan(data_class=DataClass.EMAIL, start=5, end=5)
    with pytest.raises(ValidationError, match="password is outside"):
        PredictedSpan(data_class=DataClass.PASSWORD, start=0, end=8)


def test_iou_and_matching_close_the_blanket_span_exploit() -> None:
    key = ("breach", "breach-0001-01")
    gold = {(key, DataClass.EMAIL, 0, 10), (key, DataClass.EMAIL, 20, 30)}
    blanket = {(key, DataClass.EMAIL, 0, 30)}
    # One span covering both golds has IoU 1/3 with each — below threshold.
    assert _iou((key, DataClass.EMAIL, 0, 30), (key, DataClass.EMAIL, 0, 10)) < 0.5
    assert _relaxed_match_count(blanket, gold) == 0

    aligned = {(key, DataClass.EMAIL, 0, 11)}
    assert _iou((key, DataClass.EMAIL, 0, 11), (key, DataClass.EMAIL, 0, 10)) >= 0.5
    assert _relaxed_match_count(aligned, gold) == 1
    # A different class on the same page never matches.
    assert _relaxed_match_count({(key, DataClass.PHONE, 0, 10)}, gold) == 0


def test_max_bipartite_matching_augments_under_contention() -> None:
    # left 0 -> {g0}, left 1 -> {g0, g1}: left 1 must fall through to g1.
    assert _max_bipartite_matching([[0], [0, 1]], 2) == 2
    # left 0 -> {g0, g1}, left 1 -> {g0}: left 0 must vacate g0 for left 1.
    assert _max_bipartite_matching([[0, 1], [0]], 2) == 2


def test_task_metric_rejects_non_finite_and_allows_null() -> None:
    assert TaskMetric(name="undefined", value=None, support=0).value is None
    with pytest.raises(ValidationError, match="must be finite"):
        TaskMetric(name="broken", value=float("nan"), support=1)


def _truth_partition(benchmark: ConnectionBenchmark) -> EntityResolutionPrediction:
    by_entity: dict[str, list[UUID]] = {}
    for item in benchmark.answer_key.record_memberships:
        by_entity.setdefault(item.entity_id, []).append(item.record_id)
    return EntityResolutionPrediction(
        clusters=tuple(tuple(records) for records in by_entity.values())
    )


def _er_metric(report: EvaluationReport, name: str) -> float | None:
    return next(metric.value for metric in report.metrics if metric.name == name)


def test_entity_resolution_perfect_partition_scores_one() -> None:
    benchmark = generate_adversarial_connection_benchmark(seed=_SEED)
    report = evaluate_entity_resolution(_truth_partition(benchmark), seed=_SEED)

    assert report.task == "entity_resolution"
    assert report.persona_count == 10
    assert all(metric.value == 1.0 for metric in report.metrics)
    assert sum(s.count for s in report.slices) == 0
    assert {s.value for s in report.slices} == {
        "common_name",
        "unicode_diacritics",
        "twins_shared_address",
        "maiden_name",
        "misspelling_alias",
    }


def test_entity_resolution_singletons_report_null_pairwise() -> None:
    benchmark = generate_adversarial_connection_benchmark(seed=_SEED)
    singletons = EntityResolutionPrediction(
        clusters=tuple(
            (item.record_id,) for item in benchmark.answer_key.record_memberships
        )
    )
    report = evaluate_entity_resolution(singletons, seed=_SEED)

    assert _er_metric(report, "pairwise_precision") is None
    assert _er_metric(report, "pairwise_f1") is None
    assert _er_metric(report, "pairwise_recall") == 0.0
    assert _er_metric(report, "bcubed_precision") == 1.0
    assert round(_er_metric(report, "bcubed_recall") or 0.0, 4) == 0.5556
    assert round(_er_metric(report, "bcubed_f1") or 0.0, 4) == 0.7143


def test_entity_resolution_all_one_cluster_counts_false_merges() -> None:
    benchmark = generate_adversarial_connection_benchmark(seed=_SEED)
    one_cluster = EntityResolutionPrediction(
        clusters=(
            tuple(item.record_id for item in benchmark.answer_key.record_memberships),
        )
    )
    report = evaluate_entity_resolution(one_cluster, seed=_SEED)

    assert round(_er_metric(report, "pairwise_precision") or 0.0, 4) == 0.0588
    assert _er_metric(report, "pairwise_recall") == 1.0
    assert _er_metric(report, "bcubed_recall") == 1.0
    false_merges = sum(s.count for s in report.slices if s.outcome == "false_merge")
    assert false_merges == 15
    assert sum(s.count for s in report.slices if s.outcome == "false_split") == 0


def test_entity_resolution_rejects_incomplete_partitions() -> None:
    benchmark = generate_adversarial_connection_benchmark(seed=_SEED)
    complete = _truth_partition(benchmark)

    dropped = EntityResolutionPrediction(clusters=complete.clusters[1:])
    with pytest.raises(EvaluationInputError, match="partition exactly"):
        evaluate_entity_resolution(dropped, seed=_SEED)

    with_unknown = EntityResolutionPrediction(
        clusters=(*complete.clusters, (uuid5(NAMESPACE_DNS, "not-a-record"),))
    )
    with pytest.raises(EvaluationInputError, match="partition exactly"):
        evaluate_entity_resolution(with_unknown, seed=_SEED)


def test_entity_resolution_prediction_rejects_empty_and_duplicate_clusters() -> None:
    record = uuid5(NAMESPACE_DNS, "record")
    with pytest.raises(ValidationError, match="clusters must be non-empty"):
        EntityResolutionPrediction(clusters=((),))
    with pytest.raises(ValidationError, match="only one cluster"):
        EntityResolutionPrediction(clusters=((record,), (record,)))
