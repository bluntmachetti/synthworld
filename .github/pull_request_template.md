## Summary

<!-- What changes and why. Link the agreed issue for large changes. -->

## Checklist

- [ ] `make ci` passes locally (lint, typecheck, package, tests, metrics,
      examples).
- [ ] No real personal data or plausibly real identifiers; synthetic markers
      (`synthetic: true`, `example.test`, `555-01xx`, `SYN-` prefixes) are
      intact.
- [ ] Frozen benchmark checksums are unchanged, or this PR deliberately
      introduces a reviewed benchmark version change (explain in the
      summary).
- [ ] Evaluator-only truth remains physically separated from public
      artifacts.
- [ ] CHANGELOG.md has an entry under Unreleased for user-visible changes.
