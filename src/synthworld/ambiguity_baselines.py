"""Reference pair-decision baselines for the ambiguity pack.

Three, because two would not show the trade the pack exists to expose. The exact
and fuzzy matchers always decide; the precision-first matcher may abstain. Their
numbers only mean something together: abstention buys precision, and a report that
shows precision without coverage rewards silence.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable, Mapping

from synthworld.ambiguity import PairDisposition, PairPrediction
from synthworld.ambiguity_generator import generate_ambiguity_benchmark
from synthworld.ambiguity_metrics import (
    AmbiguityMetrics,
    evaluate_ambiguity_predictions,
)
from synthworld.connection import PublicIdentityRecord

AMBIGUITY_BASELINE_SEED = 20_260_731

#: Identifiers a matcher treats as decisive. Naming them here rather than inline
#: keeps the three baselines comparable: they differ in policy, not vocabulary.
_STRONG = frozenset({"email", "phone", "username"})
_CORROBORATION_TO_MERGE = 3


def _by_kind(record: PublicIdentityRecord) -> Mapping[str, set[str]]:
    grouped: dict[str, set[str]] = {}
    for attribute in record.attributes:
        grouped.setdefault(attribute.kind.value, set()).add(attribute.value)
    return grouped


def _folded(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(item for item in decomposed if not unicodedata.combining(item))


def exact_strong_identifier(
    left: PublicIdentityRecord, right: PublicIdentityRecord
) -> PairDisposition:
    """Merge whenever any strong identifier matches exactly.

    The shortcut the old pack rewarded: precise when identifiers are clean, and
    wrong on every recycled phone, household mailbox and reused handle.
    """

    first, second = _by_kind(left), _by_kind(right)
    shared = any(first.get(kind, set()) & second.get(kind, set()) for kind in _STRONG)
    return PairDisposition.MERGE if shared else PairDisposition.SEPARATE


def normalised_name_or_address(
    left: PublicIdentityRecord, right: PublicIdentityRecord
) -> PairDisposition:
    """Merge on a normalised-name match or a shared address."""

    first, second = _by_kind(left), _by_kind(right)
    if _folded(left.display_name) == _folded(right.display_name):
        return PairDisposition.MERGE
    if first.get("full_address", set()) & second.get("full_address", set()):
        return PairDisposition.MERGE
    return PairDisposition.SEPARATE


def precision_first(
    left: PublicIdentityRecord, right: PublicIdentityRecord
) -> PairDisposition:
    """Decide only on corroboration, and abstain when the evidence is thin.

    A contradicting strong identifier or birth date separates outright; three
    corroborating attributes merge; anything less is declined rather than guessed.
    """

    first, second = _by_kind(left), _by_kind(right)
    shared = {kind for kind in first if first[kind] & second.get(kind, set())}
    contradicted = {
        kind for kind in first if kind in second and not first[kind] & second[kind]
    }
    if contradicted & (_STRONG | {"date_of_birth"}):
        return PairDisposition.SEPARATE
    if len(shared) >= _CORROBORATION_TO_MERGE:
        return PairDisposition.MERGE
    return PairDisposition.INSUFFICIENT


def run_ambiguity_baseline(
    decide: Callable[[PublicIdentityRecord, PublicIdentityRecord], PairDisposition],
) -> AmbiguityMetrics:
    """Score one decision function over the frozen pack."""

    benchmark = generate_ambiguity_benchmark(seed=AMBIGUITY_BASELINE_SEED)
    records = {item.id: item for item in benchmark.public.identity_records}
    predictions = [
        PairPrediction(
            left_record_id=pair.left_record_id,
            right_record_id=pair.right_record_id,
            disposition=decide(
                records[pair.left_record_id], records[pair.right_record_id]
            ),
        )
        for pair in benchmark.answer_key.pairs
    ]
    return evaluate_ambiguity_predictions(predictions, benchmark=benchmark)


AMBIGUITY_BASELINES: tuple[
    tuple[str, Callable[[PublicIdentityRecord, PublicIdentityRecord], PairDisposition]],
    ...,
] = (
    ("Exact strong-identifier matcher", exact_strong_identifier),
    ("Normalised-name or shared-address matcher", normalised_name_or_address),
    ("Precision-first matcher (may abstain)", precision_first),
)


__all__ = [
    "AMBIGUITY_BASELINES",
    "AMBIGUITY_BASELINE_SEED",
    "exact_strong_identifier",
    "normalised_name_or_address",
    "precision_first",
    "run_ambiguity_baseline",
]
