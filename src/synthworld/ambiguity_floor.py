"""The ambiguity pack's computed error floor, and the gates that bind it.

Issue #80's deliverable is a number with a method: the Bayes error of this generator
- the accuracy of a genie holding the public law, the observed comparable structure
and the true prevalence - computed rather than claimed, published with a confidence
interval, and keyed to a digest of every constant that can move it.

This module is the machinery. It sits above the channel, the grammar and the
generator, because the floor is a fact about all three at once: the channel supplies
the per-kind observation laws, the grammar supplies the latent vectors and the rule
that reads them, and the generator supplies the structures observations arrive in.
Nothing below it imports it.

Four quantities are estimated over sampled packs, all by the same route - draw the
latent truth, draw the observation from the exact channel law, compute the exact
posterior of the quantity's feature set over the enumerated relation vectors, decide,
and compare with truth:

- the **floor**: the genie's error, holding the full observation;
- **sup(C0)**: the best accuracy of byte-equality and form-agreement bits;
- **sup(C1)**: C0 plus raw distance where the forms agree;
- the **premium class**: per-kind normalised exact match - forms inverted exactly,
  the core-equality bit per kind and nothing else - whose gap to the ceiling is the
  technique premium.

Each is a supremum over a defined class, computed exactly per pair; the Monte Carlo
is only over which pairs occur, and every estimate carries a Wilson interval at the
stated N. The gates follow: floor in band, `sup(C1)` below the ceiling by a margin
derived from the CI, premium at least 0.05, and the enumerated channel invariants.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from math import sqrt

from synthworld.ambiguity import PairDisposition
from synthworld.ambiguity_channel import (
    CHANNEL,
    FloorPublication,
    capped_distance,
    decision_digest,
    distance_probability,
    likelihood_of,
    same_core_probability,
)
from synthworld.ambiguity_evidence import INDEX, ORDER, EvidenceKind, Relation, quantile
from synthworld.ambiguity_grammar import (
    _FS,
    _MERGE_BITS,
    _MERGE_NEEDS_CORROBORATION,
    _SEPARATE_BITS,
    _SOURCES,
    _VETO,
    _VETO_YIELDS_ABOVE,
    relation_vectors,
)
from synthworld.ambiguity_surfaces import invert_form, surface_of
from synthworld.ambiguity_v2 import DerivedPairTruth
from synthworld.ambiguity_v2_generator import (
    _CARRIED_RATE,
    _COMPLETENESS,
    _PAIRS,
    _PREVALENCE,
    generate_ambiguity_v2_pack,
)
from synthworld.connection import PublicIdentityRecord

#: The band the floor must sit in: anchored to expert disagreement on hard real
#: pairs. Below it, a perfect solver exists and the pack measures regex-writing;
#: above it, the pack measures noise.
FLOOR_BAND = (0.08, 0.12)

#: The technique premium gate: the gap between the full ceiling and the best solver
#: that only ever sees per-kind normalised exact match. Below this, tuned-for-it
#: resolvers get worse on real data than naive exact match, and the pack
#: anti-teaches.
MINIMUM_PREMIUM = 0.05

_Z_95 = 1.959963984540054


@dataclass(frozen=True)
class KindObservation:
    """One comparable kind's observation, reduced to what the modelled tuple holds."""

    left_core: str
    right_core: str
    left_form: int
    right_form: int
    rendered_equal: bool


@dataclass(frozen=True)
class PairObservation:
    kinds: tuple[EvidenceKind, ...]
    per_kind: tuple[KindObservation, ...]


def _name_part(display_name: str, given: bool) -> str | None:
    """The given or family half of a `family, given` display name, or None.

    #86 made the separator unambiguous, but a record whose name lacks it - one this
    pack never builds - yields no name observation rather than an index error.
    """

    parts = display_name.split(", ")
    if given:
        return parts[1] if len(parts) > 1 else None
    return parts[0] if parts[0] else None


def observe_pair(
    left: PublicIdentityRecord, right: PublicIdentityRecord
) -> PairObservation:
    """Reduce one public pair to its modelled observation tuple.

    Forms are inverted exactly - they are public machinery - and the display name is
    split at `", "`, which #86 made unambiguous. The two name kinds are carried by
    every record, so a pair always has at least those two comparable kinds and this
    always yields an observation; a kind only one side records is skipped, which is
    how `LOPSIDED` is represented here.
    """

    left_values = {item.kind.value: item.value for item in left.attributes}
    right_values = {item.kind.value: item.value for item in right.attributes}

    def observation(kind: EvidenceKind) -> KindObservation | None:
        if kind is EvidenceKind.GIVEN_NAME:
            left_value = _name_part(left.display_name, given=True)
            right_value = _name_part(right.display_name, given=True)
        elif kind is EvidenceKind.FAMILY_NAME:
            left_value = _name_part(left.display_name, given=False)
            right_value = _name_part(right.display_name, given=False)
        else:
            left_value = left_values.get(kind.value)
            right_value = right_values.get(kind.value)
        if left_value is None or right_value is None:
            return None
        left_form, left_core = invert_form(kind, left_value)
        right_form, right_core = invert_form(kind, right_value)
        return KindObservation(
            left_core=left_core,
            right_core=right_core,
            left_form=left_form,
            right_form=right_form,
            rendered_equal=left_value == right_value,
        )

    kinds: list[EvidenceKind] = []
    observations: list[KindObservation] = []
    for kind in sorted(EvidenceKind):
        found = observation(kind)
        if found is not None:
            kinds.append(kind)
            observations.append(found)
    return PairObservation(kinds=tuple(kinds), per_kind=tuple(observations))


#: One enumerated relation vector: relation indices in `ORDER`, the disposition the
#: rule derives, and the probability the Fellegi-Sunter table gives it under one
#: person and under two.
_Vector = tuple[tuple[int, ...], PairDisposition, float, float]


@cache
def _vectors_for(kinds: tuple[EvidenceKind, ...]) -> tuple[_Vector, ...]:
    return tuple(
        (
            tuple(INDEX[relation] for relation in relations),
            disposition,
            m_weight,
            u_weight,
        )
        for relations, disposition, m_weight, u_weight in relation_vectors(kinds)
    )


def _c0_likelihood(
    kind: EvidenceKind, relation: Relation, observation: KindObservation
) -> float:
    """P(this kind's C0 atom | relation): form agreement and byte equality.

    Forms are drawn uniformly and independently of everything, so the atoms are: the
    forms disagree (probability ``1 - 1/F``); or they agree and the cores are equal
    (``S_r / F``); or they agree and the cores differ (``(1 - S_r) / F``).
    """

    forms = surface_of(kind).form_count
    if observation.left_form != observation.right_form:
        return 1.0 - 1.0 / forms
    same_core = same_core_probability(kind, relation)
    if observation.left_core == observation.right_core:
        return same_core / forms
    return (1.0 - same_core) / forms


def _c1_likelihood(
    kind: EvidenceKind, relation: Relation, observation: KindObservation
) -> float:
    """P(this kind's C1 atom | relation): C0 plus capped distance where forms agree.

    Where the forms disagree, the rendered distance is the constant width - asserted
    by `form_defect` - so the distance carries nothing and the atom is the C0 one.
    Where they agree, the atom is the capped distance, read off the exact law.
    """

    forms = surface_of(kind).form_count
    if observation.left_form != observation.right_form:
        return 1.0 - 1.0 / forms
    distance = capped_distance(observation.left_core, observation.right_core)
    return distance_probability(kind, relation, distance) / forms


def _premium_likelihood(
    kind: EvidenceKind, relation: Relation, observation: KindObservation
) -> float:
    """P(this kind's premium atom | relation): normalised exact match and nothing else.

    The class inverts forms exactly - they are public - and sees per kind whether the
    cores are equal. That bit is the whole class; the premium is what it costs.
    """

    same_core = same_core_probability(kind, relation)
    if observation.left_core == observation.right_core:
        return same_core
    return 1.0 - same_core


@dataclass(frozen=True)
class PairDecision:
    """The MAP decision of each class for one pair, against the truth."""

    truth: PairDisposition
    genie: PairDisposition
    c0: PairDisposition
    c1: PairDisposition
    premium: PairDisposition
    genie_confidence: float


def decide_pair(
    observation: PairObservation, truth: DerivedPairTruth, prevalence: float
) -> PairDecision:
    """Exact posteriors over the enumerated latent vectors, for all four classes.

    One loop over the vectors serves every class: each accumulates its own likelihood
    product, mixed by the prevalence the genie is told. The MAP disposition is the
    class's optimal decision on this observation, so tallying correctness over pairs
    estimates the class supremum.
    """

    vectors = _vectors_for(observation.kinds)
    # Per-kind likelihood triples, computed once: the vector loop below is then pure
    # table lookup, which is the difference between milliseconds and minutes a pair.
    genie_likes: list[tuple[float, ...]] = []
    c0_likes: list[tuple[float, ...]] = []
    c1_likes: list[tuple[float, ...]] = []
    premium_likes: list[tuple[float, ...]] = []
    for kind, seen in zip(observation.kinds, observation.per_kind, strict=True):
        genie_likes.append(
            tuple(
                likelihood_of(kind, relation, seen.left_core, seen.right_core)
                for relation in (Relation.EQUAL, Relation.NEAR, Relation.FAR)
            )
        )
        c0_likes.append(
            tuple(_c0_likelihood(kind, relation, seen) for relation in ORDER)
        )
        c1_likes.append(
            tuple(_c1_likelihood(kind, relation, seen) for relation in ORDER)
        )
        premium_likes.append(
            tuple(_premium_likelihood(kind, relation, seen) for relation in ORDER)
        )

    # Three dispositions, four classes: accumulate indexed columns rather than
    # dicts, which is what makes the enumeration cheap enough to run per pair.
    merge = PairDisposition.MERGE
    separate = PairDisposition.SEPARATE
    insufficient = PairDisposition.INSUFFICIENT
    sums = {
        "genie": {merge: 0.0, separate: 0.0, insufficient: 0.0},
        "c0": {merge: 0.0, separate: 0.0, insufficient: 0.0},
        "c1": {merge: 0.0, separate: 0.0, insufficient: 0.0},
        "premium": {merge: 0.0, separate: 0.0, insufficient: 0.0},
    }
    for indices, disposition, m_weight, u_weight in vectors:
        genie_product = 1.0
        c0_product = 1.0
        c1_product = 1.0
        premium_product = 1.0
        for index, relation_index in enumerate(indices):
            genie_product *= genie_likes[index][relation_index]
            c0_product *= c0_likes[index][relation_index]
            c1_product *= c1_likes[index][relation_index]
            premium_product *= premium_likes[index][relation_index]
        # The likelihood product is the same under both mixture components - the
        # observation law given the vector does not depend on how the vector was
        # drawn - so the prevalence mixing folds into the vector weight.
        vector_mass = prevalence * m_weight + (1.0 - prevalence) * u_weight
        bucket_genie = sums["genie"][disposition]
        sums["genie"][disposition] = bucket_genie + vector_mass * genie_product
        sums["c0"][disposition] += vector_mass * c0_product
        sums["c1"][disposition] += vector_mass * c1_product
        sums["premium"][disposition] += vector_mass * premium_product

    decisions: dict[str, PairDisposition] = {}
    for name, bucket in sums.items():
        total = bucket[merge] + bucket[separate] + bucket[insufficient]
        if not total:
            # The observation the channel emitted has zero probability under the
            # model: a bug in the law, surfaced loudly rather than guessed at.
            raise ValueError("observation impossible under the modelled law")
        decisions[name] = max(bucket, key=lambda item: bucket[item])

    genie_total = (
        sums["genie"][merge] + sums["genie"][separate] + sums["genie"][insufficient]
    )
    return PairDecision(
        truth=truth.disposition,
        genie=decisions["genie"],
        c0=decisions["c0"],
        c1=decisions["c1"],
        premium=decisions["premium"],
        genie_confidence=sums["genie"][decisions["genie"]] / genie_total,
    )


def pack_prevalence(seed: int, key: bytes) -> float:
    """The pack's prevalence draw, recomputed from the generator's own law.

    The genie floor conditions on the true prevalence, and the draw is reproducible:
    one quantile under the same purpose string the generator uses.
    """

    low, high = _PREVALENCE
    return low + quantile(seed, "prevalence", 0, key) * (high - low)


def wilson_interval(successes: int, trials: int) -> tuple[float, float]:
    """A 95% Wilson interval - what the published half-widths are."""

    if not trials:
        return (0.0, 1.0)
    centre = (successes + _Z_95**2 / 2) / (trials + _Z_95**2)
    half = (
        _Z_95
        * sqrt(successes * (trials - successes) / trials + _Z_95**2 / 4)
        / (trials + _Z_95**2)
    )
    return (max(0.0, centre - half), min(1.0, centre + half))


@dataclass(frozen=True)
class FloorEstimate:
    """The four class accuracies over sampled pairs, with Wilson intervals."""

    pair_count: int
    seed_count: int
    genie_correct: int
    c0_correct: int
    c1_correct: int
    premium_correct: int

    @property
    def floor(self) -> float:
        return 1.0 - self.genie_correct / self.pair_count

    @property
    def floor_interval(self) -> tuple[float, float]:
        # The floor *is* the error rate, so its interval is the Wilson interval of
        # the errors themselves - no inversion.
        return wilson_interval(self.pair_count - self.genie_correct, self.pair_count)

    def accuracy(self, name: str) -> float:
        correct = {
            "genie": self.genie_correct,
            "c0": self.c0_correct,
            "c1": self.c1_correct,
            "premium": self.premium_correct,
        }[name]
        return correct / self.pair_count


def estimate_floor(*, seed_start: int, seed_count: int, key: bytes) -> FloorEstimate:
    """Sample packs, decide every pair four ways, and tally against truth.

    The Monte Carlo is over packs: which structures, prevalences and latent vectors
    occur. Every posterior given an observation is exact, enumerated over the latent
    space, so the only noise in the estimates is the sampling of pairs, and it is
    bounded by the Wilson intervals at this N.
    """

    genie = c0 = c1 = premium = total = 0
    for seed in range(seed_start, seed_start + seed_count):
        task, truths = generate_ambiguity_v2_pack(seed=seed, key=key)
        prevalence = pack_prevalence(seed, key)
        by_id = {record.id: record for record in task.corpus.identity_records}
        for truth in truths:
            observation = observe_pair(
                by_id[truth.left_record_id], by_id[truth.right_record_id]
            )
            decision = decide_pair(observation, truth, prevalence)
            total += 1
            genie += decision.genie is decision.truth
            c0 += decision.c0 is decision.truth
            c1 += decision.c1 is decision.truth
            premium += decision.premium is decision.truth
    return FloorEstimate(
        pair_count=total,
        seed_count=seed_count,
        genie_correct=genie,
        c0_correct=c0,
        c1_correct=c1,
        premium_correct=premium,
    )


def decision_inputs() -> dict[str, object]:
    """Every decision-relevant constant, canonicalised for the digest.

    Not just the Fellegi-Sunter table: the thresholds, the veto, the corroboration
    rule, the prevalence and completeness laws, the pack size, the carried rate, and
    every channel dial. A floor keyed only to `_FS` would have survived the threshold
    move that invalidated it, which is the defect this list exists to close.
    """

    return {
        "fs": tuple((kind.value, m, u) for kind, (m, u) in sorted(_FS.items())),
        "merge_bits": _MERGE_BITS,
        "separate_bits": _SEPARATE_BITS,
        "veto": tuple(sorted(kind.value for kind in _VETO)),
        "merge_needs_corroboration": _MERGE_NEEDS_CORROBORATION,
        "veto_yields_above": _VETO_YIELDS_ABOVE,
        "sources": tuple(sorted(_SOURCES.items())),
        "prevalence": _PREVALENCE,
        "completeness": _COMPLETENESS,
        "carried_rate": _CARRIED_RATE,
        "pairs": _PAIRS,
        "channel": CHANNEL,
        "pools": tuple(
            (
                kind.value,
                surface.clusters,
                surface.cluster_masses,
                surface.member_masses,
                surface.width,
            )
            for kind, surface in sorted(
                ((kind, surface_of(kind)) for kind in EvidenceKind),
                key=lambda item: item[0].value,
            )
        ),
    }


def floor_digest() -> str:
    return decision_digest(decision_inputs())


#: The published floor computation, produced by `examples/compute_ambiguity_floor.py`
#: under the seed and key stated there. The digest binds every number to the exact
#: decision-relevant constants it was computed from: move any of them and the suite's
#: digest check fails until the floor is recomputed. The estimate is over
#: `pair_count` pairs - pack generation is deterministic, so the number replays.
FLOOR_PUBLICATION = FloorPublication(
    floor=0.1108,
    floor_half_width=0.0094,
    c0_accuracy=0.693,
    c1_accuracy=0.7142,
    genie_ceiling=0.8892,
    technique_premium=0.0698,
    pair_count=4286,
    seed_count=60,
    digest="f2c68dd5c7f9ed1d49d63af182ce339c",
)


@dataclass(frozen=True)
class GateReport:
    """The gates of issue #80, read off one estimate."""

    floor_in_band: bool
    c1_gap_holds: bool
    premium_holds: bool
    floor: float
    floor_interval: tuple[float, float]
    ceiling: float
    c1_accuracy: float
    c0_accuracy: float
    premium: float
    delta: float


def evaluate_gates(estimate: FloorEstimate) -> GateReport:
    """Gates 1, 2 and 4. Gate 3 is class balance, asserted by the pack's own suite;
    gates 5 and 6 are the enumerated channel invariants; all are joined at the
    publication step.

    `delta` is ``max(0.05, 2 * epsilon)`` with ``epsilon`` the Wilson half-width of
    the floor estimate at this N - the margin the gate reads, derived from the stated
    CI rather than approximated.
    """

    low, high = estimate.floor_interval
    epsilon = (high - low) / 2
    delta = max(0.05, 2 * epsilon)
    ceiling = estimate.accuracy("genie")
    c1_accuracy = estimate.accuracy("c1")
    return GateReport(
        floor_in_band=FLOOR_BAND[0] <= estimate.floor <= FLOOR_BAND[1],
        c1_gap_holds=c1_accuracy <= ceiling - delta,
        premium_holds=ceiling - estimate.accuracy("premium") >= MINIMUM_PREMIUM,
        floor=estimate.floor,
        floor_interval=estimate.floor_interval,
        ceiling=ceiling,
        c1_accuracy=c1_accuracy,
        c0_accuracy=estimate.accuracy("c0"),
        premium=ceiling - estimate.accuracy("premium"),
        delta=delta,
    )


__all__ = [
    "FLOOR_BAND",
    "MINIMUM_PREMIUM",
    "FloorEstimate",
    "GateReport",
    "KindObservation",
    "PairDecision",
    "PairObservation",
    "decide_pair",
    "decision_inputs",
    "estimate_floor",
    "evaluate_gates",
    "floor_digest",
    "observe_pair",
    "pack_prevalence",
    "wilson_interval",
]
