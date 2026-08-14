# Explorer v0.1 contract and packaging decision

Status: implementation contract for issue #52.

Explorer v0.1 is a deterministic projection and rendering boundary for benchmark
packages that SynthWorld already publishes. It is not a general graph browser, an
authorization engine, or a generated-world interface for the planned
`enterprise_agentic` tiers.

## Immediate scope

The first supported profile is `agent-authority-v1`, projected from the public
artifact set of the published `asteria-agentic-v1` benchmark. Its view includes:

- organisation, department, principal, logical-agent, runtime, credential,
  delegation, resource, and action-attempt nodes;
- containment, ownership, delegation, runtime, credential, and attempted-action
  relationships; and
- the public event timeline needed to replay grants, actions, revocation, evidence
  disposal, and audit activity.

Candidate C08 v2 and `enterprise_agentic` packages are not Explorer v0.1 inputs.
Large-world controls, generated tiers, tier comparisons, and longitudinal generated
world navigation remain deferred until issue #27 fixes those package contracts.

## Artifact boundary

Explorer has three independently serialized `1.0.0` contracts:

| Artifact | Visibility | Binding |
| --- | --- | --- |
| Public projection | public | published benchmark identity and public artifact-set SHA-256 |
| Evaluator overlay | evaluator | public projection SHA-256 and evaluator artifact-set SHA-256 |
| Layout manifest | public or evaluator renderer | public projection SHA-256 and pinned layout inputs |

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
- layout engine and exact engine version;
- algorithm and direction;
- node and layer spacing;
- viewport width and height;
- coordinate precision; and
- one canonical coordinate record per rendered node.

The renderer must not accept filesystem order, locale, host state, wall-clock time,
or evaluator answers as layout inputs.
Layout validation requires exactly one coordinate per bound projection node.
Evaluator validation requires every annotation to bind a public action event and a
known projection node, edge, or timeline event.

## Renderer packaging decision

The rendering tranche will use pinned npm versions of Cytoscape and ELK, committed
through a lockfile and bundled at build time into a self-contained HTML artifact.
It will not load JavaScript, CSS, fonts, or layout code from a CDN at runtime.
Dependency license notices will ship with the bundle. Generated minified vendor
blobs will not become hand-maintained Python source.

The CLI will bind to verified package directories rather than ambiguous standalone
JSON:

```console
synthworld visualize \
  --public-package ./asteria-agentic-v1/public \
  --view agent-authority \
  --output world.html
```

Evaluator rendering will require a separate explicit evaluator package argument and
will produce evaluator-labelled output. CLI wiring and HTML rendering follow after
the projection contract lands.
