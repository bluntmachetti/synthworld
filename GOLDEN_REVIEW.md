# Golden-v1 review record

Reviewed: 2026-07-19. Seed: `20260719`. Corpus schema: `1.0.0`.

The frozen corpus contains ten personas, nine relationship edges, and one exposure script per persona. Nine personas are exposed and one is the deliberate zero-exposure control. All five relationship kinds and all four exposure-source kinds are present: 18 breaches, 9 broker listings, 21 search results, and 13 social profiles. Five search results are planted name collisions and three broker listings reappear after confirmed removal.

The review checked that every object has `synthetic: true`; identity values obey the reserved-domain, fictional-phone, example-address, and invalid-checksum rules; all exposure names and locators are explicitly Example/Test values; planted search collisions point to a different corpus persona; broker reappearances occur only after confirmed removal; and no real-person or external-corpus data is present.

The canonical SHA-256 is `8b75fcd932dbbe2d0ea94d034f8c546c6c3857d3c99669180222f807cf48755d`. Automated tests independently regenerate and validate these claims on every run.

## Connection-golden-v1 review record

Reviewed: 2026-07-19. Seed: `20260719`. Connection schema: `1.0.0`.

The frozen connection benchmark contains 18 opaque public identity records for
10 evaluator-only entities. Its complete all-pairs denominator is 153: 9 same-
entity pairs and 144 different-entity pairs. The five isolated packs cover
common-name collisions (4 records/2 entities), Unicode and diacritics (3/2),
twins sharing address and birth date (4/2), maiden-name change (3/2), and
misspelling or alias variation (4/2).

The review checked recursive `synthetic: true` markers, reserved source and
email domains, fictional 555 phones and example addresses, opaque IDs,
canonical ordering, exact pack membership, and the absence of persona routing
IDs, cluster labels, relationship truth, or other oracle fields from the public
payload. The evaluator answer key is a physically separate object, and the
product adapter accepts only the public corpus.

The canonical SHA-256 is
`044b52650039059b5841e0af9c512e2bbc7dbb089d43e465d43fda06889a8fe4`.
Automated tests regenerate it byte-for-byte and independently verify its
manifest on every run.

## Extraction public and answer review record

Reviewed: 2026-07-21. Seed: `20260719`. Extraction schema: `1.0.0`.

The separated extraction benchmark projects the annotated bundle into a
product-safe `extraction-public-golden-v1.json` and a physically separate
`extraction-answer-golden-v1.json`. The public corpus holds 62 pages (61
exposure pages and one negative control) and the answer key holds 62 answers
carrying 150 exact spans.

The review checked recursive `synthetic: true` markers; that the public pages
are byte-identical to the annotated bundle's pages; that the public corpus is
recursively free of answer keys, ownership IDs, and spans; that every answer
keys back to a public page by `(source_type, source_record_id)`; and that
every span sits exactly on its public page content when the two halves are
joined.

The canonical SHA-256 of the public corpus is
`10632f000f8aeb8ccd8557476b18b940cfd35b91f7cb38dcf209269de987160e` and of the
answer key is
`ffc6503df8cbb9d8f99161ee29324e8d0a0187901118e8eeaa590b49e7598f78`. Automated
tests regenerate both byte-for-byte and independently verify their manifests on
every run.

## Asteria Agentic v1 review record

Reviewed: 2026-07-27. Seed: `20260719`. Agentic schema and world version:
`1.0.0`.

The frozen reference world contains Asteria and one external confusion-control
tenant, four Asteria departments, ten principals, three logical agents, three
runtimes, three credentials, four grants, nine resources, eleven tool schemas,
24 events, and 11 scored actions. The reviewed timeline includes a valid
two-level attenuated delegation, an authorised child-agent comparison,
capability excess, overprivileged sub-delegation, wrong-runtime and shared
credential use, cross-tenant confusion, incorrect public attribution,
revocation while active, a post-revocation attempt, a later grant that changes
the apparent current-state answer, and declared loss of required delegation
evidence.

The review checked contiguous one-based indices, strictly increasing UTC
timestamps, referential integrity, credential and delegation validity,
revocation cascade, action-time pre-state evaluation, audit-time replay,
field-by-field public projection, absence of verdicts and canonical bindings
from every public artifact, and absence of reusable credential material. A
perfect trace must score identity, authority, attribution, owner, temporal,
provenance, and side-effect dimensions independently; decision correctness
alone is insufficient.

The path-bound SHA-256 artifact-set digest is
`9ef217b5d604f42a68b7c97596c550698293f1a44f402dbc3d39a2cef19c4594`
for the public base artifacts and
`3d856f39a5c34ca891ec61298a40ee5bfcb134feae5db7b8a20f6ce9078b2b3f`
for the evaluator base artifacts. `manifest.json` and `checksums.json` are
excluded from their own root digest. Tests regenerate every file byte-for-byte,
verify both roots and all per-file checksums, and retain 100% branch coverage.

### 0.9.0 publication staging

On 2026-07-27, the exact frozen Asteria tree and the 0.9.0 dataset card were
uploaded to the private Hugging Face staging dataset
`Bluntmachetti7/synthworld-benchmarks-staging`. Commit
`794b547e10c8623c97c3653e8d7a9ff8c05cd3f9` was downloaded again and compared
byte-for-byte with the packaged tree; every per-file hash and both artifact-set
digests matched.

Hugging Face Dataset Viewer returned `501` for the private repository because
private-dataset processing requires a PRO account or Enterprise organisation.
Consequently, the raw redownload and checksums are the pre-publication
authority. Viewer `is-valid`, split, first-row, Parquet, and size checks must run
against the public dataset commit immediately after publication, followed by a
second raw redownload and digest comparison.

## Ambiguity-v1 review record

Reviewed: 2026-08-02. Seed: `20260731`. Ambiguity schema: `1.0.0`.

The frozen pack contains 30 hand-authored public identity records forming 15 record
pairs, one per `ScenarioKind`, published as three physically separate artifacts:
public input, canonical entity membership, and evidence disposition. Six pairs must
remain separate, five must merge, and four are cases where the public evidence
cannot settle the question whatever the canonical truth happens to be.

This revision re-froze all three artifacts. The schema is unchanged at `1.0.0` and no
record content changed; what moved is metadata that had been bound to the answer key.
Three channels were closed:

- `pairs_to_decide` was emitted in the order the fixture drafts its cases, so the
  i-th public pair was the i-th `ScenarioKind` — 15 of 15 on this pack, and 750 of
  750 across fifty generated seeds. The public task now carries the pairs in
  canonical record-id order, refuses any other order, and refuses a repeated pair,
  because how often a pair is listed is a channel too.
- Record identifiers were `uuid5(namespace, f"{seed}:identity:ambiguity:{position}")`
  with `position` walking the drafts in scenario order. The seed is embedded in the
  public artifact, so 30 of 30 identifiers, 15 of 15 scenarios and dispositions, and
  30 of 30 memberships were recoverable from the public file plus this source, with
  no attribute read. Identifiers are now content-addressed over source type, display
  name and attributes.
- Variant display names and realization placeholders were indexed by the scenario's
  position in the enum. Both now derive from the pair's own evidence.

The review checked recursive `synthetic: true` markers, reserved domains, fictional
555 phones, example addresses, the absence of entity IDs, dispositions, scenario
labels and expected decisions from the public artifact, and that each truth artifact
can be held without the other. The canonical SHA-256 values are
`217b0eaeb772c8594ebd89a9b0d8ba205063ed3363d482dab32de15ef82d4b7a` (public),
`42d7f52a4c4a058d2616630dce719fb8c659fd56d4789d91d0cfdee96a264a8e` (memberships) and
`334808680b46f58f78ac820c887548692b057eab97bb6cf41571d1e77dd87e11` (dispositions).

**2026-08-04 re-freeze (#77).** One label changed: `same_name_and_date_of_birth` moved
from `separate` to `insufficient`. The pair is two people in canonical truth, but the
public evidence — matching name and birth date, nothing distinguishing them — cannot
justify concluding it, and the first consumer to run the pack abstained on exactly this
pair for exactly this reason, independently. The disposition is what the evidence
justifies, not what is true; membership truth is unchanged (`same_entity` still false),
so the memberships and public artifacts are byte-identical to the 2026-08-02 freeze and
only the dispositions artifact was re-cut. The previous dispositions digest was
`07f64fc42942d998b695eba1b15ed2bba7b032996ebac271c3b7c5900f3e9203`.

**Scope of the guarantee.** Each scenario is defined by its evidence pattern, and the
pack contains every scenario exactly once, so the answer remains derivable from the
evidence — 20 distinct patterns over fifty seeds with no collisions. That is the task
rather than a leak, but it means this pack measures whether a system handles the named
hard cases, not whether it can tell them apart from cases it has not seen. A held-out
seed changes surface values, not labels. Treat it as a conformance fixture, in the
sense Asteria Agentic v1 is one.

## Authority-governance-v1 review record

Reviewed: 2026-08-05. Authority-governance schema, benchmark, and scoring
versions: `1.0.0`. Schedule version:
`authority-governance-reference-1.0.0`.

This is the explicit additive frozen-benchmark transition for issue #73. The
hand-inspectable fixture contains 12 cases, 49 governance events and matching
V2 schedule envelopes, two decision-time policy versions, three approver
mandates, and 37 opaque evidence records. It covers the required valid grant,
wrong and expired approvers, approved-versus-enacted scope drift, denied but
enacted authority, valid emergency exception, later-policy non-retroactivity,
missing retained approval evidence, unlinked supersession, revocation timing
drift, conflicting decisions, and well-formed unauthorised change.

The review checked that integer tick remains the only deterministic world clock;
every envelope is canonically ordered by `(effective_tick,event_id)` with a
derived contiguous index and a digest-bound `governance_1_0` payload; later
policy, decision, and evidence records do not retroactively alter earlier truth;
well-formed negative cases remain scoreable; and malformed event, schedule,
policy, mandate, evidence, and cross-artifact references remain invalid.

Public and evaluator payloads are physically separate and independently
manifest-bound. The public payload contains no case kind, governance or
approver verdict, canonical state, failure reason, expected enactment, or audit-
reconstructability answer. All generated records remain recursively
`synthetic: true`, contain only safely fictional opaque identifiers, and include
no reusable credential material. The evaluator retains the structured answer
key needed to score state, governance authority, policy/rationale,
evidence/observability, and enactment independently.

The exact SHA-256 values are
`340df0ed2b33db6c05805891258dda789f445e300084a0e347ee318044d3191b`
for the public payload,
`60081ed11ff85b6909e57771f3aeffb8023136ae8b66e91bbaf4473ef7f27d92`
for its manifest,
`7822846e7d5613741857cceed33df849f04606548a4c0e1ce789646aaae8e5e5`
for the evaluator payload, and
`d9b5e3c19a74344ba9b28bfb58efde98ce8809e4157e8c0fa6b97639a7a36e18`
for its manifest. The canonical path-bound `SHA256SUMS` bytes have digest
`a856171b2a328614705340a0d8d8dcf1f6bc0794adf0853c377718f796eb585c`.
Tests regenerate the four artifacts byte-for-byte, pin all five hashes, reject
inventory/path/encoding/type/checksum tampering, and verify the packaged wheel.

No existing golden artifact or checksum changed in this transition. Asteria v1,
the post-#77 ambiguity baseline, and `src/synthworld/temporal.py` remain outside
the new tree and byte-identical to their pre-transition versions.

## C08 v2 Asteria and enterprise candidate review record

Reviewed: 2026-08-09. Seed: `20260809`. Schema version: `2.0.0`.

This record covers independently versioned `asteria-agentic-c08-v2` and
`enterprise-agentic-c08-v2` committed frozen-artifact candidates. It records
current committed bytes after native adversarial corrections `0b46a8a`,
`93e8546`, `694dbe6`, and `4dfb191`. It is not a publication record or a claim
that verification gates passed.

### Asteria inventory and digest roots

| Path | Bytes | SHA-256 |
|---|---:|---|
| `manifest.json` | 1,201 | `cb8deb43ab6216c4d913e294a7a88d882aabb75a6ecbc87f66011eb8099ad50b` |
| `public/c08-asteria-public.json` | 8,106 | `b9ed17cac90721a276b28570bd91b5c6f41b106dad5be15fa1257a7e9a16ade3` |
| `public/manifest.json` | 370 | `5313551de8dbf5f6cdf97447fe9ade9c0fa73500dfd8fd387aa8aa4954de69c3` |
| `evaluator/c08-asteria-evaluator.json` | 1,871 | `b94fc5791e36e43e2b2586cdab0c7aaec9c249700e060a784ccc582b13b777f4` |
| `evaluator/manifest.json` | 465 | `bc701080cf88c8a446e31d5d379c360b29939bf51a7e3e017ce41f417bfce45c` |

`sha256-path-bound-v1` binds sorted relative UTF-8 paths, a NUL separator,
and each payload's raw SHA-256. The visibility sets contain only their payload;
the root set contains both payloads and both visibility manifests and excludes
only root `manifest.json`.

| Digest | Value |
|---|---|
| public input/raw payload | `b9ed17cac90721a276b28570bd91b5c6f41b106dad5be15fa1257a7e9a16ade3` |
| public artifact set | `fe59c2d365194572c57f1afa892d3a86fffb41e07f5e77ac8936f8117db96db4` |
| evaluator artifact set | `68cefaa573ab2e28336cf20023147eb21c6a2b2c1cd0c53c6b8dff1c6d3f00dd` |
| root artifact set | `5fc98eafd7435580ed50581adacd3cbbecae45c02295f3733bdc87da3d59629a` |

The root, public, and evaluator frozen manifests are independent immutable
models. Their generated schema files have committed SHA-256 values
`528593f43667c5d036509f92b67f68c159ce0bddc9e5445971ac69086ece5b82`,
`93a17d3f2136e4bc180b5428d66c3fa41edd7b9ea86aa57935ac0117618c57e8`,
and `a7629b3d2ef75bcad3d6dc7cb22fe921f1eda13184c8473d2f326f9ed9c7457a`
respectively.

### Enterprise inventory and checksum record

| Path | Bytes | SHA-256 |
|---|---:|---|
| `manifest.json` | 619 | `af0697c8af4715786d4af1c4b6c9c228bdc2f0b795c69d195355be42b14af3c3` |
| `SHA256SUMS` | 258 | `a0b012bda161183ce925ca75b754cd7cbae942bf7fb4787a7b1258293210e123` |
| `public/public-input.json` | 5,943 | `d7a525cfeb53fcbd62adef9ee9c11dbb5b222ffa47874a8c5a0226d43deb61f0` |
| `evaluator/truth.json` | 1,428 | `7fb510dfad3ef71b7aa895c51c1810b2a9fb354509220ae65fa92e27e254736b` |

Root `manifest.json` inventories the public and evaluator payloads and binds
public-input digest
`d7a525cfeb53fcbd62adef9ee9c11dbb5b222ffa47874a8c5a0226d43deb61f0`.
`SHA256SUMS` lists evaluator payload, root manifest, and public payload in sorted
relative-path order and excludes itself. This lineage publishes no separate
aggregate artifact-set digest; the checksum-record bytes have SHA-256
`a0b012bda161183ce925ca75b754cd7cbae942bf7fb4787a7b1258293210e123`.
The independent frozen manifest schema
`c08-enterprise-manifest-v2.schema.json` has SHA-256
`cfbf56a9c4b1ee9c78b2e2f13dada01ce0a132e75ad66d9cea23c935d033bab2`.

The enterprise packaged loader validates exact inventory, regular-file and
symlink boundaries, canonical JSON, all checksum rows, manifest descriptors,
public/evaluator digest and semantic bindings, and then compares all bytes and
models with `generate_c08_reference(20260809)`. Integrity-valid alternate seed
bytes are therefore rejected as the wrong fixed-reference identity.

### Public binding-handle and distractor semantics

Both public contracts expose requirements as evidence kind plus opaque binding
handle, not expected observation ID. Each required kind has at least one
same-action, same-kind distractor with a different handle, while exactly one
observation matches the required handle. A reference submission can be built
from public correlation semantics without evaluator truth. Asteria makes public
IDs and ordinals scenario-neutral. Enterprise derives public observation IDs in
a separate namespace so source evidence IDs are absent from public bytes.
Evaluator truth retains exact IDs, tenant/action binding, and Asteria case labels.

This boundary prevents accidental answer-key use; it is not secrecy. The task is
deliberately publicly solvable by correlating handles and action semantics.

### Metric-only baseline records

The fixture inventory is exactly:

| Path | Bytes | SHA-256 |
|---|---:|---|
| `tests/fixtures/c08_v2/asteria/baseline-records.json` | 5,739 | `df2e1b321677d44ab99b48103f8d2b856938332dd3601aa35c746611a67b3731` |
| `tests/fixtures/c08_v2/enterprise/baseline-records.json` | 5,028 | `cf3424f7fe463d50fd77b07444cfba2cfa5c1820af1dac6a5126a5ae734b6787` |

Each aggregate file contains benchmark ID, schema version, public-input digest,
failure mode, submission digest, and denominator-bearing metrics only. It contains
no submission rows, observations, evidence IDs, action IDs, outcomes, evaluator,
or truth. Asteria's missing/discarded, fabricated, wrong-action, and extra records
each lower their dedicated metric from `6/6` to `5/6`. Enterprise missing lowers
completeness to `5/6`; fabricated, wrong-action, and extra expose their dedicated
rate at `1/7`. These committed records do not prove their reproduction tests ran.

### Completed native adversarial findings

- Kind-only candidate uniqueness was answer-revealing. Binding handles plus
  same-kind distractors now require actual correlation.
- Public ordering and source identifiers could encode labels or source truth.
  Ordering is canonical and scenario-neutral; enterprise public IDs are separately
  derived opaque observation IDs.
- Untyped/incomplete manifests and checksum-only acceptance allowed
  self-consistent replacement risk. Independent immutable manifest schemas,
  exact inventories, cross-bindings, and fixed-reference comparison close it.
- Publication checks bypassed the enterprise packaged loader. They now call both
  packaged loaders.
- Eleven per-case baseline files over-disclosed structure. They are replaced by
  exactly two aggregate metric-only files with dedicated discrimination.
- V1 evidence trusted recorded metadata or covered only four enterprise examples.
  The candidate now recomputes Asteria roots from explicit ten-public/seven-
  evaluator inventories and pins all ten enterprise agentic examples and schemas.
- Enterprise reports did not carry the limitation strongly enough. Every report
  now serializes `offline_artifacts_only=true` and explicit limitations for live
  retention, durable logging, and enforcement behavior.

### Expanded v1 hash evidence

Asteria's explicit ten-file public and seven-file evaluator base inventories
recompute to the unchanged roots
`9ef217b5d604f42a68b7c97596c550698293f1a44f402dbc3d39a2cef19c4594`
and `3d856f39a5c34ca891ec61298a40ee5bfcb134feae5db7b8a20f6ce9078b2b3f`.

| Enterprise v1 path | SHA-256 |
|---|---|
| `examples/enterprise-agentic-evaluator.json` | `9fbf331d8a037e444d3b756007ce1ab2426b3cd39ab46461cb1343bbccbfb723` |
| `examples/enterprise-agentic-metrics.json` | `983f5abb9ee17b91dbfec39fd029c8ebce3ed1de738f500a32dc01f4b61864c7` |
| `examples/enterprise-agentic-prediction.json` | `c8af6e28c4d7e47f86969cff9a669081414414c498abc9ae1cd46ccb5252a2bd` |
| `examples/enterprise-agentic-public-input.json` | `ca581923b57927c9595a6e3f44e783bcdc02bd329f6bd9b79eee11ea034f28a3` |
| `schemas/enterprise-agentic-benchmark.schema.json` | `7ca6c5fa4de53ff527b535871663606750c2dce1ddb143e1971cbaad89531f10` |
| `schemas/enterprise-agentic-evaluator.schema.json` | `b1d5ee7109c4cf0e151c30ec414976bc7fbd210607bdf2bd50ae07e930c6dbfc` |
| `schemas/enterprise-agentic-metrics.schema.json` | `979d31dc1c55e1dd034eb2840e06c3730558e17872d14fd798f520c7f6948862` |
| `schemas/enterprise-agentic-prediction.schema.json` | `f3cd117cd476176e79a2fb5264e04fb7f671815a335db6f6976578c4890bccb6` |
| `schemas/enterprise-agentic-public-input.schema.json` | `97418f7200ffdbc9665562e0560ce55cdf3ab65f3ee4baa4843a114f8aae9b1b` |
| `schemas/enterprise-agentic-truth.schema.json` | `5a3352b538fcac485e3d9d0449760586201207cb91897d113371e2ff4b377a1a` |

The assertions exist, but this documentation reconciliation did not run them.

### Pending evidence, scope, and publication status

CI, Ruff lint, Ruff format checking, schema `--check`, package build,
isolated-wheel execution, clean-install loading, and byte-for-byte regeneration
verification remain pending. The current publication test also pins an earlier
`a0b012...`; no passing checksum-root gate is claimed.

Reports measure offline artifact submissions only. They do not prove live
evidence retention, durable logging, enforcement behavior, deployment, real
Asteria/EADS compatibility, or a real EADS export. D8 excludes C13, C15/C16,
Face A, EADS compatibility, deployment, and generated-world demonstrations.
There is no registry entry, external publication, or publication claim.

## C08 v2 corrective audit closure

Fresh-audit finding 4 is resolved in the documented boundary: literal candidate
observation/evidence IDs and public binding handles are public and necessary for
solvability. Only evaluator-selected binding rows, required-ID sets, expected
outcomes, and scenario truth are evaluator-only.

Fresh-audit finding 6 is resolved by the implemented lineage evidence: after
dd40fd9, preservation covers all 19 frozen Asteria v1 files, not only the
previous public/evaluator root subsets. No v1 byte is authorized to change.

The publication-gate pins are enterprise SHA256SUMS
a0b012bda161183ce925ca75b754cd7cbae942bf7fb4787a7b1258293210e123
and Asteria root artifact-set digest
5fc98eafd7435580ed50581adacd3cbbecae45c02295f3733bdc87da3d59629a.
Enterprise additionally requires a same-action/same-kind different-handle
distractor for every requirement, and measurement_scope is schema-required on
reports after 4de6df8.

This records implemented contract corrections and completed native adversarial
resolutions only. CI, Ruff lint and format, schema --check, package builds,
isolated-wheel execution, clean-install checks, and regeneration verification
remain pending; no registry or publication completion is asserted.
