# Test identity and authorization in development pipelines

SynthWorld can run as a deterministic test-data and scoring stage in a local test
suite or CI pipeline. It does not replace the application, directory, identity
provider, policy decision point, or enforcement path being tested.

The integration shape is always:

```text
explicit version + seed + configuration
                  |
                  v
        deterministic benchmark
             /           \
            v             v
     public input    evaluator truth
            |             |
            v             |
    project adapter       |
            |             |
            v             |
    system under test     |
            |             |
            v             |
   prediction or trace ---+--> SynthWorld report --> project-owned CI gate
```

Keep the public-input and evaluator stages as separate processes, jobs, or mounts.
The split protects against accidental oracle use; a sibling `evaluator/` directory
does not enforce isolation by itself.

## Choose a pipeline

| Need | Start with | Interface |
|---|---|---|
| Fast authorization and adapter regression | Generated enterprise-agentic `smoke` | CLI plus a project adapter |
| Multi-tenant or lifecycle authorization | Generated `standard` or `longitudinal` | CLI plus a project adapter |
| An authored organisation and policy corpus | Enterprise authorization | CLI for topology; Python for compilation and scoring |
| Membership, role, entitlement, lifecycle, or governance rules | Enterprise identity fabric | Python |
| A standards-shaped product boundary | SCIM, OpenFGA, or AuthZEN projection | Python plus a project transport adapter |

The generated enterprise-agentic and enterprise authorization families are preview
capabilities on current `main`. Pin the package version and contracts used by a
pipeline rather than following an unbounded latest release.

## Pin the reproducibility inputs

Use Python 3.12 or newer and pin the distribution in the consuming project:

```text
idcognito-synthworld==0.17.0
```

Retain these inputs with every result:

- SynthWorld package version or wheel digest;
- benchmark profile, seed, complete configuration, and schema/scoring versions;
- public and evaluator artifact manifests and checksums;
- adapter, system, and policy versions, including a policy digest;
- the exact prediction or trace bytes; and
- the complete JSON report.

A seed alone is not a benchmark identity. Do not derive it from the current time,
branch name, job number, or another changing environment value. Use an absent output
directory for every generation step; artifact exporters intentionally refuse to
overwrite an existing root.

## Pipeline 1: fast authorization regression

The generated `smoke` tier is the smallest enterprise-agentic CI surface. It contains
one fictional organisation, public identity and authority events, and seven action
cases. Use `standard` for broader multi-tenant coverage and `longitudinal` for
joiner/mover/leaver, suspension, credential rotation, policy change, offboarding,
revocation-propagation, and evidence-loss cases.

### 1. Generate the benchmark

```bash
synthworld generate-enterprise-agentic \
  --profile generated \
  --tier smoke \
  --seed 20260821 \
  --output synthworld-benchmark
```

Generation writes checksum-bound `public/` and `evaluator/` trees. If generation and
product execution occur in separate jobs, publish only `synthworld-benchmark/public/`
to the product job. Keep the complete root for the later evaluator job.

### 2. Run the project adapter

The adapter must:

1. load only `synthworld-benchmark/public/`;
2. replay public events in their declared order;
3. query the real system under test at every action event; and
4. write one observed-action JSONL row per action event.

For example:

```bash
python scripts/synthworld_adapter.py \
  --public-package synthworld-benchmark/public \
  --output synthworld-observations.jsonl
```

`scripts/synthworld_adapter.py` is owned by the consuming project. The
[Asteria adapter template](../../agent-authority-contract/adapter-template/README.md)
shows the observation and JSONL plumbing and identifies the one observation function
an integration must replace. Its input loader is specific to the separately versioned
Asteria package, so a generated-world adapter must load the verified
`public/public-input.json` contract instead. Do not copy public identity claims into
observed fields unless the system independently established them.

### 3. Validate without evaluator truth

```bash
synthworld validate generated-enterprise-agentic-trace \
  --benchmark-root synthworld-benchmark \
  --predictions synthworld-observations.jsonl
```

The validator reads the public tree and exits nonzero for malformed rows, duplicate,
missing, or unknown action IDs, and incomplete action coverage. A valid trace is
scoreable; it is not necessarily correct.

### 4. Score in the evaluator stage

```bash
synthworld evaluate generated-enterprise-agentic \
  --benchmark-root synthworld-benchmark \
  --predictions synthworld-observations.jsonl \
  > synthworld-report.json
```

This stage receives the complete benchmark root. The loader verifies the public and
evaluator inventories, checksums, cross-bindings, and declared generator conformance
before scoring.

Scoring reports independent identity binding, authorization decision, authority
replay, accountability, observability, least-privilege, and excess-authority
metrics. Omit `--summary` in CI so the complete JSON report is retained.

### 5. Apply project-owned gates

Successful scoring exits zero even when the system scores poorly. That behavior
separates a malformed evaluation from a valid negative result. The consuming project
must choose its acceptance thresholds.

Save the following example as `scripts/gate_synthworld.py`:

```python
from __future__ import annotations

import json
import math
import sys
from pathlib import Path


REPORT_PATH = Path(sys.argv[1])

# Illustrative regression policy. Select thresholds appropriate to the system and
# benchmark, and review each metric's support meaning before adopting them.
GATES = {
    ("authorization_decision", "authorization_decision_accuracy"): (">=", 1.0, 1),
    ("authorization_decision", "authorization_decision_recall"): (">=", 1.0, 1),
    ("authorization_decision", "least_privilege_accuracy"): (">=", 1.0, 1),
    ("authorization_decision", "excess_authority_rate"): ("<=", 0.0, 1),
}

report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
metrics = {}
failures: list[str] = []

for metric in report["metrics"]:
    key = (metric.get("family"), metric["name"])
    if key in metrics:
        failures.append(f"duplicate metric: {key[0]}/{key[1]}")
    metrics[key] = metric

for key, (operator, threshold, minimum_support) in GATES.items():
    metric = metrics.get(key)
    if metric is None:
        failures.append(f"missing metric: {key[0]}/{key[1]}")
        continue
    value = metric.get("value")
    support = metric.get("support")
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or not isinstance(support, int)
        or isinstance(support, bool)
        or support < minimum_support
    ):
        failures.append(
            f"unusable metric: {key[0]}/{key[1]} "
            f"value={value!r} support={support!r}"
        )
        continue
    passed = value >= threshold if operator == ">=" else value <= threshold
    if not passed:
        failures.append(
            f"gate failed: {key[0]}/{key[1]} "
            f"value={value} expected {operator} {threshold}"
        )

if failures:
    raise SystemExit("\n".join(failures))
```

Run the gate after scoring:

```bash
python scripts/gate_synthworld.py synthworld-report.json
```

The gate fails closed when a required metric is missing, `null`, or lacks the chosen
minimum support. Do not treat `null` as zero, and do not gate only
`least_privilege_accuracy`: an adapter that never allows anything can look safe on
that metric while failing authorization recall.

## Pipeline 2: test an authored authorization model

Use the enterprise authorization workflow when the test should start from an
operator-authored organisation rather than a generated agentic profile.

Create and validate the bounded topology:

```bash
synthworld scaffold-enterprise-access \
  --format yaml \
  --output topology.yaml
synthworld validate-enterprise-access --input topology.yaml
synthworld compile-enterprise-access \
  --input topology.yaml \
  --seed 20260821 \
  --output compiled-enterprise
```

Treat `topology.yaml` and its generated namespace salt as operator-private. Importing
organisation structure is not anonymisation.

The documented `synthworld.enterprise.consumer` Python API can then compile an
explicit evaluation corpus and these bounded rule families:

- directory membership, nested groups, role assignment, role hierarchy,
  permissions, direct entitlements, birthright rules, exceptions, SSD, and session
  DSD;
- ABAC subject, resource, action, environment, tenant, ownership, classification,
  assurance, and network-zone predicates;
- ReBAC `member_of`, `owns`, `manages`, and `collaborates_on` relations; and
- RBAC, ABAC, ReBAC, RBAC-with-ABAC-guard, and ReBAC-with-ABAC-guard composition,
  followed by binding and lifecycle final-deny gates.

Follow the complete [enterprise authorization workflow](https://bluntmachetti.github.io/synthworld/guides/enterprise-authorization-python/)
to construct and export the corpus and policy artifacts. Its process boundary is:

```text
builder: public + evaluator artifacts
adapter: public artifacts -> external PDP -> EnterpriseAuthorizationPredictionV1
scorer:  public + evaluator artifacts + prediction -> independent metrics
```

Only topology scaffolding, validation, and compilation have CLI commands. Corpus,
RBAC/ABAC/ReBAC compilation, composition, prediction construction, and scoring are
currently Python APIs.

Good CI gates include final and effective decision accuracy, mechanism outcome and
inventory accuracy, conflict detection, and any supported binding, lifecycle, or
runtime-gate dimensions. Use each report metric's explicit denominator. A zero
denominator means the selected corpus did not discriminate that behavior; it is not a
passing result for a rule the pipeline intended to exercise.

## Pipeline 3: test identity and governance rules

Use the Python-only identity-fabric surface when the system under test answers
identity-governance queries rather than individual authorization requests. Its public
input contains directory, account, and access observations, declared intent, two
ordered checkpoints, and a vendor-neutral query inventory.

An adapter can return `EnterpriseIdentityFabricPredictionV1` observations for:

- direct and effective membership, including nested membership;
- direct, group-derived, hierarchy-inherited, and effective roles;
- canonical account resolution, binding, lifecycle, orphaned, and inactive status;
- direct and inherited entitlements, birthright, approved exceptions, intended,
  effective, and final access;
- policy conflicts, redundant derivations, access outside birthright or intent; and
- privilege accumulation across checkpoints.

Keep loading and scoring in separate stages:

```python
from pathlib import Path

from synthworld.enterprise.identity_fabric import (
    EnterpriseIdentityFabricPredictionV1,
    evaluate_enterprise_identity_fabric,
    load_evaluator_enterprise_identity_fabric,
    load_public_enterprise_identity_fabric,
)

root = Path("identity-fabric-benchmark")

# Adapter stage: expose only root / "public" to the product process.
public_input = load_public_enterprise_identity_fabric(root)
# prediction = run_your_product(public_input)

# Evaluator stage: load the saved prediction and the complete benchmark root.
prediction = EnterpriseIdentityFabricPredictionV1.model_validate_json(
    Path("identity-fabric-prediction.json").read_bytes()
)
evaluator = load_evaluator_enterprise_identity_fabric(root)
report = evaluate_enterprise_identity_fabric(
    artifacts=evaluator,
    predictions=prediction,
)
```

Generation and adapter construction for this surface are Python-only. Start from the
published schemas and examples listed in the
[enterprise identity/access contract](../../enterprise-identity-access-contract/README.md#identity-fabric-smoke-benchmark).

## Standards-shaped adapter tests

The enterprise projection APIs can convert bounded SynthWorld models to SCIM,
OpenFGA, and AuthZEN-shaped models. They are useful for testing a mapping layer or
fixture loader, but they do not perform network operations or make policy decisions.
A consuming project must provide transport, authentication, product configuration,
and response capture.

Every projection includes a support matrix marking exercised features as `exact`,
`approximated`, or `unsupported`. Review and retain that matrix so a convenient
mapping does not silently change the policy semantics being tested. See
[Standards profiles](../reference/standards-profiles.md).

## What should fail the pipeline

Fail when:

- generation, loading, integrity checking, or structural validation exits nonzero;
- the adapter omits, duplicates, or invents required cases;
- a required metric is missing, `null`, or below its minimum support;
- a metric crosses its project-owned threshold in the wrong direction; or
- benchmark, policy, adapter, prediction, or report bindings differ from the pinned
  run identity.

Do not fail merely because an optional metric has a documented zero denominator.
Instead, decide whether that metric is outside the test's declared scope or whether
the corpus is missing a necessary discriminating case.

## Interpret the result narrowly

A passing pipeline demonstrates that the pinned adapter and system behavior matched
the declared cases under the recorded inputs. It does not prove production
enforcement, security, availability, protocol conformance, real-world population
coverage, or performance. A published fixture is inspectable conformance evidence,
not a blind benchmark.

Continue with [Evaluating a system](https://bluntmachetti.github.io/synthworld/guides/evaluating-a-system/) for prediction contracts
and metric interpretation, [Public input and evaluator truth](../concepts/public-vs-evaluator.md)
for custody, and [Conformance and generalisation](../concepts/conformance-vs-generalisation.md)
for claim boundaries.
