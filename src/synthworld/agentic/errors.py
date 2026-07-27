"""Domain errors shared by agentic replay and benchmark construction."""

from __future__ import annotations


class AgenticReplayError(ValueError):
    """Raised when an agentic snapshot or event stream is structurally invalid."""


class AgenticBenchmarkIntegrityError(AgenticReplayError):
    """Raised when public records and evaluator inputs form an invalid join."""


__all__ = ["AgenticBenchmarkIntegrityError", "AgenticReplayError"]
