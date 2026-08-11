# Benchmark model

A SynthWorld benchmark binds four different things:

| Layer | Purpose |
|---|---|
| Identity | Stable family/version/configuration identity |
| Public input | Product-facing observations with no answer-key fields |
| Evaluator truth | Canonical bindings, outcomes, cases, and metric inputs |
| Reproduction record | Checksums, generator/formula versions, seed/config, and provenance |

Structural validation and benchmark truth are separate. A malformed reference is
invalid; a well-formed unauthorized attempt is a scoreable negative case.

Frozen benchmark versions are independent contracts. A transition creates a new
version with schemas, checksums, tests, packaging checks, documentation, and a
review record; it does not silently rewrite old bytes.
