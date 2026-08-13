# SynthWorld roadmap

This file records direction rather than a release promise. The user-facing Now/Next/Later view lives at https://bluntmachetti.github.io/synthworld/roadmap/; governed registries remain authoritative for current capability and benchmark status.

## Product principles

Ground truth first; public observations stay separate from evaluator truth; synthetic-data safeguards remain mandatory; replay inputs and versions stay explicit; small frozen fixtures remain stable while larger workloads are generated separately.

## Architecture direction

SynthWorld remains a deterministic identity/evaluation layer rather than a general runtime. Domain systems consume public projections and return predictions or traces for independent scoring.

## Phase 1 — Benchmark adoption

The shared evaluation framework and core benchmark families are established. Current work is documentation clarity, publication discipline, and reproducible benchmark consumption.

## Phase 2 — World depth and longitudinal truth

Richer graph profiles and broader deterministic temporal composition remain active directions under #3 and #2 while existing frozen fixtures stay stable.

## Phase 3 — Priority market packs

Priority work builds on the shipped broker lifecycle and agent-authority surfaces while generated scale and deeper composition continue separately.

### Data-broker deletion and reappearance

Broker lifecycle evaluation is shipped; broader longitudinal product behavior remains separately scoped.

### AI agents and non-human identities

Frozen agent-authority conformance surfaces are shipped. Configurable generated agent/NHI worlds and scale tiers remain tracked under #27 and #6.

## Phase 4 — Portfolio and AI-system integrations

The enterprise identity/access foundation and contextual/continuous assurance contracts are established. Remaining work extends those bounded contracts without turning SynthWorld into a general enforcement product.

## Phase 5 — Exploratory identity ecosystems

Later exploration includes LLM/RAG privacy (#8), digital wallets and verifiable credentials (#9), and disaster identity continuity (#10).

## Use-case map

Use the [documentation site](https://bluntmachetti.github.io/synthworld/) for journey guidance and the generated [benchmark catalogue](https://bluntmachetti.github.io/synthworld/benchmarks/catalogue/) for governed current state.

## Explicit non-goals

SynthWorld does not anonymise supplied real-world data, impersonate real people, replace domain runtimes, or turn deterministic benchmark scores into forecasts.

## Contribution guidance

New benchmark packs should begin with an issue that defines public input, evaluator truth, versioning, deterministic inputs, metrics, negative controls, and the frozen-versus-generated artifact strategy. See [CONTRIBUTING.md](CONTRIBUTING.md).
