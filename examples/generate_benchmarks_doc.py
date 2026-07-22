"""Generate BENCHMARKS.md: naive reference baselines and visual demonstrations.

SynthWorld's benchmarks are only useful if it is easy to see what they
measure. This script renders ``run_all_baselines()``'s scores into a table
and pulls a handful of records straight out of the pinned-seed connection
and exposure corpora to render as Mermaid diagrams, so BENCHMARKS.md can
never drift from the code that produces it.

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

_OUTPUT_PATH = Path(__file__).resolve().parents[1] / "BENCHMARKS.md"


def render_benchmarks_doc() -> str:
    """Render the full BENCHMARKS.md content deterministically."""

    baseline_results = run_all_baselines()
    connection_benchmark = generate_adversarial_connection_benchmark(seed=BASELINE_SEED)
    exposure_corpus = generate_exposure_corpus(
        seed=BASELINE_SEED,
        persona_count=BASELINE_PERSONA_COUNT,
    )
    sections = [
        _render_intro(),
        _render_reproduce_section(),
        _render_baseline_section(baseline_results),
        _render_comparison_section(),
        _render_visuals_section(connection_benchmark, exposure_corpus),
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
            "`make baselines` checks this file for drift in CI.",
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


def _render_visuals_section(
    connection_benchmark: ConnectionBenchmark,
    exposure_corpus: ExposureCorpus,
) -> str:
    parts = [
        "## What the visuals show",
        _render_visual_a(connection_benchmark),
        _render_visual_b(exposure_corpus),
        _render_visual_c(),
    ]
    return "\n\n".join(parts)


def _render_visual_a(benchmark: ConnectionBenchmark) -> str:
    records = _shared_entity_records(benchmark)
    lines = ["```mermaid", "flowchart LR", '    entity["One entity"]']
    for index, record in enumerate(records):
        node_id = f"record{index}"
        label = f"{record.source_type.value}: {record.display_name}"
        lines.append(f'    entity --> {node_id}["{label}"]')
    lines.append("```")
    caption = (
        "*One real person surfaces under three spellings across three "
        "sources; the answer key knows they are one entity.*"
    )
    return "\n".join(
        ["### A. One persona, conflicting public records", "", *lines, "", caption]
    )


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


def _render_visual_b(corpus: ExposureCorpus) -> str:
    broker = _first_reappeared_broker(corpus)
    node_labels = [
        f'state{index}["{event.at.isoformat()}<br/>{event.state.value}"]'
        for index, event in enumerate(broker.lifecycle)
    ]
    chain = " --> ".join(node_labels)
    caption = (
        "*A listing confirmed removed can reappear at a later virtual date; "
        "the benchmark plants this so removal-tracking systems can be "
        "tested.*"
    )
    return "\n".join(
        [
            "### B. Broker removal and reappearance timeline",
            "",
            "```mermaid",
            "flowchart LR",
            f"    {chain}",
            "```",
            "",
            caption,
        ]
    )


def _first_reappeared_broker(corpus: ExposureCorpus) -> BrokerExposure:
    """Return the first broker (script order, then broker order) that reappears."""

    for script in corpus.exposure_scripts:
        for broker in script.brokers:
            if any(
                event.state is LifecycleState.REAPPEARED for event in broker.lifecycle
            ):
                return broker
    raise ValueError("no broker lifecycle contains a reappeared state")


def _render_visual_c() -> str:
    caption = (
        "*Products consume only the public projection; evaluators join the "
        "separately serialized truth to score.*"
    )
    return "\n".join(
        [
            "### C. Public input vs evaluator truth",
            "",
            "```mermaid",
            "flowchart TD",
            '    public["Public corpus"] --> sut["System under test"]',
            '    sut --> predictions["Predictions"]',
            '    answers["Separately serialized answer key"] --> scorer["Scorer"]',
            "    predictions --> scorer",
            '    scorer --> results["Scored results"]',
            "```",
            "",
            caption,
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="generate_benchmarks_doc")
    parser.add_argument(
        "--check",
        action="store_true",
        help="check BENCHMARKS.md for drift instead of writing it",
    )
    args = parser.parse_args(argv)

    text = render_benchmarks_doc()
    if args.check:
        current = (
            _OUTPUT_PATH.read_text(encoding="utf-8") if _OUTPUT_PATH.exists() else None
        )
        if current != text:
            print(
                f"{_OUTPUT_PATH.name} is out of date; run "
                "`uv run python examples/generate_benchmarks_doc.py` to regenerate.",
                file=sys.stderr,
            )
            return 1
        print(f"{_OUTPUT_PATH.name} is up to date")
        return 0

    _OUTPUT_PATH.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
