from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from synthworld.agentic import generate_asteria_agentic_v1
from synthworld.agentic.models import (
    ActionAttempted,
    AgenticBenchmark,
    AgenticEvaluatorBundle,
    AgenticPublicBundle,
    AgenticWorldSnapshot,
    Capability,
    Credential,
    Delegation,
    PublicScenario,
    Resource,
)


def test_value_models_normalize_members_and_reject_bad_validity() -> None:
    capability = Capability(
        resource_ids=(" resource-b ", "resource-a"),
        actions=("read",),
        scopes=("scope:b", "scope:a"),
        purpose=" procurement ",
    )
    assert capability.resource_ids == ("resource-a", "resource-b")
    assert capability.scopes == ("scope:a", "scope:b")
    assert capability.purpose == "procurement"
    with pytest.raises(ValidationError, match="nonblank"):
        capability.model_copy(update={"purpose": ""}).__class__(
            **{**capability.model_dump(), "purpose": " "}
        )
    with pytest.raises(ValidationError, match="unique"):
        Capability(
            resource_ids=("resource-a", "resource-a"),
            actions=("read",),
            scopes=("scope:a",),
            purpose="procurement",
        )

    benchmark = generate_asteria_agentic_v1()
    credential = next(
        event.payload.credential
        for event in benchmark.public.events
        if event.payload.event_type == "credential_issued"
    )
    delegation = next(
        event.payload.delegation
        for event in benchmark.public.events
        if event.payload.event_type == "delegation_granted"
    )
    with pytest.raises(ValidationError, match="credential expiry"):
        Credential.model_validate(
            {**credential.model_dump(), "expires_at": credential.valid_from}
        )
    with pytest.raises(ValidationError, match="delegation expiry"):
        Delegation.model_validate(
            {**delegation.model_dump(), "expires_at": delegation.valid_from}
        )


def test_agentic_timestamp_models_reject_nonzero_utc_offsets() -> None:
    benchmark = generate_asteria_agentic_v1()
    credential = next(
        event.payload.credential
        for event in benchmark.public.events
        if event.payload.event_type == "credential_issued"
    )
    with pytest.raises(ValidationError, match="must use UTC"):
        Credential.model_validate(
            {
                **credential.model_dump(),
                "valid_from": datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=1))),
            }
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (("duplicate", "organisations"), "organisations must be unique"),
        (("reference", "department_org"), "department references"),
        (
            ("reference", "principal_org"),
            "principal references an unknown organisation",
        ),
        (("reference", "principal_department"), "unknown department"),
        (("reference", "principal_owner"), "unknown owner"),
        (("reference", "agent_org"), "agent references an unknown organisation"),
        (("reference", "agent_owner"), "agent references an unknown owner"),
        (("reference", "agent_parent"), "agent references an unknown parent"),
        (("reference", "resource_org"), "resource references an unknown organisation"),
        (("reference", "resource_owner"), "resource references an unknown owner"),
        (("duplicate", "initial_evidence_refs"), "initial evidence must be unique"),
    ),
)
def test_snapshot_rejects_duplicate_and_broken_references(
    mutation: tuple[str, str], message: str
) -> None:
    data = deepcopy(generate_asteria_agentic_v1().public.snapshot.model_dump())
    _, target = mutation
    if target == "organisations":
        data[target][1]["id"] = data[target][0]["id"]
    elif target == "department_org":
        data["departments"][0]["organisation_id"] = "org-unknown"
    elif target == "principal_org":
        data["principals"][0]["organisation_id"] = "org-unknown"
    elif target == "principal_department":
        data["principals"][2]["department_id"] = "department-unknown"
    elif target == "principal_owner":
        data["principals"][2]["owner_principal_id"] = "principal-unknown"
    elif target == "agent_org":
        data["agents"][0]["organisation_id"] = "org-unknown"
    elif target == "agent_owner":
        data["agents"][0]["owner_principal_id"] = "principal-unknown"
    elif target == "agent_parent":
        data["agents"][1]["parent_agent_id"] = "agent-unknown"
    elif target == "resource_org":
        data["resources"][0]["organisation_id"] = "org-unknown"
    elif target == "resource_owner":
        data["resources"][0]["owner_principal_id"] = "principal-unknown"
    else:
        data[target] = (data[target][0], data[target][0])
    with pytest.raises(ValidationError, match=message):
        AgenticWorldSnapshot.model_validate(data)


def test_snapshot_allows_a_principal_without_optional_organisation() -> None:
    data = deepcopy(generate_asteria_agentic_v1().public.snapshot.model_dump())
    data["principals"][0]["organisation_id"] = None
    validated = AgenticWorldSnapshot.model_validate(data)
    assert validated.principals[0].organisation_id is None


@pytest.mark.parametrize(
    "owner_links",
    (
        ((2, 2),),
        ((2, 3), (3, 2)),
    ),
)
def test_snapshot_rejects_principal_ownership_cycles(
    owner_links: tuple[tuple[int, int], ...],
) -> None:
    data = deepcopy(generate_asteria_agentic_v1().public.snapshot.model_dump())
    for principal_index, owner_index in owner_links:
        data["principals"][principal_index]["owner_principal_id"] = data["principals"][
            owner_index
        ]["id"]

    with pytest.raises(ValidationError, match="principal ownership must be acyclic"):
        AgenticWorldSnapshot.model_validate(data)


def test_public_evaluator_and_join_models_reject_cross_file_drift() -> None:
    benchmark = generate_asteria_agentic_v1()
    public = benchmark.public
    evaluator = benchmark.evaluator
    with pytest.raises(ValidationError, match="exactly the public action"):
        AgenticPublicBundle(
            snapshot=public.snapshot,
            events=public.events,
            scenario=public.scenario.model_copy(update={"action_event_ids": ("bad",)}),
        )
    with pytest.raises(ValidationError, match="audit event is missing"):
        AgenticPublicBundle(
            snapshot=public.snapshot,
            events=public.events,
            scenario=public.scenario.model_copy(update={"audit_event_id": "bad"}),
        )
    with pytest.raises(ValidationError, match="scenario members must be unique"):
        PublicScenario.model_validate(
            {
                **public.scenario.model_dump(),
                "tool_schema_paths": ("tool.json", "tool.json"),
            }
        )

    with pytest.raises(ValidationError, match="canonical bindings must be unique"):
        AgenticEvaluatorBundle(
            **{
                **evaluator.model_dump(exclude={"bindings"}),
                "bindings": (evaluator.bindings[0],) * len(evaluator.bindings),
            }
        )
    with pytest.raises(ValidationError, match="action keys must match"):
        AgenticEvaluatorBundle(
            **{
                **evaluator.model_dump(exclude={"bindings"}),
                "bindings": evaluator.bindings[:-1],
            }
        )
    with pytest.raises(ValidationError, match="case kind must be nonblank"):
        evaluator.cases[0].__class__.model_validate(
            {**evaluator.cases[0].model_dump(), "kind": " "}
        )

    for update, message in (
        ({"world_id": "other"}, "metadata"),
        ({"audit_event_id": "other"}, "audit events"),
    ):
        with pytest.raises(ValidationError, match=message):
            AgenticBenchmark(
                public=public,
                evaluator=evaluator.model_copy(update=update),
            )
    renamed_bindings = tuple(
        item.model_copy(update={"action_event_id": f"other-{index}"})
        for index, item in enumerate(evaluator.bindings)
    )
    renamed_truth = tuple(
        item.model_copy(update={"action_event_id": f"other-{index}"})
        for index, item in enumerate(evaluator.authority_truth)
    )
    renamed_cases = tuple(
        item.model_copy(update={"action_event_id": f"other-{index}"})
        for index, item in enumerate(evaluator.cases)
    )
    renamed = evaluator.model_copy(
        update={
            "bindings": renamed_bindings,
            "authority_truth": renamed_truth,
            "cases": renamed_cases,
        }
    )
    with pytest.raises(ValidationError, match="action events"):
        AgenticBenchmark(public=public, evaluator=renamed)


def test_action_and_resource_members_reject_blanks() -> None:
    benchmark = generate_asteria_agentic_v1()
    action = next(
        event.payload.attempt
        for event in benchmark.public.events
        if isinstance(event.payload, ActionAttempted)
    )
    with pytest.raises(ValidationError, match="nonblank"):
        action.__class__.model_validate({**action.model_dump(), "action": " "})
    with pytest.raises(ValidationError, match="unique"):
        Resource(
            id="resource-test",
            display_name="Test",
            organisation_id="org-asteria",
            owner_principal_id="principal-asteria",
            actions=("read", "read"),
        )
