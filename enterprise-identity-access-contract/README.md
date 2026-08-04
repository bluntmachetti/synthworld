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
PR3 gives its memberships, group nesting, role hierarchy, assignments, grants,
account observations, and direct entitlements native evaluation semantics. PR2
does not pre-empt those semantics or introduce ABAC/ReBAC placeholders.

Generate or verify the schemas and examples with:

```bash
uv run python enterprise-identity-access-contract/tools/generate_contract.py
uv run python enterprise-identity-access-contract/tools/generate_contract.py --check
```

The enterprise work is independent of ambiguity issue #80. It does not modify
ambiguity schemas, fixtures, checksums, or `GOLDEN_REVIEW.md`.
