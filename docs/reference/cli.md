# CLI reference

Run `synthworld --help` and the relevant subcommand `--help` for the installed
version. [Getting Started](../getting-started.md) and
[Evaluating a system](../guides/evaluating-a-system.md) contain runnable examples;
the root [user guide](../../USER_GUIDE.md) is only a historical compatibility index.

The unified `synthworld evaluate <task>` command accepts `agentic`, `broker`,
`continuous-assurance`, `contextual-access`, `enterprise-agentic`, `extraction`,
`entity-resolution`, `relationship`, and `risk`. Some additional package surfaces
remain Python-only; use the relevant contract rather than inferring a CLI.

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
