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
    EvaluationReport,
    ExposureCorpus,
    LifecycleState,
    PublicIdentityRecord,
    always_deny_agentic_trace,
    current_state_agentic_trace,
    evaluate_agentic_trace,
    generate_adversarial_connection_benchmark,
    generate_asteria_agentic_v1,
    generate_exposure_corpus,
    run_all_baselines,
)
from synthworld.agentic.enterprise import (
    ENTERPRISE_AGENTIC_BASELINES,
    evaluate_enterprise_agentic_prediction,
    reference_enterprise_agentic,
)
from synthworld.ambiguity_floor import (
    FLOOR_BAND,
    FLOOR_PUBLICATION,
    MINIMUM_PREMIUM,
)
from synthworld.authority_governance import (
    AUTHORITY_GOVERNANCE_BASELINES,
    evaluate_authority_governance_prediction,
    reference_authority_governance,
)
from synthworld.contextual_access import (
    CONTEXTUAL_ACCESS_BASELINES,
    evaluate_contextual_access_prediction,
    reference_contextual_access,
)
from synthworld.continuous_assurance import (
    CONTINUOUS_ASSURANCE_BASELINES,
    evaluate_continuous_assurance_prediction,
    reference_continuous_assurance,
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
    agentic_benchmark = generate_asteria_agentic_v1()
    agentic_results = (
        (
            "Always deny",
            evaluate_agentic_trace(
                always_deny_agentic_trace(agentic_benchmark.public),
                benchmark=agentic_benchmark,
            ),
        ),
        (
            "Audit-time current state",
            evaluate_agentic_trace(
                current_state_agentic_trace(agentic_benchmark.public),
                benchmark=agentic_benchmark,
            ),
        ),
    )
    sections = [
        _render_intro(),
        _render_reproduce_section(),
        _render_baseline_section(baseline_results),
        _render_agentic_baseline_section(agentic_results),
        _render_enterprise_baseline_section(),
        _render_ambiguity_floor_section(),
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
            "art. Every number below is regenerated from the public-only "
            "baseline adapters by the command in [Reproduce](#reproduce). "
            "All data is safely synthetic.",
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


def _render_agentic_baseline_section(
    results: tuple[tuple[str, EvaluationReport], ...],
) -> str:
    header = "| Baseline | Metric | Score | Support |"
    divider = "|---|---|---|---|"
    metric_names = (
        "authorization_decision_accuracy",
        "authorization_decision_f1",
        "delegation_chain_integrity",
        "provenance_completeness",
        "provenance_exact_match",
        "provenance_precision",
    )
    rows = []
    for baseline_name, report in results:
        metrics = {metric.name: metric for metric in report.metrics}
        for metric_name in metric_names:
            metric = metrics[metric_name]
            score = "undefined" if metric.value is None else str(round(metric.value, 4))
            rows.append(
                f"| {baseline_name} | {metric_name} | {score} | {metric.support} |"
            )
    return "\n".join(
        [
            "## Asteria Agentic v1 baselines",
            "",
            "Both baselines consume only the public bundle. Always-deny shows "
            "why accuracy alone is misleading on a deny-heavy fixture; the "
            "current-state baseline shows why final audit state cannot replace "
            "historical replay.",
            "",
            header,
            divider,
            *rows,
        ]
    )


_ENTERPRISE_METRICS: dict[str, tuple[str, ...]] = {
    "Enterprise agentic": (
        "enterprise_decision_accuracy",
        "final_decision_accuracy",
        "failure_reason_exact_match",
        "delegation_gate_accuracy",
    ),
    "Contextual access": (
        "decision_accuracy",
        "stale_context_decision_accuracy",
        "canonical_event_application_exact_match",
        "predicate_outcome_accuracy",
    ),
    "Authority-change governance": (
        "governance_authorisation_accuracy",
        "structured_rationale_accuracy",
        "policy_control_accuracy",
    ),
    "Continuous assurance": (
        "drift_classification_accuracy",
        "finding_detection_recall",
        "false_negative_rate",
    ),
}


def _enterprise_family_rows(
    family: str, scored: tuple[tuple[str, object], ...]
) -> list[str]:
    """Render one row per (baseline, selected metric) for an enterprise family."""

    wanted = _ENTERPRISE_METRICS[family]
    rows: list[str] = []
    for baseline_name, report in scored:
        metrics = {m.name: m for m in report.metrics}  # type: ignore[attr-defined]
        for name in wanted:
            metric = metrics.get(name)
            if metric is None:
                continue
            value = "undefined" if metric.value is None else str(round(metric.value, 4))
            rows.append(
                f"| {family} | {baseline_name} | {name} | {value} "
                f"| {metric.denominator} |"
            )
    return rows


def _score_enterprise_families() -> list[str]:
    """Run every shipped enterprise baseline and render the selected metrics."""

    agentic = reference_enterprise_agentic()
    contextual = reference_contextual_access()
    governance = reference_authority_governance()
    assurance = reference_continuous_assurance()

    rows: list[str] = []
    rows += _enterprise_family_rows(
        "Enterprise agentic",
        tuple(
            (
                name,
                evaluate_enterprise_agentic_prediction(
                    public=agentic.public,
                    evaluator=agentic.evaluator,
                    prediction=build(agentic.evaluator),
                ),
            )
            for name, build in ENTERPRISE_AGENTIC_BASELINES
        ),
    )
    rows += _enterprise_family_rows(
        "Contextual access",
        tuple(
            (
                name,
                evaluate_contextual_access_prediction(
                    public=contextual.public,
                    evaluator=contextual.evaluator,
                    prediction=build(
                        public=contextual.public, evaluator=contextual.evaluator
                    ),
                ),
            )
            for name, build in CONTEXTUAL_ACCESS_BASELINES
        ),
    )
    rows += _enterprise_family_rows(
        "Authority-change governance",
        tuple(
            (
                name,
                evaluate_authority_governance_prediction(
                    public=governance.public,
                    evaluator=governance.evaluator,
                    prediction=build(governance.public),
                ),
            )
            for name, build in AUTHORITY_GOVERNANCE_BASELINES
        ),
    )
    rows += _enterprise_family_rows(
        "Continuous assurance",
        tuple(
            (
                name,
                evaluate_continuous_assurance_prediction(
                    public=assurance.public,
                    evaluator=assurance.evaluator,
                    prediction=build(assurance.public),
                ),
            )
            for name, build in CONTINUOUS_ASSURANCE_BASELINES
        ),
    )
    return rows


def _render_enterprise_baseline_section() -> str:
    """Render enterprise-family baselines, computed rather than transcribed."""

    rows = _score_enterprise_families()
    return "\n".join(
        [
            "## Enterprise authorization baselines",
            "",
            "Each of these consumes the shipped reference pack for its family "
            "and deliberately fails one dimension, so the score shows what the "
            "dimension detects. Only the metrics that separate the baselines "
            "are listed; every family publishes more, each with its own "
            "denominator and no aggregate.",
            "",
            "The reference packs are conformance fixtures, not statistical "
            "benchmarks — denominators here are in the tens, and their "
            "evaluator answer keys ship in the contract packages. A perfect "
            "score is evidence that an adapter conforms, never that a system "
            "generalises.",
            "",
            "| Family | Baseline | Metric | Score | Support |",
            "|---|---|---|---|---|",
            *rows,
        ]
    )


def _render_ambiguity_floor_section() -> str:
    """Render the published ambiguity v2 error floor, a build-time constant.

    The number is not recomputed here: it is pinned in `ambiguity_floor.
    FLOOR_PUBLICATION` by `examples/compute_ambiguity_floor.py`, and the suite's
    digest check fails if any decision-relevant constant moves without a
    recomputation. This only reads the pin, so the doc and the suite agree by
    construction.
    """

    low, high = FLOOR_BAND
    return "\n".join(
        [
            "## Ambiguity v2 error floor",
            "",
            "The v2 pack's difficulty is computed, not claimed: its **genie "
            "floor** is the Bayes error of the generator itself - the accuracy of "
            "an optimal solver restricted to the modelled observation (the rendered "
            "values, the comparable structure and the true prevalence) and holding "
            "the public law. Read the pack as a **hardness certificate**, not a "
            "capability leaderboard: the ceiling `1 - floor` is the most any system "
            "can achieve, and transcribing the published rule already reaches it, so "
            "the informative number is a resolver's **gap to the genie**. A score "
            "above the ceiling is exploiting signal the model says should not exist; "
            "a score within the genie's confidence interval is, statistically, at "
            "ceiling.",
            "",
            f"- Published floor: **{FLOOR_PUBLICATION.floor:.4f}** "
            f"(±{FLOOR_PUBLICATION.floor_half_width:.4f}, 95% Wilson interval)",
            f"- Ceiling `1 - floor`: **{FLOOR_PUBLICATION.genie_ceiling:.4f}**",
            f"- Technique premium: **{FLOOR_PUBLICATION.technique_premium:.4f}** "
            f"(gate ≥ {MINIMUM_PREMIUM})",
            f"- Floor band: [{low}, {high}]",
            f"- Estimated over {FLOOR_PUBLICATION.pair_count} pairs from "
            f"{FLOOR_PUBLICATION.seed_count} seeds",
            f"- Decision digest: `{FLOOR_PUBLICATION.digest}`",
            "",
            "The digest binds these numbers to every decision-relevant constant; "
            "any parameter move invalidates them until `examples/"
            "compute_ambiguity_floor.py` is rerun.",
        ]
    )


def _render_comparison_section() -> str:
    header = "| | Row-oriented fake data (Faker/SDV) | SynthWorld |"
    divider = "|---|---|---|"
    rows = [
        "| Records | Independent rows | Connected personas |",
        "| Linkage | None | Planted relationship edges and adversarial "
        "identity records that resolve to one entity |",
        "| Answer key | None | Exact-span, entity, relationship, risk, and "
        "agent-authority truth, physically separated from public input |",
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
            "- Asteria Agentic v1 is separately frozen at 24 events and 11 "
            "action attempts; it is a conformance fixture, not a statistical "
            "leaderboard.",
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
