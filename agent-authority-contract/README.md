# Agent Authority Contract

The external contract for evaluating agent-authority systems against SynthWorld
worlds: what can be tested, what a system under test must emit, and what a result
must record to be reproducible.

This directory is **documentation and data only**. Nothing here is imported by
the `synthworld` package, and no runtime dependency is added by it — the YAML is
read by people and by external tooling, not by the library.

## Status

The catalogue, schemas, adapter template and design-intent traces are in place. The
remaining docs are the two narrative files listed below.

| Component | State |
|---|---|
| `control-catalogue.yaml` | Draft `0.2.0-draft` — revised after adversarial review; statuses re-graded, two controls added, mappings downgraded |
| `schemas/observed-action-trace.schema.json` | Generated from the model |
| `schemas/agentic-trace-submission.schema.json` | Generated from the model |
| `schemas/run-manifest.schema.json` | Draft `0.1.0-draft` — hand-authored proposal |
| `tools/generate_trace_schema.py` | Working; `--check` drift gate runs in `make ci` |
| `synthworld validate agentic-trace` | Shipped — validates a submission with no answer-key access |
| `examples/` (design-intent traces) | Generated for three pattern classes |
| `adapter-template/` | Working; runs and produces a valid trace as shipped |
| `docs/design-intent-assumptions.md` | Assumptions + scored coverage table |
| `docs/control-mappings.md`, `docs/limitations.md` | Not started |

The pydantic models in `src/synthworld/agentic/models.py` remain authoritative for
the trace contract. The schemas here are a projection of them, not an independent
definition — where the two disagree the model is right and the schema is stale.

## Schemas

**The trace schemas are generated.** Regenerate after any model change:

```bash
uv run python agent-authority-contract/tools/generate_trace_schema.py
uv run python agent-authority-contract/tools/generate_trace_schema.py --check   # CI gate
```

`--check` exits non-zero when a committed schema no longer matches the model. It runs
as the `schemas` target in `make ci`, so a model change that is not reflected here
fails the build — drift between a published contract and the scorer that enforces it
is worth a CI job.

**The run manifest is hand-authored** because no model defines it yet. It is the
component of this package that makes *findings* reproducible rather than merely
making *fixtures* reproducible — a distinction worth being explicit about, since a
seeded world and a checksum already give you the latter. A claim like "revocation did
not propagate" is a claim about a named system at a version under a configuration on
a topology, and none of that is recoverable from the benchmark artifacts.

Three design choices in it are deliberate:

- **`systems_under_test` is an array.** Every component in the authority path is
  recorded separately, so a finding can be attributed to one of them — or explicitly
  marked ambiguous. Attributing to a gateway something that originated in its
  authorization server is the most common way a report becomes unfair.
- **Lab runs must declare topology.** JSON Schema conditionals enforce it: a manifest
  with `run_layer: lab` and no `topology` or `authority_critical_dependencies` fails
  validation. A bypass or fail-closed finding is uninterpretable without reachability
  declared, so this is a schema rule rather than a convention.
- **Bounds and conflicts are declared up front.** `declared_bounds` exists so a
  latency threshold is fixed before measurement, and
  `authored_by_benchmark_maintainer` plus `conflicts_declared` record the things a
  reader would otherwise have to discover.

### `format` is decorative — read this before trusting a validator

`format` is an **annotation** in JSON Schema 2020-12, not an assertion. A conformant
validator may ignore it, and Python's `jsonschema` does not check `date-time` unless
you both pass a `FormatChecker` and install its `[format]` extra. Measured against an
earlier revision of these files, that meant the published schema accepted
`"timestamp": "not-a-date"`, a naive timestamp, and a non-UTC offset — all of which
the model rejects. An adapter author was being told those were fine and then having
the scorer reject them.

The timestamp property therefore carries an asserted `pattern` as well, admitting
the forms the model accepts (`Z`, `+00:00`, `-00:00`, optional fractional seconds)
and constraining every component to its real range, so `2026-99-99T99:99:99Z` is
refused by any conformant validator.

One gap remains and it is worth knowing precisely: a regex cannot do calendar
arithmetic, so `2026-02-30T12:00:00Z` satisfies the pattern. **Configure format
assertion and it is rejected**, which is why you should — but if you do not, you
still get component-range checking rather than the nothing you had before.

### On `jsonschema` as a dependency

An earlier version of this file said `jsonschema` would become a project dependency
when `synthworld validate agentic-trace` landed. That command has landed, and it
validates with the **pydantic models**, not with these schemas. The reason is worth
recording, because the intuition points the other way:

- The schemas are generated from the models, so validating model-parsed rows against
  them would be circular — agreement is guaranteed, and disagreement only ever means
  the projection is stale, which `--check` already catches.
- The two are not nested. Each accepts input the other refuses, so validating against
  the schema at runtime would enforce a *different* surface than the scorer, which is
  precisely the valid-then-rejected failure the command exists to prevent.
- A non-Python adapter is not helped by a Python dependency. It needs the schema
  *file*, which is committed here and consumable by `ajv`, `go-jsonschema`, or any
  other validator in its own toolchain.

`jsonschema[format]` is a **dev** dependency, used by
`tests/test_trace_schema_agreement.py`, which asserts that the model and these schemas
accept the same bytes across a mutation corpus and records the two known coercion
divergences explicitly. A new divergence fails that suite rather than reaching an
integrator.

## What the control catalogue is for

Three problems, one file.

**Separating what a benchmark can prove from what it cannot.** Each control is
tagged `core`, `lab`, or `operational`. Core controls are decidable offline from
declared observations. Lab controls require networked execution against a real
system and are deliberately outside the SynthWorld package. Operational properties
are reported, never scored as security. A claim that crosses those lines is a claim
the evidence does not support.

Note that "core" does not mean "scored": `SW-AA-C05`, `SW-AA-C10` and `SW-AA-C13`
are core but have no metric attached, and `SW-AA-C15`/`SW-AA-C16` are core gaps
with no field to carry them at all. Read `asteria_v1_status` per control rather
than assuming the layer implies coverage.

**Distinguishing a reported field from an enforced condition.** This was the main
finding of the first adversarial review and the reason most statuses are `partial`.
`ObservedActionTrace` is a set of nullable claims made by the system under test,
and most metrics compare a claim against evaluator truth. That establishes correct
*reporting*. It does not establish that authority was actually withheld, that a
credential was genuinely bound, that evidence was really retained, or that a side
effect matched reality. Where a control's invariant asserts the stronger thing, the
status says `partial` and `core_limitations` says exactly which half is missing.

**Staying implementation-neutral while standards move.** Every control states an
observable invariant that does not name a broker, vault, token format, or draft.
References to CB4A, WIMSE, OAuth and MCP are annotations carrying their own
revision, retrieval date and status, so when a draft advances or expires only the
mapping changes — never the meaning of the control. Several mappings are marked
`unresolved` on purpose: where sources disagree or say nothing, saying so is more
useful than manufacturing consensus.

**Publishing coverage honestly.** Each control carries `asteria_v1_status`:
`supported`, `partial`, `absent`, or `out-of-scope-core`. Coverage is reported per
control identifier and never as a fraction — a number like "9 of 16" would treat
this file's own control count as if it were a standard, which it is not.

`partial` is the most common status and that is not a euphemism: it means part of
the invariant is directly scored and part is not, and each control says which is
which. The shape of the coverage is worth stating plainly, because it is the
honest summary of what Asteria v1 does:

> **Authorisation decisions are well tested. The bindings and evidence around them
> are reported but not proven.**

`SW-AA-C12` (false-allow rate over denials) is the one control whose invariant is
scored directly and non-trivially end to end. Everything else is `partial` or
weaker: a system must report identity binding, credential consistency, attribution,
evidence and policy version correctly, but correct *reporting* is what gets scored,
not the underlying enforcement. `SW-AA-C05` and `SW-AA-C10` are `partial` with no
metric of their own at all — they are observable only through the decision, which is
why `partial` here means "partly evidenced", not "partly scored". Anyone using this
benchmark to make a claim should quote the relevant control's `core_limitations`
rather than its status alone.

## Reading the catalogue

Start with `security_invariant`, which is the durable part. `metrics`,
`required_observations`, `expected_truth` and `failure_slices` all carry exact
identifiers from `src/synthworld/agentic/` — they are copied verbatim so a reader
can grep for them, and they must be re-verified whenever the agentic schema or
scoring protocol version changes.

Four controls are worth knowing about before anything else:

- **`SW-AA-C09` (decision-time versus audit-time divergence)** is the invariant
  most specific to this project and the one no mapped source states: that
  re-evaluating current state is not an acceptable substitute for replaying the
  authority state at the time of the action.
- **`SW-AA-C13` (denial for the correct reason)** is `absent` rather than omitted.
  Evaluator truth already carries ordered failure reasons; the trace schema has no
  field to receive them, so nothing is scored.
- **`SW-AA-C15` (trusted issuance and credential-to-grant binding)** is `absent`
  and is the largest gap in the core layer. Nothing joins the presented credential
  to the delegation the action was authorised under, and issuance is validated for
  referential integrity rather than entitlement.
- **`SW-AA-C16` (principal intent and parameter integrity)** is `absent` because
  `ActionAttempt` carries no transaction parameters. "Approve transfer 10, execute
  transfer 10,000" is currently invisible to the oracle.

The three `absent` controls all imply a schema change, not merely a new metric.
They are listed so the gaps are visible rather than quietly missing.

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

Note that grepping `evaluation.py` for `name=` finds only 7 of the 20 metrics —
the other 13 are keys of the per-action `checks` dict. Run the scorer instead. (A
naive regex finds just 6, because `authorization_decision_f1` contains a digit.)

One consequence worth knowing: the scorer emits a `FailureSlice` only for those 13
`checks` metrics. The 7 built with a literal `name=` — both `SW-AA-C12` metrics,
`SW-AA-C09`'s temporal metric, `provenance_precision`, and the three
decision-rate metrics — produce no slices, so those controls have no per-case
failure breakdown.

The remaining vocabularies come from `synthworld.agentic.models`:
`ObservedActionTrace.model_fields`, `AgenticCaseKind`, `AuthorityFailureReason`,
`AuthorityTruth`, `CanonicalBinding`, `Capability`.

The two sets correspond exactly: all 20 emitted metrics and all 8 failure reasons
are cited by at least one control, every control's identifiers resolve, and every
`AgenticCaseKind` member is either cited as a failure slice or declared under
`meta.fixture_shape.unexercised_case_kinds`. Eleven of the thirteen kinds are
cited; `credential_invalid` and `policy_version_mismatch` name failure reasons the
oracle decides but that no frozen action reaches, so they label no case here.

That paragraph used to be a hand-checked claim, and it was wrong within a day of
the enum growing. `tests/test_control_catalogue_vocabulary.py` now enforces it in
both directions — an uncited metric is an undisclosed capability, and a control
citing a slice or reason that no longer exists reads as covered while scoring
nothing.

## Maintenance

- **Re-pin external mappings before 2026-09-30.** CB4A
  (`draft-hartman-credential-broker-4-agents-00`) expires on that date. Expiry does
  not make the pinned `-00` revision unreadable — archived Internet-Drafts stay
  retrievable and their contents are immutable — but it ends active status, so
  check for a `-01` or a working-group replacement before citing it anywhere
  public.
- **Clear the `UNVERIFIED` markers.** Several mappings carry clause numbers
  asserted by review but not yet checked at source (`SW-AA-C10`, `SW-AA-C16`,
  `SW-AA-C04`'s ID-JAG entry, `SW-AA-L05`'s CB4A §4.9). Pin or drop each before
  publication — never cite a section number nobody has opened.
- **Keep `mapping_status` and `source_maturity` distinct.** The first is how much
  of the invariant a clause covers; the second is how much standing the document
  has. Conflating them is what produced the inconsistency fixed in `0.2.0-draft`.
- **Control IDs are permanent.** Never renumber, never reuse a retired ID.
- **Do not add a control without an observable invariant.** If it cannot be stated
  without naming a product or a draft, it is not a control yet.
