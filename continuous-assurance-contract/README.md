# Continuous identity and authority assurance

This contract is a deterministic ground-truth benchmark for evaluating whether a
system detects, tracks, and clears identity and authority drift over time. It is
not a monitoring service, identity provider, policy decision point, runtime
enforcement component, incident-response workflow, vendor adapter, or enterprise
topology model. EADS continues to own enterprise and operational topology.

The pack composes four existing concrete SynthWorld consumers without adding a
speculative cross-domain core abstraction:

- identity-fabric state for entitlement and owner drift;
- enterprise-agentic state for credential and delegation drift;
- contextual-access observations for access and feed-delay cases; and
- authority-governance history for decision-time policy and evidence cases.

Each source tree is bound by its canonical public digest. Evaluator input also
binds the matching evaluator digest. Individual signals carry a family, record ID,
and record digest, so external runs must retain the receipt-bound source artifacts
needed to resolve those references. SynthWorld does not provide an ambient source
resolver.

## One temporal axis

All time coordinates are nonnegative integer ticks on SynthWorld's existing
temporal axis. Action, decision, effective, observation, detection, remediation,
and audit are named semantics on that axis; they are not independent clocks.
There is no UTC ordering contract and no new temporal-envelope family in this
pack.

Replay is canonical and as-of-tick. A later policy version cannot retroactively
change the decision-time policy, and late evidence cannot retroactively establish
continuous evidence. Feed outages and delayed feeds change only when a signal is
observable; they do not rewrite the underlying effective state.

## Cases, tiers, and visibility

One eight-case cycle covers transient entitlement drift, missing ownership,
credential revocation, delegation recurrence, later-policy non-retroactivity,
late evidence, delayed observation during an outage, and a stable negative
control. The deterministic profiles are:

| Profile | Cases | Purpose |
|---|---:|---|
| `smoke` | 8 | Hand-inspectable conformance and committed examples |
| `standard` | 24 | Repeated deterministic comparison |
| `longitudinal` | 48 | Longer lifecycle and replay comparison |
| `held_out` | 24 | Operator-controlled generation profile |

`held_out` is a profile name, not a secrecy or anti-cheating claim. The generator
is public and deterministic, and this pack has no secret-key input. A real
competitive run must withhold its private configuration and satisfy the operator
controls in
[`EVALUATION_KEY_CUSTODY.md`](../EVALUATION_KEY_CUSTODY.md). The committed smoke
examples are generated contract fixtures, not frozen benchmark goldens. A score
on generated fixtures is not evidence of real-world transfer and does not
constitute an unbiased vendor leaderboard.

Public input exposes source bindings, signals, remediations, feed windows, cases,
and deterministic checkpoints. It contains no case kinds, expected findings,
canonical policy selection, remediation verdicts, evidence verdicts, or failure
reasons. Those fields are separately typed and serialized in evaluator artifacts.
The public/evaluator split protects API hygiene and accidental leakage; it does
not claim secrecy when both trees are distributed.

## Independent measurements

Reports contain per-case findings and no aggregate security score. Every metric
publishes its aggregation, numerator, denominator, support, denominator meaning,
and explicit `null_if_empty` behavior. The families remain independent:

| Family | Measurements |
|---|---|
| Detection | recall, false-negative and false-positive rates, precision, open-tick accuracy, pre-observation openings, latency, checkpoint state |
| Classification | drift-kind accuracy |
| Staleness | clear-tick accuracy, stale duration, premature clears |
| Recurrence | precision and recall |
| Remediation | completeness accuracy |
| Evidence | continuity accuracy |

Operational performance remains the separate agent-authority L07 measurement;
it is not folded into this security report. The three public-only reference
baselines deliberately confuse latest state, effective time, and clearing
semantics so they discriminate different failure modes.

SGNL and other vendor systems may consume exported public artifacts through an
external, receipt-producing adapter after the reference-deployment gate. No SGNL
behavior or enforcement conformance is claimed by these offline fixtures.

Generate or verify schemas and deterministic smoke examples with:

```bash
uv run python continuous-assurance-contract/tools/generate_contract.py
uv run python continuous-assurance-contract/tools/generate_contract.py --check
```
