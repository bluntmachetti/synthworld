"""What the relation grammar has to prove: the fingerprint stops deciding the answer."""

from __future__ import annotations

import inspect
from collections import Counter, defaultdict
from itertools import product
from unicodedata import normalize

import pytest

from synthworld.ambiguity import (
    SCENARIO_DISPOSITIONS,
    PairDisposition,
    ScenarioKind,
)
from synthworld.ambiguity_generator import _drafts
from synthworld.ambiguity_grammar import (
    _FS,
    _SPACE,
    Relation,
    _surface,
    disposition_of,
    kind_fingerprint,
    render_relation,
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
    for seed in range(150):
        for kind in _RENDERED:
            for relation in relations:
                for value in render_relation(
                    kind, relation, seed=seed, key=b"secret", slot=0
                ):
                    learned[(kind, shape(value))][relation] += 1

    correct = total = 0
    for seed in range(150, 250):
        for kind in _RENDERED:
            for relation in relations:
                for value in render_relation(
                    kind, relation, seed=seed, key=b"secret", slot=0
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
    reading the case or its label. `render_relation` has no parameter it could read
    either from, and this test pins that rather than trusting a reviewer to notice a
    later argument being added.
    """

    parameters = set(inspect.signature(render_relation).parameters)

    assert parameters == {"kind", "relation", "seed", "key", "slot"}
    assert not parameters & {"disposition", "scenario", "same_entity", "archetype"}


@pytest.mark.parametrize("kind", _RENDERED)
@pytest.mark.parametrize("relation", (Relation.EQUAL, Relation.NEAR, Relation.FAR))
def test_rendered_values_stand_in_the_relation_they_claim(
    kind: K, relation: Relation
) -> None:
    left, right = render_relation(kind, relation, seed=7, key=b"", slot=0)

    assert left and right
    if relation is Relation.EQUAL:
        assert left == right
    else:
        assert left != right


def _similarity(kind: K, left: str, right: str) -> float:
    """How alike two values look to a competent resolver, per kind.

    Two earlier versions of this were wrong in instructive ways. A shared *prefix* is
    the wrong tool for structured values - an address is
    `house|street|town|postcode|country`, so a near pair differing only in house number
    shares no prefix while agreeing on everything that matters. Raw *token overlap* is
    the wrong tool for phone numbers, where the near case is one line written two ways
    and reformatting changes more tokens than changing the number does.

    So the comparison normalises the way a matcher would before comparing - digits for
    phone numbers, which is what `_attribute_collision_key` in `ambiguity_variants`
    already does. That is a real preprocessing step, not a thumb on the scale: if a
    relation is only visible after normalisation nobody performs, it is decoration.
    """

    if kind is K.GIVEN_NAME:
        # `A.` against `Ada` is the fourth time this comparison, not the rendering, was
        # the thing at fault. An initial is a real near form - records store them
        # constantly - and every resolver has an initial rule, so a comparison without
        # one calls a genuine near pair far.
        def initial(value: str) -> str:
            return value.casefold()[:1]

        if len(left.rstrip(".")) == 1 or len(right.rstrip(".")) == 1:
            return 1.0 if initial(left) == initial(right) else 0.0

    if kind is K.PHONE:

        def digits(value: str) -> str:
            # `00` is the international dialling prefix and `+` means the same thing,
            # so a normaliser that does not fold them reports the same line as two.
            # Standard E.164 handling; the surface forms deliberately include both.
            found = "".join(item for item in value if item.isdigit())
            return found[2:] if found.startswith("00") else found

        return 1.0 if digits(left) == digits(right) else 0.0

    def tokens(value: str) -> set[str]:
        # Every separator these surface forms use. They were added one at a time, each
        # because a near pair scored as far without it - and each time the rendering was
        # right and this comparison was wrong.
        for separator in ("|", "@", "-", " ", "_", "/", "."):
            value = value.replace(separator, "\x00")
        return {item for item in value.split("\x00") if item}

    one, other = tokens(left.casefold()), tokens(right.casefold())
    union = one | other
    return len(one & other) / len(union) if union else 0.0


def test_near_is_visibly_nearer_than_far() -> None:
    """Otherwise the distinction is a label rather than something a resolver can read.

    Measured with a token comparison a real matcher would plausibly use. If continuity
    is invisible to that, it is invisible to a system under test and the relation is
    decoration.
    """

    for kind in _RENDERED:
        left, near = render_relation(kind, Relation.NEAR, seed=11, key=b"", slot=0)
        also_left, far = render_relation(kind, Relation.FAR, seed=11, key=b"", slot=0)

        assert left == also_left
        assert _similarity(kind, left, near) > _similarity(kind, left, far), kind.value


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
#: birth date and differing on nothing else recorded. v1 calls that `separate` because
#: it planted two people; the evidence says merge, and any honest resolver would say
#: merge too. The disagreement is with the *scenario*, not with the rule: the pair
#: carries no evidence of being two people, so the label is unearned.
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


def test_the_derived_rule_reproduces_the_hand_written_answers() -> None:
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
    """A kind whose FAR outscored its EQUAL would be evidence read backwards."""

    assert weight_of(kind, Relation.EQUAL) > weight_of(kind, Relation.FAR)
    assert weight_of(kind, Relation.EQUAL) > 0.0
    assert weight_of(kind, Relation.FAR) < 0.0
    assert weight_of(kind, Relation.LOPSIDED) == 0.0


@pytest.mark.parametrize("kind", sorted(K))
def test_a_surface_names_exactly_one_value(kind: K) -> None:
    """`FAR` means "these differ", so two indices must not render the same string.

    They did. `_surface` reduced a 64-bit draw with `% 16` for given names and `% 100`
    for phones, and `FAR` drew its second index independently, so the two collided and
    the pair rendered identical values under a truth that said they differed. 61 in 3000
    given-name pairs, 10 phones, 3 addresses. A label contradicted by its own data is
    the defect this module exists to remove, and it arrived through the renderer rather
    than through a scenario table.
    """

    rendered = {_surface(kind, index, 0) for index in range(_SPACE[kind])}

    assert len(rendered) == _SPACE[kind]


@pytest.mark.parametrize("kind", sorted(K))
def test_far_never_renders_two_equal_values(kind: K) -> None:
    for seed in range(400):
        left, right = render_relation(kind, Relation.FAR, seed=seed, key=b"k", slot=0)
        assert left != right, (kind.value, seed)


def test_a_row_that_is_not_a_distribution_is_refused() -> None:
    """Otherwise the generator and the scorer disagree with no symptom anywhere.

    `sample_relation` would draw from a skewed row while `weight_of` scored as though
    it were a distribution, so the pack would be systematically mislabelled by a rule
    that looked correct.
    """

    validate_parameters(_FS)  # the shipped table is one

    with pytest.raises(ValueError, match="must sum to one"):
        validate_parameters({K.PHONE: ((0.5, 0.2, 0.2), (0.1, 0.1, 0.8))})


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
