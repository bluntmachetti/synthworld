# SynthWorld user guide

SynthWorld is a testing ground for identity and privacy systems. It creates
safely fictional test cases, lets your system process the public observations,
and then scores its answers against known truth.

You do not need to understand the internal schemas before choosing a use case.
Start with the outcome you want below.

## Choose your use case

| I want to... | What SynthWorld provides | Available in 0.8 |
|---|---|---|
| Create safe identities for a test, demo, or fixture | Connected fictional people, attributes, and planted relationships | Yes |
| Test a PII extractor or document model | Synthetic pages and exact character-span scoring | Yes |
| Test whether records are matched to the correct person | Conflicting records, known entity membership, and merge/split metrics | Yes |
| Test relationship inference | Public association evidence, positive relationships, and negative controls | Yes |
| Test breach-risk scoring | Provider-neutral breach observations and expected score bands | Yes |
| Explore privacy exposure or broker reappearance | Breach, broker, search, and social scenarios | Partial: generation and integrity metrics only |
| Test agents, IAM, RAG privacy, wallets, or disaster identity | Future benchmark packs | Planned |

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
This is the quickest way to inspect the identities, records, pages, and risk
cases before deciding whether to integrate the package.

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

## Run the four evaluation examples

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

## Use case 6: exposure scenarios

Use the exposure corpus for product fixtures involving breaches, search
collisions, broker listings, removal requests, and reappearance:

```bash
synthworld generate-corpus \
  --seed 20260719 \
  --persona-count 10 \
  --output exposures.json
```

This is currently a scenario-generation path. SynthWorld can report corpus
integrity metrics, but version 0.8 does not yet provide a unified evaluator for
broker-removal actions or longitudinal product behaviour.

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
Commands containing `answer`, and bundled evaluator artifacts such as
`generate-extraction` or `generate-connection-benchmark`, contain expected
answers. Keep them on the evaluator side.

SynthWorld creates fictional test data. It is not an anonymisation tool and
must not be used to impersonate, investigate, enrich, or target real people.

For exact field definitions, consult the
[`DATA_DICTIONARY.md`](DATA_DICTIONARY.md). For frozen reference scores, see
[`BENCHMARKS.md`](BENCHMARKS.md). Future use cases are labelled in the
[`ROADMAP.md`](ROADMAP.md).
