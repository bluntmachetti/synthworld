"""Offline evaluation of closed ABAC predicates over frozen access cells."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from typing import cast
from uuid import UUID, uuid5

from synthworld.enterprise.abac.common import (
    AssuranceLevel,
    AttributeValueState,
    InformationClassification,
)
from synthworld.enterprise.abac.models import (
    AbacAttributeFactTruthV1,
    AbacCellTruthV1,
    AbacPredicateTruthV1,
    AbacPredicateV1,
    AbacRuleTruthV1,
    AbacRuleV1,
    ActionClassIsV1,
    ActionIsV1,
    AssuranceAtLeastV1,
    AttributeFactBaseV1,
    ClassificationWithinClearanceV1,
    CompiledEnterpriseAbacTruthV1,
    EmploymentTypeIsV1,
    EnterpriseAbacCompileLimitsV1,
    EnterpriseAbacIntentOverlayV1,
    EnterpriseAbacStateOverlayV1,
    NetworkZoneIsV1,
    SameTenantV1,
    SubjectKindIsV1,
    SubjectUnitIsV1,
    SubjectUnitOwnsTargetV1,
    TargetKindIsV1,
)
from synthworld.enterprise.authorization_common import (
    AuthorizationSourceLayer,
    FlatRuleOperator,
    MechanismOutcome,
    PredicateOutcome,
    RuleEffect,
)
from synthworld.enterprise.canonical import (
    canonical_json_bytes,
    encode_parts,
    synthetic_digest,
)
from synthworld.enterprise.compiler import EnterpriseCompileError
from synthworld.enterprise.models import (
    AccessAtomV1,
    EnterpriseIdentityAccessCompileConfigV1,
    EnterpriseIdentityAccessUniverseV1,
    SyntheticDigestV1,
)
from synthworld.enterprise.rbac.corpus_models import (
    AccessEvaluationCellV1,
    EnterpriseEvaluationCorpusV1,
)

ENTERPRISE_ABAC_TRUTH_RECORD_NAMESPACE_V1 = UUID("dbecc01c-074e-5a09-8d7f-c0ed9f296cc5")

_CLASSIFICATION_RANK = {
    InformationClassification.PUBLIC: 0,
    InformationClassification.INTERNAL: 1,
    InformationClassification.CONFIDENTIAL: 2,
    InformationClassification.RESTRICTED: 3,
}
_ASSURANCE_RANK = {
    AssuranceLevel.LOW: 0,
    AssuranceLevel.MEDIUM: 1,
    AssuranceLevel.HIGH: 2,
}


@dataclass(frozen=True, slots=True)
class _LayerResult:
    facts: tuple[AbacAttributeFactTruthV1, ...]
    predicates: tuple[AbacPredicateTruthV1, ...]
    rules: tuple[AbacRuleTruthV1, ...]
    outcomes: dict[str, MechanismOutcome]
    conflicts: dict[str, bool]
    rule_truth_ids: dict[str, tuple[str, ...]]


def compile_enterprise_abac_truth(
    *,
    universe: EnterpriseIdentityAccessUniverseV1,
    corpus: EnterpriseEvaluationCorpusV1,
    abac_state: EnterpriseAbacStateOverlayV1,
    abac_intent: EnterpriseAbacIntentOverlayV1,
    compile_config: EnterpriseIdentityAccessCompileConfigV1 | None = None,
    limits: EnterpriseAbacCompileLimitsV1 | None = None,
) -> CompiledEnterpriseAbacTruthV1:
    """Compile ABAC truth without creating an entity, context, request, or cell."""

    selected_config = compile_config or EnterpriseIdentityAccessCompileConfigV1()
    selected_limits = limits or EnterpriseAbacCompileLimitsV1()
    universe_digest = synthetic_digest(canonical_json_bytes(universe))
    corpus_digest = synthetic_digest(canonical_json_bytes(corpus))
    _validate_bindings(
        universe,
        corpus,
        abac_state,
        abac_intent,
        universe_digest,
        corpus_digest,
    )
    cells = {item.cell_id: item for item in corpus.evaluation_cells}
    atoms = {item.access_atom_id: item for item in universe.access_atoms}
    _validate_references(universe, cells, atoms, abac_state)
    _validate_references(universe, cells, atoms, abac_intent)
    _preflight_budgets(
        abac_state,
        abac_intent,
        cells,
        selected_config,
        selected_limits,
    )
    state_digest = synthetic_digest(canonical_json_bytes(abac_state))
    intent_digest = synthetic_digest(canonical_json_bytes(abac_intent))
    actual = _compile_layer(
        AuthorizationSourceLayer.ACTUAL,
        abac_state.attribute_facts,
        abac_state.rules,
        cells,
        state_digest,
    )
    intended = _compile_layer(
        AuthorizationSourceLayer.INTENDED,
        abac_intent.attribute_facts,
        abac_intent.rules,
        cells,
        intent_digest,
    )
    truth = CompiledEnterpriseAbacTruthV1(
        identity_access_universe_digest=universe_digest,
        evaluation_corpus_digest=corpus_digest,
        abac_state_digest=state_digest,
        abac_intent_digest=intent_digest,
        attribute_facts=actual.facts + intended.facts,
        predicate_truth=actual.predicates + intended.predicates,
        rule_truth=actual.rules + intended.rules,
        cells=tuple(
            AbacCellTruthV1(
                cell_id=cell_id,
                actual_outcome=actual.outcomes[cell_id],
                intended_outcome=intended.outcomes[cell_id],
                actual_conflict=actual.conflicts[cell_id],
                intended_conflict=intended.conflicts[cell_id],
                actual_rule_truth_ids=actual.rule_truth_ids[cell_id],
                intended_rule_truth_ids=intended.rule_truth_ids[cell_id],
            )
            for cell_id in sorted(cells)
        ),
    )
    _check_outer_safety(truth, selected_config)
    return truth


def _validate_bindings(
    universe: EnterpriseIdentityAccessUniverseV1,
    corpus: EnterpriseEvaluationCorpusV1,
    state: EnterpriseAbacStateOverlayV1,
    intent: EnterpriseAbacIntentOverlayV1,
    universe_digest: SyntheticDigestV1,
    corpus_digest: SyntheticDigestV1,
) -> None:
    if corpus.identity_access_universe_digest != universe_digest:
        raise EnterpriseCompileError(
            "abac_corpus_universe_digest_mismatch",
            "evaluation corpus does not bind the supplied universe",
        )
    for label, overlay in (("state", state), ("intent", intent)):
        if overlay.identity_access_universe_digest != universe_digest:
            raise EnterpriseCompileError(
                f"abac_{label}_universe_digest_mismatch",
                f"ABAC {label} does not bind the supplied universe",
            )
        if overlay.evaluation_corpus_digest != corpus_digest:
            raise EnterpriseCompileError(
                f"abac_{label}_corpus_digest_mismatch",
                f"ABAC {label} does not bind the supplied corpus",
            )


def _validate_references(
    universe: EnterpriseIdentityAccessUniverseV1,
    cells: dict[str, AccessEvaluationCellV1],
    atoms: dict[str, AccessAtomV1],
    overlay: EnterpriseAbacStateOverlayV1 | EnterpriseAbacIntentOverlayV1,
) -> None:
    tenant_ids = {item.tenant_id for item in universe.tenants}
    unit_ids = {item.unit_id for item in universe.units}
    action_ids = {item.action for item in universe.permissions}
    for fact in overlay.attribute_facts:
        if fact.cell_id not in cells:
            raise EnterpriseCompileError(
                "undeclared_abac_fact_cell",
                "ABAC fact references a cell outside the frozen corpus",
            )
        if fact.value_state is AttributeValueState.UNKNOWN:
            continue
        if fact.kind in {"subject_tenant_id", "resource_tenant_id"}:
            _require_reference(cast(str, fact.value), tenant_ids, "abac_tenant")
        elif fact.kind in {"subject_unit_id", "resource_owner_unit_id"}:
            _require_reference(cast(str, fact.value), unit_ids, "abac_unit")
        elif fact.kind == "action_id":
            _require_reference(cast(str, fact.value), action_ids, "abac_action")
    for rule in overlay.rules:
        for cell_id in rule.cell_ids:
            if cell_id not in cells:
                raise EnterpriseCompileError(
                    "undeclared_abac_rule_cell",
                    "ABAC rule references a cell outside the frozen corpus",
                )
        for predicate in rule.predicates:
            if isinstance(predicate, SubjectUnitIsV1):
                for unit_id in predicate.unit_ids:
                    _require_reference(unit_id, unit_ids, "abac_predicate_unit")
            elif isinstance(predicate, ActionIsV1):
                for action_id in predicate.action_ids:
                    _require_reference(action_id, action_ids, "abac_predicate_action")
    for cell_id, cell in cells.items():
        access_atom_id = cell.access_atom_id
        if access_atom_id not in atoms:
            raise EnterpriseCompileError(
                "undeclared_access_atom",
                f"frozen cell {cell_id} references an absent access atom",
            )


def _require_reference(value: str, known: set[str], description: str) -> None:
    if value not in known:
        raise EnterpriseCompileError(
            f"unknown_{description}",
            f"{description.replace('_', ' ')} does not resolve in the frozen universe",
        )


def _preflight_budgets(
    state: EnterpriseAbacStateOverlayV1,
    intent: EnterpriseAbacIntentOverlayV1,
    cells: dict[str, AccessEvaluationCellV1],
    config: EnterpriseIdentityAccessCompileConfigV1,
    limits: EnterpriseAbacCompileLimitsV1,
) -> None:
    facts = len(state.attribute_facts) + len(intent.attribute_facts)
    rules = len(state.rules) + len(intent.rules)
    predicates = sum(len(item.predicates) for item in (*state.rules, *intent.rules))
    _enforce_limit(
        "abac_attribute_fact_budget_exceeded",
        facts,
        config.budget.max_attribute_facts,
    )
    _enforce_limit(
        "abac_rule_budget_exceeded", rules, config.budget.max_total_abac_rules
    )
    _enforce_limit(
        "abac_predicate_budget_exceeded",
        predicates,
        config.budget.max_total_abac_predicates,
    )
    for label, overlay in (("state", state), ("intent", intent)):
        _enforce_limit(
            f"abac_{label}_rule_limit_exceeded",
            len(overlay.rules),
            limits.max_rules_per_overlay,
        )
        for rule in overlay.rules:
            _enforce_limit(
                "abac_predicates_per_rule_limit_exceeded",
                len(rule.predicates),
                limits.max_predicates_per_rule,
            )
    cell_ticks = {cell_id: cell.tick for cell_id, cell in cells.items()}
    evaluated_rules = 0
    evaluated_predicates = 0
    for rule in (*state.rules, *intent.rules):
        for cell_id in rule.cell_ids:
            if _active(
                cell_ticks[cell_id], rule.valid_from_tick, rule.valid_until_tick
            ):
                evaluated_rules += 1
                evaluated_predicates += len(rule.predicates)
    predicted_records = facts + evaluated_rules + evaluated_predicates + len(cells)
    _enforce_limit(
        "abac_outer_record_budget_exceeded",
        predicted_records,
        config.outer_safety.max_serialized_records,
    )
    _enforce_limit(
        "abac_outer_step_budget_exceeded",
        evaluated_predicates,
        config.outer_safety.max_expanded_steps,
    )
    work = facts + rules + evaluated_rules + evaluated_predicates + len(cells)
    _enforce_limit(
        "abac_outer_work_budget_exceeded", work, config.outer_safety.max_work_units
    )


def _compile_layer(
    layer: AuthorizationSourceLayer,
    facts: tuple[AttributeFactBaseV1, ...],
    rules: tuple[AbacRuleV1, ...],
    cells: dict[str, AccessEvaluationCellV1],
    overlay_digest: SyntheticDigestV1,
) -> _LayerResult:
    facts_by_cell: dict[str, list[AttributeFactBaseV1]] = defaultdict(list)
    for fact in facts:
        facts_by_cell[fact.cell_id].append(fact)
    rules_by_cell: dict[str, list[AbacRuleV1]] = defaultdict(list)
    for rule in rules:
        for cell_id in rule.cell_ids:
            rules_by_cell[cell_id].append(rule)
    fact_truth: list[AbacAttributeFactTruthV1] = []
    fact_truth_ids: dict[str, str] = {}
    for fact in facts:
        cell_tick = cells[fact.cell_id].tick
        fact_id = _truth_id(overlay_digest.value, layer.value, "fact", fact.fact_id)
        fact_truth_ids[fact.fact_id] = fact_id
        fact_truth.append(
            AbacAttributeFactTruthV1(
                fact_id=fact_id,
                revision_id=_truth_id(
                    overlay_digest.value,
                    layer.value,
                    "fact-revision",
                    fact.fact_id,
                    fact.revision_id,
                ),
                source_layer=layer,
                cell_id=fact.cell_id,
                category=fact.category,
                attribute_key=fact.attribute_key,
                value_state=fact.value_state,
                value=_string_value(fact.value),
                active_at_cell_tick=_active(
                    cell_tick, fact.valid_from_tick, fact.valid_until_tick
                ),
            )
        )
    predicate_truth: list[AbacPredicateTruthV1] = []
    rule_truth: list[AbacRuleTruthV1] = []
    outcomes: dict[str, MechanismOutcome] = {}
    conflicts: dict[str, bool] = {}
    cell_rule_ids: dict[str, tuple[str, ...]] = {}
    for cell_id in sorted(cells):
        tick = cells[cell_id].tick
        active_facts = _active_facts(facts_by_cell[cell_id], tick)
        active_rules = _active_rules(rules_by_cell[cell_id], tick)
        cell_outcomes: list[MechanismOutcome] = []
        truth_ids: list[str] = []
        for rule in active_rules:
            generated_rule_id = _truth_id(
                overlay_digest.value, layer.value, "rule", rule.rule_id
            )
            generated_revision_id = _truth_id(
                overlay_digest.value,
                layer.value,
                "rule-revision",
                rule.rule_id,
                rule.revision_id,
            )
            predicate_outcomes: list[PredicateOutcome] = []
            for index, predicate in enumerate(rule.predicates):
                outcome, supporting_facts = _evaluate_predicate(predicate, active_facts)
                predicate_outcomes.append(outcome)
                predicate_truth.append(
                    AbacPredicateTruthV1(
                        truth_id=_truth_id(
                            overlay_digest.value,
                            layer.value,
                            "predicate",
                            rule.rule_id,
                            rule.revision_id,
                            cell_id,
                            str(index),
                        ),
                        source_layer=layer,
                        rule_id=generated_rule_id,
                        revision_id=generated_revision_id,
                        cell_id=cell_id,
                        predicate_index=index,
                        outcome=outcome,
                        supporting_fact_ids=tuple(
                            sorted(
                                fact_truth_ids[item.fact_id]
                                for item in supporting_facts
                            )
                        ),
                    )
                )
            predicate_outcome = _combine_predicates(
                rule.operator, tuple(predicate_outcomes)
            )
            mechanism_outcome = _rule_outcome(predicate_outcome, rule.effect)
            truth_id = _truth_id(
                overlay_digest.value,
                layer.value,
                "rule-truth",
                rule.rule_id,
                rule.revision_id,
                cell_id,
            )
            truth_ids.append(truth_id)
            cell_outcomes.append(mechanism_outcome)
            rule_truth.append(
                AbacRuleTruthV1(
                    truth_id=truth_id,
                    source_layer=layer,
                    rule_id=generated_rule_id,
                    revision_id=generated_revision_id,
                    cell_id=cell_id,
                    effect=rule.effect,
                    predicate_outcome=predicate_outcome,
                    outcome=mechanism_outcome,
                )
            )
        outcomes[cell_id], conflicts[cell_id] = _combine_rules(cell_outcomes)
        cell_rule_ids[cell_id] = tuple(sorted(truth_ids))
    return _LayerResult(
        facts=tuple(fact_truth),
        predicates=tuple(predicate_truth),
        rules=tuple(rule_truth),
        outcomes=outcomes,
        conflicts=conflicts,
        rule_truth_ids=cell_rule_ids,
    )


def _active_facts(
    facts: list[AttributeFactBaseV1], tick: int
) -> dict[str, AttributeFactBaseV1]:
    result: dict[str, AttributeFactBaseV1] = {}
    for fact in facts:
        if not _active(tick, fact.valid_from_tick, fact.valid_until_tick):
            continue
        if fact.kind in result:
            raise EnterpriseCompileError(
                "overlapping_abac_fact_revisions",
                "more than one attribute revision is active for a cell and key",
            )
        result[fact.kind] = fact
    return result


def _active_rules(rules: list[AbacRuleV1], tick: int) -> tuple[AbacRuleV1, ...]:
    result: dict[str, AbacRuleV1] = {}
    for rule in rules:
        if not _active(tick, rule.valid_from_tick, rule.valid_until_tick):
            continue
        if rule.rule_id in result:
            raise EnterpriseCompileError(
                "overlapping_abac_rule_revisions",
                "more than one ABAC rule revision is active for a cell",
            )
        result[rule.rule_id] = rule
    return tuple(sorted(result.values(), key=lambda item: item.rule_id))


def _evaluate_predicate(
    predicate: AbacPredicateV1,
    facts: dict[str, AttributeFactBaseV1],
) -> tuple[PredicateOutcome, tuple[AttributeFactBaseV1, ...]]:
    if isinstance(predicate, SubjectKindIsV1):
        return _one_value(facts, "subject_principal_kind", predicate.values)
    if isinstance(predicate, EmploymentTypeIsV1):
        return _one_value(facts, "subject_employment_type", predicate.values)
    if isinstance(predicate, SameTenantV1):
        return _equal_values(facts, "subject_tenant_id", "resource_tenant_id")
    if isinstance(predicate, SubjectUnitIsV1):
        return _one_value(facts, "subject_unit_id", predicate.unit_ids)
    if isinstance(predicate, SubjectUnitOwnsTargetV1):
        return _equal_values(facts, "subject_unit_id", "resource_owner_unit_id")
    if isinstance(predicate, TargetKindIsV1):
        return _one_value(facts, "resource_target_kind", predicate.values)
    if isinstance(predicate, ClassificationWithinClearanceV1):
        return _ordered_values(
            facts,
            "resource_classification",
            "subject_clearance",
            _CLASSIFICATION_RANK,
        )
    if isinstance(predicate, ActionIsV1):
        return _one_value(facts, "action_id", predicate.action_ids)
    if isinstance(predicate, ActionClassIsV1):
        return _one_value(facts, "action_class", predicate.values)
    if isinstance(predicate, AssuranceAtLeastV1):
        return _minimum_value(
            facts, "environment_assurance_level", predicate.minimum, _ASSURANCE_RANK
        )
    if isinstance(predicate, NetworkZoneIsV1):
        return _one_value(facts, "environment_network_zone", predicate.values)
    raise AssertionError("closed ABAC predicate union was not exhaustive")


def _one_value(
    facts: dict[str, AttributeFactBaseV1],
    fact_kind: str,
    expected: tuple[object, ...],
) -> tuple[PredicateOutcome, tuple[AttributeFactBaseV1, ...]]:
    fact = facts.get(fact_kind)
    if fact is None:
        return PredicateOutcome.UNKNOWN, ()
    if fact.value_state is AttributeValueState.UNKNOWN:
        return PredicateOutcome.UNKNOWN, (fact,)
    return (
        PredicateOutcome.TRUE if fact.value in expected else PredicateOutcome.FALSE,
        (fact,),
    )


def _equal_values(
    facts: dict[str, AttributeFactBaseV1], left_kind: str, right_kind: str
) -> tuple[PredicateOutcome, tuple[AttributeFactBaseV1, ...]]:
    selected = tuple(
        item
        for item in (facts.get(left_kind), facts.get(right_kind))
        if item is not None
    )
    if len(selected) != 2 or any(
        item.value_state is AttributeValueState.UNKNOWN for item in selected
    ):
        return PredicateOutcome.UNKNOWN, selected
    return (
        PredicateOutcome.TRUE
        if selected[0].value == selected[1].value
        else PredicateOutcome.FALSE,
        selected,
    )


def _ordered_values[ValueT](
    facts: dict[str, AttributeFactBaseV1],
    lower_kind: str,
    upper_kind: str,
    ranks: dict[ValueT, int],
) -> tuple[PredicateOutcome, tuple[AttributeFactBaseV1, ...]]:
    selected = tuple(
        item
        for item in (facts.get(lower_kind), facts.get(upper_kind))
        if item is not None
    )
    if len(selected) != 2 or any(
        item.value_state is AttributeValueState.UNKNOWN for item in selected
    ):
        return PredicateOutcome.UNKNOWN, selected
    lower = cast(ValueT, selected[0].value)
    upper = cast(ValueT, selected[1].value)
    return (
        (
            PredicateOutcome.TRUE
            if ranks[lower] <= ranks[upper]
            else PredicateOutcome.FALSE
        ),
        selected,
    )


def _minimum_value[ValueT](
    facts: dict[str, AttributeFactBaseV1],
    fact_kind: str,
    minimum: ValueT,
    ranks: dict[ValueT, int],
) -> tuple[PredicateOutcome, tuple[AttributeFactBaseV1, ...]]:
    fact = facts.get(fact_kind)
    if fact is None:
        return PredicateOutcome.UNKNOWN, ()
    if fact.value_state is AttributeValueState.UNKNOWN:
        return PredicateOutcome.UNKNOWN, (fact,)
    actual = cast(ValueT, fact.value)
    return (
        (
            PredicateOutcome.TRUE
            if ranks[actual] >= ranks[minimum]
            else PredicateOutcome.FALSE
        ),
        (fact,),
    )


def _combine_predicates(
    operator: FlatRuleOperator, outcomes: tuple[PredicateOutcome, ...]
) -> PredicateOutcome:
    if operator is FlatRuleOperator.ALL:
        if PredicateOutcome.FALSE in outcomes:
            return PredicateOutcome.FALSE
        if PredicateOutcome.UNKNOWN in outcomes:
            return PredicateOutcome.UNKNOWN
        return PredicateOutcome.TRUE
    if PredicateOutcome.TRUE in outcomes:
        return PredicateOutcome.TRUE
    if PredicateOutcome.UNKNOWN in outcomes:
        return PredicateOutcome.UNKNOWN
    return PredicateOutcome.FALSE


def _rule_outcome(
    predicate_outcome: PredicateOutcome, effect: RuleEffect
) -> MechanismOutcome:
    if predicate_outcome is PredicateOutcome.UNKNOWN:
        return MechanismOutcome.UNKNOWN
    if predicate_outcome is PredicateOutcome.FALSE:
        return MechanismOutcome.NOT_APPLICABLE
    return (
        MechanismOutcome.ALLOW if effect is RuleEffect.ALLOW else MechanismOutcome.DENY
    )


def _combine_rules(
    outcomes: list[MechanismOutcome],
) -> tuple[MechanismOutcome, bool]:
    has_allow = MechanismOutcome.ALLOW in outcomes
    has_deny = MechanismOutcome.DENY in outcomes
    if has_deny:
        return MechanismOutcome.DENY, has_allow
    if has_allow:
        return MechanismOutcome.ALLOW, False
    if MechanismOutcome.UNKNOWN in outcomes:
        return MechanismOutcome.UNKNOWN, False
    return MechanismOutcome.NOT_APPLICABLE, False


def _active(tick: int, start: int, end: int | None) -> bool:
    return tick >= start and (end is None or tick < end)


def _string_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, StrEnum):
        return value.value
    return cast(str, value)


def _truth_id(*parts: str) -> str:
    return str(uuid5(ENTERPRISE_ABAC_TRUTH_RECORD_NAMESPACE_V1, encode_parts(parts)))


def _enforce_limit(code: str, measured: int, allowed: int) -> None:
    if measured > allowed:
        raise EnterpriseCompileError(
            code,
            "ABAC compilation exceeds an independent bounded limit",
            measured=measured,
            allowed=allowed,
        )


def _check_outer_safety(
    truth: CompiledEnterpriseAbacTruthV1,
    config: EnterpriseIdentityAccessCompileConfigV1,
) -> None:
    payload_size = len(canonical_json_bytes(truth))
    _enforce_limit(
        "abac_outer_byte_budget_exceeded",
        payload_size,
        config.outer_safety.max_canonical_bytes,
    )
    supporting_relations = sum(
        len(item.supporting_fact_ids) for item in truth.predicate_truth
    )
    _enforce_limit(
        "abac_outer_relation_budget_exceeded",
        supporting_relations,
        config.outer_safety.max_relations,
    )


__all__ = ["compile_enterprise_abac_truth"]
