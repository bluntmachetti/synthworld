# Standards profiles

Standards mappings are pinned to reviewed editions, never an implicit latest
version. Mapping status, source maturity, and implementation support are separate
claims.

The enterprise ledger is
[`enterprise-identity-access-contract/standards-profile-ledger.json`](../../enterprise-identity-access-contract/standards-profile-ledger.json).
Contract READMEs explain the limits of SCIM, OpenFGA, AuthZEN, Shared Signals/CAEP,
and other projections. A mapping declaration is not evidence of protocol transport,
signing, interoperability, or vendor conformance.

## Run the Python projection APIs

The SCIM, OpenFGA, and AuthZEN surfaces are pure, offline data conversions for
testing an adapter, mapping layer, or fixture loader. They do not contact a
service, exchange a credential, or make a policy decision. Their outputs are
standards-shaped models rather than wire-format documents, so a real endpoint
still requires an adapter. There is no CLI for these projections; import them
from `synthworld.enterprise.projections`.

### SCIM

```python
from synthworld.enterprise.projections import project_scim, scim_projection_profile_v1

projection = project_scim(
    universe=universe,                        # EnterpriseIdentityAccessUniverseV1
    directory_rbac_kernel=kernel,             # EnterpriseDirectoryRbacKernelV1
    profile=scim_projection_profile_v1(snapshot_tick=0),
)
```

Both inputs are public artifacts. The kernel must bind the exact universe passed
to `project_scim`; otherwise the call fails with
`scim_kernel_universe_digest_mismatch` instead of silently mixing worlds.

The projection deliberately imports no authorization meaning: `roles` and
`entitlements` are empty and `authorization_semantics` is `"none"`. User names
use the reserved `.invalid` TLD, an account without a directory observation
fails closed to `active: false`, and only accounts—not principals or nested
groups—become group members.

### OpenFGA

```python
from synthworld.enterprise.authorization_common import AuthorizationSourceLayer
from synthworld.enterprise.projections import openfga_mapping_profile_v1, project_openfga

projection = project_openfga(
    universe=universe,                        # EnterpriseIdentityAccessUniverseV1
    rebac_truth=rebac_truth,                  # CompiledEnterpriseRebacTruthV1
    mapping_profile=openfga_mapping_profile_v1(
        source_layer=AuthorizationSourceLayer.ACTUAL,
    ),
)
```

One projection covers one source layer. `CompiledEnterpriseRebacTruthV1` is an
evaluator-side input, so treat the derived output as evaluator-side unless the
selected layer's exposure has been reviewed. The native snapshot, revision, and
validity fields on emitted tuples are inert metadata; an OpenFGA runtime does not
enforce them.

### AuthZEN

```python
from synthworld.enterprise.projections import authzen_mapping_profile_v1, project_authzen

projection = project_authzen(
    universe=universe,                        # EnterpriseIdentityAccessUniverseV1
    corpus=corpus,                            # EnterpriseEvaluationCorpusV1
    request=corpus.access_requests[0],
    mapping_profile=authzen_mapping_profile_v1(),
)
```

The API projects one request per call. Its output contains no expected decision,
so it can be handed to a system under test while the corpus's expected decision
stays evaluator-side. Record the returned outcome separately. Only `allow` and
`deny` normalize to a Boolean decision; `indeterminate`, `transport_error`,
`timeout`, and `unavailable` normalize to `None`. A transport failure is not a
deny.

## Inspect projection loss

Each projection compiles a support matrix with one row per exercised native
feature. Rows are `exact`, `approximated`, or `unsupported`; every non-exact row
must state its semantic delta.

```python
from synthworld.enterprise.projections import evaluate_projection_fidelity

for metric in evaluate_projection_fidelity(projection.support_matrix).metrics:
    print(metric.family, metric.name, metric.numerator, metric.denominator, metric.value)
```

Exact, approximated, and unsupported rates remain independent. SynthWorld does
not combine them into a single fidelity score that could conceal unsupported
authorization semantics.

Shared Signals/CAEP is different: the package exposes a mapping profile and
support matrix, but no `project_*` function, event model, or SET emitter.
