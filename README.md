# SynthWorld

[![CI](https://github.com/bluntmachetti/synthworld/actions/workflows/ci.yml/badge.svg)](https://github.com/bluntmachetti/synthworld/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/idcognito-synthworld)](https://pypi.org/project/idcognito-synthworld/)
[![Python versions](https://img.shields.io/pypi/pyversions/idcognito-synthworld)](https://pypi.org/project/idcognito-synthworld/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)
[![Coverage: 100% enforced](https://img.shields.io/badge/coverage-100%25_enforced-brightgreen)](Makefile)

SynthWorld generates deterministic, connected identity graphs for testing
privacy, PII-extraction, entity-resolution, and exposure-analysis systems
without collecting or fabricating data about real people. It began as the
ground-truth harness for Idcognito and is deliberately usable as an independent
Apache-2.0 Python package.

Every record is explicitly marked `synthetic: true`. Email addresses use the
reserved `example.test` domain, phone numbers use the fictional North American
`555-01xx` block, addresses contain obvious example components, and national
identifiers carry a `SYN-` prefix with deliberately invalid checksums. Do not
replace these safeguards with plausible real-world identifiers.

## What it provides

- seeded personas, identity attributes, and evidence-backed relationships;
- public exposure records for breach, broker, search, and social scenarios;
- exact-span extraction pages with evaluator-only answer keys;
- adversarial entity-resolution cases and relationship ground truth;
- risk-calibration cases with public observations physically separated from
  evaluator-only score and factor truth; and
- frozen, checksummed benchmarks plus machine-readable integrity metrics.

The core-world, exposure-corpus, extraction-corpus, connection-benchmark, and
risk-benchmark schemas are independently versioned `1.0.0` contracts. See
[DATA_DICTIONARY.md](DATA_DICTIONARY.md) for field definitions and the strict
public/oracle boundary. See [GOLDEN_REVIEW.md](GOLDEN_REVIEW.md) for the frozen
benchmark review record.

## Install

The distribution is published as `idcognito-synthworld`; the import package
and the CLI are both named `synthworld`, and the package ships typed
(`py.typed`). Release notes live in [CHANGELOG.md](CHANGELOG.md).

```bash
pip install idcognito-synthworld
synthworld generate --seed 20260719 --persona-count 10 --output world.json
```

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

## License

Copyright 2026 Idcognito contributors. Licensed under the
[Apache License 2.0](LICENSE).
