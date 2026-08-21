# Enterprise agentic identity policy pilot

This example compares four experiment-owned, decision-only policy views over one
deterministic generated enterprise-agentic smoke world. It demonstrates a practical
identity-planning loop: generate a safely fictional authority world, run RBAC,
ABAC, ReBAC, and combined policies using public artifacts only, then score the
resulting traces in a separate evaluator process and inspect deterministic HTML.

The policies are teaching examples, not the independently versioned
`synthworld.enterprise` authorization contracts and not an authorization engine.
The generated benchmark remains the source of identity, authority events, and
reference truth.

## Run the three process boundaries

Run these commands from the repository root. Each output path must be absent; the
pilot refuses to overwrite an existing artifact tree.

### 1. Generate one world

```bash
uv run python -m examples.enterprise_agentic_identity_pilot generate \
  --seed 20260821 \
  --output pilot-output
```

Run `generate` once. All four policy strategies below consume the same public tree
and are later scored against the matching evaluator tree. The default smoke
configuration contains one fictional organisation, four departments, 25 humans,
five logical agents, eight runtimes, six resources, and seven action cases.

Generation writes:

```text
pilot-output/
  benchmark/
    public/                         # product/adapter input
    evaluator/                      # scorer-only reference truth
  experiment/
    policy-overlay.json             # reviewable experiment proposal
    world-summary.json
  visuals/
    world-public.html               # public SynthWorld Explorer view
```

`experiment/policy-overlay.json` records the proposal in a readable form. The
executable policy implementations remain in [`policies.py`](policies.py); the JSON
file is not a SynthWorld policy contract or a production policy bundle.

### 2. Run policies with only the public package

```bash
uv run python -m examples.enterprise_agentic_identity_pilot run-policies \
  --public-package pilot-output/benchmark/public \
  --output pilot-submissions
```

Treat this as a separate system-under-test process. Mount or copy only
`pilot-output/benchmark/public/` into that process; do not mount its evaluator
sibling. The runner verifies the public package, replays public events at action
time and audit time, and writes four decision-only traces plus a digest manifest:

```text
pilot-submissions/
  rbac.jsonl
  abac.jsonl
  rebac.jsonl
  combined.jsonl
  manifest.json
```

The manifest binds the exact verified public artifact set and generated benchmark
identity, the policy overlay and implementation source digests, and every trace
byte. The evaluator rejects submissions whose public or policy-source binding does
not match the benchmark and pilot it is running.

No policy trace reads expected decisions, case labels, canonical bindings, failure
reasons, or other evaluator truth.

### 3. Score in the evaluator process

```bash
uv run python -m examples.enterprise_agentic_identity_pilot score \
  --benchmark-root pilot-output/benchmark \
  --submissions pilot-submissions \
  --output pilot-results
```

Only this process receives the complete benchmark root. It verifies the public and
evaluator trees and their digest binding before scoring the four saved traces. The
result is:

```text
pilot-results/
  reports/
    rbac.json
    abac.json
    rebac.json
    combined.json
  manifest.json
  policy-comparison.html            # experiment-owned evaluator report
  world-evaluator.html              # evaluator SynthWorld Explorer view
```

Both result HTML files contain reference truth and are visibly watermarked. Keep
them outside the public policy-runner boundary. The public graph is
`pilot-output/visuals/world-public.html`; the corresponding truth-enabled graph is
`pilot-results/world-evaluator.html`. Every HTML file is self-contained and can be
opened locally in a browser. The result manifest verifies and records the exact
submission manifest and trace digests, public and evaluator artifact sets,
benchmark identity, policy sources, and the report and HTML bytes produced from
them.

## Policy roles

| Strategy | Role in the experiment |
| --- | --- |
| RBAC | Assigns every generated logical agent a coarse, organisation-scoped `agent_reader` entitlement ceiling for `read` actions. |
| ABAC | Checks agent/resource organisation, runtime binding, credential validity, action, scope, purpose, and policy-version attributes. |
| ReBAC | Follows the active originator-to-agent delegation, capability coverage, runtime relationship, and revocation state. |
| Combined | Applies default deny and allows only when the RBAC, ABAC, and ReBAC views all allow. |

The separate strategies make the generated negative cases discriminating. They do
not imply that any single mechanism is a complete authorization design or that the
combined strategy is automatically appropriate for another organisation.

## What the results do and do not show

The scorer reports independent metrics with their own support and denominator. The
comparison HTML focuses on authorization accuracy and precision/recall, least
privilege, excess authority, and temporal validity. There is no aggregate score
that can hide a weak dimension.

This pilot is intentionally bounded:

- It uses one generated `smoke` package. It does not ingest an organisation YAML,
  a fixed-reference `enterprise-agentic` authorization package, or an arbitrary
  universe produced by `compile-enterprise-access`.
- Its four policies are local Python examples over the generated public event
  model. They are not SynthWorld RBAC/ABAC/ReBAC artifacts and do not prove a
  deployed PDP implements those mechanisms.
- The submissions report decisions only. They do not claim that the policy runner
  observed or reconstructed identity, ownership, provenance, or evidence fields.
- The evaluation is deterministic offline evidence for a design discussion, not
  proof of production enforcement, security, performance, availability, scale,
  interoperability, or vendor superiority.
- The evaluator comparison page is experiment-owned reporting. Only the two world
  pages are SynthWorld Explorer renders, and neither is a hosted service or policy
  engine.

Retain the seed, package version or wheel digest, generated manifests, policy and
submission bytes, and evaluator results when sharing the experiment.
