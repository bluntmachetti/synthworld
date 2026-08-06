"""Bounded offline ReBAC evaluation with deterministic explain paths."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from uuid import UUID, uuid5

from synthworld.enterprise.authorization_common import (
    AuthorizationSourceLayer,
    MechanismOutcome,
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
    PrincipalKind,
    SyntheticDigestV1,
)
from synthworld.enterprise.rbac.corpus_models import (
    AccessEvaluationCellV1,
    EnterpriseEvaluationCorpusV1,
)
from synthworld.enterprise.rebac.common import RebacRelation
from synthworld.enterprise.rebac.models import (
    CompiledEnterpriseRebacTruthV1,
    DirectSubjectRelationV1,
    EnterpriseRebacIntentOverlayV1,
    EnterpriseRebacStateOverlayV1,
    GroupCollaborationV1,
    ManagerOfOwnerV1,
    RebacCellTruthV1,
    RebacPathTruthV1,
    RebacRuleBaseV1,
    RebacRuleTruthV1,
    RebacTupleTruthV1,
    RelationTupleV1,
)

ENTERPRISE_REBAC_TRUTH_RECORD_NAMESPACE_V1 = UUID(
    "c6be0ad4-e95a-5dad-bc2c-8cc54edac965"
)

_HUMAN_KINDS = {
    PrincipalKind.EMPLOYEE,
    PrincipalKind.CONTRACTOR,
    PrincipalKind.SUPPLIER,
    PrincipalKind.PARTNER,
}


@dataclass(frozen=True, slots=True)
class _Entity:
    kind: str
    tenant_id: str
    human: bool = False


@dataclass(slots=True)
class _ExpansionBudget:
    max_expansions: int
    max_paths_per_cell: int
    max_total_paths: int
    expansions: int = 0
    total_paths: int = 0

    def consume_expansions(self, count: int) -> None:
        self.expansions += count
        _enforce_limit(
            "rebac_path_expansion_budget_exceeded",
            self.expansions,
            self.max_expansions,
        )

    def consume_paths(self, count: int, prior_for_cell: int) -> None:
        _enforce_limit(
            "rebac_paths_per_cell_budget_exceeded",
            prior_for_cell + count,
            self.max_paths_per_cell,
        )
        self.total_paths += count
        _enforce_limit(
            "rebac_total_derivation_budget_exceeded",
            self.total_paths,
            self.max_total_paths,
        )


@dataclass(frozen=True, slots=True)
class _LayerResult:
    tuples: tuple[RebacTupleTruthV1, ...]
    paths: tuple[RebacPathTruthV1, ...]
    rules: tuple[RebacRuleTruthV1, ...]
    outcomes: dict[str, MechanismOutcome]
    conflicts: dict[str, bool]
    rule_truth_ids: dict[str, tuple[str, ...]]
    path_ids: dict[str, tuple[str, ...]]


def compile_enterprise_rebac_truth(
    *,
    universe: EnterpriseIdentityAccessUniverseV1,
    corpus: EnterpriseEvaluationCorpusV1,
    rebac_state: EnterpriseRebacStateOverlayV1,
    rebac_intent: EnterpriseRebacIntentOverlayV1,
    compile_config: EnterpriseIdentityAccessCompileConfigV1 | None = None,
) -> CompiledEnterpriseRebacTruthV1:
    """Compile three fixed path templates without a userset or rewrite engine."""

    config = compile_config or EnterpriseIdentityAccessCompileConfigV1()
    universe_digest = synthetic_digest(canonical_json_bytes(universe))
    corpus_digest = synthetic_digest(canonical_json_bytes(corpus))
    _validate_bindings(
        corpus,
        rebac_state,
        rebac_intent,
        universe_digest,
        corpus_digest,
    )
    cells = {item.cell_id: item for item in corpus.evaluation_cells}
    atoms = {item.access_atom_id: item for item in universe.access_atoms}
    entities = _entity_index(universe)
    _validate_overlay(rebac_state, cells, entities)
    _validate_overlay(rebac_intent, cells, entities)
    _preflight_budgets(rebac_state, rebac_intent, cells, config)
    state_digest = synthetic_digest(canonical_json_bytes(rebac_state))
    intent_digest = synthetic_digest(canonical_json_bytes(rebac_intent))
    budget = _ExpansionBudget(
        max_expansions=config.budget.max_rebac_path_expansions,
        max_paths_per_cell=min(
            config.budget.max_rebac_paths_per_cell,
            config.budget.max_derivations_per_cell,
        ),
        max_total_paths=config.budget.max_total_derivations,
    )
    paths_per_cell: dict[str, int] = defaultdict(int)
    actual = _compile_layer(
        AuthorizationSourceLayer.ACTUAL,
        rebac_state.relation_tuples,
        rebac_state.rules,
        set(rebac_state.unknown_evidence_cell_ids),
        cells,
        atoms,
        state_digest,
        budget,
        paths_per_cell,
    )
    intended = _compile_layer(
        AuthorizationSourceLayer.INTENDED,
        rebac_intent.relation_tuples,
        rebac_intent.rules,
        set(rebac_intent.unknown_evidence_cell_ids),
        cells,
        atoms,
        intent_digest,
        budget,
        paths_per_cell,
    )
    truth = CompiledEnterpriseRebacTruthV1(
        identity_access_universe_digest=universe_digest,
        evaluation_corpus_digest=corpus_digest,
        rebac_state_digest=state_digest,
        rebac_intent_digest=intent_digest,
        relation_tuples=actual.tuples + intended.tuples,
        paths=actual.paths + intended.paths,
        rule_truth=actual.rules + intended.rules,
        cells=tuple(
            RebacCellTruthV1(
                cell_id=cell_id,
                actual_outcome=actual.outcomes[cell_id],
                intended_outcome=intended.outcomes[cell_id],
                actual_conflict=actual.conflicts[cell_id],
                intended_conflict=intended.conflicts[cell_id],
                actual_rule_truth_ids=actual.rule_truth_ids[cell_id],
                intended_rule_truth_ids=intended.rule_truth_ids[cell_id],
                actual_path_ids=actual.path_ids[cell_id],
                intended_path_ids=intended.path_ids[cell_id],
            )
            for cell_id in sorted(cells)
        ),
    )
    _check_outer_safety(truth, config)
    return truth


def _validate_bindings(
    corpus: EnterpriseEvaluationCorpusV1,
    state: EnterpriseRebacStateOverlayV1,
    intent: EnterpriseRebacIntentOverlayV1,
    universe_digest: SyntheticDigestV1,
    corpus_digest: SyntheticDigestV1,
) -> None:
    if corpus.identity_access_universe_digest != universe_digest:
        raise EnterpriseCompileError(
            "rebac_corpus_universe_digest_mismatch",
            "evaluation corpus does not bind the supplied universe",
        )
    for label, overlay in (("state", state), ("intent", intent)):
        if overlay.identity_access_universe_digest != universe_digest:
            raise EnterpriseCompileError(
                f"rebac_{label}_universe_digest_mismatch",
                f"ReBAC {label} does not bind the supplied universe",
            )
        if overlay.evaluation_corpus_digest != corpus_digest:
            raise EnterpriseCompileError(
                f"rebac_{label}_corpus_digest_mismatch",
                f"ReBAC {label} does not bind the supplied corpus",
            )


def _entity_index(universe: EnterpriseIdentityAccessUniverseV1) -> dict[str, _Entity]:
    result: dict[str, _Entity] = {}
    for principal in universe.principals:
        result[principal.principal_id] = _Entity(
            "principal",
            principal.tenant_id,
            principal.principal_kind in _HUMAN_KINDS,
        )
    for account in universe.accounts:
        result[account.account_id] = _Entity("account", account.tenant_id)
    for group in universe.groups:
        result[group.group_id] = _Entity("group", group.tenant_id)
    for unit in universe.units:
        result[unit.unit_id] = _Entity("unit", unit.tenant_id)
    for target in universe.authorization_targets:
        result[target.authorization_target_id] = _Entity(
            "authorization_target", target.tenant_id
        )
    return result


def _validate_overlay(
    overlay: EnterpriseRebacStateOverlayV1 | EnterpriseRebacIntentOverlayV1,
    cells: dict[str, AccessEvaluationCellV1],
    entities: dict[str, _Entity],
) -> None:
    for cell_id in overlay.unknown_evidence_cell_ids:
        _require_cell(cell_id, cells, "rebac_unknown_evidence")
    for rule in overlay.rules:
        for cell_id in rule.cell_ids:
            _require_cell(cell_id, cells, "rebac_rule")
    for item in overlay.relation_tuples:
        subject = entities.get(item.subject_entity_id)
        target = entities.get(item.object_entity_id)
        if subject is None or target is None:
            raise EnterpriseCompileError(
                "unknown_rebac_tuple_entity",
                "ReBAC tuple entity does not resolve in the frozen universe",
            )
        if subject.tenant_id != item.tenant_id or target.tenant_id != item.tenant_id:
            raise EnterpriseCompileError(
                "cross_tenant_rebac_tuple",
                "ReBAC tuple tenant must contain both typed endpoints",
            )
        if not _valid_relation_matrix(item.relation, subject, target):
            raise EnterpriseCompileError(
                "invalid_rebac_relation_type_matrix",
                "ReBAC relation endpoints do not match the closed V1 type matrix",
            )


def _valid_relation_matrix(
    relation: RebacRelation, subject: _Entity, target: _Entity
) -> bool:
    if relation is RebacRelation.MEMBER_OF:
        return subject.kind in {"principal", "account"} and target.kind == "group"
    if relation is RebacRelation.OWNS:
        return subject.kind in {"principal", "unit"} and (
            target.kind == "authorization_target"
        )
    if relation is RebacRelation.MANAGES:
        return (
            subject.kind == "principal"
            and target.kind == "principal"
            and subject.human
            and target.human
        )
    return subject.kind in {"principal", "account", "group"} and (
        target.kind == "authorization_target"
    )


def _require_cell(
    cell_id: str, cells: dict[str, AccessEvaluationCellV1], owner: str
) -> None:
    if cell_id not in cells:
        raise EnterpriseCompileError(
            f"undeclared_{owner}_cell",
            f"{owner.replace('_', ' ')} references a cell outside the frozen corpus",
        )


def _preflight_budgets(
    state: EnterpriseRebacStateOverlayV1,
    intent: EnterpriseRebacIntentOverlayV1,
    cells: dict[str, AccessEvaluationCellV1],
    config: EnterpriseIdentityAccessCompileConfigV1,
) -> None:
    tuples = len(state.relation_tuples) + len(intent.relation_tuples)
    rules = len(state.rules) + len(intent.rules)
    _enforce_limit(
        "rebac_tuple_budget_exceeded", tuples, config.budget.max_rebac_tuples
    )
    _enforce_limit("rebac_rule_budget_exceeded", rules, config.budget.max_rebac_rules)
    target_cells = {
        cell_id for rule in (*state.rules, *intent.rules) for cell_id in rule.cell_ids
    }
    unique_ticks = {cells[cell_id].tick for cell_id in target_cells}
    interval_scan_work = len(unique_ticks) * tuples
    work = interval_scan_work + rules + len(target_cells)
    _enforce_limit(
        "rebac_outer_work_budget_exceeded", work, config.outer_safety.max_work_units
    )
    minimum_records = tuples + rules + len(cells)
    _enforce_limit(
        "rebac_outer_record_budget_exceeded",
        minimum_records,
        config.outer_safety.max_serialized_records,
    )


def _compile_layer(
    layer: AuthorizationSourceLayer,
    tuples: tuple[RelationTupleV1, ...],
    rules: tuple[RebacRuleBaseV1, ...],
    unknown_cells: set[str],
    cells: dict[str, AccessEvaluationCellV1],
    atoms: dict[str, AccessAtomV1],
    overlay_digest: SyntheticDigestV1,
    budget: _ExpansionBudget,
    paths_per_cell: dict[str, int],
) -> _LayerResult:
    tuple_truth, tuple_ids = _compile_tuple_truth(layer, tuples, overlay_digest)
    rules_by_cell: dict[str, list[RebacRuleBaseV1]] = defaultdict(list)
    for rule in rules:
        for cell_id in rule.cell_ids:
            rules_by_cell[cell_id].append(rule)
    active_by_tick: dict[int, tuple[RelationTupleV1, ...]] = {}
    paths: list[RebacPathTruthV1] = []
    rule_truth: list[RebacRuleTruthV1] = []
    outcomes: dict[str, MechanismOutcome] = {}
    conflicts: dict[str, bool] = {}
    truth_ids_by_cell: dict[str, tuple[str, ...]] = {}
    path_ids_by_cell: dict[str, tuple[str, ...]] = {}
    for cell_id in sorted(cells):
        cell = cells[cell_id]
        atom = atoms.get(cell.access_atom_id)
        if atom is None:
            raise EnterpriseCompileError(
                "undeclared_access_atom",
                "frozen ReBAC cell references an absent access atom",
            )
        active_tuples = active_by_tick.setdefault(
            cell.tick, _active_tuples(tuples, cell.tick)
        )
        active_rules = _active_rules(rules_by_cell[cell_id], cell.tick)
        cell_rule_outcomes: list[MechanismOutcome] = []
        cell_truth_ids: list[str] = []
        cell_path_ids: list[str] = []
        for rule in active_rules:
            logical_paths = _enumerate_rule_paths(rule, atom, active_tuples, budget)
            budget.consume_paths(len(logical_paths), paths_per_cell[cell_id])
            paths_per_cell[cell_id] += len(logical_paths)
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
            rule_path_ids: list[str] = []
            for logical_path in logical_paths:
                generated_tuple_ids = tuple(
                    tuple_ids[_tuple_key(item)] for item in logical_path
                )
                path_id = _truth_id(
                    overlay_digest.value,
                    layer.value,
                    "path",
                    rule.rule_id,
                    rule.revision_id,
                    cell_id,
                    *generated_tuple_ids,
                )
                rule_path_ids.append(path_id)
                cell_path_ids.append(path_id)
                paths.append(
                    RebacPathTruthV1(
                        path_id=path_id,
                        source_layer=layer,
                        rule_id=generated_rule_id,
                        revision_id=generated_revision_id,
                        cell_id=cell_id,
                        template=rule.template,
                        subject_id=atom.subject_id,
                        authorization_target_id=atom.authorization_target_id,
                        tuple_ids=generated_tuple_ids,
                    )
                )
            outcome = _rule_outcome(
                bool(logical_paths), cell_id in unknown_cells, rule.effect
            )
            truth_id = _truth_id(
                overlay_digest.value,
                layer.value,
                "rule-truth",
                rule.rule_id,
                rule.revision_id,
                cell_id,
            )
            cell_truth_ids.append(truth_id)
            cell_rule_outcomes.append(outcome)
            rule_truth.append(
                RebacRuleTruthV1(
                    truth_id=truth_id,
                    source_layer=layer,
                    rule_id=generated_rule_id,
                    revision_id=generated_revision_id,
                    cell_id=cell_id,
                    template=rule.template,
                    effect=rule.effect,
                    outcome=outcome,
                    path_ids=tuple(rule_path_ids),
                )
            )
        outcomes[cell_id], conflicts[cell_id] = _combine_rules(cell_rule_outcomes)
        truth_ids_by_cell[cell_id] = tuple(sorted(cell_truth_ids))
        path_ids_by_cell[cell_id] = tuple(sorted(cell_path_ids))
    return _LayerResult(
        tuples=tuple_truth,
        paths=tuple(paths),
        rules=tuple(rule_truth),
        outcomes=outcomes,
        conflicts=conflicts,
        rule_truth_ids=truth_ids_by_cell,
        path_ids=path_ids_by_cell,
    )


def _compile_tuple_truth(
    layer: AuthorizationSourceLayer,
    tuples: tuple[RelationTupleV1, ...],
    overlay_digest: SyntheticDigestV1,
) -> tuple[tuple[RebacTupleTruthV1, ...], dict[tuple[str, str], str]]:
    rows: list[RebacTupleTruthV1] = []
    ids: dict[tuple[str, str], str] = {}
    for item in tuples:
        tuple_id = _truth_id(
            overlay_digest.value,
            layer.value,
            "tuple",
            item.tuple_id,
            item.revision_id,
        )
        ids[_tuple_key(item)] = tuple_id
        rows.append(
            RebacTupleTruthV1(
                tuple_id=tuple_id,
                revision_id=_truth_id(
                    overlay_digest.value,
                    layer.value,
                    "tuple-revision",
                    item.tuple_id,
                    item.revision_id,
                ),
                source_layer=layer,
                tenant_id=item.tenant_id,
                subject_entity_id=item.subject_entity_id,
                relation=item.relation,
                object_entity_id=item.object_entity_id,
                snapshot_id=_truth_id(
                    overlay_digest.value, layer.value, "snapshot", item.snapshot_id
                ),
                valid_from_tick=item.valid_from_tick,
                valid_until_tick=item.valid_until_tick,
            )
        )
    return tuple(rows), ids


def _active_tuples(
    tuples: tuple[RelationTupleV1, ...], tick: int
) -> tuple[RelationTupleV1, ...]:
    result: dict[str, RelationTupleV1] = {}
    for item in tuples:
        if not _active(tick, item.valid_from_tick, item.valid_until_tick):
            continue
        if item.tuple_id in result:
            raise EnterpriseCompileError(
                "overlapping_rebac_tuple_revisions",
                "more than one ReBAC tuple revision is active at a cell tick",
            )
        result[item.tuple_id] = item
    return tuple(sorted(result.values(), key=_tuple_sort_key))


def _active_rules(
    rules: list[RebacRuleBaseV1], tick: int
) -> tuple[RebacRuleBaseV1, ...]:
    result: dict[str, RebacRuleBaseV1] = {}
    for rule in rules:
        if not _active(tick, rule.valid_from_tick, rule.valid_until_tick):
            continue
        if rule.rule_id in result:
            raise EnterpriseCompileError(
                "overlapping_rebac_rule_revisions",
                "more than one ReBAC rule revision is active at a cell tick",
            )
        result[rule.rule_id] = rule
    return tuple(sorted(result.values(), key=lambda item: item.rule_id))


def _enumerate_rule_paths(
    rule: RebacRuleBaseV1,
    atom: AccessAtomV1,
    tuples: tuple[RelationTupleV1, ...],
    budget: _ExpansionBudget,
) -> tuple[tuple[RelationTupleV1, ...], ...]:
    if isinstance(rule, DirectSubjectRelationV1):
        matches = tuple(
            (item,)
            for item in tuples
            if item.subject_entity_id == atom.subject_id
            and item.relation is rule.relation
            and item.object_entity_id == atom.authorization_target_id
        )
        budget.consume_expansions(len(matches))
        return matches
    if isinstance(rule, GroupCollaborationV1):
        memberships = tuple(
            item
            for item in tuples
            if item.subject_entity_id == atom.subject_id
            and item.relation is RebacRelation.MEMBER_OF
        )
        budget.consume_expansions(len(memberships))
        paths: list[tuple[RelationTupleV1, ...]] = []
        for membership in memberships:
            collaborations = tuple(
                item
                for item in tuples
                if item.subject_entity_id == membership.object_entity_id
                and item.relation is RebacRelation.COLLABORATES_ON
                and item.object_entity_id == atom.authorization_target_id
                and item.snapshot_id == membership.snapshot_id
            )
            budget.consume_expansions(len(collaborations))
            paths.extend((membership, item) for item in collaborations)
        return tuple(paths)
    if isinstance(rule, ManagerOfOwnerV1):
        managers = tuple(
            item
            for item in tuples
            if item.subject_entity_id == atom.subject_id
            and item.relation is RebacRelation.MANAGES
        )
        budget.consume_expansions(len(managers))
        paths = []
        for manager in managers:
            ownerships = tuple(
                item
                for item in tuples
                if item.subject_entity_id == manager.object_entity_id
                and item.relation is RebacRelation.OWNS
                and item.object_entity_id == atom.authorization_target_id
                and item.snapshot_id == manager.snapshot_id
            )
            budget.consume_expansions(len(ownerships))
            paths.extend((manager, item) for item in ownerships)
        return tuple(paths)
    raise AssertionError("closed ReBAC rule union was not exhaustive")


def _rule_outcome(
    has_path: bool, evidence_unknown: bool, effect: RuleEffect
) -> MechanismOutcome:
    if has_path:
        return (
            MechanismOutcome.ALLOW
            if effect is RuleEffect.ALLOW
            else MechanismOutcome.DENY
        )
    if evidence_unknown:
        return MechanismOutcome.UNKNOWN
    return MechanismOutcome.NOT_APPLICABLE


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


def _tuple_key(item: RelationTupleV1) -> tuple[str, str]:
    return item.tuple_id, item.revision_id


def _tuple_sort_key(item: RelationTupleV1) -> tuple[str, ...]:
    return (
        item.relation.value,
        item.subject_entity_id,
        item.object_entity_id,
        item.snapshot_id,
        item.tuple_id,
        item.revision_id,
    )


def _active(tick: int, start: int, end: int | None) -> bool:
    return tick >= start and (end is None or tick < end)


def _truth_id(*parts: str) -> str:
    return str(uuid5(ENTERPRISE_REBAC_TRUTH_RECORD_NAMESPACE_V1, encode_parts(parts)))


def _enforce_limit(code: str, measured: int, allowed: int) -> None:
    if measured > allowed:
        raise EnterpriseCompileError(
            code,
            "ReBAC compilation exceeds an independent bounded limit",
            measured=measured,
            allowed=allowed,
        )


def _check_outer_safety(
    truth: CompiledEnterpriseRebacTruthV1,
    config: EnterpriseIdentityAccessCompileConfigV1,
) -> None:
    record_count = (
        len(truth.relation_tuples)
        + len(truth.paths)
        + len(truth.rule_truth)
        + len(truth.cells)
    )
    _enforce_limit(
        "rebac_outer_record_budget_exceeded",
        record_count,
        config.outer_safety.max_serialized_records,
    )
    relation_count = sum(len(item.tuple_ids) for item in truth.paths)
    _enforce_limit(
        "rebac_outer_relation_budget_exceeded",
        relation_count,
        config.outer_safety.max_relations,
    )
    _enforce_limit(
        "rebac_outer_byte_budget_exceeded",
        len(canonical_json_bytes(truth)),
        config.outer_safety.max_canonical_bytes,
    )


__all__ = ["compile_enterprise_rebac_truth"]
