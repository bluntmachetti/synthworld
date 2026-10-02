# Metrics

Metric field definitions and report schemas remain canonical in [DATA_DICTIONARY.md](../../DATA_DICTIONARY.md) and the relevant contract README.

Use `--summary` where a scorer provides it for a compact view; omit it when you need the complete JSON report. A `null` metric is not zero. It means the submission did not make that metric meaningful under the task's documented empty behavior.

Metric envelopes are independently versioned and are not field-identical:

- Legacy `TaskMetric` records expose `value`, `support`, `family`, and `support_meaning`, but no explicit numerator or denominator. Support is the denominator for its direct ratios; agentic authorization F1 instead uses support as classification support and is derived from separately reported precision and recall.
- Enterprise authorization metrics expose numerator, denominator, support, family, denominator meaning, value, and empty behavior; support equals denominator.
- C08 v2 metrics expose numerator, denominator, denominator meaning, value, and an undefined reason, but no separate support field.

Interpret each metric through its own report contract and documented polarity. Keep independent metrics independent; an aggregate must not conceal failures. A metric that only compares a reported public reference measures reporting accuracy, not underlying enforcement or evidence retention.

For reproducible evaluation, retain the benchmark identity, relevant seed/configuration, scoring/formula version, artifact checksums, and the prediction or trace bytes that were scored.

## Missing observations are not evidence of success

The teaching demo reports decisions only. Identity, ownership, attribution,
provenance, and execution capabilities are not measured by those policies, even
though the legacy report represents their absent observations as zero-valued
metrics. Read the [demo's observation boundary](../guides/agent-authorisation-quickstart.md)
before interpreting the raw JSON.

An empty adapter can report least-privilege accuracy of 1.0 because it explicitly
allows nothing. This is not evidence of a working integration. Inspect submitted
decisions and recall as well as incorrect allows. Validation checks the trace
structure; it does not establish that useful observations were captured.

## Enterprise scope-selected cohorts

`binding_status_accuracy` and `lifecycle_status_accuracy` include every cell
selected for that dimension, including `not_applicable` statuses. They are not
applicable-gate-only rates. Earlier denominator descriptions incorrectly described
those cohorts as applicable gates; 0.18.0 corrects the description without changing
numerators, denominators, or scoring rules. Reports archived from previous versions
retain their original wording. Do not compare these rates with an applicable-only
rate without explicitly restricting and recording the evaluation scope.

`effective_decision_accuracy`, `final_decision_accuracy`, and
`policy_conflict_detection_accuracy` each use the cells selected for that dimension.
Conflict resolution additionally requires an actual conflict and both conflict
and effective-decision dimensions in scope. Runtime-gate accuracy requires
final-decision scope and a gate that changes the effective decision. These
cohorts can have different denominators; none means every aggregate cell by default.

## Live-lab claims

`LIVE_LAB_CONFORMANCE` requires a declared non-reference system, but that system
can be an opaque managed service. The label alone does not prove it was contacted,
that execution occurred, or that retained evidence can reproduce it. Inspect
observed versions, configuration, and execution evidence before drawing a live-lab
conclusion. The receipt validation contract remains unchanged.
