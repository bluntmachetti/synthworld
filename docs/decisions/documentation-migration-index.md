# Documentation migration index

## Purpose and status

This is the Blume Phase 0 section-level inventory of tracked public documentation. It is not migrated site content, a release-status statement, or a publication decision. Destinations are provisional and may change during Phase 1 information architecture work. The root README remains unchanged until its replacement routes exist and have been reviewed.

Until row-level ownership is assigned, the Phase 1 documentation workstream is the provisional migration owner for every row in this index. A `TBD Phase 1` destination is a planning placeholder only; no such row is authorized to migrate until its destination, source treatment, and owner have been explicitly approved.

`retain` means the source remains canonical at its current path. `migrate` means the subject is a candidate for a site page. `link` means the site should point to the canonical source. `generate` means the site must derive the material from a checked generator or other evidence authority. `retire` means replace only after an approved successor exists. `audit-only` means an input to publication review, not an initial site source.

The initial site source allowlist is intentionally separate from this inventory. In particular, the agent-authority deep documents are excluded pending explicit review, and Hugging Face material is audit-only until its metadata and publication classifications are reconciled.

## Section inventory

| Source file | Heading/anchor | Canonical owner/evidence authority | Planned action | Provisional destination | Notes/duplication risks |
| --- | --- | --- | --- | --- | --- |
| `README.md` | `# SynthWorld` | Product positioning; package metadata and reviewed root copy | migrate | `TBD Phase 1` | Landing-page candidate; retain root README until a replacement exists. |
| `README.md` | `## Choose what you want to do` | Product navigation | migrate | `TBD Phase 1` | Duplicates user-guide use-case navigation. |
| `README.md` | `## Featured: agent authority` | Agent-authority contract and benchmark docs | migrate | `TBD Phase 1` | Must not overstate unimplemented C15/C16 or evidence retention. |
| `README.md` | `## Why SynthWorld` | Product principles and safety policy | migrate | `TBD Phase 1` | Overlaps roadmap principles and data-dictionary framing. |
| `README.md` | `## Current benchmark families` | Benchmark manifests, reviews, and package exports | generate | `TBD Phase 1` | Benchmark-family listing must not drift from registry/manifests. |
| `README.md` | `## Public input and evaluator truth` | Schema contracts and custody policy | migrate | `TBD Phase 1` | Duplicates benchmark, data-dictionary, and custody explanations. |
| `README.md` | `## Enterprise identity and access` | Enterprise contract, package release evidence, and CLI inventory | migrate | `TBD Phase 1` | Release/availability language conflicts with historical 0.9 wording elsewhere. |
| `README.md` | `## Install` | `pyproject.toml` and release artifacts | generate | `TBD Phase 1` | Installation commands require release-state evidence. |
| `README.md` | `## Develop from source` | `CONTRIBUTING.md`, package configuration, and CI | link | `TBD Phase 1` | Avoid a second contributor workflow. |
| `README.md` | `## Validate before you score` and `## Evaluate a system` | CLI registration, schemas, and evaluator implementation | generate | `TBD Phase 1` | High CLI-reference duplication risk. |
| `README.md` | `## Roadmap and integrations` | `ROADMAP.md` | link | `TBD Phase 1` | Keep roadmap chronology in one owner. |
| `README.md` | `## Verify every claim` | Checksums, `GOLDEN_REVIEW.md`, and tests | migrate | `TBD Phase 1` | Overlaps frozen-artifact governance. |
| `README.md` | `## License` | Repository license metadata | retain | `TBD Phase 1` | Keep a stable short legal notice in README. |
| `USER_GUIDE.md` | `# SynthWorld user guide` | User workflow documentation | migrate | `TBD Phase 1` | Candidate guide landing page. |
| `USER_GUIDE.md` | `## Choose your use case` and `## The three-part workflow` | User workflow documentation | migrate | `TBD Phase 1` | Duplicates README navigation; one route should own the chooser. |
| `USER_GUIDE.md` | `## Try SynthWorld without installing it`, `## Install and create your first world`, and `## Run the five evaluation examples` | CLI inventory, package metadata, and examples | generate | `TBD Phase 1` | Commands and release availability must be derived, not copied. |
| `USER_GUIDE.md` | `## Use case 1: safe connected identity fixtures` through `## Use case 5: breach-risk calibration` | Generators, schemas, and benchmark artifacts | migrate | `TBD Phase 1` | Candidate task guides; overlaps README family listing and examples. |
| `USER_GUIDE.md` | `## Use case 6: agent identity and delegated authority` | Agentic API, Asteria benchmark, and agent-authority contract | migrate | `TBD Phase 1` | Must distinguish frozen Asteria from future generated worlds. |
| `USER_GUIDE.md` | `## Use case 7: exposure scenarios` through `## Use case 10: search-provider input without the answer key` | Generators, schemas, and benchmark artifacts | migrate | `TBD Phase 1` | Candidate task guides; public/evaluator wording must remain consistent. |
| `USER_GUIDE.md` | `## Use case 11: enterprise identity and access structure` and `## Use case 12: projecting a compiled world to SCIM, OpenFGA, and AuthZEN` | Enterprise compiler and projection implementation | migrate | `TBD Phase 1` | Enterprise release status and evaluator-derived projection boundaries need audit. |
| `USER_GUIDE.md` | `## Use case 13: enterprise authorization benchmarks` | Enterprise-agentic implementation and contract docs | migrate | `TBD Phase 1` | Do not present compilable imports as benchmarkable until the plan permits it. |
| `USER_GUIDE.md` | `## Reading evaluation results` | Evaluator implementation and metric definitions | generate | `TBD Phase 1` | Metric count and C08 meaning must remain synchronized with evaluator output. |
| `USER_GUIDE.md` | `## Safety boundary` | `CONTRIBUTING.md`, `EVALUATION_KEY_CUSTODY.md`, and schemas/contract boundaries | migrate | `TBD Phase 1` | Duplicates public/evaluator explanation; requires a single canonical policy page. |
| `DATA_DICTIONARY.md` | `# SynthWorld data dictionary` | Typed models and generated schemas | generate | `TBD Phase 1` | Field reference should be generator-backed, not hand-copied. |
| `DATA_DICTIONARY.md` | `## World and graph`, `## Persona`, and `## Exposure corpus` | Core typed models and schemas | generate | `TBD Phase 1` | Candidate generated reference groups. |
| `DATA_DICTIONARY.md` | `## Frozen benchmark`, `## Exact-span extraction`, `## Public connection corpus`, and `## Public breach-risk corpus` | Frozen artifacts, schemas, and manifests | generate | `TBD Phase 1` | Duplicates benchmark-family listings; preserve version and checksum authority. |
| `DATA_DICTIONARY.md` | `## Agentic identity and delegated authority` and `## Trace validation report` | Agentic typed models and evaluator | generate | `TBD Phase 1` | Must retain C08 reporting-versus-retention boundary. |
| `DATA_DICTIONARY.md` | `## Enterprise identity and access universe`, `## Bounded authorization oracles`, and `## Standards projections` | Enterprise models, compiler, and projections | generate | `TBD Phase 1` | Contract schemas and generator-backed facts; do not infer deployment enforcement. |
| `DATA_DICTIONARY.md` | `## Temporal schedule views`, `## Identity-fabric smoke benchmark`, and `## Enterprise-agentic smoke benchmark` | Enterprise schemas, compiler, and benchmark artifacts | generate | `TBD Phase 1` | Separate shipped smoke surfaces from future adapter/benchmark work. |
| `DATA_DICTIONARY.md` | `## Contextual access`, `## Authority-change governance`, and `## Continuous assurance` | Corresponding contract schemas and evaluators | generate | `TBD Phase 1` | Contract-backed facts should link to normative sources. |
| `DATA_DICTIONARY.md` | `## Run receipts` and `## Evaluation` | Receipt models and evaluator implementation | generate | `TBD Phase 1` | Avoid a second CLI or metric reference. |
| `DATA_DICTIONARY.md` | `## What the public/evaluator split does not claim` | Custody policy and contract boundaries | migrate | `TBD Phase 1` | Duplicate of policy material across README, guide, and contracts. |
| `AGENTIC_BENCHMARK.md` | `# Asteria Agentic v1` and `## What is frozen` | Asteria manifests, checksums, and `GOLDEN_REVIEW.md` | migrate | `TBD Phase 1` | Frozen benchmark contract; all artifact facts must be manifest-backed. |
| `AGENTIC_BENCHMARK.md` | `## Replay semantics` | Replay implementation and schemas | generate | `TBD Phase 1` | Candidate generated protocol reference. |
| `AGENTIC_BENCHMARK.md` | `## Public and evaluator packages` | Public/evaluator manifests and custody policy | migrate | `TBD Phase 1` | Duplicates broader public/evaluator explanation. |
| `AGENTIC_BENCHMARK.md` | `## Observed-action JSONL` | Observed-action schema | generate | `TBD Phase 1` | Schema-backed reference; avoid manually maintained field tables. |
| `AGENTIC_BENCHMARK.md` | `## Metrics and baselines` | Evaluator implementation and generated baseline report | generate | `TBD Phase 1` | Evaluator emits 20 metrics; C08 proves reporting agreement, not retention. |
| `AGENTIC_BENCHMARK.md` | `## Creating other worlds later` | Roadmap and approved generator capabilities | link | `TBD Phase 1` | Must not imply deferred generated-world work exists today. |
| `BENCHMARKS.md` | `# SynthWorld baselines and benchmark demonstrations` and `## Reproduce` | Baseline generator and `make baselines` | generate | `TBD Phase 1` | Generated material; checked output is the evidence authority. |
| `BENCHMARKS.md` | `## Baseline results`, `## Asteria Agentic v1 baselines`, `## Enterprise authorization baselines`, and `## Ambiguity v2 error floor` | Baseline generator, evaluator, and frozen artifacts | generate | `TBD Phase 1` | Do not migrate as static prose or duplicate scores. |
| `BENCHMARKS.md` | `## Why SynthWorld, not a row generator`, `## What the visuals show`, and `## Size and limits` | Product narrative plus generated benchmark evidence | migrate | `TBD Phase 1` | Separate explanatory prose from generated figures and limits. |
| `ROADMAP.md` | `# SynthWorld roadmap`, `## Product principles`, and `## Architecture direction` | Product roadmap owner | migrate | `TBD Phase 1` | Canonical strategy and non-implementation claims. |
| `ROADMAP.md` | `## Phase 1 — Benchmark adoption` through `## Phase 5 — Exploratory identity ecosystems` | Product roadmap owner | migrate | `TBD Phase 1` | Preserve future tense; do not recast roadmap items as released capability. |
| `ROADMAP.md` | `## Use-case map` | Product roadmap owner and package evidence | audit-only | `TBD Phase 1` | Contains stale 0.9 availability framing; reconcile with release evidence before migration. |
| `ROADMAP.md` | `## Explicit non-goals` and `## Contribution guidance` | Product boundary and `CONTRIBUTING.md` | migrate | `TBD Phase 1` | Contribution material overlaps contributing guide. |
| `CHANGELOG.md` | `# Changelog` and `## [Unreleased]` | Release process and reviewed release notes | retain | `TBD Phase 1` | Changelog remains canonical for shipped changes. |
| `CHANGELOG.md` | `## [0.13.0] - 2026-08-06` through `## [0.6.0] - 2026-07-20` | Tagged releases and release notes | link | `TBD Phase 1` | Historical release evidence; do not summarize manually into capability claims. |
| `CONTRIBUTING.md` | `# Contributing` and `## Development` | Contributor workflow, package config, and CI | migrate | `TBD Phase 1` | Development commands risk duplicating docs tooling and README. |
| `CONTRIBUTING.md` | `## Reporting a security or safety issue` | `SECURITY.md` and safety policy | link | `TBD Phase 1` | Avoid separate incident paths. |
| `CONTRIBUTING.md` | `## Synthetic-data boundary` and `## Consumer-integration boundary` | Repository policy and contract boundaries | migrate | `TBD Phase 1` | Overlaps README and roadmap non-goals. |
| `CONTRIBUTING.md` | `## Releasing` | Release workflow and changelog | link | `TBD Phase 1` | Release process should have one operational owner. |
| `SECURITY.md` | `# Security policy`, `## Reporting`, and `## Scope` | Security policy owner | retain | `TBD Phase 1` | Canonical tracked policy source; site treatment must link rather than create a second maintained policy page. |
| `SECURITY.md` | `## Out of scope`, `## Supported versions`, and `## Response` | Security policy owner and release evidence | link | `TBD Phase 1` | Link to the canonical policy; supported-version claims require a release-policy check. |
| `CODE_OF_CONDUCT.md` | `# Contributor Covenant Code of Conduct` and `## Our Pledge` | Code-of-conduct policy owner | retain | `TBD Phase 1` | Keep canonical policy file; site may link to it. |
| `CODE_OF_CONDUCT.md` | `## Our Standards`, `## Enforcement Responsibilities`, `## Scope`, `## Enforcement`, `## Enforcement Guidelines`, and `## Attribution` | Code-of-conduct policy owner | link | `TBD Phase 1` | Do not fork external covenant text into multiple copies. |
| `GOLDEN_REVIEW.md` | `# Golden-v1 review record` | Frozen-artifact review records | retain | `TBD Phase 1` | Governance record, not narrative documentation. |
| `GOLDEN_REVIEW.md` | `## Connection-golden-v1 review record`, `## Extraction public and answer review record`, `## Asteria Agentic v1 review record`, `## Ambiguity-v1 review record`, and `## Authority-governance-v1 review record` | Per-benchmark frozen artifact review records | link | `TBD Phase 1` | Link from benchmark registry; do not duplicate review evidence. |
| `EVALUATION_KEY_CUSTODY.md` | `# Evaluation key custody: operator approval checklist` and `## Before generation` | Operator custody policy | migrate | `TBD Phase 1` | Canonical evaluator-custody guidance. |
| `EVALUATION_KEY_CUSTODY.md` | `## CI and execution`, `## Closeout and incidents`, and `## Approval record` | Operator custody policy | migrate | `TBD Phase 1` | Reinforces public/evaluator boundaries; do not frame as secrecy. |
| `examples/README.md` | `# Examples` and `## Worked evaluation: exact-span extraction` | Maintained examples and evaluator output | migrate | `TBD Phase 1` | Examples are instructional, not authoritative API definition. |
| `examples/README.md` | `## Worked evaluation: public-only baseline walkthrough` and `## Sample output` | Maintained examples and generated output | migrate | `TBD Phase 1` | Duplicates guide evaluation walkthroughs; ensure stable output or label illustrative. |
| `agent-authority-contract/README.md` | `# Agent Authority Contract` and `## Status` | Normative agent-authority contract | retain | `TBD Phase 1` | Keep the owning README canonical; status must remain contract-specific and must not promise deferred controls. |
| `agent-authority-contract/README.md` | `## Schemas` | Contract schemas and schema generator | generate | `TBD Phase 1` | Generator-backed facts; schemas remain normative. |
| `agent-authority-contract/README.md` | `## What the control catalogue is for` and `## Reading the catalogue` | `control-catalogue.yaml` and schema validation | link | `TBD Phase 1` | Link to the owning contract README; control descriptions require catalogued evidence authority. |
| `agent-authority-contract/README.md` | `## Verifying the identifiers` | Contract tools and deterministic verification | generate | `TBD Phase 1` | CLI/tool surface must be verified before publication. |
| `agent-authority-contract/README.md` | `## Maintenance` | Contract governance | retain | `TBD Phase 1` | Keep operational contract maintenance close to schemas. |
| `authority-governance-contract/README.md` | `# Authority-change governance conformance` and `## One clock and deterministic precedence` | Governance schemas and evaluator | retain | `TBD Phase 1` | Keep the owning README canonical; normative contract material remains schema-backed. |
| `authority-governance-contract/README.md` | `## Visibility and metrics` | Governance evaluator and public/evaluator artifacts | generate | `TBD Phase 1` | Avoid duplicating metrics and visibility classifications. |
| `contextual-access-contract/README.md` | `# Contextual-access benchmark contract v1` and `## Temporal compatibility matrix` | Contextual-access schemas and evaluator | retain | `TBD Phase 1` | Keep the owning README canonical; matrix should be derived if surfaced. |
| `contextual-access-contract/README.md` | `## Public/evaluator boundary` and `## External run contract` | Contract schemas, manifests, and custody policy | link | `TBD Phase 1` | Link to the owning contract README; preserve contract-specific requirements. |
| `continuous-assurance-contract/README.md` | `# Continuous identity and authority assurance` and `## One temporal axis` | Assurance schemas and evaluator | retain | `TBD Phase 1` | Keep the owning README canonical; normative contract material remains schema-backed. |
| `continuous-assurance-contract/README.md` | `## Cases, tiers, and visibility` and `## Independent measurements` | Assurance evaluator and artifacts | generate | `TBD Phase 1` | Metrics and tier facts should be implementation-derived. |
| `enterprise-identity-access-contract/README.md` | `# Enterprise identity/access contract v1` and `## Pinned standards profile` | Enterprise schemas and pinned standards profile | retain | `TBD Phase 1` | Keep the owning README canonical; external-standard references need review. |
| `enterprise-identity-access-contract/README.md` | `## Bounded authorization families` and `## Fixed composition and artifact boundary` | Enterprise models, compiler, and schemas | link | `TBD Phase 1` | Link to the owning contract README; keep bounded-model claims aligned with compiler. |
| `enterprise-identity-access-contract/README.md` | `## Identity-fabric smoke benchmark` and `## Enterprise-agentic smoke benchmark` | Smoke artifacts, evaluator, and release evidence | generate | `TBD Phase 1` | Avoid conflating released smoke examples with future generated-world benchmarks. |
| `enterprise-identity-access-contract/README.md` | `## Pure standards projections` | Projection implementation and schemas | generate | `TBD Phase 1` | Evaluator-derived projections require sensitivity classification. |
| `agent-authority-contract/docs/design-intent-assumptions.md` | `# Design-intent assumptions`, `## What these files are, and what they are not`, and `## The three pattern classes` | Agent-authority design policy and control catalogue | audit-only | `TBD Phase 1` | Excluded from initial site allowlist pending explicit review. |
| `agent-authority-contract/docs/design-intent-assumptions.md` | `## Coverage, scored`, `## What would make this empirical`, and `## Reproducing the table` | Generated coverage render and contract tooling | audit-only | `TBD Phase 1` | Excluded pending review; declaration coverage is not runtime enforcement evidence. |
| `agent-authority-contract/docs/failure-reason-precedence.md` | `# Failure-reason precedence` and `## 1. Scope` through `## 4. The resolution rule` | Agent-authority failure-precedence specification and evaluator | audit-only | `TBD Phase 1` | Excluded from initial site allowlist pending explicit review. |
| `agent-authority-contract/docs/failure-reason-precedence.md` | `## 5. Selection, chain, and well-formedness` through `## 7. Consequences an independent implementation must reproduce` | Agent-authority failure-precedence specification and evaluator | audit-only | `TBD Phase 1` | Potential normative reference; review whether it belongs in public site. |
| `agent-authority-contract/docs/failure-reason-precedence.md` | `## 8. Worked examples from the frozen fixture`, `## 9. Conformance`, and `## 10. Appendix A — draft formal statement (not type-checked)` | Frozen fixture, evaluator, and draft specification | audit-only | `TBD Phase 1` | Exclude pending review; draft formal statement must not be presented as checked conformance. |
| `agent-authority-contract/docs/observation-v2-migration.md` | `# Agent-authority observation v2 migration`, `## Why v2 exists`, and `## Narrow v2 surface` | Versioned observation schema and migration policy | audit-only | `TBD Phase 1` | Excluded from initial site allowlist pending explicit review. |
| `agent-authority-contract/docs/observation-v2-migration.md` | `## Migration rule` | Versioned observation schema and migration policy | audit-only | `TBD Phase 1` | Do not publish migration instructions until version/support policy is confirmed. |
| `huggingface/README.md` | Dataset-card metadata, configurations, install instructions, and raw-artifact guidance | Hugging Face publication configuration and source artifact digests | audit-only | `TBD Phase 1` | Not an initial site source. Audit version claims, install commands, all config paths, tags/categories, and proposed sensitivity classifications before Phase 5. |

## Governance-surface inventory

These exact tracked paths are contributor or governance workflow sources, not product documentation. The decision records are governance evidence and must not become independently duplicated site prose.

| Source file | Heading/anchor | Canonical owner/evidence authority | Planned action | Provisional destination | Notes/duplication risks |
| --- | --- | --- | --- | --- | --- |
| `.github/pull_request_template.md` | Pull-request template | Repository contribution workflow | retain | `TBD Phase 1` | Contributor workflow source, not product documentation; site may link to contribution guidance only. |
| `.github/ISSUE_TEMPLATE/feature_request.yml` | Feature-request issue form | Repository issue-intake workflow | retain | `TBD Phase 1` | Contributor workflow source, not product documentation. |
| `.github/ISSUE_TEMPLATE/bug_report.yml` | Bug-report issue form | Repository issue-intake workflow | retain | `TBD Phase 1` | Contributor workflow source, not product documentation. |
| `.github/ISSUE_TEMPLATE/config.yml` | Issue-template configuration | GitHub issue-intake configuration | retain | `TBD Phase 1` | Operational configuration, not independently rendered prose. |
| `.github/DISCUSSION_TEMPLATE/show-and-tell.yml` | Show-and-tell discussion form | Repository discussion workflow | retain | `TBD Phase 1` | Contributor workflow source, not product documentation. |
| `.github/DISCUSSION_TEMPLATE/q-a.yml` | Q-and-A discussion form | Repository discussion workflow | retain | `TBD Phase 1` | Contributor workflow source, not product documentation. |
| `.github/DISCUSSION_TEMPLATE/ideas.yml` | Ideas discussion form | Repository discussion workflow | retain | `TBD Phase 1` | Contributor workflow source, not product documentation. |
| `.github/DISCUSSION_TEMPLATE/announcements.yml` | Announcements discussion form | Repository discussion workflow | retain | `TBD Phase 1` | Contributor workflow source, not product documentation. |
| `.github/CODEOWNERS` | Code-owner routing rules | Repository maintainer ownership policy | retain | `TBD Phase 1` | Governance enforcement source; site content must not duplicate ownership rules. |
| `LICENSE` | License text | Repository legal policy | retain | `TBD Phase 1` | Canonical legal text; any site notice must link rather than fork it. |
| `docs/decisions/phase-0-inventory.md` | Phase 0 inventory and governance decisions | Phase 0 documentation governance record | retain | `TBD Phase 1` | Governance evidence, not independently duplicated site prose. |
| `docs/decisions/documentation-migration-index.md` | Documentation migration index | Phase 0 documentation governance record | retain | `TBD Phase 1` | Governance evidence, not independently duplicated site prose. |

## Cross-source duplication and reconciliation findings

| Topic | Affected sources | Required Phase 0/1 handling |
| --- | --- | --- |
| Stale `0.9` availability language | `USER_GUIDE.md`, `ROADMAP.md`, `huggingface/README.md` | Audit against tagged releases, `CHANGELOG.md`, package metadata, and artifact provenance before editing or migrating. |
| Enterprise release status | `README.md`, `USER_GUIDE.md`, `ROADMAP.md`, `CHANGELOG.md`, enterprise contract README | Build a release-evidence join that distinguishes package shipment, CLI availability, smoke benchmarks, and deferred scale-tier/generated-world work. |
| CLI reference duplication | `README.md`, `USER_GUIDE.md`, contract READMEs, examples, contributor guidance | Generate one CLI/API inventory from registrations and typed exports; guides should link to it rather than reproduce command tables. |
| Public/evaluator explanation | `README.md`, `USER_GUIDE.md`, `DATA_DICTIONARY.md`, `AGENTIC_BENCHMARK.md`, contract READMEs, custody policy, Hugging Face card | Establish a shared policy page with contract-specific deltas; retain the rule that this is API hygiene, not secrecy or anti-cheating. |
| Benchmark-family listings | `README.md`, `BENCHMARKS.md`, `DATA_DICTIONARY.md`, `ROADMAP.md`, `GOLDEN_REVIEW.md`, Hugging Face card | Use a registry with independent `capability_maturity`, `publication_lifecycle`, `artifact_kind`, and `sensitivity` fields; generate lists from it. |

## Initial-boundary reminders

- `BENCHMARKS.md` results and all metric/baseline claims are generated content, not prose to copy.
- Contract schemas and generator-backed facts remain normative evidence authorities; site material must link or derive from them.
- `huggingface/README.md` is an audit input only until the configuration inventory and publication classifications are validated.
- `agent-authority-contract/docs/*.md` is excluded from the initial site allowlist pending explicit review.
- No document in this index authorizes a release, Pages deployment, README reduction, Hugging Face update, or a change to frozen artifacts.
