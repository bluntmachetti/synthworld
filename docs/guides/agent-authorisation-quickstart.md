# Catch an agent authorisation failure

A credential can remain valid after the delegation that authorised an action has
been revoked. This demo shows that failure using seven fictional action cases and
four small teaching policies. You need no external policy service or API key.

## Inspect the result first

[Open the sample decision report](/synthworld/demo-report.html).

The report shows the expected outcome and each policy's decision for every case.
It is an **evaluator view containing reference truth**. It is for readers of the
results, not input to the policy runner.

With seed `20260821`, the baseline teaching policies produce:

| Teaching policy | Correct action decisions | Incorrect allows among four denied actions |
|---|---:|---:|
| RBAC example | 4 / 7 | 3 / 4 |
| ABAC example | 6 / 7 | 1 / 4 |
| ReBAC example | 5 / 7 | 2 / 4 |
| Combined example | 7 / 7 | 0 / 4 |

These numbers compare these implementations on seven constructed cases. They do
not rank RBAC, ABAC, and ReBAC as general approaches.

## Run the demo

**Release status: 0.18.0 candidate, not yet published.** The `synthworld-demo`
command is new in this candidate and is not present in 0.17.0. To preview from this
change's source checkout:

```bash
uv sync --locked --all-groups
uv run python -m examples.enterprise_agentic_identity_pilot run --output authority-demo
```

After 0.18.0 is published, the installed-package path is:

```bash
pip install idcognito-synthworld==0.18.0
synthworld-demo run --output authority-demo
```

Open `authority-demo/results/policy-comparison.html` in your browser. Every path
must be new; the demo refuses to overwrite an existing run.

Generation, policy execution, and scoring run as separate processes. The runner
receives only a public-package path; this local convenience command does not
create an operating-system sandbox. For a real integration, isolate the public
runner with separate jobs or mounts as described in the
[pipeline guide](https://bluntmachetti.github.io/synthworld/guides/development-pipelines/).

## Omit the authority view and see the failure

Use the same seed for the following comparison.

The `--omit-delegation-check` teaching flag omits the combined policy's **entire
ReBAC authority view**, including active delegation, relationship, and coverage
checks; RBAC and ABAC remain enabled. The manifest setting is a declaration, not
execution attestation. Scoring accepts externally edited, correctly bound traces
and evaluates their decisions rather than rerunning the teaching policy. Retain
the result manifest and referenced submission manifest alongside metric JSON to
identify the declared mode and exact submitted bytes.

```bash
synthworld-demo run --omit-delegation-check --output authority-demo-broken
```

For a source preview, replace `synthworld-demo` with
`uv run python -m examples.enterprise_agentic_identity_pilot`.

Open the second comparison report. Find **post revocation action**: the expected
decision is deny, but the modified combined policy allows it. Its role and
credential checks still pass; the omitted ReBAC authority view causes the
incorrect allow. Combined action accuracy falls from 7/7 to 6/7. The report also
shows the effect on audit-time temporal validity.

Restore the authority view by rerunning without the flag in a third, new output
directory.
The package, seed, and world remain the same; the deliberately omitted authority
view is declared in the submission manifest and report.

## Know what you measured

All seven actions receive action-time and audit-time decisions. The policies do
not independently resolve identity, reconstruct ownership or retained evidence,
or execute real side effects. Those capabilities are **not measured** here. Their
zero-valued fields in the underlying JSON report must not be read as tested
failures. No aggregate score hides that distinction.

## Connect your own system next

The demo contains local Python teaching policies, not an OPA adapter or an IAM
product. You can run its stages separately:

```bash
synthworld-demo generate --output authority-world
synthworld-demo run-policies --public-package authority-world/benchmark/public --output authority-submissions
synthworld-demo score --benchmark-root authority-world/benchmark --submissions authority-submissions --output authority-results
```

To test your own system, replace teaching-policy execution with a public-only
adapter and record actual decisions in the generated-world trace contract. Use
[agent authority](https://bluntmachetti.github.io/synthworld/guides/agent-authority/) and [development pipelines](https://bluntmachetti.github.io/synthworld/guides/development-pipelines/).
The demo-specific `score` command verifies its own teaching-policy manifest; score
external traces with `synthworld evaluate generated-enterprise-agentic` instead.
A maintained external-engine integration is a separate next milestone.

If you wanted fictional identity data rather than policy tests, start with
[synthetic identity worlds](https://bluntmachetti.github.io/synthworld/guides/identity-worlds/).
