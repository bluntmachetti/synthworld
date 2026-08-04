"""Fixed native enterprise evaluation-corpus tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from synthworld.enterprise.canonical import (
    canonical_json_bytes,
    canonical_json_value_bytes,
    synthetic_digest,
)
from synthworld.enterprise.compiler import (
    EnterpriseCompileError,
    compile_enterprise_identity_access_universe,
)
from synthworld.enterprise.models import (
    EnterpriseIdentityAccessCompileBudgetV1,
    EnterpriseIdentityAccessUniverseV1,
)
from synthworld.enterprise.rbac.corpus import compile_enterprise_evaluation_corpus
from synthworld.enterprise.rbac.corpus_models import (
    AccessEvaluationCellTemplateV1,
    AuthorizationSessionSlotV1,
    EnterpriseAccessRequestTemplateV1,
    EnterpriseContextTemplateV1,
    EnterpriseEvaluationCorpusConfigV1,
    EnterpriseEvaluationCorpusV1,
    RoleActivationRequestTemplateV1,
)
from synthworld.enterprise.rbac.reference import (
    REFERENCE_ENTERPRISE_SEED,
    reference_enterprise_evaluation_corpus_config,
)
from synthworld.enterprise.reference import reference_enterprise_identity_access_import


@pytest.fixture
def universe() -> EnterpriseIdentityAccessUniverseV1:
    return compile_enterprise_identity_access_universe(
        import_model=reference_enterprise_identity_access_import(),
        seed=REFERENCE_ENTERPRISE_SEED,
    ).public_universe


def test_reference_corpus_is_fixed_deterministic_and_separates_case_labels(
    universe: EnterpriseIdentityAccessUniverseV1,
) -> None:
    config = reference_enterprise_evaluation_corpus_config()
    first = compile_enterprise_evaluation_corpus(
        universe=universe, corpus_config=config
    )
    second = compile_enterprise_evaluation_corpus(
        universe=universe, corpus_config=config
    )
    assert canonical_json_bytes(first.public_corpus) == canonical_json_bytes(
        second.public_corpus
    )
    assert first.public_corpus.identity_access_universe_digest == synthetic_digest(
        canonical_json_bytes(universe)
    )
    assert len(first.public_corpus.evaluation_cells) == len(universe.access_atoms) + 3
    assert len(first.public_corpus.access_requests) == len(
        first.public_corpus.evaluation_cells
    )
    public_bytes = canonical_json_bytes(first.public_corpus)
    assert b'"labels"' not in public_bytes
    assert b"activation" in canonical_json_bytes(first.evaluator_case_inventory)


def test_corpus_models_canonicalize_and_reject_duplicate_keys() -> None:
    config = reference_enterprise_evaluation_corpus_config()
    reversed_config = config.model_copy(
        update={"evaluation_cells": tuple(reversed(config.evaluation_cells))}
    )
    reparsed = EnterpriseEvaluationCorpusConfigV1.model_validate(
        reversed_config.model_dump()
    )
    assert tuple(item.cell_key for item in reparsed.evaluation_cells) == tuple(
        sorted(item.cell_key for item in config.evaluation_cells)
    )
    duplicate = config.model_dump(mode="json")
    duplicate["contexts"] *= 2
    with pytest.raises(ValidationError, match="duplicate_context_key"):
        EnterpriseEvaluationCorpusConfigV1.model_validate_json(
            canonical_json_value_bytes(duplicate)
        )


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("digest", "corpus_universe_digest_mismatch"),
        ("session_subject", "unknown_session_subject"),
        ("session_interval", "session_validity_interval_invalid"),
        ("missing_activation", "session_activation_request_cardinality"),
        ("unknown_activation_session", "unknown_activation_session"),
        ("unknown_role", "unknown_activation_role"),
        ("unknown_atom", "unknown_cell_access_atom"),
        ("unknown_context", "unknown_cell_context"),
        ("unknown_session", "unknown_cell_session"),
        ("cross_subject", "cross_subject_cell_session"),
        ("before_activation", "cell_before_session_activation"),
        ("at_expiry", "cell_at_or_after_session_expiry"),
        ("duplicate_tuple", "duplicate_evaluation_cell_tuple"),
        ("missing_access_request", "cell_access_request_cardinality"),
        ("unknown_case", "unknown_evaluator_case_target"),
    ],
)
def test_corpus_reference_and_cardinality_failures_are_atomic(
    universe: EnterpriseIdentityAccessUniverseV1, mutation: str, code: str
) -> None:
    config = reference_enterprise_evaluation_corpus_config()
    document = config.model_dump(mode="json")
    if mutation == "digest":
        document["identity_access_universe_digest"]["value"] = "0" * 64
    elif mutation == "session_subject":
        document["session_slots"][0]["subject_id"] = "unknown"
    elif mutation == "session_interval":
        document["session_slots"][0]["valid_until_tick"] = 5
    elif mutation == "missing_activation":
        document["role_activation_requests"] = document["role_activation_requests"][1:]
    elif mutation == "unknown_activation_session":
        document["role_activation_requests"][0]["session_state_key"] = "unknown"
    elif mutation == "unknown_role":
        document["role_activation_requests"][0]["requested_role_ids"] = ["unknown"]
    elif mutation == "unknown_atom":
        document["evaluation_cells"][0]["access_atom_id"] = "unknown"
    elif mutation == "unknown_context":
        document["evaluation_cells"][0]["context_key"] = "unknown"
    elif mutation == "unknown_session":
        document["evaluation_cells"][0]["session_state_key"] = "unknown"
    elif mutation == "cross_subject":
        cell = next(
            item
            for item in document["evaluation_cells"]
            if item["cell_key"] == "employee-session-cell"
        )
        cell["session_state_key"] = "agent-session-state"
    elif mutation == "before_activation":
        cell = next(
            item
            for item in document["evaluation_cells"]
            if item["cell_key"] == "employee-session-cell"
        )
        cell["tick"] = 4
    elif mutation == "at_expiry":
        cell = next(
            item
            for item in document["evaluation_cells"]
            if item["cell_key"] == "employee-session-cell"
        )
        cell["tick"] = 10
    elif mutation == "duplicate_tuple":
        document["evaluation_cells"][1].update(
            {
                key: document["evaluation_cells"][0][key]
                for key in (
                    "access_atom_id",
                    "context_key",
                    "session_state_key",
                    "tick",
                )
            }
        )
    elif mutation == "missing_access_request":
        document["access_requests"] = document["access_requests"][1:]
    else:
        document["evaluator_cases"][0]["target_key"] = "unknown"
    changed = EnterpriseEvaluationCorpusConfigV1.model_validate_json(
        canonical_json_value_bytes(document)
    )
    with pytest.raises(EnterpriseCompileError, match=code):
        compile_enterprise_evaluation_corpus(universe=universe, corpus_config=changed)


def test_corpus_rejects_cross_tenant_roles_and_duplicate_session_or_request_keys(
    universe: EnterpriseIdentityAccessUniverseV1,
) -> None:
    config = reference_enterprise_evaluation_corpus_config()
    slot = config.session_slots[0]
    duplicate_session = slot.model_copy(update={"session_state_key": "other-state"})
    with pytest.raises(ValidationError, match="duplicate_session_key"):
        EnterpriseEvaluationCorpusConfigV1.model_validate(
            config.model_copy(
                update={"session_slots": (slot, duplicate_session)}
            ).model_dump()
        )
    activation = config.role_activation_requests[0]
    with pytest.raises(ValidationError, match="duplicate_requested_role_id"):
        RoleActivationRequestTemplateV1.model_validate(
            activation.model_copy(
                update={"requested_role_ids": (activation.requested_role_ids[0],) * 2}
            ).model_dump()
        )

    requested_role_id = config.role_activation_requests[0].requested_role_ids[0]
    roles = tuple(
        item.model_copy(update={"tenant_id": "other-tenant"})
        if item.role_id == requested_role_id
        else item
        for item in universe.roles
    )
    cross_tenant_universe = universe.model_copy(update={"roles": roles})
    changed_config = config.model_copy(
        update={
            "identity_access_universe_digest": synthetic_digest(
                canonical_json_bytes(cross_tenant_universe)
            )
        }
    )
    with pytest.raises(EnterpriseCompileError, match="cross_tenant_activation_role"):
        compile_enterprise_evaluation_corpus(
            universe=cross_tenant_universe,
            corpus_config=changed_config,
        )


@pytest.mark.parametrize(
    ("field", "budget_field", "code"),
    [
        ("contexts", "max_native_contexts", "native_context_budget_exceeded"),
        (
            "session_slots",
            "max_session_state_slots",
            "session_state_slot_budget_exceeded",
        ),
        (
            "role_activation_requests",
            "max_role_activation_requests",
            "role_activation_request_budget_exceeded",
        ),
        ("evaluation_cells", "max_evaluation_cells", "evaluation_cell_budget_exceeded"),
        ("access_requests", "max_access_requests", "access_request_budget_exceeded"),
        ("evaluator_cases", "max_evaluator_cases", "evaluator_case_budget_exceeded"),
    ],
)
def test_each_native_corpus_budget_is_independent(
    universe: EnterpriseIdentityAccessUniverseV1,
    field: str,
    budget_field: str,
    code: str,
) -> None:
    config = reference_enterprise_evaluation_corpus_config()
    if field == "contexts":
        config = config.model_copy(
            update={
                "contexts": (
                    *config.contexts,
                    EnterpriseContextTemplateV1(context_key="unused-context"),
                )
            }
        )
    budget = EnterpriseIdentityAccessCompileBudgetV1(**{budget_field: 1})
    changed = config.model_copy(
        update={
            "compile_config": config.compile_config.model_copy(
                update={"budget": budget}
            )
        }
    )
    assert len(getattr(config, field)) > 1
    with pytest.raises(EnterpriseCompileError, match=code):
        compile_enterprise_evaluation_corpus(universe=universe, corpus_config=changed)


def test_corpus_template_helpers_reject_duplicate_semantics() -> None:
    config = reference_enterprise_evaluation_corpus_config()
    cell = config.evaluation_cells[0]
    extra_cell = AccessEvaluationCellTemplateV1(
        **(cell.model_dump() | {"cell_key": "different-cell-key"})
    )
    request = EnterpriseAccessRequestTemplateV1(
        request_key="different-request", cell_key="different-cell-key"
    )
    changed = config.model_copy(
        update={
            "evaluation_cells": (*config.evaluation_cells, extra_cell),
            "access_requests": (*config.access_requests, request),
        }
    )
    with pytest.raises(EnterpriseCompileError, match="duplicate_evaluation_cell_tuple"):
        compile_enterprise_evaluation_corpus(
            universe=universe_from_config(config), corpus_config=changed
        )


def universe_from_config(
    config: EnterpriseEvaluationCorpusConfigV1,
) -> EnterpriseIdentityAccessUniverseV1:
    del config
    return compile_enterprise_identity_access_universe(
        import_model=reference_enterprise_identity_access_import(),
        seed=REFERENCE_ENTERPRISE_SEED,
    ).public_universe


def test_generated_session_slot_rejects_an_empty_half_open_interval() -> None:
    with pytest.raises(ValidationError, match="generated_session_validity"):
        AuthorizationSessionSlotV1(
            session_state_id="state",
            session_id="session",
            subject_id="subject",
            activation_tick=5,
            valid_until_tick=5,
        )


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("duplicate_session", "duplicate_generated_session_id"),
        ("activation_cardinality", "generated_session_activation_cardinality"),
        ("activation_binding", "generated_activation_slot_binding_differs"),
        ("unknown_context", "unknown_generated_cell_context"),
        ("unknown_session", "unknown_generated_cell_session"),
        ("before_activation", "generated_cell_before_session_activation"),
        ("at_expiry", "generated_cell_at_or_after_session_expiry"),
        ("duplicate_cell", "duplicate_generated_evaluation_cell_tuple"),
        ("request_cardinality", "generated_cell_access_request_cardinality"),
        ("cell_digest", "generated_evaluation_cell_digest_mismatch"),
    ],
)
def test_generated_corpus_model_rejects_internal_corruption(
    universe: EnterpriseIdentityAccessUniverseV1,
    mutation: str,
    code: str,
) -> None:
    corpus = compile_enterprise_evaluation_corpus(
        universe=universe,
        corpus_config=reference_enterprise_evaluation_corpus_config(),
    ).public_corpus
    document = corpus.model_dump(mode="json")
    if mutation == "duplicate_session":
        document["session_slots"][1]["session_id"] = document["session_slots"][0][
            "session_id"
        ]
    elif mutation == "activation_cardinality":
        document["role_activation_requests"] = document["role_activation_requests"][1:]
    elif mutation == "activation_binding":
        document["role_activation_requests"][0]["session_id"] = "different"
    elif mutation in {
        "unknown_context",
        "unknown_session",
        "before_activation",
        "at_expiry",
    }:
        cell = next(
            item
            for item in document["evaluation_cells"]
            if item["session_state_id"] is not None
        )
        if mutation == "unknown_context":
            cell["context_id"] = "unknown"
        elif mutation == "unknown_session":
            cell["session_state_id"] = "unknown"
        elif mutation == "before_activation":
            cell["tick"] = 4
        else:
            cell["tick"] = 10
    elif mutation == "duplicate_cell":
        first = document["evaluation_cells"][0]
        document["evaluation_cells"][1].update(
            {
                field: first[field]
                for field in (
                    "access_atom_id",
                    "context_id",
                    "session_state_id",
                    "tick",
                )
            }
        )
    elif mutation == "request_cardinality":
        document["access_requests"] = document["access_requests"][1:]
    else:
        document["evaluation_cell_digest"]["value"] = "0" * 64
    with pytest.raises(ValidationError, match=code):
        EnterpriseEvaluationCorpusV1.model_validate(document)
