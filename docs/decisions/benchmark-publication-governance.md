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

## B8: bounded Hugging Face v0.14.0 authorization

The first governed Hugging Face refresh treats commit
`54a7d1e89f683ade507c3518b3e0c0bfddfbe528` and its 42-file inventory as an
immutable remote baseline. It does not retroactively re-authorize, regenerate,
delete, or relabel those files.

Authorization is per artifact, not per published benchmark family. The bounded
v0.14.0 tranche contains only the nine raw ambiguity-v1 and
authority-governance-v1 artifacts enumerated by the publication manifest plus a
single dataset-card replacement. Both C08 v2 benchmark identities remain
explicitly prohibited. New paths expose the public/evaluator boundary in their
directory structure, require an absent remote precondition, and are bound by
source digest, byte size, content type, benchmark version, and canonical
destination path.

The authorization change remains dry-run-only. Network access, upload capability,
deletion, protected-environment evidence, remote integrity evidence, and Viewer
validation remain separate gates. A later uploader must consume only the reviewed
manifest and use the pinned Hub commit as its compare-and-swap parent.
