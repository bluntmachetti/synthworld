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

This record covers two independently versioned, offline C08 evidence-completeness
artifact candidates: `asteria-agentic-c08-v2` and
`enterprise-agentic-c08-v2`. They are not a combined schema or a claim of
interoperability. Their public inputs, evaluator truth, serialisation, and
checksum conventions intentionally remain lineage-specific.

### Asteria artifact inventory and digests

The Asteria root manifest records these four non-root-manifest files:

| Path | Bytes | SHA-256 |
|---|---:|---|
| `public/c08-asteria-public.json` | 5272 | `a0890759311552d99300420f0770792dba0b6daee9d5fb7f1b6552f252e676cd` |
| `public/manifest.json` | 346 | `9b49d963aca311e203bfc557b589acea112d021a78332a1aa3b90dfd3d9d7995` |
| `evaluator/c08-asteria-evaluator.json` | 1871 | `c9f855143ed78922f38045a3e74441f1dec6b81a8018fac9322aef3aae727b5b` |
| `evaluator/manifest.json` | 441 | `1ce34b25cd8e45b2e036ed4281cf175ad466ff1c7dbcba187da4cdd24b90a677` |

`public/manifest.json` binds only `c08-asteria-public.json` and records public
artifact-set digest
`064bb7752f388d695e05905f2981a9dc0f02efdcaf7c596b430e86febdfdc732`.
`evaluator/manifest.json` binds only `c08-asteria-evaluator.json`, cross-binds
the public-input digest
`a0890759311552d99300420f0770792dba0b6daee9d5fb7f1b6552f252e676cd`, and
records evaluator artifact-set digest
`92d62f85f5e82676c116bd01a3e14f1f5808538f24b4fff3f3f8d66f307ac4ae`.
The root `manifest.json` records those two roots, the same public-input digest,
and combined artifact-set digest
`a1c72b05a391416ccfacf6eb4bc18ecca342f834b007ee9b1bb0c26a795d21e8`.

The self-exclusion rule is explicit in the inventory: each visibility manifest
is excluded from its own visibility root; the root manifest includes the two
visibility manifests and data files but excludes its own bytes. This avoids a
self-referential digest without silently omitting either visibility manifest
from the combined record.

### Enterprise artifact inventory and checksums

The enterprise root `manifest.json` records the public and evaluator inventories:

| Path | Bytes | SHA-256 |
|---|---:|---|
| `public/public-input.json` | 3682 | `56274ccd6548a2734e5075728aecddb0a6c9b7d67ed93229ca1e5e7b75676810` |
| `evaluator/truth.json` | 877 | `3de3a7bffcb7adc09fa523e41e8383d23f0ba552e671efefa2f069ad44036557` |
| `manifest.json` | recorded by `SHA256SUMS` | `6091c901612658bbd70efa26d159b0ef1c223000b25f4379a7c22328f6127b9b` |

`SHA256SUMS` uses SHA-256 lines with relative paths for those three files and
explicitly excludes `SHA256SUMS` itself. The committed enterprise records do
not publish a separate aggregate root digest. This review therefore does not
invent one: the authoritative enterprise integrity record is the path-bearing
checksum list plus the manifest's public-input digest
`56274ccd6548a2734e5075728aecddb0a6c9b7d67ed93229ca1e5e7b75676810`.

### Public/evaluator boundary review

Both packs physically separate public input from evaluator truth. Asteria's
public file contains action and observation metadata and required evidence
kinds, while evaluator truth carries exact required-observation bindings and
scenario labels. Enterprise public input contains actions and evidence events;
enterprise evaluator truth carries the exact required evidence IDs and tenant
bindings. No verdict, expected metric result, or evaluator case label is present
in either public artifact.

This is API-hygiene and accidental-leakage protection, not a secrecy or
anti-cheating guarantee. Public action requirements and observation kinds can
make portions of the required set inferable to a reader of the public artifact.
The evaluator artifact is shipped with the package, so it must never be treated
as confidential. Boundary and adversarial validation remain required gates.

### Determinism, baselines, and pending gates

The committed files were materialised by the deterministic C08 v2 generators
for the pinned seed. This review does **not** claim a passed test suite,
byte-for-byte regeneration comparison, checksum-verifier run, wheel build,
isolated-wheel load, or CI run. Those integrity, canonical-JSON, packaging,
and clean-install gates remain pending until CI supplies the evidence.

Committed baseline records exercise exact, missing, fabricated, wrong-action,
and extra evidence in both lineages; Asteria also records discarded evidence.
The exact records are kept under `tests/fixtures/c08_v2/`, separate from the
benchmark trees. Asteria's exact case is perfect; each non-exact case lowers its
dedicated metric to `5/6`: missing and discarded lower
`missing_or_discarded_free`, fabricated lowers `fabricated_evidence_free`,
wrong action lowers `wrong_action_evidence_free`, and extra lowers
`extra_evidence_free` (each also lowers exact match). Enterprise missing records
completeness `5/6` and exact match `2/3`; fabricated, wrong-action, and extra
each record action binding `6/7` and exact match `2/3`, with respectively
fabrication, wrong-action, or extra rate `1/7`. These are discrimination records,
not evidence that their tests have run in this review.

The existing Asteria Agentic v1 lock values remain public artifact-set digest
`9ef217b5d604f42a68b7c97596c550698293f1a44f402dbc3d39a2cef19c4594` and
evaluator artifact-set digest
`3d856f39a5c34ca891ec61298a40ee5bfcb134feae5db7b8a20f6ce9078b2b3f`.
This documentation-only packet does not modify any v1 artifact path. CI must
still prove their byte and hash preservation. There is no frozen enterprise C08
v1 tree with a corresponding preservation digest.

### Scope and limitations

C08 v2 scores offline artifact submissions only. It does not prove live evidence
retention, durable production logging, side-effect or policy enforcement,
deployment behaviour, real Asteria export compatibility, EADS compatibility,
or a real EADS export. D8 authorises only this C08 v2 transition: C13, C15/C16,
Face A, EADS compatibility, deployment, and generated-world demonstrations are
explicitly excluded.
