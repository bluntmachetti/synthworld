# C08 evidence-binding v2 transition

Status: implemented frozen-artifact candidate, 2026-08-09. Candidate bytes are
committed; verification and publication gates remain pending.

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

Public actions declare evidence requirements as `(kind, binding_handle)` pairs.
Public evidence events carry opaque observation identifiers, the same correlation
handle, and non-oracle action semantics. Every requirement has a same-action,
same-kind distractor with a different handle, and exactly one candidate matches the
required handle. This makes the public task correlation rather than kind-only echoing
while remaining solvable without evaluator truth. Public identifiers and ordinals do
not encode case labels. Exact action-to-observation IDs and scenario labels remain in
separately typed evaluator truth.

Public, evaluator, and submission artifacts are physically separate. Every
submission and evaluator record binds the exact public-input digest. Asteria uses
independent root, public, and evaluator frozen-manifest models. Enterprise uses one
independent frozen root-manifest model plus a path-bearing `SHA256SUMS`. Both
packaged loaders compare validated payloads with fixed-seed canonical generation.

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

The following decisions describe the committed candidate bytes. They do not assert
that CI, schema drift, packaging, clean-install, regeneration, or publication gates
have passed.

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

### Asteria frozen inventory and digests

The candidate tree contains exactly five files:

```text
src/synthworld/benchmarks/asteria-agentic-c08-v2/manifest.json
src/synthworld/benchmarks/asteria-agentic-c08-v2/public/c08-asteria-public.json
src/synthworld/benchmarks/asteria-agentic-c08-v2/public/manifest.json
src/synthworld/benchmarks/asteria-agentic-c08-v2/evaluator/c08-asteria-evaluator.json
src/synthworld/benchmarks/asteria-agentic-c08-v2/evaluator/manifest.json
```

| Path | Bytes | SHA-256 |
|---|---:|---|
| `manifest.json` | 1,201 | `cb8deb43ab6216c4d913e294a7a88d882aabb75a6ecbc87f66011eb8099ad50b` |
| `public/c08-asteria-public.json` | 8,106 | `b9ed17cac90721a276b28570bd91b5c6f41b106dad5be15fa1257a7e9a16ade3` |
| `public/manifest.json` | 370 | `5313551de8dbf5f6cdf97447fe9ade9c0fa73500dfd8fd387aa8aa4954de69c3` |
| `evaluator/c08-asteria-evaluator.json` | 1,871 | `b94fc5791e36e43e2b2586cdab0c7aaec9c249700e060a784ccc582b13b777f4` |
| `evaluator/manifest.json` | 465 | `bc701080cf88c8a446e31d5d379c360b29939bf51a7e3e017ce41f417bfce45c` |

The path-bound algorithm is `sha256-path-bound-v1`: sort relative POSIX paths;
for each path append its UTF-8 bytes, one NUL byte, and the raw 32-byte SHA-256
of the payload; SHA-256 the concatenated stream. The public and evaluator
artifact sets each contain only their payload and therefore exclude their sibling
manifest. The root set contains both payloads and both visibility manifests and
excludes only root `manifest.json`. The committed artifact-set digests are:

| Set | Digest |
|---|---|
| public input and raw public payload | `b9ed17cac90721a276b28570bd91b5c6f41b106dad5be15fa1257a7e9a16ade3` |
| public artifact set | `fe59c2d365194572c57f1afa892d3a86fffb41e07f5e77ac8936f8117db96db4` |
| evaluator artifact set | `68cefaa573ab2e28336cf20023147eb21c6a2b2c1cd0c53c6b8dff1c6d3f00dd` |
| root artifact set | `5fc98eafd7435580ed50581adacd3cbbecae45c02295f3733bdc87da3d59629a` |

The three immutable manifest contracts have independent generated schemas:
`c08-asteria-frozen-root-manifest-v2.schema.json`,
`c08-asteria-frozen-public-manifest-v2.schema.json`, and
`c08-asteria-frozen-evaluator-manifest-v2.schema.json`.

### Enterprise frozen inventory and digests

The candidate tree contains exactly four files:

```text
src/synthworld/benchmarks/enterprise-agentic-c08-v2/manifest.json
src/synthworld/benchmarks/enterprise-agentic-c08-v2/SHA256SUMS
src/synthworld/benchmarks/enterprise-agentic-c08-v2/public/public-input.json
src/synthworld/benchmarks/enterprise-agentic-c08-v2/evaluator/truth.json
```

| Path | Bytes | SHA-256 |
|---|---:|---|
| `manifest.json` | 619 | `af0697c8af4715786d4af1c4b6c9c228bdc2f0b795c69d195355be42b14af3c3` |
| `SHA256SUMS` | 258 | `a0b012bda161183ce925ca75b754cd7cbae942bf7fb4787a7b1258293210e123` |
| `public/public-input.json` | 5,943 | `d7a525cfeb53fcbd62adef9ee9c11dbb5b222ffa47874a8c5a0226d43deb61f0` |
| `evaluator/truth.json` | 1,428 | `7fb510dfad3ef71b7aa895c51c1810b2a9fb354509220ae65fa92e27e254736b` |

Root `manifest.json` independently binds the public and evaluator payload
inventories and the public-input digest. `SHA256SUMS` contains exactly three
sorted `<lowercase-sha256>  <relative-path>` rows for root manifest, public
payload, and evaluator payload. It excludes itself. The enterprise convention
does not publish an aggregate artifact-set digest; the SHA-256 of the committed
checksum-record bytes is the root integrity-record digest shown above. The
independent immutable manifest schema is
`c08-enterprise-manifest-v2.schema.json`.

`load_packaged_frozen_benchmark()` loads package resources through the same
fail-closed loader as filesystem trees. After exact inventory, checksum,
canonical JSON, public/evaluator binding, and semantic checks, the loader compares
all bytes and parsed models with `generate_c08_reference(20260809)`. A
self-consistent alternate seed is rejected as the wrong root identity.

### Baseline record contract and location

Baseline records are deterministic review fixtures, not benchmark truth and not
evaluator artifacts. They are stored outside the package data at:

```text
tests/fixtures/c08_v2/asteria/baseline-records.json
tests/fixtures/c08_v2/enterprise/baseline-records.json
```

Each file is canonical UTF-8 JSON with LF and one trailing newline and contains:

```text
benchmark_id
schema_version
public_input_digest
records[]
```

Each record contains only `failure_mode`, `submission_digest`, and an ordered
metric tuple. Metric records contain only `name`, `numerator`, `denominator`,
`value`, and `denominator_meaning`. The files contain no submission rows,
observation/evidence/action IDs, outcomes, evaluator payload, or truth. Their
committed SHA-256 values are
`df2e1b321677d44ab99b48103f8d2b856938332dd3601aa35c746611a67b3731`
for Asteria and
`cf3424f7fe463d50fd77b07444cfba2cfa5c1820af1dac6a5126a5ae734b6787`
for enterprise.

Asteria records `exact`, `missing`, `fabricated`, `wrong_action`, `extra`, and
`discarded`. Missing and discarded lower `missing_or_discarded_free`, fabricated
lowers `fabricated_evidence_free`, wrong action lowers
`wrong_action_evidence_free`, and extra lowers `extra_evidence_free`, each from
`6/6` to `5/6`. Enterprise records `exact`, `missing`, `fabricated`,
`wrong_action`, and `extra`. Missing lowers completeness to `5/6`; fabricated,
wrong action, and extra expose their dedicated rate at `1/7`. These are committed
metric records, not evidence that their reproduction test has run.

### Native adversarial findings resolved in the candidate

- Kind-only matching had one candidate and made the expected ID mechanically
  recoverable. Both lineages now require binding handles and plant same-kind
  distractors with distinct handles.
- Public order and source-derived identifiers could encode labels or source
  evidence identity. Ordering is canonical, Asteria ordinals are scenario-neutral,
  and enterprise publishes separately derived opaque observation IDs.
- Untyped or incomplete manifests could accept a self-consistent replacement.
  Frozen manifests are immutable governed models with independent schemas, exact
  inventories, cross-bindings, and fixed-reference comparisons.
- Publication checks parsed enterprise resources without exercising the packaged
  loader. The publication test now calls the packaged loaders for both lineages.
- Per-case baseline files disclosed too much structure and expanded the fixture
  inventory. They were replaced by exactly two aggregate, metric-only records with
  dedicated discrimination assertions.
- V1 preservation checks trusted recorded metadata or covered only part of the
  enterprise contract. They now recompute Asteria roots over explicit base-file
  inventories and pin the complete ten-file enterprise agentic example/schema set.

### Evaluation boundary and v1 preservation

The frozen v2 artifacts establish offline reconstruction of evidence bindings
from the observations made available by the fixture. They do not establish
live evidence storage, durable production logging, side-effect enforcement,
runtime authorization, deployment behavior, or whether an omitted observation
was never observed, lost, or discarded. Reports must retain this limitation.

Every existing v1 artifact byte remains unchanged. Asteria preservation evidence
recomputes the public root over ten named base files and the evaluator root over
seven named base files, retaining digests
`9ef217b5d604f42a68b7c97596c550698293f1a44f402dbc3d39a2cef19c4594`
and `3d856f39a5c34ca891ec61298a40ee5bfcb134feae5db7b8a20f6ce9078b2b3f`.
Enterprise preservation evidence pins all four `enterprise-agentic-*` examples
and all six corresponding schemas. Those assertions are implemented but have not
been run in this documentation reconciliation.

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

## Pending verification and publication evidence

The candidate trees, loaders, governed schemas, adversarial hardening, baseline
records, and expanded v1 assertions are implemented. None of the following has
run for the current committed bytes: CI, Ruff lint, Ruff format checking, schema
`--check`, package build, isolated-wheel execution, clean-install loading, or
byte-for-byte regeneration verification. The enterprise publication test also
still pins an earlier `SHA256SUMS`-bytes digest (`3ad3c6...`) rather than the
committed `a0b012...`; that gate must be reconciled before it can pass.

There is no benchmark-registry entry, external publication, or publication claim
for these candidates. Until the pending evidence is produced, they remain
committed frozen-artifact candidates, not published benchmarks.
