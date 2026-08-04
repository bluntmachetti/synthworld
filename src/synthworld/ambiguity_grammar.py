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

from collections.abc import Mapping
from enum import StrEnum
from hashlib import blake2b
from math import log2
from typing import Literal

from synthworld.ambiguity import PairDisposition

AMBIGUITY_GRAMMAR_VERSION: Literal["1.0.0"] = "1.0.0"


class EvidenceKind(StrEnum):
    """What a pair can be compared on.

    Not `PublicIdentityAttributeKind`. That enum is v1's *storage*, and it has no given
    name, because v1 keeps given names inside a display string. A rule keyed on it
    therefore cannot see the only thing distinguishing twins from one person: the
    canonical twins pair agrees on family name, birth date, address and school year, and
    differs on nothing else a v1 attribute records. The first version of this module
    scored it +0.97 and called it a merge.
    """

    GIVEN_NAME = "given_name"
    FAMILY_NAME = "family_name"
    DATE_OF_BIRTH = "date_of_birth"
    EMAIL = "email"
    PHONE = "phone"
    USERNAME = "username"
    FULL_ADDRESS = "full_address"
    EMPLOYER = "employer"
    SCHOOL_YEAR = "school_year"


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


#: Fellegi-Sunter parameters per kind: `(m, u)`, each `(equal, near, far)`.
#:
#: `m` is the probability of an outcome given the two records are one person; `u` the
#: probability given they are not. The weight of an outcome is `log2(m / u)` - positive
#: when it is likelier under one person, negative when likelier under two.
#:
#: A first version used one number per kind and forced disagreement to be the exact
#: negative of agreement. Real linkage is not symmetric: the ONS worked example gives a
#: surname `+7.11 / -1.66` and a birth date `+6.01 / -6.06`. People change email
#: providers and move house, so those disagreements are weak evidence; almost nobody
#: changes their birth date, so that disagreement is strong. One number cannot say both,
#: and the old table made a differing email the strongest negative in the system while
#: its own comment said such a difference "says almost nothing".
#:
#: `u` is estimated over *this pack's* non-match population, which is the part that
#: matters and the part a general-purpose table would get wrong. The negatives here are
#: deliberately households, twins, colleagues and classmates - not strangers drawn at
#: random. Two people in this corpus sharing a surname or an address is unremarkable, so
#: those agreements are weak; a shared birth date is still rare, so it stays strong.
_Params = tuple[tuple[float, float, float], tuple[float, float, float]]

_FS: dict[EvidenceKind, _Params] = {
    EvidenceKind.GIVEN_NAME: ((0.75, 0.20, 0.05), (0.03, 0.07, 0.90)),
    EvidenceKind.FAMILY_NAME: ((0.85, 0.10, 0.05), (0.55, 0.05, 0.40)),
    EvidenceKind.DATE_OF_BIRTH: ((0.93, 0.05, 0.02), (0.06, 0.02, 0.92)),
    EvidenceKind.EMAIL: ((0.70, 0.20, 0.10), (0.15, 0.05, 0.80)),
    EvidenceKind.PHONE: ((0.72, 0.18, 0.10), (0.12, 0.03, 0.85)),
    EvidenceKind.USERNAME: ((0.80, 0.15, 0.05), (0.10, 0.05, 0.85)),
    EvidenceKind.FULL_ADDRESS: ((0.60, 0.25, 0.15), (0.35, 0.10, 0.55)),
    EvidenceKind.EMPLOYER: ((0.55, 0.20, 0.25), (0.30, 0.10, 0.60)),
    EvidenceKind.SCHOOL_YEAR: ((0.75, 0.15, 0.10), (0.25, 0.15, 0.60)),
}

#: Evidence whose contradiction refuses a merge however much else agrees.
#:
#: An additive score cannot express this. Making one field outweigh the sum of four
#: others needs a weight so large it distorts every vector the field appears in, and
#: real resolvers carry rules of exactly this shape instead. Twins are the case: they
#: agree on family name, birth date, address and school year, and the given name is all
#: that says they are two people.
#:
#: Deliberately only the given name. A differing birth date does *not* veto, because the
#: canonical `partial_with_contradiction` case has one and is `insufficient` rather than
#: `separate` - a contradiction there is reason to withhold judgement, not to conclude.
_VETO: frozenset[EvidenceKind] = frozenset({EvidenceKind.GIVEN_NAME})

_ORDER = (Relation.EQUAL, Relation.NEAR, Relation.FAR)
_INDEX = {relation: index for index, relation in enumerate(_ORDER)}

#: Interchangeable surface forms. Every one is reachable for every value regardless of
#: relation, which is what stops a form naming its relation.
_DOMAINS = ("example.test", "mail.example.test", "example.invalid")
_GIVEN = (
    "Ada",
    "Bilal",
    "Chen",
    "Dara",
    "Esme",
    "Faisal",
    "Gita",
    "Hugo",
    "Imani",
    "Jonas",
    "Keira",
    "Luis",
    "Mina",
    "Noor",
    "Orla",
    "Pavel",
)
_TOWNS = ("Testville", "Sampleton", "Exampleford")

#: Log-odds in bits. Zero is the point of indifference, so a band around it is where the
#: evidence genuinely settles nothing rather than where two thresholds happen to sit.
_MERGE_BITS = 3.0
_SEPARATE_BITS = -3.0


def weight_of(kind: EvidenceKind, relation: Relation) -> float:
    """The log-odds contribution of one outcome, in bits.

    `LOPSIDED` contributes nothing: one record carrying an attribute the other lacks is
    missingness, not disagreement, and scoring it as either would punish sparse records
    for being sparse. That is the standard treatment and it is the one number in this
    module a reviewer signed off without argument.
    """

    if relation is Relation.LOPSIDED:
        return 0.0
    m, u = _FS[kind]
    return log2(m[_INDEX[relation]] / u[_INDEX[relation]])


def disposition_of(relations: Mapping[EvidenceKind, Relation]) -> PairDisposition:
    """What the public evidence justifies, read off the evidence and nothing else.

    Takes no scenario, no archetype and no `same_entity`. There is no argument it could
    read a label from, which is what stops the disposition being a lookup on the case.
    """

    if not relations:
        return PairDisposition.INSUFFICIENT
    if any(relations.get(kind) is Relation.FAR for kind in _VETO):
        return PairDisposition.SEPARATE
    total = sum(weight_of(kind, relation) for kind, relation in relations.items())
    if total >= _MERGE_BITS:
        return PairDisposition.MERGE
    if total <= _SEPARATE_BITS:
        return PairDisposition.SEPARATE
    return PairDisposition.INSUFFICIENT


def validate_parameters(table: Mapping[EvidenceKind, _Params]) -> None:
    """Refuse a table whose rows are not distributions.

    `m` and `u` are probabilities over the three outcomes, so each row must sum to one.
    A row that does not is not a distribution: :func:`sample_relation` would quietly
    draw a skewed corpus from it while :func:`weight_of` went on reporting weights as
    though nothing were wrong, and the pack and its scoring rule would disagree with no
    symptom anywhere. Checked at import for the shipped table, and callable so a
    population-specific table can be checked too.
    """

    for kind, rows in table.items():
        for row in rows:
            if abs(sum(row) - 1.0) > 1e-9:
                raise ValueError(f"{kind.value} outcome probabilities must sum to one")


validate_parameters(_FS)


def sample_relation(
    kind: EvidenceKind,
    *,
    same_entity: bool,
    seed: int,
    slot: int,
    key: bytes,
) -> Relation:
    """Draw one comparison outcome from what being the same person implies.

    This is :func:`weight_of` run backwards, off the same table. `m` is by definition
    the probability of an outcome given one person and `u` given two, so sampling from
    them generates a corpus the scoring rule is *already* correct about - the generator
    and the scorer cannot drift, because there is only one set of numbers.

    That is what replaces hand-authoring. A hand-written case has an identity, and any
    feature identifying the case identifies its label; a pair drawn from a distribution
    has no identity to leak. `same_entity` reaches a value only through the relation it
    induces, which is exactly the dependency the task is to invert.
    """

    m, u = _FS[kind]
    row = m if same_entity else u
    # 1e-9 of resolution over the outcome space, from a keyed draw. Comparing against
    # cumulative mass rather than bucketing an integer, so the three outcomes get their
    # stated probabilities and not a rounding of them.
    point = (
        _draw(seed, f"relation:{kind.value}:{same_entity}", slot, key) % 10**9
    ) / 10**9
    # The last outcome is the fallthrough rather than a case, so there is no branch
    # here that a valid table can never reach - the suite gates on full branch coverage
    # and forbids pragmas, and an unreachable arm would have to be one or the other.
    # It also removes any dependence on the row summing to exactly 1.0 in floating
    # point, which `validate_parameters` only guarantees to within 1e-9.
    running = 0.0
    for outcome, mass in zip(_ORDER[:-1], row[:-1], strict=True):
        running += mass
        if point < running:
            return outcome
    return _ORDER[-1]


def kind_fingerprint(
    relations: Mapping[EvidenceKind, Relation],
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
    kind: EvidenceKind,
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

    space = _SPACE[kind]
    left_seed = _draw(seed, f"{kind.value}:identity", slot, key) % space
    # The identity component is what NEAR preserves and FAR does not. The form is a
    # free choice drawn independently for each side, so it carries nothing.
    #
    # FAR steps to a *different* index rather than drawing a second one. Drawing
    # independently let the two collide, and `_surface` maps an index to one value, so
    # a collision rendered a FAR pair as two identical strings - a pair whose truth
    # says "these differ" and whose data says they are the same. Measured at 61 in 3000
    # for given names, 10 for phones and 3 for addresses. That is the defect this whole
    # module exists to remove, arriving through the renderer instead of through a
    # scenario table, and no amount of care about labels would have caught it.
    right_seed = (
        left_seed
        if relation is not Relation.FAR
        else (
            left_seed + 1 + _draw(seed, f"{kind.value}:other", slot, key) % (space - 1)
        )
        % space
    )
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


#: How many distinct values each kind can render. `_surface` must be injective over
#: `range(_SPACE[kind])`, because `render_relation` relies on two different indices
#: producing two different strings to make FAR mean what it says.
_SPACE: dict[EvidenceKind, int] = {
    EvidenceKind.GIVEN_NAME: 16,
    EvidenceKind.FAMILY_NAME: 9000,
    EvidenceKind.DATE_OF_BIRTH: 50 * 12 * 27,
    EvidenceKind.EMAIL: 9000,
    EvidenceKind.PHONE: 9000,
    EvidenceKind.USERNAME: 9000,
    EvidenceKind.FULL_ADDRESS: 200 * 900,
    EvidenceKind.EMPLOYER: 9000,
    EvidenceKind.SCHOOL_YEAR: 900 * 30,
}


def _surface(kind: EvidenceKind, identity: int, form: int) -> str:
    """One value, from an identity component and an interchangeable surface form.

    Every form is reachable for every value. Two values sharing an identity and
    differing in form are `NEAR`; sharing both are `EQUAL`; sharing neither are `FAR`.
    A reader holding one value alone sees an identity it cannot place and a form that
    means nothing.
    """

    if kind is EvidenceKind.GIVEN_NAME:
        given = _GIVEN[identity]
        return (given, given.upper(), f"{given[0]}.")[form]

    if kind is EvidenceKind.PHONE:
        digits = f"{identity + 1000:04d}"
        return (
            f"+1-212-555-{digits}",
            f"+1 (212) 555 {digits}",
            f"001 212 555 {digits}",
        )[form]

    if kind is EvidenceKind.EMAIL:
        local = f"user{identity + 1000:04d}"
        return f"{local}@{_DOMAINS[form]}"

    if kind is EvidenceKind.USERNAME:
        handle = f"handle{identity + 1000:04d}"
        return (handle, f"{handle}_", f"{handle}.")[form]

    if kind is EvidenceKind.FULL_ADDRESS:
        house, street = identity % 200 + 1, identity // 200 + 100
        town = _TOWNS[form]
        return f"{house}|Example Street {street}|{town}|00000|ZZ"

    if kind is EvidenceKind.DATE_OF_BIRTH:
        year = 1950 + identity // (12 * 27)
        month, day = identity // 27 % 12 + 1, identity % 27 + 1
        return (
            f"{year:04d}-{month:02d}-{day:02d}",
            f"{day:02d}/{month:02d}/{year:04d}",
            f"{year:04d}/{month:02d}/{day:02d}",
        )[form]

    if kind is EvidenceKind.FAMILY_NAME:
        name = f"Surname{identity + 1000:04d}"
        return (name, name.upper(), f"{name}-{name}")[form]

    if kind is EvidenceKind.EMPLOYER:
        company = f"Example Works {identity + 1000:04d}"
        return (company, f"{company} Ltd", f"{company} Limited")[form]

    institution = f"Sample Academy {identity % 900 + 100:03d}"
    year = 1990 + identity // 900
    return (
        f"{institution}|{year}",
        f"{institution.upper()}|{year}",
        f"{institution} |{year}",
    )[form]


__all__ = [
    "AMBIGUITY_GRAMMAR_VERSION",
    "EvidenceKind",
    "Relation",
    "disposition_of",
    "kind_fingerprint",
    "render_relation",
    "sample_relation",
    "validate_parameters",
    "weight_of",
]
