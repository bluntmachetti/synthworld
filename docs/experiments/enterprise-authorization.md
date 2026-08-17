# Enterprise authorization with Topaz

This experiment series asks whether an external authorization system can consume
released SynthWorld enterprise artifacts and reproduce the relevant authorization
behaviour. Topaz is the first system under test. It is not part of SynthWorld's
oracle, and the results are not a vendor comparison or general authorization
correctness claim.

The concrete Phase 2 question was:

> Can an authorization system consume only released SynthWorld public artifacts,
> project them into its own policy model, and reproduce the scoreable authorization
> behaviour without using evaluator truth?

Phase 1 answered the narrower question of whether released relationship data could
be transported into and queried from a Topaz directory. Phase 2 exercised a live
authorization policy and the released mechanism scorers. Neither phase tested
continued authorization across changing runtime boundaries.

## Experiment boundary

The experiment kept generation and scoring on the SynthWorld side of the boundary
and treated the Topaz adapter and projected policy as experiment-owned code:

```text
fictional organization topology
    -> SynthWorld compilation
    -> public benchmark artifacts
    -> experiment-owned Topaz projection and policy
    -> Topaz authorization requests
    -> sealed predictions
    -> separate SynthWorld evaluator scoring
```

- SynthWorld owns deterministic generation, public benchmark contracts, evaluator
  truth and mechanism scorers.
- The experiment owns the organization-topology mapping, Topaz data projection,
  Topaz configuration and Rego policy.
- Topaz is the system under test. Evaluator artifacts are not Topaz inputs.
- The organization topology is an experiment input, not a SynthWorld schema.

## Evidence status

| Phase | Evidence level | Package | What was exercised |
|---|---|---|---|
| Phase 1 | Historical exploratory run; not frozen or independently reproducible | `idcognito-synthworld==0.15.0` | Public enterprise-access tuples loaded into a Topaz directory and queried through the directory check API |
| Phase 2 | Locally frozen and clean-clone verified; evidence archives published with SynthWorld 0.16.0; no independent reproduction recorded yet | `idcognito-synthworld==0.15.0` | A generated enterprise identity/access world, projected policy, live authorization decisions, blinded submissions and released scorers |
| Phase 3 | Ready for a fresh isolated-lab experiment | `idcognito-synthworld==0.16.0` | Enforced evaluator isolation and scored composed authorization decisions with discriminating adversarial cases |

The Phase 2 source-only baseline is locally tagged
`phase2-baseline-0.15.0`. A clean local clone completed all 32 validation checks
and reproduced submission digest
`89099e3b55226cd6bd378f6dc7a2153aed3ee8d0e6e7fe3f9781d5be25a69f05`.
The experiment Git tag is not hosted as a separately fetchable remote. The release
archives below preserve the source and retained evidence, making the record
independently downloadable but not yet independently reproduced.

## Phase 1: directory feasibility

Phase 1 mapped a fictional enterprise topology into the released enterprise
identity/access authoring schema, compiled it, loaded the public relationship data
into Topaz, and ran 6,880 directory checks. It established that the public artifact
could drive a real relationship directory and that evaluator bindings could remain
outside the runner container.

It did not exercise Topaz's authorization decision API or a composed policy. Its
permissions were one-to-one aliases of relations written by the same build, so the
perfect result was a directory round-trip rather than an independent authorization
test. The source Compose file selected `ghcr.io/aserto-dev/topaz:latest`; the cached
image was later identified as Topaz 0.33.16 with digest
`sha256:835868c04bdd7129127ea43642ffff7363d0bd26d5e1a37631fa881431054360`,
but that recovery does not make the original source fully pinned. The directory was
not source-controlled, and its HTML pages were experiment-owned viewers rather than
a released SynthWorld renderer.

Treat Phase 1 as historical feasibility evidence only. Its publication package must
preserve the original prompt, Compose file, scripts, inputs and reports alongside
these qualifications.

## Phase 2: frozen local run

### Run identity

| Field | Recorded value |
|---|---|
| Experiment baseline | `phase2-baseline-0.15.0` |
| Source commit | `c1c81df2c2290868ef741368324df5e46f6936b8` |
| SynthWorld package | `idcognito-synthworld==0.15.0` |
| SynthWorld wheel SHA-256 | `f1b17f8254521d307e38cfc3a44d00844308dd36c7972da00b816b92e257ee60` |
| Experiment seed | `20260816` |
| Topology SHA-256 | `29ea8dd155ceed277eedf3f7261f0ba6844ff5a3e6c5a9c70164ae78b80871d1` |
| Topaz runtime | `0.33.16`, commit `81b8405`, `linux/amd64` |
| Topaz image digest | `sha256:835868c04bdd7129127ea43642ffff7363d0bd26d5e1a37631fa881431054360` |
| Sealed submission SHA-256 | `89099e3b55226cd6bd378f6dc7a2153aed3ee8d0e6e7fe3f9781d5be25a69f05` |
| Validation | 32 of 32 checks passed |

The known working host was Fedora 44 on `x86_64`, kernel 7.0.10, with Docker
29.5.2, Docker Compose 5.1.4, `uv` 0.11.17 and Python 3.13. These host details are
observational provenance, not inputs to deterministic SynthWorld generation. A
published reproduction must capture them in a machine-readable run receipt rather
than treating this host as the only supported environment.

### Inputs and provenance

Both phases used the byte-identical
`britannia_global_bank_topology.yaml`. The source is the
`redoubtlabs/redoubtia-agents` repository at commit
`5e59e7d9b311e55c321d105a80a034c23dd704bf`. The original Phase 1 prompt shortened
the name to `britannia_global_topology.yaml`; the filename used by both runs and the
SHA-256 above are authoritative.

The topology describes a fictional bank but contains references to real technology
vendors and a real-bank comparison. A published copy must carry a fictional and
non-endorsement notice. Editing those names would create a different input and must
produce a new experiment version and digest rather than silently replacing the
recorded file.

The reproducibility inputs are more than the topology alone:

- the original Phase 1 prompt and its rendering amendment;
- the original Phase 2 build prompt and the later correction/review prompt;
- the topology, experiment configuration and namespace salt digest;
- Compose files, Topaz model manifest and Rego policy;
- mapping, projection, execution, sealing, scoring and validation scripts; and
- the hash-locked Python dependency set.

Prompts are process provenance: they explain how the experiment implementation was
created, but they are not runtime inputs or normative benchmark contracts. The full
agent transcripts are not required for reproduction and should not be published in
place of curated prompt and review records.

### Method

The Phase 2 runner performed seven stages:

1. It staged, hashed, mapped and classified every organization-topology field.
2. It generated the deterministic SynthWorld world and physically separate public
   and evaluator projections.
3. It projected only public artifacts into Topaz objects, relations, requests, a
   model manifest and Rego policy.
4. It loaded Topaz, read the directory data back and issued one authorization
   request for every public evaluation cell.
5. It normalized Topaz responses into three mechanism submissions and sealed their
   combined digest before scoring.
6. It opened the evaluator tree, verified the seal and ran the released scorers.
7. It checked input and output digests, counts, public/evaluator inventories,
   required files, submission coverage and presentation leakage.

The runner was repository-independent: it installed the released distribution and
did not use a local SynthWorld checkout or editable installation. It was not
documentation-only because implementation work still required inspection of the
released package's public Python surface.

### Results and evidence

Every result below states its denominator. The evidence paths are the locations to
retain inside the Phase 2 reference-run archive.

| Measurement | Result | Denominator meaning | Evidence |
|---|---:|---|---|
| Objects loaded and read back | 1,699 / 1,699 | Objects projected for Topaz | `04-topaz-results/run-report.json` |
| Relations loaded and read back | 5,879 / 5,879 | Relations projected for Topaz | `04-topaz-results/run-report.json` |
| Authorization requests normalized | 3,209 / 3,209 | Public evaluation cells | `04-topaz-results/run-report.json` |
| HTTP errors | 0 / 3,209 | Topaz authorization requests | `04-topaz-results/run-report.json` |
| Predictions defaulted to deny | 0 / 3,209 | Public evaluation cells | `05-submission/SUBMISSION-DIGEST.json` |
| Directory/RBAC effective decisions reproduced | 3,209 / 3,209 | Frozen directory/RBAC cells | `06-evaluator/scoring/scoring-report.json` |
| RBAC decisions reproduced | 3,209 / 3,209 | Frozen directory/RBAC cells | `06-evaluator/scoring/scoring-report.json` |
| Authorized-role sets reproduced | 895 / 895 | Subjects with authorized-role truth | `06-evaluator/scoring/scoring-report.json` |
| ABAC component decisions reproduced | 3,209 / 3,209 | Frozen ABAC component cells | `06-evaluator/scoring/scoring-report.json` |
| Birthright decisions reproduced | 3,209 / 3,209 | Frozen directory/RBAC cells | `06-evaluator/scoring/scoring-report.json` |
| Validation checks passed | 32 / 32 | Declared validation checks | `reports/validation-report.json` |

Topaz's unscored composed output contained 2,762 allows and 447 denies. It downgraded
245 effective allows: 18 at the RBAC binding/lifecycle gate and 227 at the public
ABAC guard. These are observed decision counts, not composed-decision accuracy.
The released scorers deliberately emitted no aggregate score because the mechanism
families have different denominators.

### What the run supports

- The released package could generate the input and evaluator artifacts without a
  SynthWorld repository checkout.
- An experiment-owned adapter could project the public artifacts into a live Topaz
  directory and policy.
- Topaz returned a normalized answer for every public request without a transport
  error or fallback.
- The sealed predictions reproduced the scoreable mechanism decisions listed above.

### What the run does not support

- Independent reproduction on another machine or from a published remote.
- A general claim about Topaz, policy-engine or authorization correctness.
- Accuracy of the composed Topaz decision.
- A discriminating test of principal binding.
- Enforced isolation of evaluator truth from the system under test.
- Portability of the Britannia-specific topology mapper to arbitrary organization
  YAML files.

## Reproduction materials

The SynthWorld 0.16.0 GitHub release publishes the following retained experiment
assets. The ZIPs were built from the Phase 1 and Phase 2 work conducted against
SynthWorld 0.15.0; they are historical evidence, not regenerated 0.16.0 results.

| Release asset | Bytes | SHA-256 | Intended use | Evaluator truth included |
|---|---:|---|---|---|
| [`phase1-historical-kit.zip`](https://github.com/bluntmachetti/synthworld/releases/download/v0.16.0/phase1-historical-kit.zip) | 244,962 | `443b708cf95c4de41149ea8753d9e41fe3505217fcc4826fb15890410fb93f92` | Audit the exploratory directory prototype and its original context | Yes, in a physically separate tree |
| [`phase2-reproduction-kit.zip`](https://github.com/bluntmachetti/synthworld/releases/download/v0.16.0/phase2-reproduction-kit.zip) | 213,386 | `4d870eeeae18527bd604359a5592844b9abe98bcbab01c29b084b539a0ff8921` | Conduct a clean run from the frozen source and explicit inputs | No pre-generated evaluator artifacts |
| [`phase2-reference-run.zip`](https://github.com/bluntmachetti/synthworld/releases/download/v0.16.0/phase2-reference-run.zip) | 18,124,673 | `f973b7dc0829c79cd2a6d6bce02eef97064119872bea6652423c89f3520c8fae` | Audit the retained known-good inputs, outputs, sealed submissions and scores | Yes, in a physically separate tree |
| [`SHA256SUMS`](https://github.com/bluntmachetti/synthworld/releases/download/v0.16.0/SHA256SUMS) | 277 | `bfdc21794eaadd9e1e8183994282922c834429c498dafe3caaa8d0eaebf5c9a6` | Verify the three ZIP files | No |
| [`ASSET-METADATA.json`](https://github.com/bluntmachetti/synthworld/releases/download/v0.16.0/ASSET-METADATA.json) | 766 | `ad91ef11105e2ecb47fc208cfc71e316778bfe03f4d9a231fea9e2a6426c6cb8` | Machine-readable release-asset sizes and digests | No |

The signed v0.16.0 source tag anchors the sizes and digests in this page. Verify
downloads against those values: release hosting is not itself an integrity proof.
A GitHub-generated source archive is not sufficient because the Phase 2 repository
intentionally ignores generated evidence, so those files would be absent.

Every archive must remain understandable after it is detached from this page. Its
root should contain:

```text
README.md
EXPERIMENT-ID.json
MANIFEST.json
RUN-RECEIPT.json        # required for a retained reference run
SHA256SUMS
LICENSE
prompts/
provenance/
docs/
inputs/
```

The embedded README must repeat the experiment question, evidence status, exact
version, prerequisites, commands, directory map, supported claims and limitations,
and link back to this canonical evidence record. `MANIFEST.json` should classify
each file as source, public input, system output or evaluator evidence.

The shortest verified reproduction path is:

```bash
sha256sum -c SHA256SUMS
unzip phase2-reproduction-kit.zip
cd phase2-reproduction-kit
./bin/run_all.sh
```

The published README must specify required ports, approximate disk use and the
tested Docker, Compose, Python and `uv` versions. A complete fresh-run stdout/stderr
log and machine-readable run receipt should be retained with the reference run.

## Reproducing versus adapting

An exact reproduction keeps the topology bytes, seed, configuration, policy,
dependency lock and container digest unchanged. Its result is comparable only after
the input, public-artifact, submission and report digests have been checked.

A related experiment must receive a new identifier and must not overwrite the Phase
2 baseline. Its report should describe every changed input, mapping decision and
policy assumption; regenerate all checksums; construct discriminating positive and
negative cases; keep public inputs and evaluator truth separately typed and
serialized; and report every metric with its denominator.

The Britannia mapper is organization-specific. A new organization can either extend
that mapping explicitly or begin from the released `synthworld
scaffold-enterprise-access` workflow. The adaptation guide in the reproduction kit
should identify which files are SynthWorld-generated and which are experiment-owned,
then explain how to build public requests, run the system under test, seal a blinded
submission and score it separately.

An admission-only versus continued-runtime-authorization study inspired by changing
providers, credentials, destinations, delegated authority or capabilities should be
a new experiment series. It should define the protected execution transitions and
mutations explicitly rather than retrofitting Phase 2 or silently redefining the
already planned Phase 3.

## Material limitations found by Phase 2

### The composed decision was not scored

Topaz produced a composed decision that combined RBAC-family results with the ABAC
guard. SynthWorld 0.15.0 had separate directory/RBAC, ABAC and ReBAC scorers but no
submission or evaluator for the composed `CompiledEnterpriseAccessStateV1`
decision. Cross-tenant and scope-exceeded actions were denied by the experiment's
composition while their released directory/RBAC truth remained allow.

Later contract work does not retroactively change what the frozen Phase 2 run
scored. A successor experiment must use a released composed-decision contract and
record that new package version.

### The binding cohort did not test binding

The public input exposed the observed account binding but not enough evidence to
resolve its canonical subject. The reference policy therefore treated the binding
gate as passing. All 15 wrong-binding cases were already denied because the RBAC
derivation found no path, so ignoring the binding mechanism did not change the
outcome.

### Some submitted metrics were not publicly solvable

Several released prediction fields depended on evaluator-only identifiers or
unpublished policy intent, including ABAC truth identifiers, RBAC derivation-path
identifiers and separation-of-duty constraints. Phase 2 reported these metrics as
not publicly winnable rather than folding them into a headline result.

### Public policy could reveal the negative cohort

The ABAC vocabulary did not provide the tenant inequality needed by the experiment.
The projected rule therefore enumerated the public cell identifiers in its
cross-tenant scope. A separately derived tenant comparison agreed with all 63 cases,
but it was a cross-check rather than the decision path.

### Isolation was auditable, not enforced

Public and evaluator artifacts were physically separate and submissions were sealed
before scoring, but evaluator truth existed on the same host while the system under
test ran. The supported process did not read it; the filesystem did not make such a
read impossible. Phase 3 must run the system under test without an evaluator mount
and give evaluator access only to a separate scorer.

## Contract work before Phase 3

The experiment produced four focused requirements. SynthWorld 0.16.0 implements
the first three; Phase 3 still requires the isolated lab work:

- [#137](https://github.com/bluntmachetti/synthworld/issues/137) added a publicly
  constructible composed-decision submission and independent scoring after the
  frozen Phase 2 run.
- [#138](https://github.com/bluntmachetti/synthworld/issues/138) adds
  discriminating tenant, scope, binding, temporal, clearance and composed
  authority counterfactuals with hidden pair labels and explicit discriminating
  denominators.
- [#139](https://github.com/bluntmachetti/synthworld/issues/139) added the released
  consumer API, digest helpers and supported end-to-end workflow after the frozen
  Phase 2 run.
- [#140](https://github.com/bluntmachetti/synthworld/issues/140) tracks publication
  of the fresh isolated, reproducible adapter lab against the released contracts.

Phase 3 should start in a fresh experiment directory against a released package. It
must not retrofit Phase 2 or silently reinterpret its results.
