"""Complete-partition evaluation for the ambiguity benchmark.

The ambiguity pack has two independent questions and therefore two independent
truths.  This module answers only the canonical-membership question: it validates a
consumer's complete cluster submission against the public record set and scores the
raw partition against separately supplied membership truth.  It never consumes
scenario labels or evidence dispositions.

The same validated partition can also be projected, using public pair identifiers
alone, into forced ``merge``/``separate`` decisions.  That projection cannot express
``insufficient`` and belongs to the separate disposition evaluator.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from itertools import combinations
from typing import Literal
from uuid import UUID

from pydantic import Field

from synthworld.ambiguity import PairDisposition, PairPrediction, PublicAmbiguityTask
from synthworld.ambiguity_serialization import MembershipTruth
from synthworld.evaluation import EntityResolutionPrediction
from synthworld.models import DenominatedMetric, SyntheticModel

AMBIGUITY_MEMBERSHIP_SCORING_VERSION: Literal["1.0.0"] = "1.0.0"


class AmbiguityPartitionEvaluationError(ValueError):
    """Raised when public input, a partition, or membership truth is malformed."""


class AmbiguityMembershipMetrics(SyntheticModel):
    """Complete-partition scores against canonical membership truth.

    Pairwise precision uses predicted same-cluster pairs as its denominator;
    pairwise recall uses true same-entity pairs.  Pairwise F1 is
    ``2 * true_positive_pairs / (predicted_pairs + truth_pairs)`` when precision is
    defined.  B-cubed precision and recall average their per-record fractions over
    ``record_count``; B-cubed F1 is their harmonic mean.  The embedded metric
    objects preserve those numerators, denominators, and definitions explicitly.
    """

    schema_version: Literal["1.0.0"] = "1.0.0"
    scoring_version: Literal["1.0.0"] = AMBIGUITY_MEMBERSHIP_SCORING_VERSION
    task: Literal["ambiguity_membership"] = "ambiguity_membership"
    seed: int
    public_schema_version: str
    submission_schema_version: str
    membership_truth_schema_version: str
    record_count: int = Field(ge=1)
    predicted_cluster_count: int = Field(ge=1)
    truth_entity_count: int = Field(ge=1)
    true_positive_pair_count: int = Field(ge=0)
    predicted_positive_pair_count: int = Field(ge=0)
    truth_positive_pair_count: int = Field(ge=0)
    false_merge_pair_count: int = Field(ge=0)
    false_split_pair_count: int = Field(ge=0)
    pairwise_precision: DenominatedMetric
    pairwise_recall: DenominatedMetric
    pairwise_f1: DenominatedMetric
    b_cubed_precision: DenominatedMetric
    b_cubed_recall: DenominatedMetric
    b_cubed_f1: DenominatedMetric


def _record_ids(public: PublicAmbiguityTask) -> frozenset[UUID]:
    record_sequence = tuple(item.id for item in public.corpus.identity_records)
    records = frozenset(record_sequence)
    if not records:
        raise AmbiguityPartitionEvaluationError(
            "ambiguity public input contains no identity records"
        )
    if len(records) != len(record_sequence):
        raise AmbiguityPartitionEvaluationError(
            "ambiguity public input contains a duplicate identity record"
        )
    pair_keys = [
        (item.left_record_id, item.right_record_id) for item in public.pairs_to_decide
    ]
    if len(pair_keys) != len(set(pair_keys)):
        raise AmbiguityPartitionEvaluationError(
            "ambiguity public input contains a duplicate task pair"
        )
    if any(not set(pair) <= records for pair in pair_keys):
        raise AmbiguityPartitionEvaluationError(
            "ambiguity public task pairs must reference public records"
        )
    return records


def validate_ambiguity_partition(
    prediction: EntityResolutionPrediction,
    *,
    public: PublicAmbiguityTask,
) -> None:
    """Require one non-empty cluster membership for every public record exactly."""

    public_ids = _record_ids(public)
    if any(not cluster for cluster in prediction.clusters):
        raise AmbiguityPartitionEvaluationError("predicted clusters must be non-empty")
    submitted = tuple(
        record_id for cluster in prediction.clusters for record_id in cluster
    )
    if len(submitted) != len(set(submitted)):
        raise AmbiguityPartitionEvaluationError(
            "a public record appears in more than one predicted cluster"
        )
    submitted_ids = set(submitted)
    unknown = submitted_ids - public_ids
    missing = public_ids - submitted_ids
    if unknown:
        raise AmbiguityPartitionEvaluationError(
            f"predicted partition contains {len(unknown)} unknown record(s)"
        )
    if missing:
        raise AmbiguityPartitionEvaluationError(
            f"predicted partition is missing {len(missing)} public record(s)"
        )


def derive_ambiguity_pair_predictions(
    prediction: EntityResolutionPrediction,
    *,
    public: PublicAmbiguityTask,
) -> tuple[PairPrediction, ...]:
    """Project a complete partition to forced public-pair decisions without truth.

    Records in one cluster become ``merge`` and records in different clusters become
    ``separate``.  A partition has no representation of evidential uncertainty, so
    this projection can never emit ``insufficient``.
    """

    validate_ambiguity_partition(prediction, public=public)
    cluster_of = {
        record_id: index
        for index, cluster in enumerate(prediction.clusters)
        for record_id in cluster
    }
    return tuple(
        PairPrediction(
            left_record_id=pair.left_record_id,
            right_record_id=pair.right_record_id,
            disposition=(
                PairDisposition.MERGE
                if cluster_of[pair.left_record_id] == cluster_of[pair.right_record_id]
                else PairDisposition.SEPARATE
            ),
        )
        for pair in public.pairs_to_decide
    )


def _groups[Key](assignment: dict[UUID, Key]) -> dict[Key, set[UUID]]:
    grouped: dict[Key, set[UUID]] = {}
    for record_id, key in assignment.items():
        grouped.setdefault(key, set()).add(record_id)
    return grouped


def _same_group_pairs(groups: Iterable[set[UUID]]) -> set[frozenset[UUID]]:
    return {frozenset(pair) for group in groups for pair in combinations(group, 2)}


def _metric(
    numerator: float,
    denominator: float,
    denominator_meaning: str,
    *,
    undefined_reason: str | None = None,
) -> DenominatedMetric:
    if undefined_reason is not None:
        value = None
    elif denominator:
        value = numerator / denominator
    else:
        value = None
        undefined_reason = "the metric denominator is zero"
    return DenominatedMetric(
        value=value,
        numerator=numerator,
        denominator=denominator,
        denominator_meaning=denominator_meaning,
        undefined_reason=undefined_reason,
    )


def evaluate_ambiguity_memberships(
    prediction: EntityResolutionPrediction,
    *,
    public: PublicAmbiguityTask,
    truth: MembershipTruth,
) -> AmbiguityMembershipMetrics:
    """Score the complete submitted partition using membership truth only."""

    validate_ambiguity_partition(prediction, public=public)
    public_ids = _record_ids(public)
    memberships = truth.record_memberships
    truth_ids = tuple(item.record_id for item in memberships)
    if len(truth_ids) != len(set(truth_ids)):
        raise AmbiguityPartitionEvaluationError(
            "membership truth contains a duplicate public record"
        )
    if set(truth_ids) != public_ids:
        raise AmbiguityPartitionEvaluationError(
            "membership truth must cover exactly the public record set"
        )

    truth_entity = {item.record_id: item.entity_id for item in memberships}
    predicted_cluster = {
        record_id: index
        for index, cluster in enumerate(prediction.clusters)
        for record_id in cluster
    }
    truth_groups = _groups(truth_entity)
    predicted_groups = _groups(predicted_cluster)
    truth_pairs = _same_group_pairs(truth_groups.values())
    predicted_pairs = _same_group_pairs(predicted_groups.values())
    true_positive_pairs = len(truth_pairs & predicted_pairs)

    record_order = sorted(public_ids, key=lambda item: item.int)
    b_precision_numerator = math.fsum(
        len(
            predicted_groups[predicted_cluster[record_id]]
            & truth_groups[truth_entity[record_id]]
        )
        / len(predicted_groups[predicted_cluster[record_id]])
        for record_id in record_order
    )
    b_recall_numerator = math.fsum(
        len(
            predicted_groups[predicted_cluster[record_id]]
            & truth_groups[truth_entity[record_id]]
        )
        / len(truth_groups[truth_entity[record_id]])
        for record_id in record_order
    )
    record_count = len(record_order)

    pairwise_precision = _metric(
        true_positive_pairs,
        len(predicted_pairs),
        "predicted same-cluster record pairs",
    )
    pairwise_recall = _metric(
        true_positive_pairs,
        len(truth_pairs),
        "true same-entity record pairs",
    )
    pairwise_f1 = _metric(
        2 * true_positive_pairs,
        len(predicted_pairs) + len(truth_pairs),
        "predicted same-cluster pairs plus true same-entity pairs",
        undefined_reason=(
            "pairwise precision is undefined because no positive pair was predicted"
            if pairwise_precision.value is None
            else (
                "pairwise recall is undefined because membership truth has no "
                "positive pair"
                if pairwise_recall.value is None
                else None
            )
        ),
    )
    b_precision = _metric(
        b_precision_numerator,
        record_count,
        "public identity records",
    )
    b_recall = _metric(
        b_recall_numerator,
        record_count,
        "public identity records",
    )
    b_f1 = _metric(
        2 * (b_precision.value or 0.0) * (b_recall.value or 0.0),
        (b_precision.value or 0.0) + (b_recall.value or 0.0),
        "B-cubed precision plus B-cubed recall",
    )

    return AmbiguityMembershipMetrics(
        seed=public.corpus.seed,
        public_schema_version=public.schema_version,
        submission_schema_version=prediction.schema_version,
        membership_truth_schema_version=truth.schema_version,
        record_count=record_count,
        predicted_cluster_count=len(predicted_groups),
        truth_entity_count=len(truth_groups),
        true_positive_pair_count=true_positive_pairs,
        predicted_positive_pair_count=len(predicted_pairs),
        truth_positive_pair_count=len(truth_pairs),
        false_merge_pair_count=len(predicted_pairs - truth_pairs),
        false_split_pair_count=len(truth_pairs - predicted_pairs),
        pairwise_precision=pairwise_precision,
        pairwise_recall=pairwise_recall,
        pairwise_f1=pairwise_f1,
        b_cubed_precision=b_precision,
        b_cubed_recall=b_recall,
        b_cubed_f1=b_f1,
    )


__all__ = [
    "AMBIGUITY_MEMBERSHIP_SCORING_VERSION",
    "AmbiguityMembershipMetrics",
    "AmbiguityPartitionEvaluationError",
    "DenominatedMetric",
    "derive_ambiguity_pair_predictions",
    "evaluate_ambiguity_memberships",
    "validate_ambiguity_partition",
]
