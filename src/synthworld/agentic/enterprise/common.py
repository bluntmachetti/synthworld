"""Closed versions and stable identifiers for the enterprise-agentic smoke pack."""

from __future__ import annotations

from typing import Literal
from uuid import UUID, uuid5

from synthworld.enterprise.canonical import encode_parts

ENTERPRISE_AGENTIC_CONFIG_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_AGENTIC_BENCHMARK_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_AGENTIC_PUBLIC_INPUT_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_AGENTIC_TRUTH_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_AGENTIC_PREDICTION_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_AGENTIC_METRICS_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_AGENTIC_TRACE_VALIDATION_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_AGENTIC_COMPILER_VERSION: Literal["1.0.0"] = "1.0.0"
ENTERPRISE_AGENTIC_PROFILE_VERSION: Literal["enterprise-agentic-smoke-1.0.0"] = (
    "enterprise-agentic-smoke-1.0.0"
)
ENTERPRISE_AGENTIC_AIIM_SOURCE_ID: Literal["openid-aiim-mcp-interop-2026-07-14"] = (
    "openid-aiim-mcp-interop-2026-07-14"
)
ENTERPRISE_AGENTIC_AIIM_PROFILE_VERSION: Literal["0.1.0-experimental"] = (
    "0.1.0-experimental"
)

_ENTERPRISE_AGENTIC_NAMESPACE_V1 = UUID("60707531-cde9-546a-b86c-e111e982e285")


def stable_enterprise_agentic_id(kind: str, *components: str) -> str:
    """Return a kind-separated UUID5 without incorporating seed or host state."""

    return str(
        uuid5(
            _ENTERPRISE_AGENTIC_NAMESPACE_V1,
            encode_parts((ENTERPRISE_AGENTIC_PROFILE_VERSION, kind, *components)),
        )
    )


__all__ = [name for name in globals() if not name.startswith("_")]
