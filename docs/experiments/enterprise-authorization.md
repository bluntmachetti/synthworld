# Enterprise authorization with Topaz

This experiment series asks whether an external authorization system can consume
released SynthWorld enterprise artifacts and reproduce the relevant authorization
behaviour. Topaz is the first system under test. It is not part of SynthWorld's
oracle, and the results are not a vendor comparison or general authorization
correctness claim.

## Evidence status

| Phase | Evidence level | Package | What was exercised |
|---|---|---|---|
| Phase 1 | Historical exploratory run; not frozen or independently reproducible | `idcognito-synthworld==0.15.0` | Public enterprise-access tuples loaded into a Topaz directory and queried through the directory check API |
| Phase 2 | Source-controlled and clean-clone verified locally; no published remote or independent reproduction | `idcognito-synthworld==0.15.0` | A generated enterprise identity/access world, projected policy, live authorization decisions, blinded submissions and released scorers |
| Phase 3 | Planned | A future release containing the required benchmark contracts | Enforced evaluator isolation and scored composed authorization decisions with discriminating adversarial cases |

The Phase 2 source-only baseline is locally tagged
`phase2-baseline-0.15.0`. A clean local clone completed all 32 validation checks
and reproduced submission digest
`89099e3b55226cd6bd378f6dc7a2153aed3ee8d0e6e7fe3f9781d5be25a69f05`.
The tag is not externally fetchable yet, so these details identify the evidence
but do not make it independently reproducible.

## Phase 1: directory feasibility

Phase 1 mapped a fictional enterprise topology into the released enterprise
identity/access authoring schema, compiled it, loaded the public relationship
data into Topaz, and ran 6,880 directory checks. It established that the public
artifact could drive a real relationship directory and that evaluator bindings
could remain outside the runner container.

It did not exercise Topaz's authorization decision API or a composed policy. The
Topaz image was not pinned by digest, the directory was not source-controlled,
and its HTML pages were experiment-owned viewers rather than a released
SynthWorld renderer. Treat its perfect tuple round-trip as a transport and
projection result only.

## Phase 2: authorization feasibility

Phase 2 used a digest-pinned Topaz 0.33.16 image and the released wheel to build
a larger deterministic world. The live run:

- loaded and read back 1,699 objects and 5,879 relations;
- issued 3,209 requests to Topaz's authorization decision API with no HTTP
  errors or defaulted decisions;
- reproduced 895 authorized-role sets and all 3,209 released directory/RBAC
  effective decisions;
- exercised lifecycle gating and a public ABAC policy projection;
- sealed the three mechanism submissions before the scoring stage opened the
  evaluator tree; and
- emitted no invented aggregate score.

Those results establish released-package and Topaz adapter feasibility. They do
not establish all of the adversarial properties named by the corpus.

## Material limitations found by Phase 2

### The composed decision was not scored

Topaz produced a composed decision that combined RBAC-family results with the
ABAC guard. The released package had separate directory/RBAC, ABAC and ReBAC
scorers but no submission or evaluator for the composed
`CompiledEnterpriseAccessStateV1` decision. Cross-tenant and scope-exceeded
actions were denied by the experiment's composition while their released
directory/RBAC truth remained allow.

### The binding cohort did not test binding

The public input exposed the observed account binding but not enough evidence to
resolve its canonical subject. The reference policy therefore treated the
binding gate as passing. All 15 wrong-binding cases were already denied because
the RBAC derivation found no path, so ignoring the binding mechanism did not
change the outcome.

### Some submitted metrics were not publicly solvable

Several released prediction fields depended on evaluator-only identifiers or
unpublished policy intent, including ABAC truth identifiers, RBAC derivation-path
identifiers and separation-of-duty constraints. Phase 2 reported these metrics
as not publicly winnable rather than folding them into a headline result.

### Public policy could reveal the negative cohort

The ABAC vocabulary did not provide the tenant inequality needed by the
experiment. The projected rule therefore enumerated the public cell identifiers
in its cross-tenant scope. A separately derived tenant comparison agreed with all
63 cases, but it was a cross-check rather than the decision path.

### Isolation was auditable, not enforced

Public and evaluator artifacts were physically separate and submissions were
sealed before scoring, but evaluator truth existed on the same host while the
system under test ran. The supported process did not read it; the filesystem did
not make such a read impossible. Phase 3 must run the system under test without
an evaluator mount and give evaluator access only to a separate scorer.

## Contract work before Phase 3

The experiment produced four focused requirements:

- [#137](https://github.com/bluntmachetti/synthworld/issues/137) adds a publicly
  constructible composed-decision submission and independent scoring.
- [#138](https://github.com/bluntmachetti/synthworld/issues/138) adds
  discriminating tenant, scope, binding and temporal counterfactuals.
- [#139](https://github.com/bluntmachetti/synthworld/issues/139) stabilizes the
  released consumer API, digest helpers and supported end-to-end workflow.
- [#140](https://github.com/bluntmachetti/synthworld/issues/140) publishes an
  isolated, reproducible adapter lab after the contracts are stable.

Phase 3 should start in a fresh experiment directory against a released package.
It must not retrofit Phase 2 or silently reinterpret its results.
