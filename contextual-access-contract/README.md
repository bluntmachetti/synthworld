# Contextual-access benchmark contract v1

This package is a bounded deterministic benchmark for relationship-aware and
attribute-aware authorization. It consumes the fixed enterprise identity/access
universe and its predeclared access atoms. It never adds a principal, account,
group, role, resource, action, access atom, or native evaluation cell.

The closed contextual vocabulary covers case assignment, on-call duty, device
posture, risk signals, and time-bounded business justification. Non-enterprise
objects are opaque anchors in a generated registry, not modeled cases, devices,
risk engines, approval workflows, services, or operational topology. EADS retains
ownership of system, dependency, network, deployment, and business-impact
topology. SynthWorld is not a PDP, PEP, identity fabric, context-feed service, or
vendor client.

## Temporal compatibility matrix

PR7 selected the already shipped `synthworld.temporal` schema `1.2.0`. The source
file is preserved byte-for-byte at SHA-256
`c994fa6fdfea7b77ac7c3c35b524da6c3538bc04c84af0c192f366bfd17c8f59`.

| Contract | Payload-family tag | Clock/order semantics | Compatibility |
|---|---|---|---|
| `synthworld.temporal` `1.2.0` | native privacy payload | integer `tick`; canonical `(tick,event_id)` prefixes | unchanged; no schedule fields are retrofitted |
| `TemporalEventEnvelopeV1` `1.0.0` | `privacy_1_2` | projects privacy `id/tick`; derived contiguous index | adapter view only; native privacy bytes remain unchanged |
| `TemporalEventEnvelopeV1` `1.0.0` | `contextual_access_1_0` | projects contextual `id/effective_tick`; derived contiguous index | separately typed payload joined by event ID |
| `TemporalEventEnvelopeV2` `2.0.0` | `privacy_1_2`, `contextual_access_1_0`, or `governance_1_0` | preserves V1 tick/order/digest/index semantics | additive governance transition; v1 remains closed and independently loadable |

Integer tick is the only deterministic world clock. `event_index` is a proof of
canonical position, not time. Generated benchmark artifacts contain no UTC.
Operational run records use nanoseconds only for durations after a benchmark
delivery coordinate, never as an alternative replay clock.

At a shared tick the phases are fixed: canonical changes become effective in
`(effective_tick,event_id)` order; delivery attempts are presented in
`(delivery_tick,delivery_order,event_id,attempt_index)` order; an external SUT may
then record acceptance duration; requests at that tick observe the resulting
canonical or presented prefix. Duplicate delivery is idempotent, and uniquely
delivered events are folded back into canonical effective order.

## Public/evaluator boundary

The public artifact publishes typed initial facts, changes, delivery attempts,
policies, adapter mapping intent, and requests. The evaluator artifact separately
publishes canonical checkpoints, evaluated predicates/rules, expected decisions,
stale-context labels, and case labels. Public projection is explicit and the
public-only loader never traverses `evaluator/`.

Expected decisions are intentionally derivable from public policy and public
facts/events. This is a transparent conformance oracle and accidental-leakage
boundary, not an anti-cheating mechanism. Held-out seeds and policy variants are
needed before using the pack to detect hard-coded answers.

Generate a deterministic smoke pack with:

```bash
synthworld generate-contextual-access \
  --tier smoke \
  --seed 20260804 \
  --output contextual-access-world
```

## External run contract

The run plan predeclares a closed `SW-CA-C01`–`SW-CA-C06` coverage matrix and
typed probes for mapping/ingestion, authorization decisions, protected-system
enforcement, context delivery/acceptance, synchronization faults, and evidence
correlation. It binds the enterprise and contextual public roots, universe,
access-atom, registry, mapping, request, and public case-inventory digests plus
exact public request, event, and delivery-attempt IDs. Evaluator case IDs and
labels are forbidden from the plan and observations.

Feed delay is measured in ticks. SUT acceptance and post-acceptance decision
propagation are separately bounded in nanoseconds. They are never converted into
one score. If no correct post-acceptance decision appears, the terminal result is
an explicit right-censored failure; it is not silently omitted from the
denominator.

The pure Shared Signals projection emits the selected schedule coordinates and
versioned `urn:synthworld:event:contextual-...` event identifiers only. Every row
sets its standardized CAEP event type to null and declares the custom-profile
semantic delta. SET construction, issue time, signing, transmission, and vendor
ingestion remain external; run observations record SET issue, delivery,
acceptance, and later decision coordinates independently.

Receipt-v2 consumers use these exact family roles and paths:

| Role | Path | Phase |
|---|---|---|
| `contextual_access_run_plan` | `context/contextual-access-run-plan.json` | product |
| `contextual_access_observations` | `observations/contextual-access.json` | product |
| `contextual_access_run_truth` | `evaluator/contextual-access-run-truth.json` | evaluation |
| `contextual_access_evaluation` | `evaluation/contextual-access-report.json` | evaluation |

The generic receipt-v2 source/input/output/execution paths remain unchanged. The
deterministic reference adapter now executes preflight, product-before-truth
staging, every observation variant, all four phases, synchronization faults, and
every scorer denominator through a replay-validated receipt. It proves only the
family's schema, staging, and scorer conformance. No vendor API or runtime
integration ships here.

Live contextual runners use the same boundary in two explicit phases: stage the
preflight-bound product execution first, then construct completion metadata and
call the contextual finalizer. Before evaluator truth is loaded, the finalizer
replays the run plan, public input, adapter output, component inventory,
provenance, product-input binding, and every staged artifact digest. This permits
honest post-execution timestamps without weakening the product/evaluator split.

| Acceptance surface | State | Claim permitted |
|---|---|---|
| Deterministic contextual fake | Complete | Protocol/scorer conformance |
| Deterministic agent-authority fake | Complete | Protocol/scorer conformance |
| Agent-authority disposable reference deployment | Complete as an opt-in external harness | Reference-configuration `live_lab_conformance` only |
| Contextual live reference deployment | Not executed | No live contextual or vendor claim |
| SGNL pilot | External milestone after the reference-deployment gate | None yet for SGNL behaviour or enforcement |

Live-lab readiness requires a separately executed, instrumented disposable
deployment with receipt-bound evidence. A managed-service decision is not by
itself enforcement proof: the protected enforcement point and target side effect
must be observed independently. Key custody for held-out or comparative runs is
also an operator concern and is not supplied by these deterministic fixtures.

Generate or verify schemas and examples with:

```bash
uv run python contextual-access-contract/tools/generate_contract.py
uv run python contextual-access-contract/tools/generate_contract.py --check
```
