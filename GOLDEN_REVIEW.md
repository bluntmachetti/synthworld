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
