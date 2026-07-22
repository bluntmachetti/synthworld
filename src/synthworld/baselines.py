"""Deliberately naive reference baselines over SynthWorld's public corpora.

Each baseline consumes only product-safe public input and is scored against the
physically separate answer key. The baselines are intentionally simple — a
regex, exact-string and fuzzy matchers, a reciprocity rule, and a severity-only
risk adapter — so their scores illustrate what the benchmark *measures*, not
the state of the art. Every number is deterministic for the pinned seed.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from difflib import SequenceMatcher
from itertools import combinations
from uuid import UUID

from pydantic import Field

from synthworld.connection import (
    PublicConnectionCorpus,
    PublicIdentityAttributeKind,
    PublicIdentityRecord,
    RecordMembership,
)
from synthworld.connection_generator import (
    generate_adversarial_connection_benchmark,
    generate_relationship_connection_benchmark,
)
from synthworld.extraction import PublicExtractionCorpus
from synthworld.extraction_generator import generate_extraction_benchmark
from synthworld.models import SyntheticModel
from synthworld.risk import band_for_score, severity_points
from synthworld.risk_generator import generate_risk_benchmark

BASELINE_SEED = 20_260_719
BASELINE_PERSONA_COUNT = 10

_EMAIL_PATTERN = re.compile(r"[a-z0-9][a-z0-9._%+-]*@example\.test")
_PHONE_PATTERN = re.compile(r"\+1-[0-9]{3}-555-01[0-9]{2}")
_NATIONAL_ID_PATTERN = re.compile(r"SYN-[0-9]+")
_STRONG_ATTRIBUTE_KINDS = (
    PublicIdentityAttributeKind.EMAIL,
    PublicIdentityAttributeKind.USERNAME,
)
_FUZZY_NAME_THRESHOLD = 0.80


class BaselineResult(SyntheticModel):
    """One naive baseline's headline score and a short human-readable detail."""

    name: str
    task: str
    metric: str
    score: float = Field(ge=0.0, le=1.0)
    detail: str


def run_all_baselines() -> tuple[BaselineResult, ...]:
    """Run every reference baseline deterministically for the pinned seed."""

    return (
        run_regex_extraction_baseline(),
        run_exact_entity_resolution_baseline(),
        run_fuzzy_entity_resolution_baseline(),
        run_relationship_heuristic_baseline(),
        run_breach_risk_baseline(),
    )


def run_regex_extraction_baseline() -> BaselineResult:
    """Match structured PII with regex; miss everything else in the corpus."""

    benchmark = generate_extraction_benchmark(
        seed=BASELINE_SEED,
        persona_count=BASELINE_PERSONA_COUNT,
    )
    predicted = _regex_spans(benchmark.public)
    gold: set[tuple[str, str, int, int]] = {
        (answer.source_type.value, answer.source_record_id, span.start, span.end)
        for answer in benchmark.answers.answers
        for span in answer.answer_key.spans
    }
    precision, recall, f1 = _prf(predicted, gold)
    return BaselineResult(
        name="Regex extractor",
        task="Exact-span PII extraction",
        metric="span F1",
        score=round(f1, 4),
        detail=(
            f"P={precision:.2f} R={recall:.2f} over {len(gold)} gold spans; "
            "regex catches email, phone, and national-ID patterns and misses "
            "address, date-of-birth, username, employer, and education spans"
        ),
    )


def run_exact_entity_resolution_baseline() -> BaselineResult:
    """Link records that share an identical strong identifier only."""

    benchmark = generate_adversarial_connection_benchmark(seed=BASELINE_SEED)
    truth = _truth_pairs(benchmark.answer_key.record_memberships)
    predicted = _predicted_pairs(_exact_clusters(benchmark.public.identity_records))
    precision, recall, f1 = _prf(predicted, truth)
    return BaselineResult(
        name="Exact-string entity matcher",
        task="Entity resolution (adversarial pack)",
        metric="pairwise F1",
        score=round(f1, 4),
        detail=(
            f"P={precision:.2f} R={recall:.2f} over {len(truth)} same-entity "
            "pairs; exact strong-identifier matching is precise but links only "
            "records that already share an email or username"
        ),
    )


def run_fuzzy_entity_resolution_baseline() -> BaselineResult:
    """Link records by normalised-name similarity or a shared address."""

    benchmark = generate_adversarial_connection_benchmark(seed=BASELINE_SEED)
    truth = _truth_pairs(benchmark.answer_key.record_memberships)
    predicted = _predicted_pairs(_fuzzy_clusters(benchmark.public.identity_records))
    precision, recall, f1 = _prf(predicted, truth)
    return BaselineResult(
        name="Normalised/fuzzy entity matcher",
        task="Entity resolution (adversarial pack)",
        metric="pairwise F1",
        score=round(f1, 4),
        detail=(
            f"P={precision:.2f} R={recall:.2f} over {len(truth)} same-entity "
            "pairs; fuzzy name and shared-address matching recovers more links "
            "but over-merges common names and twins at one address"
        ),
    )


def run_relationship_heuristic_baseline() -> BaselineResult:
    """Infer an edge only when a reciprocal pair of associations exists."""

    benchmark = generate_relationship_connection_benchmark(
        seed=BASELINE_SEED,
        persona_count=BASELINE_PERSONA_COUNT,
    )
    reference_to_record = _reference_index(benchmark.public.identity_records)
    predicted = _reciprocal_edges(benchmark.public, reference_to_record)
    truth = {
        _ordered_pair(item.source_record_id, item.target_record_id)
        for item in benchmark.answer_key.relationships
    }
    precision, recall, f1 = _prf(predicted, truth)
    false_edges = len(predicted - truth)
    return BaselineResult(
        name="Reciprocity relationship heuristic",
        task="Relationship inference",
        metric="edge F1",
        score=round(f1, 4),
        detail=(
            f"P={precision:.2f} R={recall:.2f} over {len(truth)} planted edges; "
            f"{false_edges} false edges — requiring reciprocal evidence "
            "correctly rejects the unilateral association controls"
        ),
    )


def run_breach_risk_baseline() -> BaselineResult:
    """Score each case from breach severity alone, ignoring data-class weight."""

    benchmark = generate_risk_benchmark(
        seed=BASELINE_SEED,
        persona_count=BASELINE_PERSONA_COUNT,
    )
    truth = {case.case_id: case for case in benchmark.answer_key.cases}
    correct = 0
    absolute_error = 0
    for case in benchmark.public.cases:
        naive_score = min(
            100, sum(severity_points(item.severity) for item in case.breaches)
        )
        truth_case = truth[case.id]
        absolute_error += abs(naive_score - truth_case.score)
        if band_for_score(naive_score) is truth_case.band:
            correct += 1
    case_count = len(benchmark.public.cases)
    band_accuracy = correct / case_count
    mean_absolute_error = absolute_error / case_count
    return BaselineResult(
        name="Severity-only risk adapter",
        task="Breach-risk calibration",
        metric="band accuracy",
        score=round(band_accuracy, 4),
        detail=(
            f"{correct}/{case_count} bands correct, mean absolute score error "
            f"{mean_absolute_error:.1f}; ignoring data-class weight "
            "under-calibrates against the documented formula"
        ),
    )


def _regex_spans(corpus: PublicExtractionCorpus) -> set[tuple[str, str, int, int]]:
    spans: set[tuple[str, str, int, int]] = set()
    for page in corpus.pages:
        key = (page.source_type.value, page.source_record_id)
        for pattern in (_EMAIL_PATTERN, _PHONE_PATTERN, _NATIONAL_ID_PATTERN):
            for match in pattern.finditer(page.content):
                spans.add((*key, match.start(), match.end()))
    return spans


def _truth_pairs(
    memberships: tuple[RecordMembership, ...],
) -> set[frozenset[UUID]]:
    by_entity: dict[str, list[UUID]] = {}
    for membership in memberships:
        by_entity.setdefault(membership.entity_id, []).append(membership.record_id)
    return {
        frozenset(pair)
        for records in by_entity.values()
        for pair in combinations(records, 2)
    }


def _predicted_pairs(
    clusters: list[list[UUID]],
) -> set[frozenset[UUID]]:
    return {
        frozenset(pair) for cluster in clusters for pair in combinations(cluster, 2)
    }


def _exact_clusters(
    records: tuple[PublicIdentityRecord, ...],
) -> list[list[UUID]]:
    union = _Union(record.id for record in records)
    keyed: dict[tuple[str, str], UUID] = {}
    for record in records:
        for attribute in record.attributes:
            if attribute.kind in _STRONG_ATTRIBUTE_KINDS:
                key = (attribute.kind.value, attribute.value)
                if key in keyed:
                    union.join(keyed[key], record.id)
                else:
                    keyed[key] = record.id
    return union.clusters()


def _fuzzy_clusters(
    records: tuple[PublicIdentityRecord, ...],
) -> list[list[UUID]]:
    union = _Union(record.id for record in records)
    address_owner: dict[str, UUID] = {}
    for record in records:
        address = _attribute_value(record, PublicIdentityAttributeKind.FULL_ADDRESS)
        if address is not None:
            if address in address_owner:
                union.join(address_owner[address], record.id)
            else:
                address_owner[address] = record.id
    for left, right in combinations(records, 2):
        if _name_similarity(left.display_name, right.display_name) >= (
            _FUZZY_NAME_THRESHOLD
        ):
            union.join(left.id, right.id)
    return union.clusters()


def _reference_index(
    records: tuple[PublicIdentityRecord, ...],
) -> dict[str, UUID]:
    index: dict[str, UUID] = {}
    for record in records:
        for kind in (
            PublicIdentityAttributeKind.FULL_ADDRESS,
            PublicIdentityAttributeKind.SOCIAL_PROFILE,
        ):
            value = _attribute_value(record, kind)
            if value is not None:
                index[value] = record.id
    return index


def _reciprocal_edges(
    corpus: PublicConnectionCorpus,
    reference_to_record: dict[str, UUID],
) -> set[frozenset[UUID]]:
    directed = {
        (item.source_reference, item.target_reference)
        for item in corpus.association_records
    }
    edges: set[frozenset[UUID]] = set()
    for source_reference, target_reference in directed:
        if (target_reference, source_reference) not in directed:
            continue
        source_record = reference_to_record.get(source_reference)
        target_record = reference_to_record.get(target_reference)
        if source_record is not None and target_record is not None:
            edges.add(frozenset((source_record, target_record)))
    return edges


def _attribute_value(
    record: PublicIdentityRecord,
    kind: PublicIdentityAttributeKind,
) -> str | None:
    for attribute in record.attributes:
        if attribute.kind is kind:
            return attribute.value
    return None


def _name_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, _normalize_name(left), _normalize_name(right)).ratio()


def _normalize_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    stripped = "".join(
        character
        for character in decomposed
        if (not unicodedata.combining(character) and character.isalnum())
        or character == " "
    )
    return " ".join(stripped.split())


def _ordered_pair(first: UUID, second: UUID) -> frozenset[UUID]:
    return frozenset((first, second))


def _prf[Pair](
    predicted: set[Pair],
    truth: set[Pair],
) -> tuple[float, float, float]:
    true_positive = len(predicted & truth)
    precision = true_positive / len(predicted) if predicted else 0.0
    recall = true_positive / len(truth) if truth else 0.0
    denominator = precision + recall
    f1 = 2 * precision * recall / denominator if denominator else 0.0
    return precision, recall, f1


class _Union:
    """Minimal union-find over record UUIDs for clustering baselines."""

    def __init__(self, items: Iterable[UUID]) -> None:
        self._parent: dict[UUID, UUID] = {item: item for item in items}

    def find(self, item: UUID) -> UUID:
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[item] != root:
            self._parent[item], item = root, self._parent[item]
        return root

    def join(self, left: UUID, right: UUID) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root != right_root:
            self._parent[right_root] = left_root

    def clusters(self) -> list[list[UUID]]:
        groups: dict[UUID, list[UUID]] = {}
        for item in self._parent:
            groups.setdefault(self.find(item), []).append(item)
        return [members for members in groups.values() if len(members) > 1]


__all__ = [
    "BASELINE_PERSONA_COUNT",
    "BASELINE_SEED",
    "BaselineResult",
    "run_all_baselines",
    "run_breach_risk_baseline",
    "run_exact_entity_resolution_baseline",
    "run_fuzzy_entity_resolution_baseline",
    "run_regex_extraction_baseline",
    "run_relationship_heuristic_baseline",
]
