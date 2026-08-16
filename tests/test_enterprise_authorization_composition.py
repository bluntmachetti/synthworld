"""Digest-exact aggregate authorization composition and artifact boundaries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError

from synthworld.enterprise.abac.models import CompiledEnterpriseAbacTruthV1
from synthworld.enterprise.authorization.compiler import (
    compile_enterprise_access_state,
    compile_enterprise_authorization_kernel,
    compose_enterprise_authorization,
)
from synthworld.enterprise.authorization.models import (
    AuthorizationCellProfileV1,
    AuthorizationEvaluationProfileV1,
    CompiledEnterpriseAccessStateV1,
    EnterpriseAuthorizationCompositionV1,
    MechanismOutcomeSetV1,
    PolicyConflictTruthV1,
)
from synthworld.enterprise.authorization.reference import (
    ReferenceEnterpriseAuthorizationInputsV1,
    reference_enterprise_authorization_inputs,
)
from synthworld.enterprise.authorization.serialization import (
    EnterpriseAuthorizationArtifactError,
    EnterpriseAuthorizationEvaluatorArtifactsV1,
    EnterpriseAuthorizationPublicArtifactsV1,
    _as,
    _require_exact_files,
    _validate_public_bindings,
    export_enterprise_authorization,
    load_evaluator_enterprise_authorization,
    load_public_enterprise_authorization,
)
from synthworld.enterprise.authorization_common import (
    AuthorizationEvaluationProfileKind,
    MechanismOutcome,
)
from synthworld.enterprise.canonical import (
    canonical_json_bytes,
    canonical_json_value_bytes,
    synthetic_digest,
)
from synthworld.enterprise.compiler import EnterpriseCompileError
from synthworld.enterprise.models import (
    EnterpriseCanonicalBindingTruthV1,
    EnterpriseIdentityAccessUniverseV1,
)
from synthworld.enterprise.rbac.common import AuthorizationDecision
from synthworld.enterprise.rbac.corpus_models import EnterpriseEvaluationCorpusV1
from synthworld.enterprise.rbac.models import (
    CompiledEnterpriseDirectoryRbacTruthV1,
)
from synthworld.enterprise.rebac.models import CompiledEnterpriseRebacTruthV1

_UNSET = object()


def _public(
    reference: ReferenceEnterpriseAuthorizationInputsV1,
) -> EnterpriseAuthorizationPublicArtifactsV1:
    return EnterpriseAuthorizationPublicArtifactsV1(
        abac_state=reference.abac_state,
        abac_intent=reference.abac_intent,
        rebac_state=reference.rebac_state,
        rebac_intent=reference.rebac_intent,
        composition=reference.composition,
        evaluation_scope=reference.evaluation_scope,
        kernel=reference.authorization_kernel,
    )


def _evaluator(
    reference: ReferenceEnterpriseAuthorizationInputsV1,
) -> EnterpriseAuthorizationEvaluatorArtifactsV1:
    return EnterpriseAuthorizationEvaluatorArtifactsV1(
        abac_truth=reference.abac_truth,
        rebac_truth=reference.rebac_truth,
        access_state=reference.access_state,
    )


def _compile(
    reference: ReferenceEnterpriseAuthorizationInputsV1,
    *,
    universe: EnterpriseIdentityAccessUniverseV1 | None = None,
    binding: EnterpriseCanonicalBindingTruthV1 | None = None,
    corpus: EnterpriseEvaluationCorpusV1 | None = None,
    composition: EnterpriseAuthorizationCompositionV1 | None = None,
    directory_rbac_truth: CompiledEnterpriseDirectoryRbacTruthV1 | None = None,
    abac_truth: CompiledEnterpriseAbacTruthV1 | None | object = _UNSET,
    rebac_truth: CompiledEnterpriseRebacTruthV1 | None | object = _UNSET,
    evaluation_profile: AuthorizationEvaluationProfileV1 | None = None,
) -> CompiledEnterpriseAccessStateV1:
    selected_abac = (
        reference.abac_truth
        if abac_truth is _UNSET
        else cast(CompiledEnterpriseAbacTruthV1 | None, abac_truth)
    )
    selected_rebac = (
        reference.rebac_truth
        if rebac_truth is _UNSET
        else cast(CompiledEnterpriseRebacTruthV1 | None, rebac_truth)
    )
    return compile_enterprise_access_state(
        universe=universe or reference.rbac.universe_result.public_universe,
        canonical_binding_truth=(
            binding or reference.rbac.universe_result.evaluator_canonical_binding_truth
        ),
        corpus=corpus or reference.rbac.corpus_result.public_corpus,
        composition=composition or reference.composition,
        directory_rbac_truth=(directory_rbac_truth or reference.directory_rbac_truth),
        abac_truth=selected_abac,
        rebac_truth=selected_rebac,
        evaluation_profile=evaluation_profile or reference.evaluation_profile,
    )


def test_reference_aggregate_covers_closed_profiles_and_raw_truth() -> None:
    reference = reference_enterprise_authorization_inputs()
    second = _compile(reference)
    assert canonical_json_bytes(second) == canonical_json_bytes(reference.access_state)
    assert {item.profile for item in second.cells} == set(
        AuthorizationEvaluationProfileKind
    )
    assert tuple(item.cell_id for item in second.cells) == tuple(
        item.cell_id
        for item in reference.rbac.corpus_result.public_corpus.evaluation_cells
    )
    assert all(
        item.actual_mechanism_outcomes.model_dump(exclude_none=True)
        for item in second.cells
    )
    assert any(item.actual_conflict for item in second.policy_conflicts)
    conflict = next(item for item in second.policy_conflicts if item.actual_conflict)
    assert conflict.actual_allowing_mechanisms
    assert conflict.actual_denying_mechanisms
    unsafe = tuple(
        item
        for item in second.cells
        if item.binding_status.value not in {"not_applicable", "matches_canonical"}
        or item.lifecycle_status.value not in {"not_applicable", "active"}
    )
    assert unsafe
    assert all(item.final_decision is AuthorizationDecision.DENY for item in unsafe)


def test_pr3_frozen_reference_bytes_remain_unchanged_after_pr4_installation() -> None:
    reference = reference_enterprise_authorization_inputs()
    artifacts = {
        "universe": reference.rbac.universe_result.public_universe,
        "corpus": reference.rbac.corpus_result.public_corpus,
        "intent": reference.rbac.intent,
        "truth": reference.directory_rbac_truth,
    }
    expected = {
        "universe": "b4eae423689ede98d98858cae004f98d07fa5b0ac4774858500a4ba257946f4a",
        "corpus": "1293dc2a22820f1e0b72f85c7c17028872c424b7483223f50b6f4dd822acf1d6",
        "intent": "83150b91a9acafd6a457b4240ee3088ee25e21e50fca25342ba49f51dd4b7a10",
        "truth": "e1c055ed5b322136fae17f91633416746a5af164a54388017f8cfc37a94bfdbb",
    }
    assert {
        name: synthetic_digest(canonical_json_bytes(model)).value
        for name, model in artifacts.items()
    } == expected


def test_composition_contains_only_fixed_typed_references_not_inline_payloads() -> None:
    reference = reference_enterprise_authorization_inputs()
    document = reference.composition.model_dump(mode="json")
    assert set(document) == {
        "synthetic",
        "schema_version",
        "identity_access_universe_digest",
        "evaluation_corpus_digest",
        "directory_rbac",
        "abac",
        "rebac",
    }
    serialized = canonical_json_bytes(reference.composition)
    for forbidden in (
        b'"cells"',
        b'"relation_tuples"',
        b'"predicate_truth"',
        b'"final_decision"',
    ):
        assert forbidden not in serialized


def test_composition_rejects_cross_universe_and_cross_corpus_components() -> None:
    reference = reference_enterprise_authorization_inputs()
    changed_abac = reference.abac_truth.model_copy(
        update={"identity_access_universe_digest": synthetic_digest(b"changed\n")}
    )
    with pytest.raises(EnterpriseCompileError, match="composition_abac_universe"):
        compose_enterprise_authorization(
            directory_rbac_truth=reference.directory_rbac_truth,
            abac_truth=changed_abac,
        )
    changed_rebac = reference.rebac_truth.model_copy(
        update={"evaluation_corpus_digest": synthetic_digest(b"changed\n")}
    )
    with pytest.raises(EnterpriseCompileError, match="composition_rebac_corpus"):
        compose_enterprise_authorization(
            directory_rbac_truth=reference.directory_rbac_truth,
            rebac_truth=changed_rebac,
        )


def test_aggregate_requires_exactly_the_referenced_explicit_payloads() -> None:
    reference = reference_enterprise_authorization_inputs()
    with pytest.raises(EnterpriseCompileError, match="missing_abac_payload"):
        _compile(reference, abac_truth=None)
    with pytest.raises(EnterpriseCompileError, match="missing_rebac_payload"):
        _compile(reference, rebac_truth=None)

    rbac_only = compose_enterprise_authorization(
        directory_rbac_truth=reference.directory_rbac_truth
    )
    rbac_profile = AuthorizationEvaluationProfileV1(
        evaluation_corpus_digest=synthetic_digest(
            canonical_json_bytes(reference.rbac.corpus_result.public_corpus)
        ),
        cells=tuple(
            AuthorizationCellProfileV1(
                cell_id=item.cell_id,
                profile=AuthorizationEvaluationProfileKind.RBAC,
            )
            for item in reference.rbac.corpus_result.public_corpus.evaluation_cells
        ),
    )
    with pytest.raises(EnterpriseCompileError, match="extra_abac_payload"):
        _compile(
            reference,
            composition=rbac_only,
            evaluation_profile=rbac_profile,
            rebac_truth=None,
        )
    with pytest.raises(EnterpriseCompileError, match="extra_rebac_payload"):
        _compile(
            reference,
            composition=rbac_only,
            evaluation_profile=rbac_profile,
            abac_truth=None,
        )

    result = _compile(
        reference,
        composition=rbac_only,
        evaluation_profile=rbac_profile,
        abac_truth=None,
        rebac_truth=None,
    )
    assert all(
        item.profile is AuthorizationEvaluationProfileKind.RBAC for item in result.cells
    )


@pytest.mark.parametrize(
    ("binding_update", "rbac_update", "match"),
    (
        (
            {"identity_access_universe_digest": synthetic_digest(b"changed\n")},
            {},
            "aggregate_binding_universe_digest_mismatch",
        ),
        (
            {},
            {"identity_access_universe_digest": synthetic_digest(b"changed\n")},
            "aggregate_rbac_universe_digest_mismatch",
        ),
        (
            {},
            {"canonical_binding_truth_digest": synthetic_digest(b"changed\n")},
            "aggregate_rbac_binding_digest_mismatch",
        ),
        (
            {},
            {"evaluation_corpus_digest": synthetic_digest(b"changed\n")},
            "aggregate_rbac_corpus_digest_mismatch",
        ),
    ),
)
def test_aggregate_rejects_stale_rbac_and_binding_inputs(
    binding_update: dict[str, object],
    rbac_update: dict[str, object],
    match: str,
) -> None:
    reference = reference_enterprise_authorization_inputs()
    with pytest.raises(EnterpriseCompileError, match=match):
        _compile(
            reference,
            binding=reference.rbac.universe_result.evaluator_canonical_binding_truth.model_copy(
                update=binding_update
            ),
            directory_rbac_truth=reference.directory_rbac_truth.model_copy(
                update=rbac_update
            ),
        )


def test_stale_digest_and_schema_version_references_fail_closed() -> None:
    reference = reference_enterprise_authorization_inputs()
    changed_truth = reference.abac_truth.model_copy(
        update={"cells": reference.abac_truth.cells[:-1]}
    )
    with pytest.raises(EnterpriseCompileError, match="abac_payload_digest_mismatch"):
        _compile(reference, abac_truth=changed_truth)

    wrong_abac_reference = reference.composition.abac
    assert wrong_abac_reference is not None
    wrong_abac_reference = wrong_abac_reference.model_copy(
        update={"component_schema_version": "9.0.0"}
    )
    with pytest.raises(
        EnterpriseCompileError, match="abac_payload_schema_version_mismatch"
    ):
        _compile(
            reference,
            composition=reference.composition.model_copy(
                update={"abac": wrong_abac_reference}
            ),
        )
    wrong_rbac_reference = reference.composition.directory_rbac.model_copy(
        update={"component_schema_version": "9.0.0"}
    )
    with pytest.raises(
        EnterpriseCompileError, match="directory_rbac_payload_schema_version"
    ):
        _compile(
            reference,
            composition=reference.composition.model_copy(
                update={"directory_rbac": wrong_rbac_reference}
            ),
        )


def test_authorization_profile_must_bind_and_cover_the_frozen_corpus() -> None:
    reference = reference_enterprise_authorization_inputs()
    profile = reference.evaluation_profile.model_copy(
        update={"evaluation_corpus_digest": synthetic_digest(b"changed\n")}
    )
    with pytest.raises(EnterpriseCompileError, match="profile_corpus_digest"):
        _compile(reference, evaluation_profile=profile)
    profile = reference.evaluation_profile.model_copy(
        update={"cells": reference.evaluation_profile.cells[:-1]}
    )
    with pytest.raises(EnterpriseCompileError, match="profile_cell_inventory"):
        _compile(reference, evaluation_profile=profile)
    with pytest.raises(
        ValidationError, match="duplicate_authorization_profile_cell_id"
    ):
        AuthorizationEvaluationProfileV1(
            evaluation_corpus_digest=reference.evaluation_profile.evaluation_corpus_digest,
            cells=(
                reference.evaluation_profile.cells[0],
                reference.evaluation_profile.cells[0],
            ),
        )

    rbac_only = compose_enterprise_authorization(
        directory_rbac_truth=reference.directory_rbac_truth
    )
    with pytest.raises(EnterpriseCompileError, match="requires_abac"):
        compile_enterprise_authorization_kernel(
            universe=reference.rbac.universe_result.public_universe,
            corpus=reference.rbac.corpus_result.public_corpus,
            composition=rbac_only,
            evaluation_profile=reference.evaluation_profile,
        )
    rebac_profile = reference.evaluation_profile.model_copy(
        update={
            "cells": tuple(
                item.model_copy(
                    update={"profile": AuthorizationEvaluationProfileKind.REBAC}
                )
                for item in reference.evaluation_profile.cells
            )
        }
    )
    composition_without_rebac = compose_enterprise_authorization(
        directory_rbac_truth=reference.directory_rbac_truth,
        abac_truth=reference.abac_truth,
    )
    with pytest.raises(EnterpriseCompileError, match="requires_rebac"):
        compile_enterprise_authorization_kernel(
            universe=reference.rbac.universe_result.public_universe,
            corpus=reference.rbac.corpus_result.public_corpus,
            composition=composition_without_rebac,
            evaluation_profile=rebac_profile,
        )


def test_component_cell_inventory_and_binding_mismatches_fail_closed() -> None:
    reference = reference_enterprise_authorization_inputs()
    changed_rbac = reference.directory_rbac_truth.model_copy(
        update={"cells": reference.directory_rbac_truth.cells[:-1]}
    )
    composition = compose_enterprise_authorization(
        directory_rbac_truth=changed_rbac,
        abac_truth=reference.abac_truth.model_copy(
            update={
                "identity_access_universe_digest": (
                    changed_rbac.identity_access_universe_digest
                )
            }
        ),
        rebac_truth=reference.rebac_truth,
    )
    with pytest.raises(
        EnterpriseCompileError, match="directory_rbac_cell_inventory_mismatch"
    ):
        _compile(
            reference,
            composition=composition,
            directory_rbac_truth=changed_rbac,
            abac_truth=reference.abac_truth,
        )

    changed_abac = reference.abac_truth.model_copy(
        update={"cells": reference.abac_truth.cells[:-1]}
    )
    composition = compose_enterprise_authorization(
        directory_rbac_truth=reference.directory_rbac_truth,
        abac_truth=changed_abac,
        rebac_truth=reference.rebac_truth,
    )
    with pytest.raises(EnterpriseCompileError, match="abac_cell_inventory_mismatch"):
        _compile(reference, composition=composition, abac_truth=changed_abac)

    changed_rebac = reference.rebac_truth.model_copy(
        update={"cells": reference.rebac_truth.cells[:-1]}
    )
    composition = compose_enterprise_authorization(
        directory_rbac_truth=reference.directory_rbac_truth,
        abac_truth=reference.abac_truth,
        rebac_truth=changed_rebac,
    )
    with pytest.raises(EnterpriseCompileError, match="rebac_cell_inventory_mismatch"):
        _compile(reference, composition=composition, rebac_truth=changed_rebac)


def test_aggregate_truth_models_reject_invalid_internal_states() -> None:
    with pytest.raises(ValidationError, match="mechanism_outcome_set_empty"):
        MechanismOutcomeSetV1()
    with pytest.raises(ValidationError, match="policy_conflict_flag_mismatch"):
        PolicyConflictTruthV1(
            conflict_id="conflict",
            cell_id="cell",
            actual_conflict=True,
            intended_conflict=False,
            actual_allowing_mechanisms=("abac",),
            actual_denying_mechanisms=(),
            intended_allowing_mechanisms=(),
            intended_denying_mechanisms=(),
        )
    with pytest.raises(ValidationError, match="duplicate_actual_allowing_mechanisms"):
        PolicyConflictTruthV1(
            conflict_id="conflict",
            cell_id="cell",
            actual_conflict=True,
            intended_conflict=False,
            actual_allowing_mechanisms=("abac", "abac"),
            actual_denying_mechanisms=("rebac",),
            intended_allowing_mechanisms=(),
            intended_denying_mechanisms=(),
        )


def test_authorization_artifacts_are_canonical_and_physically_split(
    tmp_path: Path,
) -> None:
    reference = reference_enterprise_authorization_inputs()
    root = tmp_path / "authorization"
    export_enterprise_authorization(
        root, public=_public(reference), evaluator=_evaluator(reference)
    )
    assert load_public_enterprise_authorization(root) == _public(reference)
    assert load_evaluator_enterprise_authorization(root) == _evaluator(reference)

    def object_keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | set().union(
                *(object_keys(item) for item in value.values())
            )
        if isinstance(value, list):
            return set().union(*(object_keys(item) for item in value))
        return set()

    public_files = sorted((root / "public").glob("*.json"))
    public_bytes = b"".join(item.read_bytes() for item in public_files)
    public_keys = set().union(
        *(object_keys(json.loads(item.read_bytes())) for item in public_files)
    )
    for forbidden in (
        "actual_outcome",
        "intended_outcome",
        "final_decision",
        "policy_conflicts",
        "predicate_truth",
    ):
        assert forbidden not in public_keys
    assert b'"component_digest"' in public_bytes
    with pytest.raises(EnterpriseAuthorizationArtifactError, match="already exists"):
        export_enterprise_authorization(
            root, public=_public(reference), evaluator=_evaluator(reference)
        )


def test_authorization_loaders_reject_inventory_canonicality_and_manifest_tampering(
    tmp_path: Path,
) -> None:
    reference = reference_enterprise_authorization_inputs()

    extra_root = tmp_path / "extra"
    export_enterprise_authorization(
        extra_root, public=_public(reference), evaluator=_evaluator(reference)
    )
    (extra_root / "public" / "extra.json").write_text("{}\n")
    with pytest.raises(EnterpriseAuthorizationArtifactError, match="inventory"):
        load_public_enterprise_authorization(extra_root)

    noncanonical_root = tmp_path / "noncanonical"
    export_enterprise_authorization(
        noncanonical_root, public=_public(reference), evaluator=_evaluator(reference)
    )
    path = noncanonical_root / "public" / "abac-state.json"
    path.write_text(json.dumps(reference.abac_state.model_dump(mode="json")) + "\n")
    with pytest.raises(EnterpriseAuthorizationArtifactError, match="not canonical"):
        load_public_enterprise_authorization(noncanonical_root)

    manifest_root = tmp_path / "manifest"
    export_enterprise_authorization(
        manifest_root, public=_public(reference), evaluator=_evaluator(reference)
    )
    manifest_path = manifest_root / "public" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["artifacts"][0]["byte_size"] += 1
    manifest_path.write_bytes(canonical_json_value_bytes(manifest))
    with pytest.raises(EnterpriseAuthorizationArtifactError, match="descriptor"):
        load_public_enterprise_authorization(manifest_root)

    visibility_root = tmp_path / "visibility"
    export_enterprise_authorization(
        visibility_root, public=_public(reference), evaluator=_evaluator(reference)
    )
    manifest_path = visibility_root / "public" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["visibility"] = "evaluator"
    manifest_path.write_bytes(canonical_json_value_bytes(manifest))
    with pytest.raises(EnterpriseAuthorizationArtifactError, match="visibility"):
        load_public_enterprise_authorization(visibility_root)

    inventory_root = tmp_path / "manifest-inventory"
    export_enterprise_authorization(
        inventory_root, public=_public(reference), evaluator=_evaluator(reference)
    )
    manifest_path = inventory_root / "public" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["artifacts"] = manifest["artifacts"][:-1]
    manifest_path.write_bytes(canonical_json_value_bytes(manifest))
    with pytest.raises(
        EnterpriseAuthorizationArtifactError, match="manifest inventory"
    ):
        load_public_enterprise_authorization(inventory_root)

    invalid_root = tmp_path / "invalid"
    export_enterprise_authorization(
        invalid_root, public=_public(reference), evaluator=_evaluator(reference)
    )
    (invalid_root / "public" / "abac-state.json").write_bytes(b"{\n")
    with pytest.raises(
        EnterpriseAuthorizationArtifactError, match="artifact is invalid"
    ):
        load_public_enterprise_authorization(invalid_root)


def test_authorization_loader_rejects_cross_tree_binding_drift(tmp_path: Path) -> None:
    reference = reference_enterprise_authorization_inputs()
    root = tmp_path / "binding-drift"
    changed_truth = reference.abac_truth.model_copy(
        update={"cells": reference.abac_truth.cells[:-1]}
    )
    export_enterprise_authorization(
        root,
        public=_public(reference),
        evaluator=EnterpriseAuthorizationEvaluatorArtifactsV1(
            abac_truth=changed_truth,
            rebac_truth=reference.rebac_truth,
            access_state=reference.access_state,
        ),
    )
    with pytest.raises(EnterpriseAuthorizationArtifactError, match="evaluator/public"):
        load_evaluator_enterprise_authorization(root)


def test_authorization_public_bindings_and_loader_shapes_fail_closed(
    tmp_path: Path,
) -> None:
    reference = reference_enterprise_authorization_inputs()
    public = _public(reference)
    with pytest.raises(
        EnterpriseAuthorizationArtifactError, match="public artifact bindings"
    ):
        _validate_public_bindings(
            EnterpriseAuthorizationPublicArtifactsV1(
                abac_state=public.abac_state.model_copy(
                    update={
                        "identity_access_universe_digest": synthetic_digest(
                            b"changed\n"
                        )
                    }
                ),
                abac_intent=public.abac_intent,
                rebac_state=public.rebac_state,
                rebac_intent=public.rebac_intent,
                composition=public.composition,
                evaluation_scope=public.evaluation_scope,
                kernel=public.kernel,
            )
        )
    with pytest.raises(
        EnterpriseAuthorizationArtifactError, match="kernel composition"
    ):
        _validate_public_bindings(
            EnterpriseAuthorizationPublicArtifactsV1(
                abac_state=public.abac_state,
                abac_intent=public.abac_intent,
                rebac_state=public.rebac_state,
                rebac_intent=public.rebac_intent,
                composition=public.composition,
                evaluation_scope=public.evaluation_scope,
                kernel=public.kernel.model_copy(
                    update={"composition_digest": synthetic_digest(b"changed\n")}
                ),
            )
        )

    with pytest.raises(EnterpriseAuthorizationArtifactError, match="scope kernel"):
        _validate_public_bindings(
            EnterpriseAuthorizationPublicArtifactsV1(
                abac_state=public.abac_state,
                abac_intent=public.abac_intent,
                rebac_state=public.rebac_state,
                rebac_intent=public.rebac_intent,
                composition=public.composition,
                evaluation_scope=public.evaluation_scope.model_copy(
                    update={
                        "authorization_kernel_digest": synthetic_digest(b"changed\n")
                    }
                ),
                kernel=public.kernel,
            )
        )

    with pytest.raises(
        EnterpriseAuthorizationArtifactError, match="scope cell inventory"
    ):
        _validate_public_bindings(
            EnterpriseAuthorizationPublicArtifactsV1(
                abac_state=public.abac_state,
                abac_intent=public.abac_intent,
                rebac_state=public.rebac_state,
                rebac_intent=public.rebac_intent,
                composition=public.composition,
                evaluation_scope=public.evaluation_scope.model_copy(
                    update={"cells": public.evaluation_scope.cells[:-1]}
                ),
                kernel=public.kernel,
            )
        )

    regular = tmp_path / "regular"
    regular.write_text("not a directory\n")
    with pytest.raises(
        EnterpriseAuthorizationArtifactError, match="not a real directory"
    ):
        _require_exact_files(regular, set())
    with pytest.raises(EnterpriseAuthorizationArtifactError, match="unreadable"):
        _require_exact_files(tmp_path / "absent", set())
    nonregular = tmp_path / "nonregular"
    nonregular.mkdir()
    (nonregular / "entry").mkdir()
    with pytest.raises(EnterpriseAuthorizationArtifactError, match="non-regular"):
        _require_exact_files(nonregular, {"entry"})
    with pytest.raises(EnterpriseAuthorizationArtifactError, match="type mismatch"):
        _as(reference.abac_state, CompiledEnterpriseAbacTruthV1)


def test_kernel_rejects_composition_universe_and_corpus_mismatch() -> None:
    reference = reference_enterprise_authorization_inputs()
    with pytest.raises(EnterpriseCompileError, match="kernel_universe_digest"):
        compile_enterprise_authorization_kernel(
            universe=reference.rbac.universe_result.public_universe,
            corpus=reference.rbac.corpus_result.public_corpus,
            composition=reference.composition.model_copy(
                update={
                    "identity_access_universe_digest": synthetic_digest(b"changed\n")
                }
            ),
            evaluation_profile=reference.evaluation_profile,
        )
    with pytest.raises(EnterpriseCompileError, match="kernel_corpus_digest"):
        compile_enterprise_authorization_kernel(
            universe=reference.rbac.universe_result.public_universe,
            corpus=reference.rbac.corpus_result.public_corpus,
            composition=reference.composition.model_copy(
                update={"evaluation_corpus_digest": synthetic_digest(b"changed\n")}
            ),
            evaluation_profile=reference.evaluation_profile,
        )


def test_raw_unknown_and_not_applicable_both_default_deny_without_collapsing() -> None:
    reference = reference_enterprise_authorization_inputs()
    rows = tuple(
        item
        for item in reference.access_state.cells
        if item.profile is AuthorizationEvaluationProfileKind.ABAC
        and item.actual_mechanism_outcomes.abac
        in {MechanismOutcome.UNKNOWN, MechanismOutcome.NOT_APPLICABLE}
    )
    assert rows
    assert all(item.effective_decision is AuthorizationDecision.DENY for item in rows)
    assert {item.actual_mechanism_outcomes.abac for item in rows} <= {
        MechanismOutcome.UNKNOWN,
        MechanismOutcome.NOT_APPLICABLE,
    }
