"""Shared scheduler protocol."""

from typing import Protocol

from resilient_ops.domain.models import ProblemInstance, ScheduleResult


class Scheduler(Protocol):
    """Interface implemented by scheduling algorithms."""

    def solve(self, instance: ProblemInstance) -> ScheduleResult:
        """Create a schedule for an instance."""
        ...
