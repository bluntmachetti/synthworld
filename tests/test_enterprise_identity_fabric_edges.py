"""Negative vectors for identity-fabric contract and reference tripwires."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.identity_fabric.baselines import (
    _recorded_lifecycle,
    trust_recorded_state_baseline,
)
from synthworld.enterprise.identity_fabric.metrics import (
    evaluate_enterprise_identity_fabric,
)
from synthworld.enterprise.identity_fabric.models import (
    EnterpriseIdentityFabricPredictionV1,
)
from synthworld.enterprise.identity_fabric.projection import (
    _account_status,
    _validate_evaluator_checkpoint,
)
from synthworld.enterprise.identity_fabric.reference import (
    REFERENCE_ACCUMULATION_CELL_ID,
    REFERENCE_APPROVED_EXCEPTION_CELL_ID,
    _require_discriminating_truth,
    _require_frozen_inputs,
    reference_enterprise_identity_fabric,
)
from synthworld.enterprise.rbac.common import BindingStatus, LifecycleStatus


def _validate_changed(model: BaseModel, **updates: object) -> None:
    document = model.model_dump(mode="python")
    document.update(updates)
    type(model).model_validate(document)


def test_checkpoint_models_reject_noncontiguous_and_duplicate_coordinates() -> None:
    reference = reference_enterprise_identity_fabric()
    public = reference.public
    truth = reference.evaluator.truth
    evaluator = reference.evaluator

    benchmark_refs = public.benchmark.checkpoints
    with pytest.raises(ValidationError, match="checkpoint_sequence_not_contiguous"):
        _validate_changed(
            public.benchmark,
            checkpoints=(
                benchmark_refs[0],
                benchmark_refs[1].model_copy(update={"sequence": 2}),
            ),
        )
    with pytest.raises(ValidationError, match=r"duplicate.*checkpoint"):
        _validate_changed(
            public.benchmark,
            checkpoints=(
                benchmark_refs[0],
                benchmark_refs[1].model_copy(
                    update={"checkpoint_id": benchmark_refs[0].checkpoint_id}
                ),
            ),
        )

    public_checkpoints = public.checkpoints
    with pytest.raises(ValidationError, match="public_checkpoint_sequence"):
        _validate_changed(
            public,
            checkpoints=(
                public_checkpoints[0],
                public_checkpoints[1].model_copy(update={"sequence": 2}),
            ),
        )
    with pytest.raises(ValidationError, match=r"duplicate.*public_checkpoint"):
        _validate_changed(
            public,
            checkpoints=(
                public_checkpoints[0],
                public_checkpoints[1].model_copy(
                    update={"checkpoint_id": public_checkpoints[0].checkpoint_id}
                ),
            ),
        )
    with pytest.raises(ValidationError, match="invariant_input_digest"):
        _validate_changed(
            public,
            benchmark=public.benchmark.model_copy(
                update={"invariant_input_digest": synthetic_digest(b"wrong\n")}
            ),
        )
    with pytest.raises(ValidationError, match="checkpoint_input_digest"):
        _validate_changed(
            public,
            benchmark=public.benchmark.model_copy(
                update={
                    "checkpoints": (
                        benchmark_refs[0].model_copy(
                            update={
                                "checkpoint_input_digest": synthetic_digest(b"wrong\n")
                            }
                        ),
                        benchmark_refs[1],
                    )
                }
            ),
        )

    truth_checkpoints = truth.checkpoints
    with pytest.raises(ValidationError, match="truth_sequence_not_contiguous"):
        _validate_changed(
            truth,
            checkpoints=(
                truth_checkpoints[0],
                truth_checkpoints[1].model_copy(update={"sequence": 2}),
            ),
        )
    with pytest.raises(ValidationError, match=r"duplicate.*truth_checkpoint"):
        _validate_changed(
            truth,
            checkpoints=(
                truth_checkpoints[0],
                truth_checkpoints[1].model_copy(
                    update={"checkpoint_id": truth_checkpoints[0].checkpoint_id}
                ),
            ),
        )

    evaluator_checkpoints = evaluator.checkpoints
    with pytest.raises(ValidationError, match="evaluator_sequence_not_contiguous"):
        _validate_changed(
            evaluator,
            checkpoints=(
                evaluator_checkpoints[0],
                evaluator_checkpoints[1].model_copy(update={"sequence": 2}),
            ),
        )
    with pytest.raises(ValidationError, match=r"duplicate.*evaluator_checkpoint"):
        _validate_changed(
            evaluator,
            checkpoints=(
                evaluator_checkpoints[0],
                evaluator_checkpoints[1].model_copy(
                    update={"checkpoint_id": evaluator_checkpoints[0].checkpoint_id}
                ),
            ),
        )


def test_evaluator_model_rejects_each_truth_binding_mismatch() -> None:
    reference = reference_enterprise_identity_fabric()
    evaluator = reference.evaluator
    with pytest.raises(ValidationError, match="truth_public_input_digest"):
        _validate_changed(
            evaluator,
            public_input_digest=synthetic_digest(b"wrong public\n"),
        )
    with pytest.raises(ValidationError, match="truth_binding_digest"):
        changed_truth = evaluator.truth.model_copy(
            update={"canonical_binding_truth_digest": synthetic_digest(b"wrong\n")}
        )
        _validate_changed(evaluator, truth=changed_truth)
    with pytest.raises(ValidationError, match="truth_checkpoint_inventory"):
        changed_checkpoint = evaluator.checkpoints[0].model_copy(
            update={"checkpoint_id": "different-checkpoint"}
        )
        _validate_changed(
            evaluator,
            checkpoints=(changed_checkpoint, evaluator.checkpoints[1]),
        )


def test_empty_required_metric_family_fails_explicitly() -> None:
    reference = reference_enterprise_identity_fabric()
    first = reference.evaluator.truth.checkpoints[0].model_copy(
        update={"membership": ()}
    )
    changed_truth = reference.evaluator.truth.model_copy(
        update={"checkpoints": (first, reference.evaluator.truth.checkpoints[1])}
    )
    changed_artifacts = reference.evaluator.model_copy(update={"truth": changed_truth})
    with pytest.raises(ValueError, match="requires nonempty selected coverage"):
        evaluate_enterprise_identity_fabric(
            artifacts=changed_artifacts,
            predictions=EnterpriseIdentityFabricPredictionV1(
                benchmark_digest=changed_truth.benchmark_digest
            ),
        )


def test_account_helpers_cover_absent_and_not_yet_valid_observations() -> None:
    reference = reference_enterprise_identity_fabric()
    public_checkpoint = reference.public.checkpoints[0]
    first_observation = public_checkpoint.directory_rbac_kernel.account_observations[0]
    assert _account_status(
        canonical_principal_id="canonical", observation=None, tick=0
    ) == (BindingStatus.MISSING, LifecycleStatus.INACTIVE)
    future = first_observation.model_copy(update={"valid_from_tick": 10})
    assert (
        _account_status(
            canonical_principal_id=first_observation.observed_principal_id
            or "canonical",
            observation=future,
            tick=0,
        )[1]
        is LifecycleStatus.NOT_YET_VALID
    )
    assert _recorded_lifecycle(future, 0) is LifecycleStatus.NOT_YET_VALID

    kernel_without_first = public_checkpoint.directory_rbac_kernel.model_copy(
        update={
            "account_observations": (
                public_checkpoint.directory_rbac_kernel.account_observations[1:]
            )
        }
    )
    changed_checkpoint = public_checkpoint.model_copy(
        update={"directory_rbac_kernel": kernel_without_first}
    )
    changed_public = reference.public.model_copy(
        update={"checkpoints": (changed_checkpoint, reference.public.checkpoints[1])}
    )
    prediction = trust_recorded_state_baseline(changed_public)
    changed_rows = next(
        item
        for item in prediction.checkpoints
        if item.checkpoint_id == changed_checkpoint.checkpoint_id
    ).accounts
    missing_account = first_observation.account_id
    queries = {
        item.query_id: item
        for item in reference.public.benchmark.account_queries
        if item.checkpoint_id == changed_checkpoint.checkpoint_id
    }
    assert all(
        item.binding_status is BindingStatus.MISSING
        and item.lifecycle_status is LifecycleStatus.INACTIVE
        for item in changed_rows
        if queries[item.query_id].account_id == missing_account
    )


def test_truth_validation_requires_all_native_composition_components() -> None:
    reference = reference_enterprise_identity_fabric()
    public_checkpoint = reference.public.checkpoints[0]
    evaluator_checkpoint = reference.evaluator.checkpoints[0]
    composition = public_checkpoint.composition.model_copy(update={"abac": None})
    authorization_kernel = public_checkpoint.authorization_kernel.model_copy(
        update={
            "composition_digest": synthetic_digest(canonical_json_bytes(composition))
        }
    )
    changed_public_checkpoint = public_checkpoint.model_copy(
        update={
            "composition": composition,
            "authorization_kernel": authorization_kernel,
        }
    )
    access_state = evaluator_checkpoint.access_state.model_copy(
        update={
            "composition_digest": synthetic_digest(canonical_json_bytes(composition)),
            "authorization_kernel_digest": synthetic_digest(
                canonical_json_bytes(authorization_kernel)
            ),
        }
    )
    changed_evaluator_checkpoint = evaluator_checkpoint.model_copy(
        update={"access_state": access_state}
    )
    with pytest.raises(ValueError, match="composition_component_missing"):
        _validate_evaluator_checkpoint(
            public=reference.public,
            public_checkpoint=changed_public_checkpoint,
            evaluator=changed_evaluator_checkpoint,
            binding_digest=synthetic_digest(
                canonical_json_bytes(reference.evaluator.canonical_binding_truth)
            ),
        )


def test_reference_freeze_and_discriminator_tripwires_fail_closed() -> None:
    reference = reference_enterprise_identity_fabric()
    universe_bytes = canonical_json_bytes(reference.public.invariant.universe)
    corpus_bytes = canonical_json_bytes(reference.public.invariant.corpus)
    with pytest.raises(RuntimeError, match="frozen PR2 universe"):
        _require_frozen_inputs(universe_bytes=b"wrong\n", corpus_bytes=corpus_bytes)
    with pytest.raises(RuntimeError, match="frozen PR3 corpus"):
        _require_frozen_inputs(universe_bytes=universe_bytes, corpus_bytes=b"wrong\n")

    query_by_id = {
        item.query_id: item for item in reference.public.benchmark.access_queries
    }
    baseline = reference.evaluator.truth.checkpoints[0]
    approved_query_id = next(
        item.query_id
        for item in baseline.access
        if query_by_id[item.query_id].cell_id == REFERENCE_APPROVED_EXCEPTION_CELL_ID
    )
    changed_access = tuple(
        item.model_copy(update={"approved_exception": False})
        if item.query_id == approved_query_id
        else item
        for item in baseline.access
    )
    changed_checkpoint = baseline.model_copy(update={"access": changed_access})
    changed_truth = reference.evaluator.truth.model_copy(
        update={
            "checkpoints": (
                changed_checkpoint,
                reference.evaluator.truth.checkpoints[1],
            )
        }
    )
    with pytest.raises(RuntimeError, match="approved-exception discriminator"):
        _require_discriminating_truth(
            reference.public,
            reference.evaluator.model_copy(update={"truth": changed_truth}),
        )

    accumulation_query_id = next(
        item.query_id
        for item in baseline.access
        if query_by_id[item.query_id].cell_id == REFERENCE_ACCUMULATION_CELL_ID
    )
    changed_access = tuple(
        item.model_copy(update={"outside_intent": True})
        if item.query_id == accumulation_query_id
        else item
        for item in baseline.access
    )
    changed_checkpoint = baseline.model_copy(update={"access": changed_access})
    changed_truth = reference.evaluator.truth.model_copy(
        update={
            "checkpoints": (
                changed_checkpoint,
                reference.evaluator.truth.checkpoints[1],
            )
        }
    )
    with pytest.raises(RuntimeError, match="privilege-accumulation discriminator"):
        _require_discriminating_truth(
            reference.public,
            reference.evaluator.model_copy(update={"truth": changed_truth}),
        )

    changed_truth = reference.evaluator.truth.model_copy(
        update={
            "accumulation": tuple(
                item.model_copy(update={"accumulated_cell_ids": ()})
                for item in reference.evaluator.truth.accumulation
            )
        }
    )
    with pytest.raises(RuntimeError, match="accumulation truth"):
        _require_discriminating_truth(
            reference.public,
            reference.evaluator.model_copy(update={"truth": changed_truth}),
        )
