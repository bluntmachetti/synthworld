"""Adversarial tests for staged, consumer-neutral assurance receipts."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from synthworld.ambiguity import PairDisposition, PublicAmbiguityTask
from synthworld.ambiguity_metrics import AmbiguityDispositionMetrics
from synthworld.ambiguity_partition import AmbiguityMembershipMetrics
from synthworld.ambiguity_serialization import (
    DispositionTruth,
    MembershipTruth,
    load_golden_ambiguity_disposition_truth,
    load_golden_ambiguity_membership_truth,
    load_golden_ambiguity_public_task,
)
from synthworld.assurance import ambiguity as ambiguity_receipt
from synthworld.assurance import reference_product
from synthworld.assurance.ambiguity import (
    DISPOSITION_EVALUATION_PATH,
    DISPOSITION_TRUTH_PATH,
    MEMBERSHIP_EVALUATION_PATH,
    MEMBERSHIP_TRUTH_PATH,
    SUBMISSION_CLUSTERS_PATH,
    SUBMISSION_PAIRS_PATH,
    AmbiguityPairSubmission,
    AmbiguityRunMetadata,
    build_ambiguity_run_receipt,
    build_reference_ambiguity_run_receipt,
    canonicalize_partition,
    validate_ambiguity_run_receipt,
)
from synthworld.assurance.models import (
    AdapterProvenance,
    ArtifactDescriptor,
    ArtifactPhase,
    ArtifactSerialization,
    ConfigurationEntry,
    Digest,
    EvaluationStatus,
    EvidenceClaim,
    ExecutionReceipt,
    ExecutionStatus,
    RepositoryProvenance,
    RunReceiptManifest,
    SeedPopulation,
    SystemUnderTestProvenance,
    TreeState,
    VersionBinding,
)
from synthworld.assurance.receipt import (
    EXECUTION_PATH,
    MANIFEST_PATH,
    PRODUCT_INPUT_PATH,
    PRODUCT_OUTPUT_PATH,
    SOURCE_PUBLIC_PATH,
    ArtifactSpec,
    ProductStageError,
    ReceiptIntegrityError,
    canonical_json_bytes,
    capture_repository_provenance,
    describe_artifact,
    digest_bytes,
    run_product_stage,
    validate_manifest,
    write_manifest_last,
)
from synthworld.evaluation import EntityResolutionPrediction

_ROOT = Path(__file__).resolve().parents[1]
_ZERO_DIGEST = Digest(value="0" * 64)


@pytest.fixture(scope="session")
def receipt_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("reference-receipt") / "run"
    build_reference_ambiguity_run_receipt(root, repository_root=_ROOT)
    return root


def _copy_receipt(template: Path, destination: Path) -> Path:
    root = destination / "run"
    shutil.copytree(template, root)
    return root


def _manifest(root: Path) -> RunReceiptManifest:
    return RunReceiptManifest.model_validate_json((root / MANIFEST_PATH).read_bytes())


def _write_manifest(root: Path, manifest: RunReceiptManifest) -> None:
    (root / MANIFEST_PATH).write_bytes(canonical_json_bytes(manifest))


def _replace_manifest(root: Path, **updates: object) -> None:
    manifest = _manifest(root).model_copy(update=updates)
    _write_manifest(root, manifest)


def _reindex(root: Path, relative_path: str) -> None:
    manifest = _manifest(root)
    payload = (root / relative_path).read_bytes()
    artifacts = tuple(
        item.model_copy(
            update={"digest": digest_bytes(payload), "byte_size": len(payload)}
        )
        if item.path == relative_path
        else item
        for item in manifest.artifacts
    )
    _write_manifest(root, manifest.model_copy(update={"artifacts": artifacts}))


def _write_model_and_reindex(root: Path, path: str, model: object) -> None:
    assert hasattr(model, "model_dump")
    (root / path).write_bytes(canonical_json_bytes(model))  # type: ignore[arg-type]
    _reindex(root, path)


def _fixed_metadata(public: PublicAmbiguityTask) -> AmbiguityRunMetadata:
    repository = RepositoryProvenance(
        name="SynthWorld",
        revision="test-revision",
        tree_state=TreeState.CLEAN,
    )
    adapter = AdapterProvenance(
        name="reference-test-adaptation",
        version="1.0.0",
        source_digest=_ZERO_DIGEST,
        boundary=reference_product.REFERENCE_BOUNDARY,
    )
    system = SystemUnderTestProvenance(
        name="reference test resolver",
        revision="test-revision",
        package_or_executable_digest=_ZERO_DIGEST,
        dependency_lock_digest=_ZERO_DIGEST,
        tree_state=TreeState.CLEAN,
        replayability="included in this test checkout",
    )
    return AmbiguityRunMetadata(
        product_input_schema_version=reference_product.REFERENCE_PRODUCT_SCHEMA_VERSION,
        product_output_schema_version=reference_product.REFERENCE_PRODUCT_SCHEMA_VERSION,
        callable_identifier=reference_product.REFERENCE_CALLABLE,
        generator_configuration=(
            ConfigurationEntry(name="configuration", value="test defaults"),
        ),
        synthworld=repository,
        adapter=adapter,
        system_under_test=system,
        seed_population=SeedPopulation(
            seeds=(public.corpus.seed,),
            description="one deterministic test seed",
        ),
        evidence_claim=EvidenceClaim.CANONICAL_CONFORMANCE,
    )


def _build_with_runner(
    root: Path,
    runner: Callable[[Path, Path], int],
    *,
    membership_loader: Callable[[], MembershipTruth] = (
        load_golden_ambiguity_membership_truth
    ),
    disposition_loader: Callable[[], DispositionTruth] = (
        load_golden_ambiguity_disposition_truth
    ),
) -> RunReceiptManifest:
    public = load_golden_ambiguity_public_task()
    return build_ambiguity_run_receipt(
        root,
        source_public=canonical_json_bytes(public),
        membership_truth_loader=membership_loader,
        disposition_truth_loader=disposition_loader,
        adapter=reference_product.adapt_public_ambiguity,
        runner=runner,
        normalizer=reference_product.normalize_reference_output,
        metadata=_fixed_metadata(public),
    )


def test_reference_receipt_is_complete_valid_and_deterministic(
    receipt_template: Path,
    tmp_path: Path,
) -> None:
    second = tmp_path / "second"
    manifest = build_reference_ambiguity_run_receipt(second, repository_root=_ROOT)

    first_bytes = {
        path.relative_to(receipt_template).as_posix(): path.read_bytes()
        for path in receipt_template.rglob("*")
        if path.is_file()
    }
    second_bytes = {
        path.relative_to(second).as_posix(): path.read_bytes()
        for path in second.rglob("*")
        if path.is_file()
    }
    assert first_bytes == second_bytes
    assert manifest == validate_ambiguity_run_receipt(
        second,
        adapter=reference_product.adapt_public_ambiguity,
        normalizer=reference_product.normalize_reference_output,
    )
    assert set(first_bytes) == {
        SOURCE_PUBLIC_PATH,
        PRODUCT_INPUT_PATH,
        PRODUCT_OUTPUT_PATH,
        EXECUTION_PATH,
        SUBMISSION_CLUSTERS_PATH,
        SUBMISSION_PAIRS_PATH,
        MEMBERSHIP_TRUTH_PATH,
        DISPOSITION_TRUTH_PATH,
        MEMBERSHIP_EVALUATION_PATH,
        DISPOSITION_EVALUATION_PATH,
        MANIFEST_PATH,
    }
    assert MANIFEST_PATH not in {item.path for item in manifest.artifacts}
    assert manifest.evidence_claim is EvidenceClaim.CANONICAL_CONFORMANCE
    assert manifest.seed_population.seeds == (manifest.seed,)


def test_product_stage_sees_only_input_and_output_and_truth_loads_late(
    tmp_path: Path,
) -> None:
    root = tmp_path / "run"
    events: list[str] = []
    raw_output: bytes | None = None

    def runner(input_path: Path, output_path: Path) -> int:
        nonlocal raw_output
        events.append("product")
        assert input_path.name == PRODUCT_INPUT_PATH
        assert output_path.name == PRODUCT_OUTPUT_PATH
        assert {path.name for path in root.iterdir() if path.is_file()} == {
            SOURCE_PUBLIC_PATH,
            PRODUCT_INPUT_PATH,
        }
        assert not (root / "truth").exists()
        assert not (root / "evaluation").exists()
        input_data = reference_product.ReferenceResolverInput.model_validate_json(
            input_path.read_bytes()
        )
        result = reference_product.resolve_reference(input_data)
        raw_output = b"  " + canonical_json_bytes(result).rstrip(b"\n")
        output_path.write_bytes(raw_output)
        return 0

    def memberships() -> MembershipTruth:
        events.append("memberships")
        assert (root / SUBMISSION_CLUSTERS_PATH).is_file()
        assert (root / SUBMISSION_PAIRS_PATH).is_file()
        assert not (root / MEMBERSHIP_TRUTH_PATH).exists()
        assert not (root / DISPOSITION_TRUTH_PATH).exists()
        return load_golden_ambiguity_membership_truth()

    def dispositions() -> DispositionTruth:
        events.append("dispositions")
        assert (root / SUBMISSION_CLUSTERS_PATH).is_file()
        assert (root / SUBMISSION_PAIRS_PATH).is_file()
        assert not (root / MEMBERSHIP_TRUTH_PATH).exists()
        assert not (root / DISPOSITION_TRUTH_PATH).exists()
        return load_golden_ambiguity_disposition_truth()

    _build_with_runner(
        root,
        runner,
        membership_loader=memberships,
        disposition_loader=dispositions,
    )

    assert events == ["product", "memberships", "dispositions"]
    assert (root / PRODUCT_OUTPUT_PATH).read_bytes() == raw_output


def test_noncanonical_source_is_rejected_before_creating_a_run(tmp_path: Path) -> None:
    public = load_golden_ambiguity_public_task()
    with pytest.raises(ReceiptIntegrityError, match="source public"):
        build_ambiguity_run_receipt(
            tmp_path / "run",
            source_public=public.model_dump_json(indent=2).encode(),
            membership_truth_loader=load_golden_ambiguity_membership_truth,
            disposition_truth_loader=load_golden_ambiguity_disposition_truth,
            adapter=reference_product.adapt_public_ambiguity,
            runner=reference_product.run_reference_product,
            normalizer=reference_product.normalize_reference_output,
            metadata=_fixed_metadata(public),
        )
    assert not (tmp_path / "run").exists()


def test_failed_product_is_recorded_but_never_evaluated(tmp_path: Path) -> None:
    truth_loaded = False

    def failed(_input_path: Path, output_path: Path) -> int:
        output_path.write_bytes(b"failure log\n")
        return 7

    def truth() -> MembershipTruth:
        nonlocal truth_loaded
        truth_loaded = True
        return load_golden_ambiguity_membership_truth()

    with pytest.raises(ReceiptIntegrityError, match="failed product"):
        _build_with_runner(tmp_path / "run", failed, membership_loader=truth)

    execution = ExecutionReceipt.model_validate_json(
        (tmp_path / "run" / EXECUTION_PATH).read_bytes()
    )
    assert execution.exit_code == 7
    assert execution.status is ExecutionStatus.FAILED
    assert not truth_loaded


@pytest.mark.parametrize(
    "failure",
    [
        "malformed_json",
        "empty_partition",
        "empty_cluster",
        "missing_record",
        "unknown_record",
        "duplicate_in_cluster",
        "multiply_clustered",
    ],
)
def test_malformed_raw_partitions_abort_before_truth(
    tmp_path: Path,
    failure: str,
) -> None:
    root = tmp_path / failure
    truth_calls = 0

    def runner(input_path: Path, output_path: Path) -> int:
        input_data = reference_product.ReferenceResolverInput.model_validate_json(
            input_path.read_bytes()
        )
        ids = tuple(record.id for record in input_data.records)
        if failure == "malformed_json":
            output_path.write_bytes(b"not-json")
        elif failure == "empty_partition":
            output_path.write_bytes(
                canonical_json_bytes(
                    reference_product.ReferenceResolverOutput(clusters=())
                )
            )
        elif failure == "empty_cluster":
            output_path.write_bytes(
                canonical_json_bytes(
                    reference_product.ReferenceResolverOutput(
                        clusters=((), *tuple((item,) for item in ids))
                    )
                )
            )
        elif failure == "missing_record":
            output_path.write_bytes(
                canonical_json_bytes(
                    reference_product.ReferenceResolverOutput(
                        clusters=tuple((item,) for item in ids[:-1])
                    )
                )
            )
        elif failure == "unknown_record":
            output_path.write_bytes(
                canonical_json_bytes(
                    reference_product.ReferenceResolverOutput(
                        clusters=(*tuple((item,) for item in ids), (UUID(int=0),))
                    )
                )
            )
        elif failure == "duplicate_in_cluster":
            output_path.write_bytes(
                canonical_json_bytes(
                    reference_product.ReferenceResolverOutput(
                        clusters=(
                            (ids[0], ids[0]),
                            *tuple((item,) for item in ids[1:]),
                        )
                    )
                )
            )
        else:
            output_path.write_bytes(
                canonical_json_bytes(
                    reference_product.ReferenceResolverOutput(
                        clusters=(*tuple((item,) for item in ids), (ids[0],))
                    )
                )
            )
        return 0

    def memberships() -> MembershipTruth:
        nonlocal truth_calls
        truth_calls += 1
        return load_golden_ambiguity_membership_truth()

    with pytest.raises(ValueError):
        _build_with_runner(root, runner, membership_loader=memberships)
    assert truth_calls == 0
    assert not (root / SUBMISSION_CLUSTERS_PATH).exists()
    assert not (root / MEMBERSHIP_TRUTH_PATH).exists()


def test_product_stage_refuses_existing_root_and_missing_output(tmp_path: Path) -> None:
    provenance = _fixed_metadata(load_golden_ambiguity_public_task()).adapter
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(ProductStageError, match="must not already exist"):
        run_product_stage(
            existing,
            source_public=b"{}\n",
            adapter=lambda source: source,
            runner=lambda _input, _output: 0,
            adapter_provenance=provenance,
            callable_identifier="test.callable",
        )

    with pytest.raises(ProductStageError, match="did not create"):
        run_product_stage(
            tmp_path / "missing-output",
            source_public=b"{}\n",
            adapter=lambda source: source,
            runner=lambda _input, _output: 0,
            adapter_provenance=provenance,
            callable_identifier="test.callable",
        )


def test_reference_product_transitively_clusters_strong_identifiers() -> None:
    public = load_golden_ambiguity_public_task()
    records = public.corpus.identity_records[:4]
    shared = next(
        attribute
        for record in records
        for attribute in record.attributes
        if attribute.kind.value in {"email", "phone", "username"}
    )
    first_three = tuple(
        record.model_copy(update={"attributes": (shared,)}) for record in records[:3]
    )
    weak = next(
        attribute
        for attribute in records[3].attributes
        if attribute.kind.value not in {"email", "phone", "username"}
    )
    fourth = records[3].model_copy(update={"attributes": (weak,)})
    product_input = reference_product.ReferenceResolverInput(
        records=(*first_three, fourth)
    )

    output = reference_product.resolve_reference(product_input)

    assert sorted(map(len, output.clusters)) == [1, 3]
    normalized = reference_product.normalize_reference_output(
        canonical_json_bytes(output), public
    )
    assert normalized.clusters == output.clusters
    adapted = reference_product.ReferenceResolverInput.model_validate_json(
        reference_product.adapt_public_ambiguity(canonical_json_bytes(public))
    )
    assert adapted.records == public.corpus.identity_records


def test_partition_canonicalization_is_order_independent() -> None:
    public = load_golden_ambiguity_public_task()
    ids = tuple(record.id for record in public.corpus.identity_records[:3])
    prediction = EntityResolutionPrediction(clusters=((ids[2],), (ids[1], ids[0])))
    canonical = canonicalize_partition(prediction)
    assert canonical.clusters == (
        tuple(sorted(ids[:2], key=lambda item: item.int)),
        (ids[2],),
    ) or canonical.clusters == (
        (ids[2],),
        tuple(sorted(ids[:2], key=lambda item: item.int)),
    )
    assert canonical == canonicalize_partition(canonical)


def test_repository_provenance_binds_clean_and_dirty_trees(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "--quiet"],  # noqa: S607 - fixed local Git setup
        cwd=repo,
        check=True,
    )
    tracked = repo / "tracked.txt"
    tracked.write_text("one\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "tracked.txt"],  # noqa: S607 - fixed local Git setup
        cwd=repo,
        check=True,
    )
    subprocess.run(
        [  # noqa: S607 - fixed local Git setup
            "git",
            "-c",
            "user.name=SynthWorld Tests",
            "-c",
            "user.email=tests@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "fixture",
        ],
        cwd=repo,
        check=True,
    )

    clean = capture_repository_provenance(repo, name="fixture")
    assert clean.tree_state is TreeState.CLEAN
    assert clean.tree_digest is None

    tracked.write_text("two\n", encoding="utf-8")
    (repo / "untracked.txt").write_text("three\n", encoding="utf-8")
    dirty = capture_repository_provenance(repo, name="fixture")
    repeated = capture_repository_provenance(repo, name="fixture")
    assert dirty.tree_state is TreeState.DIRTY
    assert dirty.tree_digest == repeated.tree_digest

    (repo / "untracked.txt").write_text("changed\n", encoding="utf-8")
    changed = capture_repository_provenance(repo, name="fixture")
    assert changed.tree_digest != dirty.tree_digest


@pytest.mark.parametrize("path", ["/absolute.json", "a/../b.json", "a//b.json"])
def test_artifact_paths_must_be_safe_and_canonical(path: str) -> None:
    with pytest.raises(ValidationError, match="canonical safe relative"):
        ArtifactDescriptor(
            path=path,
            role="test",
            phase=ArtifactPhase.PRODUCT,
            media_type="application/json",
            serialization=ArtifactSerialization.CANONICAL_JSON_V1,
            digest=_ZERO_DIGEST,
            byte_size=0,
        )


def test_provenance_and_execution_models_reject_inconsistent_states() -> None:
    with pytest.raises(ValidationError, match="only a dirty source"):
        RepositoryProvenance(
            name="repo",
            revision="revision",
            tree_state=TreeState.DIRTY,
        )
    with pytest.raises(ValidationError, match="only a dirty source"):
        RepositoryProvenance(
            name="repo",
            revision="revision",
            tree_state=TreeState.CLEAN,
            tree_digest=_ZERO_DIGEST,
        )
    with pytest.raises(ValidationError, match="only a dirty system"):
        SystemUnderTestProvenance(
            name="system",
            revision="revision",
            package_or_executable_digest=_ZERO_DIGEST,
            dependency_lock_digest=_ZERO_DIGEST,
            tree_state=TreeState.DIRTY,
            replayability="test fixture",
        )
    with pytest.raises(ValidationError, match="only a dirty system"):
        SystemUnderTestProvenance(
            name="system",
            revision="revision",
            package_or_executable_digest=_ZERO_DIGEST,
            dependency_lock_digest=_ZERO_DIGEST,
            tree_state=TreeState.UNKNOWN,
            tree_digest=_ZERO_DIGEST,
            replayability="test fixture",
        )
    with pytest.raises(ValidationError, match="must agree"):
        ExecutionReceipt(
            boundary="boundary",
            callable_identifier="callable",
            adapter_name="adapter",
            adapter_version="1",
            adapter_source_digest=_ZERO_DIGEST,
            source_public_digest=_ZERO_DIGEST,
            product_input_digest=_ZERO_DIGEST,
            product_output_digest=_ZERO_DIGEST,
            exit_code=0,
            status=ExecutionStatus.FAILED,
        )
    with pytest.raises(ValidationError, match="must agree"):
        ExecutionReceipt(
            boundary="boundary",
            callable_identifier="callable",
            adapter_name="adapter",
            adapter_version="1",
            adapter_source_digest=_ZERO_DIGEST,
            source_public_digest=_ZERO_DIGEST,
            product_input_digest=_ZERO_DIGEST,
            product_output_digest=_ZERO_DIGEST,
            exit_code=1,
            status=ExecutionStatus.SUCCEEDED,
        )
    assert (
        ExecutionReceipt(
            boundary="boundary",
            callable_identifier="callable",
            adapter_name="adapter",
            adapter_version="1",
            adapter_source_digest=_ZERO_DIGEST,
            source_public_digest=_ZERO_DIGEST,
            product_input_digest=_ZERO_DIGEST,
            product_output_digest=_ZERO_DIGEST,
            exit_code=1,
            status=ExecutionStatus.FAILED,
        ).status
        is ExecutionStatus.FAILED
    )


def test_seed_population_and_manifest_index_are_injective(
    receipt_template: Path,
) -> None:
    with pytest.raises(ValidationError, match="must not contain duplicates"):
        SeedPopulation(seeds=(1, 1), description="duplicates")

    manifest = _manifest(receipt_template)

    def rejected(**updates: object) -> None:
        candidate = manifest.model_copy(update=updates)
        with pytest.raises(ValidationError):
            RunReceiptManifest.model_validate(candidate.model_dump(mode="json"))

    rejected(artifacts=(*manifest.artifacts, manifest.artifacts[0]))
    duplicate_role = manifest.artifacts[1].model_copy(
        update={"role": manifest.artifacts[0].role}
    )
    rejected(artifacts=(manifest.artifacts[0], duplicate_role, *manifest.artifacts[2:]))
    self_digest = manifest.artifacts[0].model_copy(update={"path": MANIFEST_PATH})
    rejected(artifacts=(self_digest, *manifest.artifacts[1:]))
    rejected(schema_versions=(*manifest.schema_versions, manifest.schema_versions[0]))
    rejected(
        scoring_formula_versions=(
            *manifest.scoring_formula_versions,
            manifest.scoring_formula_versions[0],
        )
    )
    rejected(
        seed=manifest.seed + 1,
        seed_population=SeedPopulation(
            seeds=(manifest.seed,), description="does not contain the run seed"
        ),
    )


def test_write_manifest_requires_an_exact_pre_manifest_inventory(
    tmp_path: Path,
    receipt_template: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "artifact.json").write_bytes(b"{}\n")
    template = _manifest(receipt_template)
    spec = ArtifactSpec(
        path="artifact.json",
        role="artifact",
        phase=ArtifactPhase.PRODUCT,
        media_type="application/json",
        serialization=ArtifactSerialization.CANONICAL_JSON_V1,
        schema_version="1.0.0",
    )
    descriptor = describe_artifact(root, spec)
    manifest = template.model_copy(update={"artifacts": (descriptor,)})
    write_manifest_last(root, manifest)
    assert validate_manifest(root).artifacts == (descriptor,)

    mismatch = tmp_path / "mismatch"
    mismatch.mkdir()
    (mismatch / "other.json").write_bytes(b"{}\n")
    with pytest.raises(ReceiptIntegrityError, match="exactly match"):
        write_manifest_last(mismatch, manifest)


def test_generic_manifest_rejects_schema_canonicality_and_inventory_errors(
    receipt_template: Path,
    tmp_path: Path,
) -> None:
    invalid_schema = _copy_receipt(receipt_template, tmp_path / "schema")
    (invalid_schema / MANIFEST_PATH).write_bytes(b"{}\n")
    with pytest.raises(ReceiptIntegrityError, match="does not match its schema"):
        validate_manifest(invalid_schema)

    noncanonical = _copy_receipt(receipt_template, tmp_path / "manifest-format")
    manifest_value = json.loads((noncanonical / MANIFEST_PATH).read_text())
    (noncanonical / MANIFEST_PATH).write_text(
        json.dumps(manifest_value, indent=2), encoding="utf-8"
    )
    with pytest.raises(ReceiptIntegrityError, match=r"manifest\.json is not canonical"):
        validate_manifest(noncanonical)

    extra = _copy_receipt(receipt_template, tmp_path / "extra")
    (extra / "undeclared.txt").write_text("extra", encoding="utf-8")
    with pytest.raises(ReceiptIntegrityError, match="inventory differs"):
        validate_manifest(extra)

    missing = _copy_receipt(receipt_template, tmp_path / "missing")
    (missing / SOURCE_PUBLIC_PATH).unlink()
    with pytest.raises(ReceiptIntegrityError, match="inventory differs"):
        validate_manifest(missing)


def test_generic_manifest_rejects_size_digest_and_json_mutations(
    receipt_template: Path,
    tmp_path: Path,
) -> None:
    wrong_size = _copy_receipt(receipt_template, tmp_path / "size")
    manifest = _manifest(wrong_size)
    first = manifest.artifacts[0]
    changed = first.model_copy(update={"byte_size": first.byte_size + 1})
    _write_manifest(
        wrong_size,
        manifest.model_copy(update={"artifacts": (changed, *manifest.artifacts[1:])}),
    )
    with pytest.raises(ReceiptIntegrityError, match="byte size differs"):
        validate_manifest(wrong_size)

    stale_digest = _copy_receipt(receipt_template, tmp_path / "digest")
    path = stale_digest / SOURCE_PUBLIC_PATH
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ReceiptIntegrityError, match="byte size differs"):
        validate_manifest(stale_digest)

    same_size_bad_digest = _copy_receipt(receipt_template, tmp_path / "digest-only")
    path = same_size_bad_digest / SOURCE_PUBLIC_PATH
    payload = bytearray(path.read_bytes())
    payload[0] = ord("[")
    path.write_bytes(payload)
    with pytest.raises(ReceiptIntegrityError, match="digest differs"):
        validate_manifest(same_size_bad_digest)

    malformed_json = _copy_receipt(receipt_template, tmp_path / "malformed-json")
    (malformed_json / SOURCE_PUBLIC_PATH).write_bytes(b"{")
    _reindex(malformed_json, SOURCE_PUBLIC_PATH)
    with pytest.raises(ReceiptIntegrityError, match="not canonical JSON"):
        validate_manifest(malformed_json)

    pretty_json = _copy_receipt(receipt_template, tmp_path / "pretty-json")
    source = json.loads((pretty_json / SOURCE_PUBLIC_PATH).read_text())
    (pretty_json / SOURCE_PUBLIC_PATH).write_text(
        json.dumps(source, indent=2) + "\n", encoding="utf-8"
    )
    _reindex(pretty_json, SOURCE_PUBLIC_PATH)
    with pytest.raises(ReceiptIntegrityError, match="not canonical JSON"):
        validate_manifest(pretty_json)


def test_typed_reader_rejects_invalid_and_noncanonical_models(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_bytes(b"{}\n")
    with pytest.raises(ReceiptIntegrityError, match="declared schema"):
        ambiguity_receipt._read_model(tmp_path, invalid.name, PublicAmbiguityTask)

    public = load_golden_ambiguity_public_task()
    noncanonical = tmp_path / "noncanonical.json"
    noncanonical.write_text(public.model_dump_json(indent=2), encoding="utf-8")
    with pytest.raises(ReceiptIntegrityError, match="not canonical for"):
        ambiguity_receipt._read_model(tmp_path, noncanonical.name, PublicAmbiguityTask)


def test_receipt_rejects_manifest_role_schema_and_scoring_mismatches(
    receipt_template: Path,
    tmp_path: Path,
) -> None:
    role = _copy_receipt(receipt_template, tmp_path / "role")
    manifest = _manifest(role)
    artifact = manifest.artifacts[0].model_copy(update={"role": "wrong_role"})
    _write_manifest(
        role,
        manifest.model_copy(update={"artifacts": (artifact, *manifest.artifacts[1:])}),
    )
    with pytest.raises(ReceiptIntegrityError, match="roles or paths"):
        validate_ambiguity_run_receipt(
            role,
            adapter=reference_product.adapt_public_ambiguity,
            normalizer=reference_product.normalize_reference_output,
        )

    schema = _copy_receipt(receipt_template, tmp_path / "schema-binding")
    manifest = _manifest(schema)
    binding = manifest.schema_versions[0].model_copy(update={"version": "9.9.9"})
    _replace_manifest(schema, schema_versions=(binding, *manifest.schema_versions[1:]))
    with pytest.raises(ReceiptIntegrityError, match="schema bindings"):
        validate_ambiguity_run_receipt(
            schema,
            adapter=reference_product.adapt_public_ambiguity,
            normalizer=reference_product.normalize_reference_output,
        )

    scoring = _copy_receipt(receipt_template, tmp_path / "scoring-binding")
    manifest = _manifest(scoring)
    binding = VersionBinding(role="ambiguity_membership", version="9.9.9")
    _replace_manifest(
        scoring,
        scoring_formula_versions=(binding, manifest.scoring_formula_versions[1]),
    )
    with pytest.raises(ReceiptIntegrityError, match="scoring formula"):
        validate_ambiguity_run_receipt(
            scoring,
            adapter=reference_product.adapt_public_ambiguity,
            normalizer=reference_product.normalize_reference_output,
        )


def test_receipt_rejects_execution_provenance_and_digest_mismatches(
    receipt_template: Path,
    tmp_path: Path,
) -> None:
    provenance = _copy_receipt(receipt_template, tmp_path / "provenance")
    execution = ExecutionReceipt.model_validate_json(
        (provenance / EXECUTION_PATH).read_bytes()
    ).model_copy(update={"boundary": "different.boundary"})
    _write_model_and_reindex(provenance, EXECUTION_PATH, execution)
    with pytest.raises(ReceiptIntegrityError, match="provenance differs"):
        validate_ambiguity_run_receipt(
            provenance,
            adapter=reference_product.adapt_public_ambiguity,
            normalizer=reference_product.normalize_reference_output,
        )

    digest = _copy_receipt(receipt_template, tmp_path / "execution-digest")
    execution = ExecutionReceipt.model_validate_json(
        (digest / EXECUTION_PATH).read_bytes()
    ).model_copy(update={"source_public_digest": _ZERO_DIGEST})
    _write_model_and_reindex(digest, EXECUTION_PATH, execution)
    with pytest.raises(ReceiptIntegrityError, match="artifact digests differ"):
        validate_ambiguity_run_receipt(
            digest,
            adapter=reference_product.adapt_public_ambiguity,
            normalizer=reference_product.normalize_reference_output,
        )


def test_receipt_rejects_status_seed_and_benchmark_mismatches(
    receipt_template: Path,
    tmp_path: Path,
) -> None:
    status = _copy_receipt(receipt_template, tmp_path / "status")
    _replace_manifest(status, evaluation_status=EvaluationStatus.NOT_EVALUATED)
    with pytest.raises(ReceiptIntegrityError, match="must be evaluated"):
        validate_ambiguity_run_receipt(
            status,
            adapter=reference_product.adapt_public_ambiguity,
            normalizer=reference_product.normalize_reference_output,
        )

    seed = _copy_receipt(receipt_template, tmp_path / "seed")
    manifest = _manifest(seed)
    wrong_seed = manifest.seed + 1
    _replace_manifest(
        seed,
        seed=wrong_seed,
        seed_population=SeedPopulation(
            seeds=(manifest.seed, wrong_seed), description="mutation fixture"
        ),
    )
    with pytest.raises(ReceiptIntegrityError, match="seed differs"):
        validate_ambiguity_run_receipt(
            seed,
            adapter=reference_product.adapt_public_ambiguity,
            normalizer=reference_product.normalize_reference_output,
        )

    version = _copy_receipt(receipt_template, tmp_path / "version")
    _replace_manifest(version, benchmark_version="9.9.9")
    with pytest.raises(ReceiptIntegrityError, match="benchmark version"):
        validate_ambiguity_run_receipt(
            version,
            adapter=reference_product.adapt_public_ambiguity,
            normalizer=reference_product.normalize_reference_output,
        )


def test_rehashed_product_input_and_raw_output_tampering_is_rejected(
    receipt_template: Path,
    tmp_path: Path,
) -> None:
    product_input = _copy_receipt(receipt_template, tmp_path / "product-input")
    changed_input = b"{}\n"
    (product_input / PRODUCT_INPUT_PATH).write_bytes(changed_input)
    _reindex(product_input, PRODUCT_INPUT_PATH)
    execution = ExecutionReceipt.model_validate_json(
        (product_input / EXECUTION_PATH).read_bytes()
    ).model_copy(update={"product_input_digest": digest_bytes(changed_input)})
    _write_model_and_reindex(product_input, EXECUTION_PATH, execution)
    with pytest.raises(ReceiptIntegrityError, match="declared adapter output"):
        validate_ambiguity_run_receipt(
            product_input,
            adapter=reference_product.adapt_public_ambiguity,
            normalizer=reference_product.normalize_reference_output,
        )

    product_output = _copy_receipt(receipt_template, tmp_path / "product-output")
    changed_output = b"{}\n"
    (product_output / PRODUCT_OUTPUT_PATH).write_bytes(changed_output)
    _reindex(product_output, PRODUCT_OUTPUT_PATH)
    execution = ExecutionReceipt.model_validate_json(
        (product_output / EXECUTION_PATH).read_bytes()
    ).model_copy(update={"product_output_digest": digest_bytes(changed_output)})
    _write_model_and_reindex(product_output, EXECUTION_PATH, execution)
    with pytest.raises(ReceiptIntegrityError, match="valid partition"):
        validate_ambiguity_run_receipt(
            product_output,
            adapter=reference_product.adapt_public_ambiguity,
            normalizer=reference_product.normalize_reference_output,
        )


def test_rehashed_submission_tampering_is_rejected(
    receipt_template: Path,
    tmp_path: Path,
) -> None:
    clusters = _copy_receipt(receipt_template, tmp_path / "clusters")
    partition = EntityResolutionPrediction.model_validate_json(
        (clusters / SUBMISSION_CLUSTERS_PATH).read_bytes()
    )
    first, second, *rest = partition.clusters
    changed_partition = EntityResolutionPrediction(clusters=(first + second, *rest))
    _write_model_and_reindex(clusters, SUBMISSION_CLUSTERS_PATH, changed_partition)
    with pytest.raises(ReceiptIntegrityError, match="normalized output"):
        validate_ambiguity_run_receipt(
            clusters,
            adapter=reference_product.adapt_public_ambiguity,
            normalizer=reference_product.normalize_reference_output,
        )

    pairs = _copy_receipt(receipt_template, tmp_path / "pairs")
    submission = AmbiguityPairSubmission.model_validate_json(
        (pairs / SUBMISSION_PAIRS_PATH).read_bytes()
    )
    first_prediction = submission.predictions[0]
    replacement = (
        PairDisposition.SEPARATE
        if first_prediction.disposition is PairDisposition.MERGE
        else PairDisposition.MERGE
    )
    changed_prediction = first_prediction.model_copy(
        update={"disposition": replacement}
    )
    changed_submission = submission.model_copy(
        update={"predictions": (changed_prediction, *submission.predictions[1:])}
    )
    _write_model_and_reindex(pairs, SUBMISSION_PAIRS_PATH, changed_submission)
    with pytest.raises(ReceiptIntegrityError, match="public-only projection"):
        validate_ambiguity_run_receipt(
            pairs,
            adapter=reference_product.adapt_public_ambiguity,
            normalizer=reference_product.normalize_reference_output,
        )


@pytest.mark.parametrize("truth_path", [MEMBERSHIP_TRUTH_PATH, DISPOSITION_TRUTH_PATH])
def test_rehashed_truth_mispairing_is_rejected(
    receipt_template: Path,
    tmp_path: Path,
    truth_path: str,
) -> None:
    root = _copy_receipt(receipt_template, tmp_path / truth_path.replace("/", "-"))
    if truth_path == MEMBERSHIP_TRUTH_PATH:
        membership_truth = MembershipTruth.model_validate_json(
            (root / truth_path).read_bytes()
        )
        changed: object = membership_truth.model_copy(
            update={"record_memberships": membership_truth.record_memberships[:-1]}
        )
    else:
        disposition_truth = DispositionTruth.model_validate_json(
            (root / truth_path).read_bytes()
        )
        changed = disposition_truth.model_copy(
            update={"pairs": disposition_truth.pairs[:-1]}
        )
    _write_model_and_reindex(root, truth_path, changed)

    with pytest.raises(ReceiptIntegrityError, match="do not belong together"):
        validate_ambiguity_run_receipt(
            root,
            adapter=reference_product.adapt_public_ambiguity,
            normalizer=reference_product.normalize_reference_output,
        )


@pytest.mark.parametrize(
    ("report_path", "field", "message"),
    [
        (MEMBERSHIP_EVALUATION_PATH, "false_merge_pair_count", "membership"),
        (DISPOSITION_EVALUATION_PATH, "false_merges", "disposition"),
    ],
)
def test_rehashed_evaluation_tampering_is_rejected(
    receipt_template: Path,
    tmp_path: Path,
    report_path: str,
    field: str,
    message: str,
) -> None:
    root = _copy_receipt(receipt_template, tmp_path / message)
    model = (
        AmbiguityMembershipMetrics
        if report_path == MEMBERSHIP_EVALUATION_PATH
        else AmbiguityDispositionMetrics
    )
    report = model.model_validate_json((root / report_path).read_bytes())
    changed = report.model_copy(update={field: getattr(report, field) + 1})
    _write_model_and_reindex(root, report_path, changed)

    with pytest.raises(ReceiptIntegrityError, match=f"{message} evaluation"):
        validate_ambiguity_run_receipt(
            root,
            adapter=reference_product.adapt_public_ambiguity,
            normalizer=reference_product.normalize_reference_output,
        )
