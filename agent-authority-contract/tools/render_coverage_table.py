"""Render the design-intent coverage table from the scorer.

The table in ``docs/design-intent-assumptions.md`` was hand-transcribed from a
scoring run, which is the same closed loop that produced the defects this package
keeps finding: the numbers, and the prose describing them, came from one person
reading one run. This renders the block instead, and ``--check`` fails the build when
the committed markdown drifts from what the scorer currently says.

Two rules the previous hand-written table broke.

**Every metric is published.** The hand-written table showed 12 of the 20 the scorer
emits. Most omissions were harmless, but selection is an editorial lever nobody was
auditing, and one omitted metric - ``authorization_decision_recall``, on which the
bearer baseline scores a perfect 1.000 - is exactly the kind of row a curated table
tends to lose. Publishing all 20 removes the lever.

**Every metric states its denominator**, per AGENTS.md: "Every metric must state its
denominator and have a discriminating test case." Supports are per cell, not per row -
``authorization_decision_precision`` has support 4 for proxy-injection and 11 for
static-bearer, because the bearer baseline predicts allow everywhere - so a single
support column would be wrong.

Usage::

    uv run python agent-authority-contract/tools/render_coverage_table.py
    uv run python agent-authority-contract/tools/render_coverage_table.py --check
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from synthworld.agentic import (
    evaluate_agentic_trace,
    generate_asteria_agentic_v1,
    trace_submission_from_jsonl,
)

CONTRACT_DIR = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = CONTRACT_DIR / "examples"
DOC_PATH = CONTRACT_DIR / "docs" / "design-intent-assumptions.md"

BEGIN = "<!-- BEGIN GENERATED: coverage-table (render_coverage_table.py) -->"
END = "<!-- END GENERATED: coverage-table -->"

#: Column order. Worst-to-best reads as an argument rather than a list.
PATTERN_ORDER = ("static-bearer", "short-lived-minting", "proxy-injection")


def _score() -> dict[str, dict[str, tuple[float | None, int]]]:
    """Return ``{pattern: {metric: (value, support)}}`` straight from the scorer."""

    benchmark = generate_asteria_agentic_v1()
    scored: dict[str, dict[str, tuple[float | None, int]]] = {}
    for path in sorted(EXAMPLES_DIR.glob("idealised-*.jsonl")):
        report = evaluate_agentic_trace(
            trace_submission_from_jsonl(path.read_text(encoding="utf-8")),
            benchmark=benchmark,
        )
        scored[path.stem.removeprefix("idealised-")] = {
            metric.name: (metric.value, metric.support) for metric in report.metrics
        }
    return scored


def _cell(value: float | None, support: int) -> str:
    """Render one cell as ``value (support)``, or ``n/a`` where undefined.

    A metric with no support is not zero and must not read as zero: bearer's
    provenance precision is undefined because it submitted no evidence references
    at all, which is different from submitting wrong ones.
    """

    rendered = "n/a" if value is None else f"{value:.3f}"
    return f"{rendered} ({support})"


def render_table() -> str:
    scored = _score()
    patterns = [name for name in PATTERN_ORDER if name in scored]
    patterns += sorted(set(scored) - set(patterns))
    header = f"| metric | {' | '.join(patterns)} |"
    divider = "|---" * (len(patterns) + 1) + "|"
    lines = [header, divider]
    for metric in sorted(next(iter(scored.values()))):
        cells = " | ".join(_cell(*scored[name][metric]) for name in patterns)
        lines.append(f"| `{metric}` | {cells} |")
    return "\n".join(lines)


def replace_block(markdown: str, table: str) -> str:
    pattern = re.compile(
        f"{re.escape(BEGIN)}.*?{re.escape(END)}",
        re.DOTALL,
    )
    if not pattern.search(markdown):
        raise SystemExit(
            f"{DOC_PATH} has no generated block; expected markers {BEGIN!r} / {END!r}"
        )
    return pattern.sub(f"{BEGIN}\n\n{table}\n\n{END}", markdown)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the committed table differs from the scorer",
    )
    args = parser.parse_args(argv)

    current = DOC_PATH.read_text(encoding="utf-8")
    updated = replace_block(current, render_table())
    if args.check:
        if current != updated:
            print(f"STALE: {DOC_PATH} does not match the scorer", file=sys.stderr)
            print("re-run without --check to regenerate", file=sys.stderr)
            return 1
        print("coverage table matches the scorer")
        return 0
    DOC_PATH.write_text(updated, encoding="utf-8")
    print(f"wrote {DOC_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
