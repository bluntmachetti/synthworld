# Agent Authority Contract

The external contract for evaluating agent-authority systems against SynthWorld
worlds: what can be tested, what a system under test must emit, and what a result
must record to be reproducible.

This directory is **documentation and data only**. Nothing here is imported by
the `synthworld` package, and no runtime dependency is added by it — the YAML is
read by people and by external tooling, not by the library.

## Status

Skeleton. Only the control catalogue exists so far.

| Component | State |
|---|---|
| `control-catalogue.yaml` | Draft `0.1.0-draft` — invariants and layer assignments settled; external mappings first-pass |
| `schemas/observed-action-trace.schema.json` | Not started |
| `schemas/run-manifest.schema.json` | Not started |
| `examples/` (design-intent traces) | Not started |
| `adapter-template/` | Not started |
| `docs/` | Not started |

The authoritative trace contract today remains the pydantic models in
`src/synthworld/agentic/models.py` and the documentation in
[`AGENTIC_BENCHMARK.md`](../AGENTIC_BENCHMARK.md). The JSON Schemas here will be
generated from those models so the two cannot drift; until they exist, the models
win.

## What the control catalogue is for

Three problems, one file.

**Separating what a benchmark can prove from what it cannot.** Each control is
tagged `core`, `lab`, or `operational`. Core controls are decidable offline from
declared observations — the frozen Asteria fixture scores these. Lab controls
require networked execution against a real system and are deliberately outside
the SynthWorld package. Operational properties are reported, never scored as
security. A claim that crosses those lines is a claim the evidence does not
support.

**Staying implementation-neutral while standards move.** Every control states an
observable invariant that does not name a broker, vault, token format, or draft.
References to CB4A, WIMSE, OAuth and MCP are annotations carrying their own
revision, retrieval date and status, so when a draft advances or expires only the
mapping changes — never the meaning of the control. Several mappings are marked
`unresolved` on purpose: where sources disagree or say nothing, saying so is more
useful than manufacturing consensus.

**Publishing coverage honestly.** Each control carries `asteria_v1_status`:
`supported`, `partial`, `absent`, or `out-of-scope-core`. Coverage is reported per
control identifier and never as a fraction — a number like "9 of 14" would treat
this file's own control count as if it were a standard, which it is not.

## Reading the catalogue

Start with `security_invariant`, which is the durable part. `metrics`,
`required_observations`, `expected_truth` and `failure_slices` all carry exact
identifiers from `src/synthworld/agentic/` — they are copied verbatim so a reader
can grep for them, and they must be re-verified whenever the agentic schema or
scoring protocol version changes.

Two controls are worth knowing about before anything else:

- **`SW-AA-C09` (decision-time versus audit-time divergence)** is the invariant
  most specific to this project and the one no mapped source states: that
  re-evaluating current state is not an acceptable substitute for replaying the
  authority state at the time of the action.
- **`SW-AA-C13` (denial for the correct reason)** is listed as `absent` rather
  than omitted. Evaluator truth already carries ordered failure reasons; the
  trace schema has no field to receive them, so nothing is scored. It stays in
  the catalogue to keep the gap visible.

## Verifying the identifiers

Every `metrics`, `required_observations`, `expected_truth`, `failure_slices` and
`authority_failure_reasons` entry is copied verbatim from the source and was
checked against it. The check is reproducible — print what the scorer actually
emits and diff it against the catalogue:

```bash
uv run python -c "
from synthworld.agentic import (
    generate_asteria_agentic_v1, reference_agentic_trace, evaluate_agentic_trace,
)
b = generate_asteria_agentic_v1()
r = evaluate_agentic_trace(reference_agentic_trace(b), benchmark=b)
print('\n'.join(sorted(m.name for m in r.metrics)))
"
```

Note that grepping `evaluation.py` for `name=` finds only 6 of the 20 metrics —
the other 13 are keys of the per-action `checks` dict. Run the scorer instead.

The remaining vocabularies come from `synthworld.agentic.models`:
`ObservedActionTrace.model_fields`, `AgenticCaseKind`, `AuthorityFailureReason`,
`AuthorityTruth`, `CanonicalBinding`, `Capability`.

As of catalogue `0.1.0-draft` the two sets are in exact correspondence: all 20
emitted metrics, all 11 case kinds and all 8 failure reasons are cited by at
least one control, and every control's identifiers resolve. This check moves into
`synthworld validate` when the schema work lands.

## Maintenance

- **Re-pin external mappings before 2026-09-30.** CB4A
  (`draft-hartman-credential-broker-4-agents-00`) expires on that date; its
  section numbers become unciteable and every mapping to it needs rechecking.
- **Control IDs are permanent.** Never renumber, never reuse a retired ID.
- **Do not add a control without an observable invariant.** If it cannot be stated
  without naming a product or a draft, it is not a control yet.
