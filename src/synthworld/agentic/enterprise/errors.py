"""Failures at the bounded enterprise-agentic projection boundary."""


class EnterpriseAgenticIntegrityError(ValueError):
    """Raised when public overlay references or replay order are invalid."""


class EnterpriseAgenticArtifactError(ValueError):
    """Raised when an enterprise-agentic artifact tree is invalid."""


class EnterpriseAgenticEvaluationError(ValueError):
    """Raised when a trace cannot be scored against the benchmark."""


__all__ = [
    "EnterpriseAgenticArtifactError",
    "EnterpriseAgenticEvaluationError",
    "EnterpriseAgenticIntegrityError",
]
