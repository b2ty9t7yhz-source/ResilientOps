"""Human-readable explanations for schedule outcomes and repairs."""

from __future__ import annotations

from resilient_ops.domain.models import (
    DisruptionEvent,
    MachineBreakdown,
    ProblemInstance,
    ScheduleExplanation,
    ScheduleResult,
    UrgentTaskArrival,
    WorkerUnavailable,
)
from resilient_ops.repair.stability import classify_changes


def explain_schedule(
    instance: ProblemInstance, result: ScheduleResult
) -> list[ScheduleExplanation]:
    """Explain rejected and late tasks without claiming solver internals as certainty."""

    tasks = {task.id: task for task in instance.tasks}
    scheduled = {item.task_id: item for item in result.assignments}
    explanations: list[ScheduleExplanation] = []
    for task_id in result.rejected_task_ids:
        task = tasks[task_id]
        causes: list[str] = []
        if task.required_skill and not any(
            task.required_skill in worker.skills for worker in instance.workers
        ):
            causes.append(f"no worker has skill {task.required_skill}")
        if task.required_machine_type and not any(
            machine.machine_type == task.required_machine_type for machine in instance.machines
        ):
            causes.append(f"no {task.required_machine_type} machine is available")
        rejected_predecessors = set(task.predecessor_ids) & set(result.rejected_task_ids)
        if rejected_predecessors:
            causes.append(f"predecessor {', '.join(sorted(rejected_predecessors))} was rejected")
        reason = "; ".join(causes) or (
            "optional task value did not outweigh capacity, tardiness, and makespan costs"
        )
        explanations.append(
            ScheduleExplanation(
                task_id=task_id,
                classification="rejected",
                summary=f"{task.name} was rejected: {reason}.",
            )
        )
    for task_id, assignment in scheduled.items():
        task = tasks[task_id]
        if assignment.end_time > task.deadline:
            delay = assignment.end_time - task.deadline
            explanations.append(
                ScheduleExplanation(
                    task_id=task_id,
                    classification="late",
                    summary=(
                        f"{task.name} finishes {delay} time units after its deadline; "
                        "precedence and shared-resource capacity constrained an earlier placement."
                    ),
                )
            )
    return explanations


def explain_repair(
    instance: ProblemInstance,
    original: ScheduleResult,
    repaired: ScheduleResult,
    events: list[DisruptionEvent],
) -> list[ScheduleExplanation]:
    """Explain each visible difference between original and repaired schedules."""

    tasks = {task.id: task for task in instance.tasks}
    old = {item.task_id: item for item in original.assignments}
    new = {item.task_id: item for item in repaired.assignments}
    labels = classify_changes(original.assignments, repaired.assignments)
    outage_workers = {event.worker_id for event in events if isinstance(event, WorkerUnavailable)}
    outage_machines = {event.machine_id for event in events if isinstance(event, MachineBreakdown)}
    urgent_ids = {event.task.id for event in events if isinstance(event, UrgentTaskArrival)}
    explanations: list[ScheduleExplanation] = []
    for task_id in sorted(set(old) | set(new)):
        before = old.get(task_id)
        after = new.get(task_id)
        task_name = tasks[task_id].name if task_id in tasks else task_id
        if before is None and after is not None:
            summary = (
                f"{task_name} was inserted by the urgent-task event."
                if task_id in urgent_ids
                else f"{task_name} is new in the repaired scenario."
            )
            classification = "newly added"
            movement = 0
            worker_changed = False
            machine_changed = False
        elif before is not None and after is None:
            summary = (
                f"{task_name} was rejected after the disruption to preserve higher-value work."
            )
            classification = "rejected after disruption"
            movement = 0
            worker_changed = False
            machine_changed = False
        elif before is not None and after is not None:
            classification = labels[task_id]
            movement = abs(after.start_time - before.start_time)
            worker_changed = after.worker_id != before.worker_id
            machine_changed = after.machine_id != before.machine_id
            causes: list[str] = []
            if before.worker_id in outage_workers:
                causes.append(f"worker {before.worker_id} became unavailable")
            if before.machine_id in outage_machines:
                causes.append(f"machine {before.machine_id} broke down")
            if not causes and classification != "unchanged":
                causes.append("the optimizer made room for disrupted or urgent work")
            if after.locked:
                causes = ["the task had already completed or started and was locked"]
            summary = f"{task_name} is {classification}: {'; '.join(causes)}."
        else:
            continue
        explanations.append(
            ScheduleExplanation(
                task_id=task_id,
                classification=classification,
                summary=summary,
                start_time_movement=movement,
                worker_changed=worker_changed,
                machine_changed=machine_changed,
            )
        )
    return explanations
