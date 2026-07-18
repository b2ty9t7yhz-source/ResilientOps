"""Google OR-Tools CP-SAT scheduler."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from time import perf_counter

from ortools.sat.python import cp_model

from resilient_ops.domain.models import (
    ProblemInstance,
    ScheduleAssignment,
    ScheduleResult,
    SolverConfig,
)
from resilient_ops.evaluation.metrics import evaluate_schedule
from resilient_ops.scheduling.feasibility import check_schedule

logger = logging.getLogger(__name__)


@dataclass
class _TaskVariables:
    accepted: cp_model.IntVar
    start: cp_model.IntVar
    end: cp_model.IntVar
    tardiness: cp_model.IntVar
    workers: dict[str, cp_model.IntVar]
    machines: dict[str, cp_model.IntVar]


def _availability_choices(
    model: cp_model.CpModel,
    presence: cp_model.IntVar,
    start: cp_model.IntVar,
    end: cp_model.IntVar,
    intervals: list[tuple[int, int]],
    name: str,
) -> None:
    choices = [model.new_bool_var(f"{name}_available_{index}") for index in range(len(intervals))]
    model.add(sum(choices) == presence)
    for choice, (left, right) in zip(choices, intervals, strict=True):
        model.add(start >= left).only_enforce_if(choice)
        model.add(end <= right).only_enforce_if(choice)


def solve_cp_sat(
    instance: ProblemInstance,
    config: SolverConfig | None = None,
    original_assignments: list[ScheduleAssignment] | None = None,
    locked_assignments: list[ScheduleAssignment] | None = None,
    event_time: int | None = None,
) -> ScheduleResult:
    """Optimize a scenario, optionally preserving an earlier schedule."""

    started = perf_counter()
    settings = config or SolverConfig()
    model = cp_model.CpModel()
    horizon = instance.horizon
    workers = {worker.id: worker for worker in instance.workers}
    machines = {machine.id: machine for machine in instance.machines}
    previous = {item.task_id: item for item in original_assignments or []}
    locked = {item.task_id: item for item in locked_assignments or []}
    variables: dict[str, _TaskVariables] = {}
    worker_intervals: dict[str, list[cp_model.IntervalVar]] = {item: [] for item in workers}
    machine_intervals: dict[str, list[cp_model.IntervalVar]] = {item: [] for item in machines}
    objective_terms: list[cp_model.LinearExpr] = []
    change_terms: list[cp_model.LinearExpr] = []
    completion_vars: list[cp_model.IntVar] = []

    for task in instance.tasks:
        safe_id = task.id.replace(" ", "_")
        accepted = model.new_bool_var(f"accepted_{safe_id}")
        if task.mandatory:
            model.add(accepted == 1)
        start = model.new_int_var(0, horizon, f"start_{safe_id}")
        end = model.new_int_var(0, horizon, f"end_{safe_id}")
        model.add(start >= task.release_time).only_enforce_if(accepted)
        model.add(end == start + task.duration).only_enforce_if(accepted)
        model.add(start == 0).only_enforce_if(accepted.Not())
        model.add(end == 0).only_enforce_if(accepted.Not())
        tardiness = model.new_int_var(0, horizon, f"tardiness_{safe_id}")
        model.add(tardiness >= end - task.deadline - horizon * (1 - accepted))
        model.add(tardiness <= horizon * accepted)
        objective_terms.append(settings.weights.weighted_tardiness * task.priority * tardiness)
        objective_terms.append(settings.weights.rejected_value * task.value * (1 - accepted))

        completion = model.new_int_var(0, horizon, f"completion_{safe_id}")
        model.add(completion == end).only_enforce_if(accepted)
        model.add(completion == 0).only_enforce_if(accepted.Not())
        completion_vars.append(completion)

        worker_vars: dict[str, cp_model.IntVar] = {}
        eligible_workers = [
            worker
            for worker in instance.workers
            if task.required_skill and task.required_skill in worker.skills
        ]
        if task.required_skill:
            for worker in eligible_workers:
                present = model.new_bool_var(f"task_{safe_id}_worker_{worker.id}")
                worker_vars[worker.id] = present
                interval = model.new_optional_interval_var(
                    start, task.duration, end, present, f"interval_{safe_id}_{worker.id}"
                )
                worker_intervals[worker.id].append(interval)
                if task.id not in locked:
                    _availability_choices(
                        model,
                        present,
                        start,
                        end,
                        [(item.start, item.end) for item in worker.available_intervals],
                        f"{safe_id}_{worker.id}",
                    )
            model.add(sum(worker_vars.values()) == accepted)

        machine_vars: dict[str, cp_model.IntVar] = {}
        eligible_machines = [
            machine
            for machine in instance.machines
            if task.required_machine_type and task.required_machine_type == machine.machine_type
        ]
        if task.required_machine_type:
            for machine in eligible_machines:
                present = model.new_bool_var(f"task_{safe_id}_machine_{machine.id}")
                machine_vars[machine.id] = present
                interval = model.new_optional_interval_var(
                    start, task.duration, end, present, f"interval_{safe_id}_{machine.id}"
                )
                machine_intervals[machine.id].append(interval)
                if task.id not in locked:
                    _availability_choices(
                        model,
                        present,
                        start,
                        end,
                        [(item.start, item.end) for item in machine.available_intervals],
                        f"{safe_id}_{machine.id}",
                    )
            model.add(sum(machine_vars.values()) == accepted)

        variables[task.id] = _TaskVariables(
            accepted=accepted,
            start=start,
            end=end,
            tardiness=tardiness,
            workers=worker_vars,
            machines=machine_vars,
        )

    for task in instance.tasks:
        current = variables[task.id]
        for predecessor_id in task.predecessor_ids:
            if predecessor_id not in variables:
                continue
            predecessor = variables[predecessor_id]
            model.add(current.accepted <= predecessor.accepted)
            model.add(predecessor.end <= current.start).only_enforce_if(current.accepted)

    for intervals in worker_intervals.values():
        model.add_no_overlap(intervals)
    for intervals in machine_intervals.values():
        model.add_no_overlap(intervals)

    for task_id, assignment in locked.items():
        if task_id not in variables:
            continue
        current = variables[task_id]
        model.add(current.accepted == 1)
        model.add(current.start == assignment.start_time)
        model.add(current.end == assignment.end_time)
        if assignment.worker_id is not None:
            selected = current.workers.get(assignment.worker_id)
            if selected is None:
                model.add(current.accepted == 0)
            else:
                model.add(selected == 1)
        if assignment.machine_id is not None:
            selected = current.machines.get(assignment.machine_id)
            if selected is None:
                model.add(current.accepted == 0)
            else:
                model.add(selected == 1)

    for task_id, old in previous.items():
        if task_id not in variables or task_id in locked:
            continue
        current = variables[task_id]
        movement = model.new_int_var(0, horizon, f"movement_{task_id}")
        model.add(movement >= current.start - old.start_time).only_enforce_if(current.accepted)
        model.add(movement >= old.start_time - current.start).only_enforce_if(current.accepted)
        model.add(movement <= horizon * current.accepted)
        moved = model.new_bool_var(f"moved_{task_id}")
        model.add(movement <= horizon * moved)
        model.add(movement >= moved)
        model.add(moved <= current.accepted)

        factor = 1
        if (
            event_time is not None
            and old.start_time <= event_time + settings.weights.frozen_horizon
        ):
            factor = 5
        change_terms.append(factor * movement)
        change_terms.append(factor * settings.weights.moved_task * moved)

        if old.worker_id is not None:
            worker_changed = model.new_bool_var(f"worker_changed_{task_id}")
            original_worker = current.workers.get(old.worker_id)
            if original_worker is None:
                model.add(worker_changed == current.accepted)
            else:
                model.add(worker_changed == current.accepted - original_worker)
            change_terms.append(factor * settings.weights.worker_change * worker_changed)
        if old.machine_id is not None:
            machine_changed = model.new_bool_var(f"machine_changed_{task_id}")
            original_machine = current.machines.get(old.machine_id)
            if original_machine is None:
                model.add(machine_changed == current.accepted)
            else:
                model.add(machine_changed == current.accepted - original_machine)
            change_terms.append(factor * settings.weights.machine_change * machine_changed)
        change_terms.append(settings.weights.previously_accepted_rejection * (1 - current.accepted))

    # Warm-start repair from the prior accepted assignment. Hints do not constrain the model.
    for task_id, old in previous.items():
        hinted = variables.get(task_id)
        if hinted is None:
            continue
        model.add_hint(hinted.accepted, 1)
        model.add_hint(hinted.start, old.start_time)
        model.add_hint(hinted.end, old.end_time)
        for hinted_worker_id, selected in hinted.workers.items():
            model.add_hint(selected, int(hinted_worker_id == old.worker_id))
        for hinted_machine_id, selected in hinted.machines.items():
            model.add_hint(selected, int(hinted_machine_id == old.machine_id))

    makespan = model.new_int_var(0, horizon, "makespan")
    model.add_max_equality(makespan, completion_vars)
    objective_terms.append(settings.weights.makespan * makespan)
    if change_terms:
        objective_terms.append(
            settings.weights.schedule_change * cp_model.LinearExpr.sum(change_terms)
        )
    model.minimize(sum(objective_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = settings.time_limit_seconds
    solver.parameters.random_seed = settings.random_seed
    solver.parameters.num_search_workers = settings.num_workers
    status_code = solver.solve(model)
    status = solver.status_name(status_code)
    runtime = perf_counter() - started
    assignments: list[ScheduleAssignment] = []
    rejected: list[str] = []
    warnings: list[str] = []

    if status_code in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for task in instance.tasks:
            current = variables[task.id]
            if not solver.boolean_value(current.accepted):
                rejected.append(task.id)
                continue
            worker_id = next(
                (
                    item
                    for item, variable in current.workers.items()
                    if solver.boolean_value(variable)
                ),
                None,
            )
            machine_id = next(
                (
                    item
                    for item, variable in current.machines.items()
                    if solver.boolean_value(variable)
                ),
                None,
            )
            locked_item = locked.get(task.id)
            assignments.append(
                ScheduleAssignment(
                    task_id=task.id,
                    worker_id=worker_id,
                    machine_id=machine_id,
                    start_time=solver.value(current.start),
                    end_time=solver.value(current.end),
                    status=locked_item.status if locked_item else "planned",
                    locked=locked_item is not None,
                )
            )
        assignments.sort(key=lambda item: (item.start_time, item.task_id))
        rejected.sort()
        violations = check_schedule(instance, assignments, rejected)
        # Locked running work is deliberately allowed to overlap a newly introduced outage.
        locked_availability_errors = {
            f"Task {item.task_id} is outside worker {item.worker_id} availability."
            for item in locked.values()
            if item.worker_id
        } | {
            f"Task {item.task_id} is outside machine {item.machine_id} availability."
            for item in locked.values()
            if item.machine_id
        }
        warnings.extend(item for item in violations if item not in locked_availability_errors)
    else:
        warnings.append("CP-SAT found no feasible schedule within the configured limits.")

    metrics = evaluate_schedule(instance, assignments, rejected, original_assignments)
    objective_value = (
        solver.objective_value if status_code in (cp_model.OPTIMAL, cp_model.FEASIBLE) else None
    )
    best_bound = (
        solver.best_objective_bound
        if status_code in (cp_model.OPTIMAL, cp_model.FEASIBLE)
        else None
    )
    relative_gap = (
        abs(objective_value - best_bound) / max(1.0, abs(objective_value))
        if objective_value is not None and best_bound is not None
        else None
    )
    logger.info(
        "cp_sat_solve_completed",
        extra={
            "scenario": instance.name,
            "solver_status": status,
            "assignment_count": len(assignments),
            "rejected_count": len(rejected),
            "runtime_seconds": runtime,
        },
    )
    return ScheduleResult(
        algorithm="cp-sat",
        assignments=assignments,
        rejected_task_ids=rejected,
        metrics=metrics,
        runtime_seconds=runtime,
        solver_status=status,
        objective_value=objective_value,
        best_objective_bound=best_bound,
        relative_gap=relative_gap,
        warnings=warnings,
        validation_results=["Scenario is valid."],
    )


class CpSatScheduler:
    """Configurable CP-SAT scheduler implementation."""

    def __init__(self, config: SolverConfig | None = None) -> None:
        self.config = config or SolverConfig()

    def solve(self, instance: ProblemInstance) -> ScheduleResult:
        """Optimize a scenario."""
        return solve_cp_sat(instance, self.config)
