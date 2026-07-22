"""Generate BENCHMARKS.md and its SVG visuals: baselines and demonstrations.

SynthWorld's benchmarks are only useful if it is easy to see what they
measure. This script renders ``run_all_baselines()``'s scores into a table
and pulls a handful of records straight out of the pinned-seed connection and
exposure corpora to draw as deterministic SVG diagrams, so the document and
its assets can never drift from the code that produces them. SVG (rather than
Mermaid) renders everywhere the README travels, including PyPI.

Run with:

    uv run python examples/generate_benchmarks_doc.py

Check for drift (what `make baselines` runs) with:

    uv run python examples/generate_benchmarks_doc.py --check
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

from synthworld import (
    BASELINE_PERSONA_COUNT,
    BASELINE_SEED,
    BaselineResult,
    BrokerExposure,
    ConnectionBenchmark,
    ExposureCorpus,
    LifecycleState,
    PublicIdentityRecord,
    generate_adversarial_connection_benchmark,
    generate_exposure_corpus,
    run_all_baselines,
)

_ROOT = Path(__file__).resolve().parents[1]
_DOC_PATH = _ROOT / "BENCHMARKS.md"
_ASSETS = Path("assets")
_CONFLICTING_SVG = _ASSETS / "benchmark-conflicting-records.svg"
_TIMELINE_SVG = _ASSETS / "benchmark-broker-timeline.svg"
_SPLIT_SVG = _ASSETS / "benchmark-public-oracle-split.svg"

_FONT = (
    "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, "
    "Helvetica, Arial, sans-serif"
)
_ARROW_DEFS = (
    '<defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="7" '
    'refY="3" orient="auto" markerUnits="strokeWidth">'
    '<path d="M0,0 L7,3 L0,6 Z" fill="#64748b"/></marker></defs>'
)
_TEXT_COLOR = "#0f172a"
_ARROW_COLOR = "#64748b"
_STATE_COLORS: dict[LifecycleState, tuple[str, str]] = {
    LifecycleState.FOUND: ("#e2e8f0", "#94a3b8"),
    LifecycleState.REMOVAL_REQUESTED: ("#fef9c3", "#ca8a04"),
    LifecycleState.CONFIRMED_REMOVED: ("#dcfce7", "#16a34a"),
    LifecycleState.REAPPEARED: ("#fee2e2", "#dc2626"),
}


def build_artifacts() -> dict[Path, str]:
    """Return every generated file (the doc and its SVGs) keyed by path."""

    connection_benchmark = generate_adversarial_connection_benchmark(seed=BASELINE_SEED)
    exposure_corpus = generate_exposure_corpus(
        seed=BASELINE_SEED,
        persona_count=BASELINE_PERSONA_COUNT,
    )
    return {
        _CONFLICTING_SVG: _conflicting_records_svg(connection_benchmark),
        _TIMELINE_SVG: _broker_timeline_svg(exposure_corpus),
        _SPLIT_SVG: _public_oracle_split_svg(),
        _DOC_PATH: _render_doc(run_all_baselines()),
    }


def _render_doc(results: tuple[BaselineResult, ...]) -> str:
    sections = [
        _render_intro(),
        _render_reproduce_section(),
        _render_baseline_section(results),
        _render_comparison_section(),
        _render_visuals_section(),
        _render_limits_section(),
    ]
    return "\n\n".join(sections) + "\n"


def _render_intro() -> str:
    return "\n".join(
        [
            "# SynthWorld baselines and benchmark demonstrations",
            "",
            "These are deliberately naive reference baselines: each score "
            "illustrates what its benchmark *measures*, not the state of the "
            "art. Every number below is reproducible from "
            '`uv run python -c "from synthworld import run_all_baselines; '
            '..."` or the command in [Reproduce](#reproduce). All data is '
            "safely synthetic.",
        ]
    )


def _render_reproduce_section() -> str:
    return "\n".join(
        [
            "## Reproduce",
            "",
            "```bash",
            "uv run python examples/generate_benchmarks_doc.py",
            "```",
            "",
            "This regenerates the results table and the SVG visuals under "
            "`assets/`. `make baselines` checks the document and its assets "
            "for drift in CI.",
        ]
    )


def _render_baseline_section(results: tuple[BaselineResult, ...]) -> str:
    header = "| Baseline | Task | Metric | Score | Notes |"
    divider = "|---|---|---|---|---|"
    rows = [
        f"| {result.name} | {result.task} | {result.metric} | {result.score} "
        f"| {result.detail} |"
        for result in results
    ]
    return "\n".join(["## Baseline results", "", header, divider, *rows])


def _render_comparison_section() -> str:
    header = "| | Row-oriented fake data (Faker/SDV) | SynthWorld |"
    divider = "|---|---|---|"
    rows = [
        "| Records | Independent rows | Connected personas |",
        "| Linkage | None | Planted relationship edges and adversarial "
        "identity records that resolve to one entity |",
        "| Answer key | None | Exact-span, entity, relationship, and risk "
        "truth, physically separated from public input |",
    ]
    return "\n".join(
        ["## Why SynthWorld, not a row generator", "", header, divider, *rows]
    )


def _render_visuals_section() -> str:
    return "\n\n".join(
        [
            "## What the visuals show",
            "\n".join(
                [
                    "### A. One persona, conflicting public records",
                    "",
                    f"![One entity linked to three identity records with "
                    f"different name spellings]({_CONFLICTING_SVG.as_posix()})",
                    "",
                    "*One real person surfaces under three spellings across "
                    "three sources; the answer key knows they are one entity.*",
                ]
            ),
            "\n".join(
                [
                    "### B. Broker removal and reappearance timeline",
                    "",
                    f"![A broker listing moving from found to removal requested "
                    f"to confirmed removed to reappeared]"
                    f"({_TIMELINE_SVG.as_posix()})",
                    "",
                    "*A listing confirmed removed can reappear at a later "
                    "virtual date; the benchmark plants this so removal-"
                    "tracking systems can be tested.*",
                ]
            ),
            "\n".join(
                [
                    "### C. Public input vs evaluator truth",
                    "",
                    f"![Public corpus feeding a system under test whose "
                    f"predictions are scored against a separate answer key]"
                    f"({_SPLIT_SVG.as_posix()})",
                    "",
                    "*Products consume only the public projection; evaluators "
                    "join the separately serialized truth to score.*",
                ]
            ),
        ]
    )


def _render_limits_section() -> str:
    return "\n".join(
        [
            "## Size and limits",
            "",
            f"- The benchmarks are frozen at seed `{BASELINE_SEED}`, "
            f"{BASELINE_PERSONA_COUNT} personas (18 records for the "
            "adversarial entity-resolution pack).",
            "- Baselines are intentionally simple and are NOT state of the art.",
            "- Scores illustrate the benchmark's discriminative power, not "
            "system quality.",
            "- Numbers change only through a deliberate benchmark-version transition.",
            "",
            "See [DATA_DICTIONARY.md](DATA_DICTIONARY.md) for field "
            "definitions and [GOLDEN_REVIEW.md](GOLDEN_REVIEW.md) for the "
            "frozen benchmark review record.",
        ]
    )


def _conflicting_records_svg(benchmark: ConnectionBenchmark) -> str:
    records = _shared_entity_records(benchmark)
    body = [
        _box(24, 96, 150, 48, "#dbeafe", "#2563eb"),
        _text(99, 120, "One entity", weight="600"),
    ]
    for index, record in enumerate(records):
        top = 24 + index * 72
        center = top + 24
        body.append(_arrow(174, 120, 330, center))
        body.append(_box(330, top, 286, 48, "#f1f5f9", "#94a3b8"))
        body.append(
            _text(473, center, f"{record.source_type.value}: {record.display_name}")
        )
    return _svg(640, 240, body)


def _shared_entity_records(
    benchmark: ConnectionBenchmark,
) -> tuple[PublicIdentityRecord, ...]:
    """Return the records for the one entity with exactly three memberships."""

    grouped: dict[str, list[UUID]] = {}
    for membership in benchmark.answer_key.record_memberships:
        grouped.setdefault(membership.entity_id, []).append(membership.record_id)
    shared_entity_id = next(
        entity_id for entity_id, record_ids in grouped.items() if len(record_ids) == 3
    )
    records_by_id = {record.id: record for record in benchmark.public.identity_records}
    return tuple(records_by_id[record_id] for record_id in grouped[shared_entity_id])


def _broker_timeline_svg(corpus: ExposureCorpus) -> str:
    broker = _first_reappeared_broker(corpus)
    body: list[str] = []
    for index, event in enumerate(broker.lifecycle):
        left = 20 + index * 204
        center = left + 80
        fill, stroke = _STATE_COLORS[event.state]
        if index > 0:
            body.append(_arrow(left - 44, 60, left, 60))
        body.append(_box(left, 30, 160, 60, fill, stroke))
        body.append(_text(center, 54, event.at.isoformat(), size=12, weight="600"))
        body.append(_text(center, 73, event.state.value, size=13))
    return _svg(20 + len(broker.lifecycle) * 204, 120, body)


def _first_reappeared_broker(corpus: ExposureCorpus) -> BrokerExposure:
    """Return the first broker (script order, then broker order) that reappears."""

    for script in corpus.exposure_scripts:
        for broker in script.brokers:
            if any(
                event.state is LifecycleState.REAPPEARED for event in broker.lifecycle
            ):
                return broker
    raise ValueError("no broker lifecycle contains a reappeared state")


def _public_oracle_split_svg() -> str:
    public = ("#dbeafe", "#2563eb")
    truth = ("#fee2e2", "#dc2626")
    neutral = ("#f1f5f9", "#94a3b8")
    body = [
        _box(40, 24, 200, 52, *public),
        _text(140, 50, "Public corpus", weight="600"),
        _box(40, 114, 200, 52, *neutral),
        _text(140, 140, "System under test"),
        _box(40, 204, 200, 52, *neutral),
        _text(140, 230, "Predictions"),
        _box(360, 24, 200, 52, *truth),
        _text(460, 50, "Answer key", weight="600"),
        _box(360, 114, 200, 52, *neutral),
        _text(460, 140, "Scorer"),
        _box(360, 204, 200, 52, *neutral),
        _text(460, 230, "Scored results"),
        _arrow(140, 76, 140, 114),
        _arrow(140, 166, 140, 204),
        _arrow(460, 76, 460, 114),
        _arrow(240, 230, 360, 156),
        _arrow(460, 166, 460, 204),
    ]
    return _svg(600, 280, body)


def _svg(width: int, height: int, body: list[str]) -> str:
    header = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" font-family="{_FONT}">'
    )
    return "\n".join([header, _ARROW_DEFS, *body, "</svg>", ""])


def _box(x: int, y: int, width: int, height: int, fill: str, stroke: str) -> str:
    return (
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="8" ry="8" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>'
    )


def _text(
    center_x: int,
    center_y: int,
    label: str,
    *,
    size: int = 14,
    weight: str = "400",
) -> str:
    return (
        f'<text x="{center_x}" y="{center_y}" text-anchor="middle" '
        f'dominant-baseline="central" font-size="{size}" font-weight="{weight}" '
        f'fill="{_TEXT_COLOR}">{_escape(label)}</text>'
    )


def _arrow(x1: int, y1: int, x2: int, y2: int) -> str:
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{_ARROW_COLOR}" '
        f'stroke-width="2" marker-end="url(#arrow)"/>'
    )


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="generate_benchmarks_doc")
    parser.add_argument(
        "--check",
        action="store_true",
        help="check the document and its assets for drift instead of writing",
    )
    args = parser.parse_args(argv)

    artifacts = build_artifacts()
    if args.check:
        drifted = [
            relative
            for relative, content in _relative(artifacts).items()
            if _read(relative) != content
        ]
        if drifted:
            names = ", ".join(sorted(path.as_posix() for path in drifted))
            print(
                f"Out of date: {names}; run "
                "`uv run python examples/generate_benchmarks_doc.py` to regenerate.",
                file=sys.stderr,
            )
            return 1
        print("BENCHMARKS.md and assets are up to date")
        return 0

    for relative, content in _relative(artifacts).items():
        absolute = _ROOT / relative
        absolute.parent.mkdir(parents=True, exist_ok=True)
        absolute.write_text(content, encoding="utf-8")
    return 0


def _relative(artifacts: dict[Path, str]) -> dict[Path, str]:
    return {
        (path if not path.is_absolute() else path.relative_to(_ROOT)): content
        for path, content in artifacts.items()
    }


def _read(relative: Path) -> str | None:
    absolute = _ROOT / relative
    return absolute.read_text(encoding="utf-8") if absolute.exists() else None


if __name__ == "__main__":
    raise SystemExit(main())
