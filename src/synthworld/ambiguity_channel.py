"""The structured-noise channel of the ambiguity pack, and its computed floor.

Issue #80 in one sentence: a public deterministic renderer is enumerable, so
difficulty cannot come from hiding values - it must come from *overlap*. This module
is that overlap, engineered and measured rather than claimed.

The construction. Every kind draws a **base** from a pool arranged in confusable
clusters. `EQUAL` and `NEAR` share the base; `FAR` redraws from a stationary mixture
that lands inside the base's cluster with probability ``w``. Every rendered value
then passes through one **noise operator** - transposition, deletion, doubling,
keyboard slip, variant substitution, or nothing - applied per side, from a published
law, **identically under every relation**. The operator takes no relation argument;
the signature says so. `FAR` pairs therefore sit in the same edit neighbourhoods as
`NEAR` pairs. Recovering the identity is free and expected; it does not recover the
relation, because the distance distributions overlap by construction of the pool.

What that costs is stated here too: the error floor is not closed-form. It is the
Bayes error of this very generator - the accuracy of a genie holding the public law
and the true prevalence - and it is computed by enumeration of the per-kind laws plus
Monte Carlo over pairs, with a published confidence interval. The published numbers
are keyed to a digest of every decision-relevant constant, so any parameter move
invalidates them loudly instead of silently.

The module sits *below* the grammar: it knows pools, noise, kernels and likelihoods,
and it takes the decision rule as data. It never imports the rule, which keeps the
import graph acyclic and the floor an input to the gate rather than a creature of it.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import cache
from typing import TYPE_CHECKING, Literal

from synthworld.ambiguity_evidence import EvidenceKind, Relation, draw, quantile
from synthworld.ambiguity_surfaces import (
    base_probability,
    bases,
    invert_form,
    render_form,
    siblings_of,
    surface_of,
    surfaces,
)

if TYPE_CHECKING:
    from synthworld.ambiguity_surfaces import KindSurface

AMBIGUITY_CHANNEL_VERSION: Literal["1.0.0"] = "1.0.0"


@dataclass(frozen=True)
class ChannelConstants:
    """The dials of the channel. Every one is decision-relevant and digest-keyed.

    ``sigma`` is the probability that `EQUAL` shares one noise draw across both sides
    - "the same transcription" rather than "two independent transcriptions of the same
    value". Fixing it at 1 rebuilds a knife edge: core inequality becomes a certain
    not-`EQUAL` event, the floor and the technique premium turn anti-correlated, and
    the feasible region collapses. ``w_far_cluster`` is how often two different people
    look like one person written twice. ``a_min`` is the gated minimum sibling-landing
    mass, per base: if the edit law reaches a sibling only in principle, an observation
    showing two different bases becomes a near-certain `FAR` oracle and the floor
    collapses out of band.
    """

    sigma: float
    w_far_cluster: float
    identity_mass: float
    transpose_mass: float
    delete_mass: float
    double_mass: float
    substitute_mass: float
    variant_mass: float
    a_min: float


#: The operating point. Derived on this channel by the gate computation - see
#: `ambiguity_floor` and the publication below - not inherited from the abstract
#: surrogate of the parked plan, whose numbers only proved the region non-empty.
CHANNEL = ChannelConstants(
    sigma=0.80,
    w_far_cluster=0.24,
    identity_mass=0.16,
    transpose_mass=0.14,
    delete_mass=0.17,
    double_mass=0.17,
    substitute_mass=0.22,
    variant_mass=0.14,
    a_min=0.12,
)

#: Keyboard-adjacent slips, QWERTY rows. Characters absent from the table cannot be
#: slipped at that position; the position is skipped rather than guessed at.
_ADJACENT: dict[str, str] = {
    "q": "wa",
    "w": "qe",
    "e": "wr",
    "r": "et",
    "t": "ry",
    "y": "tu",
    "u": "yi",
    "i": "uo",
    "o": "ip",
    "p": "o",
    "a": "sq",
    "s": "ad",
    "d": "sf",
    "f": "dg",
    "g": "fh",
    "h": "gj",
    "j": "hk",
    "k": "jl",
    "l": "k",
    "z": "x",
    "x": "zc",
    "c": "xv",
    "v": "cb",
    "b": "vn",
    "n": "bm",
    "m": "n",
    "0": "9",
    "1": "2",
    "2": "13",
    "3": "24",
    "4": "35",
    "5": "46",
    "6": "57",
    "7": "68",
    "8": "79",
    "9": "80",
}

_OPERATIONS = (
    "identity",
    "transpose",
    "delete",
    "double",
    "substitute",
    "variant",
)


def _operation_mass(operation: str) -> float:
    masses = {
        "identity": CHANNEL.identity_mass,
        "transpose": CHANNEL.transpose_mass,
        "delete": CHANNEL.delete_mass,
        "double": CHANNEL.double_mass,
        "substitute": CHANNEL.substitute_mass,
        "variant": CHANNEL.variant_mass,
    }
    return masses[operation]


def _editable_positions(kind: EvidenceKind, core: str) -> tuple[int, ...]:
    """Where character edits may apply, per kind.

    Real transcription error concentrates: the digits of a date or a house number,
    the local-part of an address, anywhere a human copied a name. Modelling that is
    channel realism, and it also bounds the noise support of the long structured
    kinds, which is what keeps the floor's distance laws enumerable. `variant` is not
    a character edit and ignores the mask.
    """

    if kind is EvidenceKind.DATE_OF_BIRTH:
        return tuple(index for index, char in enumerate(core) if char.isdigit())
    if kind is EvidenceKind.EMAIL:
        local = core.partition("@")[0]
        return tuple(range(len(local)))
    if kind is EvidenceKind.FULL_ADDRESS:
        return tuple(index for index, char in enumerate(core) if char.isdigit())
    return tuple(range(len(core)))


def _applications(operation: str, core: str, kind: EvidenceKind) -> tuple[str, ...]:
    """Every outcome one operation can produce on one core, uniformly weighted.

    An operation with no valid application on this core contributes its mass to the
    identity outcome instead - the law must stay a distribution, and a core with no
    editable position has no edit to offer. None of the shipped cores reaches that
    branch; it exists so a future pool cannot silently skew the law.
    """

    if operation == "identity":
        return (core,)
    positions = _editable_positions(kind, core)
    if operation == "transpose":
        return tuple(
            f"{core[:index]}{core[index + 1]}{core[index]}{core[index + 2 :]}"
            for index in positions
            if index + 1 < len(core) and index + 1 in positions
        )
    if operation == "delete":
        if len(core) < 2:
            return ()
        return tuple(core[:index] + core[index + 1 :] for index in positions)
    if operation == "double":
        return tuple(core[:index] + core[index] + core[index:] for index in positions)
    if operation == "substitute":
        return tuple(
            core[:index] + replacement + core[index + 1 :]
            for index in positions
            for replacement in _ADJACENT.get(core[index], ())
        )
    if operation == "variant":
        return siblings_of(kind, core)
    raise ValueError(f"unknown operation {operation!r}")


def validate_operations(
    candidate: Mapping[EvidenceKind, KindSurface] | None = None,
) -> None:
    """Refuse a pool the edit law cannot act on.

    Every cluster must hold at least two bases - a lone base has no sibling for the
    variant draw to jump to - and every character operation must have at least one
    application on every base, since an empty outcome set would divide the law by
    zero. Checked once, loudly, and callable on a candidate pool so a redesign is
    refused here rather than skewing the law at draw time.
    """

    pool = surfaces() if candidate is None else candidate
    for kind, surface in pool.items():
        for cluster in surface.clusters:
            if len(cluster) < 2:
                raise ValueError(f"{kind.value} cluster {cluster!r} is too small")
        for base in surface.bases:
            for operation in ("transpose", "delete", "double", "substitute"):
                if not _applications(operation, base, kind):
                    raise ValueError(
                        f"{kind.value} base {base!r} admits no {operation}"
                    )


validate_operations()


@cache
def noise_outcomes(kind: EvidenceKind, core: str) -> tuple[tuple[str, float], ...]:
    """The exact noise law of one base: every reachable noisy core and its mass.

    A single edit per draw. The support is enumerable, which is what lets the floor be
    exact per kind, and what makes "inversion is a lookup" a published fact rather
    than a weakness: the codebook is on purpose. Every operation is guaranteed at
    least one application on every shipped base by the surfaces validation, so an
    empty outcome set here is a pool regression and divides loudly rather than
    folding silently into the identity mass.
    """

    gathered: dict[str, float] = {}
    for operation in _OPERATIONS:
        mass = _operation_mass(operation)
        outcomes = _applications(operation, core, kind)
        share = mass / len(outcomes)
        for outcome in outcomes:
            gathered[outcome] = gathered.get(outcome, 0.0) + share
    return tuple(sorted(gathered.items()))


def noise_support(kind: EvidenceKind) -> tuple[str, ...]:
    """Every string the noise law can emit for this kind, in canonical order."""

    support = {
        outcome for base in bases(kind) for outcome, _ in noise_outcomes(kind, base)
    }
    return tuple(sorted(support))


@cache
def base_outcomes(kind: EvidenceKind) -> tuple[tuple[str, float], ...]:
    """The base law ``pi``, in canonical order."""

    return tuple((base, base_probability(kind, base)) for base in bases(kind))


@cache
def far_outcomes(kind: EvidenceKind, base: str) -> tuple[tuple[str, float], ...]:
    """The FAR kernel: where a different person's value lands, given the base.

    A conditional-redraw mixture - with probability ``w`` redraw from ``pi`` restricted
    to the base's cluster, otherwise redraw from ``pi`` globally. Inflow into any base
    ``j`` is ``w * pi_j + (1 - w) * pi_j = pi_j``, so the kernel is stationary for any
    ``pi`` and any cluster geometry by a two-line lemma, asserted here by enumeration
    rather than by signature. Stationarity is what keeps the side-two marginal
    identical across relations - the #84 defect class, one level down.

    The kernel occasionally redraws the *same* base: two different people with the
    same name. That is realistic, and it is why no test here asserts that FAR renders
    two different values.
    """

    gathered: dict[str, float] = {}
    cluster = set(siblings_of(kind, base)) | {base}
    cluster_mass = sum(base_probability(kind, item) for item in cluster)
    for candidate, mass in base_outcomes(kind):
        within = CHANNEL.w_far_cluster * (
            mass / cluster_mass if candidate in cluster else 0.0
        )
        outside = (1.0 - CHANNEL.w_far_cluster) * mass
        gathered[candidate] = within + outside
    return tuple(sorted(gathered.items()))


def _pick(
    seed: int,
    purpose: str,
    slot: int,
    key: bytes,
    outcomes: tuple[tuple[str, float], ...],
) -> str:
    """Read one keyed quantile against cumulative mass, in canonical order."""

    point = quantile(seed, purpose, slot, key)
    running = 0.0
    for value, mass in outcomes[:-1]:
        running += mass
        if point < running:
            return value
    return outcomes[-1][0]


def sample_base(kind: EvidenceKind, *, seed: int, slot: int, key: bytes) -> str:
    return _pick(seed, f"{kind.value}:base", slot, key, base_outcomes(kind))


def sample_far_base(
    kind: EvidenceKind, base: str, *, seed: int, slot: int, key: bytes
) -> str:
    return _pick(seed, f"{kind.value}:other", slot, key, far_outcomes(kind, base))


def sample_noise(
    kind: EvidenceKind, core: str, *, purpose: str, seed: int, slot: int, key: bytes
) -> str:
    return _pick(seed, purpose, slot, key, noise_outcomes(kind, core))


def sample_form(
    kind: EvidenceKind, *, purpose: str, seed: int, slot: int, key: bytes
) -> int:
    return draw(seed, purpose, slot, key) % surface_of(kind).form_count


def render_relation(
    kind: EvidenceKind,
    relation: Relation,
    *,
    seed: int,
    key: bytes,
    slot: int,
) -> tuple[str, str]:
    """Two rendered values standing in the requested relation.

    The relation decides which base the second side draws and whether `EQUAL` shares
    its noise draw. It never decides how either side is corrupted: noise is drawn per
    side from one law with no relation argument, which is the whole of the #84 fix -
    damage applied only under one relation made pool membership an oracle, and here
    the signature makes that shape impossible.
    """

    if relation is Relation.LOPSIDED:
        raise ValueError("LOPSIDED is an absence, not a comparison: use render_value")

    base = sample_base(kind, seed=seed, slot=slot, key=key)
    left_form = sample_form(
        kind, purpose=f"{kind.value}:form:left", seed=seed, slot=slot, key=key
    )
    right_form = sample_form(
        kind, purpose=f"{kind.value}:form:right", seed=seed, slot=slot, key=key
    )

    if relation is Relation.FAR:
        other = sample_far_base(kind, base, seed=seed, slot=slot, key=key)
        left_core = sample_noise(
            kind,
            base,
            purpose=f"{kind.value}:noise:left",
            seed=seed,
            slot=slot,
            key=key,
        )
        right_core = sample_noise(
            kind,
            other,
            purpose=f"{kind.value}:noise:right",
            seed=seed,
            slot=slot,
            key=key,
        )
    elif (
        relation is Relation.EQUAL
        and quantile(seed, f"{kind.value}:share", slot, key) < CHANNEL.sigma
    ):
        shared = sample_noise(
            kind,
            base,
            purpose=f"{kind.value}:noise:shared",
            seed=seed,
            slot=slot,
            key=key,
        )
        left_core = right_core = shared
    else:
        left_core = sample_noise(
            kind,
            base,
            purpose=f"{kind.value}:noise:left",
            seed=seed,
            slot=slot,
            key=key,
        )
        right_core = sample_noise(
            kind,
            base,
            purpose=f"{kind.value}:noise:right",
            seed=seed,
            slot=slot,
            key=key,
        )

    return (
        render_form(kind, left_form, left_core),
        render_form(kind, right_form, right_core),
    )


def render_value(kind: EvidenceKind, *, seed: int, key: bytes, slot: int) -> str:
    """One value for a kind only one record carries.

    Drawn with exactly the purposes of a pair's first side, so a one-sided value is
    not distinguishable from a two-sided one: same base law, same noise law, same
    forms. Anything else would make "the other record lacks this" readable from the
    value itself.
    """

    base = sample_base(kind, seed=seed, slot=slot, key=key)
    core = sample_noise(
        kind, base, purpose=f"{kind.value}:noise:left", seed=seed, slot=slot, key=key
    )
    form = sample_form(
        kind, purpose=f"{kind.value}:form:left", seed=seed, slot=slot, key=key
    )
    return render_form(kind, form, core)


@cache
def emission_index(
    kind: EvidenceKind,
) -> tuple[tuple[str, tuple[tuple[str, float], ...]], ...]:
    """Which bases can emit each noisy core, and with what mass.

    The inverse of the noise table, restricted to positive mass: the ambiguity the
    pack is scored on, as data. Inverting a rendered value is a lookup on exactly
    this index - published on purpose, since a public deterministic renderer is
    enumerable and pretending otherwise is what sank the first two designs.
    """

    gathered: dict[str, dict[str, float]] = {}
    for base in bases(kind):
        for outcome, mass in noise_outcomes(kind, base):
            gathered.setdefault(outcome, {})[base] = mass
    return tuple(
        (outcome, tuple(sorted(emitters.items())))
        for outcome, emitters in sorted(gathered.items())
    )


@cache
def _emitter_lookup(
    kind: EvidenceKind,
) -> Mapping[str, tuple[tuple[str, float], ...]]:
    return dict(emission_index(kind))


def emitters_of(kind: EvidenceKind, core: str) -> tuple[tuple[str, float], ...]:
    """The bases this noisy core could have come from, with their noise masses."""

    return _emitter_lookup(kind).get(core, ())


def likelihood_of(
    kind: EvidenceKind, relation: Relation, left_core: str, right_core: str
) -> float:
    """P(two noisy cores | relation), from the factored law.

    `NEAR` is two independent noise draws on one base; `FAR` pushes the second base
    through the stationary kernel; `EQUAL` mixes a shared draw (probability ``sigma``,
    which forces equal cores) with the `NEAR` law. Kept factored rather than
    materialised: the joint table of a long kind has a million entries, and every
    consumer of it only ever asks point questions.
    """

    left_emitters = emitters_of(kind, left_core)
    right_emitters = emitters_of(kind, right_core)
    if not left_emitters or not right_emitters:
        return 0.0
    if relation is Relation.EQUAL and left_core == right_core:
        shared = sum(
            base_probability(kind, base) * mass for base, mass in left_emitters
        )
        return CHANNEL.sigma * shared + (1.0 - CHANNEL.sigma) * likelihood_of(
            kind, Relation.NEAR, left_core, right_core
        )
    if relation is Relation.EQUAL:
        return (1.0 - CHANNEL.sigma) * likelihood_of(
            kind, Relation.NEAR, left_core, right_core
        )
    if relation is Relation.NEAR:
        by_base = dict(right_emitters)
        return sum(
            base_probability(kind, base) * mass * by_base[base]
            for base, mass in left_emitters
            if base in by_base
        )
    total = 0.0
    for left_base, left_mass in left_emitters:
        kernel = dict(far_outcomes(kind, left_base))
        for right_base, right_mass in right_emitters:
            total += (
                base_probability(kind, left_base)
                * kernel[right_base]
                * left_mass
                * right_mass
            )
    return total


def core_distance(left: str, right: str) -> int:
    """Levenshtein distance, the pack's raw-distance feature."""

    return capped_distance(left, right, max(len(left), len(right)))


#: Distances above this cap carry no further relation signal: a pair of noisy cores
#: more than `_DISTANCE_CAP` apart cannot share a base or a cluster - two independent
#: single edits move a pair by at most two, and no shipped cluster is wider than the
#: cap minus two - so every observation beyond the cap is a cross-cluster pair, which
#: only `FAR` can produce, whatever its exact distance. The C1 class sees the capped
#: distance and loses nothing; the floor computation enumerates eleven buckets instead
#: of an unbounded range.
_DISTANCE_CAP = 9


def capped_distance(left: str, right: str, cap: int = _DISTANCE_CAP) -> int:
    """Levenshtein distance, reported as `cap + 1` once it exceeds the cap."""

    if left == right:
        return 0
    if abs(len(left) - len(right)) > cap:
        return cap + 1
    previous = list(range(len(right) + 1))
    for index_left, left_char in enumerate(left, start=1):
        current = [index_left]
        for index_right, right_char in enumerate(right, start=1):
            current.append(
                min(
                    previous[index_right] + 1,
                    current[index_right - 1] + 1,
                    previous[index_right - 1] + (left_char != right_char),
                )
            )
        if min(current) > cap:
            return cap + 1
        previous = current
    return previous[-1] if previous[-1] <= cap else cap + 1


@cache
def distance_law(kind: EvidenceKind) -> tuple[tuple[Relation, tuple[float, ...]], ...]:
    """The distribution of capped core-pair distance per relation.

    Eleven buckets - distances 0 to 9, then "beyond the cap" - and exact: the sum over
    bases and noise outcomes of the factored law. This is the feature law the C1 class
    supremum is computed from, and the enumerated fact that makes the constructive-
    closure argument a computation rather than a claim.
    """

    buckets = _DISTANCE_CAP + 2

    def accumulate(
        pairs: Iterable[
            tuple[float, tuple[tuple[str, float], ...], tuple[tuple[str, float], ...]]
        ],
    ) -> list[float]:
        law = [0.0] * buckets
        for mass, left_outcomes, right_outcomes in pairs:
            for left, left_mass in left_outcomes:
                for right, right_mass in right_outcomes:
                    distance = capped_distance(left, right)
                    law[distance] += mass * left_mass * right_mass
        return law

    noise = {base: noise_outcomes(kind, base) for base in bases(kind)}
    near = accumulate(
        (
            (base_mass, noise[base], noise[base])
            for base, base_mass in base_outcomes(kind)
        )
    )
    far = accumulate(
        (
            (base_mass * kernel_mass, noise[base], noise[other])
            for base, base_mass in base_outcomes(kind)
            for other, kernel_mass in far_outcomes(kind, base)
        )
    )
    equal = [CHANNEL.sigma if index == 0 else 0.0 for index in range(buckets)]
    for index in range(buckets):
        equal[index] += (1.0 - CHANNEL.sigma) * near[index]
    return (
        (Relation.EQUAL, tuple(equal)),
        (Relation.NEAR, tuple(near)),
        (Relation.FAR, tuple(far)),
    )


def distance_probability(
    kind: EvidenceKind, relation: Relation, distance: int
) -> float:
    """P(capped distance | relation), read off the exact law."""

    return dict(distance_law(kind))[relation][min(distance, _DISTANCE_CAP + 1)]


# ---------------------------------------------------------------------------
# Invariants. Each returns a defect magnitude; the gates assert it is zero or
# within a stated tolerance. They are enumerated over the exact law, never
# sampled, and they check distributions rather than signatures wherever the
# signature is not the property - the oracle this pack keeps finding hides in
# the difference.
# ---------------------------------------------------------------------------


def stationarity_defect(kind: EvidenceKind) -> float:
    """max over bases of |inflow under the FAR kernel - pi|; must be ~0."""

    inflow = {base: 0.0 for base in bases(kind)}
    for base, base_mass in base_outcomes(kind):
        for other, kernel_mass in far_outcomes(kind, base):
            inflow[other] += base_mass * kernel_mass
    return max(abs(inflow[base] - mass) for base, mass in base_outcomes(kind))


def side_two_total_variation(kind: EvidenceKind) -> float:
    """TV between the side-two marginal under NEAR and under FAR.

    Side one is a two-line theorem - its observation is ``noise(c1)`` with ``c1 ~ pi``
    under every relation. Side two needs the kernel stationary; this measures the
    consequence rather than trusting the lemma.
    """

    near_marginal: dict[str, float] = {}
    far_marginal: dict[str, float] = {}
    noise = {base: noise_outcomes(kind, base) for base in bases(kind)}
    for base, base_mass in base_outcomes(kind):
        for outcome, mass in noise[base]:
            near_marginal[outcome] = near_marginal.get(outcome, 0.0) + base_mass * mass
    for base, base_mass in base_outcomes(kind):
        for other, kernel_mass in far_outcomes(kind, base):
            for outcome, mass in noise[other]:
                far_marginal[outcome] = (
                    far_marginal.get(outcome, 0.0) + base_mass * kernel_mass * mass
                )
    support = set(near_marginal) | set(far_marginal)
    return (
        sum(
            abs(near_marginal.get(item, 0.0) - far_marginal.get(item, 0.0))
            for item in support
        )
        / 2
    )


def sibling_mass(kind: EvidenceKind, base: str) -> float:
    """Mass the noise law lands exactly on a sibling spelling of this base."""

    siblings = set(siblings_of(kind, base))
    return sum(
        mass for outcome, mass in noise_outcomes(kind, base) if outcome in siblings
    )


def min_sibling_mass(kind: EvidenceKind) -> float:
    """The per-base minimum; the gate is on the minimum, not the pool average."""

    return min(sibling_mass(kind, base) for base in bases(kind))


def mass_breakdown(kind: EvidenceKind, base: str) -> Mapping[str, float]:
    """Per-base (q, a, sh, pv): identity, sibling, shared off-string, private.

    A shared off-string is reachable from at least one other base as well; a private
    one from this base alone. The breakdown is what the floor publication reports so a
    consumer can audit where the ambiguity lives.
    """

    reachable_elsewhere: set[str] = set()
    for other in bases(kind):
        if other == base:
            continue
        reachable_elsewhere |= {outcome for outcome, _ in noise_outcomes(kind, other)}
    siblings = set(siblings_of(kind, base))
    breakdown = {"q": 0.0, "a": 0.0, "sh": 0.0, "pv": 0.0}
    for outcome, mass in noise_outcomes(kind, base):
        if outcome == base:
            breakdown["q"] += mass
        elif outcome in siblings:
            breakdown["a"] += mass
        elif outcome in reachable_elsewhere:
            breakdown["sh"] += mass
        else:
            breakdown["pv"] += mass
    return breakdown


def same_core_probability(kind: EvidenceKind, relation: Relation) -> float:
    """P(both sides carry the same noisy core | relation), before forms.

    Computed from the factored law: `NEAR` as the collision of two independent noise
    draws on one base, `FAR` as the kernel-weighted overlap of two bases' noise laws,
    and `EQUAL` as the shared-draw mixture, which lands on the diagonal with its whole
    ``sigma`` mass.
    """

    if relation is Relation.EQUAL:
        return CHANNEL.sigma + (1.0 - CHANNEL.sigma) * same_core_probability(
            kind, Relation.NEAR
        )
    total = 0.0
    if relation is Relation.NEAR:
        for base, base_mass in base_outcomes(kind):
            total += base_mass * sum(
                mass * mass for _, mass in noise_outcomes(kind, base)
            )
        return total
    noise = {base: dict(noise_outcomes(kind, base)) for base in bases(kind)}
    for base, base_mass in base_outcomes(kind):
        for other, kernel_mass in far_outcomes(kind, base):
            overlap = sum(
                mass * noise[other].get(outcome, 0.0)
                for outcome, mass in noise_outcomes(kind, base)
            )
            total += base_mass * kernel_mass * overlap
    return total


def form_defect(kind: EvidenceKind, cores: tuple[str, ...] | None = None) -> float:
    """How far the forms stray from the three enumerated promises.

    Bijectivity - every rendered value inverts to exactly its (form, core), so the
    cheap classes can undo a form and read the core. Form-independence - where the
    forms agree, the raw rendered distance is the same whichever form agreed, so the
    distance signal is the cores' and not the wrapping's. Separation - where the forms
    disagree, the raw rendered distance is the constant ``width``, so bytes carry no
    graded signal across forms and the constructive-closure argument loses nothing by
    restricting C1 to agreeing forms. Returns the magnitude of the worst violation,
    0.0 when all hold.

    Defaults to the clean bases, which is the suite-scale check; the floor computation
    passes the full noise support, where the same promises must also hold because
    noise happens before forms.
    """

    surface = surface_of(kind)
    checked = bases(kind) if cores is None else cores
    worst = 0.0
    for form in range(surface.form_count):
        for core in checked:
            rendered = render_form(kind, form, core)
            inverted_form, inverted_core = invert_form(kind, rendered)
            if inverted_form != form or inverted_core != core:
                return 1.0
    for left in checked:
        for right in checked:
            agreeing = [
                core_distance(
                    render_form(kind, form, left), render_form(kind, form, right)
                )
                for form in range(surface.form_count)
            ]
            spread = max(agreeing) - min(agreeing)
            worst = max(worst, spread / (surface.width or 1))
            for form in range(surface.form_count):
                for other in range(surface.form_count):
                    if other == form:
                        continue
                    across = core_distance(
                        render_form(kind, form, left), render_form(kind, other, right)
                    )
                    worst = max(worst, abs(across - surface.width) / surface.width)
    return worst


def _side_one_marginal(kind: EvidenceKind, relation: Relation) -> dict[str, float]:
    """One side's value law under a relation, computed through that relation's path.

    All three must come out as ``pi`` composed with the noise law - side one is
    ``noise(c1)`` with ``c1 ~ pi`` whatever the relation, since the relation only
    decides ``c2`` - and each is computed by its own structure rather than asserted:
    the shared-draw mixture for `EQUAL`, the summed kernel for `FAR`.
    """

    marginal: dict[str, float] = {}
    if relation is Relation.FAR:
        for base, base_mass in base_outcomes(kind):
            kernel_total = sum(mass for _, mass in far_outcomes(kind, base))
            for outcome, mass in noise_outcomes(kind, base):
                marginal[outcome] = (
                    marginal.get(outcome, 0.0) + base_mass * kernel_total * mass
                )
        return marginal
    if relation is Relation.EQUAL:
        shared_part = _side_one_marginal(kind, Relation.NEAR)
        independent_part = _side_one_marginal(kind, Relation.NEAR)
        return {
            outcome: CHANNEL.sigma * shared_part.get(outcome, 0.0)
            + (1.0 - CHANNEL.sigma) * independent_part.get(outcome, 0.0)
            for outcome in set(shared_part) | set(independent_part)
        }
    for base, base_mass in base_outcomes(kind):
        for outcome, mass in noise_outcomes(kind, base):
            marginal[outcome] = marginal.get(outcome, 0.0) + base_mass * mass
    return marginal


def single_value_defect(kind: EvidenceKind) -> float:
    """max TV between one-value marginals across relations; must be ~0.

    The operator takes no relation argument, and this verifies the consequence at the
    distribution level - the #84 defect was invisible to signature checks and visible
    to exactly this measurement.
    """

    marginals = {
        relation: _side_one_marginal(kind, relation)
        for relation in (Relation.EQUAL, Relation.NEAR, Relation.FAR)
    }
    worst = 0.0
    ordered = tuple(marginals.values())
    for index, first in enumerate(ordered):
        for second in ordered[index + 1 :]:
            support = set(first) | set(second)
            worst = max(
                worst,
                sum(
                    abs(first.get(item, 0.0) - second.get(item, 0.0))
                    for item in support
                )
                / 2,
            )
    return worst


# ---------------------------------------------------------------------------
# The decision digest. The published floor is keyed to every constant that can
# move it - not just the Fellegi-Sunter table, which is what an earlier draft
# did, and which would have missed the threshold move that changed the floor
# without touching that table at all.
# ---------------------------------------------------------------------------


def decision_digest(decision_inputs: Mapping[str, object]) -> str:
    """Blake2b over the canonical rendering of every decision-relevant input."""

    canonical = ";".join(
        f"{key}={value!r}" for key, value in sorted(decision_inputs.items())
    )
    return hashlib.blake2b(canonical.encode(), digest_size=16).hexdigest()


#: The floor publication. Numbers are filled by the gate computation
#: (`examples/compute_ambiguity_floor.py`, run via `make baselines`) after the
#: channel and the generator agree; the digest binds them to the constants they
#: were computed under. A parameter change moves the digest, and the suite fails
#: on the mismatch until the floor is recomputed - loudly, not silently.
@dataclass(frozen=True)
class FloorPublication:
    floor: float
    floor_half_width: float
    c0_accuracy: float
    c1_accuracy: float
    genie_ceiling: float
    technique_premium: float
    pair_count: int
    seed_count: int
    digest: str


__all__ = [
    "AMBIGUITY_CHANNEL_VERSION",
    "CHANNEL",
    "ChannelConstants",
    "FloorPublication",
    "base_outcomes",
    "capped_distance",
    "core_distance",
    "decision_digest",
    "distance_law",
    "distance_probability",
    "emission_index",
    "emitters_of",
    "far_outcomes",
    "form_defect",
    "likelihood_of",
    "mass_breakdown",
    "min_sibling_mass",
    "noise_outcomes",
    "noise_support",
    "render_relation",
    "render_value",
    "same_core_probability",
    "sample_base",
    "sample_far_base",
    "sample_form",
    "sample_noise",
    "sibling_mass",
    "side_two_total_variation",
    "single_value_defect",
    "stationarity_defect",
]
