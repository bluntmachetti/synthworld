"""Fail-closed routing across released generated enterprise-agentic contracts."""

from __future__ import annotations

import json
import stat
from pathlib import Path
from typing import Literal

from synthworld.agentic.enterprise.errors import EnterpriseAgenticArtifactError
from synthworld.agentic.enterprise.generated_models import (
    EnterpriseAgenticGeneratedBenchmarkV1,
    EnterpriseAgenticGeneratedPublicV1,
)
from synthworld.agentic.enterprise.generated_scale_models import (
    EnterpriseAgenticGeneratedBenchmarkV2,
    EnterpriseAgenticGeneratedPublicV2,
)
from synthworld.agentic.enterprise.generated_scale_serialization import (
    load_generated_enterprise_agentic_scale_benchmark,
    load_public_generated_enterprise_agentic_scale_benchmark,
)
from synthworld.agentic.enterprise.generated_serialization import (
    load_generated_enterprise_agentic_benchmark,
    load_public_generated_enterprise_agentic_benchmark,
)

GeneratedEnterpriseAgenticBenchmark = (
    EnterpriseAgenticGeneratedBenchmarkV1 | EnterpriseAgenticGeneratedBenchmarkV2
)
GeneratedEnterpriseAgenticPublic = (
    EnterpriseAgenticGeneratedPublicV1 | EnterpriseAgenticGeneratedPublicV2
)


def load_any_generated_enterprise_agentic_public(
    root: Path,
) -> GeneratedEnterpriseAgenticPublic:
    """Load a generated public root using its explicit profile discriminator."""

    profile = _declared_profile(root)
    if profile == "v1":
        return load_public_generated_enterprise_agentic_benchmark(root)
    return load_public_generated_enterprise_agentic_scale_benchmark(root)


def load_any_generated_enterprise_agentic_benchmark(
    root: Path,
) -> GeneratedEnterpriseAgenticBenchmark:
    """Load a complete generated root using its explicit profile discriminator."""

    profile = _declared_profile(root)
    if profile == "v1":
        return load_generated_enterprise_agentic_benchmark(root)
    return load_generated_enterprise_agentic_scale_benchmark(root)


def _declared_profile(root: Path) -> Literal["v1", "v2"]:
    public_input = root / "public" / "public-input.json"
    try:
        status = public_input.lstat()
        if not stat.S_ISREG(status.st_mode):
            raise EnterpriseAgenticArtifactError(
                "generated enterprise-agentic public input is not a regular file"
            )
        document = json.loads(public_input.read_bytes())
        profile = document["config"]["profile_version"]
    except EnterpriseAgenticArtifactError:
        raise
    except (KeyError, OSError, TypeError, UnicodeDecodeError, ValueError) as error:
        raise EnterpriseAgenticArtifactError(
            "generated enterprise-agentic profile discriminator is invalid"
        ) from error
    if profile == "enterprise-agentic-generated-1.0.0":
        return "v1"
    if profile == "enterprise-agentic-generated-2.0.0":
        return "v2"
    raise EnterpriseAgenticArtifactError(
        "generated enterprise-agentic profile version is unsupported"
    )


__all__ = [
    "GeneratedEnterpriseAgenticBenchmark",
    "GeneratedEnterpriseAgenticPublic",
    "load_any_generated_enterprise_agentic_benchmark",
    "load_any_generated_enterprise_agentic_public",
]
