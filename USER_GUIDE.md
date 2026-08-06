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
Agentic scoring protocol `0.3.0` reports evidence completeness, exact match, and
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

## Use case 11: enterprise identity and access structure

Use this when you need a bounded, safely fictional enterprise identity/access universe —
tenants, organisational units, principals, unbound account slots, groups, roles,
authorization targets, permissions, and a frozen access-atom inventory — to test an IAM,
IGA, or authorization system against.

You author the *structure*; SynthWorld compiles the *universe*. It is not a directory
service, IGA workflow system, PDP, policy engine, or runtime enforcement component, and it
makes no network call at any point. The runtime dependencies are `pydantic`, `Faker`, and
`pyyaml`; there is no HTTP client in the package.

### Author, validate, compile

Three commands, in order:

```bash
synthworld scaffold-enterprise-access \
  --format yaml \
  --output private-enterprise.yaml

synthworld validate-enterprise-access --input private-enterprise.yaml

synthworld compile-enterprise-access \
  --input private-enterprise.yaml \
  --seed 20260804 \
  --output compiled-enterprise
```

The scaffold writes a working reference blueprint you edit in place. When you do not pass
`--id-namespace-salt`, it generates a fresh 256-bit salt with `secrets.token_hex(32)` and
writes it into the template. It also prints:

```text
Importing structure is not anonymisation; protect the source and namespace salt.
```

Take that literally. Logical keys, headcounts, group structure, role structure, and access
breadth can stay commercially sensitive even when the file contains no person rows.

Every compiled identifier is `uuid5(kind_namespace, blueprint_namespace ‖ logical-key
components)`, where `blueprint_namespace = uuid5(BLUEPRINT_NS, schema_version ‖ salt)`. The
salt and your logical keys are *both* load-bearing: neither alone determines an identifier,
and both are inputs to every identifier the compiler emits, account identifiers included.
Treat the blueprint as an operator-private document, not a shareable one.

`--format json` writes a single JSON envelope instead. `--format csv` writes a directory
holding a 20-file CSV bundle; `compile-enterprise-access` accepts that directory path, or a
`.zip` of it, as `--input`. On the scaffolded reference blueprint all formats compile to
identical bytes — but that equivalence is not a general guarantee, because the CSV reader
hardcodes `account_observations` and `direct_entitlements` to empty lists (see the limits
below). A YAML or JSON blueprint that uses either cannot be round-tripped through CSV.

### Validation returns every error at once

`validate-enterprise-access` exits `0` on a valid import and `1` otherwise, printing one
diagnostic per line to stderr in the form `<code> <file:row:column>: <message>`. Add
`--json` for the full `EnterpriseIdentityAccessValidationReportV1`. It does not stop at the
first problem. A blueprint whose only content is a `blueprint_key` set to an email address
produces all six of these at once:

```text
model_validation blueprint.blueprint_key: Value error, person_level_email_forbidden
model_validation blueprint.id_namespace_salt: Field required
model_validation blueprint.organisations: Field required
model_validation blueprint.tenants: Field required
model_validation directory_rbac_state: Field required
model_validation iam_universe_extension: Field required
```

`person_level_email_forbidden` is worth calling out: any logical key that looks like an
email address is rejected outright, because a logical key is the one field where a real
person's identifier tends to leak in from a directory export.

One caveat on staging. The CLI reconstructs its report from the import loader, so it stops
at whichever stage fails first — a parse error and a structural-reference error will not
appear in the same run. Call `validate_enterprise_identity_access()` directly if you want
the structural pass in isolation.

### What compilation writes

Compilation is deterministic from the saved import, the explicit seed, the schema versions,
and the compiler version. It prints a count and writes four files into two disjoint trees:

```text
Enterprise identity/access universe ready: 6 principals, 4 account slots, 16 access atoms
  -> compiled-enterprise

compiled-enterprise/
  public/
    identity-access-universe.json     # EnterpriseIdentityAccessUniverseV1
    manifest.json                     # visibility: "public"
  evaluator/
    canonical-binding-truth.json      # account_id -> principal_id
    manifest.json                     # visibility: "evaluator"
```

The public universe holds entity inventories and the frozen access-atom inventory. Every
identifier is an opaque UUIDv5 string, every label is a generated placeholder
(`Example Account 000001`), and every record carries `synthetic: true`. It contains neither
`id_namespace_salt` nor `blueprint_key` nor any logical key you authored.

`EnterpriseAccountV1` has no `principal_id`. Which principal owns an account is exactly the
linkage the public tree withholds, and it lives only in
`evaluator/canonical-binding-truth.json`. That file is a whole
`EnterpriseCanonicalBindingTruthV1` object — a `bindings` array plus the universe digest it
is bound to — not a bare list of pairs:

```json
{
  "bindings": [
    {"account_id": "…", "principal_id": "…", "synthetic": true}
  ],
  "identity_access_universe_digest": {
    "algorithm": "sha256", "synthetic": true, "value": "…"
  },
  "schema_version": "1.0.0",
  "synthetic": true
}
```

Write your loader against that shape. The split is physical, not a flag: there is no API
that loads both trees at once; each loader requires its directory to hold exactly its two
expected files, requires the manifest's declared visibility to match, and re-verifies path,
schema version, byte size and SHA-256 digest against the bytes on disk. Bytes that differ
from their own canonical JSON form are rejected.

### What the seed moves, and what it does not

At a fixed salt, tenant, organisation, unit, principal, group, role, authorization-target
and permission identifiers do not depend on the seed.

Account allocation *is* seed-driven — the seed ranks principal slots — and that choice
cascades. Compiling the scaffolded reference blueprint at the same salt under two seeds
changes `accounts` (2 of 4), `access_subjects` (2 of 10), `access_atoms` (2 of 16), and
`relationship_anchors` (2 of 16). Every changed record is one whose subject or entity is an
account, so an access-atom identifier is seed-stable only when its subject is a principal.

Adding an unrelated template does not remap existing identifiers. But generated
`display_label` values are positional over the canonical key order, so a template that sorts
ahead of existing ones renumbers their labels. Pin downstream tests to identifiers, never to
labels.

### Limits worth knowing before you author

- **Export is write-once.** `compile-enterprise-access` and `scaffold-enterprise-access`
  both refuse an existing output path. There is no `--force`.
- **Selectors are a closed three-member vocabulary** — `all`, `count`, `fraction`. A
  fraction must be pre-reduced, so `2/4` fails with `selector_fraction_not_reduced`.
- **Multiple tenants and organisations are supported; references between them are not.**
  Each requires at least one entry and has no upper bound, and a two-tenant blueprint
  compiles cleanly. What is rejected is any *reference* that leaves its silo — access
  declarations, memberships, group nesting, role assignments, group-role assignments, role
  hierarchy, and role grants each get their own `cross_tenant_*` diagnostic. You can model
  several independent silos in one blueprint; you cannot model federated access across them.
- **Access atoms must be globally unique.** Two rules declaring the same
  (subject, target, action) abort compilation with `duplicate_access_atom_declaration`.
- **CSV and ZIP cannot express everything.** `account_observations` and
  `direct_entitlements` have no CSV files and are hardcoded empty by the CSV reader.
- **The compiled universe carries no edges.** No memberships, group nesting, role
  assignments, role hierarchy, role grants, entitlements, or account bindings. The
  `directory_rbac_state` you author is validated for referential integrity and cross-tenant
  safety here, and is consumed downstream by the **`enterprise.rbac`** package only —
  nothing under `enterprise.abac` or `enterprise.rebac` reads it.
  `EnterpriseRelationshipAnchorV1` is an addressability stub whose fields are `anchor_id`,
  `entity_id`, `entity_kind`, `tenant_id`, and `synthetic`. It records that an entity is
  addressable, and carries no relation type and no edges.
- **Nothing enterprise-related is exported from the top-level `synthworld` package.**
  Import `synthworld.enterprise...` explicitly.

## Use case 12: projecting a compiled world to SCIM, OpenFGA, and AuthZEN

Use this when you need SynthWorld's enterprise data in the *shape* another standard uses —
to exercise an adapter, a mapping layer, or a fixture loader — and you want a written record
of what the conversion could not carry.

**These are pure, offline data conversions.** The package holds no SCIM client, no AuthZEN
HTTP client, no Shared Signals transmitter, and no OpenFGA writer or evaluator. Nothing here
contacts a service, exchanges a credential, or makes a policy decision.

They are also **shape-level projections, not wire-format documents**. The SCIM output has no
`schemas` URN array, no `meta`, no `externalId`; its fields are `user_id` / `user_name` /
`active`. The OpenFGA authorization model is a constant `OpenFgaAuthorizationModelV1` —
`schema_version: "1.1"` plus five fixed `type_definitions` strings — not a DSL document. You
will need an adapter before a real endpoint accepts any of it.

There is no CLI for this. Import from `synthworld.enterprise.projections`.

### SCIM

```python
from synthworld.enterprise.projections import project_scim, scim_projection_profile_v1

projection = project_scim(
    universe=universe,                        # EnterpriseIdentityAccessUniverseV1
    directory_rbac_kernel=kernel,             # EnterpriseDirectoryRbacKernelV1
    profile=scim_projection_profile_v1(snapshot_tick=0),
)
```

Both inputs are public artifacts. The kernel must bind the exact universe you pass, or the
call raises `scim_kernel_universe_digest_mismatch` — projections fail closed rather than
silently mixing worlds.

Four things to expect from the output:

- `roles` and `entitlements` are **always empty**, and `authorization_semantics` is the
  frozen literal `"none"`. The projection deliberately imports no authorization meaning.
- `user_name` is fabricated as `<account_id>@accounts.example.invalid`, using the reserved
  `.invalid` TLD.
- An account with no directory observation projects `active: false`. Missing observation
  fails closed to inactive.
- Only **accounts** become group members. A membership edge whose subject is a principal is
  skipped, and nested groups never appear as members of their parent. On the shipped
  reference pack every membership subject is a principal, so both projected groups come back
  with no members — correct behaviour, and why that fixture is a poor smoke test for a
  membership adapter.

### OpenFGA

```python
from synthworld.enterprise.authorization_common import AuthorizationSourceLayer
from synthworld.enterprise.projections import openfga_mapping_profile_v1, project_openfga

actual = project_openfga(
    universe=universe,
    rebac_truth=rebac_truth,                  # CompiledEnterpriseRebacTruthV1
    mapping_profile=openfga_mapping_profile_v1(
        source_layer=AuthorizationSourceLayer.ACTUAL,
    ),
)
```

One projection covers exactly one source layer, so seeing both takes two calls.

Two cautions. First, **the input is compiled truth**, not a public artifact —
`CompiledEnterpriseRebacTruthV1` is evaluator-side, so an OpenFGA projection is derived from
truth and is not automatically safe to hand to a system under test. Second, each emitted
tuple carries `native_snapshot_id`, `native_revision_id`, `native_valid_from_tick`, and
`native_valid_until_tick` as inert metadata that no OpenFGA runtime enforces.

### AuthZEN

```python
from synthworld.enterprise.projections import authzen_mapping_profile_v1, project_authzen

projection = project_authzen(
    universe=universe,
    corpus=corpus,                            # EnterpriseEvaluationCorpusV1
    request=corpus.access_requests[0],
    mapping_profile=authzen_mapping_profile_v1(),
)
```

One request per call — there is no batch or evaluations-endpoint shape.

The projection **embeds no expected decision**. That is what makes it safe to hand to a
system under test while the corpus's expected decision stays evaluator-side.

If your system under test returns a decision, record it as a separate observation.
Normalisation is deliberately lossy: only `allow` and `deny` normalise to a decision, while
`indeterminate`, `transport_error`, `timeout`, and `unavailable` normalise to `None` — and
the model *forces* `boolean_decision` to be `None` for those four. Supplying `False`
alongside a timeout raises `authzen_raw_outcome_boolean_mismatch`. A transport failure is not
a deny, and the schema refuses to let you record it as one.

### Every projection reports what it lost

Each call also compiles a support matrix: one row per exercised native feature, classified
`exact`, `approximated`, or `unsupported`, with a mandatory prose `semantic_delta` on every
non-exact row and a canonical mapping digest binding the set together.

```python
from synthworld.enterprise.projections import evaluate_projection_fidelity

for metric in evaluate_projection_fidelity(projection.support_matrix).metrics:
    print(metric.family, metric.name, metric.numerator, metric.denominator, metric.value)
```

There is no combined fidelity score, by design — the three rates are reported independently.
A single "fidelity" number would let a target that drops authorization semantics entirely
read as mostly fine.

### Shared Signals / CAEP is a declaration, not an emitter

`synthworld.enterprise.projections.shared_signals` publishes a mapping profile and a support
matrix, and nothing else. **There is no `project_*` function, no event model, and no SET
envelope is ever constructed.** The deferral is encoded in the schema itself:
`schedule_view_status` is the frozen literal `"deferred_to_pr7"` and
`emitted_event_projection` is `"deferred"` — no other value validates.

Two of its six declared mappings reach a real CAEP event type — `credential_change` exactly,
and `account_disabled` only approximately, with the recorded delta "Account disablement is
not necessarily a CAEP session revocation". Two more map onto SynthWorld-private URNs that no
CAEP receiver knows. The profile records which edition was reviewed; it is not evidence of a
working event emitter.

## Use case 13: enterprise authorization benchmarks

Use these when you want to score a system rather than fixture it — specifically, whether it
reaches the right authorization decision *and* can say why.

Three enterprise benchmarks have a command line — `generate-enterprise-agentic`,
`generate-contextual-access`, and `generate-continuous-assurance`. The directory/RBAC, ABAC,
ReBAC, identity-fabric, and authority-governance packs are Python API only.

### Run the enterprise-agentic smoke pack

This pack replays an agent overlay — agent accounts, runtimes, opaque credential handles,
capabilities, and human-to-agent delegations — over a fixed compiled access state, and
scores the immutable enterprise decision separately from seven downstream authority gates,
attribution, and audit evidence.

```bash
synthworld generate-enterprise-agentic \
  --tier smoke \
  --seed 20260804 \
  --output enterprise-agentic-world
```

```text
Enterprise-agentic smoke pack ready: 20 cases -> enterprise-agentic-world

enterprise-agentic-world/
  public/enterprise-agentic-input.json
  public/manifest.json
  evaluator/enterprise-agentic-evaluator.json
  evaluator/manifest.json
```

Give only `enterprise-agentic-world/public/` to the system under test — that keeps an
adapter from reading truth by accident. (It does *not* keep the answers secret; see "The
reference packs are not blind" below.) That tree does not contain `expected_decision`,
`failure_reasons`, `case_labels`, `canonical_binding_truth`, `reconstructable_at_audit`, or
the compiled access state. Credential records appear as `opaque_handle` identifiers; no
`secret` or `token` field exists in either tree.

`--tier` accepts `smoke` and nothing else. `EnterpriseAgenticTier` has exactly one member,
so no other tier is representable without a schema change.

### Check the shape before you score

```bash
synthworld validate enterprise-agentic-trace \
  --predictions predictions/enterprise-agentic.jsonl \
  --benchmark-root enterprise-agentic-world
```

This reads only the public tree — public case ids and the public benchmark digest, never
truth — so you can iterate on an adapter without the evaluator bundle at hand. It reports
every bad row at once with line numbers. The codes it emits are `invalid_row`,
`duplicate_case_id`, `benchmark_digest_mismatch`, `unexpected_case_id`, and `missing_case_id`.

Each JSONL line is one `EnterpriseAgenticTraceRowV1`, carrying `enterprise_decision`, the
seven `gates`, `final_decision`, `failure_reasons`, the four attribution ids, `evidence_refs`,
and `reconstructable_at_audit`.

Scoring is strict-inventory: every declared case must appear exactly once. Partial
submissions are rejected rather than partially scored.

### Evaluate a prediction

```bash
synthworld evaluate enterprise-agentic \
  --predictions predictions/enterprise-agentic.jsonl \
  --benchmark-root enterprise-agentic-world \
  --summary
```

`--benchmark-root` is required for this task; omit `--summary` for the complete JSON report.

For the shipped `Enterprise decision only` baseline — a system that reads the enterprise
decision correctly and then treats every downstream agent gate as satisfied —
`enterprise_decision_accuracy` is 1.0000 while `final_decision_accuracy` and
`failure_reason_exact_match` are both 0.3000.

That gap is the whole point. The authority model is deliberately non-unioning: the final
decision allows only when the enterprise cell allows **and** every applicable subject,
tenant, agent-account, runtime, credential, capability, and delegation gate passes. There is
no path by which a human owner's authority rescues an agent denial, so a product cannot hide
an enterprise denial behind a runtime failure or the reverse.

Note the differing denominators. `delegation_gate_accuracy` has `n=10` because delegation is
`not_applicable` for the ten `agent_as_principal` cases, while the other six gates have
`n=20`. Every metric states its own denominator and denominator meaning, and there is **no
aggregate agentic score**.

### Scoring the directory/RBAC oracle from Python

The bounded authorization oracles — directory/RBAC, ABAC, ReBAC, and the composed access
state — have **no CLI at all**. Compile truth and score a prediction in process:

```python
from synthworld.enterprise import (
    compile_enterprise_directory_rbac_truth,
    evaluate_enterprise_directory_rbac,
)
from synthworld.enterprise.rbac import perfect_enterprise_directory_rbac_prediction
from synthworld.enterprise.rbac.reference import reference_enterprise_rbac_inputs

reference = reference_enterprise_rbac_inputs()
truth = compile_enterprise_directory_rbac_truth(
    universe=reference.universe_result.public_universe,
    canonical_binding_truth=reference.universe_result.evaluator_canonical_binding_truth,
    corpus=reference.corpus_result.public_corpus,
    directory_rbac_kernel=reference.kernel,
    session_state=reference.session_state,
    directory_rbac_intent=reference.intent,
)

report = evaluate_enterprise_directory_rbac(
    truth=truth,
    predictions=perfect_enterprise_directory_rbac_prediction(truth),
)
```

Substitute your own system's output for `perfect_…` — that function exists to prove the
scorer is satisfiable and to give you the exact prediction shape to fill in. Unknown
prediction ids are rejected; *missing* predictions score as incorrect rather than erroring.

**Read the metric families before reading the numbers.** Five of the metrics do not score
your prediction at all — `sprawl/effective_outside_intent_rate`,
`sprawl/missing_intended_access_rate`,
`birthright_breadth/effective_outside_birthright_rate`,
`redundancy/redundant_derivation_cell_rate`, and
`accumulation/privilege_accumulation_subject_rate` are computed from the compiled truth
alone. They describe how much excess access the *world* contains, not how well a system
found it.

There is deliberately no aggregate. The scorer's own docstring says so: *score independent
semantic families; deliberately emit no aggregate.*

### The identity-fabric pack is Python-only

The identity-fabric benchmark scores membership, role resolution, account
binding/lifecycle, entitlement, birthright, exception, intended-vs-effective-vs-final
access, redundancy, sprawl, and cross-checkpoint privilege accumulation over at least two
ordered immutable checkpoints.

```python
from synthworld.enterprise import evaluate_enterprise_identity_fabric
from synthworld.enterprise.identity_fabric.metrics import (
    perfect_enterprise_identity_fabric_prediction,
)
from synthworld.enterprise.identity_fabric.reference import (
    reference_enterprise_identity_fabric,
)

reference = reference_enterprise_identity_fabric()
report = evaluate_enterprise_identity_fabric(
    artifacts=reference.evaluator,
    predictions=perfect_enterprise_identity_fabric_prediction(reference.evaluator),
)
```

Two gaps to plan around. There is **no CLI subcommand** for this pack, and there is **no
JSONL trace format and no shape validator** — predictions must be constructed as
`EnterpriseIdentityFabricPredictionV1` in Python. The agentic pack has both; this one does
not.

### Limits, stated plainly

**The reference packs are conformance fixtures, not statistical benchmarks.** The
identity-fabric pack has 19 evaluation cells *per checkpoint* over two checkpoints; the
agentic pack is exactly 20 cases, one per case kind, so every gate metric has `n <= 20`. A
1-of-1 or 3-of-3 slice is not a rate.

**The reference packs are not blind, and re-seeding does not make them blind.** Three facts
to plan around:

1. `synthworld generate-enterprise-agentic --tier smoke --seed 20260804` reproduces the
   checked-in `enterprise-identity-access-contract/examples/` files byte-for-byte. Your
   "fresh" pack *is* the shipped fixture.
2. Changing the seed does not re-sample the world or the answers. The compiled `access`
   block — universe, corpus, both kernels, intents, states, evaluation profile, and
   composition — is byte-identical across seeds. The overlay is not byte-identical, but its
   counts are unchanged (6 agent accounts, 6 runtimes, 10 credentials, 8 capabilities, 11
   delegations, 24 events, 20 cases) and every case kind keeps the same
   `expected_decision`. What moves is case ids, a subset of overlay and event identifiers,
   and the digests. The seed selects which principal plays the primary agent and rotates
   part of the identifier namespace — it is not a re-randomisation knob.
3. The identity-fabric pack takes no seed at all, and its reference builder output is
   byte-identical to the checked-in public and evaluator files.

So for these two packs the answer key is in the repository regardless of what you pass on
the command line. The public/evaluator split is still worth honouring — it stops an adapter
reading truth by accident, and for a universe you compile from your *own* blueprint the
account-to-principal binding really is withheld — but it is not secrecy here. Treat a
perfect score on the reference packs as evidence that an adapter conforms, never as
evidence that a system generalises.

**Nothing here decides or enforces anything.** These packs perform no network call,
credential exchange, model execution, PDP decision, runtime enforcement, containment, or
vendor configuration.

For the contract-level description of these families — schemas, examples, and the pinned
standards ledger — see
[`enterprise-identity-access-contract/README.md`](enterprise-identity-access-contract/README.md).

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

### Enterprise trees

The enterprise commands follow the same rule with two additions.

`compile-enterprise-access`, `generate-enterprise-agentic`, and the identity-fabric exporter
each write a `public/` tree and an `evaluator/` tree. Ship the `public/` tree; keep
`evaluator/` on the evaluator side. `evaluator/canonical-binding-truth.json` is the
account-to-principal linkage the public universe deliberately withholds, and the agentic and
identity-fabric evaluator bundles hold expected decisions, failure reasons, and case labels.
For the two shipped reference packs this separation is hygiene rather than secrecy — their
evaluator bundles are checked into `enterprise-identity-access-contract/examples/`.

Separately, the blueprint you author is neither public nor evaluator — it is
operator-private. It carries your logical keys and the 256-bit `id_namespace_salt`, and
every compiled identifier is derived from both. Neither the salt nor any logical key appears
in the compiled artifacts. Do not distribute the blueprint alongside them.

One projection is the exception to the "public in, public out" reading: `project_openfga`
consumes `CompiledEnterpriseRebacTruthV1`, which is evaluator-side. An OpenFGA projection is
derived from truth and is not automatically a public artifact.

For exact field definitions, consult the
[`DATA_DICTIONARY.md`](DATA_DICTIONARY.md). For frozen reference scores, see
[`BENCHMARKS.md`](BENCHMARKS.md). Future use cases are labelled in the
[`ROADMAP.md`](ROADMAP.md).
