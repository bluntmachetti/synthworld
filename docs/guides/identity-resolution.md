# Identity resolution

SynthWorld identity-resolution benchmarks expose ambiguous public records and keep canonical membership truth in a separately typed evaluator artifact. A resolver should be scored as a complete partition before any selected pair view is interpreted.

## Base entity-resolution task

The public side contains opaque records. A prediction must place every record in exactly one cluster, including single-record clusters:

```json
{
  "schema_version": "0.1.0",
  "clusters": [
    ["record-uuid-a", "record-uuid-b"],
    ["record-uuid-c"]
  ]
}
```

The report includes pairwise and B-cubed measures plus false merges and false splits. Keep those harms visible separately rather than relying on one aggregate score.

## Ambiguity benchmark

The ambiguity pack exists because a simple resolver can look perfect on a small exact-join fixture and still fail when evidence conflicts. It separates two truths:

- **Membership truth:** which records belong to the same canonical entity.
- **Pair disposition truth:** whether the public evidence justifies `merge`, `separate`, or `insufficient` for a selected pair.

Those answers can deliberately differ. A same-entity pair may expose only insufficient evidence, and a different-entity pair may also be insufficient. Abstention is therefore a first-class result.

```python
from synthworld.ambiguity_serialization import load_golden_ambiguity_benchmark

benchmark = load_golden_ambiguity_benchmark()
records = benchmark.public.corpus.identity_records
```

The public task is serialized separately from both truth artifacts.

## Score the complete partition first

Submit every public record exactly once through `EntityResolutionPrediction`. Score that partition with `evaluate_ambiguity_memberships`, using the separately loaded membership truth.

Only after the partition is valid should you derive decisions for the selected public pairs with `derive_ambiguity_pair_predictions`. That derivation consumes no truth: records in one cluster become `merge`; records in different clusters become `separate`.

A forced partition cannot express `insufficient`. If your product natively produces three-valued pair decisions, preserve that distinction in the interface you evaluate rather than treating every different-cluster pair as an evidence-backed separation.

Do not reconstruct the full partition from the selected pairs. A false merge between scenarios can be absent from the pair projection while remaining visible in complete-partition metrics.

## Read the report by failure mode

The ambiguity report deliberately has no single aggregate. Interpret these dimensions independently:

- false merges and false splits;
- unwarranted decisions;
- coverage beside decided precision;
- pairwise and B-cubed membership metrics;
- per-scenario support and low-support flags.

A system that abstains everywhere should not look perfect, and a system that merges two people should not be able to cancel that harm with an unrelated correct split.

## Reference baselines

The frozen v1 pack includes deliberately weak reference policies. CI fails if one unexpectedly resolves the pack cleanly.

| Baseline | Coverage | Decided precision | False merges | False splits | Unwarranted |
|---|---:|---:|---:|---:|---:|
| Exact strong identifier | 1.00 | 0.533 | 3 | 1 | 3 |
| Normalised name or address | 1.00 | 0.267 | 5 | 3 | 3 |
| Precision-first, with abstention | 0.73 | 0.727 | 1 | 1 | 1 |

These figures describe the declared frozen fixture, not a population estimate.

## Limits

The canonical v1 pack carries one selected pair per scenario. Every scenario slice is therefore low-support: a 1-of-1 result is a conformance observation, not a statistical rate.

Seed variants change surface values and some case carriers while preserving the declared scenario structure. Seeds 0 through 99 are a correlated robustness sweep, not 100 independent observations.

The generated v2 ambiguity work uses a different construction with overlapping evidence distributions and a computed generator error floor. Use [BENCHMARKS.md](../../BENCHMARKS.md) and [DATA_DICTIONARY.md](../../DATA_DICTIONARY.md) for the published v2 identities, invariants, schemas, and current status rather than assuming v1 semantics transfer to v2.

## Public boundary

Do not infer benchmark truth from identifiers, ordering, or case labels. Public artifacts reject oracle-bearing fields rather than relying only on naming conventions.

For general scorer integration see [Evaluating a system](evaluating-a-system.md).