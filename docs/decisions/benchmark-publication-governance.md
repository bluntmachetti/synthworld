# Benchmark publication governance

Status: accepted  
Decision date: 2026-08-10

## B6: independent publication axes

Benchmark publication governance keeps four axes independent:

- **Capability maturity** describes what a product capability can demonstrate. It
  is governed by the capability registry and does not imply benchmark publication.
- **Publication lifecycle** records the benchmark state using exactly
  `experimental`, `candidate`, `published`, or `superseded`.
- **Artifact kind** records an artifact's role using the governed `kind` field.
- **Artifact sensitivity** records custody and publication constraints using the
  governed `sensitivity` field.

The benchmark registry also records `benchmark_kind`, which describes benchmark
construction, and `evaluation_mode`, which describes how evaluation is performed.
These are additional benchmark semantics. They do not replace or collapse any of
the four governance axes.

`undetermined` is permitted only in a working discovery inventory before a record
enters governance. It is forbidden in curated, resolved, or otherwise governed
records. An unclassified record must remain outside those records or fail the
applicable gate; uncertainty must not be presented as publication status.

## B7: independent Section 13 review

Section 13 benchmark-publication governance, and any change that authorizes
external benchmark publication under it, requires independent adversarial review
before publication. The review must examine classification vocabulary, axis
separation, public/evaluator boundaries, gate evidence, and publication claims. It
must not be replaced by author self-review.

The independent review dated 2026-08-10 found two repository blockers:

1. The benchmark reference described lifecycle using terms outside the governed
   `experimental`, `candidate`, `published`, and `superseded` vocabulary.
2. The Hugging Face control workflow watched a nonexistent transition filename
   instead of the authoritative `benchmark-transitions.json` input.

This branch addresses those blockers through the aligned benchmark reference and
workflow trigger. This decision record also preserves the durable B6/B7 owner
decisions without adopting the historical Phase 0 inventories or migration index
as current repository facts.
