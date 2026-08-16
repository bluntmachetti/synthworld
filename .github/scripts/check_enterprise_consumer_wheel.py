"""Exercise the documented enterprise authorization path from an installed wheel."""

from __future__ import annotations

import hashlib
import json
import tempfile
from importlib.metadata import version
from pathlib import Path

from synthworld.enterprise import consumer as sw


def _topology() -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "blueprint": {
            "schema_version": "1.0.0",
            "blueprint_key": "installed-wheel-smoke",
            "id_namespace_salt": "1" * 64,
            "tenants": [{"key": "tenant"}],
            "organisations": [{"key": "org", "tenant_key": "tenant"}],
            "units": [
                {
                    "key": "unit",
                    "tenant_key": "tenant",
                    "organisation_key": "org",
                    "unit_kind": "department",
                }
            ],
            "populations": [
                {
                    "key": "people",
                    "tenant_key": "tenant",
                    "organisation_key": "org",
                    "unit_key": "unit",
                    "population_kind": "employee",
                    "count": 1,
                }
            ],
            "groups": [],
            "roles": [
                {
                    "key": "reader",
                    "tenant_key": "tenant",
                    "organisation_key": "org",
                    "owner_unit_key": "unit",
                }
            ],
            "resource_sets": [
                {
                    "key": "records",
                    "tenant_key": "tenant",
                    "organisation_key": "org",
                    "target_kind": "data_store",
                    "owner_unit_key": "unit",
                    "instance_count": 1,
                    "actions": ["read"],
                }
            ],
            "principal_access_atom_rules": [
                {
                    "rule_key": "read-case",
                    "population_key": "people",
                    "resource_set_key": "records",
                    "action": "read",
                    "selector": {"kind": "all"},
                }
            ],
        },
        "iam_universe_extension": {
            "schema_version": "1.0.0",
            "account_allocations": [],
            "account_access_atom_rules": [],
        },
        "directory_rbac_state": {
            "schema_version": "1.0.0",
            "account_observations": [],
            "memberships": [],
            "group_nesting": [],
            "group_role_assignments": [],
            "population_role_assignments": [
                {
                    "rule_key": "reader-assignment",
                    "population_key": "people",
                    "role_key": "reader",
                    "selector": {"kind": "all"},
                }
            ],
            "role_hierarchy": [],
            "role_grants": [
                {
                    "role_key": "reader",
                    "resource_set_key": "records",
                    "action": "read",
                }
            ],
            "direct_entitlements": [],
        },
    }


def _public_prediction(
    *, identity_root: Path, corpus_root: Path, rbac_root: Path, auth_root: Path
) -> sw.EnterpriseAuthorizationPredictionV1:
    """Tiny example adapter that receives public roots only."""

    universe = sw.load_public_enterprise_identity_access_universe(identity_root)
    corpus = sw.load_public_enterprise_evaluation_corpus(corpus_root)
    rbac = sw.load_public_enterprise_directory_rbac_kernel(rbac_root)
    authorization = sw.load_public_enterprise_authorization(auth_root)

    atoms = {item.access_atom_id: item for item in universe.access_atoms}
    permissions = {
        (item.authorization_target_id, item.action): item.permission_id
        for item in universe.permissions
    }
    roles_by_subject: dict[str, set[str]] = {}
    for assignment in rbac.subject_role_assignments:
        roles_by_subject.setdefault(assignment.subject_id, set()).add(
            assignment.role_id
        )
    grants = {(item.role_id, item.permission_id) for item in rbac.role_grants}

    predictions: list[dict[str, object]] = []
    for cell in corpus.evaluation_cells:
        atom = atoms[cell.access_atom_id]
        permission_id = permissions[(atom.authorization_target_id, atom.action)]
        allowed = any(
            (role_id, permission_id) in grants
            for role_id in roles_by_subject.get(atom.subject_id, set())
        )
        decision = "allow" if allowed else "deny"
        predictions.append(
            {
                "cell_id": cell.cell_id,
                "mechanism_outcomes": {"rbac": decision},
                "effective_decision": decision,
                "final_decision": decision,
                "policy_conflict": False,
            }
        )

    execution = {
        "synthworld_package_version": version("idcognito-synthworld"),
        "adapter_name": "installed-wheel-smoke",
        "adapter_version": "1.0.0",
        "system_name": "example-public-rbac",
        "system_version": "1.0.0",
        "policy_name": "reader",
        "policy_version": "1.0.0",
        "policy_sha256": hashlib.sha256(b"example-public-rbac-v1\n").hexdigest(),
    }
    return sw.build_enterprise_model(
        sw.EnterpriseAuthorizationPredictionV1,
        {
            "identity_access_universe_digest": sw.digest_enterprise_model(
                universe
            ).model_dump(mode="json"),
            "evaluation_corpus_digest": sw.digest_enterprise_model(corpus).model_dump(
                mode="json"
            ),
            "composition_digest": sw.digest_enterprise_model(
                authorization.composition
            ).model_dump(mode="json"),
            "authorization_kernel_digest": sw.digest_enterprise_model(
                authorization.kernel
            ).model_dump(mode="json"),
            "evaluation_scope_digest": sw.digest_enterprise_model(
                authorization.evaluation_scope
            ).model_dump(mode="json"),
            "execution": execution,
            "cells": predictions,
        },
    )


def _compiled_ids(
    provenance: sw.EnterpriseCompilerProvenanceV1,
    *,
    source_kind: sw.EnterpriseCompilerSourceKind,
    logical_key: str,
    object_kind: sw.EnterpriseCompiledObjectKind,
    action: str | None = None,
) -> tuple[str, ...]:
    entry = next(
        item
        for item in provenance.entries
        if item.source_kind is source_kind and item.logical_key == (logical_key,)
    )
    return tuple(
        item.stable_id
        for item in entry.compiled_objects
        if item.object_kind is object_kind and (action is None or item.action == action)
    )


def main() -> None:
    imported = sw.build_enterprise_model(
        sw.EnterpriseIdentityAccessImportV1, _topology()
    )
    universe_result = sw.compile_enterprise_identity_access_universe(
        import_model=imported, seed=7
    )
    universe = universe_result.public_universe
    universe_digest = sw.digest_enterprise_model(universe)
    directory_kernel = sw.compile_enterprise_directory_rbac_kernel(
        import_model=imported, universe=universe
    )
    provenance = sw.build_enterprise_compiler_provenance(
        import_model=imported,
        compile_result=universe_result,
        directory_rbac_kernel=directory_kernel,
    )
    (atom_id,) = _compiled_ids(
        provenance,
        source_kind=sw.EnterpriseCompilerSourceKind.PRINCIPAL_ACCESS_RULE,
        logical_key="read-case",
        object_kind=sw.EnterpriseCompiledObjectKind.ACCESS_ATOM,
    )
    (principal_id,) = _compiled_ids(
        provenance,
        source_kind=sw.EnterpriseCompilerSourceKind.POPULATION,
        logical_key="people",
        object_kind=sw.EnterpriseCompiledObjectKind.PRINCIPAL,
    )
    (role_id,) = _compiled_ids(
        provenance,
        source_kind=sw.EnterpriseCompilerSourceKind.ROLE,
        logical_key="reader",
        object_kind=sw.EnterpriseCompiledObjectKind.ROLE,
    )
    (permission_id,) = _compiled_ids(
        provenance,
        source_kind=sw.EnterpriseCompilerSourceKind.RESOURCE_SET,
        logical_key="records",
        object_kind=sw.EnterpriseCompiledObjectKind.PERMISSION,
        action="read",
    )

    corpus_config = sw.build_enterprise_model(
        sw.EnterpriseEvaluationCorpusConfigV1,
        {
            "identity_access_universe_digest": universe_digest.model_dump(mode="json"),
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
        universe=universe, corpus_config=corpus_config
    )
    corpus = corpus_result.public_corpus
    corpus_digest = sw.digest_enterprise_model(corpus)

    directory_intent = sw.build_enterprise_model(
        sw.EnterpriseDirectoryRbacIntentOverlayV1,
        {
            "identity_access_universe_digest": universe_digest.model_dump(mode="json"),
            "evaluation_corpus_digest": corpus_digest.model_dump(mode="json"),
            "intended_subject_role_assignments": [
                {
                    "subject_id": principal_id,
                    "role_id": role_id,
                }
            ],
            "intended_role_grants": [
                {
                    "role_id": role_id,
                    "permission_id": permission_id,
                }
            ],
        },
    )
    session_state = sw.build_enterprise_model(
        sw.EnterpriseRbacSessionStateInputV1,
        {"evaluation_corpus_digest": corpus_digest.model_dump(mode="json")},
    )
    directory_truth = sw.compile_enterprise_directory_rbac_truth(
        universe=universe,
        canonical_binding_truth=(universe_result.evaluator_canonical_binding_truth),
        corpus=corpus,
        directory_rbac_kernel=directory_kernel,
        session_state=session_state,
        directory_rbac_intent=directory_intent,
    )

    common_overlay = {
        "identity_access_universe_digest": universe_digest.model_dump(mode="json"),
        "evaluation_corpus_digest": corpus_digest.model_dump(mode="json"),
    }
    abac_state = sw.build_enterprise_model(
        sw.EnterpriseAbacStateOverlayV1, common_overlay
    )
    abac_intent = sw.build_enterprise_model(
        sw.EnterpriseAbacIntentOverlayV1, common_overlay
    )
    abac_truth = sw.compile_enterprise_abac_truth(
        universe=universe,
        corpus=corpus,
        abac_state=abac_state,
        abac_intent=abac_intent,
    )
    rebac_state = sw.build_enterprise_model(
        sw.EnterpriseRebacStateOverlayV1, common_overlay
    )
    rebac_intent = sw.build_enterprise_model(
        sw.EnterpriseRebacIntentOverlayV1, common_overlay
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
    (cell,) = corpus.evaluation_cells
    cell_id = cell.cell_id
    profile = sw.build_enterprise_model(
        sw.AuthorizationEvaluationProfileV1,
        {
            "evaluation_corpus_digest": corpus_digest.model_dump(mode="json"),
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
        canonical_binding_truth=(universe_result.evaluator_canonical_binding_truth),
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
            "evaluation_corpus_digest": corpus_digest.model_dump(mode="json"),
            "authorization_kernel_digest": sw.digest_enterprise_model(
                authorization_kernel
            ).model_dump(mode="json"),
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

    root = Path(tempfile.mkdtemp(prefix="synthworld-enterprise-consumer-"))
    identity_root = root / "identity"
    corpus_root = root / "corpus"
    rbac_root = root / "rbac"
    auth_root = root / "authorization"
    sw.export_enterprise_identity_access_compile_result(identity_root, universe_result)
    identity_manifest = json.loads(
        (identity_root / "public" / "manifest.json").read_bytes()
    )
    identity_descriptor = next(
        item
        for item in identity_manifest["artifacts"]
        if item["path"] == "identity-access-universe.json"
    )
    exported_universe = identity_root / "public" / "identity-access-universe.json"
    if (
        identity_descriptor["digest"] != universe_digest.model_dump(mode="json")
        or sw.digest_enterprise_artifact(exported_universe.read_bytes())
        != universe_digest
    ):
        raise RuntimeError("direct enterprise digest differs from exported artifact")
    sw.export_enterprise_evaluation_corpus(corpus_root, corpus_result)
    sw.export_enterprise_directory_rbac(
        rbac_root, kernel=directory_kernel, truth=directory_truth
    )
    sw.export_enterprise_authorization(
        auth_root,
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
    (root / "operator-provenance.json").write_bytes(
        sw.canonical_enterprise_model_bytes(provenance)
    )

    prediction = _public_prediction(
        identity_root=identity_root,
        corpus_root=corpus_root,
        rbac_root=rbac_root,
        auth_root=auth_root,
    )
    evaluator = sw.load_evaluator_enterprise_authorization(auth_root)
    public = sw.load_public_enterprise_authorization(auth_root)
    report = sw.evaluate_enterprise_authorization(
        scope=public.evaluation_scope,
        truth=evaluator.access_state,
        predictions=prediction,
    )
    metrics = {item.name: item.value for item in report.metrics}
    expected = {
        "effective_decision_accuracy": 1.0,
        "final_decision_accuracy": 1.0,
        "policy_conflict_detection_accuracy": 1.0,
    }
    if any(metrics[name] != value for name, value in expected.items()):
        raise RuntimeError(f"installed-wheel enterprise metrics differ: {metrics}")


if __name__ == "__main__":
    main()
