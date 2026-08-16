"""Small deterministic reference inputs for PR4 authorization components."""

from __future__ import annotations

from dataclasses import dataclass

from synthworld.enterprise.abac.common import (
    AbacEmploymentType,
    ActionClass,
    AssuranceLevel,
    AttributeValueState,
    InformationClassification,
    NetworkZone,
)
from synthworld.enterprise.abac.compiler import compile_enterprise_abac_truth
from synthworld.enterprise.abac.models import (
    AbacRuleV1,
    ActionClassFactV1,
    ActionClassIsV1,
    ActionIdFactV1,
    ActionIsV1,
    AssuranceAtLeastV1,
    AttributeFactV1,
    ClassificationWithinClearanceV1,
    CompiledEnterpriseAbacTruthV1,
    EmploymentTypeIsV1,
    EnterpriseAbacIntentOverlayV1,
    EnterpriseAbacStateOverlayV1,
    EnvironmentAssuranceLevelFactV1,
    EnvironmentNetworkZoneFactV1,
    NetworkZoneIsV1,
    ResourceClassificationFactV1,
    ResourceOwnerUnitIdFactV1,
    ResourceTargetKindFactV1,
    ResourceTenantIdFactV1,
    SameTenantV1,
    SubjectClearanceFactV1,
    SubjectEmploymentTypeFactV1,
    SubjectKindIsV1,
    SubjectPrincipalKindFactV1,
    SubjectTenantIdFactV1,
    SubjectUnitIdFactV1,
    SubjectUnitIsV1,
    SubjectUnitOwnsTargetV1,
    TargetKindIsV1,
)
from synthworld.enterprise.authorization.compiler import (
    compile_enterprise_access_state,
    compile_enterprise_authorization_kernel,
    compose_enterprise_authorization,
)
from synthworld.enterprise.authorization.metrics import (
    AuthorizationScoredDimension,
    EnterpriseAuthorizationEvaluationScopeV1,
    EnterpriseAuthorizationScopeCellV1,
)
from synthworld.enterprise.authorization.models import (
    AuthorizationCellProfileV1,
    AuthorizationEvaluationProfileV1,
    CompiledEnterpriseAccessStateV1,
    EnterpriseAuthorizationCompositionV1,
    EnterpriseAuthorizationKernelV1,
)
from synthworld.enterprise.authorization_common import (
    AuthorizationEvaluationProfileKind,
    FlatRuleOperator,
    RuleEffect,
)
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.models import (
    AccessSubjectKind,
    PrincipalKind,
    SyntheticDigestV1,
)
from synthworld.enterprise.rbac.compiler import (
    compile_enterprise_directory_rbac_truth,
)
from synthworld.enterprise.rbac.models import CompiledEnterpriseDirectoryRbacTruthV1
from synthworld.enterprise.rbac.reference import (
    ReferenceEnterpriseRbacInputsV1,
    reference_enterprise_rbac_inputs,
)
from synthworld.enterprise.rebac.common import RebacRelation
from synthworld.enterprise.rebac.compiler import compile_enterprise_rebac_truth
from synthworld.enterprise.rebac.models import (
    CompiledEnterpriseRebacTruthV1,
    DirectSubjectRelationV1,
    EnterpriseRebacIntentOverlayV1,
    EnterpriseRebacStateOverlayV1,
    GroupCollaborationV1,
    ManagerOfOwnerV1,
    RelationTupleV1,
)


@dataclass(frozen=True, slots=True)
class ReferenceEnterpriseAuthorizationInputsV1:
    rbac: ReferenceEnterpriseRbacInputsV1
    directory_rbac_truth: CompiledEnterpriseDirectoryRbacTruthV1
    abac_state: EnterpriseAbacStateOverlayV1
    abac_intent: EnterpriseAbacIntentOverlayV1
    abac_truth: CompiledEnterpriseAbacTruthV1
    rebac_state: EnterpriseRebacStateOverlayV1
    rebac_intent: EnterpriseRebacIntentOverlayV1
    rebac_truth: CompiledEnterpriseRebacTruthV1
    evaluation_profile: AuthorizationEvaluationProfileV1
    composition: EnterpriseAuthorizationCompositionV1
    authorization_kernel: EnterpriseAuthorizationKernelV1
    evaluation_scope: EnterpriseAuthorizationEvaluationScopeV1
    access_state: CompiledEnterpriseAccessStateV1


def reference_enterprise_authorization_inputs() -> (
    ReferenceEnterpriseAuthorizationInputsV1
):
    rbac = reference_enterprise_rbac_inputs()
    universe = rbac.universe_result.public_universe
    corpus = rbac.corpus_result.public_corpus
    directory_truth = compile_enterprise_directory_rbac_truth(
        universe=universe,
        canonical_binding_truth=rbac.universe_result.evaluator_canonical_binding_truth,
        corpus=corpus,
        directory_rbac_kernel=rbac.kernel,
        session_state=rbac.session_state,
        directory_rbac_intent=rbac.intent,
    )
    universe_digest = synthetic_digest(canonical_json_bytes(universe))
    corpus_digest = synthetic_digest(canonical_json_bytes(corpus))
    abac_state, abac_intent = _abac_inputs(rbac, universe_digest, corpus_digest)
    abac_truth = compile_enterprise_abac_truth(
        universe=universe,
        corpus=corpus,
        abac_state=abac_state,
        abac_intent=abac_intent,
    )
    rebac_state, rebac_intent = _rebac_inputs(rbac, universe_digest, corpus_digest)
    rebac_truth = compile_enterprise_rebac_truth(
        universe=universe,
        corpus=corpus,
        rebac_state=rebac_state,
        rebac_intent=rebac_intent,
    )
    profiles = tuple(AuthorizationEvaluationProfileKind)
    evaluation_profile = AuthorizationEvaluationProfileV1(
        evaluation_corpus_digest=corpus_digest,
        cells=tuple(
            AuthorizationCellProfileV1(
                cell_id=item.cell_id,
                profile=profiles[index % len(profiles)],
            )
            for index, item in enumerate(corpus.evaluation_cells)
        ),
    )
    composition = compose_enterprise_authorization(
        directory_rbac_truth=directory_truth,
        abac_truth=abac_truth,
        rebac_truth=rebac_truth,
    )
    kernel = compile_enterprise_authorization_kernel(
        universe=universe,
        corpus=corpus,
        composition=composition,
        evaluation_profile=evaluation_profile,
    )
    evaluation_scope = _evaluation_scope(rbac, kernel)
    access_state = compile_enterprise_access_state(
        universe=universe,
        canonical_binding_truth=rbac.universe_result.evaluator_canonical_binding_truth,
        corpus=corpus,
        composition=composition,
        directory_rbac_truth=directory_truth,
        abac_truth=abac_truth,
        rebac_truth=rebac_truth,
        evaluation_profile=evaluation_profile,
    )
    return ReferenceEnterpriseAuthorizationInputsV1(
        rbac=rbac,
        directory_rbac_truth=directory_truth,
        abac_state=abac_state,
        abac_intent=abac_intent,
        abac_truth=abac_truth,
        rebac_state=rebac_state,
        rebac_intent=rebac_intent,
        rebac_truth=rebac_truth,
        evaluation_profile=evaluation_profile,
        composition=composition,
        authorization_kernel=kernel,
        evaluation_scope=evaluation_scope,
        access_state=access_state,
    )


def _evaluation_scope(
    rbac: ReferenceEnterpriseRbacInputsV1,
    kernel: EnterpriseAuthorizationKernelV1,
) -> EnterpriseAuthorizationEvaluationScopeV1:
    """Select only dimensions derivable from the reference public artifacts."""

    universe = rbac.universe_result.public_universe
    corpus = rbac.corpus_result.public_corpus
    atom_by_id = {item.access_atom_id: item for item in universe.access_atoms}
    subject_kind_by_id = {
        item.subject_id: item.subject_kind for item in universe.access_subjects
    }
    corpus_cell_by_id = {item.cell_id: item for item in corpus.evaluation_cells}
    cells: list[EnterpriseAuthorizationScopeCellV1] = []
    for kernel_cell in kernel.cells:
        corpus_cell = corpus_cell_by_id[kernel_cell.cell_id]
        subject_kind = subject_kind_by_id[
            atom_by_id[corpus_cell.access_atom_id].subject_id
        ]
        dimensions = [
            AuthorizationScoredDimension.EFFECTIVE_DECISION,
            AuthorizationScoredDimension.POLICY_CONFLICT,
        ]
        if subject_kind is AccessSubjectKind.PRINCIPAL:
            dimensions.append(AuthorizationScoredDimension.FINAL_DECISION)
        else:
            dimensions.append(AuthorizationScoredDimension.LIFECYCLE_STATUS)
        cells.append(
            EnterpriseAuthorizationScopeCellV1(
                cell_id=kernel_cell.cell_id,
                scored_dimensions=tuple(dimensions),
            )
        )
    return EnterpriseAuthorizationEvaluationScopeV1(
        evaluation_corpus_digest=kernel.evaluation_corpus_digest,
        authorization_kernel_digest=synthetic_digest(canonical_json_bytes(kernel)),
        cells=tuple(cells),
    )


def _abac_inputs(
    rbac: ReferenceEnterpriseRbacInputsV1,
    universe_digest: SyntheticDigestV1,
    corpus_digest: SyntheticDigestV1,
) -> tuple[EnterpriseAbacStateOverlayV1, EnterpriseAbacIntentOverlayV1]:
    universe = rbac.universe_result.public_universe
    corpus = rbac.corpus_result.public_corpus
    atoms = {item.access_atom_id: item for item in universe.access_atoms}
    principals = {item.principal_id: item for item in universe.principals}
    access_subjects = {item.subject_id: item for item in universe.access_subjects}
    targets = {
        item.authorization_target_id: item for item in universe.authorization_targets
    }
    unit_ids = tuple(item.unit_id for item in universe.units)
    facts: list[AttributeFactV1] = []
    for index, cell in enumerate(corpus.evaluation_cells):
        atom = atoms[cell.access_atom_id]
        target = targets[atom.authorization_target_id]
        principal = principals.get(atom.subject_id)
        state = (
            AttributeValueState.KNOWN
            if principal is not None
            else AttributeValueState.UNKNOWN
        )
        facts.extend(
            (
                SubjectPrincipalKindFactV1(
                    fact_id=f"subject-kind-{index}",
                    cell_id=cell.cell_id,
                    value_state=state,
                    value=principal.principal_kind if principal else None,
                    revision_id="r1",
                    valid_from_tick=0,
                ),
                SubjectEmploymentTypeFactV1(
                    fact_id=f"employment-{index}",
                    cell_id=cell.cell_id,
                    value_state=AttributeValueState.KNOWN,
                    value=(
                        AbacEmploymentType.EMPLOYEE
                        if principal is not None
                        and principal.principal_kind is PrincipalKind.EMPLOYEE
                        else AbacEmploymentType.NOT_APPLICABLE
                    ),
                    revision_id="r1",
                    valid_from_tick=0,
                ),
                SubjectTenantIdFactV1(
                    fact_id=f"subject-tenant-{index}",
                    cell_id=cell.cell_id,
                    value_state=AttributeValueState.KNOWN,
                    value=access_subjects[atom.subject_id].tenant_id,
                    revision_id="r1",
                    valid_from_tick=0,
                ),
                SubjectUnitIdFactV1(
                    fact_id=f"subject-unit-{index}",
                    cell_id=cell.cell_id,
                    value_state=state,
                    value=principal.unit_id if principal else None,
                    revision_id="r1",
                    valid_from_tick=0,
                ),
                SubjectClearanceFactV1(
                    fact_id=f"clearance-{index}",
                    cell_id=cell.cell_id,
                    value_state=AttributeValueState.KNOWN,
                    value=InformationClassification.CONFIDENTIAL,
                    revision_id="r1",
                    valid_from_tick=0,
                ),
                ResourceTargetKindFactV1(
                    fact_id=f"target-kind-{index}",
                    cell_id=cell.cell_id,
                    value_state=AttributeValueState.KNOWN,
                    value=target.target_kind,
                    revision_id="r1",
                    valid_from_tick=0,
                ),
                ResourceTenantIdFactV1(
                    fact_id=f"resource-tenant-{index}",
                    cell_id=cell.cell_id,
                    value_state=AttributeValueState.KNOWN,
                    value=target.tenant_id,
                    revision_id="r1",
                    valid_from_tick=0,
                ),
                ResourceOwnerUnitIdFactV1(
                    fact_id=f"owner-unit-{index}",
                    cell_id=cell.cell_id,
                    value_state=AttributeValueState.KNOWN,
                    value=target.owner_unit_id,
                    revision_id="r1",
                    valid_from_tick=0,
                ),
                ResourceClassificationFactV1(
                    fact_id=f"classification-{index}",
                    cell_id=cell.cell_id,
                    value_state=AttributeValueState.KNOWN,
                    value=InformationClassification.INTERNAL,
                    revision_id="r1",
                    valid_from_tick=0,
                ),
                ActionIdFactV1(
                    fact_id=f"action-id-{index}",
                    cell_id=cell.cell_id,
                    value_state=AttributeValueState.KNOWN,
                    value=atom.action,
                    revision_id="r1",
                    valid_from_tick=0,
                ),
                ActionClassFactV1(
                    fact_id=f"action-class-{index}",
                    cell_id=cell.cell_id,
                    value_state=AttributeValueState.KNOWN,
                    value=(
                        ActionClass.READ if atom.action == "read" else ActionClass.WRITE
                    ),
                    revision_id="r1",
                    valid_from_tick=0,
                ),
                EnvironmentAssuranceLevelFactV1(
                    fact_id=f"assurance-{index}",
                    cell_id=cell.cell_id,
                    value_state=AttributeValueState.KNOWN,
                    value=AssuranceLevel.HIGH,
                    revision_id="r1",
                    valid_from_tick=0,
                ),
                EnvironmentNetworkZoneFactV1(
                    fact_id=f"network-{index}",
                    cell_id=cell.cell_id,
                    value_state=AttributeValueState.KNOWN,
                    value=(NetworkZone.PUBLIC if index == 1 else NetworkZone.INTERNAL),
                    revision_id="r1",
                    valid_from_tick=0,
                ),
            )
        )
    all_cells = tuple(item.cell_id for item in corpus.evaluation_cells)
    allow_rule = AbacRuleV1(
        rule_id="reference-allow",
        revision_id="r1",
        effect=RuleEffect.ALLOW,
        operator=FlatRuleOperator.ALL,
        cell_ids=all_cells,
        predicates=(
            SubjectKindIsV1(values=tuple(PrincipalKind)),
            EmploymentTypeIsV1(values=tuple(AbacEmploymentType)),
            SameTenantV1(),
            SubjectUnitIsV1(unit_ids=unit_ids),
            SubjectUnitOwnsTargetV1(),
            TargetKindIsV1(
                values=tuple(
                    item.target_kind for item in universe.authorization_targets[:1]
                )
            ),
            ClassificationWithinClearanceV1(),
            ActionIsV1(action_ids=("read", "write")),
            ActionClassIsV1(values=(ActionClass.READ, ActionClass.WRITE)),
            AssuranceAtLeastV1(minimum=AssuranceLevel.MEDIUM),
            NetworkZoneIsV1(values=(NetworkZone.INTERNAL,)),
        ),
        valid_from_tick=0,
    )
    deny_rule = AbacRuleV1(
        rule_id="reference-deny",
        revision_id="r1",
        effect=RuleEffect.DENY,
        operator=FlatRuleOperator.ANY,
        cell_ids=(all_cells[0], all_cells[1]),
        predicates=(NetworkZoneIsV1(values=(NetworkZone.INTERNAL,)),),
        valid_from_tick=0,
    )
    intended_rule = allow_rule.model_copy(
        update={"rule_id": "reference-intended-allow"}
    )
    return (
        EnterpriseAbacStateOverlayV1(
            identity_access_universe_digest=universe_digest,
            evaluation_corpus_digest=corpus_digest,
            attribute_facts=tuple(facts),
            rules=(allow_rule, deny_rule),
        ),
        EnterpriseAbacIntentOverlayV1(
            identity_access_universe_digest=universe_digest,
            evaluation_corpus_digest=corpus_digest,
            attribute_facts=tuple(facts),
            rules=(intended_rule,),
        ),
    )


def _rebac_inputs(
    rbac: ReferenceEnterpriseRbacInputsV1,
    universe_digest: SyntheticDigestV1,
    corpus_digest: SyntheticDigestV1,
) -> tuple[EnterpriseRebacStateOverlayV1, EnterpriseRebacIntentOverlayV1]:
    universe = rbac.universe_result.public_universe
    corpus = rbac.corpus_result.public_corpus
    atoms = {item.access_atom_id: item for item in universe.access_atoms}
    principal_cells = tuple(
        item
        for item in corpus.evaluation_cells
        if atoms[item.access_atom_id].subject_id
        in {principal.principal_id for principal in universe.principals}
        and next(
            principal
            for principal in universe.principals
            if principal.principal_id == atoms[item.access_atom_id].subject_id
        ).principal_kind
        is PrincipalKind.EMPLOYEE
    )
    direct_cell, group_cell, manager_cell = principal_cells[:3]
    direct_atom = atoms[direct_cell.access_atom_id]
    group_atom = atoms[group_cell.access_atom_id]
    manager_atom = atoms[manager_cell.access_atom_id]
    group = universe.groups[0]
    owner = next(
        item
        for item in universe.principals
        if item.principal_kind is PrincipalKind.EMPLOYEE
        and item.principal_id != manager_atom.subject_id
    )
    tenant_id = universe.tenants[0].tenant_id
    snapshot = "snapshot-1"
    tuples = (
        _tuple(
            "direct-own",
            direct_atom.subject_id,
            RebacRelation.OWNS,
            direct_atom.authorization_target_id,
            tenant_id,
            snapshot,
        ),
        _tuple(
            "group-member",
            group_atom.subject_id,
            RebacRelation.MEMBER_OF,
            group.group_id,
            tenant_id,
            snapshot,
        ),
        _tuple(
            "group-collaboration",
            group.group_id,
            RebacRelation.COLLABORATES_ON,
            group_atom.authorization_target_id,
            tenant_id,
            snapshot,
        ),
        _tuple(
            "manager",
            manager_atom.subject_id,
            RebacRelation.MANAGES,
            owner.principal_id,
            tenant_id,
            snapshot,
        ),
        _tuple(
            "manager-owner",
            owner.principal_id,
            RebacRelation.OWNS,
            manager_atom.authorization_target_id,
            tenant_id,
            snapshot,
        ),
        _tuple(
            "account-member",
            universe.accounts[0].account_id,
            RebacRelation.MEMBER_OF,
            group.group_id,
            tenant_id,
            snapshot,
        ),
        _tuple(
            "account-collaboration",
            universe.accounts[0].account_id,
            RebacRelation.COLLABORATES_ON,
            universe.authorization_targets[0].authorization_target_id,
            tenant_id,
            snapshot,
        ),
        _tuple(
            "unit-owner",
            universe.units[0].unit_id,
            RebacRelation.OWNS,
            universe.authorization_targets[0].authorization_target_id,
            tenant_id,
            snapshot,
        ),
    )
    rules = (
        DirectSubjectRelationV1(
            rule_id="direct-allow",
            revision_id="r1",
            effect=RuleEffect.ALLOW,
            cell_ids=(direct_cell.cell_id,),
            valid_from_tick=0,
            relation=RebacRelation.OWNS,
        ),
        DirectSubjectRelationV1(
            rule_id="direct-deny",
            revision_id="r1",
            effect=RuleEffect.DENY,
            cell_ids=(direct_cell.cell_id,),
            valid_from_tick=0,
            relation=RebacRelation.OWNS,
        ),
        GroupCollaborationV1(
            rule_id="group-collaboration",
            revision_id="r1",
            effect=RuleEffect.ALLOW,
            cell_ids=(group_cell.cell_id,),
            valid_from_tick=0,
        ),
        ManagerOfOwnerV1(
            rule_id="manager-of-owner",
            revision_id="r1",
            effect=RuleEffect.ALLOW,
            cell_ids=(manager_cell.cell_id,),
            valid_from_tick=0,
        ),
        DirectSubjectRelationV1(
            rule_id="unknown-collaboration",
            revision_id="r1",
            effect=RuleEffect.ALLOW,
            cell_ids=(corpus.evaluation_cells[-1].cell_id,),
            valid_from_tick=0,
            relation=RebacRelation.COLLABORATES_ON,
        ),
    )
    intended_tuples = tuple(
        item.model_copy(update={"tuple_id": f"intended-{item.tuple_id}"})
        for item in tuples[:5]
    )
    intended_rules = tuple(
        item.model_copy(update={"rule_id": f"intended-{item.rule_id}"})
        for item in rules
        if item.rule_id != "direct-deny"
    )
    return (
        EnterpriseRebacStateOverlayV1(
            identity_access_universe_digest=universe_digest,
            evaluation_corpus_digest=corpus_digest,
            relation_tuples=tuples,
            rules=rules,
            unknown_evidence_cell_ids=(corpus.evaluation_cells[-1].cell_id,),
        ),
        EnterpriseRebacIntentOverlayV1(
            identity_access_universe_digest=universe_digest,
            evaluation_corpus_digest=corpus_digest,
            relation_tuples=intended_tuples,
            rules=intended_rules,
            unknown_evidence_cell_ids=(corpus.evaluation_cells[-1].cell_id,),
        ),
    )


def _tuple(
    tuple_id: str,
    subject_id: str,
    relation: RebacRelation,
    object_id: str,
    tenant_id: str,
    snapshot_id: str,
) -> RelationTupleV1:
    return RelationTupleV1(
        tuple_id=tuple_id,
        tenant_id=tenant_id,
        subject_entity_id=subject_id,
        relation=relation,
        object_entity_id=object_id,
        snapshot_id=snapshot_id,
        revision_id="r1",
        valid_from_tick=0,
    )


__all__ = [
    "ReferenceEnterpriseAuthorizationInputsV1",
    "reference_enterprise_authorization_inputs",
]
