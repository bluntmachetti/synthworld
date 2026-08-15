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

> **Available in 0.15.0.** Generation, public-only artifact validation, and
> complete-root evaluation are available through the Python and CLI surfaces below.

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
from pathlib import Path

from synthworld.agentic.enterprise import (
    EnterpriseAgenticGenerationConfigV1,
    EnterpriseAgenticSmokeTopologyV1,
    export_generated_enterprise_agentic_benchmark,
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
export_generated_enterprise_agentic_benchmark(
    Path("generated-enterprise-agentic"), benchmark
)
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

### Run an external system against the generated world

Give an adapter only the `public/` subtree. Keep the complete benchmark root in a
separate evaluator process. Public loading verifies canonical bytes, the exact
inventory, manifests, the duplicated scenario, and the tool schema without listing
or opening `evaluator/`. Complete loading additionally cross-checks the two trees,
re-derives metrics, and reproduces the declared generator output from its versioned
configuration.

The adapter must process public events in `event_index` order. Apply runtime,
credential, and delegation changes as they appear; query the system immediately
when an `action_attempted` event appears; save that observation; then continue to
later revocation, evidence-loss, and audit events. Evaluating every action against
the final state destroys the distinction between valid-then-revoked and
post-revocation cases.

Normalize actual system observations into the `ObservedActionTrace` JSONL contract.
Do not copy a principal, owner chain, delegation path, or evidence reference from
SynthWorld into the trace unless the system or its captured execution evidence
actually returned it. A decision-only policy decision point can legitimately submit
only the event identifier and decision. Its authorization metrics are then the
relevant result; zeroes in unobserved identity and provenance dimensions must not be
presented as capabilities of that policy decision point.

Validate in the public-only process:

```bash
synthworld validate generated-enterprise-agentic-trace \
  --benchmark-root generated-enterprise-agentic \
  --predictions observed-actions.jsonl
```

After the trace has been saved outside the product path, score it in the evaluator
process:

```bash
synthworld evaluate generated-enterprise-agentic \
  --benchmark-root generated-enterprise-agentic \
  --predictions observed-actions.jsonl \
  --summary
```

An external organisation YAML can be used as a sizing brief for the supported
topology counts. Version 0.15.0 does not import named organisations, departments,
people, or relationships from that file: SynthWorld creates its own safely fictional
graph. Exact topology import would require a new versioned input contract.

Generated manifests prove internal consistency. The public-only loader does not
establish who created a tree. For a reproducible lab, retain the exact package or
wheel digest, benchmark configuration and identity, public/evaluator artifact
digests, trace bytes, adapter and policy digests, and observable system version.
This is still an offline ground-truth evaluation unless separately captured
execution evidence supports a stronger lab claim.

This slice is an implementation-neutral deterministic benchmark generator. It is
not an IAM product, policy engine, agent runtime, hosted simulator, vendor
leaderboard, or claim about deployed enforcement. `standard` and `longitudinal`
generated tiers remain follow-up work in issue #27; the existing 1.0 event union is
not being widened to imply those lifecycle semantics.

## Explorer v0.1 preview

Version 0.15.0 ships a projection-only `synthworld.explorer` Python API. It can
project the published Asteria Agentic v1 public package into deterministic nodes,
relationships, and a replayable public event timeline. It also defines separately
typed evaluator-overlay and layout-manifest contracts, with digest binding that
prevents either artifact from silently attaching to a different public projection.
The projector returns data records; it does not render HTML or provide an
interactive viewer.

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
