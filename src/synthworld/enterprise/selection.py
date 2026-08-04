"""Pinned deterministic population selection shared by enterprise compilers."""

from __future__ import annotations

import hashlib
from uuid import UUID

from synthworld.enterprise.canonical import (
    ENTERPRISE_PRINCIPAL_NAMESPACE_V1,
    encode_parts,
    stable_enterprise_id,
)
from synthworld.enterprise.models import (
    ENTERPRISE_SELECTOR_ALGORITHM_VERSION,
    SelectorV1,
)
from synthworld.enterprise.validation import selector_count


def select_principal_slot_indices(
    *,
    population_key: str,
    population_count: int,
    selector: SelectorV1,
    seed: int,
    blueprint_namespace: UUID,
    selection_key: str,
) -> tuple[int, ...]:
    """Return selected slots in canonical generated-principal-ID order."""

    selected_count = selector_count(selector, population_count)
    ranked = sorted(
        range(population_count),
        key=lambda slot: (
            hashlib.sha256(
                encode_parts(
                    (
                        ENTERPRISE_SELECTOR_ALGORITHM_VERSION,
                        str(seed),
                        str(blueprint_namespace),
                        population_key,
                        selection_key,
                        str(slot),
                    )
                ).encode("utf-8")
            ).digest(),
            stable_enterprise_id(
                ENTERPRISE_PRINCIPAL_NAMESPACE_V1,
                blueprint_namespace,
                population_key,
                str(slot),
            ),
        ),
    )
    return tuple(
        sorted(
            ranked[:selected_count],
            key=lambda slot: stable_enterprise_id(
                ENTERPRISE_PRINCIPAL_NAMESPACE_V1,
                blueprint_namespace,
                population_key,
                str(slot),
            ),
        )
    )


__all__ = ["select_principal_slot_indices"]
