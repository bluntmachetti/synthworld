# Explorer v0.1 contract and packaging decision

Status: packaged Asteria renderer available; the generated enterprise-agentic
smoke adapter from issue #149 is available as a separately versioned profile.

Explorer v0.1 is a deterministic projection contract and renderer boundary for
benchmark packages that SynthWorld already publishes. It is not a general graph
browser, an authorization engine, or a generated-world interface for the planned
`enterprise_agentic` tiers.

The package ships the Python projection contracts introduced in 0.15.0 and a
checksum-verified renderer for the published Asteria Agentic v1 package. The
renderer produces one deterministic, self-contained HTML file. It does not accept
arbitrary topology files, generated enterprise-agentic packages, or experiment
visualizations.

## Immediate scope

The first supported profile is `agent-authority-v1`, projected from the public
artifact set of the published `asteria-agentic-v1` benchmark. Its view includes:

- organisation, department, principal, logical-agent, runtime, credential,
  delegation, resource, and action-attempt nodes;
- containment, ownership, delegation, runtime, credential, and attempted-action
  relationships; and
- the public event timeline needed to replay grants, actions, revocation, evidence
  disposal, and audit activity.

The second supported profile is `enterprise-agentic-generated-v1`, projected
from a verified released generated enterprise-agentic public package (smoke
tier). It reuses the same node, edge, and timeline contracts and the same
shared renderer; only its independently versioned source record, profile
literal, and computed layout differ. Candidate C08 v2 and fixed-reference
`enterprise_agentic` packages are not Explorer inputs. Large-world controls,
standard and longitudinal generated tiers, and tier comparisons remain deferred
until issue #27 fixes those package contracts.

## Artifact boundary

Explorer keeps its released public projection, evaluator overlay, and layout v1
contracts independently versioned. The packaged renderer uses layout manifest
`2.0.0`; layout `1.0.0` remains unchanged for compatibility.

| Artifact | Visibility | Binding |
| --- | --- | --- |
| Public projection | public | published benchmark identity and public artifact-set SHA-256 |
| Evaluator overlay | evaluator | public projection SHA-256 and evaluator artifact-set SHA-256 |
| Layout manifest `2.0.0` | public or evaluator renderer | public projection SHA-256, explicit world/profile identity, and pinned layout inputs |
| Generated projection `1.0.0` | public | generated configuration SHA-256, world identity, and public artifact-set SHA-256 |
| Generated layout `1.0.0` | public or evaluator renderer | public projection SHA-256 plus explicit world/profile identity, computed deterministically at render time |

The generated enterprise-agentic profile does not widen the frozen
`agent-authority-v1` projection, evaluator, or layout literals in place; it is an
independent `1.0.0` contract with its own source record. The shared evaluator
overlay contract is reused unchanged for generated worlds because its digest
bindings are already world-agnostic.

The public projection is constructed field by field from `AgenticPublicBundle`.
It cannot carry expected decisions, canonical bindings, case labels, authority
truth, or failure reasons. Evaluator annotations use a separate model and a
separate physical artifact. Any evaluator-rendered HTML must display:

> EVALUATOR VIEW - CONTAINS REFERENCE TRUTH

Evaluator data must never be embedded in public HTML behind a client-side switch.
The evaluator contract has its own schema-version identity even when its current
version number matches the public projection version.

## Identity, normalization, and collisions

Projection node and edge IDs are UUID5 values under the dedicated Explorer v1
namespace. UUID names use explicit `node` and `edge` domains and length-framed
UTF-8 components. This prevents delimiter ambiguity and separates otherwise equal
node and edge inputs. Duplicate resulting IDs, source-reference failures, and
open graph references fail validation rather than receiving suffixes.

Set-like nodes, edges, properties, annotations, references, and coordinates are
sorted by stable identifiers or keys. Collection-valued properties remain JSON
arrays rather than delimiter-joined strings. Timeline events retain source
event-index order, use UTC, and must also be strictly increasing in time. Compound
node parents must be acyclic. No ordering key may depend on an evaluator verdict,
case kind, failure reason, or canonical binding.

Canonical JSON uses sorted object keys, compact separators, UTF-8, no NaN values,
LF line endings, and exactly one trailing newline. Digests cover those exact bytes.

## Deterministic layout inputs

The layout manifest records all inputs that can alter coordinates:

- public projection digest;
- world seed and world schema version;
- visualisation profile and visualisation-profile version;
- layout engine and exact engine version;
- algorithm and direction;
- node and layer spacing;
- viewport width and height;
- coordinate precision; and
- one canonical coordinate record per rendered node.

The renderer must not accept filesystem order, locale, host state, wall-clock time,
or evaluator answers as layout inputs.
The layout repeats the projection's world seed and world schema version plus the
visualisation profile and profile version. Validation compares those explicit values
and also verifies the public-projection digest, which binds the complete projection
source and published benchmark identity.
Layout validation requires exactly one coordinate per bound projection node.
Evaluator validation requires every annotation to bind a public action event and a
known projection node, edge, or timeline event.

## Packaged renderer

The renderer uses Cytoscape 3.34.1 in the browser and a committed layout generated
by ELK.js 0.12.0. Exact npm dependencies are locked; the generated CSS, JavaScript,
layout manifest, and dependency notices are checksum-bound package assets. The
HTML does not load JavaScript, CSS, fonts, layout code, or data from a CDN or other
network origin. Its content-security policy disables connections, and the layout
is validated against the exact public projection digest before rendering.

The CLI binds to verified package directories rather than ambiguous standalone
JSON:

```console
synthworld visualize \
  --public-package ./asteria-agentic-v1/public \
  --view agent-authority \
  --output world.html
```

The public command reads only the public tree. To inspect reference truth, pass the
separate evaluator tree explicitly:

```console
synthworld visualize \
  --public-package ./asteria-agentic-v1/public \
  --evaluator-package ./asteria-agentic-v1/evaluator \
  --view agent-authority \
  --output evaluator-world.html
```

The complete loader verifies both inventories and their public/evaluator digest
binding before deserializing either one. Evaluator HTML contains a prominent
reference-truth watermark and evaluator annotations; public HTML contains neither.
The command refuses to replace an existing output file.

The rendered page supports graph pan/zoom, node and edge inspection, event-timeline
replay, revocation state, and evaluator annotations when explicitly enabled. The
coordinates are pinned build artifacts: the browser never recomputes layout from
host state or evaluator truth.

## Generated enterprise-agentic adapter

Generated worlds vary by seed and topology, so their coordinates cannot be
committed build assets. The `enterprise-agentic-generated-v1` adapter instead
computes a deterministic kind-layered grid in Python from the projection alone
and records the engine, spacing, viewport, and per-node coordinates in the
independently versioned generated layout contract. The browser still receives
preset coordinates and never recomputes layout.

```console
synthworld visualize \
  --public-package generated-enterprise-agentic/public \
  --view agent-authority \
  --package-profile generated-enterprise-agentic \
  --output generated-public.html
```

The public command consumes only the verified public tree - no repository
examples, private topology source, or evaluator access. Evaluator truth requires
the separate evaluator tree, verifies both inventories, digest cross-binding,
and declared generator conformance, and produces the same prominent watermark.
Unsupported generated tiers or package versions fail explicitly.

Four surfaces stay distinct and must not be conflated:

- **Topology import** (`scaffold/validate/compile-enterprise-access`) authors a
  private fictional identity/access universe; it is never a rendering input.
- **Generated benchmark artifacts** (`generate-enterprise-agentic --profile
  generated`) are the checksum-bound public and evaluator trees.
- **Visualization** (`visualize --package-profile generated-enterprise-agentic`)
  projects and renders the verified public tree, with evaluator truth as a
  separately loaded, digest-bound, watermarked overlay.
- **Authorization evaluation** (`validate`/`evaluate
  generated-enterprise-agentic`) scores observed-action traces; the Explorer
  never imports its verdicts into public output.

## Deliberate limitations

- The Asteria profile accepts only the published `asteria-agentic-v1` public
  artifact-set digest; the generated profile accepts only verified released
  generated smoke packages.
- The legacy core identity world remains a deterministic smoke surface whose path
  topology carries no structural signal. It is not an Explorer v0.1 input, and a
  chain-shaped rendering of it would not be evidence of meaningful organisation
  structure.
- The generated enterprise-agentic smoke package is not silently coerced into the
  Asteria view; its issue #149 adapter is a separately versioned profile selected
  explicitly with `--package-profile generated-enterprise-agentic`.
- The HTML is a local inspection aid, not a hosted service, policy engine, agent
  runtime, or evaluator report.
- The npm toolchain is needed only to reproduce or verify committed renderer assets;
  released-wheel users need only Python and a browser.
