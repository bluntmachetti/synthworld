# Evaluating a system

Every SynthWorld integration follows the same boundary:

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

The system under test receives only the public artifact. Your adapter converts the
system's native output into the task-specific prediction or trace contract. The
scorer loads evaluator truth separately and compares the two.

## The three terms that matter

- **Public input** is the safely fictional observation set the system is allowed to
  see.
- **Prediction or trace** is the system's answer in a versioned SynthWorld shape.
- **Evaluator truth** is the expected result. Keep it outside the product path even
  when a reference fixture publishes that truth for conformance.

A public/evaluator split prevents accidental oracle use; it does not make a public
reference benchmark secret.

## Run the foundational walkthrough

From a repository checkout:

```bash
uv sync --locked --all-groups
uv run python examples/evaluate_all.py --predictions-dir predictions
```

The example uses deliberately simple public-only rules and writes:

```text
predictions/
  extraction.json
  entity-resolution.json
  relationship.json
  risk.json
  agentic.jsonl
```

Each file is a valid scorer input. For example:

```bash
synthworld evaluate extraction \
  --predictions predictions/extraction.json \
  --seed 20260719 \
  --persona-count 10 \
  --summary
```

Replace one example rule at a time with your own model, service, gateway, policy
engine, or product. Keep the code that constructs the SynthWorld prediction model:
that is your adapter boundary.

## Validate shape before scoring

Use `synthworld validate ...` where a task exposes a validator. Structural validity
means a submission can be scored; it does not mean the system performed well.

For trace-oriented tasks, validation is intentionally usable without evaluator
truth. For example:

```bash
synthworld validate agentic-trace --predictions predictions/agentic.jsonl
```

A validator should catch duplicate or missing ids, bad rows, digest mismatches, and
other contract errors before you interpret benchmark metrics.

## Score with evaluator truth separated

Run the task-specific evaluator only after the product output is durably available.
Do not make evaluator truth available to an adapter just because the benchmark is
publicly inspectable.

Use `--summary` for a compact view and omit it for the full report:

```bash
synthworld evaluate risk --predictions predictions/risk.json --summary
synthworld evaluate risk --predictions predictions/risk.json > report.json
```

The full report records the benchmark and scoring identities required by that
contract, together with metrics and failure slices. A `null` metric is not zero: it
means the submitted predictions did not make that metric meaningful, such as
precision when no positive result was predicted.

## Keep independent failures independent

Do not hide a weak dimension behind an aggregate. Depending on the evaluator, a
report may distinguish:

- false merges from false splits;
- false accepts from false rejects;
- coverage from precision;
- final decisions from failure-reason or provenance correctness;
- action-time authority from later audit state;
- evidence completeness from evidence exact match and precision.

Interpret every metric using its own denominator, support definition, polarity,
formula/scoring version, and empty behavior. Some metric families describe the
benchmark world rather than prediction quality; the relevant contract says which is
which.

See the [metrics reference](../reference/metrics.md) and
[DATA_DICTIONARY.md](../../DATA_DICTIONARY.md) for the exact report contracts.

## Record enough to reproduce the run

For a reproducible result, retain the inputs that define the artifact rather than
only the headline score. Depending on the benchmark this includes:

- benchmark identity and schema version;
- seed and explicit configuration;
- event schedule or profile version where applicable;
- scoring/formula version;
- public and evaluator artifact checksums;
- adapter and system-under-test version or provenance;
- the prediction or trace bytes that were scored.

A seed is one input to reproducibility, not a substitute for the rest of the
configuration.

## Choose a task guide

- [Identity worlds](identity-worlds.md)
- [Identity resolution](identity-resolution.md)
- [Privacy and exposure](privacy-exposure.md)
- [Agent authority](agent-authority.md)
- [Enterprise identity and access](enterprise-access.md)

For exact command availability, use the [CLI reference](../reference/cli.md) and the
installed command's `--help` output.