# Run an enterprise agentic identity experiment

> **Preview on main.** The policy pilot example and generated Explorer adapter
> described here are current-main behavior. Run them from a repository checkout;
> use the documentation at a signed release tag for released behavior.

Use this guide to compare RBAC, ABAC, ReBAC, and a default-deny combination over
one deterministic enterprise-agentic world. The workflow generates the world
once, keeps the policy runner away from evaluator truth, projects the public and
evaluator views separately, and produces self-contained HTML for a design review.

This is a bounded architecture experiment. The policies in the repository example
are experiment-owned Python views over the generated public event stream. They are
not SynthWorld enterprise authorization contracts, a production policy decision
point, or an agentic overlay applied to an imported organisation.

## State the question before generating data

A useful hypothesis for the released smoke slice is:

> A deliberately broad RBAC role sets an action-and-resource entitlement ceiling,
> ReBAC proves a current delegated-authority path, and ABAC guards the runtime,
> credential, and request context. Requiring all three should reject cases that
> any one view misses.

The seven generated action cases deliberately test authorised access, excess
capability, wrong runtime binding, expired credentials, valid-then-revoked access,
incorrect attribution, and post-revocation access. This is a conformance slice for
mechanism coverage, not evidence that one architecture is universally best.

## Preserve the process boundaries

```text
generator
  |-- benchmark/public/ ------> public-only policy runner
  |                                  |
  |                                  +--> decision-only JSONL traces
  |
  +-- benchmark/evaluator/ ----> evaluator-only scorer
                                     ^
                                     |
                              saved JSONL traces

public tree ----> public projection + layout ----> public Explorer HTML
complete tree --> evaluator overlay -------------> watermarked evaluator HTML
```

The policy process receives the direct `public/` tree and never lists or opens its
`evaluator/` sibling. Only the scoring process receives the complete benchmark
root. The public Explorer page is suitable for world inspection; the evaluator
Explorer page and policy comparison page contain reference truth and require
evaluator custody.

Run the commands below from a current-main repository checkout after
`uv sync --locked --all-groups`. Every output path must be absent because the
generator, pilot, and Explorer writers refuse to overwrite existing data.

## 1. Generate one shared world

The repository pilot creates the split benchmark, a reviewable policy proposal,
world summary, and public Explorer page in one step:

```bash
uv run python -m examples.enterprise_agentic_identity_pilot generate \
  --seed 20260821 \
  --output pilot-output
```

The default smoke configuration contains one safely fictional organisation, four
departments, 25 humans, five logical agents, eight runtimes, six resources, and
seven action cases. Generation writes:

```text
pilot-output/
  benchmark/
    public/
      manifest.json
      public-input.json
      scenarios/enterprise-agentic-smoke-v1.json
      tool_schemas/enterprise-agentic-actions-v1.json
    evaluator/
      manifest.json
      truth.json
  experiment/
    policy-overlay.json
    world-summary.json
  visuals/
    world-public.html
```

All four policy strategies must consume these exact public bytes. Do not generate
a new world for each strategy.

To generate only the released benchmark package through the core CLI, use the
explicit generated profile:

```bash
uv run synthworld generate-enterprise-agentic \
  --profile generated \
  --tier smoke \
  --seed 20260821 \
  --output generated-enterprise-agentic
```

That command writes `generated-enterprise-agentic/public/` and
`generated-enterprise-agentic/evaluator/` directly. Only `smoke` is implemented
for this generated profile.

## 2. Generate the public projection and evaluator overlay

### Render self-contained HTML

The pilot already writes `pilot-output/visuals/world-public.html`. The equivalent
explicit public render is:

```bash
uv run synthworld visualize \
  --public-package pilot-output/benchmark/public \
  --view agent-authority \
  --package-profile generated-enterprise-agentic \
  --output pilot-world-public.html
```

This command verifies and opens only the exact public tree. It projects
organisations, departments, principals, agents, runtimes, credentials,
delegations, resources, action attempts, and the event timeline. It then derives
deterministic grid coordinates from that public projection and writes one offline
HTML file.

Create a separate, visibly watermarked evaluator view only in the scorer boundary:

```bash
uv run synthworld visualize \
  --public-package pilot-output/benchmark/public \
  --evaluator-package pilot-output/benchmark/evaluator \
  --view agent-authority \
  --package-profile generated-enterprise-agentic \
  --output pilot-world-evaluator.html
```

The evaluator command verifies the two trees, their digest cross-binding, and the
declared deterministic generator output before attaching a separately typed truth
overlay. Evaluator truth does not influence node coordinates.

| Output | Input boundary | Use |
| --- | --- | --- |
| Public Explorer HTML | `public/` only | Inspect identities, authority relationships, and timeline events without verdicts. |
| Evaluator Explorer HTML | `public/` plus `evaluator/` | Inspect expected decisions and evaluator annotations; keep watermarked. |
| Policy comparison HTML | Complete benchmark plus saved submissions | Compare the four scored policy traces; this is experiment-owned reporting, not an Explorer policy overlay. |

Explorer does not draw the four candidate policy decisions on the authority graph.
Use `policy-comparison.html`, generated during scoring, for that comparison.

### Export the projection contracts as JSON

The HTML renderer performs projection and layout internally. Export the same
versioned artifacts explicitly when a team wants to review them, feed a separate
visualiser, or retain their digests:

```python
from pathlib import Path

from synthworld.agentic.enterprise import (
    generated_enterprise_agentic_artifact_checksums,
    load_generated_enterprise_agentic_benchmark,
    load_generated_enterprise_agentic_public_tree,
)
from synthworld.explorer import (
    canonical_json_bytes,
    compute_generated_enterprise_agentic_layout,
    project_generated_enterprise_agentic_evaluator_v1,
    project_generated_enterprise_agentic_v1,
    validate_evaluator_overlay,
    validate_generated_layout,
)

benchmark_root = Path("pilot-output/benchmark")
projection_root = Path("pilot-projections")
projection_root.mkdir()

public = load_generated_enterprise_agentic_public_tree(benchmark_root / "public")
projection = project_generated_enterprise_agentic_v1(public)
layout = compute_generated_enterprise_agentic_layout(projection)
validate_generated_layout(projection, layout)

generated = load_generated_enterprise_agentic_benchmark(benchmark_root)
evaluator_digest = dict(
    generated_enterprise_agentic_artifact_checksums(generated)
)["evaluator"]
overlay = project_generated_enterprise_agentic_evaluator_v1(
    projection,
    generated.evaluator,
    evaluator_artifact_set_digest=evaluator_digest,
)
validate_evaluator_overlay(projection, overlay)

for name, artifact in (
    ("public-projection.json", projection),
    ("public-layout.json", layout),
    ("evaluator-overlay.json", overlay),
):
    with (projection_root / name).open("xb") as destination:
        destination.write(canonical_json_bytes(artifact))
```

`public-projection.json` and `public-layout.json` derive only from verified public
input. `evaluator-overlay.json` contains reference truth. Keep it with evaluator
results, even if all three files share one directory for a controlled review.

Do not add projection or HTML files inside a verified `public/`, `evaluator/`, or
complete benchmark root. Package loaders enforce exact inventories and reject
extra files. Use an external sibling such as `pilot-projections/` or `visuals/`.

## 3. Run the policy views from public data only

Mount or copy only `pilot-output/benchmark/public/` into the policy process, then
run:

```bash
uv run python -m examples.enterprise_agentic_identity_pilot run-policies \
  --public-package pilot-output/benchmark/public \
  --output pilot-submissions
```

The process verifies the public package, replays events in `event_index` order, and
writes `rbac.jsonl`, `abac.jsonl`, `rebac.jsonl`, `combined.jsonl`, plus a digest
manifest. That manifest binds the exact public artifact set and benchmark identity,
the policy proposal and implementation source digests, and every trace byte. Each
trace reports only the action-time and audit-time decision; it does not claim
identity, ownership, evidence, or provenance observations that the example policy
did not produce.

The proposed roles are:

| Strategy | Experiment role |
| --- | --- |
| RBAC | Assign every generated logical agent a coarse, organisation-scoped `agent_reader` role with `read` permission on managed resources. |
| ABAC | Check organisation, runtime binding, credential validity, action, scope, purpose, and policy version. |
| ReBAC | Follow the originator-to-agent delegation, capability coverage, agent-to-runtime relationship, and revocation state. |
| Combined | Apply default deny and allow only when RBAC, ABAC, and ReBAC all allow. |

The readable proposal is
[`policy-overlay.json`](../../examples/enterprise_agentic_identity_pilot/policy-overlay.json);
the executable source is
[`policies.py`](../../examples/enterprise_agentic_identity_pilot/policies.py).
Review both: the JSON is descriptive and is not a SynthWorld policy contract.

Replay matters. Decide immediately when each `action_attempted` event occurs, save
that observation, continue through later revocation events, and re-evaluate at
audit time using the event prefix immediately before the audit event. Evaluating
every action against final state erases the difference between
valid-then-revoked and post-revocation cases.

## 4. Score in the evaluator boundary

Give the scorer the complete benchmark root and the saved submissions:

```bash
uv run python -m examples.enterprise_agentic_identity_pilot score \
  --benchmark-root pilot-output/benchmark \
  --submissions pilot-submissions \
  --output pilot-results
```

The scorer checks every JSONL file against the digest declared in the adjacent
submission manifest, rejects a different public artifact set or policy source, and
verifies public/evaluator package binding before writing:

```text
pilot-results/
  reports/{rbac,abac,rebac,combined}.json
  manifest.json
  policy-comparison.html
  world-evaluator.html
```

Both HTML files in `pilot-results/` contain reference truth and are visibly
watermarked. The result manifest binds the exact public and evaluator artifact
sets, benchmark identity, policy sources, submission manifest and traces, reports,
and HTML bytes.

For an external system that emits the generated observed-action contract, validate
its saved trace in a public-only process and evaluate it separately:

```bash
uv run synthworld validate generated-enterprise-agentic-trace \
  --benchmark-root generated-enterprise-agentic \
  --predictions observed-actions.jsonl

uv run synthworld evaluate generated-enterprise-agentic \
  --benchmark-root generated-enterprise-agentic \
  --predictions observed-actions.jsonl \
  --summary
```

`validate` expects a parent containing `public/`; for hard isolation, pass a parent
whose only child is the copied public tree. `evaluate` requires the complete parent
with both `public/` and `evaluator/`.

## 5. Interpret the smoke result

Seed `20260821` gives the following decision-only comparison:

| Strategy | Decision accuracy | Least privilege | Excess authority | Temporal validity |
| --- | ---: | ---: | ---: | ---: |
| RBAC | 4/7 | 1/4 | 3/4 | 0/2 |
| ABAC | 6/7 | 3/4 | 1/4 | 0/2 |
| ReBAC | 5/7 | 2/4 | 2/4 | 2/2 |
| Combined | 7/7 | 4/4 | 0/4 | 2/2 |

Read every metric with its support and denominator. Do not collapse the dimensions
into one score. These numbers show why the selected negative cases distinguish the
mechanisms; they do not establish production fitness or rank authorization models
in general. In particular, `incorrect_attribution` is expected to allow at the
authorization layer, and these decision-only traces submit no attribution
observation. The combined strategy's 7/7 authorization result therefore does not
mean that it detected or corrected the attribution mismatch.

Use the review to record which condition closed each gap, which production facts
would supply the corresponding role, attribute, or relationship, and what evidence
would prove revocation and audit behavior in the real system.

## Reproducibility and acceptance checklist

Retain:

- the SynthWorld version plus source commit or wheel digest;
- seed, configuration, topology, generator, serialization, schema, and event
  schedule versions;
- public and evaluator manifests and their digest binding;
- the readable policy proposal and executable policy implementation digest;
- the four submission traces and submission manifest;
- reports, result manifest, and both watermarked evaluator HTML files; and
- the system-under-test version and separately captured runtime receipt, if one
  was involved.

Before presenting results, check that repeated runs with the same inputs produce
the same bytes, the policy runner succeeds with no evaluator sibling, altered or
mixed package trees are rejected, public HTML contains no evaluator verdicts, and
evaluator HTML displays its watermark. The generated cases cover wrong runtime,
invalid credential, excess capability, and revocation. This broad RBAC baseline
assigns every generated logical agent, so add an explicit unassigned-role fixture
as a follow-up when adapting the pattern to a selective production role model.

## Scope and current limitations

- The generated smoke world is an independently versioned enterprise-agentic
  package. It is not an agentic overlay on an arbitrary universe from
  `compile-enterprise-access`, imported organisation YAML, or named production
  topology.
- The example RBAC, ABAC, ReBAC, and combined policies are experiment-owned. They
  are not the separately versioned `synthworld.enterprise` authorization compiler
  outputs and do not provide production enforcement.
- The fixed-reference `enterprise-agentic` package and arbitrary compiled
  enterprise authorization packages are not inputs to this Explorer profile.
- Explorer is an offline inspection aid, not a policy engine, hosted simulator, or
  evaluator report. Only the released generated `smoke` profile is supported;
  standard, longitudinal, and large-world navigation remain out of scope.
- Decision-only traces evaluate authorization decisions. They do not prove
  identity resolution, attribution, ownership reconstruction, evidence retention,
  provenance, security, availability, performance, interoperability, or live
  revocation enforcement.

Continue with
[Agent authority](https://bluntmachetti.github.io/synthworld/guides/agent-authority/)
for the generated benchmark and Explorer contracts,
[Enterprise Identity Planning](https://bluntmachetti.github.io/synthworld/guides/enterprise-identity-planning/)
for the broader roadmap boundary, and the
[`examples/enterprise_agentic_identity_pilot` README](../../examples/enterprise_agentic_identity_pilot/README.md)
for the repository example's concise command reference.
