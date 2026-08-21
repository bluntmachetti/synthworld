# Generate enterprise-agentic scale tiers

> **Available since 0.17.0.** Standard and longitudinal use their own V2 contracts;
> the released smoke V1 contract remains unchanged.

SynthWorld provides three generated enterprise-agentic tiers without changing the
frozen Asteria Agentic v1 benchmark or the released generated smoke V1 contract.
These tiers measure generated workload and control behaviour. They are not a vendor
leaderboard, production authorisation claim, IAM service, or agent runtime.

## Tier and contract ladder

| Tier | Contract | Default topology | Default action cases | Purpose |
| --- | --- | --- | ---: | --- |
| `smoke` | `enterprise-agentic-generated-1.0.0` | 1 organisation, 25 humans, 5 agents, 8 runtimes, 6 resources | 7 | Fast CI and adapter validation |
| `standard` | `enterprise-agentic-generated-2.0.0` | 2 organisations, 250 humans, 36 agents, 72 runtimes, 36 resources | 23 | Ordinary comparative evaluation and multi-tenant controls |
| `longitudinal` | `enterprise-agentic-generated-2.0.0` | The standard topology over 180 virtual days | 31 | Rotation, joiner/mover/leaver, suspension, policy change, offboarding, revocation propagation, evidence loss, and audit-time evaluation |

`stress` is explicitly deferred to the generic scale work in
[issue #3](https://github.com/bluntmachetti/synthworld/issues/3). Large generated
worlds remain out-of-band workloads and never become mandatory package fixtures.

## Generate and consume a tier

```bash
synthworld generate-enterprise-agentic \
  --profile generated \
  --tier standard \
  --seed 20260821 \
  --output generated-standard
```

Use `--tier longitudinal` for the lifecycle schedule. Use `--public-only` when the
machine preparing product input must not write an evaluator tree. A JSON file passed
with `--config` supplies a complete validated configuration; explicit `--tier` and
`--seed` values are authoritative and become part of the resolved benchmark identity.

The Python API preserves smoke V1 and exposes V2 separately:

```python
from pathlib import Path

from synthworld.agentic.enterprise import (
    EnterpriseAgenticScaleTierV2,
    default_enterprise_agentic_generation_config_v2,
    export_generated_enterprise_agentic_scale_benchmark,
    generate_enterprise_agentic_scale_world,
)

config = default_enterprise_agentic_generation_config_v2(
    EnterpriseAgenticScaleTierV2.STANDARD,
    seed=17,
)
generated = generate_enterprise_agentic_scale_world(config)
export_generated_enterprise_agentic_scale_benchmark(Path("generated-standard"), generated)
```

Give only `generated-standard/public/` to an adapter. The public tree contains the
base agentic snapshot and ordered events, team, population, resource, and opaque
credential-handle projections, public lifecycle events, the scenario, and the tool
schema. It contains no canonical
bindings, expected decisions, case labels, authority truth, or integrity answer key.
The evaluator tree cross-binds the complete public artifact-set digest.

The existing observed-action JSONL boundary works for every tier:

```bash
synthworld validate generated-enterprise-agentic-trace \
  --benchmark-root generated-standard \
  --predictions observed-actions.jsonl
synthworld evaluate generated-enterprise-agentic \
  --benchmark-root generated-standard \
  --predictions observed-actions.jsonl \
  --summary
```

## Configuration surface

`EnterpriseAgenticGenerationConfigV2` is immutable, rejects extra fields, and binds
the profile, schema, generator, canonical-serialisation and event-schedule versions,
seed, tier, and every resolved knob. Its bounded submodels configure:

- organisations, departments, teams, employees, contractors, suppliers, external
  partners, agents, runtimes, and resources;
- direct-human, organisation, and agent sub-delegation ratios, delegation depth,
  capability breadth, and scope density;
- credential validity, shared-identity prevalence, and runtime-binding breadth;
- independent counts for authorised, capability, child-delegation, runtime,
  shared-credential, tenant, revocation, later-grant, evidence, attribution,
  credential, policy, rotation, suspension, offboarding, and propagation cases;
- virtual duration, rotation interval, evidence retention, policy change, and agent
  offboarding; and
- explicit principal, event, and case generation limits.

Invalid ratios, impossible topologies, lifecycle controls on `standard`, missing
lifecycle controls on `longitudinal`, cross-tenant cases with one organisation, and
limit overruns fail before artifact export.

## Longitudinal event boundary

The base agentic `1.0.0` event union remains unchanged. V2 serialises lifecycle
events as a separate, typed `lifecycle-events.json` stream and keeps their ordering
stable with `sequence_index` plus UTC timestamps. Rotation, suspension, offboarding,
policy activation, principal join/move/leave, and revocation propagation compile to
base credential-validity, delegation, policy, action, evidence, and audit records so
the hardened base replay and evaluator still derive action-time and audit-time truth.
The evaluator-only lifecycle case map supplies the more specific V2 cohort labels.

## Determinism, integrity, and metrics

Dedicated UUID5 namespaces derive opaque IDs only from the explicit configuration
identity. Collections use canonical ordering; event streams retain semantic order;
JSON uses UTF-8, LF, and one trailing newline. Complete loading rebuilds the hardened
base benchmark, re-derives metrics, regenerates the declared world, and compares the
exact public and evaluator bytes.

Metrics are derived from generated records rather than copied from requested counts.
Every count and distribution states its denominator. Reports include topology and
population counts, graph components, owner/delegation depth, delegation branching,
runtimes per agent, credential-runtime binding breadth, allowed/denied actions, case
prevalence,
isolated controls, revocations, evidence loss, lifecycle kinds, and referential and
canonical-binding integrity.

## Runtime and memory receipt

Host observations are deliberately outside deterministic artifacts. Reproduce the
checked-in receipt with:

```bash
uv run python tools/measure_enterprise_agentic_scale.py \
  --source-revision <commit-or-source-digest> \
  --dependency-lock uv.lock \
  --iterations 3 \
  --output enterprise-agentic-tier-performance.json
```

The repository receipt records Python 3.12.12 on Linux with the locked dependency
digest. Three-iteration medians were:

| Tier | Generate | Serialise | Replay | Score | Peak traced memory |
| --- | ---: | ---: | ---: | ---: | ---: |
| `standard` | 2.894 s | 0.035 s | 0.056 s | 0.048 s | 5,465,472 bytes |
| `longitudinal` | 4.043 s | 0.037 s | 0.061 s | 0.048 s | 5,480,891 bytes |

These are environment-specific observations, not deterministic promises. Each row
binds its resolved configuration and complete public artifact-set digest in
[`enterprise-agentic-tier-performance.json`](https://github.com/bluntmachetti/synthworld/blob/main/docs/_data/enterprise-agentic-tier-performance.json).
