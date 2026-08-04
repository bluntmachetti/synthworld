"""The ambiguity partition and evidence-policy channels stay lossless and separate."""

from __future__ import annotations

from collections import defaultdict
from inspect import signature
from uuid import UUID

import pytest
from pydantic import ValidationError

from synthworld.ambiguity import (
    AmbiguityBenchmark,
    PairDisposition,
    PairPrediction,
    PublicRecordPair,
    ScenarioKind,
)
from synthworld.ambiguity_generator import generate_ambiguity_benchmark
from synthworld.ambiguity_metrics import (
    AmbiguityEvaluationError,
    evaluate_ambiguity_dispositions,
    evaluate_ambiguity_predictions,
)
from synthworld.ambiguity_partition import (
    AmbiguityPartitionEvaluationError,
    DenominatedMetric,
    derive_ambiguity_pair_predictions,
    evaluate_ambiguity_memberships,
    validate_ambiguity_partition,
)
from synthworld.ambiguity_serialization import DispositionTruth, MembershipTruth
from synthworld.evaluation import EntityResolutionPrediction

_SEED = 20_260_731


def _benchmark() -> AmbiguityBenchmark:
    return generate_ambiguity_benchmark(seed=_SEED)


def _membership_truth(benchmark: AmbiguityBenchmark) -> MembershipTruth:
    return MembershipTruth(record_memberships=benchmark.answer_key.record_memberships)


def _disposition_truth(benchmark: AmbiguityBenchmark) -> DispositionTruth:
    return DispositionTruth(pairs=benchmark.answer_key.pairs)


def _truth_partition(benchmark: AmbiguityBenchmark) -> EntityResolutionPrediction:
    grouped: dict[str, list[UUID]] = defaultdict(list)
    for membership in benchmark.answer_key.record_memberships:
        grouped[membership.entity_id].append(membership.record_id)
    return EntityResolutionPrediction(
        clusters=tuple(
            tuple(sorted(record_ids, key=lambda item: item.int))
            for _entity, record_ids in sorted(grouped.items())
        )
    )


def _merge_records(
    prediction: EntityResolutionPrediction, left: UUID, right: UUID
) -> EntityResolutionPrediction:
    clusters = [list(cluster) for cluster in prediction.clusters]
    left_index = next(
        index for index, cluster in enumerate(clusters) if left in cluster
    )
    right_index = next(
        index for index, cluster in enumerate(clusters) if right in cluster
    )
    assert left_index != right_index
    clusters[left_index].extend(clusters[right_index])
    del clusters[right_index]
    return EntityResolutionPrediction(
        clusters=tuple(tuple(cluster) for cluster in clusters)
    )


def _split_first_entity(
    prediction: EntityResolutionPrediction,
) -> EntityResolutionPrediction:
    target = next(cluster for cluster in prediction.clusters if len(cluster) > 1)
    return EntityResolutionPrediction(
        clusters=tuple(
            cluster for cluster in prediction.clusters if cluster is not target
        )
        + tuple((record_id,) for record_id in target)
    )


def _truth_pair_predictions(
    benchmark: AmbiguityBenchmark,
) -> tuple[PairPrediction, ...]:
    return tuple(
        PairPrediction(
            left_record_id=pair.left_record_id,
            right_record_id=pair.right_record_id,
            disposition=pair.disposition,
        )
        for pair in benchmark.answer_key.pairs
    )


def _replace_scenario_prediction(
    predictions: tuple[PairPrediction, ...],
    benchmark: AmbiguityBenchmark,
    scenario: ScenarioKind,
    disposition: PairDisposition,
) -> tuple[PairPrediction, ...]:
    pair = next(
        item for item in benchmark.answer_key.pairs if item.scenario is scenario
    )
    return tuple(
        item.model_copy(update={"disposition": disposition})
        if (item.left_record_id, item.right_record_id)
        == (pair.left_record_id, pair.right_record_id)
        else item
        for item in predictions
    )


def test_truth_partition_reports_exact_denominators() -> None:
    benchmark = _benchmark()
    report = evaluate_ambiguity_memberships(
        _truth_partition(benchmark),
        public=benchmark.public,
        truth=_membership_truth(benchmark),
    )

    assert report.record_count == 30
    assert report.truth_entity_count == report.predicted_cluster_count == 23
    assert report.true_positive_pair_count == 7
    assert report.predicted_positive_pair_count == 7
    assert report.truth_positive_pair_count == 7
    assert report.false_merge_pair_count == report.false_split_pair_count == 0
    assert report.pairwise_precision.value == 1.0
    assert report.pairwise_precision.denominator == 7
    assert report.pairwise_recall.value == 1.0
    assert report.pairwise_recall.denominator == 7
    assert report.pairwise_f1.value == 1.0
    assert report.pairwise_f1.numerator == 14
    assert report.pairwise_f1.denominator == 14
    assert report.b_cubed_precision.denominator == 30
    assert report.b_cubed_recall.denominator == 30
    assert report.b_cubed_f1.value == 1.0
    serialized = report.model_dump_json()
    assert "scenario" not in serialized
    assert "disposition" not in serialized


def test_false_merge_and_false_split_harm_different_partition_metrics() -> None:
    benchmark = _benchmark()
    perfect = _truth_partition(benchmark)
    singleton_clusters = [cluster for cluster in perfect.clusters if len(cluster) == 1]
    false_merge = _merge_records(
        perfect, singleton_clusters[0][0], singleton_clusters[1][0]
    )
    false_split = _split_first_entity(perfect)

    merge_report = evaluate_ambiguity_memberships(
        false_merge, public=benchmark.public, truth=_membership_truth(benchmark)
    )
    split_report = evaluate_ambiguity_memberships(
        false_split, public=benchmark.public, truth=_membership_truth(benchmark)
    )

    assert merge_report.false_merge_pair_count == 1
    assert merge_report.false_split_pair_count == 0
    assert merge_report.pairwise_precision.value is not None
    assert merge_report.pairwise_precision.value < 1.0
    assert merge_report.pairwise_recall.value == 1.0
    assert merge_report.b_cubed_precision.value is not None
    assert merge_report.b_cubed_precision.value < 1.0

    assert split_report.false_merge_pair_count == 0
    assert split_report.false_split_pair_count == 1
    assert split_report.pairwise_precision.value == 1.0
    assert split_report.pairwise_recall.value is not None
    assert split_report.pairwise_recall.value < 1.0
    assert split_report.b_cubed_recall.value is not None
    assert split_report.b_cubed_recall.value < 1.0


def test_cross_scenario_false_merge_is_not_lost_in_pair_projection() -> None:
    """The selected fifteen pairs cannot represent every error in a partition."""

    benchmark = _benchmark()
    perfect = _truth_partition(benchmark)
    by_scenario = {item.scenario: item for item in benchmark.answer_key.pairs}
    recycled = by_scenario[ScenarioKind.RECYCLED_PHONE].left_record_id
    reused = by_scenario[ScenarioKind.REUSED_USERNAME].left_record_id
    corrupted = _merge_records(perfect, recycled, reused)

    assert derive_ambiguity_pair_predictions(
        corrupted, public=benchmark.public
    ) == derive_ambiguity_pair_predictions(perfect, public=benchmark.public)

    report = evaluate_ambiguity_memberships(
        corrupted, public=benchmark.public, truth=_membership_truth(benchmark)
    )
    assert report.false_merge_pair_count == 1
    assert report.pairwise_precision.value is not None
    assert report.pairwise_precision.value < 1.0


def test_partition_projection_is_public_only_and_forces_binary_decisions() -> None:
    benchmark = _benchmark()
    predictions = derive_ambiguity_pair_predictions(
        _truth_partition(benchmark), public=benchmark.public
    )

    assert len(predictions) == len(benchmark.public.pairs_to_decide)
    assert {(item.left_record_id, item.right_record_id) for item in predictions} == {
        (item.left_record_id, item.right_record_id)
        for item in benchmark.public.pairs_to_decide
    }
    assert {item.disposition for item in predictions} == {
        PairDisposition.MERGE,
        PairDisposition.SEPARATE,
    }
    assert PairDisposition.INSUFFICIENT not in {
        item.disposition for item in predictions
    }
    assert set(signature(derive_ambiguity_pair_predictions).parameters) == {
        "prediction",
        "public",
    }


def test_forced_partition_decisions_are_scored_only_against_dispositions() -> None:
    benchmark = _benchmark()
    predictions = derive_ambiguity_pair_predictions(
        _truth_partition(benchmark), public=benchmark.public
    )
    report = evaluate_ambiguity_dispositions(
        predictions,
        public=benchmark.public,
        truth=_disposition_truth(benchmark),
    )

    assert set(signature(evaluate_ambiguity_dispositions).parameters) == {
        "predictions",
        "public",
        "truth",
    }
    assert report.pair_count == 15
    assert report.decided_count == report.pair_count
    assert report.abstained_count == 0
    # Eleven, not twelve, since #77: `same_name_and_date_of_birth` is `insufficient`,
    # so the clairvoyant partition-follower's "separate" there is an unwarranted
    # decision - it answered from the truth, which the public evidence cannot reach.
    # A scorer that rewarded it would be scoring clairvoyance, which is the exact
    # conflation this evaluation exists to refuse.
    assert report.decidable_count == 11
    assert report.correct_decided_count == 11
    assert report.coverage == 1.0
    assert report.decided_precision == 11 / 15
    assert report.decided_recall == 1.0
    assert report.unwarranted_decisions == 4
    assert set(report.low_support_scenarios) == set(ScenarioKind)
    serialized = report.model_dump_json()
    assert "entity_id" not in serialized
    assert "pairwise" not in serialized
    assert "b_cubed" not in serialized


def test_explicit_disposition_channel_preserves_legacy_formulas() -> None:
    benchmark = _benchmark()
    predictions = _truth_pair_predictions(benchmark)
    explicit = evaluate_ambiguity_dispositions(
        predictions,
        public=benchmark.public,
        truth=_disposition_truth(benchmark),
    )
    legacy = evaluate_ambiguity_predictions(predictions, benchmark=benchmark)

    for field in (
        "pair_count",
        "decided_count",
        "abstained_count",
        "coverage",
        "decided_precision",
        "decided_recall",
        "false_merges",
        "false_splits",
        "unwarranted_decisions",
        "scenarios",
        "low_support_scenarios",
    ):
        assert getattr(explicit, field) == getattr(legacy, field)


@pytest.mark.parametrize(
    ("scenario", "replacement", "field"),
    [
        (ScenarioKind.RECYCLED_PHONE, PairDisposition.MERGE, "false_merges"),
        (ScenarioKind.STALE_ATTRIBUTE, PairDisposition.SEPARATE, "false_splits"),
        (
            ScenarioKind.PARTIAL_WITH_CONTRADICTION,
            PairDisposition.SEPARATE,
            "unwarranted_decisions",
        ),
    ],
)
def test_disposition_mutations_worsen_the_named_error_channel(
    scenario: ScenarioKind,
    replacement: PairDisposition,
    field: str,
) -> None:
    benchmark = _benchmark()
    perfect = _truth_pair_predictions(benchmark)
    baseline = evaluate_ambiguity_dispositions(
        perfect, public=benchmark.public, truth=_disposition_truth(benchmark)
    )
    mutated = evaluate_ambiguity_dispositions(
        _replace_scenario_prediction(perfect, benchmark, scenario, replacement),
        public=benchmark.public,
        truth=_disposition_truth(benchmark),
    )

    assert getattr(baseline, field) == 0
    assert getattr(mutated, field) == 1
    assert mutated.correct_decided_count < baseline.correct_decided_count or (
        field == "unwarranted_decisions"
        and mutated.decided_count > baseline.decided_count
    )


def test_singleton_submission_makes_positive_pair_precision_undefined() -> None:
    benchmark = _benchmark()
    singletons = EntityResolutionPrediction(
        clusters=tuple(
            (record.id,) for record in benchmark.public.corpus.identity_records
        )
    )
    report = evaluate_ambiguity_memberships(
        singletons, public=benchmark.public, truth=_membership_truth(benchmark)
    )

    assert report.pairwise_precision.value is None
    assert report.pairwise_precision.denominator == 0
    assert report.pairwise_precision.undefined_reason is not None
    assert report.pairwise_recall.value == 0.0
    assert report.pairwise_f1.value is None
    assert report.b_cubed_precision.value == 1.0
    assert report.b_cubed_recall.value is not None
    assert report.b_cubed_recall.value < 1.0


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("empty", "non-empty"),
        ("duplicate", "more than one"),
        ("unknown", "unknown"),
        ("missing", "missing"),
    ],
)
def test_malformed_partitions_abort_before_truth_scoring(
    mutation: str, message: str
) -> None:
    benchmark = _benchmark()
    complete = _truth_partition(benchmark)
    first = complete.clusters[0][0]
    if mutation == "empty":
        clusters = (*complete.clusters, ())
    elif mutation == "duplicate":
        clusters = (*complete.clusters, (first,))
    elif mutation == "unknown":
        clusters = (*complete.clusters, (UUID(int=0),))
    else:
        clusters = complete.clusters[1:]
    malformed = complete.model_copy(update={"clusters": clusters})

    with pytest.raises(AmbiguityPartitionEvaluationError, match=message):
        validate_ambiguity_partition(malformed, public=benchmark.public)


def test_membership_truth_must_match_the_public_record_set() -> None:
    benchmark = _benchmark()
    memberships = benchmark.answer_key.record_memberships
    partition = _truth_partition(benchmark)

    with pytest.raises(AmbiguityPartitionEvaluationError, match="duplicate"):
        evaluate_ambiguity_memberships(
            partition,
            public=benchmark.public,
            truth=MembershipTruth(record_memberships=(*memberships, memberships[0])),
        )
    with pytest.raises(AmbiguityPartitionEvaluationError, match="exactly"):
        evaluate_ambiguity_memberships(
            partition,
            public=benchmark.public,
            truth=MembershipTruth(record_memberships=memberships[:-1]),
        )


def test_public_task_structure_is_validated_without_truth() -> None:
    benchmark = _benchmark()
    partition = _truth_partition(benchmark)
    public = benchmark.public

    empty_corpus = public.corpus.model_copy(update={"identity_records": ()})
    with pytest.raises(AmbiguityPartitionEvaluationError, match="no identity"):
        validate_ambiguity_partition(
            partition, public=public.model_copy(update={"corpus": empty_corpus})
        )

    first_record = public.corpus.identity_records[0]
    duplicate_corpus = public.corpus.model_copy(
        update={"identity_records": (*public.corpus.identity_records, first_record)}
    )
    with pytest.raises(AmbiguityPartitionEvaluationError, match="duplicate identity"):
        validate_ambiguity_partition(
            partition, public=public.model_copy(update={"corpus": duplicate_corpus})
        )

    first_pair = public.pairs_to_decide[0]
    duplicate_pairs = public.model_copy(
        update={"pairs_to_decide": (first_pair, first_pair)}
    )
    with pytest.raises(AmbiguityPartitionEvaluationError, match="duplicate task"):
        validate_ambiguity_partition(partition, public=duplicate_pairs)

    unknown_pair = PublicRecordPair.model_construct(
        left_record_id=UUID(int=0), right_record_id=first_pair.right_record_id
    )
    bad_reference = public.model_copy(update={"pairs_to_decide": (unknown_pair,)})
    with pytest.raises(AmbiguityPartitionEvaluationError, match="reference public"):
        validate_ambiguity_partition(partition, public=bad_reference)


def test_disposition_truth_and_submissions_must_cover_public_pairs_exactly() -> None:
    benchmark = _benchmark()
    predictions = _truth_pair_predictions(benchmark)
    truth = _disposition_truth(benchmark)

    with pytest.raises(AmbiguityEvaluationError, match="duplicate pair"):
        evaluate_ambiguity_dispositions(
            predictions,
            public=benchmark.public,
            truth=DispositionTruth(pairs=(*truth.pairs, truth.pairs[0])),
        )
    with pytest.raises(AmbiguityEvaluationError, match="truth must cover"):
        evaluate_ambiguity_dispositions(
            predictions,
            public=benchmark.public,
            truth=DispositionTruth(pairs=truth.pairs[:-1]),
        )
    duplicate_public = benchmark.public.model_copy(
        update={
            "pairs_to_decide": (
                benchmark.public.pairs_to_decide[0],
                benchmark.public.pairs_to_decide[0],
            )
        }
    )
    with pytest.raises(AmbiguityEvaluationError, match=r"public task.*duplicate"):
        evaluate_ambiguity_dispositions(
            predictions, public=duplicate_public, truth=truth
        )
    empty_public = benchmark.public.model_copy(update={"pairs_to_decide": ()})
    with pytest.raises(AmbiguityEvaluationError, match="no record pairs"):
        evaluate_ambiguity_dispositions(predictions, public=empty_public, truth=truth)
    first_public_pair = benchmark.public.pairs_to_decide[0]
    unknown_pair = PublicRecordPair.model_construct(
        left_record_id=UUID(int=0),
        right_record_id=first_public_pair.right_record_id,
    )
    bad_reference = benchmark.public.model_copy(
        update={"pairs_to_decide": (unknown_pair,)}
    )
    with pytest.raises(AmbiguityEvaluationError, match="non-public"):
        evaluate_ambiguity_dispositions(predictions, public=bad_reference, truth=truth)
    with pytest.raises(AmbiguityEvaluationError, match="submitted twice"):
        evaluate_ambiguity_dispositions(
            (*predictions, predictions[0]), public=benchmark.public, truth=truth
        )
    with pytest.raises(AmbiguityEvaluationError, match="cover exactly"):
        evaluate_ambiguity_dispositions(
            predictions[:-1], public=benchmark.public, truth=truth
        )


def test_denominated_metrics_reject_incoherent_numbers() -> None:
    with pytest.raises(ValidationError, match="numerator and denominator"):
        DenominatedMetric(
            value=1.0,
            numerator=float("inf"),
            denominator=1.0,
            denominator_meaning="test cases",
        )
    with pytest.raises(ValidationError, match="metric value"):
        DenominatedMetric(
            value=float("inf"),
            numerator=1.0,
            denominator=1.0,
            denominator_meaning="test cases",
        )
    with pytest.raises(ValidationError, match="must explain"):
        DenominatedMetric(
            value=None,
            numerator=0.0,
            denominator=0.0,
            denominator_meaning="test cases",
        )
    with pytest.raises(ValidationError, match="cannot have"):
        DenominatedMetric(
            value=1.0,
            numerator=1.0,
            denominator=1.0,
            denominator_meaning="test cases",
            undefined_reason="not really undefined",
        )
    with pytest.raises(ValidationError, match="meaning must be nonblank"):
        DenominatedMetric(
            value=1.0,
            numerator=1.0,
            denominator=1.0,
            denominator_meaning=" ",
        )
    with pytest.raises(ValidationError, match=r"must be in \[0, 1\]"):
        DenominatedMetric(
            value=2.0,
            numerator=2.0,
            denominator=1.0,
            denominator_meaning="test cases",
        )
    with pytest.raises(ValidationError, match="zero denominator"):
        DenominatedMetric(
            value=0.0,
            numerator=0.0,
            denominator=0.0,
            denominator_meaning="test cases",
        )
    with pytest.raises(ValidationError, match="equal numerator"):
        DenominatedMetric(
            value=0.5,
            numerator=1.0,
            denominator=3.0,
            denominator_meaning="test cases",
        )
