"""Per-run wall-clock measurements for the opt-in aligned translation path."""

from dataclasses import dataclass


@dataclass
class AlignmentStatistics:
    """Calls count orchestration calls, not hidden backend generation calls."""

    translation_calls: int = 0
    translation_seconds: float = 0.0
    alignment_calls: int = 0
    alignment_seconds: float = 0.0
    alignment_failures: int = 0
    planning_seconds: float = 0.0
    protected_units: int = 0
