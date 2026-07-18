"""Orchestration for disruption-aware schedule repair."""

from __future__ import annotations

import logging

from resilient_ops.domain.models import (
    DisruptionEvent,
    ProblemInstance,
    ScheduleResult,
    SolverConfig,
)
from resilient_ops.domain.validation import validate_scenario
from resilient_ops.repair.events import apply_events
from resilient_ops.repair.stability import lock_started_work
from resilient_ops.scheduling.cp_sat import solve_cp_sat

logger = logging.getLogger(__name__)


def repair_schedule(
    instance: ProblemInstance,
    events: list[DisruptionEvent],
    original_schedule: ScheduleResult | None = None,
    config: SolverConfig | None = None,
) -> tuple[ProblemInstance, ScheduleResult, ScheduleResult]:
    """Generate (if needed), disrupt, and repair a schedule."""

    if not events:
        raise ValueError("At least one disruption event is required.")
    settings = config or SolverConfig()
    original = original_schedule or solve_cp_sat(instance, settings)
    if original.solver_status not in {"OPTIMAL", "FEASIBLE"}:
        raise ValueError("Cannot repair an original schedule that is not feasible.")
    disrupted = apply_events(instance, events)
    validate_scenario(disrupted)
    event_time = max(event.event_time for event in events)
    locked = lock_started_work(original.assignments, event_time)
    repaired = solve_cp_sat(
        disrupted,
        settings,
        original_assignments=original.assignments,
        locked_assignments=locked,
        event_time=event_time,
    )
    logger.info(
        "schedule_repair_completed",
        extra={
            "scenario": instance.name,
            "event_count": len(events),
            "event_time": event_time,
            "locked_task_count": len(locked),
            "changed_task_count": repaired.metrics.number_of_changed_tasks,
        },
    )
    return disrupted, original, repaired
