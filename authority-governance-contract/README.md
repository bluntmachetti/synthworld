# Authority-change governance conformance

This contract is a bounded ground-truth benchmark for reconstructing why an
authority change occurred. It is not an IGA workflow engine, approval UI, GRC
platform, policy decision point, runtime enforcement service, or vendor adapter.
EADS continues to own enterprise and operational topology; this package models
only fictional identity authority, governance observations, and evaluator truth.

The `1.0.0` fixture contains 12 hand-inspectable cases covering a valid grant,
wrong and expired approvers, approved-versus-enacted scope drift, denied-but-
enacted authority, an emergency exception, decision-time policy selection,
missing retained evidence, supersession linkage, revocation timing drift,
conflicting decisions, and a structurally valid unauthorized change. The
examples remain generated contract documentation. The byte-identical
public/evaluator fixture is frozen separately under
`synthworld.benchmarks/authority-governance-v1`, where a root `SHA256SUMS`
binds both payloads and both visibility manifests.

## One clock and deterministic precedence

All request, decision, enactment, expiry, and audit coordinates are nonnegative
integer ticks on SynthWorld's shipped temporal axis. No UTC field participates
in generation, ordering, identity, replay, or scoring. `TemporalEventEnvelopeV2`
preserves V1's fields, payload digest, canonical `(effective_tick,event_id)`
ordering, and derived zero-based index. V2 adds only `governance_1_0`; V1 remains
closed and rejects that family. Neither loader upgrades or relabels an artifact.

For multiple decisions, the controlling decision is the last canonical
`(effective_tick,event_id)` decision strictly before enactment. A later policy,
decision, or evidence record cannot retroactively authorize an earlier change.
Malformed references and phase ordering are rejected. A well-formed but
unauthorized or incorrectly enacted history remains valid input and is scored.

## Visibility and metrics

Public input contains observed requests, decisions, enactments, audits, bounded
policy rules, approver mandates, and opaque evidence references. Evaluator data
is serialized separately and holds case labels, canonical before/after state,
governance and approver verdicts, applicable decision-time policy/control,
required evidence, expected enactment, and reconstructability truth.

Reports contain no aggregate security score. State, governance authority,
policy/rationale, evidence/observability, and enactment metrics each publish an
integer numerator, denominator, support, and denominator meaning. Action
auditability remains an independent Asteria/enterprise-agentic measurement;
this family scores authority-change auditability.

Three public-only baselines deliberately fail distinct dimensions: inferring
validity from final state, trusting any recorded approval, and evaluating all
history under the latest policy.

Generate or verify the schemas and examples with:

```bash
uv run python authority-governance-contract/tools/generate_contract.py
uv run python authority-governance-contract/tools/generate_contract.py --check
```
