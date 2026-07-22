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
