# Evaluating a system

Every SynthWorld integration follows one rule: give the system under test only input explicitly documented as public, then score its prediction or trace against evaluator truth outside the product path.

```text
public benchmark input
        |
        v
 system under test
        |
        v
prediction / trace  ---------+
                            |
evaluator truth  ------------+--> independent metrics
```

Do not infer that every generated bundle is product-safe. Commands such as `generate-public-extraction`, `generate-public-connections`, and `generate-risk-public` emit product-facing projections. Evaluator or annotated bundles such as those produced by `generate-extraction` and `generate-connection-benchmark` can contain expected answers and must not be passed wholesale to the system under test. For mixed-output commands, use only the subtree explicitly documented as `public/`.

## The three terms that matter

- **Public input** is the safely fictional observation set explicitly allowed on the product side.
- **Prediction or trace** is the system's answer in a versioned SynthWorld contract.
- **Evaluator truth** is the expected result used for scoring. Keep it outside the adapter path even when a frozen reference fixture publishes it for conformance.

This separation prevents accidental oracle use; it does not make a public reference benchmark secret.

## Run the foundational walkthrough

From a repository checkout:

```bash
uv sync --locked --all-groups
uv run python examples/evaluate_all.py --predictions-dir predictions
```

The example writes valid scorer inputs for extraction, entity resolution, relationship inference, risk, and agent authority. Replace one example rule at a time with your own model, service, gateway, policy engine, or product while keeping the SynthWorld prediction-model construction as the adapter boundary.

For example:

```bash
synthworld evaluate extraction \
  --predictions predictions/extraction.json \
  --seed 20260719 \
  --persona-count 10 \
  --summary
```

## Validate before scoring

Use `synthworld validate ...` where a task exposes a validator. Structural validity means a submission can be scored; it does not mean the system performed well.

```bash
synthworld validate agentic-trace --predictions predictions/agentic.jsonl
```

Validation should catch contract problems such as duplicate or missing identifiers, invalid rows, and digest mismatches before metric interpretation.

## Score with evaluator truth separated

Run the task-specific evaluator only after the system output is durably available. Do not expose evaluator truth to an adapter merely because the benchmark is publicly inspectable.

Use `--summary` for a compact view and omit it for the full JSON report. A `null` metric is not zero; it means the submitted predictions did not make that metric meaningful under the task's documented empty behavior.

## Keep independent failures independent

Do not hide weak dimensions behind an aggregate. Depending on the evaluator, inspect false merges versus false splits, false accepts versus false rejects, coverage versus precision, authority at action time versus later audit state, and evidence completeness versus evidence exactness.

Interpret each metric using its own denominator, support definition, polarity, formula or scoring version, and empty behavior. See the [metrics reference](../reference/metrics.md) and [DATA_DICTIONARY.md](../../DATA_DICTIONARY.md) for exact report contracts.

## Record enough to reproduce the run

Retain the inputs that define the evaluated artifact, not only the headline score. Depending on the benchmark this includes:

- benchmark identity and schema version;
- seed and explicit configuration;
- event schedule or profile version where applicable;
- scoring or formula version;
- public and evaluator artifact checksums;
- adapter and system-under-test version or provenance;
- the exact prediction or trace bytes that were scored.

A seed is one reproducibility input, not a substitute for the rest of the configuration.

## Choose a task guide

- [Identity worlds](identity-worlds.md)
- [Identity resolution](identity-resolution.md)
- [Privacy and exposure](privacy-exposure.md)
- [Agent authority](agent-authority.md)
- [Enterprise identity and access](enterprise-access.md)

For exact command availability, use the [CLI reference](../reference/cli.md) and the installed command's `--help` output.
