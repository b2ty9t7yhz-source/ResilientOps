"""Algorithm-independent schedule metrics."""

from __future__ import annotations

from resilient_ops.domain.models import (
    ObjectiveMetrics,
    ProblemInstance,
    ScheduleAssignment,
)


def evaluate_schedule(
    instance: ProblemInstance,
    assignments: list[ScheduleAssignment],
    rejected_task_ids: list[str] | None = None,
    original_assignments: list[ScheduleAssignment] | None = None,
) -> ObjectiveMetrics:
    """Calculate the common scorecard for any scheduler."""

    rejected = set(rejected_task_ids or [])
    by_task = {task.id: task for task in instance.tasks}
    scheduled = {assignment.task_id: assignment for assignment in assignments}
    tardiness = {
        task_id: max(0, assignment.end_time - by_task[task_id].deadline)
        for task_id, assignment in scheduled.items()
        if task_id in by_task
    }
    weighted_tardiness = sum(
        by_task[task_id].priority * late for task_id, late in tardiness.items()
    )
    late_tasks = sum(late > 0 for late in tardiness.values())
    count = len(assignments)
    makespan = max((assignment.end_time for assignment in assignments), default=0)
    elapsed = max(makespan, 1)
    worker_busy = sum(
        assignment.end_time - assignment.start_time
        for assignment in assignments
        if assignment.worker_id is not None
    )
    machine_busy = sum(
        assignment.end_time - assignment.start_time
        for assignment in assignments
        if assignment.machine_id is not None
    )
    worker_utilization = (
        worker_busy / (elapsed * len(instance.workers)) if instance.workers else 0.0
    )
    machine_utilization = (
        machine_busy / (elapsed * len(instance.machines)) if instance.machines else 0.0
    )

    old = {assignment.task_id: assignment for assignment in original_assignments or []}
    changed = 0
    movement = 0
    for task_id, assignment in scheduled.items():
        previous = old.get(task_id)
        if previous is None:
            continue
        movement += abs(assignment.start_time - previous.start_time)
        if (
            assignment.start_time != previous.start_time
            or assignment.worker_id != previous.worker_id
            or assignment.machine_id != previous.machine_id
        ):
            changed += 1
    changed += len(set(old) & rejected)

    return ObjectiveMetrics(
        weighted_tardiness=weighted_tardiness,
        late_tasks=late_tasks,
        on_time_completion_rate=(count - late_tasks) / count if count else 0.0,
        accepted_task_value=sum(by_task[item].value for item in scheduled if item in by_task),
        rejected_task_value=sum(by_task[item].value for item in rejected if item in by_task),
        worker_utilization=worker_utilization,
        machine_utilization=machine_utilization,
        makespan=makespan,
        number_of_changed_tasks=changed,
        total_start_time_movement=movement,
    )
