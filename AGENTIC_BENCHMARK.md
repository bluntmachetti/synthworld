# Asteria Agentic v1

Asteria Agentic v1 is SynthWorld's frozen conformance fixture for agent
identity, delegated authority, temporal validity, and audit provenance. It is
small enough to inspect manually and runs locally without an identity provider,
agent framework, policy service, or LLM.

This is a reference/conformance suite, not a statistically representative
vendor leaderboard. The committed answer key is public, so the public/oracle
split prevents accidental label leakage in an integration; it is not an
anti-cheating boundary. Competitive evaluation needs private held-out worlds.

## What is frozen

The fixture uses world ID `asteria-agentic`, world version `1.0.0`, schema
version `1.0.0`, and seed `20260719`. It contains:

- Asteria plus one deliberately confusing external tenant, four Asteria
  departments, ten principals, and three logical agents;
- three runtime instances, three task-bound credentials, four grants, nine
  resources, and eleven tool schemas;
- 24 strictly ordered events and 11 action attempts;
- an authorised attenuated child-agent comparison, supplier reads and
  quotation requests, capability excess, overprivileged sub-delegation,
  wrong-runtime and shared-credential use, cross-tenant confusion, revocation,
  a later grant, incorrect attribution, and declared evidence loss.

At least one action is allowed when performed but denied at the later audit.
Another is denied when performed but appears allowed under a later grant. The
draft-recommendation action remains authorised, but its required delegation
evidence is deliberately discarded before audit.

## Replay semantics

Event indices are contiguous and one-based. Index `0` means the immutable
initial snapshot. Grant, credential issue, runtime spawn, revocation, and
evidence-discard events become effective at their own index. An action is
authorised against the state immediately before its event index. All timestamps
must be UTC and strictly increase; timestamps do not break ordering ties.

`materialize_agentic_world` validates the complete event stream before it
returns any requested prefix, so an invalid suffix cannot be hidden by asking
for an earlier cursor.

```python
from synthworld.agentic import (
    generate_asteria_agentic_v1,
    materialize_agentic_world,
)

benchmark = generate_asteria_agentic_v1()
before_first_action = materialize_agentic_world(
    benchmark.public.snapshot,
    benchmark.public.events,
    at_event_index=9,
)
```

## Public and evaluator packages

Run:

```bash
synthworld generate-agentic --output asteria-agentic-v1
```

The output has physically separate trees:

```text
asteria-agentic-v1/
  public/
    manifest.json
    organisation.json
    principals.jsonl
    agents.jsonl
    runtimes.jsonl
    resources.jsonl
    public_credentials.jsonl
    public_delegations.jsonl
    public_events.jsonl
    tool_schemas/procurement-tools.json
    scenarios/procurement-delegation.json
  evaluator/
    canonical_bindings.json
    authority_truth.jsonl
    cases.jsonl
    expected_decisions.jsonl
    expected_side_effects.jsonl
    expected_provenance.jsonl
    evidence_epochs.jsonl
    checksums.json
```

Public credentials contain identifiers, binding, and validity metadata only;
there is no reusable credential material. Public files contain no expected
decision, failure label, canonical binding, side-effect answer, or audit
reconstructability answer. The evaluator joins those fields only after the
system under test has emitted a trace.

The public manifest records SHA-256 for every public base artifact plus a root
artifact-set digest that binds both relative paths and file bytes. The evaluator
checksum file records evaluator per-file hashes and binds the evaluator tree to
the verified public root digest, without creating a second public hash
authority. Both metadata files are excluded from their own root digest to avoid
a self-referential checksum.

## Observed-action JSONL

Submit exactly one `ObservedActionTrace` row for every public action event.
Identity, decision, attribution, owner, evidence, and side-effect fields are
nullable: missing capture is scored as missing rather than filled from the
answer key. `decision` is the action-time decision;
`decision_at_audit` is the later historical evaluation.

```json
{"event_id":"evt-010-authorised-comparison","timestamp":"2026-01-15T09:10:00Z","originating_principal_id":"principal-procurement-manager","logical_agent_id":"agent-comparison","runtime_principal_id":"principal-runtime-comparison-001","credential_subject_id":"principal-runtime-comparison-001","attributed_actor_id":"principal-comparison-service","resource_id":"resource-quotation-comparison","action":"compare","requested_scope":["supplier:atlas","supplier:cirrus","supplier:novus"],"decision":"allow","decision_at_audit":"deny","side_effect":"comparison_recorded","policy_version":"asteria-policy-v1","delegation_chain_ids":["delegation-procurement-task-001","delegation-comparison-child-001"],"accountable_owner_chain":["principal-procurement-manager","principal-asteria"],"evidence_refs":["evidence:credential:credential-comparison-task-001","evidence:delegation:delegation-comparison-child-001","evidence:delegation:delegation-procurement-task-001","evidence:policy:asteria-policy-v1","evidence:runtime:runtime-comparison-001"],"reconstructable_from_retained_evidence":true}
```

Score it with:

```bash
synthworld evaluate agentic --predictions observed-actions.jsonl --summary
```

### Run the public-only example

The repository includes a complete adapter that receives only the public
bundle, applies a deliberately naive audit-time policy check, and serializes
the resulting observations:

```bash
uv run python examples/evaluate_all.py --predictions-dir predictions
uv run synthworld evaluate agentic \
  --predictions predictions/agentic.jsonl \
  --summary
```

To integrate a real system, replace the call to
`current_state_agentic_trace(benchmark.public)` in `run_agentic_eval` with a
call that passes `benchmark.public` to your adapter and returns an
`AgenticTraceSubmission`. Do not give the adapter `benchmark.evaluator`; that
object is consumed only by `evaluate_agentic_trace` after the trace exists.

Or use the API:

```python
from pathlib import Path

from synthworld.agentic import evaluate_agentic_trace, trace_submission_from_jsonl

submission = trace_submission_from_jsonl(
    Path("observed-actions.jsonl").read_text(encoding="utf-8")
)
report = evaluate_agentic_trace(submission)
```

## Metrics and baselines

The report keeps these dimensions independent:

- originating-principal, logical-agent, runtime, and credential-subject
  resolution;
- action-time authorisation accuracy, allow precision/recall/F1, temporal
  audit validity, least-privilege accuracy, and excess-authority rate;
- delegation-chain, public attribution, and accountable owner-chain integrity;
- provenance completeness and audit reconstructability;
- expected side effect and policy-version correctness.

Every canonical case also receives a per-dimension failure slice. A correct
allow/deny with missing evidence can therefore score perfectly on decision
accuracy while scoring below one on provenance; there is no aggregate score
that conceals that difference.

Two public-only baselines are available in `synthworld.agentic`: an
`always_deny_agentic_trace` baseline and a `current_state_agentic_trace`
baseline that incorrectly uses audit-time state for historical actions. On the
frozen fixture, both reach only `0.6364` action-time decision accuracy. The
current-state baseline has `0.3333` decision F1 and `0.5455` provenance
completeness, illustrating why a final-state policy check is not replay.

## Creating other worlds later

The replay, contracts, projection builder, JSONL trace, and scorer are not
hard-coded to Asteria's exact case list. A developer can construct another
`AgenticWorldSnapshot`, ordered event tuple, scenario, canonical bindings, and
case labels, then call `build_agentic_benchmark`. Case labels are open strings;
Asteria's named labels are helpers for this fixture, not a global closed list.

What v1 does not yet provide is a high-level profile/configuration generator or
world-authoring UI. Adding generated organisations, scale tiers, and custom
scenario authoring belongs to the follow-on temporal/profile work. Those worlds
can reuse this event and evaluation boundary without changing the frozen
Asteria bytes.
