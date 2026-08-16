# CLI reference

Run `synthworld --help` and the relevant subcommand `--help` for the installed
version. [Getting Started](../getting-started.md) and
[Evaluating a system](../guides/evaluating-a-system.md) contain runnable examples;
the root [user guide](../../USER_GUIDE.md) is only a historical compatibility index.

The unified `synthworld evaluate <task>` command accepts `agentic`, `broker`,
`continuous-assurance`, `contextual-access`, `enterprise-agentic`,
`generated-enterprise-agentic`, `extraction`, `entity-resolution`, `relationship`,
and `risk`. Some additional package surfaces remain Python-only; use the relevant
contract rather than inferring a CLI.

Enterprise authorization currently has CLI commands only for scaffolding,
validating, and compiling the identity/access import. Corpus construction,
directory/RBAC, ABAC, ReBAC, composition, prediction, and scoring use the
documented `synthworld.enterprise.consumer` Python API. See
[Build and score an enterprise authorization experiment](../guides/enterprise-authorization-python.md).

`generate-enterprise-agentic` preserves its fixed-reference default. Select the
new generated smoke profile explicitly:

```bash
synthworld generate-enterprise-agentic \
  --profile generated \
  --tier smoke \
  --seed 20260814 \
  --output generated-enterprise-agentic
```

Only `smoke` is implemented for generated scale in this version. The command
writes separate `public/` and `evaluator/` trees and refuses to replace an existing
output root. Use `EnterpriseAgenticGenerationConfigV1` directly when topology
counts must differ from the documented smoke defaults.

The fixed and generated enterprise-agentic submissions are deliberately separate
CLI tasks because they use different trace contracts. Reload and check a generated
observed-action trace using only its public tree:

```bash
synthworld validate generated-enterprise-agentic-trace \
  --benchmark-root generated-enterprise-agentic \
  --predictions observed-actions.jsonl
```

Score it only after the complete root is available to the evaluator process:

```bash
synthworld evaluate generated-enterprise-agentic \
  --benchmark-root generated-enterprise-agentic \
  --predictions observed-actions.jsonl \
  --summary
```

Validation checks structure and action-event coverage; it does not claim the
reported observations are correct. The generated benchmark guide defines the
required event replay and public/evaluator separation.
