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
- Shared Signals/CAEP has a versioned mapping/support profile only. It emits no
  events in PR4. PR7 must build its schedule view on the shipped
  `synthworld.temporal` v1.1 integer-tick contract; it may not introduce UTC or a
  second logical clock.

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
