# SynthWorld roadmap

SynthWorld is a deterministic ground-truth identity layer for evaluating privacy,
identity, and agent systems. The project should remain narrower than a general
simulation engine: it generates identities, records, relationships, events, and
hidden truth; domain systems consume product-safe projections and return
predictions or actions for evaluation.

This roadmap records direction rather than a release promise. Schema contracts
remain independently versioned, and the existing frozen benchmarks must not
change without an explicit benchmark-version transition.

## Product principles

1. **Ground truth first.** Every generated ambiguity, relationship, lifecycle
   event, and policy violation must have independently checkable truth.
2. **No oracle leakage in public adapters.** Public-facing schemas must keep
   product-safe observations physically and structurally separate from
   evaluator-only truth.
3. **Safely fictional by construction.** Reserved domains, fictional phone
   ranges, obvious example addresses, invalid identifiers, and recursive
   `synthetic: true` markers remain non-negotiable.
4. **Deterministic replay.** A seed, configuration, schema version, and event
   schedule must reproduce the same benchmark.
5. **Packs, not a second simulator.** SynthWorld owns identity truth. Arena,
   EADS, ZeroID, Idcognito, and Aftershock retain their own runtime and domain
   responsibilities.
6. **Small frozen benchmarks plus generated scale tiers.** CI fixtures should be
   inspectable and byte-stable; larger workloads should be generated rather
   than permanently embedded in the package.

## Architecture direction

```text
synthworld-core
  entities
  observations
  relationships
  events
  public/oracle boundary
  deterministic generation

packs/
  privacy_exposure
  broker_deletion
  agent_nhi
  enterprise_iam
  llm_privacy
  wallet_vc
  disaster_identity

adapters/
  idcognito
  zeroid
  eads
  arena
  aftershock
  generic_jsonl

evaluators/
  extraction
  entity_resolution
  relationship_inference
  calibration
  delegation
  lifecycle
```

Adapters should depend on stable public schemas. Domain-specific behaviour and
world mutation must not leak back into the SynthWorld core.

## Phase 1 — Benchmark adoption

**Objective:** make the existing benchmark families easy to evaluate and easy to
understand before expanding their scope.

- [#1 — Build a unified evaluation SDK and `synthworld evaluate` CLI](https://github.com/bluntmachetti/synthworld/issues/1)
- [#11 — Publish baseline benchmark results and visual demonstrations](https://github.com/bluntmachetti/synthworld/issues/11)
- [#13 — Add a public-only exact-span extraction corpus](https://github.com/bluntmachetti/synthworld/issues/13)

Expected outcomes:

- versioned prediction and evaluation-report schemas;
- extraction, entity-resolution, relationship, and calibration metrics;
- separately serialized public extraction pages and exact-span truth;
- reproducible naive baselines that run in CI;
- a clear visual explanation of public input versus evaluator truth;
- benchmark cards that state size, limits, seed, schema versions, and checksums.

## Phase 2 — World depth and longitudinal truth

**Objective:** move from a small connected fixture toward configurable identity
worlds while preserving the current frozen corpus.

- [#2 — Add deterministic temporal identity worlds and event streams](https://github.com/bluntmachetti/synthworld/issues/2)
- [#3 — Add realistic graph profiles and scalable benchmark tiers](https://github.com/bluntmachetti/synthworld/issues/3)
- [#4 — Expand adversarial data quality, ambiguity, and confidence cases](https://github.com/bluntmachetti/synthworld/issues/4)

Expected outcomes:

- immutable initial snapshots plus replayable lifecycle events;
- households, organisations, teams, communities, and overlapping membership;
- named topology profiles rather than one mandatory relationship path;
- smoke, standard, stress, and longitudinal workload tiers;
- stale, missing, contradictory, transliterated, and miscalibrated records.

## Phase 3 — Priority market packs

**Objective:** demonstrate two differentiated use cases that build directly on
existing capabilities and the wider project portfolio.

### Data-broker deletion and reappearance

- [#5 — Add a data-broker deletion and reappearance benchmark pack](https://github.com/bluntmachetti/synthworld/issues/5)

This extends the existing broker lifecycle into multi-broker discovery,
verification, removal, downstream propagation, partial deletion, and
reappearance testing. Idcognito can consume the public side while SynthWorld
retains definitive lifecycle truth.

### AI agents and non-human identities

- [#6 — Add an AI-agent and non-human identity benchmark pack](https://github.com/bluntmachetti/synthworld/issues/6)

This introduces agents, workloads, service accounts, credentials, scopes,
delegation chains, expiry, and revocation. ZeroID can enforce runtime identity,
Arena can exercise agent behaviour, and EADS can supply enterprise resources and
business impact; SynthWorld remains the benchmark oracle.

## Phase 4 — Portfolio and AI-system integrations

**Objective:** project the ground-truth identity layer into enterprise and AI
systems without duplicating their simulation kernels.

- [#7 — Add an enterprise IAM and identity-governance benchmark pack](https://github.com/bluntmachetti/synthworld/issues/7)
- [#8 — Add an LLM, RAG, and agent-memory privacy benchmark pack](https://github.com/bluntmachetti/synthworld/issues/8)

Expected outcomes:

- joiner, mover, leaver, orphan-account, excessive-privilege, and toxic-access
  benchmarks;
- EADS projections for systems, entitlements, dependencies, and impact;
- Arena scenarios for organisational remediation decisions;
- mixed documents, messages, logs, retrieval chunks, and memory records with
  fact ownership and authorisation truth;
- evaluation of cross-user leakage, stale memory, incorrect entity merges, and
  deletion propagation.

## Phase 5 — Exploratory identity ecosystems

**Objective:** validate adjacent markets only after the common evaluator,
temporal model, and priority packs are stable.

- [#9 — Add a digital-wallet and verifiable-credentials benchmark pack](https://github.com/bluntmachetti/synthworld/issues/9)
- [#10 — Add a disaster identity-continuity benchmark and Aftershock adapter](https://github.com/bluntmachetti/synthworld/issues/10)

These packs explore issuer-holder-verifier ecosystems, selective disclosure,
credential lifecycle, family reunification, identity recovery, duplicate aid
records, and safe inter-agency matching.

## Use-case map

| Use case | SynthWorld responsibility | Consumer or adapter |
|---|---|---|
| Privacy exposure and broker removal | Synthetic identities, observations, lifecycle truth | Idcognito |
| Agent and workload identity | Principals, credentials, grants, delegation and revocation truth | ZeroID, Arena, EADS |
| Enterprise IAM and governance | Accounts, entitlements, ownership and policy truth | EADS, Arena |
| LLM and RAG privacy | Fact ownership, sensitivity, authorisation and current-state truth | Model, RAG or agent harness |
| Digital wallets and credentials | Issuers, holders, claims, presentations and validity truth | Wallet or verifier adapter |
| Disaster identity continuity | Households, records, matching and status truth | Aftershock |

## Explicit non-goals

- Generating plausible unmarked identifiers that could be mistaken for real
  people.
- Impersonation, targeting, investigation, or enrichment of real people.
- Claiming that procedural synthetic fixtures anonymise a supplied real-world
  dataset.
- Replacing Arena, EADS, ZeroID, Idcognito, or Aftershock with a general-purpose
  SynthWorld runtime.
- Treating a deterministic descriptive risk index as a probability or forecast.

## Contribution guidance

New packs should begin with an issue that defines:

- public input and evaluator truth;
- schema and formula versioning;
- safety invariants;
- deterministic generation parameters;
- evaluation metrics and negative controls;
- the adapter boundary with any external project;
- a frozen small benchmark and a generated scale path.
