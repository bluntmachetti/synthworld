# SynthWorld

[![CI](https://github.com/bluntmachetti/synthworld/actions/workflows/ci.yml/badge.svg)](https://github.com/bluntmachetti/synthworld/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/idcognito-synthworld?cacheSeconds=3600)](https://pypi.org/project/idcognito-synthworld/)
[![Python versions](https://img.shields.io/pypi/pyversions/idcognito-synthworld?cacheSeconds=3600)](https://pypi.org/project/idcognito-synthworld/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](https://github.com/bluntmachetti/synthworld/blob/main/LICENSE)
[![Coverage: 100% enforced](https://img.shields.io/badge/coverage-100%25_enforced-brightgreen)](https://github.com/bluntmachetti/synthworld/blob/main/Makefile)

**Deterministic synthetic identity worlds with adversarial evidence and ground-truth answer keys.**

SynthWorld creates safely fictional, connected test worlds for evaluating identity,
privacy, access, and agent systems. Where a benchmark provides a product-safe
projection, public observations are serialized separately from evaluator truth so a
system can be tested without feeding it its own answers. Other commands emit
annotated or evaluator bundles and must not be treated as product input.

> **SynthWorld is not an anonymisation tool.** It does not transform sensitive real
> data into a safe dataset, and it is not an IAM product, policy engine, or runtime
> enforcement service.

## Choose what you want to do

| Goal | Start here |
|---|---|
| Install and create a first deterministic world | [Getting Started](https://bluntmachetti.github.io/synthworld/getting-started/) |
| Inspect published frozen benchmark tables | [Hugging Face dataset](https://huggingface.co/datasets/Bluntmachetti7/synthworld-benchmarks) |
| Evaluate identity resolution and ambiguity | [Identity resolution guide](https://bluntmachetti.github.io/synthworld/guides/identity-resolution/) |
| Evaluate privacy, extraction, exposure, or broker behavior | [Privacy and exposure guide](https://bluntmachetti.github.io/synthworld/guides/privacy-exposure/) |
| Test agent delegation, authority, and audit evidence | [Agent authority guide](https://bluntmachetti.github.io/synthworld/guides/agent-authority/) |
| Build or evaluate enterprise identity/access worlds | [Enterprise access guide](https://bluntmachetti.github.io/synthworld/guides/enterprise-access/) |
| Build and score an enterprise authorization experiment | [Enterprise authorization guide](https://bluntmachetti.github.io/synthworld/guides/enterprise-authorization-python/) |
| Connect a product or model to a SynthWorld scorer | [Evaluating a system](https://bluntmachetti.github.io/synthworld/guides/evaluating-a-system/) |
| Check current benchmark maturity and publication state | [Benchmark catalogue](https://bluntmachetti.github.io/synthworld/benchmarks/catalogue/) |

## Featured: agent authority

Identity resolution tells you **who acted**. Agent-authority evaluation asks whether
the action was within delegated authority **at the time it occurred**, whether the
runtime and credential bindings were correct, and whether retained evidence can
still reconstruct the decision later.

[Asteria Agentic v1](https://github.com/bluntmachetti/synthworld/blob/main/AGENTIC_BENCHMARK.md)
is the frozen, inspectable conformance fixture for that workflow. It keeps public
action evidence separate from authority, attribution, temporal, and provenance
truth.

## Why SynthWorld

| Requirement | SynthWorld approach |
|---|---|
| Repeatable evaluation | Explicit seeds/configuration, canonical ordering, frozen fixtures, and checksums |
| Connected test data | Coherent worlds rather than independent fake rows |
| Adversarial cases | Conflicts, ambiguity, lifecycle changes, and negative controls are planted deliberately |
| Controlled oracle exposure | Product-facing observations and evaluator truth use separate artifacts and contracts |
| Reproducible claims | Versioned schemas, scoring formulas, benchmark identities, and integrity metadata |

A frozen conformance fixture is evidence that an adapter handles the declared cases;
it is not automatically evidence of real-world transfer or a vendor leaderboard.

## Current benchmark families

SynthWorld includes deterministic surfaces for connected identity fixtures, privacy
and exposure, extraction, entity resolution, relationship inference, risk
calibration, agent authority, and enterprise identity/access evaluation. These
families do not all share the same maturity, publication state, CLI, or statistical
meaning.

Use the generated [benchmark catalogue](https://bluntmachetti.github.io/synthworld/benchmarks/catalogue/)
for governed current state and the human-readable
[BENCHMARKS.md](https://github.com/bluntmachetti/synthworld/blob/main/BENCHMARKS.md)
for benchmark context and reference results.

## The core identity world is a smoke surface

The frozen core world is intentionally small and structurally simple. It is useful
for deterministic fixtures, demonstrations, and CI, but it is **not a transfer
surface** for claims about real populations. Use richer generated profiles when
graph structure or population variation is part of the test.

See the [identity-world guide](https://bluntmachetti.github.io/synthworld/guides/identity-worlds/)
and [BENCHMARKS.md](https://github.com/bluntmachetti/synthworld/blob/main/BENCHMARKS.md)
for measured limits.

## What the ambiguity pack does and does not measure

The ambiguity families exercise conflicting evidence and evidence-aware resolution.
The frozen reference pack is a conformance fixture with deliberately small slices;
the generated v2 construction uses a different difficulty model. Neither should be
presented as proof of real-world transfer simply because a system scores well.

See the [identity-resolution guide](https://bluntmachetti.github.io/synthworld/guides/identity-resolution/)
and [BENCHMARKS.md](https://github.com/bluntmachetti/synthworld/blob/main/BENCHMARKS.md)
for the current constructions, baselines, and limitations.

## Public input and evaluator truth

Only inputs explicitly documented as public belong on the product side. Do **not**
assume that an artifact is product-safe merely because SynthWorld generated it.

For example, `generate-public-extraction`, `generate-public-connections`, and
`generate-risk-public` emit product-facing projections. By contrast,
`generate-extraction` and `generate-connection-benchmark` emit evaluator or annotated
bundles containing expected answers and must not be passed to the system under test.
Some benchmark commands write both `public/` and `evaluator/` subtrees; in that case,
pass only the documented public subtree to the product or model.

Evaluator artifacts contain the information used to score the resulting prediction
or trace.

```text
public benchmark input
        |
        v
 system under test
        |
        v
 prediction / trace ---------+
                             |
 evaluator truth ------------+--> independent metrics
```

Physical separation prevents accidental oracle use; it does not make a published
reference fixture secret.

## Enterprise identity and access

The enterprise surface can compile operator-authored structure into a deterministic,
safely fictional identity/access universe and provides bounded reference benchmark
and projection surfaces around it. Public product inputs and canonical evaluator
truth remain separate.

Start with the [enterprise access guide](https://bluntmachetti.github.io/synthworld/guides/enterprise-access/),
follow the [enterprise authorization guide](https://bluntmachetti.github.io/synthworld/guides/enterprise-authorization-python/)
for the installed-package experiment path, and use the
[normative enterprise contract](https://github.com/bluntmachetti/synthworld/blob/main/enterprise-identity-access-contract/README.md)
for the versioned artifact requirements.

## What the enterprise surface does not claim

- Importing enterprise structure is **not anonymisation**; authored structural inputs can remain sensitive.
- Offline evaluation and standards-shaped projections are **not deployed IAM or enforcement**.
- Published reference packs are **conformance fixtures**, not blind statistical benchmarks or vendor leaderboards.

## Install

SynthWorld requires Python 3.12 or newer. The distribution is
`idcognito-synthworld`; the import package and CLI are `synthworld`.

```bash
pip install idcognito-synthworld
synthworld generate --seed 20260719 --persona-count 10 --output world.json
```

The same explicit inputs reproduce the same deterministic fixture. Continue with
[Getting Started](https://bluntmachetti.github.io/synthworld/getting-started/) before
using a benchmark scorer.

## Evaluate a system

Every integration follows the same pattern: give the system only explicitly public
input, normalize its native output into the task-specific prediction or trace
contract, then score it against separately loaded evaluator truth.

See [Evaluating a system](https://bluntmachetti.github.io/synthworld/guides/evaluating-a-system/)
for runnable examples and metric interpretation.

## Validate before you score

Use a task validator where one exists. Structural validity means a submission can be
scored; it does not mean the system performed well.

```bash
synthworld validate agentic-trace --predictions observed-actions.jsonl
```

## Use Asteria Agentic v1

A minimal agent-authority evaluation flow is:

```bash
synthworld generate-agentic --output asteria-agentic-v1
synthworld validate agentic-trace --predictions observed-actions.jsonl
synthworld evaluate agentic --predictions observed-actions.jsonl --summary
```

Give only the generated `public/` tree to the system under test. Keep the evaluator
side out of the adapter path even though the frozen reference truth is publicly
inspectable. See the full [Asteria Agentic v1 guide](https://github.com/bluntmachetti/synthworld/blob/main/AGENTIC_BENCHMARK.md).

For configurable generated enterprise-agentic worlds, explicitly select the
generated profile. Smoke preserves its released V1 contract; standard and
longitudinal use a separate V2 scale/lifecycle family:

```bash
synthworld generate-enterprise-agentic \
  --profile generated \
  --tier smoke \
  --seed 20260814 \
  --output generated-enterprise-agentic
```

An external adapter receives only `generated-enterprise-agentic/public`, replays its
events in order, and writes the observations it actually obtained. Validate without
evaluator access, then score in a separate evaluator process:

```bash
synthworld validate generated-enterprise-agentic-trace \
  --benchmark-root generated-enterprise-agentic \
  --predictions observed-actions.jsonl
synthworld evaluate generated-enterprise-agentic \
  --benchmark-root generated-enterprise-agentic \
  --predictions observed-actions.jsonl \
  --summary
```

This is a deterministic benchmark-data generator, not an IAM product, policy
engine, agent framework, hosted simulator, or vendor leaderboard. A reference
organisation topology can inform the supported count configuration; SynthWorld does
not import its named entities or relationships. See the
[agent-authority guide](https://bluntmachetti.github.io/synthworld/guides/agent-authority/)
for the replay, decision-only SUT, and provenance boundaries, and the
[scale-tier guide](https://bluntmachetti.github.io/synthworld/guides/enterprise-agentic-scale/)
for configuration, lifecycle, metrics, and measured runtime/memory characteristics.

## Verify every claim

For reproducible evaluation, retain the benchmark identity, relevant seed and
configuration, schema/scoring versions, artifact checksums, and the exact prediction
or trace bytes that were scored. Interpret each metric through its own denominator
and support semantics rather than hiding weak dimensions behind an aggregate.

Use the [data dictionary](https://github.com/bluntmachetti/synthworld/blob/main/DATA_DICTIONARY.md)
and [benchmark inventory](https://github.com/bluntmachetti/synthworld/blob/main/BENCHMARKS.md)
for authoritative contracts and reference results.

## Roadmap and integrations

Current direction is summarized in the [documentation roadmap](https://bluntmachetti.github.io/synthworld/roadmap/)
and the repository [ROADMAP.md](https://github.com/bluntmachetti/synthworld/blob/main/ROADMAP.md).
Governed registries—not issue state—remain authoritative for current capability and
benchmark publication status.

## Develop from source

```bash
uv sync --locked --all-groups
make ci
```

Contribution guidance is in
[CONTRIBUTING.md](https://github.com/bluntmachetti/synthworld/blob/main/CONTRIBUTING.md).

## License

Copyright 2026 Redoubt Labs ltd. Licensed under the
[Apache License 2.0](https://github.com/bluntmachetti/synthworld/blob/main/LICENSE).
