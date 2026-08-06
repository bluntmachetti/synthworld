"""Physical visibility and canonical artifact tests for governance lineage."""

from __future__ import annotations

from pathlib import Path

import pytest

from synthworld.authority_governance import (
    EVALUATOR_AUTHORITY_GOVERNANCE_PATH,
    PUBLIC_AUTHORITY_GOVERNANCE_PATH,
    AuthorityGovernanceArtifactError,
    export_authority_governance_benchmark,
    load_evaluator_authority_governance_benchmark,
    load_public_authority_governance_benchmark,
    reference_authority_governance,
)
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.models import EnterpriseArtifactManifestV1


def test_governance_artifact_round_trip_is_canonical_and_physically_split(
    tmp_path: Path,
) -> None:
    reference = reference_authority_governance()
    root = tmp_path / "governance"
    export_authority_governance_benchmark(
        root,
        public=reference.public,
        evaluator=reference.evaluator,
    )
    assert load_public_authority_governance_benchmark(root) == reference.public
    assert load_evaluator_authority_governance_benchmark(root) == reference.evaluator
    assert (root / PUBLIC_AUTHORITY_GOVERNANCE_PATH).read_bytes() == (
        canonical_json_bytes(reference.public)
    )
    assert (root / EVALUATOR_AUTHORITY_GOVERNANCE_PATH).read_bytes() == (
        canonical_json_bytes(reference.evaluator)
    )
    assert set(item.name for item in (root / "public").iterdir()) == {
        "authority-governance-input.json",
        "manifest.json",
    }
    assert set(item.name for item in (root / "evaluator").iterdir()) == {
        "authority-governance-evaluator.json",
        "manifest.json",
    }


def test_export_rejects_existing_root_and_invalid_evaluator(tmp_path: Path) -> None:
    reference = reference_authority_governance()
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(AuthorityGovernanceArtifactError, match="root exists"):
        export_authority_governance_benchmark(
            existing,
            public=reference.public,
            evaluator=reference.evaluator,
        )
    invalid = reference.evaluator.model_copy(
        update={
            "public_digest": reference.evaluator.public_digest.model_copy(
                update={"value": "0" * 64}
            )
        }
    )
    with pytest.raises(AuthorityGovernanceArtifactError, match="artifacts are invalid"):
        export_authority_governance_benchmark(
            tmp_path / "invalid",
            public=reference.public,
            evaluator=invalid,
        )


def test_loader_rejects_inventory_directory_and_nonregular_entries(
    tmp_path: Path,
) -> None:
    with pytest.raises(AuthorityGovernanceArtifactError, match="unreadable"):
        load_public_authority_governance_benchmark(tmp_path / "missing")

    fake = tmp_path / "fake"
    fake.mkdir()
    (fake / "public").write_bytes(b"not a directory")
    with pytest.raises(AuthorityGovernanceArtifactError, match="not a real directory"):
        load_public_authority_governance_benchmark(fake)

    root = _export(tmp_path / "extra")
    (root / "public" / "unexpected.json").write_bytes(b"{}")
    with pytest.raises(AuthorityGovernanceArtifactError, match="inventory differs"):
        load_public_authority_governance_benchmark(root)

    root = _export(tmp_path / "nonregular")
    artifact = root / PUBLIC_AUTHORITY_GOVERNANCE_PATH
    artifact.unlink()
    artifact.mkdir()
    with pytest.raises(AuthorityGovernanceArtifactError, match="non-regular"):
        load_public_authority_governance_benchmark(root)


def test_loader_rejects_manifest_visibility_count_and_binding(tmp_path: Path) -> None:
    root = _export(tmp_path / "visibility")
    manifest_path = root / "public" / "manifest.json"
    manifest = EnterpriseArtifactManifestV1.model_validate_json(
        manifest_path.read_bytes()
    )
    manifest_path.write_bytes(
        canonical_json_bytes(manifest.model_copy(update={"visibility": "evaluator"}))
    )
    with pytest.raises(AuthorityGovernanceArtifactError, match="visibility differs"):
        load_public_authority_governance_benchmark(root)

    root = _export(tmp_path / "count")
    manifest_path = root / "public" / "manifest.json"
    manifest = EnterpriseArtifactManifestV1.model_validate_json(
        manifest_path.read_bytes()
    )
    manifest_path.write_bytes(
        canonical_json_bytes(manifest.model_copy(update={"artifacts": ()}))
    )
    with pytest.raises(AuthorityGovernanceArtifactError, match="declare one"):
        load_public_authority_governance_benchmark(root)

    root = _export(tmp_path / "binding")
    manifest_path = root / "public" / "manifest.json"
    manifest = EnterpriseArtifactManifestV1.model_validate_json(
        manifest_path.read_bytes()
    )
    descriptor = manifest.artifacts[0].model_copy(update={"byte_size": 0})
    manifest_path.write_bytes(
        canonical_json_bytes(manifest.model_copy(update={"artifacts": (descriptor,)}))
    )
    with pytest.raises(AuthorityGovernanceArtifactError, match="binding differs"):
        load_public_authority_governance_benchmark(root)


def test_loader_rejects_invalid_and_noncanonical_json(tmp_path: Path) -> None:
    root = _export(tmp_path / "invalid-json")
    (root / PUBLIC_AUTHORITY_GOVERNANCE_PATH).write_bytes(b"{")
    with pytest.raises(AuthorityGovernanceArtifactError, match="artifact is invalid"):
        load_public_authority_governance_benchmark(root)

    root = _export(tmp_path / "noncanonical")
    artifact = root / PUBLIC_AUTHORITY_GOVERNANCE_PATH
    artifact.write_bytes(b" " + artifact.read_bytes())
    with pytest.raises(AuthorityGovernanceArtifactError, match="not canonical"):
        load_public_authority_governance_benchmark(root)


def test_loaders_reject_semantically_invalid_public_and_evaluator(
    tmp_path: Path,
) -> None:
    reference = reference_authority_governance()
    root = _export(tmp_path / "bad-public")
    bad_public = reference.public.model_copy(
        update={"schedule": reference.public.schedule[:-1]}
    )
    _replace_bound_artifact(
        root,
        visibility="public",
        name="authority-governance-input.json",
        payload=canonical_json_bytes(bad_public),
    )
    with pytest.raises(AuthorityGovernanceArtifactError, match="public bindings"):
        load_public_authority_governance_benchmark(root)

    root = _export(tmp_path / "bad-evaluator")
    bad_evaluator = reference.evaluator.model_copy(
        update={
            "public_digest": reference.evaluator.public_digest.model_copy(
                update={"value": "0" * 64}
            )
        }
    )
    _replace_bound_artifact(
        root,
        visibility="evaluator",
        name="authority-governance-evaluator.json",
        payload=canonical_json_bytes(bad_evaluator),
    )
    with pytest.raises(AuthorityGovernanceArtifactError, match="evaluator bindings"):
        load_evaluator_authority_governance_benchmark(root)


def _export(root: Path) -> Path:
    reference = reference_authority_governance()
    export_authority_governance_benchmark(
        root,
        public=reference.public,
        evaluator=reference.evaluator,
    )
    return root


def _replace_bound_artifact(
    root: Path,
    *,
    visibility: str,
    name: str,
    payload: bytes,
) -> None:
    artifact = root / visibility / name
    artifact.write_bytes(payload)
    manifest_path = root / visibility / "manifest.json"
    manifest = EnterpriseArtifactManifestV1.model_validate_json(
        manifest_path.read_bytes()
    )
    descriptor = manifest.artifacts[0].model_copy(
        update={
            "digest": synthetic_digest(payload),
            "byte_size": len(payload),
        }
    )
    manifest_path.write_bytes(
        canonical_json_bytes(manifest.model_copy(update={"artifacts": (descriptor,)}))
    )
