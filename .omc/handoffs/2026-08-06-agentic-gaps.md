# What SynthWorld can and cannot test — enterprise access and agent authority

Written 2026-08-06, after #97 merged (squash `2e67642`). Verified against that tree; file and symbol
references are given so a fresh session can re-check rather than trust this document.

Supersedes an earlier draft of this file that conflated two agentic lineages and mis-ranked the work.
See §2 — the correction matters.

## 1. What SynthWorld is, in this context

SynthWorld generates identity worlds and **scores control tests**. It is never an enforcement point.
The loop is:

```
generate world  →  project it (SCIM / OpenFGA / AuthZEN)  →  your system decides
                →  you submit a prediction  →  SynthWorld scores it against evaluator truth
```

The library ships no HTTP client (runtime deps: Faker, pydantic, pyyaml). It cannot call your policy
engine. You run your engine; you submit what it concluded.

**This gives the single most useful framing in this document: the prediction schema is the
measurement boundary.** Whatever your system cannot express in the prediction contract cannot be
scored, however much the evaluator knows. Most of what reads as a "gap" is the interface being
narrower than the truth — a different and cheaper problem than a missing control.

## 2. Correction: there are two agentic lineages, and the catalogue describes only one

`agent-authority-contract/control-catalogue.yaml` has a status column named **`asteria_v1_status`**.
It documents coverage of the frozen **Asteria Agentic v1** pack, whose observation type is
`ObservedActionTrace` — 20 fields, **no failure-reason field**. That is what control C13 is about.

The **enterprise agentic** benchmark shipped by #97 uses a much richer contract:

```
EnterpriseAgenticTraceRowV1:
  enterprise_decision, gates, final_decision, failure_reasons,
  human_principal_id, agent_principal_id, agent_account_id, runtime_id,
  evidence_refs, reconstructable_at_audit
```

where `gates` is `AgenticGatePredictionV1` — **seven individually scored gates**: subject, tenant,
agent_account, runtime, credential, capability, delegation, each
`satisfied | unsatisfied | not_applicable`. `failure_reason_exact_match` scores the reasons.

**Consequence:** "denial reasons are unscored" is true of Asteria v1 and **false** of the enterprise
agentic pack. Do not read `asteria_v1_status` as a statement about what #97 ships. Anyone planning
work from the catalogue alone will mis-rank it, as the previous version of this handoff did.

## 3. The prediction contracts, by family

| Family | Prediction contract | Shape |
|---|---|---|
| Asteria agentic v1 | `ObservedActionTrace` | 20 flat fields, no failure reasons |
| Enterprise agentic | `EnterpriseAgenticPredictionV1` → `EnterpriseAgenticTraceRowV1` | 7 gates + failure reasons + attribution + evidence |
| Enterprise identity fabric | `EnterpriseIdentityFabricPredictionV1` | checkpoints + accumulation; RBAC/ABAC sub-predictions incl. SSD/DSD evaluations, activations, birthright |
| Contextual access | `ContextualAccessPredictionV1` | rows + predicate outcomes |
| Authority governance | `AuthorityGovernancePredictionRowV1` | 22 fields: before/after state, approval chain, rationale, policy rules, controls, evidence, supersession |
| Continuous assurance | `ContinuousAssurancePredictionRowV1` | drift kind, finding open/clear ticks, recurrence, remediation, evidence continuity |

## 4. The four kinds of gap

This is the axis that matters. They are not interchangeable and they do not cost the same.

### A. Missing controls — the world cannot represent the situation

No metric can rescue these; the model has to change first. There are exactly two.

**C15 — credential-to-grant binding.** Verified field list:

```
Credential: id, issuer_principal_id, subject_principal_id,
            allowed_runtime_principal_ids, valid_from, expires_at
```

`ActionAttempt.presented_credential_id` exists, so an attempt *names* a credential — but nothing on
the credential names a delegation, audience, resource, or scope. `Capability` (which carries
`resource_ids`, `actions`, `scopes`, `purpose`) hangs off `Delegation`, not off `Credential`. So the
two are never required to agree, and issuance is validated only for referential integrity — any known
principal may mint a credential the oracle accepts. The catalogue calls this the largest single gap
in the core layer, and that is correct.

**C16 — parameter integrity.** `ActionAttempt` carries `resource_id`, `action`, `requested_scope`,
`purpose` — and no transaction parameters, no approved-payload digest. An action approved as
"transfer 10" and executed as "transfer 10,000" is the same object to the oracle. Note this is about
parameter *values*; scopes and purpose are modelled on `Capability` already.

### B. Measurement gaps — represented but unscored

Cheap. The data exists on both sides; the metric or the trace field does not.

- Asteria v1 carries `resource_id` and `requested_scope` on the trace and **no metric reads either**
  (verified: 0 occurrences in `src/synthworld/agentic/evaluation.py`).
- Asteria v1 has no failure-reason field, so C13 is unscoreable **in that lineage** and C10 (tenant
  coherence) has no metric at all.
- `purpose` is not on `ObservedActionTrace`, and is a single constant across the frozen fixture, so
  it is inert as a control even where present.

The whole Asteria v1 evaluator emits 20 metrics: 13 per-action `checks`
metrics plus seven separately constructed metrics:
`authorization_decision_precision`, `authorization_decision_recall`,
`authorization_decision_f1`, `excess_authority_rate`,
`least_privilege_accuracy`, `provenance_precision`, and
`temporal_validity_accuracy`.

### C. World-population gaps — scoreable, but no case discriminates

The model can express it and a metric would score it; the frozen fixture contains no instance that
separates a real implementation from a shortcut.

- **C01** — `originating_principal_claim` always equals canonical truth, so copying the public claim passes.
- **C03** — `credential_invalid` never fires: no expired, wrong-subject, or unissued credential case.
- **C05** — no scope-superset-only case, no purpose-mismatch case.
- **C06** — no action attempted under a *descendant* of a revoked grant.
- **C11** — five of eleven frozen actions have no covering delegation, so an echo still scores them.

All blocked on **#27**, which is larger than it looks: `reference_enterprise_agentic()` calls
`_require_frozen_access_inputs()` to *enforce* the frozen PR4 universe, and no benchmark family
consumes an operator-compiled universe. Closing #27 needs tiers on `EnterpriseAgenticTier`
(currently `SMOKE` only), a generator that accepts a compiled universe, and `compile-enterprise-access`
wired to the generators.

### D. Out of scope by construction — leave declared

Six **lab** controls (L01–L06: secret exposure, credential replay, direct-path bypass, network-policy
enforcement, authority-critical dependency failure, revocation propagation latency) require networked
execution against a real system. Two **operational** controls (L07–L08) are reported, never scored as
security.

These are not debts. A generator-plus-scorer cannot close them, and saying so is the honest output.

### Separate: C08 is a measurement-validity defect

Not a coverage gap. In both the Asteria and enterprise agentic lineages, the required evidence refs —
three base references plus one per delegation-chain member — are **derivable from public data alone**,
so a system that computes the expected identifiers while retaining no evidence scores 1.0 on all four
metrics.

That is a metric rewarding transcription over work, the same family as the ambiguity-pack leaks
(#80, #84). Treat it with that seriousness: either bind the refs to something not publicly derivable,
or restate what the metric measures.

## 5. What you can test today

Generate an enterprise world, project it, run your authorization policy, submit predictions.

**You can test:**

| Question | How |
|---|---|
| Did the policy allow/deny correctly? | `enterprise_decision_accuracy`, `final_decision_accuracy`, `authorization_decision_precision`/`recall` |
| **Why** did it deny? | `failure_reason_exact_match` plus seven individually scored gates — "right denial, wrong reason" is visible |
| Did it grant more than needed? | `excess_authority_rate`, `least_privilege_accuracy` |
| Does it respect action-time vs audit-time? | `temporal_validity_accuracy`, `audit_reconstructability_accuracy`, `reconstructable_at_audit` |
| Did it report the delegation chain? | `provenance_precision` |
| Who acted? | `human_principal_id`, `agent_principal_id`, `agent_account_id`, `runtime_id` |
| Is agent authority attenuated from the human's? | case kind `HUMAN_AUTHORITY_NOT_UNIONED` |
| Shared credentials, cross-tenant, wrong runtime, revoked or missing delegation | 20 `EnterpriseAgenticCaseKind` values |
| Entitlement reconciliation, birthright vs sprawl, SSD/DSD | identity-fabric prediction (RBAC/ABAC cells, activations, birthright assignments) |
| Governance of an authority change | 22-field authority-governance row: approval chain, rationale, policy rules, controls, evidence, supersession |

**You cannot test:**

- Whether a credential was legitimately **issued**, or bound to the grant it is exercised under (§4A)
- Whether action **parameters** match what was approved (§4A)
- Whether your system **retained** evidence, versus recomputing refs from public data (C08)
- **Purpose** correctness — inert, single constant across the fixture
- Anything requiring a live system — secret extraction, replay, bypass, network policy, revocation latency

## 6. Suggested work, and the right success criterion

**The target is discrimination, not coverage.** Driving every `partial` to `supported` is the wrong
goal: the cheapest route there is metrics that are easy to pass, which is exactly where C08 already
sits and where the ambiguity pack sat before #80. A `partial` with an honest, specific explanation is
a **finished state**, not a debt.

Ordered by value per unit effort:

1. **C08** — measurement validity. A metric that scores 1.0 without the work is worse than no metric.
2. **§4B measurement gaps** — score `resource_id` and `requested_scope`; add a failure-reason field to
   `ObservedActionTrace` if Asteria v1 is to keep parity with the enterprise lineage. Trace-schema
   changes are published-contract changes (`schema_version` bump, `DATA_DICTIONARY.md`, contract README).
3. **C15** — the largest genuine missing control, and the one an enterprise reviewer will probe first.
4. **C16** — most likely to matter to a payments or procurement reviewer; the catalogue notes that on
   the evidence of the mapped sources, the standards work does not address it either.
5. **#27** — unblocks every §4C population gap at once.
6. **Lab tier on K12** — L01–L06, per the lab design note (OSS SUTs deployed ephemerally per run,
   credentials never leave K12, no LLM in conformance runs). The recorded open question — per-run
   network-topology control — gates L03 and L04 specifically, not the whole tier.

Coverage is published **per control identifier**. The catalogue forbids aggregate fractions: the
denominator is an artefact of the file, not a standard.

## 7. Constraints

- `make ci` enforces 100% branch coverage with zero pragmas, strict mypy, ruff at line-length 88.
- Runtime deps are Faker, pydantic, pyyaml only. Core stays offline and pure.
- Frozen v1 artifacts must stay byte-identical.
- The tranche is **not** frozen at one seed — enterprise agentic, contextual access and continuous
  assurance reference builders all accept a `seed`; only identity fabric takes no arguments.
- `authority_governance` does **not** use the enterprise identity/access universe; it defines its own
  subjects and capabilities and imports only digest and serialization helpers.
