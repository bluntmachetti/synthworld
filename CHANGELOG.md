# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
package adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
The data contracts (core-world, exposure, extraction, connection, risk, and
agentic schemas) are versioned independently of the package; see
[DATA_DICTIONARY.md](DATA_DICTIONARY.md).

## [Unreleased]

### Added

- A deterministic temporal slice for privacy exposure, and a broker
  deletion-and-reappearance pack scored on top of it. Virtual time is an integer tick,
  never a wall clock; `materialise` returns the events at or before a tick, so a
  system is asked what it knew when it could have known it. Seven named cases - six failure modes and a
  clean-removal control: a clean removal, a phantom removal the broker confirms
  but never performs, a reappearance after genuine removal, reseller copies surviving
  a source deletion, a refusal, a listing that was never the subject's, and a stale
  binding after a move. The clean and phantom cases emit the same sequence of event
  kinds at the same ticks, so the hardest one cannot be read off the timeline. Replay refuses histories that
  cannot happen — a confirmation with no request, a reappearance with no removal — while
  admitting repeated requests and conflicting statuses, which are cases rather than
  corruptions.
- `evaluate_broker_assessment`, reporting six families that are never combined:
  discovery, identity matching, request correctness, completion, propagation and
  recurrence. Every score publishes its numerator, denominator and the denominator's
  meaning. Two reference policies run in CI, gated on properties rather than numbers:
  neither may resolve the pack, both must overstate propagation, and recurrence must
  separate them — trusting broker confirmations catches no reappearance, while
  continuing to watch catches every one and still cannot see the phantom removal or
  the surviving copies.

- Scoring for the oracle-free search projection: `evaluate_search_judgements`
  separates false accepts from false rejects and from unwarranted decisions on
  results the public text cannot settle, reports coverage beside precision so
  abstaining everywhere cannot look perfect, and reports distinct findings against
  accepted results so a consumer that fails to collapse syndicated copies is visible.
  Errors are broken out by difficulty tier *with that tier's support*, because raw
  error counts rank tiers by size rather than by failure rate. `SearchMetrics` and
  `SearchEvaluation` publish their denominators, a `scoring_version` and a task
  discriminator, matching the ambiguity evaluation channels, and `SearchTruthBundle`
  now records the seed it describes.

- Separate ambiguity membership and evidence-disposition evaluation channels. A
  complete `EntityResolutionPrediction` is validated and scored directly against
  explicit membership truth with denominated pairwise and B-cubed metrics; a
  public-only projection derives forced binary decisions for the selected task
  pairs without discarding the raw partition or loading truth.
- A consumer-integration publication boundary: `.local-assurance/` is excluded
  from Git and package builds, repository tests reject private consumer symbols,
  dependencies, unreviewed adapter paths, and force-added local artifacts, and
  a named CI check plus code-owner review protects the boundary-defining files.
  Contribution guidance keeps one-off product execution out of public CI.
- A `synthworld validate agentic-trace` command that checks an observed-action
  JSONL submission for structural and cardinality correctness before scoring,
  with no access to evaluator truth. It reports every bad row in one pass with
  line numbers, exits `0` for valid and `1` for invalid, and prints a human
  summary by default or a machine report with `--json`. The guarantee is
  one-directional: a valid result means `evaluate agentic` will not raise
  `EvaluationInputError`. It is deliberately stricter in one case, rejecting a
  submission in which every row is empty, because the scorer would accept that
  and award a perfect `least_privilege_accuracy`.
- `load_public_agentic_bundle`, which loads and checksum-verifies a public-only
  Asteria tree without reading any evaluator artifact, plus
  `TraceValidationReport`, `TraceValidationIssue`, and `validate_trace_jsonl`.
- An asserted `pattern` on the timestamp property of the published trace schemas.
  `format` is an annotation rather than an assertion in JSON Schema 2020-12, so
  the schemas previously accepted a naive timestamp, a non-UTC offset, and
  `"not-a-date"` — all rejected by the model.
- A `schemas` target in `make ci` running `generate_trace_schema.py --check`, so
  schema drift fails the build, and an isolated-wheel check exercising the new
  command's accept and reject paths.
- A design-intent trace per agent-credential pattern class in
  `agent-authority-contract/examples/`, generated by
  `tools/generate_design_intent_traces.py`, with assumptions and a scored coverage
  table in `docs/design-intent-assumptions.md`. These are explicitly **not**
  measurements: no implementation was run and no product was tested. What they show
  is each pattern's observability ceiling — most usefully that short-lived scoped
  credentials match proxy injection on decisions and temporal correctness while
  scoring zero on delegation provenance, attribution and accountable ownership,
  because those are directory facts rather than token claims.
- An adapter template in `agent-authority-contract/adapter-template/` that reads only
  the public package, runs as shipped to produce a structurally valid trace, and
  isolates the integration work in one function.
- `tests/test_trace_schema_agreement.py`, asserting that the models and the
  published schemas accept the same bytes across a mutation corpus, with the two
  known pydantic coercion divergences declared explicitly. Adds
  `jsonschema[format]` and `types-jsonschema` as dev dependencies only.

### Changed

- Agentic scoring protocol `0.3.0`. `expected_policy_version` is derived from the
  delegation that covered the action instead of being copied from the attempt, and
  a policy-version-mismatch denial now records its covering chain. Every frozen
  Asteria Agentic v1 artifact is byte-identical under both protocols, because that
  world registers a single policy version; the number moves because the resolution
  rule changed, and a consumer scoring a world with more than one version would
  otherwise have no way to tell which rule produced their truth.

- `agent-authority-contract/README.md` no longer states that `jsonschema` will
  become a project dependency. The validate command uses the pydantic models
  instead, because the schemas are generated from those models and the two are
  not nested — each accepts input the other refuses, so runtime schema
  validation would enforce a different surface than the scorer.

### Added

- An AGENTIC_BENCHMARK.md "Trace conventions" section (issue #34) documenting
  the deterministic delegation-chain, evidence-reference, and side-effect
  rules the agentic evaluator grades against for the frozen Asteria Agentic
  v1 fixture, referenced from DATA_DICTIONARY.md.

## [0.10.0] - 2026-07-27

### Added

- Relational integrity validation for custom agentic worlds, including reusable
  owner/runtime graph helpers, bounded v1 root and child delegator provenance,
  exact canonical-binding joins, and explicit integrity errors before evaluator
  truth generation.
- Agentic provenance exact-match and micro-precision metrics so fabricated
  evidence is distinguishable from missing evidence.

### Changed

- Agentic reports now use scoring protocol `0.2.0`; other task scoring versions
  and every frozen Asteria Agentic v1 artifact remain unchanged.
- The README and Hugging Face dataset card now state the Python 3.12 minimum
  explicitly, and published copyright notices consistently name Redoubt Labs
  ltd.
- Package verification now derives the wheel filename from the project version,
  so release bumps do not leave `make ci` checking a stale distribution.

## [0.9.0] - 2026-07-27

### Added

- Asteria Agentic v1 (issue #23): a frozen, checksum-bound procurement
  conformance world with separate organisation, principal, logical-agent,
  runtime, credential, resource, delegation, policy, and evidence roles; 24
  replayable events and 11 positive/negative authority cases; physically
  separate public and evaluator artifact trees; a nullable observed-action
  JSONL contract; independent identity, authority, temporal, attribution,
  owner, provenance, and side-effect metrics; public-only naive baselines; and
  `generate-agentic` / `evaluate agentic` CLI support.
- Reusable `synthworld.agentic` contracts, deterministic index/timestamp replay,
  field-by-field benchmark projection, tamper-checked package loaders, and an
  open-string case label so later custom worlds are not forced to reproduce
  Asteria's canonical case set.
- A repository-maintained Hugging Face dataset card that documents the Asteria
  public/evaluator boundary, authoritative artifact digests, and raw-file
  verification workflow.

### Changed

- The extraction evaluator now rejects predictions that reference pages outside
  the public corpus (for example, from a mismatched seed or persona count) with
  `EvaluationInputError`, and `ExtractionPredictionSet` rejects duplicate pages
  — consistent with the malformed-submission handling of the other scorers.
- BENCHMARKS.md renders its three visuals as native Mermaid diagrams again,
  dropping the committed `assets/*.svg` files. GitHub renders Mermaid inline, so
  the document no longer depends on the image proxy.
- The README now starts with a goal-led use-case chooser, and a new
  `USER_GUIDE.md` explains the public-input-to-score workflow, current use
  cases, runnable commands, metric interpretation, and the safety boundary in
  plain language.
- The all-task example now derives every prediction from public observations
  only and can write five CLI-ready prediction files, including an Asteria
  observed-action JSONL trace. The README, user guide, examples guide, and
  Asteria guide now document the complete export, integration, scoring, and
  metric-interpretation workflow. The roadmap use-case map now labels packaged,
  partial, and planned capabilities explicitly.

## [0.8.0] - 2026-07-22

### Added

- Unified evaluation SDK (issue #1): versioned, oracle-free prediction schemas
  and four scorers — `evaluate_extraction`, `evaluate_entity_resolution`,
  `evaluate_relationship_inference`, `evaluate_risk_calibration` — that load
  truth themselves and return a uniform `EvaluationReport` of metrics and
  failure slices, with undefined metrics reported as `null` and malformed
  submissions rejected via `EvaluationInputError`. Metric definitions are
  versioned by `scoring_version`; the evaluation schemas are provisional
  `0.1.0` while the package is pre-1.0. A `synthworld evaluate <task>` CLI
  scores a predictions file (with an optional `--summary` table), and
  `examples/evaluate_all.py` demonstrates every task.
- Separated exact-span extraction benchmark (issue #13): a product-safe
  `PublicExtractionCorpus` and a physically separate `ExtractionAnswerKeyCorpus`,
  joined and integrity-checked by `ExtractionBenchmark`. New
  `generate-public-extraction` and `generate-extraction-answers` CLI commands,
  `generate_extraction_benchmark`, and separately checksummed
  `extraction-public-golden-v1.json` / `extraction-answer-golden-v1.json`
  frozen artifacts. The existing annotated `ExtractionCorpus` bundle is
  unchanged.
- A DATA_DICTIONARY.md section for the extraction schema, distinguishing the
  annotated evaluator bundle from the product-safe projection.
- The frozen golden benchmarks are published as a browsable Hugging Face
  dataset
  ([Bluntmachetti7/synthworld-benchmarks](https://huggingface.co/datasets/Bluntmachetti7/synthworld-benchmarks)),
  linked from the README.
- BENCHMARKS.md (issue #11): naive baseline results over the extraction,
  entity-resolution, relationship, and risk benchmarks, plus deterministic SVG
  visual demonstrations (under `assets/`) pulled straight from the pinned-seed
  corpora. Generated by `examples/generate_benchmarks_doc.py`, which
  `make baselines` checks for drift in CI.

### Changed

- The extraction example now feeds the system under test only the public pages
  and loads the answer key separately to score.

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

[Unreleased]: https://github.com/bluntmachetti/synthworld/compare/v0.10.0...HEAD
[0.10.0]: https://github.com/bluntmachetti/synthworld/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/bluntmachetti/synthworld/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/bluntmachetti/synthworld/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/bluntmachetti/synthworld/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/bluntmachetti/synthworld/releases/tag/v0.6.0
