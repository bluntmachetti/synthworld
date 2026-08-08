# EADS adapter Phase 1: sanitized gap requirements

## Status and boundary

This document is the reviewed, sanitized aggregate requirements record for the
Phase 1 humans-only EADS adapter. It describes known semantic mismatches that an
adapter and future generated-world work must handle. It is not a source export,
validation report for a named organisation, frozen benchmark artifact, checksum
manifest, or `GOLDEN_REVIEW.md` record.

No raw organisation topology, source path, namespace salt, source-content
digest, person record, or real organisation, vendor, or product label belongs in
this public record. Deterministic per-run details remain in the private adapter
output. This summary does not claim that any raw EADS export is bundled, tested,
imported, or validated by SynthWorld.

## Phase 1 decisions

- **Humans only.** Phase 1 creates human populations and their bounded
  identity/access structure. Agents, workloads, services as identities, and
  other non-human identities are deferred. BIAN-specific interpretation is
  deferred.
- **Tenant isolation.** Each source organisation maps independently to one
  tenant and one organisation. Tenant is the isolation boundary; the one-to-one
  mapping avoids implying unsupported cross-organisation tenant semantics.
- **Explicit reference profiles.** `sdk-size-v1` and
  `topology-headcount-v1` are strict, caller-selected profiles inferred from
  planning inputs and synthetic fixtures. Shape inference and mixed-profile
  input are prohibited. Compatibility with the 31 real exports remains
  unproven until a representative sanitized export or exact schema is pinned.
- **Bounded input.** The reader accepts at most 50 MiB plus one detection byte
  from a no-follow regular-file descriptor. Its restricted parser permits only
  JSON-compatible finite scalars and string keys, enforces depth and node
  limits, rejects YAML duplicate keys, aliases, merges, custom tags, and
  non-JSON scalars, and sanitizes recursion and memory failures.
- **Deterministic population policy.** Source `size` and `headcount` values are
  validated but ignored. Source-export `scale`, `team_type`, and `industry`
  fields are interpreted by the adapter profile, not supplied as independent
  SynthWorld inputs. Counts follow the exact published policy below.
- **Fictional public output.** Source organisation, vendor, and product labels
  cannot cross into compiled or public artifacts. Safely fictional labels and
  opaque deterministic identifiers are required.
- **Private deterministic input.** A private 256-bit namespace salt, encoded as
  64 lowercase hexadecimal characters, is an explicit deterministic input and
  must never be published. Opaque references use keyed HMAC under that salt. The
  canonical source payload digest covers normalized JSON-compatible content,
  not exact source bytes or a path.
- **Atomic publication boundary.** The output root may be absent or existing
  and empty; non-empty roots and non-directories are rejected. The run is staged
  and atomically promoted. Imports and reports remain under `private/`;
  manifested reference artifacts remain under physically separate
  `artifacts/<opaque-ref>/public/` and `evaluator/` trees. Partial failure exits
  nonzero while retaining correctly manifest-bound artifacts for successful
  organisations beside the failure report. All-excluded emits no artifacts and
  exits nonzero; every other zero-success run also exits nonzero.
- **Frozen Asteria v1.** This adapter does not change Asteria v1 schemas,
  semantics, artifacts, checksums, or evaluation. Any generated-world agentic
  profile is a later independently versioned transition.

## Population policy `eads-human-population-policy-v1`

Scale bases are `micro=4`, `small=8`, `medium=16`, `large=32`, and
`enterprise=64`. Team factors are `product=3/2`, `operations=5/4`,
`control=1`, and `platform=3/2`; aliases are `controls -> control`,
`ops -> operations`, `product-team -> product`, and
`platform-team -> platform`. Unknown team types use factor `1` and emit a gap.
Industry factors are `banking=5/4`, `financial-services=5/4`,
`healthcare=5/4`, `logistics=1`, `public-services=1`, `research=1`, and
`technology=3/2`; unknown industries use factor `1` and emit a gap.

Raw count is `max(1, nearest(scale_base * team_factor * industry_factor))`.
Exact halves round up using `(numerator + denominator // 2) // denominator`.
`--max-principals-per-organisation` defaults to `10000`, is limited to
`1000000`, and triggers `largest-remainder-proportional-v1` above the cap. That
profile floors one person per team, distributes the remaining cap
proportionally to `raw_count - 1`, then assigns residual people by largest
fractional remainder and canonical team key. It fails below the team count.

## Aggregate gap register

| Gap | Phase 1 treatment | Requirement created |
| --- | --- | --- |
| Region, regulatory, and geopolitical metadata has no faithful enterprise v1 unit representation. | Retain sanitized category-level gap metadata; do not map regions to tenants or invent a unit kind. | A future model must distinguish security isolation from geographic and regulatory placement if those dimensions become evaluable. |
| Source domain trees may be deeper or use different levels than the closed division/department/team vocabulary. | Apply an explicit deterministic hierarchy-collapse policy and report every collapsed level or rejected shape. | Generated worlds must include deep and uneven hierarchies that discriminate faithful mapping from silent flattening. |
| Classifications may be null or present but enterprise v1 has no faithful target field. | Map no classification into enterprise v1. Record null and present classifications as distinct unexpressed gaps; do not reject or guess from labels. | A future mapping contract needs typed classification semantics and discriminating null-versus-present cases. |
| Ownership declarations may express operational responsibility, service stewardship, escalation, or other semantics that are not enterprise authorization grants. | Supported `owner` and `approver` rows widen intentionally to the whole mapped employee team through `AllSelector`; record that fidelity loss and any owning-team divergence from `owning_team_id`. Record and skip unsupported ownership. | Future scenarios must distinguish ownership, accountability, approval, and authority instead of treating them as synonyms. |
| Source `size` or legacy `headcount` can be placeholder, commercially sensitive, or semantically inconsistent. | Validate the selected vintage's field but never use it to generate people. Record that source scale was ignored. | Population must remain reproducible from the published mix-policy version and explicit scale/team/industry inputs. |
| Service types and labels may contain unsupported tiers, vendor vocabulary, or product vocabulary. | Reject unsupported enum values and fictionalize accepted targets before compilation or publication. | Mapping tests must prove that real vendor/product labels cannot leak into compiled output or this aggregate report. |
| Phase 1 has no non-human identity, delegation, credential, capability, or action-generation mapping. | Defer BIAN and all agent/workload identities; do not anticipate future schema fields in the humans-only adapter. | Issue #27 generated-world work must add independently typed non-human identities, authority, credentials, actions, and evaluator truth without mutating Asteria v1. |
| A source set may contain only BIAN/excluded organisations, partially fail, or otherwise yield no compilable organisation. | Retain manifest-bound artifacts for successful organisations with the failure report and exit nonzero. All-excluded emits no artifacts; every zero-success run exits nonzero. | Automation must distinguish partial success, exclusion, and total compile failure from a fully successful conversion. |

## Issue #27 generated-world requirements

The Phase 1 private gap reports are design input for later issue #27 work, not a
generated-world fixture themselves. A future design must:

- generate safely fictional enterprise worlds rather than package source
  organisations or raw source labels;
- preserve tenant isolation separately from organisation, region, and
  regulatory dimensions;
- include discriminating hierarchy-collapse, unknown-classification, ownership,
  and source-scale cases;
- introduce non-human identities, delegation, credential/capability bindings,
  and action parameters only through new typed and independently versioned
  contracts;
- keep public product input physically and structurally separate from evaluator
  truth; and
- coordinate any new frozen benchmark publication with schemas, checksums,
  integrity and packaging tests, documentation, and `GOLDEN_REVIEW.md`.

Until that transition is designed and reviewed, Phase 1 remains a humans-only
adapter to existing enterprise v1 inputs and Asteria v1 remains unchanged.
