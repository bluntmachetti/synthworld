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
#: Interchangeable surface forms. Every one is reachable for every value regardless of
#: relation, which is what stops a form naming its relation.
_DOMAINS = ("example.test", "mail.example.test", "example.invalid")
_TOWNS = ("Testville", "Sampleton", "Exampleford")

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


def _variant(seed: int, purpose: str, slot: int, key: bytes, count: int) -> int:
    """Pick one of `count` interchangeable surface forms for a value.

    Drawn per *value*, never per relation. That distinction is the whole of the fix
    below: if a form belongs to a relation, the relation is written on the value.
    """

    return _draw(seed, f"form:{purpose}", slot, key) % count


def render_relation(
    kind: PublicIdentityAttributeKind,
    relation: Relation,
    *,
    seed: int,
    key: bytes,
    slot: int,
) -> tuple[str, str]:
    """Two safely fictional values standing in the requested relation.

    Both values are drawn from **one** distribution of surface forms. The relation
    decides how they relate to each other and never how either one looks, so no single
    value carries its relation and a reader must compare the pair to learn anything.

    That is not where this started. A first version gave each relation its own surface
    marker - `mail.example.test` only for NEAR, `example.invalid` only for FAR, a
    parenthesised phone only for NEAR, `Sampleton` only for a FAR address, a
    `(Division N)` suffix only for a NEAR employer. Six of eight kinds were affected,
    and a decoder classifying each value *in isolation* recovered the relation on 1200
    of 1200 renderings - then ran the public :func:`disposition_of` to get the answer.
    The key did not help, because nothing was being recomputed: the answer was written
    on the surface. Making the pack a lookup table one level down is exactly the defect
    #62 exists to remove.

    The signature guarantee - no label parameter - was real and insufficient. It stops
    the label flowing in; it cannot stop the *relation* being stamped on the way out,
    and the relation determines the label. What closes it is that every free choice is
    drawn per value from a shared pool: an `example.invalid` address is as likely on a
    merge pair as on a separate one.
    """

    left_seed = _draw(seed, f"{kind.value}:identity", slot, key)
    other_seed = _draw(seed, f"{kind.value}:other", slot, key)
    # The identity component is what NEAR preserves and FAR does not. The form is a
    # free choice drawn independently for each side, so it carries nothing.
    right_seed = left_seed if relation is not Relation.FAR else other_seed
    left_form = _variant(seed, f"{kind.value}:left", slot, key, 3)
    right_form = (
        left_form
        if relation is Relation.EQUAL
        else _variant(seed, f"{kind.value}:right", slot, key, 3)
    )
    if relation is Relation.NEAR and right_form == left_form:
        # NEAR must differ somewhere, or it renders identical to EQUAL.
        right_form = (right_form + 1) % 3
    return (
        _surface(kind, left_seed, left_form),
        _surface(kind, right_seed, right_form),
    )


def _surface(kind: PublicIdentityAttributeKind, identity: int, form: int) -> str:
    """One value, from an identity component and an interchangeable surface form.

    Every form is reachable for every value. Two values sharing an identity and
    differing in form are `NEAR`; sharing both are `EQUAL`; sharing neither are `FAR`.
    A reader holding one value alone sees an identity it cannot place and a form that
    means nothing.
    """

    if kind is _K.PHONE:
        digits = f"{identity % 100 + 100:04d}"
        return (
            f"+1-212-555-{digits}",
            f"+1 (212) 555 {digits}",
            f"001 212 555 {digits}",
        )[form]

    if kind is _K.EMAIL:
        local = f"user{identity % 9000 + 1000:04d}"
        return f"{local}@{_DOMAINS[form]}"

    if kind is _K.USERNAME:
        handle = f"handle{identity % 9000 + 1000:04d}"
        return (handle, f"{handle}_", f"{handle}.")[form]

    if kind is _K.FULL_ADDRESS:
        house, street = identity % 200 + 1, identity % 900 + 100
        town = _TOWNS[form]
        return f"{house}|Example Street {street}|{town}|00000|ZZ"

    if kind is _K.DATE_OF_BIRTH:
        year, month, day = 1950 + identity % 50, identity % 12 + 1, identity % 27 + 1
        return (
            f"{year:04d}-{month:02d}-{day:02d}",
            f"{day:02d}/{month:02d}/{year:04d}",
            f"{year:04d}/{month:02d}/{day:02d}",
        )[form]

    if kind is _K.FAMILY_NAME:
        name = f"Surname{identity % 9000 + 1000:04d}"
        return (name, name.upper(), f"{name}-{name}")[form]

    if kind is _K.EMPLOYER:
        company = f"Example Works {identity % 9000 + 1000:04d}"
        return (company, f"{company} Ltd", f"{company} Limited")[form]

    institution = f"Sample Academy {identity % 900 + 100:03d}"
    year = 1990 + identity % 30
    return (
        f"{institution}|{year}",
        f"{institution.upper()}|{year}",
        f"{institution} |{year}",
    )[form]


__all__ = [
    "AMBIGUITY_GRAMMAR_VERSION",
    "Relation",
    "disposition_of",
    "kind_fingerprint",
    "render_relation",
]
