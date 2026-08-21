# Build and score an enterprise authorization experiment

This is the supported released-package path from an authored organisation to a
composed authorization report. The identity import has CLI support; corpus,
RBAC/ABAC/ReBAC compilation, composition, submission construction, and scoring
are Python-only in 0.16.0. Import those contracts from the curated
`synthworld.enterprise.consumer` namespace.

SynthWorld generates deterministic benchmark data and evaluates observations. It
does not deploy Topaz, OPA, AuthZEN, or another policy decision point. Keep that
adapter in the experiment repository and give it only the exported public trees.

## 1. Author and validate the topology

Start with the installed CLI, then replace the scaffolded fictional structure
with the organisation shape needed by the experiment:

```bash
synthworld scaffold-enterprise-access --format yaml --output topology.yaml
synthworld validate-enterprise-access --input topology.yaml
```

For the runnable one-cell example below, the topology must contain these logical
keys:

- a population `people` with `count: 1`, role `reader`, and resource set
  `records` with `instance_count: 1` and action `read`;
- a principal access-atom rule `read-case` selecting that population and
  resource; and
- directory state with a population-role assignment and a `reader`/`records`/
  `read` role grant.

The scaffold shows the complete envelope. Keep its `id_namespace_salt` as a
lowercase 64-character hexadecimal value and treat it as operator-private.

## 2. Compile the world, corpus, and authorization artifacts

Save this as `build_experiment.py`. It imports no repository example, test, or
internal module.

```python
from pathlib import Path

from synthworld.enterprise import consumer as sw


def json_value(model):
    return model.model_dump(mode="json")


imported = sw.load_enterprise_identity_access_import(Path("topology.yaml"))
world = sw.compile_enterprise_identity_access_universe(
    import_model=imported,
    seed=20260816,
)
universe = world.public_universe
universe_digest = sw.digest_enterprise_model(universe)
directory_kernel = sw.compile_enterprise_directory_rbac_kernel(
    import_model=imported,
    universe=universe,
)
provenance = sw.build_enterprise_compiler_provenance(
    import_model=imported,
    compile_result=world,
    directory_rbac_kernel=directory_kernel,
)


def compiled_ids(source_kind, logical_key, object_kind):
    entry = next(
        item
        for item in provenance.entries
        if item.source_kind is source_kind and item.logical_key == (logical_key,)
    )
    return tuple(
        item.stable_id
        for item in entry.compiled_objects
        if item.object_kind is object_kind
    )


atom_id, = compiled_ids(
    sw.EnterpriseCompilerSourceKind.PRINCIPAL_ACCESS_RULE,
    "read-case",
    sw.EnterpriseCompiledObjectKind.ACCESS_ATOM,
)
principal_id, = compiled_ids(
    sw.EnterpriseCompilerSourceKind.POPULATION,
    "people",
    sw.EnterpriseCompiledObjectKind.PRINCIPAL,
)
role_id, = compiled_ids(
    sw.EnterpriseCompilerSourceKind.ROLE,
    "reader",
    sw.EnterpriseCompiledObjectKind.ROLE,
)
permission_id, = (
    item.stable_id
    for item in next(
        row
        for row in provenance.entries
        if row.source_kind is sw.EnterpriseCompilerSourceKind.RESOURCE_SET
        and row.logical_key == ("records",)
    ).compiled_objects
    if item.object_kind is sw.EnterpriseCompiledObjectKind.PERMISSION
    and item.action == "read"
)

corpus_config = sw.build_enterprise_model(
    sw.EnterpriseEvaluationCorpusConfigV1,
    {
        "identity_access_universe_digest": json_value(universe_digest),
        "contexts": [{"context_key": "default"}],
        "evaluation_cells": [
            {
                "cell_key": "read",
                "access_atom_id": atom_id,
                "context_key": "default",
                "session_state_key": None,
                "tick": 1,
            }
        ],
        "access_requests": [{"request_key": "read", "cell_key": "read"}],
    },
)
corpus_result = sw.compile_enterprise_evaluation_corpus(
    universe=universe,
    corpus_config=corpus_config,
)
corpus = corpus_result.public_corpus
corpus_digest = sw.digest_enterprise_model(corpus)

directory_intent = sw.build_enterprise_model(
    sw.EnterpriseDirectoryRbacIntentOverlayV1,
    {
        "identity_access_universe_digest": json_value(universe_digest),
        "evaluation_corpus_digest": json_value(corpus_digest),
        "intended_subject_role_assignments": [
            {"subject_id": principal_id, "role_id": role_id}
        ],
        "intended_role_grants": [
            {"role_id": role_id, "permission_id": permission_id}
        ],
    },
)
session_state = sw.build_enterprise_model(
    sw.EnterpriseRbacSessionStateInputV1,
    {"evaluation_corpus_digest": json_value(corpus_digest)},
)
directory_truth = sw.compile_enterprise_directory_rbac_truth(
    universe=universe,
    canonical_binding_truth=world.evaluator_canonical_binding_truth,
    corpus=corpus,
    directory_rbac_kernel=directory_kernel,
    session_state=session_state,
    directory_rbac_intent=directory_intent,
)

overlay_binding = {
    "identity_access_universe_digest": json_value(universe_digest),
    "evaluation_corpus_digest": json_value(corpus_digest),
}
abac_state = sw.build_enterprise_model(
    sw.EnterpriseAbacStateOverlayV1, overlay_binding
)
abac_intent = sw.build_enterprise_model(
    sw.EnterpriseAbacIntentOverlayV1, overlay_binding
)
abac_truth = sw.compile_enterprise_abac_truth(
    universe=universe,
    corpus=corpus,
    abac_state=abac_state,
    abac_intent=abac_intent,
)
rebac_state = sw.build_enterprise_model(
    sw.EnterpriseRebacStateOverlayV1, overlay_binding
)
rebac_intent = sw.build_enterprise_model(
    sw.EnterpriseRebacIntentOverlayV1, overlay_binding
)
rebac_truth = sw.compile_enterprise_rebac_truth(
    universe=universe,
    corpus=corpus,
    rebac_state=rebac_state,
    rebac_intent=rebac_intent,
)

composition = sw.compose_enterprise_authorization(
    directory_rbac_truth=directory_truth,
    abac_truth=abac_truth,
    rebac_truth=rebac_truth,
)
cell, = corpus.evaluation_cells
cell_id = cell.cell_id
profile = sw.build_enterprise_model(
    sw.AuthorizationEvaluationProfileV1,
    {
        "evaluation_corpus_digest": json_value(corpus_digest),
        "cells": [{"cell_id": cell_id, "profile": "rbac"}],
    },
)
authorization_kernel = sw.compile_enterprise_authorization_kernel(
    universe=universe,
    corpus=corpus,
    composition=composition,
    evaluation_profile=profile,
)
access_state = sw.compile_enterprise_access_state(
    universe=universe,
    canonical_binding_truth=world.evaluator_canonical_binding_truth,
    corpus=corpus,
    composition=composition,
    directory_rbac_truth=directory_truth,
    evaluation_profile=profile,
    abac_truth=abac_truth,
    rebac_truth=rebac_truth,
)
scope = sw.build_enterprise_model(
    sw.EnterpriseAuthorizationEvaluationScopeV1,
    {
        "evaluation_corpus_digest": json_value(corpus_digest),
        "authorization_kernel_digest": json_value(
            sw.digest_enterprise_model(authorization_kernel)
        ),
        "cells": [
            {
                "cell_id": cell_id,
                "scored_dimensions": [
                    "effective_decision",
                    "final_decision",
                    "policy_conflict",
                ],
            }
        ],
    },
)

sw.export_enterprise_identity_access_compile_result(Path("artifacts/identity"), world)
sw.export_enterprise_evaluation_corpus(Path("artifacts/corpus"), corpus_result)
sw.export_enterprise_directory_rbac(
    Path("artifacts/rbac"),
    kernel=directory_kernel,
    truth=directory_truth,
)
sw.export_enterprise_authorization(
    Path("artifacts/authorization"),
    public=sw.EnterpriseAuthorizationPublicArtifactsV1(
        abac_state=abac_state,
        abac_intent=abac_intent,
        rebac_state=rebac_state,
        rebac_intent=rebac_intent,
        composition=composition,
        evaluation_scope=scope,
        kernel=authorization_kernel,
    ),
    evaluator=sw.EnterpriseAuthorizationEvaluatorArtifactsV1(
        abac_truth=abac_truth,
        rebac_truth=rebac_truth,
        access_state=access_state,
    ),
)
with Path("operator-provenance.json").open("xb") as output:
    output.write(sw.canonical_enterprise_model_bytes(provenance))
```

Run it in a new directory. Every exporter rejects an existing output root:

```bash
python build_experiment.py
```

The ABAC and ReBAC mechanisms are optional to the composition API. The fixed
authorization export bundle currently requires both typed state/intent and truth
artifacts; use digest-bound empty overlays, as above, when an experiment selects
only RBAC. This keeps the public file inventory explicit and loadable.

`operator-provenance.json` is not product input or evaluator truth. It contains
private logical keys and canonical JSON Pointer locations such as
`/blueprint/roles/0`, plus their compiled opaque IDs. Store it with operator
configuration. Paths refer to the validated, canonically ordered model—not raw
YAML line numbers—and remove the need to infer IDs from collection position.

## 3. Run the system with public artifacts only

Mount or copy only these directories into the adapter environment:

```text
artifacts/identity/public/
artifacts/corpus/public/
artifacts/rbac/public/
artifacts/authorization/public/
```

Load them with `load_public_enterprise_identity_access_universe`,
`load_public_enterprise_evaluation_corpus`,
`load_public_enterprise_directory_rbac_kernel`, and
`load_public_enterprise_authorization`. Project those records into the external
system, collect one observation for every public cell, and construct
`EnterpriseAuthorizationPredictionV1`. Use `digest_enterprise_model` for every
binding; do not export a tree and scrape its manifest merely to recover a digest.
It canonicalizes a typed model and returns the same SHA-256 record used by the
exporters and evaluators. To verify bytes already read from an exported canonical
JSON file, use `digest_enterprise_artifact(path.read_bytes())`; that helper hashes
the bytes exactly and does not parse or rewrite them.

For this one-cell example, the normalized adapter result is:

```python
import hashlib
from importlib.metadata import version
from pathlib import Path

from synthworld.enterprise import consumer as sw


def json_value(model):
    return model.model_dump(mode="json")

universe = sw.load_public_enterprise_identity_access_universe(
    Path("artifacts/identity")
)
corpus = sw.load_public_enterprise_evaluation_corpus(Path("artifacts/corpus"))
public = sw.load_public_enterprise_authorization(
    Path("artifacts/authorization")
)
universe_digest = sw.digest_enterprise_model(universe)
corpus_digest = sw.digest_enterprise_model(corpus)
cell, = corpus.evaluation_cells
cell_id = cell.cell_id
prediction = sw.build_enterprise_model(
    sw.EnterpriseAuthorizationPredictionV1,
    {
        "identity_access_universe_digest": json_value(universe_digest),
        "evaluation_corpus_digest": json_value(corpus_digest),
        "composition_digest": json_value(
            sw.digest_enterprise_model(public.composition)
        ),
        "authorization_kernel_digest": json_value(
            sw.digest_enterprise_model(public.kernel)
        ),
        "evaluation_scope_digest": json_value(
            sw.digest_enterprise_model(public.evaluation_scope)
        ),
        "execution": {
            "synthworld_package_version": version("idcognito-synthworld"),
            "adapter_name": "your-adapter",
            "adapter_version": "1.0.0",
            "system_name": "your-pdp",
            "system_version": "pinned-version",
            "policy_name": "reader-policy",
            "policy_version": "1.0.0",
            "policy_sha256": hashlib.sha256(b"reader-policy-v1\n").hexdigest(),
        },
        "cells": [
            {
                "cell_id": cell_id,
                "mechanism_outcomes": {"rbac": "allow"},
                "effective_decision": "allow",
                "final_decision": "allow",
                "policy_conflict": False,
            }
        ],
    },
)
with Path("prediction.json").open("xb") as output:
    output.write(sw.canonical_enterprise_model_bytes(prediction))
```

Replace the literal decision fields with observations returned by the external
system. Do not derive them from `access_state` or another evaluator artifact.

## 4. Score in a separate evaluator process

Only the scorer receives the complete authorization root:

```python
from pathlib import Path

from synthworld.enterprise import consumer as sw

public = sw.load_public_enterprise_authorization(
    Path("artifacts/authorization")
)
evaluator = sw.load_evaluator_enterprise_authorization(
    Path("artifacts/authorization")
)
prediction = sw.EnterpriseAuthorizationPredictionV1.model_validate_json(
    Path("prediction.json").read_bytes()
)
report = sw.evaluate_enterprise_authorization(
    scope=public.evaluation_scope,
    truth=evaluator.access_state,
    predictions=prediction,
)
with Path("report.json").open("xb") as output:
    output.write(sw.canonical_enterprise_model_bytes(report))
```

`load_evaluator_enterprise_authorization(root)` validates the evaluator artifacts
against the public artifacts and therefore requires both the `public/` and
`evaluator/` subtrees beneath the supplied root. An evaluator deliverable may duplicate
the public bytes for this purpose. That layout is an integrity requirement, not
permission for the system under test to read evaluator data: mount only the public
deliverable into the product or adapter, and make the complete root available only to
the isolated scorer.

Interpret every metric independently using its denominator. There is no aggregate
enterprise authorization score.

## Input and reproducibility rules

- Direct Pydantic constructors are strict: supply enum instances and tuples. For
  ordinary dict/list/string data, use `build_enterprise_model`, `model_validate_json`,
  or the YAML/JSON/CSV import loaders. Those are the canonical configuration style.
- YAML aliases and merge keys, duplicate mapping keys, tags, timestamps, and
  non-JSON scalars are rejected. Semantic duplicate rows are also rejected after
  canonical ordering.
- The same explicit import, seed, configuration, schema versions, and package
  version produce the same bytes. Structural IDs are namespace-derived; seeded
  selectors can change selected principal/account mappings. Do not join generated
  collections by position.
- Exporters require absent destination roots and never overwrite them. Compilation
  is in-memory and does not create files; export is mandatory when a process or
  trust boundary consumes the artifacts.
- Retain the seed, authored input, package version, provenance artifact, canonical
  artifact digests, external policy digest, prediction bytes, and report bytes.

## Rendering boundary

The released `synthworld.explorer` surface includes a self-contained HTML renderer,
but its inputs are bounded to the checksum-verified published Asteria Agentic v1
package and verified generated enterprise-agentic smoke packages selected with the
explicit `generated-enterprise-agentic` package profile. That generated adapter
consumes the independently versioned generated smoke contract; it is not an adapter
for the enterprise authorization artifacts built in this guide.

Explorer does not render an arbitrary universe produced by
`compile-enterprise-access`, this guide's RBAC/ABAC/ReBAC authorization bundle, or
the fixed-reference `enterprise-agentic` authorization package. Any SVG/HTML
topology page produced by a Topaz or other enterprise lab remains an
experiment-owned visualization, not a SynthWorld render or benchmark artifact. See
the [Explorer v0.1 contract](../concepts/explorer-v01.md) for the supported package
profiles and exact public/evaluator boundary.
