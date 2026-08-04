"""Bounded native ReBAC relations, explain paths, budgets, and metrics."""

from __future__ import annotations

from collections import Counter
from typing import cast

import pytest
from pydantic import ValidationError

from synthworld.enterprise.authorization.reference import (
    ReferenceEnterpriseAuthorizationInputsV1,
    reference_enterprise_authorization_inputs,
)
from synthworld.enterprise.authorization_common import (
    MechanismOutcome,
)
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.compiler import EnterpriseCompileError
from synthworld.enterprise.models import (
    EnterpriseCompileOuterSafetyV1,
    EnterpriseIdentityAccessCompileBudgetV1,
    EnterpriseIdentityAccessCompileConfigV1,
    PrincipalKind,
)
from synthworld.enterprise.rebac.common import RebacRelation, RebacTemplateKind
from synthworld.enterprise.rebac.compiler import (
    _enumerate_rule_paths,
    _ExpansionBudget,
    compile_enterprise_rebac_truth,
)
from synthworld.enterprise.rebac.metrics import (
    EnterpriseRebacPredictionV1,
    RebacCellPredictionV1,
    evaluate_enterprise_rebac,
    perfect_enterprise_rebac_prediction,
)
from synthworld.enterprise.rebac.models import (
    CompiledEnterpriseRebacTruthV1,
    DirectSubjectRelationV1,
    EnterpriseRebacIntentOverlayV1,
    EnterpriseRebacStateOverlayV1,
    GroupCollaborationV1,
    RebacRuleBaseV1,
    RelationTupleV1,
)


def _compile(
    reference: ReferenceEnterpriseAuthorizationInputsV1,
    *,
    state: EnterpriseRebacStateOverlayV1 | None = None,
    intent: EnterpriseRebacIntentOverlayV1 | None = None,
    config: EnterpriseIdentityAccessCompileConfigV1 | None = None,
) -> CompiledEnterpriseRebacTruthV1:
    return compile_enterprise_rebac_truth(
        universe=reference.rbac.universe_result.public_universe,
        corpus=reference.rbac.corpus_result.public_corpus,
        rebac_state=state or reference.rebac_state,
        rebac_intent=intent or reference.rebac_intent,
        compile_config=config,
    )


def test_reference_rebac_is_deterministic_bounded_and_cell_preserving() -> None:
    reference = reference_enterprise_authorization_inputs()
    universe_before = canonical_json_bytes(
        reference.rbac.universe_result.public_universe
    )
    corpus_before = canonical_json_bytes(reference.rbac.corpus_result.public_corpus)
    second = _compile(reference)
    assert canonical_json_bytes(second) == canonical_json_bytes(reference.rebac_truth)
    assert (
        canonical_json_bytes(reference.rbac.universe_result.public_universe)
        == universe_before
    )
    assert (
        canonical_json_bytes(reference.rbac.corpus_result.public_corpus)
        == corpus_before
    )
    assert tuple(item.cell_id for item in second.cells) == tuple(
        item.cell_id
        for item in reference.rbac.corpus_result.public_corpus.evaluation_cells
    )
    assert Counter(item.actual_outcome for item in second.cells) == {
        MechanismOutcome.ALLOW: 2,
        MechanismOutcome.DENY: 1,
        MechanismOutcome.NOT_APPLICABLE: 15,
        MechanismOutcome.UNKNOWN: 1,
    }
    assert {item.template for item in second.paths} == set(RebacTemplateKind)
    assert {len(item.tuple_ids) for item in second.paths} == {1, 2}
    assert (
        next(item for item in second.cells if item.actual_conflict).actual_outcome
        is MechanismOutcome.DENY
    )


def test_two_hop_paths_require_one_snapshot_and_explicit_unknown_is_retained() -> None:
    reference = reference_enterprise_authorization_inputs()
    group_tuple = next(
        item
        for item in reference.rebac_state.relation_tuples
        if item.tuple_id == "group-collaboration"
    )
    changed = group_tuple.model_copy(update={"snapshot_id": "snapshot-2"})
    state = reference.rebac_state.model_copy(
        update={
            "relation_tuples": tuple(
                changed if item.tuple_id == changed.tuple_id else item
                for item in reference.rebac_state.relation_tuples
            )
        }
    )
    truth = _compile(reference, state=state)
    group_rule = next(
        item for item in state.rules if isinstance(item, GroupCollaborationV1)
    )
    cell = next(item for item in truth.cells if item.cell_id == group_rule.cell_ids[0])
    assert cell.actual_outcome is MechanismOutcome.NOT_APPLICABLE
    assert cell.actual_path_ids == ()
    unknown_cell = next(
        item for item in truth.cells if item.cell_id in state.unknown_evidence_cell_ids
    )
    assert unknown_cell.actual_outcome is MechanismOutcome.UNKNOWN


@pytest.mark.parametrize(
    ("relation", "subject_kind", "object_kind"),
    (
        (RebacRelation.MEMBER_OF, "unit", "group"),
        (RebacRelation.OWNS, "account", "authorization_target"),
        (RebacRelation.MANAGES, "agent", "human"),
        (RebacRelation.COLLABORATES_ON, "unit", "authorization_target"),
    ),
)
def test_relation_type_matrix_rejects_every_undeclared_endpoint_shape(
    relation: RebacRelation, subject_kind: str, object_kind: str
) -> None:
    reference = reference_enterprise_authorization_inputs()
    universe = reference.rbac.universe_result.public_universe
    human = next(
        item
        for item in universe.principals
        if item.principal_kind is PrincipalKind.EMPLOYEE
    )
    agent = next(
        item
        for item in universe.principals
        if item.principal_kind is PrincipalKind.AGENT
    )
    ids = {
        "unit": universe.units[0].unit_id,
        "account": universe.accounts[0].account_id,
        "group": universe.groups[0].group_id,
        "authorization_target": (
            universe.authorization_targets[0].authorization_target_id
        ),
        "agent": agent.principal_id,
        "human": human.principal_id,
    }
    base = reference.rebac_state.relation_tuples[0]
    invalid = base.model_copy(
        update={
            "tuple_id": f"invalid-{relation.value}",
            "relation": relation,
            "subject_entity_id": ids[subject_kind],
            "object_entity_id": ids[object_kind],
        }
    )
    state = reference.rebac_state.model_copy(update={"relation_tuples": (invalid,)})
    with pytest.raises(
        EnterpriseCompileError, match="invalid_rebac_relation_type_matrix"
    ):
        _compile(reference, state=state)


def test_rebac_tuple_entities_and_tenant_are_validated_before_paths() -> None:
    reference = reference_enterprise_authorization_inputs()
    base = reference.rebac_state.relation_tuples[0]
    unknown = base.model_copy(update={"subject_entity_id": "absent"})
    with pytest.raises(EnterpriseCompileError, match="unknown_rebac_tuple_entity"):
        _compile(
            reference,
            state=reference.rebac_state.model_copy(
                update={"relation_tuples": (unknown,)}
            ),
        )
    cross_tenant = base.model_copy(update={"tenant_id": "absent-tenant"})
    with pytest.raises(EnterpriseCompileError, match="cross_tenant_rebac_tuple"):
        _compile(
            reference,
            state=reference.rebac_state.model_copy(
                update={"relation_tuples": (cross_tenant,)}
            ),
        )


def test_native_rebac_schema_rejects_closed_surface_violations() -> None:
    reference = reference_enterprise_authorization_inputs()
    item = reference.rebac_state.relation_tuples[0]
    document = item.model_dump()
    document["relation"] = "delegates_to"
    with pytest.raises(ValidationError):
        RelationTupleV1.model_validate(document)
    document = item.model_dump()
    document["userset"] = "group:x#member"
    with pytest.raises(ValidationError, match="Extra inputs"):
        RelationTupleV1.model_validate(document)
    document = item.model_dump()
    document["valid_until_tick"] = document["valid_from_tick"]
    with pytest.raises(ValidationError, match="rebac_tuple_validity_interval_invalid"):
        RelationTupleV1.model_validate(document)
    rule = reference.rebac_state.rules[0]
    rule_document = rule.model_dump()
    rule_document["template"] = "recursive_rewrite"
    with pytest.raises(ValidationError):
        DirectSubjectRelationV1.model_validate(rule_document)
    rule_document = rule.model_dump()
    rule_document["relation"] = RebacRelation.MEMBER_OF
    with pytest.raises(ValidationError):
        DirectSubjectRelationV1.model_validate(rule_document)
    rule_document = rule.model_dump()
    rule_document["valid_until_tick"] = rule_document["valid_from_tick"]
    with pytest.raises(ValidationError, match="rebac_rule_validity_interval_invalid"):
        DirectSubjectRelationV1.model_validate(rule_document)


@pytest.mark.parametrize(
    ("field", "code"),
    (
        ("identity_access_universe_digest", "rebac_state_universe_digest_mismatch"),
        ("evaluation_corpus_digest", "rebac_state_corpus_digest_mismatch"),
    ),
)
def test_rebac_state_digest_bindings_are_exact(field: str, code: str) -> None:
    reference = reference_enterprise_authorization_inputs()
    state = reference.rebac_state.model_copy(
        update={field: synthetic_digest(b"changed\n")}
    )
    with pytest.raises(EnterpriseCompileError, match=code):
        _compile(reference, state=state)


def test_rebac_intent_and_corpus_digest_bindings_are_exact() -> None:
    reference = reference_enterprise_authorization_inputs()
    with pytest.raises(EnterpriseCompileError, match="rebac_intent_universe"):
        _compile(
            reference,
            intent=reference.rebac_intent.model_copy(
                update={
                    "identity_access_universe_digest": synthetic_digest(b"changed\n")
                }
            ),
        )
    with pytest.raises(EnterpriseCompileError, match="rebac_intent_corpus"):
        _compile(
            reference,
            intent=reference.rebac_intent.model_copy(
                update={"evaluation_corpus_digest": synthetic_digest(b"changed\n")}
            ),
        )
    changed_corpus = reference.rbac.corpus_result.public_corpus.model_copy(
        update={"identity_access_universe_digest": synthetic_digest(b"changed\n")}
    )
    with pytest.raises(EnterpriseCompileError, match="rebac_corpus_universe"):
        compile_enterprise_rebac_truth(
            universe=reference.rbac.universe_result.public_universe,
            corpus=changed_corpus,
            rebac_state=reference.rebac_state,
            rebac_intent=reference.rebac_intent,
        )


def test_unknown_rule_and_evidence_cells_fail_instead_of_resizing() -> None:
    reference = reference_enterprise_authorization_inputs()
    unknown_rule = reference.rebac_state.rules[0].model_copy(
        update={"cell_ids": ("absent",)}
    )
    with pytest.raises(EnterpriseCompileError, match="undeclared_rebac_rule_cell"):
        _compile(
            reference,
            state=reference.rebac_state.model_copy(update={"rules": (unknown_rule,)}),
        )
    with pytest.raises(
        EnterpriseCompileError, match="undeclared_rebac_unknown_evidence_cell"
    ):
        _compile(
            reference,
            state=reference.rebac_state.model_copy(
                update={"unknown_evidence_cell_ids": ("absent",)}
            ),
        )


@pytest.mark.parametrize(
    ("budget_update", "code"),
    (
        ({"max_rebac_tuples": 1}, "rebac_tuple_budget_exceeded"),
        ({"max_rebac_rules": 1}, "rebac_rule_budget_exceeded"),
        ({"max_rebac_path_expansions": 1}, "rebac_path_expansion_budget_exceeded"),
        ({"max_rebac_paths_per_cell": 1}, "rebac_paths_per_cell_budget_exceeded"),
        ({"max_total_derivations": 1}, "rebac_total_derivation_budget_exceeded"),
    ),
)
def test_rebac_independent_budgets_fail_closed(
    budget_update: dict[str, int], code: str
) -> None:
    reference = reference_enterprise_authorization_inputs()
    budget = EnterpriseIdentityAccessCompileBudgetV1().model_copy(update=budget_update)
    with pytest.raises(EnterpriseCompileError, match=code):
        _compile(
            reference,
            config=EnterpriseIdentityAccessCompileConfigV1(budget=budget),
        )


def test_overlapping_tuple_and_rule_revisions_fail_closed() -> None:
    reference = reference_enterprise_authorization_inputs()
    item = reference.rebac_state.relation_tuples[0]
    overlapping = item.model_copy(update={"revision_id": "r2"})
    state = reference.rebac_state.model_copy(
        update={
            "relation_tuples": (
                *reference.rebac_state.relation_tuples,
                overlapping,
            )
        }
    )
    with pytest.raises(EnterpriseCompileError, match="overlapping_rebac_tuple"):
        _compile(reference, state=state)
    rule = reference.rebac_state.rules[0]
    overlapping_rule = rule.model_copy(update={"revision_id": "r2"})
    state = reference.rebac_state.model_copy(
        update={"rules": (*reference.rebac_state.rules, overlapping_rule)}
    )
    with pytest.raises(EnterpriseCompileError, match="overlapping_rebac_rule"):
        _compile(reference, state=state)


def test_inactive_rebac_revisions_are_retained_but_do_not_create_paths() -> None:
    reference = reference_enterprise_authorization_inputs()
    future_tuple = reference.rebac_state.relation_tuples[0].model_copy(
        update={"valid_from_tick": 10_000, "valid_until_tick": None}
    )
    future_rule = reference.rebac_state.rules[0].model_copy(
        update={"valid_from_tick": 10_000, "valid_until_tick": None}
    )
    state = reference.rebac_state.model_copy(
        update={
            "relation_tuples": (future_tuple,),
            "rules": (future_rule,),
            "unknown_evidence_cell_ids": (),
        }
    )
    truth = _compile(
        reference,
        state=state,
        intent=reference.rebac_intent.model_copy(
            update={
                "relation_tuples": (),
                "rules": (),
                "unknown_evidence_cell_ids": (),
            }
        ),
    )
    assert truth.paths == ()
    assert all(
        item.actual_outcome is MechanismOutcome.NOT_APPLICABLE for item in truth.cells
    )


def test_rebac_rejects_a_frozen_cell_whose_access_atom_is_absent() -> None:
    reference = reference_enterprise_authorization_inputs()
    corpus = reference.rbac.corpus_result.public_corpus
    changed_cell = corpus.evaluation_cells[0].model_copy(
        update={"access_atom_id": "absent-atom"}
    )
    changed_corpus = corpus.model_copy(
        update={"evaluation_cells": (changed_cell, *corpus.evaluation_cells[1:])}
    )
    changed_digest = synthetic_digest(canonical_json_bytes(changed_corpus))
    with pytest.raises(EnterpriseCompileError, match="undeclared_access_atom"):
        compile_enterprise_rebac_truth(
            universe=reference.rbac.universe_result.public_universe,
            corpus=changed_corpus,
            rebac_state=reference.rebac_state.model_copy(
                update={"evaluation_corpus_digest": changed_digest}
            ),
            rebac_intent=reference.rebac_intent.model_copy(
                update={"evaluation_corpus_digest": changed_digest}
            ),
        )


def test_rebac_outer_safety_limits_are_independent_backstops() -> None:
    reference = reference_enterprise_authorization_inputs()
    with pytest.raises(EnterpriseCompileError, match="rebac_outer_work"):
        _compile(
            reference,
            config=EnterpriseIdentityAccessCompileConfigV1(
                outer_safety=EnterpriseCompileOuterSafetyV1(max_work_units=1)
            ),
        )
    with pytest.raises(EnterpriseCompileError, match="rebac_outer_record"):
        _compile(
            reference,
            config=EnterpriseIdentityAccessCompileConfigV1(
                outer_safety=EnterpriseCompileOuterSafetyV1(max_serialized_records=1)
            ),
        )


def test_rebac_metrics_are_independent_discriminating_and_null_when_empty() -> None:
    reference = reference_enterprise_authorization_inputs()
    perfect = perfect_enterprise_rebac_prediction(reference.rebac_truth)
    metrics = evaluate_enterprise_rebac(
        truth=reference.rebac_truth, predictions=perfect
    )
    assert {item.name: item.value for item in metrics.metrics} == {
        "rebac_decision_accuracy": 1.0,
        "relationship_path_exact_match_rate": 1.0,
    }
    path_cell = next(item for item in perfect.cells if item.actual_path_ids)
    changed = path_cell.model_copy(update={"actual_path_ids": ()})
    prediction = perfect.model_copy(
        update={
            "cells": tuple(
                changed if item.cell_id == changed.cell_id else item
                for item in perfect.cells
            )
        }
    )
    scored = evaluate_enterprise_rebac(
        truth=reference.rebac_truth, predictions=prediction
    )
    assert (
        next(
            item
            for item in scored.metrics
            if item.name == "relationship_path_exact_match_rate"
        ).numerator
        == sum(
            bool(item.actual_path_ids or item.intended_path_ids)
            for item in reference.rebac_truth.cells
        )
        - 1
    )
    with pytest.raises(ValueError, match="unknown_rebac_prediction_cell_id"):
        evaluate_enterprise_rebac(
            truth=reference.rebac_truth,
            predictions=EnterpriseRebacPredictionV1(
                cells=(
                    RebacCellPredictionV1(
                        cell_id="absent",
                        actual_outcome=MechanismOutcome.DENY,
                        intended_outcome=MechanismOutcome.DENY,
                    ),
                )
            ),
        )
    with pytest.raises(ValidationError, match="duplicate_rebac_prediction_cell_id"):
        EnterpriseRebacPredictionV1(cells=(perfect.cells[0], perfect.cells[0]))

    universe_digest = synthetic_digest(
        canonical_json_bytes(reference.rbac.universe_result.public_universe)
    )
    corpus_digest = synthetic_digest(
        canonical_json_bytes(reference.rbac.corpus_result.public_corpus)
    )
    empty = _compile(
        reference,
        state=EnterpriseRebacStateOverlayV1(
            identity_access_universe_digest=universe_digest,
            evaluation_corpus_digest=corpus_digest,
        ),
        intent=EnterpriseRebacIntentOverlayV1(
            identity_access_universe_digest=universe_digest,
            evaluation_corpus_digest=corpus_digest,
        ),
    )
    empty_metrics = evaluate_enterprise_rebac(
        truth=empty, predictions=perfect_enterprise_rebac_prediction(empty)
    )
    path_metric = next(
        item
        for item in empty_metrics.metrics
        if item.name == "relationship_path_exact_match_rate"
    )
    assert path_metric.denominator == 0
    assert path_metric.value is None


def test_closed_rule_dispatch_has_an_explicit_unreachable_guard() -> None:
    reference = reference_enterprise_authorization_inputs()
    atom = reference.rbac.universe_result.public_universe.access_atoms[0]
    with pytest.raises(AssertionError, match="not exhaustive"):
        _enumerate_rule_paths(
            cast(RebacRuleBaseV1, object()),
            atom,
            (),
            _ExpansionBudget(10, 10, 10),
        )
