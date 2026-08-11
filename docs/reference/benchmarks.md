# Benchmarks

The [registry catalogue](/benchmarks/catalogue) is generated during documentation
preparation from `docs/_data/benchmarks.resolved.json`. It is an explicitly
allowlisted public projection rather than a hand-maintained status table or a copy
of the raw registry. The existing human-readable generated inventory remains
[BENCHMARKS.md](../../BENCHMARKS.md).

Keep these axes separate:

- Capability maturity: what a product surface can demonstrate.
- Publication lifecycle: whether a benchmark is proposed, packaged, approved, or
  externally published under the registry's vocabulary.
- Sensitivity: what custody and publication controls an artifact requires.
- Generation profile: a reproducibility/configuration choice, not a sensitivity
  label.

External publication requires explicit allowlisted artifacts and boundary audit; it
is never inferred from package presence.
