# SynthWorld documentation

> **Current-main documentation.** These pages describe the repository's current
> `main` branch and may include changes not yet released. For a released contract,
> use the matching signed Git tag, release notes, and packaged artifacts.

SynthWorld generates deterministic, safely fictional identity worlds and separates
product-facing observations from evaluator truth so identity, privacy, access, and
agent systems can be tested reproducibly.

## Mental model

```text
explicit seed + config + schema version + event schedule
                         |
                         v
             deterministic identity world
                    /            \
                   v              v
          public product input   evaluator truth
                   |              |
                   v              |
             system under test    |
                   |              |
                   +---- prediction/trace
                                  |
                                  v
                       independent metrics
```

## Choose your goal

| Goal | Start here |
|---|---|
| Install and create a first world | [Getting Started](getting-started.md) |
| Build connected identity fixtures | [Identity worlds](guides/identity-worlds.md) |
| Evaluate matching or privacy behavior | [Identity resolution](guides/identity-resolution.md) or [privacy exposure](guides/privacy-exposure.md) |
| Test agent delegation and audit evidence | [Agent authority](guides/agent-authority.md) |
| Compare RBAC, ABAC, and ReBAC on one agentic world | [Enterprise agentic identity experiment](guides/enterprise-agentic-identity-experiment.md) |
| Compile enterprise identity and access truth | [Enterprise access](guides/enterprise-access.md) |
| Build and score an enterprise authorization experiment | [Enterprise authorization](guides/enterprise-authorization-python.md) |
| Plan an enterprise identity and authorization journey | [Enterprise Identity Planning](guides/enterprise-identity-planning.md) |
| Connect a system to an evaluator | [Evaluating a system](guides/evaluating-a-system.md) |
| Understand benchmark contracts and boundaries | [Concepts](concepts/index.md) |

## Five-minute quickstart

```bash
pip install idcognito-synthworld
synthworld generate --seed 20260719 --persona-count 10 --output world.json
```

`world.json` is fictional and repeatable for the same explicit inputs. Continue with
[Getting Started](getting-started.md) before using a benchmark scorer.

## Capability and benchmark status

Capability maturity and benchmark publication are different axes. The documentation
build consumes drift-checked resolved capability and benchmark registries and emits a
public allowlisted catalogue:

- [Capability reference](reference/capabilities.md)
- [Benchmark publication reference](reference/benchmarks.md)
- [Generated registry catalogue](/benchmarks/catalogue)

A benchmark being packaged or published does not imply that every related capability
is mature, and capability maturity does not authorize external publication.

## Featured benchmarks

- [Generated benchmark inventory](../BENCHMARKS.md)
- [Asteria Agentic v1](../AGENTIC_BENCHMARK.md)
- [Published frozen tables on Hugging Face](https://huggingface.co/datasets/Bluntmachetti7/synthworld-benchmarks)

## Current focus

The project is preserving frozen benchmark bytes while improving user journeys,
publication controls, generated enterprise/agent depth, and evidence-binding
contracts. Candidate benchmark artifacts remain candidates until their explicit
publication gates are satisfied.

See the [roadmap view](roadmap/index.md) for Now/Next/Later framing and the generated
registries for current maturity/publication state.

## Navigate

| Destination | Link |
|---|---|
| Home | This page |
| Getting Started | [Install and first evaluation](getting-started.md) |
| Guides | [Journey guides](guides/index.md) |
| Benchmarks | [Benchmark reference](reference/benchmarks.md) |
| Experiments | [Reproducible experiments](experiments/index.md) |
| Roadmap | [Now/Next/Later](roadmap/index.md) |
| Support | [Help and contribution routes](support/index.md) |
| Reference | [Technical reference](reference/index.md) |

## Project links

- [Source](https://github.com/bluntmachetti/synthworld)
- [PyPI](https://pypi.org/project/idcognito-synthworld/)
- [Releases](https://github.com/bluntmachetti/synthworld/releases)
- [Hugging Face](https://huggingface.co/datasets/Bluntmachetti7/synthworld-benchmarks)
- [GitHub Discussions](https://github.com/bluntmachetti/synthworld/discussions)
