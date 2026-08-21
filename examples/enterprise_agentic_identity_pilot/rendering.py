"""Deterministic evaluator-only reporting for the identity pilot.

This module is intentionally experiment-owned.  It renders a comparison of
already-computed evaluation reports; it is not an Explorer projection, a policy
engine, or a path for passing evaluator truth to a system under test.
"""

from __future__ import annotations

import html
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from synthworld.evaluation import EvaluationReport, TaskMetric

EVALUATOR_WATERMARK = "EVALUATOR VIEW - CONTAINS REFERENCE TRUTH"

_SELECTED_METRICS = (
    "authorization_decision_accuracy",
    "authorization_decision_precision",
    "authorization_decision_recall",
    "least_privilege_accuracy",
    "excess_authority_rate",
    "temporal_validity_accuracy",
)


@dataclass(frozen=True, slots=True)
class _StrategyResult:
    label: str
    report: EvaluationReport
    metrics: tuple[TaskMetric, ...]

    @property
    def combined(self) -> bool:
        return self.label.casefold() == "combined"


def evaluator_report_summary(
    *,
    world_summary: Mapping[str, int | str],
    strategy_reports: Sequence[tuple[str, EvaluationReport]],
) -> dict[str, object]:
    """Return a JSON-shaped, evaluator-marked summary of the rendered inputs."""

    world, strategies = _validated_inputs(world_summary, strategy_reports)
    reference = strategies[0].report
    return {
        "artifact_kind": "enterprise-agentic-identity-pilot-evaluator-report",
        "benchmark": {
            "artifact_checksums": [list(item) for item in reference.artifact_checksums],
            "benchmark_version": reference.benchmark_version,
            "checksum_scheme": reference.checksum_scheme,
            "scoring_version": reference.scoring_version,
            "seed": reference.seed,
            "task": reference.task,
        },
        "strategies": [
            {
                "combined": strategy.combined,
                "label": strategy.label,
                "metrics": [
                    {
                        "family": metric.family,
                        "name": metric.name,
                        "support": metric.support,
                        "support_meaning": metric.support_meaning,
                        "value": metric.value,
                    }
                    for metric in strategy.metrics
                ],
            }
            for strategy in strategies
        ],
        "visibility": "evaluator",
        "watermark": EVALUATOR_WATERMARK,
        "world_summary": dict(world),
    }


def canonical_evaluator_report_summary_bytes(
    *,
    world_summary: Mapping[str, int | str],
    strategy_reports: Sequence[tuple[str, EvaluationReport]],
) -> bytes:
    """Serialize the evaluator summary as canonical UTF-8 JSON."""

    summary = evaluator_report_summary(
        world_summary=world_summary,
        strategy_reports=strategy_reports,
    )
    serialized = json.dumps(
        summary,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"{serialized}\n".encode()


def render_evaluator_report_html(
    *,
    world_summary: Mapping[str, int | str],
    strategy_reports: Sequence[tuple[str, EvaluationReport]],
) -> bytes:
    """Render one deterministic, self-contained evaluator comparison report."""

    world, strategies = _validated_inputs(world_summary, strategy_reports)
    reference = strategies[0].report
    summary_cards = "".join(
        '<div class="summary-item">'
        f"<dt>{_escape(_display_name(key))}</dt>"
        f"<dd>{_escape(str(value))}</dd>"
        "</div>"
        for key, value in world
    )
    metric_rows = "".join(
        _metric_row(strategy, metric)
        for strategy in strategies
        for metric in strategy.metrics
    )
    checksum_rows = "".join(
        '<div class="binding-row">'
        f"<dt>{_escape(name)}</dt><dd><code>{_escape(digest)}</code></dd>"
        "</div>"
        for name, digest in reference.artifact_checksums
    )
    csp = (
        "default-src 'none'; img-src data:; style-src 'unsafe-inline'; "
        "script-src 'none'; connect-src 'none'; font-src 'none'; "
        "object-src 'none'; base-uri 'none'; form-action 'none'"
    )
    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{csp}">
<title>Enterprise agentic identity policy pilot</title>
<style>
:root {{
  color-scheme: light dark;
  --background: #f5f7fb;
  --surface: #ffffff;
  --surface-muted: #eef2f7;
  --foreground: #172033;
  --muted: #586579;
  --border: #cfd7e3;
  --accent: #3157b7;
  --accent-soft: #e7edff;
  --danger: #8f1d2c;
  --danger-soft: #fde8eb;
  --track: #dfe5ee;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --background: #111827;
    --surface: #182235;
    --surface-muted: #202d43;
    --foreground: #eef3fb;
    --muted: #b4bfd0;
    --border: #3c4b62;
    --accent: #8aabff;
    --accent-soft: #24375e;
    --danger: #ff9aa8;
    --danger-soft: #4d2029;
    --track: #344258;
  }}
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background: var(--background);
  color: var(--foreground);
  font-family:
    ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI",
    sans-serif;
  line-height: 1.5;
}}
.watermark {{
  padding: 0.85rem 1rem;
  background: var(--danger);
  color: #ffffff;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-align: center;
}}
.shell {{
  width: min(1180px, calc(100% - 2rem));
  margin: 0 auto;
  padding: 2rem 0 3rem;
}}
h1, h2, h3 {{ line-height: 1.2; }}
h1 {{ margin: 0; font-size: clamp(1.8rem, 5vw, 3.1rem); }}
h2 {{ margin: 0 0 1rem; font-size: 1.45rem; }}
h3 {{ margin: 0 0 0.35rem; font-size: 1rem; }}
p {{ margin: 0; }}
.eyebrow {{
  color: var(--accent);
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.11em;
  text-transform: uppercase;
}}
.hero {{ display: grid; gap: 1rem; margin-bottom: 2rem; }}
.lede {{ max-width: 78ch; color: var(--muted); }}
.identity {{
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 1rem;
  color: var(--muted);
  font-size: 0.9rem;
}}
.identity strong {{ color: var(--foreground); }}
section {{ margin-top: 2.25rem; }}
.summary-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(145px, 1fr));
  gap: 0.75rem;
  margin: 0;
}}
.summary-item {{
  padding: 0.9rem 1rem;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 0.55rem;
}}
.summary-item dt {{
  color: var(--muted);
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}}
.summary-item dd {{
  margin: 0.25rem 0 0;
  font-size: 1.25rem;
  font-weight: 700;
  overflow-wrap: anywhere;
}}
.architecture {{
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.75rem;
}}
.architecture article {{
  position: relative;
  padding: 1rem;
  background: var(--surface);
  border-top: 0.3rem solid var(--accent);
}}
.architecture article:not(:last-child)::after {{
  content: "→";
  position: absolute;
  right: -0.68rem;
  top: 50%;
  z-index: 1;
  color: var(--accent);
  font-size: 1.25rem;
  font-weight: 700;
}}
.architecture p {{ color: var(--muted); font-size: 0.9rem; }}
.architecture .combined {{ background: var(--accent-soft); }}
.architecture-note {{ margin-top: 0.85rem; color: var(--muted); }}
.table-wrap {{ overflow-x: auto; }}
table {{
  width: 100%;
  border-collapse: collapse;
  background: var(--surface);
  font-size: 0.9rem;
}}
caption {{ padding: 0 0 0.75rem; color: var(--muted); text-align: left; }}
th, td {{
  padding: 0.75rem;
  border-bottom: 1px solid var(--border);
  text-align: left;
  vertical-align: top;
}}
th {{
  background: var(--surface-muted);
  font-size: 0.78rem;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}}
tbody tr:last-child td {{ border-bottom: 0; }}
tr.combined-row {{ background: var(--accent-soft); }}
.strategy {{ font-weight: 700; white-space: nowrap; }}
.recommended {{
  display: block;
  margin-top: 0.2rem;
  color: var(--accent);
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}}
.metric-name {{ min-width: 14rem; }}
.score {{ min-width: 8rem; }}
.score-value {{
  display: block;
  margin-bottom: 0.35rem;
  font-variant-numeric: tabular-nums;
}}
.score-track {{
  display: block;
  width: 7rem;
  height: 0.42rem;
  background: var(--track);
  border-radius: 999px;
  overflow: hidden;
}}
.score-fill {{ display: block; height: 100%; background: var(--accent); }}
.undefined {{ color: var(--muted); }}
.support {{
  text-align: right;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}}
.meaning {{ min-width: 19rem; color: var(--muted); }}
.interpretation {{ margin-top: 0.85rem; color: var(--muted); }}
details {{
  margin-top: 2.25rem;
  padding: 1rem;
  border: 1px solid var(--border);
  background: var(--surface);
}}
summary {{ cursor: pointer; font-weight: 700; }}
.bindings {{
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  gap: 0.45rem 1rem;
  margin: 1rem 0 0;
}}
.binding-row {{ display: contents; }}
.bindings dt {{ color: var(--muted); }}
.bindings dd {{ margin: 0; min-width: 0; overflow-wrap: anywhere; }}
footer {{
  margin-top: 2.25rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border);
  color: var(--muted);
  font-size: 0.85rem;
}}
@media (max-width: 760px) {{
  .architecture {{ grid-template-columns: 1fr; }}
  .architecture article:not(:last-child)::after {{
    content: "↓";
    right: 50%;
    top: auto;
    bottom: -1.05rem;
  }}
}}
@media print {{
  :root {{ color-scheme: light; }}
  body {{ background: #ffffff; }}
  .shell {{ width: 100%; }}
  .table-wrap {{ overflow: visible; }}
  details {{ break-inside: avoid; }}
}}
</style>
</head>
<body>
<div class="watermark" role="note">{EVALUATOR_WATERMARK}</div>
<main class="shell">
  <header class="hero">
    <div class="eyebrow">SynthWorld / experiment-owned policy comparison</div>
    <h1>Enterprise agentic identity pilot</h1>
    <p class="lede">
      A deterministic offline comparison of authorization strategies over one
      synthetic public identity world and its separately evaluated authority truth.
      This report is not a policy engine, deployment result, vendor comparison, or
      SynthWorld Explorer artifact.
    </p>
    <div class="identity">
      <span><strong>Task:</strong> {_escape(reference.task)}</span>
      <span><strong>Benchmark:</strong> {_escape(reference.benchmark_version)}</span>
      <span><strong>Seed:</strong> {reference.seed}</span>
      <span><strong>Scoring:</strong> {_escape(reference.scoring_version)}</span>
    </div>
  </header>

  <section aria-labelledby="world-heading">
    <h2 id="world-heading">Public world inventory</h2>
    <dl class="summary-grid">{summary_cards}</dl>
  </section>

  <section aria-labelledby="architecture-heading">
    <h2 id="architecture-heading">Policy architecture</h2>
    <div class="architecture">
      <article>
        <h3>RBAC ceiling</h3>
        <p>
          Coarse job-function entitlement establishes whether the agent is eligible
          for the action.
        </p>
      </article>
      <article>
        <h3>ReBAC authority path</h3>
        <p>
          An active, resource-covering delegated relationship must connect the
          originator, agent and target.
        </p>
      </article>
      <article>
        <h3>ABAC guard</h3>
        <p>
          Tenant, runtime, credential, purpose, scope, action and policy-version
          context must remain valid.
        </p>
      </article>
      <article class="combined">
        <h3>Combined decision</h3>
        <p>
          Default deny. RBAC, ReBAC and ABAC must all allow; downstream lifecycle
          and revocation checks still apply.
        </p>
      </article>
    </div>
    <p class="architecture-note">
      Human-owner authority is not unioned into agent authority. The combined
      strategy is highlighted as the proposed least-authority composition, not as
      an automatically recommended production policy.
    </p>
  </section>

  <section aria-labelledby="metrics-heading">
    <h2 id="metrics-heading">Strategy evaluation</h2>
    <div class="table-wrap">
      <table>
        <caption>
          Independent metrics from the evaluator. Every value retains its
          scorer-provided support and denominator meaning; no aggregate score is
          calculated.
        </caption>
        <thead>
          <tr>
            <th scope="col">Strategy</th>
            <th scope="col">Metric</th>
            <th scope="col">Value</th>
            <th scope="col">Support</th>
            <th scope="col">Support / denominator meaning</th>
          </tr>
        </thead>
        <tbody>{metric_rows}</tbody>
      </table>
    </div>
    <p class="interpretation">
      Accuracy, precision and recall describe different decision populations.
      Least-privilege accuracy and excess-authority rate are complements over
      truth-denied actions. Temporal validity is restricted to explicitly labelled
      timing cases. Undefined values remain undefined rather than being coerced to
      zero.
    </p>
  </section>

  <details>
    <summary>Reproducibility bindings</summary>
    <dl class="bindings">
      <div class="binding-row">
        <dt>Checksum scheme</dt>
        <dd>{_escape(reference.checksum_scheme)}</dd>
      </div>
      {checksum_rows}
    </dl>
  </details>

  <footer>
    {EVALUATOR_WATERMARK} · Keep this report outside the public system-under-test
    path.
  </footer>
</main>
</body>
</html>
"""
    return document.encode()


def write_evaluator_report_html(
    output: Path,
    *,
    world_summary: Mapping[str, int | str],
    strategy_reports: Sequence[tuple[str, EvaluationReport]],
) -> None:
    """Write a new evaluator report without replacing an existing file."""

    payload = render_evaluator_report_html(
        world_summary=world_summary,
        strategy_reports=strategy_reports,
    )
    with output.open("xb") as destination:
        destination.write(payload)


def _validated_inputs(
    world_summary: Mapping[str, int | str],
    strategy_reports: Sequence[tuple[str, EvaluationReport]],
) -> tuple[tuple[tuple[str, int | str], ...], tuple[_StrategyResult, ...]]:
    if not world_summary:
        raise ValueError("world summary must not be empty")
    world: list[tuple[str, int | str]] = []
    world_keys: set[str] = set()
    for key, value in sorted(world_summary.items()):
        normalized_key = key.strip()
        if not normalized_key:
            raise ValueError("world summary keys must be nonblank")
        if normalized_key in world_keys:
            raise ValueError("normalized world summary keys must be unique")
        world_keys.add(normalized_key)
        if isinstance(value, str) and not value.strip():
            raise ValueError("world summary string values must be nonblank")
        world.append((normalized_key, value))

    if not strategy_reports:
        raise ValueError("at least one strategy report is required")
    strategies: list[_StrategyResult] = []
    labels: set[str] = set()
    reference_identity: tuple[object, ...] | None = None
    for raw_label, report in strategy_reports:
        label = raw_label.strip()
        normalized_label = label.casefold()
        if not label:
            raise ValueError("strategy labels must be nonblank")
        if normalized_label in labels:
            raise ValueError("strategy labels must be unique")
        labels.add(normalized_label)
        identity = (
            report.task,
            report.seed,
            report.persona_count,
            report.benchmark_version,
            report.scoring_version,
            report.checksum_scheme,
            report.artifact_checksums,
        )
        if reference_identity is None:
            reference_identity = identity
        elif identity != reference_identity:
            raise ValueError("strategy reports must bind the same benchmark")
        metrics_by_name = {metric.name: metric for metric in report.metrics}
        missing = tuple(
            name for name in _SELECTED_METRICS if name not in metrics_by_name
        )
        if missing:
            raise ValueError(
                f"strategy report {label!r} is missing required metrics: {missing}"
            )
        selected = tuple(metrics_by_name[name] for name in _SELECTED_METRICS)
        for metric in selected:
            if metric.value is not None and not 0.0 <= metric.value <= 1.0:
                raise ValueError(
                    f"strategy report {label!r} metric {metric.name!r} "
                    "must be a proportion between zero and one"
                )
        strategies.append(_StrategyResult(label=label, report=report, metrics=selected))
    return tuple(world), tuple(strategies)


def _metric_row(strategy: _StrategyResult, metric: TaskMetric) -> str:
    row_class = ' class="combined-row"' if strategy.combined else ""
    recommendation = (
        '<span class="recommended">Proposed composition</span>'
        if strategy.combined
        else ""
    )
    if metric.value is None:
        score = '<span class="score-value undefined">undefined</span>'
    else:
        width = f"{metric.value * 100:.4f}%"
        score = (
            f'<span class="score-value">{metric.value:.4f}</span>'
            '<span class="score-track" aria-hidden="true">'
            f'<span class="score-fill" style="width:{width}"></span></span>'
        )
    meaning = metric.support_meaning or "support reported by the scorer"
    return (
        f"<tr{row_class}>"
        f'<th class="strategy" scope="row">{_escape(strategy.label)}'
        f"{recommendation}</th>"
        f'<td class="metric-name"><code>{_escape(metric.name)}</code></td>'
        f'<td class="score">{score}</td>'
        f'<td class="support">{metric.support}</td>'
        f'<td class="meaning">{_escape(meaning)}</td>'
        "</tr>"
    )


def _display_name(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").strip().title()


def _escape(value: str) -> str:
    return html.escape(value, quote=True)


__all__ = [
    "EVALUATOR_WATERMARK",
    "canonical_evaluator_report_summary_bytes",
    "evaluator_report_summary",
    "render_evaluator_report_html",
    "write_evaluator_report_html",
]
