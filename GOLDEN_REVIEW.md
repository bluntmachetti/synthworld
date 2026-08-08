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

## Risk-v1 review record

Reviewed: 2026-08-08. Seed: `20260719`. Risk benchmark and schema versions:
`1.0.0`.

This record reviews the existing frozen risk-v1 publication without re-cutting
or changing its artifacts. The public input is
`src/synthworld/benchmarks/risk-public-golden-v1.json`; the separate evaluator
answer is `src/synthworld/benchmarks/risk-answer-golden-v1.json`. The evaluator
answer is published reference truth, not a private held-out artifact. Their
checked-in checksum manifests are
`src/synthworld/benchmarks/RISK_PUBLIC_SHA256SUMS` and
`src/synthworld/benchmarks/RISK_ANSWER_SHA256SUMS`.

The recorded SHA-256 values are
`690c2fb081826f72970af1e729651819c3563d9aa590190d566af24424238b33` for the
public payload,
`32479aa077887a63d31a4de3dfbc822f01f6622f09ea6dd6d2a87e3af3cb319e` for the
evaluator answer,
`16f95e9d9e9f7539e8f14fab4688cf5c0ed995bb539ad415456ec77c08688a73` for the
public checksum manifest, and
`07e300c8eee695c0eef60af9a4701cd5df03457215f5c310b1a9d7e05ff087cd` for the
evaluator checksum manifest.

The review confirms that the public and evaluator payloads remain physically
separate, that the evaluator truth is not inferred from a path or mislabeled as
private, and that the four existing files and their recorded checksums remain
the publication boundary. This is an artifact-integrity and boundary record;
it makes no new held-out-evaluation or Hugging Face publication claim.
