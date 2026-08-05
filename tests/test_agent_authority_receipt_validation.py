"""Adversarial replay and staging tests for the agent-authority specialization."""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import ValidationError

from synthworld.agent_authority.cases import AgentAuthorityStimulusSetV1
from synthworld.agent_authority.models import (
    AgentAuthorityLabReportV1,
    AgentAuthorityLabTruthV1,
    AgentAuthorityProductInputV1,
    AgentAuthorityRunObservationsV1,
)
from synthworld.agent_authority.reference import (
    build_reference_agent_authority_run_receipt,
    reference_metadata,
    reference_observations,
    reference_plan,
    reference_stimuli,
    reference_systems,
    reference_truth,
)
from synthworld.assurance.agent_authority import (
    EVALUATION_PATH,
    OBSERVATIONS_PATH,
    RUN_PLAN_PATH,
    TRUTH_PATH,
    AgentAuthorityPreExecutionArtifactsV1,
    AgentAuthorityRunMetadataV1,
    build_agent_authority_run_receipt,
    finalize_agent_authority_run_receipt,
    run_product_stage_with_preflight,
    validate_agent_authority_run_receipt,
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
    ProductStageError,
    ReceiptIntegrityError,
    canonical_json_bytes,
)
from synthworld.assurance.receipt_v2 import digest_bytes_v2


@pytest.fixture(scope="module")
def receipt_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("agent-authority-validation") / "run"
    build_reference_agent_authority_run_receipt(root)
    return root


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


def _write_model_and_reindex(
    root: Path,
    relative_path: str,
    model: AgentAuthorityProductInputV1
    | AgentAuthorityLabReportV1
    | AgentAuthorityRunObservationsV1
    | ExecutionReceiptV2
    | ExecutionReceipt,
) -> None:
    _write_bytes_and_reindex(root, relative_path, canonical_json_bytes(model))


def _preflight(
    root: Path,
    *,
    systems: tuple[SystemComponentProvenanceV2, ...] | None = None,
    source: bytes | None = None,
    adapter: Callable[[bytes], bytes] | None = None,
    runner: Callable[[Path, Path], int] | None = None,
) -> ExecutionReceiptV2:
    selected_systems = reference_systems() if systems is None else systems
    return run_product_stage_with_preflight(
        root,
        systems_under_test=selected_systems,
        pre_execution_artifacts=AgentAuthorityPreExecutionArtifactsV1(
            reference_plan(), reference_stimuli()
        ),
        source_public=(
            canonical_json_bytes(reference_stimuli()) if source is None else source
        ),
        adapter=(lambda payload: payload) if adapter is None else adapter,
        runner=(
            (lambda _input, output: output.write_bytes(b"output\n") and 0)
            if runner is None
            else runner
        ),
        adapter_provenance=reference_metadata().adapter,
        callable_identifier="tests.fake",
    )


def test_metadata_and_preflight_reject_noncanonical_system_order(
    tmp_path: Path,
) -> None:
    metadata = reference_metadata()
    document = metadata.model_dump(mode="json")
    document["systems_under_test"] = list(reversed(document["systems_under_test"]))
    with pytest.raises(ValidationError, match="sorted and unique"):
        AgentAuthorityRunMetadataV1.model_validate(document)
    with pytest.raises(ProductStageError, match="sorted and unique"):
        _preflight(tmp_path / "preflight", systems=tuple(reversed(reference_systems())))


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (b"\xff\n", "must use canonical JSON"),
        (
            json.dumps(reference_stimuli().model_dump(mode="json"), indent=2).encode(),
            "must use canonical JSON",
        ),
    ],
)
def test_preflight_rejects_malformed_or_noncanonical_source_without_creating_root(
    tmp_path: Path,
    source: bytes,
    message: str,
) -> None:
    root = tmp_path / str(len(source))
    with pytest.raises(ReceiptIntegrityError, match=message):
        _preflight(root, source=source)
    assert not root.exists()


def test_preflight_rejects_adapter_schema_and_canonicality_failures(
    tmp_path: Path,
) -> None:
    with pytest.raises(ReceiptIntegrityError, match="does not match its schema"):
        _preflight(tmp_path / "schema", adapter=lambda _payload: b"{}\n")
    pretty = (
        json.dumps(reference_stimuli().model_dump(mode="json"), indent=2) + "\n"
    ).encode()
    with pytest.raises(ReceiptIntegrityError, match="not canonical JSON"):
        _preflight(tmp_path / "canonical", adapter=lambda _payload: pretty)


def test_preflight_requires_the_runner_output(tmp_path: Path) -> None:
    with pytest.raises(ProductStageError, match="did not create"):
        _preflight(tmp_path / "run", runner=lambda _input, _output: 0)


def test_builder_rejects_metadata_mismatches_before_execution(tmp_path: Path) -> None:
    metadata = reference_metadata()
    changed_run = metadata.run.model_copy(update={"run_id": "different"})
    bad_run = metadata.model_copy(update={"run": changed_run})
    with pytest.raises(ReceiptIntegrityError, match="metadata identifier"):
        _build(tmp_path / "run-id", bad_run)
    assert not (tmp_path / "run-id").exists()

    bad_benchmark = metadata.model_copy(
        update={
            "benchmark": metadata.benchmark.model_copy(update={"family": "different"})
        }
    )
    with pytest.raises(ReceiptIntegrityError, match="benchmark identity"):
        _build(tmp_path / "benchmark", bad_benchmark)
    assert not (tmp_path / "benchmark").exists()


def _build(root: Path, metadata: AgentAuthorityRunMetadataV1) -> RunReceiptManifestV2:
    observations = reference_observations()

    def runner(_input: Path, output: Path) -> int:
        output.write_bytes(canonical_json_bytes(observations))
        return 0

    return build_agent_authority_run_receipt(
        root,
        pre_execution_artifacts=AgentAuthorityPreExecutionArtifactsV1(
            reference_plan(), reference_stimuli()
        ),
        source_public=canonical_json_bytes(reference_stimuli()),
        adapter=lambda payload: payload,
        runner=runner,
        observation_normalizer=lambda payload, _plan, _stimuli: (
            AgentAuthorityRunObservationsV1.model_validate_json(payload)
        ),
        truth_loader=reference_truth,
        metadata=metadata,
    )


def test_two_phase_finalizer_attributes_run_after_product_execution(
    tmp_path: Path,
) -> None:
    root = tmp_path / "two-phase"
    observations = reference_observations()
    execution = _preflight(
        root,
        runner=lambda _input, output: (
            output.write_bytes(canonical_json_bytes(observations)) and 0
        ),
    )
    assert execution.status is ExecutionStatus.SUCCEEDED

    metadata = reference_metadata().model_copy(
        update={"callable_identifier": "tests.fake"}
    )
    completed_run = metadata.run.model_copy(
        update={"completed_at": metadata.run.completed_at.replace(minute=2)}
    )
    manifest = finalize_agent_authority_run_receipt(
        root,
        pre_execution_artifacts=AgentAuthorityPreExecutionArtifactsV1(
            reference_plan(), reference_stimuli()
        ),
        adapter=lambda payload: payload,
        observation_normalizer=lambda payload, _plan, _stimuli: (
            AgentAuthorityRunObservationsV1.model_validate_json(payload)
        ),
        truth_loader=reference_truth,
        metadata=metadata.model_copy(update={"run": completed_run}),
    )

    assert manifest.run.completed_at == completed_run.completed_at
    assert manifest.evaluation_status is EvaluationStatus.EVALUATED


def _stage_for_finalizer(root: Path) -> None:
    observations = reference_observations()

    def runner(_input: Path, output: Path) -> int:
        output.write_bytes(canonical_json_bytes(observations))
        return 0

    _preflight(root, runner=runner)


def _finalize_staged(
    root: Path,
    *,
    adapter: Callable[[bytes], bytes] | None = None,
) -> RunReceiptManifestV2:
    metadata = reference_metadata().model_copy(
        update={"callable_identifier": "tests.fake"}
    )
    return finalize_agent_authority_run_receipt(
        root,
        pre_execution_artifacts=AgentAuthorityPreExecutionArtifactsV1(
            reference_plan(), reference_stimuli()
        ),
        adapter=(lambda payload: payload) if adapter is None else adapter,
        observation_normalizer=lambda payload, _plan, _stimuli: (
            AgentAuthorityRunObservationsV1.model_validate_json(payload)
        ),
        truth_loader=reference_truth,
        metadata=metadata,
    )


def _changed_stimuli() -> AgentAuthorityStimulusSetV1:
    stimuli = reference_stimuli()
    first = stimuli.stimuli[0]
    changed_payload = first.payload.model_copy(
        update={"runtime_handle": "runtime:changed"}
    )
    changed_first = first.model_copy(update={"payload": changed_payload})
    return AgentAuthorityStimulusSetV1(stimuli=(changed_first, *stimuli.stimuli[1:]))


def test_finalizer_rejects_an_incomplete_product_stage_before_truth(
    tmp_path: Path,
) -> None:
    truth_called = False
    metadata = reference_metadata().model_copy(
        update={"callable_identifier": "tests.fake"}
    )

    def truth_loader() -> AgentAuthorityLabTruthV1:
        nonlocal truth_called
        truth_called = True
        return reference_truth()

    with pytest.raises(ReceiptIntegrityError, match="execution is incomplete"):
        finalize_agent_authority_run_receipt(
            tmp_path / "missing",
            pre_execution_artifacts=AgentAuthorityPreExecutionArtifactsV1(
                reference_plan(), reference_stimuli()
            ),
            adapter=lambda payload: payload,
            observation_normalizer=lambda _payload, _plan, _stimuli: (
                reference_observations()
            ),
            truth_loader=truth_loader,
            metadata=metadata,
        )
    assert not truth_called


def test_finalizer_rejects_changed_plan_stimuli_and_adapter(tmp_path: Path) -> None:
    plan_root = tmp_path / "plan"
    _stage_for_finalizer(plan_root)
    changed_plan = reference_plan().model_copy(
        update={"event_schedule_version": "changed"}
    )
    (plan_root / RUN_PLAN_PATH).write_bytes(canonical_json_bytes(changed_plan))
    with pytest.raises(ReceiptIntegrityError, match="run plan differs"):
        _finalize_staged(plan_root)

    stimuli_root = tmp_path / "stimuli"
    _stage_for_finalizer(stimuli_root)
    product_input = AgentAuthorityProductInputV1.model_validate_json(
        (stimuli_root / PRODUCT_INPUT_PATH).read_bytes()
    )
    changed = _changed_stimuli()
    (stimuli_root / PRODUCT_INPUT_PATH).write_bytes(
        canonical_json_bytes(
            product_input.model_copy(update={"stimuli": changed.stimuli})
        )
    )
    with pytest.raises(ReceiptIntegrityError, match="stimuli differ"):
        _finalize_staged(stimuli_root)

    adapter_root = tmp_path / "adapter"
    _stage_for_finalizer(adapter_root)
    with pytest.raises(ReceiptIntegrityError, match="adapter output"):
        _finalize_staged(
            adapter_root,
            adapter=lambda _payload: canonical_json_bytes(_changed_stimuli()),
        )


def test_finalizer_rejects_wrong_execution_version_and_input_binding(
    tmp_path: Path,
) -> None:
    version_root = tmp_path / "version"
    _stage_for_finalizer(version_root)
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
        _finalize_staged(version_root)

    input_root = tmp_path / "input"
    _stage_for_finalizer(input_root)
    product_input = AgentAuthorityProductInputV1.model_validate_json(
        (input_root / PRODUCT_INPUT_PATH).read_bytes()
    )
    zero_v2 = DigestV2(value="0" * 64)
    (input_root / PRODUCT_INPUT_PATH).write_bytes(
        canonical_json_bytes(
            product_input.model_copy(update={"run_plan_digest": zero_v2})
        )
    )
    with pytest.raises(ReceiptIntegrityError, match="input bindings"):
        _finalize_staged(input_root)


def test_finalizer_rejects_execution_system_provenance_and_digest_drift(
    tmp_path: Path,
) -> None:
    systems_root = tmp_path / "systems"
    _stage_for_finalizer(systems_root)
    execution = ExecutionReceiptV2.model_validate_json(
        (systems_root / EXECUTION_PATH).read_bytes()
    )
    changed_systems = execution.model_copy(
        update={"systems_under_test": execution.systems_under_test[:1]}
    )
    (systems_root / EXECUTION_PATH).write_bytes(canonical_json_bytes(changed_systems))
    with pytest.raises(ReceiptIntegrityError, match="systems differ"):
        _finalize_staged(systems_root)

    provenance_root = tmp_path / "provenance"
    _stage_for_finalizer(provenance_root)
    execution = ExecutionReceiptV2.model_validate_json(
        (provenance_root / EXECUTION_PATH).read_bytes()
    )
    changed_provenance = execution.model_copy(update={"boundary": "changed"})
    (provenance_root / EXECUTION_PATH).write_bytes(
        canonical_json_bytes(changed_provenance)
    )
    with pytest.raises(ReceiptIntegrityError, match="provenance differs"):
        _finalize_staged(provenance_root)

    digest_root = tmp_path / "digest"
    _stage_for_finalizer(digest_root)
    execution = ExecutionReceiptV2.model_validate_json(
        (digest_root / EXECUTION_PATH).read_bytes()
    )
    changed_digest = execution.model_copy(
        update={"product_output_digest": DigestV2(value="0" * 64)}
    )
    (digest_root / EXECUTION_PATH).write_bytes(canonical_json_bytes(changed_digest))
    with pytest.raises(ReceiptIntegrityError, match="digest bindings"):
        _finalize_staged(digest_root)


def test_builder_stops_after_failed_product_execution(tmp_path: Path) -> None:
    truth_called = False

    def runner(_input: Path, output: Path) -> int:
        output.write_bytes(b"failed product output\n")
        return 7

    def truth_loader() -> AgentAuthorityLabTruthV1:
        nonlocal truth_called
        truth_called = True
        return reference_truth()

    with pytest.raises(ReceiptIntegrityError, match="failed product execution"):
        build_agent_authority_run_receipt(
            tmp_path / "failed",
            pre_execution_artifacts=AgentAuthorityPreExecutionArtifactsV1(
                reference_plan(), reference_stimuli()
            ),
            source_public=canonical_json_bytes(reference_stimuli()),
            adapter=lambda payload: payload,
            runner=runner,
            observation_normalizer=lambda _payload, _plan, _stimuli: (
                reference_observations()
            ),
            truth_loader=truth_loader,
            metadata=reference_metadata(),
        )
    assert not truth_called
    assert (tmp_path / "failed" / EXECUTION_PATH).is_file()
    assert not (tmp_path / "failed" / TRUTH_PATH).exists()


def test_builder_stages_observations_before_loading_truth(tmp_path: Path) -> None:
    root = tmp_path / "ordered"
    observations = reference_observations()
    events: list[str] = []

    def runner(_input: Path, output: Path) -> int:
        events.append("runner")
        output.write_bytes(canonical_json_bytes(observations))
        return 0

    def normalizer(
        payload: bytes, _plan: object, _stimuli: object
    ) -> AgentAuthorityRunObservationsV1:
        events.append("normalizer")
        assert (root / EXECUTION_PATH).is_file()
        if events.count("normalizer") == 1:
            assert not (root / OBSERVATIONS_PATH).exists()
            assert not (root / TRUTH_PATH).exists()
        else:
            assert (root / OBSERVATIONS_PATH).is_file()
            assert (root / TRUTH_PATH).is_file()
        return AgentAuthorityRunObservationsV1.model_validate_json(payload)

    def truth_loader() -> AgentAuthorityLabTruthV1:
        events.append("truth")
        assert (root / OBSERVATIONS_PATH).is_file()
        assert not (root / TRUTH_PATH).exists()
        return reference_truth()

    manifest = build_agent_authority_run_receipt(
        root,
        pre_execution_artifacts=AgentAuthorityPreExecutionArtifactsV1(
            reference_plan(), reference_stimuli()
        ),
        source_public=canonical_json_bytes(reference_stimuli()),
        adapter=lambda payload: payload,
        runner=runner,
        observation_normalizer=normalizer,
        truth_loader=truth_loader,
        metadata=reference_metadata(),
    )
    assert events == ["runner", "normalizer", "truth", "normalizer"]
    assert manifest.evaluation_status is EvaluationStatus.EVALUATED


def test_validator_rejects_role_schema_and_scoring_indexes(
    receipt_template: Path,
    tmp_path: Path,
) -> None:
    role = _copy_receipt(receipt_template, tmp_path / "role")
    manifest = _manifest(role)
    artifacts = (
        manifest.artifacts[0].model_copy(update={"role": "wrong"}),
        *manifest.artifacts[1:],
    )
    _write_manifest(role, manifest.model_copy(update={"artifacts": artifacts}))
    with pytest.raises(ReceiptIntegrityError, match="roles or paths"):
        validate_agent_authority_run_receipt(role)

    schema = _copy_receipt(receipt_template, tmp_path / "schema")
    manifest = _manifest(schema)
    bindings = (
        manifest.schema_versions[0].model_copy(update={"version": "wrong"}),
        *manifest.schema_versions[1:],
    )
    _write_manifest(schema, manifest.model_copy(update={"schema_versions": bindings}))
    with pytest.raises(ReceiptIntegrityError, match="schema bindings"):
        validate_agent_authority_run_receipt(schema)

    scoring = _copy_receipt(receipt_template, tmp_path / "scoring")
    manifest = _manifest(scoring)
    _write_manifest(
        scoring,
        manifest.model_copy(
            update={
                "scoring_formula_versions": (
                    VersionBindingV2(role="agent_authority_lab", version="wrong"),
                )
            }
        ),
    )
    with pytest.raises(ReceiptIntegrityError, match="scoring formula"):
        validate_agent_authority_run_receipt(scoring)


def test_validator_requires_execution_v2(
    receipt_template: Path,
    tmp_path: Path,
) -> None:
    root = _copy_receipt(receipt_template, tmp_path)
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
    _write_model_and_reindex(root, EXECUTION_PATH, execution_v1)
    with pytest.raises(ReceiptIntegrityError, match="requires execution v2"):
        validate_agent_authority_run_receipt(root)


def test_validator_reports_cross_artifact_reference_failures_as_integrity_errors(
    receipt_template: Path,
    tmp_path: Path,
) -> None:
    root = _copy_receipt(receipt_template, tmp_path)
    observations = AgentAuthorityRunObservationsV1.model_validate_json(
        (root / OBSERVATIONS_PATH).read_bytes()
    )
    changed = observations.model_copy(update={"run_id": "different"})
    _write_model_and_reindex(root, OBSERVATIONS_PATH, changed)
    with pytest.raises(ReceiptIntegrityError, match="relationships are invalid"):
        validate_agent_authority_run_receipt(root)


def _mutate_product_input(
    root: Path,
    mutation: Callable[[AgentAuthorityProductInputV1], AgentAuthorityProductInputV1],
) -> None:
    model = AgentAuthorityProductInputV1.model_validate_json(
        (root / PRODUCT_INPUT_PATH).read_bytes()
    )
    _write_model_and_reindex(root, PRODUCT_INPUT_PATH, mutation(model))


def _mutate_execution(
    root: Path, mutation: Callable[[ExecutionReceiptV2], ExecutionReceiptV2]
) -> None:
    model = ExecutionReceiptV2.model_validate_json((root / EXECUTION_PATH).read_bytes())
    _write_model_and_reindex(root, EXECUTION_PATH, mutation(model))


def test_validator_rejects_every_digest_binding_position(
    receipt_template: Path,
    tmp_path: Path,
) -> None:
    plan_envelope = _copy_receipt(receipt_template, tmp_path / "plan-envelope")
    _mutate_product_input(
        plan_envelope,
        lambda item: item.model_copy(
            update={"run_plan_digest": DigestV2(value="1" * 64)}
        ),
    )
    with pytest.raises(ReceiptIntegrityError, match="run-plan digest"):
        validate_agent_authority_run_receipt(plan_envelope)

    plan_execution = _copy_receipt(receipt_template, tmp_path / "plan-execution")
    _mutate_execution(
        plan_execution,
        lambda item: item.model_copy(
            update={"run_plan_digest": DigestV2(value="2" * 64)}
        ),
    )
    with pytest.raises(ReceiptIntegrityError, match="run-plan digest"):
        validate_agent_authority_run_receipt(plan_execution)

    for name, mutate in (
        (
            "stimulus-plan",
            _change_plan_stimulus_digest_and_rebind_plan_digest,
        ),
        (
            "stimulus-envelope",
            lambda root: _mutate_product_input(
                root,
                lambda item: item.model_copy(
                    update={"stimulus_digest": DigestV2(value="4" * 64)}
                ),
            ),
        ),
        (
            "stimulus-execution",
            lambda root: _mutate_execution(
                root,
                lambda item: item.model_copy(
                    update={"stimulus_digest": DigestV2(value="5" * 64)}
                ),
            ),
        ),
        ("stimulus-calculated", _change_stimulus_without_rebinding_digest),
    ):
        root = _copy_receipt(receipt_template, tmp_path / name)
        mutate(root)
        with pytest.raises(ReceiptIntegrityError, match="stimulus digest"):
            validate_agent_authority_run_receipt(root)


def _change_stimulus_without_rebinding_digest(root: Path) -> None:
    product_input = AgentAuthorityProductInputV1.model_validate_json(
        (root / PRODUCT_INPUT_PATH).read_bytes()
    )
    rows = list(product_input.stimuli)
    replay = rows[1]
    rows[1] = replay.model_copy(
        update={"payload": replay.payload.model_copy(update={"expiry_tick": 11})}
    )
    changed = product_input.model_copy(update={"stimuli": tuple(rows)})
    _write_model_and_reindex(root, PRODUCT_INPUT_PATH, changed)


def _change_plan_stimulus_digest_and_rebind_plan_digest(root: Path) -> None:
    changed_plan = reference_plan().model_copy(
        update={"stimulus_set_digest": DigestV2(value="3" * 64)}
    )
    _write_bytes_and_reindex(root, RUN_PLAN_PATH, canonical_json_bytes(changed_plan))
    plan_digest = digest_bytes_v2((root / RUN_PLAN_PATH).read_bytes())
    _mutate_product_input(
        root,
        lambda item: item.model_copy(update={"run_plan_digest": plan_digest}),
    )
    _mutate_execution(
        root,
        lambda item: item.model_copy(
            update={
                "run_plan_digest": plan_digest,
                "product_input_digest": digest_bytes_v2(
                    (root / PRODUCT_INPUT_PATH).read_bytes()
                ),
            }
        ),
    )


@pytest.mark.parametrize(
    "field",
    ["source_public_digest", "product_input_digest", "product_output_digest"],
)
def test_validator_rejects_each_execution_artifact_digest(
    receipt_template: Path,
    tmp_path: Path,
    field: str,
) -> None:
    root = _copy_receipt(receipt_template, tmp_path)
    _mutate_execution(
        root,
        lambda item: item.model_copy(update={field: DigestV2(value="6" * 64)}),
    )
    with pytest.raises(ReceiptIntegrityError, match="artifact digests"):
        validate_agent_authority_run_receipt(root)


def test_validator_rejects_system_evaluation_and_manifest_identity_mismatches(
    receipt_template: Path,
    tmp_path: Path,
) -> None:
    systems = _copy_receipt(receipt_template, tmp_path / "systems")
    _mutate_execution(
        systems,
        lambda item: item.model_copy(
            update={"systems_under_test": (item.systems_under_test[0],)}
        ),
    )
    with pytest.raises(ReceiptIntegrityError, match="systems differ"):
        validate_agent_authority_run_receipt(systems)

    evaluation = _copy_receipt(receipt_template, tmp_path / "evaluation")
    manifest = _manifest(evaluation)
    _write_manifest(
        evaluation,
        manifest.model_copy(
            update={"evaluation_status": EvaluationStatus.NOT_EVALUATED}
        ),
    )
    with pytest.raises(ReceiptIntegrityError, match="receipt is evaluated"):
        validate_agent_authority_run_receipt(evaluation)

    run_id = _copy_receipt(receipt_template, tmp_path / "run-id")
    manifest = _manifest(run_id)
    _write_manifest(
        run_id,
        manifest.model_copy(
            update={"run": manifest.run.model_copy(update={"run_id": "different"})}
        ),
    )
    with pytest.raises(ReceiptIntegrityError, match="manifest run identifier"):
        validate_agent_authority_run_receipt(run_id)

    benchmark = _copy_receipt(receipt_template, tmp_path / "benchmark")
    manifest = _manifest(benchmark)
    _write_manifest(
        benchmark,
        manifest.model_copy(
            update={
                "benchmark": manifest.benchmark.model_copy(
                    update={"family": "different"}
                )
            }
        ),
    )
    with pytest.raises(ReceiptIntegrityError, match="benchmark identity"):
        validate_agent_authority_run_receipt(benchmark)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("boundary", "different"),
        ("adapter_name", "different"),
        ("adapter_version", "different"),
        ("adapter_source_digest", DigestV2(value="7" * 64)),
    ],
)
def test_validator_rejects_each_execution_provenance_binding(
    receipt_template: Path,
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    root = _copy_receipt(receipt_template, tmp_path)
    _mutate_execution(root, lambda item: item.model_copy(update={field: value}))
    with pytest.raises(ReceiptIntegrityError, match="execution provenance"):
        validate_agent_authority_run_receipt(root)


def test_validator_rejects_execution_status_binding(
    receipt_template: Path,
    tmp_path: Path,
) -> None:
    root = _copy_receipt(receipt_template, tmp_path)
    _mutate_execution(
        root,
        lambda item: item.model_copy(
            update={"exit_code": 1, "status": ExecutionStatus.FAILED}
        ),
    )
    with pytest.raises(ReceiptIntegrityError, match="execution provenance"):
        validate_agent_authority_run_receipt(root)


def test_validator_replays_adapter_normalizer_and_report(
    receipt_template: Path,
    tmp_path: Path,
) -> None:
    altered_stimuli = reference_stimuli().model_dump(mode="json")
    altered_stimuli["stimuli"][0]["stimulus_id"] = "different"
    with pytest.raises(ReceiptIntegrityError, match="adapter output"):
        validate_agent_authority_run_receipt(
            receipt_template,
            adapter=lambda _source: canonical_json_bytes(
                type(reference_stimuli()).model_validate(altered_stimuli)
            ),
        )

    changed_observations = reference_observations().model_copy(
        update={"limitations": ("different",)}
    )
    with pytest.raises(ReceiptIntegrityError, match="normalized product output"):
        validate_agent_authority_run_receipt(
            receipt_template,
            observation_normalizer=lambda _output, _plan, _stimuli: (
                changed_observations
            ),
        )

    report_root = _copy_receipt(receipt_template, tmp_path)
    report = AgentAuthorityLabReportV1.model_validate_json(
        (report_root / EVALUATION_PATH).read_bytes()
    )
    _write_model_and_reindex(
        report_root,
        EVALUATION_PATH,
        report.model_copy(update={"limitations": ("different",)}),
    )
    with pytest.raises(ReceiptIntegrityError, match="evaluation does not replay"):
        validate_agent_authority_run_receipt(report_root)
