"""Deterministically compile an explicit, non-Cartesian evaluation corpus."""

from __future__ import annotations

from collections import Counter
from uuid import UUID, uuid5

from synthworld.enterprise.canonical import (
    canonical_json_bytes,
    canonical_json_value_bytes,
    encode_parts,
    synthetic_digest,
)
from synthworld.enterprise.compiler import EnterpriseCompileError
from synthworld.enterprise.models import (
    AccessAtomV1,
    EnterpriseAccessSubjectV1,
    EnterpriseIdentityAccessUniverseV1,
    EnterpriseRoleV1,
)
from synthworld.enterprise.rbac.common import ENTERPRISE_CORPUS_COMPILER_VERSION
from synthworld.enterprise.rbac.corpus_models import (
    AccessEvaluationCellTemplateV1,
    AccessEvaluationCellV1,
    AuthorizationSessionSlotTemplateV1,
    AuthorizationSessionSlotV1,
    EnterpriseAccessRequestV1,
    EnterpriseContextTemplateV1,
    EnterpriseContextV1,
    EnterpriseEvaluationCaseInventoryV1,
    EnterpriseEvaluationCaseV1,
    EnterpriseEvaluationCorpusCompileResultV1,
    EnterpriseEvaluationCorpusConfigV1,
    EnterpriseEvaluationCorpusV1,
    RoleActivationRequestV1,
)

ENTERPRISE_CONTEXT_NAMESPACE_V1 = UUID("76143385-578b-5b02-8fc3-c83a9edc3214")
ENTERPRISE_SESSION_STATE_NAMESPACE_V1 = UUID("3aae035c-843c-524a-96be-f9ec6130852a")
ENTERPRISE_SESSION_NAMESPACE_V1 = UUID("57e5a979-c173-52c2-be68-cd95b714fa9c")
ENTERPRISE_ACTIVATION_REQUEST_NAMESPACE_V1 = UUID(
    "d0963c42-cb83-54f8-8538-17d68a3f2ab8"
)
ENTERPRISE_EVALUATION_CELL_NAMESPACE_V1 = UUID("2effd006-35c1-558e-ae4e-9dc42b4cbccf")
ENTERPRISE_ACCESS_REQUEST_NAMESPACE_V1 = UUID("4807ce8d-96ef-5ed9-97b4-2df587e54880")
ENTERPRISE_EVALUATOR_CASE_NAMESPACE_V1 = UUID("2ed40c95-45e4-543e-a286-e79d5d47f585")


def compile_enterprise_evaluation_corpus(
    *,
    universe: EnterpriseIdentityAccessUniverseV1,
    corpus_config: EnterpriseEvaluationCorpusConfigV1,
) -> EnterpriseEvaluationCorpusCompileResultV1:
    """Freeze exactly the declared contexts, sessions, requests, cells, and cases."""

    universe_digest = synthetic_digest(canonical_json_bytes(universe))
    if corpus_config.identity_access_universe_digest != universe_digest:
        raise EnterpriseCompileError(
            "corpus_universe_digest_mismatch",
            "corpus config does not bind the supplied identity/access universe",
        )
    _check_corpus_budgets(corpus_config)

    subjects = {item.subject_id: item for item in universe.access_subjects}
    roles = {item.role_id: item for item in universe.roles}
    atoms = {item.access_atom_id: item for item in universe.access_atoms}
    context_templates = {item.context_key: item for item in corpus_config.contexts}
    slot_templates = {
        item.session_state_key: item for item in corpus_config.session_slots
    }
    cell_templates = {item.cell_key: item for item in corpus_config.evaluation_cells}

    _validate_session_templates(slot_templates, subjects)
    _validate_activation_templates(corpus_config, slot_templates, subjects, roles)
    _validate_cell_templates(cell_templates, context_templates, slot_templates, atoms)
    _validate_access_request_templates(corpus_config, cell_templates)
    _validate_case_templates(corpus_config, cell_templates)

    config_digest = synthetic_digest(canonical_json_bytes(corpus_config))
    digest_value = config_digest.value
    contexts_by_key = {
        item.context_key: EnterpriseContextV1(
            context_id=_stable_id(
                ENTERPRISE_CONTEXT_NAMESPACE_V1, digest_value, item.context_key
            )
        )
        for item in corpus_config.contexts
    }
    sessions_by_key = {
        item.session_state_key: AuthorizationSessionSlotV1(
            session_state_id=_stable_id(
                ENTERPRISE_SESSION_STATE_NAMESPACE_V1,
                digest_value,
                item.session_state_key,
            ),
            session_id=_stable_id(
                ENTERPRISE_SESSION_NAMESPACE_V1, digest_value, item.session_key
            ),
            subject_id=item.subject_id,
            activation_tick=item.activation_tick,
            valid_until_tick=item.valid_until_tick,
        )
        for item in corpus_config.session_slots
    }
    activation_requests_by_key = {
        item.request_key: RoleActivationRequestV1(
            activation_request_id=_stable_id(
                ENTERPRISE_ACTIVATION_REQUEST_NAMESPACE_V1,
                digest_value,
                item.request_key,
            ),
            session_state_id=sessions_by_key[item.session_state_key].session_state_id,
            session_id=sessions_by_key[item.session_state_key].session_id,
            subject_id=sessions_by_key[item.session_state_key].subject_id,
            request_tick=sessions_by_key[item.session_state_key].activation_tick,
            requested_role_ids=item.requested_role_ids,
        )
        for item in corpus_config.role_activation_requests
    }
    cells_by_key = {
        item.cell_key: _compile_cell(
            item,
            config_digest=digest_value,
            contexts_by_key=contexts_by_key,
            sessions_by_key=sessions_by_key,
        )
        for item in corpus_config.evaluation_cells
    }
    access_requests_by_key = {
        item.request_key: EnterpriseAccessRequestV1(
            access_request_id=_stable_id(
                ENTERPRISE_ACCESS_REQUEST_NAMESPACE_V1,
                digest_value,
                item.request_key,
            ),
            cell_id=cells_by_key[item.cell_key].cell_id,
        )
        for item in corpus_config.access_requests
    }
    cells = tuple(sorted(cells_by_key.values(), key=lambda item: item.cell_id))
    cell_digest = synthetic_digest(
        canonical_json_value_bytes(
            {
                "schema_version": "1.0.0",
                "evaluation_cells": [item.model_dump(mode="json") for item in cells],
            }
        )
    )
    corpus = EnterpriseEvaluationCorpusV1(
        identity_access_universe_digest=universe_digest,
        corpus_config_digest=config_digest,
        compile_config_digest=synthetic_digest(
            canonical_json_bytes(corpus_config.compile_config)
        ),
        evaluation_cell_digest=cell_digest,
        contexts=tuple(contexts_by_key.values()),
        session_slots=tuple(sessions_by_key.values()),
        role_activation_requests=tuple(activation_requests_by_key.values()),
        evaluation_cells=cells,
        access_requests=tuple(access_requests_by_key.values()),
    )
    corpus_digest = synthetic_digest(canonical_json_bytes(corpus))
    activation_ids = {
        key: value.activation_request_id
        for key, value in activation_requests_by_key.items()
    }
    cases = tuple(
        EnterpriseEvaluationCaseV1(
            case_id=_stable_id(
                ENTERPRISE_EVALUATOR_CASE_NAMESPACE_V1,
                digest_value,
                item.case_key,
            ),
            target_kind=item.target_kind,
            target_id=(
                cells_by_key[item.target_key].cell_id
                if item.target_kind.value == "access_cell"
                else activation_ids[item.target_key]
            ),
            labels=item.labels,
        )
        for item in corpus_config.evaluator_cases
    )
    return EnterpriseEvaluationCorpusCompileResultV1(
        public_corpus=corpus,
        evaluator_case_inventory=EnterpriseEvaluationCaseInventoryV1(
            evaluation_corpus_digest=corpus_digest,
            cases=cases,
        ),
    )


def _validate_session_templates(
    slots: dict[str, AuthorizationSessionSlotTemplateV1],
    subjects: dict[str, EnterpriseAccessSubjectV1],
) -> None:
    for key, slot in slots.items():
        if slot.subject_id not in subjects:
            raise EnterpriseCompileError(
                "unknown_session_subject",
                f"session slot {key!r} has an unknown subject",
            )
        if (
            slot.valid_until_tick is not None
            and slot.valid_until_tick <= slot.activation_tick
        ):
            raise EnterpriseCompileError(
                "session_validity_interval_invalid",
                "session validity must be a nonempty half-open interval",
            )


def _validate_activation_templates(
    config: EnterpriseEvaluationCorpusConfigV1,
    slots: dict[str, AuthorizationSessionSlotTemplateV1],
    subjects: dict[str, EnterpriseAccessSubjectV1],
    roles: dict[str, EnterpriseRoleV1],
) -> None:
    for request in config.role_activation_requests:
        if request.session_state_key not in slots:
            raise EnterpriseCompileError(
                "unknown_activation_session",
                "activation request references an unknown session slot",
            )
    counts = Counter(item.session_state_key for item in config.role_activation_requests)
    if set(counts) != set(slots) or any(count != 1 for count in counts.values()):
        raise EnterpriseCompileError(
            "session_activation_request_cardinality",
            "each session slot must resolve exactly one activation request",
        )
    for request in config.role_activation_requests:
        slot = slots[request.session_state_key]
        slot_subject = subjects[slot.subject_id]
        for role_id in request.requested_role_ids:
            role = roles.get(role_id)
            if role is None:
                raise EnterpriseCompileError(
                    "unknown_activation_role",
                    "activation request references an unknown role",
                )
            if role.tenant_id != slot_subject.tenant_id:
                raise EnterpriseCompileError(
                    "cross_tenant_activation_role",
                    "activation roles must share the session subject tenant",
                )


def _validate_cell_templates(
    cells: dict[str, AccessEvaluationCellTemplateV1],
    contexts: dict[str, EnterpriseContextTemplateV1],
    slots: dict[str, AuthorizationSessionSlotTemplateV1],
    atoms: dict[str, AccessAtomV1],
) -> None:
    semantic_keys: set[tuple[str, str, str | None, int]] = set()
    for cell in cells.values():
        atom = atoms.get(cell.access_atom_id)
        if atom is None:
            raise EnterpriseCompileError(
                "unknown_cell_access_atom", "evaluation cell has an unknown access atom"
            )
        if cell.context_key not in contexts:
            raise EnterpriseCompileError(
                "unknown_cell_context", "evaluation cell has an unknown context"
            )
        slot = (
            slots.get(cell.session_state_key)
            if cell.session_state_key is not None
            else None
        )
        if cell.session_state_key is not None and slot is None:
            raise EnterpriseCompileError(
                "unknown_cell_session", "evaluation cell has an unknown session slot"
            )
        if slot is not None:
            if slot.subject_id != atom.subject_id:
                raise EnterpriseCompileError(
                    "cross_subject_cell_session",
                    "a cell session must belong to the access-atom subject",
                )
            if cell.tick < slot.activation_tick:
                raise EnterpriseCompileError(
                    "cell_before_session_activation",
                    "a cell cannot use a session before its activation tick",
                )
            if slot.valid_until_tick is not None and cell.tick >= slot.valid_until_tick:
                raise EnterpriseCompileError(
                    "cell_at_or_after_session_expiry",
                    "a cell must fall inside the session half-open interval",
                )
        semantic_key = (
            cell.access_atom_id,
            cell.context_key,
            cell.session_state_key,
            cell.tick,
        )
        if semantic_key in semantic_keys:
            raise EnterpriseCompileError(
                "duplicate_evaluation_cell_tuple",
                "two cell keys declare the same evaluation tuple",
            )
        semantic_keys.add(semantic_key)


def _validate_access_request_templates(
    config: EnterpriseEvaluationCorpusConfigV1,
    cells: dict[str, AccessEvaluationCellTemplateV1],
) -> None:
    counts = Counter(item.cell_key for item in config.access_requests)
    if set(counts) != set(cells) or any(count != 1 for count in counts.values()):
        raise EnterpriseCompileError(
            "cell_access_request_cardinality",
            "each evaluation cell must resolve exactly one access request",
        )


def _validate_case_templates(
    config: EnterpriseEvaluationCorpusConfigV1,
    cells: dict[str, AccessEvaluationCellTemplateV1],
) -> None:
    activation_keys = {item.request_key for item in config.role_activation_requests}
    for case in config.evaluator_cases:
        targets = cells if case.target_kind.value == "access_cell" else activation_keys
        if case.target_key not in targets:
            raise EnterpriseCompileError(
                "unknown_evaluator_case_target",
                "evaluator case references an unknown target of its declared kind",
            )


def _check_corpus_budgets(config: EnterpriseEvaluationCorpusConfigV1) -> None:
    budget = config.compile_config.budget
    limits = (
        (
            "native_context_budget_exceeded",
            len(config.contexts),
            budget.max_native_contexts,
        ),
        (
            "session_state_slot_budget_exceeded",
            len(config.session_slots),
            budget.max_session_state_slots,
        ),
        (
            "role_activation_request_budget_exceeded",
            len(config.role_activation_requests),
            budget.max_role_activation_requests,
        ),
        (
            "evaluation_cell_budget_exceeded",
            len(config.evaluation_cells),
            budget.max_evaluation_cells,
        ),
        (
            "access_request_budget_exceeded",
            len(config.access_requests),
            budget.max_access_requests,
        ),
        (
            "evaluator_case_budget_exceeded",
            len(config.evaluator_cases),
            budget.max_evaluator_cases,
        ),
    )
    for code, measured, allowed in limits:
        if measured > allowed:
            raise EnterpriseCompileError(
                code,
                "native corpus exceeds its independent semantic budget",
                measured=measured,
                allowed=allowed,
            )


def _compile_cell(
    template: AccessEvaluationCellTemplateV1,
    *,
    config_digest: str,
    contexts_by_key: dict[str, EnterpriseContextV1],
    sessions_by_key: dict[str, AuthorizationSessionSlotV1],
) -> AccessEvaluationCellV1:
    session_state_id = (
        sessions_by_key[template.session_state_key].session_state_id
        if template.session_state_key is not None
        else None
    )
    return AccessEvaluationCellV1(
        cell_id=_stable_id(
            ENTERPRISE_EVALUATION_CELL_NAMESPACE_V1,
            config_digest,
            template.cell_key,
        ),
        access_atom_id=template.access_atom_id,
        context_id=contexts_by_key[template.context_key].context_id,
        session_state_id=session_state_id,
        tick=template.tick,
    )


def _stable_id(namespace: UUID, config_digest: str, logical_key: str) -> str:
    return str(
        uuid5(
            namespace,
            encode_parts(
                (ENTERPRISE_CORPUS_COMPILER_VERSION, config_digest, logical_key)
            ),
        )
    )


__all__ = [
    "compile_enterprise_evaluation_corpus",
]
