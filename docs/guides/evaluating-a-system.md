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

## Relationship-inference workflow

Use this task to test whether a system infers a relationship only when public
evidence supports it. The corpus includes unilateral associations specifically
to catch systems that infer too much from one weak signal.

Generate only the public product input:

```bash
synthworld generate-public-connections \
  --seed 20260719 \
  --persona-count 10 \
  --output relationship-input.json
```

Give `relationship-input.json` to the system under test. Normalize its output as
a `RelationshipPrediction`: each edge names two public records, the relationship
kind, and the public association records cited as evidence. The identifiers below
are placeholders; use identifiers from the generated input.

```json
{
  "schema_version": "0.1.0",
  "edges": [
    {
      "source_record_id": "record-uuid-a",
      "target_record_id": "record-uuid-b",
      "kind": "neighbor",
      "evidence_association_ids": ["association-uuid-a", "association-uuid-b"]
    }
  ]
}
```

Save that document as `relationship-prediction.json`, then score it with the same
seed and persona count used to create the public input:

```bash
synthworld evaluate relationship \
  --predictions relationship-prediction.json \
  --seed 20260719 \
  --persona-count 10
```

The report separates edge quality from citation quality, so a correct
relationship with unsupported evidence remains visible. Do not give the system
the output of `generate-connection-benchmark`; that annotated artifact contains
evaluator truth.

**Validate before scoring.** Use a task validator where one exists. Structural validity means a submission can be scored; it does not mean the system performed well.

```bash
synthworld validate agentic-trace --predictions predictions/agentic.jsonl
```

Generated enterprise-agentic worlds have an explicit artifact-root workflow in
0.15.0. The validator reads only `public/`; the evaluator subsequently requires the
complete checksum-bound root:

```bash
synthworld validate generated-enterprise-agentic-trace \
  --benchmark-root generated-enterprise-agentic \
  --predictions predictions/generated-agentic.jsonl
synthworld evaluate generated-enterprise-agentic \
  --benchmark-root generated-enterprise-agentic \
  --predictions predictions/generated-agentic.jsonl \
  --summary
```

The adapter must replay public events in their declared order and query the system
at each action event. See [Agent authority](agent-authority.md) for the temporal,
topology, policy-decision-point, and provenance boundaries.

Run the evaluator only after the system output is durably available. Do not expose evaluator truth to the adapter merely because a frozen reference fixture is publicly inspectable.

**Interpret metrics independently.** A `null` metric is not zero; it means the prediction set did not make that metric meaningful under the task's documented empty behavior. Do not hide weak dimensions behind an aggregate. Interpret every metric using its own denominator, support, polarity, scoring version, and empty behavior.

See the [metrics reference](../reference/metrics.md) and [DATA_DICTIONARY.md](../../DATA_DICTIONARY.md) for exact report contracts.

**Record enough to reproduce the run.** Retain benchmark identity, schema and scoring versions, seed and explicit configuration, artifact checksums, adapter/system provenance, and the exact prediction or trace bytes that were scored. A seed is one reproducibility input, not a substitute for the rest of the configuration.

Use the documentation site's Guides navigation for task-specific workflows. For exact command availability, use the [CLI reference](../reference/cli.md) and the installed command's `--help` output.
