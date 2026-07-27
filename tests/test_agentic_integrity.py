from __future__ import annotations

import pytest

from synthworld.agentic import generate_asteria_agentic_v1
from synthworld.agentic.errors import AgenticBenchmarkIntegrityError
from synthworld.agentic.integrity import validate_canonical_binding
from synthworld.agentic.models import (
    ActionAttempted,
    AgenticBenchmark,
    AgenticCase,
    AuditPerformed,
    AuthorityFailureReason,
    CanonicalBinding,
)
from synthworld.agentic.projection import build_agentic_benchmark
from synthworld.agentic.replay import AgenticReplayError, materialize_agentic_world


def _build_with_bindings(
    bindings: tuple[CanonicalBinding, ...],
    *,
    cases: tuple[AgenticCase, ...] | None = None,
) -> AgenticBenchmark:
    benchmark = generate_asteria_agentic_v1()
    return build_agentic_benchmark(
        benchmark.public.snapshot,
        benchmark.public.events,
        benchmark.public.scenario,
        bindings,
        cases or benchmark.evaluator.cases,
    )


@pytest.mark.parametrize(
    ("update", "message"),
    (
        (
            {"originating_principal_id": "principal-unknown"},
            "unknown originating principal",
        ),
        ({"logical_agent_id": "agent-unknown"}, "unknown logical agent"),
        ({"runtime_id": "runtime-unknown"}, "runtime unavailable"),
        ({"runtime_id": "runtime-quotation-001"}, "different logical agent"),
        (
            {"originating_principal_id": "principal-orion"},
            "crosses the logical agent tenant",
        ),
        (
            {"runtime_principal_id": "principal-runtime-quotation-001"},
            "differs from the runtime record",
        ),
        (
            {"credential_subject_id": "principal-runtime-quotation-001"},
            "differs from the presented credential",
        ),
        ({"attributed_actor_id": "principal-unknown"}, "unknown attributed actor"),
        (
            {"attributed_actor_id": "principal-payroll-owner"},
            "unrelated to runtime and credential",
        ),
    ),
)
def test_builder_rejects_inconsistent_binding_relationships(
    update: dict[str, str], message: str
) -> None:
    benchmark = generate_asteria_agentic_v1()
    first = benchmark.evaluator.bindings[0].model_copy(update=update)
    with pytest.raises(AgenticBenchmarkIntegrityError, match=message):
        _build_with_bindings((first, *benchmark.evaluator.bindings[1:]))


@pytest.mark.parametrize(
    "owner_chain",
    (
        ("principal-unknown",),
        ("principal-asteria", "principal-procurement-manager"),
        ("principal-procurement-manager",),
        (
            "principal-procurement-manager",
            "principal-payroll-owner",
            "principal-asteria",
        ),
        (
            "principal-procurement-manager",
            "principal-asteria",
            "principal-payroll-owner",
        ),
    ),
)
def test_builder_rejects_unknown_reordered_truncated_or_fabricated_owner_chain(
    owner_chain: tuple[str, ...],
) -> None:
    benchmark = generate_asteria_agentic_v1()
    first = benchmark.evaluator.bindings[0].model_copy(
        update={"accountable_owner_chain": owner_chain}
    )
    with pytest.raises(AgenticBenchmarkIntegrityError, match="ownership graph"):
        _build_with_bindings((first, *benchmark.evaluator.bindings[1:]))


def test_false_cross_tenant_join_is_rejected_but_truthful_attempt_scores() -> None:
    benchmark = generate_asteria_agentic_v1()
    cross_tenant_index = benchmark.public.scenario.action_event_ids.index(
        "evt-018-cross-tenant"
    )
    cross_tenant_truth = benchmark.evaluator.authority_truth[cross_tenant_index]
    assert cross_tenant_truth.decision_at_action.value == "deny"
    assert AuthorityFailureReason.TENANT_MISMATCH in (
        cross_tenant_truth.failure_reasons_at_action
    )

    binding = benchmark.evaluator.bindings[cross_tenant_index].model_copy(
        update={"logical_agent_id": "agent-quotation"}
    )
    bindings = list(benchmark.evaluator.bindings)
    bindings[cross_tenant_index] = binding
    with pytest.raises(AgenticBenchmarkIntegrityError, match="different logical agent"):
        _build_with_bindings(tuple(bindings))


def test_frozen_unauthorised_identity_cases_remain_valid_benchmark_cases() -> None:
    benchmark = generate_asteria_agentic_v1()
    truth = {item.action_event_id: item for item in benchmark.evaluator.authority_truth}
    assert AuthorityFailureReason.WRONG_RUNTIME in (
        truth["evt-013-wrong-runtime"].failure_reasons_at_action
    )
    assert truth["evt-014-shared-credential"].decision_at_action.value == "deny"
    assert truth["evt-016-incorrect-attribution"].decision_at_action.value == "allow"
    assert AuthorityFailureReason.TENANT_MISMATCH in (
        truth["evt-018-cross-tenant"].failure_reasons_at_action
    )


@pytest.mark.parametrize("kind", ("missing", "unknown", "duplicate"))
@pytest.mark.parametrize("target", ("bindings", "cases"))
def test_builder_rejects_invalid_action_key_coverage(kind: str, target: str) -> None:
    benchmark = generate_asteria_agentic_v1()
    values = list(
        benchmark.evaluator.bindings
        if target == "bindings"
        else benchmark.evaluator.cases
    )
    if kind == "missing":
        values.pop()
    elif kind == "unknown":
        values[-1] = values[-1].model_copy(update={"action_event_id": "evt-unknown"})
    else:
        values[-1] = values[0]

    kwargs: dict[str, object] = {
        "snapshot": benchmark.public.snapshot,
        "events": benchmark.public.events,
        "scenario": benchmark.public.scenario,
        "bindings": benchmark.evaluator.bindings,
        "cases": benchmark.evaluator.cases,
    }
    kwargs[target] = tuple(values)
    with pytest.raises(AgenticBenchmarkIntegrityError, match=target):
        build_agentic_benchmark(**kwargs)  # type: ignore[arg-type]


def test_builder_requires_one_scenario_audit_event() -> None:
    benchmark = generate_asteria_agentic_v1()
    events = list(benchmark.public.events)
    events[22] = events[22].model_copy(
        update={"payload": AuditPerformed(audit_id="audit-extra")}
    )
    with pytest.raises(AgenticReplayError, match="only audit event"):
        build_agentic_benchmark(
            benchmark.public.snapshot,
            tuple(events),
            benchmark.public.scenario,
            benchmark.evaluator.bindings,
            benchmark.evaluator.cases,
        )


def test_direct_validator_rejects_wrong_event_and_unavailable_credential() -> None:
    benchmark = generate_asteria_agentic_v1()
    action = benchmark.public.events[9]
    assert isinstance(action.payload, ActionAttempted)
    state = materialize_agentic_world(
        benchmark.public.snapshot,
        benchmark.public.events,
        at_event_index=action.event_index - 1,
    )
    binding = benchmark.evaluator.bindings[0]
    with pytest.raises(AgenticBenchmarkIntegrityError, match="does not match"):
        validate_canonical_binding(
            state,
            action,
            binding.model_copy(update={"action_event_id": "evt-other"}),
        )
    with pytest.raises(AgenticBenchmarkIntegrityError, match="must refer to an action"):
        validate_canonical_binding(state, benchmark.public.events[0], binding)
    with pytest.raises(AgenticBenchmarkIntegrityError, match="credential unavailable"):
        validate_canonical_binding(
            state.model_copy(update={"credentials": ()}), action, binding
        )

    principals = tuple(
        principal.model_copy(update={"organisation_id": "org-orion"})
        if principal.id == "principal-asteria"
        else principal
        for principal in state.snapshot.principals
    )
    broken_snapshot = state.snapshot.model_copy(update={"principals": principals})
    with pytest.raises(AgenticBenchmarkIntegrityError, match="crosses organisation"):
        validate_canonical_binding(
            state.model_copy(update={"snapshot": broken_snapshot}), action, binding
        )
