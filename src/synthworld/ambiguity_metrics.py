"""Scoring for the ambiguity pack, built so an aggregate cannot hide a failure.

Issue #41 opens with a resolver scoring pairwise F1 1.0 on a pack whose positives
aligned with exact joins. One number said it worked; a mutation matrix said it
broke four ways. So this report has no headline score. It carries per-scenario
outcomes, false merges and false splits counted separately, and a machine-readable
low-support flag on every slice too small to conclude from.

Three definitions decide everything else:

*decided* - the system committed to ``merge`` or ``separate``. Abstention is not a
wrong answer and is not counted as one.

*false merge* - ``merge`` predicted where truth says ``separate``. *false split* -
``separate`` where truth says ``merge``. Kept apart because they are different
harms: a false merge attaches one person's record to another, a false split leaves
someone unresolved, and a single F1 trades them against each other silently.

*coverage* - decided pairs over all pairs. A system that abstains everywhere scores
perfect precision, so precision is meaningless without it.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Literal
from uuid import UUID

from synthworld.ambiguity import (
    AmbiguityBenchmark,
    PairDisposition,
    PairPrediction,
    PairTruth,
    PublicAmbiguityTask,
    ScenarioKind,
)
from synthworld.ambiguity_serialization import DispositionTruth
from synthworld.models import SyntheticModel

#: Below this many pairs a slice is reported but must not be concluded from. The
#: canonical pack carries one pair per scenario and therefore warns on all of them:
#: it is a conformance fixture, in the sense Asteria Agentic v1 is, not a
#: statistical benchmark. Seed variants are what raise support.
MINIMUM_SCENARIO_SUPPORT = 3
AMBIGUITY_DISPOSITION_SCORING_VERSION: Literal["1.0.0"] = "1.0.0"


class ScenarioOutcome(SyntheticModel):
    scenario: ScenarioKind
    expected: PairDisposition
    support: int
    correct: int
    predicted: Mapping[str, int]
    #: True when `support` is below the declared minimum. Machine-readable, so a
    #: consumer rendering a table cannot quietly present a 1-of-1 slice as a rate.
    low_support: bool


class ClusterMetrics(SyntheticModel):
    """Pairwise and B-cubed, computed over clusters induced by merge decisions.

    Issue #41 asks for both from #1, and they disagree in a way that matters here.
    Pairwise weights a large cluster quadratically, so one over-merge of a busy
    entity can dominate; B-cubed weights per record, so it reports what an average
    person's records experienced. A system that merges everything scores well on
    pairwise recall and badly on B-cubed precision, and seeing both is the point.
    """

    pairwise_precision: float | None
    pairwise_recall: float | None
    pairwise_f1: float | None
    b_cubed_precision: float
    b_cubed_recall: float
    b_cubed_f1: float


class AmbiguityMetrics(SyntheticModel):
    """Deliberately without an aggregate score."""

    pair_count: int
    decided_count: int
    abstained_count: int
    #: Decided pairs over all pairs. Without it, precision rewards silence.
    coverage: float
    decided_precision: float | None
    decided_recall: float | None
    false_merges: int
    false_splits: int
    #: Decisions on pairs the public evidence cannot settle: the system should have
    #: abstained and instead guessed. Counted apart from false merges and splits
    #: because the error is different - not a wrong answer, an unwarranted one.
    unwarranted_decisions: int
    scenarios: tuple[ScenarioOutcome, ...]
    low_support_scenarios: tuple[ScenarioKind, ...]
    #: Cluster-level view of the same submission, so a pair-decision system can be
    #: compared against the cluster contract without emitting clusters itself.
    clusters: ClusterMetrics


class AmbiguityDispositionMetrics(SyntheticModel):
    """Evidence-policy scores computed without loading membership truth.

    The exact denominators are fields rather than prose: ``coverage`` is
    ``decided_count / pair_count``; ``decided_precision`` is
    ``correct_decided_count / decided_count``; and ``decided_recall`` is
    ``correct_decided_count / decidable_count``.  The historical names and formulas
    are preserved under an explicit scoring version.
    """

    schema_version: Literal["1.0.0"] = "1.0.0"
    scoring_version: Literal["1.0.0"] = AMBIGUITY_DISPOSITION_SCORING_VERSION
    task: Literal["ambiguity_evidence_disposition"] = "ambiguity_evidence_disposition"
    seed: int
    public_schema_version: str
    submission_schema_version: str
    disposition_truth_schema_version: str
    pair_count: int
    decided_count: int
    abstained_count: int
    decidable_count: int
    correct_decided_count: int
    coverage: float
    decided_precision: float | None
    decided_recall: float | None
    false_merges: int
    false_splits: int
    unwarranted_decisions: int
    scenarios: tuple[ScenarioOutcome, ...]
    low_support_scenarios: tuple[ScenarioKind, ...]


class AmbiguityEvaluationError(ValueError):
    """Raised when a submission does not cover the benchmark's pairs exactly."""


def _key(left: UUID, right: UUID) -> tuple[UUID, UUID]:
    return (left, right) if left < right else (right, left)


def _induced_clusters(
    records: Iterable[UUID], merges: Iterable[tuple[UUID, UUID]]
) -> dict[UUID, frozenset[UUID]]:
    """Union-find over merge decisions.

    Merges are transitive whether or not a system intends them to be: deciding
    a~b and b~c asserts a~c, and scoring the pairs independently would let a
    contradictory submission look consistent.
    """

    parent: dict[UUID, UUID] = {record: record for record in records}

    def find(item: UUID) -> UUID:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    for left, right in merges:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    grouped: dict[UUID, set[UUID]] = {}
    for record in parent:
        grouped.setdefault(find(record), set()).add(record)
    return {
        record: frozenset(members) for members in grouped.values() for record in members
    }


def _cluster_metrics(
    predicted: Mapping[UUID, frozenset[UUID]],
    truth: Mapping[UUID, frozenset[UUID]],
) -> ClusterMetrics:
    def pairs(groups: Mapping[UUID, frozenset[UUID]]) -> set[tuple[UUID, UUID]]:
        return {
            _key(left, right)
            for members in set(groups.values())
            for left in members
            for right in members
            if left < right
        }

    predicted_pairs, truth_pairs = pairs(predicted), pairs(truth)
    overlap = len(predicted_pairs & truth_pairs)
    precision = overlap / len(predicted_pairs) if predicted_pairs else None
    recall = overlap / len(truth_pairs) if truth_pairs else None
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else None

    # B-cubed averages over records, so it cannot be dominated by one large cluster.
    b_precision = sum(
        len(predicted[record] & truth[record]) / len(predicted[record])
        for record in truth
    ) / len(truth)
    b_recall = sum(
        len(predicted[record] & truth[record]) / len(truth[record]) for record in truth
    ) / len(truth)
    b_f1 = (
        2 * b_precision * b_recall / (b_precision + b_recall)
        if b_precision + b_recall
        else 0.0
    )
    return ClusterMetrics(
        pairwise_precision=precision,
        pairwise_recall=recall,
        pairwise_f1=f1,
        b_cubed_precision=b_precision,
        b_cubed_recall=b_recall,
        b_cubed_f1=b_f1,
    )


def evaluate_ambiguity_dispositions(
    predictions: Iterable[PairPrediction],
    *,
    public: PublicAmbiguityTask,
    truth: DispositionTruth,
) -> AmbiguityDispositionMetrics:
    """Score pair decisions using public task identifiers and disposition truth."""

    truth_pairs: dict[tuple[UUID, UUID], PairTruth] = {
        _key(item.left_record_id, item.right_record_id): item for item in truth.pairs
    }
    if len(truth_pairs) != len(truth.pairs):
        raise AmbiguityEvaluationError("disposition truth contains a duplicate pair")
    public_keys = [
        _key(item.left_record_id, item.right_record_id)
        for item in public.pairs_to_decide
    ]
    if not public_keys:
        raise AmbiguityEvaluationError("the public task contains no record pairs")
    if len(public_keys) != len(set(public_keys)):
        raise AmbiguityEvaluationError("the public task contains a duplicate pair")
    public_record_ids = {item.id for item in public.corpus.identity_records}
    if any(not set(key) <= public_record_ids for key in public_keys):
        raise AmbiguityEvaluationError(
            "the public task pair list references a non-public record"
        )
    if set(public_keys) != set(truth_pairs):
        raise AmbiguityEvaluationError(
            "disposition truth must cover exactly the public task pairs"
        )

    prediction_items = tuple(predictions)
    submitted: dict[tuple[UUID, UUID], PairDisposition] = {}
    for prediction in prediction_items:
        key = _key(prediction.left_record_id, prediction.right_record_id)
        if key in submitted:
            raise AmbiguityEvaluationError("a record pair was submitted twice")
        submitted[key] = prediction.disposition
    if set(submitted) != set(truth_pairs):
        raise AmbiguityEvaluationError(
            "predictions must cover exactly the benchmark's record pairs"
        )

    false_merges = false_splits = unwarranted = decided = correct_decided = 0
    decidable = 0
    by_scenario: dict[ScenarioKind, Counter[str]] = {}
    correct_by_scenario: Counter[ScenarioKind] = Counter()

    for key, expected in truth_pairs.items():
        predicted = submitted[key]
        by_scenario.setdefault(expected.scenario, Counter())[predicted.value] += 1
        if expected.disposition is not PairDisposition.INSUFFICIENT:
            decidable += 1
        if predicted is expected.disposition:
            correct_by_scenario[expected.scenario] += 1
        if predicted is PairDisposition.INSUFFICIENT:
            continue
        decided += 1
        if predicted is expected.disposition:
            correct_decided += 1
        elif expected.disposition is PairDisposition.INSUFFICIENT:
            unwarranted += 1
        elif predicted is PairDisposition.MERGE:
            false_merges += 1
        else:
            false_splits += 1

    outcomes = tuple(
        ScenarioOutcome(
            scenario=scenario,
            expected=next(
                item.disposition for item in truth.pairs if item.scenario is scenario
            ),
            support=sum(by_scenario[scenario].values()),
            correct=correct_by_scenario[scenario],
            predicted=dict(sorted(by_scenario[scenario].items())),
            low_support=sum(by_scenario[scenario].values()) < MINIMUM_SCENARIO_SUPPORT,
        )
        for scenario in sorted(by_scenario, key=lambda item: item.value)
    )
    total = len(truth_pairs)
    return AmbiguityDispositionMetrics(
        seed=public.corpus.seed,
        public_schema_version=public.schema_version,
        submission_schema_version=prediction_items[0].schema_version,
        disposition_truth_schema_version=truth.schema_version,
        pair_count=total,
        decided_count=decided,
        abstained_count=total - decided,
        decidable_count=decidable,
        correct_decided_count=correct_decided,
        coverage=decided / total,
        decided_precision=correct_decided / decided if decided else None,
        decided_recall=correct_decided / decidable if decidable else None,
        false_merges=false_merges,
        false_splits=false_splits,
        unwarranted_decisions=unwarranted,
        scenarios=outcomes,
        low_support_scenarios=tuple(
            item.scenario for item in outcomes if item.low_support
        ),
    )


def evaluate_ambiguity_predictions(
    predictions: Iterable[PairPrediction],
    *,
    benchmark: AmbiguityBenchmark,
) -> AmbiguityMetrics:
    """Legacy combined report; prefer the two independently typed evaluators."""

    prediction_items = tuple(predictions)
    disposition_metrics = evaluate_ambiguity_dispositions(
        prediction_items,
        public=benchmark.public,
        truth=DispositionTruth(pairs=benchmark.answer_key.pairs),
    )
    submitted = {
        _key(item.left_record_id, item.right_record_id): item.disposition
        for item in prediction_items
    }
    record_ids = [item.record_id for item in benchmark.answer_key.record_memberships]
    entity_of = {
        item.record_id: item.entity_id
        for item in benchmark.answer_key.record_memberships
    }
    truth_clusters = {
        record: frozenset(
            other for other in record_ids if entity_of[other] == entity_of[record]
        )
        for record in record_ids
    }
    predicted_clusters = _induced_clusters(
        record_ids,
        (key for key, value in submitted.items() if value is PairDisposition.MERGE),
    )

    return AmbiguityMetrics(
        pair_count=disposition_metrics.pair_count,
        decided_count=disposition_metrics.decided_count,
        abstained_count=disposition_metrics.abstained_count,
        coverage=disposition_metrics.coverage,
        decided_precision=disposition_metrics.decided_precision,
        decided_recall=disposition_metrics.decided_recall,
        false_merges=disposition_metrics.false_merges,
        false_splits=disposition_metrics.false_splits,
        unwarranted_decisions=disposition_metrics.unwarranted_decisions,
        scenarios=disposition_metrics.scenarios,
        low_support_scenarios=disposition_metrics.low_support_scenarios,
        clusters=_cluster_metrics(predicted_clusters, truth_clusters),
    )


__all__ = [
    "AMBIGUITY_DISPOSITION_SCORING_VERSION",
    "MINIMUM_SCENARIO_SUPPORT",
    "AmbiguityDispositionMetrics",
    "AmbiguityEvaluationError",
    "AmbiguityMetrics",
    "ClusterMetrics",
    "ScenarioOutcome",
    "evaluate_ambiguity_dispositions",
    "evaluate_ambiguity_predictions",
]
