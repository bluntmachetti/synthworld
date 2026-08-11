# Face B compiled-universe contract design

Status: design under review, 2026-08-11.
Design version: `0.2.0-design`.
Target contract family: `synthworld.enterprise-agentic-face-b`.
Target schema version: `1.0.0`.
Target benchmark ID: `synthworld-enterprise-agentic-face-b-v1`.

This note defines a future, independently versioned enterprise-agentic Face B
benchmark family. It may consume a compiled synthetic enterprise universe and
plant discriminating authority cases. It is not a runtime implementation,
schema, benchmark artifact, freeze decision, publication authorization, or
claim of compatibility with a real EADS product or export.

The design uses requirements evidence from the
[fictional EADS-shaped adapter gap record](../../enterprise-identity-access-contract/EADS_ADAPTER_GAPS.md)
and depends on the applicable enterprise C15 and C16 control-scoped contract
families in the
[C15/C16 contract design](c15-c16-contract-design.md). Those families remain
under review. Face B cannot implement their cases until they are accepted and
implemented with public input, evaluator truth, submission, replay, and metric
contracts.

## Decision summary

- Face B starts a new `1.0.0` family. It is not a generic enterprise v2
  contract and does not reuse an existing `2.0.0` identity.
- Existing enterprise v1, Asteria v1, Asteria C08 v2, enterprise C08 v2, and
  their schemas, artifacts, checksums, loaders, and scorers remain unchanged.
- Face B neither implements nor supersedes C08. A future benchmark composing
  C08 with Face B requires another identity and benchmark transition.
- Face B consumes a versioned compiled-universe envelope. It never parses raw
  EADS-shaped input, guesses an adapter vintage, or receives a source path.
- Tenant is the hard security-isolation boundary. Organisation is a distinct
  authorization scope inside a tenant. Placement is orthogonal to both.
- Every scored decision must be solvable from public product input alone.
  Private mapping-fidelity evidence may test generator integrity but cannot
  determine a product-visible expected decision.
- Public product input, evaluator truth, submissions, reports, and visibility
  manifests use separately typed models and physically separate artifacts.
- The proposed `conformance`, `coverage`, and `scale` tiers are blocked until
  the complete Face B case-family register is accepted. There is no implicit
  pre-C15/C16 profile.
- A separate benchmark transition, integrity record, registry decision,
  publication authorization, and review record are required before any Face B
  artifact is frozen or published.

## Family identity and coexistence

The future implementation owns this bounded namespace:

| Surface | Reserved Face B identity |
| --- | --- |
| Contract family | `synthworld.enterprise-agentic-face-b` |
| Contract version | `1.0.0` |
| Benchmark ID | `synthworld-enterprise-agentic-face-b-v1` |
| Python package | `synthworld.agentic.enterprise_face_b` |
| Schema root | `agent-authority-contract/schemas/enterprise-agentic-face-b/1.0.0/` |
| Compiled intake | `enterprise-agentic-face-b-compiled-input-v1` |
| Public input | `enterprise-agentic-face-b-public-input-v1` |
| Evaluator truth | `enterprise-agentic-face-b-evaluator-truth-v1` |
| Submission | `enterprise-agentic-face-b-submission-v1` |
| Evaluation report | `enterprise-agentic-face-b-report-v1` |
| Public manifest | `enterprise-agentic-face-b-public-manifest-v1` |
| Evaluator manifest | `enterprise-agentic-face-b-evaluator-manifest-v1` |
| Root visibility manifest | `enterprise-agentic-face-b-root-visibility-manifest-v1` |

These identities are design reservations, not implemented capabilities. An
implementation must generate schemas from dedicated immutable models rather
than extending the frozen `SynthWorld`, enterprise v1, Asteria v1, or C08 v2
models.

The C08 v2 families remain independent C08-only benchmarks. Face B does not
import their manifests, metrics, registry rows, frozen bytes, or publication
claims. A consumer may compare results across independent benchmarks but must
not aggregate or relabel them as one score. Composition requires a newly
reviewed family and benchmark ID.

## Scope and non-goals

Face B begins after synthetic enterprise authoring and compilation. Its only
runtime input is a SynthWorld-owned compiled-universe envelope plus explicit
generation configuration. Raw source parsing, vendor normalization, migration,
hosted execution, production authorization, and external-system behavior remain
outside the generator.

This design does not:

- add enum members or fields to an existing v1 or C08 v2 model;
- implement C15 or C16 contracts, cases, replay, or metrics;
- add a raw-EADS-shaped input mode to a generator or CLI;
- infer BIAN semantics from names, hierarchy, or services;
- define a general-purpose enterprise simulator or identity provider;
- publish private adapter reports, salts, source paths, source payload digests,
  or raw topology;
- authorize an implementation, benchmark freeze, registry transition, or
  external publication; or
- claim real-EADS compatibility, conformance, coverage, or deployment evidence.

## Compiled-universe intake

The implementation must introduce a dedicated immutable
`FaceBCompiledUniverseInputV1` model. It must reject extras and recursively mark
synthetic records with `synthetic: true`.

### Required envelope bindings

| Field | Requirement |
| --- | --- |
| `schema_version` | Exact Face B compiled-intake version `1.0.0`; unknown versions fail closed. |
| `universe_id`, `universe_version` | Opaque safely fictional logical identity and explicit version. |
| `compiler_contract_id`, `compiler_contract_version` | Exact compiler family and version that produced the input. |
| `compiled_profile_id` | Explicit caller-selected profile; never inferred from payload shape. |
| `synthetic_topology_profile_id` | Exact fictional topology profile. Multi-organisation C10 cases require `face-b-synthetic-multi-org-v1`. |
| `synthetic_topology_digest` | Digest of the separately typed synthetic topology authoring input. |
| `tier` | Exact accepted Face B tier; v1 `smoke` and C08 tiers are invalid. |
| `seed` | Explicit bounded integer generation input. |
| `projection_config_digest` | Digest of canonical non-secret generation configuration. |
| `population_policy_id`, `population_policy_version`, `population_policy_digest` | Exact policy and canonical policy input that produced compiled counts. |
| `mapping_fidelity_digest` | Digest of a private sanitized mapping-fidelity record or an explicit zero-loss synthetic record. |
| `public_universe_digest` | Digest of the separately typed compiled public universe. |
| `evaluator_universe_digest` | Digest of separately typed compiler truth. |
| `compiler_build_digest` | Reproducible implementation-input digest, never a host or wall-clock identifier. |
| `provenance_chain` | Canonically ordered version and digest bindings for every transformation. |

The validator must reject missing, duplicate, unknown, or mismatched bindings;
unsupported versions; public/evaluator identity drift; non-canonical
collections; raw paths or labels; namespace salts; source population fields;
untyped extension objects; empty universes; inferred source vintages; and any
attempt to recompute population after compilation.

The build pipeline is:

```text
explicit synthetic authoring input
  -> enterprise compiler
  -> Face B compiled-universe envelope
  -> deterministic case planner
  -> separate public and evaluator projections
  -> visibility-bound manifests and digests
```

Face B starts at the envelope. Partial adapter output, unresolved exclusions,
or failed compilation cannot be silently converted into a successful Face B
run.

## Adapter evidence and future bridge

The repository-only fictional EADS-shaped adapter is requirements evidence,
not a Face B input implementation. Its current report schema is `2.0.0`, its
adapter version is `repository-eads-shaped-structure-v1`, its human population
policy is `eads-human-population-policy-v1`, and
`real_eads_compatibility` is always false. Those versions belong to the adapter,
not to the Face B family.

The adapter does not emit `FaceBCompiledUniverseInputV1`, a Face B topology
profile, or a Face B mapping-fidelity model. A future bridge must be separately
typed and must bind the exact adapter report, mapping, population policy,
compiler output, and resulting envelope. It must reject failed or partial
organisations unless a reviewed compiled profile explicitly models those
exclusions.

A private `FaceBMappingFidelitySummaryV1` may contain only closed adapter-gap
codes and counts. It contains no raw labels, source paths, salts, source
payloads, or source topology. Its digest provides transformation accountability
and generator-integrity evidence. It is never product authority and cannot be
the hidden fact that changes an expected authorization decision.

## Tenant, organisation, topology, and placement

Tenant is the security boundary for `SW-AA-C10`. Principal, logical agent,
runtime, credential, resource, and enforcement context resolve to exactly one
tenant. An opaque identifier valid in one tenant grants no authority in another,
even when its text collides.

Organisation is a separate authorization scope. A Face B universe may contain
multiple fictional organisations in one tenant so this distinction is
observable. Same-tenant cross-organisation action is denied by default and is
allowed only by an exact public authority record binding the target
organisation, resource, action, scope, purpose, and time. Cross-tenant action is
always denied.

Region, regulatory regime, and geopolitical placement are separately typed
dimensions. They may constrain public policy but never create a tenant,
organisation, unit, ownership relation, or grant by inference. Unknown placement
remains explicit unknown data.

The `face-b-synthetic-multi-org-v1` authoring profile contains opaque tenant
keys, canonically ordered organisation keys, typed placement references, the
selected tier, and no grants. Grants compile separately so topology cannot imply
authorization. The compiler provenance chain binds the profile and its digest;
Face B may select cases but may not add, merge, or move organisations after
compilation.

## Tier and case-family gate

The target `FaceBTierV1` vocabulary is `conformance`, `coverage`, and `scale`.
The following values are capacity targets retained from the earlier proposal;
they are not accepted runtime constants while the case-family register remains
unresolved.

| Tier | Tenants / organisations | Humans / NHIs / resources | Target case-action budget | Event ceiling |
| --- | --- | --- | --- | --- |
| `conformance` | 2 / 3 | 48 / 8 / 24 | 86 | 256 |
| `coverage` | 4 / 8 | 256 / 32 / 128 | 172 | 1,024 |
| `scale` | 16 / 64 | 4,096 / 256 / 1,024 | 1,720 | 10,000 |

No tier may be implemented until the applicable enterprise C15/C16 v1
contract-family design reaches its acceptance gate and every imported family
has representable public input, evaluator truth, submission, replay, and an
independent metric denominator. The authoritative C15/C16 family register must
be imported without collapsing issuer-source, issuer-ceiling, audience,
resource, policy, chain, revocation, intent, target, parameter, approval-use, or
side-effect distinctions.

The prior allocation of six C15 and four C16 families is withdrawn. Exact tier
budgets must be recalculated from the accepted register. Any changed target
counts require a new Face B design version before implementation. Face B does
not expose a reduced or implicit pre-C15/C16 tier.

C08 is not a Face B case family. Importing C08 cases would create a composite
benchmark and requires another family identity and transition.

## Deterministic case planning

The planner declares the complete case inventory before generating records. It
may not search generated output until a desired verdict appears. Cases are pure
functions of the compiled-universe digests, seed, tier, schema versions,
canonical case plan, and explicit event schedule.

Each accepted family requires discriminating negative attempts and positive
counterparts, at least two distinct subjects and resources where the invariant
permits, and an independent denominator. Metrics remain separate; aggregate
scores cannot hide a failed family.

Approved exceptions reuse the existing closed reason vocabulary. A reason is
metadata, not authority. Cases must cover active, expired, not-yet-valid,
wrong-subject, and wrong-access-atom records. Exception metrics remain separate
from ordinary authority and future C15/C16 metrics.

## Public solvability and evaluator separation

Every expected product decision must follow from public input alone. The public
model includes all authority, policy, lifecycle, placement, and correlation
facts needed to construct a valid submission. It may include typed opaque
handles and same-kind distractors. It never includes expected verdicts, case
labels, selected canonical bindings, planted mutation labels, failure reasons,
or metric denominators.

Evaluator truth contains those answer-key fields. Submission contains only
product-reported decisions and permitted observability fields. Public,
evaluator, and submission projections are constructed explicitly field by
field and serialized to physically separate roots. Dumping an oracle-bearing
model with an exclusion list is prohibited.

Private mapping-fidelity evidence may select or validate a generator-integrity
scenario, but the public compiled structure must independently expose every
fact needed for the product decision. A fidelity condition that is not public
can be tested only as generation integrity, not scored as product behavior.

The implementation gate requires a deterministic public-only reference builder
that receives no evaluator bytes and constructs a structurally valid reference
submission. Tests must prove evaluator files can be absent while the builder and
submission validator operate.

Boundary tests scan nested JSON, JSONL, manifests, package archives,
documentation output, and search indexes. The split is API hygiene and
accidental-leakage protection, not a secrecy claim when evaluator artifacts are
distributed.

## Artifact and visibility contract

Fixed benchmark artifacts are limited to separately typed public input,
evaluator truth, their visibility-specific manifests, and the root visibility
manifest. Generated schemas and package loaders are versioned contract assets,
not substitutes for benchmark inventory records.

Submission instances, evaluation reports, private adapter reports, bridge
reports, namespace salts, source paths, raw source data, source payload digests,
and source oracle records are run or private inputs and are excluded from the
frozen benchmark inventory. Submission and report schemas may be versioned, but
their per-run instances are never frozen benchmark bytes by implication.

Face B owns the bounded digest profile
`enterprise-agentic-face-b-path-bound-sha256-v1`. It is not a repository-wide
primitive. Each manifest row binds a canonical POSIX-relative path, artifact
role, visibility, byte size, and lowercase SHA-256 digest. Rows are sorted by
path, duplicate paths fail, and visibility must match both the containing
manifest and destination root.

The public and evaluator manifests exclude themselves from their row sets and
bind the exact bytes in their respective roots. The root visibility manifest
binds the paths, sizes, digests, identities, and versions of both manifests and
their artifact-set digests. It also binds `compiled_intake_digest`, the
lowercase SHA-256 digest of the canonical bytes of the complete validated
`FaceBCompiledUniverseInputV1` envelope. The intake digest uses the same
canonical JSON profile and is not a field of that envelope, avoiding a
self-referential digest. The root manifest excludes itself; the benchmark root
digest is the SHA-256 digest of its canonical bytes. Canonical JSON uses UTF-8,
LF line endings, sorted keys, compact separators, and one trailing newline.

Packaged loaders must validate path safety, visibility, size, digest, exact disk
inventory, cross-bindings, and fixed-reference generation before exposing
models. Public loaders must not read or require evaluator paths.

## Determinism and provenance

Generation is a pure function of the bound compiled universe, explicit seed,
projection configuration, tier, contract versions, case plan, and event
schedule. Wall-clock time, random UUIDs, locale, host state, filesystem order,
and source paths are forbidden inputs.

The root manifest binds at least the compiled-intake and compiler versions, the
canonical digest of the complete validated compiled-intake envelope, Face B
generator and projection versions, tier, seed, configuration digest, compiled
public and evaluator universe digests, case-plan and event-schedule digests,
public and evaluator artifact-set digests, and canonically ordered provenance
edges. Set-like collections use canonical ordering; event streams and
provenance chains use stable semantic ordering.

## Adapter-gap disposition

| Fictional adapter observation | Face B disposition |
| --- | --- |
| Region and placement do not imply a unit or grant. | Preserve placement as typed public policy input only when required; never infer authority. |
| Deep hierarchy may be collapsed. | Bind the public compiled hierarchy and private fidelity outcome separately; score only decisions solvable from public structure. |
| Classification may be null or present. | Preserve explicit public unknown/present state; never infer classification from labels. |
| Ownership semantics may diverge or be unsupported. | Keep ownership and grants separately typed; unsupported ownership never becomes authority. |
| Source population fields have adapter-specific meaning. | Bind the compiler population policy; Face B never recomputes source population. |
| Adapter outcomes may be partial or failed. | Require a reviewed bridge and reject unresolved outcomes before Face B intake. |
| The adapter is humans-only. | Keep NHI and agent populations blocked on accepted and implemented C15/C16 contracts. |
| The adapter has no real-EADS compatibility. | Preserve `real_eads_compatibility=false`; make no external compatibility claim. |

## Implementation, freeze, and publication gates

Design acceptance does not authorize code. Implementation requires dedicated
models, generated schemas, bounded generator and projection modules, packaged
loaders, public-only reference construction, replay, metrics, CLI selection,
and discriminating tests with 100% branch coverage. Existing frozen v1 and C08
bytes and checksums must remain byte-identical.

Freezing requires exact generated artifacts, checksums, path-bound manifests,
integrity and packaging tests, fixed-reference comparison, an explicit benchmark
transition, and a review record in `GOLDEN_REVIEW.md`.

Section 13 publication governance remains closed until all of these records are
reviewed together:

1. An authorized Face B transition in
   `docs/_data/benchmark-transitions.json`.
2. A matching curated registry candidate and regenerated repository catalogue.
3. An exact publication-gate identity for benchmark ID, version, target, paths,
   and digests.
4. Explicit `authorized_benchmarks` and path-and-digest-bound `operations` in
   `huggingface/publication-manifest.json`.
5. Public Viewer mappings limited to public artifacts, with any raw evaluator
   distribution separately labelled and explicitly authorized.
6. CI, package, leakage, integrity, secret-scan, and documentation evidence
   recorded against the final commit.

Uploads, network access, and external publication remain disabled until every
gate passes. No current transition, registry row, manifest entry, workflow, or
design statement authorizes Face B publication.

## Design acceptance criteria

The design can advance only when review confirms:

- the Face B v1 identity is distinct from every v1, C08, and C15/C16 family;
- the C15/C16 contract-family register is accepted and the Face B budget is
  recalculated without collapsing independent metrics;
- C08 exclusion and composition rules are explicit;
- every scored decision is constructible from public input without evaluator or
  private fidelity bytes;
- the adapter bridge and mapping-fidelity record are separately typed and
  version-bound;
- the root manifest binds the canonical digest of the complete validated
  compiled-intake envelope;
- the frozen inventory excludes run outputs and private source evidence;
- manifest self-exclusion, visibility, path, size, digest, and cross-binding
  rules are complete;
- v1 and C08 frozen artifacts remain byte-identical; and
- implementation, freeze, registry, and publication remain separately
  authorized transitions.

Until those criteria are met, the verdict is **NOT READY for implementation,
freeze, or publication**.
