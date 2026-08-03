"""Deterministic, semantically validated variants of the ambiguity pack.

Issue #41 requires surface and structural variation without changing what a case
means.  A variant therefore has three explicit stages:

* build a corpus-wide injective substitution plan, so source equality and
  inequality survive rewriting;
* construct the seed-selected realization for the scenarios that permit one;
* validate the emitted public evidence independently of the copied truth labels.

The canonical frozen pack is never modified.  Variant-realization metadata is a
separate evaluator-only model rather than an extension of the frozen 1.0.0 public
or answer-key schemas.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import blake2b
from typing import Literal
from unicodedata import normalize

from synthworld.ambiguity import (
    SCENARIO_DISPOSITIONS,
    AmbiguityAnswerKey,
    AmbiguityBenchmark,
    PairTruth,
    PublicAmbiguityTask,
    ScenarioKind,
    public_pairs_from_truth,
)
from synthworld.ambiguity_generator import _Draft, _drafts, _record_key
from synthworld.connection import (
    PublicConnectionCorpus,
    PublicIdentityAttribute,
    PublicIdentityAttributeKind,
    PublicIdentityRecord,
    PublicIdentitySourceType,
    RecordMembership,
)
from synthworld.connection_generator import _identity_record
from synthworld.models import SyntheticModel

_K = PublicIdentityAttributeKind

#: Scenarios whose defining attributes are part of the case itself.  In
#: particular, a Unicode case with one possible family-name realization is fixed;
#: a one-option list is not structural variation.
FIXED_REALIZATION = frozenset(
    {
        ScenarioKind.RECYCLED_PHONE,
        ScenarioKind.SHARED_HOUSEHOLD_EMAIL,
        ScenarioKind.REUSED_USERNAME,
        ScenarioKind.SHARED_EMPLOYER_AND_ADDRESS,
        ScenarioKind.SAME_NAME_AND_DATE_OF_BIRTH,
        ScenarioKind.TWINS_OVERLAPPING_CONTEXT,
        ScenarioKind.ALIAS_CHANGE,
        ScenarioKind.UNICODE_VARIANT,
        ScenarioKind.DUPLICATE_OBSERVATION,
        ScenarioKind.SPARSE_RECORDS,
    }
)

#: Scenarios that genuinely permit more than one carrying attribute.
REALIZATIONS: dict[ScenarioKind, tuple[PublicIdentityAttributeKind, ...]] = {
    ScenarioKind.CONTRADICTORY_STRONG_IDENTIFIERS: (_K.EMAIL, _K.PHONE),
    ScenarioKind.STALE_ATTRIBUTE: (_K.PHONE, _K.FULL_ADDRESS),
    ScenarioKind.PARTIAL_BUT_SUFFICIENT: (_K.DATE_OF_BIRTH, _K.SCHOOL_YEAR),
    ScenarioKind.SINGLE_UNCORROBORATED_ATTRIBUTE: (_K.EMPLOYER, _K.SCHOOL_YEAR),
    ScenarioKind.PARTIAL_WITH_CONTRADICTION: (_K.DATE_OF_BIRTH, _K.SCHOOL_YEAR),
}

_SAME_ENTITY_SCENARIOS = frozenset(
    {
        ScenarioKind.STALE_ATTRIBUTE,
        ScenarioKind.ALIAS_CHANGE,
        ScenarioKind.UNICODE_VARIANT,
        ScenarioKind.PARTIAL_BUT_SUFFICIENT,
        ScenarioKind.DUPLICATE_OBSERVATION,
        ScenarioKind.SINGLE_UNCORROBORATED_ATTRIBUTE,
        ScenarioKind.SPARSE_RECORDS,
    }
)

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
    "Quinn",
    "Rina",
    "Sami",
    "Talia",
    "Uma",
    "Viktor",
    "Wren",
    "Xenia",
    "Yusuf",
    "Zara",
    "Amara",
    "Bruno",
    "Celine",
    "Dario",
)
_FAMILY = (
    "Aldridge",
    "Barros",
    "Chevalier",
    "Delgado",
    "Eriksen",
    "Fontaine",
    "Ghaly",
    "Haddad",
    "Ibarra",
    "Jansen",
    "Kestrel",
    "Laurent",
    "Moreno",
    "Novak",
    "Okafor",
    "Pereira",
    "Quill",
    "Raman",
    "Silva",
    "Tanaka",
    "Underwood",
    "Valen",
    "Whitaker",
    "Xu",
    "Yarrow",
    "Zoric",
    "Bellamy",
    "Corwin",
    "Deneuve",
    "Farrow",
)
_DOMAINS = ("example.test", "example.invalid", "mail.example.test")
_UNICODE_NAMES = (
    ("Zoë", "Zoe", "Dvořák", "Dvorak"),
    ("André", "Andre", "García", "Garcia"),
    ("Élodie", "Elodie", "Müller", "Muller"),
    ("François", "Francois", "Brontë", "Bronte"),
    ("Šimon", "Simon", "Núñez", "Nunez"),
)
_VIRTUAL_PREFIX = "\x00realization:"
_DisplayRelation = Literal[
    "alias", "distinct", "equal", "initial_full", "same_family", "unicode"
]


class ScenarioRealization(SyntheticModel):
    """One evaluator-only declaration of the attribute selected for a case."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    scenario: ScenarioKind
    attribute_kind: PublicIdentityAttributeKind


class AmbiguityVariantMetadata(SyntheticModel):
    """Evaluator-only realization metadata stored separately from public input."""

    schema_version: Literal["1.0.0"] = "1.0.0"
    seed: int
    selected_realizations: tuple[ScenarioRealization, ...]


class AmbiguityVariantError(ValueError):
    """Raised when a variant no longer exhibits the scenario it declares."""


@dataclass(frozen=True)
class _ScenarioSpec:
    #: Kinds carried by *both* records.
    kinds: frozenset[PublicIdentityAttributeKind]
    shared: frozenset[PublicIdentityAttributeKind]
    different: frozenset[PublicIdentityAttributeKind]
    display_relation: _DisplayRelation
    #: Kinds carried by exactly one of the two records. Empty for every case whose
    #: records are equally rich, and the whole point of `partial_but_sufficient`.
    lopsided: frozenset[PublicIdentityAttributeKind] = frozenset()


@dataclass(frozen=True)
class _CaseShape:
    """A case's relational shape, in terms that survive a realization choice.

    Read off the hand-authored canonical drafts and compared against what a variant
    actually emits. Deliberately coarse: it says whether the two records agree
    anywhere, contradict anywhere, and how lopsided they are - not which attribute
    kinds carry those relations, because choosing a different carrying kind is the
    legitimate variation and must not fail.

    Orientation-free. Variant pairs are ordered by record id, so which record ends up
    on the left is arbitrary; ``lopsided`` is therefore sorted rather than sided.
    """

    agrees: bool
    contradicts: bool
    lopsided: tuple[int, int]
    #: How many kinds agree and contradict, counted rather than merely detected.
    #: Only meaningful where the realization is fixed, so it is ``None`` for the five
    #: cases that choose a carrying attribute per seed - there the counts move for
    #: legitimate reasons. Without it the shape was coarse enough that reducing
    #: `duplicate_observation` from three shared attributes to one still validated.
    counts: tuple[int, int] | None


def canonical_source_agreement() -> dict[ScenarioKind, bool]:
    """Whether each case's two records share a provenance, per the canonical drafts.

    Nothing checked this before, so every record could be relabelled `directory` and
    the pack still validated - which is why the source types could drift into being
    pure label metadata without anything noticing.
    """

    drafts = _drafts()
    return {
        drafts[index].scenario: drafts[index].source_type
        is drafts[index + 1].source_type
        for index in range(0, len(drafts), 2)
    }


def _case_shape(
    left: Mapping[_K, str], right: Mapping[_K, str], *, exact: bool
) -> _CaseShape:
    common = left.keys() & right.keys()
    agreeing = sum(1 for kind in common if left[kind] == right[kind])
    return _CaseShape(
        agrees=agreeing > 0,
        contradicts=agreeing < len(common),
        lopsided=tuple(  # type: ignore[arg-type]
            sorted((len(left.keys() - right.keys()), len(right.keys() - left.keys())))
        ),
        counts=(agreeing, len(common) - agreeing) if exact else None,
    )


def canonical_case_shapes() -> dict[ScenarioKind, _CaseShape]:
    """What each case looks like in the frozen pack, as a shape a variant must keep.

    The point is that this reads a *different source* from the one the generator
    writes from. `_scenario_spec` and `_realize_attributes` are the same switch
    stated twice, so validating one against the other proves only that the switch
    agrees with itself: when the `partial_but_sufficient` realization was changed to
    hand both records the same attribute, `_scenario_spec` was changed to declare no
    differing attribute, and the check passed on all 100 seeds while the case had
    stopped being partial. The canonical drafts are hand-authored and reviewed, so
    they are the normative statement of what a case means.
    """

    drafts = _drafts()
    shapes: dict[ScenarioKind, _CaseShape] = {}
    for index in range(0, len(drafts), 2):
        left, right = drafts[index], drafts[index + 1]
        shapes[left.scenario] = _case_shape(
            {item.kind: item.value for item in left.attributes},
            {item.kind: item.value for item in right.attributes},
            exact=left.scenario not in REALIZATIONS,
        )
    return shapes


def _draw(seed: int, purpose: str, index: int, key: bytes = b"") -> int:
    """A keyed pseudorandom draw. The key is never serialized.

    Without a key this generator is invertible, and that is not a hypothetical. The
    seed is published in `PublicConnectionCorpus.seed`, the canonical values live in
    `_drafts()` in this public source, and `_substitution_plan` orders each kind's
    values by `_draw(seed, f"value-order:{kind}:{value}", 0)`. So the whole
    canonical-to-surface map is recomputable by anyone holding the repository: brute
    force the 32 realization combinations, keep the plan whose outputs appear in the
    corpus, invert it, and read each record's canonical value - which names its draft,
    which names its scenario. Measured over seeds 900-929, that recovers the
    disposition on **0.974** of pairs against a 0.467 majority baseline, reading no
    identity evidence at all.

    No hash makes that go away. Any deterministic public function of a public seed and
    a public value set inverts; three comments in this module already say so about
    permutations, and the same argument applies here. What closes it is a secret, so a
    pack generated with an unpublished key cannot be recomputed.

    `key=b""` is byte-identical to unkeyed blake2b, so the published packs - whose
    answer keys ship in this repository anyway, and which claim no secret - are
    unchanged and remain auditable.

    Material is length-prefixed rather than delimited because 22 canonical values
    contain the `|` separator, including every address, so a delimited encoding was
    collision-free only by luck.
    """

    parts = (str(seed), purpose, str(index))
    material = "".join(f"{len(item)}:{item}" for item in parts)
    return int.from_bytes(
        blake2b(material.encode(), digest_size=8, key=key).digest(), "big"
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AmbiguityVariantError(message)


def ambiguity_variant_metadata(
    *, seed: int, key: bytes = b""
) -> AmbiguityVariantMetadata:
    """Return the deterministic evaluator-only realization choices for ``seed``."""

    selected = tuple(
        ScenarioRealization(
            scenario=scenario,
            attribute_kind=choices[
                _draw(seed, f"realization:{scenario.value}", 0, key) % len(choices)
            ],
        )
        for scenario, choices in sorted(
            REALIZATIONS.items(), key=lambda item: item[0].value
        )
    )
    return AmbiguityVariantMetadata(seed=seed, selected_realizations=selected)


def _selected(metadata: AmbiguityVariantMetadata) -> dict[ScenarioKind, _K]:
    selected = {
        item.scenario: item.attribute_kind for item in metadata.selected_realizations
    }
    _require(
        len(selected) == len(metadata.selected_realizations),
        "variant metadata contains a duplicate scenario realization",
    )
    _require(
        set(selected) == set(REALIZATIONS),
        "variant metadata does not cover every variable scenario exactly once",
    )
    for scenario, kind in selected.items():
        _require(
            kind in REALIZATIONS[scenario],
            f"{scenario.value} does not support realization {kind.value}",
        )
    return selected


def _draft_anchor(drafts: Sequence[_Draft], scenario: ScenarioKind) -> str:
    """A pair's identity, taken from its hand-authored evidence rather than its name.

    Realized values are reserved in the substitution plan under a placeholder key.
    That key used to be the scenario's own name, which made every realized value a
    deterministic function of the label: with the public seed and this source, all
    five variable scenarios were recoverable, 500 of 500 across seeds 0-99. Worse, it
    fed forward - those values are what :func:`_evidence_anchor` ranks, so the label
    reached the display slots and the record identifiers that were supposed to have
    been cleaned of it.

    Anchoring on the canonical evidence keeps the placeholder unique per case while
    depending only on what the case contains.
    """

    pair = [item for item in drafts if item.scenario is scenario]
    body = "|".join(
        sorted(
            f"{item.kind.value}={item.value}"
            for draft in pair
            for item in draft.attributes
        )
    )
    return blake2b(body.encode(), digest_size=16).hexdigest()


def _virtual_key(anchor: str, role: str) -> str:
    return f"{_VIRTUAL_PREFIX}{anchor}:{role}"


def _virtual_requirements(
    selected: Mapping[ScenarioKind, _K],
    anchors: Mapping[ScenarioKind, str],
) -> tuple[tuple[_K, str], ...]:
    keys: list[tuple[_K, str]] = []
    for scenario, kind in selected.items():
        anchor = anchors[scenario]
        if scenario in {
            ScenarioKind.CONTRADICTORY_STRONG_IDENTIFIERS,
            ScenarioKind.STALE_ATTRIBUTE,
        }:
            keys.extend(
                (
                    (kind, _virtual_key(anchor, "left")),
                    (kind, _virtual_key(anchor, "right")),
                )
            )
        elif scenario is ScenarioKind.PARTIAL_BUT_SUFFICIENT:
            # One role, not two: only the richer record carries this attribute.
            keys.append((kind, _virtual_key(anchor, "richer")))
        elif scenario is ScenarioKind.SINGLE_UNCORROBORATED_ATTRIBUTE:
            keys.append((kind, _virtual_key(anchor, "shared")))
        else:
            other = next(item for item in REALIZATIONS[scenario] if item is not kind)
            keys.extend(
                (
                    (kind, _virtual_key(anchor, "left")),
                    (kind, _virtual_key(anchor, "right")),
                    (other, _virtual_key(anchor, "corroborating")),
                )
            )
    return tuple(keys)


def _substituted(value: str, kind: str, seed: int, slot: int, key: bytes = b"") -> str:
    """Format the collision-free slot assigned to one distinct source value.

    ``slot`` is the corpus-wide rank of the source value within its attribute kind,
    never a record position.  Equal source values use one plan entry; distinct
    values receive distinct slots.
    """

    offset = _draw(seed, f"surface:{kind}", 0, key)
    if kind == _K.EMAIL.value:
        return (
            f"synthetic.{offset % 10000:04d}.{slot:04d}"
            f"@{_DOMAINS[(offset + slot) % len(_DOMAINS)]}"
        )
    if kind == _K.PHONE.value:
        _require(slot < 100, "the fictional 555-01xx phone pool is exhausted")
        return f"+1-212-555-{slot + 100:04d}"
    if kind == _K.USERNAME.value:
        return f"synthetic_{offset % 10000:04d}_{slot:04d}"
    if kind == _K.FAMILY_NAME.value:
        return f"FictionalSurname{offset % 10000:04d}{slot:04d}"
    if kind == _K.FULL_ADDRESS.value:
        return f"{slot + 1}|Example Avenue {offset % 1000:03d}|Testville|00000|ZZ"
    if kind == _K.EMPLOYER.value:
        family = _FAMILY[(offset + slot) % len(_FAMILY)]
        # The offset is spelled out, as it is for emails and usernames. Carrying it
        # only through the family choice left about 30 distinct strings per slot, so
        # two seeds landed on the same institution name often enough to matter: over
        # 200 seeds, 27 anchors recurred in a different seed, which lets an attacker
        # carry a memorised evidence-to-label mapping between seeds.
        return f"Example {family} Works {offset % 10000:04d}-{slot + 1}"
    if kind == _K.SCHOOL_YEAR.value:
        family = _FAMILY[(offset + slot) % len(_FAMILY)]
        return (
            f"Test {family} Academy {offset % 10000:04d}-{slot + 1}|{1990 + slot % 30}"
        )
    if kind == _K.DATE_OF_BIRTH.value:
        day_index = offset % (60 * 12 * 27) + slot
        return (
            f"{1960 + day_index // (12 * 27)}-"
            f"{day_index // 27 % 12 + 1:02d}-{day_index % 27 + 1:02d}"
        )
    return value


def _substitution_plan(
    drafts: Sequence[_Draft], metadata: AmbiguityVariantMetadata, key: bytes = b""
) -> dict[tuple[_K, str], str]:
    selected = _selected(metadata)
    keys = {(item.kind, item.value) for draft in drafts for item in draft.attributes}
    anchors = {scenario: _draft_anchor(drafts, scenario) for scenario in ScenarioKind}
    keys.update(_virtual_requirements(selected, anchors))
    grouped: dict[_K, set[str]] = defaultdict(set)
    for kind, value in keys:
        grouped[kind].add(value)

    result: dict[tuple[_K, str], str] = {}
    for kind, values in grouped.items():
        ordered = sorted(
            values,
            key=lambda value: (
                _draw(metadata.seed, f"value-order:{kind.value}:{value}", 0, key),
                value,
            ),
        )
        rewritten = [
            _substituted(value, kind.value, metadata.seed, slot, key)
            for slot, value in enumerate(ordered)
        ]
        _require(
            len(rewritten) == len(set(rewritten)),
            f"{kind.value} substitution is not injective",
        )
        result.update(
            ((kind, value), replacement)
            for value, replacement in zip(ordered, rewritten, strict=True)
        )
    return result


def _attribute(kind: _K, value: str) -> PublicIdentityAttribute:
    return PublicIdentityAttribute(kind=kind, value=value, confidence=1.0)


def _rewritten_attributes(
    draft: _Draft, substitutions: Mapping[tuple[_K, str], str]
) -> tuple[PublicIdentityAttribute, ...]:
    return tuple(
        PublicIdentityAttribute(
            kind=item.kind,
            value=substitutions[(item.kind, item.value)],
            confidence=item.confidence,
        )
        for item in draft.attributes
    )


def _realize_attributes(
    scenario: ScenarioKind,
    anchor: str,
    left: tuple[PublicIdentityAttribute, ...],
    right: tuple[PublicIdentityAttribute, ...],
    selected: Mapping[ScenarioKind, _K],
    substitutions: Mapping[tuple[_K, str], str],
) -> tuple[tuple[PublicIdentityAttribute, ...], tuple[PublicIdentityAttribute, ...]]:
    if scenario not in REALIZATIONS:
        return left, right

    chosen = selected[scenario]
    choices = frozenset(REALIZATIONS[scenario])
    left_kept = tuple(item for item in left if item.kind not in choices)
    right_kept = tuple(item for item in right if item.kind not in choices)

    def value(kind: _K, role: str) -> str:
        return substitutions[(kind, _virtual_key(anchor, role))]

    if scenario in {
        ScenarioKind.CONTRADICTORY_STRONG_IDENTIFIERS,
        ScenarioKind.STALE_ATTRIBUTE,
    }:
        return (
            (*left_kept, _attribute(chosen, value(chosen, "left"))),
            (*right_kept, _attribute(chosen, value(chosen, "right"))),
        )
    if scenario is ScenarioKind.PARTIAL_BUT_SUFFICIENT:
        # One record is strictly poorer than the other, matching the canonical case.
        # The canonical comment reads "neither record is sufficient alone; together
        # they are", which overstates it: under a strict subset the richer record
        # already equals the union, so what this actually tests is merging by
        # subsumption - recognising that a sparse record is the same person as a
        # fuller one, without a contradiction to lean on.
        #
        # An earlier revision handed the same attribute to both records, which made
        # the pair attribute-identical in all 100 seeds: a duplicate observation
        # wearing a partial-record label.
        return left_kept, (*right_kept, _attribute(chosen, value(chosen, "richer")))
    if scenario is ScenarioKind.SINGLE_UNCORROBORATED_ATTRIBUTE:
        shared = _attribute(chosen, value(chosen, "shared"))
        return (*left_kept, shared), (*right_kept, shared)

    other = next(item for item in REALIZATIONS[scenario] if item is not chosen)
    corroborating = _attribute(other, value(other, "corroborating"))
    return (
        (
            *left_kept,
            corroborating,
            _attribute(chosen, value(chosen, "left")),
        ),
        (
            *right_kept,
            corroborating,
            _attribute(chosen, value(chosen, "right")),
        ),
    )


def _unicode_name(seed: int) -> tuple[str, str, str, str]:
    return _UNICODE_NAMES[_draw(seed, "unicode-name", 0) % len(_UNICODE_NAMES)]


def _replace_family(
    attributes: tuple[PublicIdentityAttribute, ...], family: str
) -> tuple[PublicIdentityAttribute, ...]:
    return tuple(
        _attribute(_K.FAMILY_NAME, family) if item.kind is _K.FAMILY_NAME else item
        for item in attributes
    )


def _family_value(attributes: Sequence[PublicIdentityAttribute], fallback: str) -> str:
    return next(
        (item.value for item in attributes if item.kind is _K.FAMILY_NAME), fallback
    )


def _evidence_anchor(
    left: tuple[PublicIdentityAttribute, ...],
    right: tuple[PublicIdentityAttribute, ...],
) -> str:
    """Identify a pair by the evidence it carries, independently of side."""

    return "|".join(
        sorted(f"{item.kind.value}={item.value}" for item in (*left, *right))
    )


def _source_types(
    seed: int, anchor: str, left: _Draft, right: _Draft
) -> tuple[PublicIdentitySourceType, PublicIdentitySourceType]:
    """Choose provenance per seed, preserving only whether the two sources agree.

    Source types were copied verbatim from the drafts, so they were constant per
    scenario on every seed: a decoder trained on one seed and using nothing but each
    pair's unordered source-type signature scored 1200 of 1500 on a hundred others,
    against a 7/15 baseline.

    Whether two records come from one source or two is part of the case - a syndicated
    observation needs two, twins found in one alumni directory need one - so that
    relation is preserved and validated against the canonical drafts. *Which* source
    is a free choice, and free choices must not be bound to the label.
    """

    kinds = tuple(PublicIdentitySourceType)
    first = kinds[_draw(seed, f"source:{anchor}", 0) % len(kinds)]
    if left.source_type is right.source_type:
        return first, first
    others = tuple(item for item in kinds if item is not first)
    return first, others[_draw(seed, f"source:{anchor}", 1) % len(others)]


def _display_slots(
    seed: int, anchors: Mapping[ScenarioKind, str]
) -> dict[ScenarioKind, int]:
    """Give each pair a disjoint name slot, ranked by its own evidence.

    The slot used to be ``_SCENARIO_INDEX[scenario]``, which put the answer in the
    public display name: ``len(_GIVEN) == 30 == 2 * len(ScenarioKind)`` made the given
    name a bijection onto (scenario, side), and the fallback family name spelled the
    ordinal in decimal as ``ExampleNNFamilyNN``. One regex recovered every scenario -
    and therefore every disposition, through the public ``SCENARIO_DISPOSITIONS`` map -
    on 750 of 750 pairs across fifty seeds.

    A seed-keyed *permutation* of the ordinal does not fix that. The seed is in the
    public artifact and this source is public, so the permutation inverts exactly;
    three independent reviewers each recovered 750/750 against that proposal.

    What fixes it is dropping the label from the derivation. The slot is now a keyed
    rank over the pair's own evidence, the same collision-free scheme
    :func:`_substitution_plan` uses for attribute values. A name therefore tells a
    reader only what the evidence already told them, and no decoder survives to the
    next seed, because the anchors are themselves seed-substituted.
    """

    _require(
        len(set(anchors.values())) == len(anchors),
        "two scenarios carry identical evidence, so name slots would be ordinal",
    )
    ordered = sorted(
        anchors.items(),
        key=lambda item: (_draw(seed, f"display-slot:{item[1]}", 0), item[1]),
    )
    return {scenario: slot for slot, (scenario, _anchor) in enumerate(ordered)}


def _display_names(
    *,
    seed: int,
    scenario: ScenarioKind,
    slot: int,
    left: tuple[PublicIdentityAttribute, ...],
    right: tuple[PublicIdentityAttribute, ...],
) -> tuple[str, str]:
    given_offset = _draw(seed, "display-given", 0) % len(_GIVEN)
    family_offset = _draw(seed, "display-family", 0) % len(_FAMILY)
    left_given = _GIVEN[(given_offset + slot * 2) % len(_GIVEN)]
    right_given = _GIVEN[(given_offset + slot * 2 + 1) % len(_GIVEN)]
    left_family = _family_value(left, f"Example{family_offset:02d}Family{slot * 2:02d}")
    right_family = _family_value(
        right, f"Example{family_offset:02d}Family{slot * 2 + 1:02d}"
    )

    if scenario in {
        ScenarioKind.SAME_NAME_AND_DATE_OF_BIRTH,
        ScenarioKind.CONTRADICTORY_STRONG_IDENTIFIERS,
        ScenarioKind.STALE_ATTRIBUTE,
        ScenarioKind.DUPLICATE_OBSERVATION,
        ScenarioKind.PARTIAL_WITH_CONTRADICTION,
    }:
        name = f"{left_given} {left_family}"
        return name, name
    if scenario in {
        ScenarioKind.SHARED_HOUSEHOLD_EMAIL,
        ScenarioKind.TWINS_OVERLAPPING_CONTEXT,
    }:
        return f"{left_given} {left_family}", f"{right_given} {left_family}"
    if scenario is ScenarioKind.ALIAS_CHANGE:
        return f"{left_given} {left_family}", f"{left_given} {right_family}"
    if scenario is ScenarioKind.UNICODE_VARIANT:
        unicode_given, ascii_given, unicode_family, ascii_family = _unicode_name(seed)
        return f"{unicode_given} {unicode_family}", f"{ascii_given} {ascii_family}"
    if scenario in {
        ScenarioKind.PARTIAL_BUT_SUFFICIENT,
        ScenarioKind.SINGLE_UNCORROBORATED_ATTRIBUTE,
        ScenarioKind.SPARSE_RECORDS,
    }:
        return f"{right_given[0]}. {left_family}", f"{right_given} {left_family}"
    return f"{left_given} {left_family}", f"{right_given} {right_family}"


def _scenario_spec(
    scenario: ScenarioKind, selected: Mapping[ScenarioKind, _K]
) -> _ScenarioSpec:
    fixed: dict[ScenarioKind, _ScenarioSpec] = {
        ScenarioKind.RECYCLED_PHONE: _ScenarioSpec(
            frozenset({_K.PHONE, _K.EMAIL, _K.FULL_ADDRESS}),
            frozenset({_K.PHONE}),
            frozenset({_K.EMAIL, _K.FULL_ADDRESS}),
            "distinct",
        ),
        ScenarioKind.SHARED_HOUSEHOLD_EMAIL: _ScenarioSpec(
            frozenset({_K.EMAIL, _K.DATE_OF_BIRTH, _K.FULL_ADDRESS}),
            frozenset({_K.EMAIL, _K.FULL_ADDRESS}),
            frozenset({_K.DATE_OF_BIRTH}),
            "same_family",
        ),
        ScenarioKind.REUSED_USERNAME: _ScenarioSpec(
            frozenset({_K.USERNAME, _K.DATE_OF_BIRTH, _K.EMPLOYER}),
            frozenset({_K.USERNAME}),
            frozenset({_K.DATE_OF_BIRTH, _K.EMPLOYER}),
            "distinct",
        ),
        ScenarioKind.SHARED_EMPLOYER_AND_ADDRESS: _ScenarioSpec(
            frozenset({_K.EMPLOYER, _K.FULL_ADDRESS, _K.EMAIL}),
            frozenset({_K.EMPLOYER, _K.FULL_ADDRESS}),
            frozenset({_K.EMAIL}),
            "distinct",
        ),
        ScenarioKind.SAME_NAME_AND_DATE_OF_BIRTH: _ScenarioSpec(
            frozenset({_K.DATE_OF_BIRTH, _K.FAMILY_NAME, _K.FULL_ADDRESS}),
            frozenset({_K.DATE_OF_BIRTH, _K.FAMILY_NAME}),
            frozenset({_K.FULL_ADDRESS}),
            "equal",
        ),
        ScenarioKind.TWINS_OVERLAPPING_CONTEXT: _ScenarioSpec(
            frozenset(
                {_K.FAMILY_NAME, _K.DATE_OF_BIRTH, _K.FULL_ADDRESS, _K.SCHOOL_YEAR}
            ),
            frozenset(
                {_K.FAMILY_NAME, _K.DATE_OF_BIRTH, _K.FULL_ADDRESS, _K.SCHOOL_YEAR}
            ),
            frozenset(),
            "same_family",
        ),
        ScenarioKind.ALIAS_CHANGE: _ScenarioSpec(
            frozenset({_K.FAMILY_NAME, _K.DATE_OF_BIRTH, _K.USERNAME, _K.SCHOOL_YEAR}),
            frozenset({_K.DATE_OF_BIRTH, _K.USERNAME, _K.SCHOOL_YEAR}),
            frozenset({_K.FAMILY_NAME}),
            "alias",
        ),
        ScenarioKind.UNICODE_VARIANT: _ScenarioSpec(
            frozenset({_K.FAMILY_NAME, _K.DATE_OF_BIRTH, _K.EMAIL}),
            frozenset({_K.DATE_OF_BIRTH, _K.EMAIL}),
            frozenset({_K.FAMILY_NAME}),
            "unicode",
        ),
        ScenarioKind.DUPLICATE_OBSERVATION: _ScenarioSpec(
            frozenset({_K.EMAIL, _K.PHONE, _K.FULL_ADDRESS}),
            frozenset({_K.EMAIL, _K.PHONE, _K.FULL_ADDRESS}),
            frozenset(),
            "equal",
        ),
        ScenarioKind.SPARSE_RECORDS: _ScenarioSpec(
            frozenset({_K.FAMILY_NAME}),
            frozenset({_K.FAMILY_NAME}),
            frozenset(),
            "initial_full",
        ),
    }
    if scenario in fixed:
        return fixed[scenario]

    chosen = selected[scenario]
    if scenario is ScenarioKind.CONTRADICTORY_STRONG_IDENTIFIERS:
        shared = frozenset({_K.EMPLOYER, _K.SCHOOL_YEAR})
        return _ScenarioSpec(shared | {chosen}, shared, frozenset({chosen}), "equal")
    if scenario is ScenarioKind.STALE_ATTRIBUTE:
        shared = frozenset({_K.EMAIL, _K.DATE_OF_BIRTH})
        return _ScenarioSpec(shared | {chosen}, shared, frozenset({chosen}), "equal")
    if scenario is ScenarioKind.PARTIAL_BUT_SUFFICIENT:
        shared = frozenset({_K.FAMILY_NAME, _K.EMPLOYER})
        return _ScenarioSpec(
            shared, shared, frozenset(), "initial_full", frozenset({chosen})
        )
    if scenario is ScenarioKind.SINGLE_UNCORROBORATED_ATTRIBUTE:
        shared = frozenset({chosen})
        return _ScenarioSpec(shared, shared, frozenset(), "initial_full")

    other = next(item for item in REALIZATIONS[scenario] if item is not chosen)
    shared = frozenset({_K.FAMILY_NAME, other})
    return _ScenarioSpec(shared | {chosen}, shared, frozenset({chosen}), "equal")


def _values(record: PublicIdentityRecord) -> dict[_K, str]:
    result = {item.kind: item.value for item in record.attributes}
    _require(
        len(result) == len(record.attributes),
        f"record {record.id} repeats an attribute kind",
    )
    return result


def _ascii_fold(value: str) -> str:
    return normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()


def _attribute_collision_key(
    attribute: PublicIdentityAttribute,
) -> tuple[_K, str]:
    normalized = " ".join(normalize("NFKC", attribute.value).casefold().split())
    if attribute.kind is _K.PHONE:
        normalized = "".join(
            character for character in normalized if character.isdigit()
        )
    elif attribute.kind is _K.FAMILY_NAME:
        normalized = _ascii_fold(normalized)
    return attribute.kind, normalized


def _validate_display(
    scenario: ScenarioKind,
    relation: _DisplayRelation,
    left: str,
    right: str,
) -> None:
    left_parts = left.split()
    right_parts = right.split()
    _require(
        len(left_parts) >= 2 and len(right_parts) >= 2,
        f"{scenario.value} display names must contain given and family components",
    )
    if relation == "equal":
        valid = left.casefold() == right.casefold()
    elif relation == "same_family":
        valid = (
            left_parts[-1].casefold() == right_parts[-1].casefold()
            and left_parts[0].casefold() != right_parts[0].casefold()
        )
    elif relation == "alias":
        valid = (
            left_parts[0].casefold() == right_parts[0].casefold()
            and left_parts[-1].casefold() != right_parts[-1].casefold()
        )
    elif relation == "unicode":
        valid = (
            left != right
            and _ascii_fold(left) == _ascii_fold(right)
            and (not left.isascii() or not right.isascii())
        )
    elif relation == "initial_full":
        left_is_initial = left_parts[0].endswith(".")
        right_is_initial = right_parts[0].endswith(".")
        valid = (
            left_parts[-1].casefold() == right_parts[-1].casefold()
            and left_is_initial is not right_is_initial
            and left_parts[0][0].casefold() == right_parts[0][0].casefold()
        )
    else:
        valid = left.casefold() != right.casefold()
    _require(valid, f"{scenario.value} display-name relationship is corrupt")


def validate_ambiguity_variant(
    benchmark: AmbiguityBenchmark,
    *,
    metadata: AmbiguityVariantMetadata | None = None,
) -> None:
    """Check emitted evidence against the frozen pack, not against the generator.

    The claim this docstring used to make - validation "independent of copied scenario
    labels" - was false. Every expectation came from `_scenario_spec`, which is the
    same per-scenario switch `_realize_attributes` generates from, so the two agreed
    by construction and a matching mistake in both was asserted rather than caught.
    That is exactly what happened to `partial_but_sufficient`, corrupt in 100 of 100
    seeds under a green suite at 100% branch coverage.

    So the shape of each case is now read off the hand-authored canonical drafts and
    compared with what the variant actually emits. The spec checks remain - they are
    a useful statement of intent - but they are no longer the only judge.
    """

    metadata = metadata or ambiguity_variant_metadata(seed=benchmark.seed)
    _require(metadata.seed == benchmark.seed, "variant metadata seed does not match")
    selected = _selected(metadata)
    canonical_shapes = canonical_case_shapes()
    canonical_shared_sources = canonical_source_agreement()
    records = {item.id: item for item in benchmark.public.corpus.identity_records}
    memberships = {
        item.record_id: item.entity_id
        for item in benchmark.answer_key.record_memberships
    }
    _require(
        len(memberships) == len(benchmark.answer_key.record_memberships),
        "variant contains duplicate record memberships",
    )
    _require(
        set(memberships) == set(records),
        "variant memberships do not cover the public records exactly",
    )
    scenario_counts = Counter(item.scenario for item in benchmark.answer_key.pairs)
    _require(
        scenario_counts == Counter({scenario: 1 for scenario in ScenarioKind}),
        "variant must contain every scenario exactly once",
    )
    paired_record_ids = tuple(
        record_id
        for pair in benchmark.answer_key.pairs
        for record_id in (pair.left_record_id, pair.right_record_id)
    )
    _require(
        len(paired_record_ids) == len(set(paired_record_ids))
        and set(paired_record_ids) == set(records),
        "variant scenarios must partition the public records",
    )

    attribute_scenarios: dict[tuple[_K, str], set[ScenarioKind]] = defaultdict(set)
    display_scenarios: dict[str, set[ScenarioKind]] = defaultdict(set)
    for pair in benchmark.answer_key.pairs:
        left = records[pair.left_record_id]
        right = records[pair.right_record_id]
        left_values = _values(left)
        right_values = _values(right)
        spec = _scenario_spec(pair.scenario, selected)
        _require(
            (set(left_values) & set(right_values)) == spec.kinds
            and (set(left_values) ^ set(right_values)) == spec.lopsided,
            f"{pair.scenario.value} has the wrong attribute cardinality or kinds",
        )
        shared = frozenset(
            kind for kind in spec.kinds if left_values[kind] == right_values[kind]
        )
        different = spec.kinds - shared
        _require(
            shared == spec.shared and different == spec.different,
            f"{pair.scenario.value} public evidence does not exhibit its case",
        )
        # The independent check. Everything above compares the emitted world against
        # `_scenario_spec`, which is the same switch `_realize_attributes` generates
        # from - so it can only prove the switch agrees with itself. This compares it
        # against the hand-authored canonical drafts instead.
        _require(
            _case_shape(
                left_values, right_values, exact=pair.scenario not in REALIZATIONS
            )
            == canonical_shapes[pair.scenario],
            f"{pair.scenario.value} no longer has the shape it has in the frozen pack",
        )
        _require(
            (left.source_type is right.source_type)
            is canonical_shared_sources[pair.scenario],
            f"{pair.scenario.value} disagrees with the frozen pack on whether its "
            "two records come from one source",
        )
        expected_same_entity = pair.scenario in _SAME_ENTITY_SCENARIOS
        _require(
            pair.same_entity is expected_same_entity,
            f"{pair.scenario.value} carries the wrong canonical entity relationship",
        )
        _require(
            (memberships[left.id] == memberships[right.id]) is expected_same_entity,
            f"{pair.scenario.value} membership truth is semantically corrupt",
        )
        _require(
            pair.disposition is SCENARIO_DISPOSITIONS[pair.scenario],
            f"{pair.scenario.value} carries the wrong disposition",
        )
        _validate_display(
            pair.scenario, spec.display_relation, left.display_name, right.display_name
        )
        for record, values in ((left, left_values), (right, right_values)):
            family_name = values.get(_K.FAMILY_NAME)
            _require(
                family_name is None
                or record.display_name.split()[-1].casefold() == family_name.casefold(),
                f"{pair.scenario.value} display name disagrees with family evidence",
            )
            display_scenarios[_ascii_fold(record.display_name)].add(pair.scenario)
            for item in record.attributes:
                attribute_scenarios[_attribute_collision_key(item)].add(pair.scenario)

        if pair.scenario is ScenarioKind.UNICODE_VARIANT:
            left_family = left_values[_K.FAMILY_NAME]
            right_family = right_values[_K.FAMILY_NAME]
            _require(
                left_family != right_family
                and _ascii_fold(left_family) == _ascii_fold(right_family)
                and (not left_family.isascii() or not right_family.isascii()),
                "unicode_variant family-name evidence lost its transliteration",
            )

    _require(
        all(len(origins) == 1 for origins in attribute_scenarios.values()),
        "a generated attribute value collides across scenarios",
    )
    _require(
        all(len(origins) == 1 for origins in display_scenarios.values()),
        "a generated display name collides across scenarios",
    )


def generate_ambiguity_variant(*, seed: int, key: bytes = b"") -> AmbiguityBenchmark:
    """Generate one deterministic variant and refuse semantically corrupt output."""

    drafts = _drafts()
    metadata = ambiguity_variant_metadata(seed=seed, key=key)
    selected = _selected(metadata)
    substitutions = _substitution_plan(drafts, metadata, key)
    records: list[PublicIdentityRecord] = []
    pairs: list[PairTruth] = []

    # Realize every pair before naming any of them. Name slots are ranked across the
    # whole corpus's evidence, so they cannot be assigned one pair at a time - and
    # ranking is the point, because it is what keeps the scenario ordinal out.
    realized: list[
        tuple[
            _Draft,
            _Draft,
            tuple[PublicIdentityAttribute, ...],
            tuple[PublicIdentityAttribute, ...],
        ]
    ] = []
    for position in range(0, len(drafts), 2):
        left_draft, right_draft = drafts[position : position + 2]
        left_attributes, right_attributes = _realize_attributes(
            left_draft.scenario,
            _draft_anchor(drafts, left_draft.scenario),
            _rewritten_attributes(left_draft, substitutions),
            _rewritten_attributes(right_draft, substitutions),
            selected,
            substitutions,
        )
        if left_draft.scenario is ScenarioKind.UNICODE_VARIANT:
            _, _, unicode_family, ascii_family = _unicode_name(seed)
            left_attributes = _replace_family(left_attributes, unicode_family)
            right_attributes = _replace_family(right_attributes, ascii_family)
        realized.append((left_draft, right_draft, left_attributes, right_attributes))

    slots = _display_slots(
        seed,
        {
            left_draft.scenario: _evidence_anchor(left_attributes, right_attributes)
            for left_draft, _right, left_attributes, right_attributes in realized
        },
    )

    for left_draft, right_draft, left_attributes, right_attributes in realized:
        scenario = left_draft.scenario
        left_name, right_name = _display_names(
            seed=seed,
            scenario=scenario,
            slot=slots[scenario],
            left=left_attributes,
            right=right_attributes,
        )
        left_source, right_source = _source_types(
            seed, _draft_anchor(drafts, scenario), left_draft, right_draft
        )
        left_record = _identity_record(
            seed=seed,
            key=_record_key(left_name, left_source, left_attributes),
            source_type=left_source,
            display_name=left_name,
            attributes=left_attributes,
        )
        right_record = _identity_record(
            seed=seed,
            key=_record_key(right_name, right_source, right_attributes),
            source_type=right_source,
            display_name=right_name,
            attributes=right_attributes,
        )
        _require(
            left_record.id != right_record.id,
            "two records in one pair are indistinguishable by content",
        )
        records.extend((left_record, right_record))
        first, second = sorted((left_record.id, right_record.id))
        pairs.append(
            PairTruth(
                left_record_id=first,
                right_record_id=second,
                disposition=SCENARIO_DISPOSITIONS[scenario],
                scenario=scenario,
                same_entity=left_draft.entity_number == right_draft.entity_number,
            )
        )

    memberships = tuple(
        RecordMembership(
            record_id=record.id, entity_id=f"entity-{draft.entity_number:04d}"
        )
        for record, draft in zip(records, drafts, strict=True)
    )
    benchmark = AmbiguityBenchmark(
        seed=seed,
        public=PublicAmbiguityTask(
            corpus=PublicConnectionCorpus(
                seed=seed, identity_records=tuple(records), association_records=()
            ),
            pairs_to_decide=public_pairs_from_truth(pairs),
        ),
        answer_key=AmbiguityAnswerKey(
            record_memberships=memberships, pairs=tuple(pairs)
        ),
    )
    validate_ambiguity_variant(benchmark, metadata=metadata)
    return benchmark


__all__ = [
    "FIXED_REALIZATION",
    "REALIZATIONS",
    "AmbiguityVariantError",
    "AmbiguityVariantMetadata",
    "ScenarioRealization",
    "ambiguity_variant_metadata",
    "generate_ambiguity_variant",
    "validate_ambiguity_variant",
]
