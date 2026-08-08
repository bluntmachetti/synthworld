# Contributing documentation

Documentation is authored as plain Markdown and must remain useful directly on
GitHub before any renderer is involved.

## Source hierarchy

- Code, typed models, generated artifacts, release metadata, and validated registries
  are product-fact sources.
- `DATA_DICTIONARY.md` remains the deep core field reference.
- `BENCHMARKS.md` remains generated/drift-checked.
- Contract READMEs remain normative for contract schemas, budgets, boundaries, and
  examples.
- `CHANGELOG.md` remains the committed release source.
- `ROADMAP.md` remains the concise repository-readable roadmap.

Summarize and link these sources; do not duplicate their tables line for line.

## Version language

These pages track current `main`. Label behavior not present in the latest tagged
release `Unreleased` or `Preview on main`. Historical truth remains available through
matching tags and releases; do not create a second versioned route tree yet.

## Safety and review

Do not include evaluator answer keys, private imports, salts, keys, local receipts,
real personal data, or proprietary integration details. Changes to benchmark claims
must follow the validated capability and publication registries.

Track migrations in [the migration index](../migration-index.md) and leave source
content in place until its canonical destination is complete and validated.
