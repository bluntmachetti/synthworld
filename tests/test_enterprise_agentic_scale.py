"""Generated enterprise-agentic standard and longitudinal contract tests."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from synthworld.agentic import (
    AgenticBenchmark,
    AgenticTraceSubmission,
    ObservedActionTrace,
    reference_agentic_trace,
    trace_submission_to_jsonl,
)
from synthworld.agentic.enterprise import (
    EnterpriseAgenticArtifactError,
    EnterpriseAgenticGenerationConfigV1,
    EnterpriseAgenticGenerationConfigV2,
    EnterpriseAgenticScaleTierV2,
    default_enterprise_agentic_generation_config_v2,
    evaluate_generated_enterprise_agentic_trace,
    export_generated_enterprise_agentic_public_benchmark,
    export_generated_enterprise_agentic_scale_benchmark,
    export_generated_enterprise_agentic_scale_public_benchmark,
    generate_enterprise_agentic_scale_world,
    generate_enterprise_agentic_world,
    generated_enterprise_agentic_scale_artifact_checksums,
    generated_enterprise_agentic_scale_evaluator_artifacts,
    generated_enterprise_agentic_scale_public_artifacts,
    load_any_generated_enterprise_agentic_benchmark,
    load_any_generated_enterprise_agentic_public,
    load_generated_enterprise_agentic_scale_benchmark,
    load_public_generated_enterprise_agentic_scale_benchmark,
)
from synthworld.agentic.enterprise.generated_dispatch import _declared_profile
from synthworld.agentic.enterprise.generated_models import (
    EnterpriseAgenticArtifactDescriptorV1,
)
from synthworld.agentic.enterprise.generated_scale import (
    derive_enterprise_agentic_scale_integrity_metrics,
)
from synthworld.agentic.enterprise.generated_scale_models import (
    ENTERPRISE_AGENTIC_LONGITUDINAL_EVENT_SCHEDULE_VERSION,
    EnterpriseAgenticAgentLifecycleStateV2,
    EnterpriseAgenticAgentStatusChangedV2,
    EnterpriseAgenticAuthorityTopologyV2,
    EnterpriseAgenticCredentialRotatedV2,
    EnterpriseAgenticCredentialStatusChangedV2,
    EnterpriseAgenticCredentialTopologyV2,
    EnterpriseAgenticDelegationPropagationV2,
    EnterpriseAgenticGeneratedBenchmarkV2,
    EnterpriseAgenticGeneratedEvaluatorManifestV2,
    EnterpriseAgenticGeneratedEvaluatorV2,
    EnterpriseAgenticGeneratedPublicManifestV2,
    EnterpriseAgenticGeneratedPublicV2,
    EnterpriseAgenticGenerationLimitsV2,
    EnterpriseAgenticLifecycleCaseKindV2,
    EnterpriseAgenticLifecycleEventV2,
    EnterpriseAgenticLifecycleStreamV2,
    EnterpriseAgenticLongitudinalScheduleV2,
    EnterpriseAgenticPersonLifecycleStateV2,
    EnterpriseAgenticPersonStatusChangedV2,
    EnterpriseAgenticPolicyActivatedV2,
    EnterpriseAgenticScaleTopologyV2,
    EnterpriseAgenticScenarioPrevalenceV2,
    EnterpriseAgenticTopologyMetadataV2,
)
from synthworld.agentic.enterprise.generated_serialization import (
    export_generated_enterprise_agentic_benchmark,
    generated_enterprise_agentic_artifact_set_sha256,
)
from synthworld.agentic.models import Decision
from synthworld.cli import main
from synthworld.enterprise.canonical import (
    canonical_json_bytes,
    canonical_json_value_bytes,
)


def _benchmark(generated: EnterpriseAgenticGeneratedBenchmarkV2) -> AgenticBenchmark:
    return AgenticBenchmark(public=generated.public, evaluator=generated.evaluator)


def _write_tree(root: Path, artifacts: dict[str, bytes]) -> None:
    for relative_path, payload in artifacts.items():
        target = root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)


def _descriptor(path: str, payload: bytes) -> EnterpriseAgenticArtifactDescriptorV1:
    return EnterpriseAgenticArtifactDescriptorV1(
        path=path,
        byte_size=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def _rebind_public(artifacts: dict[str, bytes]) -> None:
    base = {
        path: payload for path, payload in artifacts.items() if path != "manifest.json"
    }
    artifacts["manifest.json"] = canonical_json_bytes(
        EnterpriseAgenticGeneratedPublicManifestV2(
            artifact_set_sha256=generated_enterprise_agentic_artifact_set_sha256(base),
            artifacts=tuple(
                _descriptor(path, payload) for path, payload in sorted(base.items())
            ),
        )
    )


def _rebind_evaluator(artifacts: dict[str, bytes], public_digest: str) -> None:
    base = {
        path: payload for path, payload in artifacts.items() if path != "manifest.json"
    }
    artifacts["manifest.json"] = canonical_json_bytes(
        EnterpriseAgenticGeneratedEvaluatorManifestV2(
            artifact_set_sha256=generated_enterprise_agentic_artifact_set_sha256(base),
            public_artifact_set_sha256=public_digest,
            artifacts=tuple(
                _descriptor(path, payload) for path, payload in sorted(base.items())
            ),
        )
    )


@pytest.mark.parametrize("tier", tuple(EnterpriseAgenticScaleTierV2))
def test_scale_tiers_are_deterministic_derived_and_scoreable(
    tier: EnterpriseAgenticScaleTierV2,
) -> None:
    config = default_enterprise_agentic_generation_config_v2(tier, seed=17)
    first = generate_enterprise_agentic_scale_world(config)
    second = generate_enterprise_agentic_scale_world(config)
    alternate = generate_enterprise_agentic_scale_world(
        default_enterprise_agentic_generation_config_v2(tier, seed=18)
    )

    assert first == second
    assert generated_enterprise_agentic_scale_public_artifacts(first) == (
        generated_enterprise_agentic_scale_public_artifacts(second)
    )
    assert first.identity.world_id != alternate.identity.world_id
    assert first.public.snapshot.principals != alternate.public.snapshot.principals
    assert len(first.public.snapshot.principals) == 360
    assert len(first.evaluator.authority_truth) == config.prevalence.total
    assert first.metrics == derive_enterprise_agentic_scale_integrity_metrics(
        _benchmark(first),
        first.topology,
        first.lifecycle_events,
        first.lifecycle_cases,
    )
    assert first.metrics.principal_graph_component_count == 2
    counts = {item.name: item for item in first.metrics.counts}
    assert counts["organisation_count"].count == 2
    assert counts["human_principal_count"].count == 250
    assert counts["logical_agent_count"].count == 36
    assert counts["runtime_count"].count == 72
    assert counts["resource_count"].count == 36
    assert counts["team_count"].count == 16
    assert counts["allowed_action_count"].count > 0
    assert counts["denied_action_count"].count > 0
    assert all(item.denominator_meaning for item in first.metrics.counts)
    assert first.metrics.delegation_branching_distribution
    report = evaluate_generated_enterprise_agentic_trace(
        reference_agentic_trace(_benchmark(first)), first
    )
    assert report.checksum_scheme == "sha256-generated-enterprise-agentic-v2"
    assert report.artifact_checksums == (
        generated_enterprise_agentic_scale_artifact_checksums(first)
    )
    assert all(item.value in {0.0, 1.0, None} for item in report.metrics)


def test_longitudinal_tier_covers_versioned_lifecycle_semantics() -> None:
    generated = generate_enterprise_agentic_scale_world(
        default_enterprise_agentic_generation_config_v2(
            EnterpriseAgenticScaleTierV2.LONGITUDINAL,
            seed=19,
        )
    )
    kinds = Counter(item.payload.event_type for item in generated.lifecycle_events)
    case_kinds = Counter(item.kind for item in generated.lifecycle_cases)

    assert len(generated.lifecycle_events) == 13
    assert kinds["credential_rotated"] == 3
    assert kinds["credential_status_changed"] == 4
    assert kinds["person_status_changed"] == 3
    assert kinds["policy_activated"] == 1
    assert kinds["agent_status_changed"] == 1
    assert kinds["delegation_revocation_propagated"] == 1
    assert (
        case_kinds[EnterpriseAgenticLifecycleCaseKindV2.ROTATED_CREDENTIAL_REUSE] == 2
    )
    assert case_kinds[EnterpriseAgenticLifecycleCaseKindV2.SUSPENDED_CREDENTIAL] == 2
    assert (
        case_kinds[
            EnterpriseAgenticLifecycleCaseKindV2.AGENT_OFFBOARDING_ACTIVE_CREDENTIAL
        ]
        == 2
    )
    assert (
        case_kinds[EnterpriseAgenticLifecycleCaseKindV2.REVOCATION_PROPAGATION_FAILURE]
        == 2
    )
    assert tuple(item.sequence_index for item in generated.lifecycle_events) == tuple(
        range(1, 14)
    )
    assert tuple(item.occurred_at for item in generated.lifecycle_events) == tuple(
        sorted(item.occurred_at for item in generated.lifecycle_events)
    )
    truth = {item.action_event_id: item for item in generated.evaluator.authority_truth}
    for case in generated.lifecycle_cases:
        if case.kind in {
            EnterpriseAgenticLifecycleCaseKindV2.ROTATED_CREDENTIAL_REUSE,
            EnterpriseAgenticLifecycleCaseKindV2.SUSPENDED_CREDENTIAL,
            EnterpriseAgenticLifecycleCaseKindV2.AGENT_OFFBOARDING_ACTIVE_CREDENTIAL,
            EnterpriseAgenticLifecycleCaseKindV2.REVOCATION_PROPAGATION_FAILURE,
        }:
            assert truth[case.action_event_id].decision_at_action is Decision.DENY


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (
            {
                "employee_count": 12,
                "contractor_count": 0,
                "supplier_count": 0,
                "external_partner_count": 0,
                "logical_agent_count": 13,
            },
            "logical agents cannot outnumber",
        ),
        ({"logical_agent_count": 12, "runtime_count": 10}, "requires at least"),
        (
            {"organisation_count": 3, "resource_count": 8},
            "at least three resources",
        ),
        ({"employee_count": True}, "valid integer"),
    ],
)
def test_scale_topology_rejects_invalid_counts(
    kwargs: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        EnterpriseAgenticScaleTopologyV2(**kwargs)  # type: ignore[arg-type]


def test_scale_configuration_rejects_invalid_ratios_schedules_and_limits() -> None:
    with pytest.raises(ValidationError, match="ratios must sum to one"):
        EnterpriseAgenticAuthorityTopologyV2(
            direct_human_delegation_ratio=0.5,
            organisation_delegation_ratio=0.2,
            agent_subdelegation_ratio=0.2,
        )
    schedule = EnterpriseAgenticLongitudinalScheduleV2()
    schedule_values = schedule.model_dump(exclude={"synthetic"})
    for field in (
        "credential_rotation_interval_days",
        "evidence_retention_days",
        "policy_change_day",
        "agent_offboarding_day",
    ):
        invalid = {**schedule_values, field: schedule.virtual_duration_days}
        with pytest.raises(ValidationError, match="within virtual duration"):
            EnterpriseAgenticLongitudinalScheduleV2(**invalid)
    with pytest.raises(ValidationError, match="suspension must occur"):
        EnterpriseAgenticLongitudinalScheduleV2(
            virtual_duration_days=100,
            credential_rotation_interval_days=90,
            evidence_retention_days=50,
            policy_change_day=40,
            agent_offboarding_day=70,
        )
    with pytest.raises(ValidationError, match="must precede"):
        EnterpriseAgenticLongitudinalScheduleV2(
            policy_change_day=130,
            agent_offboarding_day=120,
        )
    with pytest.raises(ValidationError, match="propagation must occur"):
        EnterpriseAgenticLongitudinalScheduleV2(
            virtual_duration_days=130,
            policy_change_day=90,
            agent_offboarding_day=120,
        )

    with pytest.raises(ValidationError, match="standard event schedule"):
        EnterpriseAgenticGenerationConfigV2(
            event_schedule_version=(
                ENTERPRISE_AGENTIC_LONGITUDINAL_EVENT_SCHEDULE_VERSION
            )
        )
    with pytest.raises(ValidationError, match="longitudinal controls"):
        EnterpriseAgenticGenerationConfigV2(
            longitudinal=EnterpriseAgenticLongitudinalScheduleV2()
        )
    with pytest.raises(ValidationError, match="longitudinal event schedule"):
        EnterpriseAgenticGenerationConfigV2(
            tier=EnterpriseAgenticScaleTierV2.LONGITUDINAL
        )
    with pytest.raises(ValidationError, match="every lifecycle case"):
        EnterpriseAgenticGenerationConfigV2(
            tier=EnterpriseAgenticScaleTierV2.LONGITUDINAL,
            event_schedule_version=(
                ENTERPRISE_AGENTIC_LONGITUDINAL_EVENT_SCHEDULE_VERSION
            ),
            longitudinal=EnterpriseAgenticLongitudinalScheduleV2(),
        )
    with pytest.raises(ValidationError, match="at least two organisations"):
        EnterpriseAgenticGenerationConfigV2(
            topology=EnterpriseAgenticScaleTopologyV2(organisation_count=1)
        )
    with pytest.raises(ValidationError, match="runtime breadth"):
        EnterpriseAgenticGenerationConfigV2(
            credentials=EnterpriseAgenticCredentialTopologyV2(
                allowed_runtimes_per_shared_credential=12
            ),
            topology=EnterpriseAgenticScaleTopologyV2(
                logical_agent_count=10, runtime_count=10
            ),
        )
    with pytest.raises(ValidationError, match="per-agent runtimes"):
        EnterpriseAgenticGenerationConfigV2(
            topology=EnterpriseAgenticScaleTopologyV2(
                logical_agent_count=10, runtime_count=10
            )
        )
    with pytest.raises(ValidationError, match="scheduled rotations"):
        EnterpriseAgenticGenerationConfigV2(
            tier=EnterpriseAgenticScaleTierV2.LONGITUDINAL,
            event_schedule_version=(
                ENTERPRISE_AGENTIC_LONGITUDINAL_EVENT_SCHEDULE_VERSION
            ),
            prevalence=EnterpriseAgenticScenarioPrevalenceV2(
                rotated_credential_reuse=3,
                suspended_credential=1,
                agent_offboarding_active_credential=1,
                revocation_propagation_failure=1,
            ),
            longitudinal=EnterpriseAgenticLongitudinalScheduleV2(
                virtual_duration_days=60,
                credential_rotation_interval_days=20,
                evidence_retention_days=30,
                policy_change_day=30,
                agent_offboarding_day=40,
            ),
        )

    base = EnterpriseAgenticGenerationConfigV2()
    with pytest.raises(ValidationError, match="cases exceed"):
        EnterpriseAgenticGenerationConfigV2(
            limits=EnterpriseAgenticGenerationLimitsV2(max_cases=1)
        )
    with pytest.raises(ValidationError, match="principals exceed"):
        EnterpriseAgenticGenerationConfigV2(
            limits=EnterpriseAgenticGenerationLimitsV2(max_principals=1)
        )
    with pytest.raises(ValidationError, match="events exceed"):
        EnterpriseAgenticGenerationConfigV2(
            limits=EnterpriseAgenticGenerationLimitsV2(max_events=1)
        )
    assert base.prevalence.total == 23


def test_scale_generation_supports_one_tenant_and_enforces_actual_event_limit() -> None:
    config = EnterpriseAgenticGenerationConfigV2(
        topology=EnterpriseAgenticScaleTopologyV2(organisation_count=1),
        prevalence=EnterpriseAgenticScenarioPrevalenceV2(
            cross_tenant_confusion=0,
            evidence_loss=0,
            valid_then_revoked=0,
        ),
    )
    generated = generate_enterprise_agentic_scale_world(config)
    assert generated.metrics.principal_graph_component_count == 1
    counts = {item.name: item.count for item in generated.metrics.counts}
    assert counts["isolated_tenant_count"] == 0
    constrained = config.model_dump()
    constrained["limits"] = EnterpriseAgenticGenerationLimitsV2(
        max_events=(
            config.topology.logical_agent_count
            + (2 * config.topology.runtime_count)
            + config.prevalence.total
            + 1
        )
    )
    limited = EnterpriseAgenticGenerationConfigV2.model_validate(constrained)
    with pytest.raises(ValueError, match="generated events exceed"):
        generate_enterprise_agentic_scale_world(limited)

    sparse_resources = generate_enterprise_agentic_scale_world(
        EnterpriseAgenticGenerationConfigV2(
            topology=EnterpriseAgenticScaleTopologyV2(
                logical_agent_count=10,
                runtime_count=20,
                resource_count=6,
            )
        )
    )
    assert sparse_resources.evaluator.authority_truth


def test_scale_model_validators_reject_invalid_lifecycle_shapes() -> None:
    with pytest.raises(ValidationError, match="distinct credentials"):
        EnterpriseAgenticCredentialRotatedV2(
            old_credential_id="same", new_credential_id="same"
        )
    assert EnterpriseAgenticPersonStatusChangedV2(
        principal_id="person",
        state=EnterpriseAgenticPersonLifecycleStateV2.JOINED,
        department_id="department",
    )
    assert EnterpriseAgenticPersonStatusChangedV2(
        principal_id="person",
        state=EnterpriseAgenticPersonLifecycleStateV2.MOVED,
        previous_department_id="old",
        department_id="new",
    )
    assert EnterpriseAgenticPersonStatusChangedV2(
        principal_id="person",
        state=EnterpriseAgenticPersonLifecycleStateV2.LEFT,
        previous_department_id="old",
    )
    for state in EnterpriseAgenticPersonLifecycleStateV2:
        with pytest.raises(ValidationError, match="inconsistent departments"):
            EnterpriseAgenticPersonStatusChangedV2(
                principal_id="person",
                state=state,
            )
    with pytest.raises(ValidationError, match="version change"):
        EnterpriseAgenticPolicyActivatedV2(
            previous_policy_version="same", policy_version="same"
        )
    with pytest.raises(ValidationError, match="timestamp must be UTC"):
        EnterpriseAgenticLifecycleEventV2(
            id="event",
            sequence_index=1,
            occurred_at=datetime(2035, 1, 1),
            payload=EnterpriseAgenticPolicyActivatedV2(
                previous_policy_version="v1", policy_version="v2"
            ),
        )
    with pytest.raises(ValidationError, match="at least 1 item"):
        EnterpriseAgenticAgentStatusChangedV2(
            agent_id="agent",
            state=EnterpriseAgenticAgentLifecycleStateV2.OFFBOARDED,
            active_credential_ids=(),
        )


def test_scale_public_model_rejects_broken_topology_references() -> None:
    generated = generate_enterprise_agentic_scale_world(
        default_enterprise_agentic_generation_config_v2(
            EnterpriseAgenticScaleTierV2.LONGITUDINAL,
            seed=21,
        )
    )

    def reject(topology: EnterpriseAgenticTopologyMetadataV2, message: str) -> None:
        with pytest.raises(ValidationError, match=message):
            EnterpriseAgenticGeneratedPublicV2(
                config=generated.config,
                identity=generated.identity,
                benchmark=generated.public,
                topology=topology,
                lifecycle_events=generated.lifecycle_events,
            )

    topology = generated.topology
    reject(
        topology.model_copy(
            update={
                "teams": (topology.teams[0], topology.teams[0], *topology.teams[2:])
            }
        ),
        "teams have invalid",
    )
    reject(
        topology.model_copy(
            update={
                "teams": (
                    topology.teams[0].model_copy(
                        update={"department_id": "unknown-department"}
                    ),
                    *topology.teams[1:],
                )
            }
        ),
        "teams have invalid",
    )
    reject(
        topology.model_copy(
            update={
                "people": (
                    topology.people[0],
                    topology.people[0],
                    *topology.people[2:],
                )
            }
        ),
        "people must cover",
    )
    reject(
        topology.model_copy(update={"people": topology.people[:-1]}),
        "people must cover",
    )
    reject(
        topology.model_copy(
            update={
                "people": (
                    topology.people[0].model_copy(
                        update={"team_ids": ("unknown-team",)}
                    ),
                    *topology.people[1:],
                )
            }
        ),
        "unknown teams",
    )
    reject(
        topology.model_copy(
            update={
                "resources": (
                    topology.resources[0],
                    topology.resources[0],
                    *topology.resources[2:],
                )
            }
        ),
        "resources must be profiled",
    )
    reject(
        topology.model_copy(update={"resources": topology.resources[:-1]}),
        "resources must be profiled",
    )
    reject(
        topology.model_copy(
            update={
                "credentials": (
                    topology.credentials[0],
                    topology.credentials[0],
                    *topology.credentials[2:],
                )
            }
        ),
        "credentials must be profiled",
    )
    reject(
        topology.model_copy(update={"credentials": topology.credentials[:-1]}),
        "credentials must be profiled",
    )
    reject(
        topology.model_copy(update={"isolated_tenant_ids": ("unknown-tenant",)}),
        "unknown tenants",
    )


def test_scale_public_model_rejects_broken_lifecycle_references() -> None:
    generated = generate_enterprise_agentic_scale_world(
        default_enterprise_agentic_generation_config_v2(
            EnterpriseAgenticScaleTierV2.LONGITUDINAL,
            seed=22,
        )
    )

    def reject(
        events: tuple[EnterpriseAgenticLifecycleEventV2, ...], message: str
    ) -> None:
        with pytest.raises(ValidationError, match=message):
            EnterpriseAgenticGeneratedPublicV2(
                config=generated.config,
                identity=generated.identity,
                benchmark=generated.public,
                topology=generated.topology,
                lifecycle_events=events,
            )

    def replace_payload(
        payload_type: type[object], **updates: object
    ) -> tuple[EnterpriseAgenticLifecycleEventV2, ...]:
        events = list(generated.lifecycle_events)
        index = next(
            position
            for position, item in enumerate(events)
            if isinstance(item.payload, payload_type)
        )
        events[index] = events[index].model_copy(
            update={"payload": events[index].payload.model_copy(update=updates)}
        )
        return tuple(events)

    reject(
        (
            generated.lifecycle_events[0],
            generated.lifecycle_events[1].model_copy(
                update={"id": generated.lifecycle_events[0].id}
            ),
            *generated.lifecycle_events[2:],
        ),
        "IDs must be unique",
    )
    reject(
        (
            generated.lifecycle_events[0].model_copy(
                update={"related_agentic_event_id": "unknown-event"}
            ),
            *generated.lifecycle_events[1:],
        ),
        "unknown agentic event",
    )
    reject(
        replace_payload(
            EnterpriseAgenticCredentialRotatedV2,
            old_credential_id="unknown-credential",
        ),
        "broken references",
    )
    reject(
        replace_payload(
            EnterpriseAgenticCredentialStatusChangedV2,
            credential_id="unknown-credential",
        ),
        "broken references",
    )
    reject(
        replace_payload(
            EnterpriseAgenticAgentStatusChangedV2,
            agent_id="unknown-agent",
        ),
        "broken references",
    )
    reject(
        replace_payload(
            EnterpriseAgenticAgentStatusChangedV2,
            active_credential_ids=("unknown-credential",),
        ),
        "broken references",
    )
    reject(
        replace_payload(
            EnterpriseAgenticPersonStatusChangedV2,
            principal_id="unknown-principal",
        ),
        "broken references",
    )
    reject(
        replace_payload(
            EnterpriseAgenticPersonStatusChangedV2,
            department_id="unknown-department",
        ),
        "broken references",
    )
    reject(
        replace_payload(
            EnterpriseAgenticPolicyActivatedV2,
            previous_policy_version="unknown-policy",
        ),
        "broken references",
    )
    reject(
        replace_payload(
            EnterpriseAgenticDelegationPropagationV2,
            parent_delegation_id="unknown-delegation",
        ),
        "broken references",
    )
    reject(
        replace_payload(
            EnterpriseAgenticDelegationPropagationV2,
            descendant_delegation_ids=("unknown-delegation",),
        ),
        "broken references",
    )


@pytest.mark.parametrize("tier", tuple(EnterpriseAgenticScaleTierV2))
def test_scale_artifacts_round_trip_and_dispatch(
    tier: EnterpriseAgenticScaleTierV2,
    tmp_path: Path,
) -> None:
    generated = generate_enterprise_agentic_scale_world(
        default_enterprise_agentic_generation_config_v2(tier, seed=23)
    )
    root = tmp_path / tier.value
    export_generated_enterprise_agentic_scale_benchmark(root, generated)
    with pytest.raises(FileExistsError, match="already exists"):
        export_generated_enterprise_agentic_scale_benchmark(root, generated)

    public = load_public_generated_enterprise_agentic_scale_benchmark(root)
    assert public.benchmark == generated.public
    assert load_any_generated_enterprise_agentic_public(root) == public
    assert load_generated_enterprise_agentic_scale_benchmark(root) == generated
    assert load_any_generated_enterprise_agentic_benchmark(root) == generated
    public_bytes = b"".join(
        generated_enterprise_agentic_scale_public_artifacts(generated).values()
    )
    for forbidden in (
        b"authority_truth",
        b"lifecycle_cases",
        b"expected_decision",
        b"failure_reasons_at_action",
    ):
        assert forbidden not in public_bytes


def test_v1_and_v2_dispatch_are_backward_compatible(tmp_path: Path) -> None:
    smoke = generate_enterprise_agentic_world(
        EnterpriseAgenticGenerationConfigV1(seed=29)
    )
    smoke_root = tmp_path / "smoke"
    export_generated_enterprise_agentic_benchmark(smoke_root, smoke)
    assert load_any_generated_enterprise_agentic_public(smoke_root).config == (
        smoke.config
    )
    assert load_any_generated_enterprise_agentic_benchmark(smoke_root) == smoke

    missing = tmp_path / "missing"
    with pytest.raises(
        EnterpriseAgenticArtifactError, match="discriminator is invalid"
    ):
        _declared_profile(missing)
    invalid = tmp_path / "invalid"
    (invalid / "public").mkdir(parents=True)
    (invalid / "public" / "public-input.json").write_text("[]\n", encoding="utf-8")
    with pytest.raises(
        EnterpriseAgenticArtifactError, match="discriminator is invalid"
    ):
        _declared_profile(invalid)
    unsupported = tmp_path / "unsupported"
    (unsupported / "public").mkdir(parents=True)
    (unsupported / "public" / "public-input.json").write_text(
        json.dumps({"config": {"profile_version": "unknown"}}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(EnterpriseAgenticArtifactError, match="unsupported"):
        _declared_profile(unsupported)
    linked = tmp_path / "linked"
    (linked / "public").mkdir(parents=True)
    (linked / "public" / "public-input.json").symlink_to(
        unsupported / "public" / "public-input.json"
    )
    with pytest.raises(EnterpriseAgenticArtifactError, match="not a regular file"):
        _declared_profile(linked)


def test_scale_public_only_export_and_cli_paths(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    generated = generate_enterprise_agentic_scale_world(
        default_enterprise_agentic_generation_config_v2(
            EnterpriseAgenticScaleTierV2.STANDARD,
            seed=31,
        )
    )
    public_root = tmp_path / "public-only-api"
    export_generated_enterprise_agentic_scale_public_benchmark(public_root, generated)
    assert (public_root / "public" / "public-input.json").is_file()
    assert not (public_root / "evaluator").exists()
    with pytest.raises(FileExistsError, match="already exists"):
        export_generated_enterprise_agentic_scale_public_benchmark(
            public_root, generated
        )

    cli_root = tmp_path / "standard-cli"
    assert (
        main(
            [
                "generate-enterprise-agentic",
                "--profile",
                "generated",
                "--tier",
                "standard",
                "--seed",
                "31",
                "--output",
                str(cli_root),
            ]
        )
        == 0
    )
    assert "standard world ready: 360 principals, 23 actions" in (
        capsys.readouterr().out
    )
    reloaded = load_any_generated_enterprise_agentic_benchmark(cli_root)
    assert isinstance(reloaded, EnterpriseAgenticGeneratedBenchmarkV2)
    trace = tmp_path / "reference.jsonl"
    trace.write_text(
        trace_submission_to_jsonl(reference_agentic_trace(_benchmark(reloaded))),
        encoding="utf-8",
    )
    assert (
        main(
            [
                "validate",
                "generated-enterprise-agentic-trace",
                "--benchmark-root",
                str(cli_root),
                "--predictions",
                str(trace),
            ]
        )
        == 0
    )
    assert "valid" in capsys.readouterr().out
    assert (
        main(
            [
                "evaluate",
                "generated-enterprise-agentic",
                "--benchmark-root",
                str(cli_root),
                "--predictions",
                str(trace),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["checksum_scheme"].endswith("v2")


def test_cli_accepts_resolved_config_and_public_only(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = default_enterprise_agentic_generation_config_v2(
        EnterpriseAgenticScaleTierV2.LONGITUDINAL,
        seed=41,
    )
    config_path = tmp_path / "config.json"
    config_path.write_bytes(canonical_json_bytes(config))
    output = tmp_path / "longitudinal-public"
    assert (
        main(
            [
                "generate-enterprise-agentic",
                "--profile",
                "generated",
                "--tier",
                "longitudinal",
                "--seed",
                "42",
                "--config",
                str(config_path),
                "--public-only",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert "longitudinal world ready" in capsys.readouterr().out
    public = load_any_generated_enterprise_agentic_public(output)
    assert public.config.seed == 42
    assert not (output / "evaluator").exists()

    smoke_config = tmp_path / "smoke-config.json"
    smoke_config.write_bytes(
        canonical_json_bytes(EnterpriseAgenticGenerationConfigV1(seed=1))
    )
    smoke_output = tmp_path / "smoke-public"
    assert (
        main(
            [
                "generate-enterprise-agentic",
                "--profile",
                "generated",
                "--tier",
                "smoke",
                "--seed",
                "43",
                "--config",
                str(smoke_config),
                "--public-only",
                "--output",
                str(smoke_output),
            ]
        )
        == 0
    )
    assert not (smoke_output / "evaluator").exists()
    smoke_generated = generate_enterprise_agentic_world(
        EnterpriseAgenticGenerationConfigV1(seed=43)
    )
    with pytest.raises(FileExistsError, match="already exists"):
        export_generated_enterprise_agentic_public_benchmark(
            smoke_output, smoke_generated
        )
    capsys.readouterr()

    invalid_config = tmp_path / "invalid.json"
    invalid_config.write_text("{\n", encoding="utf-8")
    assert (
        main(
            [
                "generate-enterprise-agentic",
                "--profile",
                "generated",
                "--tier",
                "standard",
                "--config",
                str(invalid_config),
                "--output",
                str(tmp_path / "invalid-output"),
            ]
        )
        == 1
    )
    assert capsys.readouterr().err
    list_config = tmp_path / "list.json"
    list_config.write_text("[]\n", encoding="utf-8")
    assert (
        main(
            [
                "generate-enterprise-agentic",
                "--profile",
                "generated",
                "--config",
                str(list_config),
                "--output",
                str(tmp_path / "list-output"),
            ]
        )
        == 1
    )
    assert "JSON object" in capsys.readouterr().err
    assert (
        main(
            [
                "generate-enterprise-agentic",
                "--profile",
                "fixed",
                "--tier",
                "standard",
                "--output",
                str(tmp_path / "fixed-standard"),
            ]
        )
        == 1
    )
    assert "require --profile generated" in capsys.readouterr().err


def test_v2_loader_rejects_duplicate_and_resigned_drift(tmp_path: Path) -> None:
    generated = generate_enterprise_agentic_scale_world(
        default_enterprise_agentic_generation_config_v2(
            EnterpriseAgenticScaleTierV2.STANDARD,
            seed=43,
        )
    )
    public_artifacts = generated_enterprise_agentic_scale_public_artifacts(generated)
    evaluator_artifacts = generated_enterprise_agentic_scale_evaluator_artifacts(
        generated
    )

    scenario_drift = dict(public_artifacts)
    scenario = generated.public.scenario.model_copy(update={"title": "Drift"})
    scenario_drift["scenarios/enterprise-agentic-scale-v2.json"] = canonical_json_bytes(
        scenario
    )
    _rebind_public(scenario_drift)
    scenario_root = tmp_path / "scenario"
    _write_tree(scenario_root / "public", scenario_drift)
    with pytest.raises(EnterpriseAgenticArtifactError, match="scenario differs"):
        load_public_generated_enterprise_agentic_scale_benchmark(scenario_root)

    changed_public = EnterpriseAgenticGeneratedPublicV2.model_validate_json(
        public_artifacts["public-input.json"]
    )
    changed_snapshot = changed_public.benchmark.snapshot.model_copy(
        update={
            "organisations": (
                changed_public.benchmark.snapshot.organisations[0].model_copy(
                    update={"display_name": "Altered Synthetic Enterprise"}
                ),
                *changed_public.benchmark.snapshot.organisations[1:],
            )
        }
    )
    changed_public = changed_public.model_copy(
        update={
            "benchmark": changed_public.benchmark.model_copy(
                update={"snapshot": changed_snapshot}
            )
        }
    )
    public_artifacts["public-input.json"] = canonical_json_bytes(changed_public)
    _rebind_public(public_artifacts)
    public_digest = generated_enterprise_agentic_artifact_set_sha256(public_artifacts)
    evaluator = EnterpriseAgenticGeneratedEvaluatorV2.model_validate_json(
        evaluator_artifacts["truth.json"]
    ).model_copy(update={"public_artifact_set_sha256": public_digest})
    evaluator_artifacts["truth.json"] = canonical_json_bytes(evaluator)
    _rebind_evaluator(evaluator_artifacts, public_digest)
    root = tmp_path / "resigned"
    _write_tree(root / "public", public_artifacts)
    _write_tree(root / "evaluator", evaluator_artifacts)
    with pytest.raises(EnterpriseAgenticArtifactError, match="declared generation"):
        load_generated_enterprise_agentic_scale_benchmark(root)


def test_v2_public_loader_rejects_resigned_duplicate_artifact_drift(
    tmp_path: Path,
) -> None:
    generated = generate_enterprise_agentic_scale_world(
        default_enterprise_agentic_generation_config_v2(
            EnterpriseAgenticScaleTierV2.STANDARD,
            seed=44,
        )
    )
    pristine = generated_enterprise_agentic_scale_public_artifacts(generated)

    def reject(
        name: str, artifacts: dict[str, bytes], message: str, *, rebind: bool = True
    ) -> None:
        if rebind:
            _rebind_public(artifacts)
        root = tmp_path / name
        _write_tree(root / "public", artifacts)
        with pytest.raises(EnterpriseAgenticArtifactError, match=message):
            load_public_generated_enterprise_agentic_scale_benchmark(root)

    manifest_drift = dict(pristine)
    manifest = EnterpriseAgenticGeneratedPublicManifestV2.model_validate_json(
        manifest_drift["manifest.json"]
    ).model_copy(update={"artifact_set_sha256": "0" * 64})
    manifest_drift["manifest.json"] = canonical_json_bytes(manifest)
    reject("manifest", manifest_drift, "manifest differs", rebind=False)

    topology_drift = dict(pristine)
    topology_drift["topology.json"] = canonical_json_bytes(
        generated.topology.model_copy(update={"isolated_tenant_ids": ()})
    )
    reject("topology", topology_drift, "topology differs")

    lifecycle_drift = dict(pristine)
    lifecycle_drift["lifecycle-events.json"] = canonical_json_bytes(
        EnterpriseAgenticLifecycleStreamV2(
            events=(
                EnterpriseAgenticLifecycleEventV2(
                    id="standalone-lifecycle-drift",
                    sequence_index=1,
                    occurred_at=generated.public.events[0].occurred_at,
                    payload=EnterpriseAgenticPolicyActivatedV2(
                        previous_policy_version="enterprise-agentic-policy-v1",
                        policy_version="enterprise-agentic-policy-v2",
                    ),
                ),
            )
        )
    )
    reject("lifecycle", lifecycle_drift, "lifecycle events differ")

    tool_drift = dict(pristine)
    tool_drift["tool_schemas/enterprise-agentic-actions-v1.json"] = (
        canonical_json_value_bytes({"title": "synthetic drift"})
    )
    reject("tool", tool_drift, "tool schema differs")


def test_v2_complete_loader_rejects_evaluator_semantic_drift(tmp_path: Path) -> None:
    generated = generate_enterprise_agentic_scale_world(
        default_enterprise_agentic_generation_config_v2(
            EnterpriseAgenticScaleTierV2.STANDARD,
            seed=45,
        )
    )
    public_artifacts = generated_enterprise_agentic_scale_public_artifacts(generated)
    public_digest = generated_enterprise_agentic_artifact_set_sha256(public_artifacts)
    pristine = generated_enterprise_agentic_scale_evaluator_artifacts(generated)

    def reject(
        name: str, artifacts: dict[str, bytes], message: str, *, rebind: bool = True
    ) -> None:
        if rebind:
            _rebind_evaluator(artifacts, public_digest)
        root = tmp_path / name
        _write_tree(root / "public", public_artifacts)
        _write_tree(root / "evaluator", artifacts)
        with pytest.raises(EnterpriseAgenticArtifactError, match=message):
            load_generated_enterprise_agentic_scale_benchmark(root)

    manifest_drift = dict(pristine)
    manifest = EnterpriseAgenticGeneratedEvaluatorManifestV2.model_validate_json(
        manifest_drift["manifest.json"]
    ).model_copy(update={"artifact_set_sha256": "0" * 64})
    manifest_drift["manifest.json"] = canonical_json_bytes(manifest)
    reject("evaluator-manifest", manifest_drift, "manifest differs", rebind=False)

    binding_drift = dict(pristine)
    evaluator = EnterpriseAgenticGeneratedEvaluatorV2.model_validate_json(
        binding_drift["truth.json"]
    ).model_copy(update={"public_artifact_set_sha256": "0" * 64})
    binding_drift["truth.json"] = canonical_json_bytes(evaluator)
    reject("public-binding", binding_drift, "public/evaluator binding differs")

    invalid_binding = dict(pristine)
    evaluator = EnterpriseAgenticGeneratedEvaluatorV2.model_validate_json(
        invalid_binding["truth.json"]
    )
    binding = evaluator.benchmark.bindings[0].model_copy(
        update={"accountable_owner_chain": ("unknown-principal",)}
    )
    evaluator_bundle = evaluator.benchmark.model_copy(
        update={"bindings": (binding, *evaluator.benchmark.bindings[1:])}
    )
    invalid_binding["truth.json"] = canonical_json_bytes(
        evaluator.model_copy(update={"benchmark": evaluator_bundle})
    )
    reject("invalid-binding", invalid_binding, "bindings are invalid")

    truth_drift = dict(pristine)
    evaluator = EnterpriseAgenticGeneratedEvaluatorV2.model_validate_json(
        truth_drift["truth.json"]
    )
    truth = evaluator.benchmark.authority_truth[0].model_copy(
        update={"required_evidence_refs": ()}
    )
    evaluator_bundle = evaluator.benchmark.model_copy(
        update={"authority_truth": (truth, *evaluator.benchmark.authority_truth[1:])}
    )
    truth_drift["truth.json"] = canonical_json_bytes(
        evaluator.model_copy(update={"benchmark": evaluator_bundle})
    )
    reject("truth-drift", truth_drift, "evaluator truth differs")

    metric_drift = dict(pristine)
    evaluator = EnterpriseAgenticGeneratedEvaluatorV2.model_validate_json(
        metric_drift["truth.json"]
    )
    first_count = evaluator.metrics.counts[0]
    changed_count = first_count.model_copy(update={"count": first_count.count - 1})
    changed_metrics = evaluator.metrics.model_copy(
        update={"counts": (changed_count, *evaluator.metrics.counts[1:])}
    )
    metric_drift["truth.json"] = canonical_json_bytes(
        evaluator.model_copy(update={"metrics": changed_metrics})
    )
    reject("metric-drift", metric_drift, "integrity metrics differ")


def test_v2_generated_models_reject_identity_case_and_order_drift() -> None:
    generated = generate_enterprise_agentic_scale_world(
        default_enterprise_agentic_generation_config_v2(
            EnterpriseAgenticScaleTierV2.LONGITUDINAL,
            seed=47,
        )
    )
    bad_identity = generated.identity.model_copy(
        update={"configuration_sha256": "0" * 64}
    )
    with pytest.raises(ValidationError, match="configuration identity differs"):
        EnterpriseAgenticGeneratedPublicV2(
            config=generated.config,
            identity=bad_identity,
            benchmark=generated.public,
            topology=generated.topology,
            lifecycle_events=generated.lifecycle_events,
        )
    bad_world = generated.identity.model_copy(update={"world_id": "other"})
    with pytest.raises(ValidationError, match="world identity differs"):
        EnterpriseAgenticGeneratedPublicV2(
            config=generated.config,
            identity=bad_world,
            benchmark=generated.public,
            topology=generated.topology,
            lifecycle_events=generated.lifecycle_events,
        )
    with pytest.raises(ValidationError, match="world identity differs"):
        EnterpriseAgenticGeneratedBenchmarkV2(
            config=generated.config,
            identity=bad_world,
            public=generated.public,
            topology=generated.topology,
            lifecycle_events=generated.lifecycle_events,
            evaluator=generated.evaluator,
            lifecycle_cases=generated.lifecycle_cases,
            metrics=generated.metrics,
        )
    duplicate_cases = (
        generated.lifecycle_cases[0],
        generated.lifecycle_cases[0],
        *generated.lifecycle_cases[2:],
    )
    with pytest.raises(ValidationError, match="cover every action"):
        EnterpriseAgenticGeneratedBenchmarkV2(
            config=generated.config,
            identity=generated.identity,
            public=generated.public,
            topology=generated.topology,
            lifecycle_events=generated.lifecycle_events,
            evaluator=generated.evaluator,
            lifecycle_cases=duplicate_cases,
            metrics=generated.metrics,
        )
    bad_order = (
        generated.lifecycle_events[0].model_copy(update={"sequence_index": 2}),
        *generated.lifecycle_events[1:],
    )
    with pytest.raises(ValidationError, match="ordering is invalid"):
        EnterpriseAgenticGeneratedPublicV2(
            config=generated.config,
            identity=generated.identity,
            benchmark=generated.public,
            topology=generated.topology,
            lifecycle_events=bad_order,
        )
    reversed_time = (
        generated.lifecycle_events[0],
        generated.lifecycle_events[1].model_copy(
            update={
                "occurred_at": generated.lifecycle_events[0].occurred_at
                - timedelta(days=1)
            }
        ),
        *generated.lifecycle_events[2:],
    )
    with pytest.raises(ValidationError, match="ordering is invalid"):
        EnterpriseAgenticGeneratedPublicV2(
            config=generated.config,
            identity=generated.identity,
            benchmark=generated.public,
            topology=generated.topology,
            lifecycle_events=reversed_time,
        )
    with pytest.raises(ValidationError, match="evaluator identity differs"):
        EnterpriseAgenticGeneratedEvaluatorV2(
            identity=bad_world,
            public_artifact_set_sha256="0" * 64,
            benchmark=generated.evaluator,
            lifecycle_cases=generated.lifecycle_cases,
            metrics=generated.metrics,
        )
    with pytest.raises(ValidationError, match="cover every action"):
        EnterpriseAgenticGeneratedEvaluatorV2(
            identity=generated.identity,
            public_artifact_set_sha256="0" * 64,
            benchmark=generated.evaluator,
            lifecycle_cases=generated.lifecycle_cases[:-1],
            metrics=generated.metrics,
        )


def test_scale_trace_requires_exact_coverage() -> None:
    generated = generate_enterprise_agentic_scale_world(
        default_enterprise_agentic_generation_config_v2(
            EnterpriseAgenticScaleTierV2.STANDARD,
            seed=53,
        )
    )
    submission = AgenticTraceSubmission(
        rows=(
            ObservedActionTrace(
                event_id=generated.public.scenario.action_event_ids[0],
                decision=Decision.DENY,
            ),
        )
    )
    with pytest.raises(ValueError, match="cover every action"):
        evaluate_generated_enterprise_agentic_trace(submission, generated)
