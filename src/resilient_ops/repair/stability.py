"""Schedule locking and change classification."""

from __future__ import annotations

from resilient_ops.domain.models import ScheduleAssignment


def lock_started_work(
    assignments: list[ScheduleAssignment], event_time: int
) -> list[ScheduleAssignment]:
    """Lock completed work and work already running strictly before the event."""

    result: list[ScheduleAssignment] = []
    for assignment in assignments:
        if assignment.end_time <= event_time:
            result.append(assignment.model_copy(update={"status": "completed", "locked": True}))
        elif assignment.start_time < event_time < assignment.end_time:
            result.append(assignment.model_copy(update={"status": "in_progress", "locked": True}))
    return result


def classify_changes(
    original: list[ScheduleAssignment], repaired: list[ScheduleAssignment]
) -> dict[str, str]:
    """Label tasks for accessible original-versus-repaired charts."""

    old = {item.task_id: item for item in original}
    labels: dict[str, str] = {}
    for item in repaired:
        previous = old.get(item.task_id)
        if previous is None:
            labels[item.task_id] = "newly added"
        elif item.worker_id != previous.worker_id or item.machine_id != previous.machine_id:
            labels[item.task_id] = "reassigned"
        elif item.start_time > previous.start_time:
            labels[item.task_id] = "delayed"
        elif item.start_time != previous.start_time:
            labels[item.task_id] = "moved"
        else:
            labels[item.task_id] = "unchanged"
    return labels
