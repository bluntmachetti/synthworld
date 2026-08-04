"""Bounded ABAC contracts, compiler semantics, budgets, and metrics."""

from __future__ import annotations

from collections import Counter
from typing import cast

import pytest
from pydantic import ValidationError

from synthworld.enterprise.abac.common import (
    AssuranceLevel,
    AttributeValueState,
    NetworkZone,
)
from synthworld.enterprise.abac.compiler import (
    _evaluate_predicate,
    compile_enterprise_abac_truth,
)
from synthworld.enterprise.abac.metrics import (
    AbacCellPredictionV1,
    AbacPredicatePredictionV1,
    EnterpriseAbacPredictionV1,
    evaluate_enterprise_abac,
    perfect_enterprise_abac_prediction,
)
from synthworld.enterprise.abac.models import (
    AbacAttributeFactTruthV1,
    AbacPredicateV1,
    AbacRuleV1,
    AssuranceAtLeastV1,
    ClassificationWithinClearanceV1,
    CompiledEnterpriseAbacTruthV1,
    EnterpriseAbacCompileLimitsV1,
    EnterpriseAbacIntentOverlayV1,
    EnterpriseAbacStateOverlayV1,
    NetworkZoneIsV1,
    SubjectPrincipalKindFactV1,
)
from synthworld.enterprise.authorization.reference import (
    ReferenceEnterpriseAuthorizationInputsV1,
    reference_enterprise_authorization_inputs,
)
from synthworld.enterprise.authorization_common import (
    FlatRuleOperator,
    MechanismOutcome,
    PredicateOutcome,
    RuleEffect,
)
from synthworld.enterprise.canonical import canonical_json_bytes, synthetic_digest
from synthworld.enterprise.compiler import EnterpriseCompileError
from synthworld.enterprise.models import (
    EnterpriseCompileOuterSafetyV1,
    EnterpriseIdentityAccessCompileBudgetV1,
    EnterpriseIdentityAccessCompileConfigV1,
    PrincipalKind,
)


def _compile(
    reference: ReferenceEnterpriseAuthorizationInputsV1,
    *,
    state: EnterpriseAbacStateOverlayV1 | None = None,
    intent: EnterpriseAbacIntentOverlayV1 | None = None,
    config: EnterpriseIdentityAccessCompileConfigV1 | None = None,
    limits: EnterpriseAbacCompileLimitsV1 | None = None,
) -> CompiledEnterpriseAbacTruthV1:
    return compile_enterprise_abac_truth(
        universe=reference.rbac.universe_result.public_universe,
        corpus=reference.rbac.corpus_result.public_corpus,
        abac_state=state or reference.abac_state,
        abac_intent=intent or reference.abac_intent,
        compile_config=config,
        limits=limits,
    )


def test_reference_abac_is_deterministic_complete_and_cell_preserving() -> None:
    reference = reference_enterprise_authorization_inputs()
    universe_before = canonical_json_bytes(
        reference.rbac.universe_result.public_universe
    )
    corpus_before = canonical_json_bytes(reference.rbac.corpus_result.public_corpus)
    second = _compile(reference)
    assert canonical_json_bytes(second) == canonical_json_bytes(reference.abac_truth)
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
        MechanismOutcome.ALLOW: 13,
        MechanismOutcome.DENY: 1,
        MechanismOutcome.NOT_APPLICABLE: 1,
        MechanismOutcome.UNKNOWN: 4,
    }
    assert {item.kind for item in reference.abac_state.rules[0].predicates} == {
        "action_class_is",
        "action_is",
        "assurance_at_least",
        "classification_within_clearance",
        "employment_type_is",
        "network_zone_is",
        "same_tenant",
        "subject_kind_is",
        "subject_unit_is",
        "subject_unit_owns_target",
        "target_kind_is",
    }
    conflict = next(item for item in second.cells if item.actual_conflict)
    assert conflict.actual_outcome is MechanismOutcome.DENY


def test_missing_explicit_unknown_and_false_predicates_remain_distinct() -> None:
    reference = reference_enterprise_authorization_inputs()
    corpus = reference.rbac.corpus_result.public_corpus
    principal_cell = next(
        item
        for item in corpus.evaluation_cells
        if any(
            principal.principal_id
            == next(
                atom.subject_id
                for atom in reference.rbac.universe_result.public_universe.access_atoms
                if atom.access_atom_id == item.access_atom_id
            )
            for principal in reference.rbac.universe_result.public_universe.principals
        )
    )
    digest = synthetic_digest(canonical_json_bytes(corpus))
    universe_digest = synthetic_digest(
        canonical_json_bytes(reference.rbac.universe_result.public_universe)
    )
    rule = AbacRuleV1(
        rule_id="missing-assurance",
        revision_id="r1",
        effect=RuleEffect.ALLOW,
        operator=FlatRuleOperator.ANY,
        cell_ids=(principal_cell.cell_id,),
        predicates=(AssuranceAtLeastV1(minimum=AssuranceLevel.MEDIUM),),
        valid_from_tick=0,
    )
    empty_intent = EnterpriseAbacIntentOverlayV1(
        identity_access_universe_digest=universe_digest,
        evaluation_corpus_digest=digest,
    )
    missing = _compile(
        reference,
        state=EnterpriseAbacStateOverlayV1(
            identity_access_universe_digest=universe_digest,
            evaluation_corpus_digest=digest,
            rules=(rule,),
        ),
        intent=empty_intent,
    )
    predicate = next(item for item in missing.predicate_truth)
    assert predicate.outcome is PredicateOutcome.UNKNOWN
    assert predicate.supporting_fact_ids == ()

    account_fact = next(
        item
        for item in reference.abac_state.attribute_facts
        if item.kind == "subject_principal_kind"
        and item.value_state is AttributeValueState.UNKNOWN
    )
    unknown_rule = rule.model_copy(
        update={
            "rule_id": "explicit-unknown",
            "cell_ids": (account_fact.cell_id,),
            "predicates": (
                next(
                    item
                    for item in reference.abac_state.rules[0].predicates
                    if item.kind == "subject_kind_is"
                ),
            ),
        }
    )
    explicit = _compile(
        reference,
        state=EnterpriseAbacStateOverlayV1(
            identity_access_universe_digest=universe_digest,
            evaluation_corpus_digest=digest,
            attribute_facts=(account_fact,),
            rules=(unknown_rule,),
        ),
        intent=empty_intent,
    )
    explicit_predicate = next(item for item in explicit.predicate_truth)
    assert explicit_predicate.outcome is PredicateOutcome.UNKNOWN
    assert len(explicit_predicate.supporting_fact_ids) == 1

    network_fact = next(
        item
        for item in reference.abac_state.attribute_facts
        if item.kind == "environment_network_zone" and item.value is NetworkZone.PUBLIC
    )
    false_rule = rule.model_copy(
        update={
            "rule_id": "false-network",
            "cell_ids": (network_fact.cell_id,),
            "predicates": (NetworkZoneIsV1(values=(NetworkZone.INTERNAL,)),),
        }
    )
    false_truth = _compile(
        reference,
        state=EnterpriseAbacStateOverlayV1(
            identity_access_universe_digest=universe_digest,
            evaluation_corpus_digest=digest,
            attribute_facts=(network_fact,),
            rules=(false_rule,),
        ),
        intent=empty_intent,
    )
    assert (
        next(item for item in false_truth.predicate_truth).outcome
        is PredicateOutcome.FALSE
    )
    assert (
        next(
            item for item in false_truth.cells if item.cell_id == network_fact.cell_id
        ).actual_outcome
        is MechanismOutcome.NOT_APPLICABLE
    )


def test_abac_models_are_closed_typed_flat_and_revision_safe() -> None:
    reference = reference_enterprise_authorization_inputs()
    fact = next(
        item
        for item in reference.abac_state.attribute_facts
        if item.kind == "subject_principal_kind"
    )
    document = fact.model_dump()
    document["value_state"] = AttributeValueState.KNOWN
    document["value"] = None
    with pytest.raises(ValidationError, match="known_attribute_value_missing"):
        SubjectPrincipalKindFactV1.model_validate(document)
    document["value_state"] = AttributeValueState.UNKNOWN
    document["value"] = PrincipalKind.EMPLOYEE
    with pytest.raises(ValidationError, match="unknown_attribute_value_present"):
        SubjectPrincipalKindFactV1.model_validate(document)
    document["value_state"] = AttributeValueState.KNOWN
    document["value"] = "undeclared-kind"
    with pytest.raises(ValidationError):
        SubjectPrincipalKindFactV1.model_validate(document)
    document = fact.model_dump()
    document["valid_until_tick"] = document["valid_from_tick"]
    with pytest.raises(ValidationError, match="validity_interval_invalid"):
        SubjectPrincipalKindFactV1.model_validate(document)
    document = fact.model_dump()
    document["arbitrary_attribute"] = "forbidden"
    with pytest.raises(ValidationError, match="Extra inputs"):
        SubjectPrincipalKindFactV1.model_validate(document)

    rule = reference.abac_state.rules[0]
    with pytest.raises(ValidationError, match="duplicate_abac_rule_predicate"):
        AbacRuleV1(
            rule_id="duplicate-predicate",
            revision_id="r1",
            effect=RuleEffect.ALLOW,
            operator=FlatRuleOperator.ALL,
            cell_ids=(rule.cell_ids[0],),
            predicates=(rule.predicates[0], rule.predicates[0]),
            valid_from_tick=0,
        )
    invalid_rule = rule.model_dump()
    invalid_rule["predicates"] = ({"kind": "free_expression", "code": "x"},)
    with pytest.raises(ValidationError):
        AbacRuleV1.model_validate(invalid_rule)
    invalid_rule = rule.model_dump()
    invalid_rule["valid_until_tick"] = 0
    with pytest.raises(ValidationError, match="abac_rule_validity_interval_invalid"):
        AbacRuleV1.model_validate(invalid_rule)
    with pytest.raises(ValidationError):
        EnterpriseAbacCompileLimitsV1(max_rules_per_overlay=257)
    with pytest.raises(ValidationError):
        EnterpriseAbacCompileLimitsV1(max_predicates_per_rule=65)
    with pytest.raises(ValidationError, match="duplicate_abac_network_zone"):
        NetworkZoneIsV1(values=(NetworkZone.INTERNAL, NetworkZone.INTERNAL))

    truth_fact = next(
        item
        for item in reference.abac_truth.attribute_facts
        if item.value_state is AttributeValueState.KNOWN
    )
    document = truth_fact.model_dump()
    document["value"] = None
    with pytest.raises(ValidationError, match="known_truth_attribute_value_missing"):
        AbacAttributeFactTruthV1.model_validate(document)
    document = truth_fact.model_dump()
    document["value_state"] = AttributeValueState.UNKNOWN
    with pytest.raises(ValidationError, match="unknown_truth_attribute_value_present"):
        AbacAttributeFactTruthV1.model_validate(document)


@pytest.mark.parametrize(
    ("field", "code"),
    (
        ("identity_access_universe_digest", "abac_state_universe_digest_mismatch"),
        ("evaluation_corpus_digest", "abac_state_corpus_digest_mismatch"),
    ),
)
def test_abac_state_digest_bindings_are_exact(field: str, code: str) -> None:
    reference = reference_enterprise_authorization_inputs()
    changed = reference.abac_state.model_copy(
        update={field: synthetic_digest(b"changed\n")}
    )
    with pytest.raises(EnterpriseCompileError, match=code):
        _compile(reference, state=changed)


def test_abac_intent_and_corpus_digest_bindings_are_exact() -> None:
    reference = reference_enterprise_authorization_inputs()
    with pytest.raises(EnterpriseCompileError, match="abac_intent_universe"):
        _compile(
            reference,
            intent=reference.abac_intent.model_copy(
                update={
                    "identity_access_universe_digest": synthetic_digest(b"changed\n")
                }
            ),
        )
    with pytest.raises(EnterpriseCompileError, match="abac_intent_corpus"):
        _compile(
            reference,
            intent=reference.abac_intent.model_copy(
                update={"evaluation_corpus_digest": synthetic_digest(b"changed\n")}
            ),
        )
    changed_universe_digest = synthetic_digest(b"changed\n")
    changed_corpus = reference.rbac.corpus_result.public_corpus.model_copy(
        update={"identity_access_universe_digest": changed_universe_digest}
    )
    with pytest.raises(EnterpriseCompileError, match="abac_corpus_universe"):
        compile_enterprise_abac_truth(
            universe=reference.rbac.universe_result.public_universe,
            corpus=changed_corpus,
            abac_state=reference.abac_state,
            abac_intent=reference.abac_intent,
        )


@pytest.mark.parametrize(
    ("budget_update", "code"),
    (
        ({"max_attribute_facts": 1}, "abac_attribute_fact_budget_exceeded"),
        ({"max_total_abac_rules": 1}, "abac_rule_budget_exceeded"),
        ({"max_total_abac_predicates": 1}, "abac_predicate_budget_exceeded"),
    ),
)
def test_abac_independent_semantic_budgets_fail_closed(
    budget_update: dict[str, int], code: str
) -> None:
    reference = reference_enterprise_authorization_inputs()
    budget = EnterpriseIdentityAccessCompileBudgetV1().model_copy(update=budget_update)
    config = EnterpriseIdentityAccessCompileConfigV1(budget=budget)
    with pytest.raises(EnterpriseCompileError, match=code):
        _compile(reference, config=config)


def test_abac_per_profile_limits_and_overlapping_revisions_fail_closed() -> None:
    reference = reference_enterprise_authorization_inputs()
    with pytest.raises(EnterpriseCompileError, match="state_rule_limit"):
        _compile(
            reference,
            limits=EnterpriseAbacCompileLimitsV1(max_rules_per_overlay=1),
        )
    with pytest.raises(EnterpriseCompileError, match="predicates_per_rule"):
        _compile(
            reference,
            limits=EnterpriseAbacCompileLimitsV1(max_predicates_per_rule=1),
        )
    fact = reference.abac_state.attribute_facts[0]
    overlapping_fact = fact.model_copy(
        update={"fact_id": "overlap", "revision_id": "r2"}
    )
    state = reference.abac_state.model_copy(
        update={
            "attribute_facts": (
                *reference.abac_state.attribute_facts,
                overlapping_fact,
            )
        }
    )
    with pytest.raises(EnterpriseCompileError, match="overlapping_abac_fact"):
        _compile(reference, state=state)
    rule = reference.abac_state.rules[0]
    overlapping_rule = rule.model_copy(update={"revision_id": "r2"})
    state = reference.abac_state.model_copy(
        update={"rules": (*reference.abac_state.rules, overlapping_rule)}
    )
    with pytest.raises(EnterpriseCompileError, match="overlapping_abac_rule"):
        _compile(reference, state=state)


def test_inactive_abac_revisions_remain_in_input_but_do_not_affect_truth() -> None:
    reference = reference_enterprise_authorization_inputs()
    future_fact = reference.abac_state.attribute_facts[0].model_copy(
        update={"valid_from_tick": 10_000, "valid_until_tick": None}
    )
    future_rule = reference.abac_state.rules[0].model_copy(
        update={"valid_from_tick": 10_000, "valid_until_tick": None}
    )
    state = reference.abac_state.model_copy(
        update={"attribute_facts": (future_fact,), "rules": (future_rule,)}
    )
    truth = _compile(
        reference,
        state=state,
        intent=reference.abac_intent.model_copy(
            update={"attribute_facts": (), "rules": ()}
        ),
    )
    assert state.attribute_facts == (future_fact,)
    assert not any(
        item.fact_id == future_fact.fact_id for item in truth.attribute_facts
    )
    assert all(
        item.actual_outcome is MechanismOutcome.NOT_APPLICABLE for item in truth.cells
    )


def test_abac_unknown_references_and_outer_safety_fail_before_widening() -> None:
    reference = reference_enterprise_authorization_inputs()
    fact = reference.abac_state.attribute_facts[0]
    unknown_cell_fact = fact.model_copy(update={"cell_id": "absent-cell"})
    with pytest.raises(EnterpriseCompileError, match="undeclared_abac_fact_cell"):
        _compile(
            reference,
            state=reference.abac_state.model_copy(
                update={"attribute_facts": (unknown_cell_fact,)}
            ),
        )
    unknown_cell_rule = reference.abac_state.rules[0].model_copy(
        update={"cell_ids": ("absent-cell",)}
    )
    with pytest.raises(EnterpriseCompileError, match="undeclared_abac_rule_cell"):
        _compile(
            reference,
            state=reference.abac_state.model_copy(
                update={"rules": (unknown_cell_rule,)}
            ),
        )
    tenant_fact = next(
        item
        for item in reference.abac_state.attribute_facts
        if item.kind == "subject_tenant_id"
    ).model_copy(update={"value": "absent-tenant"})
    with pytest.raises(EnterpriseCompileError, match="unknown_abac_tenant"):
        _compile(
            reference,
            state=reference.abac_state.model_copy(
                update={"attribute_facts": (tenant_fact,)}
            ),
        )

    outer = EnterpriseCompileOuterSafetyV1(max_serialized_records=1)
    with pytest.raises(EnterpriseCompileError, match="abac_outer_record"):
        _compile(
            reference,
            config=EnterpriseIdentityAccessCompileConfigV1(outer_safety=outer),
        )


def test_abac_rejects_a_frozen_cell_whose_access_atom_is_absent() -> None:
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
        compile_enterprise_abac_truth(
            universe=reference.rbac.universe_result.public_universe,
            corpus=changed_corpus,
            abac_state=reference.abac_state.model_copy(
                update={"evaluation_corpus_digest": changed_digest}
            ),
            abac_intent=reference.abac_intent.model_copy(
                update={"evaluation_corpus_digest": changed_digest}
            ),
        )


def test_abac_predicate_unknown_paths_distinguish_missing_and_explicit_facts() -> None:
    reference = reference_enterprise_authorization_inputs()
    assert _evaluate_predicate(NetworkZoneIsV1(values=(NetworkZone.INTERNAL,)), {}) == (
        PredicateOutcome.UNKNOWN,
        (),
    )
    assert _evaluate_predicate(ClassificationWithinClearanceV1(), {}) == (
        PredicateOutcome.UNKNOWN,
        (),
    )
    assurance = next(
        item
        for item in reference.abac_state.attribute_facts
        if item.kind == "environment_assurance_level"
    ).model_copy(update={"value_state": AttributeValueState.UNKNOWN, "value": None})
    outcome, facts = _evaluate_predicate(
        AssuranceAtLeastV1(minimum=AssuranceLevel.MEDIUM),
        {assurance.kind: assurance},
    )
    assert outcome is PredicateOutcome.UNKNOWN
    assert facts == (assurance,)


def test_abac_metrics_are_independent_and_discriminating() -> None:
    reference = reference_enterprise_authorization_inputs()
    perfect = perfect_enterprise_abac_prediction(reference.abac_truth)
    metrics = evaluate_enterprise_abac(truth=reference.abac_truth, predictions=perfect)
    assert {item.name: item.value for item in metrics.metrics} == {
        "abac_decision_accuracy": 1.0,
        "predicate_outcome_accuracy": 1.0,
    }
    first = perfect.cells[0]
    wrong = first.model_copy(
        update={
            "actual_outcome": (
                MechanismOutcome.DENY
                if first.actual_outcome is not MechanismOutcome.DENY
                else MechanismOutcome.ALLOW
            )
        }
    )
    mutated = perfect.model_copy(update={"cells": (wrong, *perfect.cells[1:])})
    scored = evaluate_enterprise_abac(truth=reference.abac_truth, predictions=mutated)
    assert (
        next(
            item for item in scored.metrics if item.name == "abac_decision_accuracy"
        ).numerator
        == len(reference.abac_truth.cells) - 1
    )
    with pytest.raises(ValueError, match="unknown_abac_prediction_id"):
        evaluate_enterprise_abac(
            truth=reference.abac_truth,
            predictions=EnterpriseAbacPredictionV1(
                cells=(
                    AbacCellPredictionV1(
                        cell_id="absent",
                        actual_outcome=MechanismOutcome.DENY,
                        intended_outcome=MechanismOutcome.DENY,
                    ),
                )
            ),
        )
    with pytest.raises(ValidationError, match="duplicate_abac_prediction_id"):
        EnterpriseAbacPredictionV1(cells=(first, first))
    predicate = perfect.predicates[0]
    with pytest.raises(ValidationError, match="duplicate_abac_prediction_id"):
        EnterpriseAbacPredictionV1(predicates=(predicate, predicate))


def test_closed_predicate_dispatch_has_an_explicit_unreachable_guard() -> None:
    with pytest.raises(AssertionError, match="not exhaustive"):
        _evaluate_predicate(cast(AbacPredicateV1, object()), {})


def test_empty_abac_predicate_metric_is_null_not_silently_perfect() -> None:
    reference = reference_enterprise_authorization_inputs()
    universe_digest = synthetic_digest(
        canonical_json_bytes(reference.rbac.universe_result.public_universe)
    )
    corpus_digest = synthetic_digest(
        canonical_json_bytes(reference.rbac.corpus_result.public_corpus)
    )
    truth = _compile(
        reference,
        state=EnterpriseAbacStateOverlayV1(
            identity_access_universe_digest=universe_digest,
            evaluation_corpus_digest=corpus_digest,
        ),
        intent=EnterpriseAbacIntentOverlayV1(
            identity_access_universe_digest=universe_digest,
            evaluation_corpus_digest=corpus_digest,
        ),
    )
    metrics = evaluate_enterprise_abac(
        truth=truth, predictions=perfect_enterprise_abac_prediction(truth)
    )
    predicate_metric = next(
        item for item in metrics.metrics if item.name == "predicate_outcome_accuracy"
    )
    assert predicate_metric.denominator == 0
    assert predicate_metric.value is None


def test_abac_prediction_predicate_mutation_is_detected() -> None:
    reference = reference_enterprise_authorization_inputs()
    perfect = perfect_enterprise_abac_prediction(reference.abac_truth)
    first = perfect.predicates[0]
    changed = AbacPredicatePredictionV1(
        truth_id=first.truth_id,
        outcome=(
            PredicateOutcome.FALSE
            if first.outcome is not PredicateOutcome.FALSE
            else PredicateOutcome.TRUE
        ),
    )
    prediction = perfect.model_copy(
        update={"predicates": (changed, *perfect.predicates[1:])}
    )
    metrics = evaluate_enterprise_abac(
        truth=reference.abac_truth, predictions=prediction
    )
    assert (
        next(
            item
            for item in metrics.metrics
            if item.name == "predicate_outcome_accuracy"
        ).numerator
        == len(reference.abac_truth.predicate_truth) - 1
    )
