"""Deterministic serial schedule-generation baselines."""

from __future__ import annotations

from collections.abc import Callable
from time import perf_counter

from resilient_ops.domain.models import ProblemInstance, ScheduleAssignment, ScheduleResult, Task
from resilient_ops.evaluation.metrics import evaluate_schedule
from resilient_ops.scheduling.feasibility import check_schedule

Ranker = Callable[[Task, int], tuple[int, ...]]


def _available(intervals: list[tuple[int, int]], start: int, end: int) -> bool:
    return any(left <= start and end <= right for left, right in intervals)


def _free(reservations: list[tuple[int, int]], start: int, end: int) -> bool:
    return all(end <= left or right <= start for left, right in reservations)


def _ranker(algorithm: str) -> Ranker:
    if algorithm == "edf":
        return lambda task, now: (task.deadline, -task.priority, task.release_time)
    if algorithm == "priority":
        return lambda task, now: (-task.priority, task.deadline, task.release_time)
    if algorithm == "slack":
        return lambda task, now: (
            task.deadline - now - task.duration,
            task.deadline,
            -task.priority,
        )
    raise ValueError(f"Unknown baseline algorithm: {algorithm}")


def solve_baseline(instance: ProblemInstance, algorithm: str) -> ScheduleResult:
    """Schedule tasks using EDF, highest priority, or minimum slack first."""

    started = perf_counter()
    rank = _ranker(algorithm)
    tasks = {task.id: task for task in instance.tasks}
    remaining = set(tasks)
    rejected: list[str] = []
    assignments: list[ScheduleAssignment] = []
    scheduled: dict[str, ScheduleAssignment] = {}
    worker_bookings: dict[str, list[tuple[int, int]]] = {
        worker.id: [] for worker in instance.workers
    }
    machine_bookings: dict[str, list[tuple[int, int]]] = {
        machine.id: [] for machine in instance.machines
    }
    warnings: list[str] = []
    infeasible = False

    while remaining:
        rejected_set = set(rejected)
        blocked = [
            tasks[task_id]
            for task_id in remaining
            if any(predecessor in rejected_set for predecessor in tasks[task_id].predecessor_ids)
        ]
        for task in blocked:
            remaining.remove(task.id)
            if task.mandatory:
                warnings.append(f"Mandatory task {task.id} depends on a rejected task.")
                infeasible = True
            else:
                rejected.append(task.id)
        if infeasible:
            break

        ready = [
            tasks[task_id]
            for task_id in remaining
            if all(predecessor in scheduled for predecessor in tasks[task_id].predecessor_ids)
        ]
        if not ready:
            warnings.append("No dependency-ready task remained; the instance is infeasible.")
            infeasible = True
            break
        current_time = min(
            max(
                task.release_time,
                max(
                    (scheduled[item].end_time for item in task.predecessor_ids),
                    default=0,
                ),
            )
            for task in ready
        )
        task = min(ready, key=lambda item: (*rank(item, current_time), item.id))
        earliest = max(
            task.release_time,
            max((scheduled[item].end_time for item in task.predecessor_ids), default=0),
        )
        eligible_workers = (
            sorted(worker.id for worker in instance.workers if task.required_skill in worker.skills)
            if task.required_skill
            else [None]
        )
        eligible_machines = (
            sorted(
                machine.id
                for machine in instance.machines
                if machine.machine_type == task.required_machine_type
            )
            if task.required_machine_type
            else [None]
        )
        selected: tuple[int, str | None, str | None] | None = None
        for start in range(earliest, instance.horizon - task.duration + 1):
            end = start + task.duration
            for worker_id in eligible_workers:
                worker_ok = worker_id is None or (
                    _available(
                        [
                            (item.start, item.end)
                            for item in next(
                                worker for worker in instance.workers if worker.id == worker_id
                            ).available_intervals
                        ],
                        start,
                        end,
                    )
                    and _free(worker_bookings[worker_id], start, end)
                )
                if not worker_ok:
                    continue
                for machine_id in eligible_machines:
                    machine_ok = machine_id is None or (
                        _available(
                            [
                                (item.start, item.end)
                                for item in next(
                                    machine
                                    for machine in instance.machines
                                    if machine.id == machine_id
                                ).available_intervals
                            ],
                            start,
                            end,
                        )
                        and _free(machine_bookings[machine_id], start, end)
                    )
                    if machine_ok:
                        selected = (start, worker_id, machine_id)
                        break
                if selected:
                    break
            if selected:
                break
        remaining.remove(task.id)
        if selected is None:
            if task.mandatory:
                warnings.append(f"Mandatory task {task.id} could not be placed within the horizon.")
                infeasible = True
                break
            rejected.append(task.id)
            continue
        start, worker_id, machine_id = selected
        assignment = ScheduleAssignment(
            task_id=task.id,
            worker_id=worker_id,
            machine_id=machine_id,
            start_time=start,
            end_time=start + task.duration,
        )
        assignments.append(assignment)
        scheduled[task.id] = assignment
        if worker_id:
            worker_bookings[worker_id].append((assignment.start_time, assignment.end_time))
        if machine_id:
            machine_bookings[machine_id].append((assignment.start_time, assignment.end_time))

    runtime = perf_counter() - started
    if infeasible:
        assignments = []
        rejected = sorted(task.id for task in instance.tasks if not task.mandatory)
        status = "INFEASIBLE"
    else:
        assignments.sort(key=lambda item: (item.start_time, item.task_id))
        rejected.sort()
        violations = check_schedule(instance, assignments, rejected)
        warnings.extend(violations)
        status = "FEASIBLE" if not violations else "INVALID"
    metrics = evaluate_schedule(instance, assignments, rejected)
    return ScheduleResult(
        algorithm=algorithm,
        assignments=assignments,
        rejected_task_ids=rejected,
        metrics=metrics,
        runtime_seconds=runtime,
        solver_status=status,
        warnings=warnings,
        validation_results=["Scenario is valid."],
    )


class GreedyScheduler:
    """Object-oriented wrapper around a deterministic baseline."""

    def __init__(self, algorithm: str) -> None:
        self.algorithm = algorithm

    def solve(self, instance: ProblemInstance) -> ScheduleResult:
        """Generate a schedule."""
        return solve_baseline(instance, self.algorithm)
