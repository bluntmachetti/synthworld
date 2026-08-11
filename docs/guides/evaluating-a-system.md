# Evaluating a system

Every integration follows three steps:

1. Give the system only the benchmark's public product input.
2. Convert native output into the typed prediction or trace contract.
3. Score it against the separately serialized evaluator artifact.

Use `synthworld validate ...` before scoring where a validator exists. Structural
validity means a submission can be scored; it does not mean the system performed
well.

Keep metrics independent. Record each numerator, denominator, support, formula
version, benchmark identity, seed/config, and artifact checksums. Do not hide a weak
dimension behind an aggregate.

See [metrics](../reference/metrics.md), the detailed
[user guide](../../USER_GUIDE.md), and the relevant contract README.
