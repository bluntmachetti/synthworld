# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
package adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
The data contracts (core-world, exposure, extraction, connection, and risk
schemas) are versioned independently of the package; see
[DATA_DICTIONARY.md](DATA_DICTIONARY.md).

## [Unreleased]

## [0.7.0] - 2026-07-20

### Added

- PyPI release workflow using GitHub OIDC Trusted Publishing, gated on the
  full CI suite and a tag-to-version match.
- `py.typed` marker so type checkers consume the package's inline annotations;
  its presence in the wheel is asserted by `make package`.
- `examples/` with a worked exact-span extraction evaluation and annotated
  sample output; the example runs as part of `make ci` so it cannot rot.
- Project URLs, keywords, and classifiers in the packaging metadata.
- This changelog, a code of conduct, issue templates, and a pull-request
  template.

### Changed

- README documents the `idcognito-synthworld` install name, adds status
  badges, and links the examples.
- The public data dictionary no longer references internal roadmap
  milestones.

## [0.6.0] - 2026-07-20

Initial public release, extracted from a private workspace with history
squashed; internal 0.x iterations are not part of this repository.

### Added

- Deterministic seeded world generator: personas, identity attributes, and
  evidence-backed relationship ground truth (core-world schema `1.0.0`).
- Exposure corpus generator for breach, broker, search, and social scenarios
  (exposure schema `1.0.0`).
- Exact-span extraction corpus with evaluator-only answer keys (extraction
  schema `1.0.0`).
- Adversarial and relationship connection benchmarks with a strict
  public/oracle type boundary (connection schema `1.0.0`).
- Risk-calibration benchmark with public observations physically separated
  from evaluator-only score and factor truth (risk schema `1.0.0`).
- `synthworld` CLI with eleven generate and metrics subcommands.
- Seven frozen golden benchmarks with SHA256 manifests and byte-equality
  tests.
- Quality gates: strict mypy, ruff, 100% enforced branch coverage, an honesty
  gate for unexplained skips, CI on Python 3.12 and 3.14, and a full-history
  secret scan.

[Unreleased]: https://github.com/bluntmachetti/synthworld/compare/v0.7.0...HEAD
[0.7.0]: https://github.com/bluntmachetti/synthworld/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/bluntmachetti/synthworld/releases/tag/v0.6.0
