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

## Render the published Asteria authority world

Create a deterministic, self-contained public HTML view from a generated or
reproduced Asteria Agentic v1 public package:

```bash
synthworld generate-agentic --output asteria-agentic-v1
synthworld visualize \
  --public-package asteria-agentic-v1/public \
  --view agent-authority \
  --output asteria-public.html
```

Reference truth is opt-in and must come from the separately verified evaluator
tree:

```bash
synthworld visualize \
  --public-package asteria-agentic-v1/public \
  --evaluator-package asteria-agentic-v1/evaluator \
  --view agent-authority \
  --output asteria-evaluator.html
```

Evaluator output is visibly watermarked. The default `--package-profile asteria`
accepts only the published Asteria v1 artifact-set digest and refuses to
overwrite an existing file. It does not render enterprise authorization
packages.

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

## Render a generated enterprise-agentic world

Select the generated package contract explicitly to render a verified generated
public tree with the same shared Explorer renderer:

```bash
synthworld visualize \
  --public-package generated-enterprise-agentic/public \
  --view agent-authority \
  --package-profile generated-enterprise-agentic \
  --output generated-public.html
```

The public command reads only the public tree and never opens evaluator truth.
Passing `--evaluator-package generated-enterprise-agentic/evaluator` as well
verifies both trees, their digest cross-binding, and declared generator
conformance before producing watermarked evaluator output. Unsupported generated
tiers or package versions fail explicitly rather than rendering a partial view.
Layout coordinates are computed deterministically from the projection alone, so
the same verified package always produces the same HTML bytes.

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
