# Failure-reason precedence

| | |
|---|---|
| **Version** | `0.1.0-draft` |
| **Created** | 2026-07-31 |
| **Normative subject** | `AuthorityDecision.failure_reasons`, `delegation_chain_ids` and `effective_policy_version` as produced by `evaluate_action_authority`, and therefore `AuthorityTruth.failure_reasons_at_action` / `failure_reasons_at_audit` and `expected_policy_version`, which the projection derives by calling that oracle at action time and audit time |
| **Derived from** | `src/synthworld/agentic/replay.py` with the version-blind delegation resolution introduced by the SW-AA-C11 fix; the conformance test, not this prose, is the drift gate |
| **Conformance test** | `tests/test_agentic_failure_reason_precedence.py` |
| **Versioning** | A change to any clause in §4–§6 changes the meaning of published truth and requires a scoring-protocol bump, whether or not the frozen fixture bytes move. The failure reasons themselves are scored by no current metric (SW-AA-C13 is `absent`), but §5's chain rule feeds `delegation_chain_integrity` and §6's decision rule feeds every decision metric, so this document's clauses are not free to drift |

Identity truth in an agentic world says *which* authority condition failed,
not merely that one did. This document specifies exactly which
`AuthorityFailureReason` values the reference oracle reports for an action
attempt, in which cases, and why the answer is unique. It exists because the
selection rule was previously implicit in control flow: any independent
implementation — the planned world generator (#27), an adapter author
interpreting evaluator truth, a future scorer for SW-AA-C13, or a formal
model — must reproduce it from this document alone, without reading the
oracle's `if/elif` cascade.

## 1. Scope

This document specifies, for a single evaluation
`evaluate_action_authority(state, attempt, binding, decision_time)`:

- which single **delegation-family** reason (§2) the effective-chain
  resolution contributes, as a function of the state;
- when the resolution refuses to decide at all (§4 clause A, §5
  well-formedness);
- how the covering delegation chain is selected, ordered, and published;
- how `effective_policy_version` is derived;
- how all of it composes into the final `failure_reasons` tuple.

It does **not** change anything. Failure reasons are not scored by any
current metric: `ObservedActionTrace` has no field to carry them, which
SW-AA-C13 records as `absent`, and closing that is a trace-schema
(`schema_version`) change, not a metric addition. The serialized truth in
`evaluator/expected_decisions.jsonl` and `evaluator/authority_truth.jsonl`
already follows this specification, because it is produced by the oracle
this document describes.

## 2. Vocabulary

The eight `AuthorityFailureReason` values divide into two groups.

**Delegation family** — the effective-chain resolution contributes at most
one of these per evaluation, chosen by the rule in §4:

- `policy_version_mismatch` (also has an independent source, §6)
- `delegation_revoked`
- `capability_exceeded`
- `no_active_delegation` (also has an independent source, §6)

Because two of the four also have independent sources, two family *values*
can still co-occur in one final tuple — e.g. `no_active_delegation` from
the resolution plus `policy_version_mismatch` from an unknown attempted
version. What is unique is the resolution's contribution, not the tuple's
family subset.

**Independent checks** — each is added or not on its own evidence,
regardless of the resolution outcome:

- `wrong_runtime` (two sources, §6)
- `credential_invalid`
- `tenant_mismatch`
- `overprivileged_subdelegation` (guarded by the chain, §6)

`delegation_revoked` and `capability_exceeded` have **no** source outside
the resolution: if either appears, it came from §4.

## 3. Definitions

Given state `s`, attempt `a`, binding `b`, and decision time `t`, define:

**CapabilityAllows(c, a)** — capability `c` admits attempt `a`:

```text
a.resource_id ∈ c.resource_ids
∧ a.action ∈ c.actions
∧ set(a.requested_scope) ⊆ set(c.scopes)
∧ a.purpose = c.purpose
```

All four clauses are required; each alone defeats sufficiency.

**Four nested delegation sets**, each a subset of the previous:

```text
Candidates(s, b)   = { d ∈ s.delegations :
                         d.grantee_agent_id = b.logical_agent_id
                       ∧ d.originating_principal_id = b.originating_principal_id }
TimeValid(s, b, t) = { d ∈ Candidates : d.valid_from ≤ t < d.expires_at }
Active(s, b, t)    = { d ∈ TimeValid : d.id ∉ s.revoked_delegation_ids }
Capable(s, a, b, t)= { d ∈ Active : CapabilityAllows(d.capability, a) }
```

**`Capable` is version-blind.** Coverage is a fact about resources,
actions, scopes and purpose; the attempted policy version does not
participate in resolution and is compared only afterwards (§4). This is
what makes `expected_policy_version` a derived value rather than an echo of
a public byte.

Candidate filtering keys on the **canonical binding**, never on any claim
field of the attempt. A delegation granted to a different agent or from a
different originating principal is invisible to the evaluation, whatever it
would otherwise permit. Validity intervals are half-open: inclusive of
`valid_from`, exclusive of `expires_at`.

## 4. The resolution rule

On a well-formed state (§5), exactly one of the following holds. Clause A
is a refusal, not a decision; among clauses 0–4 the outcome is the first
that applies, stated so an independent implementation can compute it from
the set profile directly. The conformance test checks exclusivity and
totality by exhaustive enumeration.

| # | Outcome | Holds when |
|---|---|---|
| A | *world rejected as ambiguous* (`AgenticReplayError`) | the members of `Capable` do not all share one `policy_version` |
| 0 | *chain found, no reason* | `Capable ≠ ∅` and the shared capable version equals `a.policy_version` |
| 1 | `policy_version_mismatch` **with the chain published** | `Capable ≠ ∅` and the shared capable version differs from `a.policy_version` |
| 2 | `delegation_revoked` | `Capable = ∅` and some `d ∈ TimeValid` has `CapabilityAllows(d.capability, a) ∧ d.id ∈ s.revoked_delegation_ids` |
| 3 | `capability_exceeded` | neither 2 nor above, and `Active ≠ ∅` |
| 4 | `no_active_delegation` | none of the above |

Reading order matters and is deliberate: a delegation that *covers* the
attempt is always the explanation, and its policy version decides between
authorisation (clause 0) and a mismatch denial that still names its chain
(clause 1). Ambiguity — capable delegations disagreeing on version — is
under-determined and rejected rather than resolved by tie-break;
overlapping grants that *agree* on version are legal and fall to the id
tie-break in §5. A revoked delegation that would have covered the attempt
explains a denial better than "nothing active" (clause 2 ranges over
`TimeValid`, so it fires even when `Active = ∅`, and it is version-blind
like coverage itself). `capability_exceeded` is the residual for
"something is active for this binding, but nothing covers the attempt and
no better explanation applies".

## 5. Selection, chain, and well-formedness

When clause 0 **or clause 1** holds:

- the covering delegation is the member of `Capable` with the
  **lexicographically smallest id** — ids are the only tie-break criterion;
  no recency, specificity, or chain-depth preference exists;
- `delegation_chain_ids` walks `parent_delegation_id` links upward from the
  selected delegation and is reported **root-first**: index 0 is the root,
  the last element is the selected delegation itself;
- `effective_policy_version` is the selected delegation's version.

When clause 2, 3, or 4 holds, `delegation_chain_ids` is empty and
`effective_policy_version` falls back to the attempted version — where no
delegation covered the action there is no delegation-bound policy to name,
and the accompanying failure reason carries the information that nothing
was authorised.

The chain is otherwise independent of the final decision (already public
in `AGENTIC_BENCHMARK.md`): an action denied only by an independent check —
credential, runtime, tenant, sub-delegation, or the policy-version
comparison of clause 1 — still records its covering chain.

**Well-formedness precondition.** The chain walk requires delegation ids
to be unique and parent links to resolve acyclically. States produced by
replay guarantee this (grant validation requires an existing, active,
already-granted parent and rejects duplicate ids, so neither cycles nor
dangling links nor duplicates can form). The oracle does **not**
re-validate this globally: on a directly constructed state, corruption is
detected lazily, only where the chain walk actually treads. A missing
parent or a cycle on the *selected covering delegation's* ancestor path
raises `AgenticReplayError` ("missing parent" / "contains a cycle"); the
same malformation on a delegation the walk never visits goes unnoticed,
and duplicate delegation ids never raise at all — lookups silently resolve
to the first occurrence, so behaviour on duplicate-id states is
unspecified and outside this contract. The totality claim in §4 is scoped
to well-formed, unambiguous states, and an independent implementation must
not front-load a global validity check when predicting oracle outcomes.

## 6. Composition into `failure_reasons`

Failure reasons accumulate in a **set**: duplicates collapse, and the final
tuple is

```text
tuple(sorted(failures, key=reason.value))
```

The decision is `DENY` iff the tuple is non-empty; `expected_side_effect`
is `"none"` on every denial.

**The tuple order is lexicographic by enum value string. It does not encode
precedence, severity, or evaluation order.** The full lexicographic order
over all eight values is:

```text
capability_exceeded < credential_invalid < delegation_revoked
< no_active_delegation < overprivileged_subdelegation
< policy_version_mismatch < tenant_mismatch < wrong_runtime
```

SW-AA-C13's `core_limitations` phrase "ordered failure reasons" refers to
this deterministic serialization order, nothing more.

Policy evidence names the governing version: `required_evidence_refs`
contains `evidence:policy:<effective_policy_version>` — the version of the
delegation that actually covered the action where one did, the attempted
version otherwise — plus `evidence:delegation:<id>` for exactly the chain
members.

Beyond the single resolution reason of §4, the independent sources are:

- `wrong_runtime` — **source A**: the binding's runtime is unknown, or its
  recorded `logical_agent_id` / `runtime_principal_id` disagree with the
  binding. **Source B**: the credential check *passed* but
  `b.runtime_principal_id ∉ credential.allowed_runtime_principal_ids`.
  Source B is chained as an `elif` on the credential check, so an invalid
  credential suppresses it (consequence (g)).
- `credential_invalid` — the presented credential is unknown, its subject
  differs from `b.credential_subject_id`, or `t` is outside
  `[valid_from, expires_at)`.
- `no_active_delegation` — **second source**: the binding's agent, the
  attempt's resource, or the binding's originating principal is unknown to
  the snapshot. Collapses with the clause-4 source in the set.
- `tenant_mismatch` — all three of those entities exist but their
  `organisation_id` values are not all equal (a principal with no
  organisation mismatches everything).
- `policy_version_mismatch` — **second source**: `a.policy_version` does
  not exist in the snapshot's policy set at all. Independent of clause 1;
  collapses in the set.
- `overprivileged_subdelegation` — only evaluated when the attempt carries
  a `proposed_delegation` **and the resolution published a chain** (clause
  0 *or* clause 1): the proposal is judged against the *selected leaf* of
  that chain (attenuation and delegator authority). It can therefore
  co-fire with `policy_version_mismatch` on a clause-1 row. With no chain,
  a proposal is not separately flagged — the resolution reason stands
  alone.

## 7. Consequences an independent implementation must reproduce

Each is pinned by a named conformance test.

- **(a)** A delegation set that is only expired or not-yet-valid yields
  `no_active_delegation`. There is no temporal member of the family; chain
  expiry is reported as absence, not as a distinct reason.
- **(b)** The revoked probe is version-blind: a revoked,
  capability-sufficient delegation is reported as `delegation_revoked`
  whatever policy version it was granted under.
- **(c)** A delegation that covers the attempt outranks the revoked
  explanation: where an unrevoked covering delegation exists at a different
  version, the outcome is `policy_version_mismatch` with its chain
  published, and the revoked probe is never consulted.
- **(d)** `delegation_revoked` outranks `no_active_delegation` even when
  `Active = ∅` — the clause-2 probe ranges over `TimeValid`.
- **(e)** `capability_exceeded` is the residual: it covers every active
  delegation that no other clause explains, including active delegations
  that are simultaneously wrong-policy *and* capability-insufficient.
- **(f)** `overprivileged_subdelegation` requires a published chain, is
  judged against the selected *leaf*, and the denial it produces still
  records the chain — including on clause-1 rows, where it co-fires with
  `policy_version_mismatch`. At audit time the family can therefore change:
  the fixture's `evt-012-overprivileged-delegation` reports
  `overprivileged_subdelegation` at action and `delegation_revoked` at
  audit, because post-revocation the chain is empty and the proposal check
  never runs.
- **(g)** An invalid credential suppresses the allowed-runtime source of
  `wrong_runtime`; a *valid* credential that excludes the binding's runtime
  principal fires it.
- **(h)** Chain selection is by lexicographically smallest capable id,
  reported root-first; clauses 2–4 report an empty chain.
- **(i)** Capable delegations that disagree on policy version reject the
  world as ambiguous instead of deciding — an error, not a denial.

## 8. Worked examples from the frozen fixture

The version-blind resolution is byte-neutral on `asteria-agentic-v1` — the
fixture registers one policy version and no action has two
capability-matching delegations — so these truth rows hold under both the
current and the prior resolution (action-time / audit-time):

| Event | `failure_reasons_at_action` | `failure_reasons_at_audit` |
|---|---|---|
| `evt-012-overprivileged-delegation` | `overprivileged_subdelegation` | `delegation_revoked` |
| `evt-013-wrong-runtime` | `wrong_runtime` | `delegation_revoked, wrong_runtime` |
| `evt-014-shared-credential` | `no_active_delegation, tenant_mismatch, wrong_runtime` | same |
| `evt-015-valid-then-revoked` | *(none — allowed)* | `delegation_revoked` |
| `evt-021-invalid-before-grant` | `capability_exceeded` | *(none)* |

`evt-014-shared-credential` shows the lexicographic serialization order;
`evt-012-overprivileged-delegation` and `evt-013-wrong-runtime` show the
audit-time family change; `evt-021-invalid-before-grant` shows clause 3 at
action time resolving to clause 0 under the later grant. Two enum values
occur in no frozen truth row: `credential_invalid` and
`policy_version_mismatch`. Both are reachable in the oracle, and both are
now labellable case kinds (`AgenticCaseKind` is a closed vocabulary of 13,
two of them exercised by no frozen case) — demonstrating them on a
published world is what waits on issue #27.

## 9. Conformance

`tests/test_agentic_failure_reason_precedence.py` transcribes §3–§5 as
independent predicates and checks the oracle against them over a
deterministic enumeration: all 24 single-delegation profiles
(policy × capability × temporal × revocation), all 576 ordered pairs of
profiles — including the pairs the spec declares ambiguous, which must
raise — the empty state, binding invisibility (including an attempt claim
naming the foreign grantee), and each `CapabilityAllows` clause in
isolation. Every enumerated evaluation also checks `delegation_chain_ids`,
`effective_policy_version`, the policy- and delegation-evidence refs, and
the side-effect rule. Named tests pin each consequence (a)–(i) — except (f)'s audit-time family
flip, which is asserted against frozen truth in
`tests/test_agentic_benchmark.py` — plus the derived-version, fallback,
and evidence re-pointing behaviour, both `policy_version_mismatch` sources
collapsing, the independent-check compositions (tenant, credential subject
and unknown credential, runtime disagreement on either recorded field,
unknown resource), the §5 well-formedness raises, and the laziness of
those raises off the walked path. The enumeration is exhaustive
over the profile dimensions the clauses read — there is no sampling.

Obligations on planned work:

- **#27 world generator** — the planner must derive each labelled case's
  expected reason from §4, not by mimicking oracle control flow, and must
  never generate a world that trips clause A; disagreement between planner
  intent and oracle output is a generator bug by definition of this
  document.
- **SW-AA-C13** — if a failure-reason field is added to
  `ObservedActionTrace`, this document defines the truth side of the
  comparison. The `always_deny` baseline will then need a declared reason
  policy; that choice extends §6 and bumps this document's version.
- **Formal model** — Appendix A restates §4 as a machine-checkable
  predicate for any future theorem-prover formalisation of the oracle; it
  is a draft statement, not a proof.

## 10. Appendix A — draft formal statement (not type-checked)

`ChainReason` models the resolution's contribution only; the independent
checks compose outside `ReasonSpec` exactly as §6 describes. Unlike §4's
first-match table, every case carries its full guard, so the
disjointness-and-totality claim is explicit.

```lean
inductive ChainReason
  | policyVersionMismatch | delegationRevoked
  | capabilityExceeded | noActiveDelegation

/-- Version-blind coverage: §3. -/
def Capable (s : WorldState) (a : ActionAttempt) (b : CanonicalBinding)
    (t : Instant) : List Delegation :=
  (Active s b t).filter (fun d => CapabilityAllows d.capability a)

/-- §4 clause A: a capable set spanning two versions refuses to decide. -/
def Ambiguous (s a b t) : Prop :=
  ∃ d₁ ∈ Capable s a b t, ∃ d₂ ∈ Capable s a b t,
    d₁.policyVersion ≠ d₂.policyVersion

def ReasonSpec (s a b t) : Option ChainReason → Prop
  | none =>
      ¬ Ambiguous s a b t ∧
      ∃ d ∈ Capable s a b t, d.policyVersion = a.policyVersion
  | some .policyVersionMismatch =>
      ¬ Ambiguous s a b t ∧ Capable s a b t ≠ [] ∧
      ∀ d ∈ Capable s a b t, d.policyVersion ≠ a.policyVersion
  | some .delegationRevoked =>
      Capable s a b t = [] ∧
      ∃ d ∈ TimeValid s b t,
        CapabilityAllows d.capability a ∧ Revoked s d
  | some .capabilityExceeded =>
      Capable s a b t = [] ∧
      (∀ d ∈ TimeValid s b t,
        CapabilityAllows d.capability a → ¬ Revoked s d) ∧
      Active s b t ≠ []
  | some .noActiveDelegation =>
      Capable s a b t = [] ∧
      (∀ d ∈ TimeValid s b t,
        CapabilityAllows d.capability a → ¬ Revoked s d) ∧
      Active s b t = []

/-- The oracle satisfies the spec on every well-formed, unambiguous state;
ambiguous states are rejected (modelled as `Except`). -/
theorem effectiveChain_reason_spec (s a b t)
    (hwf : WellFormed s) (hna : ¬ Ambiguous s a b t) :
    ∃ r, effectiveChain s a b t = .ok r ∧ ReasonSpec s a b t r.reason := by
  sorry

theorem reasonSpec_total_and_unique (s a b t)
    (hna : ¬ Ambiguous s a b t) :
    ∃! r, ReasonSpec s a b t r := by
  sorry
```

Chain selection and publication (§5) are stated separately from
`ReasonSpec`; a `Selected` predicate over `Capable` with the min-id rule
carries them.
