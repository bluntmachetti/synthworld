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

See [Enterprise Identity Planning](https://bluntmachetti.github.io/synthworld/guides/enterprise-identity-planning/) for how this
separate reference world relates to today's human enterprise compiler and the
generated enterprise-agentic work under issue #27.

## Generated enterprise-agentic smoke world

The first configurable generated slice is separate from both frozen Asteria and
the fixed-universe enterprise-agentic reference pack:

```bash
synthworld generate-enterprise-agentic \
  --profile generated \
  --tier smoke \
  --seed 20260814 \
  --output generated-enterprise-agentic
```

The default smoke topology contains one fictional organisation, 25 humans, five
logical agents, eight runtimes, six resources, five delegations, and ten opaque
credential records. Seven action cases exercise authorised access, excess
capability, wrong runtime binding, expired credentials, valid-then-revoked access,
incorrect attribution, and post-revocation access. Counts are defaults in a
validated Python configuration model, not an unversioned promise hidden behind the
tier name.

```python
from synthworld.agentic.enterprise import (
    EnterpriseAgenticGenerationConfigV1,
    EnterpriseAgenticSmokeTopologyV1,
    generate_enterprise_agentic_world,
)

config = EnterpriseAgenticGenerationConfigV1(
    seed=17,
    topology=EnterpriseAgenticSmokeTopologyV1(
        department_count=2,
        human_principal_count=12,
        logical_agent_count=3,
        runtime_count=4,
        resource_count=4,
    ),
)
benchmark = generate_enterprise_agentic_world(config)
```

The output has physically separate `public/` and `evaluator/` trees. Public input,
the scenario, and its tool schema are checksum-bound as one set; evaluator truth
cross-binds that complete public-set digest and contains the independently derived
topology, decision, case, and graph-integrity metrics. Only the `public/` tree is a
product input.

Benchmark identity binds the versioned configuration, generator, canonical
serialization, event schedule, seed, tier, and resolved topology. It does not read
the clock, filesystem order, Python version, platform, or Git state. Runtime and
memory measurements are host observations and belong in a separate receipt keyed
to the artifact digest.

This slice is an implementation-neutral deterministic benchmark generator. It is
not an IAM product, policy engine, agent runtime, hosted simulator, vendor
leaderboard, or claim about deployed enforcement. `standard` and `longitudinal`
generated tiers remain follow-up work in issue #27; the existing 1.0 event union is
not being widened to imply those lifecycle semantics.

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
- Explorer adapters for candidate C08 v2 or generated `enterprise_agentic` worlds;
  and
- large-world filtering, tier comparison, or generated longitudinal navigation.

See [Explorer v0.1 contract and packaging decision](../concepts/explorer-v01.md)
for the exact boundary and deferred renderer design.
