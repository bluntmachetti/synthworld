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

Granted delegations also have provenance semantics. A root delegator must be
the origin or appear in every delegated resource owner's inclusive ownership
chain, and all involved records must share an organisation. A child delegator
must be the parent origin/delegator, an accountable owner of the parent agent,
or a principal on a parent-agent runtime path. The child agent must name the
parent grantee as its parent. Runtime-based child authority is order-sensitive:
the parent runtime must be spawned before the child grant. These are bounded v1
rules, not a general-purpose policy engine.

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
synthworld validate agentic-trace --predictions observed-actions.jsonl
synthworld evaluate agentic --predictions observed-actions.jsonl --summary
```

### Validate before you score

`validate agentic-trace` checks the submission's shape with no access to evaluator
truth, so an adapter author can iterate without the answer key. It examines every
line rather than stopping at the first failure.

## C08 v2 offline evidence-completeness candidates

The independently versioned `asteria-agentic-c08-v2` and
`enterprise-agentic-c08-v2` committed candidates pin seed `20260809` and schema
version `2.0.0`. Each has separate public and evaluator artifacts, an independent
frozen manifest contract, a packaged loader with fixed-reference comparison, and
its own submission and scoring contract.

Public actions declare `(evidence kind, binding handle)` requirements. Each
requirement has a same-action, same-kind distractor with a different handle, and
exactly one observation matches the required handle. Products therefore correlate
public action semantics and handles rather than echoing a unique kind or a public
expected ID. Exact required observation IDs and case truth remain evaluator-only.
Enterprise additionally derives opaque public observation IDs separately from its
source evidence IDs.

Asteria has exactly five candidate files: root manifest, public payload/manifest,
and evaluator payload/manifest. Its public, evaluator, and root artifact-set
digests are respectively `fe59c2...`, `68cefa...`, and `5fc98e...`. Enterprise
has exactly four: root manifest, `SHA256SUMS`, public payload, and evaluator truth;
its checksum-record bytes hash to `a0b012...`, and that lineage defines no separate
aggregate artifact-set digest. Exactly two metric-only baseline files record
dedicated discrimination without submission rows or evaluator truth.

Reports explicitly mark `offline_artifacts_only`. They do not establish live
evidence retention, durable logging, enforcement, deployment behaviour,
real-export compatibility, or EADS compatibility. CI, Ruff/format, schema check,
package, isolated-wheel, clean-install, and regeneration evidence remain pending;
there is no registry or publication claim. Exact committed hashes and D8 exclusions
are in [GOLDEN_REVIEW.md](GOLDEN_REVIEW.md).

| code | severity | meaning |
|---|---|---|
| `malformed_json` | error | the line is not valid JSON |
| `invalid_row` | error | the line is JSON but violates the trace model |
| `duplicate_event_id` | error | the same `event_id` appears on more than one line |
| `unexpected_event_id` | error | the `event_id` is not an action event in this benchmark |
| `missing_event_id` | error | an expected action event is absent from the submission |
| `all_rows_null` | error | every row is empty; a misconfigured adapter, not a submission |
| `all_null_row` | warning | one row carries nothing but its `event_id` |
| `no_scored_fields` | warning | only fields the scorer does not read are set |
| `empty_evidence_refs` | warning | `evidence_refs` is `[]`; use `null` to assert no capture |
| `cardinality_unchecked` | warning | a line had no recoverable `event_id` to match |

Exit codes are `0` for valid, `1` for invalid or unreadable; warnings never change the
exit code. A valid result guarantees that `evaluate agentic` will not raise
`EvaluationInputError` for the same document, and guarantees nothing about the scores.

Two gotchas that catch non-Python adapters, both deliberate. `synthetic` must be
`true` or omitted — `false` is rejected, because the marker is what makes the artifact
unmistakably fictional. And `evidence_refs: []` is not `null`: the empty list claims
that evidence was captured and there was none of it, while `null` claims nothing was
captured. Asteria v1 scores the two identically, so the distinction is about
stating what you mean; the mechanical consequences are that
`synthworld validate agentic-trace` warns on the empty form, and that a submission
whose rows carry nothing but an empty `evidence_refs` is rejected as uninformative,
exactly as an all-null one is.

### Trace conventions

The evaluator grades `delegation_chain_ids`, `evidence_refs`, and
`side_effect` against deterministic conventions computed by the replay
engine. For the frozen Asteria Agentic v1 fixture, a public-only
integration can reproduce them exactly; publishing them here reveals
nothing beyond the already-public answer key. Custom v1 worlds derive
their truth with the same replay rules, but exact public reproducibility
additionally requires that the world's public data map each runtime
principal to a single runtime, because the required runtime reference
follows the canonical binding's runtime ID.

`delegation_chain_ids` records the chain the action-time policy check
selects. Among the delegations granted to the acting logical agent by the
originating principal that are time-valid and unrevoked, keep those whose
capability covers the resource, the action, every requested scope, and the
purpose; take the qualifying delegation with the lexicographically smallest
ID and expand it through its parents, root first. The chain is independent
of the final decision. An action denied for a credential, runtime, tenant,
sub-delegation, or policy-version reason still records its covering chain —
the fixture's wrong-runtime and overprivileged-delegation cases both do —
while an action whose covering delegation is revoked, expired, or not yet
granted records an empty chain, as in the post-revocation and
invalid-before-grant cases. Null is scored as missing capture, not as an
empty chain.

Selection deliberately ignores the attempt's policy version. It used to
require a match, which made `expected_policy_version` equal to the requested
version by construction, so echoing the request scored perfectly. Selection
is now version-blind and the version is compared afterwards, so a covering
delegation at a different version yields a denial that still names its
chain. Where the qualifying delegations disagree on policy version the
world is rejected as ambiguous; where they agree, the ID tie-break above
applies as before.

`expected_policy_version` is the covering delegation's version, taken from
the action-time evaluation. Where no delegation covers the action there is
no delegation-bound policy to name and the attempted version stands, so
those rows remain echoable — the accompanying failure reason is what records
that nothing was authorised. This is delegation-bound policy correctness:
`PolicyVersion` carries no activation schedule, so the benchmark does not
model which policy was in force at a given time.

`evidence_refs` is the sorted union of exactly four groups: the policy
(`evidence:policy:<version>`), the presented credential
(`evidence:credential:<id>`), the canonical runtime mapped from the claimed
runtime principal (`evidence:runtime:<runtime id>`), and one
`evidence:delegation:<id>` entry per member of `delegation_chain_ids`.
Denied actions therefore require no delegation references beyond the
recorded chain and never require revocation references, and the runtime
reference follows that canonical mapping rather than any runtime reference
the attempt happened to cite.
`reconstructable_from_retained_evidence` states whether that required set
is still retained at the audit event, given every `evidence_discarded`
event.

`side_effect` is `none` whenever the action-time decision is deny. For
allowed actions it is a fixed name derived from the action: `read` becomes
`read_recorded`, `request_quotation` becomes `quotation_requested`,
`compare` becomes `comparison_recorded`, `create_draft` becomes
`draft_created`, `create_delegation` becomes `delegation_created`, and any
other action becomes `action_recorded`.

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

Every metric names the family it belongs to and what its denominator counts, so a
report can be read by family and each ratio re-derived rather than trusted.

The split that carries the most information is **observability against everything
else**. An agent can decide well and record badly, or the reverse, and those need
different fixes — one is a policy problem, the other a logging problem. A single
aggregate hides which you have.

| family | metric | 1.0 means | 0.0 means | support counts |
|---|---|---|---|---|
| identity_binding | `principal_resolution_accuracy` | the originating principal is named correctly | it is not | scored action events |
| | `logical_agent_resolution_accuracy` | the acting logical agent is named correctly | it is not | scored action events |
| | `runtime_binding_accuracy` | the runtime principal is named correctly | it is not | scored action events |
| | `credential_subject_accuracy` | the presented credential's subject is named correctly | it is not | scored action events |
| authorization_decision | `authorization_decision_accuracy` | allow/deny matches truth | it never does | scored action events |
| | `authorization_decision_precision` | nothing the trace allowed should have been denied | everything it allowed should have been denied | actions the trace allowed at action time |
| | `authorization_decision_recall` | every action truth allows was reported `allow` | none was — note a null decision is neither allow nor deny, so this is not the same as "all were denied" | actions truth allows at action time |
| | `authorization_decision_f1` | harmonic mean of the two above | precision and recall are both zero | classification support — **not** this metric's denominator, which is why it is derived from the two rows above rather than from `support` |
| | `temporal_validity_accuracy` | the audit-time verdict is right on every event labelled `valid_then_revoked`, `post_revocation_action` or `invalid_then_later_granted` | it is wrong on all of them | events carrying one of those three case labels |
| | `policy_version_accuracy` | the expected policy version is named correctly — the covering delegation's where a chain exists, and the attempt's own where truth records no chain | it is not | scored action events |
| authority_replay | `delegation_chain_integrity` | the delegation chain matches the one the action-time check selected, root first | it does not | scored action events |
| accountability | `attribution_integrity` | the attributed actor matches the evaluator's canonical binding | it does not — note two attribution paths can be equally defensible, so this scores agreement with the canonical choice rather than objective correctness | scored action events |
| | `accountable_owner_chain_integrity` | the chain of principals accountable for the action is correct | it is not | scored action events |
| observability | `provenance_completeness` | every event's reported reference set includes every evaluator-required reference | no event's reported reference set includes every required reference — which happens well short of submitting nothing | scored action events |
| | `provenance_exact_match` | each reported reference set is exactly the evaluator-required one — nothing missing, nothing extra | it is not. An extra reported reference is one not required *for this action*; the scorer does not establish it was invented | scored action events |
| | `provenance_precision` | every reported reference was required for the action it was reported against | none was. A genuine reference reported against the wrong action counts here, so this measures misfiling as well as invention | distinct action-event and evidence-reference pairs reported |
| | `audit_reconstructability_accuracy` | the reported claim about whether the decision can be rebuilt from retained evidence matches evaluator truth | it does not | scored action events |
| | `expected_side_effect_accuracy` | the side effect the action should record is named correctly | it is not | scored action events |
| | `least_privilege_accuracy` | nothing truth denies was allowed | everything truth denies was allowed | actions truth denies |
| | `excess_authority_rate` | every action truth denies was allowed — this is the **bad** end | nothing truth denies was allowed | actions truth denies |

`excess_authority_rate` is the only metric where zero is the good score, so its row
reads in the opposite direction to every other. Note also that `support` is not always
a denominator: for every metric but `authorization_decision_f1` the value is
`numerator / support` and the numerator is recoverable, while F1 comes from the
precision and recall reported beside it. It is the exact complement of
`least_privilege_accuracy`, and both are reported so a reader scanning for failures
does not have to invert one in their head.

Families name where a failure comes from, not how a denominator is shaped. Precision
and recall differ only in denominator and sit together, because a reader chasing one
wants the other projections of the same matrix beside it. `least_privilege_accuracy`
and `excess_authority_rate` sit there too: they are exact complements over one support,
so as a family of their own their mean would be 0.5 whatever the trace did.

A metric is `null` rather than `0.0` when it cannot be computed. Usually that is an
empty denominator — a world with no timing cases cannot score temporal validity, and
zero would read as total failure at something never asked. It is not only that:
`authorization_decision_f1` is null whenever precision and recall are both zero, which
can happen with a perfectly non-empty denominator.

Agentic reports use scoring protocol `0.3.0`; other SynthWorld tasks remain on
their existing scoring protocols. Grouping metrics into families changed the report's *shape*, not any metric's
definition or value, so it moved `EVALUATION_SCHEMA_VERSION` to `0.2.0` rather than
this number - and that knob is shared, because every task's report gained the same two
fields. `0.3.0` derives
`expected_policy_version` from
the delegation that covered the action rather than echoing the attempt, and
records the covering chain on a policy-version-mismatch denial. Asteria Agentic
v1's artifacts are byte-identical under both, because it registers a single
policy version - the protocol number moves because the rule changed, not because
the fixture did. The report keeps these dimensions
independent:

- originating-principal, logical-agent, runtime, and credential-subject
  resolution;
- action-time authorisation accuracy, allow precision/recall/F1, temporal
  audit validity, least-privilege accuracy, and excess-authority rate;
- delegation-chain, public attribution, and accountable owner-chain integrity;
- provenance completeness, exact match, micro precision, and audit
  reconstructability;
- expected side effect and policy-version correctness.

Each canonical case receives a per-dimension failure slice for the thirteen
per-action checks. The seven metrics built separately - both least-privilege
metrics, the temporal metric, provenance precision and the three decision rates -
emit no slices, so those dimensions have no per-case breakdown. A correct
allow/deny with missing evidence can therefore score perfectly on decision
accuracy while scoring below one on provenance; there is no aggregate score
that conceals that difference.

`provenance_completeness` is the fraction of actions whose reported evidence
reference set contains every required reference. It deliberately retains its
original subset-based meaning. `provenance_exact_match` is the fraction of
actions whose distinct reported and required reference sets are equal.
`provenance_precision` is micro precision over distinct `(action, evidence
reference)` pairs; its support is the number reported and its value is undefined
at zero support. Consequently, fabricated extras can leave completeness at one
while lowering exact match and precision.

These are reference-reporting metrics, not evidence-retention tests. The scorer
compares submitted reference labels, and the submitted reconstructability claim,
with evaluator truth. It does not retrieve, reconstruct from, or otherwise prove
the retention of the underlying evidence. A perfect C08 score therefore does not
establish that the cited evidence remains available. `delegation_chain_integrity`
already compares the ordered chain IDs exactly; those IDs resolve to public
delegations containing each delegator, grantee, parent, policy, and capability.

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

### Custom-world construction trust boundary

`build_agentic_benchmark` fully replays the public stream before deriving any
truth. It rejects invalid runtime ownership, unrelated grant delegators,
duplicate/missing evaluator keys, false runtime/agent joins, credential subjects
that disagree with the credential actually presented, fabricated accountable
owner chains, and attributed actors unrelated to the runtime or credential
identity paths. Owner chains are derived from the canonical principal graph;
the builder does not repair a supplied tuple.

Malformed construction remains separate from a well-formed denied action. A
real credential used from a runtime it does not permit, a truthful external
runtime targeting another tenant's resource, or an incorrect public claim stays
scoreable and produces authority/identity failure truth. "Cross-tenant binding"
rejection means an intrinsically false join—such as an Orion runtime bound to an
Asteria logical agent—not a truthful cross-tenant access attempt.

V1 still has explicit limits:

- an action carries a runtime-principal claim but no independently verifiable
  runtime ID, and its canonical origin may be ambiguous;
- there is no explicit actor relationship, so when credential and runtime
  identities differ the builder can constrain the actor to those public paths
  but cannot select one without evaluator-author input;
- arbitrary out-of-band authorised delegates are not representable. V1 supports
  origins, resource owners, accountable owners, parent delegators, and principals
  attached through already-spawned parent runtimes. A broader delegate relation
  requires a separately versioned public contract.

Automatic relational integrity enforcement occurs in
`build_agentic_benchmark`. The packaged golden loader separately verifies every
artifact checksum. A caller that bypasses both by manually constructing an
`AgenticBenchmark` and passing it directly to the scorer is responsible for that
object's evaluator integrity.

The normalized v1 records already retain the full provenance join without
duplicating it into `AuthorityTruth`: bindings identify origin/runtime/credential
and owner truth; ordered truth chain IDs resolve public delegation hops and their
delegators, grantees, parents, policies, and capabilities; credentials retain
issuer and subject; and the action retains resource, operation, scope, and
evidence references.

What v1 does not yet provide is a high-level profile/configuration generator or
world-authoring UI. Adding generated organisations, scale tiers, and custom
scenario authoring belongs to the follow-on temporal/profile work. Those worlds
can reuse this event and evaluation boundary without changing the frozen
Asteria bytes.

## C08 v2 public identifier and report correction

Candidate observation/evidence IDs and binding handles are public benchmark
inputs. They provide the literal identifiers needed to submit a selection.
Evaluator-selected binding rows, required-ID sets, expected outcomes, and
scenario truth remain confined to evaluator artifacts.

For enterprise C08 v2, each requirement must have a same-action/same-kind
candidate with a different binding handle. This runtime invariant makes the
handle discriminating and prevents kind-only matching. Since 4de6df8,
measurement_scope is required by the report schema; it must describe the
offline measurement boundary and must not imply live retention, durable
logging, enforcement, deployment, or EADS compatibility.
