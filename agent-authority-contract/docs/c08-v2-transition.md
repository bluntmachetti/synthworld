# C08 evidence-binding v2 transition

Status: implemented contract candidate, 2026-08-09. Freeze specification locked;
artifacts are not frozen or published.

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

## Locked C08-only freeze contract

The following decisions are fixed for the next bounded freeze phase. They define
the artifact contract; they do not assert that the artifacts or any publication
gate currently exist or have passed.

### Identity and deterministic inputs

The two lineages are independent benchmark identities:

| lineage | benchmark ID | schema version | fixed seed |
|---|---|---|---:|
| Asteria | `asteria-agentic-c08-v2` | `2.0.0` | `20260809` |
| enterprise | `enterprise-agentic-c08-v2` | `2.0.0` | `20260809` |

The seed, benchmark ID, schema version, generator implementation, and explicit
event/input schedule are the complete deterministic inputs for the frozen
fixture. A freeze command must fail rather than substitute another seed or use
wall-clock, locale, host, filesystem, or random UUID state.

### Asteria frozen inventory

The planned packaged inventory is exactly:

```text
src/synthworld/benchmarks/asteria-agentic-c08-v2/public/c08-asteria-public.json
src/synthworld/benchmarks/asteria-agentic-c08-v2/public/manifest.json
src/synthworld/benchmarks/asteria-agentic-c08-v2/evaluator/c08-asteria-evaluator.json
src/synthworld/benchmarks/asteria-agentic-c08-v2/evaluator/checksums.json
```

The public root contains only the public payload and its manifest. The evaluator
root contains only the evaluator payload and its checksum record. The evaluator
root does not gain a second evaluator manifest: this preserves the existing
Asteria v1 convention in which `public/manifest.json` describes the public base
set and `evaluator/checksums.json` cross-binds the evaluator set to the public
artifact-set digest.

The Asteria artifact-set digest is the existing path-bound algorithm: sort the
relative POSIX paths lexicographically; for each path append its UTF-8 bytes,
one NUL byte, and the raw 32-byte SHA-256 digest of that file; SHA-256 the
concatenated stream and encode the result as lowercase hexadecimal. The public
manifest is excluded from the public artifact set. The evaluator checksum file
is excluded from the evaluator artifact set. Per-file records use the same
relative paths and lowercase SHA-256 values. No digest may be computed from a
manifest or checksum record that includes itself.

### Enterprise frozen inventory

The planned packaged inventory is exactly:

```text
src/synthworld/benchmarks/enterprise-agentic-c08-v2/public/public-input.json
src/synthworld/benchmarks/enterprise-agentic-c08-v2/public/manifest.json
src/synthworld/benchmarks/enterprise-agentic-c08-v2/evaluator/truth.json
src/synthworld/benchmarks/enterprise-agentic-c08-v2/evaluator/manifest.json
src/synthworld/benchmarks/enterprise-agentic-c08-v2/SHA256SUMS
```

The public and evaluator roots each contain one payload and one visibility
manifest. The enterprise root uses the existing enterprise `SHA256SUMS`
convention: four sorted relative POSIX-path entries, one for each payload and
manifest, in the form `<lowercase-sha256>  <relative-path>`. `SHA256SUMS` is
excluded from its own listed file set and is never included in its own digest.
Each visibility manifest describes only its sibling payload, records its byte
size and lowercase SHA-256 digest, and excludes the manifest itself from that
payload digest. The public and evaluator manifests are independently validated;
the evaluator manifest also binds the evaluator truth to the public input
digest. No enterprise C08 v1 manifest, payload, or checksum is replaced.

The two inventories are independent. Asteria's `checksums.json` must not be
replaced by enterprise `SHA256SUMS`, and enterprise must not inherit Asteria's
evaluator checksum layout. A shared digest primitive is permitted only if its
path ordering and self-exclusion rules remain byte-for-byte equivalent to the
lineage convention being recorded.

### Baseline record contract and location

Baseline records are deterministic review fixtures, not benchmark truth and not
evaluator artifacts. They are stored outside the package data at:

```text
tests/fixtures/c08_v2/asteria/baseline-records.json
tests/fixtures/c08_v2/enterprise/baseline-records.json
```

Each file is canonical UTF-8 JSON with LF and one trailing newline and contains:

```text
schema_version
benchmark_id
seed
records[]
```

Each record contains `baseline_id`, `failure_mode`, `submission_digest`, and a
complete ordered tuple of metric records. Each metric record contains `name`,
`numerator`, `denominator`, `value`, `denominator_meaning`, and
`undefined_reason`. Records must cover the reference case and every failure
mode declared by that lineage. Asteria covers `exact`, `missing`, `fabricated`,
`wrong_action`, `extra`, and `discarded`; enterprise covers `exact`, `missing`,
`fabricated`, `wrong_action`, and `extra`. Each declared failure mode must
change at least one relevant metric from the perfect reference result. The
records must contain no evaluator binding IDs, case labels, or answer-key
fields beyond the metric outcome needed for this review fixture.

### Evaluation boundary and v1 preservation

The frozen v2 artifacts establish offline reconstruction of evidence bindings
from the observations made available by the fixture. They do not establish
live evidence storage, durable production logging, side-effect enforcement,
runtime authorization, deployment behavior, or whether an omitted observation
was never observed, lost, or discarded. Reports must retain this limitation.

Every existing v1 artifact byte, including its manifests, checksum records,
schemas, loaders, and package assertions, remains unchanged. The v2 transition
adds independently versioned paths; it must not regenerate, relabel, overwrite,
or reserialize any v1 artifact. V1 preservation is an acceptance condition for
the freeze, not a claim that has passed before the v2 artifact and package gates
are run.

### Explicit D8 exclusions

This freeze is limited to `SW-AA-C08` evidence rebinding in the Asteria and
enterprise lineages. It does not include:

- C13.
- C15/C16 model fields or scoring changes.
- Face A or its generated-world implementation.
- Compatibility with a real EADS export or serialized EADS schema.
- Production or reference deployment work.
- Generated-world demonstrations that depend on those deferred tracks.

No C08-only artifact, registry entry, documentation claim, or checksum record
may imply that an excluded item has shipped or been validated.

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
