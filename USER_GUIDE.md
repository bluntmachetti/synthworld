# SynthWorld user guide

This file is now a **compatibility index** for repository links and historical anchors. Detailed user documentation lives at https://bluntmachetti.github.io/synthworld/.

Use these canonical entry points:

- [Getting Started](docs/getting-started.md)
- [Guides](docs/guides/index.md)
- [Evaluating a system](docs/guides/evaluating-a-system.md)
- [Identity resolution](docs/guides/identity-resolution.md)
- [Privacy and exposure](docs/guides/privacy-exposure.md)
- [Agent authority](docs/guides/agent-authority.md)
- [Enterprise identity and access](docs/guides/enterprise-access.md)
- [Enterprise Identity Planning](docs/guides/enterprise-identity-planning.md)
- [Technical reference](docs/reference/index.md)
- [Benchmark inventory](BENCHMARKS.md)
- [Data dictionary](DATA_DICTIONARY.md)

The headings below intentionally preserve earlier GitHub anchors while routing each topic to its canonical owner.

## Choose your use case

See the [documentation home](docs/index.md) for current journey routing and the generated [benchmark catalogue](https://bluntmachetti.github.io/synthworld/benchmarks/catalogue/) for governed current state.

## The three-part workflow

See [Evaluating a system](docs/guides/evaluating-a-system.md).

## Try SynthWorld without installing it

Browse the published frozen tables on [Hugging Face](https://huggingface.co/datasets/Bluntmachetti7/synthworld-benchmarks), then use [Benchmarks](docs/reference/benchmarks.md) for publication boundaries.

## Install and create your first world

See [Getting Started](docs/getting-started.md).

## Run five foundational evaluation examples

See [Evaluating a system](docs/guides/evaluating-a-system.md).

## Use case 1: safe connected identity fixtures

See [Identity worlds](docs/guides/identity-worlds.md) and [BENCHMARKS.md](BENCHMARKS.md) for the core fixture's measured limits.

## Use case 2: PII extraction

See [Privacy and exposure](docs/guides/privacy-exposure.md) and [DATA_DICTIONARY.md](DATA_DICTIONARY.md) for the exact extraction contract.

## Use case 3: entity resolution

See [Identity resolution](docs/guides/identity-resolution.md).

## Use case 4: relationship inference

See [Identity worlds](docs/guides/identity-worlds.md), [Evaluating a system](docs/guides/evaluating-a-system.md), and [BENCHMARKS.md](BENCHMARKS.md).

## Use case 5: breach-risk calibration

See [Privacy and exposure](docs/guides/privacy-exposure.md) and [DATA_DICTIONARY.md](DATA_DICTIONARY.md).

## Use case 6: agent identity and delegated authority

See [Agent authority](docs/guides/agent-authority.md), [Asteria Agentic v1](AGENTIC_BENCHMARK.md), and the [agent-authority contract](agent-authority-contract/README.md).

## Use case 7: exposure scenarios

See [Privacy and exposure](docs/guides/privacy-exposure.md).

## Use case 8: households and workplaces

See [Identity worlds](docs/guides/identity-worlds.md) and [BENCHMARKS.md](BENCHMARKS.md).

### Generation cost

The original guide carried one measured reference that is retained here for compatibility until it has a dedicated generated-performance reference page. `examples/measure_households_cost.py` records interpreter and platform with each run.

Reference run: Python 3.12.12, Linux x86-64, glibc 2.43; three timed repeats after a discarded warm-up.

| People | Median runtime | Peak Python allocation |
|---:|---:|---:|
| 100 | 0.046 s | 1.1 MiB |
| 500 | 0.287 s | 12.3 MiB |
| 2000 | 2.003 s | 116.6 MiB |

```bash
uv run python examples/measure_households_cost.py --person-count 100 --repeats 5
```

Peak allocation is `tracemalloc`, not process RSS. The configured 2000-person ceiling is not a measured performance cliff.

## Use case 9: identity-resolution ambiguity

See [Identity resolution](docs/guides/identity-resolution.md).

### Two truths, kept apart

See [Identity resolution](docs/guides/identity-resolution.md) and [Public vs evaluator](docs/concepts/public-vs-evaluator.md).

### Score complete partitions before projecting pairs

See [Identity resolution](docs/guides/identity-resolution.md).

### The report has no aggregate score

See [Identity resolution](docs/guides/identity-resolution.md) and [Metrics](docs/reference/metrics.md).

### Reference baselines

See [Identity resolution](docs/guides/identity-resolution.md) and [BENCHMARKS.md](BENCHMARKS.md).

### Limits, stated plainly

See [Identity resolution](docs/guides/identity-resolution.md) and [BENCHMARKS.md](BENCHMARKS.md).

## Use case 10: search-provider input without the answer key

See [Privacy and exposure](docs/guides/privacy-exposure.md).

### The public half rejects truth, it does not merely omit it

See [Public vs evaluator](docs/concepts/public-vs-evaluator.md).

### Controlled failure modes, all planted deliberately

See [Privacy and exposure](docs/guides/privacy-exposure.md) and [BENCHMARKS.md](BENCHMARKS.md).

### Scoring, and what it refuses to hide

See [Privacy and exposure](docs/guides/privacy-exposure.md) and [Metrics](docs/reference/metrics.md).

### Reference baselines

See [Privacy and exposure](docs/guides/privacy-exposure.md) and [BENCHMARKS.md](BENCHMARKS.md).

## Use case 11: enterprise identity and access structure

See [Enterprise Identity Planning](docs/guides/enterprise-identity-planning.md), [Enterprise identity and access](docs/guides/enterprise-access.md), and the [enterprise contract](enterprise-identity-access-contract/README.md).

### Author, validate, compile

See [Enterprise identity and access](docs/guides/enterprise-access.md).

### Validation reports every error in a stage, not the first one

See the [enterprise contract](enterprise-identity-access-contract/README.md) for normative validation behavior.

### What compilation writes

See [Enterprise identity and access](docs/guides/enterprise-access.md) and the [enterprise contract](enterprise-identity-access-contract/README.md).

### What the seed moves, and what it does not

See [Determinism, seeds, and keys](docs/concepts/determinism-seeds-and-keys.md).

### Limits worth knowing before you author

See the [enterprise contract](enterprise-identity-access-contract/README.md).

## Use case 12: projecting a compiled world to SCIM, OpenFGA, and AuthZEN

See [Standards profiles](docs/reference/standards-profiles.md) and the [enterprise contract](enterprise-identity-access-contract/README.md).

### SCIM

See [Standards profiles](docs/reference/standards-profiles.md).

### OpenFGA

See [Standards profiles](docs/reference/standards-profiles.md).

### AuthZEN

See [Standards profiles](docs/reference/standards-profiles.md).

### Every projection reports what it lost

See [Standards profiles](docs/reference/standards-profiles.md) and the normative enterprise contract.

### Shared Signals / CAEP is a declaration, not an emitter

See [Standards profiles](docs/reference/standards-profiles.md).

## Use case 13: enterprise authorization benchmarks

See [Enterprise Identity Planning](docs/guides/enterprise-identity-planning.md), [Enterprise identity and access](docs/guides/enterprise-access.md), [Evaluating a system](docs/guides/evaluating-a-system.md), and the relevant contract README.

### Run the enterprise-agentic smoke pack

See [Enterprise identity and access](docs/guides/enterprise-access.md) and [CLI reference](docs/reference/cli.md).

### Check the shape before you score

See [Evaluating a system](docs/guides/evaluating-a-system.md).

### Evaluate a prediction

See [Evaluating a system](docs/guides/evaluating-a-system.md).

### Scoring the directory/RBAC oracle from Python

See [Enterprise identity and access](docs/guides/enterprise-access.md) and the [enterprise contract](enterprise-identity-access-contract/README.md).

### The identity-fabric pack is Python-only

See [CLI reference](docs/reference/cli.md) and the [enterprise contract](enterprise-identity-access-contract/README.md).

### Limits, stated plainly

See [Enterprise identity and access](docs/guides/enterprise-access.md) and [Benchmarks](docs/reference/benchmarks.md).

## Reading evaluation results

See [Metrics](docs/reference/metrics.md) and [Evaluating a system](docs/guides/evaluating-a-system.md).

## Safety boundary

See [Safety boundary](docs/concepts/safety-boundary.md) and [Public vs evaluator](docs/concepts/public-vs-evaluator.md).

### Enterprise trees

See [Enterprise identity and access](docs/guides/enterprise-access.md) and the normative enterprise contract.
