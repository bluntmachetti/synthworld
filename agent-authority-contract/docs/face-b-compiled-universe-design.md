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
| `tier` | Exact v2 Face B tier. A v1 `smoke` bundle cannot be relabelled as a v2 tier. |
| `seed` | Explicit integer generation input. |
| `projection_config_digest` | Digest of canonical, non-secret generation configuration. |
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

The future tier type belongs to v2. It must not widen the v1 literal field.

| Tier | Purpose | Minimum semantic obligation |
| --- | --- | --- |
| existing v1 `smoke` | Preserve the frozen small reference projection. | No new Face B claim. |
| v2 `conformance` | Smallest discriminating Face B suite. | Every required case family has at least two negative attempts and two positive counterparts. |
| v2 `coverage` | Exercise the supported cross-product of hierarchy, identity, authority, placement, lifecycle, and exception dimensions. | Every supported enum value and named edge category appears; each family still meets the conformance floor. |
| v2 `scale` | Exercise larger populations and event schedules without changing semantics. | Preserve the coverage case mix and declared ratios while increasing bounded counts. |

Tier selection is explicit configuration and is recorded in both manifests. Each
tier publishes exact counts and an independent denominator for every metric and
case family. Scale is not a new security property, and results from different tiers
must not be blended into one aggregate score.

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
| hierarchy and classification | silent deep-hierarchy flattening; present classification treated as authority | declared collapse outcome; null and present classification retained without invented authority |
| ownership semantics | owner, approver, steward, or accountable party treated as an authorization grant | explicit grant coexisting with a separately typed ownership relation |
| approved exception | expired/not-yet-valid exception; wrong subject or access atom | exact active exception and the equivalent action after ordinary authorization is restored |
| C15 issuance and binding | unauthorized issuer; wrong authority source/audience/resource/scope | entitled issuer and exact credential-to-authority binding |
| C16 intent and parameters | payload replay with a material parameter changed; approval used for a different target/action | exact normalized payload approved by the originating principal |

C15 and C16 rows are mandatory design targets but cannot enter a generated suite
until the independently versioned public input, evaluator truth, submission, replay,
and metric contracts described by `c15-c16-v2-design.md` are implemented.

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
They are separately typed and written to physically distinct roots.

Public projections must be constructed field by field. Dumping an oracle-bearing
model with an exclusion list is prohibited. Boundary tests must scan nested JSON,
JSONL, manifests, package archives, documentation output, and search indexes.

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

## Adapter-gap disposition

| Sanitized Phase 1 gap | Face B disposition |
| --- | --- |
| Region/regulatory/geopolitical metadata lacks a v1 unit mapping. | Keep placement orthogonal and typed in v2; never infer tenant or unit semantics. |
| Domain trees may be deep or uneven. | Plant declared collapse, preserved-depth, and rejected-shape cases; score silent flattening separately. |
| Classification may be null or present without a v1 target. | Preserve null-versus-present as a typed distinction and plant cases proving neither implies authority. |
| Ownership has several non-grant meanings. | Type ownership, stewardship, approval, and accountability separately; require an explicit authority grant. |
| `size` and `headcount` are unreliable. | They never control Face B population. Use explicit tier/configuration and published deterministic policies. |
| Service types and labels may contain vendor vocabulary. | Accept only closed fictional service kinds; reject unsupported values before public projection. |
| Phase 1 has no NHI, credential, delegation, or action mapping. | Gate those populations and cases on implemented C15/C16 v2 contracts. |
| Adapter input may exclude, partially fail, or yield zero organisations. | Face B accepts only a complete, non-empty, digest-bound envelope; it never recasts adapter failure as success. |

## Version-transition and publication gates

Runtime implementation requires a later reviewed branch that introduces separate
enterprise v2 models, schemas, generator family, CLI selection, replay, submission,
metrics, tests, and documentation. It must not extend frozen v1 models in place.

A frozen Face B benchmark additionally requires:

- numeric tier budgets and deterministic planted-case counts;
- complete public/evaluator leakage tests;
- discriminating baselines and independent metric denominators;
- generated schemas and schema/model agreement tests;
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
