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
