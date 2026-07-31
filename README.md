# SynthWorld

[![CI](https://github.com/bluntmachetti/synthworld/actions/workflows/ci.yml/badge.svg)](https://github.com/bluntmachetti/synthworld/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/idcognito-synthworld?cacheSeconds=3600)](https://pypi.org/project/idcognito-synthworld/)
[![Python versions](https://img.shields.io/pypi/pyversions/idcognito-synthworld?cacheSeconds=3600)](https://pypi.org/project/idcognito-synthworld/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)
[![Coverage: 100% enforced](https://img.shields.io/badge/coverage-100%25_enforced-brightgreen)](Makefile)

**Faker generates rows. SynthWorld generates connected identity worlds with
adversarial evidence and an answer key.**

SynthWorld creates deterministic, safely fictional populations for evaluating
privacy, PII-extraction, entity-resolution, relationship-inference,
agent-authority, and exposure-analysis systems. Selected benchmark families
expose separately
serialized product-safe observations; other artifacts are evaluator bundles
that retain answer keys for scoring.

SynthWorld began as the ground-truth harness for Idcognito and is deliberately
usable as an independent Apache-2.0 Python package. It is not an anonymisation
tool and does not transform sensitive real-world data into a safe dataset.

## Choose what you want to do

| Your goal | Start here | Availability |
|---|---|---|
| Inspect the data without installing anything | [Browse the frozen benchmarks on Hugging Face](https://huggingface.co/datasets/Bluntmachetti7/synthworld-benchmarks) | Available |
| Test agent identity and delegated authority | Use [Asteria Agentic v1](AGENTIC_BENCHMARK.md) | Available |
| Create safe connected identities for tests or demos | Run `synthworld generate` | Available |
| Evaluate PII extraction, entity matching, relationship inference, or risk scoring | Follow the [user guide](USER_GUIDE.md) | Available |
| Explore breach, search, broker, and social exposure scenarios | Generate an exposure corpus | Partial: generation and integrity metrics |
| Test broader IAM, RAG privacy, wallets, or disaster identity | See the [roadmap](ROADMAP.md) | Planned |

New to benchmark evaluation? The [user guide](USER_GUIDE.md) explains the
workflow in plain language, provides a five-minute walkthrough, and shows where
your own system plugs into each current use case.

## Featured: agent authority

**Identity tells you which agent acted. SynthWorld evaluates whether your
system can show that the action was within delegated authority at the time —
and whether the retained evidence can still prove it later.**

Give your gateway, policy or audit stack a deterministic public identity
world. Emit an `ObservedActionTrace`; score it against physically separate
evaluator truth:

```bash
synthworld generate-agentic --output asteria-agentic-v1
synthworld validate agentic-trace --predictions observed-actions.jsonl
synthworld evaluate agentic --predictions observed-actions.jsonl --summary
```

[Asteria Agentic v1](AGENTIC_BENCHMARK.md) is a frozen, manually inspectable
conformance fixture with separate authority, attribution, temporal, and
provenance truth. Final audit state cannot replace historical replay; Asteria
scores the difference.

## Why SynthWorld

| Requirement | SynthWorld approach |
|---|---|
| Repeatable evaluation | Seeded generation, canonical ordering, frozen fixtures, and checksums |
| Connected identities | Personas share planted family, colleague, classmate, neighbour, and social evidence |
| Measurable ambiguity | Adversarial identity records include common names, Unicode, twins, maiden names, aliases, and misspellings |
| Controlled oracle exposure | Extraction, connection, and risk each provide a separately serialized product-safe corpus and physically separate evaluator truth |
| Safe fixtures | Reserved domains, fictional phones, example addresses, invalid identifiers, and recursive `synthetic: true` markers |
| Honest scoring | Versioned formulas and benchmark integrity metrics make every published claim reproducible |

A generated row can test whether a field accepts an email address. A SynthWorld
benchmark can measure whether a system extracts that address from a document,
links several conflicting records to the correct entity, infers only supported
relationships, and assigns the expected exposure score.

## Current benchmark families

- **Core identity world:** seeded personas, identity attributes, and
  evidence-backed relationships. A deterministic smoke surface, not a transfer
  surface — see [the scope note](#the-core-identity-world-is-a-smoke-surface).
- **Exposure corpus:** breach, broker, search, and social observations,
  including zero-exposure controls, search collisions, and broker
  reappearance.
- **Exact-span extraction:** a product-safe public page corpus and a physically
  separate exact-span answer key, plus an annotated evaluator bundle that
  pairs the two for offline scoring.
- **Entity resolution:** opaque records and adversarial cases with separate
  entity-membership truth.
- **Relationship inference:** public association evidence, reciprocal positive
  cases, and unilateral negative controls.
- **Risk calibration:** provider-neutral breach observations with separately
  checksummed score, band, and factor truth.
- **Asteria Agentic v1:** ordered agent/runtime/delegation events, an
  oracle-free observed-action interface, and separate authority, attribution,
  temporal, and provenance truth.

### The core identity world is a smoke surface

The core world is frozen, and its shape is deliberate rather than realistic. Three
properties matter if you plan to derive evaluation data from it, all measured on
100 personas across seeds 7, 11 and 42:

- **Identifiers embed the persona ordinal.** `persona-0003` produces
  `synth_sian_cox_0003@example.test`, the username `synth_sian_cox_0003`,
  `Example Works 0003`, and `Test University 0003` — 100% of emails and usernames,
  80% of employers and schools. If you generate records where several rows describe
  one persona, that ordinal is an oracle: a matcher can recover the entity partition
  by reading it out of a public field rather than by resolving anything. The shipped
  entity-resolution pack is hand-authored and does **not** carry it.
- **The relationship graph is a path.** 100 personas yield 99 edges in one component
  with no cycles, no isolated nodes, and a degree distribution of `{1: 2, 2: 98}`.
  Graph structure therefore carries no signal.
- **Seeds change values, not structure.** The component count, degree distribution,
  relationship-kind counts and the 13 distinct exposure signatures are identical on
  every seed.

That makes it excellent for deterministic tests, demonstrations, and CI: byte-stable,
tiny, and easy to reason about. It makes it a poor basis for judging whether a system
will work on real data — a perfect score here is not evidence of transfer.

Realism improvements land in a separate named profile rather than by changing this
one, so existing fixtures and checksums stay byte-identical. Track that work in
[issue #43](https://github.com/bluntmachetti/synthworld/issues/43); the adversarial
identity cases that go with it are [issue #41](https://github.com/bluntmachetti/synthworld/issues/41).

The core-world, exposure-corpus, extraction-corpus, connection-benchmark,
risk-benchmark, and agentic schemas are independently versioned `1.0.0`
contracts. See
[DATA_DICTIONARY.md](DATA_DICTIONARY.md) for field definitions and the strict
public/oracle boundary. See [GOLDEN_REVIEW.md](GOLDEN_REVIEW.md) for the frozen
benchmark review record.

## Public input and evaluator truth

Extraction, connection, risk, and Asteria Agentic each provide separately
serialized product-safe input and physically separate evaluator truth. The
first three use `PublicExtractionCorpus`, `PublicConnectionCorpus`, and
`PublicRiskCorpus`; Asteria uses a multi-file public package. Extraction also
ships an `ExtractionCorpus` annotated bundle, in which every
`AnnotatedExtractionPage` embeds both the safe page and its `answer_key`, for
offline evaluators; that bundle is convenient but is not a product-safe input.

The separated evaluation flow is:

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

Only corpus types and CLI commands explicitly described as public should be
passed to product adapters. Do not pass the annotated extraction corpus into a
product or model without first projecting only its page fields.

## Install

The distribution is published as `idcognito-synthworld`; the import package and
the CLI are both named `synthworld`, and the package ships typed (`py.typed`).
Release notes live in [CHANGELOG.md](CHANGELOG.md).

SynthWorld requires Python 3.12 or newer; Python 3.11 and earlier are not
supported.

```bash
pip install idcognito-synthworld
synthworld generate --seed 20260719 --persona-count 10 --output world.json
```

Selected frozen golden benchmarks are also browsable as tables on
[Hugging Face](https://huggingface.co/datasets/Bluntmachetti7/synthworld-benchmarks),
byte-identical to the artifacts shipped in this package. The maintained
dataset-card source and Asteria download instructions live in
[`huggingface/README.md`](huggingface/README.md).

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
uv run synthworld generate-public-extraction --seed 20260719 --persona-count 10 --output extraction.json
uv run synthworld generate-public-connections --seed 20260719 --persona-count 10 --output connections.json
uv run synthworld generate-risk-public --seed 20260719 --persona-count 10 --output risk.json
uv run synthworld generate-agentic --output asteria-agentic-v1
```

### Use Asteria Agentic v1

Export the frozen world, then give only its `public/` directory to the system
under test:

```bash
synthworld generate-agentic --output asteria-agentic-v1
jq -c 'select(.payload.event_type == "action_attempted")' \
  asteria-agentic-v1/public/public_events.jsonl
```

Your adapter must write one `ObservedActionTrace` JSON object per action event.
The repository's deliberately imperfect current-state baseline demonstrates the
public-only integration path and writes a CLI-ready trace:

```bash
uv run python examples/evaluate_all.py --predictions-dir predictions
uv run synthworld evaluate agentic \
  --predictions predictions/agentic.jsonl \
  --summary
```

Replace `current_state_agentic_trace` in the example with your own policy,
agent-observability, or audit system. Keep `asteria-agentic-v1/evaluator/` out of
that adapter; the SynthWorld scorer joins the answer key only after predictions
have been produced. See the [Asteria guide](AGENTIC_BENCHMARK.md) for the JSONL
schema, Python API, replay rules, checksum verification, and metric definitions.

Custom agentic worlds built with `build_agentic_benchmark` are fully replayed
and relationally validated before evaluator truth is created. Malformed
runtime/agent, credential, delegator, actor, and owner-chain joins are rejected;
truthful unauthorized attempts remain scoreable denials. Agentic scoring
protocol `0.3.0` also distinguishes missing evidence from fabricated extras with
completeness, exact-match, and micro-precision metrics.

See the [user guide](USER_GUIDE.md) for goal-led walkthroughs,
[examples/](examples/) for runnable adapters and annotated sample output, and
[BENCHMARKS.md](BENCHMARKS.md) for reference baseline results and visual
demonstrations.

The `generate-extraction`, `generate-extraction-answers`,
`generate-connection-benchmark`, and `generate-risk-answer` commands include or
emit evaluator-only truth. Keep those artifacts outside product and demo data
paths. The `generate-public-extraction`, `generate-public-connections`, and
`generate-risk-public` commands emit the separately serialized product-safe
observations.

## Validate before you score

Agentic submissions can be checked for shape before any scoring, without the answer
key:

```bash
synthworld validate agentic-trace --predictions PATH [--json]
```

It reports every malformed row, duplicate, missing and unexpected event in one pass
with line numbers, and exits `0` when the submission is valid or `1` when it is not.
A valid result means `evaluate agentic` will not reject the file; it says nothing
about how well the system scored. Unlike `evaluate`, the default output is a human
summary and `--json` opts into the machine report — an evaluation report is a record
to keep, whereas this is read once to find a broken line.

## Evaluate a system

SynthWorld provides a unified command line tool to score predictions against separately serialized ground-truth answer keys:

```bash
synthworld evaluate <task> --predictions PATH [--seed S] [--persona-count N] [--summary]
```

Where `task` is one of `agentic`, `extraction`, `entity-resolution`,
`relationship`, or `risk`. Agentic predictions use JSONL; the other tasks use
JSON.

- `--predictions`: Path to the system predictions JSON or JSONL file,
  conforming to the task-specific schema.
- `--seed`: The benchmark seed used to load/generate matching ground-truth
  (ignored for frozen Asteria Agentic v1).
- `--persona-count`: The benchmark persona count (ignored for
  `entity-resolution` and Asteria Agentic v1).
- `--summary`: If provided, outputs a clean, compact terminal table summarizing the metrics instead of the raw JSON report.

Examples:
```bash
synthworld evaluate extraction --predictions predictions.json --seed 20260719 --summary
synthworld evaluate agentic --predictions observed-actions.jsonl --summary
```

Start with the [user guide](USER_GUIDE.md) for runnable examples and score
interpretation. See [DATA_DICTIONARY.md](DATA_DICTIONARY.md) for the full
prediction and report schemas.

## Roadmap and integrations

SynthWorld is intended to remain a focused ground-truth identity layer rather
than become a second general-purpose simulator. Planned work is organised as
packs and adapters:

- data-broker deletion and reappearance for Personal Identity protection solutions;
- broader AI-agent and non-human identity profiles for Enterprise simulation systems,
  building on the available Asteria Agentic v1 conformance fixture;
- enterprise IAM and identity-governance scenarios;
- LLM, RAG, and agent-memory privacy evaluation;
- digital-wallet and verifiable-credential testing;
- disaster identity continuity scenario testing.

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

Generated JSON is safely fictional for fixtures, demos, tutorials, and
evaluation when its synthetic markers remain intact. That safety property does
not make every artifact oracle-free product input; use only explicitly public
corpora for product adapters. SynthWorld is not a source of real identity data
and must never be used to impersonate, target, or investigate a person. Do not
replace the safeguards with plausible real-world identifiers.

## License

Copyright 2026 Redoubt Labs ltd. Licensed under the
[Apache License 2.0](LICENSE).
