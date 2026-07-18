"""Feasibility checks shared by tests and user-facing validation."""

from __future__ import annotations

from resilient_ops.domain.models import ProblemInstance, ScheduleAssignment


def _contains(intervals: list[tuple[int, int]], start: int, end: int) -> bool:
    return any(left <= start and end <= right for left, right in intervals)


def check_schedule(
    instance: ProblemInstance,
    assignments: list[ScheduleAssignment],
    rejected_task_ids: list[str] | None = None,
) -> list[str]:
    """Return human-readable hard-constraint violations."""

    errors: list[str] = []
    rejected = set(rejected_task_ids or [])
    workers = {worker.id: worker for worker in instance.workers}
    machines = {machine.id: machine for machine in instance.machines}
    scheduled = {assignment.task_id: assignment for assignment in assignments}

    duplicates = len(scheduled) != len(assignments)
    if duplicates:
        errors.append("A task is assigned more than once.")
    for task in instance.tasks:
        assignment = scheduled.get(task.id)
        if task.mandatory and assignment is None:
            errors.append(f"Mandatory task {task.id} is not scheduled.")
        if assignment is None:
            continue
        if task.id in rejected:
            errors.append(f"Task {task.id} is both scheduled and rejected.")
        if assignment.start_time < task.release_time:
            errors.append(f"Task {task.id} starts before its release time.")
        if assignment.end_time - assignment.start_time != task.duration:
            errors.append(f"Task {task.id} has the wrong duration.")
        if task.required_skill:
            worker = workers.get(assignment.worker_id or "")
            if worker is None or task.required_skill not in worker.skills:
                errors.append(f"Task {task.id} has no qualified worker.")
            elif not _contains(
                [(item.start, item.end) for item in worker.available_intervals],
                assignment.start_time,
                assignment.end_time,
            ):
                errors.append(f"Task {task.id} is outside worker {worker.id} availability.")
        if task.required_machine_type:
            machine = machines.get(assignment.machine_id or "")
            if machine is None or task.required_machine_type != machine.machine_type:
                errors.append(f"Task {task.id} has no compatible machine.")
            elif not _contains(
                [(item.start, item.end) for item in machine.available_intervals],
                assignment.start_time,
                assignment.end_time,
            ):
                errors.append(f"Task {task.id} is outside machine {machine.id} availability.")
        for predecessor_id in task.predecessor_ids:
            predecessor = scheduled.get(predecessor_id)
            if predecessor is None:
                errors.append(f"Task {task.id} has unscheduled predecessor {predecessor_id}.")
            elif predecessor.end_time > assignment.start_time:
                errors.append(
                    f"Task {task.id} starts before predecessor {predecessor_id} finishes."
                )

    for resource_field, label in (("worker_id", "Worker"), ("machine_id", "Machine")):
        resource_ids = {
            getattr(assignment, resource_field)
            for assignment in assignments
            if getattr(assignment, resource_field) is not None
        }
        for resource_id in resource_ids:
            intervals = sorted(
                (
                    assignment.start_time,
                    assignment.end_time,
                    assignment.task_id,
                )
                for assignment in assignments
                if getattr(assignment, resource_field) == resource_id
            )
            for previous, current in zip(intervals, intervals[1:], strict=False):
                if current[0] < previous[1]:
                    errors.append(
                        f"{label} {resource_id} overlaps on tasks {previous[2]} and {current[2]}."
                    )
    return errors
