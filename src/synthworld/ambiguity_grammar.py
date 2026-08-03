"""Evidence relations for the ambiguity pack, and the rule that reads them.

Issue #62 exists because the v1 pack is a lookup table. Each scenario is *defined* by
which attribute kinds it carries and which of them agree, every pack contains all
fifteen exactly once, and ``SCENARIO_DISPOSITIONS`` maps each to one answer. So the
kind-level fingerprint determines the disposition on 750 of 750 pairs, and a held-out
seed changes surface values without changing a single label.

The fix is not more hashing. It is that **two pairs with the same kind-level fingerprint
must be able to carry different answers**, which requires saying something the v1
vocabulary cannot say.

Today a pair of values either matches or does not. That is why "recycled phone" and
"moved house but kept the number" are indistinguishable at the kind level *and* have to
be given different dispositions by fiat: both are `phone` agreeing while `email` and
`address` differ. The missing word is :attr:`Relation.NEAR` — values that differ but
show continuity, a house number changing on one street, an email local-part surviving a
change of provider. With it, the two cases have the same fingerprint and different
evidence, and a resolver has to read the values.

Two design rules carry the module.

**The label is derived, never sampled alongside the evidence.** :func:`disposition_of`
takes a relation vector and nothing else. ``same_entity`` is a fact about the world and
is sampled; ``disposition`` means *what the public evidence justifies*, so computing it
from the evidence is what the word means rather than a compromise. It also keeps
per-pair truth exactly checkable, so the disposition scorer needs no change.

**Rendering cannot see the label.** :func:`render_relation` takes a kind, a relation, a
seed and a key. There is no parameter it could read a disposition from, so the eight
metadata channels closed in #59 — ordering, name pools, identifiers, source types,
repetition counts, attribute counts, locality tokens, multiplicity — cannot recur here
by the same route. A type signature enforces that; a test would only sample it.
"""

from __future__ import annotations

from enum import StrEnum
from hashlib import blake2b
from typing import Literal

from synthworld.ambiguity import PairDisposition
from synthworld.connection import PublicIdentityAttributeKind

AMBIGUITY_GRAMMAR_VERSION: Literal["1.0.0"] = "1.0.0"

_K = PublicIdentityAttributeKind


class Relation(StrEnum):
    """How one attribute relates across the two records of a pair."""

    #: Byte-identical. Strong evidence of one entity for a rarely-shared kind, and
    #: nearly none for a kind households share.
    EQUAL = "equal"
    #: Different values that show continuity - one street with another house number, a
    #: local-part surviving a change of provider. The word v1 could not say, and the
    #: reason two cases can share a fingerprint and differ in what they justify.
    NEAR = "near"
    #: Different, with nothing connecting them.
    FAR = "far"
    #: Present on one record only. Not evidence either way; its absence is the point.
    LOPSIDED = "lopsided"


#: How much one kind agreeing is worth, and how readily unrelated people share it.
#:
#: `weight` is evidence toward one entity when the kind agrees. `shareability` is how
#: often unrelated people legitimately share it: a household email is shared far more
#: readily than a national identifier, so its agreement says less. Both are declared
#: here, reviewed, and used by one rule - rather than each scenario asserting its own
#: answer, which is what made v1 a table.
_KIND_EVIDENCE: dict[PublicIdentityAttributeKind, tuple[float, float]] = {
    _K.PHONE: (0.65, 0.35),
    _K.EMAIL: (0.70, 0.30),
    _K.USERNAME: (0.55, 0.40),
    _K.FULL_ADDRESS: (0.55, 0.45),
    _K.DATE_OF_BIRTH: (0.45, 0.25),
    _K.FAMILY_NAME: (0.30, 0.55),
    _K.EMPLOYER: (0.35, 0.50),
    _K.SCHOOL_YEAR: (0.35, 0.45),
}

#: Above this the evidence justifies merging; below the negative of it, separating;
#: between them it justifies neither and `insufficient` is the honest answer.
#:
#: Deliberately wide. A narrow band would make `insufficient` a rounding artefact of two
#: thresholds rather than a real region, and the whole point of the third disposition is
#: that some evidence genuinely settles nothing.
_MERGE_THRESHOLD = 0.55
_SEPARATE_THRESHOLD = -0.35


def _contribution(kind: PublicIdentityAttributeKind, relation: Relation) -> float:
    """What one kind in one relation contributes toward merging.

    Positive pulls toward one entity, negative toward two. `NEAR` is deliberately
    positive but weaker than `EQUAL`: continuity is real evidence, and weaker than
    identity. `FAR` is negative in proportion to how *rarely* the kind is shared —
    two people differing on a household email says almost nothing, differing on a
    national identifier says a great deal.
    """

    weight, shareability = _KIND_EVIDENCE[kind]
    if relation is Relation.EQUAL:
        return weight * (1.0 - shareability)
    if relation is Relation.NEAR:
        return weight * (1.0 - shareability) * 0.6
    if relation is Relation.FAR:
        return -weight * (1.0 - shareability)
    return 0.0


def disposition_of(
    relations: dict[PublicIdentityAttributeKind, Relation],
) -> PairDisposition:
    """What the public evidence justifies, read off the evidence and nothing else.

    Takes no scenario, no archetype name and no `same_entity`. There is no argument it
    could read a label from, which is the property that stops the disposition being a
    lookup on the case — and the reason two pairs with the same attribute kinds can
    come out differently when their *values* relate differently.
    """

    if not relations:
        return PairDisposition.INSUFFICIENT
    total = sum(_contribution(kind, relation) for kind, relation in relations.items())
    if total >= _MERGE_THRESHOLD:
        return PairDisposition.MERGE
    if total <= _SEPARATE_THRESHOLD:
        return PairDisposition.SEPARATE
    return PairDisposition.INSUFFICIENT


def kind_fingerprint(
    relations: dict[PublicIdentityAttributeKind, Relation],
) -> tuple[tuple[str, bool], ...]:
    """What a kind-level decoder sees: which kinds, and whether each agrees.

    This is exactly the view that determined the answer on 750 of 750 v1 pairs. It
    cannot tell `NEAR` from `FAR` — both are "these differ" — so two realizations that
    differ only in that are one fingerprint here and two dispositions in truth. Kept in
    the module it constrains, so the claim can be measured rather than argued.
    """

    return tuple(
        sorted(
            (kind.value, relation is Relation.EQUAL)
            for kind, relation in relations.items()
            if relation is not Relation.LOPSIDED
        )
    )


def _draw(seed: int, purpose: str, index: int, key: bytes) -> int:
    material = "".join(
        f"{len(part)}:{part}" for part in (str(seed), purpose, str(index))
    )
    return int.from_bytes(
        blake2b(material.encode(), digest_size=8, key=key).digest(), "big"
    )


def render_relation(
    kind: PublicIdentityAttributeKind,
    relation: Relation,
    *,
    seed: int,
    key: bytes,
    slot: int,
) -> tuple[str, str]:
    """Two safely fictional values standing in the requested relation.

    The signature is the guarantee: there is no disposition, no archetype and no
    ``same_entity`` parameter, so no surface value can be a function of the answer.
    Every leak closed in #59 reached a public value through exactly that route.
    """

    left = _draw(seed, f"{kind.value}:left", slot, key)
    right = _draw(seed, f"{kind.value}:right", slot, key)

    if kind is _K.PHONE:
        subscriber = left % 100 + 100
        first = f"+1-212-555-{subscriber:04d}"
        if relation is Relation.EQUAL:
            return first, first
        # The same line written differently - the messy-data case a resolver has to
        # normalise before it can match. A first revision used consecutive subscriber
        # numbers, which reads as continuity and is not: `0115` and `0116` share no
        # token, exactly as `0115` and `0256` do, so nothing distinguished it from FAR
        # to any comparison a real matcher would make.
        if relation is Relation.NEAR:
            return first, f"+1 (212) 555 {subscriber:04d}"
        return first, f"+1-212-555-{right % 100 + 200:04d}"

    if kind is _K.EMAIL:
        stem = f"stem{left % 9000 + 1000:04d}"
        first = f"{stem}@example.test"
        if relation is Relation.EQUAL:
            return first, first
        # The local part survives a change of provider - the same person, reachable
        # somewhere else - against an unrelated address entirely.
        return first, (
            f"{stem}@mail.example.test"
            if relation is Relation.NEAR
            else f"other{right % 9000 + 1000:04d}@example.invalid"
        )

    if kind is _K.FULL_ADDRESS:
        street = f"Example Street {left % 900 + 100:03d}"
        first = f"{left % 200 + 1}|{street}|Testville|00000|ZZ"
        if relation is Relation.EQUAL:
            return first, first
        # One street, another door, against another town entirely.
        return first, (
            f"{left % 200 + 2}|{street}|Testville|00000|ZZ"
            if relation is Relation.NEAR
            else f"{right % 200 + 1}|Example Street {right % 900 + 100:03d}|"
            "Sampleton|00000|ZZ"
        )

    if kind is _K.USERNAME:
        stem = f"handle{left % 9000 + 1000:04d}"
        if relation is Relation.EQUAL:
            return stem, stem
        return stem, (
            f"{stem}_{left % 90 + 10:02d}"
            if relation is Relation.NEAR
            else f"handle{right % 9000 + 1000:04d}"
        )

    if kind is _K.DATE_OF_BIRTH:
        year, month, day = 1950 + left % 50, left % 12 + 1, left % 27 + 1
        first = f"{year:04d}-{month:02d}-{day:02d}"
        if relation is Relation.EQUAL:
            return first, first
        # A transposed pair of digits in the day is the classic keying error; a
        # different year entirely is a different person.
        return first, (
            f"{year:04d}-{month:02d}-{(day % 27) + 1:02d}"
            if relation is Relation.NEAR
            else f"{1950 + right % 50:04d}-{right % 12 + 1:02d}-{right % 27 + 1:02d}"
        )

    if kind is _K.FAMILY_NAME:
        first = f"Surname{left % 9000 + 1000:04d}"
        if relation is Relation.EQUAL:
            return first, first
        # A maiden name kept as a compound, against an unrelated surname.
        return first, (
            f"{first}-Surname{left % 90 + 10:02d}"
            if relation is Relation.NEAR
            else f"Surname{right % 9000 + 1000:04d}"
        )

    if kind is _K.EMPLOYER:
        first = f"Example Works {left % 9000 + 1000:04d}"
        if relation is Relation.EQUAL:
            return first, first
        # The same employer under a renamed division, against a different company.
        return first, (
            f"{first} (Division {left % 9 + 1})"
            if relation is Relation.NEAR
            else f"Test Logistics {right % 9000 + 1000:04d}"
        )

    institution = f"Sample Academy {left % 900 + 100:03d}"
    year = 1990 + left % 30
    first = f"{institution}|{year}"
    if relation is Relation.EQUAL:
        return first, first
    # One institution, adjacent cohorts - siblings, or a repeated year.
    return first, (
        f"{institution}|{year + 1}"
        if relation is Relation.NEAR
        else f"Test College {right % 900 + 100:03d}|{1990 + right % 30}"
    )


__all__ = [
    "AMBIGUITY_GRAMMAR_VERSION",
    "Relation",
    "disposition_of",
    "kind_fingerprint",
    "render_relation",
]
