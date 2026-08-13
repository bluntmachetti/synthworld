# SynthWorld roadmap

SynthWorld is a deterministic ground-truth layer for evaluating identity, privacy, access, and agent systems. This file records direction rather than a release promise. The user-facing Now/Next/Later view lives at https://bluntmachetti.github.io/synthworld/roadmap/ and governed registries remain authoritative for current capability and benchmark status.

## Principles

1. Ground truth first.
2. Keep public observations separate from evaluator truth.
3. Preserve synthetic-data safeguards.
4. Make replay inputs and versions explicit.
5. Keep domain runtimes outside the SynthWorld core.
6. Keep small frozen fixtures stable and generate larger workloads separately.

## Current foundation

The project includes deterministic world generation, multiple independent evaluator families, governed capability and benchmark registries, versioned contract families, a deployed documentation site, and guarded publication workflows. Newer candidate artifacts remain candidates until their explicit publication gates are satisfied.

## Now

- Complete user-journey documentation and enterprise planning guidance (#124).
- Preserve frozen benchmark bytes while tightening publication and provenance controls.
- Keep candidate-versus-published status explicit.

## Next

- Configurable generated `enterprise_agentic` profiles and scale tiers (#27, #6).
- Deeper graph profiles and scalable workload tiers (#3).
- Broader deterministic temporal composition for lifecycle and historical evaluation (#2).

## Later

- LLM, RAG, and agent-memory privacy evaluation (#8).
- Digital-wallet and verifiable-credential ecosystems (#9).
- Disaster identity-continuity scenarios (#10).

These are exploration directions, not statements that the capability already exists.

## Phase 1 — Benchmark adoption

The shared evaluation framework and core benchmark families are established. Current maturity and publication state come from the generated registries rather than from this roadmap heading.

## Phase 2 — World depth and longitudinal truth

Richer graph profiles and broader deterministic temporal composition remain active directions under #3 and #2 while existing frozen fixtures stay stable.

## Phase 3 — Priority market packs

Priority market work includes the shipped broker lifecycle evaluator and frozen agent-authority conformance surfaces, with generated scale and deeper composition continuing separately.

### Data-broker deletion and reappearance

Broker lifecycle evaluation is shipped; broader longitudinal product behavior remains separately scoped. See the privacy/exposure documentation and governed benchmark catalogue for current status.

### AI agents and non-human identities

Asteria and enterprise agent-authority conformance surfaces are shipped. Configurable generated agent/NHI worlds and scale tiers remain tracked under #27 and #6.

## Phase 4 — Portfolio and AI-system integrations

The enterprise identity/access foundation and contextual/continuous assurance contracts are established. Remaining integration work should extend those bounded contracts without turning SynthWorld into a general runtime or enforcement product.

## Contribution guidance

New benchmark packs should begin with an issue that defines public input, evaluator truth, versioning, deterministic inputs, metrics, negative controls, and the intended frozen-versus-generated artifact strategy.

See [CONTRIBUTING.md](CONTRIBUTING.md), the [documentation site](https://bluntmachetti.github.io/synthworld/), and the generated [benchmark catalogue](https://bluntmachetti.github.io/synthworld/benchmarks/catalogue/).
