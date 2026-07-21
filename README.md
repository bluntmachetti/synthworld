# SynthWorld

[![CI](https://github.com/bluntmachetti/synthworld/actions/workflows/ci.yml/badge.svg)](https://github.com/bluntmachetti/synthworld/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/idcognito-synthworld)](https://pypi.org/project/idcognito-synthworld/)
[![Python versions](https://img.shields.io/pypi/pyversions/idcognito-synthworld)](https://pypi.org/project/idcognito-synthworld/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)
[![Coverage: 100% enforced](https://img.shields.io/badge/coverage-100%25_enforced-brightgreen)](Makefile)

**Faker generates rows. SynthWorld generates connected identity worlds with
adversarial evidence and an answer key.**

SynthWorld creates deterministic, safely fictional populations for evaluating
privacy, PII-extraction, entity-resolution, relationship-inference, and
exposure-analysis systems. It lets a product operate on realistic-looking but
explicitly synthetic observations while evaluators retain physically separate
ground truth.

SynthWorld began as the ground-truth harness for Idcognito and is deliberately
usable as an independent Apache-2.0 Python package. It is not an anonymisation
tool and does not transform sensitive real-world data into a safe dataset.

## Why SynthWorld

| Requirement | SynthWorld approach |
|---|---|
| Repeatable evaluation | Seeded generation, canonical ordering, frozen fixtures, and checksums |
| Connected identities | Personas share planted family, colleague, classmate, neighbour, and social evidence |
| Measurable ambiguity | Adversarial identity records include common names, Unicode, twins, maiden names, aliases, and misspellings |
| No label leakage | Product-safe public inputs are physically separated from evaluator-only answer keys |
| Safe fixtures | Reserved domains, fictional phones, example addresses, invalid identifiers, and recursive `synthetic: true` markers |
| Honest scoring | Versioned formulas and benchmark integrity metrics make every published claim reproducible |

A generated row can test whether a field accepts an email address. A SynthWorld
benchmark can test whether a system extracts that address from a document,
links several conflicting records to the correct entity, infers only supported
relationships, and assigns the expected exposure score without seeing the
answer key.

## Current benchmark families

- **Core identity world:** seeded personas, identity attributes, and
  evidence-backed relationships.
- **Exposure corpus:** breach, broker, search, and social observations,
  including zero-exposure controls, search collisions, and broker
  reappearance.
- **Exact-span extraction:** product-safe pages paired with evaluator-only
  occurrence-level PII labels.
- **Entity resolution:** opaque records and adversarial cases with separate
  entity-membership truth.
- **Relationship inference:** public association evidence, reciprocal positive
  cases, and unilateral negative controls.
- **Risk calibration:** provider-neutral breach observations with separately
  checksummed score, band, and factor truth.

The core-world, exposure-corpus, extraction-corpus, connection-benchmark, and
risk-benchmark schemas are independently versioned `1.0.0` contracts. See
[DATA_DICTIONARY.md](DATA_DICTIONARY.md) for field definitions and the strict
public/oracle boundary. See [GOLDEN_REVIEW.md](GOLDEN_REVIEW.md) for the frozen
benchmark review record.

## Public input and hidden truth

SynthWorld keeps the two sides of an evaluation distinct:

```text
product or model                    evaluator
       |                                |
       v                                v
public observations  ---------->  system predictions
                                          |
                                          v
                               separate answer key
                                          |
                                          v
                                  scored results
```

Public constructors accept only oracle-free corpus types. Commands that emit
answer keys are intended for evaluation infrastructure, not product or demo
data paths.

## Install

The distribution is published as `idcognito-synthworld`; the import package and
the CLI are both named `synthworld`, and the package ships typed (`py.typed`).
Release notes live in [CHANGELOG.md](CHANGELOG.md).

```bash
pip install idcognito-synthworld
synthworld generate --seed 20260719 --persona-count 10 --output world.json
```

The frozen golden benchmarks are also browsable as tables on
[Hugging Face](https://huggingface.co/datasets/Bluntmachetti7/synthworld-benchmarks),
byte-identical to the artifacts shipped in this package.

## Develop from source

Install [uv](https://docs.astral.sh/uv/), clone the repository, and run:

```bash
uv sync --locked --all-groups
uv run synthworld generate --seed 20260719 --persona-count 10 --output world.json
uv run synthworld metrics --seed 20260719 --persona-count 10
```

Useful corpus commands include:

```bash
uv run synthworld generate-corpus --seed 20260719 --persona-count 10 --output exposures.json
uv run synthworld generate-extraction --seed 20260719 --persona-count 10 --output extraction.json
uv run synthworld generate-public-connections --seed 20260719 --persona-count 10 --output connections.json
uv run synthworld generate-risk-public --seed 20260719 --persona-count 10 --output risk.json
```

See [examples/](examples/) for a worked exact-span extraction evaluation and
annotated sample output.

The `generate-connection-benchmark` and `generate-risk-answer` commands include
or emit evaluator-only truth. Keep those artifacts outside product and demo data
paths. The public commands emit only product-safe observations.

## Roadmap and integrations

SynthWorld is intended to remain a focused ground-truth identity layer rather
than become a second general-purpose simulator. Planned work is organised as
packs and adapters:

- data-broker deletion and reappearance for Idcognito;
- AI-agent and non-human identity graphs for ZeroID, Arena, and EADS;
- enterprise IAM and identity-governance scenarios;
- LLM, RAG, and agent-memory privacy evaluation;
- digital-wallet and verifiable-credential testing;
- disaster identity continuity for Aftershock.

The phased plan, architecture boundaries, and tracking issues are documented in
[ROADMAP.md](ROADMAP.md).

## Verify every claim

`make ci` runs formatting, linting, strict type checking, all tests with 100%
branch coverage, benchmark metrics at 10- and 100-persona scales, package
inspection, and an isolated-wheel smoke test. The same gates run on Python 3.12
and 3.14 in GitHub Actions; a separate workflow job scans the repository's full
history for secrets.

```bash
make ci
```

Generated JSON is safe for fixtures, demos, tutorials, and evaluation when its
synthetic markers remain intact. SynthWorld is not a source of real identity
data and must never be used to impersonate, target, or investigate a person.
Do not replace the safeguards with plausible real-world identifiers.

## License

Copyright 2026 Redoubt Labs ltd. Licensed under the
[Apache License 2.0](LICENSE).
