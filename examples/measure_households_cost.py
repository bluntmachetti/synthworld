"""Measure generation cost for the households profile at its standard tier.

Issue #43 asks for a 100-person standard run to document runtime and peak memory.
A number typed into a document is not that: it cannot be re-checked, and it says
nothing about the machine it came from. This prints both, with the interpreter and
platform beside them, so a reader can tell whether the figures apply to them.

Peak memory is measured with `tracemalloc`, so it reports Python allocations rather
than resident set size. That understates the true footprint - the interpreter
itself is not counted - but it is the part this profile controls, and it is
comparable across hosts in a way RSS is not.

Usage::

    uv run python examples/measure_households_cost.py
    uv run python examples/measure_households_cost.py --repeats 5
"""

from __future__ import annotations

import argparse
import platform
import statistics
import sys
import time
import tracemalloc

from synthworld.profiles.households import (
    HouseholdsConfig,
    generate_households_benchmark,
)


def measure(*, seed: int, config: HouseholdsConfig) -> tuple[float, int]:
    """Return elapsed seconds and peak Python allocation in bytes."""

    tracemalloc.start()
    start = time.perf_counter()
    generate_households_benchmark(seed=seed, config=config)
    elapsed = time.perf_counter() - start
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return elapsed, peak


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--person-count", type=int, default=100)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args(argv)

    config = HouseholdsConfig(person_count=args.person_count)
    # The first run pays import and Faker-locale costs that later runs do not, so
    # reporting it as the standard figure would overstate steady-state cost.
    measure(seed=1, config=config)

    samples = [measure(seed=seed, config=config) for seed in range(args.repeats)]
    times = [item[0] for item in samples]
    peaks = [item[1] for item in samples]

    print("profile        households_and_workplaces")
    print(f"person_count   {args.person_count}")
    print(f"repeats        {args.repeats} (after one discarded warm-up)")
    print(f"python         {platform.python_version()}")
    print(f"platform       {platform.platform(terse=True)}")
    print(
        f"runtime        median {statistics.median(times):.3f}s  "
        f"min {min(times):.3f}s  max {max(times):.3f}s"
    )
    print(
        f"peak memory    median {statistics.median(peaks) / 1024 / 1024:.1f} MiB  "
        f"max {max(peaks) / 1024 / 1024:.1f} MiB"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
