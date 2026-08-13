# SynthWorld

[![CI](https://github.com/bluntmachetti/synthworld/actions/workflows/ci.yml/badge.svg)](https://github.com/bluntmachetti/synthworld/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/idcognito-synthworld?cacheSeconds=3600)](https://pypi.org/project/idcognito-synthworld/)
[![Python versions](https://img.shields.io/pypi/pyversions/idcognito-synthworld?cacheSeconds=3600)](https://pypi.org/project/idcognito-synthworld/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](https://github.com/bluntmachetti/synthworld/blob/main/LICENSE)
[![Coverage: 100% enforced](https://img.shields.io/badge/coverage-100%25_enforced-brightgreen)](https://github.com/bluntmachetti/synthworld/blob/main/Makefile)

**Deterministic synthetic identity worlds with adversarial evidence and ground-truth answer keys.**

SynthWorld creates safely fictional, connected test worlds for evaluating privacy,
identity resolution, relationship inference, access decisions, agent authority, and
evidence quality. Public observations and evaluator truth are kept as separate
artifacts so a system can be tested without feeding it its own answers.

> **SynthWorld is not an anonymisation tool.** It does not transform sensitive real
> data into a safe dataset, and it is not an IAM product, policy engine, or runtime
> enforcement service.

## How it fits together

```text
seed + explicit configuration
          |
          v
 deterministic world
      /          \
     v            v
public input   evaluator truth
     |            |
     v            |
system under test |
     |            |
     +-> prediction/trace
                  |
                  v
          independent scoring
```

## Choose your goal

| Goal | Start here |
|---|---|
| Install and create a first world | [Getting Started](https://bluntmachetti.github.io/synthworld/getting-started/) |
| Build connected test worlds | [Identity worlds](https://bluntmachetti.github.io/synthworld/guides/identity-worlds/) |
| Evaluate identity resolution | [Identity resolution](https://bluntmachetti.github.io/synthworld/guides/identity-resolution/) |
| Evaluate privacy and exposure behavior | [Privacy and exposure](https://bluntmachetti.github.io/synthworld/guides/privacy-exposure/) |
| Test agent delegation and audit evidence | [Agent authority](https://bluntmachetti.github.io/synthworld/guides/agent-authority/) |
| Compile enterprise identity/access truth | [Enterprise access](https://bluntmachetti.github.io/synthworld/guides/enterprise-access/) |
| Connect a product or model to a scorer | [Evaluating a system](https://bluntmachetti.github.io/synthworld/guides/evaluating-a-system/) |
| Inspect benchmark status and publication state | [Benchmark catalogue](https://bluntmachetti.github.io/synthworld/benchmarks/catalogue/) |

## Install and generate

SynthWorld requires Python 3.12 or newer.

```bash
pip install idcognito-synthworld
synthworld generate --seed 20260719 --persona-count 10 --output world.json
```

The same explicit inputs reproduce the same deterministic fixture. Continue with
[Getting Started](https://bluntmachetti.github.io/synthworld/getting-started/) before
using a benchmark scorer.

## Why SynthWorld

| Requirement | Approach |
|---|---|
| Repeatable evaluation | Explicit seeds/configuration, canonical ordering, frozen fixtures, and checksums |
| Connected test data | Coherent worlds rather than independent fake rows |
| Adversarial cases | Conflicts, ambiguity, lifecycle changes, and negative controls are planted deliberately |
| Controlled oracle exposure | Product-facing observations and evaluator truth use separate artifacts and contracts |
| Reproducible claims | Versioned schemas, scoring formulas, benchmark identities, and integrity metadata |

A frozen conformance fixture is evidence that an adapter handles the declared cases;
it is not automatically evidence of real-world transfer or a vendor leaderboard.

## Current benchmark families

Use the generated [benchmark catalogue](https://bluntmachetti.github.io/synthworld/benchmarks/catalogue/) for governed current state and [BENCHMARKS.md](https://github.com/bluntmachetti/synthworld/blob/main/BENCHMARKS.md) for the human-readable inventory. Package presence does not by itself imply publication or maturity.

## Enterprise identity and access

The enterprise surface is documented in the [enterprise access guide](https://bluntmachetti.github.io/synthworld/guides/enterprise-access/) and its normative contract. It provides deterministic test inputs and evaluator truth; it is not a live IAM or enforcement service.

## What the ambiguity pack does and does not measure

The ambiguity families are conformance and generated evaluation surfaces, not claims of real-world transfer. Use the [identity-resolution guide](https://bluntmachetti.github.io/synthworld/guides/identity-resolution/) and [BENCHMARKS.md](https://github.com/bluntmachetti/synthworld/blob/main/BENCHMARKS.md) for their construction, limits, baselines, and current publication state.

## Benchmarks and documentation

- [Documentation](https://bluntmachetti.github.io/synthworld/)
- [Generated benchmark catalogue](https://bluntmachetti.github.io/synthworld/benchmarks/catalogue/)
- [Human-readable benchmark inventory](https://github.com/bluntmachetti/synthworld/blob/main/BENCHMARKS.md)
- [Asteria Agentic v1](https://github.com/bluntmachetti/synthworld/blob/main/AGENTIC_BENCHMARK.md)
- [Data dictionary](https://github.com/bluntmachetti/synthworld/blob/main/DATA_DICTIONARY.md)
- [Frozen tables on Hugging Face](https://huggingface.co/datasets/Bluntmachetti7/synthworld-benchmarks)
- [Roadmap](https://bluntmachetti.github.io/synthworld/roadmap/)
- [Changelog](https://github.com/bluntmachetti/synthworld/blob/main/CHANGELOG.md)

## Community and project policy

Questions and design discussions belong in
[GitHub Discussions](https://github.com/bluntmachetti/synthworld/discussions). Bugs
and scoped work belong in
[Issues](https://github.com/bluntmachetti/synthworld/issues).

Before contributing, read
[CONTRIBUTING.md](https://github.com/bluntmachetti/synthworld/blob/main/CONTRIBUTING.md).
Report security issues through the
[security policy](https://github.com/bluntmachetti/synthworld/security/policy), not a
public issue. SynthWorld is licensed under
[Apache-2.0](https://github.com/bluntmachetti/synthworld/blob/main/LICENSE).
