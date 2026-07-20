# Contributing

Thank you for helping make privacy-system evaluation more honest and
reproducible. Open an issue before a large change so its intended benchmark or
schema impact can be agreed first.

## Development

Install [uv](https://docs.astral.sh/uv/), then run:

```bash
uv sync --locked --all-groups
make ci
```

Changes to analytical behavior must begin with a ground-truth assertion. The
full suite must retain 100% branch coverage, zero unexplained skips, deterministic
output for a fixed seed, and unchanged benchmark checksums unless a deliberately
reviewed benchmark version is being introduced.

## Synthetic-data boundary

Never submit real personal data or plausible identifiers that could belong to a
real person. New generated identities must retain `synthetic: true`, reserved
domains, fictional phone ranges, obvious example addresses, and deliberately
invalid national identifiers. Public observations and evaluator-only truth must
remain physically separated.

By submitting a contribution, you agree that it is licensed under Apache-2.0.
