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
| Model an enterprise identity/access world and test RBAC, ABAC, or ReBAC authorization | See [the enterprise surface](#enterprise-identity-and-access) | Partial: contracts published, unreleased |
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
  entity-resolution pack is hand-authored and does not carry *this* ordinal, but it
  carried three of its own until recently — see below.
- **The relationship graph is a path.** 100 personas yield 99 edges in one component
  with no cycles, no isolated nodes, and a degree distribution of `{1: 2, 2: 98}`.
  Graph structure therefore carries no signal.
- **Seeds change values, not structure.** The component count, degree distribution,
  relationship-kind counts and the 13 distinct exposure signatures are identical on
  every seed.

That makes it excellent for deterministic tests, demonstrations, and CI: byte-stable,
tiny, and easy to reason about. It makes it a poor basis for judging whether a system
will work on real data — a perfect score here is not evidence of transfer.

### What the ambiguity pack does and does not measure

The pack asks a system to decide record pairs. Three of its public surfaces used to
answer the question for it, each because a *free* choice was tied to the answer key
rather than to the evidence:

- the public pair list was emitted in draft order, so the i-th pair was the i-th
  scenario — 15/15 in the frozen pack, 750/750 across fifty generated seeds;
- display names were indexed by the scenario's position in the enum, so one regex
  recovered every scenario and, through the published scenario-to-disposition map,
  every answer;
- variant record identifiers were derived from draft position and the public seed.

All three are closed, and the first is closed in the model, so a generator that
rebuilds the pair list in draft order now fails to construct. Record identifiers in
both the canonical pack and its variants are content-addressed. One limit remains,
and it is a property of the design rather than a bug:

- **The evidence determines the answer.** Each scenario is *defined* by its evidence
  pattern — which attribute kinds are present, which agree, which contradict — so a
  system that reads the pattern can name the scenario. Over fifty seeds there are 20
  distinct patterns and no collisions. That is the task, not a leak; but it does mean
  a pack containing every scenario exactly once is a conformance fixture rather than
  a discrimination test.

Held-out private seeds therefore protect surface values, not labels. Treat a score on
this pack as evidence that a pipeline handles the named hard cases, not as evidence
that it can tell them apart from cases it has not seen.

Realism improvements land in a separate named profile rather than by changing this
one, so existing fixtures and checksums stay byte-identical. Track that work in
[issue #43](https://github.com/bluntmachetti/synthworld/issues/43); the adversarial
identity cases that go with it are [issue #41](https://github.com/bluntmachetti/synthworld/issues/41).

The generated **v2 pack** goes further (#80): instead of a codebook of cleartext
identity indices, each value is drawn from a pool of confusable clusters and passed
through a structured-noise operator applied identically under every relation, so
identity recovery stays free but the *relation* is carried only by overlapping distance
distributions. Its difficulty is therefore a computed **genie floor** — the Bayes error
of the generator itself, published with a confidence interval and keyed to a digest of
every decision-relevant constant — rather than a claim. See
[DATA_DICTIONARY.md](DATA_DICTIONARY.md) and [BENCHMARKS.md](BENCHMARKS.md) for the
published number and the enumerated channel invariants that back it.

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

## Enterprise identity and access

**Identity tells you who holds an entitlement. The enterprise surface evaluates
whether a system reaches the correct authorization decision — and whether it can
still show which rule, role, relationship, or delegation produced it.**

The surface is two things, and it matters which one you are using.

**A compiler.** `compile-enterprise-access` turns an operator-authored blueprint
of enterprise identity/access *structure* into a fixed, safely fictional
universe: tenants, organisations, units, principals, unbound account slots,
access subjects, groups, roles, permissions, opaque authorization targets,
relationship anchors, and a frozen access-atom inventory. Canonical
account-to-principal bindings are written to a separate `evaluator/` file; the
public universe carries no `principal_id` on an account.

**Reference benchmark packs.** The enterprise `generate-*` commands build
built-in reference packs. **No CLI command takes a universe you compiled.**
`generate-enterprise-agentic` and `generate-contextual-access` re-derive the
pinned reference universe and abort if its digest has moved;
`generate-continuous-assurance` builds from the shipped reference sources; the
authority-change governance pack is self-contained. So the three-command
quickstart below gives you a universe and its binding truth — it does not, on
its own, give you the oracles.

The Python API is the bridge, partially. The RBAC, ABAC, and ReBAC truth
compilers, the evaluation-corpus compiler, the SCIM/OpenFGA/AuthZEN projections,
and `generate_contextual_access_smoke` all take a `universe=` argument and will
accept one you compiled. But they also require inputs that nothing derives from
your blueprint: a corpus config, and state and intent overlays. A corpus config
pins the digest of the universe it was built against, so it is not portable to
any other universe — re-pointing the shipped reference corpus config at a
universe compiled from the same blueprint at a different seed fails with
`corpus_universe_digest_mismatch`.

It is for teams building or auditing an IAM, authorization, access-review, or
agent-gateway stack who need a deterministic world plus an answer key. It is not
a directory service, IGA workflow system, policy decision point, identity-fabric
product, vendor client, or runtime enforcement component. Nothing in it performs
a network call, credential exchange, or enforcement action — and the package
ships no HTTP client at all. The AuthZEN surface projects requests and
normalizes decision observations, but you supply the entire transport: calling a
live PDP, and producing the `transport_evidence_digest` that
`normalize_authzen_observation` expects, are yours to implement.

```bash
synthworld scaffold-enterprise-access --format yaml --output private-enterprise.yaml
synthworld validate-enterprise-access --input private-enterprise.yaml
synthworld compile-enterprise-access \
  --input private-enterprise.yaml \
  --seed 20260804 \
  --output compiled-enterprise
```

Compilation is deterministic: the same import at the same seed, compiler
version, and selector algorithm version reproduces the universe and the binding
truth byte for byte.

The seed does two different things, and only one of them is cosmetic.
Structural identifiers — tenant, organisation, unit, principal, group, role,
authorization target, and permission — derive from the namespace salt and your
logical keys, not from the seed. Across two seeds those records stay byte-identical.
But the seed also selects *which* principals receive accounts and access atoms,
so it changes the world's content, not just its labels. Account identifiers embed
the selected principal slot and change with the seed, and an access atom whose
subject is an account inherits that: in the shipped smoke blueprint, all twelve
principal-subject atom IDs held across seeds while two of the four
account-subject atom IDs moved.

The `--seed` flag on `generate-enterprise-agentic` and
`generate-contextual-access` is a different knob again. Those packs are pinned to
one universe, whose digest is identical across seeds. The seed varies which
agents, accounts, capabilities, and access atoms the cases are drawn over. What
does not move is the universe, the case count — twenty and ten respectively —
and the mix of case kinds.

| Family | What it measures | Runs over | How you reach it |
|---|---|---|---|
| Identity/access universe | Compiles the fixed world and its evaluator-only account-to-principal binding truth | your blueprint | `scaffold-`, `validate-`, and `compile-enterprise-access` |
| Directory/RBAC, ABAC, and ReBAC oracles | Birthright, intended, effective, and binding/lifecycle-gated final decision per cell, plus the derivation that produced each one | any universe, given a corpus config and overlays you author | Python: `synthworld.enterprise` |
| Identity fabric | Membership and role resolution, account binding and lifecycle, redundant grants, access outside birthright and intent, and privilege accumulation across ordered checkpoints | built-in reference pack | Python: `synthworld.enterprise.identity_fabric` |
| Enterprise agentic | Whether an agent action was within delegated authority, gate by gate, and whether retained evidence still reconstructs it at audit | the pinned reference universe only (digest-enforced) | `generate-enterprise-agentic`, `validate enterprise-agentic-trace`, `evaluate enterprise-agentic` |
| Contextual access | Whether the decision follows when the facts that justify access change and arrive late, twice, or out of order | pinned reference universe via the CLI; any universe via `generate_contextual_access_smoke` | `generate-contextual-access`, `validate contextual-access-trace`, `evaluate contextual-access` |
| Authority-change governance | Whether you can reconstruct why an authority change happened, under the policy in force at decision time | its own self-contained world — not the enterprise universe | Python: `synthworld.authority_governance` |
| Continuous assurance | Whether identity and authority drift is detected, classified, cleared, and not silently reopened over time | shipped reference sources | `generate-continuous-assurance`, `evaluate continuous-assurance` |
| Standards projections | SCIM, AuthZEN, and OpenFGA shapes; Shared Signals/CAEP is a mapping declaration that emits no enterprise events. Each ships a support matrix classifying every mapping `exact`, `approximated`, or `unsupported` | any universe, plus the kernel or truth each projection needs | Python: `synthworld.enterprise.projections` |

The contract packages are the normative documentation for this surface and
describe each family's schemas, budgets, and boundaries in full:
[enterprise identity/access](enterprise-identity-access-contract/README.md),
[contextual access](contextual-access-contract/README.md),
[authority governance](authority-governance-contract/README.md), and
[continuous assurance](continuous-assurance-contract/README.md). Each ships
generated JSON Schemas and examples, regenerated and checked by
`uv run python <package>/tools/generate_contract.py --check`.

### What the enterprise surface does not claim

- **Importing structure is not anonymisation.** Logical keys, counts, group and
  role structure, and access breadth can stay commercially sensitive even with no
  person rows present. Keep the source import and the 64-hex namespace salt
  private; `scaffold-enterprise-access` prints that warning after a successful
  write.
- **The public/evaluator split is a directory convention, not a custody
  boundary.** `compile-enterprise-access` takes one `--output`, and `public/` and
  `evaluator/` are sibling subdirectories beneath it, written with default file
  permissions. Nothing chmods the evaluator tree or offers it a separate
  destination. Keeping answer keys away from a model is your operational job.
- **The reference packs are conformance fixtures, not blind tests.** All four
  contract packages ship their evaluator answer key in `examples/` —
  `enterprise-identity-fabric-evaluator.json` and
  `enterprise-agentic-evaluator.json` under
  `enterprise-identity-access-contract/`, plus
  `contextual-access-evaluator.json`, `continuous-assurance-evaluator.json`, and
  `authority-governance-evaluator.json`. Treat every shipped reference pack's
  truth as public.
- **Tiers govern assurance cadence, not world scale.** Enterprise agentic and
  contextual access expose `smoke` only; identity fabric has no tier at all.
  Continuous assurance's `smoke`, `standard`, `longitudinal`, and `held_out`
  profiles repeat a fixed eight-template cycle — 8, 24, 48, and 24 cases — over
  the shipped source records. `held_out` additionally permutes template order,
  and the source record each case binds to is indexed by seed, `--risk-threshold`,
  cycle, and position, so case identities differ between seeds and risk
  thresholds while staying reproducible for any given configuration. `held_out`
  is a generation-profile name, not keyed concealment — see
  [EVALUATION_KEY_CUSTODY.md](EVALUATION_KEY_CUSTODY.md).
- **Not every family has a command line.** Identity fabric and authority-change
  governance are reachable only through the Python API; no terminal command
  generates or scores either, and identity fabric has no JSONL trace format.
- **Shared Signals/CAEP is a mapping declaration.** The enterprise projection
  declares its mappings and support matrix but emits no events and constructs no
  SET envelope; temporal emission is deferred. The additive contextual projection
  under `contextual-access-contract/` does emit event projections and selects the
  shipped temporal `1.2` tick contract — but every mapping it declares is
  classified `custom_profile` with a null `standardized_caep_event_type`, so
  these are versioned SynthWorld events, not standardized CAEP event types. SET
  construction, signing, transmission, and vendor ingestion remain external.
- **There is no aggregate score in any of these families.** Each metric carries
  its own numerator, denominator, support, and denominator meaning, so a weak
  dimension cannot be averaged away. Four of the five families also publish an
  explicit empty behaviour; authority-change governance does not — its metric
  model has no empty-behaviour field and requires `denominator > 0`, so an empty
  governance metric is unrepresentable rather than null-reported.
- **Standards are pinned, never "latest".** `standards-profile-ledger.json`
  records eleven external editions reviewed on 2026-08-04 and the versioned
  SynthWorld profile selected from each. Entries are classified across six
  categories — normative standard, government reference, test method,
  implementation model, community work, and research — so a final standard is
  never conflated with a draft or a research paper. The dated AIIM MCP interop
  snapshot is `community_work`/`draft` and supplies experimental scenario
  vocabulary only.
- **This surface is unreleased.** It sits under `[Unreleased]` in
  [CHANGELOG.md](CHANGELOG.md) and is not yet covered by a tagged release.

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
