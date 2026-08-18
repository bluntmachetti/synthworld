# Enterprise authorization with OPA and an AuthZEN-style adapter

This frozen external-consumer experiment asks whether one authorization policy can
consume released SynthWorld 0.16.0 artifacts through an AuthZEN-style request
boundary and preserve the scoreable authorization behaviour across two fictional
organizations. Britannia is the calibration topology; Aurelia is the unseen
generalization topology.

The experiment is recorded in
[Discussion #147](https://github.com/bluntmachetti/synthworld/discussions/147) and
published as the immutable release
[`enterprise-authorization-opa-authzen-0.16.0-2`](https://github.com/bluntmachetti/synthworld/releases/tag/enterprise-authorization-opa-authzen-0.16.0-2).
It is an unsupported evidence record, not a maintained SynthWorld adapter, AuthZEN
conformance result, product certification, vendor comparison, or claim that the
policy is suitable for production.

## Experiment boundary

The experiment installed `idcognito-synthworld==0.16.0` as a released dependency.
It did not modify SynthWorld or import repository examples or tests. Its workflow
kept benchmark generation, the system under test, submission sealing, and scoring
as distinct capabilities:

```text
Britannia and Aurelia topology YAML
    -> experiment-owned deterministic mapping
    -> released SynthWorld compilation
    -> physically split public and evaluator artifacts
    -> experiment-owned OPA policy and AuthZEN-style adapter
    -> raw responses and typed sealed submissions
    -> isolated offline SynthWorld scoring
```

The projector, adapter, OPA process, and system-under-test runner received only the
public artifact tree. The offline scorer was the only capability with an evaluator
mount. A deliberate regression exposed evaluator paths to both the projector and
runner; the isolation checker rejected both configurations.

## Run identity

| Field | Recorded value |
|---|---|
| Experiment | `agent-auth-3`, revision `1.0.0` |
| Authoritative publication | `enterprise-authorization-opa-authzen-0.16.0-2` |
| Source-file-set SHA-256 | `cc3cf9a09c254ad311361f1ec206a8462ead1fa26a366a56dc4d4014d728fb8b` |
| SynthWorld package | `idcognito-synthworld==0.16.0` |
| SynthWorld wheel SHA-256 | `dfe584e3ac3f4f5a3d55e389797cc9a1bac049f9bc78c0b4547257185d213480` |
| Experiment seed | `20260817` |
| Britannia topology SHA-256 | `29ea8dd155ceed277eedf3f7261f0ba6844ff5a3e6c5a9c70164ae78b80871d1` |
| Aurelia topology SHA-256 | `5a7f9b141f6ffa1e1007f8e2d311abbc33f84e7a4326f477b6923fe05bf07f82` |
| Open Policy Agent | `1.4.2`, build commit `03da822be92592b36c8ae246d41d421a03df95e2` |
| OPA image digest | `sha256:3c995dc8a59f6ddfd92eb7404d2f7ff9fe71cd025d9251199957a8a6afbfd76e` |
| Authorization API shape | OpenID Authorization API 1.0, Final Specification, 11 January 2026 |

The experiment directory was not a Git repository. Its frozen source is therefore
identified by the source-file-set digest and final manifests, not by a source
commit. The release tag points to the SynthWorld repository revision that hosts the
evidence; it is not an experiment-source revision.

## Method

One deterministic mapper converted each organization topology into the released
enterprise identity and authorization authoring surfaces. One combined
RBAC/ABAC/ReBAC policy then processed every public evaluation cell through an
experiment-owned AuthZEN-style adapter in front of OPA.

Each request bound the subject identifier and type, action name, resource identifier
and type, evaluation tick, profile, and topology lane to the selected public cell.
Sixteen fixed-cell-ID mutation controls changed those values independently and were
all refused. The runner retained raw requests and responses, normalized them into
typed submissions, and sealed each topology's complete input, policy, adapter,
package, product, and result evidence before scoring.

The reproduction workflow uses Docker Compose, digest-pinned images, and a
hash-pinned Python lock. The two complete deterministic runs compared 175 files
byte-for-byte. A separate clean extraction of the published reproduction ZIP also
completed successfully.

## Results

Every metric retains its own denominator; no aggregate score is computed.

| Measurement | Result | Denominator meaning |
|---|---:|---|
| Effective composed decision | 649 / 649 | Public evaluation cells across both topologies |
| Final composed decision | 648 / 649 | Cells after lifecycle and runtime gates |
| Binding-status classification | 638 / 649 | Cells with released binding-status truth |
| Runtime-gate decision | 211 / 212 | Cells where the runtime gate was scoreable |
| ABAC outcome | 232 / 232 | Scoreable ABAC component cases |
| RBAC outcome | 577 / 577 | Scoreable RBAC component cases |
| ReBAC outcome | 72 / 72 | Scoreable ReBAC component cases |
| Conflict resolution | 71 / 71 | Cells containing a policy conflict |
| Policy-conflict detection | 649 / 649 | Public evaluation cells |
| Lifecycle-status classification | 649 / 649 | Public evaluation cells |
| Mechanism outcome | 649 / 649 | Public evaluation cells with expected per-mechanism outcomes |
| Mechanism inventory | 649 / 649 | Public evaluation cells with expected mechanism inventories |
| Policy and adapter negative controls | 20 / 20 | Deliberately faulty policies or prediction dimensions detected |
| Request-binding mutation controls | 16 / 16 | Altered AuthZEN-style request fields refused |
| Seal and replay controls | 20 / 20 | Untampered submissions accepted and invalid variants refused as required |

Britannia contributed 324 cells and the single final-decision error; Aurelia
contributed 325 cells and reproduced every effective and final decision. The
binding metric remains separately visible: canonical account-to-principal binding
is evaluator-only, so plausible same-kind substitutions are not always decidable
from the public evidence. A superficially correct final decision must not conceal
that mechanism-level miss.

## Frozen assets

Publication revision 2 is the authoritative release. Revision 1 accidentally
included unmanifested Python bytecode caches in both archives. Revision 2 removes
only those generated files; experiment inputs, source, retained evidence, results,
and internal checksums are unchanged. Both revisions remain immutable so the
correction history is auditable.

| Release asset | Bytes | SHA-256 | Intended use | Evaluator truth included |
|---|---:|---|---|---|
| [`enterprise-authorization-opa-authzen-0.16.0-2-reproduction-kit.zip`](https://github.com/bluntmachetti/synthworld/releases/download/enterprise-authorization-opa-authzen-0.16.0-2/enterprise-authorization-opa-authzen-0.16.0-2-reproduction-kit.zip) | 148,620 | `8a48b643dfaeb84d3d0ec5ecc0683c02cea109dbc73e4404928f91f4dfea9cfa` | Reproduce from source, pinned dependencies, two explicit topologies, policy, adapter, controls, and documentation | No generated evaluator artifacts |
| [`enterprise-authorization-opa-authzen-0.16.0-2-reference-run.zip`](https://github.com/bluntmachetti/synthworld/releases/download/enterprise-authorization-opa-authzen-0.16.0-2/enterprise-authorization-opa-authzen-0.16.0-2-reference-run.zip) | 4,995,313 | `ef73d2fd92973843412a63f6fb34ecc1077db72e71630dc300d9127f2530e997` | Audit the retained public artifacts, separate evaluator truth, raw decisions, sealed submissions, controls, and reports | Yes, in a physically separate tree |
| [`ASSET-METADATA.json`](https://github.com/bluntmachetti/synthworld/releases/download/enterprise-authorization-opa-authzen-0.16.0-2/ASSET-METADATA.json) | 2,783 | `59f3ae5c8ed958857da6761bad4f9174b55ad73c95140583f2f7a86c5f70ba8a` | Machine-readable correction, source identity, versions, asset digests, result counts, and unsupported claims | No |
| [`SHA256SUMS`](https://github.com/bluntmachetti/synthworld/releases/download/enterprise-authorization-opa-authzen-0.16.0-2/SHA256SUMS) | 349 | `806edc08e566d388f875bc639bf9b4d618940cb84a8d231bf4e832c5f6c7d471` | Verify every custom release asset | No |

Verify the release attestation and assets with `gh release verify` and the retained
checksums:

```bash
gh release verify enterprise-authorization-opa-authzen-0.16.0-2 \
  --repo bluntmachetti/synthworld
sha256sum -c SHA256SUMS
unzip enterprise-authorization-opa-authzen-0.16.0-2-reproduction-kit.zip
cd enterprise-authorization-opa-authzen-0.16.0-2-reproduction-kit
./run.sh
```

First execution may need network access to obtain the pinned images and packages.
After that run, `./reproduce.sh --offline` performs the complete two-run
byte-identity comparison using the retained local cache.

## What this experiment does not establish

- AuthZEN protocol or implementation conformance. The adapter is merely shaped
  around the published decision-request model.
- A comparison among authorization strategies. It exercises one policy; the
  negative controls are intentionally broken variants, not alternatives.
- Individual person-to-agent accountability. The topology mapping establishes
  team-level responsibility but does not model an explicit person assignment for
  every agent.
- Arbitrary topology portability. Britannia and Aurelia use the same mapping
  method, but two successful inputs do not prove that every organization YAML is
  representable.
- A SynthWorld rendering feature. The released package has no HTML renderer, and
  this experiment did not substitute an experiment-owned viewer.
- A maintenance commitment. Experiment authors own future adaptations, policies,
  infrastructure, and support.

These limitations define the useful next experiment: keep the released benchmark
and isolation boundaries, add explicit person-to-agent accountability, and compare
multiple independently designed authorization strategies over the same frozen
worlds rather than optimizing another single policy against this result.
