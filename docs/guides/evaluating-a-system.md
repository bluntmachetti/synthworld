# Evaluating a system

Give the system under test only input explicitly documented as public. Normalize its output into the task prediction or trace contract, then score against evaluator truth outside the product path.

```text
public input -> system under test -> prediction / trace
                                      |
evaluator truth ---------------------+--> metrics
```

Do not assume every generated bundle is product-safe. `generate-public-extraction`, `generate-public-connections`, and `generate-risk-public` emit product-facing projections. Outputs from evaluator or annotated commands such as `generate-extraction` and `generate-connection-benchmark` can contain expected answers and must not be passed wholesale to the system under test. For mixed-output commands, use only the subtree explicitly documented as `public/`.

**Run the walkthrough.** From a repository checkout:

```bash
uv sync --locked --all-groups
uv run python examples/evaluate_all.py --predictions-dir predictions
```

Replace an example rule with your own model, service, gateway, policy engine, or product while keeping the SynthWorld prediction-model construction as the adapter boundary.

**Validate before scoring.** Use a task validator where one exists. Structural validity means a submission can be scored; it does not mean the system performed well.

```bash
synthworld validate agentic-trace --predictions predictions/agentic.jsonl
```

Run the evaluator only after the system output is durably available. Do not expose evaluator truth to the adapter merely because a frozen reference fixture is publicly inspectable.

**Interpret metrics independently.** A `null` metric is not zero; it means the prediction set did not make that metric meaningful under the task's documented empty behavior. Do not hide weak dimensions behind an aggregate. Interpret every metric using its own denominator, support, polarity, scoring version, and empty behavior.

See the [metrics reference](../reference/metrics.md) and [DATA_DICTIONARY.md](../../DATA_DICTIONARY.md) for exact report contracts.

**Record enough to reproduce the run.** Retain benchmark identity, schema and scoring versions, seed and explicit configuration, artifact checksums, adapter/system provenance, and the exact prediction or trace bytes that were scored. A seed is one reproducibility input, not a substitute for the rest of the configuration.

Use the documentation site's Guides navigation for task-specific workflows. For exact command availability, use the [CLI reference](../reference/cli.md) and the installed command's `--help` output.
