# Privacy and exposure

Use this guide for extraction, breach-risk, exposure, broker-lifecycle, and offline search-provider evaluation. SynthWorld supplies safely fictional public inputs and separate evaluator truth; it does not anonymize supplied real data or predict real-world harm.

## Exact-span extraction

Create product-safe pages with:

```bash
synthworld generate-public-extraction \
  --seed 20260719 \
  --persona-count 10 \
  --output extraction-input.json
```

Adapters return the versioned extraction prediction contract. The scorer reports span precision, recall, F1, overlap, and misses by data class. Use [`examples/evaluate_extraction.py`](../../examples/evaluate_extraction.py) for the smallest runnable adapter and [DATA_DICTIONARY.md](../../DATA_DICTIONARY.md) for the exact prediction schema.

## Breach-risk calibration

```bash
synthworld generate-risk-public \
  --seed 20260719 \
  --persona-count 10 \
  --output risk-input.json
```

Every public case receives a predicted band. Optional score or probability fields are scored only when supplied according to the task contract. The expected score is a deterministic reference index, not a probability or forecast.

## Exposure and broker lifecycle

```bash
synthworld generate-corpus \
  --seed 20260719 \
  --persona-count 10 \
  --output exposures.json
```

The exposure corpus covers deterministic breach, broker, search, and social scenarios. Broker-removal lifecycle evaluation is available through `synthworld evaluate broker`; broader longitudinal product behavior is tracked separately and should not be inferred from `generate-corpus`.

## Offline search-provider projection

`generate_search_projection` provides an offline public-results boundary for exercising search-consumer logic without a network dependency. It plants collisions, insufficient-evidence cases, syndicated copies, stale observations, missing snippets, and seed-dependent result order while keeping evaluator truth separate.

The search report keeps false accepts, false rejects, unwarranted decisions, coverage, distinct findings, stale acceptances, and difficulty support separate. It does not claim to reproduce a search engine's ranking algorithm.

## Boundary

Only artifacts explicitly documented as public belong on the product side. Annotated or evaluator bundles may contain expected results even when the same benchmark also provides a product-safe projection.

Use the documentation site's evaluation guide for the general integration sequence. For schemas, formulas, benchmark identities, and frozen reference values use [DATA_DICTIONARY.md](../../DATA_DICTIONARY.md) and [BENCHMARKS.md](../../BENCHMARKS.md).
