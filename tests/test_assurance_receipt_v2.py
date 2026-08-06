"""Closed-branch tests for generic marker-neutral assurance receipt v2."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from synthworld.agent_authority.reference import (
    build_reference_agent_authority_run_receipt,
    reference_systems,
)
from synthworld.assurance.ambiguity import build_reference_ambiguity_run_receipt
from synthworld.assurance.models import (
    ArtifactSerialization,
    EvaluationStatus,
    ExecutionReceipt,
    ExecutionStatus,
    TreeState,
)
from synthworld.assurance.models_v2 import (
    ArtifactDescriptorV2,
    ComponentArtifactKindV2,
    ConfigurationObservabilityV2,
    DigestV2,
    EvidenceClaimV2,
    ExecutionReceiptV2,
    ManagedServiceComponentProvenanceV2,
    ReferenceComponentProvenanceV2,
    ReplayabilityV2,
    RepositoryProvenanceV2,
    RunReceiptManifestV2,
    SelfHostedComponentProvenanceV2,
    VersionBindingV2,
    VersionObservabilityV2,
)
from synthworld.assurance.receipt import (
    EXECUTION_PATH,
    MANIFEST_PATH,
    SOURCE_PUBLIC_PATH,
    ReceiptIntegrityError,
    canonical_json_bytes,
)
from synthworld.assurance.receipt_v2 import (
    ArtifactSpecV2,
    describe_artifact_v2,
    digest_bytes_v2,
    digest_file_v2,
    parse_execution_receipt,
    validate_manifest_dispatched,
    validate_manifest_v2,
    write_manifest_last_v2,
)

_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def v2_receipt(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("receipt-v2") / "run"
    build_reference_agent_authority_run_receipt(root)
    return root


@pytest.fixture(scope="module")
def v1_receipt(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("receipt-v1") / "run"
    build_reference_ambiguity_run_receipt(root, repository_root=_ROOT)
    return root


def _copy_receipt(template: Path, destination: Path) -> Path:
    root = destination / "run"
    shutil.copytree(template, root)
    return root


def _manifest(root: Path) -> RunReceiptManifestV2:
    return RunReceiptManifestV2.model_validate_json((root / MANIFEST_PATH).read_bytes())


def _write_manifest(root: Path, manifest: RunReceiptManifestV2) -> None:
    (root / MANIFEST_PATH).write_bytes(canonical_json_bytes(manifest))


def _canonical_value(value: object) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode()


def _reindex_bytes(root: Path, relative_path: str, payload: bytes) -> None:
    (root / relative_path).write_bytes(payload)
    manifest = _manifest(root)
    artifacts = tuple(
        item.model_copy(
            update={"digest": digest_bytes_v2(payload), "byte_size": len(payload)}
        )
        if item.path == relative_path
        else item
        for item in manifest.artifacts
    )
    _write_manifest(root, manifest.model_copy(update={"artifacts": artifacts}))


def _reject(model: BaseModel, match: str, **updates: object) -> None:
    document = model.model_dump(mode="json")
    document.update(updates)
    with pytest.raises(ValidationError, match=match):
        type(model).model_validate(document)


def test_hosted_component_provenance_closes_tree_and_replayability_states() -> None:
    hosted = reference_systems()[1]
    assert isinstance(hosted, SelfHostedComponentProvenanceV2)
    _reject(hosted, "dirty hosted", tree_state=TreeState.DIRTY)
    _reject(hosted, "dirty hosted", tree_digest=DigestV2(value="1" * 64))
    _reject(hosted, "exact replayability", replayability_limitation="unexpected")
    _reject(hosted, "non-exact replayability", replayability=ReplayabilityV2.LIMITED)

    limited = hosted.model_copy(
        update={
            "replayability": ReplayabilityV2.LIMITED,
            "replayability_limitation": "host dependency is not pinned",
        }
    )
    assert type(hosted).model_validate(limited.model_dump()).replayability == "limited"
    dirty = hosted.model_copy(
        update={"tree_state": TreeState.DIRTY, "tree_digest": DigestV2(value="2" * 64)}
    )
    assert type(hosted).model_validate(dirty.model_dump()).tree_state is TreeState.DIRTY


def _managed_base() -> dict[str, object]:
    return {
        "component_id": "managed",
        "role": "policy",
        "provider": "provider",
        "product": "product",
        "configuration_observability": "not_exposed",
        "configuration_capture_limitation": "configuration is hidden",
        "version_observability": "not_exposed",
        "replayability": "not_replayable",
        "replayability_limitation": "vendor state cannot be replayed",
    }


def test_managed_service_provenance_closes_configuration_and_version_states() -> None:
    hidden = ManagedServiceComponentProvenanceV2.model_validate(_managed_base())
    _reject(
        hidden, "requires a capture limitation", configuration_capture_limitation=None
    )
    _reject(
        hidden,
        "sorted and unique",
        configuration_evidence_refs=("z", "a"),
    )
    _reject(hidden, "nonblank", observed_configuration_fields=("",))
    _reject(hidden, "not-exposed version forbids", release_identifier="release")
    _reject(
        hidden,
        "not-exposed configuration forbids",
        configuration_evidence_refs=("evidence:hidden-config",),
    )
    _reject(
        hidden,
        "not-exposed version forbids",
        version_evidence_refs=("evidence:hidden-version",),
    )

    observed_config = _managed_base() | {
        "configuration_observability": ConfigurationObservabilityV2.OBSERVED,
        "configuration_digest": DigestV2(value="3" * 64),
        "configuration_evidence_refs": ("evidence:config",),
        "configuration_capture_limitation": None,
    }
    with pytest.raises(ValidationError, match="forbids partial fields"):
        ManagedServiceComponentProvenanceV2.model_validate(
            observed_config | {"observed_configuration_fields": ("policy",)}
        )

    with pytest.raises(ValidationError, match="release or build"):
        ManagedServiceComponentProvenanceV2.model_validate(
            observed_config | {"version_observability": "observed"}
        )
    with pytest.raises(ValidationError, match="version requires evidence"):
        ManagedServiceComponentProvenanceV2.model_validate(
            observed_config
            | {
                "version_observability": "observed",
                "release_identifier": "release",
            }
        )
    observed = ManagedServiceComponentProvenanceV2.model_validate(
        observed_config
        | {
            "version_observability": VersionObservabilityV2.OBSERVED,
            "build_identifier": "build",
            "version_evidence_refs": ("evidence:version",),
        }
    )
    assert observed.build_identifier == "build"
    with pytest.raises(ValidationError):
        ManagedServiceComponentProvenanceV2.model_validate(
            _managed_base() | {"replayability": ReplayabilityV2.EXACT}
        )


def test_repository_run_artifact_and_execution_models_reject_ambiguous_states(
    v2_receipt: Path,
) -> None:
    repository = RepositoryProvenanceV2(
        name="repo",
        revision="revision",
        tree_state=TreeState.CLEAN,
    )
    _reject(repository, "dirty source tree", tree_digest=DigestV2(value="4" * 64))
    _reject(repository, "dirty source tree", tree_state=TreeState.DIRTY)
    assert (
        RepositoryProvenanceV2(
            name="repo",
            revision="revision",
            tree_state=TreeState.DIRTY,
            tree_digest=DigestV2(value="4" * 64),
        ).tree_digest
        is not None
    )

    run = _manifest(v2_receipt).run
    _reject(run, "timestamps must be UTC", started_at=datetime(2026, 8, 4))
    _reject(
        run,
        "timestamps must be UTC",
        completed_at=datetime(
            2026,
            8,
            4,
            tzinfo=timezone(timedelta(hours=1)),
        ),
    )
    _reject(run, "cannot precede", completed_at=run.started_at - timedelta(seconds=1))

    descriptor = _manifest(v2_receipt).artifacts[0]
    for path in (".", "/absolute.json", "../parent.json", "a//b.json"):
        _reject(descriptor, "canonical safe relative", path=path)
        with pytest.raises(ValidationError, match="canonical safe relative"):
            ArtifactSpecV2(
                path=path,
                role="test",
                phase=descriptor.phase,
                media_type="application/json",
                serialization=descriptor.serialization,
            )

    execution = ExecutionReceiptV2.model_validate_json(
        (v2_receipt / EXECUTION_PATH).read_bytes()
    )
    _reject(execution, "sorted and unique", systems_under_test=("z", "a"))
    _reject(execution, "nonblank", systems_under_test=("",))
    _reject(execution, "agree with the exit code", status=ExecutionStatus.FAILED)
    failed = execution.model_copy(
        update={"exit_code": 2, "status": ExecutionStatus.FAILED}
    )
    assert ExecutionReceiptV2.model_validate(failed.model_dump()).status == "failed"


def test_manifest_v2_rejects_duplicate_indexes_and_self_inventory(
    v2_receipt: Path,
) -> None:
    manifest = _manifest(v2_receipt)
    first_artifact = manifest.artifacts[0]
    first_schema = manifest.schema_versions[0]
    first_score = manifest.scoring_formula_versions[0]
    first_system = manifest.systems_under_test[0]
    for update, message in (
        ({"artifacts": (first_artifact, first_artifact)}, "artifact paths"),
        (
            {
                "artifacts": (
                    first_artifact,
                    manifest.artifacts[1].model_copy(
                        update={"role": first_artifact.role}
                    ),
                )
            },
            "artifact roles",
        ),
        ({"schema_versions": (first_schema, first_schema)}, "schema binding roles"),
    ):
        _reject(manifest, message, **update)
    _reject(
        manifest,
        "scoring binding roles",
        scoring_formula_versions=(first_score, first_score),
    )
    _reject(
        manifest,
        "system component identifiers",
        systems_under_test=(first_system, first_system),
    )
    self_descriptor = first_artifact.model_copy(update={"path": MANIFEST_PATH})
    _reject(manifest, "cannot contain its own digest", artifacts=(self_descriptor,))


def _reference_system() -> ReferenceComponentProvenanceV2:
    return ReferenceComponentProvenanceV2(
        component_id="component-reference",
        role="reference",
        name="reference implementation",
        version="1.0.0",
        artifact_kind=ComponentArtifactKindV2.SOURCE,
        artifact_digest=DigestV2(value="1" * 64),
        dependency_lock_digest=DigestV2(value="2" * 64),
        configuration_digest=DigestV2(value="3" * 64),
        tree_state=TreeState.CLEAN,
        replayability=ReplayabilityV2.EXACT,
    )


def test_manifest_v2_pairs_claims_statuses_and_scoring(v2_receipt: Path) -> None:
    manifest = _manifest(v2_receipt)

    _reject(
        manifest,
        "deployed system",
        evidence_claim=EvidenceClaimV2.LIVE_LAB_CONFORMANCE,
        systems_under_test=(_reference_system(),),
    )
    offline = manifest.model_copy(
        update={
            "evidence_claim": EvidenceClaimV2.CANONICAL_CONFORMANCE,
            "systems_under_test": (_reference_system(),),
        }
    )
    RunReceiptManifestV2.model_validate(offline.model_dump(mode="json"))
    live = manifest.model_copy(
        update={"evidence_claim": EvidenceClaimV2.LIVE_LAB_CONFORMANCE}
    )
    RunReceiptManifestV2.model_validate(live.model_dump(mode="json"))

    _reject(
        manifest,
        "failed executions are unevaluated",
        execution_status=ExecutionStatus.FAILED,
    )
    _reject(
        manifest,
        "failed executions are unevaluated",
        evaluation_status=EvaluationStatus.NOT_EVALUATED,
    )
    _reject(manifest, "must bind its scoring formulas", scoring_formula_versions=())
    _reject(
        manifest,
        "must not bind scoring formulas",
        execution_status=ExecutionStatus.FAILED,
        evaluation_status=EvaluationStatus.NOT_EVALUATED,
    )


def test_receipt_v2_digest_description_and_manifest_write_precondition(
    v2_receipt: Path,
    tmp_path: Path,
) -> None:
    source = v2_receipt / SOURCE_PUBLIC_PATH
    assert digest_file_v2(source) == digest_bytes_v2(source.read_bytes())
    descriptor = _manifest(v2_receipt).artifacts[1]
    described = describe_artifact_v2(
        v2_receipt,
        ArtifactSpecV2(
            path=descriptor.path,
            role=descriptor.role,
            phase=descriptor.phase,
            media_type=descriptor.media_type,
            serialization=descriptor.serialization,
            schema_version=descriptor.schema_version,
        ),
    )
    assert described == descriptor

    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ReceiptIntegrityError, match="exactly match"):
        write_manifest_last_v2(empty, _manifest(v2_receipt))


def test_version_dispatch_accepts_v1_and_v2_and_rejects_unknown(
    v1_receipt: Path,
    v2_receipt: Path,
    tmp_path: Path,
) -> None:
    assert validate_manifest_dispatched(v1_receipt).schema_version == "1.0.0"
    assert validate_manifest_dispatched(v2_receipt).schema_version == "2.0.0"
    v1_execution = (v1_receipt / EXECUTION_PATH).read_bytes()
    assert isinstance(parse_execution_receipt(v1_execution), ExecutionReceipt)
    v2_execution = (v2_receipt / EXECUTION_PATH).read_bytes()
    assert isinstance(parse_execution_receipt(v2_execution), ExecutionReceiptV2)

    unknown = tmp_path / "unknown"
    unknown.mkdir()
    (unknown / MANIFEST_PATH).write_bytes(b'{"schema_version":"9.9.9"}\n')
    with pytest.raises(ReceiptIntegrityError, match="unsupported run receipt"):
        validate_manifest_dispatched(unknown)
    with pytest.raises(ReceiptIntegrityError, match="unsupported execution"):
        parse_execution_receipt(b'{"schema_version":"9.9.9"}\n')


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"not-json\n", "not a JSON object"),
        (b"[]\n", "no string schema_version"),
        (b'{"schema_version":2}\n', "no string schema_version"),
        (b'{"schema_version":"2.0.0"}\n', "dispatched schema"),
    ],
)
def test_execution_dispatch_rejects_malformed_payloads(
    payload: bytes, message: str
) -> None:
    with pytest.raises(ReceiptIntegrityError, match=message):
        parse_execution_receipt(payload)


def test_execution_dispatch_rejects_noncanonical_json(v2_receipt: Path) -> None:
    execution = json.loads((v2_receipt / EXECUTION_PATH).read_bytes())
    pretty = (json.dumps(execution, indent=2) + "\n").encode()
    with pytest.raises(ReceiptIntegrityError, match="not canonical"):
        parse_execution_receipt(pretty)


def test_manifest_v2_integrity_failure_modes(
    v2_receipt: Path,
    tmp_path: Path,
) -> None:
    invalid_schema = _copy_receipt(v2_receipt, tmp_path / "schema")
    document = json.loads((invalid_schema / MANIFEST_PATH).read_bytes())
    document["schema_version"] = "9.9.9"
    (invalid_schema / MANIFEST_PATH).write_bytes(_canonical_value(document))
    with pytest.raises(ReceiptIntegrityError, match=r"schema 2\.0\.0"):
        validate_manifest_v2(invalid_schema)

    noncanonical = _copy_receipt(v2_receipt, tmp_path / "manifest-canonical")
    document = json.loads((noncanonical / MANIFEST_PATH).read_bytes())
    (noncanonical / MANIFEST_PATH).write_text(
        json.dumps(document, indent=2) + "\n", encoding="utf-8"
    )
    with pytest.raises(ReceiptIntegrityError, match=r"manifest\.json is not canonical"):
        validate_manifest_v2(noncanonical)

    extra = _copy_receipt(v2_receipt, tmp_path / "extra")
    (extra / "extra.txt").write_text("extra", encoding="utf-8")
    with pytest.raises(ReceiptIntegrityError, match="inventory differs"):
        validate_manifest_v2(extra)

    wrong_size = _copy_receipt(v2_receipt, tmp_path / "size")
    manifest = _manifest(wrong_size)
    descriptor = manifest.artifacts[0]
    _write_manifest(
        wrong_size,
        manifest.model_copy(
            update={
                "artifacts": (
                    descriptor.model_copy(
                        update={"byte_size": descriptor.byte_size + 1}
                    ),
                    *manifest.artifacts[1:],
                )
            }
        ),
    )
    with pytest.raises(ReceiptIntegrityError, match="byte size differs"):
        validate_manifest_v2(wrong_size)

    wrong_digest = _copy_receipt(v2_receipt, tmp_path / "digest")
    manifest = _manifest(wrong_digest)
    descriptor = manifest.artifacts[0]
    _write_manifest(
        wrong_digest,
        manifest.model_copy(
            update={
                "artifacts": (
                    descriptor.model_copy(update={"digest": DigestV2(value="f" * 64)}),
                    *manifest.artifacts[1:],
                )
            }
        ),
    )
    with pytest.raises(ReceiptIntegrityError, match="digest differs"):
        validate_manifest_v2(wrong_digest)

    malformed = _copy_receipt(v2_receipt, tmp_path / "malformed-json")
    _reindex_bytes(malformed, SOURCE_PUBLIC_PATH, b"\xff\n")
    with pytest.raises(ReceiptIntegrityError, match="not canonical JSON"):
        validate_manifest_v2(malformed)

    pretty_artifact = _copy_receipt(v2_receipt, tmp_path / "pretty-artifact")
    source_document = json.loads((pretty_artifact / SOURCE_PUBLIC_PATH).read_bytes())
    _reindex_bytes(
        pretty_artifact,
        SOURCE_PUBLIC_PATH,
        (json.dumps(source_document, indent=2) + "\n").encode(),
    )
    with pytest.raises(ReceiptIntegrityError, match="not canonical JSON"):
        validate_manifest_v2(pretty_artifact)


def test_raw_bytes_artifacts_are_not_parsed_as_canonical_json(
    v2_receipt: Path,
) -> None:
    manifest = _manifest(v2_receipt)
    product_output = next(
        item for item in manifest.artifacts if item.role == "product_output"
    )
    assert product_output.serialization is ArtifactSerialization.RAW_BYTES
    assert (
        validate_manifest_v2(v2_receipt).evaluation_status is EvaluationStatus.EVALUATED
    )


def test_artifact_descriptor_constructor_is_strict(v2_receipt: Path) -> None:
    descriptor = _manifest(v2_receipt).artifacts[0]
    with pytest.raises(ValidationError):
        ArtifactDescriptorV2.model_validate(
            descriptor.model_dump(mode="json") | {"synthetic": True}
        )
    with pytest.raises(ValidationError):
        VersionBindingV2(role="", version="1")
    assert isinstance(_manifest(v2_receipt), RunReceiptManifestV2)
