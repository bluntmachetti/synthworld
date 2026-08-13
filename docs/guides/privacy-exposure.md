# Privacy and exposure

Use this guide for extraction, breach-risk, exposure, broker-lifecycle, and offline search-provider evaluation. SynthWorld supplies safely fictional public inputs and separate evaluator truth; it does not anonymize supplied real data or predict real-world harm.

**Exact-span extraction.** Create product-safe pages with:

```bash
synthworld generate-public-extraction \
  --seed 20260719 \
  --persona-count 10 \
  --output extraction-input.json
```

Adapters return the versioned extraction prediction contract. The scorer reports span precision, recall, F1, overlap, and misses by data class. See [`examples/evaluate_extraction.py`](../../examples/evaluate_extraction.py) and [DATA_DICTIONARY.md](../../DATA_DICTIONARY.md).

**Breach-risk calibration.** Create product-safe breach observations with:

```bash
synthworld generate-risk-public \
  --seed 20260719 \
  --persona-count 10 \
  --output risk-input.json
```

Every case receives a predicted band. Optional score or probability fields are scored only when supplied by the task contract; the expected score is a deterministic reference index, not a probability or forecast.

**Exposure and broker lifecycle.** `synthworld generate-corpus` creates deterministic breach, broker, search, and social scenarios. Broker-removal lifecycle evaluation is available through `synthworld evaluate broker`; do not infer broader longitudinal product behavior from the static corpus.

**Offline search-provider projection.** `generate_search_projection` exercises search-consumer logic without a network dependency. It includes collisions, insufficient-evidence cases, syndicated copies, stale observations, missing snippets, and seed-dependent result order while keeping evaluator truth separate. The report keeps false accepts, false rejects, unwarranted decisions, coverage, distinct findings, stale acceptances, and difficulty support independent.

**Boundary.** Only artifacts explicitly documented as public belong on the product side. Annotated or evaluator bundles may contain expected results even when the same benchmark also provides a product-safe projection.

Use the documentation site's evaluation guide for the general integration sequence. For schemas, formulas, benchmark identities, and frozen reference values use [DATA_DICTIONARY.md](../../DATA_DICTIONARY.md) and [BENCHMARKS.md](../../BENCHMARKS.md).
