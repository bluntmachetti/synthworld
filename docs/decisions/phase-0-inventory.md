# Phase 0 documentation inventory and governance decisions

Status: proposed pending review closure

Date: 2026-08-08

Scope: Work Package A records the evidence snapshot, documentation ownership,
publication-boundary vocabulary, and prerequisites for the documentation site.
Work Package A is partial until this record and the section-level
[documentation migration index](documentation-migration-index.md) are complete.
This record does not publish or migrate canonical product documentation.

## Public delivery labels

The following labels are defined in this record and do not rely on an external
or local planning document:

- Work Package A: the Phase 0 public documentation inventory, ownership, and
  governance record, completed only with the migration index.
- B6: the four-axis benchmark-publication metadata design in this record.
- B7: the mandatory independent adversarial review before Phase 5 publication.
- Section 13: the future public benchmark-publication implementation area,
  including registry, gate, workflows, and Hugging Face publication controls.
- PR B: the publication-boundary harness.
- PR C: the capability checker.
- PR D: the benchmark registry and publication gate.

## Explicit non-actions

This record does not authorize or perform:

- README reduction or replacement.
- GitHub Pages deployment.
- Hugging Face upload or dataset-card refresh.
- Schema, benchmark, checksum, or golden-artifact changes.

## Evidence snapshot

- The package version is `0.13.0` in [pyproject.toml](../../pyproject.toml#L7).
- Current automation is Python CI and release automation, including the Public
  consumer boundary and Secret scan CI jobs. See
  [ci.yml](../../.github/workflows/ci.yml) and
  [release.yml](../../.github/workflows/release.yml#L57). There is no
  documentation or SynthWorld Pages workflow.
- The root `docs/` directory currently contains only this decision tree. There
  is no `package.json`, Node lockfile, Blume configuration, Pages workflow, or
  `CNAME` file. The separate `agent-authority-contract/docs/` directory has
  three tracked design documents, including generated, drift-checked content.
- Root `AGENTS.md` is local and gitignored. It is not a tracked, public, or
  CI-readable authority. No tracked `CLAUDE.md` or nested policy file is
  present.
- Current external publication surfaces are PyPI, GitHub Releases, and the
  Hugging Face dataset card. See [pyproject.toml](../../pyproject.toml#L7),
  [release.yml](../../.github/workflows/release.yml#L57), and
  [huggingface/README.md](../../huggingface/README.md).

### External observations

Every external observation below carries an observation date and reproduction
command. It must be rechecked before a decision that depends on live service
state.

| Observation | Date | Reproduction command |
| --- | --- | --- |
| npm metadata reports `blume@1.3.1`, engine `>=22.12.0`, and executable `blume` | 2026-08-08 | `npm view blume version description bin engines repository --json` |
| Account-root Pages site is built, public, HTTPS-enforced, legacy build type, sourced from `main:/`, has `cname: null`, and has URL `https://bluntmachetti.github.io/` | 2026-08-08 | `gh api repos/bluntmachetti/bluntmachetti.github.io/pages` |
| SynthWorld has no Pages configuration (`404`) | 2026-08-08 | `gh api repos/bluntmachetti/synthworld/pages` |

## Documentation ownership and migration rule

The canonical source remains authoritative until a later migration explicitly
changes ownership. A site page may summarize or link to a canonical source, but
must not create an independently hand-maintained copy of its factual tables,
commands, schemas, benchmark results, or release status. Generated source data
must be rendered by its generator. Curated interpretation must identify its
owner and evidence.

Tracked public documentation and contributor policy must live in
[CONTRIBUTING.md](../../CONTRIBUTING.md) or another tracked public document in a
future update. Local agent files may point to that policy but are not authority.
Prompts and assets are excluded from documentation publication unless a later
decision explicitly approves them.

| Source | Canonical responsibility | Site migration rule |
| --- | --- | --- |
| [README.md](../../README.md) and [USER_GUIDE.md](../../USER_GUIDE.md) | Product positioning, installation, user workflows, CLI and Python boundaries, safety guidance | One product and task-oriented ownership surface; do not duplicate command reference or availability prose by hand. |
| [DATA_DICTIONARY.md](../../DATA_DICTIONARY.md) | Field meanings, schema versioning, and public/evaluator semantics | Link to or migrate field definitions as a single owned reference; schema facts remain derived from source models and schemas. |
| [AGENTIC_BENCHMARK.md](../../AGENTIC_BENCHMARK.md) | Asteria replay contract, artifact layout, traces, and metrics | Preserve as the authoritative frozen-benchmark guide until a successor page owns the entire contract. |
| [BENCHMARKS.md](../../BENCHMARKS.md) | Generated baseline demonstrations and explanations | Render generated material; retain its existing drift check and never hand-copy baseline values. |
| [GOLDEN_REVIEW.md](../../GOLDEN_REVIEW.md) and [EVALUATION_KEY_CUSTODY.md](../../EVALUATION_KEY_CUSTODY.md) | Frozen-artifact governance, checksums, review history, evaluation-key custody | Keep governance records canonical and link from site policy pages. |
| [ROADMAP.md](../../ROADMAP.md) | Direction, maturity, availability boundaries, and non-goals | Curated roadmap content has one owner; release availability must be joined to tag/changelog evidence. |
| [CHANGELOG.md](../../CHANGELOG.md) and [CONTRIBUTING.md](../../CONTRIBUTING.md) | Release history, version authority, contribution and benchmark-change policy | Historical release claims come from tags and changelog; contribution policy remains canonical here. |
| [SECURITY.md](../../SECURITY.md) and [CODE_OF_CONDUCT.md](../../CODE_OF_CONDUCT.md) | Security reporting and community conduct policy | Preserve as tracked policy sources; site material links to them rather than recreating policy. |
| [.github/pull_request_template.md](../../.github/pull_request_template.md) | Contributor workflow authority, including public/evaluator separation and frozen-checksum policy | Preserve as a tracked contributor workflow source; do not recreate its policy in product documentation. |
| Five contract package READMEs and schemas | Normative contract boundaries, schemas, examples, and adapter requirements | Contract pages link to the specific contract README and schema rather than paraphrase normative rules. |
| Contract design documents | Design assumptions, generated matrices, and drift-checked rationale | Initially excluded from the public site allowlist; retain their owning contract generator and drift checks. |
| [examples/README.md](../../examples/README.md) | Worked flows and demonstrations | Examples may be indexed but are not an authoritative API or schema reference. |
| [huggingface/README.md](../../huggingface/README.md) | Dataset-card metadata, configurations, viewer projections, and raw-artifact guidance | Audit input only for the initial site; any later site summary must be generated or traceable to the card audit. |

The five contract packages are:

- [agent-authority-contract](../../agent-authority-contract/README.md).
- [authority-governance-contract](../../authority-governance-contract/README.md).
- [contextual-access-contract](../../contextual-access-contract/README.md).
- [continuous-assurance-contract](../../continuous-assurance-contract/README.md).
- [enterprise-identity-access-contract](../../enterprise-identity-access-contract/README.md).

Each package owns its README, schemas, design documents, and any generator that
produces checked-in contract documentation. A site integration does not assume
ownership of those generators.

## Versioning decisions

- Documentation tracks current `main` and must show an explicit `Unreleased` or
  `Preview` label when a capability is not established by a released tag.
- Tagged documentation and contract artifacts are historical authority for their
  tagged release. Current-main documentation must not rewrite their past claims.
- No versioned documentation route tree is introduced initially. Historical
  content is reached through repository tags and release artifacts.

## Tooling decision and evidence

Blume is retained as the candidate site renderer. The Node dependency cost is
accepted, and portable Markdown remains the canonical content format. Node
isolation from Python packaging is intended architecture, pending the package
cleanliness proof; it is not yet established fact.

The npm observation above identifies `blume@1.3.1`, engine `>=22.12.0`,
executable `blume`, and these commands:

`add`, `audit`, `build`, `check`, `dev`, `doctor`, `eject`, `eval`, `init`,
`mcp-stdio`, `preview`, `sync`, and `validate`.

The local evidence snapshot is Node `22.22.2` and npm `10.9.7`, satisfying the
published engine constraint. Blume is not installed in this repository or as a
local tool. Command behavior, configuration conventions, and subpath handling
remain unverified until the technical spike installs a pinned version and builds
copied, non-canonical content. No `make` wrapper is promised before that proof.

## Pages topology decision

The confirmed account-root Pages site is an independent public legacy site at
`https://bluntmachetti.github.io/`, built from `main:/` with no custom domain.
SynthWorld has no Pages configuration or workflow. The intended future target
is a project site at `/synthworld/`; it must not alter the account-root site.

Only future SynthWorld project-site decisions remain unresolved:

- Deployment workflow, trigger, and permissions.
- Pages environment and deployment approval model.
- Project-site base path, canonical URL, and preview URL.
- Asset, navigation, sitemap, feed, and canonical-link behavior under
  `/synthworld/`.
- Rollback procedure and required-check/branch-protection implications.

## Capability governance design

Capability claims are a resolved join of two separately governed inputs:

- Generated implementation facts: command or API identifier, surface, source
  location, input/output contract, schema/version reference, and detected
  availability evidence.
- Curated maturity metadata: capability identifier, maturity label, owner,
  rationale, known limitations, and evidence reference.
- Resolved publication record: capability identifier, generated fact revision,
  curated metadata revision, release/tag evidence, display label, and any
  unresolved state.

The checker must fail when an identifier is missing from either side, sources
disagree on the public name or surface, a maturity record is stale relative to
its fact revision, release availability lacks tag/changelog evidence, or an
unreleased capability is labelled as released. Generated facts and curated
judgment are intentionally not merged into a hand-maintained table.

## Benchmark publication design and traceability

This public record resolves B6 design by separating the following four
independent fields. The earlier mixed Section 13 list is superseded for
implementation; PR D must use these four fields.

| Field | Allowed values | Meaning |
| --- | --- | --- |
| `capability_maturity` | `planned`, `experimental`, `preview`, `stable` | Capability readiness and support maturity. |
| `publication_lifecycle` | `unpublished`, `candidate`, `published`, `superseded` | Publication state. |
| `artifact_kind` | `frozen_fixture`, `generated_benchmark`, `generated_profile`, `projection`, `experiment` | What the artifact is. |
| `sensitivity` | `public_input`, `public_reference_truth`, `private_held_out_truth`, `operator_private`, `internal_build_only` | The sole authority for publication sensitivity. |

`generated_profile` is an artifact kind, not a lifecycle state. Held-out truth
is a sensitivity classification, not a lifecycle state. A publication gate must
read all four fields, plus artifact-specific evidence, rather than infer safety
from a filename, path, or one overloaded status field. `undetermined` is an
inventory-only placeholder permitted on any axis when evidence is weak. It is
not a fifth field or an allowed publication value: the publication gate rejects
every record containing it.

This record also makes B7 mandatory: the dedicated adversarial review described
below must close before Phase 5 Hugging Face publication.

## Initial public site source allowlist

The initial site build accepts only tracked files from a clean checkout. It has
no recursive repository-root source. Each allowlisted source has an exact path,
source type, permitted site destination, generator owner where relevant, and
explicit sensitivity handling.

| Exact repository path | Source type | Destination or allowed use | Generator owner | Sensitivity handling |
| --- | --- | --- | --- | --- |
| [README.md](../../README.md) | Tracked curated Markdown | Product overview | None | Ordinary curated prose; not an artifact payload. |
| [USER_GUIDE.md](../../USER_GUIDE.md) | Tracked curated Markdown | Task guides | None | Ordinary curated prose; evaluator-derived inserts require `public_reference_truth` or rejection. |
| [DATA_DICTIONARY.md](../../DATA_DICTIONARY.md) | Tracked curated Markdown | Reference pages | None | Ordinary curated prose; evaluator-derived inserts require `public_reference_truth` or rejection. |
| [AGENTIC_BENCHMARK.md](../../AGENTIC_BENCHMARK.md) | Tracked curated Markdown | Asteria guide | None | Ordinary curated prose; evaluator-derived inserts require `public_reference_truth` or rejection. |
| [BENCHMARKS.md](../../BENCHMARKS.md) | Tracked generated Markdown | Benchmark demonstrations | `make baselines` | Generated summaries are not artifact payloads; evaluator-derived inserts require `public_reference_truth` or rejection. |
| [ROADMAP.md](../../ROADMAP.md) | Tracked curated Markdown | Roadmap | None | Ordinary curated prose; not an artifact payload. |
| [CHANGELOG.md](../../CHANGELOG.md) | Tracked curated Markdown | Release history | None | Ordinary curated prose; not an artifact payload. |
| [CONTRIBUTING.md](../../CONTRIBUTING.md) | Tracked curated Markdown | Contributor policy | None | Ordinary curated prose; not an artifact payload. |
| [SECURITY.md](../../SECURITY.md) | Tracked curated Markdown | Security policy | None | Ordinary curated prose; not an artifact payload. |
| [CODE_OF_CONDUCT.md](../../CODE_OF_CONDUCT.md) | Tracked curated Markdown | Community policy | None | Ordinary curated prose; not an artifact payload. |
| [GOLDEN_REVIEW.md](../../GOLDEN_REVIEW.md) | Tracked governance Markdown | Frozen-artifact governance | None | Ordinary governance prose; no artifact payload. |
| [EVALUATION_KEY_CUSTODY.md](../../EVALUATION_KEY_CUSTODY.md) | Tracked governance Markdown | Evaluation custody policy | None | Ordinary governance prose; no artifact payload. |
| [examples/README.md](../../examples/README.md) | Tracked curated Markdown | Examples index | None | Ordinary curated prose; not an artifact payload. |
| [agent-authority-contract/README.md](../../agent-authority-contract/README.md) | Tracked contract Markdown | Contract index | Contract package | Ordinary contract prose; evaluator-derived inserts require `public_reference_truth` or rejection. |
| [authority-governance-contract/README.md](../../authority-governance-contract/README.md) | Tracked contract Markdown | Contract index | Contract package | Ordinary contract prose; evaluator-derived inserts require `public_reference_truth` or rejection. |
| [contextual-access-contract/README.md](../../contextual-access-contract/README.md) | Tracked contract Markdown | Contract index | Contract package | Ordinary contract prose; evaluator-derived inserts require `public_reference_truth` or rejection. |
| [continuous-assurance-contract/README.md](../../continuous-assurance-contract/README.md) | Tracked contract Markdown | Contract index | Contract package | Ordinary contract prose; evaluator-derived inserts require `public_reference_truth` or rejection. |
| [enterprise-identity-access-contract/README.md](../../enterprise-identity-access-contract/README.md) | Tracked contract Markdown | Contract index | Contract package | Ordinary contract prose; evaluator-derived inserts require `public_reference_truth` or rejection. |
| [docs/decisions/phase-0-inventory.md](../../docs/decisions/phase-0-inventory.md) | Tracked decision Markdown | Governance decision | None | Ordinary governance prose; no artifact payload. |
| [docs/decisions/documentation-migration-index.md](documentation-migration-index.md) | Planned tracked decision Markdown | Section-level migration inventory when tracked | None | Ordinary governance prose; no artifact payload. |

The five sensitivity values apply to artifact and evaluator-derived payloads.
Ordinary curated prose is not silently classified as `public_input`. Any
evaluator-derived inserted content must be explicitly classified as
`public_reference_truth` or rejected.

Initially excluded are `AGENTS.md`, [huggingface/README.md](../../huggingface/README.md)
as audit-input-only, contract deep documentation, schemas, `src/`, `tests/`,
prompts, assets, plans, generated benchmark artifacts, and untracked, ignored,
build, cache, or local paths. PR B will convert this policy into an executable
manifest that records each source's destination, source type, sensitivity
handling, and generator owner.

Search indexes, sitemaps, feeds, source maps, generated JSON, asset manifests,
`llms.txt`, raw AI exports, and raw machine-readable exports remain disabled and
require separate review before enablement. Evaluator-derived content requires an
explicit sensitivity label. The publication audit must apply allowlist and
metadata policy; it must not reject content merely because text or paths contain
`evaluator`.

## Repository benchmark-family inventory

This is an inventory of repository families, not a final publication
classification or permission to upload. "Repository only" means no current
Hugging Face configuration is evidenced by the current card.

| Family | `capability_maturity` | `publication_lifecycle` | `artifact_kind` | `sensitivity` | Evidence | Current HF representation |
| --- | --- | --- | --- | --- | --- | --- |
| Core identity | `undetermined` | `undetermined` | `frozen_fixture` | `undetermined` | [DATA_DICTIONARY.md](../../DATA_DICTIONARY.md) and [huggingface card](../../huggingface/README.md) | Represented by `personas` and `relationships`. |
| Extraction | `undetermined` | `undetermined` | `frozen_fixture` | `undetermined` | [huggingface card](../../huggingface/README.md) | Represented by `public_extraction_pages` and `extraction_answers`. |
| Connection | `undetermined` | `undetermined` | `frozen_fixture` | `undetermined` | [huggingface card](../../huggingface/README.md) | Repository only. |
| Risk | `undetermined` | `undetermined` | `frozen_fixture` | `undetermined` | [huggingface card](../../huggingface/README.md) | Repository only. |
| Ambiguity v1 | `undetermined` | `undetermined` | `frozen_fixture` | `undetermined` | [packaged public artifact](../../src/synthworld/benchmarks/ambiguity-public-v1.json), [memberships artifact](../../src/synthworld/benchmarks/ambiguity-memberships-v1.json), and [review record](../../GOLDEN_REVIEW.md#L107) | Repository only. |
| Ambiguity v2 | `undetermined` | `undetermined` | `generated_benchmark` | `undetermined` | [BENCHMARKS.md](../../BENCHMARKS.md#L101) and [DATA_DICTIONARY.md](../../DATA_DICTIONARY.md#L1155) | Repository only. |
| Search | `undetermined` | `undetermined` | `generated_benchmark` | `undetermined` | [USER_GUIDE.md](../../USER_GUIDE.md#L520) | Repository only. |
| Temporal | `undetermined` | `undetermined` | `generated_benchmark` | `undetermined` | [DATA_DICTIONARY.md](../../DATA_DICTIONARY.md#L638) | Repository only. |
| Broker | `undetermined` | `undetermined` | `generated_benchmark` | `undetermined` | [USER_GUIDE.md](../../USER_GUIDE.md#L345) | Repository only. |
| Households | `undetermined` | `undetermined` | `frozen_fixture` | `undetermined` | [packaged households fixture](../../src/synthworld/benchmarks/households-smoke-v1.json) and [checksum manifest](../../src/synthworld/benchmarks/HOUSEHOLDS_SMOKE_SHA256SUMS) | Repository only. |
| Asteria agentic | `undetermined` | `undetermined` | `frozen_fixture` | `undetermined` | [AGENTIC_BENCHMARK.md](../../AGENTIC_BENCHMARK.md) and [huggingface card](../../huggingface/README.md) | Represented by five `asteria_*` configurations. |
| Enterprise identity fabric | `undetermined` | `undetermined` | `generated_benchmark` | `undetermined` | [enterprise contract](../../enterprise-identity-access-contract/README.md) | Repository only. |
| Enterprise agentic | `undetermined` | `undetermined` | `generated_benchmark` | `undetermined` | [USER_GUIDE.md](../../USER_GUIDE.md) | Repository only. |
| Contextual access | `undetermined` | `undetermined` | `generated_benchmark` | `undetermined` | [contextual contract](../../contextual-access-contract/README.md) | Repository only. |
| Authority governance | `undetermined` | `undetermined` | `frozen_fixture` | `undetermined` | [authority governance contract](../../authority-governance-contract/README.md) | Repository only. |
| Continuous assurance | `undetermined` | `undetermined` | `generated_benchmark` | `undetermined` | [continuous assurance contract](../../continuous-assurance-contract/README.md) | Repository only. |
| Projections | `undetermined` | `undetermined` | `projection` | `undetermined` | [huggingface card](../../huggingface/README.md) and viewer guidance | Represented where the card names `viewer/` paths; individual provenance remains undetermined. |

Where evidence does not prove a runtime benchmark is packaged as a frozen
fixture, the inventory uses `generated_benchmark`. A later registry must retain
`undetermined` rather than invent evidence when a family or projection cannot be
classified confidently.

## Current Hugging Face configuration inventory

The card declares ten configurations. `personas` is the default configuration;
all declared data files use the `golden` split. The listed `frozen/` and
`viewer/` paths are Hugging Face repository paths and are not locally verifiable
from this record.

| Configuration | `data_files` path | Proposed `capability_maturity` pending PR D validation | Proposed `publication_lifecycle` pending PR D validation | Proposed `artifact_kind` pending PR D validation | Proposed `sensitivity` pending PR D validation |
| --- | --- | --- | --- | --- | --- |
| `personas` (default) | `viewer/personas.jsonl` | `undetermined` | `undetermined` | `projection` | `public_input` |
| `relationships` | `viewer/relationships.jsonl` | `undetermined` | `undetermined` | `projection` | `public_input` |
| `public_extraction_pages` | `viewer/public_extraction_pages.jsonl` | `undetermined` | `undetermined` | `projection` | `public_input` |
| `extraction_answers` | `viewer/extraction_answers.jsonl` | `undetermined` | `undetermined` | `projection` | `public_reference_truth` |
| `public_identity_records` | `viewer/public_identity_records.jsonl` | `undetermined` | `undetermined` | `projection` | `public_input` |
| `asteria_principals` | `frozen/asteria-agentic-v1/public/principals.jsonl` | `undetermined` | `undetermined` | `frozen_fixture` | `public_input` |
| `asteria_resources` | `frozen/asteria-agentic-v1/public/resources.jsonl` | `undetermined` | `undetermined` | `frozen_fixture` | `public_input` |
| `asteria_delegations` | `frozen/asteria-agentic-v1/public/public_delegations.jsonl` | `undetermined` | `undetermined` | `frozen_fixture` | `public_input` |
| `asteria_authority_truth` | `frozen/asteria-agentic-v1/evaluator/authority_truth.jsonl` | `undetermined` | `undetermined` | `frozen_fixture` | `public_reference_truth` |
| `asteria_cases` | `frozen/asteria-agentic-v1/evaluator/cases.jsonl` | `undetermined` | `undetermined` | `frozen_fixture` | `public_reference_truth` |

The current [Hugging Face card](../../huggingface/README.md#L73) still says
`v0.9.0+` and provides a `v0.9.0` installation instruction, while the package
is `0.13.0`. The audit must cover card version claims, installation
instructions, config names, configuration paths, `data_files` paths, source
artifact digests, license, language, task category, size category, tags, and
sensitivity classification. The card is not changed by this record.

## Mandatory adversarial-review gate

Before any Phase 5 Hugging Face publication, B7 requires a dedicated
adversarial review of the full Section 13 implementation. Its scope includes
the schema, publication gate, workflows and triggers, required checks,
permissions, dataset-card audit, and post-publish verification.

Claude, invoked through `omc ask claude`, is the desired reviewer for incumbent
continuity. Sol is the independent OpenAI review. Kimi is the independent
Moonshot review. Qwen 3.8 Max via OpenRouter is the documented Kimi fallback.
This record does not claim any of these reviews has occurred or closed.

## Phase 0 status and next slices

| Slice | Status | Exit gate |
| --- | --- | --- |
| This decision record | Proposed | Review closes with any factual corrections incorporated. |
| Work Package A and documentation migration index | Partial | This record is accepted and [documentation-migration-index.md](documentation-migration-index.md) inventories each section's canonical source and migration owner. |
| PR B: publication-boundary harness | Pending | Deterministically detect planted forbidden content in a synthetic build while allowing explicitly labelled `public_reference_truth`; state whether it extends, siblings, or replaces the existing public-boundary test. |
| PR C: capability checker | Pending | Generate implementation facts, join curated maturity, and fail on missing, stale, contradictory, or unsupported release claims. |
| PR D: benchmark registry | Pending | Validate all four independent metadata fields, retain `undetermined` where evidence is weak, and require all four in the publication gate. |
| Technical Blume spike and package cleanliness | Pending | Pin and install Blume, prove a copied-content build under `/synthworld/`, verify commands, and prove Node tooling does not alter Python package behavior. |

The pending slices must remain separate from README reduction, production Pages
deployment, Hugging Face publication, and frozen benchmark changes until their
own exit gates and required review gates are satisfied.
