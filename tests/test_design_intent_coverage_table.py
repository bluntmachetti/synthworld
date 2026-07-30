"""Verify the published coverage table against the scorer, independently.

Three paths must disagree before a wrong number can reach a reader: the scorer that
produces the values, the renderer that writes them into markdown, and this test,
which parses the committed markdown and recomputes from the public API.

**This module must not import the renderer.** Reusing its formatting helpers would
collapse the read path into the write path and reduce the check to ``render() ==
render()``. The cell format is duplicated here on purpose; that is not a DRY
violation to be refactored away.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from synthworld.agentic import (
    evaluate_agentic_trace,
    generate_asteria_agentic_v1,
    trace_submission_from_jsonl,
)

DOC = Path("agent-authority-contract/docs/design-intent-assumptions.md")
EXAMPLES = Path("agent-authority-contract/examples")
BEGIN = "<!-- BEGIN GENERATED: coverage-table"
END = "<!-- END GENERATED: coverage-table -->"

_CELL = re.compile(r"^(n/a|\d+\.\d{3}) \((\d+)\)$")


def _published() -> tuple[list[str], dict[str, dict[str, tuple[float | None, int]]]]:
    """Parse the committed block.

    Returns the pattern column order and ``{metric: {pattern: (value, support)}}``.
    """

    text = DOC.read_text(encoding="utf-8")
    body = text.split(BEGIN, 1)[1].split(END, 1)[0]
    rows = [line for line in body.splitlines() if line.strip().startswith("|")]
    header = [cell.strip() for cell in rows[0].strip("|").split("|")]
    patterns = header[1:]
    table: dict[str, dict[str, tuple[float | None, int]]] = {}
    for line in rows[2:]:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        metric = cells[0].strip("`")
        table[metric] = {}
        for pattern, cell in zip(patterns, cells[1:], strict=True):
            match = _CELL.match(cell)
            assert match is not None, f"unparseable cell for {metric}/{pattern}: {cell}"
            rendered, support = match.groups()
            value = None if rendered == "n/a" else float(rendered)
            table[metric][pattern] = (value, int(support))
    return patterns, table


def _recomputed() -> dict[str, dict[str, tuple[float | None, int]]]:
    benchmark = generate_asteria_agentic_v1()
    scored: dict[str, dict[str, tuple[float | None, int]]] = {}
    for path in sorted(EXAMPLES.glob("idealised-*.jsonl")):
        report = evaluate_agentic_trace(
            trace_submission_from_jsonl(path.read_text(encoding="utf-8")),
            benchmark=benchmark,
        )
        pattern = path.stem.removeprefix("idealised-")
        for metric in report.metrics:
            scored.setdefault(metric.name, {})[pattern] = (metric.value, metric.support)
    return scored


def test_block_markers_are_present() -> None:
    """Guard the guard: without markers the renderer silently no-ops."""

    text = DOC.read_text(encoding="utf-8")
    assert text.count(BEGIN) == 1
    assert text.count(END) == 1
    assert text.index(BEGIN) < text.index(END)


def test_published_numbers_match_the_scorer() -> None:
    _, published = _published()
    recomputed = _recomputed()

    for metric, cells in published.items():
        for pattern, (value, support) in cells.items():
            actual_value, actual_support = recomputed[metric][pattern]
            # Compare rounded floats, not strings: string equality would mask a
            # genuine change that happens to round to the same three decimals.
            expected = None if actual_value is None else round(actual_value, 3)
            assert value == expected, f"{metric}/{pattern}: {value} != {expected}"
            assert support == actual_support, f"{metric}/{pattern} support"


def test_every_emitted_metric_is_published() -> None:
    """Selection is an editorial lever; publishing all of them removes it.

    An earlier hand-curated revision showed 12 of 20, and one omission was the
    bearer baseline's perfect authorization_decision_recall.
    """

    _, published = _published()
    emitted = set(_recomputed())

    assert set(published) == emitted, (
        f"published but not emitted: {sorted(set(published) - emitted)}; "
        f"emitted but not published: {sorted(emitted - set(published))}"
    )


def test_every_pattern_is_published() -> None:
    patterns, _ = _published()
    on_disk = {
        path.stem.removeprefix("idealised-") for path in EXAMPLES.glob("*.jsonl")
    }

    assert set(patterns) == on_disk


@pytest.mark.parametrize(
    ("metric", "pattern", "expected"),
    [
        # The flattery vector, published deliberately: a pattern that allows every
        # action cannot lose a recall point. If this ever stops being 1.000 the
        # prose explaining it is stale and must be revisited.
        ("authorization_decision_recall", "static-bearer", 1.0),
        # And the counterweight the prose pairs it with.
        ("excess_authority_rate", "static-bearer", 1.0),
        ("authorization_decision_precision", "static-bearer", 0.364),
    ],
)
def test_readings_in_the_prose_still_hold(
    metric: str, pattern: str, expected: float
) -> None:
    """Pin the specific numbers the surrounding prose interprets."""

    _, published = _published()

    assert published[metric][pattern][0] == expected
