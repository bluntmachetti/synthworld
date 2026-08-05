"""Contextual receipt-v2 preflight, staging, and adversarial replay tests."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from synthworld.assurance.contextual_access import (
    CONTEXTUAL_RUN_SCORING_VERSION,
    ContextualAccessPreExecutionArtifactsV1,
    ContextualAccessProductInputV1,
    ContextualAccessRunMetadataV1,
    build_contextual_access_run_receipt,
    finalize_contextual_access_run_receipt,
    run_contextual_product_stage_with_preflight,
    validate_contextual_access_run_receipt,
)
from synthworld.assurance.models import (
    Digest,
    EvaluationStatus,
    ExecutionReceipt,
    ExecutionStatus,
)
from synthworld.assurance.models_v2 import (
    DigestV2,
    ExecutionReceiptV2,
    RunReceiptManifestV2,
    SystemComponentProvenanceV2,
    VersionBindingV2,
)
from synthworld.assurance.receipt import (
    EXECUTION_PATH,
    MANIFEST_PATH,
    PRODUCT_INPUT_PATH,
    SOURCE_PUBLIC_PATH,
    ProductStageError,
    ReceiptIntegrityError,
    canonical_json_bytes,
)
from synthworld.assurance.receipt_v2 import digest_bytes_v2
from synthworld.cli import main
from synthworld.contextual_access.models import (
    ContextualAccessEvaluatorV1,
    ContextualAccessPublicV1,
)
from synthworld.contextual_access.protocol import (
    CONTEXTUAL_OBSERVATIONS_PATH,
    CONTEXTUAL_REPORT_PATH,
    CONTEXTUAL_RUN_PLAN_PATH,
    CONTEXTUAL_RUN_TRUTH_PATH,
    ContextualAccessObservationsV1,
    ContextualAccessReportV1,
    ContextualAccessRunPlanV1,
)
from synthworld.contextual_access.protocol_reference import (
    ReferenceContextualRunV1,
    reference_contextual_access_run,
)
from synthworld.contextual_access.receipt_reference import (
    build_reference_contextual_access_run_receipt,
    reference_contextual_receipt_metadata,
)
from synthworld.contextual_access.reference import reference_contextual_access


@pytest.fixture(scope="module")
def receipt_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("contextual-receipt") / "run"
    build_reference_contextual_access_run_receipt(root)
    return root


def test_reference_receipt_exercises_all_contract_roles_and_replays(
    receipt_template: Path,
) -> None:
    manifest = validate_contextual_access_run_receipt(receipt_template)
    assert manifest.schema_version == "2.0.0"
    assert manifest.evaluation_status is EvaluationStatus.EVALUATED
    assert {item.role for item in manifest.artifacts} == {
        "contextual_access_run_plan",
        "source_public",
        "product_input",
        "product_output",
        "execution",
        "contextual_access_observations",
        "contextual_access_run_truth",
        "contextual_access_evaluation",
    }
    assert {item.version for item in manifest.scoring_formula_versions} == {
        CONTEXTUAL_RUN_SCORING_VERSION
    }
    run = reference_contextual_access_run()
    assert {item.observation_type for item in run.observations.observations} == {
        "mapping_ingestion",
        "access_decision",
        "protected_enforcement",
        "delivery_acceptance",
        "synchronization_fault",
        "evidence_correlation",
    }
    assert {item.kind.value for item in run.plan.faults} == {
        "delayed_delivery",
        "duplicate_delivery",
        "out_of_order_delivery",
    }


def test_contextual_receipt_cli_accepts_valid_and_rejects_missing_roots(
    receipt_template: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        main(
            [
                "validate",
                "contextual-access-receipt",
                "--input",
                str(receipt_template),
            ]
        )
        == 0
    )
    assert (
        "contextual-access-receipt: valid (8 bound artifacts)"
        in capsys.readouterr().out
    )

    assert (
        main(
            [
                "validate",
                "contextual-access-receipt",
                "--input",
                str(tmp_path / "missing"),
            ]
        )
        == 1
    )
    assert "manifest.json" in capsys.readouterr().err


def test_metadata_and_preflight_reject_noncanonical_system_order(
    tmp_path: Path,
) -> None:
    run = reference_contextual_access_run()
    metadata = reference_contextual_receipt_metadata(run)
    with pytest.raises(ValidationError, match="sorted and unique"):
        ContextualAccessRunMetadataV1(
            callable_identifier=metadata.callable_identifier,
            source_public_schema_version=metadata.source_public_schema_version,
            product_output_schema_version=metadata.product_output_schema_version,
            benchmark=metadata.benchmark,
            build_environment=metadata.build_environment,
            run=metadata.run,
            adapter=metadata.adapter,
            systems_under_test=tuple(reversed(metadata.systems_under_test)),
            generator_configuration=metadata.generator_configuration,
            event_schedule=metadata.event_schedule,
            evidence_claim=metadata.evidence_claim,
        )
    with pytest.raises(ProductStageError, match="sorted and unique"):
        _preflight(
            tmp_path / "systems",
            run=run,
            systems=tuple(reversed(run.systems_under_test)),
        )


def test_preflight_rejects_existing_root_and_invalid_plan(tmp_path: Path) -> None:
    run = reference_contextual_access_run()
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(ProductStageError, match="must not already exist"):
        _preflight(existing, run=run)
    bad_plan = run.plan.model_copy(update={"sut_component_ids": ("unknown",)})
    with pytest.raises(ProductStageError, match="preflight failed"):
        _preflight(tmp_path / "plan", run=run, plan=bad_plan)
    assert not (tmp_path / "plan").exists()


def test_validator_wraps_artifact_read_errors(
    receipt_template: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _copy_receipt(receipt_template, tmp_path / "read-error")
    target = root / CONTEXTUAL_RUN_PLAN_PATH
    original = Path.read_bytes
    target_reads = 0

    def flaky_read_bytes(path: Path) -> bytes:
        nonlocal target_reads
        if path == target:
            target_reads += 1
            if target_reads == 2:
                raise OSError("simulated read failure")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", flaky_read_bytes)
    with pytest.raises(ReceiptIntegrityError, match="cannot be read"):
        validate_contextual_access_run_receipt(root)


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (b"{", "does not match its schema"),
        (b"\xff", "does not match its schema"),
    ],
)
def test_preflight_rejects_invalid_source_without_creating_root(
    tmp_path: Path, source: bytes, message: str
) -> None:
    root = tmp_path / str(len(source))
    with pytest.raises(ReceiptIntegrityError, match=message):
        _preflight(root, source=source)
    assert not root.exists()


def test_preflight_rejects_noncanonical_and_different_source(tmp_path: Path) -> None:
    run = reference_contextual_access_run()
    pretty = (
        json.dumps(run.benchmark.public.model_dump(mode="json"), indent=2) + "\n"
    ).encode()
    with pytest.raises(ReceiptIntegrityError, match="not canonical JSON"):
        _preflight(tmp_path / "pretty", run=run, source=pretty)
    other = reference_contextual_access(seed=2).public
    with pytest.raises(ReceiptIntegrityError, match="differs from preflight"):
        _preflight(
            tmp_path / "different",
            run=run,
            source=canonical_json_bytes(other),
        )


def test_preflight_rejects_adapter_schema_canonicality_and_difference(
    tmp_path: Path,
) -> None:
    run = reference_contextual_access_run()
    with pytest.raises(ReceiptIntegrityError, match="does not match its schema"):
        _preflight(tmp_path / "schema", run=run, adapter=lambda _: b"{}\n")
    pretty = (
        json.dumps(run.benchmark.public.model_dump(mode="json"), indent=2) + "\n"
    ).encode()
    with pytest.raises(ReceiptIntegrityError, match="not canonical JSON"):
        _preflight(tmp_path / "canonical", run=run, adapter=lambda _: pretty)
    other = canonical_json_bytes(reference_contextual_access(seed=2).public)
    with pytest.raises(ReceiptIntegrityError, match="adapter output differs"):
        _preflight(tmp_path / "different", run=run, adapter=lambda _: other)


def test_preflight_requires_runner_output(tmp_path: Path) -> None:
    with pytest.raises(ProductStageError, match="did not create"):
        _preflight(
            tmp_path / "missing-output",
            runner=lambda _input, _output: 0,
        )


def test_builder_rejects_metadata_mismatches_before_execution(tmp_path: Path) -> None:
    run = reference_contextual_access_run()
    metadata = reference_contextual_receipt_metadata(run)
    bad_run = metadata.model_copy(
        update={"run": metadata.run.model_copy(update={"run_id": "different"})}
    )
    with pytest.raises(ReceiptIntegrityError, match="metadata identifier"):
        _build(tmp_path / "run-id", run, bad_run)
    assert not (tmp_path / "run-id").exists()
    for field, value in (
        ("family", "different"),
        ("policy_digest", DigestV2(value="1" * 64)),
        ("cell_digest", DigestV2(value="2" * 64)),
    ):
        changed = metadata.model_copy(
            update={"benchmark": metadata.benchmark.model_copy(update={field: value})}
        )
        with pytest.raises(ReceiptIntegrityError, match="benchmark identity"):
            _build(tmp_path / field, run, changed)
        assert not (tmp_path / field).exists()


def test_builder_stops_after_failed_execution_before_truth(tmp_path: Path) -> None:
    run = reference_contextual_access_run()
    truth_called = False

    def runner(_input: Path, output: Path) -> int:
        output.write_bytes(b"failed\n")
        return 7

    def truth_loader() -> ContextualAccessEvaluatorV1:
        nonlocal truth_called
        truth_called = True
        return run.benchmark.evaluator

    root = tmp_path / "failed"
    with pytest.raises(ReceiptIntegrityError, match="failed contextual execution"):
        build_contextual_access_run_receipt(
            root,
            pre_execution_artifacts=ContextualAccessPreExecutionArtifactsV1(
                run.plan, run.benchmark.public
            ),
            source_public=canonical_json_bytes(run.benchmark.public),
            adapter=lambda payload: payload,
            runner=runner,
            observation_normalizer=lambda _payload, _plan, _public: run.observations,
            truth_loader=truth_loader,
            metadata=reference_contextual_receipt_metadata(run),
        )
    assert not truth_called
    assert (root / EXECUTION_PATH).is_file()
    assert not (root / CONTEXTUAL_RUN_TRUTH_PATH).exists()


def test_builder_stages_observations_before_truth_and_checks_evaluator_digest(
    tmp_path: Path,
) -> None:
    run = reference_contextual_access_run()
    root = tmp_path / "ordered"
    calls: list[str] = []

    def runner(_input: Path, output: Path) -> int:
        calls.append("runner")
        output.write_bytes(canonical_json_bytes(run.observations))
        return 0

    def normalizer(
        payload: bytes,
        _plan: ContextualAccessRunPlanV1,
        _public: ContextualAccessPublicV1,
    ) -> ContextualAccessObservationsV1:
        calls.append("normalizer")
        if calls.count("normalizer") == 1:
            assert (root / EXECUTION_PATH).is_file()
            assert not (root / CONTEXTUAL_OBSERVATIONS_PATH).exists()
            assert not (root / CONTEXTUAL_RUN_TRUTH_PATH).exists()
        else:
            assert (root / CONTEXTUAL_OBSERVATIONS_PATH).is_file()
            assert (root / CONTEXTUAL_RUN_TRUTH_PATH).is_file()
        return ContextualAccessObservationsV1.model_validate_json(payload)

    def truth_loader() -> ContextualAccessEvaluatorV1:
        calls.append("truth")
        assert (root / CONTEXTUAL_OBSERVATIONS_PATH).is_file()
        assert not (root / CONTEXTUAL_RUN_TRUTH_PATH).exists()
        return run.benchmark.evaluator

    build_contextual_access_run_receipt(
        root,
        pre_execution_artifacts=ContextualAccessPreExecutionArtifactsV1(
            run.plan, run.benchmark.public
        ),
        source_public=canonical_json_bytes(run.benchmark.public),
        adapter=lambda payload: payload,
        runner=runner,
        observation_normalizer=normalizer,
        truth_loader=truth_loader,
        metadata=reference_contextual_receipt_metadata(run),
    )
    assert calls == ["runner", "normalizer", "truth", "normalizer"]

    bad = reference_contextual_receipt_metadata(run)
    bad = bad.model_copy(
        update={
            "benchmark": bad.benchmark.model_copy(
                update={"evaluator_root_digest": DigestV2(value="3" * 64)}
            )
        }
    )
    with pytest.raises(ReceiptIntegrityError, match="evaluator digest"):
        _build(tmp_path / "bad-evaluator", run, bad)


def test_two_phase_finalizer_attributes_contextual_run_after_execution(
    tmp_path: Path,
) -> None:
    run = reference_contextual_access_run()
    root = tmp_path / "two-phase"
    execution = _preflight(root, run=run)
    assert execution.status is ExecutionStatus.SUCCEEDED
    metadata = _finalizer_metadata(run)
    completed_run = metadata.run.model_copy(
        update={"completed_at": metadata.run.completed_at.replace(minute=2)}
    )

    manifest = _finalize_staged(
        root,
        run=run,
        metadata=metadata.model_copy(update={"run": completed_run}),
    )

    assert manifest.run.completed_at == completed_run.completed_at
    assert manifest.evaluation_status is EvaluationStatus.EVALUATED


def test_contextual_finalizer_rejects_incomplete_stage_before_truth(
    tmp_path: Path,
) -> None:
    run = reference_contextual_access_run()
    truth_called = False

    def truth_loader() -> ContextualAccessEvaluatorV1:
        nonlocal truth_called
        truth_called = True
        return run.benchmark.evaluator

    with pytest.raises(ReceiptIntegrityError, match="execution is incomplete"):
        finalize_contextual_access_run_receipt(
            tmp_path / "missing",
            pre_execution_artifacts=ContextualAccessPreExecutionArtifactsV1(
                run.plan,
                run.benchmark.public,
            ),
            adapter=lambda payload: payload,
            observation_normalizer=lambda _payload, _plan, _public: run.observations,
            truth_loader=truth_loader,
            metadata=_finalizer_metadata(run),
        )
    assert not truth_called


def test_contextual_finalizer_rejects_plan_public_and_adapter_drift(
    tmp_path: Path,
) -> None:
    run = reference_contextual_access_run()

    plan_root = tmp_path / "plan"
    _preflight(plan_root, run=run)
    changed_plan = run.plan.model_copy(update={"event_schedule_version": "changed"})
    (plan_root / CONTEXTUAL_RUN_PLAN_PATH).write_bytes(
        canonical_json_bytes(changed_plan)
    )
    with pytest.raises(ReceiptIntegrityError, match="run plan differs"):
        _finalize_staged(plan_root, run=run)

    public_root = tmp_path / "public"
    _preflight(public_root, run=run)
    other_public = reference_contextual_access(seed=2).public
    (public_root / SOURCE_PUBLIC_PATH).write_bytes(canonical_json_bytes(other_public))
    with pytest.raises(ReceiptIntegrityError, match="public input differs"):
        _finalize_staged(public_root, run=run)

    adapter_root = tmp_path / "adapter"
    _preflight(adapter_root, run=run)
    with pytest.raises(ReceiptIntegrityError, match="adapter output"):
        _finalize_staged(
            adapter_root,
            run=run,
            adapter=lambda _payload: canonical_json_bytes(other_public),
        )


def test_contextual_finalizer_rejects_invalid_staged_plan_relationships(
    tmp_path: Path,
) -> None:
    run = reference_contextual_access_run()
    root = tmp_path / "relationships"
    _preflight(root, run=run)
    invalid_plan = run.plan.model_copy(update={"sut_component_ids": ("unknown",)})
    plan_bytes = canonical_json_bytes(invalid_plan)
    (root / CONTEXTUAL_RUN_PLAN_PATH).write_bytes(plan_bytes)
    plan_digest = digest_bytes_v2(plan_bytes)
    product_input = ContextualAccessProductInputV1.model_validate_json(
        (root / PRODUCT_INPUT_PATH).read_bytes()
    ).model_copy(update={"run_plan_digest": plan_digest})
    product_input_bytes = canonical_json_bytes(product_input)
    (root / PRODUCT_INPUT_PATH).write_bytes(product_input_bytes)
    execution = ExecutionReceiptV2.model_validate_json(
        (root / EXECUTION_PATH).read_bytes()
    ).model_copy(
        update={
            "run_plan_digest": plan_digest,
            "product_input_digest": digest_bytes_v2(product_input_bytes),
        }
    )
    (root / EXECUTION_PATH).write_bytes(canonical_json_bytes(execution))

    with pytest.raises(ReceiptIntegrityError, match="relationships are invalid"):
        _finalize_staged(
            root,
            run=run,
            pre_execution_artifacts=ContextualAccessPreExecutionArtifactsV1(
                invalid_plan,
                run.benchmark.public,
            ),
        )


def test_contextual_finalizer_rejects_execution_version_and_input_binding(
    tmp_path: Path,
) -> None:
    run = reference_contextual_access_run()
    version_root = tmp_path / "version"
    _preflight(version_root, run=run)
    zero_v1 = Digest(value="0" * 64)
    execution_v1 = ExecutionReceipt(
        boundary="legacy",
        callable_identifier="legacy.callable",
        adapter_name="legacy",
        adapter_version="1.0.0",
        adapter_source_digest=zero_v1,
        source_public_digest=zero_v1,
        product_input_digest=zero_v1,
        product_output_digest=zero_v1,
        exit_code=0,
        status=ExecutionStatus.SUCCEEDED,
    )
    (version_root / EXECUTION_PATH).write_bytes(canonical_json_bytes(execution_v1))
    with pytest.raises(ReceiptIntegrityError, match="requires execution v2"):
        _finalize_staged(version_root, run=run)

    input_root = tmp_path / "input"
    _preflight(input_root, run=run)
    product_input = ContextualAccessProductInputV1.model_validate_json(
        (input_root / PRODUCT_INPUT_PATH).read_bytes()
    )
    (input_root / PRODUCT_INPUT_PATH).write_bytes(
        canonical_json_bytes(
            product_input.model_copy(
                update={"run_plan_digest": DigestV2(value="0" * 64)}
            )
        )
    )
    with pytest.raises(ReceiptIntegrityError, match="input bindings"):
        _finalize_staged(input_root, run=run)


def test_contextual_finalizer_rejects_system_provenance_and_digest_drift(
    tmp_path: Path,
) -> None:
    run = reference_contextual_access_run()
    systems_root = tmp_path / "systems"
    _preflight(systems_root, run=run)
    execution = ExecutionReceiptV2.model_validate_json(
        (systems_root / EXECUTION_PATH).read_bytes()
    )
    (systems_root / EXECUTION_PATH).write_bytes(
        canonical_json_bytes(
            execution.model_copy(
                update={"systems_under_test": execution.systems_under_test[:1]}
            )
        )
    )
    with pytest.raises(ReceiptIntegrityError, match="systems differ"):
        _finalize_staged(systems_root, run=run)

    provenance_root = tmp_path / "provenance"
    _preflight(provenance_root, run=run)
    execution = ExecutionReceiptV2.model_validate_json(
        (provenance_root / EXECUTION_PATH).read_bytes()
    )
    (provenance_root / EXECUTION_PATH).write_bytes(
        canonical_json_bytes(execution.model_copy(update={"boundary": "changed"}))
    )
    with pytest.raises(ReceiptIntegrityError, match="provenance differs"):
        _finalize_staged(provenance_root, run=run)

    digest_root = tmp_path / "digest"
    _preflight(digest_root, run=run)
    execution = ExecutionReceiptV2.model_validate_json(
        (digest_root / EXECUTION_PATH).read_bytes()
    )
    (digest_root / EXECUTION_PATH).write_bytes(
        canonical_json_bytes(
            execution.model_copy(
                update={"product_output_digest": DigestV2(value="0" * 64)}
            )
        )
    )
    with pytest.raises(ReceiptIntegrityError, match="digest bindings"):
        _finalize_staged(digest_root, run=run)


def test_validator_rejects_role_schema_scoring_and_execution_version(
    receipt_template: Path, tmp_path: Path
) -> None:
    role = _copy_receipt(receipt_template, tmp_path / "role")
    manifest = _manifest(role)
    artifacts = (
        manifest.artifacts[0].model_copy(update={"role": "wrong"}),
        *manifest.artifacts[1:],
    )
    _write_manifest(role, manifest.model_copy(update={"artifacts": artifacts}))
    with pytest.raises(ReceiptIntegrityError, match="roles or paths"):
        validate_contextual_access_run_receipt(role)

    schema = _copy_receipt(receipt_template, tmp_path / "schema")
    manifest = _manifest(schema)
    bindings = (
        manifest.schema_versions[0].model_copy(update={"version": "wrong"}),
        *manifest.schema_versions[1:],
    )
    _write_manifest(schema, manifest.model_copy(update={"schema_versions": bindings}))
    with pytest.raises(ReceiptIntegrityError, match="schema bindings"):
        validate_contextual_access_run_receipt(schema)

    scoring = _copy_receipt(receipt_template, tmp_path / "scoring")
    manifest = _manifest(scoring)
    _write_manifest(
        scoring,
        manifest.model_copy(
            update={
                "scoring_formula_versions": (
                    VersionBindingV2(role="contextual_access", version="wrong"),
                )
            }
        ),
    )
    with pytest.raises(ReceiptIntegrityError, match="scoring formula"):
        validate_contextual_access_run_receipt(scoring)

    legacy = _copy_receipt(receipt_template, tmp_path / "legacy")
    zero = Digest(value="0" * 64)
    execution_v1 = ExecutionReceipt(
        boundary="legacy",
        callable_identifier="legacy.callable",
        adapter_name="legacy",
        adapter_version="1.0.0",
        adapter_source_digest=zero,
        source_public_digest=zero,
        product_input_digest=zero,
        product_output_digest=zero,
        exit_code=0,
        status=ExecutionStatus.SUCCEEDED,
    )
    _write_model_and_reindex(legacy, EXECUTION_PATH, execution_v1)
    with pytest.raises(ReceiptIntegrityError, match="requires execution v2"):
        validate_contextual_access_run_receipt(legacy)


def test_validator_wraps_cross_artifact_protocol_failures(
    receipt_template: Path, tmp_path: Path
) -> None:
    root = _copy_receipt(receipt_template, tmp_path)
    observations = ContextualAccessObservationsV1.model_validate_json(
        (root / CONTEXTUAL_OBSERVATIONS_PATH).read_bytes()
    )
    _write_model_and_reindex(
        root,
        CONTEXTUAL_OBSERVATIONS_PATH,
        observations.model_copy(update={"run_id": "different"}),
    )
    with pytest.raises(ReceiptIntegrityError, match="relationships are invalid"):
        validate_contextual_access_run_receipt(root)


def test_validator_rejects_plan_public_and_product_input_bindings(
    receipt_template: Path, tmp_path: Path
) -> None:
    root = _copy_receipt(receipt_template, tmp_path / "plan")
    _mutate_product_input(
        root,
        lambda item: item.model_copy(
            update={"run_plan_digest": DigestV2(value="4" * 64)}
        ),
    )
    with pytest.raises(ReceiptIntegrityError, match="run-plan digest"):
        validate_contextual_access_run_receipt(root)

    root = _copy_receipt(receipt_template, tmp_path / "plan-execution")
    _mutate_execution(
        root,
        lambda item: item.model_copy(
            update={"run_plan_digest": DigestV2(value="5" * 64)}
        ),
    )
    with pytest.raises(ReceiptIntegrityError, match="run-plan digest"):
        validate_contextual_access_run_receipt(root)

    public_digest_mutations: tuple[tuple[str, Callable[[Path], None]], ...] = (
        (
            "input-public-digest",
            lambda root: _mutate_product_input(
                root,
                lambda item: item.model_copy(
                    update={"contextual_public_digest": DigestV2(value="6" * 64)}
                ),
            ),
        ),
        (
            "execution-stimulus",
            lambda root: _mutate_execution(
                root,
                lambda item: item.model_copy(
                    update={"stimulus_digest": DigestV2(value="7" * 64)}
                ),
            ),
        ),
        (
            "execution-source",
            lambda root: _mutate_execution(
                root,
                lambda item: item.model_copy(
                    update={"source_public_digest": DigestV2(value="8" * 64)}
                ),
            ),
        ),
    )
    for name, mutate in public_digest_mutations:
        root = _copy_receipt(receipt_template, tmp_path / name)
        mutate(root)
        with pytest.raises(ReceiptIntegrityError, match="public digest"):
            validate_contextual_access_run_receipt(root)

    root = _copy_receipt(receipt_template, tmp_path / "inline-public")
    other = reference_contextual_access(seed=2).public
    _mutate_product_input(root, lambda item: item.model_copy(update={"public": other}))
    _rebind_execution_product_input(root)
    with pytest.raises(ReceiptIntegrityError, match="product input differs"):
        validate_contextual_access_run_receipt(root)


@pytest.mark.parametrize("field", ["product_input_digest", "product_output_digest"])
def test_validator_rejects_execution_artifact_digests(
    receipt_template: Path, tmp_path: Path, field: str
) -> None:
    root = _copy_receipt(receipt_template, tmp_path)
    _mutate_execution(
        root,
        lambda item: item.model_copy(update={field: DigestV2(value="9" * 64)}),
    )
    with pytest.raises(ReceiptIntegrityError, match="artifact digests"):
        validate_contextual_access_run_receipt(root)


def test_validator_rejects_system_status_run_and_benchmark_root_mismatches(
    receipt_template: Path, tmp_path: Path
) -> None:
    systems = _copy_receipt(receipt_template, tmp_path / "systems")
    _mutate_execution(
        systems,
        lambda item: item.model_copy(
            update={"systems_under_test": (item.systems_under_test[0],)}
        ),
    )
    with pytest.raises(ReceiptIntegrityError, match="systems differ"):
        validate_contextual_access_run_receipt(systems)

    evaluation = _copy_receipt(receipt_template, tmp_path / "evaluation")
    manifest = _manifest(evaluation)
    _write_manifest(
        evaluation,
        manifest.model_copy(
            update={"evaluation_status": EvaluationStatus.NOT_EVALUATED}
        ),
    )
    with pytest.raises(ReceiptIntegrityError, match="receipt is evaluated"):
        validate_contextual_access_run_receipt(evaluation)

    run_id = _copy_receipt(receipt_template, tmp_path / "run-id")
    manifest = _manifest(run_id)
    _write_manifest(
        run_id,
        manifest.model_copy(
            update={"run": manifest.run.model_copy(update={"run_id": "different"})}
        ),
    )
    with pytest.raises(ReceiptIntegrityError, match="manifest run identifier"):
        validate_contextual_access_run_receipt(run_id)

    for name, field in (
        ("benchmark", "family"),
        ("public-root", "public_root_digest"),
        ("evaluator-root", "evaluator_root_digest"),
    ):
        root = _copy_receipt(receipt_template, tmp_path / name)
        manifest = _manifest(root)
        value: object = "different"
        if field.endswith("digest"):
            value = DigestV2(value="a" * 64)
        _write_manifest(
            root,
            manifest.model_copy(
                update={
                    "benchmark": manifest.benchmark.model_copy(update={field: value})
                }
            ),
        )
        message = (
            "roots differ" if field == "evaluator_root_digest" else "benchmark identity"
        )
        with pytest.raises(ReceiptIntegrityError, match=message):
            validate_contextual_access_run_receipt(root)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("boundary", "different"),
        ("adapter_name", "different"),
        ("adapter_version", "different"),
        ("adapter_source_digest", DigestV2(value="b" * 64)),
    ],
)
def test_validator_rejects_execution_provenance(
    receipt_template: Path, tmp_path: Path, field: str, value: object
) -> None:
    root = _copy_receipt(receipt_template, tmp_path)
    _mutate_execution(root, lambda item: item.model_copy(update={field: value}))
    with pytest.raises(ReceiptIntegrityError, match="execution provenance"):
        validate_contextual_access_run_receipt(root)


def test_validator_rejects_execution_status_binding(
    receipt_template: Path, tmp_path: Path
) -> None:
    root = _copy_receipt(receipt_template, tmp_path)
    _mutate_execution(
        root,
        lambda item: item.model_copy(
            update={"exit_code": 1, "status": ExecutionStatus.FAILED}
        ),
    )
    with pytest.raises(ReceiptIntegrityError, match="execution provenance"):
        validate_contextual_access_run_receipt(root)


def test_validator_replays_adapter_normalizer_and_report(
    receipt_template: Path, tmp_path: Path
) -> None:
    other = canonical_json_bytes(reference_contextual_access(seed=2).public)
    with pytest.raises(ReceiptIntegrityError, match="adapter output"):
        validate_contextual_access_run_receipt(
            receipt_template,
            adapter=lambda _source: other,
        )
    changed = reference_contextual_access_run().observations.model_copy(
        update={"limitations": ("different",)}
    )
    with pytest.raises(ReceiptIntegrityError, match="normalized product output"):
        validate_contextual_access_run_receipt(
            receipt_template,
            observation_normalizer=lambda _output, _plan, _public: changed,
        )
    root = _copy_receipt(receipt_template, tmp_path)
    report = ContextualAccessReportV1.model_validate_json(
        (root / CONTEXTUAL_REPORT_PATH).read_bytes()
    )
    changed_report = report.model_copy(update={"run_id": "different"})
    _write_model_and_reindex(root, CONTEXTUAL_REPORT_PATH, changed_report)
    with pytest.raises(ReceiptIntegrityError, match="evaluation does not replay"):
        validate_contextual_access_run_receipt(root)


def _preflight(
    root: Path,
    *,
    run: ReferenceContextualRunV1 | None = None,
    systems: tuple[SystemComponentProvenanceV2, ...] | None = None,
    plan: ContextualAccessRunPlanV1 | None = None,
    source: bytes | None = None,
    adapter: Callable[[bytes], bytes] | None = None,
    runner: Callable[[Path, Path], int] | None = None,
) -> ExecutionReceiptV2:
    selected = run or reference_contextual_access_run()
    selected_systems = selected.systems_under_test if systems is None else systems

    def default_runner(_input: Path, output: Path) -> int:
        output.write_bytes(canonical_json_bytes(selected.observations))
        return 0

    return run_contextual_product_stage_with_preflight(
        root,
        systems_under_test=selected_systems,
        pre_execution_artifacts=ContextualAccessPreExecutionArtifactsV1(
            plan or selected.plan,
            selected.benchmark.public,
        ),
        source_public=(
            canonical_json_bytes(selected.benchmark.public)
            if source is None
            else source
        ),
        adapter=(lambda payload: payload) if adapter is None else adapter,
        runner=default_runner if runner is None else runner,
        adapter_provenance=reference_contextual_receipt_metadata(selected).adapter,
        callable_identifier="tests.contextual.fake",
    )


def _finalizer_metadata(
    run: ReferenceContextualRunV1,
) -> ContextualAccessRunMetadataV1:
    return reference_contextual_receipt_metadata(run).model_copy(
        update={"callable_identifier": "tests.contextual.fake"}
    )


def _finalize_staged(
    root: Path,
    *,
    run: ReferenceContextualRunV1,
    adapter: Callable[[bytes], bytes] | None = None,
    metadata: ContextualAccessRunMetadataV1 | None = None,
    pre_execution_artifacts: ContextualAccessPreExecutionArtifactsV1 | None = None,
) -> RunReceiptManifestV2:
    return finalize_contextual_access_run_receipt(
        root,
        pre_execution_artifacts=(
            ContextualAccessPreExecutionArtifactsV1(
                run.plan,
                run.benchmark.public,
            )
            if pre_execution_artifacts is None
            else pre_execution_artifacts
        ),
        adapter=(lambda payload: payload) if adapter is None else adapter,
        observation_normalizer=lambda payload, _plan, _public: (
            ContextualAccessObservationsV1.model_validate_json(payload)
        ),
        truth_loader=lambda: run.benchmark.evaluator,
        metadata=_finalizer_metadata(run) if metadata is None else metadata,
    )


def _build(
    root: Path,
    run: ReferenceContextualRunV1,
    metadata: ContextualAccessRunMetadataV1,
) -> RunReceiptManifestV2:
    def runner(_input: Path, output: Path) -> int:
        output.write_bytes(canonical_json_bytes(run.observations))
        return 0

    return build_contextual_access_run_receipt(
        root,
        pre_execution_artifacts=ContextualAccessPreExecutionArtifactsV1(
            run.plan, run.benchmark.public
        ),
        source_public=canonical_json_bytes(run.benchmark.public),
        adapter=lambda payload: payload,
        runner=runner,
        observation_normalizer=lambda payload, _plan, _public: (
            ContextualAccessObservationsV1.model_validate_json(payload)
        ),
        truth_loader=lambda: run.benchmark.evaluator,
        metadata=metadata,
    )


def _copy_receipt(template: Path, destination: Path) -> Path:
    root = destination / "run"
    shutil.copytree(template, root)
    return root


def _manifest(root: Path) -> RunReceiptManifestV2:
    return RunReceiptManifestV2.model_validate_json((root / MANIFEST_PATH).read_bytes())


def _write_manifest(root: Path, manifest: RunReceiptManifestV2) -> None:
    (root / MANIFEST_PATH).write_bytes(canonical_json_bytes(manifest))


def _write_bytes_and_reindex(root: Path, relative_path: str, payload: bytes) -> None:
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


def _write_model_and_reindex(root: Path, relative_path: str, model: BaseModel) -> None:
    _write_bytes_and_reindex(root, relative_path, canonical_json_bytes(model))


def _mutate_product_input(
    root: Path,
    mutation: Callable[
        [ContextualAccessProductInputV1], ContextualAccessProductInputV1
    ],
) -> None:
    model = ContextualAccessProductInputV1.model_validate_json(
        (root / PRODUCT_INPUT_PATH).read_bytes()
    )
    _write_model_and_reindex(root, PRODUCT_INPUT_PATH, mutation(model))


def _mutate_execution(
    root: Path, mutation: Callable[[ExecutionReceiptV2], ExecutionReceiptV2]
) -> None:
    model = ExecutionReceiptV2.model_validate_json((root / EXECUTION_PATH).read_bytes())
    _write_model_and_reindex(root, EXECUTION_PATH, mutation(model))


def _rebind_execution_product_input(root: Path) -> None:
    _mutate_execution(
        root,
        lambda item: item.model_copy(
            update={
                "product_input_digest": digest_bytes_v2(
                    (root / PRODUCT_INPUT_PATH).read_bytes()
                )
            }
        ),
    )
