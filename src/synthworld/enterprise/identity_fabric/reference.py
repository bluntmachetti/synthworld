"""Deterministic two-checkpoint reference pack for issue #7."""

from __future__ import annotations

from dataclasses import dataclass

from synthworld.enterprise.authorization.compiler import (
    compile_enterprise_access_state,
    compile_enterprise_authorization_kernel,
    compose_enterprise_authorization,
)
from synthworld.enterprise.authorization.models import (
    AuthorizationEvaluationProfileV1,
    CompiledEnterpriseAccessStateV1,
    EnterpriseAuthorizationCompositionV1,
    EnterpriseAuthorizationKernelV1,
)
from synthworld.enterprise.authorization.reference import (
    ReferenceEnterpriseAuthorizationInputsV1,
    reference_enterprise_authorization_inputs,
)
from synthworld.enterprise.authorization_common import (
    AuthorizationEvaluationProfileKind,
    RuleEffect,
)
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.identity_fabric.models import (
    EnterpriseIdentityFabricEvaluatorArtifactsV1,
    EnterpriseIdentityFabricPublicInputV1,
    IdentityFabricCheckpointEvaluatorArtifactV1,
    IdentityFabricCheckpointPublicInputV1,
    IdentityFabricInvariantPublicInputV1,
)
from synthworld.enterprise.identity_fabric.projection import (
    compile_enterprise_identity_fabric_truth,
    project_enterprise_identity_fabric_public,
)
from synthworld.enterprise.rebac.common import RebacRelation
from synthworld.enterprise.rebac.compiler import compile_enterprise_rebac_truth
from synthworld.enterprise.rebac.models import (
    CompiledEnterpriseRebacTruthV1,
    DirectSubjectRelationV1,
    EnterpriseRebacStateOverlayV1,
    RelationTupleV1,
)

REFERENCE_IDENTITY_FABRIC_BASELINE_CHECKPOINT = "baseline"
REFERENCE_IDENTITY_FABRIC_ACCUMULATED_CHECKPOINT = "accumulated"
REFERENCE_APPROVED_EXCEPTION_CELL_ID = "c79ada55-d9d2-5319-a869-8fdd8074718a"
REFERENCE_ACCUMULATION_CELL_ID = "b5afa2e1-05d8-598a-9c26-24503ad72b84"
REFERENCE_UNIVERSE_SHA256 = (
    "b4eae423689ede98d98858cae004f98d07fa5b0ac4774858500a4ba257946f4a"
)
REFERENCE_CORPUS_SHA256 = (
    "1293dc2a22820f1e0b72f85c7c17028872c424b7483223f50b6f4dd822acf1d6"
)


@dataclass(frozen=True, slots=True)
class ReferenceEnterpriseIdentityFabricV1:
    authorization: ReferenceEnterpriseAuthorizationInputsV1
    evaluation_profile: AuthorizationEvaluationProfileV1
    baseline_rebac_truth: CompiledEnterpriseRebacTruthV1
    baseline_composition: EnterpriseAuthorizationCompositionV1
    baseline_authorization_kernel: EnterpriseAuthorizationKernelV1
    baseline_access_state: CompiledEnterpriseAccessStateV1
    accumulated_rebac_state: EnterpriseRebacStateOverlayV1
    accumulated_rebac_truth: CompiledEnterpriseRebacTruthV1
    accumulated_composition: EnterpriseAuthorizationCompositionV1
    accumulated_authorization_kernel: EnterpriseAuthorizationKernelV1
    accumulated_access_state: CompiledEnterpriseAccessStateV1
    public: EnterpriseIdentityFabricPublicInputV1
    evaluator: EnterpriseIdentityFabricEvaluatorArtifactsV1


def reference_enterprise_identity_fabric() -> ReferenceEnterpriseIdentityFabricV1:
    """Build a fixed two-checkpoint pack without resizing atoms or cells."""

    authorization = reference_enterprise_authorization_inputs()
    rbac = authorization.rbac
    universe = rbac.universe_result.public_universe
    corpus = rbac.corpus_result.public_corpus
    binding = rbac.universe_result.evaluator_canonical_binding_truth
    _require_frozen_inputs(
        universe_bytes=canonical_json_bytes(universe),
        corpus_bytes=canonical_json_bytes(corpus),
    )

    evaluation_profile = AuthorizationEvaluationProfileV1(
        evaluation_corpus_digest=(
            authorization.evaluation_profile.evaluation_corpus_digest
        ),
        cells=tuple(
            item.model_copy(update={"profile": AuthorizationEvaluationProfileKind.RBAC})
            if item.cell_id == REFERENCE_APPROVED_EXCEPTION_CELL_ID
            else item
            for item in authorization.evaluation_profile.cells
        ),
    )
    baseline_composition = compose_enterprise_authorization(
        directory_rbac_truth=authorization.directory_rbac_truth,
        abac_truth=authorization.abac_truth,
        rebac_truth=authorization.rebac_truth,
    )
    baseline_kernel = compile_enterprise_authorization_kernel(
        universe=universe,
        corpus=corpus,
        composition=baseline_composition,
        evaluation_profile=evaluation_profile,
    )
    baseline_access = compile_enterprise_access_state(
        universe=universe,
        canonical_binding_truth=binding,
        corpus=corpus,
        composition=baseline_composition,
        directory_rbac_truth=authorization.directory_rbac_truth,
        abac_truth=authorization.abac_truth,
        rebac_truth=authorization.rebac_truth,
        evaluation_profile=evaluation_profile,
    )

    accumulated_rebac_state = _accumulated_rebac_state(authorization)
    accumulated_rebac_truth = compile_enterprise_rebac_truth(
        universe=universe,
        corpus=corpus,
        rebac_state=accumulated_rebac_state,
        rebac_intent=authorization.rebac_intent,
    )
    accumulated_composition = compose_enterprise_authorization(
        directory_rbac_truth=authorization.directory_rbac_truth,
        abac_truth=authorization.abac_truth,
        rebac_truth=accumulated_rebac_truth,
    )
    accumulated_kernel = compile_enterprise_authorization_kernel(
        universe=universe,
        corpus=corpus,
        composition=accumulated_composition,
        evaluation_profile=evaluation_profile,
    )
    accumulated_access = compile_enterprise_access_state(
        universe=universe,
        canonical_binding_truth=binding,
        corpus=corpus,
        composition=accumulated_composition,
        directory_rbac_truth=authorization.directory_rbac_truth,
        abac_truth=authorization.abac_truth,
        rebac_truth=accumulated_rebac_truth,
        evaluation_profile=evaluation_profile,
    )

    invariant = IdentityFabricInvariantPublicInputV1(
        universe=universe,
        corpus=corpus,
        directory_rbac_intent=rbac.intent,
        rbac_session_state=rbac.session_state,
        abac_intent=authorization.abac_intent,
        rebac_intent=authorization.rebac_intent,
        evaluation_profile=evaluation_profile,
    )
    public_checkpoints = (
        IdentityFabricCheckpointPublicInputV1(
            checkpoint_id=REFERENCE_IDENTITY_FABRIC_BASELINE_CHECKPOINT,
            sequence=0,
            directory_rbac_kernel=rbac.kernel,
            abac_state=authorization.abac_state,
            rebac_state=authorization.rebac_state,
            composition=baseline_composition,
            authorization_kernel=baseline_kernel,
        ),
        IdentityFabricCheckpointPublicInputV1(
            checkpoint_id=REFERENCE_IDENTITY_FABRIC_ACCUMULATED_CHECKPOINT,
            sequence=1,
            directory_rbac_kernel=rbac.kernel,
            abac_state=authorization.abac_state,
            rebac_state=accumulated_rebac_state,
            composition=accumulated_composition,
            authorization_kernel=accumulated_kernel,
        ),
    )
    public = project_enterprise_identity_fabric_public(
        invariant=invariant, checkpoints=public_checkpoints
    )
    evaluator_checkpoints = (
        IdentityFabricCheckpointEvaluatorArtifactV1(
            checkpoint_id=REFERENCE_IDENTITY_FABRIC_BASELINE_CHECKPOINT,
            sequence=0,
            directory_rbac_truth=authorization.directory_rbac_truth,
            abac_truth=authorization.abac_truth,
            rebac_truth=authorization.rebac_truth,
            access_state=baseline_access,
        ),
        IdentityFabricCheckpointEvaluatorArtifactV1(
            checkpoint_id=REFERENCE_IDENTITY_FABRIC_ACCUMULATED_CHECKPOINT,
            sequence=1,
            directory_rbac_truth=authorization.directory_rbac_truth,
            abac_truth=authorization.abac_truth,
            rebac_truth=accumulated_rebac_truth,
            access_state=accumulated_access,
        ),
    )
    evaluator = compile_enterprise_identity_fabric_truth(
        public=public,
        canonical_binding_truth=binding,
        checkpoints=evaluator_checkpoints,
    )
    _require_discriminating_truth(public, evaluator)
    return ReferenceEnterpriseIdentityFabricV1(
        authorization=authorization,
        evaluation_profile=evaluation_profile,
        baseline_rebac_truth=authorization.rebac_truth,
        baseline_composition=baseline_composition,
        baseline_authorization_kernel=baseline_kernel,
        baseline_access_state=baseline_access,
        accumulated_rebac_state=accumulated_rebac_state,
        accumulated_rebac_truth=accumulated_rebac_truth,
        accumulated_composition=accumulated_composition,
        accumulated_authorization_kernel=accumulated_kernel,
        accumulated_access_state=accumulated_access,
        public=public,
        evaluator=evaluator,
    )


def _accumulated_rebac_state(
    authorization: ReferenceEnterpriseAuthorizationInputsV1,
) -> EnterpriseRebacStateOverlayV1:
    universe = authorization.rbac.universe_result.public_universe
    corpus = authorization.rbac.corpus_result.public_corpus
    cell = next(
        item
        for item in corpus.evaluation_cells
        if item.cell_id == REFERENCE_ACCUMULATION_CELL_ID
    )
    atom = next(
        item
        for item in universe.access_atoms
        if item.access_atom_id == cell.access_atom_id
    )
    subject = next(
        item for item in universe.access_subjects if item.subject_id == atom.subject_id
    )
    new_tuple = RelationTupleV1(
        tuple_id="identity-fabric-accumulated-own",
        tenant_id=subject.tenant_id,
        subject_entity_id=atom.subject_id,
        relation=RebacRelation.OWNS,
        object_entity_id=atom.authorization_target_id,
        snapshot_id="identity-fabric-checkpoint-1",
        revision_id="r1",
        valid_from_tick=0,
    )
    new_rule = DirectSubjectRelationV1(
        rule_id="identity-fabric-accumulated-own",
        revision_id="r1",
        effect=RuleEffect.ALLOW,
        cell_ids=(cell.cell_id,),
        valid_from_tick=0,
        relation=RebacRelation.OWNS,
    )
    return EnterpriseRebacStateOverlayV1(
        identity_access_universe_digest=(
            authorization.rebac_state.identity_access_universe_digest
        ),
        evaluation_corpus_digest=(authorization.rebac_state.evaluation_corpus_digest),
        relation_tuples=(
            *authorization.rebac_state.relation_tuples,
            new_tuple,
        ),
        rules=(*authorization.rebac_state.rules, new_rule),
        unknown_evidence_cell_ids=(authorization.rebac_state.unknown_evidence_cell_ids),
    )


def _require_frozen_inputs(*, universe_bytes: bytes, corpus_bytes: bytes) -> None:
    if synthetic_digest(universe_bytes).value != REFERENCE_UNIVERSE_SHA256:
        raise RuntimeError("identity-fabric reference changed the frozen PR2 universe")
    if synthetic_digest(corpus_bytes).value != REFERENCE_CORPUS_SHA256:
        raise RuntimeError("identity-fabric reference changed the frozen PR3 corpus")


def _require_discriminating_truth(
    public: EnterpriseIdentityFabricPublicInputV1,
    evaluator: EnterpriseIdentityFabricEvaluatorArtifactsV1,
) -> None:
    query_by_id = {item.query_id: item for item in public.benchmark.access_queries}
    by_checkpoint = {
        checkpoint.checkpoint_id: {
            query_by_id[item.query_id].cell_id: item for item in checkpoint.access
        }
        for checkpoint in evaluator.truth.checkpoints
    }
    approved = by_checkpoint[REFERENCE_IDENTITY_FABRIC_BASELINE_CHECKPOINT][
        REFERENCE_APPROVED_EXCEPTION_CELL_ID
    ]
    before = by_checkpoint[REFERENCE_IDENTITY_FABRIC_BASELINE_CHECKPOINT][
        REFERENCE_ACCUMULATION_CELL_ID
    ]
    after = by_checkpoint[REFERENCE_IDENTITY_FABRIC_ACCUMULATED_CHECKPOINT][
        REFERENCE_ACCUMULATION_CELL_ID
    ]
    if not (
        approved.approved_exception
        and approved.outside_birthright
        and not approved.outside_intent
    ):
        raise RuntimeError("identity-fabric approved-exception discriminator missing")
    if before.outside_intent or not after.outside_intent:
        raise RuntimeError(
            "identity-fabric privilege-accumulation discriminator missing"
        )
    positive_accumulations = tuple(
        item for item in evaluator.truth.accumulation if item.accumulated_cell_ids
    )
    if len(positive_accumulations) != 1 or positive_accumulations[
        0
    ].accumulated_cell_ids != (REFERENCE_ACCUMULATION_CELL_ID,):
        raise RuntimeError("identity-fabric accumulation truth is not discriminating")


__all__ = [
    "REFERENCE_ACCUMULATION_CELL_ID",
    "REFERENCE_APPROVED_EXCEPTION_CELL_ID",
    "REFERENCE_IDENTITY_FABRIC_ACCUMULATED_CHECKPOINT",
    "REFERENCE_IDENTITY_FABRIC_BASELINE_CHECKPOINT",
    "ReferenceEnterpriseIdentityFabricV1",
    "reference_enterprise_identity_fabric",
]
