"""Exact component composition and closed aggregate authorization algebra."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from uuid import UUID, uuid5

from synthworld.enterprise.abac.models import (
    AbacCellTruthV1,
    CompiledEnterpriseAbacTruthV1,
)
from synthworld.enterprise.authorization.models import (
    AbacComponentReferenceV1,
    AuthorizationEvaluationProfileV1,
    AuthorizationKernelCellV1,
    CompiledEnterpriseAccessCellV1,
    CompiledEnterpriseAccessStateV1,
    DirectoryRbacComponentReferenceV1,
    EnterpriseAuthorizationCompositionV1,
    EnterpriseAuthorizationKernelV1,
    MechanismOutcomeSetV1,
    PolicyConflictTruthV1,
    RebacComponentReferenceV1,
)
from synthworld.enterprise.authorization_common import (
    AuthorizationEvaluationProfileKind,
    MechanismOutcome,
)
from synthworld.enterprise.canonical import (
    canonical_json_bytes,
    encode_parts,
    synthetic_digest,
)
from synthworld.enterprise.compiler import EnterpriseCompileError
from synthworld.enterprise.models import (
    EnterpriseCanonicalBindingTruthV1,
    EnterpriseIdentityAccessUniverseV1,
    SyntheticDigestV1,
)
from synthworld.enterprise.rbac.common import (
    AuthorizationDecision,
    BindingStatus,
    LifecycleStatus,
    ReconciliationOutcome,
)
from synthworld.enterprise.rbac.corpus_models import EnterpriseEvaluationCorpusV1
from synthworld.enterprise.rbac.models import (
    CompiledEnterpriseDirectoryRbacTruthV1,
    DirectoryRbacCellTruthV1,
)
from synthworld.enterprise.rebac.models import (
    CompiledEnterpriseRebacTruthV1,
    RebacCellTruthV1,
)

ENTERPRISE_AUTHORIZATION_TRUTH_RECORD_NAMESPACE_V1 = UUID(
    "bdce70b5-a955-505e-a63c-aee7cc5e187a"
)


@dataclass(frozen=True, slots=True)
class _ConflictSets:
    allowing: tuple[str, ...]
    denying: tuple[str, ...]

    @property
    def conflict(self) -> bool:
        return bool(self.allowing and self.denying)


def compose_enterprise_authorization(
    *,
    directory_rbac_truth: CompiledEnterpriseDirectoryRbacTruthV1,
    abac_truth: CompiledEnterpriseAbacTruthV1 | None = None,
    rebac_truth: CompiledEnterpriseRebacTruthV1 | None = None,
) -> EnterpriseAuthorizationCompositionV1:
    """Create fixed typed digest references; never retain inline payloads."""

    for label, component in (("abac", abac_truth), ("rebac", rebac_truth)):
        if component is None:
            continue
        if (
            component.identity_access_universe_digest
            != directory_rbac_truth.identity_access_universe_digest
        ):
            raise EnterpriseCompileError(
                f"composition_{label}_universe_digest_mismatch",
                f"{label.upper()} truth does not bind the RBAC universe",
            )
        if (
            component.evaluation_corpus_digest
            != directory_rbac_truth.evaluation_corpus_digest
        ):
            raise EnterpriseCompileError(
                f"composition_{label}_corpus_digest_mismatch",
                f"{label.upper()} truth does not bind the RBAC corpus",
            )
    return EnterpriseAuthorizationCompositionV1(
        identity_access_universe_digest=(
            directory_rbac_truth.identity_access_universe_digest
        ),
        evaluation_corpus_digest=directory_rbac_truth.evaluation_corpus_digest,
        directory_rbac=DirectoryRbacComponentReferenceV1(
            component_digest=synthetic_digest(
                canonical_json_bytes(directory_rbac_truth)
            )
        ),
        abac=(
            AbacComponentReferenceV1(
                component_digest=synthetic_digest(canonical_json_bytes(abac_truth))
            )
            if abac_truth is not None
            else None
        ),
        rebac=(
            RebacComponentReferenceV1(
                component_digest=synthetic_digest(canonical_json_bytes(rebac_truth))
            )
            if rebac_truth is not None
            else None
        ),
    )


def compile_enterprise_authorization_kernel(
    *,
    universe: EnterpriseIdentityAccessUniverseV1,
    corpus: EnterpriseEvaluationCorpusV1,
    composition: EnterpriseAuthorizationCompositionV1,
    evaluation_profile: AuthorizationEvaluationProfileV1,
) -> EnterpriseAuthorizationKernelV1:
    """Bind one closed evaluation profile to every existing corpus cell."""

    universe_digest = synthetic_digest(canonical_json_bytes(universe))
    corpus_digest = synthetic_digest(canonical_json_bytes(corpus))
    if composition.identity_access_universe_digest != universe_digest:
        raise EnterpriseCompileError(
            "authorization_kernel_universe_digest_mismatch",
            "composition does not bind the supplied universe",
        )
    if composition.evaluation_corpus_digest != corpus_digest:
        raise EnterpriseCompileError(
            "authorization_kernel_corpus_digest_mismatch",
            "composition does not bind the supplied corpus",
        )
    if evaluation_profile.evaluation_corpus_digest != corpus_digest:
        raise EnterpriseCompileError(
            "authorization_profile_corpus_digest_mismatch",
            "evaluation profile does not bind the supplied corpus",
        )
    expected_cell_ids = {item.cell_id for item in corpus.evaluation_cells}
    profile_cell_ids = {item.cell_id for item in evaluation_profile.cells}
    if profile_cell_ids != expected_cell_ids:
        raise EnterpriseCompileError(
            "authorization_profile_cell_inventory_mismatch",
            "evaluation profile must cover every frozen cell exactly once",
        )
    for item in evaluation_profile.cells:
        _require_profile_components(item.profile, composition)
    return EnterpriseAuthorizationKernelV1(
        identity_access_universe_digest=universe_digest,
        evaluation_corpus_digest=corpus_digest,
        composition_digest=synthetic_digest(canonical_json_bytes(composition)),
        evaluation_profile_digest=synthetic_digest(
            canonical_json_bytes(evaluation_profile)
        ),
        cells=tuple(
            AuthorizationKernelCellV1(cell_id=item.cell_id, profile=item.profile)
            for item in evaluation_profile.cells
        ),
    )


def compile_enterprise_access_state(
    *,
    universe: EnterpriseIdentityAccessUniverseV1,
    canonical_binding_truth: EnterpriseCanonicalBindingTruthV1,
    corpus: EnterpriseEvaluationCorpusV1,
    composition: EnterpriseAuthorizationCompositionV1,
    directory_rbac_truth: CompiledEnterpriseDirectoryRbacTruthV1,
    evaluation_profile: AuthorizationEvaluationProfileV1,
    abac_truth: CompiledEnterpriseAbacTruthV1 | None = None,
    rebac_truth: CompiledEnterpriseRebacTruthV1 | None = None,
) -> CompiledEnterpriseAccessStateV1:
    """Verify explicit payloads and compile immutable aggregate B/I/E/F truth."""

    kernel = compile_enterprise_authorization_kernel(
        universe=universe,
        corpus=corpus,
        composition=composition,
        evaluation_profile=evaluation_profile,
    )
    digests = _verify_payloads(
        universe,
        canonical_binding_truth,
        corpus,
        composition,
        directory_rbac_truth,
        abac_truth,
        rebac_truth,
    )
    rbac_cells = {item.cell_id: item for item in directory_rbac_truth.cells}
    abac_cells = (
        {item.cell_id: item for item in abac_truth.cells}
        if abac_truth is not None
        else {}
    )
    rebac_cells = (
        {item.cell_id: item for item in rebac_truth.cells}
        if rebac_truth is not None
        else {}
    )
    expected_cells = {item.cell_id for item in corpus.evaluation_cells}
    _require_component_cells("directory_rbac", set(rbac_cells), expected_cells)
    if abac_truth is not None:
        _require_component_cells("abac", set(abac_cells), expected_cells)
    if rebac_truth is not None:
        _require_component_cells("rebac", set(rebac_cells), expected_cells)
    profile_by_cell = {item.cell_id: item.profile for item in kernel.cells}
    cells: list[CompiledEnterpriseAccessCellV1] = []
    conflicts: list[PolicyConflictTruthV1] = []
    composition_digest = synthetic_digest(canonical_json_bytes(composition))
    for cell_id in sorted(expected_cells):
        profile = profile_by_cell[cell_id]
        rbac = rbac_cells[cell_id]
        actual_outcomes, intended_outcomes = _profile_outcomes(
            profile, rbac, abac_cells.get(cell_id), rebac_cells.get(cell_id)
        )
        actual_conflicts = _conflict_sets(
            actual_outcomes,
            abac_internal=(
                abac_cells[cell_id].actual_conflict if cell_id in abac_cells else False
            ),
            rebac_internal=(
                rebac_cells[cell_id].actual_conflict
                if cell_id in rebac_cells
                else False
            ),
        )
        intended_conflicts = _conflict_sets(
            intended_outcomes,
            abac_internal=(
                abac_cells[cell_id].intended_conflict
                if cell_id in abac_cells
                else False
            ),
            rebac_internal=(
                rebac_cells[cell_id].intended_conflict
                if cell_id in rebac_cells
                else False
            ),
        )
        intended = _normalize(profile, intended_outcomes)
        effective = _normalize(profile, actual_outcomes)
        final = effective if _runtime_gates_pass(rbac) else AuthorizationDecision.DENY
        conflict_id = _truth_id(composition_digest.value, "conflict", cell_id)
        conflicts.append(
            PolicyConflictTruthV1(
                conflict_id=conflict_id,
                cell_id=cell_id,
                actual_conflict=actual_conflicts.conflict,
                intended_conflict=intended_conflicts.conflict,
                actual_allowing_mechanisms=actual_conflicts.allowing,
                actual_denying_mechanisms=actual_conflicts.denying,
                intended_allowing_mechanisms=intended_conflicts.allowing,
                intended_denying_mechanisms=intended_conflicts.denying,
            )
        )
        cells.append(
            CompiledEnterpriseAccessCellV1(
                cell_id=cell_id,
                profile=profile,
                actual_mechanism_outcomes=actual_outcomes,
                intended_mechanism_outcomes=intended_outcomes,
                intended_decision=intended,
                effective_decision=effective,
                final_decision=final,
                reconciliation=_reconciliation(intended, effective),
                binding_status=rbac.binding_status,
                lifecycle_status=rbac.lifecycle_status,
                policy_conflict_id=conflict_id,
                directory_rbac_cell_id=cell_id,
                abac_cell_id=cell_id if cell_id in abac_cells else None,
                rebac_cell_id=cell_id if cell_id in rebac_cells else None,
            )
        )
    return CompiledEnterpriseAccessStateV1(
        identity_access_universe_digest=digests.universe,
        canonical_binding_truth_digest=digests.binding,
        evaluation_corpus_digest=digests.corpus,
        composition_digest=composition_digest,
        authorization_kernel_digest=synthetic_digest(canonical_json_bytes(kernel)),
        directory_rbac_truth_digest=digests.rbac,
        abac_truth_digest=digests.abac,
        rebac_truth_digest=digests.rebac,
        policy_conflicts=tuple(conflicts),
        cells=tuple(cells),
    )


@dataclass(frozen=True, slots=True)
class _PayloadDigests:
    universe: SyntheticDigestV1
    binding: SyntheticDigestV1
    corpus: SyntheticDigestV1
    rbac: SyntheticDigestV1
    abac: SyntheticDigestV1 | None
    rebac: SyntheticDigestV1 | None


def _verify_payloads(
    universe: EnterpriseIdentityAccessUniverseV1,
    binding: EnterpriseCanonicalBindingTruthV1,
    corpus: EnterpriseEvaluationCorpusV1,
    composition: EnterpriseAuthorizationCompositionV1,
    rbac: CompiledEnterpriseDirectoryRbacTruthV1,
    abac: CompiledEnterpriseAbacTruthV1 | None,
    rebac: CompiledEnterpriseRebacTruthV1 | None,
) -> _PayloadDigests:
    digests = _PayloadDigests(
        universe=synthetic_digest(canonical_json_bytes(universe)),
        binding=synthetic_digest(canonical_json_bytes(binding)),
        corpus=synthetic_digest(canonical_json_bytes(corpus)),
        rbac=synthetic_digest(canonical_json_bytes(rbac)),
        abac=synthetic_digest(canonical_json_bytes(abac)) if abac else None,
        rebac=synthetic_digest(canonical_json_bytes(rebac)) if rebac else None,
    )
    if binding.identity_access_universe_digest != digests.universe:
        raise EnterpriseCompileError(
            "aggregate_binding_universe_digest_mismatch",
            "canonical binding truth does not bind the supplied universe",
        )
    if rbac.identity_access_universe_digest != digests.universe:
        raise EnterpriseCompileError(
            "aggregate_rbac_universe_digest_mismatch",
            "RBAC truth does not bind the supplied universe",
        )
    if rbac.canonical_binding_truth_digest != digests.binding:
        raise EnterpriseCompileError(
            "aggregate_rbac_binding_digest_mismatch",
            "RBAC truth does not bind the supplied canonical binding truth",
        )
    if rbac.evaluation_corpus_digest != digests.corpus:
        raise EnterpriseCompileError(
            "aggregate_rbac_corpus_digest_mismatch",
            "RBAC truth does not bind the supplied corpus",
        )
    _require_component_version(
        "directory_rbac",
        composition.directory_rbac.component_schema_version,
        rbac.schema_version,
    )
    _require_reference(
        "directory_rbac", composition.directory_rbac.component_digest, digests.rbac
    )
    _verify_optional_reference("abac", composition.abac, abac, digests.abac)
    _verify_optional_reference("rebac", composition.rebac, rebac, digests.rebac)
    return digests


def _verify_optional_reference(
    family: str,
    reference: AbacComponentReferenceV1 | RebacComponentReferenceV1 | None,
    payload: CompiledEnterpriseAbacTruthV1 | CompiledEnterpriseRebacTruthV1 | None,
    digest: SyntheticDigestV1 | None,
) -> None:
    if reference is None and payload is not None:
        raise EnterpriseCompileError(
            f"aggregate_extra_{family}_payload",
            f"{family.upper()} payload was supplied without a composition reference",
        )
    if reference is not None and payload is None:
        raise EnterpriseCompileError(
            f"aggregate_missing_{family}_payload",
            f"composition requires an explicitly supplied {family.upper()} payload",
        )
    if reference is not None and payload is not None and digest is not None:
        _require_component_version(
            family, reference.component_schema_version, payload.schema_version
        )
        _require_reference(family, reference.component_digest, digest)


def _require_component_version(family: str, expected: str, actual: str) -> None:
    if expected != actual:
        raise EnterpriseCompileError(
            f"aggregate_{family}_payload_schema_version_mismatch",
            f"supplied {family} payload does not match its composition version",
        )


def _require_reference(
    family: str, expected: SyntheticDigestV1, actual: SyntheticDigestV1
) -> None:
    if expected != actual:
        raise EnterpriseCompileError(
            f"aggregate_{family}_payload_digest_mismatch",
            f"supplied {family} payload does not match its composition digest",
        )


def _require_profile_components(
    profile: AuthorizationEvaluationProfileKind,
    composition: EnterpriseAuthorizationCompositionV1,
) -> None:
    needs_abac = profile in {
        AuthorizationEvaluationProfileKind.ABAC,
        AuthorizationEvaluationProfileKind.RBAC_WITH_ABAC_GUARD,
        AuthorizationEvaluationProfileKind.REBAC_WITH_ABAC_GUARD,
    }
    needs_rebac = profile in {
        AuthorizationEvaluationProfileKind.REBAC,
        AuthorizationEvaluationProfileKind.REBAC_WITH_ABAC_GUARD,
    }
    if needs_abac and composition.abac is None:
        raise EnterpriseCompileError(
            "authorization_profile_requires_abac",
            "selected evaluation profile requires an ABAC component",
        )
    if needs_rebac and composition.rebac is None:
        raise EnterpriseCompileError(
            "authorization_profile_requires_rebac",
            "selected evaluation profile requires a ReBAC component",
        )


def _require_component_cells(family: str, actual: set[str], expected: set[str]) -> None:
    if actual != expected:
        raise EnterpriseCompileError(
            f"aggregate_{family}_cell_inventory_mismatch",
            f"{family} truth must contain exactly one row for every frozen cell",
        )


def _profile_outcomes(
    profile: AuthorizationEvaluationProfileKind,
    rbac: DirectoryRbacCellTruthV1,
    abac: AbacCellTruthV1 | None,
    rebac: RebacCellTruthV1 | None,
) -> tuple[MechanismOutcomeSetV1, MechanismOutcomeSetV1]:
    rbac_actual = _mechanism_outcome(rbac.effective_decision)
    rbac_intended = _mechanism_outcome(rbac.intended_decision)
    if profile is AuthorizationEvaluationProfileKind.RBAC:
        return MechanismOutcomeSetV1(rbac=rbac_actual), MechanismOutcomeSetV1(
            rbac=rbac_intended
        )
    if profile is AuthorizationEvaluationProfileKind.ABAC:
        abac_cell = cast(AbacCellTruthV1, abac)
        return MechanismOutcomeSetV1(
            abac=abac_cell.actual_outcome
        ), MechanismOutcomeSetV1(abac=abac_cell.intended_outcome)
    if profile is AuthorizationEvaluationProfileKind.REBAC:
        rebac_cell = cast(RebacCellTruthV1, rebac)
        return MechanismOutcomeSetV1(
            rebac=rebac_cell.actual_outcome
        ), MechanismOutcomeSetV1(rebac=rebac_cell.intended_outcome)
    abac_cell = cast(AbacCellTruthV1, abac)
    if profile is AuthorizationEvaluationProfileKind.RBAC_WITH_ABAC_GUARD:
        return MechanismOutcomeSetV1(
            rbac=rbac_actual, abac=abac_cell.actual_outcome
        ), MechanismOutcomeSetV1(rbac=rbac_intended, abac=abac_cell.intended_outcome)
    rebac_cell = cast(RebacCellTruthV1, rebac)
    return MechanismOutcomeSetV1(
        rebac=rebac_cell.actual_outcome, abac=abac_cell.actual_outcome
    ), MechanismOutcomeSetV1(
        rebac=rebac_cell.intended_outcome, abac=abac_cell.intended_outcome
    )


def _normalize(
    profile: AuthorizationEvaluationProfileKind, outcomes: MechanismOutcomeSetV1
) -> AuthorizationDecision:
    if profile in {
        AuthorizationEvaluationProfileKind.RBAC_WITH_ABAC_GUARD,
        AuthorizationEvaluationProfileKind.REBAC_WITH_ABAC_GUARD,
    }:
        base = (
            outcomes.rbac
            if profile is AuthorizationEvaluationProfileKind.RBAC_WITH_ABAC_GUARD
            else outcomes.rebac
        )
        return (
            AuthorizationDecision.ALLOW
            if base is MechanismOutcome.ALLOW
            and outcomes.abac is MechanismOutcome.ALLOW
            else AuthorizationDecision.DENY
        )
    values = tuple(
        item for item in (outcomes.rbac, outcomes.abac, outcomes.rebac) if item
    )
    if MechanismOutcome.DENY in values:
        return AuthorizationDecision.DENY
    if MechanismOutcome.ALLOW in values:
        return AuthorizationDecision.ALLOW
    return AuthorizationDecision.DENY


def _conflict_sets(
    outcomes: MechanismOutcomeSetV1,
    *,
    abac_internal: bool,
    rebac_internal: bool,
) -> _ConflictSets:
    values = {
        "rbac": outcomes.rbac,
        "abac": outcomes.abac,
        "rebac": outcomes.rebac,
    }
    allowing = {
        name for name, outcome in values.items() if outcome is MechanismOutcome.ALLOW
    }
    denying = {
        name for name, outcome in values.items() if outcome is MechanismOutcome.DENY
    }
    if abac_internal:
        allowing.add("abac")
        denying.add("abac")
    if rebac_internal:
        allowing.add("rebac")
        denying.add("rebac")
    return _ConflictSets(tuple(sorted(allowing)), tuple(sorted(denying)))


def _runtime_gates_pass(cell: DirectoryRbacCellTruthV1) -> bool:
    return cell.binding_status in {
        BindingStatus.NOT_APPLICABLE,
        BindingStatus.MATCHES_CANONICAL,
    } and cell.lifecycle_status in {
        LifecycleStatus.NOT_APPLICABLE,
        LifecycleStatus.ACTIVE,
    }


def _mechanism_outcome(decision: AuthorizationDecision) -> MechanismOutcome:
    return (
        MechanismOutcome.ALLOW
        if decision is AuthorizationDecision.ALLOW
        else MechanismOutcome.DENY
    )


def _reconciliation(
    intended: AuthorizationDecision, effective: AuthorizationDecision
) -> ReconciliationOutcome:
    if intended is AuthorizationDecision.ALLOW:
        return (
            ReconciliationOutcome.ALIGNED_ALLOW
            if effective is AuthorizationDecision.ALLOW
            else ReconciliationOutcome.MISSING
        )
    return (
        ReconciliationOutcome.EXCESSIVE
        if effective is AuthorizationDecision.ALLOW
        else ReconciliationOutcome.ALIGNED_DENY
    )


def _truth_id(*parts: str) -> str:
    return str(
        uuid5(ENTERPRISE_AUTHORIZATION_TRUTH_RECORD_NAMESPACE_V1, encode_parts(parts))
    )


__all__ = [
    "compile_enterprise_access_state",
    "compile_enterprise_authorization_kernel",
    "compose_enterprise_authorization",
]
