"""Build a v2 ambiguity pack by sampling truth and reading the answer off the evidence.

The v1 generator walks a fixed list of fifteen drafts. Every leak closed in #59 and #66
was a free choice in that walk quietly bound to which draft was being written - the
order pairs were emitted, the UUIDs, the provenance strings, the number of sources, the
shape of the letter case. There was no principle saying which choices were free, so each
one had to be found, and one of them was only findable by recomputing the generator from
a public seed rather than by looking at the data at all.

Here there is no list. For each pair the generator samples whether the two records are
one person, draws each comparison from the distribution that fact implies, and derives
the disposition. Everything else - source type, confidence, how many attributes a record
carries, which records are asked about - is drawn from a purpose string that does not
mention `same_entity` or the disposition, so there is nothing for a free choice to be
bound to.

What a held-out seed conceals is the key, and therefore the *values*. It does not
conceal the rule: :func:`disposition_of` is published, and a solver that recovers the
relations from the rendered values and applies it should score perfectly. That is the
intended difficulty. The task is reading `Sørensen` against `Sorensen`, a phone written
three ways, and an initial against a full name - not guessing a hidden mapping.
"""

from __future__ import annotations

from uuid import UUID

from synthworld.ambiguity import PairDisposition
from synthworld.ambiguity_grammar import (
    EvidenceKind,
    Relation,
    _draw,
    disposition_of,
    render_relation,
    sample_relation,
)
from synthworld.ambiguity_v2 import (
    DerivedPairTruth,
    PublicAmbiguityTaskV2,
    public_pairs_from_derived,
)
from synthworld.connection import (
    PublicConnectionCorpus,
    PublicIdentityAttribute,
    PublicIdentityAttributeKind,
    PublicIdentityRecord,
    PublicIdentitySourceType,
)

#: Kinds that live in `display_name` rather than in an attribute. v1 has no given-name
#: attribute and adding one would change the v1 corpus, which must stay byte-identical.
_IN_NAME = (EvidenceKind.GIVEN_NAME, EvidenceKind.FAMILY_NAME)

_SOURCES = tuple(PublicIdentitySourceType)

#: How much of each pack is genuinely the same person. Varying this per seed is the
#: point: a fixed prevalence lets a solver score well by guessing the majority class,
#: and v1's was fixed at five merges in fifteen for every seed ever generated.
_PREVALENCE = (0.25, 0.70)

#: Pairs per pack, and distractor records beyond those the pairs need. Both vary per
#: seed so neither count is a constant a consumer can hard-code against.
#: How much of the evidence vocabulary a given pair can be compared on, as a range
#: drawn from per pair. The low end is what produces genuinely undecidable pairs.
_COMPLETENESS = (0.05, 0.85)

_PAIRS = (18, 44)
_DISTRACTORS = (8, 30)


def _between(
    seed: int, purpose: str, index: int, key: bytes, low: int, high: int
) -> int:
    return low + _draw(seed, purpose, index, key) % (high - low + 1)


def _fraction(seed: int, purpose: str, index: int, key: bytes) -> float:
    return (_draw(seed, purpose, index, key) % 10**9) / 10**9


def _comparable(seed: int, slot: int, key: bytes) -> tuple[EvidenceKind, ...]:
    """Which kinds this pair can be compared on at all.

    Drawn without reference to `same_entity`, so sparseness is not a tell.

    How complete a pair is varies per pair rather than being fixed. That is what makes
    `insufficient` a real third class instead of a label with nothing in it: at a fixed
    high density almost every pair accumulates enough weight to clear a threshold, and a
    first version of this generator produced 0, 0, 1 and 0 insufficient pairs across
    four seeds. Sparseness is also the honest cause - a broker dossier carrying eight
    fields and a conference badge carrying two are the same corpus, and two records that
    overlap on almost nothing genuinely do not settle the question.
    """

    low, high = _COMPLETENESS
    density = low + _fraction(seed, "completeness", slot, key) * (high - low)
    optional = tuple(
        kind
        for kind in sorted(EvidenceKind)
        if kind not in _IN_NAME
        and _fraction(seed, f"present:{kind.value}", slot, key) < density
    )
    # A record with no attributes cannot exist - `PublicIdentityRecord` requires at
    # least one - and the two name kinds live in `display_name` rather than in an
    # attribute, so a pair comparable only on names would build a corpus record with an
    # empty attribute list. Falling back to the most commonly recorded identifier keeps
    # that impossible without making sparseness itself readable: email is present on
    # most records anyway, so forcing it changes what a sparse pair looks like far less
    # than a shorter attribute list would.
    return (*_IN_NAME, *(optional or (EvidenceKind.EMAIL,)))


def _carried(
    seed: int, slot: int, key: bytes, kinds: tuple[EvidenceKind, ...], side: int
) -> tuple[EvidenceKind, ...]:
    """Which of a pair's comparable kinds this side actually records.

    Drawn per side, so the two records in a pair carry different fields - which is the
    ordinary situation and the one v1's vocabulary has a word for. Without this,
    `LOPSIDED` is unreachable: every pair produced EQUAL, NEAR or FAR and both sides
    carried the same fields in all 626 pairs across twenty seeds. A quarter of the
    relation vocabulary being unreachable is not a small gap - one record holding a
    phone the other lacks is the most common thing in record linkage, and a pack that
    cannot express it is not exercising the missingness rule at all.

    The names are exempt: every record has a display name, so a given or family name is
    never one-sided. That is a property of the corpus format, not a modelling choice.
    """

    carried = tuple(
        kind
        for kind in kinds
        if kind in _IN_NAME
        or _fraction(seed, f"carries:{kind.value}:{side}", slot, key) < 0.82
    )
    # Every record needs at least one attribute, and the names are not attributes. The
    # fallback has to come from `kinds` rather than being a fixed kind: a constant would
    # name something this pair may not be comparable on at all, and the record would be
    # built with an attribute the other side has no counterpart for by construction.
    if len(carried) > len(_IN_NAME):
        return carried
    spare = next(kind for kind in kinds if kind not in _IN_NAME)
    return (*carried, spare)


def _record_id(seed: int, slot: int, side: int, key: bytes) -> UUID:
    return UUID(int=_draw(seed, f"record:{side}", slot, key) % (1 << 128), version=4)


def _pair(
    seed: int, slot: int, key: bytes
) -> tuple[DerivedPairTruth, PublicIdentityRecord, PublicIdentityRecord]:
    """One pair: sample the truth, draw the evidence, read the answer, render it."""

    low, high = _PREVALENCE
    prevalence = low + _fraction(seed, "prevalence", 0, key) * (high - low)
    # Drawn once per pack and compared per pair, so the *rate* varies between packs
    # while each pair stays an independent draw. A prevalence fixed across seeds - v1's
    # was five merges in fifteen, every time - is a free win for guessing the majority.
    same_entity = _fraction(seed, "same-entity", slot, key) < prevalence
    comparable = _comparable(seed, slot, key)
    carried = tuple(_carried(seed, slot, key, comparable, side) for side in (0, 1))
    both = [kind for kind in comparable if all(kind in item for item in carried)]
    # A kind only one side records is `LOPSIDED`: missingness, not disagreement. It is
    # worth zero bits, so a sparse record is not punished for being sparse.
    relations = {
        kind: sample_relation(
            kind, same_entity=same_entity, seed=seed, slot=slot, key=key
        )
        if kind in both
        else Relation.LOPSIDED
        for kind in comparable
        if any(kind in item for item in carried)
    }
    rendered = {
        kind: render_relation(kind, relation, seed=seed, key=key, slot=slot)
        for kind, relation in relations.items()
    }
    # Sorted, and not checked for collision here: `DerivedPairTruth` already refuses
    # equal ids, so a second check would be an unreachable branch in a suite that
    # gates on full branch coverage and forbids pragmas.
    ids = sorted(_record_id(seed, slot, side, key) for side in (0, 1))
    records = tuple(
        _record(seed, slot, side, key, ids[side], rendered, carried[side])
        for side in (0, 1)
    )
    truth = DerivedPairTruth(
        left_record_id=ids[0],
        right_record_id=ids[1],
        same_entity=same_entity,
        relations=relations,
        # Read off the evidence, never chosen. The model refuses any other value, so
        # this line is a derivation rather than a claim the pack has to be trusted on.
        disposition=disposition_of(relations),
    )
    return truth, records[0], records[1]


def _record(
    seed: int,
    slot: int,
    side: int,
    key: bytes,
    record_id: UUID,
    rendered: dict[EvidenceKind, tuple[str, str]],
    carried: tuple[EvidenceKind, ...],
) -> PublicIdentityRecord:
    """One side of a pair, dressed in metadata drawn independently of the answer.

    `source_type`, `source_url` and `confidence` were all leak channels in v1 - the
    provenance string named the case, the source count tracked the disposition. None of
    the purpose strings here mention `same_entity` or the disposition, which is the
    property that makes them free rather than the absence of a test looking for it.
    """

    attributes = tuple(
        PublicIdentityAttribute(
            kind=PublicIdentityAttributeKind(kind.value),
            value=rendered[kind][side],
            confidence=0.55
            + _fraction(seed, f"conf:{kind.value}:{side}", slot, key) * 0.4,
        )
        for kind in sorted(rendered)
        if kind not in _IN_NAME and kind in carried
    )
    # Indexed, not `.get` with a default: `_comparable` always returns both name kinds,
    # so a default would be a branch that never runs and a claim that is never true.
    given, family = (rendered[kind][side] for kind in _IN_NAME)
    source = _SOURCES[_draw(seed, f"source:{side}", slot, key) % len(_SOURCES)]
    return PublicIdentityRecord(
        id=record_id,
        source_type=source,
        source_url=f"https://{source.value}.example.test/{record_id}",
        display_name=f"{given} {family}",
        confidence=0.6 + _fraction(seed, f"record-conf:{side}", slot, key) * 0.35,
        attributes=attributes,
    )


def _distractor(seed: int, index: int, key: bytes) -> PublicIdentityRecord:
    """A record no pair asks about, drawn from the same machinery as a real one.

    Built by rendering a relation vector that is then thrown away, so a distractor is
    indistinguishable from half of a pair. Anything cheaper - a shorter attribute list,
    a fixed source - would make "is this a distractor" readable, and a solver that can
    tell which records are asked about learns the pair list without being given it.
    """

    slot = 10**6 + index
    relations = {
        kind: sample_relation(
            kind,
            same_entity=_fraction(seed, "distractor-entity", slot, key) < 0.5,
            seed=seed,
            slot=slot,
            key=key,
        )
        for kind in _comparable(seed, slot, key)
    }
    rendered = {
        kind: render_relation(kind, relation, seed=seed, key=key, slot=slot)
        for kind, relation in relations.items()
    }
    return _record(
        seed,
        slot,
        0,
        key,
        _record_id(seed, slot, 0, key),
        rendered,
        _carried(seed, slot, key, tuple(relations), 0),
    )


def generate_ambiguity_v2_pack(
    *, seed: int, key: bytes
) -> tuple[PublicAmbiguityTaskV2, tuple[DerivedPairTruth, ...]]:
    """A public task and the truth behind it.

    Returned as a pair rather than one object so the public half can be serialized
    without the truth being one attribute access away. The key is required and has no
    default: a partially keyed generator is worse than an unkeyed one, because it reads
    as protected while four call sites quietly fall back to `b""`.
    """

    count = _between(seed, "pair-count", 0, key, *_PAIRS)
    built = [_pair(seed, slot, key) for slot in range(count)]
    truths = tuple(item[0] for item in built)
    records = [record for item in built for record in item[1:]]
    records.extend(
        _distractor(seed, index, key)
        for index in range(_between(seed, "distractors", 0, key, *_DISTRACTORS))
    )
    task = PublicAmbiguityTaskV2(
        corpus=PublicConnectionCorpus(
            seed=seed,
            # Sorted by id, so corpus position carries the id and nothing else. In v1
            # the emission order was the draft order, and the draft order was the
            # answer key.
            identity_records=tuple(sorted(records, key=lambda item: item.id)),
            association_records=(),
        ),
        pairs_to_decide=public_pairs_from_derived(truths),
    )
    return task, truths


def prevalence_of(truths: tuple[DerivedPairTruth, ...]) -> float:
    """Fraction of pairs that really are one person. For tests and for reporting."""

    return sum(item.same_entity for item in truths) / len(truths)


def disposition_counts(
    truths: tuple[DerivedPairTruth, ...],
) -> dict[PairDisposition, int]:
    return {
        disposition: sum(item.disposition is disposition for item in truths)
        for disposition in PairDisposition
    }


__all__ = [
    "disposition_counts",
    "generate_ambiguity_v2_pack",
    "prevalence_of",
]
