# Agent authority

Asteria Agentic v1 evaluates whether reported agent actions match delegated
authority at action time and whether audit evidence reconstructs that decision.

```bash
synthworld generate-agentic --output asteria-agentic-v1
synthworld validate agentic-trace --predictions observed-actions.jsonl
synthworld evaluate agentic --predictions observed-actions.jsonl --summary
```

The [Asteria benchmark guide](../../AGENTIC_BENCHMARK.md) describes the frozen
fixture. The [agent-authority contract](../../agent-authority-contract/README.md)
is normative for external traces and evidence claims.

Reference truth ships publicly for conformance. This is not a blind or secret test,
and core trace scoring does not prove deployed enforcement.

## Explorer v0.1 preview

The preview `synthworld.explorer` Python API can project the published Asteria
Agentic v1 public package into deterministic nodes, relationships, and a replayable
public event timeline. It also defines separately typed evaluator-overlay and
layout-manifest contracts, with digest binding that prevents either artifact from
silently attaching to a different public projection.

Available now:

- field-by-field public projection of organisations, departments, principals,
  logical agents, runtimes, credentials, delegations, resources, and action
  attempts;
- stable, domain-separated UUID5 graph identities and answer-independent ordering;
- UTC timeline validation, acyclic compound-node validation, and exact layout-node
  coverage checks; and
- physically separate evaluator annotations carrying a mandatory evaluator-view
  watermark.

Not yet available:

- the `synthworld visualize` command;
- the packaged interactive Cytoscape/ELK renderer;
- adapters for candidate C08 v2 or generated `enterprise_agentic` worlds; and
- large-world filtering, tier comparison, or generated longitudinal navigation.

See [Explorer v0.1 contract and packaging decision](../concepts/explorer-v01.md)
for the exact boundary and deferred renderer design.
