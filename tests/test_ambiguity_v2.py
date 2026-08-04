"""What v2 must prove: the answer follows from evidence, and nothing else carries it."""

from __future__ import annotations

from collections import Counter, defaultdict
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from synthworld.ambiguity import PairDisposition, PublicRecordPair
from synthworld.ambiguity_grammar import EvidenceKind, Relation, kind_fingerprint
from synthworld.ambiguity_v2 import (
    AMBIGUITY_V2_SCHEMA_VERSION,
    DerivedPairTruth,
    PublicAmbiguityTaskV2,
    public_pairs_from_derived,
)
from synthworld.ambiguity_v2_generator import (
    disposition_counts,
    generate_ambiguity_v2_pack,
    prevalence_of,
)
from synthworld.connection import PublicConnectionCorpus, PublicIdentityRecord

_KEY = b"held-out-key"


def _truth(**overrides: object) -> DerivedPairTruth:
    base: dict[str, object] = {
        "left_record_id": UUID(int=1),
        "right_record_id": UUID(int=2),
        "same_entity": True,
        "comparisons": {
            EvidenceKind.GIVEN_NAME: Relation.EQUAL,
            EvidenceKind.DATE_OF_BIRTH: Relation.EQUAL,
        },
        "disposition": PairDisposition.MERGE,
    }
    return DerivedPairTruth.model_validate(base | overrides)


def test_a_disposition_that_does_not_follow_from_the_evidence_cannot_be_built() -> None:
    """The one guarantee everything else rests on.

    v1 checked a disposition against a lookup table keyed by scenario, which made the
    table the ground truth and every route to it a leak. Here the disposition has no
    independent existence, so a generator that computed it any other way is refused at
    construction rather than caught by a test that might never be written.
    """

    with pytest.raises(ValidationError, match="does not follow from the evidence"):
        _truth(disposition=PairDisposition.SEPARATE)


def test_truth_and_the_evidence_are_allowed_to_disagree() -> None:
    """Two people who look identical on paper are `merge` and not the same entity.

    v1 forbade this - a merge pair had to be the same entity - which is why it could not
    represent `same_name_and_date_of_birth` honestly and why #77 exists. The disposition
    is what the public evidence justifies; `same_entity` is what is true. A benchmark
    that conflates them is scoring clairvoyance rather than resolution.
    """

    pair = _truth(same_entity=False)

    assert pair.disposition is PairDisposition.MERGE
    assert not pair.same_entity


def test_a_pair_with_no_comparisons_is_refused() -> None:
    with pytest.raises(ValidationError, match="at least one comparison"):
        _truth(comparisons={})


def test_pair_records_must_be_distinct_and_ordered() -> None:
    with pytest.raises(ValidationError, match="distinct and ordered"):
        _truth(left_record_id=UUID(int=2), right_record_id=UUID(int=1))

    # Equal, not just reversed. The name says distinct *and* ordered and an earlier
    # version only checked the ordering half.
    with pytest.raises(ValidationError, match="distinct and ordered"):
        _truth(left_record_id=UUID(int=2), right_record_id=UUID(int=2))


def _task(**overrides: object) -> PublicAmbiguityTaskV2:
    task, _ = generate_ambiguity_v2_pack(seed=1, key=_KEY)
    return PublicAmbiguityTaskV2.model_validate(task.model_dump() | overrides)


def test_the_public_task_refuses_a_repeated_pair() -> None:
    """How many times a pair is listed is a free choice, so it can be bound to truth."""

    task, _ = generate_ambiguity_v2_pack(seed=1, key=_KEY)
    first = task.pairs_to_decide[0]

    with pytest.raises(ValidationError, match="must not repeat a pair"):
        _task(pairs_to_decide=(first, first, *task.pairs_to_decide[1:]))


def test_the_public_task_refuses_pairs_out_of_canonical_order() -> None:
    task, _ = generate_ambiguity_v2_pack(seed=1, key=_KEY)

    with pytest.raises(ValidationError, match="canonical record-id order"):
        _task(pairs_to_decide=tuple(reversed(task.pairs_to_decide)))


def test_the_public_task_refuses_a_pair_naming_a_record_it_does_not_have() -> None:
    """Otherwise the pair list can reference records the solver was never shown."""

    left, right = sorted((uuid4(), uuid4()))
    task, _ = generate_ambiguity_v2_pack(seed=1, key=_KEY)
    stray = PublicRecordPair(left_record_id=left, right_record_id=right)

    with pytest.raises(ValidationError, match="present in the corpus"):
        _task(
            pairs_to_decide=tuple(
                sorted(
                    (*task.pairs_to_decide, stray),
                    key=lambda item: (item.left_record_id, item.right_record_id),
                )
            )
        )


def test_a_pack_replays_and_is_keyed() -> None:
    first, first_truths = generate_ambiguity_v2_pack(seed=5, key=_KEY)
    again, again_truths = generate_ambiguity_v2_pack(seed=5, key=_KEY)
    other, other_truths = generate_ambiguity_v2_pack(seed=5, key=b"a-different-key")

    assert first == again
    assert first_truths == again_truths
    # The truths must move too, not just some public field. A generator that drew
    # labels and evidence from the seed alone and used the key only for `source_type`
    # would pass a test that discarded the other key's truths - and would be
    # seed-invertible without the key, which is exactly v1's tenth channel.
    assert first != other
    assert first_truths != other_truths
    assert [item.disposition for item in first_truths] != [
        item.disposition for item in other_truths
    ]


def test_the_pack_shape_is_not_a_constant() -> None:
    """v1 shipped fifteen pairs with five merges in every pack ever generated.

    Anything constant across seeds is something a consumer can hard-code and a solver
    can exploit - a fixed prevalence makes guessing the majority class a free score, and
    a fixed pair count makes the pack's size an assertion rather than an observation.
    """

    shapes = set()
    prevalences = set()
    distractors = set()
    for seed in range(1, 25):
        task, truths = generate_ambiguity_v2_pack(seed=seed, key=_KEY)
        shapes.add(len(truths))
        prevalences.add(round(prevalence_of(truths), 3))
        distractors.add(len(task.distractor_ids))

    assert len(shapes) > 5
    assert len(prevalences) > 15
    assert len(distractors) > 5


def test_every_disposition_occurs() -> None:
    """A third class with nothing in it is a two-class benchmark with a longer enum."""

    seen: Counter[PairDisposition] = Counter()
    for seed in range(1, 25):
        _, truths = generate_ambiguity_v2_pack(seed=seed, key=_KEY)
        seen.update(disposition_counts(truths))

    assert all(seen[disposition] for disposition in PairDisposition)


def test_distractors_are_present_and_belong_to_no_pair() -> None:
    """A record the pair list never mentions is a distractor, with nothing marking it.

    v1's public record set was exactly the records appearing in pairs, so membership was
    itself a signal and counting a record's appearances bounded what it could be.
    """

    task, truths = generate_ambiguity_v2_pack(seed=3, key=_KEY)
    asked = {
        item
        for pair in task.pairs_to_decide
        for item in (pair.left_record_id, pair.right_record_id)
    }

    assert task.distractor_ids
    assert not task.distractor_ids & asked
    assert len(task.corpus.identity_records) == len(asked) + len(task.distractor_ids)
    assert len(asked) == 2 * len(truths)


def _assert_same_distribution[Bucket](observed: dict[bool, Counter[Bucket]]) -> None:
    """Distractors and paired records must be drawn alike, bucket by bucket."""

    totals = {role: sum(tally.values()) for role, tally in observed.items()}
    for bucket in set(observed[True]) | set(observed[False]):
        share = [observed[role][bucket] / totals[role] for role in (True, False)]
        assert abs(share[0] - share[1]) < 0.05, bucket


def test_a_distractor_is_not_distinguishable_by_shape() -> None:
    """If a distractor were cheaper to build, "is this asked about" would be readable.

    A solver that can tell which records are in the pair list has been handed the pair
    list, which is public anyway - but it has also learnt that record shape carries
    something, and the next thing shape could carry is the answer.
    """

    by_role: dict[bool, Counter[int]] = defaultdict(Counter)
    sources: dict[bool, Counter[str]] = defaultdict(Counter)
    for seed in range(1, 41):
        task, _ = generate_ambiguity_v2_pack(seed=seed, key=_KEY)
        for record in task.corpus.identity_records:
            distractor = record.id in task.distractor_ids
            by_role[distractor][len(record.attributes)] += 1
            sources[distractor][record.source_type.value] += 1

    # Compared as distributions, not as sets of observed values. A first version
    # asserted only that the two attribute-count sets intersected, which would have
    # passed with every distractor carrying one attribute and every paired record six.
    # The test name claimed indistinguishability and the body checked overlap.
    _assert_same_distribution(by_role)
    _assert_same_distribution(sources)


def test_the_fingerprint_no_longer_determines_the_answer() -> None:
    """The measurement #62 exists for, run as the attack rather than argued.

    In v1 a decoder holding only the kind-level fingerprint - which kinds are present
    and which agree - recovered the disposition on 750 of 750 pairs across fifty seeds,
    because every fingerprint was a scenario and every scenario had one hand-written
    answer. The mapping was a bijection by construction, not by evidence.

    Here the same decoder is trained on sixty public-key seeds and scored on held-out
    seeds under a held-out key, with a majority-class fallback so that an unseen
    fingerprint costs it a guess rather than a certainty. It gets **0.694** against a
    0.488 majority baseline, and **0.840** on the 67.6% of pairs whose fingerprint it
    has seen before.

    What it retains is legitimate: the fingerprint *is* evidence, and agreement patterns
    really do predict identity. A benchmark where reading the evidence did not help
    would be broken in the other direction. What it loses is the part v1 could not
    express - whether a disagreement is a reformatted phone number or a different
    person's, which the fingerprint flattens to "did not agree".
    """

    learned: dict[tuple[tuple[str, bool], ...], Counter[PairDisposition]] = defaultdict(
        Counter
    )
    prior: Counter[PairDisposition] = Counter()
    for seed in range(1, 61):
        _, truths = generate_ambiguity_v2_pack(seed=seed, key=b"public")
        for pair in truths:
            learned[kind_fingerprint(pair.relations)][pair.disposition] += 1
            prior[pair.disposition] += 1
    # `min` over the tied-most-common entries, so the decoder does not depend on
    # dictionary insertion order in a suite that gates on PYTHONHASHSEED independence.
    fallback = min(prior.most_common(1))[0]

    correct = total = 0
    for seed in range(900, 940):
        _, truths = generate_ambiguity_v2_pack(seed=seed, key=_KEY)
        for pair in truths:
            tally = learned.get(kind_fingerprint(pair.relations))
            guess = min(tally.most_common(1))[0] if tally else fallback
            correct += guess is pair.disposition
            total += 1

    assert correct / total < 0.80  # v1 scored 1.000 here


def test_public_pairs_are_projected_in_canonical_order() -> None:
    pairs = (
        _truth(left_record_id=UUID(int=7), right_record_id=UUID(int=9)),
        _truth(left_record_id=UUID(int=3), right_record_id=UUID(int=4)),
    )

    projected = public_pairs_from_derived(pairs)

    assert [item.left_record_id for item in projected] == [UUID(int=3), UUID(int=7)]


def test_the_schema_version_is_declared() -> None:
    task, _ = generate_ambiguity_v2_pack(seed=1, key=_KEY)

    assert task.schema_version == AMBIGUITY_V2_SCHEMA_VERSION == "2.0.0"
    assert isinstance(task.corpus, PublicConnectionCorpus)


def test_the_two_sides_of_a_pair_carry_different_fields() -> None:
    """One record holding a phone the other lacks is the ordinary case, not an edge.

    A first version drew field presence per pair rather than per side, so both records
    always carried exactly the same kinds: `LOPSIDED` never occurred in 3277 relations
    and all 626 pairs had identically sized records. A quarter of the relation
    vocabulary was unreachable, which meant the missingness rule - worth zero bits, so
    that a sparse record is not punished for being sparse - was never exercised by any
    generated pack.
    """

    relations: Counter[Relation] = Counter()
    same_size = Counter[bool]()
    for seed in range(1, 21):
        task, truths = generate_ambiguity_v2_pack(seed=seed, key=_KEY)
        by_id = {record.id: record for record in task.corpus.identity_records}
        for pair in truths:
            relations.update(pair.relations.values())
            same_size[
                len(by_id[pair.left_record_id].attributes)
                == len(by_id[pair.right_record_id].attributes)
            ] += 1

    assert relations[Relation.LOPSIDED]
    assert same_size[False]
    assert set(relations) == set(Relation)


def test_a_one_sided_kind_appears_on_exactly_one_record() -> None:
    """Otherwise `LOPSIDED` is a label rather than something the corpus shows."""

    task, truths = generate_ambiguity_v2_pack(seed=4, key=_KEY)
    by_id = {record.id: record for record in task.corpus.identity_records}
    checked = 0
    for pair in truths:
        left = {item.kind.value for item in by_id[pair.left_record_id].attributes}
        right = {item.kind.value for item in by_id[pair.right_record_id].attributes}
        for kind, relation in pair.relations.items():
            if relation is Relation.LOPSIDED and kind.value in left | right:
                checked += 1
                assert (kind.value in left) != (kind.value in right), kind.value

    assert checked


def test_a_kind_compared_twice_is_refused() -> None:
    """A repeated kind would let one comparison silently overwrite another.

    Only reachable by passing the stored tuple form directly - the mapping shorthand
    cannot express it - which is exactly why the validator has to check the stored form
    rather than trusting the shorthand it usually arrives as.
    """

    with pytest.raises(ValidationError, match="not compare the same kind twice"):
        _truth(
            comparisons=(
                (EvidenceKind.GIVEN_NAME, Relation.EQUAL),
                (EvidenceKind.GIVEN_NAME, Relation.FAR),
            )
        )


def test_comparisons_out_of_canonical_order_are_refused() -> None:
    """The order comparisons were drawn in must not survive into the artifact.

    Emission order was one of v1's leaks - the i-th public pair was the i-th scenario,
    measured 15/15 - so a tuple field that accepted any order would reopen it one level
    down.
    """

    with pytest.raises(ValidationError, match="canonical kind order"):
        _truth(
            comparisons=(
                (EvidenceKind.PHONE, Relation.EQUAL),
                (EvidenceKind.GIVEN_NAME, Relation.EQUAL),
            )
        )


def _metadata(record: object, position: int, pair_index: int) -> dict[str, object]:
    """Everything about a record except the evidence it carries.

    Every one of these was a leak channel in v1, or is the v2 analogue of one. None may
    predict the answer; the evidence may, and does.
    """

    assert isinstance(record, PublicIdentityRecord)
    return {
        "source_type": record.source_type.value,
        "record_confidence": round(record.confidence, 1),
        "attribute_count": len(record.attributes),
        "mean_attribute_confidence": round(
            sum(item.confidence for item in record.attributes) / len(record.attributes),
            1,
        ),
        "corpus_position_parity": position % 4,
        "identifier_low_bits": record.id.int % 8,
        "pair_index_parity": pair_index % 4,
        "kinds_present": tuple(sorted(item.kind.value for item in record.attributes)),
    }


def test_no_metadata_channel_predicts_the_answer() -> None:
    """The regression test v2 shipped without, and the reason v1 leaked eleven times.

    Every closed channel in #59 and #66 was metadata quietly bound to truth - display
    order, identifiers, provenance strings, source counts, case shapes. Nothing in this
    suite would have caught one recurring in v2: appending `same_entity` to a confidence
    purpose string passes every other test here.

    So this is the attack, run as a test. A decoder is trained on one key's packs, one
    metadata channel at a time, and scored on held-out seeds under a held-out key. A
    channel that beats the majority baseline by a real margin is carrying the answer.
    The evidence deliberately is not offered to it: reading the answer off the values is
    the task, and a test that forbade that would be forbidding the benchmark.
    """

    def channels(
        record: PublicIdentityRecord, position: int, index: int, truth: DerivedPairTruth
    ) -> dict[str, object]:
        # A control channel that *is* bound to the label, so the decoder has to catch
        # something. Without it this test proves only that the decoder scores badly,
        # which a decoder that always guessed wrong would also do - and a test that
        # cannot fail is the defect this suite keeps finding in the code it tests.
        return _metadata(record, position, index) | {
            "control_bound_to_the_label": truth.same_entity
        }

    trained: dict[str, dict[object, Counter[PairDisposition]]] = defaultdict(
        lambda: defaultdict(Counter)
    )
    prior: Counter[PairDisposition] = Counter()
    for seed in range(1, 41):
        task, truths = generate_ambiguity_v2_pack(seed=seed, key=b"attacker-key")
        position = {
            record.id: index
            for index, record in enumerate(task.corpus.identity_records)
        }
        by_id = {record.id: record for record in task.corpus.identity_records}
        for index, pair in enumerate(truths):
            for record_id in (pair.left_record_id, pair.right_record_id):
                record = by_id[record_id]
                for channel, value in channels(
                    record, position[record_id], index, pair
                ).items():
                    trained[channel][value][pair.disposition] += 1
            prior[pair.disposition] += 1
    fallback = min(prior.most_common(1))[0]

    scored: Counter[str] = Counter()
    total = 0
    seen: Counter[PairDisposition] = Counter()
    for seed in range(800, 830):
        task, truths = generate_ambiguity_v2_pack(seed=seed, key=_KEY)
        position = {
            record.id: index
            for index, record in enumerate(task.corpus.identity_records)
        }
        by_id = {record.id: record for record in task.corpus.identity_records}
        for index, pair in enumerate(truths):
            total += 1
            seen[pair.disposition] += 1
            record = by_id[pair.left_record_id]
            for channel, value in channels(
                record, position[pair.left_record_id], index, pair
            ).items():
                tally = trained[channel].get(value)
                guess = min(tally.most_common(1))[0] if tally else fallback
                scored[channel] += guess is pair.disposition

    baseline = max(seen.values()) / total

    # The detector works: a channel bound to the label is caught easily.
    assert scored["control_bound_to_the_label"] / total > baseline + 0.15

    for channel, correct in scored.items():
        if channel == "control_bound_to_the_label":
            continue
        # Five points of headroom over the majority class, which is what a channel
        # carrying nothing looks like once sampling noise is allowed for.
        assert correct / total < baseline + 0.05, (channel, correct / total, baseline)


def test_every_disposition_holds_a_real_share_of_the_pack() -> None:
    """A third class with 7% of the mass is a two-class benchmark with a longer enum.

    `test_every_disposition_occurs` only asks that each class appear *somewhere* across
    twenty-four seeds, which stayed true while `insufficient` fell to 7.6% of pairs and
    **8.5% of individual packs contained none at all**. A consumer scoring one pack
    would have been scoring two classes one time in twelve, and nothing said so.

    Two levers set the balance and both are needed. Widening the decision band alone,
    far enough to fix this, makes a third canonical scenario disagree with v1 -
    `partial_but_sufficient` becomes insufficient, contradicting its own name. Raising
    the pack-size floor supplies the rest: whether a pack holds all three classes
    is a sample-size question: at this rate an 18-pair pack misses one 16% of the time
    and a 50-pair pack 0.6%.
    """

    seen: Counter[PairDisposition] = Counter()
    packs_missing_a_class = 0
    packs = 60
    for seed in range(400, 400 + packs):
        _, truths = generate_ambiguity_v2_pack(seed=seed, key=_KEY)
        present = {pair.disposition for pair in truths}
        packs_missing_a_class += len(present) < len(PairDisposition)
        seen.update(pair.disposition for pair in truths)

    total = sum(seen.values())
    for disposition in PairDisposition:
        assert seen[disposition] / total >= 0.08, (
            disposition.value,
            seen[disposition] / total,
        )
    assert packs_missing_a_class / packs <= 0.02, packs_missing_a_class / packs
