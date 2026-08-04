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

**Rendering cannot see the label.** :func:`render_relation` takes a kind, a relation,
a seed, a key and a slot. There is no parameter it could read a disposition from, so
the eight metadata channels closed in #59 — ordering, name pools, identifiers, sources,
repetition counts, attribute counts, locality tokens, multiplicity — cannot recur here
by the same route. A type signature enforces that; a test would only sample it.
"""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import blake2b
from math import isfinite, log2
from typing import Literal

from synthworld.ambiguity import PairDisposition
from synthworld.ambiguity_evidence import EvidenceKind, Relation
from synthworld.ambiguity_surfaces import pool_size, surface, variant_count

AMBIGUITY_GRAMMAR_VERSION: Literal["1.0.0"] = "1.0.0"


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
#: One constraint is not negotiable and the first table broke it on four kinds: an exact
#: match must never be worth *less* than a near one. Family name paid +0.63 for byte
#: equality and +1.00 for a near variant, address +0.78 against +1.32, employer +0.87
#: against +1.00, and phone paid exactly the same for both. A resolver reading that
#: table is paid more for a near-miss surname than an exact match, which no amount of
#: population-specific estimation makes defensible. Fixed by raising `u_near` on those
#: four - saying near variants are commoner among non-matches than the first estimate
#: allowed, which is the true statement and the one that restores monotonicity.
#:
#: `u` is estimated over *this pack's* non-match population, which is the part that
#: matters and the part a general-purpose table would get wrong. The negatives here are
#: deliberately households, twins, colleagues and classmates - not strangers drawn at
#: random. Two people in this corpus sharing a surname or an address is unremarkable, so
#: those agreements are weak; a shared birth date is still rare, so it stays strong.
_Params = tuple[tuple[float, float, float], tuple[float, float, float]]

_FS: dict[EvidenceKind, _Params] = {
    EvidenceKind.GIVEN_NAME: ((0.75, 0.20, 0.05), (0.03, 0.07, 0.90)),
    EvidenceKind.FAMILY_NAME: ((0.85, 0.10, 0.05), (0.55, 0.08, 0.37)),
    EvidenceKind.DATE_OF_BIRTH: ((0.93, 0.05, 0.02), (0.06, 0.02, 0.92)),
    EvidenceKind.EMAIL: ((0.70, 0.20, 0.10), (0.15, 0.05, 0.80)),
    EvidenceKind.PHONE: ((0.72, 0.18, 0.10), (0.12, 0.05, 0.83)),
    EvidenceKind.USERNAME: ((0.80, 0.15, 0.05), (0.10, 0.05, 0.85)),
    EvidenceKind.FULL_ADDRESS: ((0.60, 0.25, 0.15), (0.35, 0.18, 0.47)),
    EvidenceKind.EMPLOYER: ((0.55, 0.20, 0.25), (0.30, 0.14, 0.56)),
    EvidenceKind.SCHOOL_YEAR: ((0.75, 0.15, 0.10), (0.25, 0.10, 0.65)),
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


#: Log-odds in bits. Zero is the point of indifference, so a band around it is where the
#: evidence genuinely settles nothing rather than where two thresholds happen to sit.
_MERGE_BITS = 3.0
_SEPARATE_BITS = -3.0

#: How many kinds must agree before a merge is allowed at all.
#:
#: Without this a single field carries a merge on its own: a birth date alone is worth
#: +3.95 and a given name +4.64, both over the threshold, so two records agreeing on a
#: date and nothing else were a merge. That was reachable - 79 of 14,062 generated pairs
#: merged on the display name alone, and two of those 79 were genuinely two people.
#:
#: Raising the threshold instead would have been the wrong instrument: it would weaken
#: every vector rather than the ones with nothing corroborating them. Real resolvers
#: carry a corroboration rule of exactly this shape, because a single agreeing field is
#: a coincidence until something else agrees too.
_MERGE_NEEDS_CORROBORATION = 2

#: How much independent agreement makes a vetoed pair undecidable rather than separate.
#:
#: The veto used to be absolute: a contradicted given name forced `separate` against
#: +15.6 bits, which is every other kind byte-identical - same birth date, email,
#: phone, username, address, employer and school. The twins case justifies overriding
#: family name, birth date, address and school year. It does not justify overriding a
#: shared email *and* phone *and* username, and an expert reading that pair would
#: withhold rather than conclude two people.
_VETO_YIELDS_ABOVE = 8.0


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
    weights = {kind: weight_of(kind, relation) for kind, relation in relations.items()}
    if any(relations.get(kind) is Relation.FAR for kind in _VETO):
        # A veto refuses the merge. Whether it also concludes *separate* depends on how
        # much is arguing the other way: a contradicted given name against a shared
        # email, phone and username is a pair to withhold on, not one to decide.
        supporting = sum(
            weight
            for kind, weight in weights.items()
            if kind not in _VETO and weight > 0
        )
        return (
            PairDisposition.INSUFFICIENT
            if supporting >= _VETO_YIELDS_ABOVE
            else PairDisposition.SEPARATE
        )
    total = sum(weights.values())
    if total >= _MERGE_BITS and sum(1 for w in weights.values() if w > 0) >= (
        _MERGE_NEEDS_CORROBORATION
    ):
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
            # Summing to one is necessary, not sufficient. `(-1.0, 1.0, 1.0)`
            # sums to one and is not a distribution; a first version of this function
            # accepted it while its own docstring and test both said otherwise. A
            # negative mass makes `log2(m/u)` a domain error or a nonsense weight, and a
            # NaN makes every comparison against it false, so `sample_relation`
            # would fall through to the last outcome for that entire kind.
            if len(row) != len(_ORDER):
                raise ValueError(f"{kind.value} needs one probability per outcome")
            if not all(isfinite(mass) and 0.0 < mass <= 1.0 for mass in row):
                # Strictly positive, not merely non-negative. A zero mass passes every
                # other check here and then makes `weight_of` raise - ZeroDivisionError
                # for `u = 0`, a domain error for `m = 0` - while `sample_relation`
                # carries on drawing from the row quite happily. `u_near = 0` is a
                # plausible thing to write for a population where near variants never
                # occur, which is what makes the gap worth closing rather than a
                # theoretical corner.
                raise ValueError(
                    f"{kind.value} outcome probabilities must each be within (0, 1]"
                )
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
    # The purpose string does not mention `same_entity`, so the label never enters the
    # hash material. It reaches the outcome only by choosing which row the point is
    # read against, which is the one channel it is supposed to have. An earlier version
    # keyed the draw on it, which was not exploitable without the key but put the label
    # in the material for no benefit - and every leak this pack has had began as
    # something that was not exploitable yet.
    #
    # Sharing one point across both rows also couples them: the same pair drawn as a
    # match and as a non-match moves through the same quantile, which is the standard
    # common-random-numbers trick and makes the two populations comparable.
    point = (_draw(seed, f"relation:{kind.value}", slot, key) % 10**9) / 10**9
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


def _first_different(candidates: tuple[str, ...], left: str) -> str:
    """The first candidate that is not the value it has to differ from.

    `NEAR` and `FAR` both mean "these two values are not the same string", and the pools
    can collide: `Kate` is reachable from Katherine and from Ekaterina, and a damaged
    variant can land back on the value it was damaged from. A pair whose truth
    says the values differ while the values are identical is a label contradicted by its
    own data, which is the defect this whole module exists to remove.

    Refuses rather than returning a duplicate. Reaching that means the pools have been
    changed so that one identity renders exactly like another under every form, and the
    right response is a loud failure at generation time rather than a quietly
    self-contradicting pack. It is a unit rather than an inline loop so the refusal is
    reachable from a test - the shipped pools never trigger it, and a branch no test can
    reach is one this suite forbids.
    """

    for candidate in candidates:
        if candidate != left:
            return candidate
    raise ValueError(f"every rendering collided with {left!r}")


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

    `NEAR` is the same identity written differently, damaged, or both - `Sørensen`
    against `Soerensen`, `Robert` against `Bob`, `Kowalczyk` against `Kowalcyzk`. The
    damage is lossy on purpose. An earlier version made every form a *reversible*
    re-encoding of an index (`Surname1042`, `user1042@…`), so stripping the form and
    comparing indices recovered every relation exactly and a thirty-line parser scored
    1.0000 on held-out-key packs. Nothing leaked - the parser read only evidence - but
    the only skill the pack measured was writing a regex. That was #80.

    `FAR` is a different identity, drawn to be a plausible neighbour rather than an
    obvious stranger: another house on the same street, another surname from the
    lookalike pool, a date whose day and month could be read either way. So `NEAR` and
    `FAR` overlap, which is the point - telling them apart is a judgement about
    similarity, not an equality test, and a resolver that is always right about it is
    not being asked anything.
    """

    if relation is Relation.LOPSIDED:
        # An absence is not a comparison, so there is no pair of values to render. The
        # old behaviour was to treat it as "not FAR" and return two values that stood in
        # no stated relation at all. Use `render_value`.
        raise ValueError("LOPSIDED is an absence, not a comparison: use render_value")

    size, forms = pool_size(kind), variant_count(kind)
    identity = _draw(seed, f"{kind.value}:identity", slot, key) % size
    variant = _draw(seed, f"{kind.value}:left", slot, key) % forms
    left = surface(kind, identity, variant, 0)
    if relation is Relation.EQUAL:
        return (left, left)

    if relation is Relation.NEAR:
        # A different way of writing the same identity, damaged about half the time. It
        # must differ from the left value or NEAR renders as EQUAL, and the retry walks
        # the variants rather than redrawing, so it terminates.
        damage = _draw(seed, f"{kind.value}:damage", slot, key) % 6
        return (
            left,
            _first_different(
                tuple(
                    surface(kind, identity, variant + step, damage)
                    for step in range(1, forms)
                ),
                left,
            ),
        )

    # FAR steps to a different identity rather than drawing a second one independently,
    # because two independent draws collided and rendered a pair whose truth said the
    # values differed while the values were identical.
    step_by = 1 + _draw(seed, f"{kind.value}:other", slot, key) % (size - 1)
    other = (identity + step_by) % size
    return (
        left,
        _first_different(
            tuple(surface(kind, other, variant + step, 0) for step in range(forms)),
            left,
        ),
    )


def render_value(kind: EvidenceKind, *, seed: int, key: bytes, slot: int) -> str:
    """One value for a kind only one record carries.

    Drawn from exactly the same identity and form pools as either half of a rendered
    pair, so a one-sided value is not distinguishable from a two-sided one. Anything
    else would make "the other record lacks this" readable from the value itself, and
    which fields a record happens to carry would start carrying something.
    """

    return surface(
        kind,
        _draw(seed, f"{kind.value}:identity", slot, key) % pool_size(kind),
        _draw(seed, f"{kind.value}:left", slot, key) % variant_count(kind),
        0,
    )


__all__ = [
    "AMBIGUITY_GRAMMAR_VERSION",
    "EvidenceKind",
    "Relation",
    "disposition_of",
    "kind_fingerprint",
    "render_relation",
    "render_value",
    "sample_relation",
    "validate_parameters",
    "weight_of",
]
