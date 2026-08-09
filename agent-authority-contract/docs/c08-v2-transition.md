# C08 evidence-binding v2 transition

Status: implemented contract candidate, 2026-08-09. Not frozen or published.

This transition gives `SW-AA-C08` independently versioned Asteria and enterprise
surfaces for evidence completeness. Existing v1 models, metric names, schemas,
artifacts, checksums, loaders, and scoring remain unchanged.

## Contract boundary

Each lineage owns separate immutable, `extra="forbid"` models for:

- public actions and canonically ordered evidence observations;
- evaluator-only action-to-required-evidence bindings and case labels;
- product submissions containing selected observed evidence identifiers; and
- independent denominator-bearing metrics and reports.

The Asteria implementation lives in `synthworld.agentic.c08_v2`. The enterprise
implementation lives in `synthworld.agentic.enterprise.c08_v2`. Equivalent
semantics do not make them one combined cross-domain model.

Public actions declare closed evidence-kind requirements. Public evidence events
carry opaque observation identifiers and the non-oracle semantics needed to
correlate them. They do not carry required observation identifiers, expected case
labels, or verdicts. Exact action-to-observation requirements remain in separately
typed evaluator truth. A reference submission can be constructed from public
semantics without loading evaluator truth.

Public, evaluator, and submission artifacts are physically separate. Every
submission and evaluator record binds the exact public-input digest. Canonical
manifests bind the Asteria roots; the enterprise serializer preserves the same
physical split while its frozen-manifest transition remains a later gate.

## What the metrics mean

The v2 metrics discriminate:

- exact evidence-set reconstruction;
- missing evidence;
- fabricated evidence identifiers;
- evidence assigned to the wrong action or tenant; and
- known but non-required extra evidence.

Every metric states its numerator, denominator, denominator meaning, and undefined
state. Exactness, completeness, fabrication, wrong-action assignment, and excess
evidence remain independent rather than being hidden behind one aggregate score.

This is still offline synthetic artifact evaluation. It establishes whether a
submission reconstructs the required evidence bindings from the observations made
available by the fixture. It does not prove live storage durability, production log
integrity, side-effect enforcement, or deployment behavior. A missing identifier in
an offline submission does not reveal whether evidence was never observed, lost, or
discarded, so the contract does not claim to distinguish those causes.

## Determinism and schemas

Both reference builders are pure functions of an explicit nonnegative integer seed
and use dedicated UUID5 namespaces. They do not read wall-clock, host, locale,
filesystem order, or random UUID state. Serialization is canonical UTF-8 JSON with
LF and one trailing newline.

Authoritative Pydantic models generate the Asteria and enterprise public,
evaluator, submission, report, and manifest schemas. `make schemas` checks both
families for drift.

## Remaining freeze gates

Before any C08 v2 artifact becomes a frozen benchmark, a later transition must add:

- fixed generated public and evaluator roots with checksums and package inventory;
- byte-for-byte clean-install reproduction from the built wheel;
- public/evaluator recursive leakage and cross-binding tests;
- discriminating baseline records for every declared failure mode;
- benchmark-registry publication metadata and documentation;
- an adversarial and safety review; and
- a new `GOLDEN_REVIEW.md` record containing exact artifact-set digests.

Until those gates pass, these packages are versioned contract candidates, not a
published benchmark and not evidence that v1 retained more than it reported.
