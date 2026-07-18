"""Pure functions that apply disruption events to scenarios."""

from __future__ import annotations

from resilient_ops.domain.models import (
    AvailabilityInterval,
    DisruptionEvent,
    MachineBreakdown,
    ProblemInstance,
    UrgentTaskArrival,
    WorkerUnavailable,
)


class DisruptionError(ValueError):
    """Raised when a disruption references unknown or invalid data."""


def _subtract_outage(
    intervals: list[AvailabilityInterval], outage_start: int, outage_end: int
) -> list[AvailabilityInterval]:
    result: list[AvailabilityInterval] = []
    for interval in intervals:
        if outage_end <= interval.start or interval.end <= outage_start:
            result.append(interval)
            continue
        if interval.start < outage_start:
            result.append(AvailabilityInterval(start=interval.start, end=outage_start))
        if outage_end < interval.end:
            result.append(AvailabilityInterval(start=outage_end, end=interval.end))
    return result


def apply_event(instance: ProblemInstance, event: DisruptionEvent) -> ProblemInstance:
    """Return a copy of an instance with one event applied."""

    if isinstance(event, UrgentTaskArrival):
        if any(task.id == event.task.id for task in instance.tasks):
            raise DisruptionError(f"Urgent task ID {event.task.id} already exists.")
        task = event.task
        if task.release_time < event.event_time:
            task = task.model_copy(update={"release_time": event.event_time})
        if task.deadline <= task.release_time:
            raise DisruptionError(
                f"Urgent task {task.id} deadline must be after its event-adjusted release time."
            )
        return instance.model_copy(
            update={
                "tasks": [*instance.tasks, task],
                "horizon": max(instance.horizon, task.deadline + task.duration),
            }
        )
    if isinstance(event, WorkerUnavailable):
        found = False
        updated = []
        for worker in instance.workers:
            if worker.id != event.worker_id:
                updated.append(worker)
                continue
            found = True
            updated.append(
                worker.model_copy(
                    update={
                        "available_intervals": _subtract_outage(
                            worker.available_intervals, event.event_time, event.recovery_time
                        )
                    }
                )
            )
        if not found:
            raise DisruptionError(f"Unknown worker {event.worker_id}.")
        return instance.model_copy(
            update={"workers": updated, "horizon": max(instance.horizon, event.recovery_time)}
        )
    if isinstance(event, MachineBreakdown):
        found = False
        updated_machines = []
        for machine in instance.machines:
            if machine.id != event.machine_id:
                updated_machines.append(machine)
                continue
            found = True
            updated_machines.append(
                machine.model_copy(
                    update={
                        "available_intervals": _subtract_outage(
                            machine.available_intervals, event.event_time, event.recovery_time
                        )
                    }
                )
            )
        if not found:
            raise DisruptionError(f"Unknown machine {event.machine_id}.")
        return instance.model_copy(
            update={
                "machines": updated_machines,
                "horizon": max(instance.horizon, event.recovery_time),
            }
        )
    raise DisruptionError(f"Unsupported disruption event: {event}")


def apply_events(instance: ProblemInstance, events: list[DisruptionEvent]) -> ProblemInstance:
    """Apply disruptions in chronological input order."""

    updated = instance
    for event in sorted(events, key=lambda item: item.event_time):
        updated = apply_event(updated, event)
    return updated
