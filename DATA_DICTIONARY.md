# SynthWorld data dictionary

Schema version: `1.0.0`. Every object below includes `synthetic: true`; models reject unknown fields and are immutable after validation.

## World and graph

| Record | Required fields | Meaning |
|---|---|---|
| `SynthWorld` | `schema_version`, `seed`, `personas`, `relationships` | One deterministic generated society and its relationship answer key. |
| `RelationshipEdge` | `id`, `source_person_id`, `target_person_id`, `kind`, `evidence` | A planted, undirected relationship between two persona IDs. |
| `RelationshipEvidence` | `signal`, `value` | The exact shared or synthetic signal supporting an edge label. |

Relationship kinds are `family`, `colleague`, `classmate`, `neighbor`, and `social`. Their respective evidence signals are shared surname plus address, employer, school plus graduation year, street, and a synthetic mutual-profile link.

## Persona

| Field | Type | Safety rule |
|---|---|---|
| `id` | string | World-local stable ID such as `persona-0001`. |
| `given_name`, `family_name` | string | Faker-generated atoms, meaningful only inside a marked synthetic record. |
| `date_of_birth` | ISO date | Faker-generated within the configured adult age range. |
| `emails` | `EmailAddress[]` | Reserved `example.test` domain; kind is `primary` or the reserved `managed_alias`. |
| `usernames` | `Username[]` | Begins with `synth_` and ends with a unique world-local index. |
| `phones` | `PhoneNumber[]` | North American fictional `555-01xx` subscriber block. |
| `addresses` | `Address[]` | Example-named street, `Testville`, invalid postal code `00000`, country `ZZ`. |
| `employment` | `Employment[]` | `Example Works` organization and explicitly synthetic role. |
| `education` | `Education[]` | `Test University` institution and a graduation year. |
| `national_ids` | `NationalId[]` | `SYN-` prefix, invalid Luhn checksum, and `checksum_valid: false`. |

`managed_alias` is reserved as a first-class email kind for planned identity-migration and enquiry workflows; the current generator does not create or operate aliases.

## Exposure corpus

`ExposureCorpus` schema `1.0.0` wraps an unchanged `SynthWorld` plus exactly one `ExposureScript` per persona. A script contains four ground-truth collections:

| Record | Required fields | Meaning |
|---|---|---|
| `BreachExposure` | `id`, `breach_name`, `occurred_on`, `severity`, `exposed_data` | A planted breach and the exact data classes it exposed. |
| `BrokerExposure` | `id`, `broker_name`, `exposed_data`, `lifecycle` | A planted broker listing and its virtual-time removal history. |
| `BrokerLifecycleEvent` | `state`, `at` | One of `found`, `removal_requested`, `confirmed_removed`, or `reappeared`. |
| `SearchExposure` | `id`, `result_kind`, `title`, `locator`, `match_kind`, `actual_persona_id`, `exposed_data` | A planted true result or labelled name-collision false positive. |
| `SocialExposure` | `id`, `platform`, `username`, `locator`, `exposed_data`, `connected_person_ids` | A planted synthetic social profile and existing-person connection references. |

Data classes are email, username, phone, address, date of birth, employer, education, national ID, and password. Password denotes a planted credential exposure; SynthWorld intentionally never stores reusable password values.

## Frozen benchmark

`src/synthworld/benchmarks/golden-v1.json` freezes seed `20260719` at ten personas. `SHA256SUMS` authenticates its exact bytes. Tests regenerate the corpus and require byte equality, so changes to generation, schema, ordering, or dependencies must be treated as an explicit benchmark-version change.

## Exact-span extraction

The extraction benchmark ships in two packaging patterns that share schema `1.0.0`.

The **annotated evaluator bundle** `ExtractionCorpus` pairs each page with its answer key in one artifact, convenient for offline evaluators. It embeds labels, so it is not a product-safe input.

| Record | Required fields | Meaning |
|---|---|---|
| `ExtractionPage` | `source_type`, `source_record_id`, `purpose`, `title`, `content` | One product-safe synthetic source document. `purpose` is `exposure` or `negative_control`. Fields reject blanks and any `persona-####` routing key. |
| `ExtractionSpan` | `data_class`, `start`, `end`, `text` | One exact character occurrence in the answer key. `end` must follow `start`, `text` must equal `content[start:end]`, and password values are forbidden. |
| `ExtractionAnswerKey` | `content_persona_id`, `spans` | Evaluator-only ownership and the sorted, non-overlapping spans for one page. |
| `AnnotatedExtractionPage` | `page`, `answer_key` | The bundled pair; validates that spans sit exactly on the page content. |

The **separated benchmark** splits the same data across two artifacts so products consume only the public projection:

| Record | Required fields | Meaning |
|---|---|---|
| `PublicExtractionCorpus` | `schema_version`, `seed`, `pages` | The product-safe input: `ExtractionPage` objects only, with unique keys and exactly one negative control. Recursively free of answer keys, ownership, and spans. |
| `ExtractionPageAnswer` | `source_type`, `source_record_id`, `answer_key` | One page's evaluator truth, keyed back to its public page by `(source_type, source_record_id)`. |
| `ExtractionAnswerKeyCorpus` | `schema_version`, `seed`, `answers` | The evaluator-only side: `ExtractionPageAnswer` objects with unique keys. |
| `ExtractionBenchmark` | `schema_version`, `seed`, `public`, `answers` | The join. It requires matching seeds, an exact page-key match between public and answers (no missing or extra pages), and that every span sits exactly on its public page content. |

`extraction-golden-v1.json` freezes the annotated bundle. The separately checksummed `extraction-public-golden-v1.json` and `extraction-answer-golden-v1.json` freeze the public projection and its answer key; `EXTRACTION_PUBLIC_SHA256SUMS` and `EXTRACTION_ANSWER_SHA256SUMS` authenticate their exact bytes. Product adapters should load only the public corpus and join truth afterwards.

## Public connection corpus

`PublicConnectionCorpus` schema `1.0.0` is the only connection input intended
for product adapters. Its objects reject unknown fields, sort by opaque UUID,
and contain no persona membership, expected cluster, relationship label, or
other evaluator oracle.

| Record | Required fields | Meaning |
|---|---|---|
| `PublicIdentityRecord` | `id`, `source_type`, `source_url`, `display_name`, `confidence`, `attributes` | One raw observation from a directory, conference, alumni, broker, or social source. It is not a resolved person. |
| `PublicIdentityAttribute` | `kind`, `value`, `confidence` | An observed email, family name, username, fictional phone/address, date of birth, employer, school/year, or reserved social-profile reference. Relationship-tier directory records expose the family name explicitly so downstream family evidence never relies on parsing a display name. |
| `PublicAssociationRecord` | `id`, `kind`, `source_url`, `source_reference`, `target_reference`, `confidence` | One directed public property-adjacency or profile-link observation. Reciprocity requires a separate reverse record. |

`ConnectionAnswerKey` is evaluator-only and physically separate. It maps each
raw record to a truth entity, assigns one of five adversarial pack labels, lists
planted neighbor/social edges with their reciprocal evidence IDs, and labels
the two unilateral negative controls. `ConnectionBenchmark` wraps distinct
`public` and `answer_key` objects for evaluation; product constructors accept
only `PublicConnectionCorpus`.

The frozen `connection-golden-v1.json` contains 18 raw observations for 10
truth entities across common-name, Unicode/diacritics, twins/shared-address,
maiden-name, and alias/misspelling cases. The separately checksummed
`connection-public-golden-v1.json` contains only the product-safe public input,
so evaluators can run and serialize linkage before loading truth.
`CONNECTION_SHA256SUMS` and `CONNECTION_PUBLIC_SHA256SUMS` authenticate their
exact bytes independently of the existing exposure and extraction benchmarks.

## Public breach-risk corpus

`PublicRiskCorpus` schema `1.0.0` is the provider-neutral input for calibrating
the descriptive breach-exposure index. It contains one opaque case per exposure
script and no persona routing ID, identifier value, URL, search match truth,
broker lifecycle, social connection, relationship label, expected score, band,
or factor points.

| Record | Required fields | Meaning |
|---|---|---|
| `PublicRiskCase` | `id`, `breaches` | One opaque synthetic evaluation case. The UUID is stable for a seed but carries no persona identity. |
| `PublicBreachRiskObservation` | `source_record_id`, `occurred_on`, `severity`, `exposed_data` | One opaque breach observation containing only the public facts accepted by the v1 index. Exposed data labels are unique and canonically sorted. |

`RiskAnswerKey` is evaluator-only. Its case truth contains the exact score,
band, and one `BreachRiskFactorTruth` per public observation with independently
checkable severity, data, and total points. `RiskBenchmark` joins the two typed
halves only inside evaluation and rejects missing, extra, or inconsistent cases
and factors.

The formula labelled `breach-exposure-v1` adds severity points (`5`, `10`,
`15`, `20` from low through critical) and fixed data-class points per distinct
label, caps the index at `100`, and maps it to `none`, `low`, `moderate`, `high`,
or `critical`. It is a deterministic descriptive index, not a probability,
forecast, confidence percentage, or comprehensive personal-risk score.

The frozen `risk-public-golden-v1.json` and `risk-answer-golden-v1.json` are
authenticated independently by `RISK_PUBLIC_SHA256SUMS` and
`RISK_ANSWER_SHA256SUMS`. Loaders verify each checksum before parsing and then
reject cross-file seed, case, factor, arithmetic, score, or band drift.

## Agentic identity and delegated authority

The agentic schema `1.0.0` represents a bounded identity and authority world as
an immutable `AgenticWorldSnapshot` plus a strictly ordered tuple of
`AgenticEvent` objects. Event indices are contiguous and one-based; index zero
is the initial snapshot. Every timestamp is UTC and strictly increases.

| Record | Required fields | Meaning |
|---|---|---|
| `Organisation`, `Department` | stable ID, display name, organisation/tenant links | Organisational boundary and Asteria's four departments. |
| `Principal` | ID, kind, display name, optional organisation/department/owner | Organisation, human, service-account, or workload identity. |
| `LogicalAgent` | ID, organisation, accountable owner, optional parent agent | Stable named agent, distinct from any execution. |
| `Runtime` | ID, logical agent, runtime principal, owner, organisation | Concrete executing instance. |
| `Credential` | issuer, subject, allowed runtime principals, validity interval | Public binding metadata only; no credential material is stored. |
| `Resource` | organisation, owner, available actions | Application or tool boundary. |
| `Capability` | resources, actions, scopes, purpose, delegation flag | Task authority. Requested scope must be a subset and purpose must match exactly. |
| `Delegation` | originator, delegator, grantee agent, capability, policy, interval, optional parent | Authority grant; a child must be attenuated within its active parent. |
| `AgenticEvent` | ID, one-based index, UTC time, evidence references, typed payload | Grant, credential issue, runtime spawn, action attempt, revocation, evidence discard, or audit. |

`CanonicalBinding` is evaluator-only truth that keeps the originating
principal, logical agent, runtime ID/principal, credential subject, publicly
attributed actor, and accountable owner chain separate. `AuthorityTruth`
records action-time and audit-time decisions, failures, required delegation
chain and evidence, reconstructability, policy, and expected side effect.

The frozen Asteria package lives under
`src/synthworld/benchmarks/asteria-agentic-v1/`. Its `public/` tree contains
only snapshot/event/tool/scenario inputs. Its physically separate `evaluator/`
tree contains canonical bindings and answers. Both trees have per-file SHA-256
values and a path-bound artifact-set digest. See
[AGENTIC_BENCHMARK.md](AGENTIC_BENCHMARK.md) for the complete layout and replay
semantics.

### Observed action trace

`AgenticTraceSubmission` is serialized as JSONL, one
`ObservedActionTrace` object for each public action event. The event ID is
required. Timestamp, five neutral identity roles, resource/action/scope,
action-time and audit-time decisions, side effect, policy, delegation chain,
owner chain, evidence, and audit-reconstructability fields are nullable. A
missing field is scored as missing and is never filled from evaluator truth.
The deterministic conventions behind the graded delegation-chain,
evidence-reference, and side-effect values are documented in
[AGENTIC_BENCHMARK.md](AGENTIC_BENCHMARK.md) under "Trace conventions".

The agentic scorer independently reports identity-role accuracy,
authorisation precision/recall/F1 and accuracy, temporal validity,
least-privilege/excess-authority measures, delegation-chain integrity,
attribution and owner-chain integrity, provenance completeness, audit
reconstructability, policy version, and side-effect correctness. Case labels
are open strings so other worlds can reuse the generic contract without being
forced to reproduce Asteria's exact case set.

## Trace validation report

Emitted by `synthworld validate agentic-trace` and by
`synthworld.agentic.validate_trace_jsonl`. Independent of the evaluation report:
validation describes a submission's shape and never reads evaluator truth.

`TraceValidationReport`

| field | type | meaning |
|---|---|---|
| `schema_version` | `"1.0.0"` | report contract version |
| `valid` | bool | true when no issue has `severity == "error"` |
| `row_count` | int | rows that parsed and were retained |
| `expected_action_count` | int | action events the benchmark expects |
| `issues` | tuple[`TraceValidationIssue`] | every finding, in discovery order |

`TraceValidationIssue`

| field | type | meaning |
|---|---|---|
| `severity` | `"error"` \| `"warning"` | errors make the report invalid |
| `code` | str | stable identifier; see AGENTIC_BENCHMARK.md for the table |
| `message` | str | human-readable detail |
| `line` | int \| None | 1-based source line, or None for whole-document findings |
| `event_id` | str \| None | subject event, when one could be determined |

Codes are `malformed_json`, `invalid_row`, `duplicate_event_id`,
`unexpected_event_id`, `missing_event_id`, `all_rows_null` (errors) and
`all_null_row`, `no_scored_fields`, `empty_evidence_refs`, `cardinality_unchecked`
(warnings). `valid` is enforced against `issues` by a model validator, so a report
cannot claim validity while carrying an error.

## Evaluation

The evaluation SDK debuts provisional schema version `0.1.0`. A system submits
an oracle-free prediction to the matching evaluator function or the `synthworld
evaluate` CLI; the evaluator loads truth itself and returns an
`EvaluationReport`.

### Threat model

The public/oracle split is an **API-hygiene** guarantee that stops a pipeline
from accidentally scoring against leaked labels — not an anti-cheating measure.
SynthWorld's golden answer keys are committed in this repository, so they are
public; adversarial or competitive evaluation requires benchmarks generated
from held-out private seeds.

Hygiene has a sharper form than "no labelled field appears in public output", and
it is the one to hold generators to: **a public value may depend on the seed and on
the evidence, and never on the label.** Where a generator has a free choice — which
name to use, what order to list things in, which identifier to mint — binding that
choice to truth hands the answer over without ever writing it down. The ambiguity
pack shipped three such channels (pair ordering, name-pool indexing, positional
identifiers), none of which a field-name check could see, and all of which survived
100% branch coverage. Recovering a label *from the evidence* is not a leak; that is
the task.

A held-out *seed* is not a secret. The seed is published inside the artifact, the
generator is public source, and the canonical inputs are in this repository — so an
artifact generated from a deterministic public function of those is recomputable, and
the answer key with it. Measured on the ambiguity variants: rebuilding the substitution
plan from public information alone recovered the disposition on **0.929** of pairs
against a 0.467 baseline, reading no identity evidence.

What a key protects is narrower than "the artifact", and the precise claim is worth
stating: **the serialized seed diversifies surface values but does not conceal them; a
high-entropy unpublished key prevents recomputation of the key-dependent free choices
and the substitution plan; and neither conceals a label that the public evidence
already implies.** A reviewer's structural attacker, reading only attribute kinds and
which of them agree, recovered 450 of 450 dispositions on keyed packs — legitimate
evidence under this threat model, and the reason the sentence needs its third clause.

The mechanism is a **key**: `generate_ambiguity_variant(seed=..., key=...)`
takes a byte string that is never serialized. The same attack against a keyed pack
scores 0.080 — and that number is a *recovery* rate, not an accuracy: without the key
the decoder can produce an answer for only about a fifth of pairs and is right on 8% of
all of them. It is not "worse than guessing"; it is a decoder that mostly cannot answer,
which is what closing the channel looks like. Published packs use the empty key and are byte-identical to unkeyed
output, which is correct — their answer keys ship here, so they claim no secret and
remain auditable. Generate evaluation packs with a key you do not publish.

**Evaluation-key custody.** The keys in this repository's tests and published packs
(`b""`, `b"held-out-key"` and similar) are deliberately public and claim no secrecy;
their packs are auditable precisely because anyone can regenerate them. A key used for a
*real* evaluation is a secret, and it is governed:

- **Generation**: at least 256 bits from a CSPRNG (`secrets.token_bytes(32)`); never a
  phrase, never derived from the seed.
- **Storage**: outside the repository, in a secret store; injected into CI or harnesses
  as masked ephemeral environment material. The Gitleaks scan in CI is a backstop, not
  the mechanism.
- **Scope and rotation**: one key per evaluation campaign. Scores are comparable only
  within a key; rotating starts a new comparison, and that is the point of rotating.
- **Never serialized**: no key bytes, key digests, or key-derived identifiers in
  artifacts, receipts, or logs. Key recovery yields every latent draw and therefore
  every answer — it voids the evaluation, not just weakens it.

Held-out private seeds are necessary for competitive evaluation but not always
sufficient. A seed protects surface values. Where a pack's case list is fixed and
each case is defined by its evidence pattern — as in the ambiguity pack, whose
scenarios appear exactly once each — the label remains derivable from the repository
alone, whatever the seed. Read each pack's own section for what its seeds do and do
not conceal.

**Reading v1 results at the right size.** Keyed v1 variants vary *surfaces*, not
structure: every variant contains the same fifteen scenario pairs re-skinned. A run over
fifty variants is therefore evidence about **fifteen structural cases**, deterministically
replicated — not about 750 independent problems — and should be reported at that size.
Structural cross-seed variation is what v2 adds.

#### Ambiguity v2: what a held-out seed conceals

That last paragraph states a limit of the v1 construction rather than of seeds, and
`ambiguity_v2_generator` is the answer to it. There is no case list. Each pair samples
whether the two records are one person, draws every comparison from the Fellegi–Sunter
`m`/`u` row that fact implies, and *derives* the disposition with `disposition_of` —
the same published rule a solver is invited to use. `DerivedPairTruth` refuses to
construct if the two disagree, so the label has no independent existence for a free
choice to be bound to.

Stated precisely, for a pack generated with an unpublished key:

- **Concealed:** every rendered value, every record identifier, the pair count, the
  prevalence of true matches, per-pair completeness, and the distractor count. All are
  keyed draws, and `generate_ambiguity_v2_pack` has no default key — a partially keyed
  generator reads as protected while call sites quietly fall back to `b""`.
- **Not concealed, by design:** the scoring rule. `disposition_of`, the `m`/`u` table
  and the thresholds are public. A solver that recovers the relations from the rendered
  values and applies the rule *should* score perfectly; that is the task, not a leak.
- **Not claimed:** that `same_entity` is recoverable from the evidence. It often is not,
  and that is the point — see below.

**What v2 does and does not measure — read this before using it.** The *construction*
is sound and measured: labels derive from evidence, metadata carries nothing (a
metadata-only attacker scores at chance), and class balance is asserted. Since #80 the
*surfaces* are no longer placeholders. Each kind draws a base from a pool arranged in
**confusable clusters** (`Sorensen`/`Sorenson`/`Soerensen`, one phone line with two
digits transposed, a day and a month swapped); `EQUAL` and `NEAR` share the base while
`FAR` redraws from a stationary mixture that lands inside the cluster with probability
`w`. Every rendered value then passes through one **structured-noise operator** —
transposition, deletion, doubling, keyboard slip, transliteration/nickname variant, or
nothing — applied per side, identically under every relation, so `FAR` pairs sit in the
same edit neighbourhoods as `NEAR` pairs. Recovering the *identity* is free and
expected — a public deterministic pool is enumerable and inversion is a lookup — but it
does not recover the *relation*, which is carried by overlapping distance distributions.

The difficulty is therefore not claimed but **computed**: the pack publishes its
**genie floor**, the Bayes error of the generator itself — the accuracy of an optimal
solver holding the public law, the observed comparable structure and the true
prevalence. It is estimated with a stated method and N, with a Wilson confidence
interval, and keyed to a digest of every decision-relevant constant, so any parameter
move invalidates the number loudly. An accuracy is only readable against that ceiling:
a score at `1 − floor` has read all the evidence there is, and a score above it is
exploiting signal the model says should not exist. The enumerated channel invariants —
stationarity of the `FAR` kernel, an identical one-value marginal under every relation,
a per-base sibling-landing mass above the gate, form bijectivity/separation, and the
artifact-factorization check — are asserted in the suite rather than sampled, and the
technique premium (the gap between the ceiling and the best solver that only ever sees
per-kind normalised exact match) is gated to stay positive, so real resolution technique
is rewarded rather than anti-taught.

One clarification the earlier failures made precise, and the design now leans on: **a key
conceals which sample was drawn, never the law.** Keying prevents recomputation of
metadata free choices; it cannot make published evidence harder to decode, because the
generator, pools and format strings are public source and the reachable value set is
enumerable offline. Difficulty therefore comes from the overlap geometry and the noise
law, and is quantified by the floor rather than asserted.

Two consequences worth stating plainly. **`disposition` and `same_entity` are allowed
to differ.** The disposition is what the public evidence justifies; `same_entity` is
what is true. v1 forbade the difference, which is why it could not represent two people
who are identical on paper. Scoring is against the disposition; a benchmark scored
against `same_entity` where the evidence cannot reach it is measuring clairvoyance.

**Measured.** A decoder holding only the kind-level fingerprint — which kinds are
present and which agree — recovered the v1 disposition on 750 of 750 pairs across fifty
seeds, because every fingerprint was a scenario and every scenario had one hand-written
answer. Against v2, trained on sixty public-key seeds and scored on held-out seeds under
a held-out key with a majority-class fallback, the same decoder scores **0.694** against
a 0.488 majority baseline, and **0.840** on the 67.6% of pairs whose fingerprint it has
seen before. What it keeps is legitimate — agreement patterns really do predict identity
— and what it loses is the distinction v1 could not express, between a reformatted phone
number and a different person's.

**Class balance.** The three dispositions hold roughly 38% `merge`, 53% `separate` and
**9%** `insufficient`, and fewer than 1% of packs are missing a class entirely. Both are
asserted rather than hoped for: every class must hold at least 8% of the mass, and at most
2% of packs may lack one.

That gate exists because the middle class was starving. It held 7.6% of pairs and **8.5%
of individual packs contained none at all**, so one pack in twelve was a two-class
benchmark wearing a three-class enum — while the test suite stayed green, because it only
asked that each class appear *somewhere* across many seeds. The fix was Fellegi–Sunter's
own: the decision is three-way, and the middle region is sized by the error rates you will
tolerate rather than left over between two hand-picked thresholds. Decision now needs 16:1
odds, and packs carry 50–90 pairs rather than 18–44, because whether a pack contains all
three classes is a sample-size question as much as a threshold one.

One known weakness remains, tracked as **#79**: the `m`/`u` table was estimated over v1's
non-match population, which is deliberately households, twins and classmates. v2 samples
from that same table, so the pack and its scoring rule agree by construction, but the
numbers still lean on names — the two name kinds alone give the same answer on **59.3%**
of pairs. That figure was 86.8% before the decision threshold moved, so the symptom is
much reduced, but the cause is untouched: Fellegi–Sunter parameters belong to a
population, and sharing one table across two is the thing to fix.

### Scorer inputs (Prediction schemas)

| Task | Prediction schema | Required fields | Meaning |
|---|---|---|---|
| Exact-span extraction | `ExtractionPredictionSet` | `schema_version`, `predictions` | A list of `ExtractionPagePrediction` each containing `source_type`, `source_record_id`, and a list of `PredictedSpan` (`data_class`, `start`, `end`). |
| Entity resolution | `EntityResolutionPrediction` | `schema_version`, `clusters` | A list of partition clusters where each cluster is a list of public identity record UUIDs. All public records must be partitioned exactly. |
| Relationship inference | `RelationshipPrediction` | `schema_version`, `edges` | A list of `PredictedRelationship` (`source_record_id`, `target_record_id`, `kind`, `evidence_association_ids`). |
| Risk calibration | `RiskPrediction` | `schema_version`, `cases` | A list of `RiskCasePrediction` (`case_id`, `band`, and optional `score`, `band_probabilities`). Score and probabilities must be provided for either every case or none. |
| Agentic authority | `AgenticTraceSubmission` (JSONL rows) | one `ObservedActionTrace` per action event | Nullable identity-role, decision, attribution, owner, delegation, evidence, reconstructability, policy, and side-effect observations. |

All prediction schemas are Pydantic models supporting `.model_validate_json(text)` for parsing and validation.

### Evaluation outputs

| Model | Required fields | Meaning |
|---|---|---|
| `EvaluationReport` | `schema_version`, `scoring_version`, `task`, `seed`, `persona_count`, `benchmark_version`, `checksum_scheme`, `artifact_checksums`, `metrics`, `slices` | The uniform scored result of a task prediction set against separate truth. |
| `TaskMetric` | `name`, `value`, `support`, `family`, `support_meaning` | One named scalar metric. A `null` value marks the metric undefined for that score. |
| `FailureSlice` | `dimension`, `value`, `outcome`, `count`, `support` | A counted slice of where the system failed (e.g. `data_class` missed, or `adversarial_pack` false merge/split) for error analysis. |

### Error handling
- `EvaluationInputError`: Raised (inheriting from `ValueError`) if the submission is malformed or invalid for the benchmark (e.g. partitioning incorrect records, or missing case IDs), rather than merely scoring poorly.
- Pydantic's `ValidationError` is raised if predictions violate the schema.
