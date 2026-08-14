# Documentation ownership record

The detailed documentation surface is the Blume site under `docs/`. Root files remain concise repository entry points or authoritative generated/contract references.

`USER_GUIDE.md` is retained only as a compatibility index so existing repository anchors continue to resolve. It is not a second hand-maintained guide system.

## Canonical ownership

| Topic | Canonical owner |
|---|---|
| Documentation entry and goal routing | `docs/index.md` |
| Installation and first run | `docs/getting-started.md` |
| General evaluation workflow | `docs/guides/evaluating-a-system.md` |
| Core/generated identity worlds | `docs/guides/identity-worlds.md` plus `BENCHMARKS.md` |
| Entity resolution and ambiguity | `docs/guides/identity-resolution.md` |
| Extraction, risk, exposure, broker, search | `docs/guides/privacy-exposure.md` |
| Agent authority | `docs/guides/agent-authority.md`, `AGENTIC_BENCHMARK.md`, and the agent-authority contract |
| Enterprise Identity Planning | `docs/guides/enterprise-identity-planning.md` |
| Enterprise identity/access | `docs/guides/enterprise-access.md` and the enterprise contract |
| Standards-shaped projections | `docs/reference/standards-profiles.md` and the enterprise contract |
| CLI availability | `docs/reference/cli.md` and installed `--help` output |
| Metric/report interpretation | `docs/reference/metrics.md` and task contracts |
| Public/evaluator boundary | `docs/concepts/public-vs-evaluator.md` |
| Safety boundary | `docs/concepts/safety-boundary.md` |
| Benchmark inventory and reference values | `BENCHMARKS.md` |
| Field and schema definitions | `DATA_DICTIONARY.md` and contract READMEs |
| Release history | `CHANGELOG.md` |
| Direction | `ROADMAP.md` with the site Now/Next/Later view |

## Compatibility exception

The household/workplace generation-cost measurement remains in `USER_GUIDE.md` under its historical `Generation cost` anchor because no other authoritative generated-performance page currently carries those measured values. The compatibility index labels this explicitly rather than duplicating the measurement elsewhere.

Future changes should update the canonical owner in the same pull request as the implementation. Do not reintroduce detailed user documentation into the root README.
