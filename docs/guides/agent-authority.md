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
