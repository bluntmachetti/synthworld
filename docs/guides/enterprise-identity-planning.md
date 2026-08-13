---
title: Enterprise Identity Planning
description: Plan enterprise identity, access, lifecycle, and agent-authority changes with safely fictional deterministic worlds.
---

# Enterprise Identity Planning

SynthWorld can turn a bounded enterprise identity/access structure into a
deterministic fictional universe for architecture planning and evaluation. It does
not copy production identities, choose an authorization architecture, enforce a
policy, or replace an IAM, IGA, PDP, or EADS implementation.

This guide distinguishes three delivery states:

- **Available now** means the workflow resolves to a shipped command, contract, or
  reproducible reference fixture.
- **Partially available** means bounded components exist, but the complete journey
  still requires explicit authoring or composition outside SynthWorld.
- **Planned** means the required generator or contract has not shipped.

## The planning journey

```text
private enterprise structure
          |
          v
deterministic fictional identity/access universe
  organisations, tenants, units, principals, accounts
  groups, roles, permissions, resources, ownership scopes
          |
          v
bounded authorization models
  directory/RBAC, ABAC, ReBAC, contextual guards
          |
          v
planning scenarios and deterministic evaluation
          |
          +------ planned composition under #27 ------+
          |
          v
generated agents, runtimes, credentials, delegation and authority events
```

The responsibilities remain separate throughout:

| Responsibility | Owner |
|---|---|
| Systems, services, dependencies, deployment/network structure and business impact | Enterprise source or EADS |
| Safely fictional identities, relationships, authority evidence and evaluator truth | SynthWorld |
| Access and runtime decisions | Authorization system under test |
| Comparison with declared truth and independent metrics | SynthWorld evaluator |

SynthWorld models only the enterprise structure needed to generate and evaluate
identity and access. It is not a general enterprise simulator or an identity
topology product.

## 1. Compile a fictional Enterprise Identity universe

**Available now.** Start with the reference blueprint, edit its bounded enterprise
structure, validate it, and compile it with an explicit seed:

```bash
synthworld scaffold-enterprise-access \
  --format yaml \
  --output private-enterprise.yaml

synthworld validate-enterprise-access \
  --input private-enterprise.yaml

synthworld compile-enterprise-access \
  --input private-enterprise.yaml \
  --seed 20260804 \
  --output compiled-enterprise
```

Treat `private-enterprise.yaml` as operator-private. Structural keys, headcounts,
access breadth, and its namespace salt may remain commercially sensitive even
without person rows. Compilation is synthetic generation, not anonymization.

The result is physically split:

```text
compiled-enterprise/
  public/
    identity-access-universe.json
    manifest.json
  evaluator/
    canonical-binding-truth.json
    manifest.json
```

The public universe carries fictional entities and opaque identifiers. Canonical
account-to-principal bindings remain in the evaluator tree. Give only the public
tree to a system under test.

### Starting from an EADS-shaped source

**Partially available.** The repository includes a
[fictional EADS-shaped fixture adapter](../../enterprise-identity-access-contract/examples/eads_adapter/README.md)
for one declared, humans-only input shape. It demonstrates sanitized translation
into the bounded enterprise compiler.

It is not compatible with a real EADS product, API, schema, deployment, or
arbitrary export. A real source must first be sanitized and translated into the
supported fictional input contract. EADS continues to own operational topology;
SynthWorld consumes only the identity/access structure it needs.

## 2. Explore authorization architecture choices

**Partially available.** The compiled universe can be combined with independently
versioned directory/RBAC, ABAC, and ReBAC authoring contracts. SynthWorld can
evaluate their declared semantics and retain mechanism-specific outcomes, but it
does not recommend the organisation's best policy design.

The bounded models support questions such as:

- Which access is inherited through groups or role hierarchy?
- Where would a tenant or accountable-owner boundary make a broad role unsafe?
- Which decisions change when an ABAC guard is added to RBAC or ReBAC?
- Which facts or relationship paths are unknown, conflicting, or unsupported?

Every mechanism keeps its own result and denominator. There is no combined score
that can hide a weak authorization dimension. Standards-shaped SCIM, AuthZEN and
OpenFGA outputs are offline projections with explicit semantic-loss reports, not
live endpoint integrations.

For exact contracts and limitations, continue with
[Enterprise identity and access](enterprise-access.md).

## 3. Plan lifecycle, revocation and audit evidence

**Partially available.** Published conformance fixtures already distinguish action
time from later audit state, including policy versions, revocation, retained
evidence and reconstructability. They are frozen end-to-end slices, not a general
temporal-world generator.

Use these slices to ask:

- Was the action authorized when it occurred?
- Would the same action be authorized at audit time?
- Was the required credential, delegation and policy evidence retained?
- Can a correct verdict be justified from the evidence available at the relevant
  epoch?

The broader immutable snapshot, arbitrary-tick materialization, lifecycle-event,
and evidence-retention programme remains planned under
[#2](https://github.com/bluntmachetti/synthworld/issues/2).

## 4. Extend planning into Agentic Identity

### Separate reference world

**Available now.** Asteria Agentic v1 is a small published conformance world with
humans, logical agents, runtimes, credentials, resources, delegation, ordered
events, revocation and evaluator truth:

```bash
synthworld generate-agentic --output asteria-agentic-v1
synthworld validate agentic-trace --predictions observed-actions.jsonl
synthworld evaluate agentic --predictions observed-actions.jsonl --summary
```

It supports deterministic reasoning about runtime identity, credential subject,
delegated capability, action-time authority, later audit state, accountable owner
chains, provenance and reconstructability. It remains separate from an imported
enterprise universe. See [Agent authority](agent-authority.md).

Candidate C08 v2 artifacts may be present in the repository, but candidate status
is not publication approval and this guide does not present them as published
benchmarks.

### Generated enterprise-agentic composition

**Planned.** Automatic composition of a compiled enterprise structure into
configurable `smoke`, `standard`, and `longitudinal` agentic worlds remains under
[#27](https://github.com/bluntmachetti/synthworld/issues/27). That work must define
the generated profile, scale tiers, configuration identity, event schedule,
metrics and public/evaluator package contract before planning tools rely on it.

Face B compiled-universe work and C15/C16 authority-binding and principal-intent
contracts are also design dependencies. Do not infer those capabilities from the
current frozen reference worlds.

## Three concrete planning scenarios

### Scenario A: role breadth across tenant boundaries

**Available now.** Input a private blueprint with two isolated tenants, groups,
roles, permissions and fictional resource targets. Explore whether a broad role or
nested membership would cross a tenant boundary.

Expected outputs and evidence:

- A deterministic public universe with opaque fictional principals and accounts.
- A separately bound evaluator account mapping.
- Directory/RBAC derivations and final access decisions per declared cell.
- Independent policy-violation and derivation evidence rather than one aggregate
  score.

### Scenario B: add context to a role-oriented model

**Partially available.** Input the compiled universe, a directory/RBAC state, an
ABAC fact/rule overlay and a fixed request corpus. Compare pure RBAC with RBAC
guarded by tenant, ownership, assurance or network-zone facts.

Expected outputs and evidence:

- Raw RBAC and ABAC outcomes retained independently.
- Missing versus explicitly unknown facts kept distinct.
- Final deny gates for invalid binding or lifecycle state.
- A support matrix explaining exact, approximated and unsupported projection
  semantics when exporting to another authorization shape.

### Scenario C: credential revoked after an agent action

**Available now as a frozen conformance scenario.** Use Asteria's public world and
an observed-action trace to compare authority at action time with audit-time
credential and delegation state.

Expected outputs and evidence:

- Separate identity, authorization, temporal-validity and reconstructability
  metrics.
- Expected action-time authority and later audit state in evaluator truth only.
- No full credit for a correct verdict when required provenance cannot be
  reconstructed.

## Planning is not benchmark publication

Planning and benchmark evaluation reuse deterministic identity/access primitives,
but they are not equivalent.

| Planning workflow | Governed benchmark evaluation |
|---|---|
| Explore a fictional architecture or policy choice | Use an independently versioned benchmark identity |
| Change private structure and explicit configuration | Freeze or select reviewed public input and evaluator truth |
| Inspect mechanism-specific effects | Collect a versioned prediction or trace before scoring |
| Produce local evidence for design discussion | Apply publication gates before making comparative claims |

A planning experiment is not automatically a publishable benchmark result. A
frozen public reference fixture is not a secret test or vendor leaderboard, and an
offline score does not prove live enforcement.

## Capability map

| Journey | Status | Boundary |
|---|---|---|
| Private structure to fictional enterprise universe | **Available now** | Bounded identity/access compiler |
| Fictional EADS-shaped human adapter | **Partially available** | Repository-only declared fixture shape |
| RBAC, ABAC and ReBAC architecture experiments | **Partially available** | Explicit offline contracts and composition |
| Action-time versus audit-time authority slices | **Available now** | Frozen conformance worlds |
| General temporal-world generation | **Planned** | Issue #2 |
| Separate agent-authority reference evaluation | **Available now** | Asteria Agentic v1 |
| Imported topology to generated multi-tier agentic world | **Planned** | Issue #27 and later contracts |
| Interactive deterministic world exploration | **Planned** | [SynthWorld Explorer #52](https://github.com/bluntmachetti/synthworld/issues/52) |

Continue with the [benchmark catalogue](/benchmarks/catalogue) for governed
lifecycle status and [Evaluating a system](evaluating-a-system.md) for the
prediction/evaluator workflow.
