# Documentation migration index

This execution tracker maps every semantic heading in `USER_GUIDE.md`. The guide
remains intact until canonical replacements are complete and validated.

| Source heading | Canonical destination | Retained summary | State | Validation |
|---|---|---|---|---|
| SynthWorld user guide | `docs/index.md` | Documentation entrypoint | Summary migrated | Link review pending |
| Choose your use case | `docs/index.md` | Goal routing | Summary migrated | Link review pending |
| The three-part workflow | `docs/guides/evaluating-a-system.md` | Public input, adapter, evaluator | Summary migrated | Link review pending |
| Try SynthWorld without installing it | `docs/index.md` | Published-table route | Summary migrated | External publication review pending |
| Install and create your first world | `docs/getting-started.md` | Install and deterministic generation | Migrated | Command validation pending |
| Run five foundational evaluation examples | `docs/getting-started.md` | Public-only baseline walkthrough | Summary migrated | Command validation pending |
| Use case 1: safe connected identity fixtures | `docs/guides/identity-worlds.md` | Core fixture journey | Summary migrated | Detailed guide retained |
| Use case 2: PII extraction | `docs/guides/privacy-exposure.md` | Extraction journey | Routed | Detailed guide retained |
| Use case 3: entity resolution | `docs/guides/identity-resolution.md` | Matching journey | Routed | Detailed guide retained |
| Use case 4: relationship inference | `docs/guides/identity-worlds.md` | Relationship evidence journey | Routed | Detailed guide retained |
| Use case 5: breach-risk calibration | `docs/guides/privacy-exposure.md` | Risk journey | Routed | Detailed guide retained |
| Use case 6: agent identity and delegated authority | `docs/guides/agent-authority.md` | Agentic conformance journey | Summary migrated | Contract guide retained |
| Use case 7: exposure scenarios | `docs/guides/privacy-exposure.md` | Exposure corpus journey | Routed | Detailed guide retained |
| Use case 8: households and workplaces | `docs/guides/identity-worlds.md` | Population graph journey | Routed | Detailed guide retained |
| Generation cost | `docs/guides/identity-worlds.md` | Performance caveat | Retained in source | Migration pending |
| Use case 9: identity-resolution ambiguity | `docs/guides/identity-resolution.md` | Adversarial ambiguity journey | Summary migrated | Detailed guide retained |
| Two truths, kept apart | `docs/concepts/public-vs-evaluator.md` | Physical/type separation | Migrated | Concept review pending |
| Score complete partitions before projecting pairs | `docs/guides/identity-resolution.md` | Partition-first scoring | Migrated | Metric review pending |
| The report has no aggregate score | `docs/reference/metrics.md` | Independent metrics | Migrated | Metric review pending |
| Reference baselines (identity resolution) | `docs/guides/identity-resolution.md` | Baseline context | Retained in source | Migration pending |
| Limits, stated plainly (identity resolution) | `docs/guides/identity-resolution.md` | Scope limits | Retained in source | Migration pending |
| Use case 10: search-provider input without the answer key | `docs/guides/privacy-exposure.md` | Search projection journey | Routed | Detailed guide retained |
| The public half rejects truth, it does not merely omit it | `docs/concepts/public-vs-evaluator.md` | Typed leakage rejection | Migrated | Concept review pending |
| Controlled failure modes, all planted deliberately | `docs/concepts/benchmark-model.md` | Declared case planting | Summary migrated | Migration pending |
| Scoring, and what it refuses to hide | `docs/reference/metrics.md` | Independent failure dimensions | Summary migrated | Metric review pending |
| Reference baselines (search) | `docs/guides/privacy-exposure.md` | Baseline context | Retained in source | Migration pending |
| Use case 11: enterprise identity and access structure | `docs/guides/enterprise-access.md` | Enterprise compile journey | Summary migrated | Contract guide retained |
| Author, validate, compile | `docs/guides/enterprise-access.md` | Three-stage enterprise flow | Routed | Detailed guide retained |
| Validation reports every error in a stage, not the first one | `docs/guides/enterprise-access.md` | Validation behavior | Retained in source | Migration pending |
| What compilation writes | `docs/guides/enterprise-access.md` | Public/evaluator output layout | Routed to contract | Contract authoritative |
| What the seed moves, and what it does not | `docs/concepts/determinism-seeds-and-keys.md` | Seed semantics | Summary migrated | Concept review pending |
| Limits worth knowing before you author | `docs/guides/enterprise-access.md` | Authoring limits | Routed to contract | Contract authoritative |
| Use case 12: projecting a compiled world to SCIM, OpenFGA, and AuthZEN | `docs/reference/standards-profiles.md` | Projection journey | Summary migrated | Contract guide retained |
| SCIM | `docs/reference/standards-profiles.md` | Projection profile | Routed to contract | Contract authoritative |
| OpenFGA | `docs/reference/standards-profiles.md` | Projection profile | Routed to contract | Contract authoritative |
| AuthZEN | `docs/reference/standards-profiles.md` | Projection profile | Routed to contract | Contract authoritative |
| Every projection reports what it lost | `docs/reference/standards-profiles.md` | Support classification | Summary migrated | Contract authoritative |
| Shared Signals / CAEP is a declaration, not an emitter | `docs/reference/standards-profiles.md` | Mapping limitation | Migrated | Contract authoritative |
| Use case 13: enterprise authorization benchmarks | `docs/guides/enterprise-access.md` | Enterprise evaluator journey | Routed | Detailed guide retained |
| Run the enterprise-agentic smoke pack | `docs/guides/enterprise-access.md` | Generation command | Retained in source | Command validation pending |
| Check the shape before you score | `docs/guides/evaluating-a-system.md` | Structural validation | Summary migrated | Validator review pending |
| Evaluate a prediction | `docs/guides/evaluating-a-system.md` | Scoring flow | Summary migrated | Command validation pending |
| Scoring the directory/RBAC oracle from Python | `docs/guides/enterprise-access.md` | Python API path | Retained in source | Migration pending |
| The identity-fabric pack is Python-only | `docs/reference/cli.md` | CLI/API boundary | Summary migrated | Reference review pending |
| Limits, stated plainly (enterprise authorization) | `docs/guides/enterprise-access.md` | Conformance limits | Routed to contract | Contract authoritative |
| Reading evaluation results | `docs/reference/metrics.md` | Report interpretation | Summary migrated | Metric review pending |
| Safety boundary | `docs/concepts/safety-boundary.md` | Fictional-data requirements | Migrated | Safety review pending |
| Enterprise trees | `docs/concepts/safety-boundary.md` | Structural sensitivity | Summary migrated | Safety review pending |

The line beginning `# one community...` in `USER_GUIDE.md` is a shell comment inside
a fenced code block, not a documentation heading, and therefore has no migration row.
