# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
package adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
The data contracts (core-world, exposure, extraction, connection, risk, agentic,
ambiguity, search, temporal, and broker schemas) are versioned independently of the
package; see [DATA_DICTIONARY.md](DATA_DICTIONARY.md).

## [Unreleased]

## [0.14.0] - 2026-08-11

### Added

- **Independent C08 evidence-binding v2 contracts.** Asteria and enterprise
  lineages now have separately versioned public input, evaluator truth,
  submission, report, manifest, deterministic reference-generation, and
  evidence-quality metric contracts. Public inputs expose opaque binding
  handles and same-kind distractors while exact required bindings remain in
  evaluator truth. Existing v1 contracts and frozen bytes remain unchanged.
- **C08 v2 candidate registry metadata.** Repository-local metadata records the
  Asteria and enterprise C08 v2 benchmark identities as candidates with pending
  publication gates. These entries do not publish either benchmark externally
  or claim external hosting, viewer support, download availability, or
  re-download verification.

- **Independent C08 v2 frozen-artifact candidates.** Asteria now commits an exact
  five-file root/public/evaluator manifest tree; enterprise commits an exact
  four-file root-manifest/`SHA256SUMS` tree with a packaged fail-closed loader and
  fixed-seed identity comparison. Both public contracts use opaque binding
  handles plus same-kind distractors instead of exposing a unique kind-to-ID
  answer. Independent manifest schemas, expanded v1 hash locks, explicit offline
  report scope, and exactly two metric-only discrimination records accompany the
  candidate bytes. Native adversarial findings and repository verification gates
  are recorded as resolved. Nothing is externally published or deployed.
- A curated benchmark registry now records independent lifecycle, benchmark-kind,
  evaluation-mode, artifact-sensitivity, integrity, and publication-gate evidence
  for every current benchmark family.
- **A source-complete Blume documentation site.** The repository now carries a
  structured public documentation tree, generated capability and benchmark
  catalogues, dark-preview builds, documentation-impact routing, and distribution
  audits. The site is ready for a separately authorized deployment but is not
  published by this release.
- **Guarded Hugging Face publication planning.** A local publication manifest,
  offline validator, and protected dry-run workflow bind publication authority to
  the resolved benchmark registry. Uploads remain disabled: no benchmark or
  operation is authorized and the outstanding external gates remain explicit.
- **A safely fictional EADS-shaped adapter example.** The repository-only,
  humans-only example accepts bounded JSON or YAML fixtures, emits separately
  typed public and evaluator projections, and records deterministic path-bound
  provenance. It is not shipped in the wheel, performs no network access, and
  makes no real-EADS compatibility claim.
- **Future enterprise authority designs.** Reviewed design records reserve
  non-conflicting C15/C16 v1 and Face B contract, schema, package, benchmark, and
  manifest identities. They define canonical normalization, collision rejection,
  UUID5 domain separation, public/evaluator boundaries, and staged gates without
  implementing or freezing those deferred families.

### Changed

- Agentic evidence metrics and deployment-pattern coverage now state their
  reporting-only limits, metric polarity, denominators, null and abstention
  semantics, and declaration-versus-observation boundary without changing metric
  values, scoring versions, schemas, or frozen artifacts.
- Benchmark, documentation, release, and Hugging Face governance now fail closed
  on same-version frozen-inventory additions, compare push transitions with the
  pre-push commit, audit the exact documentation distribution, and publish the
  already-verified release artifact rather than rebuilding it.

## [0.13.0] - 2026-08-06

### Added

- **A deterministic enterprise identity and access surface, with authorization
  evaluated against standards-shaped projections (#7, #27).** SynthWorld now
  generates a fixed enterprise identity/access universe — organisations, units,
  populations, principals, accounts, groups, roles, permissions, entitlements,
  and opaque authorization targets — and evaluates access against it through
  three bounded oracles: a directory **RBAC** oracle with role and group closure,
  a bounded **ABAC** oracle over declared attributes, and a bounded **ReBAC**
  oracle over relationship tuples. Access derivation is an implementation detail
  of the oracle rather than a published topology, so no artifact describes the
  model as an identity topology.
  New modules: `enterprise`, `enterprise/rbac`, `enterprise/abac`,
  `enterprise/rebac`, `enterprise/authorization`, `enterprise/conformance`,
  `enterprise/identity_fabric`, `agentic/enterprise`.
- **Vendor-neutral projections so a real authorization engine can consume the
  world without a bespoke adapter.** `enterprise/projections/` emits an RFC
  7643-style **SCIM** user/group projection, an **OpenFGA** authorization model
  and relationship tuples for the bounded ReBAC subset, and an **AuthZEN 1.0**
  request projection with per-field provenance. Each projection carries an
  explicit mapping profile recording what it can and cannot represent, so a
  projection gap is declared rather than silently lossy. A **Shared Signals/CAEP**
  mapping profile is declared, but temporal event emission is deliberately
  deferred and no SET envelope is constructed yet.
- **Two smoke benchmarks and a graded assurance ladder.** An enterprise identity
  fabric smoke benchmark and an enterprise agentic smoke benchmark publish public
  inputs and evaluator truth under `enterprise-identity-access-contract/`; a
  contextual access benchmark profile publishes under
  `contextual-access-contract/`. `continuous_assurance` adds `smoke`,
  `standard`, `longitudinal`, and `held_out` tiers governing assurance cadence.
  Note these are assurance tiers, not generated-world scale tiers — the
  `enterprise_agentic` scale ladder #27 asks for remains open at `smoke` only.
- **An executable agent-authority run protocol.** `agent_authority` and
  `assurance` add a staged run protocol with signed execution receipts, component
  provenance, and evidence claims, so an evaluation run is reconstructible from
  its receipt rather than trusted on assertion.
- **The ambiguity v2 pack gets its difficulty from a computed error floor, not a
  codebook (#80).** The v1-style surfaces encoded each identity index in cleartext, so a
  ~30-line normaliser recovered every relation and scored 1.0000; two successor designs
  fell to pool inversion. The fix follows the reviewed plan: each kind draws a base from
  a pool of **confusable clusters** (`Sorensen`/`Sorenson`/`Soerensen`, a transposed
  phone, a swapped day/month), `EQUAL`/`NEAR` share the base while `FAR` redraws from a
  **stationary** mixture, and every value passes through one **structured-noise operator**
  applied identically under every relation. Identity recovery stays free and expected;
  the *relation* is carried by overlapping distance distributions. The pack publishes its
  **genie floor** — the Bayes error of the generator, estimated with a stated N and
  Wilson interval and keyed to a digest of every decision-relevant constant — plus the
  enumerated channel invariants (kernel stationarity, an identical one-value marginal
  under every relation, a per-base sibling-landing mass gate, form bijectivity and
  constant cross-form distance, and an artifact-factorization check) and a gated
  technique premium, so real resolution technique is rewarded rather than anti-taught.
  New modules: `ambiguity_evidence`, `ambiguity_surfaces`, `ambiguity_channel`,
  `ambiguity_floor`, with v2 serialization/metrics/baselines support and
  `examples/compute_ambiguity_floor.py`.
- Agent-authority and contextual-access receipt builders now seal honest
  failed-run receipts: a failed product execution produces a manifest with
  `execution_status=failed` and `evaluation_status=not_evaluated` that binds
  only the product-stage artifacts and never loads evaluator truth, so an
  assurance corpus can no longer be structurally biased toward successful runs.
  Receipt validation enforces the paired statuses and the product-only artifact
  inventory, and run manifests whose evidence claim is not supported by the
  systems under test (live-lab claims with reference-only components) are
  rejected. Managed-service provenance in `not_exposed` observability states
  additionally forbids evidence references, and the contextual execution
  receipt leaves `stimulus_digest` unset because that lineage executes the
  public input directly.
- Contextual-access receipts now expose the same explicit two-phase live-run
  boundary as agent-authority receipts. External runners may finish and attribute
  the product stage before constructing completion metadata; the finalizer then
  replays the plan, public input, adapter, component inventory, provenance, and
  artifact digests before evaluator truth is loaded. Existing deterministic
  contextual receipt bytes remain unchanged.
- An opt-in disposable agent-authority reference deployment now executes the
  public enterprise-agentic smoke world across isolated Docker networks. It
  produces live observation-v2 receipts covering L01-L06, the exact declared
  L07 baseline/SUT inventory, and measured/unsupported L08 targets, while
  keeping runtime credentials in a destroyed named volume and scanning canary
  and token markers out of receipts, logs, and container metadata. A new
  two-phase receipt finalizer lets live runners record completion metadata only
  after external execution without exposing evaluator truth before product
  output is durably staged.
- Agent-authority observation schema `2.0.0` corrects L06 clock semantics without
  changing the frozen observation-v1 schema. It records one explicit monotonic
  revocation epoch, non-negative acknowledgement offsets, and signed send/completion
  offsets so pre-revocation in-flight requests are representable. Receipt validation
  dispatches v1/v2 observations and binds them to scoring formulas `1.0.0`/`2.0.0`;
  migration guidance forbids guessing offsets from ambiguous v1 rows.
- The 12-case authority-change governance conformance fixture from #73 is now an
  additive frozen benchmark. Its public and evaluator payloads remain physically
  separate; their visibility manifests and exact raw bytes are path-bound by a
  packaged `SHA256SUMS`, verified by the packaged loader API, regeneration tests,
  and isolated-wheel checks. No existing golden bytes changed.
- The broker-removal pack is scored through the unified evaluator: `evaluate_broker_removal`
  projects each family's headline ratio into the standard `EvaluationReport`, the CLI gains
  `synthworld evaluate broker`, and `examples/evaluate_broker_adapter.py` is the worked
  Idcognito-style adapter #5 asked for - public timeline in, versioned assessment out,
  scored against regenerated truth. Closes the last acceptance criteria of #5.
- Propagation **lag** is representable and scored (#65). Downstream copies carry their own
  removal tick (`None` never goes), a new `slow_propagation` case has copies that catch up
  late rather than never, a submission can predict the completion tick, and
  `propagation_lag` reports mean absolute error with support. The credulous baseline now
  predicts completion at confirmation - "done means done everywhere" - and eats a 14-tick
  error on exactly the case built to price that claim; the example adapter's modest grace
  period cuts it to 4.

### Changed

- **Ambiguity grammar `2.0.0`, v2 schema `2.1.0`.** `render_relation`/`render_value`
  delegate to the structured-noise channel; the old `_SPACE`/`_surface` codebook is gone.
  `Relation.EQUAL` no longer means "byte-identical" — it is one value transcribed once
  per record, rendered identically only with probability `sigma` — and the charter
  docstrings that claimed otherwise are rewritten. The v1 pack and its frozen artifacts
  are untouched and stay byte-identical.
- **`display_name` renders `family, given` (#86).** The two name kinds are scored as
  separate evidence, so the boundary between them must be readable off the value; the
  old `given family` lost it whenever a pool entry carried a space. No rendered name
  contains `", "`, so the split is unambiguous.
- **Temporal schema `1.2.0`.** `ListingTruth.downstream_refs` (bare strings) becomes
  `downstream_copies` with per-copy removal ticks, and a recorded reappearance must now
  coincide with a published `LISTING_REAPPEARED` event - truth that disagrees with the
  public timeline is refused as corrupt input. Deliberately asymmetric with removal, which
  stays unpinned because a confirmation is the broker's claim and the phantom case exists
  to show the claim can be false. `BrokerAssessment` moves to `1.1.0` for the new
  prediction field; propagation state is now read *as of the assessed tick*, so a slowly
  propagating deletion no longer scores identically to one that never propagates.
- `DenominatedMetric` moved to `synthworld.models`, below the evaluation/partition import
  cycle it was about to create; `ambiguity_partition` re-exports it unchanged.

## [0.12.0] - 2026-08-04

### Changed

- **Breaking (ambiguity answer key):** `same_name_and_date_of_birth` is now
  `insufficient`, not `separate` (#77). The pair is two people in canonical truth, but
  the public evidence — matching name and birth date, nothing distinguishing them —
  cannot justify concluding it. The pack's first consumer abstained on exactly this pair
  and independently gave the same reason. Membership truth is unchanged; the public and
  memberships artifacts are byte-identical, and only the dispositions artifact was
  re-cut (new digest in `GOLDEN_REVIEW.md`). A resolver scored against the old key that
  answered `separate` here was being rewarded for clairvoyance; one that abstains is now
  scored correctly.

- `EVALUATION_SCHEMA_VERSION` is `0.2.0`. `TaskMetric` gains optional `family` and
  `support_meaning`, so **every** task's report carries two more keys - extraction,
  entity resolution, relationship inference and risk included, even though none of
  their metrics changed meaning. The wire shape is what moved, so the schema knob is
  what moves; no per-task scoring version changes, because a scoring version here means
  the metric definitions and those are untouched. A stored `0.1.0` report does **not**
  load under the new model — the report's `schema_version` is a single-value literal —
  so read archived reports with the library version that wrote them.
- Agentic metrics are grouped into five families and every denominator says what it
  counts, so a report can be read by family and each ratio re-derived rather than
  trusted. No metric value moves. The split carrying the most information is
  `observability` against the rest: an agent can decide well and record badly, or the
  reverse, and those need different fixes. Measured on the reference trace, wrecking
  the recording drops observability to 0.25 while identity resolution, authorization
  and delegation stay at 1.0; wrecking the decisions drops authorization to 0.40 while
  observability stays at 1.0.
- `AGENTIC_BENCHMARK.md` gains a per-metric glossary: what each measures, what 0.0 and
  1.0 mean, and its denominator. **Sixteen of the twenty** metrics had no mention in any
  top-level document, so the only way to learn what they measured was to read the
  scorer or diff scores between policies. (They were cited in
  `agent-authority-contract/control-catalogue.yaml` and its design-intent notes, which
  a first version of this entry overlooked while claiming a repository-wide count.)

## [0.11.0] - 2026-08-03

### Security

- **Nine of eleven** known channels through which the ambiguity pack's answer key was
  recoverable from its public artifact are closed. Two remain open and are described
  below; regenerating a pack with this version does not make it safe against those two.
  Anyone who generated evaluation packs with an earlier version should still
  regenerate: nine channels are a great deal worse than two, and a system under test
  could otherwise reach the right answer without doing the task at all, so scores
  measured against those packs do not mean what they appear to. The frozen canonical
  pack was affected too and is re-cut here, with new digests recorded in
  [GOLDEN_REVIEW.md](GOLDEN_REVIEW.md).
- Eight of the eleven were metadata bound to the label — collection ordering, name
  pools indexed by a scenario ordinal, positional record identifiers, source types
  constant per scenario, repetition counts, attribute counts, a distinctive locality
  token, and cross-listing multiplicity. Each is closed by deriving the value from the
  evidence rather than from the case.
- The ninth was different and is the reason for the new `key` parameter: the
  substitution plan was a deterministic function of a *published* seed over canonical
  values that live in public source, so it could be recomputed and inverted rather than
  correlated. Rebuilding it recovered the disposition on 0.929 of pairs against a 0.467
  baseline. `generate_ambiguity_variant` now requires a `key` that is never serialized;
  pass `UNKEYED` to reproduce the published packs, or at least 16 bytes from
  `secrets.token_bytes` for evaluation.
- **The two that remain open**, tracked in
  [#68](https://github.com/bluntmachetti/synthworld/issues/68). Non-ASCII display names
  appear in only one scenario, so a search for them identifies a `merge` pair on every
  seed measured. Source-type agreement implies `separate` on every pair measured where
  the two sources match. A key closes neither, because neither depends on a draw: they
  are properties of a fixed case list, which
  [#62](https://github.com/bluntmachetti/synthworld/issues/62) addresses. Treat scores
  on the affected scenarios accordingly until then.

### Changed

- `BROKER_SCORING_VERSION` is `2.0.0`. The scoring formulas changed rather than grew:
  four families moved from an assessed-listings denominator to the discovered world,
  a removal request counts as warranted only when the system itself concluded the
  listing is the subject's, and `request_correctness` became `request_recall` because
  its denominator was always recall's. The same submission scores differently, so two
  reports at one version would be incomparable.
- `TEMPORAL_SCHEMA_VERSION` is `1.1.0`. Additive: the public artifact gained
  `listings` and truth gained `attributable`, both defaulted, so every `1.0.0`
  artifact still parses and a consumer that ignores the new field reads what it did.

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
- Public listing content and a published subject identity, so attribution is
  answerable rather than guessable. A first revision emitted lifecycle events with no
  content at all and never said who the subject was, which left the listing that is
  *not* theirs indistinguishable from the six that are. Content is drawn from one
  vocabulary and every readable page carries the same attribute kinds, so neither the
  attribute count nor a distinctive token substitutes for reading the values. `ListingTruth.attributable`
  marks the case whose page carries a common name and nothing to corroborate it:
  declining is correct there and deciding is unwarranted, the same distinction
  `PairDisposition.INSUFFICIENT` and `SearchMatchTruth.INSUFFICIENT_EVIDENCE` draw.
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

[Unreleased]: https://github.com/bluntmachetti/synthworld/compare/v0.14.0...HEAD
[0.14.0]: https://github.com/bluntmachetti/synthworld/compare/v0.13.0...v0.14.0
[0.13.0]: https://github.com/bluntmachetti/synthworld/compare/v0.12.0...v0.13.0
[0.12.0]: https://github.com/bluntmachetti/synthworld/compare/v0.11.0...v0.12.0
[0.11.0]: https://github.com/bluntmachetti/synthworld/compare/v0.10.0...v0.11.0
[0.10.0]: https://github.com/bluntmachetti/synthworld/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/bluntmachetti/synthworld/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/bluntmachetti/synthworld/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/bluntmachetti/synthworld/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/bluntmachetti/synthworld/releases/tag/v0.6.0
