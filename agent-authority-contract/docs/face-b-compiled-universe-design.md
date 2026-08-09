# Face B compiled-universe design

Status: proposed design contract for review, 2026-08-09.
Design version: `0.1.0-design`.

This note defines how a future enterprise-agentic Face B generator may consume a
compiled enterprise identity/access universe, select a generation tier, and plant
discriminating authority cases. It is not a runtime implementation, schema,
benchmark artifact, or claim of compatibility with a real EADS export.

The design depends on the sanitized requirements in
`enterprise-identity-access-contract/EADS_ADAPTER_GAPS.md` and on the accepted
`agent-authority-contract/docs/c15-c16-v2-design.md`. It does not change either
contract.

## Decision summary

- Keep the existing `EnterpriseAgenticTier.SMOKE`, enterprise v1 models, Asteria
  v1 models, schemas, artifacts, checksums, loaders, and scorers unchanged.
- Add future Face B tiers only in an independently versioned enterprise-agentic
  contract. The target tier vocabulary is `conformance`, `coverage`, and `scale`.
- Consume a versioned compiled-universe envelope. Face B never parses raw EADS,
  guesses an adapter vintage, or receives a source path.
- Bind synthetic multi-organisation topology, population policy, compiler build,
  and sanitized mapping-fidelity evidence as independently digested inputs.
- Treat tenant as the hard security isolation boundary. Treat organisation as an
  explicit authorization scope within a tenant, not as an alias for tenant.
- Deny same-tenant cross-organisation access unless an exact grant authorizes it.
  Cross-tenant access is always denied.
- Keep region, regulatory, and geopolitical placement orthogonal to tenant and
  organisation. Placement never grants authority implicitly.
- Require planted negative cases and positive counterparts for every declared
  case family, with an independent denominator per family.
- Keep public product input and evaluator truth separately typed and physically
  serialized. Construct the public projection field by field.
- Gate agent, NHI, credential-to-grant, delegation, and action-payload cases on
  implemented C15/C16 v2 contracts. Do not generate those cases against v1.
- Require a later benchmark-version transition before any Face B artifact is
  frozen or published.

## Scope and non-goals

Face B begins after enterprise authoring and compilation. Its input is a
SynthWorld-owned compiled universe plus explicit generation configuration. Raw
source parsing, vendor normalization, migration, hosted execution, production
authorization, and external-system behavior remain outside the generator.

The Phase 1 EADS adapter is evidence for gap semantics only. Its synthetic fixtures
do not establish compatibility with 31 real exports. A representative sanitized
export or exact serialized schema remains an external gate for that claim.

This design does not:

- add enum members to `EnterpriseAgenticTier` in v1;
- modify `src/synthworld/agentic/enterprise/`;
- implement C15 or C16 models, replay, metrics, or artifacts;
- add a raw-EADS input mode to a generator or CLI;
- interpret BIAN-like labels, hierarchy, or services as BIAN semantics;
- publish a private adapter report, namespace salt, source digest, or topology;
- define a general-purpose enterprise simulator; or
- authorize a frozen benchmark transition.

## Compiled-universe intake contract

The runtime implementation must introduce a bounded
`EnterpriseAgenticCompiledUniverseInputV2`-equivalent model in the enterprise
lineage. The name is illustrative until the v2 schema review, but the following
semantics are required.

### Required envelope fields

| Field | Requirement |
| --- | --- |
| `schema_version` | Exact supported compiled-intake contract version. Unknown versions fail closed. |
| `universe_id` and `universe_version` | Opaque, safely fictional logical identity for the compiled universe. |
| `compiler_contract_version` | Exact enterprise compiler contract used to create the input. |
| `compiled_profile_id` | Explicit caller-selected profile. It is never inferred from shape or field presence. |
| `synthetic_topology_profile_id` | Exact fictional topology profile; multi-organisation C10 cases require `face-b-synthetic-multi-org-v1`. |
| `synthetic_topology_digest` | Digest of the separately typed synthetic topology authoring input. |
| `tier` | Exact v2 Face B tier. A v1 `smoke` bundle cannot be relabelled as a v2 tier. |
| `seed` | Explicit integer generation input. |
| `projection_config_digest` | Digest of canonical, non-secret generation configuration. |
| `population_policy_id`, `population_policy_version`, and `population_policy_digest` | Exact policy that produced already-compiled principal counts. |
| `mapping_fidelity_digest` | Digest of a private, sanitized mapping-fidelity summary; the all-zero synthetic summary is still explicit. |
| `public_universe_digest` | Digest of the separately typed compiled public universe. |
| `evaluator_universe_digest` | Digest of the separately typed compiler truth. |
| `compiler_build_digest` | Reproducible digest of the compiler implementation input, not a host or wall-clock identifier. |
| `provenance_chain` | Canonically ordered version and digest bindings for each build step. |

The build process may hold the public universe and evaluator universe together in
private memory, but it must never serialize a combined oracle-bearing artifact as
product input. The Face B public projection is built explicitly from the compiled
public model. Evaluator bindings are built explicitly from compiler truth.

The intake validator must reject:

- missing, duplicate, unknown, or mismatched digest bindings;
- unsupported schema, compiler, profile, or tier versions;
- a public/evaluator universe identity or version mismatch;
- non-canonical set-like collections or event order;
- a caller-selected profile that does not match the bound compiler contract;
- raw source paths, source labels, namespace salts, or untyped extension fields;
- `size`, `headcount`, or an attempt to recompute population from source-scale
  fields after compilation;
- BIAN interpretation inferred from a label, hierarchy level, or service shape;
- zero organisations or an empty principal/resource/action universe; and
- an attempt to infer a source or adapter vintage from payload shape.

### Generator boundary

The required pipeline is:

```text
explicit synthetic authoring input or private adapter
  -> enterprise compiler
  -> versioned compiled-universe envelope
  -> Face B case planner
  -> separate public and evaluator projections
  -> independent manifests and digests
```

Face B starts at the envelope. Adapter failures, exclusions, and partial success
must be resolved before intake. A partial adapter run is not silently converted
into a successful generator run.

### Synthetic multi-organisation authoring profile

Same-tenant cross-organisation C10 cases are admitted only when the compiled
envelope binds `face-b-synthetic-multi-org-v1`. Its upstream, separately typed
authoring input contains opaque tenant keys, each tenant's ordered fictional
organisation keys, typed placement references, the selected tier, and no grants.
Version 1 has the exact tier topology declared below: 2 tenants and 3 organisations,
4 and 8, or 16 and 64. Every tier includes at least one multi-organisation tenant
and one separate tenant. Grants are compiled separately, so topology cannot imply
authorization.

The authoring bytes use the canonical digest profile below and are bound by
`synthetic_topology_digest` through the compiler provenance edge. Face B may select
cases from compiled topology but may not add, merge, or move an organisation. A
Phase 1 EADS adapter result cannot claim this profile because its one-to-one mapping
makes the scenario unobservable. It remains ineligible for these C10 cases until a
separately reviewed compiler/adapter contract supplies equivalent typed topology.

### Private mapping-fidelity summary

The compiler boundary supplies a private `MappingFidelitySummaryV2`-equivalent
record containing only closed reason codes and counts for hierarchy collapses,
classification-null rows, classification-present rows, ownership widenings,
`owning_team_id` divergences, unsupported ownership rows skipped, ignored source
scale rows, exclusions, and failed inputs. It contains no raw labels, paths, salts,
or source topology.

An adapter-derived envelope must bind that record to the private adapter report and
compiler output through `mapping_fidelity_digest`. A wholly synthetic envelope must
bind an explicit zero-loss summary. Face B may plant fidelity cases only for a
declared category whose compiler output or synthetic authoring profile contains the
corresponding typed structure. Private fidelity evidence never enters product input.

Adapter-derived principal counts bind `eads-human-population-policy-v1`. Purely
synthetic Face B counts bind `face-b-synthetic-population-policy-v1`, whose exact
tier counts are declared below. No profile may substitute one policy identity for
the other while retaining its digest.

## Tenant, organisation, and placement decision

Tenant is the security boundary for `SW-AA-C10`. Principal, logical agent,
runtime, credential, resource, and enforcement context must resolve to one tenant.
An identifier valid in one tenant confers no authority in another, even if its
opaque text collides.

Organisation is a separate authorization scope. A generated v2 universe may contain
multiple fictional organisations in one tenant to make this distinction observable.
Same-tenant cross-organisation action is denied by default and becomes valid only
when an exact capability or delegation binds the target organisation, resource,
action, scope, purpose, and time. This generated-world decision does not change the
Phase 1 adapter's one-source-organisation-to-one-tenant mapping.

Region, regulatory regime, and geopolitical placement are independent typed
dimensions in a future v2 universe. They may constrain case selection or policy,
but never create a tenant, organisation, unit, ownership relation, or grant by
inference. Unknown placement remains explicit unknown data rather than a guessed
mapping.

## Tier contract

The future `EnterpriseAgenticTierV2` is a closed enum with exact values
`conformance`, `coverage`, and `scale` under target schema `2.0.0`. The v2 intake
rejects `smoke`; v1 code remains the only owner of that value.

| Tier | Tenants / organisations | Humans / NHIs / resources | Case-action budget | Event ceiling |
| --- | --- | --- | --- | --- |
| `conformance` | 2 / 3 | 48 / 8 / 24 | 86 | 256 |
| `coverage` | 4 / 8 | 256 / 32 / 128 | 172 | 1,024 |
| `scale` | 16 / 64 | 4,096 / 256 / 1,024 | 1,720 | 10,000 |

Tier selection is explicit configuration and is recorded in both manifests. Each
tier publishes exact realized counts and an independent denominator for every
metric and case family. The budgets are exact: a planner that cannot satisfy them
fails rather than silently reducing coverage. Scale is exactly ten coverage case
plans concatenated under distinct domain-separated case namespaces; it is not a new
security property. Results from different tiers must not be blended into one
aggregate score.

Eighteen standard families receive 4, 8, and 80 actions respectively: C01, C03,
C05, C06, C11, hierarchy, classification, ownership, the six C15 subfamilies, and
the four C16 subfamilies specified below. C10 receives 6, 12, and 120 actions.
Approved exceptions receive 8, 16, and 160 actions. These sum to the declared tier
budgets.

`coverage` exercises every supported value in this finite dimension register:
same/cross tenant; same/cross organisation; human/agent/workload/service principal;
both enterprise agent authorization mapping kinds; not-yet-valid/valid/expired/
revoked credential and delegation state; resource/action/scope/purpose/audience
capability mismatch; current/stale/unknown policy; owner/approver/steward/
accountable/unsupported ownership; null/present classification; preserved/
collapsed/rejected hierarchy; all approved-exception reasons and validity states;
and every C15/C16 subfamily. This is enum and edge-category coverage, not an
unbounded Cartesian-product claim.

## Case-planting policy

Planting operates on canonical compiled keys and a deterministic case plan. It may
not search generated output until a desired verdict appears. The planner first
declares the complete case inventory, then derives all records from the seed,
compiled-universe digests, tier, schema versions, and canonical event schedule.

For each required family, `conformance` includes at least two negative attempts,
two positive counterparts, two distinct principals or subjects, and two distinct
resources where the invariant permits. `coverage` expands dimensions rather than
repeating one case under new labels.

| Family | Required negative cases | Positive counterparts |
| --- | --- | --- |
| C01 originating principal | self-asserted principal substitution; shared identity across distinct originators | system-established human origin; system-established NHI origin after v2 support |
| C03 credential subject | subject mismatch; credential used by an unbound runtime | matching subject and runtime at the same lifecycle point |
| C05 capability boundary | excess resource/action; excess scope or wrong purpose | exact resource, action, scope, and purpose |
| C06 action-time validity | action after revocation; action before grant or validity | equivalent action inside the valid interval |
| C10 tenant/organisation | cross-tenant collision; same-tenant cross-organisation action without an exact grant | same-organisation allow; explicitly granted same-tenant cross-organisation allow |
| C11 policy version | stale policy; unknown or mismatched policy version | exact action-time policy version |
| hierarchy | silent deep-hierarchy flattening; uneven hierarchy accepted without a declared outcome | declared preserved, collapsed, or rejected outcome |
| classification | present classification treated as authority; null classification guessed from labels | null and present classification retained without invented authority |
| ownership semantics | widening or owning-team divergence omitted from fidelity evidence; unsupported ownership converted to a grant | explicit grant coexisting with a separately typed ownership relation and bound fidelity outcome |
| approved exception | expired/not-yet-valid exception; wrong subject or access atom | exact active exception and the equivalent action after ordinary authorization is restored |
| C15 issuance and binding | See the six independently denominated subfamilies below. | Entitled issuance and exact named-authority use for each subfamily. |
| C16 intent and parameters | See the four independently denominated subfamilies below. | Exact normalized payload and single-use semantics for each subfamily. |

C15 and C16 rows are mandatory design targets but cannot enter a generated suite
until the independently versioned public input, evaluator truth, submission, replay,
and metric contracts described by `c15-c16-v2-design.md` are implemented.

### C15/C16 inherited subfamilies

Face B inherits, rather than summarizes away, the accepted v2 design. Each listed
subfamily is a standard family with its own case labels, metrics, false-allow and
false-deny counts, and denominator:

- C15 issuer entitlement: entitled versus unauthorized issuer decision.
- C15 named authority source: exact bound source versus a different source.
- C15 issuer ceiling: exact or narrower authority versus authority exceeding the
  issuer's entitlement.
- C15 subject/runtime binding: matching subject and runtime versus either mismatch.
- C15 revocation: valid named authority versus that exact authority after revocation.
- C15 anti-laundering: invalid or insufficient named authority while an unrelated
  live grant could otherwise make the action valid.
- C16 material-parameter integrity: exact parameters versus one material mutation.
- C16 target/action substitution: exact target/action versus either substitution.
- C16 approval replay: first exact use versus reuse outside the approved use rule.
- C16 failed mutation: a rejected mutation with no side effect versus an exact
  approved action, scored separately from successful mutation attempts.

C15 replay resolves only the authority source named by the credential. It must not
search for, substitute, or fall back to another live grant, capability, delegation,
or approval that would rescue the action.

For a scored issuance request, public input must not contain a later issued-record,
credential, or outcome event that reveals the oracle decision before submission.
If an issuance result is needed for a later non-scored sequence, it belongs after a
submission boundary in a separately versioned sequence, not beside the scored
request.

## Approved exception semantics

Face B reuses the existing closed `ApprovedExceptionReason` vocabulary:
`business_need`, `emergency`, `migration`, and `remediation_pending`. A reason is
metadata, not authority. An exception is valid only for its exact subject, access
atoms, owner, and validity interval.

The planner must include active, expired, not-yet-valid, wrong-subject, and
wrong-access-atom cases. `coverage` includes every reason value. Reports state the
exception-case denominator separately; exception success cannot conceal failures in
ordinary grant, delegation, C15, or C16 metrics.

Public input may contain the exception record needed by a product to decide the
case. Evaluator-only case labels, expected decisions, canonical bindings, and
failure reasons remain in evaluator truth.

## Public/evaluator and fictionalisation boundary

The public model contains only product inputs needed to make and report a decision.
The evaluator model contains expected decisions, case labels, hidden canonical
bindings, planted mutations, authority failure reasons, and metric denominators.
The submission model contains only product-reported decisions and permitted
observability fields. All three are separately typed and written to physically
distinct roots.

Public projections must be constructed field by field. Dumping an oracle-bearing
model with an exclusion list is prohibited. Boundary tests must scan nested JSON,
JSONL, manifests, submission artifacts, package archives, documentation output, and
search indexes. A submission cannot contain evaluator labels or bindings, and
evaluator truth cannot be required to validate submission structure.

All names, domains, phone numbers, addresses, credential handles, organisation
labels, service labels, products, vendors, and topology are safely fictional.
Opaque IDs use a dedicated deterministic namespace. Private adapter salts, raw
source labels, source paths, source payload digests, and per-organisation gap
reports never enter Face B artifacts.

## Determinism and provenance

Generation is a pure function of the bound compiled universe, explicit seed,
projection configuration, tier, schema versions, case plan, and event schedule.
Wall-clock time, random UUIDs, locale, host state, filesystem order, and source path
are forbidden inputs.

The run manifest binds at least:

- compiled-intake schema and compiler contract versions;
- Face B generator, projection, case-plan, and scoring versions;
- tier and seed;
- canonical projection-configuration digest;
- compiled public and evaluator universe digests;
- case-plan and event-schedule digests;
- generated public input, evaluator truth, and submission-schema digests; and
- canonically ordered provenance-chain entries for every transformation.

Set-like collections use canonical ordering. Event streams and provenance chains
use stable semantic order. Serialization is UTF-8 with LF line endings and one
trailing newline.

### Canonical digest and provenance profile

Face B v2 uses `synthworld-artifact-digest-v1`. Every digest is lowercase SHA-256.
For an existing artifact, the digest covers its exact bytes. Generated structured
records use `synthworld-canonical-json-v1`: UTF-8 JSON, object keys sorted by Unicode
code point, no floats or non-finite numbers, no insignificant whitespace, semantic
array order preserved, canonical set-like arrays pre-sorted, LF, and one trailing
newline.

An artifact-set manifest contains canonical rows of POSIX-relative path, byte size,
and exact-byte SHA-256 sorted by path. Symlinks and paths outside the declared root
are rejected. The manifest excludes itself; the artifact-set digest covers the
canonical manifest bytes. Public, evaluator, and submission roots each have their
own manifest and artifact-set digest.

The compiler build record binds the exact wheel SHA-256, `uv.lock` SHA-256, package
version, compiler contract version, and population-policy digest. Its digest covers
that canonical record. It never substitutes a host name, environment path, build
time, or mutable branch name for reproducible build identity.

Each provenance edge is a canonical record containing step ID, tool ID and version,
input artifact-set digests, configuration digest, output artifact-set digests, and
the previous edge digest. Edges are ordered by declared pipeline step and then step
ID. Reordering, dropping, or substituting an input changes the terminal provenance
digest. A source payload digest remains private adapter evidence and is not
relabelled as an exact-byte artifact or compiler-build digest.

## Adapter-gap disposition

| Sanitized Phase 1 gap | Face B disposition |
| --- | --- |
| Region/regulatory/geopolitical metadata lacks a v1 unit mapping. | Keep placement orthogonal and typed in v2; never infer tenant or unit semantics. |
| Domain trees may be deep or uneven. | Plant declared collapse, preserved-depth, and rejected-shape cases; score silent flattening separately. |
| Classification may be null or present without a v1 target. | Preserve null-versus-present as a typed distinction and plant cases proving neither implies authority. |
| Ownership has several non-grant meanings. | Bind widening, skipped-row, and owning-team-divergence counts in private fidelity evidence; type ownership, stewardship, approval, and accountability separately; require an explicit authority grant. |
| `size` and `headcount` are unreliable. | Exclude them from Face B intake. Bind already-compiled counts and the exact `eads-human-population-policy-v1` identity/version/digest when adapter-derived. |
| Service types and labels may contain vendor vocabulary. | Accept only closed fictional service kinds; reject unsupported values before public projection. |
| Phase 1 has no NHI, credential, delegation, or action mapping. | Gate those populations and cases on implemented C15/C16 v2 contracts. |
| Adapter input may exclude, partially fail, or yield zero organisations. | Face B accepts only a complete, non-empty, digest-bound envelope; it never recasts adapter failure as success. |

BIAN interpretation remains deferred. A BIAN-like source label or hierarchy never
acquires BIAN semantics in the adapter, compiler, topology profile, or Face B case
planner.

## Version-transition and publication gates

Runtime implementation requires a later reviewed branch that introduces separate
enterprise v2 models, schemas, generator family, CLI selection, replay, submission,
metrics, tests, and documentation. It must not extend frozen v1 models in place.

A frozen Face B benchmark additionally requires:

- exact tier budgets and deterministic planted-case counts defined above;
- complete public/evaluator/submission leakage tests;
- discriminating baselines and independent metric denominators;
- generated schemas and schema/model agreement tests;
- an independently versioned C16 canonical-payload digest profile with
  cross-language conformance vectors and mismatch-path fixtures;
- tests proving scored issuance requests do not leak outcome events before the
  submission boundary and C15 replay cannot launder authority through another grant;
- checksums, integrity and package-content gates;
- clean-install deterministic reproduction from the built wheel;
- a benchmark registry publication decision;
- adversarial and safety review; and
- a new `GOLDEN_REVIEW.md` record.

Real EADS compatibility remains blocked until a representative sanitized export or
exact serialized schema is pinned and tested. That evidence is not required to
prove this synthetic compiled-universe contract, and synthetic contract success must
not be described as real-export validation.

## Design acceptance criteria

- Every row in `EADS_ADAPTER_GAPS.md` maps to a requirement or named deferral.
- Tier, intake, C10, planting, exception, determinism, and provenance semantics are
  explicit and do not depend on raw EADS data.
- C15/C16 dependencies agree with the accepted design and create no v1 fields.
- Every declared case family has multiple negatives, positive counterparts, and an
  independent denominator.
- The public/evaluator split is physical, typed, and field-by-field.
- Existing `1.0.0` schemas and frozen artifacts remain byte-identical.
- Runtime implementation, benchmark publication, and real-export compatibility
  remain separate later gates.
