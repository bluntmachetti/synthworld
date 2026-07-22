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
from collections.abc import Iterable
from itertools import combinations
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from synthworld.connection import (
    AdversarialCase,
    PublicAssociationRecord,
    PublicIdentityAttributeKind,
    PublicIdentityRecord,
    PublicTruthRelationshipKind,
    UnilateralAssociationControl,
)
from synthworld.connection_generator import (
    generate_adversarial_connection_benchmark,
    generate_relationship_connection_benchmark,
)
from synthworld.connection_serialization import (
    connection_benchmark_to_json,
    public_connection_corpus_to_json,
)
from synthworld.exposures import DataClass
from synthworld.extraction import ExtractionSourceType
from synthworld.extraction_generator import generate_extraction_benchmark
from synthworld.extraction_serialization import (
    extraction_answers_to_json,
    public_extraction_corpus_to_json,
)
from synthworld.models import SyntheticModel
from synthworld.risk import RiskBand, RiskCaseTruth
from synthworld.risk_generator import generate_risk_benchmark
from synthworld.risk_serialization import (
    public_risk_corpus_to_json,
    risk_answer_key_to_json,
)

EVALUATION_SCHEMA_VERSION = "0.1.0"
SCORING_PROTOCOL_VERSION = "0.1.0"
CHECKSUM_SCHEME = "synthworld-json-v1"

_RELAXED_IOU_THRESHOLD = 0.5


class EvaluationInputError(ValueError):
    """Raised when a submission is malformed for a benchmark, not merely wrong.

    This separates an invalid submission (unknown or missing IDs, a partition
    that is not complete) from a valid submission that simply scores poorly.
    """


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
    """A counted slice of where a system failed, for error analysis.

    `dimension`/`value` name the slice (e.g. data_class=address, or
    adversarial_pack=twins_shared_address); `outcome` names the error type
    (missed, spurious, false_merge, false_split); `count` is the errors and
    `support` the denominator they are drawn from.
    """

    dimension: str
    value: str
    outcome: str
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


class EntityResolutionPrediction(SyntheticModel):
    """A complete predicted partition of the public identity records.

    Every record must appear in exactly one non-empty cluster; singletons are
    explicit. The scorer additionally requires the members to cover the public
    record set exactly. Cluster and member order do not affect scoring.
    """

    schema_version: Literal["0.1.0"] = "0.1.0"
    clusters: tuple[tuple[UUID, ...], ...]

    @model_validator(mode="after")
    def validate_partition(self) -> EntityResolutionPrediction:
        seen: set[UUID] = set()
        for cluster in self.clusters:
            if not cluster:
                raise ValueError("clusters must be non-empty")
            for record_id in cluster:
                if record_id in seen:
                    raise ValueError("a record may appear in only one cluster")
                seen.add(record_id)
        return self


class PredictedRelationship(SyntheticModel):
    """One predicted undirected typed edge between two public records."""

    source_record_id: UUID
    target_record_id: UUID
    kind: PublicTruthRelationshipKind
    evidence_association_ids: tuple[UUID, ...] = ()

    @model_validator(mode="after")
    def require_distinct_endpoints(self) -> PredictedRelationship:
        if self.source_record_id == self.target_record_id:
            raise ValueError("a relationship needs two distinct records")
        return self


class RelationshipPrediction(SyntheticModel):
    """Oracle-free predicted relationships submitted for scoring."""

    schema_version: Literal["0.1.0"] = "0.1.0"
    edges: tuple[PredictedRelationship, ...]

    @model_validator(mode="after")
    def reject_duplicate_edges(self) -> RelationshipPrediction:
        keys = [
            (_canonical_pair(edge.source_record_id, edge.target_record_id), edge.kind)
            for edge in self.edges
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate predicted relationships")
        return self


class RiskCasePrediction(SyntheticModel):
    """One case's predicted breach-risk band, with optional score and vector.

    `band` is always required. `score` and `band_probabilities` are optional,
    but the prediction set requires each to be provided for every case or for
    none, so a system cannot report the easy cases only.
    """

    case_id: UUID
    band: RiskBand
    score: int | None = None
    band_probabilities: tuple[tuple[RiskBand, float], ...] | None = None

    @model_validator(mode="after")
    def validate_optional_capabilities(self) -> RiskCasePrediction:
        if self.score is not None and not 0 <= self.score <= 100:
            raise ValueError("risk score must be between 0 and 100")
        probabilities = self.band_probabilities
        if probabilities is not None:
            bands = [band for band, _ in probabilities]
            if sorted(bands, key=_BAND_INDEX.__getitem__) != list(_BAND_ORDER):
                raise ValueError("band probabilities must cover every band once")
            values = [value for _, value in probabilities]
            if any(not math.isfinite(value) or not 0 <= value <= 1 for value in values):
                raise ValueError("band probabilities must be in [0, 1]")
            if abs(sum(values) - 1.0) > 1e-6:
                raise ValueError("band probabilities must sum to one")
        return self


class RiskPrediction(SyntheticModel):
    """Oracle-free predicted breach-risk assessments submitted for scoring."""

    schema_version: Literal["0.1.0"] = "0.1.0"
    cases: tuple[RiskCasePrediction, ...]

    @model_validator(mode="after")
    def validate_case_set(self) -> RiskPrediction:
        if len({case.case_id for case in self.cases}) != len(self.cases):
            raise ValueError("duplicate risk case predictions")
        scored = [case.score is not None for case in self.cases]
        if any(scored) and not all(scored):
            raise ValueError("score must be given for every case or for none")
        vectored = [case.band_probabilities is not None for case in self.cases]
        if any(vectored) and not all(vectored):
            raise ValueError("probabilities must be given for every case or for none")
        return self


_PageKey = tuple[str, str]
_Span = tuple[_PageKey, DataClass, int, int]
_Group = tuple[_PageKey, DataClass]
_Endpoints = tuple[UUID, UUID]
_Edge = tuple[_Endpoints, PublicTruthRelationshipKind]
_BAND_ORDER = (
    RiskBand.NONE,
    RiskBand.LOW,
    RiskBand.MODERATE,
    RiskBand.HIGH,
    RiskBand.CRITICAL,
)
_BAND_INDEX = {band: index for index, band in enumerate(_BAND_ORDER)}


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
            dimension="data_class",
            value=data_class.value,
            outcome="missed",
            count=missed_by_class[data_class],
            support=gold_by_class[data_class],
        )
        for data_class in sorted(missed_by_class, key=lambda item: item.value)
    )
    spurious_slice = FailureSlice(
        dimension="overall",
        value="all",
        outcome="spurious",
        count=len(spurious),
        support=len(predicted),
    )
    return (*class_slices, spurious_slice)


def evaluate_entity_resolution(
    prediction: EntityResolutionPrediction,
    *,
    seed: int,
) -> EvaluationReport:
    """Score a predicted record partition against entity-membership truth."""

    benchmark = generate_adversarial_connection_benchmark(seed=seed)
    public_ids = {record.id for record in benchmark.public.identity_records}
    predicted_ids = {rid for cluster in prediction.clusters for rid in cluster}
    if predicted_ids != public_ids:
        raise EvaluationInputError(
            "entity-resolution prediction must partition exactly the public records"
        )

    truth_entity = {
        item.record_id: item.entity_id
        for item in benchmark.answer_key.record_memberships
    }
    pred_cluster = {
        rid: index
        for index, cluster in enumerate(prediction.clusters)
        for rid in cluster
    }
    truth_members = _members_by_key(truth_entity)
    pred_members = _members_by_key(pred_cluster)
    truth_pairs = _same_group_pairs(truth_members.values())
    pred_pairs = _same_group_pairs(pred_members.values())
    true_positive = len(pred_pairs & truth_pairs)

    pairwise_precision = _ratio_or_none(true_positive, len(pred_pairs))
    pairwise_recall = _ratio_or_none(true_positive, len(truth_pairs))
    bcubed_precision, bcubed_recall, bcubed_f1 = _bcubed(
        public_ids, pred_members, truth_members, pred_cluster, truth_entity
    )

    metrics = (
        TaskMetric(
            name="pairwise_precision", value=pairwise_precision, support=len(pred_pairs)
        ),
        TaskMetric(
            name="pairwise_recall", value=pairwise_recall, support=len(truth_pairs)
        ),
        TaskMetric(
            name="pairwise_f1",
            value=_f1_or_none(pairwise_precision, pairwise_recall),
            support=len(truth_pairs),
        ),
        TaskMetric(
            name="bcubed_precision", value=bcubed_precision, support=len(public_ids)
        ),
        TaskMetric(name="bcubed_recall", value=bcubed_recall, support=len(public_ids)),
        TaskMetric(name="bcubed_f1", value=bcubed_f1, support=len(public_ids)),
    )
    return EvaluationReport(
        scoring_version=SCORING_PROTOCOL_VERSION,
        task="entity_resolution",
        seed=seed,
        persona_count=len(truth_members),
        benchmark_version=benchmark.schema_version,
        checksum_scheme=CHECKSUM_SCHEME,
        artifact_checksums=(
            ("public", _sha256(public_connection_corpus_to_json(benchmark.public))),
            ("benchmark", _sha256(connection_benchmark_to_json(benchmark))),
        ),
        metrics=metrics,
        slices=_entity_resolution_slices(
            benchmark.answer_key.adversarial_cases, pred_pairs, truth_pairs
        ),
    )


def _members_by_key[Key](assignment: dict[UUID, Key]) -> dict[Key, set[UUID]]:
    members: dict[Key, set[UUID]] = {}
    for record_id, key in assignment.items():
        members.setdefault(key, set()).add(record_id)
    return members


def _same_group_pairs(groups: Iterable[set[UUID]]) -> set[frozenset[UUID]]:
    return {frozenset(pair) for group in groups for pair in combinations(group, 2)}


def _bcubed(
    records: set[UUID],
    pred_members: dict[int, set[UUID]],
    truth_members: dict[str, set[UUID]],
    pred_cluster: dict[UUID, int],
    truth_entity: dict[UUID, str],
) -> tuple[float, float, float]:
    precision_sum = 0.0
    recall_sum = 0.0
    for record_id in records:
        predicted = pred_members[pred_cluster[record_id]]
        truth = truth_members[truth_entity[record_id]]
        shared = len(predicted & truth)
        precision_sum += shared / len(predicted)
        recall_sum += shared / len(truth)
    count = len(records)
    precision = precision_sum / count
    recall = recall_sum / count
    return precision, recall, _harmonic_mean(precision, recall)


def _entity_resolution_slices(
    cases: tuple[AdversarialCase, ...],
    pred_pairs: set[frozenset[UUID]],
    truth_pairs: set[frozenset[UUID]],
) -> tuple[FailureSlice, ...]:
    slices: list[FailureSlice] = []
    for case in cases:
        pack_pairs = {frozenset(pair) for pair in combinations(case.record_ids, 2)}
        pack_truth = pack_pairs & truth_pairs
        pack_different = pack_pairs - truth_pairs
        slices.append(
            FailureSlice(
                dimension="adversarial_pack",
                value=case.pack.value,
                outcome="false_merge",
                count=len(pred_pairs & pack_different),
                support=len(pack_different),
            )
        )
        slices.append(
            FailureSlice(
                dimension="adversarial_pack",
                value=case.pack.value,
                outcome="false_split",
                count=len(pack_truth - pred_pairs),
                support=len(pack_truth),
            )
        )
    return tuple(slices)


def evaluate_relationship_inference(
    prediction: RelationshipPrediction,
    *,
    seed: int,
    persona_count: int = 10,
) -> EvaluationReport:
    """Score predicted undirected typed relationship edges against truth.

    Scoring is record-level, which is unambiguous because the relationship
    benchmark carries exactly one identity record per persona.
    """

    benchmark = generate_relationship_connection_benchmark(
        seed=seed, persona_count=persona_count
    )
    record_ids = {record.id for record in benchmark.public.identity_records}
    association_ids = {item.id for item in benchmark.public.association_records}
    for edge in prediction.edges:
        if edge.source_record_id not in record_ids or (
            edge.target_record_id not in record_ids
        ):
            raise EvaluationInputError("relationship endpoints must be public records")

    predicted_edges = {
        (_canonical_pair(edge.source_record_id, edge.target_record_id), edge.kind)
        for edge in prediction.edges
    }
    truth_edges: set[_Edge] = {
        ((item.source_record_id, item.target_record_id), item.kind)
        for item in benchmark.answer_key.relationships
    }
    true_positive = len(predicted_edges & truth_edges)
    edge_precision = _ratio_or_none(true_positive, len(predicted_edges))
    edge_recall = _ratio_or_none(true_positive, len(truth_edges))

    cited = [
        cited_id
        for edge in prediction.edges
        for cited_id in edge.evidence_association_ids
    ]
    valid_cited = sum(cited_id in association_ids for cited_id in cited)
    citations_by_edge: dict[_Edge, set[UUID]] = {}
    for edge in prediction.edges:
        key = (_canonical_pair(edge.source_record_id, edge.target_record_id), edge.kind)
        citations_by_edge.setdefault(key, set()).update(edge.evidence_association_ids)
    evidence_backed = sum(
        (
            (item.source_record_id, item.target_record_id),
            item.kind,
        )
        in predicted_edges
        and bool(
            citations_by_edge.get(
                ((item.source_record_id, item.target_record_id), item.kind), set()
            )
            & set(item.reciprocal_association_ids)
        )
        for item in benchmark.answer_key.relationships
    )

    metrics = (
        TaskMetric(
            name="edge_precision", value=edge_precision, support=len(predicted_edges)
        ),
        TaskMetric(name="edge_recall", value=edge_recall, support=len(truth_edges)),
        TaskMetric(
            name="edge_f1",
            value=_f1_or_none(edge_precision, edge_recall),
            support=len(truth_edges),
        ),
        TaskMetric(
            name="citation_validity",
            value=_ratio_or_none(valid_cited, len(cited)),
            support=len(cited),
        ),
        TaskMetric(
            name="evidence_backed_recall",
            value=_rate(evidence_backed, len(truth_edges)),
            support=len(truth_edges),
        ),
    )
    return EvaluationReport(
        scoring_version=SCORING_PROTOCOL_VERSION,
        task="relationship_inference",
        seed=seed,
        persona_count=persona_count,
        benchmark_version=benchmark.schema_version,
        checksum_scheme=CHECKSUM_SCHEME,
        artifact_checksums=(
            ("public", _sha256(public_connection_corpus_to_json(benchmark.public))),
            ("benchmark", _sha256(connection_benchmark_to_json(benchmark))),
        ),
        metrics=metrics,
        slices=_relationship_slices(
            prediction,
            benchmark.public.identity_records,
            benchmark.public.association_records,
            benchmark.answer_key.unilateral_controls,
            predicted_edges,
            truth_edges,
        ),
    )


def _relationship_slices(
    prediction: RelationshipPrediction,
    records: tuple[PublicIdentityRecord, ...],
    associations: tuple[PublicAssociationRecord, ...],
    controls: tuple[UnilateralAssociationControl, ...],
    predicted_edges: set[_Edge],
    truth_edges: set[_Edge],
) -> tuple[FailureSlice, ...]:
    reference_to_record = _reference_to_record(records)
    association_by_id = {item.id: item for item in associations}
    control_pairs = _control_endpoint_pairs(
        controls, association_by_id, reference_to_record
    )
    predicted_pairs = {
        _canonical_pair(edge.source_record_id, edge.target_record_id)
        for edge in prediction.edges
    }
    return (
        FailureSlice(
            dimension="overall",
            value="all",
            outcome="false_edge",
            count=len(predicted_edges - truth_edges),
            support=len(predicted_edges),
        ),
        FailureSlice(
            dimension="unilateral_control",
            value="all",
            outcome="false_edge",
            count=len(control_pairs & predicted_pairs),
            support=len(control_pairs),
        ),
    )


def _reference_to_record(
    records: tuple[PublicIdentityRecord, ...],
) -> dict[str, UUID]:
    index: dict[str, UUID] = {}
    for record in records:
        for attribute in record.attributes:
            if attribute.kind in (
                PublicIdentityAttributeKind.FULL_ADDRESS,
                PublicIdentityAttributeKind.SOCIAL_PROFILE,
            ):
                index[attribute.value] = record.id
    return index


def _control_endpoint_pairs(
    controls: tuple[UnilateralAssociationControl, ...],
    association_by_id: dict[UUID, PublicAssociationRecord],
    reference_to_record: dict[str, UUID],
) -> set[_Endpoints]:
    pairs: set[_Endpoints] = set()
    for control in controls:
        association = association_by_id[control.association_id]
        source = reference_to_record.get(association.source_reference)
        target = reference_to_record.get(association.target_reference)
        if source is not None and target is not None:
            pairs.add(_canonical_pair(source, target))
    return pairs


def _canonical_pair(first: UUID, second: UUID) -> _Endpoints:
    return (first, second) if first.int <= second.int else (second, first)


def _ratio_or_none(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _f1_or_none(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None:
        return None
    return _harmonic_mean(precision, recall)


def evaluate_risk_calibration(
    prediction: RiskPrediction,
    *,
    seed: int,
    persona_count: int = 10,
) -> EvaluationReport:
    """Score predicted breach-risk bands against the calibration answer key.

    ECE is deliberately omitted as a headline metric: at the frozen ten-case
    scale it is too sample-starved to be credible. Brier and the ordinal band
    distance are reported when a system submits probabilities.
    """

    benchmark = generate_risk_benchmark(seed=seed, persona_count=persona_count)
    truth = {case.case_id: case for case in benchmark.answer_key.cases}
    predicted = {case.case_id: case for case in prediction.cases}
    if set(predicted) != set(truth):
        raise EvaluationInputError(
            "risk prediction must cover exactly the public cases"
        )

    count = len(truth)
    correct = sum(predicted[cid].band is truth[cid].band for cid in truth)
    band_distance = (
        sum(
            abs(_BAND_INDEX[predicted[cid].band] - _BAND_INDEX[truth[cid].band])
            for cid in truth
        )
        / count
    )

    metrics = (
        TaskMetric(name="band_accuracy", value=correct / count, support=count),
        TaskMetric(name="macro_f1", value=_macro_f1(predicted, truth), support=count),
        TaskMetric(name="mean_band_distance", value=band_distance, support=count),
        TaskMetric(
            name="mean_absolute_error", value=_mae(predicted, truth), support=count
        ),
        TaskMetric(name="brier", value=_brier(predicted, truth), support=count),
    )
    return EvaluationReport(
        scoring_version=SCORING_PROTOCOL_VERSION,
        task="risk_calibration",
        seed=seed,
        persona_count=persona_count,
        benchmark_version=benchmark.schema_version,
        checksum_scheme=CHECKSUM_SCHEME,
        artifact_checksums=(
            ("public", _sha256(public_risk_corpus_to_json(benchmark.public))),
            ("answers", _sha256(risk_answer_key_to_json(benchmark.answer_key))),
        ),
        metrics=metrics,
        slices=_risk_slices(predicted, truth),
    )


def _macro_f1(
    predicted: dict[UUID, RiskCasePrediction],
    truth: dict[UUID, RiskCaseTruth],
) -> float:
    truth_bands = {case.band for case in truth.values()}
    scores: list[float] = []
    for band in truth_bands:
        true_positive = sum(
            predicted[cid].band is band and truth[cid].band is band for cid in truth
        )
        predicted_positive = sum(predicted[cid].band is band for cid in truth)
        actual_positive = sum(truth[cid].band is band for cid in truth)
        precision = _rate(true_positive, predicted_positive)
        recall = _rate(true_positive, actual_positive)
        scores.append(_harmonic_mean(precision, recall))
    return sum(scores) / len(scores)


def _mae(
    predicted: dict[UUID, RiskCasePrediction],
    truth: dict[UUID, RiskCaseTruth],
) -> float | None:
    total = 0
    for cid, truth_case in truth.items():
        score = predicted[cid].score
        if score is None:
            return None
        total += abs(score - truth_case.score)
    return total / len(truth)


def _brier(
    predicted: dict[UUID, RiskCasePrediction],
    truth: dict[UUID, RiskCaseTruth],
) -> float | None:
    total = 0.0
    for cid, truth_case in truth.items():
        probabilities = predicted[cid].band_probabilities
        if probabilities is None:
            return None
        probability_by_band = dict(probabilities)
        total += sum(
            (probability_by_band[band] - (1.0 if band is truth_case.band else 0.0)) ** 2
            for band in _BAND_ORDER
        )
    return total / len(truth)


def _risk_slices(
    predicted: dict[UUID, RiskCasePrediction],
    truth: dict[UUID, RiskCaseTruth],
) -> tuple[FailureSlice, ...]:
    counts: dict[RiskBand, tuple[int, int]] = {}
    for cid, truth_case in truth.items():
        total, wrong = counts.get(truth_case.band, (0, 0))
        counts[truth_case.band] = (
            total + 1,
            wrong + (predicted[cid].band is not truth_case.band),
        )
    return tuple(
        FailureSlice(
            dimension="true_band",
            value=band.value,
            outcome="misband",
            count=wrong,
            support=total,
        )
        for band, (total, wrong) in sorted(
            counts.items(), key=lambda item: _BAND_INDEX[item[0]]
        )
    )


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
    "EntityResolutionPrediction",
    "EvaluationInputError",
    "EvaluationReport",
    "ExtractionPagePrediction",
    "ExtractionPredictionSet",
    "FailureSlice",
    "PredictedRelationship",
    "PredictedSpan",
    "RelationshipPrediction",
    "RiskCasePrediction",
    "RiskPrediction",
    "TaskMetric",
    "evaluate_entity_resolution",
    "evaluate_extraction",
    "evaluate_relationship_inference",
    "evaluate_risk_calibration",
]
