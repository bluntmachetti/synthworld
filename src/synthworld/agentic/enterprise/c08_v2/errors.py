"""Errors for the isolated enterprise C08 v2 surface."""


class C08ProjectionError(ValueError):
    """Raised when a public projection cannot be bound to its source."""


class C08EvaluationError(ValueError):
    """Raised when evaluator or submission inputs are structurally unbindable."""


class C08SerializationError(ValueError):
    """Raised when a C08 artifact is missing, non-canonical, or unsafe."""
