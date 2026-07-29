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
| `control-catalogue.yaml` | Draft `0.2.0-draft` — revised after adversarial review; statuses re-graded, two controls added, mappings downgraded |
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

`SW-AA-C06` (action-time decision, four metrics) and `SW-AA-C12` (false-allow rate
over denials) are `supported` — the decision itself is scored directly and
non-trivially. Identity binding, credential consistency, attribution, evidence and
policy version are all `partial`: a system must report them correctly, but correct
reporting is what gets scored, not the underlying enforcement. Anyone using this
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

As of catalogue `0.1.0-draft` the two sets are in exact correspondence: all 20
emitted metrics, all 11 case kinds and all 8 failure reasons are cited by at
least one control, and every control's identifiers resolve. This check moves into
`synthworld validate` when the schema work lands.

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
