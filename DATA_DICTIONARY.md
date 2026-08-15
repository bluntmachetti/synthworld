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
reconstructability, policy version, and side-effect correctness. The provenance
and audit-reconstructability metrics compare reported reference labels and a
reported reconstructability claim with evaluator truth; they do not verify that
the underlying evidence was retained. Case labels are open strings so other
worlds can reuse the generic contract without being forced to reproduce
Asteria's exact case set.

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

## Enterprise identity and access universe

The enterprise tranche is versioned independently of the schema `1.0.0` stated at the top of
this document. Every constant named below is pinned in source; nothing resolves an ambient
latest. Contract-level prose lives in
[`enterprise-identity-access-contract/README.md`](enterprise-identity-access-contract/README.md);
this section is the schema reference for it.

**How to read the tables in this block.** The **Key fields** column lists the fields that define
each record. It is *not* the pydantic-required set: almost every model in this block defaults
`schema_version`, `compiler_version`, and `synthetic`, and several models default every field
they have. Where required-ness is load-bearing it is stated in the Meaning column. (The tables in
the earlier sections of this document use a `Required fields` column; the different header here is
deliberate.)

Two base classes divide the tranche and the division is load-bearing.
`SyntheticModel` is frozen, forbids unknown fields, and carries `synthetic: true`; every
*generated* record inherits it. `EnterpriseOperatorModel` is frozen, strict, and forbids unknown
fields but carries **no** `synthetic` marker; every *operator-authored* record inherits it.
Importing a real organisation's structure does not make the import synthetic, and the scaffold
CLI says so: `Importing structure is not anonymisation; protect the source and namespace salt.`

`LogicalKey` is the operator-facing key type: NFC-normalised, non-empty, unpadded, at most 256
UTF-8 bytes, and it rejects anything matching an email address (`person_level_email_forbidden`).

### Import contract

| Record | Key fields | Meaning |
|---|---|---|
| `EnterpriseIdentityAccessImportV1` | `schema_version`, `blueprint`, `iam_universe_extension`, `directory_rbac_state` | The top-level authored import. Each of the three parts is independently versioned. |
| `EnterpriseIdentityAccessBlueprintV1` | `blueprint_key`, `id_namespace_salt`, `tenants`, `organisations`, `units`, `populations`, `groups`, `roles`, `resource_sets`, `principal_access_atom_rules` | Structure only. `id_namespace_salt` matches `^[0-9a-f]{64}$` and is the operator's secret. Only the first four are required; `tenants` and `organisations` each carry `min_length=1`, and every template tuple defaults to empty. |
| `EnterpriseIamUniverseExtensionV1` | `schema_version` | Adds `account_allocations` and `account_access_atom_rules`; both default empty. |
| `EnterpriseDirectoryRbacStateInputV1` | `schema_version` | Observed directory state: `account_observations`, `memberships`, `group_nesting`, `group_role_assignments`, `population_role_assignments`, `role_hierarchy`, `role_grants`, `direct_entitlements`; all default empty. |
| `SelectorV1` | `kind` | Discriminated union of `AllSelectorV1` (`all`), `CountSelectorV1` (`count`, `count > 0`), and `FractionSelectorV1` (`fraction`, `numerator > 0`, `denominator > 0`). A fraction must satisfy `numerator <= denominator` and be fully reduced (`gcd == 1`), else `selector_fraction_out_of_range` / `selector_fraction_not_reduced`. |
| `EnterpriseImportDiagnosticV1` | `code`, `message`, `remediation_hint` | Those three are required and each carries `min_length=1` — a diagnostic cannot be raised without a remediation hint. `file`, `row` (`>= 1`), `column`, `logical_key`, `measured`, `allowed` are optional and default to null. |
| `EnterpriseIdentityAccessValidationReportV1` | `valid`, `diagnostics` | `valid` is the only required field. A model validator enforces `valid` XOR `diagnostics` (`validation_status_mismatch`), so a report cannot claim validity while carrying a finding. |

Population, group, role, unit, and resource-set templates are the authored generators
(`PopulationTemplateV1` carries a `population_kind` and a `count > 0`; `ResourceSetTemplateV1`
carries a `target_kind`, an `instance_count > 0`, and at least one action).

Closed vocabularies: `UnitKind` (`division`, `department`, `team`); `PrincipalKind`
(`employee`, `contractor`, `supplier`, `partner`, `service`, `workload`, `agent`); `AccountKind`
(`workforce`, `service`, `workload`, `agent`); `TargetKind` (`application`, `api`, `tool`,
`data_store`, `environment`); `AdministrativeState` (`active`, `suspended`, `disabled`);
`AccessSubjectKind` (`principal`, `account`); `RelationshipAnchorKind` (`principal`, `account`,
`group`, `unit`, `authorization_target`).

Authoring formats are one YAML envelope, one JSON envelope, or the exact 20-file CSV bundle
(`CSV_HEADERS`), of which seven files are mandatory (`blueprint.csv`, `tenants.csv`,
`organisations.csv`, `universe_extension.csv`, `directory_rbac_state.csv`,
`principal_access_atom_rules.csv`, `account_access_atom_rules.csv`). YAML is a restricted
JSON-compatible subset: aliases, non-JSON tags, non-string mapping keys, and duplicate keys are
rejected. **The CSV and ZIP readers cannot express `account_observations` or
`direct_entitlements` at all** — the CSV document builder hard-codes both to empty lists and no
such member exists in the allowlist. Those two record families are reachable only through YAML
or JSON.

### Compiled universe and canonical binding truth

| Constant | Value |
|---|---|
| `ENTERPRISE_IMPORT_SCHEMA_VERSION`, `ENTERPRISE_BLUEPRINT_SCHEMA_VERSION`, `ENTERPRISE_UNIVERSE_EXTENSION_SCHEMA_VERSION`, `ENTERPRISE_DIRECTORY_RBAC_STATE_SCHEMA_VERSION` | `1.0.0` |
| `ENTERPRISE_UNIVERSE_SCHEMA_VERSION`, `ENTERPRISE_CANONICAL_BINDING_SCHEMA_VERSION` | `1.0.0` |
| `ENTERPRISE_COMPILER_VERSION`, `ENTERPRISE_SELECTOR_ALGORITHM_VERSION` | `1.0.0` |
| `ENTERPRISE_SERIALIZATION_VERSION` | `canonical-json-v1` |

| Record | Key fields | Meaning |
|---|---|---|
| `EnterpriseIdentityAccessUniverseV1` | `schema_version`, `compiler_version`, `selector_algorithm_version`, `seed`, and twelve record tuples | The public artifact: `tenants`, `organisations`, `units`, `principals`, `accounts`, `access_subjects`, `groups`, `roles`, `authorization_targets`, `permissions`, `relationship_anchors`, `access_atoms`. |
| `AccessAtomV1` | `access_atom_id`, `subject_id`, `authorization_target_id`, `action` | One declared feasible (subject, target, action) triple. The inventory is frozen here and no later stage may add to it. |
| `EnterprisePermissionV1` | `permission_id`, `authorization_target_id`, `action` | A target/action pair, independent of any subject. |
| `EnterpriseRelationshipAnchorV1` | `anchor_id`, `tenant_id`, `entity_kind`, `entity_id` | An addressability stub only. It carries no relation type and no edges; ReBAC tuples live in the ReBAC overlay. |
| `EnterpriseCanonicalBindingTruthV1` | `schema_version`, `identity_access_universe_digest`, `bindings` | **Evaluator-only.** `bindings` is a tuple of `EnterpriseCanonicalAccountBindingV1` (`account_id`, `principal_id`) and the digest binds the exact public universe it was compiled against. |
| `SyntheticDigestV1` | `algorithm`, `value` | `algorithm` is the literal `sha256`; `value` matches `^[0-9a-f]{64}$`. The digest type for published artifacts across the tranche. `EnterprisePrivateCompilationReceiptV1` is the exception: its `blueprint_semantic_digest` and `source_artifact_set_digest` are plain `str` constrained by the same `^[0-9a-f]{64}$` pattern. |
| `EnterpriseArtifactDescriptorV1` | `path`, `schema_version`, `digest`, `byte_size` | One file's binding inside a visibility manifest. |
| `EnterpriseArtifactManifestV1` | `schema_version` (`1.0.0`), `visibility`, `artifacts` | `visibility` is the literal `public` or `evaluator`. This is the per-tree `manifest.json` used by every export in the tranche. |
| `EnterpriseIdentityAccessCompileConfigV1` | `budget`, `outer_safety` | Both default, so the whole config is optional. `EnterpriseIdentityAccessCompileBudgetV1` has 30 fields; `EnterpriseCompileOuterSafetyV1` has 5. Each is user-settable downward and hard-capped, raising `compile_budget_hard_ceiling:<field>` or `outer_safety_hard_ceiling:<field>`. |
| `EnterprisePrivateCompilationReceiptV1` | `schema_version` (`1.0.0`), `publication_consent`, `blueprint_semantic_digest`, `source_artifact_set_digest` | Lets an operator publish digests of a private blueprint and source-file set. `publication_consent` is `Literal[True]`; the builder refuses without it. |

`EnterpriseIdentityAccessCompileResultV1` is a frozen dataclass holding the public universe and
the evaluator binding truth. It is an in-memory split and **is never serialized as one file**.

**Public vs evaluator truth.** `export_enterprise_identity_access_compile_result` writes exactly
four files and refuses to run if the output root already exists:

| Path | Model | Visibility |
|---|---|---|
| `public/identity-access-universe.json` | `EnterpriseIdentityAccessUniverseV1` | product-safe |
| `public/manifest.json` | `EnterpriseArtifactManifestV1(visibility="public")` | product-safe |
| `evaluator/canonical-binding-truth.json` | `EnterpriseCanonicalBindingTruthV1` | evaluator-only |
| `evaluator/manifest.json` | `EnterpriseArtifactManifestV1(visibility="evaluator")` | evaluator-only |

### C08 v2 frozen-artifact candidates

| Artifact | Schema version | Visibility | Meaning |
|---|---|---|---|
| `asteria-agentic-c08-v2/manifest.json` | `2.0.0` | root | Four-child exact inventory and public/evaluator/root digest cross-bindings. |
| `asteria-agentic-c08-v2/public/c08-asteria-public.json` | `2.0.0` | public | Actions, `(kind, binding_handle)` requirements, and opaque observations with same-kind distractors. |
| `asteria-agentic-c08-v2/public/manifest.json` | `2.0.0` | public | One-payload public inventory and artifact-set digest. |
| `asteria-agentic-c08-v2/evaluator/c08-asteria-evaluator.json` | `2.0.0` | evaluator | Exact observation bindings and scenario labels, bound to public bytes. |
| `asteria-agentic-c08-v2/evaluator/manifest.json` | `2.0.0` | evaluator | One-payload evaluator inventory, artifact-set digest, and public-input digest. |
| `enterprise-agentic-c08-v2/manifest.json` | `2.0.0` | root | Independent public/evaluator payload inventories and public-input binding. |
| `enterprise-agentic-c08-v2/SHA256SUMS` | n/a | root | Sorted path-bearing hashes for manifest and both payloads; excludes itself. |
| `enterprise-agentic-c08-v2/public/public-input.json` | `2.0.0` | public | Actions, binding-handle requirements, separately derived opaque observation IDs, and same-kind distractors. |
| `enterprise-agentic-c08-v2/evaluator/truth.json` | `2.0.0` | evaluator | Exact observation-ID, handle, tenant, and action bindings. |

Asteria uses independent frozen root/public/evaluator manifest schemas. Its
visibility artifact sets contain only their payload; its root artifact set includes
both payloads and both visibility manifests and excludes only root manifest.
Enterprise uses one independent frozen manifest schema and has no visibility
manifests or aggregate artifact-set digest. Its `SHA256SUMS` excludes itself.

`C08EvidenceRequirementV2` carries kind plus binding handle. The corresponding
public observation model carries action semantics, an opaque observation ID, and
the handle. Same-kind distractors make kind-only matching insufficient while one
handle match keeps the public task deterministically solvable. The evaluator keeps
the exact required IDs. Packaged loaders reject integrity-valid alternate seeds by
comparing parsed models and bytes with fixed seed `20260809` generation.

Exactly two aggregate baseline files live under `tests/fixtures/c08_v2/`, one per
lineage. They contain public/submission digests and denominator-bearing metrics,
but no submission rows, observations, IDs, outcomes, or evaluator truth. Reports
carry an offline measurement scope and do not prove live retention, durable
logging, enforcement, deployment, or EADS compatibility. Repository verification
and candidate registry/capability checks have passed; external publication evidence
remains pending. See `GOLDEN_REVIEW.md`.

The withheld fact is precise: `EnterpriseAccountV1` publishes `account_id`, `tenant_id`,
`authorization_target_id`, and `account_kind` but **no `principal_id`**. Recovering the
account-to-principal binding is the task, and that mapping exists only in the evaluator tree.
The public universe also contains no `id_namespace_salt`, no `blueprint_key`, and no operator
logical key; every identifier is an opaque UUIDv5 and every display label is a generated
placeholder such as `Example Access Role 001`. The compiled `access_atoms` inventory *is*
public — it is the declared feasible space, not a decision label.

The split is physical, not a flag. Each loader requires its directory to contain exactly its
two expected files as regular files, requires the manifest's declared `visibility` to match,
re-verifies path, `schema_version`, `byte_size`, and sha256 against the bytes on disk, and
rejects any file whose bytes differ from the canonical serialization of what was parsed. There
is no API that loads both trees together.

**Determinism.** Every identifier is
`uuid5(namespace, encode_parts(blueprint_namespace, *components))`, where
`blueprint_namespace = uuid5(BLUEPRINT_NS, schema_version + id_namespace_salt)`. The seed enters
exactly two places: the `seed` field recorded on the universe, and the ranking hash inside slot
selection (`select_principal_slot_indices`). Whether an identifier survives a seed change
therefore depends on whether a selector chose its subject, and the split is not the one you might
assume:

- **Seed-independent**, because their components are purely authored logical keys: `tenants`,
  `organisations`, `units`, `principals`, `groups`, `roles`, `authorization_targets`,
  `permissions`. Changing the seed or adding an unrelated template does not remap these.
- **Seed-sensitive**: `accounts`, because `account_id` embeds the selected principal slot index;
  and therefore `access_subjects`, `relationship_anchors`, and `access_atoms`, each of which
  embeds an account ID whenever the subject is an account. Access atoms declared against
  *principals* keep a stable ID for a given `(subject, target, action)` triple, but their
  **membership** in the inventory still moves with the seed whenever the rule's selector picks a
  proper subset of a population.

Compiling the shipped reference import at seeds 11 and 12 shows this directly: tenants,
organisations, units, principals, groups, roles, authorization targets, and permissions are
identical, while `accounts` (4), `access_subjects` (10), `relationship_anchors` (16), and
`access_atoms` (16) each differ, with a symmetric difference of 4 in every case. Do not describe
the access-atom inventory as seed-stable.

Canonical JSON is `sort_keys=True`, `separators=(',', ':')`, `ensure_ascii=False`,
`allow_nan=False`, plus a single trailing newline.

**Not implemented, stated plainly.** Two compile-budget fields, `max_scenario_deltas` and
`max_temporal_events`, are declared with defaults and ceilings but are read by no code path in
`src/`; nothing measures scenario deltas or temporal events against them. The top-level
compiler enforces ten of the 30 budget fields; the rest are enforced (or not) by downstream
subpackages. `EnterprisePrivateCompilationReceiptV1` and its builder are implemented and tested
but wired into no CLI command and into no export — no shipped command emits one. `blueprint_key`
is validated but never read by the compiler or by any ID derivation; only `id_namespace_salt`
feeds the namespace.

CLI entry points are `synthworld scaffold-enterprise-access`,
`synthworld validate-enterprise-access`, and `synthworld compile-enterprise-access`. Nothing in
`synthworld.enterprise` is re-exported from the top-level `synthworld` package; import it
explicitly.

**No benchmark family consumes an operator-compiled universe.** `compile-enterprise-access`
compiles an operator blueprint and writes the four-file split, and that is where it stops. Each
of the enterprise `generate-*` commands — `generate-enterprise-agentic`,
`generate-contextual-access`, and `generate-continuous-assurance` — builds a built-in reference
pack from the shipped reference sources rather than from anything you compiled; the
enterprise-agentic and identity-fabric reference builders additionally call an internal
`_require_frozen_*_inputs` guard that raises unless the universe and corpus bytes hash to the
pinned reference digests. Compiling your own organisation's structure and then benchmarking
against it is not a supported path today.

### Pinned standards profile ledger

`StandardsProfileLedgerV1` (`STANDARDS_PROFILE_LEDGER_SCHEMA_VERSION` `1.0.0`) is a single dated
snapshot, not a live lookup. Every entry's `reviewed_on` must equal
`STANDARDS_PROFILE_REVIEW_DATE` = `2026-08-04` or the model raises
`standards_review_date_mismatch`. `authoritative_uri` must begin `https://`, and duplicate
`source_id` or duplicate `(profile_id, profile_version)` bindings are rejected.
`StandardsProfileCategory` is `normative_standard`, `government_reference`, `research`,
`implementation_model`, `community_work`, `test_method`; `StandardsProfileStatus` is `final`,
`reaffirmed`, `draft`, `expired`, `research`, `implementation`.

The shipped ledger has exactly eleven entries:

| `source_id` | `selected_profile_id` | Version | Category / status |
|---|---|---|---|
| `authzen-authorization-api-1.0` | `synthworld-authzen-projection` | `1.0.0` | normative standard / final |
| `incits-359-2012-r2022` | `synthworld-directory-rbac` | `1.0.0` | normative standard / reaffirmed |
| `nist-sp-800-162-2019` | `synthworld-bounded-abac` | `1.0.0` | government reference / final |
| `nist-sp-800-192-2017` | `synthworld-policy-test-coverage` | `1.0.0` | test method / final |
| `openfga-authorization-model-schema-1.1` | `synthworld-openfga-projection` | `1.0.0` | implementation model / implementation |
| `openid-aiim-mcp-interop-2026-07-14` | `synthworld-aiim-scenario-tags` | `0.1.0-experimental` | community work / **draft** |
| `openid-caep-1.0-final` | `synthworld-caep-projection` | `1.0.0` | normative standard / final |
| `openid-ssf-1.0-final` | `synthworld-shared-signals-projection` | `1.0.0` | normative standard / final |
| `rfc-7643` | `synthworld-scim-core-projection` | `1.0.0` | normative standard / final |
| `rfc-7644` | `synthworld-scim-protocol-projection` | `1.0.0` | normative standard / final |
| `zanzibar-usenix-atc-2019` | `synthworld-bounded-rebac` | `1.0.0` | research / research |

Two entries need care when quoting them. `openid-aiim-mcp-interop-2026-07-14` is a dated
community snapshot at an experimental profile version; it must not be presented as a normative
standard. `openfga-authorization-model-schema-1.1` is a vendor implementation model, not a
ratified specification. Ledger membership is a *pin*, not a claim of working behaviour: the
`synthworld-shared-signals-projection` and `synthworld-scim-protocol-projection` entries are
discussed under "Standards projections" below, where the gap between the pin and the shipped
code is stated.

## Bounded authorization oracles

Four packages compile a frozen-corpus, offline authorization oracle over the universe above.
Every compiler is digest-bound — each input must carry the exact universe, corpus, config, or
kernel digest, and mismatches raise a typed compile error — and no stage may add an entity,
atom, context, request, or cell. All schema and compiler constants in this section are `1.0.0`.

### Evaluation corpus

| Record | Key fields | Meaning |
|---|---|---|
| `EnterpriseEvaluationCorpusV1` | `schema_version`, `compiler_version`, `identity_access_universe_digest`, `corpus_config_digest`, `compile_config_digest`, `evaluation_cell_digest`, `contexts`, `session_slots`, `role_activation_requests`, `evaluation_cells`, `access_requests` | The **public** corpus. `contexts`, `evaluation_cells`, and `access_requests` each require at least one member; the compiler forms no implicit Cartesian product. |
| `AccessEvaluationCellV1` | `cell_id`, `access_atom_id`, `context_id`, `session_state_id`, `tick` | One frozen evaluation cell. `session_state_id` is nullable; `tick` is the existing integer logical clock. |
| `EnterpriseEvaluationCaseInventoryV1` | `schema_version`, `evaluation_corpus_digest`, `cases` | **Evaluator-only.** `EnterpriseEvaluationCaseV1` carries `case_id`, `target_kind` (`access_cell` or `activation_request`), `target_id`, and at least one open-string label. |

Corpus constants: `ENTERPRISE_CORPUS_CONFIG_SCHEMA_VERSION`, `ENTERPRISE_CORPUS_SCHEMA_VERSION`,
`ENTERPRISE_CORPUS_COMPILER_VERSION`, `ENTERPRISE_EVALUATOR_CASE_SCHEMA_VERSION`.

### Directory and RBAC

| Record | Key fields | Meaning |
|---|---|---|
| `EnterpriseDirectoryRbacKernelV1` | `schema_version`, `compiler_version`, `identity_access_universe_digest`, `directory_rbac_state_input_digest`, `compile_config_digest`, plus eight state tuples | **Public** observed/actual directory state: `account_observations`, `memberships`, `group_nesting`, `group_role_assignments`, `subject_role_assignments`, `role_hierarchy`, `role_grants`, `direct_entitlements`. |
| `EnterpriseDirectoryRbacIntentOverlayV1` | `schema_version`, `identity_access_universe_digest`, `evaluation_corpus_digest` | Declared intent: `birthright_rules`, `approved_exceptions`, six `intended_*` relation tuples, `ssd_constraints`, `dsd_constraints`. All default empty. |
| `EnterpriseRbacSessionStateInputV1` | `schema_version`, `evaluation_corpus_digest` | Observed role-activation sessions. A `rejected` session may not carry activated roles. |
| `CompiledEnterpriseDirectoryRbacTruthV1` | `schema_version`, `compiler_version`, plus fourteen truth collections | **Evaluator-only.** Membership paths, authorized role paths and sets, actual and intended derivation paths, birthright predicate/eligibility/assignment rows, approved exceptions, SSD and DSD evaluations, activation decisions, observed sessions, and per-cell truth. |
| `DirectoryRbacCellTruthV1` | `birthright_decision`, `intended_decision`, `effective_decision`, `final_decision`, `reconciliation`, `binding_status`, `lifecycle_status`, plus the supporting ID tuples | The four-decision algebra per cell. |
| `EnterpriseDirectoryRbacMetricsV1` | `schema_version`, `directory_rbac_truth_digest`, `metrics` | The scored report. |
| `EnterpriseDirectoryRbacPredictionV1` | `schema_version` | The scorer input. |

The decision algebra is fixed. Birthright `B` allows when an active birthright assignment covers
the cell's atom. Intended `I` allows on an active birthright assignment, an active approved
exception, or an intended derivation path. Effective `E` allows on any actual derivation path.
Final `F` allows only when `E` allows **and** `binding_status` is `not_applicable` or
`matches_canonical` **and** `lifecycle_status` is `not_applicable` or `active`. Reconciliation
is computed from intended against effective and never from final: intended allow yields
`aligned_allow` or `missing`; intended deny yields `excessive` or `aligned_deny`.

`BindingStatus` is `not_applicable`, `matches_canonical`, `missing`, `mismatch`.
`LifecycleStatus` is `not_applicable`, `active`, `inactive`, `not_yet_valid`, `expired`.
`DerivationMechanism` is `direct_entitlement` or `role`. All validity intervals are half-open
`[valid_from_tick, valid_until_tick)`.

Two facts about the overlays are easy to get wrong. `ApprovedExceptionReason` (`business_need`,
`emergency`, `migration`, `remediation_pending`) is validated and carried but the compiler never
reads it; only the validity window affects any decision, and no metric is keyed on it. Approved
exceptions widen the intended layer only — they never create effective access and never appear
in `effective_path_ids`. Separately — and note that **two distinct classes are named
`EmploymentTypeIsV1`**, one in `enterprise.abac.models` and one in `enterprise.rbac.models` — the
*RBAC birthright* `EmploymentTypeIsV1` resolves against the principal's `principal_kind`, not
against any employment attribute. `EmploymentType` has only `employee`, `contractor`, `supplier`,
and `partner`, so `service`, `workload`, and `agent` principals can never satisfy it. The
identically named ABAC predicate is a separate class; this quirk is not a statement about it.

### ABAC and ReBAC overlays

| Record | Key fields | Meaning |
|---|---|---|
| `EnterpriseAbacStateOverlayV1` / `EnterpriseAbacIntentOverlayV1` | `schema_version` plus the bound universe and corpus digests | **Public** attribute facts and flat rules for the actual and intended layers. |
| `AbacRuleV1` | `rule_id`, `revision_id`, `effect`, `operator`, `cell_ids`, `predicates`, validity window | Rules are flat: `FlatRuleOperator` is `all` or `any` only. Schema cap is 64 predicates per rule; the default compile limits cap 64 rules per overlay and 16 predicates per rule. |
| `CompiledEnterpriseAbacTruthV1` | `schema_version`, `compiler_version`, `attribute_facts`, `predicate_truth`, `rule_truth`, `cells` | **Evaluator-only.** |
| `EnterpriseRebacStateOverlayV1` / `EnterpriseRebacIntentOverlayV1` | `schema_version` plus bound digests | **Public** relation tuples, rules, and `unknown_evidence_cell_ids`. |
| `CompiledEnterpriseRebacTruthV1` | `schema_version`, `compiler_version`, `relation_tuples`, `paths`, `rule_truth`, `cells` | **Evaluator-only.** `RebacPathTruthV1.tuple_ids` is capped at 2 by schema. |

The ABAC vocabulary is closed: thirteen typed `AttributeFactV1` members over twelve attribute
keys, and eleven named predicates (`subject_kind_is`, `employment_type_is`, `same_tenant`,
`subject_unit_is`, `subject_unit_owns_target`, `target_kind_is`,
`classification_within_clearance`, `action_is`, `action_class_is`, `assurance_at_least`,
`network_zone_is`). There is no arbitrary attribute key, no nesting, no negation, no obligation,
and no executable policy text. Three-valued combination is explicit: under `all`, any `false`
gives `false`, else any `unknown` gives `unknown`; under `any`, any `true` gives `true`, else any
`unknown` gives `unknown`. Rule combination is deny-overrides, and a conflict flag is set only
when both allow and deny are present.

ReBAC is equally closed and **has no userset or rewrite engine**. There are four relations
(`member_of`, `owns`, `manages`, `collaborates_on`) and exactly three path templates
(`DirectSubjectRelationV1`, `GroupCollaborationV1`, `ManagerOfOwnerV1`) with a maximum path length
of two tuples (`RebacPathTruthV1.tuple_ids` is `min_length=1, max_length=2`). A two-hop path requires both tuples to share one `snapshot_id`, so cross-snapshot
chains are not derivable. Where no path is found and the cell is listed in
`unknown_evidence_cell_ids`, the outcome is `unknown` rather than `not_applicable`.

Overlapping revisions are hard errors in both packages, not last-write-wins.

### Composition and compiled access state

| Record | Key fields | Meaning |
|---|---|---|
| `EnterpriseAuthorizationCompositionV1` | `identity_access_universe_digest`, `evaluation_corpus_digest`, `directory_rbac`, `abac`, `rebac` | **Public.** Typed schema-version and digest references only; it never inlines a component payload. `directory_rbac` is required, `abac` and `rebac` default to null. |
| `AuthorizationEvaluationProfileV1` | `evaluation_corpus_digest`, `cells` | **Public.** Binds one closed profile to every frozen cell exactly once. |
| `EnterpriseAuthorizationKernelV1` | universe/corpus/composition/profile digests, `cells` | **Public.** The cell/profile kernel. |
| `CompiledEnterpriseAccessStateV1` | eight bound digests, `policy_conflicts`, `cells` | **Evaluator-only.** Per-cell `MechanismOutcomeSetV1`, aggregate access state, and `PolicyConflictTruthV1` rows. |

`AuthorizationEvaluationProfileKind` is `rbac`, `abac`, `rebac`, `rbac_with_abac_guard`,
`rebac_with_abac_guard`. `MechanismOutcome` is `allow`, `deny`, `not_applicable`, `unknown`.
Guard profiles require the base mechanism to allow **and** ABAC to allow; otherwise
deny-overrides then allow applies. The aggregate is strictly default-deny: `unknown` and
`not_applicable` both collapse to `deny`, so **the composed decision cannot express
indeterminacy** even though the component truth preserves it. A policy-conflict row folds a
single mechanism's internal conflict in by adding that mechanism to both the allowing and the
denying set, so a conflict row cannot distinguish an internal disagreement from a genuine
cross-mechanism one.

The composed access state is **not scored**. There is no evaluate or perfect-prediction function
and no metrics module in the authorization package; `CompiledEnterpriseAccessStateV1` is truth
output only, consumed by the downstream packs.

### Artifact boundary

There are **three independent export roots**, not one shared tree. Each exporter refuses to run if
its root already exists, each writes its own `public/` and `evaluator/` subdirectory, and each
subdirectory gets its own `manifest.json`. The loaders require the directory to contain *exactly*
the expected files plus `manifest.json`, so the three roots cannot be merged into one directory.

| Export root | `public/` | `evaluator/` |
|---|---|---|
| `export_enterprise_evaluation_corpus` | `evaluation-corpus.json`, `manifest.json` | `evaluation-case-inventory.json`, `manifest.json` |
| `export_enterprise_directory_rbac` | `directory-rbac-kernel.json`, `manifest.json` | `directory-rbac-truth.json`, `manifest.json` |
| `export_enterprise_authorization` | `abac-state.json`, `abac-intent.json`, `rebac-state.json`, `rebac-intent.json`, `authorization-composition.json`, `authorization-kernel.json`, `manifest.json` | `abac-truth.json`, `rebac-truth.json`, `compiled-access-state.json`, `manifest.json` |

So the ABAC and ReBAC *policy* — facts, tuples, and rules, in both the actual and the intended
layer — is product-safe, while every `Compiled*TruthV1` and the compiled access state is
evaluator-only. Loaders re-derive the cross-visibility digests in both directions and reject
non-canonical bytes or any unexpected file. Every evaluator loader also loads the matching public
tree from the same root and checks the binding, so the two halves of a root travel together.

`EnterpriseDirectoryRbacIntentOverlayV1` and `EnterpriseRbacSessionStateInputV1` have **no
exporter or loader in these packages** — they are passed in process; the downstream packs that do
ship them classify them as public inputs, and that decision belongs to those packs.

### Authorization metric envelope

Every metric in the enterprise authorization families — directory/RBAC, ABAC, ReBAC,
identity fabric, enterprise agentic, and contextual access — is an
`EnterpriseAuthorizationMetricV1`. Authority-change governance is the exception and uses its
own envelope; see that section.

| Field | Type | Meaning |
|---|---|---|
| `family`, `name` | str | Independent semantic family and metric name. |
| `numerator`, `denominator`, `support` | int | Counts. A validator enforces `support == denominator` and `numerator <= denominator`. |
| `denominator_meaning` | str | The exact population the denominator counts. |
| `empty_behaviour` | `nonempty` \| `null_if_empty` | An empty denominator requires `null_if_empty` and a null value; a `nonempty` metric with a zero denominator raises. |
| `value` | float \| None | Must equal `numerator / denominator` within `1e-12`, or be null under `null_if_empty`. |

Counted from the reference pipeline: the directory/RBAC oracle emits **19** metrics across the
families `birthright`, `intent`, `rbac`, `activation`, `activation_safety`, `ssd`, `dsd`,
`sprawl`, `birthright_breadth`, `redundancy`, and `accumulation`; ABAC emits **2**; ReBAC emits
**2**. **There is no aggregate or composite score anywhere in these four packages**, by design.
Missing predictions score as incorrect rather than erroring, so partial submissions are legal;
unknown prediction IDs are rejected.

There is no CLI for this layer. Directory/RBAC, ABAC, ReBAC, and the composed access state are
Python API only.

## Standards projections

`synthworld.enterprise.projections` performs deterministic data conversion and nothing else.
The package docstring is the contract: *pure, versioned standards projections; no network or
runtime clients.* There is no SCIM network operation, AuthZEN HTTP client, Shared Signals
transmitter, OpenFGA writer, vendor connector, credential handling, or enforcement behaviour
anywhere in it, and no CLI surface reaches it.

Every conversion emits a machine-readable support matrix alongside its payload.

| Record | Key fields | Meaning |
|---|---|---|
| `ProjectionMappingProfileV1` | `schema_version` (`1.0.0`), `profile_id`, `target`, `native_profile_version`, `target_profile_version`, `definitions` | Operator-owned mapping declaration; at least one definition. |
| `ProjectionMappingDefinitionV1` | `mapping_id`, `native_source_feature`, `target_construct`, `classification`, `conformance_vector_ids` | `semantic_delta` is structurally **mandatory** for every non-exact row and structurally **forbidden** on exact rows. |
| `ProjectionSupportMatrixV1` | `schema_version` (`1.0.0`), `profile_id`, `target`, both profile versions, `mapping_digest`, `exercised_native_features`, `rows` | Exactly one row per exercised native feature, bound to one canonical mapping digest. |
| `ProjectionFidelityMetricsV1` | `support_matrix_digest`, `metrics` | A tuple of `EnterpriseAuthorizationMetricV1`. The **schema imposes no length**, only canonical `(family, name)` ordering; it is `evaluate_projection_fidelity` that always emits exactly three, one per `ProjectionSupportClassification` member. A hand-constructed instance with one or five metrics validates. |

`ProjectionTarget` is `scim`, `authzen`, `openfga`, `shared_signals`.
`ProjectionSupportClassification` is `exact`, `approximated`, `unsupported`. Fidelity emits
`exact_feature_rate`, `approximated_feature_rate`, and `unsupported_feature_rate` under the
family `projection:<target>`, each with denominator `all native features exercised by this
projection`. **No combined fidelity score is emitted**; the three rates sum to one by
construction.

| Target | Schemas and pinned versions |
|---|---|
| SCIM | `ScimProjectionProfileV1` and `ScimProjectionV1` at `1.0.0`, compiler `1.0.0`; native profile `enterprise-authorization-1.0.0`, target profile `rfc7643-rfc7644-2015` |
| AuthZEN | `AuthZenMappingProfileV1`, `AuthZenRequestProjectionV1`, and the shared observation schema at `1.0.0`, compiler `1.0.0`; native profile `enterprise-authorization-1.0.0`, target profile `authzen-authorization-api-1.0-final` |
| OpenFGA | `OpenFgaMappingProfileV1` and `OpenFgaProjectionV1` at `1.0.0`, compiler `1.0.0`; native profile `synthworld-bounded-rebac-1.0.0`, target profile `openfga-model-schema-1.1`; the emitted `OpenFgaAuthorizationModelV1.schema_version` is the literal `1.1` |
| Shared Signals / CAEP | `SharedSignalsMappingProfileV1` at `1.0.0`; native profile `enterprise-authorization-1.0.0`, target profile `ssf-1.0-caep-1.0-final`; `temporal_base_version` pinned to `synthworld-temporal-1.1.0` |

**Shared Signals emission is not implemented.** `shared_signals.py` has no projection function,
no output model, and constructs no SET or event envelope; its only callables are the profile
builder and the support-matrix compiler. The deferral is encoded in the schema itself as frozen
literals — `schedule_view_status: Literal["deferred_to_pr7"]` and
`emitted_event_projection: Literal["deferred"]` — so no other value validates. Of its six
mapping rows, `temporal_coordinate_projection` and `domain_policy_change_as_caep` are
`unsupported`, `account_disabled` is `approximated` onto `caep:session-revoked`, and only
`credential_change` maps to a real CAEP type; `effective_access_change` and
`relationship_change` are classified `exact` but map to SynthWorld-private
`urn:synthworld:event:*` identifiers, not to standardized CAEP event types. The profile is
pinned to the historical PR4 temporal contract `synthworld-temporal-1.1.0`, deliberately not the
shipped `synthworld.temporal` 1.2. Presence of `synthworld-shared-signals-projection` in the
standards ledger must not be read as a working event emitter. A separate, additive successor
that *does* emit events ships under `synthworld.contextual_access.shared_signals` and is
documented below.

Other limits worth recording. SCIM `roles` and `entitlements` are always empty and
`ScimUserProjectionV1.authorization_semantics` is the frozen literal `none`; only accounts
become group members; `user_name` is fabricated as `<account_id>@accounts.example.invalid`; an
account with no observation projects as `active: false`. The emitted payload is a shape-level
projection carrying SynthWorld-native field names and `synthetic: true`, not an RFC 7643 wire
document. The OpenFGA authorization model is a hardcoded five-element tuple, constant regardless
of input universe, and each emitted tuple carries native snapshot and validity fields as inert
metadata that no OpenFGA runtime enforces. AuthZEN normalization is lossy by design: only
`allow` and `deny` map to a decision; `indeterminate`, `transport_error`, `timeout`, and
`unavailable` all normalize to null. `project_authzen` handles exactly one request per call and
deliberately embeds no expected decision, which is what makes the request projection safe to
hand to a system under test.

Two visibility notes. `project_scim` and `project_authzen` consume public inputs, but
`project_openfga` consumes `CompiledEnterpriseRebacTruthV1` and copies native snapshot,
revision, and validity fields onto every emitted tuple — **an OpenFGA projection is derived from
evaluator truth and is not automatically a public artifact.** And every mapping row carries
`conformance_vector_ids`, but those identifiers resolve to nothing shipped:
`AuthorizationConformanceVectorV1` exists in `synthworld.enterprise.conformance`, and
`PolicyCoverageManifestV1` (`POLICY_COVERAGE_MANIFEST_SCHEMA_VERSION` `1.0.0`, with
`exhaustive: Literal[False]`) is published as a schema, but no conformance-vector corpus ships
in `src/`.

The standards ledger also pins `synthworld-scim-protocol-projection` to RFC 7644 and
`synthworld-caep-projection` to OpenID CAEP 1.0, but no mapping profile in the package uses
either profile identifier. RFC 7644 protocol semantics have no mapping profile at all.

## Temporal schedule views

`synthworld.temporal_schedule` adds a schedule *view* over the shipped privacy tick contract.
It introduces no time: `effective_tick` projects the selected family's existing integer tick and
`event_index` is only the derived position in canonical `(effective_tick, event_id)` order.

| Record | Key fields | Meaning |
|---|---|---|
| `TemporalEventEnvelopeV1` | `schema_version` (`1.0.0`), `event_id`, `effective_tick`, `event_index`, `event_schedule_version`, `payload_family`, `payload_sha256` | `TemporalPayloadFamilyV1` is closed at `privacy_1_2` and `contextual_access_1_0`. |
| `TemporalScheduleV1` | `schema_version` (`1.0.0`), `event_schedule_version`, `events` | Validates unique event IDs, canonical `(effective_tick, event_id)` order, a contiguous zero-based `event_index`, and one shared schedule version. |
| `TemporalEventEnvelopeV2` / `TemporalScheduleV2` | as above at `2.0.0` | `TemporalPayloadFamilyV2` adds only `governance_1_0`. V1 remains closed and rejects that family; neither loader upgrades or relabels an artifact. |

`SELECTED_PRIVACY_TEMPORAL_SCHEMA_VERSION` is `1.2.0`. Integer tick is the only deterministic
world clock in the generated artifacts; nanoseconds appear only in operational *run* records, as
durations after a delivery coordinate, never as an alternative replay clock.

## Identity-fabric smoke benchmark

The identity-fabric pack is a bounded directory- and access-state slice layered over the fixed
universe and corpus. It adds no entity, atom, or cell. `IDENTITY_FABRIC_PROFILE_VERSION` is
`identity-fabric-smoke-1.0.0`; every schema and compiler constant is `1.0.0`. There is **no tier
enum, no tier field, and no tier flag** anywhere in the package — the profile version is the
only variant marker.

| Record | Key fields | Meaning |
|---|---|---|
| `EnterpriseIdentityFabricPublicInputV1` | `schema_version`, `invariant`, `checkpoints`, `benchmark` | **Public.** At least two checkpoints, whose `sequence` values must be contiguous from zero. A validator binds the invariant digest and every per-checkpoint input digest. |
| `IdentityFabricInvariantPublicInputV1` | `profile_version`, `universe`, `corpus`, `directory_rbac_intent`, `rbac_session_state`, `abac_intent`, `rebac_intent`, `evaluation_profile` | The parts that do not change between checkpoints. |
| `IdentityFabricCheckpointPublicInputV1` | `checkpoint_id`, `sequence`, `directory_rbac_kernel`, `abac_state`, `rebac_state`, `composition`, `authorization_kernel` | One ordered immutable snapshot. `sequence` is canonical ordering only — it is not time and not a second clock; all validity and lifecycle logic uses the integer `tick` axis. |
| `EnterpriseIdentityFabricBenchmarkV1` | universe/corpus/invariant digests, `checkpoints`, `membership_queries`, `role_queries`, `account_queries`, `access_queries`, `accumulation_queries` | The digest-bound query inventory. |
| `EnterpriseIdentityFabricTruthV1` | `schema_version`, `compiler_version`, `public_input_digest`, `benchmark_digest`, `canonical_binding_truth_digest`, `checkpoints`, `accumulation`, `case_labels` | **Evaluator-only.** |
| `EnterpriseIdentityFabricEvaluatorArtifactsV1` | `schema_version`, `public_input_digest`, `canonical_binding_truth`, `checkpoints`, `truth` | **Evaluator-only.** Each checkpoint carries the compiled directory/RBAC, ABAC, and ReBAC truth plus the compiled access state. |
| `EnterpriseIdentityFabricPredictionV1` | `schema_version`, `benchmark_digest` | The scorer input: per-checkpoint component predictions plus membership, role, account, and access rows, and cross-checkpoint accumulation rows. |
| `EnterpriseIdentityFabricMetricsV1` | `schema_version`, `benchmark_digest`, `truth_digest`, `checkpoints`, `cross_checkpoint_metrics` | Each checkpoint nests the full directory/RBAC, ABAC, and ReBAC component reports alongside `identity_fabric_metrics`. |

**Public vs evaluator truth.** `export_enterprise_identity_fabric` writes
`public/identity-fabric-input.json` and `public/manifest.json`, and
`evaluator/identity-fabric-evaluator.json` and `evaluator/manifest.json`. The public loader
never traverses `evaluator/` and re-runs the deterministic projection; the evaluator loader
recompiles all truth and rejects drift. Tests assert the public bytes contain none of
`case_labels`, `canonical_binding_truth`, `membership_path_ids`, `authorized_role_path_ids`,
`outside_intent`, or `redundant_derivation`.

The prediction contract is deliberately narrower than truth. `membership_path_ids`,
`authorized_role_path_ids`, `observed_principal_id`, and `mechanism_outcomes` are retained for
evaluator inspection but are never requested and never scored. One asymmetry is worth knowing:
`IdentityFabricAccountPredictionV1.canonical_principal_id` is nullable while the truth field is
not, so a null prediction can never score correct on `canonical_account_owner_accuracy`.

The reference pack is fixed and tiny: two checkpoints (`baseline` at sequence 0, `accumulated`
at sequence 1) over 10 access subjects, 2 groups, 2 roles, 4 accounts, 2 authorization targets,
16 access atoms, and 19 evaluation cells spread over 3 distinct ticks (`0`, `5`, `20`).
`reference_enterprise_identity_fabric()` takes no arguments — there is no seed to vary. It scores
34 `identity_fabric_metrics` per checkpoint across the families
`membership`, `role_resolution`, `account`, `entitlement`, `birthright`,
`approved_exception`, `intent`, `effective_access`, `final_access`, `conflict`, `redundancy`,
`birthright_breadth`, and `sprawl`, plus 3 cross-checkpoint `accumulation` metrics. Several
detection denominators are single-digit; these are discrimination fixtures, not statistically
meaningful rates. There is **no aggregate identity-fabric score.**

The query inventory is a fixed cross product, not a sample. Every family carries the checkpoint
factor except accumulation, which pairs adjacent checkpoints:

| Family | Cross product | Reference count |
|---|---|---|
| membership | checkpoints x subjects x groups | 2 x 10 x 2 = 40 |
| role | checkpoints x subjects x roles | 2 x 10 x 2 = 40 |
| account | checkpoints x accounts x distinct corpus ticks | 2 x 4 x 3 = 24 |
| access | checkpoints x cells | 2 x 19 = 38 |
| accumulation | adjacent checkpoint pairs x subjects | 1 x 10 = 10 |

Any deviation raises `identity_fabric_public_query_inventory_mismatch`.

**No CLI and no trace format.** `synthworld` exposes no generate, validate, or evaluate
subcommand for this pack, and there is no JSONL submission format, no shape validator, and no
validation-report model. Predictions must be constructed in Python. Accumulation is defined
narrowly as the set difference of outside-intent allow cells attributable to a subject between
two adjacent checkpoints; it is not a general drift or time-series measure.

## Enterprise-agentic smoke benchmark

The enterprise-agentic pack replays an agent overlay over the same fixed universe, corpus,
component truth, and compiled access state, and scores the immutable enterprise decision `F`
separately from seven downstream authority gates. `ENTERPRISE_AGENTIC_PROFILE_VERSION` is
`enterprise-agentic-smoke-1.0.0`; every schema and compiler constant is `1.0.0`.

**`EnterpriseAgenticTier` has exactly one member, `smoke`.** Both the config and the benchmark
type `tier` as `Literal[EnterpriseAgenticTier.SMOKE]`, so no other tier is representable, and
the CLI flag accepts only `smoke`. There is no standard, large, or held-out agentic tier.

| Record | Key fields | Meaning |
|---|---|---|
| `EnterpriseAgenticPublicInputV1` | `schema_version`, `config`, `access`, `snapshot`, `events`, `benchmark` | **Public.** A validator binds the config, access, snapshot, and event digests into the benchmark. |
| `EnterpriseAgenticAccessPublicInputV1` | universe, corpus, directory/RBAC kernel and intent, session state, ABAC state and intent, ReBAC state and intent, composition, evaluation profile, authorization kernel | The exact enterprise policy inputs. |
| `EnterpriseAgenticSnapshotV1` | `accounts`, `runtimes`, `credentials`, `capabilities`, `delegations`, `initial_evidence_refs` | The agent overlay. Credentials are **opaque handles** for safely fictional records, never reusable credential material. |
| `EnterpriseAgenticEventPayloadV1` | `event_type` | Discriminated union of `action_attempted`, `credential_revoked`, `delegation_revoked`, `evidence_discarded`, `audit_performed`. |
| `AgentAuthorizationMappingProfileV1` | `mapping_kind` | `AgentAsPrincipalV1` (`agent_as_principal`) or `HumanSubjectAgentContextV1` (`human_subject_agent_context`). |
| `EnterpriseAgenticBenchmarkV1` | `schema_version`, `compiler_version`, `profile_version`, `aiim_source_id`, `aiim_profile_version`, `seed`, `tier`, six digests, `audit_event_id`, `cases` | `EnterpriseAgenticCaseReferenceV1` publishes only `case_id`, `action_event_id`, and `mapping_kind`. |
| `AgenticExpectedDecisionV1` | `enterprise_decision`, seven gate outcomes, `final_decision`, `failure_reasons` | **Evaluator-only.** |
| `EnterpriseAgenticTruthV1` | `schema_version`, `compiler_version`, `public_input_digest`, `benchmark_digest`, `access_state_digest`, `cases`, `case_labels` | **Evaluator-only.** Case truth adds attribution, `required_evidence_refs`, and `reconstructable_at_audit`. |
| `EnterpriseAgenticEvaluatorArtifactsV1` | `schema_version`, `public_input_digest`, `canonical_binding_truth`, `directory_rbac_truth`, `abac_truth`, `rebac_truth`, `access_state`, `truth` | **Evaluator-only.** |
| `EnterpriseAgenticTraceRowV1` | `schema_version`, `benchmark_digest`, `case_id`, `enterprise_decision`, `gates`, `final_decision`, `failure_reasons`, `agent_principal_id`, `agent_account_id`, `runtime_id`, `evidence_refs`, `reconstructable_at_audit` | One JSONL submission row; `human_principal_id` is nullable. |
| `EnterpriseAgenticPredictionV1` | `schema_version`, `benchmark_digest`, `rows` | At least one row; every row must repeat the benchmark digest. |
| `EnterpriseAgenticMetricsV1` | `schema_version`, `benchmark_digest`, `truth_digest`, `metrics` | |
| `EnterpriseAgenticTraceValidationReportV1` | `schema_version`, `valid`, `row_count`, `expected_case_count`, `issues` | A validator enforces `valid` against the presence of an error-severity issue. |

`AgenticGateOutcome` is `satisfied`, `unsatisfied`, `not_applicable`. `AgenticFailureReason` has
ten members. `EnterpriseAgenticCaseKind` has twenty, and the reference pack contains exactly one
case per kind — a tripwire raises unless the label kinds equal the full set with no repeats.

The authority model is deliberately **non-unioning**: the final decision allows only when the
enterprise cell decision `F` allows *and* the subject, tenant, agent-account, runtime,
credential, capability, and delegation gates all pass. Under `agent_as_principal` the delegation
gate is always `not_applicable` and the owning human and provenance delegation are attributable
context that grant no authority; there is no path by which a human owner's authority rescues an
agent denial.

**Public vs evaluator truth.** `public/enterprise-agentic-input.json` plus its manifest carry
the config, enterprise access inputs, agent overlay snapshot, ordered event log, and the opaque
case inventory. `evaluator/enterprise-agentic-evaluator.json` plus its manifest carry the
canonical binding truth, component truth, compiled access state, expected decisions, attribution,
evidence truth, and case labels. Tests assert the public bytes contain none of
`expected_decision`, `case_labels`, `canonical_binding_truth`, `failure_reasons`,
`reconstructable_at_audit`, or `access_state`, and that `opaque_handle` is present while
`secret` and `token` are not. `validate_enterprise_agentic_trace_jsonl` is public-only: it uses
the public case IDs and benchmark digest and never reads truth.

The reference pack scores **20** metrics across the families `enterprise_authorization`,
`downstream_authorization`, `agentic_gate` (seven), `identity_attribution` (four),
`observability` (four), and `mapping_profile` (two). Every agentic metric carries
`empty_behaviour: null_if_empty`. **There is no agentic aggregate score.** The pack is 20 cases,
so every denominator is at most 20 and the delegation-gate denominator is 10. Scoring is
strict-inventory: the prediction's case set must equal the truth case set exactly.

The four enterprise-agentic observability metrics score reported evidence-reference
labels and the reported audit reconstructability claim against evaluator truth. They
do not retrieve, reconstruct from, or otherwise verify retention of the underlying
evidence.

Scenario tags are evaluator-only and fixed; they derive from the pinned AIIM snapshot, which
supplies experimental scenario vocabulary only and defines neither a normative protocol nor a
core agent identity model.

CLI: `synthworld generate-enterprise-agentic --tier smoke --seed <int> --output <dir>`,
`synthworld validate enterprise-agentic-trace`, `synthworld evaluate enterprise-agentic`.

For the default fixed profile, **`--tier` is accepted but has only the single allowed value
`smoke`**. **The CLI default seed is not the reference seed** — `--seed` defaults to `20260719`, while
`REFERENCE_ENTERPRISE_AGENTIC_SEED` is `20260804`. Generating without `--seed` produces a pack
with a different public digest and different case IDs from the committed contract examples; the
case count stays 20, so the difference is silent unless digests are compared. Pass
`--seed 20260804` to reproduce the shipped pack.

### Generated enterprise-agentic smoke profile

`synthworld generate-enterprise-agentic --profile generated --tier smoke` selects an
independently versioned generated family. It does not widen the fixed contracts above.
`EnterpriseAgenticGenerationConfigV1` binds `profile_version`, `generator_version`,
`canonical_serialization_version`, `event_schedule_version`, seed, tier, and the explicit
`EnterpriseAgenticSmokeTopologyV1` counts. The topology currently supports exactly one
organisation, 2–8 departments, 4–100 humans, 3–12 logical agents, 3–24 runtimes, and 3–24
resources; every agent requires a runtime and an accountable human.

| Record | Key fields | Meaning |
|---|---|---|
| `EnterpriseAgenticBenchmarkIdentityV1` | four implementation/serialization versions, `tier`, `seed`, `configuration_sha256`, `world_id` | Deterministic identity derived only from explicit inputs. Host platform, clock, filesystem, and Git state are excluded. |
| `EnterpriseAgenticGeneratedPublicV1` | `config`, `identity`, `benchmark` | **Public.** Explicit config plus the base `AgenticPublicBundle`; no bindings, cases, expected decisions, or metrics. |
| `EnterpriseAgenticGeneratedEvaluatorV1` | `identity`, `public_artifact_set_sha256`, `benchmark`, `metrics` | **Evaluator-only.** Base evaluator truth and derived integrity observations cross-bound to the entire public tree. |
| `EnterpriseAgenticIntegrityMetricsV1` | count metrics, five supported distributions, principal component count, two integrity flags | Derived from the generated graph, replay state, cases, and truth. Every count or bucket states its denominator and denominator meaning. |

Default smoke output contains one organisation, four departments, 25 humans, five logical
agents, eight runtimes, six resources, ten opaque credentials, five delegations, and seven
action cases. The case set covers allow, excess capability, wrong runtime, expired credential,
valid-then-revoked, incorrect attribution, and post-revocation behavior. One delegation is an
attenuated child, and discarded delegation evidence makes the revoked path non-reconstructable
at audit.

The generated package contains `public/public-input.json`, a separate scenario and tool schema,
and `public/manifest.json`; evaluator output contains `evaluator/truth.json` and its manifest.
The evaluator payload and manifest bind the digest of the complete public tree. Generated worlds
are outputs, not committed golden fixtures. `standard` and `longitudinal` are not representable
in this schema version and remain issue #27 work; runtime and memory measurements are external
receipts keyed to artifact digests, not host state embedded in benchmark bytes.

`load_public_generated_enterprise_agentic_benchmark` verifies only the public inventory,
canonical bytes, manifest, scenario, tool schema, configuration, and identity; it does not inspect
the evaluator subtree and establishes internal consistency rather than producer authenticity.
`load_generated_enterprise_agentic_benchmark` additionally requires the exact two-directory root,
cross-validates evaluator bindings, re-derives integrity metrics, and reproduces the declared
generator output byte-for-byte. CLI consumers use
`synthworld validate generated-enterprise-agentic-trace` in the public-only path and
`synthworld evaluate generated-enterprise-agentic` in the evaluator path.

External adapters replay `AgenticEvent` records in `event_index` order and query their system at
each `action_attempted` position; final-state-only evaluation is not equivalent. A reference
organisation document may inform the supported count knobs, but this version does not import its
named topology. Trace fields represent observed SUT output: copying identity, delegation, or
evidence values from public input would not demonstrate that a decision-only PDP produced them.

## Contextual access

Contextual access is a bounded deterministic benchmark for relationship- and attribute-aware
authorization under changing, late, duplicated, and reordered context. It is a pure overlay: it
never creates a principal, account, group, role, resource, action, or access atom. Contract
prose lives in [`contextual-access-contract/README.md`](contextual-access-contract/README.md).

`ContextualAccessTier` has exactly one member, `smoke`. Versions:
`CONTEXTUAL_ACCESS_CONFIG_SCHEMA_VERSION` `1.0.0`, `CONTEXTUAL_ACCESS_SCHEMA_VERSION` `1.0.0`,
`CONTEXTUAL_ACCESS_COMPILER_VERSION` `1.0.0`, `CONTEXTUAL_ACCESS_PROFILE_VERSION`
`contextual-access-smoke-1.0.0`, `CONTEXTUAL_ACCESS_EVENT_SCHEDULE_VERSION`
`contextual-access-schedule-1.0.0`, `CONTEXTUAL_ACCESS_PROTOCOL_VERSION`
`synthworld-contextual-access-1.0.0`.

| Record | Key fields | Meaning |
|---|---|---|
| `ContextualAccessConfigV1` | `seed`, `tier`, `enabled_fact_kinds`, `enabled_case_kinds`, `cases_per_kind`, `object_counts`, `event_schedule_version`, `limits` | Generation configuration. **`seed` is the only required field**; every other field defaults, including `object_counts` and `limits` (default factories). |
| `ContextualAccessPublicV1` | `schema_version`, `universe`, `registry`, `mapping_profile`, `policies`, `initial_facts`, `events`, `schedule`, `delivery_attempts`, `requests`, `benchmark` | **Public.** `schedule` is a tuple of `TemporalEventEnvelopeV1` in the `contextual_access_1_0` family. |
| `ContextualFactV1` | `fact_type` | Discriminated union over the five fact kinds; each fact carries `fact_id`, `fact_key`, `revision`, and `tombstone`. |
| `ContextualAccessEventV1` | `id`, `effective_tick`, `payload` | Payload is `ContextualFactUpsertedV1` or `ContextualFactRemovedV1`; upsert forbids a tombstone and removal requires one. |
| `ContextDeliveryAttemptV1` | `attempt_id`, `event_id`, `attempt_index`, `delivery_tick`, `delivery_order` | Delivery is modelled separately from effect. |
| `ContextualPolicyV1` | `policy_id`, `policy_version_id`, `target_handles`, `actions`, `rules`, `default_decision`, `combining_algorithm` | Decision semantics are **fixed, not configurable**: `default_decision` is `Literal[DENY]` and `combining_algorithm` is `Literal["deny_overrides"]`. |
| `ContextualAccessTruthV1` | `schema_version`, `compiler_version`, `public_digest`, `benchmark_digest`, `checkpoints`, `cases`, `case_labels` | **Evaluator-only.** |
| `ContextualAccessCaseTruthV1` | `case_id`, `request_id`, `canonical`, `presented_feed`, `stale_context`, `required_evidence_refs` | Both the canonical and presented-feed decisions are retained, with per-predicate and per-rule outcomes and a deny-override conflict flag. |
| `ContextualAccessEvaluatorV1` | `schema_version`, `public_digest`, `truth` | **Evaluator-only** wrapper; a validator binds truth to the public digest. |
| `ContextualAccessTraceRowV1` | `schema_version`, `benchmark_digest`, `request_id`, `decision`, `predicate_outcomes`, `applied_event_ids`, `evidence_refs` | One JSONL submission row. |
| `ContextualAccessPredictionV1` | `schema_version`, `benchmark_digest`, `rows` | |
| `ContextualTraceValidationReportV1` | `schema_version`, `valid`, `row_count`, `expected_request_count`, `issues` | Issue `severity` is the literal `error`; the validator emits no warnings. |
| `ContextualAccessMetricsV1` | `schema_version`, `benchmark_digest`, `truth_digest`, `metrics` | |

Vocabularies are closed: `ContextualFactKind` (`case_assignment`, `on_call`, `device_posture`,
`risk_signal`, `business_justification`), `ContextualObjectKind` (five members),
`ContextualPredicateTruth` (`true`, `false`, `unknown`), and `ContextualCaseKind` (ten members,
one per reference request). Only a rule outcome of exactly `true` counts as matched; `unknown`
never matches. Facts are active on the half-open interval `[start, end)`. A request at tick `t`
observes every event with `effective_tick <= t`; presented state folds uniquely delivered events
back into canonical effective order, so duplicate delivery is idempotent by construction.

**Public vs evaluator truth.** `public/contextual-access-input.json` and
`evaluator/contextual-access-evaluator.json`, each with its own manifest. The public loader never
traverses `evaluator/`, and the evaluator loader recompiles truth and requires exact equality.

**Read the boundary honestly.** Expected decisions are *intentionally derivable* from public
policy plus public facts and events. The contract states it directly: this is a transparent
conformance oracle and accidental-leakage boundary, **not an anti-cheating mechanism**, and
held-out seeds and policy variants are still needed before the pack can detect hard-coded
answers. No held-out contextual seed ships.

The offline prediction scorer emits **9** metrics across the families `decision`, `freshness`,
`delivery`, `predicate`, `relationship`, and `evidence`, all `null_if_empty`. In the shipped
pack `stale_context_decision_accuracy` has denominator 1 — a tripwire requires the stale set to
equal exactly the delayed-delivery labels — so it is a single-sample metric.

Declared but not implemented: `cases_per_kind` is a config field the generator rejects at any
value other than 1, and `enabled_case_kinds` is not enforced by the public projection (only
`enabled_fact_kinds` is). `ContextualFaultKind.DROPPED_DELIVERY` and
`MappingIngestionStatus.UNSUPPORTED` are declared and never produced. The constant
`CONTEXTUAL_ACCESS_SCORING_VERSION` is exported but referenced nowhere; the version bound into
receipts is `CONTEXTUAL_RUN_SCORING_VERSION`. The CLI `--tier` flag is accepted but never read.
Note also that the CLI `--seed` default is `20260719` while `REFERENCE_CONTEXTUAL_ACCESS_SEED` is
`20260804`, so running `generate-contextual-access` without `--seed` produces a different pack
from the committed contract examples.

### Contextual run protocol

The run contracts describe an *external* run and execute nothing.

| Record | Key fields | Meaning |
|---|---|---|
| `ContextualAccessRunPlanV1` | `schema_version` (`1.0.0`), `protocol_version`, `run_id`, `benchmark`, `mapping_profile_digest`, `event_schedule_version`, `request_ids`, `event_ids`, `delivery_attempt_ids`, `sut_component_ids`, `context_feed_component_ids`, `faults`, `bounds`, `required_evidence_kinds`, `control_coverage`, `probes` | **Product-safe.** Coverage must contain every control, and selected controls must match probe coverage. The model has no field for an evaluator case ID or label, so it structurally cannot carry one. |
| `ContextualRunBoundsV1` | `feed_delay_bound_ticks`, `sut_acceptance_bound_ns`, `post_acceptance_decision_bound_ns` | Feed delay is measured in ticks; acceptance and post-acceptance decision latency in nanoseconds. They are never combined into one score. |
| `ContextualAccessObservationsV1` | `schema_version` (`1.0.0`), `run_id`, `observations`, `evidence_handles`, `limitations` | **Product-safe** observed output. |
| `ContextualAccessRunTruthV1` | `schema_version` (`1.0.0`) | **Evaluator-only.** |
| `ContextualAccessReportV1` | `schema_version` (`1.0.0`) | **Evaluator-only.** Findings plus metrics. |
| `ContextualProtocolFindingV1` | `probe_id`, `control_id`, `passed`, `right_censored`, `failure_code` | Right-censoring is a first-class field, not an omission. |
| `ContextualAccessProductInputV1` | `schema_version` (`1.0.0`), `run_plan_digest`, `contextual_public_digest`, `public` | The staged product input for a receipt-bound run. |

`ContextualControlId` is the closed set `SW-CA-C01` (mapping ingestion) through `SW-CA-C06`
(evidence correlation). The run scorer emits **8** metrics: one per control, two under
`SW-CA-C04`, and `propagation/post_acceptance_decision_propagation`, whose denominator meaning
records explicitly that missing correct decisions are right-censored failures rather than
silently dropped from the denominator.

Artifact paths: `context/contextual-access-run-plan.json`,
`observations/contextual-access.json`, `evaluator/contextual-access-run-truth.json`,
`evaluation/contextual-access-report.json`.

The additive contextual Shared Signals projection *does* emit events, unlike the enterprise
projection above. `ContextualSharedSignalsMappingProfileV1` and
`ContextualSharedSignalsProjectionV1` are schema `1.0.0` at profile version
`synthworld-contextual-shared-signals-1.0.0`, and select `synthworld-temporal-1.2.0`. Every
mapping row sets `standardized_caep_event_type` to null with classification `custom_profile`;
event types are versioned `urn:synthworld:event:contextual-*-change:1.0` identifiers, not
standardized CAEP types. SET construction, issue time, signing, transmission, and vendor
ingestion remain external.

`synthworld validate contextual-access-run-plan` performs pydantic structural validation only;
it does not check the benchmark digest binding, public ID inventory, or probe references, and
its success message says `structurally valid` for that reason.

## Authority-change governance

The authority-governance family scores whether a system can reconstruct *why* an authority
change occurred. `AUTHORITY_GOVERNANCE_SCHEMA_VERSION`,
`AUTHORITY_GOVERNANCE_BENCHMARK_VERSION`, and `AUTHORITY_GOVERNANCE_SCORING_VERSION` are all
`1.0.0`. There is **no generator, no config model, no seed, no tier enum, and no CLI**:
`reference_authority_governance()` takes no arguments and returns one hand-built 12-case
fixture.

| Record | Key fields | Meaning |
|---|---|---|
| `AuthorityGovernancePublicV1` | `schema_version`, `benchmark_family` (`authority_governance`), `benchmark_version`, `event_schedule_version`, `policies`, `approver_mandates`, `evidence`, `initial_state`, `cases`, `events`, `schedule` | **Public.** Observed requests, decisions, enactments and audits; bounded policy versions and rules; approver mandates; opaque evidence references. `schedule` is a tuple of `TemporalEventEnvelopeV2` in the `governance_1_0` family. |
| `AuthorityGovernanceEventV1` | `event_type` | Discriminated union of request, decision, enactment, and audit events. |
| `GovernancePolicyVersionV1` / `ApproverMandateV1` | half-open `active_from_tick` / `inactive_from_tick` and `valid_from_tick` / `valid_until_tick` | Decision-time selection is by these intervals, never by "latest". |
| `AuthorityGovernanceEvaluatorV1` | `schema_version`, `public_digest`, `truth` | **Evaluator-only.** |
| `AuthorityGovernanceTruthRowV1` | `authority_change_id`, `case_kind`, `change_type`, canonical before/after state, `governance_decision_authorised`, `approver_authorised_at_decision`, canonical requester and chains, applicable policy version/rules/controls, expected rationale and exception, required evidence refs, `controlling_decision_id`, expected outcome and effective tick, supersession link, `enactment_consistent`, `audit_reconstructable`, `failure_reasons` | **Evaluator-only.** |
| `AuthorityGovernancePredictionV1` | `schema_version`, `rows` | One row per authority change, in canonical order. |
| `AuthorityGovernanceReportV1` | `schema_version`, `scoring_version`, `findings`, `metrics` | Per-case findings plus metrics; **no aggregate security score**. |

`AuthorityChangeType` is `grant`, `amend`, `attenuate`, `suspend`, `revoke`, `expire`,
`supersede`. `GovernanceDecisionOutcome` is `approved`, `denied`, `partially_approved`,
`withdrawn`, `expired`. `AuthorityGovernanceCaseKind` has twelve members and
`GovernanceMetricFamily` has five: `state`, `governance_authority`, `policy_rationale`,
`evidence_observability`, `enactment`. The scored fixture emits **20** metrics across those five
families.

`AuthorityGovernanceMetricV1` differs from every other metric envelope in the tranche: its
`denominator` is `Field(gt=0)` and its `value` is a plain `float`. It has no null-if-empty
concept, so do not describe metric empty-behaviour across these families as uniform.

**Public vs evaluator truth.** `public/authority-governance-input.json` and
`evaluator/authority-governance-evaluator.json`, each with its own manifest. Export is
create-only and never overwrites. The byte-identical fixture is additionally frozen under
`src/synthworld/benchmarks/authority-governance-v1/`, where a root `SHA256SUMS` binds all four
paths and `load_golden_authority_governance_benchmark()` verifies them before parsing. Of the
five families documented in this block — identity-fabric, enterprise-agentic, contextual-access,
authority-governance, and continuous assurance — authority-governance is the **only** one that
ships a frozen, byte-checked golden; the other four ship generated contract fixtures instead.
This is not a claim about SynthWorld as a whole: the separate, non-enterprise Asteria agentic
family ships `src/synthworld/benchmarks/asteria-agentic-v1/` with its own
`evaluator/checksums.json`, and several older packs ship `*_SHA256SUMS` files.

One precision note. The controlling decision is documented as the last canonical
`(effective_tick, event_id)` decision strictly before enactment, but the resolver takes the
maximum over all of a case's decisions with no enactment-tick filter; ordering is enforced
indirectly by a case-level phase check. That permits a decision at the same effective tick as
the enactment when its event ID sorts earlier, so the code is slightly weaker than the phrase
"strictly before enactment".

## Continuous assurance

The continuous-assurance pack composes four existing families — identity-fabric,
enterprise-agentic, contextual-access, and authority-governance — into a longitudinal
drift-detection benchmark. `CONTINUOUS_ASSURANCE_SCHEMA_VERSION`,
`CONTINUOUS_ASSURANCE_BENCHMARK_VERSION`, `CONTINUOUS_ASSURANCE_SCORING_VERSION`, and
`CONTINUOUS_ASSURANCE_GENERATOR_VERSION` are all `1.0.0`.

| Record | Key fields | Meaning |
|---|---|---|
| `ContinuousAssuranceConfigV1` | `tier`, `seed`, `risk_threshold`, `justification_kind` | Generation configuration. **It has no required fields at all** — `tier` defaults to `smoke`, `seed` to `20260804`, `risk_threshold` to `70`, and `justification_kind` to `business_need`, so `ContinuousAssuranceConfigV1()` is valid. `justification_kind` is one of `business_need`, `case_assignment`, `emergency_access`. |
| `ContinuousAssurancePublicV1` | `schema_version`, `benchmark`, `horizon_tick`, `source_bindings`, `signals`, `remediations`, `feed_windows`, `cases`, `checkpoints` | **Public.** The final checkpoint's tick must equal the horizon. |
| `ContinuousAssuranceBenchmarkBindingV1` | `benchmark_family`, `benchmark_version`, `generator_version`, `tier`, `source_public_bindings_digest`, `case_inventory_digest`, `policy_profile_id` | |
| `ContinuousAssuranceSignalV1` / `ContinuousAssuranceRemediationV1` | five ordered tick coordinates: action `<=` decision `<=` effective `<=` observation `<=` audit | Named semantics on **one** integer axis, not independent clocks. |
| `ContinuousAssuranceFeedWindowV1` | `unavailable_from_tick`, `restored_at_tick`, `delayed_signal_ids` | An outage changes only when a signal is observable; it never rewrites effective state. |
| `ContinuousAssuranceEvaluatorV1` | `schema_version`, `public_digest`, `private_config_digest`, `source_bindings`, `truth` | **Evaluator-only.** Evaluator source bindings add the evaluator schema version and digest. |
| `ContinuousAssuranceCaseTruthV1` | `case_id`, `case_kind`, `drift_kind`, `finding_required`, `drift_effective_tick`, `first_observable_tick`, expected open/clear/recurrence ticks, `expected_remediation_complete`, `expected_evidence_continuous`, `canonical_policy_version_id`, `lifecycle`, `failure_reasons` | **Evaluator-only.** |
| `ContinuousAssurancePredictionV1` | `schema_version`, `rows` | One row per case, in canonical order. A row without an opening tick may carry no lifecycle data. |
| `ContinuousAssuranceMetricV1` | `family`, `name`, `aggregation`, `value`, `numerator`, `denominator`, `support`, `denominator_meaning`, `empty_behavior` | `aggregation` is `ratio` or `mean_ticks`; `empty_behavior` has the single member `null_if_empty`. |
| `ContinuousAssuranceReportV1` | `schema_version`, `scoring_version`, `findings`, `metrics` | Per-case findings plus metrics; **no aggregate security score**. |

`ContinuousAssuranceSourceFamily` is `authority_governance_1_0`, `contextual_access_1_0`,
`enterprise_agentic_1_0`, `identity_fabric_1_0`. `AssuranceDriftKind` is `credential`,
`delegation`, `entitlement`, `evidence`, `owner`, `policy`. `ContinuousAssuranceMetricFamily` is
`classification`, `detection`, `evidence`, `recurrence`, `remediation`, `staleness`. The smoke
profile scores **16** metrics across those six families.

`ContinuousAssuranceTier` is `smoke`, `standard`, `longitudinal`, `held_out`, repeating a fixed
eight-case template cycle 1, 3, 6, and 3 times for 8, 24, 48, and 24 cases. At the library default
seed `20260804` the four tiers generate:

| Tier | Cases | Checkpoints | Horizon tick |
|---|---|---|---|
| `smoke` | 8 | 53 | 153 |
| `standard` | 24 | 155 | 553 |
| `longitudinal` | 48 | 308 | 1153 |
| `held_out` | 24 | 155 | 557 |

**Those tick figures are seed-dependent.** The generator computes `offset = config.seed % 7` and
lays every case at `base_tick = 1 + offset + cycle * 200 + position * 20`, so the seed shifts the
whole timeline. The CLI's `--seed` default is `20260719`,
not the config default `20260804`, and `20260719 % 7 = 3` against `20260804 % 7 = 4`: running
`generate-continuous-assurance` without `--seed` yields smoke with horizon tick **152**, not 153,
along with different derived IDs. Case and checkpoint counts are unaffected.

**These are assurance cadence tiers, not generated-world scale tiers.** The source worlds do not
grow with the tier: `EnterpriseAgenticTier` and `ContextualAccessTier` each have exactly one
member, identity-fabric has no tier at all, and the generator indexes modulo a fixed pool of
source records. `held_out` differs from `standard` only by a permutation of the template order,
and that permutation is a `uuid5` sort over the *public* config tuple — generator version, tier,
seed, risk threshold, justification kind — with no secret input. Both tiers produce 24 cases;
reordering the templates is also what moves the horizon from 553 to 557. There is no secret-key
input anywhere in `ContinuousAssuranceConfigV1`, and `held_out` must never be described as keyed
concealment.

**Do not describe the public tree as configuration-blind.** `tier` is a public field of the
benchmark binding, and `risk_threshold` and `justification_kind` appear in cleartext inside every
public signal's `policy_version_id`, which is formatted
`policy:{phase}:risk-{risk_threshold}:{justification_kind}:cycle-{n}`. The seed is not rendered
directly but shifts every base tick by a recoverable offset. The public/evaluator split here
protects API hygiene and accidental leakage; it does not claim secrecy when both trees are
distributed.

`mean_ticks` metrics are **not** bounded to `[0, 1]`: `ContinuousAssuranceMetricV1` does not
inherit `DenominatedMetric`, its ratio guard applies only to `ratio` aggregation, and stale
duration scales with the horizon.

**Public vs evaluator truth.** `public/continuous-assurance-input.json` and
`evaluator/continuous-assurance-evaluator.json`, each with its own manifest; export is
create-only. There is **no frozen golden** for continuous assurance — the committed smoke
examples are generated contract fixtures, not benchmark goldens — and no run-receipt lineage
binds a continuous-assurance benchmark to an executed run.

CLI: `synthworld generate-continuous-assurance --tier {smoke,standard,longitudinal,held_out}
--seed <int> --risk-threshold <int> --justification-kind {business_need,case_assignment,emergency_access}
--output <dir>` and `synthworld evaluate continuous-assurance`. This is the **one** generator
with a multi-value tier ladder. The fixed `generate-enterprise-agentic` and
`generate-contextual-access` profiles each accept only `smoke`; the explicitly selected generated
enterprise-agentic profile binds that selected smoke tier into its configuration identity. Pass
`--seed 20260804` to match the committed continuous-assurance contract fixtures.
Authority-governance has no CLI at all and is reached only through the Python API and through
this pack, which consumes it as a source family.

## Run receipts

`synthworld.assurance` is the consumer-neutral run-receipt layer. Two lineages ship.

| Model | Schema version | Used by |
|---|---|---|
| `RunReceiptManifest`, `ExecutionReceipt` | `1.0.0` | the ambiguity lineage |
| `RunReceiptManifestV2`, `ExecutionReceiptV2` | `2.0.0` | the agent-authority and contextual-access lineages |

| Record | Key fields | Meaning |
|---|---|---|
| `RunReceiptManifest` | `schema_version`, `benchmark_family`, `benchmark_version`, `schema_versions`, `scoring_formula_versions`, `seed`, `generator_configuration`, `event_schedule`, `synthworld`, `adapter`, `system_under_test`, `digest_algorithm`, `serialization`, `artifacts`, `execution_status`, `evaluation_status`, `seed_population`, `evidence_claim` | v1 is frozen and single-system: one `system_under_test` and a mandatory `seed` that must belong to the declared seed population. |
| `RunReceiptManifestV2` | `schema_version`, `benchmark`, `build_environment`, `run`, `schema_versions`, `adapter`, `systems_under_test`, `digest_algorithm`, `serialization`, `artifacts`, `execution_status`, `evaluation_status`, `evidence_claim` | v2 models multiple systems under test, managed-service observability limits, and honest failed runs. `scoring_formula_versions` is required when evaluated and forbidden when not. |
| `ExecutionReceiptV2` | `schema_version`, `boundary`, `callable_identifier`, `adapter_name`, `adapter_version`, `adapter_source_digest`, `systems_under_test`, `run_plan_digest`, `source_public_digest`, `product_input_digest`, `product_output_digest`, `exit_code`, `status` | `stimulus_digest` is optional and must be left unset by lineages without a stimulus set rather than borrowing another artifact's digest. `status` must agree with `exit_code`. |
| `SystemComponentProvenanceV2` | `component_type` | Discriminated union of self-hosted, managed-service, and reference provenance. |

`ArtifactPhase` is `product` or `evaluation`; `ArtifactSerialization` is `canonical_json_v1` or
`raw_bytes`; `ExecutionStatus` is `succeeded` or `failed`; `EvaluationStatus` is `evaluated`,
`invalid_submission`, or `not_evaluated`. `SerializationConvention` and its v2 counterpart pin
`synthworld-canonical-json-v1`: UTF-8, lexicographic keys, LF, one trailing newline.
`EvidenceClaim` is `canonical_conformance`, `variant_robustness`, or
`generated_transfer_evidence`; `EvidenceClaimV2` adds `live_lab_conformance`.

Three invariants are enforced rather than documented. A failed execution is unevaluated and an
evaluated run succeeded — the manifest rejects any other pairing. A managed-service component
cannot claim `exact` replayability and must supply a non-empty replayability limitation. And a
`live_lab_conformance` claim is rejected when every system under test is a reference component,
because a reference-only run is offline by construction.

`validate_manifest_dispatched` accepts exactly schema versions `1.0.0` and `2.0.0` and raises on
anything else. Receipt-v2 records deliberately use a separate base class and **never serialize
the `synthetic` marker**, because v1's inheritance of it was misleading for real vendor
provenance.

Scoring-version bindings: `AGENT_AUTHORITY_SCORING_VERSION` `1.0.0` and
`AGENT_AUTHORITY_SCORING_VERSION_V2` `2.0.0`; `CONTEXTUAL_RUN_SCORING_VERSION` `1.0.0` under the
role `contextual_access`; `CONTEXTUAL_PRODUCT_INPUT_SCHEMA_VERSION` `1.0.0`;
`AMBIGUITY_PAIR_SUBMISSION_SCHEMA_VERSION` `1.0.0`.

The contextual finalizer enforces product-before-truth ordering: it replays the run plan, public
input, adapter output, component inventory, provenance, and every staged artifact digest
*before* the truth loader is called, and a failed execution seals `execution_status: failed` and
`evaluation_status: not_evaluated` without loading evaluator truth at all.

CLI: `synthworld validate agent-authority-receipt --input <dir>` and
`synthworld validate contextual-access-receipt --input <dir>`.

## What the public/evaluator split does not claim

The public/evaluator split described in every section above protects a **freshly generated**
run. It is not a claim that the reference packs are blind. The checked-in contract examples
publish both sides for the fixed reference packs — `enterprise-identity-access-contract/examples/`
contains `enterprise-identity-fabric-evaluator.json` and `enterprise-agentic-evaluator.json`
alongside their public inputs, predictions, and metrics — so the reference answer keys are in
this repository, exactly as the existing threat-model section says of SynthWorld's other golden
keys. Competitive evaluation requires packs generated from configuration the operator withholds,
and for contextual access it additionally requires held-out seeds and policy variants that do
not yet ship.

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
solver restricted to the modelled observation (the rendered values, the comparable
structure and the true prevalence) and holding the public law. It is estimated with a
stated method and N, with a Wilson confidence interval, and keyed to a digest of every
decision-relevant constant, so any parameter move invalidates the number loudly. Read
the pack as a **hardness certificate**, not a capability leaderboard: the ceiling
`1 − floor` is the most any system can achieve, and transcribing the published rule
already reaches it, so the informative number is a resolver's **gap to the genie**. A
score above the ceiling is exploiting signal the model says should not exist; a score
within the genie's confidence interval is, statistically, at ceiling. The enumerated
channel invariants — stationarity of the `FAR` kernel, an identical one-value marginal
under every relation, a per-base sibling-landing mass above the gate, form
bijectivity/separation, and the artifact-factorization check — are asserted in the
suite rather than sampled, and the technique premium (the gap between the ceiling and
the best solver that only ever sees per-kind normalised exact match) is gated to stay
positive, so real resolution technique is rewarded rather than anti-taught.

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

## C08 v2 corrective field boundary

- Candidate observation_id and evidence_id values are public identifiers for
  selectable records.
- binding_handle is public and is required to correlate a requirement with the
  intended candidate among same-action/same-kind distractors.
- Evaluator-selected binding rows, required-ID sets, expected outcomes, and
  scenario truth are evaluator-only.
- Enterprise measurement_scope is a schema-required report field after
  4de6df8; it records offline measurement limitations rather than operational
  proof.
