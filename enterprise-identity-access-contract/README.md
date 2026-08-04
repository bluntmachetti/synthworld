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

This is an offline reference oracle, not a PDP, policy administration service,
mutable directory, or runtime enforcement component. ABAC and ReBAC remain
independently versioned PR4 families; there are no placeholder variants in the
frozen PR3 unions.

Generate or verify the schemas and examples with:

```bash
uv run python enterprise-identity-access-contract/tools/generate_contract.py
uv run python enterprise-identity-access-contract/tools/generate_contract.py --check
```

The enterprise work is independent of ambiguity issue #80. It does not modify
ambiguity schemas, fixtures, checksums, or `GOLDEN_REVIEW.md`.
