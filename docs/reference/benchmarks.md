# Benchmarks

The [registry catalogue](/benchmarks/catalogue) is generated during documentation
preparation from `docs/_data/benchmarks.resolved.json`. It is an explicitly
allowlisted public projection rather than a hand-maintained status table or a copy
of the raw registry. The existing human-readable generated inventory remains
[BENCHMARKS.md](../../BENCHMARKS.md).

Keep these axes separate:

- Capability maturity: what a product surface can demonstrate, governed separately
  by the capability registry.
- Publication lifecycle: the benchmark state, using exactly `experimental`,
  `candidate`, `published`, or `superseded`.
- Artifact kind: the role of an artifact, recorded by its governed `kind` field.
- Artifact sensitivity: the custody and publication controls recorded by the
  governed `sensitivity` field.

The registry's `benchmark_kind` and `evaluation_mode` fields are additional
benchmark semantics: they describe benchmark construction and evaluation
behaviour. They do not replace or collapse the four governance axes. In
particular, a generated profile is a benchmark kind, not a publication lifecycle
or sensitivity label.

`undetermined` may appear in a working discovery inventory, but it is forbidden in
curated, resolved, or otherwise governed records.

External publication requires explicit allowlisted artifacts and boundary audit; it
is never inferred from package presence.
