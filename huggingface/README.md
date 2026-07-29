---
license: apache-2.0
language:
- en
pretty_name: SynthWorld Frozen Benchmarks
tags:
- synthetic-data
- privacy
- pii-detection
- entity-resolution
- identity-graph
- ai-agents
- authorization
- benchmark
task_categories:
- token-classification
size_categories:
- n<1K
configs:
- config_name: personas
  default: true
  data_files:
  - split: golden
    path: viewer/personas.jsonl
- config_name: relationships
  data_files:
  - split: golden
    path: viewer/relationships.jsonl
- config_name: public_extraction_pages
  data_files:
  - split: golden
    path: viewer/public_extraction_pages.jsonl
- config_name: extraction_answers
  data_files:
  - split: golden
    path: viewer/extraction_answers.jsonl
- config_name: public_identity_records
  data_files:
  - split: golden
    path: viewer/public_identity_records.jsonl
- config_name: asteria_principals
  data_files:
  - split: golden
    path: frozen/asteria-agentic-v1/public/principals.jsonl
- config_name: asteria_resources
  data_files:
  - split: golden
    path: frozen/asteria-agentic-v1/public/resources.jsonl
- config_name: asteria_delegations
  data_files:
  - split: golden
    path: frozen/asteria-agentic-v1/public/public_delegations.jsonl
- config_name: asteria_authority_truth
  data_files:
  - split: golden
    path: frozen/asteria-agentic-v1/evaluator/authority_truth.jsonl
- config_name: asteria_cases
  data_files:
  - split: golden
    path: frozen/asteria-agentic-v1/evaluator/cases.jsonl
---

# SynthWorld Frozen Benchmarks

Deterministic, connected **synthetic identity graphs** and agent-authority
traces with ground-truth answer keys, for testing privacy, PII extraction,
entity resolution, exposure analysis, identity attribution, delegated
authority, temporal validity, and audit provenance — without collecting or
fabricating data about real people.

These artifacts are the frozen golden benchmarks of the
[SynthWorld generator](https://github.com/bluntmachetti/synthworld)
(`pip install idcognito-synthworld`, v0.9.0+). They are generated from seed
`20260719` and authenticated by SHA-256 manifests. Generator CI recreates the
artifacts byte-for-byte and fails on drift, so results remain tied to exact
benchmark bytes.

## Every record is unmistakably fake

Safety is mechanical and enforced by the generator's models and tests:

- every persisted object carries `synthetic: true`;
- emails use the reserved `example.test` domain;
- phones use a fictional `555-01xx` range;
- addresses use example-named streets in `Testville`, postal code `00000`,
  country `ZZ`;
- national identifiers carry a `SYN-` prefix with deliberately invalid
  checksums;
- agentic credentials contain opaque identifiers and validity metadata, never
  reusable secret material.

This dataset must never be used to impersonate, target, or investigate a
person. No real person's data was used.

## Authoritative data and viewer projections

`frozen/` contains the authoritative artifacts shipped by the Python package.
`viewer/` contains derived JSONL tables for convenient browsing. Viewer-created
Parquet files and the `viewer/` projections are not checksum authorities; use
the raw files under `frozen/` when reproducing or comparing scores.

The identity/privacy benchmark files retain their per-file SHA-256 values:

| File | SHA-256 |
|---|---|
| `frozen/golden-v1.json` | `8b75fcd932dbbe2d0ea94d034f8c546c6c3857d3c99669180222f807cf48755d` |
| `frozen/extraction-golden-v1.json` | `69bf567bf122ed7831f0963883b0524c3b9d991b5ef0f7a5b6b7ce69ee234e57` |
| `frozen/extraction-public-golden-v1.json` | `10632f000f8aeb8ccd8557476b18b940cfd35b91f7cb38dcf209269de987160e` |
| `frozen/extraction-answer-golden-v1.json` | `ffc6503df8cbb9d8f99161ee29324e8d0a0187901118e8eeaa590b49e7598f78` |
| `frozen/connection-golden-v1.json` | `044b52650039059b5841e0af9c512e2bbc7dbb089d43e465d43fda06889a8fe4` |
| `frozen/connection-public-golden-v1.json` | `fa896ae417f75d6fc4ac650ec26683a39b3994bc004c743fc1fcc71f605ff17e` |
| `frozen/risk-public-golden-v1.json` | `690c2fb081826f72970af1e729651819c3563d9aa590190d566af24424238b33` |
| `frozen/risk-answer-golden-v1.json` | `32479aa077887a63d31a4de3dfbc822f01f6622f09ea6dd6d2a87e3af3cb319e` |

## Asteria Agentic v1

Asteria is a small, inspectable procurement conformance world for agent
identity and delegated authority. It contains two organisations, four Asteria
departments, ten principals, three logical agents, three runtimes, four grants,
nine resources, 24 ordered events, and 11 positive and negative action cases.

The authoritative tree is:

```text
frozen/asteria-agentic-v1/
  public/       # input for the system under test
  evaluator/    # answer-key material used only after predictions exist
```

The public and evaluator roots are independently bound with the
`sha256-artifact-set-v1` convention:

| Tree | Artifact-set digest |
|---|---|
| `public/` | `9ef217b5d604f42a68b7c97596c550698293f1a44f402dbc3d39a2cef19c4594` |
| `evaluator/` | `3d856f39a5c34ca891ec61298a40ee5bfcb134feae5db7b8a20f6ce9078b2b3f` |

The public `manifest.json` and evaluator `checksums.json` are excluded from
their own root digests. Each root hashes the sorted relative path, a NUL byte,
and the raw SHA-256 digest of every listed base artifact. Both metadata files
also carry per-file hashes.

The answer key is deliberately public in this repository. The physical split
prevents accidental label leakage in an integration; it is not an anti-cheating
boundary. Competitive evaluation requires held-out private worlds.

### Use Asteria

Install v0.9.0 or later and export the frozen package:

The SynthWorld Python package requires Python 3.12 or newer; Python 3.11 and
earlier are not supported.

```bash
pip install idcognito-synthworld
synthworld generate-agentic --output asteria-agentic-v1
```

Give only `asteria-agentic-v1/public/` to the system being evaluated. It must
emit one nullable `ObservedActionTrace` JSON object for each action event. Then
score the JSONL trace locally:

```bash
synthworld validate agentic-trace --predictions observed-actions.jsonl
synthworld evaluate agentic \
  --predictions observed-actions.jsonl \
  --summary
```

The report keeps identity resolution, action-time authority, audit-time
temporal validity, least privilege, attribution, ownership, delegation-chain
integrity, provenance, reconstructability, policy version, and side effects as
separate metrics. There is no aggregate score that can hide a weak dimension.

See the
[complete Asteria guide](https://github.com/bluntmachetti/synthworld/blob/main/AGENTIC_BENCHMARK.md)
for the JSONL contract, replay semantics, runnable public-only baseline, and
Python API.

## Other benchmark families

- `golden-v1.json` contains ten connected personas, nine evidence-backed
  relationships, and scripted breach, broker, search, and social histories.
- `extraction-public-golden-v1.json` and
  `extraction-answer-golden-v1.json` separate 62 product-safe pages from their
  exact character-span answer keys. `extraction-golden-v1.json` is the joined
  evaluator convenience bundle.
- `connection-public-golden-v1.json` contains 18 opaque adversarial identity
  records; `connection-golden-v1.json` carries the entity and relationship
  truth.
- `risk-public-golden-v1.json` separates provider-neutral observations from
  the score, band, and factor truth in `risk-answer-golden-v1.json`.

## Public input and evaluator truth

Answer keys exist so evaluators can score predictions; a system that reads its
own answer key is not being evaluated. Give products and models only files
explicitly described as public. Join evaluator data after the system has
produced its predictions.

Because the golden answer keys are published, this separation is an API-hygiene
guarantee rather than a secrecy claim. The same split can be used with private
held-out worlds for adversarial or leaderboard evaluation.

## Quick start with the viewer tables

```python
from datasets import load_dataset

pages = load_dataset(
    "Bluntmachetti7/synthworld-benchmarks",
    "public_extraction_pages",
)
principals = load_dataset(
    "Bluntmachetti7/synthworld-benchmarks",
    "asteria_principals",
)

print(pages["golden"][0]["content"])
print(principals["golden"][0])
```

Download the authoritative Asteria event stream rather than a Viewer-derived
projection:

```python
from huggingface_hub import hf_hub_download

events_path = hf_hub_download(
    "Bluntmachetti7/synthworld-benchmarks",
    "frozen/asteria-agentic-v1/public/public_events.jsonl",
    repo_type="dataset",
)
print(events_path)
```

## Links

- Generator source: <https://github.com/bluntmachetti/synthworld>
- PyPI: <https://pypi.org/project/idcognito-synthworld/>
- User guide:
  <https://github.com/bluntmachetti/synthworld/blob/main/USER_GUIDE.md>
- Field and schema reference:
  <https://github.com/bluntmachetti/synthworld/blob/main/DATA_DICTIONARY.md>
- Baseline results:
  <https://github.com/bluntmachetti/synthworld/blob/main/BENCHMARKS.md>

Licensed under Apache-2.0. Copyright 2026 Redoubt Labs ltd.
