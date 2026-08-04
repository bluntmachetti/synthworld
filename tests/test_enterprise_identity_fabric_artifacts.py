"""Physical boundary and generated-contract tests for the #7 smoke pack."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import BaseModel

from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.identity_fabric.metrics import (
    evaluate_enterprise_identity_fabric,
    perfect_enterprise_identity_fabric_prediction,
)
from synthworld.enterprise.identity_fabric.models import (
    EnterpriseIdentityFabricBenchmarkV1,
    EnterpriseIdentityFabricPublicInputV1,
)
from synthworld.enterprise.identity_fabric.reference import (
    reference_enterprise_identity_fabric,
)
from synthworld.enterprise.identity_fabric.serialization import (
    EnterpriseIdentityFabricArtifactError,
    export_enterprise_identity_fabric,
    load_evaluator_enterprise_identity_fabric,
    load_public_enterprise_identity_fabric,
)
from synthworld.enterprise.models import EnterpriseArtifactManifestV1

CONTRACT_ROOT = Path("enterprise-identity-access-contract")


def _rewrite_artifact(
    root: Path,
    *,
    visibility: str,
    name: str,
    model: BaseModel,
) -> None:
    payload = canonical_json_bytes(model)
    (root / visibility / name).write_bytes(payload)
    manifest_path = root / visibility / "manifest.json"
    manifest = EnterpriseArtifactManifestV1.model_validate_json(
        manifest_path.read_bytes()
    )
    descriptor = manifest.artifacts[0].model_copy(
        update={
            "schema_version": str(model.model_dump()["schema_version"]),
            "digest": synthetic_digest(payload),
            "byte_size": len(payload),
        }
    )
    manifest_path.write_bytes(
        canonical_json_bytes(manifest.model_copy(update={"artifacts": (descriptor,)}))
    )


def test_artifacts_round_trip_and_public_loader_never_traverses_evaluator(
    tmp_path: Path,
) -> None:
    reference = reference_enterprise_identity_fabric()
    root = tmp_path / "identity-fabric"
    export_enterprise_identity_fabric(
        root, public=reference.public, evaluator=reference.evaluator
    )
    assert load_public_enterprise_identity_fabric(root) == reference.public
    assert load_evaluator_enterprise_identity_fabric(root) == reference.evaluator
    assert {
        str(item.relative_to(root)) for item in root.rglob("*") if item.is_file()
    } == {
        "public/identity-fabric-input.json",
        "public/manifest.json",
        "evaluator/identity-fabric-evaluator.json",
        "evaluator/manifest.json",
    }
    public_bytes = (root / "public" / "identity-fabric-input.json").read_bytes()
    assert public_bytes == canonical_json_bytes(reference.public)
    assert b'"case_labels"' not in public_bytes
    assert b'"canonical_binding_truth"' not in public_bytes

    (root / "evaluator" / "identity-fabric-evaluator.json").write_bytes(b"{")
    assert load_public_enterprise_identity_fabric(root) == reference.public
    with pytest.raises(EnterpriseIdentityFabricArtifactError, match="invalid"):
        load_evaluator_enterprise_identity_fabric(root)


def test_export_rejects_an_existing_destination(tmp_path: Path) -> None:
    reference = reference_enterprise_identity_fabric()
    root = tmp_path / "existing"
    root.mkdir()
    with pytest.raises(EnterpriseIdentityFabricArtifactError, match="already exists"):
        export_enterprise_identity_fabric(
            root, public=reference.public, evaluator=reference.evaluator
        )


@pytest.mark.parametrize(
    ("corruption", "message"),
    (
        ("missing", "unreadable"),
        ("not_directory", "not a real directory"),
        ("unexpected", "inventory differs"),
        ("nonregular", "non-regular entry"),
        ("visibility", "visibility differs"),
        ("manifest_count", "exactly one artifact"),
        ("descriptor_path", "manifest binding differs"),
        ("descriptor_schema", "manifest binding differs"),
        ("descriptor_size", "manifest binding differs"),
        ("descriptor_digest", "manifest binding differs"),
        ("invalid_json", "artifact is invalid"),
        ("noncanonical", "not canonical JSON"),
    ),
)
def test_public_loader_rejects_every_physical_corruption_class(
    tmp_path: Path,
    corruption: str,
    message: str,
) -> None:
    reference = reference_enterprise_identity_fabric()
    root = tmp_path / corruption
    if corruption == "missing":
        with pytest.raises(EnterpriseIdentityFabricArtifactError, match=message):
            load_public_enterprise_identity_fabric(root)
        return
    if corruption == "not_directory":
        root.mkdir()
        (root / "public").write_text("not a directory\n")
        with pytest.raises(EnterpriseIdentityFabricArtifactError, match=message):
            load_public_enterprise_identity_fabric(root)
        return

    export_enterprise_identity_fabric(
        root, public=reference.public, evaluator=reference.evaluator
    )
    public_root = root / "public"
    manifest_path = public_root / "manifest.json"
    artifact_path = public_root / "identity-fabric-input.json"
    if corruption == "unexpected":
        (public_root / "unexpected.json").write_text("{}\n")
    elif corruption == "nonregular":
        artifact_path.unlink()
        artifact_path.symlink_to(manifest_path)
    elif corruption == "visibility":
        manifest = EnterpriseArtifactManifestV1.model_validate_json(
            manifest_path.read_bytes()
        ).model_copy(update={"visibility": "evaluator"})
        manifest_path.write_bytes(canonical_json_bytes(manifest))
    elif corruption == "manifest_count":
        manifest = EnterpriseArtifactManifestV1.model_validate_json(
            manifest_path.read_bytes()
        ).model_copy(update={"artifacts": ()})
        manifest_path.write_bytes(canonical_json_bytes(manifest))
    elif corruption.startswith("descriptor_"):
        manifest = EnterpriseArtifactManifestV1.model_validate_json(
            manifest_path.read_bytes()
        )
        updates_by_corruption: dict[str, dict[str, object]] = {
            "descriptor_path": {"path": "wrong.json"},
            "descriptor_schema": {"schema_version": "9.9.9"},
            "descriptor_size": {"byte_size": 0},
            "descriptor_digest": {"digest": synthetic_digest(b"wrong\n")},
        }
        updates = updates_by_corruption[corruption]
        descriptor = manifest.artifacts[0].model_copy(update=updates)
        manifest_path.write_bytes(
            canonical_json_bytes(
                manifest.model_copy(update={"artifacts": (descriptor,)})
            )
        )
    elif corruption == "invalid_json":
        artifact_path.write_bytes(b"{")
    else:
        artifact_path.write_bytes(b" " + artifact_path.read_bytes())
    with pytest.raises(EnterpriseIdentityFabricArtifactError, match=message):
        load_public_enterprise_identity_fabric(root)


def test_public_loader_recomputes_projection_and_input_bindings(
    tmp_path: Path,
) -> None:
    reference = reference_enterprise_identity_fabric()
    projection_root = tmp_path / "projection"
    export_enterprise_identity_fabric(
        projection_root,
        public=reference.public,
        evaluator=reference.evaluator,
    )
    first_query = reference.public.benchmark.membership_queries[0]
    changed_query = first_query.model_copy(update={"query_id": "changed-query-id"})
    changed_benchmark_document = reference.public.benchmark.model_dump(mode="python")
    changed_benchmark_document["membership_queries"] = (
        changed_query,
        *reference.public.benchmark.membership_queries[1:],
    )
    changed_benchmark = EnterpriseIdentityFabricBenchmarkV1.model_validate(
        changed_benchmark_document
    )
    changed_public = EnterpriseIdentityFabricPublicInputV1(
        invariant=reference.public.invariant,
        checkpoints=reference.public.checkpoints,
        benchmark=changed_benchmark,
    )
    _rewrite_artifact(
        projection_root,
        visibility="public",
        name="identity-fabric-input.json",
        model=changed_public,
    )
    with pytest.raises(
        EnterpriseIdentityFabricArtifactError, match="projection differs"
    ):
        load_public_enterprise_identity_fabric(projection_root)

    binding_root = tmp_path / "binding"
    export_enterprise_identity_fabric(
        binding_root, public=reference.public, evaluator=reference.evaluator
    )
    checkpoint = reference.public.checkpoints[0]
    changed_kernel = checkpoint.directory_rbac_kernel.model_copy(
        update={"identity_access_universe_digest": synthetic_digest(b"wrong\n")}
    )
    changed_checkpoint = checkpoint.model_copy(
        update={"directory_rbac_kernel": changed_kernel}
    )
    checkpoint_reference = reference.public.benchmark.checkpoints[0].model_copy(
        update={
            "checkpoint_input_digest": synthetic_digest(
                canonical_json_bytes(changed_checkpoint)
            )
        }
    )
    changed_benchmark = reference.public.benchmark.model_copy(
        update={
            "checkpoints": (
                checkpoint_reference,
                reference.public.benchmark.checkpoints[1],
            )
        }
    )
    changed_public = reference.public.model_copy(
        update={
            "checkpoints": (changed_checkpoint, reference.public.checkpoints[1]),
            "benchmark": changed_benchmark,
        }
    )
    _rewrite_artifact(
        binding_root,
        visibility="public",
        name="identity-fabric-input.json",
        model=changed_public,
    )
    with pytest.raises(
        EnterpriseIdentityFabricArtifactError, match="bindings are invalid"
    ):
        load_public_enterprise_identity_fabric(binding_root)


def test_evaluator_loader_recompiles_truth_and_component_bindings(
    tmp_path: Path,
) -> None:
    reference = reference_enterprise_identity_fabric()
    binding_root = tmp_path / "component-binding"
    export_enterprise_identity_fabric(
        binding_root, public=reference.public, evaluator=reference.evaluator
    )
    checkpoint = reference.evaluator.checkpoints[0]
    changed_truth = checkpoint.directory_rbac_truth.model_copy(
        update={"identity_access_universe_digest": synthetic_digest(b"wrong\n")}
    )
    changed_checkpoint = checkpoint.model_copy(
        update={"directory_rbac_truth": changed_truth}
    )
    changed_evaluator = reference.evaluator.model_copy(
        update={
            "checkpoints": (
                changed_checkpoint,
                reference.evaluator.checkpoints[1],
            )
        }
    )
    _rewrite_artifact(
        binding_root,
        visibility="evaluator",
        name="identity-fabric-evaluator.json",
        model=changed_evaluator,
    )
    with pytest.raises(
        EnterpriseIdentityFabricArtifactError, match="bindings are invalid"
    ):
        load_evaluator_enterprise_identity_fabric(binding_root)

    truth_root = tmp_path / "truth"
    export_enterprise_identity_fabric(
        truth_root, public=reference.public, evaluator=reference.evaluator
    )
    first_label = reference.evaluator.truth.case_labels[0]
    changed_label = first_label.model_copy(update={"labels": ("changed-label",)})
    changed_pack_truth = reference.evaluator.truth.model_copy(
        update={
            "case_labels": (
                changed_label,
                *reference.evaluator.truth.case_labels[1:],
            )
        }
    )
    changed_evaluator = reference.evaluator.model_copy(
        update={"truth": changed_pack_truth}
    )
    _rewrite_artifact(
        truth_root,
        visibility="evaluator",
        name="identity-fabric-evaluator.json",
        model=changed_evaluator,
    )
    with pytest.raises(EnterpriseIdentityFabricArtifactError, match="truth differs"):
        load_evaluator_enterprise_identity_fabric(truth_root)


def test_generated_schemas_and_examples_match_reference_contracts() -> None:
    reference = reference_enterprise_identity_fabric()
    prediction = perfect_enterprise_identity_fabric_prediction(reference.evaluator)
    metrics = evaluate_enterprise_identity_fabric(
        artifacts=reference.evaluator, predictions=prediction
    )
    models = {
        "enterprise-identity-fabric-benchmark": reference.public.benchmark,
        "enterprise-identity-fabric-public-input": reference.public,
        "enterprise-identity-fabric-truth": reference.evaluator.truth,
        "enterprise-identity-fabric-evaluator": reference.evaluator,
        "enterprise-identity-fabric-prediction": prediction,
        "enterprise-identity-fabric-metrics": metrics,
    }
    for stem, model in models.items():
        schema = json.loads(
            (CONTRACT_ROOT / "schemas" / f"{stem}.schema.json").read_text()
        )
        errors = tuple(
            Draft202012Validator(schema).iter_errors(model.model_dump(mode="json"))
        )
        assert errors == ()
    examples = {
        "enterprise-identity-fabric-public-input.json": reference.public,
        "enterprise-identity-fabric-evaluator.json": reference.evaluator,
        "enterprise-identity-fabric-prediction.json": prediction,
        "enterprise-identity-fabric-metrics.json": metrics,
    }
    for name, model in examples.items():
        assert (CONTRACT_ROOT / "examples" / name).read_bytes() == canonical_json_bytes(
            model
        )
