# From PII spans to identity resolution

This locally frozen external-consumer experiment asks how errors in personally
identifiable information (PII) detection propagate into identity resolution,
relationship inference, and exposure assessment. Two detector arms and an
oracle-span diagnostic arm feed one experiment-owned downstream system over a
connected synthetic world.

The run installed `idcognito-synthworld==0.17.0` as a released dependency.
SynthWorld generated the fictional substrate and supplied the released extraction
scorer; it was not the system under test. This page is an unsupported local evidence
record, not a SynthWorld benchmark result, detector ranking, product certification,
or real-world transfer claim.

## Evidence status

The corrected implementation was committed before the final two-run rescore, and
the final artifacts are retained on the experiment owner's local laboratory host.
They have not been published as a release or otherwise made independently
downloadable. The commit identifiers and digests below therefore identify the
locally frozen record; they are provenance anchors, not public reproduction links.

The original run's method freeze predated source control. Review found scoring and
reporting defects, which were corrected through separately committed source-freeze
and rescore steps. The final result described here is the corrected run, not the
superseded first report.

## Experiment boundary

The workflow physically separated public product inputs from evaluator truth:

```text
released SynthWorld 0.17.0 package + explicit seed
    -> synthetic extraction pages and evaluator truth
    -> opaque, shuffled system-under-test inputs
    -> isolated regex and Presidio detection arms
    -> shared experiment-owned downstream system
    -> sealed submission
    -> offline evaluator scoring
```

The system under test ran under Bubblewrap with its network namespace unshared.
Evaluator, build, public, submission, input, report, and control trees were not
mounted. Its virtual environment did not contain SynthWorld. A deliberate
isolation regression mounted forbidden evaluator and build trees and required the
boundary checker to reject the poisoned specification.

The oracle arm received answer-key span classes and offsets only. It is a diagnostic
bound for the downstream system with perfect spans, not an end-to-end detector run.

## Run identity

| Field | Recorded value |
|---|---|
| Experiment | `agent-spy` |
| Evidence status | Locally frozen external-consumer result |
| Experiment date | `2026-08-22` |
| Final source-freeze commit | `7b46dc5d1329746ac86d0009890054f0a9a09261` |
| Final source tree | `8544a58e2e5739d802704413973c8d70bf467fd5` |
| Final scored commit | `05fea86fcd2a5f3225ce37556bd84804b48aecf8` |
| Final scored tree | `6c5664109cc9231d70f616c39bfc5920a694cc4d` |
| SynthWorld package | `idcognito-synthworld==0.17.0` |
| SynthWorld seed | `20260822` |
| Personas and pages | 40 personas, 272 pages |
| Detectors | Experiment-owned regex rules; Presidio Analyzer `2.2.360` with `en_core_web_sm==3.8.0` |
| SPY input revision | `093be5a0235c9e15bc1c364f10ac48b9563de34c`; first 400 legal and 400 medical records |
| Nemotron-PII input revision | `b70ffaf5ff39e079776134c5bf4381f00a9fd1ed`; first 400 test records |
| File manifest SHA-256 | `45f5edefc9903ec05737b0691aa6e077b012e10df4534f8eca666f4b2d532607` |
| Final checksum-list SHA-256 | `7dc3950734a06f725db5cc7e850c53d7d1e0c1c735b395604129ebf2ea7aa35d` |
| Final report SHA-256 | `1f617d68c9fb001d287b612a0e0610a3f5f70f9956cde9a278e5f42b39d574fd` |
| Metrics SHA-256 | `082d93d8a102e8977f299acc02d4a3e36c043771fb04795f01497ad72a28b14c` |

Both external corpora are synthetic. SPY placeholder values were materialized by a
seeded reimplementation of its upstream loader because the upstream shuffle was not
fully seeded. All three retained input files were pinned by SHA-256 before the run.

## Method

The regex arm used experiment-owned patterns and labelled-line rules. The Presidio
arm used its standard English analyser at a frozen 0.4 score threshold. Native
detector and corpus labels were mapped into SynthWorld's nine-class extraction
vocabulary; unmapped labels were counted rather than silently discarded.

The resolver linked documents only through exact normalized values in four hard
identifier classes: email, username, phone, and national identifier. It also linked
an email local part to an equal username. Relationship rules used rendered surname,
address, employer, and education features. Exposure profiles were the distinct data
classes observed per predicted subject.

External relaxed-span scoring used one-to-one maximum-cardinality overlap matching
within each document and class. Exposure scoring reported an exact interval over all
cluster-to-persona assignments that maximized document overlap, because equally
optimal assignments can attach different exposure content. Relationship
recoverability subsets were explicitly SUT-rule-relative: their oracle scores are
consistency checks, not independent evidence of inference competence.

## Results

Every metric retains its own denominator; no aggregate score is computed.

### Detection and resolution

| Arm | Exact span F1 | Linking-span recall | Resolution pairwise F1 | Resolution B-cubed F1 | Predicted clusters |
|---|---:|---:|---:|---:|---:|
| Regex | 0.865 | 362 / 362 | 0.999 | 0.998 | 41 |
| Presidio | 0.059 | 0 / 362 | 0.015 | 0.270 | 267 |
| Oracle spans | Not a detector | 362 / 362 | 0.999 | 0.998 | 41 |

Exact recall on linking identifiers is the mechanistic result. The regex arm found
all 362 gold hard-identifier spans and matched the oracle arm on resolution.
Presidio found none: its email recognizer rejected the safely fictional `.test`
addresses, and it had no username class. The resulting resolution collapse is a
format-compatibility stress case on this fixture, not evidence about Presidio on
production data.

### External mapped-label slices

| Detector | SPY legal relaxed F1 | SPY medical relaxed F1 | Nemotron-PII relaxed F1 |
|---|---:|---:|---:|
| Regex | 0.330 | 0.341 | 0.419 |
| Presidio | 0.211 | 0.216 | 0.327 |
| Mapped-label coverage | 1,761 / 2,545 | 1,947 / 2,753 | 726 / 3,352 |

The external figures apply only to the mapped label slices. Nemotron-PII coverage
was 21.7%, so its column is not a corpus-level detector score. Detector magnitudes
did not transfer between the semi-structured SynthWorld fixture and the external
free-text samples.

### Relationship inference

| Arm | Precision | Recall over all 39 truth edges | F1 | Pair recall where the SUT rule fires, n=20 | Recall where the SUT rule recovers the truth kind, n=18 |
|---|---:|---:|---:|---:|---:|
| Regex | 0.581 | 0.462 | 0.514 | 1.000 | 1.000 |
| Presidio | 0.020 | 0.051 | 0.029 | 0.250 | 0.111 |
| Oracle spans | 0.581 | 0.462 | 0.514 | 1.000 | 1.000 |

The two rightmost denominators execute the same declared relationship rules on
truth-rendered endpoint evidence. Oracle recall of 1.000 is therefore a consistency
check by construction. It does not establish general relationship-inference
competence. Against all truth edges, unavailable social evidence, sparsely rendered
address evidence, and precision errors remain visible in the 0.514 oracle F1.

### Exposure assessment

| Arm | Subject-matching profile F1 | Unmatched clusters | Truth-conditional profile F1 | Spearman at the two F1-extremal assignments |
|---|---:|---:|---:|---:|
| Regex | [0.945, 0.953] | 1 | 0.953 | 0.846 |
| Presidio | [0.036, 0.211] | 227 | 0.297 | [-0.225, 0.616] |
| Oracle spans | [0.992, 1.000] | 1 | 1.000 | 0.759 |

Subject matching penalized fragmentation and reported the exact F1 range across
tie-equivalent maximum-overlap assignments. The Spearman values are evaluated at
the two F1-extremal assignments and are not an exact rank-correlation interval. The
truth-conditional diagnostic merges all fragments assigned to one true persona and
therefore must not be read as the end-to-end result.

### Error attribution

Oracle-minus-detector deltas locate error introduced by span detection within this
fixed pipeline:

| Quantity | Resolution B-cubed F1 | Relationship F1 over all edges | Subject-matching exposure F1 |
|---|---:|---:|---:|
| Caused by regex detection | 0.000 | 0.000 | [0.040, 0.055] |
| Caused by Presidio detection | 0.728 | 0.486 | [0.781, 0.964] |
| Remaining with perfect spans | 0.002 | 0.486 | [0.000, 0.008] |

The relationship residual over all truth edges combines evidence that the documents
never render, relative to the declared rules, with precision errors. It is not a
single measure of downstream inference failure.

## Integrity and reproducibility

- Two clean executions were byte-identical across 73 checksummed files: 43 derived
  artifacts, 29 source files, and the final report.
- Five negative controls passed, including hand-verifiable matching-solver cases.
- Three malformed or tampered submission cases were refused.
- The Bubblewrap isolation check and its deliberate-failure regression passed.
- Both virtual environments were synchronized from hash-pinned locks on every run,
  and their installed distributions were retained in the environment inventory.
- Public system inputs and evaluator truth remained physically separate artifacts.

These checks establish deterministic reproduction on the retained local setup. They
do not make the experiment independently reproducible while its source and pinned
input bytes remain unpublished.

## What this experiment supports

Within this SUT and fixture, exact recall on the identifier classes used for linking
determined resolution performance. Perfect spans left the resolver near ceiling,
while Presidio's zero linking-span recall fragmented 272 documents into 267
clusters. The result demonstrates error propagation through this declared pipeline.

## What this experiment does not establish

- That aggregate external detector F1 predicts end-to-end identity resolution.
  There were only two detectors, one seed, and one fixture.
- A general detector ranking or claim about Presidio on production data.
- Transfer from SynthWorld's structurally simple extraction fixture to real identity
  resolution workloads.
- Independent relationship-inference competence. The recoverability subsets execute
  the SUT's own declared rules.
- Independent reproduction. The source, report, and input bytes are locally retained
  but not published as immutable release assets.
- A SynthWorld feature, baseline, supported adapter, or benchmark claim. The
  detectors and downstream system are experiment-owned.

The useful next experiment is a preregistered multi-seed study with a larger detector
roster, representative sampling, independently defined relationship sufficiency,
and immutable public reproduction assets.
