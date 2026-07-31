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
from uuid import UUID

from synthworld.ambiguity import (
    AmbiguityBenchmark,
    PairDisposition,
    PairPrediction,
    PairTruth,
    ScenarioKind,
)
from synthworld.models import SyntheticModel

#: Below this many pairs a slice is reported but must not be concluded from. The
#: canonical pack carries one pair per scenario and therefore warns on all of them:
#: it is a conformance fixture, in the sense Asteria Agentic v1 is, not a
#: statistical benchmark. Seed variants are what raise support.
MINIMUM_SCENARIO_SUPPORT = 3


class ScenarioOutcome(SyntheticModel):
    scenario: ScenarioKind
    expected: PairDisposition
    support: int
    correct: int
    predicted: Mapping[str, int]
    #: True when `support` is below the declared minimum. Machine-readable, so a
    #: consumer rendering a table cannot quietly present a 1-of-1 slice as a rate.
    low_support: bool


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


class AmbiguityEvaluationError(ValueError):
    """Raised when a submission does not cover the benchmark's pairs exactly."""


def _key(left: UUID, right: UUID) -> tuple[UUID, UUID]:
    return (left, right) if left < right else (right, left)


def evaluate_ambiguity_predictions(
    predictions: Iterable[PairPrediction],
    *,
    benchmark: AmbiguityBenchmark,
) -> AmbiguityMetrics:
    """Score pair decisions against the pack's evidence dispositions."""

    truth: dict[tuple[UUID, UUID], PairTruth] = {
        _key(item.left_record_id, item.right_record_id): item
        for item in benchmark.answer_key.pairs
    }
    submitted: dict[tuple[UUID, UUID], PairDisposition] = {}
    for prediction in predictions:
        key = _key(prediction.left_record_id, prediction.right_record_id)
        if key in submitted:
            raise AmbiguityEvaluationError("a record pair was submitted twice")
        submitted[key] = prediction.disposition
    if set(submitted) != set(truth):
        raise AmbiguityEvaluationError(
            "predictions must cover exactly the benchmark's record pairs"
        )

    false_merges = false_splits = unwarranted = decided = correct_decided = 0
    decidable = 0
    by_scenario: dict[ScenarioKind, Counter[str]] = {}
    correct_by_scenario: Counter[ScenarioKind] = Counter()

    for key, expected in truth.items():
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
                item.disposition
                for item in benchmark.answer_key.pairs
                if item.scenario is scenario
            ),
            support=sum(by_scenario[scenario].values()),
            correct=correct_by_scenario[scenario],
            predicted=dict(sorted(by_scenario[scenario].items())),
            low_support=sum(by_scenario[scenario].values()) < MINIMUM_SCENARIO_SUPPORT,
        )
        for scenario in sorted(by_scenario, key=lambda item: item.value)
    )
    total = len(truth)
    return AmbiguityMetrics(
        pair_count=total,
        decided_count=decided,
        abstained_count=total - decided,
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


__all__ = [
    "MINIMUM_SCENARIO_SUPPORT",
    "AmbiguityEvaluationError",
    "AmbiguityMetrics",
    "ScenarioOutcome",
    "evaluate_ambiguity_predictions",
]
