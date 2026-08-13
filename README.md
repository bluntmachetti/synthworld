# SynthWorld

[![CI](https://github.com/bluntmachetti/synthworld/actions/workflows/ci.yml/badge.svg)](https://github.com/bluntmachetti/synthworld/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/idcognito-synthworld?cacheSeconds=3600)](https://pypi.org/project/idcognito-synthworld/)
[![Python versions](https://img.shields.io/pypi/pyversions/idcognito-synthworld?cacheSeconds=3600)](https://pypi.org/project/idcognito-synthworld/)

**Deterministic synthetic identity worlds with adversarial evidence and ground-truth answer keys.**

SynthWorld creates safely fictional connected test worlds and keeps public observations separate from evaluator truth. It is not an anonymisation tool.

## Choose what you want to do

Start with the [documentation site](https://bluntmachetti.github.io/synthworld/) or the generated [benchmark catalogue](https://bluntmachetti.github.io/synthworld/benchmarks/catalogue/).

## Featured: agent authority

See the [agent authority guide](https://bluntmachetti.github.io/synthworld/guides/agent-authority/) and [Asteria Agentic v1](AGENTIC_BENCHMARK.md).

## Why SynthWorld

Repeatable inputs, connected fictional data, adversarial cases, separate evaluator truth, and versioned scoring make benchmark claims reproducible.

## Current benchmark families

See the [benchmark catalogue](https://bluntmachetti.github.io/synthworld/benchmarks/catalogue/) and [BENCHMARKS.md](BENCHMARKS.md).

## The core identity world is a smoke surface

See the [identity-world guide](https://bluntmachetti.github.io/synthworld/guides/identity-worlds/) for scope and limits.

## What the ambiguity pack does and does not measure

See the [identity-resolution guide](https://bluntmachetti.github.io/synthworld/guides/identity-resolution/) and [BENCHMARKS.md](BENCHMARKS.md).

## Public input and evaluator truth

Give systems only explicitly public inputs; keep evaluator artifacts on the scoring side.

## Enterprise identity and access

See the [enterprise access guide](https://bluntmachetti.github.io/synthworld/guides/enterprise-access/) and the normative enterprise contract.

## What the enterprise surface does not claim

The enterprise surface provides deterministic test artifacts and offline evaluation, not a deployed enforcement service.

## Install

```bash
pip install idcognito-synthworld
synthworld generate --seed 20260719 --persona-count 10 --output world.json
```

## Evaluate a system

See [Evaluating a system](https://bluntmachetti.github.io/synthworld/guides/evaluating-a-system/).

## Validate before you score

Use the task validator where one exists, then run the corresponding evaluator.

## Use Asteria Agentic v1

See [AGENTIC_BENCHMARK.md](AGENTIC_BENCHMARK.md) for the frozen fixture and replay contract.

## Verify every claim

Retain benchmark identity, versions, explicit inputs, checksums, and the submitted prediction or trace.

## Roadmap and integrations

See the [roadmap](https://bluntmachetti.github.io/synthworld/roadmap/) and [ROADMAP.md](ROADMAP.md).

## Develop from source

```bash
uv sync --locked --all-groups
make ci
```

## License

Apache-2.0. See [LICENSE](LICENSE).
