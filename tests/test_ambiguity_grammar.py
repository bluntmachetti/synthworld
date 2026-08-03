"""What the relation grammar has to prove: the fingerprint stops deciding the answer."""

from __future__ import annotations

import inspect
from collections import defaultdict
from itertools import product

import pytest

from synthworld.ambiguity import PairDisposition
from synthworld.ambiguity_grammar import (
    Relation,
    disposition_of,
    kind_fingerprint,
    render_relation,
)
from synthworld.connection import PublicIdentityAttributeKind as K

#: Every kind the grammar renders. The enumeration test below is combinatorial, so it
#: uses a subset; the rendering tests must cover all of them, or a kind can ship with a
#: near form nobody ever compared against its far form.
_RENDERED = (
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

    Identical at the kind level - phone agrees, email and address differ - and opposite
    in what they justify. v1 could not express the difference, so it asserted the
    answer per scenario, which is precisely what made the pack a lookup table.
    """

    recycled = {
        K.PHONE: Relation.EQUAL,
        K.EMAIL: Relation.FAR,
        K.FULL_ADDRESS: Relation.FAR,
    }
    moved = {
        K.PHONE: Relation.EQUAL,
        K.EMAIL: Relation.NEAR,
        K.FULL_ADDRESS: Relation.NEAR,
    }

    assert kind_fingerprint(recycled) == kind_fingerprint(moved)
    assert disposition_of(recycled) is PairDisposition.SEPARATE
    assert disposition_of(moved) is PairDisposition.MERGE


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

    if kind is K.PHONE:
        first = "".join(item for item in left if item.isdigit())
        second = "".join(item for item in right if item.isdigit())
        return 1.0 if first == second else 0.0

    def tokens(value: str) -> set[str]:
        #  included because usernames use it as a separator, and the near case for a
        # handle is a suffixed variant of the same stem.
        for separator in ("|", "@", "-", " ", "_"):
            value = value.replace(separator, "\x00")
        return {item for item in value.split("\x00") if item}

    one, other = tokens(left), tokens(right)
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
