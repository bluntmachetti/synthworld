"""Compute - or check - the ambiguity pack's published error floor.

The floor is a deliverable of issue #80, not a side effect: the Bayes error of the
shipped generator, estimated with a stated method and N, gated, and keyed to a digest
of every decision-relevant constant. This script is the only place the full-scale
computation runs; the suite exercises the same code path at toy scale and pins the
publication it produces.

    uv run python examples/compute_ambiguity_floor.py            # compute and print
    uv run python examples/compute_ambiguity_floor.py --check    # diff the publication

`--check` is what `make baselines` runs: it recomputes the invariants, re-estimates
the floor at the publication's N, and fails if any number has moved or the digest no
longer matches - so a parameter change invalidates the published floor loudly.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys

from synthworld.ambiguity_channel import (
    CHANNEL,
    distance_law,
    form_defect,
    mass_breakdown,
    min_sibling_mass,
    noise_support,
    same_core_probability,
    side_two_total_variation,
    single_value_defect,
    stationarity_defect,
)
from synthworld.ambiguity_evidence import EvidenceKind, Relation
from synthworld.ambiguity_floor import (
    FLOOR_BAND,
    MINIMUM_PREMIUM,
    estimate_floor,
    evaluate_gates,
    floor_digest,
)
from synthworld.ambiguity_floor import (
    FLOOR_PUBLICATION as PUBLISHED,
)
from synthworld.ambiguity_surfaces import bases

#: The computation's own seed and key. The floor is a property of the generator law,
#: estimated over packs; which packs is a free choice, stated here so the number is
#: reproducible.
FLOOR_KEY = b"synthworld-floor-computation"
FLOOR_SEED_START = 10_000


def check_invariants() -> list[str]:
    """The enumerated channel invariants, at full scale. Returns failures."""

    failures: list[str] = []
    for kind in EvidenceKind:
        if (defect := stationarity_defect(kind)) > 1e-9:
            failures.append(f"{kind.value}: stationarity defect {defect:.3e}")
        if (defect := side_two_total_variation(kind)) > 1e-9:
            failures.append(f"{kind.value}: side-two TV {defect:.3e}")
        if (defect := single_value_defect(kind)) > 1e-9:
            failures.append(f"{kind.value}: single-value TV {defect:.3e}")
        if (a := min_sibling_mass(kind)) < CHANNEL.a_min:
            failures.append(f"{kind.value}: sibling mass {a:.4f} < {CHANNEL.a_min}")
        # The form promises must hold over noisy cores, not just the clean bases:
        # noise happens before forms. The promises are structural - uniform alphabet
        # shifts are isometries, and equal-width disjoint alphabets make cross-form
        # distance the constant width - so the audit checks a deterministic subset of
        # the support rather than a quadratic census of it.
        support = noise_support(kind)
        step = max(1, len(support) // 120)
        if (defect := form_defect(kind, support[::step])) > 0.0:
            failures.append(f"{kind.value}: form defect {defect:.3e} on support")
        for relation in (Relation.EQUAL, Relation.NEAR, Relation.FAR):
            law = dict(distance_law(kind))[relation]
            if abs(sum(law) - 1.0) > 1e-9:
                failures.append(
                    f"{kind.value}: distance law for {relation} sums to {sum(law)}"
                )
        equal_same = same_core_probability(kind, Relation.EQUAL)
        near_same = same_core_probability(kind, Relation.NEAR)
        expected = CHANNEL.sigma + (1.0 - CHANNEL.sigma) * near_same
        if abs(equal_same - expected) > 1e-9:
            failures.append(f"{kind.value}: EQUAL diagonal {equal_same} != {expected}")
    return failures


def mass_report() -> None:
    """Per-base (q, a, sh, pv) - where the ambiguity lives, for the record."""

    print("per-base mass breakdown (q identity, a sibling, sh shared, pv private)")
    for kind in EvidenceKind:
        worst_a = 1.0
        for base in bases(kind):
            breakdown = mass_breakdown(kind, base)
            worst_a = min(worst_a, breakdown["a"])
        sample = mass_breakdown(kind, bases(kind)[0])
        print(
            f"  {kind.value:14s} base0 q={sample['q']:.3f} a={sample['a']:.3f} "
            f"sh={sample['sh']:.3f} pv={sample['pv']:.3f}  min_a={worst_a:.3f}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="recompute and diff against the published constants",
    )
    parser.add_argument(
        "--seed-count",
        type=int,
        default=None,
        help="override the publication's seed count (toy runs only)",
    )
    args = parser.parse_args(argv)

    failures = check_invariants()
    for failure in failures:
        print(f"INVARIANT FAILURE: {failure}")
    if failures:
        return 1
    print("invariants: all enumerated checks pass at full scale")
    mass_report()

    seed_count = args.seed_count or PUBLISHED.seed_count
    estimate = estimate_floor(
        seed_start=FLOOR_SEED_START, seed_count=seed_count, key=FLOOR_KEY
    )
    gates = evaluate_gates(estimate)
    digest = floor_digest()

    print(f"pairs={estimate.pair_count} seeds={estimate.seed_count}")
    low, high = gates.floor_interval
    print(
        f"floor={gates.floor:.4f} CI=[{low:.4f}, {high:.4f}]"
        f"  band={FLOOR_BAND}  in_band={gates.floor_in_band}"
    )
    print(
        f"ceiling={gates.ceiling:.4f} c0={gates.c0_accuracy:.4f}"
        f" c1={gates.c1_accuracy:.4f} gap_delta={gates.delta:.4f}"
        f" c1_gap_holds={gates.c1_gap_holds}"
    )
    print(
        f"premium={gates.premium:.4f} minimum={MINIMUM_PREMIUM}"
        f" holds={gates.premium_holds}"
    )
    print(f"digest={digest}")

    publication = {
        "floor": round(gates.floor, 4),
        "floor_half_width": round(
            (gates.floor_interval[1] - gates.floor_interval[0]) / 2, 4
        ),
        "c0_accuracy": round(gates.c0_accuracy, 4),
        "c1_accuracy": round(gates.c1_accuracy, 4),
        "genie_ceiling": round(gates.ceiling, 4),
        "technique_premium": round(gates.premium, 4),
        "pair_count": estimate.pair_count,
        "seed_count": estimate.seed_count,
        "digest": digest,
    }
    if not args.check:
        print("\npaste into ambiguity_floor.FLOOR_PUBLICATION:")
        print(
            "FloorPublication(\n"
            + "".join(f"    {key}={value!r},\n" for key, value in publication.items())
            + ")"
        )
        return (
            0
            if gates.floor_in_band and gates.c1_gap_holds and gates.premium_holds
            else 1
        )

    published = {
        field.name: getattr(PUBLISHED, field.name)
        for field in dataclasses.fields(PUBLISHED)
    }
    drifted = {
        key: (published[key], publication[key])
        for key in publication
        if published[key] != publication[key]
    }
    if drifted:
        print("\nPUBLICATION DRIFT:")
        for key, (was, now) in sorted(drifted.items()):
            print(f"  {key}: published {was!r} != computed {now!r}")
        return 1
    print("\npublication matches: no drift")
    return 0


if __name__ == "__main__":
    sys.exit(main())
