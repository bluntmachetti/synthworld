"""Repository-only fictional EADS-shaped structure adapter.

The package performs no network operations and does not claim compatibility with a
real EADS export or schema.
"""

from .adapter import (
    ADAPTER_VERSION,
    AdapterCode,
    AdapterConfig,
    AdapterGap,
    AdapterPathError,
    AdapterRunReport,
    ArtifactKind,
    ArtifactRecord,
    ArtifactVisibility,
    DownscaleDeclaration,
    OrganisationOutcome,
    SourcePayloadError,
    run_adapter,
)
from .models import (
    CanonicalDomain,
    CanonicalEadsSource,
    CanonicalOrganisation,
    CanonicalOwnership,
    CanonicalRegion,
    CanonicalService,
    CanonicalTeam,
    IgnoredSourceMeasurement,
    SourceVintage,
    parse_source,
)

__all__ = (
    "ADAPTER_VERSION",
    "AdapterCode",
    "AdapterConfig",
    "AdapterGap",
    "AdapterPathError",
    "AdapterRunReport",
    "ArtifactKind",
    "ArtifactRecord",
    "ArtifactVisibility",
    "CanonicalDomain",
    "CanonicalEadsSource",
    "CanonicalOrganisation",
    "CanonicalOwnership",
    "CanonicalRegion",
    "CanonicalService",
    "CanonicalTeam",
    "DownscaleDeclaration",
    "IgnoredSourceMeasurement",
    "OrganisationOutcome",
    "SourcePayloadError",
    "SourceVintage",
    "parse_source",
    "run_adapter",
)
