# Enterprise identity/access contract v1

This package describes and compiles a bounded enterprise **identity/access
structure**. It is not a topology model, IAM product, policy engine, production
directory, or general simulator. SynthWorld owns fictional tenants and
organisational scopes only where they determine identity population, ownership,
access eligibility, account binding, or tenant isolation. EADS owns systems,
services, dependencies, deployment/network topology, and business impact.

Importing an organisation's structure is **not anonymisation**. Logical keys,
counts, group structure, role structure, and access breadth can remain commercially
sensitive even when no person rows are present. Keep source documents and the
256-bit namespace salt private. Public/evaluator artifacts contain safely fictional
labels and opaque UUID5 identifiers, and contain neither the salt nor source-key
mapping.

Supported authoring formats are one YAML or JSON import envelope and the exact
20-file CSV bundle in `examples/csv/`. YAML uses a restricted JSON-compatible
subset: aliases, merges, custom tags, timestamps, duplicate keys, and non-JSON
scalars are rejected. CSV and ZIP readers use fixed allowlists and explicit limits;
they do not infer a dialect, extract archives, follow links, or silently repair
rows.

The generated public universe freezes principals, unbound account slots, groups,
roles, permissions, opaque authorization targets, relationship anchors, and sparse
candidate access atoms before any authorization mechanism is evaluated. Canonical
principal/account bindings are emitted separately under the evaluator tree.
Observed state may later disagree with those bindings without rewriting either
artifact.

## Pinned standards profile

`standards-profile-ledger.json` records the exact external editions reviewed on
2026-08-04 and the versioned SynthWorld profile selected from each. Benchmark
identity binds those selected profile identifiers and mapping digests; it never
means "whatever is latest". The ledger distinguishes final and reaffirmed
standards from research, implementation models, and draft community work.

SCIM RFC 7643/7644 supplies lifecycle and interchange vocabulary, INCITS
359-2012 (R2022) supplies the bounded RBAC vocabulary, and NIST SP 800-162
supplies ABAC categories. AuthZEN, Shared Signals/CAEP, and OpenFGA are projection
targets, not sources that can rewrite the native oracle. Zanzibar is research
prior art. The dated AIIM MCP interop snapshot is experimental scenario
vocabulary only. Unversioned COAZ-MCP/AARP work and SCIM role, entitlement, or
agent proposals are deliberately excluded until an exact source can be pinned;
they are not frozen core dependencies.

Start with YAML for the complete authoring experience, or choose JSON/the exact
CSV bundle when that better matches an existing directory export:

```bash
synthworld scaffold-enterprise-access --format yaml --output private-enterprise.yaml
synthworld validate-enterprise-access --input private-enterprise.yaml
synthworld compile-enterprise-access \
  --input private-enterprise.yaml \
  --seed 20260804 \
  --output compiled-enterprise
```

The first command creates and persists a private random namespace salt when one is
not supplied. Validation and compilation are deterministic from the saved import,
explicit seed, schema versions, and compiler version. Compilation writes only the
fixed universe beneath `public/` and canonical account-binding truth beneath
`evaluator/`; the public loader never traverses the evaluator tree.

## EADS adapter Phase 1 boundary

The documented [EADS adapter example](../examples/eads_adapter/README.md) is a
humans-only conversion into this existing enterprise v1 authoring contract. It
maps each EADS organisation independently to one tenant and one organisation.
Tenant is the security isolation boundary; regions and regulatory or
geopolitical groupings remain sanitized gap metadata rather than tenants or
invented unit kinds.

Source parsing requires an explicit `sdk-size-v1` or
`topology-headcount-v1` strict reference profile. The profiles were inferred
from planning inputs and synthetic fixtures, not validated against the 31 real
exports; a representative sanitized export or exact schema is required before
claiming that compatibility. The corresponding `size` or `headcount` field is
validated but never controls generated population. Counts come from a
versioned, published deterministic mix policy over source-export `scale`,
`team_type`, and `industry` fields, not independent SynthWorld inputs.
Phase 1 defers BIAN and all agent, workload, service, and other non-human
identities.

`eads-human-population-policy-v1` uses scale bases `micro=4`, `small=8`,
`medium=16`, `large=32`, and `enterprise=64`; team factors `product=3/2`,
`operations=5/4`, `control=1`, and `platform=3/2`; and aliases
`controls -> control`, `ops -> operations`, `product-team -> product`, and
`platform-team -> platform`. Industry factors are `banking=5/4`,
`financial-services=5/4`, `healthcare=5/4`, `logistics=1`,
`public-services=1`, `research=1`, and `technology=3/2`. Unknown team or
industry values use factor `1` and emit a gap. Raw count is
`max(1, nearest(scale_base * team_factor * industry_factor))`; exact halves
round up by `(numerator + denominator // 2) // denominator`. Source `size` and
`headcount` are ignored.

When `--max-principals-per-organisation` is exceeded,
`largest-remainder-proportional-v1` floors one person per team, distributes the
remaining cap proportionally to `raw_count - 1`, then assigns residues by
largest fractional remainder and canonical team key. A cap below team count
fails. The cap defaults to `10000` and cannot exceed `1000000`.

The reader reads at most 50 MiB plus one detection byte from a no-follow
regular-file descriptor. Its JSON-compatible restricted parser requires finite
scalars and string keys, enforces fixed depth and node limits, rejects YAML
duplicate keys, aliases, merges, custom tags, and non-JSON scalars, and
sanitizes recursion and memory failures. Source classification is
not mapped into enterprise v1; null and present values are recorded as distinct
unexpressed gaps. Supported `owner` and `approver` relationships widen to the
whole mapped employee team through `AllSelector` and record that fidelity loss,
including any divergence from `owning_team_id`; unsupported ownership is
skipped.

The command interface is:

```bash
uv run python -m examples.eads_adapter \
  --source PATH \
  --vintage sdk-size-v1 \
  --output OUTPUT_DIR \
  --seed 42 \
  --namespace-salt-file PRIVATE_SALT_FILE \
  --max-principals-per-organisation 10000
```

The salt file contains a private 256-bit salt encoded as 64 lowercase
hexadecimal characters. It is an explicit deterministic input and must never be
published. Opaque references are keyed HMAC derivations under that salt. The
output root may be absent or existing and empty; non-empty roots and
non-directories are rejected. The run is staged and atomically promoted.
Private imports are written under `private/imports/<opaque-ref>/`, the machine
report under `private/reports/`, and manifested reference artifacts under
physically separate `artifacts/<opaque-ref>/public/` and `evaluator/` trees.
Private imports and reports must not be published. Partial multi-organisation
failure exits nonzero while retaining correctly manifest-bound artifacts for
successful organisations beside the failure report. All-excluded emits no
artifacts and exits nonzero; every other zero-success run also exits nonzero.

The machine report's canonical source payload digest covers normalized
JSON-compatible content, not exact source bytes or a source path. Raw EADS
exports remain private and are not bundled, tested, or validated by this
documentation. Source
organisation, vendor, and product labels must be replaced by safely fictional
labels or opaque stable identifiers before compiled or public output. Asteria v1
remains frozen and is not changed by this adapter. The
[sanitized aggregate gap record](EADS_ADAPTER_GAPS.md) captures hierarchy,
classification, ownership, region/regulatory, ignored source-scale, and future
issue #27 generated-world requirements; it is requirements evidence, not a
frozen benchmark.

`directory_rbac_state` in this version is a structurally validated input contract.
The independently versioned PR3 corpus declares exact context, subject-bound
session, activation-request, access-request, and access-cell slots. Its compiler
does not form an implicit Cartesian product. Directory/RBAC compilation resolves
memberships, group nesting, role assignments, role hierarchy, permissions,
account observations, and direct entitlements against that frozen inventory. All
tick fields use the existing integer logical-clock semantics from
`synthworld.temporal`; PR3 introduces neither UTC semantics nor a second clock.

`EnterpriseDirectoryRbacIntentOverlayV1` separately records named birthright
eligibility and assignment rules, approved exceptions, intended relations, SSD,
and true session-role DSD constraints. The evaluator retains birthright (`B`),
intended (`I`), effective (`E`), and lifecycle/binding-gated final (`F`) decisions
independently for every cell. It also retains every bounded group/role derivation,
activation reasons, and SoD result. Adding a rule, path, or metric cannot create a
principal, account, atom, context, session, request, or cell; coverage that does
not fit the declared budgets fails. Before evaluation, the compiler exactly
pre-counts actual and intended relations plus projected birthright predicate,
eligibility, assignment, and exception rows against
`max_directory_rbac_relations`; intended group and role DAGs must also fit their
independent depth limits before path enumeration. Assignment and exception lookup
is indexed by the already frozen atom IDs, so adding an unrelated rule does not
cause an implicit cell-product scan. Derivation, SoD, serialized-record, and
canonical-byte limits remain independently enforced.

## Bounded authorization families

PR4 adds ABAC and ReBAC as independently versioned state/intent overlays over
the already frozen universe and evaluation corpus. The standalone JSON examples
`enterprise-abac-state.json`, `enterprise-abac-intent.json`,
`enterprise-rebac-state.json`, and `enterprise-rebac-intent.json` are the
authoring starting points. They do not extend the v1 structural import envelope
or any PR3 union. Each overlay binds the exact universe and corpus digests and
may populate only existing cells; it cannot create a principal, account, target,
atom, context, request, session, or evaluation cell.

The ABAC vocabulary is a closed NIST-category profile. It provides typed
subject, resource, action, and environment facts and eleven named predicates:
subject kind, employment type, same tenant, subject unit, subject-unit ownership,
target kind, classification within clearance, action, action class, minimum
assurance, and network zone. Rules are flat `all`/`any` combinations with an
explicit allow or deny effect. Missing facts and explicitly unknown facts remain
distinct evidence while both produce the native `unknown` predicate outcome.
There is no arbitrary attribute key, user-selected operator, nested expression,
negation, function, or executable policy text.

Native ReBAC is similarly closed. The only relation matrices are `member_of`,
`owns`, `manages`, and `collaborates_on`; the only path templates are
`DirectSubjectRelation`, `GroupCollaboration`, and `ManagerOfOwner`, with maximum
path lengths one, two, and two. Tuples and rules carry explicit snapshot,
revision, tenant, and half-open tick validity. A two-hop path must use one
snapshot. Native input has no userset subjects, rewrite rules, recursion, union,
intersection, exclusion, wildcard, condition, delegation, or request-contextual
tuple. Human-to-agent delegation remains a later agentic-profile concern.

ABAC fact/rule/predicate limits and ReBAC tuple/rule/path-expansion limits are
independent of the frozen atom and cell budgets. Both compilers preflight their
work and serialized-record ceilings before expansion. Inactive revisions,
unknown evidence, conflicts, and every valid explain path are retained
deterministically; coverage that exceeds a bound fails rather than resizing the
world. ABAC decision/predicate metrics and ReBAC decision/path metrics report
their own numerators, denominators, and empty behavior—there is no combined
authorization score.

## Fixed composition and artifact boundary

`EnterpriseAuthorizationCompositionV1` contains only exact schema-version and
canonical-digest references to directory/RBAC and optional ABAC/ReBAC component
truth. `EnterpriseAuthorizationKernelV1` binds one of five closed profiles to
each existing cell: RBAC, ABAC, ReBAC, RBAC with an ABAC guard, or ReBAC with an
ABAC guard. The compiler requires every referenced payload explicitly, performs
no ambient lookup, preserves each mechanism's raw
`allow`/`deny`/`not_applicable`/`unknown` outcome, applies deny-overrides or the
selected guard algebra, and then applies account binding and lifecycle as
unconditional final-deny gates. Intended, effective, and final decisions and
pre-combination conflicts remain separate evaluator records.

Authorization export is physically split. The public tree contains ABAC/ReBAC
state and intent, composition, and the cell/profile kernel. The evaluator tree
contains ABAC/ReBAC component truth and compiled aggregate access state. Both
trees have exact canonical inventories and digest-bound manifests; loaders reject
extra, missing, non-regular, noncanonical, stale, or cross-bound artifacts.

## Identity-fabric smoke benchmark

The independently versioned `identity_fabric` package is the first bounded
directory/access-state slice of issue #7. It consumes the fixed enterprise
universe, corpus, native policy inputs, and compiled component states; it does not
introduce an identity-topology layer or add a principal, account, group, role,
target, atom, request, or cell. EADS continues to own operational systems,
services, dependencies, deployment/network topology, and business impact.

The public input contains only directory/account/access observations, declared
intent and policy inputs, two ordered immutable checkpoint states, and a
vendor-neutral query inventory. Evaluator artifacts separately contain canonical
account bindings, direct and effective membership, direct/group/hierarchy role
resolution, direct and inherited entitlement truth, birthright and approved
exception classification, intended/effective/final access, SSD and session DSD,
ABAC/ReBAC component truth, redundant derivations, access outside birthright,
access outside intent, privilege accumulation, and case labels. An approved
exception is deliberately non-birthright without being classified as sprawl.
Checkpoint `sequence` is only canonical ordering between declared immutable
snapshots; it is not time or a second clock. Every validity and lifecycle
decision continues to use the existing integer `tick` axis.

Metrics remain independent and state their exact denominators. Directory/RBAC,
ABAC, and ReBAC component reports are retained alongside separate membership,
role-resolution, account-binding/lifecycle, entitlement, birthright, exception,
conflict, redundancy, sprawl, and cross-checkpoint accumulation metrics. There is
no combined identity-fabric or authorization score. Missing predictions score as
incorrect; unknown checkpoint, query, cell, or benchmark bindings fail.

Five intentionally weak baselines make the important distinctions observable:
direct-only membership, role resolution without hierarchy or nested groups,
trusting recorded account ownership, applying only the latest checkpoint, and
classifying every non-birthright grant as sprawl. The generated reference pack
contains a dedicated failure for each shortcut while preserving the pinned PR2
universe and PR3 corpus bytes.

Export writes exactly one canonical public input plus its manifest under
`public/`, and exactly one evaluator bundle plus its manifest under `evaluator/`.
The public-only loader never traverses the evaluator directory; the evaluator
loader recompiles all truth and verifies the cross-visibility bindings.

This slice evaluates account observations at the corpus's existing integer ticks,
but does not claim to deliver the broader lifecycle/governance portion of #7.
Joiner/mover/leaver event programmes, access reviews, ownership remediation,
workflow evidence, and authority-change legitimacy remain later separately typed
work. The pack is also not a directory service, IGA workflow system, PDP, policy
engine, SGNL client, runtime enforcement service, or continuous-assurance agent.

## Enterprise-agentic smoke benchmark

The independently versioned `synthworld.agentic.enterprise` package is the
issue-#27 smoke projection over the same fixed universe, corpus, component truth,
and compiled access state used by the identity-fabric pack. It does not resize
that universe or corpus. Agent runtime accounts, runtimes, opaque synthetic
credential handles, capabilities, human-to-agent delegations, action events,
case prevalence, and retained audit evidence belong only to this overlay. The
handles are identifiers for safely fictional records, never reusable credential
material.

Every case retains the immutable enterprise final decision `F` and separately
emits `AgenticExpectedDecisionV1`. The downstream decision allows only when `F`
allows and every applicable subject, tenant, agent-account, runtime, credential,
capability, and delegation gate is satisfied. Gate outcomes and ordered failure
reasons remain separate, so a product cannot hide an enterprise denial behind a
runtime failure or vice versa.

Two explicit mappings are covered:

- `agent_as_principal` binds the frozen access atom to the agent principal. A
  human owner or provenance delegation is attributable context and grants no
  enterprise authority implicitly.
- `human_subject_agent_context` binds the atom to the human and carries exact
  agent principal, agent runtime-account, runtime, credential, capability, and
  delegation references. Agent authority is not unioned into the human's `F`.

The 20-case reference pack distinguishes valid and enterprise-denied actions,
human ownership that must not override an agent denial, same-human/different-agent
and same-agent/different-human contexts, missing and revoked delegation,
suspended agent account, revoked or shared credential, wrong subject, wrong
runtime, wrong scope, cross-tenant context, and evidence discarded before audit.
All event time uses the repository's integer `tick` axis and canonical
`(tick, event id)` order; no UTC field or alternate clock exists. The pinned
OpenID AIIM snapshot supplies experimental scenario tags only. It defines
neither a normative protocol nor a core agent identity model, and draft
COAZ-MCP/AARP profiles remain out of scope.

Public artifacts contain the exact enterprise policy inputs, overlay state,
events, mapping context, and opaque case inventory. Evaluator artifacts separately
contain component truth, compiled access state, expected gates/decisions,
attribution, evidence truth, and AIIM-informed labels. The evaluator loader
recompiles enterprise `F` and every downstream gate. Metrics independently report
enterprise-decision, final-decision, failure-reason, per-gate, per-mapping,
attribution, evidence, and audit-reconstructability accuracy with explicit
denominators; there is no agentic aggregate score.

Four shortcut baselines—enterprise-decision-only, owner-authority union,
lifecycle/revocation blindness, and discarded evidence—fail their dedicated
dimensions. The smoke pack exports, reloads, validates JSONL traces, and scores
end to end. Generate a deterministic reference run with:

```bash
synthworld generate-enterprise-agentic \
  --tier smoke \
  --seed 20260804 \
  --output enterprise-agentic-world
```

The command is a reference-smoke entry point. The pure Python projection accepts
an explicitly compiled access input and evaluator artifacts; it performs no
network call, credential exchange, model execution, PDP decision, runtime
enforcement, containment, or external vendor configuration. Frozen
`generate-agentic` remains dedicated to Asteria v1.

## Pure standards projections

The projection package performs deterministic data conversion only:

- SCIM maps account slots to Users and groups to Groups at an explicit snapshot
  tick. It preserves direct versus indirect membership and declares provider
  capabilities, but emits empty roles/entitlements and assigns no authorization
  meaning to `active` or membership.
- AuthZEN maps a frozen request to Subject, Action, Resource, and Context with
  field-level provenance. Runtime responses are separate observations that
  retain allow, deny, indeterminate, transport error, timeout, or unavailable
  before optional normalization.
- OpenFGA maps the bounded compiled ReBAC subset. Group usersets appear only at
  this projection boundary; snapshot and validity limitations are explicit and
  an OpenFGA runtime remains an external system under test.
- Shared Signals/CAEP v1 remains the historical PR4 mapping/support declaration
  pinned to the then-reviewed temporal 1.1 contract and emits no events. PR7 does
  not mutate that independently versioned schema. The additive contextual
  projection is published under `contextual-access-contract/`; it selects the
  shipped `synthworld.temporal` 1.2 tick contract, uses custom contextual event
  identifiers rather than mislabeling domain changes as standardized CAEP event
  types, and introduces neither UTC nor a second logical clock.

Every target emits a complete support matrix with one `exact`, `approximated`,
or `unsupported` row per exercised native feature, a mandatory semantic delta
for every non-exact row, a canonical mapping digest, and conformance-vector IDs.
Projection fidelity reports those three rates independently. The package has no
SCIM network operations, AuthZEN HTTP client, Shared Signals transmitter,
OpenFGA writer/evaluator, vendor connector, credential handling, or production
enforcement behavior.

This is an offline reference oracle, not a PDP, policy administration service,
mutable directory, identity fabric, or runtime enforcement component.

Generate or verify the schemas and examples with:

```bash
uv run python enterprise-identity-access-contract/tools/generate_contract.py
uv run python enterprise-identity-access-contract/tools/generate_contract.py --check
```

The enterprise work is independent of ambiguity issue #80. It does not modify
ambiguity schemas, fixtures, checksums, or `GOLDEN_REVIEW.md`.
