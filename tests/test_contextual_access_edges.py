"""Structural, replay, projection, and model edge cases for contextual access."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

import pytest
from pydantic import BaseModel, ValidationError

import synthworld.contextual_access.reference as reference_module
from synthworld.contextual_access.common import stable_contextual_fact_key
from synthworld.contextual_access.models import (
    BusinessJustificationContextV1,
    CaseAssignmentContextV1,
    CaseAssignmentState,
    ContextualAccessConfigV1,
    ContextualAccessEvaluatorV1,
    ContextualAccessEventV1,
    ContextualAccessPredictionV1,
    ContextualAccessPublicV1,
    ContextualAccessRequestV1,
    ContextualCaseKind,
    ContextualCheckpointV1,
    ContextualFactKind,
    ContextualFactMappingProfileV1,
    ContextualFactMappingV1,
    ContextualFactRemovedV1,
    ContextualFactUpsertedV1,
    ContextualFactV1,
    ContextualObjectKind,
    ContextualPredicateV1,
    ContextualReplayStateV1,
    DevicePostureContextV1,
    DevicePostureIsV1,
    OnCallContextV1,
    OnCallState,
    RiskAtMostV1,
    RiskSignalContextV1,
)
from synthworld.contextual_access.policy import _evaluate_predicate
from synthworld.contextual_access.projection import (
    ContextualAccessIntegrityError,
    _validate_delivery_attempts,
    _validate_facts,
    _validate_policies,
    _validate_registry,
    _validate_requests,
    compile_contextual_access_truth,
    project_contextual_access_public,
    validate_contextual_access_public,
)
from synthworld.contextual_access.reference import (
    ReferenceContextualAccessV1,
    reference_contextual_access,
)
from synthworld.contextual_access.replay import (
    ContextualReplayError,
    active_contextual_facts,
    materialize_contextual_state,
    presented_contextual_state,
)
from synthworld.contextual_access.shared_signals import (
    ContextualSharedSignalsEventV1,
    ContextualSharedSignalsMappingProfileV1,
    ContextualSharedSignalsProjectionV1,
    contextual_shared_signals_mapping_profile_v1,
    project_contextual_shared_signals,
)
from synthworld.models import SyntheticModel


def test_replay_prefixes_tombstones_expiry_and_same_tick_revision_order() -> None:
    reference = reference_contextual_access()
    for count, checkpoint in enumerate(reference.evaluator.truth.checkpoints):
        state = materialize_contextual_state(
            reference.public.initial_facts,
            reference.public.events,
            event_count=count,
        )
        assert checkpoint.event_count == count
        assert checkpoint.event_ids == state.processed_event_ids
        assert checkpoint.latest_facts == state.latest_facts
    assignment_event = next(
        item
        for item in reference.public.events
        if item.payload.fact.fact_type is ContextualFactKind.CASE_ASSIGNMENT
    )
    before = materialize_contextual_state(
        reference.public.initial_facts,
        reference.public.events,
        as_of_tick=assignment_event.effective_tick - 1,
    )
    after = materialize_contextual_state(
        reference.public.initial_facts,
        reference.public.events,
        as_of_tick=assignment_event.effective_tick,
    )
    assert any(
        item.fact_key == assignment_event.payload.fact.fact_key
        for item in active_contextual_facts(before, at_tick=4)
    )
    assert not any(
        item.fact_key == assignment_event.payload.fact.fact_key
        for item in active_contextual_facts(after, at_tick=5)
    )
    expiring = next(
        item
        for item in reference.public.initial_facts
        if isinstance(item, OnCallContextV1) and item.valid_until_tick is not None
    )
    initial = materialize_contextual_state(reference.public.initial_facts, ())
    assert expiring in active_contextual_facts(initial, at_tick=4)
    assert expiring not in active_contextual_facts(initial, at_tick=5)

    base = _assignment(revision=0, tick=0, state=CaseAssignmentState.ASSIGNED)
    unassigned = _assignment(revision=1, tick=5, state=CaseAssignmentState.UNASSIGNED)
    restored = _assignment(revision=2, tick=5, state=CaseAssignmentState.ASSIGNED)
    events = (
        _event("event-a", unassigned),
        _event("event-b", restored),
    )
    same_tick = materialize_contextual_state((base,), events)
    assert same_tick.latest_facts == (restored,)


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (
            lambda r: materialize_contextual_state(
                r.public.initial_facts,
                r.public.events,
                as_of_tick=1,
                event_count=1,
            ),
            "choose an as-of tick",
        ),
        (
            lambda r: materialize_contextual_state(
                r.public.initial_facts, r.public.events, as_of_tick=-1
            ),
            "cannot be negative",
        ),
        (
            lambda r: materialize_contextual_state(
                r.public.initial_facts, r.public.events, event_count=99
            ),
            "outside the schedule",
        ),
        (
            lambda r: active_contextual_facts(
                materialize_contextual_state(r.public.initial_facts, ()),
                at_tick=-1,
            ),
            "cannot be negative",
        ),
        (
            lambda r: presented_contextual_state(
                r.public.initial_facts,
                r.public.events,
                r.public.delivery_attempts,
                as_of_tick=-1,
            ),
            "cannot be negative",
        ),
    ],
)
def test_replay_rejects_invalid_prefix_coordinates(
    call: Callable[[ReferenceContextualAccessV1], object], message: str
) -> None:
    with pytest.raises(ContextualReplayError, match=message):
        call(reference_contextual_access())


def test_replay_rejects_event_revision_and_initial_state_corruption() -> None:
    reference = reference_contextual_access()
    event = reference.public.events[0]
    with pytest.raises(ContextualReplayError, match="unique and ordered"):
        materialize_contextual_state(
            reference.public.initial_facts,
            tuple(reversed(reference.public.events)),
        )
    with pytest.raises(ContextualReplayError, match="unique and ordered"):
        materialize_contextual_state(reference.public.initial_facts, (event, event))
    wrong_tick = event.model_copy(update={"effective_tick": event.effective_tick + 1})
    with pytest.raises(ContextualReplayError, match="effective tick differs"):
        materialize_contextual_state(reference.public.initial_facts, (wrong_tick,))
    wrong_revision = event.payload.fact.model_copy(update={"revision": 9})
    with pytest.raises(ContextualReplayError, match="contiguous from zero"):
        materialize_contextual_state(
            reference.public.initial_facts,
            (event.model_copy(update={"payload": _payload(wrong_revision)}),),
        )
    previous = next(
        item
        for item in reference.public.initial_facts
        if item.fact_key == event.payload.fact.fact_key
    )
    wrong_type = _on_call(revision=1, tick=event.effective_tick).model_copy(
        update={"fact_key": previous.fact_key}
    )
    wrong_type_event = event.model_copy(
        update={"id": "event-wrong-type", "payload": _payload(wrong_type)}
    )
    with pytest.raises(ContextualReplayError, match="changes type"):
        materialize_contextual_state(
            reference.public.initial_facts,
            (wrong_type_event,),
        )
    duplicate_id = event.payload.fact.model_copy(update={"fact_id": previous.fact_id})
    with pytest.raises(ContextualReplayError, match="fact ids must be unique"):
        materialize_contextual_state(
            reference.public.initial_facts,
            (event.model_copy(update={"payload": _payload(duplicate_id)}),),
        )

    invalid_initial = (
        previous.model_copy(update={"revision": 1}),
        previous.model_copy(update={"tombstone": True}),
        previous.model_copy(update={"observed_at_tick": 1}),
    )
    for fact in invalid_initial:
        with pytest.raises(ContextualReplayError, match="live revision zero"):
            materialize_contextual_state((fact,), ())
    with pytest.raises(ContextualReplayError, match="keys and ids must be unique"):
        materialize_contextual_state((previous, previous), ())


def test_delivery_inventory_rejects_unknown_order_duplicate_and_gap() -> None:
    reference = reference_contextual_access()
    events = reference.public.events
    attempts = reference.public.delivery_attempts
    unknown = attempts[0].model_copy(update={"event_id": "unknown-event"})
    with pytest.raises(ContextualReplayError, match="unknown event"):
        presented_contextual_state(
            reference.public.initial_facts,
            events,
            (unknown, *attempts[1:]),
            as_of_tick=10,
        )
    with pytest.raises(ContextualReplayError, match="presentation order"):
        presented_contextual_state(
            reference.public.initial_facts,
            events,
            tuple(reversed(attempts)),
            as_of_tick=10,
        )
    duplicate = attempts[1].model_copy(update={"attempt_id": attempts[0].attempt_id})
    corrupted = tuple(
        sorted(
            (attempts[0], duplicate, *attempts[2:]),
            key=lambda item: (
                item.delivery_tick,
                item.delivery_order,
                item.event_id,
                item.attempt_index,
            ),
        )
    )
    with pytest.raises(ContextualReplayError, match="attempt ids must be unique"):
        presented_contextual_state(
            reference.public.initial_facts,
            events,
            corrupted,
            as_of_tick=10,
        )
    duplicate_event_attempts = tuple(
        item for item in attempts if item.event_id == attempts[-1].event_id
    )
    gap = duplicate_event_attempts[0].model_copy(update={"attempt_index": 2})
    with pytest.raises(ContextualReplayError, match="indices must be contiguous"):
        presented_contextual_state(
            reference.public.initial_facts,
            events,
            (gap,),
            as_of_tick=10,
        )


def test_replay_rejects_an_unsupported_fact_runtime_type() -> None:
    class UnsupportedFact(SyntheticModel):
        fact_id: str
        fact_key: str
        revision: int
        tombstone: bool

    unsupported = cast(
        ContextualFactV1,
        UnsupportedFact(fact_id="x", fact_key="x", revision=0, tombstone=False),
    )
    with pytest.raises(ContextualReplayError, match="unsupported contextual fact type"):
        materialize_contextual_state((unsupported,), ())
    state = ContextualReplayStateV1.model_construct(
        processed_event_ids=(),
        latest_facts=(unsupported,),
        fact_history=(unsupported,),
    )
    with pytest.raises(ContextualReplayError, match="unsupported contextual fact type"):
        active_contextual_facts(state, at_tick=0)


@pytest.mark.parametrize(
    ("mutate", "validator", "message"),
    [
        (
            lambda p: p.model_copy(
                update={
                    "registry": p.registry.model_copy(
                        update={
                            "objects": (
                                p.registry.objects[0].model_copy(
                                    update={"tenant_id": "unknown-tenant"}
                                ),
                                *p.registry.objects[1:],
                            )
                        }
                    )
                }
            ),
            _validate_registry,
            "unknown tenant",
        ),
        (
            lambda p: p.model_copy(
                update={
                    "registry": p.registry.model_copy(
                        update={
                            "objects": (
                                p.registry.objects[0].model_copy(
                                    update={"organisation_id": "unknown-org"}
                                ),
                                *p.registry.objects[1:],
                            )
                        }
                    )
                }
            ),
            _validate_registry,
            "does not belong",
        ),
        (
            lambda p: _replace_initial(
                p,
                0,
                p.initial_facts[0].model_copy(update={"subject_id": "unknown"}),
            ),
            _validate_facts,
            "unknown principal",
        ),
        (
            lambda p: _mutate_assignment(p, work_item_id="unknown"),
            _validate_facts,
            "unknown registry object",
        ),
        (
            lambda p: _mutate_assignment(
                p, work_item_id=_registry_id(p, ContextualObjectKind.DEVICE)
            ),
            _validate_facts,
            "wrong registry object kind",
        ),
        (
            lambda p: _mutate_assignment(p, asset_id="unknown"),
            _validate_facts,
            "unknown authorization target",
        ),
        (
            lambda p: _mutate_justification_action(p),
            _validate_facts,
            "action is undeclared",
        ),
        (
            lambda p: p.model_copy(
                update={
                    "policies": (
                        p.policies[0].model_copy(
                            update={"target_handles": ("unknown",)}
                        ),
                        *p.policies[1:],
                    )
                }
            ),
            _validate_policies,
            "unknown target",
        ),
        (
            lambda p: p.model_copy(
                update={
                    "policies": (
                        p.policies[0].model_copy(update={"actions": ("undeclared",)}),
                        *p.policies[1:],
                    )
                }
            ),
            _validate_policies,
            "undeclared by a target",
        ),
        (
            lambda p: _mutate_policy_reference(p),
            _validate_policies,
            "unknown or wrong-kind",
        ),
        (
            lambda p: _replace_request(
                p,
                0,
                p.requests[0].model_copy(update={"subject_id": "unknown"}),
            ),
            _validate_requests,
            "unknown universe object",
        ),
        (
            lambda p: _replace_request(
                p,
                0,
                p.requests[0].model_copy(
                    update={"access_atom_id": p.requests[1].access_atom_id}
                ),
            ),
            _validate_requests,
            "does not bind",
        ),
        (
            lambda p: _replace_request(
                p,
                0,
                p.requests[0].model_copy(update={"device_id": None}),
            ),
            _validate_requests,
            "requires a device",
        ),
        (
            lambda p: _replace_request(
                p,
                0,
                p.requests[0].model_copy(update={"device_id": "unknown"}),
            ),
            _validate_requests,
            "device is unknown",
        ),
        (
            lambda p: p.model_copy(update={"delivery_attempts": ()}),
            _validate_delivery_attempts,
            "cover every event",
        ),
    ],
)
def test_public_reference_validators_reject_each_failure_class(
    mutate: Callable[[ContextualAccessPublicV1], ContextualAccessPublicV1],
    validator: Callable[[ContextualAccessPublicV1], None],
    message: str,
) -> None:
    public = mutate(reference_contextual_access().public)
    with pytest.raises(ContextualAccessIntegrityError, match=message):
        validator(public)


def test_scope_validation_for_facts_registry_devices_and_requests() -> None:
    public = reference_contextual_access().public
    assignment = next(
        item
        for item in public.initial_facts
        if isinstance(item, CaseAssignmentContextV1)
    )
    principal_index = next(
        index
        for index, item in enumerate(public.universe.principals)
        if item.principal_id == assignment.subject_id
    )
    principals = list(public.universe.principals)
    principals[principal_index] = principals[principal_index].model_copy(
        update={"organisation_id": "other-org"}
    )
    scoped_public = public.model_copy(
        update={
            "universe": public.universe.model_copy(
                update={"principals": tuple(principals)}
            )
        }
    )
    with pytest.raises(ContextualAccessIntegrityError, match="crosses tenant"):
        _validate_facts(scoped_public)

    request = public.requests[0]
    device_index = next(
        index
        for index, item in enumerate(public.registry.objects)
        if item.id == request.device_id
    )
    scoped_device = public.registry.objects[device_index].model_copy(
        update={"organisation_id": "other-org"}
    )
    objects = list(public.registry.objects)
    objects[device_index] = scoped_device
    device_public = public.model_copy(
        update={
            "registry": public.registry.model_copy(update={"objects": tuple(objects)})
        }
    )
    with pytest.raises(ContextualAccessIntegrityError, match="device crosses scope"):
        _validate_requests(device_public)

    principal_id = request.subject_id
    request_principals = tuple(
        item.model_copy(update={"organisation_id": "other-org"})
        if item.principal_id == principal_id
        else item
        for item in public.universe.principals
    )
    universe = public.universe.model_copy(update={"principals": request_principals})
    cross_request = public.model_copy(update={"universe": universe})
    with pytest.raises(ContextualAccessIntegrityError, match="request crosses"):
        _validate_requests(cross_request)


def test_optional_device_is_allowed_when_no_applicable_device_predicate() -> None:
    public = reference_contextual_access().public
    request = public.requests[0].model_copy(update={"device_id": None})
    policies = tuple(
        policy.model_copy(
            update={
                "rules": tuple(
                    rule.model_copy(
                        update={
                            "predicates": tuple(
                                predicate
                                for predicate in rule.predicates
                                if not isinstance(predicate, DevicePostureIsV1)
                            )
                            or rule.predicates
                        }
                    )
                    for rule in policy.rules
                    if not any(
                        isinstance(predicate, DevicePostureIsV1)
                        for predicate in rule.predicates
                    )
                )
                or (policy.rules[0],)
            }
        )
        for policy in public.policies
    )
    no_device = public.model_copy(
        update={"policies": policies, "requests": (request, *public.requests[1:])}
    )
    _validate_requests(no_device)


def test_projection_truth_compiler_rejects_limits_labels_and_schedule() -> None:
    reference = reference_contextual_access()
    public = reference.public
    with pytest.raises(ContextualAccessIntegrityError, match="disabled"):
        _reproject(
            public,
            reference.config.model_copy(
                update={"enabled_fact_kinds": (ContextualFactKind.CASE_ASSIGNMENT,)}
            ),
        )
    limit_fields = (
        "max_registry_objects",
        "max_initial_facts",
        "max_events",
        "max_delivery_attempts",
        "max_requests",
        "max_policies",
    )
    for field in limit_fields:
        limits = reference.config.limits.model_copy(update={field: 1})
        with pytest.raises(ContextualAccessIntegrityError, match="exceeds"):
            _reproject(public, reference.config.model_copy(update={"limits": limits}))
    many_rules = public.policies[1].model_copy(
        update={"rules": public.policies[1].rules[:2]}
    )
    limits = reference.config.limits.model_copy(update={"max_rules_per_policy": 1})
    with pytest.raises(ContextualAccessIntegrityError, match="rule count"):
        _reproject(
            public.model_copy(update={"policies": (public.policies[0], many_rules)}),
            reference.config.model_copy(update={"limits": limits}),
        )
    limits = reference.config.limits.model_copy(update={"max_predicates_per_rule": 1})
    multi_predicate = next(
        rule for rule in public.policies[1].rules if len(rule.predicates) > 1
    )
    with pytest.raises(ContextualAccessIntegrityError, match="predicate count"):
        _reproject(
            public.model_copy(
                update={
                    "policies": (
                        public.policies[0],
                        public.policies[1].model_copy(
                            update={"rules": (multi_predicate,)}
                        ),
                    )
                }
            ),
            reference.config.model_copy(update={"limits": limits}),
        )

    with pytest.raises(ContextualAccessIntegrityError, match="cover every public"):
        compile_contextual_access_truth(
            public=public,
            case_labels=reference.evaluator.truth.case_labels[:-1],
        )
    bad_label = reference.evaluator.truth.case_labels[0].model_copy(
        update={"transition_event_ids": ("unknown",)}
    )
    with pytest.raises(ContextualAccessIntegrityError, match="unknown transition"):
        compile_contextual_access_truth(
            public=public,
            case_labels=(bad_label, *reference.evaluator.truth.case_labels[1:]),
        )
    with pytest.raises(
        ContextualAccessIntegrityError, match="schedule or fact history"
    ):
        validate_contextual_access_public(public.model_copy(update={"schedule": ()}))


@pytest.mark.parametrize(
    ("model", "mutation", "message"),
    [
        (ContextualAccessConfigV1, {"enabled_fact_kinds": ()}, "unique_nonempty"),
        (
            ContextualAccessConfigV1,
            {
                "enabled_case_kinds": (
                    ContextualCaseKind.STATIC_ALLOW,
                    ContextualCaseKind.STATIC_ALLOW,
                )
            },
            "unique_nonempty",
        ),
        (CaseAssignmentContextV1, {"valid_until_tick": 0}, "interval_invalid"),
        (CaseAssignmentContextV1, {"fact_key": "wrong"}, "fact_key_mismatch"),
        (ContextualFactUpsertedV1, {"fact": "tombstone"}, "cannot_carry_tombstone"),
        (ContextualFactRemovedV1, {"fact": "live"}, "must_carry_tombstone"),
        (
            ContextualFactMappingV1,
            {"mapping_kind": "relationship_predicate", "nist_category": "subject"},
            "relationship_mapping_fields_invalid",
        ),
        (
            ContextualFactMappingV1,
            {"mapping_kind": "subject_attribute", "nist_category": None},
            "attribute_mapping_fields_invalid",
        ),
        (ContextualFactMappingProfileV1, {"mappings": ()}, "profile_incomplete"),
        (ContextualReplayStateV1, {"latest_facts": "duplicate"}, "key_duplicate"),
        (ContextualAccessPublicV1, {"events": "duplicate"}, "event_id_duplicate"),
        (
            ContextualAccessPublicV1,
            {"delivery_attempts": "duplicate"},
            "attempt_id_duplicate",
        ),
        (
            ContextualAccessPublicV1,
            {"delivery_attempts": "gap"},
            "attempt_index_gap",
        ),
        (ContextualAccessPublicV1, {"requests": "duplicate"}, "request_id_duplicate"),
        (ContextualAccessPublicV1, {"requests": "gap"}, "request_index_gap"),
        (ContextualAccessPublicV1, {"benchmark": "digest"}, "digest_mismatch"),
        (ContextualCheckpointV1, {"latest_facts": "duplicate"}, "key_duplicate"),
        (
            ContextualCheckpointV1,
            {"state_digest": "bad_digest"},
            "digest_mismatch",
        ),
        (
            ContextualAccessEvaluatorV1,
            {"public_digest": "bad_digest"},
            "public_digest_mismatch",
        ),
        (
            ContextualAccessPredictionV1,
            {"benchmark_digest": "bad_digest"},
            "row_digest_mismatch",
        ),
    ],
)
def test_model_validators_reject_corrupt_shapes(
    model: type[BaseModel], mutation: dict[str, object], message: str
) -> None:
    reference = reference_contextual_access()
    value = _base_model_value(model, reference)
    _apply_model_mutation(value, mutation)
    with pytest.raises(ValidationError, match=message):
        model.model_validate(value)


def test_truth_models_reject_stale_checkpoint_and_case_label_mismatches() -> None:
    reference = reference_contextual_access()
    truth = reference.evaluator.truth
    checkpoints = list(truth.model_dump(mode="json")["checkpoints"])
    checkpoints[1]["event_count"] = 9
    value = truth.model_dump(mode="json")
    value["checkpoints"] = checkpoints
    with pytest.raises(ValidationError, match="checkpoint_count_gap"):
        type(truth).model_validate(value)
    case = truth.cases[0]
    invalid_case = case.model_dump(mode="json") | {
        "stale_context": not case.stale_context
    }
    with pytest.raises(ValidationError, match="stale_context_label_mismatch"):
        type(case).model_validate(invalid_case)


def test_projection_rejects_an_asset_that_crosses_subject_scope() -> None:
    public = reference_contextual_access().public
    assignment = next(
        item
        for item in public.initial_facts
        if isinstance(item, CaseAssignmentContextV1)
    )
    targets = tuple(
        item.model_copy(update={"organisation_id": "other-org"})
        if item.authorization_target_id == assignment.asset_id
        else item
        for item in public.universe.authorization_targets
    )
    changed = public.model_copy(
        update={
            "universe": public.universe.model_copy(
                update={"authorization_targets": targets}
            )
        }
    )
    with pytest.raises(ContextualAccessIntegrityError, match="asset crosses"):
        _validate_facts(changed)


def test_policy_rejects_an_unsupported_runtime_predicate_type() -> None:
    class UnsupportedPredicate(SyntheticModel):
        predicate_id: str

    request = reference_contextual_access().public.requests[0]
    with pytest.raises(TypeError, match="unsupported contextual predicate"):
        _evaluate_predicate(
            predicate=cast(
                ContextualPredicateV1,
                UnsupportedPredicate(predicate_id="unsupported"),
            ),
            facts=(),
            request=request,
        )


def test_shared_signals_models_reject_incomplete_or_impure_projections() -> None:
    reference = reference_contextual_access()
    profile = contextual_shared_signals_mapping_profile_v1()
    with pytest.raises(ValidationError, match="profile is incomplete"):
        ContextualSharedSignalsMappingProfileV1(mappings=profile.mappings[:-1])
    changed_mapping = profile.mappings[0].model_copy(
        update={"custom_event_type": "urn:synthworld:event:wrong:1.0"}
    )
    with pytest.raises(ValidationError, match="custom event type differs"):
        ContextualSharedSignalsMappingProfileV1(
            mappings=(changed_mapping, *profile.mappings[1:])
        )

    projection = project_contextual_shared_signals(reference.public)
    event = projection.events[0]
    with pytest.raises(ValidationError, match="cannot change effective tick"):
        _revalidate_model(
            ContextualSharedSignalsEventV1,
            event,
            projected_event_tick=event.effective_tick + 1,
        )
    with pytest.raises(ValidationError, match="custom event type differs"):
        _revalidate_model(
            ContextualSharedSignalsEventV1,
            event,
            custom_event_type="urn:synthworld:event:wrong:1.0",
        )
    gap = projection.events[0].model_copy(update={"event_index": 9})
    with pytest.raises(ValidationError, match="event index differs"):
        _revalidate_model(
            ContextualSharedSignalsProjectionV1,
            projection,
            events=(gap, *projection.events[1:]),
        )
    duplicate = projection.events[1].model_copy(
        update={"event_id": projection.events[0].event_id}
    )
    with pytest.raises(ValidationError, match="event id is duplicated"):
        _revalidate_model(
            ContextualSharedSignalsProjectionV1,
            projection,
            events=(projection.events[0], duplicate, *projection.events[2:]),
        )


def test_reference_tripwires_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    with monkeypatch.context() as scoped:
        scoped.setattr(
            reference_module,
            "REFERENCE_CONTEXTUAL_UNIVERSE_SHA256",
            "0" * 64,
        )
        with pytest.raises(RuntimeError, match="enterprise universe changed"):
            reference_module.reference_contextual_access()

    reference = reference_contextual_access()
    with monkeypatch.context() as scoped:
        scoped.setattr(reference_module, "_principal_atoms", lambda _: ())
        with pytest.raises(RuntimeError, match="too few principal access atoms"):
            reference_module.generate_contextual_access_smoke(
                universe=reference.public.universe,
                config=reference.config,
            )
    with pytest.raises(RuntimeError, match="atom pairing changed"):
        reference_module._principal_atoms(
            reference.public.universe.model_copy(update={"access_atoms": ()})
        )

    incomplete_truth = reference.evaluator.truth.model_copy(
        update={"case_labels": reference.evaluator.truth.case_labels[:-1]}
    )
    with pytest.raises(RuntimeError, match="case inventory is incomplete"):
        reference_module._require_case_inventory(
            reference.evaluator.model_copy(update={"truth": incomplete_truth})
        )
    first_case = reference.evaluator.truth.cases[0]
    changed_cases = (
        first_case.model_copy(update={"stale_context": not first_case.stale_context}),
        *reference.evaluator.truth.cases[1:],
    )
    changed_truth = reference.evaluator.truth.model_copy(
        update={"cases": changed_cases}
    )
    with pytest.raises(RuntimeError, match="not discriminating"):
        reference_module._require_case_inventory(
            reference.evaluator.model_copy(update={"truth": changed_truth})
        )


def _assignment(
    *, revision: int, tick: int, state: CaseAssignmentState
) -> CaseAssignmentContextV1:
    key = stable_contextual_fact_key("case_assignment", "subject", "work", "asset")
    return CaseAssignmentContextV1(
        fact_id=f"fact-{revision}",
        fact_key=key,
        revision=revision,
        subject_id="subject",
        work_item_id="work",
        asset_id="asset",
        assignment_state=state,
        valid_from_tick=tick,
    )


def _on_call(*, revision: int, tick: int) -> OnCallContextV1:
    return OnCallContextV1(
        fact_id=f"on-call-{revision}",
        fact_key=stable_contextual_fact_key("on_call", "subject", "duty"),
        revision=revision,
        subject_id="subject",
        duty_scope_id="duty",
        duty_state=OnCallState.ON_CALL,
        valid_from_tick=tick,
    )


def _payload(fact: ContextualFactV1) -> ContextualFactUpsertedV1:
    return ContextualFactUpsertedV1.model_construct(fact=fact)


def _event(event_id: str, fact: ContextualFactV1) -> ContextualAccessEventV1:
    start = (
        fact.observed_at_tick
        if isinstance(fact, DevicePostureContextV1)
        else fact.effective_from_tick
        if isinstance(fact, RiskSignalContextV1)
        else fact.valid_from_tick
    )
    return ContextualAccessEventV1(
        id=event_id,
        effective_tick=start,
        payload=ContextualFactUpsertedV1(fact=fact),
    )


def _registry_id(public: ContextualAccessPublicV1, kind: ContextualObjectKind) -> str:
    return next(item.id for item in public.registry.objects if item.kind is kind)


def _replace_initial(
    public: ContextualAccessPublicV1,
    index: int,
    fact: ContextualFactV1,
) -> ContextualAccessPublicV1:
    values = list(public.initial_facts)
    values[index] = fact
    return public.model_copy(update={"initial_facts": tuple(values)})


def _replace_request(
    public: ContextualAccessPublicV1,
    index: int,
    request: ContextualAccessRequestV1,
) -> ContextualAccessPublicV1:
    values = list(public.requests)
    values[index] = request
    return public.model_copy(update={"requests": tuple(values)})


def _mutate_assignment(
    public: ContextualAccessPublicV1,
    **updates: object,
) -> ContextualAccessPublicV1:
    index = next(
        index
        for index, item in enumerate(public.initial_facts)
        if isinstance(item, CaseAssignmentContextV1)
    )
    fact = public.initial_facts[index].model_copy(update=updates)
    return _replace_initial(public, index, fact)


def _mutate_justification_action(
    public: ContextualAccessPublicV1,
) -> ContextualAccessPublicV1:
    index = next(
        index
        for index, item in enumerate(public.initial_facts)
        if isinstance(item, BusinessJustificationContextV1)
    )
    fact = public.initial_facts[index].model_copy(update={"action": "undeclared"})
    return _replace_initial(public, index, fact)


def _mutate_policy_reference(
    public: ContextualAccessPublicV1,
) -> ContextualAccessPublicV1:
    policy_index, rule_index = next(
        (policy_index, rule_index)
        for policy_index, policy in enumerate(public.policies)
        for rule_index, rule in enumerate(policy.rules)
        if any(isinstance(item, RiskAtMostV1) for item in rule.predicates)
    )
    policy = public.policies[policy_index]
    rule = policy.rules[rule_index]
    predicate = next(item for item in rule.predicates if isinstance(item, RiskAtMostV1))
    changed = predicate.model_copy(update={"signal_source_id": "unknown"})
    changed_rule = rule.model_copy(update={"predicates": (changed,)})
    rules = list(policy.rules)
    rules[rule_index] = changed_rule
    changed_policy = policy.model_copy(update={"rules": tuple(rules)})
    policies = list(public.policies)
    policies[policy_index] = changed_policy
    return public.model_copy(update={"policies": tuple(policies)})


def _reproject(
    public: ContextualAccessPublicV1,
    config: ContextualAccessConfigV1,
) -> ContextualAccessPublicV1:
    return project_contextual_access_public(
        config=config,
        universe=public.universe,
        registry=public.registry,
        mapping_profile=public.mapping_profile,
        policies=public.policies,
        initial_facts=public.initial_facts,
        events=public.events,
        delivery_attempts=public.delivery_attempts,
        requests=public.requests,
    )


def _base_model_value(
    model: type[BaseModel], reference: ReferenceContextualAccessV1
) -> dict[str, object]:
    if model is ContextualAccessConfigV1:
        return reference.config.model_dump(mode="python")
    elif model is CaseAssignmentContextV1:
        return next(
            fact
            for fact in reference.public.initial_facts
            if isinstance(fact, CaseAssignmentContextV1)
        ).model_dump(mode="python")
    elif model is ContextualFactUpsertedV1:
        return next(
            event.payload
            for event in reference.public.events
            if isinstance(event.payload, ContextualFactUpsertedV1)
        ).model_dump(mode="python")
    elif model is ContextualFactRemovedV1:
        return next(
            event.payload
            for event in reference.public.events
            if isinstance(event.payload, ContextualFactRemovedV1)
        ).model_dump(mode="python")
    elif model is ContextualFactMappingV1:
        return reference.public.mapping_profile.mappings[0].model_dump(mode="python")
    elif model is ContextualFactMappingProfileV1:
        return reference.public.mapping_profile.model_dump(mode="python")
    elif model is ContextualReplayStateV1:
        return materialize_contextual_state(
            reference.public.initial_facts, ()
        ).model_dump(mode="python")
    elif model is ContextualAccessPublicV1:
        return reference.public.model_dump(mode="python")
    elif model is ContextualCheckpointV1:
        return reference.evaluator.truth.checkpoints[0].model_dump(mode="python")
    elif model is ContextualAccessEvaluatorV1:
        return reference.evaluator.model_dump(mode="python")
    from synthworld.contextual_access.metrics import (
        perfect_contextual_access_prediction,
    )

    return perfect_contextual_access_prediction(
        public=reference.public, evaluator=reference.evaluator
    ).model_dump(mode="python")


def _apply_model_mutation(
    value: dict[str, object],
    mutation: dict[str, object],
) -> None:
    for key, replacement in mutation.items():
        if key == "fact" and replacement in {"tombstone", "live"}:
            fact = cast(dict[str, object], value["fact"])
            fact["tombstone"] = replacement == "tombstone"
        elif replacement == "duplicate":
            rows = cast(tuple[dict[str, object], ...], value[key])
            value[key] = (*rows, rows[0].copy())
        elif replacement == "gap":
            gap_rows = list(cast(tuple[dict[str, object], ...], value[key]))
            if key == "delivery_attempts":
                gap_rows[0]["attempt_index"] = 9
            else:
                gap_rows[0]["request_index"] = 9
            value[key] = tuple(gap_rows)
        elif key == "benchmark" and replacement == "digest":
            benchmark = cast(dict[str, object], value["benchmark"])
            digest = cast(dict[str, object], benchmark["request_digest"])
            digest["value"] = "0" * 64
        elif replacement == "bad_digest":
            value[key] = {"algorithm": "sha256", "value": "0" * 64}
        else:
            value[key] = replacement


def _revalidate_model[ModelT: BaseModel](
    model: type[ModelT], value: BaseModel, **updates: object
) -> ModelT:
    document = value.model_dump(mode="python")
    document.update(updates)
    return model.model_validate(document)
