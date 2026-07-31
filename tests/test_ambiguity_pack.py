"""What the ambiguity pack has to be true of, measured rather than asserted."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from uuid import UUID

import pytest
from pydantic import ValidationError

from synthworld.ambiguity import (
    AmbiguityAnswerKey,
    AmbiguityBenchmark,
    PairDisposition,
    PairPrediction,
    PairTruth,
    ScenarioKind,
)
from synthworld.ambiguity_baselines import (
    AMBIGUITY_BASELINE_SEED,
    AMBIGUITY_BASELINES,
    exact_strong_identifier,
    precision_first,
    run_ambiguity_baseline,
)
from synthworld.ambiguity_generator import generate_ambiguity_benchmark
from synthworld.ambiguity_metrics import (
    MINIMUM_SCENARIO_SUPPORT,
    AmbiguityEvaluationError,
    evaluate_ambiguity_predictions,
)
from synthworld.connection import PublicIdentityRecord, RecordMembership

_SEED = AMBIGUITY_BASELINE_SEED
_Decide = Callable[[PublicIdentityRecord, PublicIdentityRecord], PairDisposition]


def _benchmark() -> AmbiguityBenchmark:
    return generate_ambiguity_benchmark(seed=_SEED)


def test_every_required_scenario_appears_exactly_once() -> None:
    """The case matrix issue #41 lists, with nothing quietly dropped."""

    counts = Counter(item.scenario for item in _benchmark().answer_key.pairs)

    assert set(counts) == set(ScenarioKind)
    assert set(counts.values()) == {1}


def test_positives_and_negatives_share_the_attribute_that_decides_them() -> None:
    """The property that makes the pack adversarial rather than merely large.

    A resolver keyed on any single attribute must get one of each pair wrong, so
    every attribute that carries a merge somewhere must also carry a separate
    somewhere.
    """

    benchmark = _benchmark()
    records = {item.id: item for item in benchmark.public.identity_records}
    carriers: dict[str, set[PairDisposition]] = {}
    for pair in benchmark.answer_key.pairs:
        left, right = records[pair.left_record_id], records[pair.right_record_id]
        shared = {item.kind.value for item in left.attributes} & {
            item.kind.value for item in right.attributes
        }
        for kind in shared:
            values_left = {i.value for i in left.attributes if i.kind.value == kind}
            values_right = {i.value for i in right.attributes if i.kind.value == kind}
            if values_left & values_right:
                carriers.setdefault(kind, set()).add(pair.disposition)

    decisive = {
        kind
        for kind, dispositions in carriers.items()
        if PairDisposition.MERGE in dispositions
    }
    assert decisive
    for kind in decisive:
        assert PairDisposition.SEPARATE in carriers[kind] or (
            PairDisposition.INSUFFICIENT in carriers[kind]
        ), f"{kind} only ever carries merges, so matching on it is free"


def test_canonical_truth_and_evidence_disposition_are_independent() -> None:
    """The distinction the pack exists to make scoreable.

    Two records can be one person while the public evidence supports only
    `insufficient`, and can be different people under the same disposition. If the
    two truths always agreed, abstention could not be scored at all.
    """

    pairs = _benchmark().answer_key.pairs
    undecidable = [
        item for item in pairs if item.disposition is PairDisposition.INSUFFICIENT
    ]

    assert any(item.same_entity for item in undecidable)
    assert any(not item.same_entity for item in undecidable)


def test_public_records_carry_no_oracle() -> None:
    """No entity id, scenario label, or expected decision anywhere in the input."""

    benchmark = _benchmark()
    serialized = benchmark.public.model_dump_json().lower()

    for scenario in ScenarioKind:
        assert scenario.value not in serialized
    for disposition in PairDisposition:
        assert f'"{disposition.value}"' not in serialized
    for membership in benchmark.answer_key.record_memberships:
        assert membership.entity_id.lower() not in serialized


def test_generation_is_deterministic() -> None:
    assert (
        _benchmark().model_dump_json()
        == generate_ambiguity_benchmark(seed=_SEED).model_dump_json()
    )
    assert (
        _benchmark().model_dump_json()
        != generate_ambiguity_benchmark(seed=_SEED + 1).model_dump_json()
    )


@pytest.mark.parametrize(
    ("scenario", "disposition", "same_entity", "message"),
    [
        (
            ScenarioKind.RECYCLED_PHONE,
            PairDisposition.MERGE,
            True,
            "must carry disposition",
        ),
        (
            ScenarioKind.STALE_ATTRIBUTE,
            PairDisposition.MERGE,
            False,
            "must be the same entity",
        ),
        (
            ScenarioKind.RECYCLED_PHONE,
            PairDisposition.SEPARATE,
            True,
            "must be different entities",
        ),
    ],
)
def test_pair_truth_rejects_incoherent_labels(
    scenario: ScenarioKind,
    disposition: PairDisposition,
    same_entity: bool,
    message: str,
) -> None:
    """A fixture cannot redefine a scenario by mislabelling it."""

    with pytest.raises(ValidationError, match=message):
        PairTruth(
            left_record_id=UUID(int=1),
            right_record_id=UUID(int=2),
            disposition=disposition,
            scenario=scenario,
            same_entity=same_entity,
        )


def test_answer_key_rejects_a_pair_contradicting_membership_truth() -> None:
    with pytest.raises(ValidationError, match="membership truth says otherwise"):
        AmbiguityAnswerKey(
            record_memberships=(
                RecordMembership(record_id=UUID(int=1), entity_id="entity-0001"),
                RecordMembership(record_id=UUID(int=2), entity_id="entity-0001"),
            ),
            pairs=(
                PairTruth(
                    left_record_id=UUID(int=1),
                    right_record_id=UUID(int=2),
                    disposition=PairDisposition.INSUFFICIENT,
                    scenario=ScenarioKind.SPARSE_RECORDS,
                    same_entity=False,
                ),
            ),
        )


def test_the_evaluator_separates_false_merges_from_false_splits() -> None:
    """Different harms, so a single score must not trade them off silently."""

    benchmark = _benchmark()
    predictions = [
        PairPrediction(
            left_record_id=pair.left_record_id,
            right_record_id=pair.right_record_id,
            disposition=PairDisposition.MERGE,
        )
        for pair in benchmark.answer_key.pairs
    ]
    metrics = evaluate_ambiguity_predictions(predictions, benchmark=benchmark)

    expected = Counter(item.disposition for item in benchmark.answer_key.pairs)
    assert metrics.false_merges == expected[PairDisposition.SEPARATE]
    assert metrics.false_splits == 0
    assert metrics.unwarranted_decisions == expected[PairDisposition.INSUFFICIENT]
    assert metrics.coverage == 1.0


def test_abstaining_everywhere_scores_no_precision_and_no_coverage() -> None:
    """Precision without coverage is meaningless; the report must show both."""

    benchmark = _benchmark()
    metrics = evaluate_ambiguity_predictions(
        [
            PairPrediction(
                left_record_id=pair.left_record_id,
                right_record_id=pair.right_record_id,
                disposition=PairDisposition.INSUFFICIENT,
            )
            for pair in benchmark.answer_key.pairs
        ],
        benchmark=benchmark,
    )

    assert metrics.coverage == 0.0
    assert metrics.decided_precision is None
    assert metrics.false_merges == metrics.false_splits == 0
    assert metrics.abstained_count == metrics.pair_count


def test_every_scenario_warns_on_low_support() -> None:
    """The canonical pack carries one pair per scenario, and says so.

    A 1-of-1 slice is not a rate. The flag is machine-readable so a consumer
    rendering a table cannot present it as one.
    """

    metrics = run_ambiguity_baseline(exact_strong_identifier)

    assert set(metrics.low_support_scenarios) == set(ScenarioKind)
    assert all(item.support < MINIMUM_SCENARIO_SUPPORT for item in metrics.scenarios)


def test_the_report_has_no_aggregate_score() -> None:
    """Deliberate: one number is what let a broken resolver read as perfect."""

    fields = set(type(run_ambiguity_baseline(precision_first)).model_fields)

    assert not {"f1", "score", "accuracy", "overall"} & fields


@pytest.mark.parametrize(("name", "decide"), AMBIGUITY_BASELINES)
def test_no_baseline_resolves_the_pack(name: str, decide: _Decide) -> None:
    """The whole point. Every shortcut must fail somewhere."""

    metrics = run_ambiguity_baseline(decide)
    wrong = metrics.false_merges + metrics.false_splits + metrics.unwarranted_decisions

    assert wrong > 0, f"{name} resolved the pack, so it is not adversarial enough"


def test_abstention_buys_precision_at_the_cost_of_coverage() -> None:
    """The trade the pack exists to make visible."""

    deciding = run_ambiguity_baseline(exact_strong_identifier)
    abstaining = run_ambiguity_baseline(precision_first)

    assert abstaining.coverage < deciding.coverage
    assert deciding.decided_precision is not None
    assert abstaining.decided_precision is not None
    assert abstaining.decided_precision > deciding.decided_precision
    assert abstaining.false_merges < deciding.false_merges


def test_submissions_must_cover_the_pack_exactly() -> None:
    benchmark = _benchmark()
    complete = [
        PairPrediction(
            left_record_id=pair.left_record_id,
            right_record_id=pair.right_record_id,
            disposition=PairDisposition.SEPARATE,
        )
        for pair in benchmark.answer_key.pairs
    ]

    with pytest.raises(AmbiguityEvaluationError, match="exactly"):
        evaluate_ambiguity_predictions(complete[:-1], benchmark=benchmark)

    with pytest.raises(AmbiguityEvaluationError, match="twice"):
        evaluate_ambiguity_predictions([*complete, complete[0]], benchmark=benchmark)


def _sparse_pair(left: int, right: int) -> PairTruth:
    return PairTruth(
        left_record_id=UUID(int=left),
        right_record_id=UUID(int=right),
        disposition=PairDisposition.INSUFFICIENT,
        scenario=ScenarioKind.SPARSE_RECORDS,
        same_entity=True,
    )


def test_pair_records_must_be_distinct_and_ordered() -> None:
    """Ordering makes a pair's identity canonical, so (a,b) and (b,a) cannot both
    exist and quietly count twice."""

    with pytest.raises(ValidationError, match="distinct and ordered"):
        PairTruth(
            left_record_id=UUID(int=2),
            right_record_id=UUID(int=1),
            disposition=PairDisposition.INSUFFICIENT,
            scenario=ScenarioKind.SPARSE_RECORDS,
            same_entity=True,
        )


def test_answer_key_rejects_duplicate_and_unknown_pairs() -> None:
    memberships = tuple(
        RecordMembership(record_id=UUID(int=index), entity_id="entity-0001")
        for index in (1, 2)
    )

    with pytest.raises(ValidationError, match="pairs must be unique"):
        AmbiguityAnswerKey(
            record_memberships=memberships,
            pairs=(_sparse_pair(1, 2), _sparse_pair(1, 2)),
        )

    with pytest.raises(ValidationError, match="no membership"):
        AmbiguityAnswerKey(record_memberships=memberships, pairs=(_sparse_pair(1, 9),))
