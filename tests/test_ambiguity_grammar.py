"""What the relation grammar has to prove: the fingerprint stops deciding the answer."""

from __future__ import annotations

import inspect
from collections import Counter, defaultdict
from itertools import product
from typing import cast
from unicodedata import normalize

import pytest

from synthworld.ambiguity import (
    SCENARIO_DISPOSITIONS,
    PairDisposition,
    ScenarioKind,
)
from synthworld.ambiguity_channel import (
    render_relation as _channel_render_relation,
)
from synthworld.ambiguity_channel import (
    render_value as _channel_render_value,
)
from synthworld.ambiguity_generator import _drafts
from synthworld.ambiguity_grammar import (
    _FS,
    Relation,
    _Params,
    disposition_of,
    kind_fingerprint,
    render_relation,
    render_value,
    sample_relation,
    validate_parameters,
    weight_of,
)
from synthworld.ambiguity_grammar import (
    EvidenceKind as K,
)

#: Every kind the grammar renders. The enumeration test below is combinatorial, so it
#: uses a subset; the rendering tests must cover all of them, or a kind can ship with a
#: near form nobody ever compared against its far form.
_RENDERED = (
    K.GIVEN_NAME,
    K.PHONE,
    K.EMAIL,
    K.USERNAME,
    K.FULL_ADDRESS,
    K.DATE_OF_BIRTH,
    K.FAMILY_NAME,
    K.EMPLOYER,
    K.SCHOOL_YEAR,
)
_KINDS = (K.PHONE, K.EMAIL, K.FULL_ADDRESS, K.DATE_OF_BIRTH, K.EMPLOYER)


def _vectors() -> list[dict[K, Relation]]:
    seen: list[dict[K, Relation]] = []
    for size in (3, 4):
        for chosen in product(_KINDS, repeat=size):
            if len(set(chosen)) != size:
                continue
            ordered = sorted(set(chosen), key=lambda item: item.value)
            for relations in product(
                (Relation.EQUAL, Relation.NEAR, Relation.FAR), repeat=size
            ):
                seen.append(dict(zip(ordered, relations, strict=True)))
    return seen


def test_one_fingerprint_can_carry_more_than_one_disposition() -> None:
    """The property issue #62 exists for, measured rather than argued.

    In v1 the kind-level fingerprint - which attribute kinds are present and which
    agree - determined the disposition on 750 of 750 pairs across fifty seeds, because
    each scenario was defined by its pattern and mapped to one answer. A held-out seed
    changed surface values and not a single label.
    """

    by_fingerprint: dict[tuple[tuple[str, bool], ...], set[PairDisposition]] = (
        defaultdict(set)
    )
    for vector in _vectors():
        by_fingerprint[kind_fingerprint(vector)].add(disposition_of(vector))

    ambiguous = [item for item in by_fingerprint.values() if len(item) > 1]

    assert by_fingerprint
    # Most fingerprints must be genuinely undecided, not a token few.
    assert len(ambiguous) / len(by_fingerprint) > 0.5
    # And at least one must span the whole vocabulary.
    assert any(len(item) == 3 for item in by_fingerprint.values())


def test_the_archetype_that_motivated_the_grammar() -> None:
    """A recycled number against a person who moved and kept theirs.

    Identical at the kind level - phone agrees, name, email and address differ - and
    opposite in what they justify. v1 could not express the difference, so it asserted
    the answer per scenario, which is precisely what made the pack a lookup table.

    The fingerprint records *whether* a kind agreed, so `Rob`/`Robert` and `Ada`/`Bilal`
    are both "the name differs" to it, and the two pairs are indistinguishable. Only the
    NEAR/FAR distinction separates them, and only the veto turns a contradicted given
    name into a refusal however much else agrees.
    """

    recycled = {
        K.GIVEN_NAME: Relation.FAR,
        K.PHONE: Relation.EQUAL,
        K.EMAIL: Relation.FAR,
        K.FULL_ADDRESS: Relation.FAR,
    }
    moved = {
        K.GIVEN_NAME: Relation.NEAR,
        K.PHONE: Relation.EQUAL,
        K.EMAIL: Relation.NEAR,
        K.FULL_ADDRESS: Relation.NEAR,
    }

    assert kind_fingerprint(recycled) == kind_fingerprint(moved)
    assert disposition_of(recycled) is PairDisposition.SEPARATE
    assert disposition_of(moved) is PairDisposition.MERGE


def test_no_single_value_reveals_the_relation_that_made_it() -> None:
    """The channel the signature guarantee does not close, and nearly shipped.

    A first version gave each relation its own surface marker - one email domain only
    for NEAR, another only for FAR, a parenthesised phone only for NEAR, one town only
    for a FAR address. A decoder classifying each value *in isolation* recovered the
    relation on 1200 of 1200 renderings and then ran the public `disposition_of` to get
    the answer. The key did not help, because nothing was being recomputed - the answer
    was written on the surface.

    So this trains the best structural decoder it can on one set of seeds and scores it
    on another. Anything above chance means a form belongs to a relation.
    """

    def shape(value: str) -> tuple[object, ...]:
        return (
            value.count("|"),
            value.count("@"),
            value.count("-"),
            value.count("/"),
            value.count("_"),
            value.count("."),
            value.isupper(),
            value.endswith(" "),
            value.split("@")[-1] if "@" in value else "",
            value.split("|")[2] if value.count("|") > 2 else "",
        )

    learned: dict[tuple[K, tuple[object, ...]], Counter[Relation]] = defaultdict(
        Counter
    )
    relations = (Relation.EQUAL, Relation.NEAR, Relation.FAR)
    # Every slot, not just slot zero. An implementation that stamped the relation on
    # values whenever `slot > 0` would leak nearly every generated pair while a
    # slot-zero-only test went on passing.
    for seed in range(150):
        for slot in range(3):
            for kind in _RENDERED:
                for relation in relations:
                    for value in render_relation(
                        kind, relation, seed=seed, key=b"secret", slot=slot
                    ):
                        learned[(kind, shape(value))][relation] += 1

    correct = total = 0
    for seed in range(150, 250):
        for slot in range(3):
            for kind in _RENDERED:
                for relation in relations:
                    for value in render_relation(
                        kind, relation, seed=seed, key=b"secret", slot=slot
                    ):
                        tally = learned.get((kind, shape(value)))
                        guess = tally.most_common(1)[0][0] if tally else Relation.FAR
                        total += 1
                        correct += guess is relation

    # Chance is one in three. A real channel showed 1.000 here.
    assert correct / total < 0.42


def test_nothing_that_makes_a_value_can_see_the_answer() -> None:
    """Enforced by the signature, so a leak of that shape is a type error.

    Every one of the eight metadata channels closed in #59 reached a public value by
    reading the case or its label. None of the functions that produce a public value
    has a parameter it could read one from, and this pins that rather than trusting a
    reviewer to notice a later argument being added.

    An earlier version inspected `render_relation` alone while claiming "nothing that
    makes a value", which left every other value-producing function unchecked - the
    name asserted more than the body did, which is the defect this suite keeps finding
    in the code it tests.
    """

    forbidden = {"disposition", "scenario", "same_entity", "archetype", "label"}
    for maker in (
        render_relation,
        render_value,
        _channel_render_relation,
        _channel_render_value,
        disposition_of,
    ):
        parameters = set(inspect.signature(maker).parameters)
        assert not parameters & forbidden, maker.__name__

    assert set(inspect.signature(render_relation).parameters) == {
        "kind",
        "relation",
        "seed",
        "key",
        "slot",
    }


def test_rendering_replays_and_is_keyed() -> None:
    first = render_relation(K.EMAIL, Relation.NEAR, seed=3, key=b"", slot=0)
    again = render_relation(K.EMAIL, Relation.NEAR, seed=3, key=b"", slot=0)
    keyed = render_relation(K.EMAIL, Relation.NEAR, seed=3, key=b"held-out", slot=0)

    assert first == again
    assert first != keyed


def test_an_empty_relation_vector_settles_nothing() -> None:
    assert disposition_of({}) is PairDisposition.INSUFFICIENT


def test_a_lopsided_attribute_is_neither_evidence_nor_a_fingerprint() -> None:
    """One record carrying an attribute the other lacks says nothing on its own."""

    with_lopsided = {K.PHONE: Relation.EQUAL, K.EMPLOYER: Relation.LOPSIDED}
    without = {K.PHONE: Relation.EQUAL}

    assert disposition_of(with_lopsided) is disposition_of(without)
    assert kind_fingerprint(with_lopsided) == kind_fingerprint(without)


def _projected() -> list[tuple[ScenarioKind, dict[K, Relation]]]:
    """Every canonical v1 pair, read as relations by something that cannot see labels.

    This is the join between the two worlds. v1 asserts a disposition per scenario by
    hand; the grammar derives one from evidence. Projecting the real pack - not a
    transcription of it - is what stops the two drifting apart silently, and it means a
    change to a canonical pair shows up here as a disagreement rather than as nothing.

    The projection reads only public attributes and display names, exactly what a
    resolver under test gets.
    """

    def folds_together(left: str, right: str) -> bool:
        # Transliteration is planted deliberately: `Sørensen` and `Sorensen` are one
        # surname, and reading that as FAR is a projection bug rather than a parameter
        # problem. `synthworld.ambiguity_variants._ascii_fold` cannot be reused here
        # because it drops these letters entirely - NFKD leaves them atomic, so
        # `ascii/ignore` deletes them and `Sørensen` becomes `srensen`. That is #78.
        atomic = str.maketrans(
            {"ø": "o", "Ø": "O", "ł": "l", "Ł": "L", "đ": "d", "æ": "ae"}
        )

        def fold(value: str) -> str:
            folded = value.translate(atomic)
            return (
                normalize("NFKD", folded).encode("ascii", "ignore").decode().casefold()
            )

        return fold(left) == fold(right)

    def relate(left: str | None, right: str | None) -> Relation:
        if left is None or right is None:
            return Relation.LOPSIDED
        if left == right or folds_together(left, right):
            return Relation.EQUAL
        return Relation.FAR

    drafts = _drafts()
    projected = []
    for index in range(0, len(drafts), 2):
        left, right = drafts[index], drafts[index + 1]
        left_values = {item.kind.value: item.value for item in left.attributes}
        right_values = {item.kind.value: item.value for item in right.attributes}
        relations = {
            K(name): relate(left_values.get(name), right_values.get(name))
            for name in set(left_values) | set(right_values)
            if name in set(K)
        }
        # v1 has no given-name attribute: it keeps given names inside a display string.
        # Recovering it is not a convenience - it is the only evidence separating the
        # twins pair from one person, and a rule blind to it scores them +0.97.
        left_given, right_given = (
            left.display_name.split()[0],
            right.display_name.split()[0],
        )
        stem = left_given.rstrip(".")
        if left_given == right_given or folds_together(left_given, right_given):
            relations[K.GIVEN_NAME] = Relation.EQUAL
        elif stem and right_given.startswith(stem):
            relations[K.GIVEN_NAME] = Relation.NEAR  # `H.` against `Helen`
        else:
            relations[K.GIVEN_NAME] = Relation.FAR
        projected.append((left.scenario, relations))
    return projected


#: The two the derived rule reads differently from v1's hand-written answer, and why
#: they are not fixed by moving numbers. Tracked as #77.
#:
#: `same_name_and_date_of_birth` is two people agreeing on given name, family name and
#: birth date and differing on nothing else recorded. v1 originally called that
#: `separate` because it planted two people; #77 corrected the label to `insufficient`
#: after the pack's first consumer abstained on exactly this pair, independently giving
#: the same reason - the evidence cannot justify "separate". The rule still disagrees,
#: now from the other side: it says `merge`, because the two name kinds plus a birth
#: date clear the corroboration bar. That residual overconfidence in names is #79's
#: territory, not a label defect - `insufficient` is what the evidence justifies for a
#: pair that is indistinguishable on paper.
#:
#: `contradictory_strong_identifiers` v1 calls `separate` and the rule calls
#: `insufficient` - contradiction between strong identifiers is a reason to withhold,
#: which is exactly what `partial_with_contradiction` is labelled.
#:
#: Both could be forced by tuning. With fifty-four parameters against fifteen
#: constraints that is fitting, not calibration, and it would buy 15/15 by making the
#: numbers describe this pack rather than record linkage.
_KNOWN_DISAGREEMENTS = frozenset(
    {
        ScenarioKind.SAME_NAME_AND_DATE_OF_BIRTH,
        ScenarioKind.CONTRADICTORY_STRONG_IDENTIFIERS,
    }
)


def test_the_derived_rule_agrees_with_thirteen_of_the_fifteen_answers() -> None:
    """Thirteen of fifteen, with the other two named rather than absorbed.

    The point of #62 is that a disposition should follow from evidence instead of being
    asserted per scenario. That is only worth anything if the derived answers are the
    same answers - a rule free to disagree everywhere has not replaced the lookup table,
    it has replaced the pack.
    """

    disagreed = {
        scenario
        for scenario, relations in _projected()
        if disposition_of(relations) is not SCENARIO_DISPOSITIONS[scenario]
    }

    assert disagreed == _KNOWN_DISAGREEMENTS


@pytest.mark.parametrize("kind", sorted(K))
def test_every_kind_prefers_agreement_to_contradiction(kind: K) -> None:
    """Weights must fall monotonically from EQUAL through NEAR to FAR.

    An earlier version asserted only `EQUAL > FAR`, and four kinds violated the middle
    of the ordering without it noticing: family name paid +0.63 for byte equality and
    +1.00 for a near variant, address +0.78 against +1.32, employer +0.87 against +1.00,
    and phone paid exactly the same for both. A resolver reading that table is paid more
    for a near-miss surname than for an exact match, and the test name said "prefers
    agreement" while the body allowed it.
    """

    equal, near, far = (
        weight_of(kind, relation)
        for relation in (Relation.EQUAL, Relation.NEAR, Relation.FAR)
    )

    assert equal > near > far, kind.value
    assert equal > 0.0
    assert far < 0.0
    # Missingness is neither evidence nor its opposite, so a sparse record is not
    # punished for being sparse.
    assert weight_of(kind, Relation.LOPSIDED) == 0.0


def test_a_row_that_is_not_a_distribution_is_refused() -> None:
    """Otherwise the generator and the scorer disagree with no symptom anywhere.

    `sample_relation` would draw from a skewed row while `weight_of` scored as though
    it were a distribution, so the pack would be systematically mislabelled by a rule
    that looked correct.
    """

    validate_parameters(_FS)  # the shipped table is one

    with pytest.raises(ValueError, match="must sum to one"):
        validate_parameters({K.PHONE: ((0.5, 0.2, 0.2), (0.1, 0.1, 0.8))})

    # Summing to one is not enough, and an earlier version checked nothing else. A
    # negative mass makes `log2(m/u)` a domain error or a nonsense weight; a NaN makes
    # every comparison against it false, so `sample_relation` would fall through to the
    # last outcome for that whole kind. Both of these sum to one.
    with pytest.raises(ValueError, match=r"within \(0, 1\]"):
        validate_parameters({K.PHONE: ((-1.0, 1.0, 1.0), (0.1, 0.1, 0.8))})
    with pytest.raises(ValueError, match=r"within \(0, 1\]"):
        validate_parameters({K.PHONE: ((float("nan"), 0.5, 0.5), (0.1, 0.1, 0.8))})
    # Zero is the case that reads as legitimate - "near variants never occur in this
    # population" is a sentence someone would write - and it passes every other check
    # here, then makes `weight_of` raise while `sample_relation` keeps drawing.
    with pytest.raises(ValueError, match=r"within \(0, 1\]"):
        validate_parameters({K.PHONE: ((0.5, 0.5, 0.0), (0.05, 0.15, 0.80))})
    # Cast because the annotation already forbids a two-outcome row, so mypy rejects
    # this call. The guard is still worth testing: the function is public, and a table
    # loaded from JSON or built by an untyped caller reaches it with no static check.
    short = cast("_Params", ((0.5, 0.5), (0.1, 0.1, 0.8)))
    with pytest.raises(ValueError, match="one probability per outcome"):
        validate_parameters({K.PHONE: short})


@pytest.mark.parametrize("kind", sorted(K))
def test_the_label_never_enters_the_draw_material(kind: K) -> None:
    """`same_entity` must reach the outcome only by choosing a row, never by hashing.

    Checked behaviourally rather than by reading the source. One point is drawn per
    (kind, seed, slot) and read against `m` or `u`, so the two outcomes a pair would get
    as a match and as a non-match must be consistent with a *single* quantile. If the
    label were in the hash material the two draws would be independent, and the
    quantile intervals they imply would routinely fail to intersect.

    Not exploitable without the key either way - but every leak this pack has had began
    as something that was not exploitable yet, and the earlier version put the label in
    the material for no benefit at all.
    """

    def interval(
        row: tuple[float, float, float], outcome: Relation
    ) -> tuple[float, float]:
        bounds = (0.0, row[0], row[0] + row[1], 1.0)
        index = (Relation.EQUAL, Relation.NEAR, Relation.FAR).index(outcome)
        return bounds[index], bounds[index + 1]

    matched, unmatched = _FS[kind]
    for seed in range(300):
        low, high = interval(
            matched,
            sample_relation(kind, same_entity=True, seed=seed, slot=0, key=b"k"),
        )
        other_low, other_high = interval(
            unmatched,
            sample_relation(kind, same_entity=False, seed=seed, slot=0, key=b"k"),
        )

        assert max(low, other_low) < min(high, other_high), (kind.value, seed)


@pytest.mark.parametrize("kind", sorted(K))
def test_rendering_an_absence_as_a_comparison_is_refused(kind: K) -> None:
    """`LOPSIDED` had no rendering and was silently treated as "not FAR".

    A caller asking for missingness got two values standing in no stated relation, so
    the contract that a rendered pair stands in the relation it claims did not hold for
    a quarter of the vocabulary - and `test_rendered_values_stand_in_the_relation_they_
    claim` never noticed, because it does not parametrize over LOPSIDED.
    """

    with pytest.raises(ValueError, match="absence, not a comparison"):
        render_relation(kind, Relation.LOPSIDED, seed=1, key=b"k", slot=0)


@pytest.mark.parametrize("kind", sorted(K))
def test_a_one_sided_value_is_drawn_from_the_same_pool_as_a_paired_one(kind: K) -> None:
    """Otherwise "the other record lacks this" is readable from the value itself.

    The one-sided draw uses the same purposes as a pair's first side, so it is the
    same law. Compared against a `NEAR` pair, whose first side never shares a noise
    draw, the equality is byte-for-byte.
    """

    for seed in range(40):
        one_sided = render_value(kind, seed=seed, key=b"k", slot=0)
        paired_left = render_relation(kind, Relation.NEAR, seed=seed, key=b"k", slot=0)[
            0
        ]
        assert one_sided == paired_left, (kind.value, seed)


def test_one_agreeing_field_is_never_enough_to_merge() -> None:
    """A coincidence until something else agrees too.

    A birth date alone scores +3.95 and a given name +4.64, both over the +3.0
    threshold, so two records agreeing on a date and nothing else were a merge. That was
    reachable: 79 of 14,062 generated pairs merged on the display name alone, and two of
    those were genuinely two people.

    Raising the threshold would be the wrong instrument - it weakens every vector rather
    than the ones with nothing corroborating them.
    """

    for kind in sorted(K):
        assert disposition_of({kind: Relation.EQUAL}) is not PairDisposition.MERGE, (
            kind.value
        )

    assert (
        disposition_of({K.DATE_OF_BIRTH: Relation.EQUAL, K.GIVEN_NAME: Relation.EQUAL})
        is PairDisposition.MERGE
    )


def test_the_two_halves_of_a_name_corroborate_once() -> None:
    """A given name and a family name are one string, not two witnesses.

    The corroboration rule above is defeated by its own premise otherwise: `GIVEN_NAME`
    and `FAMILY_NAME` are the two halves of one `display_name`, so counting them
    separately let a bare name match satisfy "two independent kinds agree" and carry a
    merge anyway. Measured at 93 of 3,844 merges riding on the display name alone,
    including pairs that were genuinely two people and contradicted each other on
    employer.
    """

    assert (
        disposition_of({K.GIVEN_NAME: Relation.EQUAL, K.FAMILY_NAME: Relation.EQUAL})
        is not PairDisposition.MERGE
    )
    # One genuinely independent field is all it takes.
    assert (
        disposition_of(
            {
                K.GIVEN_NAME: Relation.EQUAL,
                K.FAMILY_NAME: Relation.EQUAL,
                K.DATE_OF_BIRTH: Relation.EQUAL,
            }
        )
        is PairDisposition.MERGE
    )


def test_the_veto_yields_to_overwhelming_agreement() -> None:
    """A contradicted given name refuses a merge. It does not conclude two people.

    An absolute veto forces `separate` against +15.6 bits - every other kind
    byte-identical, including email, phone and username. The twins case justifies
    overriding family name, birth date, address and school year. It does not justify
    overriding three shared strong identifiers.
    """

    twins = {
        K.GIVEN_NAME: Relation.FAR,
        K.FAMILY_NAME: Relation.EQUAL,
        K.DATE_OF_BIRTH: Relation.EQUAL,
        K.FULL_ADDRESS: Relation.EQUAL,
        K.SCHOOL_YEAR: Relation.EQUAL,
    }
    everything = {kind: Relation.EQUAL for kind in K} | {K.GIVEN_NAME: Relation.FAR}

    assert disposition_of(twins) is PairDisposition.SEPARATE
    assert disposition_of(everything) is PairDisposition.INSUFFICIENT


def test_a_veto_does_not_withhold_when_the_evidence_has_already_settled_it() -> None:
    """Overwhelming evidence of two people is `separate`, not `undecidable`.

    The yield rule compared the *positive* support alone and discarded every
    contradiction beside it, so this pair - differing birth date, email, surname and
    address, at -9.184 bits overall - came back `insufficient` because three identifiers
    happened to agree. 1,199 vectors did that.
    """

    overwhelming = {
        K.GIVEN_NAME: Relation.FAR,
        K.DATE_OF_BIRTH: Relation.FAR,
        K.EMAIL: Relation.FAR,
        K.FAMILY_NAME: Relation.FAR,
        K.FULL_ADDRESS: Relation.FAR,
        K.EMPLOYER: Relation.EQUAL,
        K.PHONE: Relation.EQUAL,
        K.SCHOOL_YEAR: Relation.EQUAL,
        K.USERNAME: Relation.EQUAL,
    }

    assert sum(weight_of(kind, r) for kind, r in overwhelming.items()) < -9.0
    assert disposition_of(overwhelming) is PairDisposition.SEPARATE


#: A subset small enough to enumerate in a suite that runs in seconds, chosen to include
#: the veto kind, the other half of the display name, and identifiers either side of it.
#: The full 4^9 enumeration finds nothing this misses and takes minutes.
_ENUMERATED = (
    K.GIVEN_NAME,
    K.FAMILY_NAME,
    K.DATE_OF_BIRTH,
    K.USERNAME,
    K.EMPLOYER,
)
_BETTER = {Relation.FAR: Relation.NEAR, Relation.NEAR: Relation.EQUAL}
_RANK = {
    PairDisposition.SEPARATE: 0,
    PairDisposition.INSUFFICIENT: 1,
    PairDisposition.MERGE: 2,
}


def test_better_evidence_never_gives_a_worse_verdict() -> None:
    """Improving one comparison must never move the answer away from merge.

    It could. `given_name` FAR -> NEAR lifts the veto and moves the pair to the ordinary
    branch, and that turned `insufficient` into `separate` on exactly 3 vectors - the
    evidence got better and the verdict got worse. Two branches with different logic do
    that at the seam between them unless the seam is checked, and only an enumeration
    checks a seam.
    """

    for combination in product(
        (Relation.EQUAL, Relation.NEAR, Relation.FAR, Relation.LOPSIDED),
        repeat=len(_ENUMERATED),
    ):
        vector = dict(zip(_ENUMERATED, combination, strict=True))
        before = disposition_of(vector)
        for kind, relation in vector.items():
            if relation not in _BETTER:
                continue
            after = disposition_of(vector | {kind: _BETTER[relation]})

            assert _RANK[after] >= _RANK[before], (kind.value, vector, before, after)


def test_no_relation_is_worth_exactly_nothing() -> None:
    """`school_year: NEAR` scored 0.000 bits - in the vocabulary, inert in use.

    `LOPSIDED` is excluded because zero is what it means: missingness is not evidence
    either way, which is the one weight in this module nobody argued with.
    """

    for kind in sorted(K):
        for relation in (Relation.EQUAL, Relation.NEAR, Relation.FAR):
            assert weight_of(kind, relation) != 0.0, (kind.value, relation.value)
