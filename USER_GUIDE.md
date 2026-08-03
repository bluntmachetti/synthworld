# SynthWorld user guide

SynthWorld is a testing ground for identity and privacy systems. It creates
safely fictional test cases, lets your system process the public observations,
and then scores its answers against known truth.

You do not need to understand the internal schemas before choosing a use case.
Start with the outcome you want below.

## Choose your use case

| I want to... | What SynthWorld provides | Available in 0.9 |
|---|---|---|
| Create safe identities for a test, demo, or fixture | Connected fictional people, attributes, and planted relationships | Yes |
| Test a PII extractor or document model | Synthetic pages and exact character-span scoring | Yes |
| Test whether records are matched to the correct person | Conflicting records, known entity membership, and merge/split metrics | Yes |
| Test relationship inference | Public association evidence, positive relationships, and negative controls | Yes |
| Test breach-risk scoring | Provider-neutral breach observations and expected score bands | Yes |
| Test agent identity and delegated authority | Ordered Asteria actions with separate temporal, authority, attribution, and provenance truth | Yes |
| Explore privacy exposure or broker reappearance | Breach, broker, search, and social scenarios | Partial: generation and integrity metrics only |
| Test broader IAM, RAG privacy, wallets, or disaster identity | Future benchmark packs | Planned |

## The three-part workflow

```text
SynthWorld creates public test data
                  |
                  v
        your system or model
                  |
                  v
        prediction JSON files
                  |
                  v
SynthWorld compares predictions with separate truth
```

Three terms appear throughout the project:

- **Public input** is the safe test data your system is allowed to see.
- **Prediction** is your system's answer in a small, task-specific JSON shape.
- **Answer key** is the expected result. Keep it on the evaluator side and do
  not pass it to the system being tested.

A **seed** is simply the number that makes a generated benchmark repeatable.
Use the same seed and persona count when generating input and scoring output.

## Try SynthWorld without installing it

The frozen benchmarks are browsable as tables in the
[SynthWorld dataset on Hugging Face](https://huggingface.co/datasets/Bluntmachetti7/synthworld-benchmarks).
This is the quickest way to inspect identities, records, pages, risk cases,
and Asteria principals, resources, delegations, and evaluator truth before
deciding whether to integrate the package. For Asteria, download
`frozen/asteria-agentic-v1/public/public_events.jsonl` when you need the
authoritative ordered trace; Dataset Viewer tables are browsing conveniences.

## Install and create your first world

SynthWorld requires Python 3.12 or newer.

```bash
pip install idcognito-synthworld
synthworld generate --seed 20260719 --persona-count 10 --output world.json
```

`world.json` contains ten fictional personas plus planted relationships and
supporting evidence. Use it when you need stable identity fixtures for a test,
demo, graph import, or product prototype. Changing the seed creates a different
repeatable world.

## Run the five evaluation examples

From a clone of this repository:

```bash
uv sync --locked --all-groups
uv run python examples/evaluate_all.py --predictions-dir predictions
```

The walkthrough uses deliberately simple rules over public data only. It prints
a score for every supported evaluation task and writes:

```text
predictions/
  extraction.json
  entity-resolution.json
  relationship.json
  risk.json
  agentic.jsonl
```

Each file is valid input to the evaluation CLI. For example:

```bash
synthworld evaluate extraction \
  --predictions predictions/extraction.json \
  --seed 20260719 \
  --persona-count 10 \
  --summary
```

Replace one rule at a time with a call to your own model, service, or product.
Keep the code that creates the prediction model: it is the adapter between your
system's native output and SynthWorld's scorer.

## Use case 1: safe connected identity fixtures

Use this when independent fake rows are not enough—for example, when a demo
needs people who share addresses, employers, schools, or evidence-backed
relationships.

```bash
synthworld generate \
  --seed 20260719 \
  --persona-count 25 \
  --output world.json
```

The result contains fictional identity data and known relationships. This path
generates a fixture; it does not evaluate a system.

All records retain `synthetic: true`. Emails use reserved domains, phone
numbers use a fictional range, addresses are obvious examples, and national
identifiers are deliberately invalid. Do not remove those safeguards.

**Scope.** This world is a deterministic smoke surface, not a transfer surface.
Its identifiers embed the persona ordinal — `persona-0003` yields
`synth_sian_cox_0003@example.test` — its relationship graph is a path, and
changing the seed changes values but not structure. That is ideal for fixtures,
demos and CI, and unsuitable for judging whether a system will work on real data.
It also means that if you build records where several rows describe one persona,
the ordinal becomes an answer key in a public field. See
[the scope note in the README](README.md#the-core-identity-world-is-a-smoke-surface).

## Use case 2: PII extraction

Use this to test whether a regex, NLP model, LLM, or document pipeline finds
the correct PII without highlighting unrelated text.

Create product-safe pages:

```bash
synthworld generate-public-extraction \
  --seed 20260719 \
  --persona-count 10 \
  --output extraction-input.json
```

Your adapter should return one prediction per page:

```json
{
  "schema_version": "0.1.0",
  "predictions": [
    {
      "source_type": "breach",
      "source_record_id": "breach-0001-01",
      "spans": [
        {"data_class": "email", "start": 65, "end": 100}
      ]
    }
  ]
}
```

The positions use Python-style character offsets: `start` is included and
`end` is excluded. The scorer reports span precision, recall, F1, overlap, and
misses by data class. See
[`examples/evaluate_extraction.py`](examples/evaluate_extraction.py) for the
smallest complete adapter.

## Use case 3: entity resolution

Use this to test whether records with misspellings, aliases, common names,
Unicode differences, twins, or maiden names are assigned to the right entity.

The public side contains opaque records. Your system must put every record in
exactly one cluster, including single-record clusters:

```json
{
  "schema_version": "0.1.0",
  "clusters": [
    ["record-uuid-a", "record-uuid-b"],
    ["record-uuid-c"]
  ]
}
```

The walkthrough's exact-identifier matcher shows how to build a complete
partition using only public attributes. The report includes pairwise and
B-cubed scores plus false merges and false splits for each adversarial case.

## Use case 4: relationship inference

Use this to test whether a system infers a relationship only when public
evidence supports it. The corpus includes unilateral associations specifically
to catch systems that infer too much from one weak signal.

```bash
synthworld generate-public-connections \
  --seed 20260719 \
  --persona-count 10 \
  --output relationship-input.json
```

A prediction names both public records, the relationship kind, and any public
association records used as evidence:

```json
{
  "schema_version": "0.1.0",
  "edges": [
    {
      "source_record_id": "record-uuid-a",
      "target_record_id": "record-uuid-b",
      "kind": "neighbor",
      "evidence_association_ids": ["association-uuid-a", "association-uuid-b"]
    }
  ]
}
```

The report separates edge quality from citation quality, so a correct
relationship with unsupported evidence is still visible.

## Use case 5: breach-risk calibration

Use this when a product turns breach observations into a risk band, numerical
score, or probability distribution.

```bash
synthworld generate-risk-public \
  --seed 20260719 \
  --persona-count 10 \
  --output risk-input.json
```

Every public case must receive a band. Scores and probabilities are optional,
but if supplied they must be supplied for every case:

```json
{
  "schema_version": "0.1.0",
  "cases": [
    {
      "case_id": "case-uuid",
      "band": "moderate",
      "score": 42
    }
  ]
}
```

The scorer reports band accuracy, macro F1, average band distance, and—when
provided—score error and probability quality. The expected score is a
documented deterministic index, not a probability or forecast.

## Use case 6: agent identity and delegated authority

Use Asteria Agentic v1 to test whether a system can distinguish the accountable
principal, logical agent, concrete runtime, credential subject, and publicly
attributed actor—and decide whether the action was within delegated authority
at the time it occurred.

Export the frozen public and evaluator trees:

```bash
synthworld generate-agentic --output asteria-agentic-v1
```

Start with these public files:

- `public/manifest.json` identifies the world, schema, seed, files, and public
  artifact-set digest;
- `public/organisation.json` and the principal, agent, runtime, resource,
  credential, and delegation JSONL files describe the starting identities and
  bindings;
- `public/public_events.jsonl` is the ordered event stream;
- `public/scenarios/procurement-delegation.json` identifies the action and audit
  events to evaluate;
- `public/tool_schemas/` describes the available procurement operations.

Inspect just the attempted actions with:

```bash
jq -c 'select(.payload.event_type == "action_attempted") | \
  {event_id: .id, timestamp: .occurred_at, attempt: .payload.attempt}' \
  asteria-agentic-v1/public/public_events.jsonl
```

Give only `asteria-agentic-v1/public/` to the system under test. For every
action event, the adapter should resolve the claimed identity roles, evaluate
authority at action time and audit time, and retain the supporting delegation,
credential, runtime, and policy references. It must emit one nullable
`ObservedActionTrace` JSON object per action in a JSONL file.

The all-task example contains a deliberately flawed but useful public-only
adapter. It evaluates every action against the final audit state, making the
temporal error visible in the resulting metrics:

```bash
uv run python examples/evaluate_all.py --predictions-dir predictions
```

Replace `current_state_agentic_trace` in that example with your own system and
keep the trace serializer. Then score the resulting file against the packaged
truth:

```bash
synthworld validate agentic-trace --predictions predictions/agentic.jsonl
```

Check the shape first. This needs no answer key, reports every bad row at once with
line numbers, and exits non-zero on anything `evaluate agentic` would reject — so you
can iterate on an adapter without the evaluator bundle. Then score it:

```bash
synthworld evaluate agentic \
  --predictions predictions/agentic.jsonl \
  --summary
```

The report separates identity role resolution, action-time allow/deny quality,
audit-time temporal validity, delegation-chain integrity, attribution,
accountable ownership, retained evidence, reconstructability, and side effects.
Agentic scoring protocol `0.4.0` reports evidence completeness, exact match, and
micro precision separately: missing references lower completeness, while
fabricated extras can preserve completeness but lower exact match and precision.
Returning the correct decision does not compensate for missing or fabricated
provenance. A score below one is expected for the example baseline: it
intentionally proves that evaluating historical actions from final state is
not replay. See [AGENTIC_BENCHMARK.md](AGENTIC_BENCHMARK.md) for the complete
JSONL contract, replay rules, baselines, Python API, and checksum procedure.

The reusable contracts can assemble additional worlds, but v1 does not yet
include a high-level custom-world/profile generator or authoring UI. The builder
rejects malformed runtime, delegation, credential, actor, and accountable-owner
joins before truth generation while preserving truthful unauthorized actions as
negative cases.

## Use case 7: exposure scenarios

Use the exposure corpus for product fixtures involving breaches, search
collisions, broker listings, removal requests, and reappearance:

```bash
synthworld generate-corpus \
  --seed 20260719 \
  --persona-count 10 \
  --output exposures.json
```

This is currently a scenario-generation path. SynthWorld can report corpus
integrity metrics, but version 0.9 does not yet provide a unified evaluator for
broker-removal actions or longitudinal product behaviour.

## Use case 8: households and workplaces

Use this when the core world is too thin to judge a system on — when you need
overlapping households, shared workplaces and schools, real graph structure, and
identifiers that do not hand back the answer.

```bash
synthworld generate-households \
  --seed 20260731 \
  --person-count 100 \
  --community-count 4 \
  --output households/
```

It writes `world.json` and `manifest.json`. The manifest keeps three separable
things apart: **benchmark identity** decides the artifact, **build provenance**
records the environment that produced it, and **semantic invariants** hold across
environments even when bytes do not. It also carries a checksum of the world bytes,
so a manifest cannot be paired with a world it does not describe.

Generation **fails** rather than emitting a world that misses its declared shape.
The floors are part of the configuration, and they are checked against the measured
world rather than against the request that produced it:

```bash
# one community collapses the graph into a single component, so this exits 1
synthworld generate-households --seed 1 --community-count 1 --output /tmp/rejected
```

Why it differs from the core world, measured on 100 people across three seeds:

| | core identity world | households_and_workplaces |
|---|---|---|
| components | 1 | 20-21 |
| cycle rank | 0 | 65-77 |
| isolated controls | 0 | 6 |
| distinct degrees | 2 | 9-10 |
| identifiers | embed the persona ordinal | derived from content and a keyed hash |
| seeds | change values only | change memberships and structure |

Household members share an address but **not** a surname. Only a household's
surname core is family, so the remaining co-residents share an address with people
they have no relationship to — a resolver that merges on address is wrong about
them, which is the negative control that makes address evidence worth testing.

### Generation cost

Measured with `examples/measure_households_cost.py`, which prints the interpreter
and platform beside the figures so you can tell whether they apply to you. Three
timed repeats after a discarded warm-up, on Python 3.12.12, Linux x86-64,
glibc 2.43:

| people | runtime (median) | peak Python allocation |
|---|---|---|
| 100 (standard) | 0.046 s | 1.1 MiB |
| 500 | 0.287 s | 12.3 MiB |
| 2000 (config ceiling) | 2.003 s | 116.6 MiB |

```bash
uv run python examples/measure_households_cost.py --person-count 100 --repeats 5
```

Two caveats. Peak memory is `tracemalloc`, so it counts Python allocations rather
than resident set size — it understates the real footprint and excludes the
interpreter. And cost grows faster than the population: memory rises about 100x
between 100 and 2000 people while the population rises 20x, because relationship
construction holds membership groups for the whole world. The `person_count`
ceiling of 2000 is a configuration limit, not a measured cliff.

## Use case 9: identity-resolution ambiguity

Use this when you need to know whether a resolver actually resolves, rather than
whether it can follow an exact join.

A resolver scored pairwise F1 **1.0** on the 18-record entity-resolution pack. A
one-factor mutation matrix then broke it four ways on the same data: unrelated
people sharing a phone were merged, people sharing an employer and address were
merged, stale records for one person were split, and Unicode name variants were
split. **A perfect aggregate score on that pack is not evidence of real-world
transfer**, and this pack exists because of it.

```python
from synthworld.ambiguity_serialization import load_golden_ambiguity_benchmark

benchmark = load_golden_ambiguity_benchmark()
records = benchmark.public.corpus.identity_records   # no truth of any kind
```

### Two truths, kept apart

Canonical entity membership says who someone **is**. Pair disposition says what the
public record pair **justifies**. They disagree deliberately: the pack contains
pairs that are the same person where the evidence supports only `insufficient`, and
pairs that are different people under the same disposition.

A system may answer `merge`, `separate`, or `insufficient`. Abstention is a
first-class answer, not a failure to answer. The public task and both truths are
serialized as three separate artifacts so a consumer can hold the public corpus
without either truth.

### Score complete partitions before projecting pairs

A cluster-producing resolver must submit every public record exactly once through
the existing `EntityResolutionPrediction` contract. Score that complete partition
directly with `evaluate_ambiguity_memberships`, supplying the public task and the
separately loaded `MembershipTruth`. This channel reports pairwise and B-cubed
precision, recall, and F1 over all within- and cross-scenario record pairs. Every
metric carries its numerator, denominator, and denominator definition.

Only after the partition is validated, use
`derive_ambiguity_pair_predictions(prediction, public=...)` to derive decisions for
the public `pairs_to_decide`. This function consumes no truth: records in one
cluster become `merge`, and records in different clusters become `separate`. That
is a forced partition interpretation, so it can never express `insufficient`.
Score those decisions separately with `evaluate_ambiguity_dispositions`, supplying
only `DispositionTruth`. Do not reconstruct the complete partition from the
fifteen selected pairs; a false merge between scenarios may be absent from that
projection while remaining visible in the raw partition metrics.

### The report has no aggregate score

That is the point. One number is what let a broken resolver read as perfect, so the
report gives you:

- **false merges and false splits, counted apart** — a false merge attaches one
  person's records to another, a false split leaves someone unresolved, and a single
  F1 trades them off silently;
- **unwarranted decisions** — deciding a pair the evidence cannot settle is not a
  wrong answer, it is an unjustified one;
- **coverage beside precision** — a system that abstains everywhere would otherwise
  score perfectly;
- **pairwise and B-cubed membership metrics** over the complete submitted partition,
  because they weight differently and either alone hides what the other shows;
- **per-scenario support with a machine-readable low-support flag.**

### Reference baselines

None of them resolves the pack, and a CI gate fails if one ever does:

| baseline | coverage | precision | false merge | false split | unwarranted |
|---|---|---|---|---|---|
| exact strong-identifier | 1.00 | 0.533 | 3 | 1 | 3 |
| normalised name or address | 1.00 | 0.267 | 5 | 3 | 3 |
| precision-first (abstains) | 0.73 | 0.727 | 1 | 1 | 1 |

### Limits, stated plainly

The canonical pack carries **one pair per scenario**, so every slice is flagged
low-support. It is a conformance fixture — like Asteria Agentic v1 — not a
statistical benchmark, and a 1-of-1 slice is not a rate.

Seed variants raise the variety but not the support:
`generate_ambiguity_variant(seed=...)` preserves declared prevalence while changing
surface values and, for five of the fifteen scenarios, which attribute carries the
case. The other ten are defined by their attribute — `recycled_phone` is about a
phone, and a one-option Unicode choice is not structural variation — so for those a
variant changes values only. The seed-selected choices are available separately
through `ambiguity_variant_metadata(seed=...)`; they are evaluator metadata and are
not added to the public task. Seeds 0 through 99 are the documented correlated
robustness sweep, not 100 independent observations.

## Use case 10: search-provider input without the answer key

Use this when you need to exercise a product's search-provider path offline — at
the same trust boundary a live SERP integration has, and without a paid provider,
network access, scraped results or real-person data.

**This emulates a data boundary and a set of controlled failure modes. It does not
model any search engine's ranking algorithm**, and a system that scores well here
has been shown to handle the shapes that break consumers — not to rank well.

```python
from synthworld.search_generator import generate_search_projection

projection = generate_search_projection(seed=20260731)
for page in projection.responses:          # rank, url, title, snippet only
    ...
```

### The public half rejects truth, it does not merely omit it

`PublicSearchResult` and `PublicSearchResponse` forbid extra fields. An adapter that
tries to attach `match_kind`, `actual_persona_id`, a relevance label or a scenario
name gets a validation error rather than a passing test and a silent oracle. The
worked adapter takes a public response and cannot see truth at all — the signature
is the guarantee, because an adapter is exactly where a truth field gets added by
someone being helpful.

Truth lives in a separate bundle, bound to the public half by a checksum so a report
cannot be paired with a projection it did not score.

### Controlled failure modes, all planted deliberately

True, false and insufficient-evidence results in one query; literal same-name
collisions; rank and order that change with the seed while the planted set does not;
three-way syndication of one source; missing and truncated snippets; noise; stale
observations; both Unicode and transliterated spellings of the **same** identity;
and a reported total larger than any page serves.

### Scoring, and what it refuses to hide

```python
from synthworld.search_metrics import ResultDecision, ResultJudgement, evaluate_search_judgements

report = evaluate_search_judgements(judgements, truth=projection.truth)
```

Truth is read here and nowhere earlier. The report separates:

- **false accepts from false rejects** — accepting a stranger's record attaches
  their exposure to a person; rejecting a real one leaves exposure unfound. A single
  score trades them silently;
- **unwarranted decisions** — deciding a result the public text cannot settle is not
  a wrong answer, it is an unjustified one;
- **coverage beside precision** — abstaining everywhere would otherwise look perfect;
- **distinct findings from accepted results** — three aggregator copies of one source
  are one finding, and a consumer counting them separately overstates exposure
  threefold;
- **stale acceptances** and **errors by difficulty, beside that tier's support** —
  which cases a system fails matters more than how many, and raw counts answer the
  wrong question. The accept-everything baseline on seed 1 errs 18 times at
  difficulty 1 and 12 times at difficulty 3, which reads as though tier 1 were the
  problem; tier 1 holds 42 results and tier 3 holds 12, so the rates are 0.43 and
  1.00 — complete failure on the hardest tier, ranked as the milder one. Tiers with
  no errors are listed too, because a missing row is indistinguishable from a tier
  that is not there.

### Reference baselines

None scores cleanly, on any seed, and CI fails if one ever does:

| policy | coverage | false accept | false reject | unwarranted | findings/accepted |
|---|---|---|---|---|---|
| accept everything | 1.00 | 24 | 0 | 6 | 57/72 |
| exact name in title | 1.00 | 3 | 21 | 6 | 21/27 |
| folded name, abstains without a snippet | 0.93 | 5 | 7 | 1 | 28/40 |

Accepting everything achieves perfect recall and attaches every collision. Exact
matching fails the transliterated spelling of the same person — which is why both
spellings are generated. Normalising and declining without corroboration trades
coverage for precision, which is the choice the projection exists to make visible.

## Reading evaluation results

Use `--summary` for the headline metrics and omit it for the complete JSON
report:

```bash
synthworld evaluate risk --predictions predictions/risk.json --summary
synthworld evaluate risk --predictions predictions/risk.json > report.json
```

The full report records the seed, benchmark version, scoring version, artifact
checksums, metrics, and failure slices. A `null` metric means the submitted
predictions did not make that metric meaningful—for example, precision when no
positive result was predicted.

## Safety boundary

Only inputs explicitly named `public` should be sent to a product or model.
Commands containing `answer`, the Asteria `evaluator/` tree, and bundled evaluator artifacts such as
`generate-extraction` or `generate-connection-benchmark`, contain expected
answers. Keep them on the evaluator side.

SynthWorld creates fictional test data. It is not an anonymisation tool and
must not be used to impersonate, investigate, enrich, or target real people.

For exact field definitions, consult the
[`DATA_DICTIONARY.md`](DATA_DICTIONARY.md). For frozen reference scores, see
[`BENCHMARKS.md`](BENCHMARKS.md). Future use cases are labelled in the
[`ROADMAP.md`](ROADMAP.md).
