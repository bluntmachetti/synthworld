"""Closed vocabulary and versions for the #7 identity-fabric smoke pack."""

from typing import Literal

IDENTITY_FABRIC_BENCHMARK_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
IDENTITY_FABRIC_PUBLIC_INPUT_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
IDENTITY_FABRIC_TRUTH_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
IDENTITY_FABRIC_PREDICTION_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
IDENTITY_FABRIC_METRICS_SCHEMA_VERSION: Literal["1.0.0"] = "1.0.0"
IDENTITY_FABRIC_COMPILER_VERSION: Literal["1.0.0"] = "1.0.0"
IDENTITY_FABRIC_PROFILE_VERSION: Literal["identity-fabric-smoke-1.0.0"] = (
    "identity-fabric-smoke-1.0.0"
)
__all__ = [name for name in globals() if not name.startswith("_")]
