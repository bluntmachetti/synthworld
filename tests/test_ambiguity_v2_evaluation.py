"""What v2 evaluation and serialization have to prove.

The two truths stay apart, the evaluator counts the same harms v1 counts and attaches
the pack's ceiling, and - the invariant the floor theorem rests on - the serialized
public task is re-derived byte for byte from the modelled observation tuple alone, so
nothing latent-dependent reaches serialization.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from synthworld.ambiguity import PairDisposition, PairPrediction, PublicRecordPair
from synthworld.ambiguity_baselines import (
    AMBIGUITY_V2_BASELINES,
    run_ambiguity_v2_baseline,
)
from synthworld.ambiguity_evidence import EvidenceKind
from synthworld.ambiguity_floor import FLOOR_PUBLICATION, floor_digest
from synthworld.ambiguity_metrics import (
    AmbiguityEvaluationError,
    evaluate_ambiguity_v2_dispositions,
)
from synthworld.ambiguity_serialization import (
    AmbiguityV2DispositionTruth,
    AmbiguityV2MembershipTruth,
    ambiguity_v2_artifacts,
    ambiguity_v2_disposition_truth_to_json,
    ambiguity_v2_manifest,
    ambiguity_v2_membership_truth_to_json,
    ambiguity_v2_public_to_json,
    ambiguity_v2_truths,
)
from synthworld.ambiguity_v2 import (
    DerivedPairTruth,
    PublicAmbiguityTaskV2,
    public_pairs_from_derived,
)
from synthworld.ambiguity_v2_generator import (
    _distractor,
    _record,
    generate_ambiguity_v2_pack,
)
from synthworld.connection import PublicConnectionCorpus

_KEY = b"v2-evaluation-key"
_SEED = 21


def _pack() -> tuple[PublicAmbiguityTaskV2, tuple[DerivedPairTruth, ...]]:
    return generate_ambiguity_v2_pack(seed=_SEED, key=_KEY)


def test_truths_project_to_separate_typed_halves() -> None:
    task, truths = _pack()
    dispositions, memberships = ambiguity_v2_truths(task, truths)

    assert len(dispositions.pairs) == len(truths)
    for pair, truth in zip(dispositions.pairs, truths, strict=True):
        assert pair.left_record_id == truth.left_record_id
        assert pair.disposition is truth.disposition
        assert pair.same_entity is truth.same_entity

    # Every record of the corpus appears exactly once in membership truth -
    # distractors included, each an entity of one.
    record_ids = {record.id for record in task.corpus.identity_records}
    assert {item.record_id for item in memberships.record_memberships} == record_ids


def test_same_entity_pairs_share_one_canonical_entity() -> None:
    task, truths = _pack()
    _, memberships = ambiguity_v2_truths(task, truths)
    entity_of = {
        item.record_id: item.entity_id for item in memberships.record_memberships
    }
    for truth in truths:
        if truth.same_entity:
            assert entity_of[truth.left_record_id] == entity_of[truth.right_record_id]
        else:
            assert entity_of[truth.left_record_id] != entity_of[truth.right_record_id]
    # Canonical: the entity id is its least member's id.
    for truth in truths:
        if truth.same_entity:
            entity = entity_of[truth.left_record_id]
            assert entity == str(min(truth.left_record_id, truth.right_record_id))


def test_the_evaluator_scores_and_attaches_the_ceiling() -> None:
    task, truths = _pack()
    dispositions, _ = ambiguity_v2_truths(task, truths)
    predictions = [
        PairPrediction(
            left_record_id=pair.left_record_id,
            right_record_id=pair.right_record_id,
            disposition=pair.disposition,
        )
        for pair in dispositions.pairs
    ]

    metrics = evaluate_ambiguity_v2_dispositions(
        predictions, public=task, truth=dispositions
    )
    # A perfect submission decides every decidable pair and abstains on the rest.
    assert metrics.false_merges == 0
    assert metrics.false_splits == 0
    assert metrics.unwarranted_decisions == 0
    assert metrics.decided_count == metrics.decidable_count
    assert metrics.correct_decided_count == metrics.decidable_count
    assert metrics.decided_precision == 1.0
    assert metrics.pack_floor == FLOOR_PUBLICATION.floor
    assert metrics.floor_digest == floor_digest()


def test_the_evaluator_counts_each_harm_separately() -> None:
    task, truths = _pack()
    dispositions, _ = ambiguity_v2_truths(task, truths)
    flipped = []
    for pair in dispositions.pairs:
        if pair.disposition is PairDisposition.MERGE:
            disposition = PairDisposition.SEPARATE  # a false split
        elif pair.disposition is PairDisposition.SEPARATE:
            disposition = PairDisposition.MERGE  # a false merge
        else:
            disposition = PairDisposition.MERGE  # an unwarranted decision
        flipped.append(
            PairPrediction(
                left_record_id=pair.left_record_id,
                right_record_id=pair.right_record_id,
                disposition=disposition,
            )
        )

    metrics = evaluate_ambiguity_v2_dispositions(
        flipped, public=task, truth=dispositions
    )
    merges = sum(
        1 for p in dispositions.pairs if p.disposition is PairDisposition.MERGE
    )
    separates = sum(
        1 for p in dispositions.pairs if p.disposition is PairDisposition.SEPARATE
    )
    insufficient = sum(
        1 for p in dispositions.pairs if p.disposition is PairDisposition.INSUFFICIENT
    )
    assert metrics.false_splits == merges
    assert metrics.false_merges == separates
    assert metrics.unwarranted_decisions == insufficient
    assert metrics.correct_decided_count == 0
    assert metrics.abstained_count == 0


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("duplicate_truth", "duplicate pair"),
        ("duplicate_public", "duplicate pair"),
        ("missing_truth", "cover exactly"),
        ("extra_prediction", "submitted twice"),
        ("missing_prediction", "cover exactly"),
        ("no_predictions", "no predictions"),
        ("non_public_record", "non-public record"),
        ("empty_public_pairs", "no record pairs"),
    ],
)
def test_the_evaluator_refuses_malformed_submissions(
    mutation: str, message: str
) -> None:
    task, truths = _pack()
    dispositions, _ = ambiguity_v2_truths(task, truths)
    predictions = [
        PairPrediction(
            left_record_id=pair.left_record_id,
            right_record_id=pair.right_record_id,
            disposition=pair.disposition,
        )
        for pair in dispositions.pairs
    ]

    if mutation == "duplicate_truth":
        doubled = AmbiguityV2DispositionTruth(
            pairs=(*dispositions.pairs, dispositions.pairs[0])
        )
        with pytest.raises(AmbiguityEvaluationError, match=message):
            evaluate_ambiguity_v2_dispositions(predictions, public=task, truth=doubled)
        return
    if mutation == "duplicate_public":
        # `model_copy` skips validation, reaching the evaluator's own duplicate check.
        doubled_task = task.model_copy(
            update={"pairs_to_decide": (*task.pairs_to_decide, task.pairs_to_decide[0])}
        )
        with pytest.raises(AmbiguityEvaluationError, match=message):
            evaluate_ambiguity_v2_dispositions(
                predictions, public=doubled_task, truth=dispositions
            )
        return
    if mutation == "non_public_record":
        stranger = PublicRecordPair.model_construct(
            left_record_id=UUID(int=10**12), right_record_id=UUID(int=10**12 + 1)
        )
        bad_task = task.model_copy(update={"pairs_to_decide": (stranger,)})
        with pytest.raises(AmbiguityEvaluationError, match=message):
            evaluate_ambiguity_v2_dispositions(
                predictions, public=bad_task, truth=dispositions
            )
        return
    if mutation == "missing_truth":
        trimmed = AmbiguityV2DispositionTruth(pairs=dispositions.pairs[:-1])
        with pytest.raises(AmbiguityEvaluationError, match=message):
            evaluate_ambiguity_v2_dispositions(predictions, public=task, truth=trimmed)
        return
    if mutation == "extra_prediction":
        with pytest.raises(AmbiguityEvaluationError, match=message):
            evaluate_ambiguity_v2_dispositions(
                [*predictions, predictions[0]], public=task, truth=dispositions
            )
        return
    if mutation == "missing_prediction":
        with pytest.raises(AmbiguityEvaluationError, match=message):
            evaluate_ambiguity_v2_dispositions(
                predictions[:-1], public=task, truth=dispositions
            )
        return
    if mutation == "empty_public_pairs":
        # `model_copy` skips validation, so the model's `min_length=1` cannot mask
        # the evaluator's own empty-task guard.
        empty_task = task.model_copy(update={"pairs_to_decide": ()})
        with pytest.raises(AmbiguityEvaluationError, match=message):
            evaluate_ambiguity_v2_dispositions(
                predictions, public=empty_task, truth=dispositions
            )
        return
    with pytest.raises(AmbiguityEvaluationError, match=message):
        evaluate_ambiguity_v2_dispositions([], public=task, truth=dispositions)


def test_baselines_run_and_do_not_resolve_the_pack() -> None:
    results = [
        (name, run_ambiguity_v2_baseline(fn, seed=7, key=b"baseline-key"))
        for name, fn in AMBIGUITY_V2_BASELINES
    ]
    assert len(results) == 3
    for _name, metrics in results:
        # Every baseline gets something wrong: the pack is not a lookup table.
        harms = (
            metrics.false_merges + metrics.false_splits + metrics.unwarranted_decisions
        )
        assert harms > 0
        # And none crosses the ceiling the floor publishes.
        ceiling = 1.0 - metrics.pack_floor
        decided_accuracy = (
            metrics.correct_decided_count / metrics.pair_count
            if metrics.pair_count
            else 0.0
        )
        assert decided_accuracy <= ceiling


def test_v2_artifacts_are_physically_separate() -> None:
    task, truths = _pack()
    artifacts = ambiguity_v2_artifacts(task, truths)
    assert set(artifacts) == {
        "ambiguity-v2-public.json",
        "ambiguity-v2-memberships.json",
        "ambiguity-v2-dispositions.json",
    }
    manifest = ambiguity_v2_manifest(artifacts)
    assert len(manifest.strip().splitlines()) == 3
    # Each half parses on its own, without the other.
    dispositions, memberships = ambiguity_v2_truths(task, truths)
    assert (
        AmbiguityV2DispositionTruth.model_validate_json(
            ambiguity_v2_disposition_truth_to_json(dispositions)
        )
        == dispositions
    )
    assert (
        AmbiguityV2MembershipTruth.model_validate_json(
            ambiguity_v2_membership_truth_to_json(memberships)
        )
        == memberships
    )


def test_public_serialization_refuses_foreign_models() -> None:
    with pytest.raises(ValidationError):
        PublicAmbiguityTaskV2.model_validate({"schema_version": "2.1.0"})


def test_the_public_task_is_a_function_of_observations_alone() -> None:
    """The seventh invariant: artifact factorization.

    Re-derive the serialized public task byte for byte from the modelled observation
    tuple - rendered values, presence patterns, pack structure, seed and key - with
    no truth in the inputs. If a future field were derived from `same_entity` or the
    disposition, the reconstruction would diverge and this comparison would fail.
    """

    task, truths = _pack()
    by_id = {record.id: record for record in task.corpus.identity_records}

    rebuilt_records = []
    for slot, truth in enumerate(truths):
        for side, record_id in enumerate((truth.left_record_id, truth.right_record_id)):
            record = by_id[record_id]
            family, given = record.display_name.split(", ", 1)
            rendered: dict[EvidenceKind, tuple[str, str]] = {
                EvidenceKind.GIVEN_NAME: (given, given),
                EvidenceKind.FAMILY_NAME: (family, family),
            }
            carried = [EvidenceKind.GIVEN_NAME, EvidenceKind.FAMILY_NAME]
            for attribute in record.attributes:
                kind = EvidenceKind(attribute.kind.value)
                rendered[kind] = (attribute.value, attribute.value)
                carried.append(kind)
            rebuilt_records.append(
                _record(
                    _SEED,
                    slot,
                    side,
                    _KEY,
                    record_id,
                    rendered,
                    tuple(carried),
                )
            )
    distractor_count = len(task.distractor_ids)
    rebuilt_records.extend(
        _distractor(_SEED, index, _KEY) for index in range(distractor_count)
    )

    rebuilt = PublicAmbiguityTaskV2(
        corpus=PublicConnectionCorpus(
            seed=task.corpus.seed,
            identity_records=tuple(sorted(rebuilt_records, key=lambda item: item.id)),
            association_records=(),
        ),
        pairs_to_decide=public_pairs_from_derived(truths),
    )
    assert ambiguity_v2_public_to_json(rebuilt) == ambiguity_v2_public_to_json(task)
