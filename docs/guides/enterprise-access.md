# Enterprise identity and access

The enterprise surface compiles an operator-authored structural import into a deterministic, safely fictional identity/access universe with physically separate public product input and evaluator truth. It also provides bounded reference benchmark packs and standards-shaped projections.

SynthWorld is not a directory service, IGA workflow system, policy decision point, or runtime enforcement component.

**Author, validate, compile.**

```bash
synthworld scaffold-enterprise-access --format yaml --output private-enterprise.yaml
synthworld validate-enterprise-access --input private-enterprise.yaml
synthworld compile-enterprise-access \
  --input private-enterprise.yaml \
  --seed 20260804 \
  --output compiled-enterprise
```

Treat the authored blueprint as operator-private. Importing enterprise structure is not anonymization, and structural keys or namespace material can remain sensitive even when no production person records are present.

Validation reports stage-local diagnostics rather than silently accepting partial structure. Compilation then writes separate `public/` and `evaluator/` trees. Canonical account-to-principal binding truth belongs only in the evaluator tree; public account records do not expose that linkage.

**Determinism and seed semantics.** Compilation is reproducible from the saved import plus the explicit seed and versioned compiler/schema inputs. Structural identifiers such as tenants, organisations, units, principals, groups, roles, targets, and permissions are derived from the authored namespace and logical structure. Account allocation is seed-driven, so account-related subjects and access atoms can move between seeds while principal-level structure remains stable.

Do not generalize one generator's seed behavior to another SynthWorld surface. Record the complete configuration and version inputs with any result.

**What the compiled universe represents.** The public universe contains bounded entity inventories and access atoms. It is a test input, not a live directory topology or policy engine. The normative enterprise contract defines supported authoring formats, selector rules, cross-tenant constraints, output layout, and other limits:

[Enterprise identity/access contract](../../enterprise-identity-access-contract/README.md)

Persistent access declarations and observed account bindings are intentionally
tenant-local. A cross-tenant reference in either surface is malformed input, not a
scoreable denied case. To test a cross-tenant authorization guard, keep the compiled
access atom structurally valid and express the evaluated subject/resource tenant
divergence in the cell's public ABAC facts and policy. The bounded enterprise contract
does not model a persistent federated cross-tenant grant; a consumer must not bypass
validation to manufacture one.

**Authorization and benchmark surfaces.** The repository contains directory/RBAC, ABAC, ReBAC, identity-fabric, enterprise-agentic, contextual-access, authority-governance, and continuous-assurance surfaces with different APIs and maturity levels. Do not infer that every family has the same CLI or accepts an arbitrary compiled universe.

Some tasks expose command-line generation/evaluation; others are Python-only. Use the [CLI reference](../reference/cli.md), the relevant contract README, and the generated [capability catalogue](/benchmarks/catalogue) for the current boundary.

For the released-package Python workflow from this compiled universe through a
public-only authorization adapter and independent scorer, use
[Build and score an enterprise authorization experiment](https://bluntmachetti.github.io/synthworld/guides/enterprise-authorization-python/).

Reference packs are conformance fixtures. Their evaluator truth may be published in the repository, so physical separation prevents accidental oracle use but does not turn a public reference pack into a blind test. A perfect reference score is evidence of conformance to the declared cases, not generalization.

**Standards-shaped projections.** SCIM, OpenFGA, AuthZEN, and Shared Signals/CAEP mappings are documented in [Standards profiles](../reference/standards-profiles.md). These are bounded offline mapping surfaces; a mapping declaration is not proof of protocol transport, signing, interoperability, or deployed enforcement.

**Evaluation boundary.** Give a system under test only the public artifact required by that task. Normalize its output into the versioned prediction or trace contract, then score against separately loaded evaluator truth.

See [Evaluating a system](https://bluntmachetti.github.io/synthworld/guides/evaluating-a-system/), [DATA_DICTIONARY.md](../../DATA_DICTIONARY.md), and the normative enterprise contract for exact schemas and metric semantics.

For the end-to-end topology, planning, lifecycle, and future agentic-composition
journey, see [Enterprise Identity Planning](https://bluntmachetti.github.io/synthworld/guides/enterprise-identity-planning/).
