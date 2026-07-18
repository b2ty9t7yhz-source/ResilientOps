"""Dynamic schedule-repair tests."""

from resilient_ops.domain.models import (
    MachineBreakdown,
    ProblemInstance,
    Task,
    UrgentTaskArrival,
    WorkerUnavailable,
)
from resilient_ops.repair.engine import repair_schedule
from resilient_ops.repair.events import apply_event
from resilient_ops.scheduling.cp_sat import solve_cp_sat


def test_all_event_types_apply(small: ProblemInstance) -> None:
    worker_event = WorkerUnavailable(event_time=5, worker_id="W1", recovery_time=12)
    machine_event = MachineBreakdown(event_time=5, machine_id="M1", recovery_time=12)
    worker_changed = apply_event(small, worker_event)
    machine_changed = apply_event(small, machine_event)
    assert worker_changed.workers[0].available_intervals != small.workers[0].available_intervals
    assert machine_changed.machines[0].available_intervals != small.machines[0].available_intervals


def test_urgent_task_is_added_and_scheduled(small: ProblemInstance) -> None:
    original = solve_cp_sat(small)
    urgent = Task(
        id="URGENT",
        name="Urgent electrical repair",
        duration=2,
        release_time=5,
        deadline=12,
        priority=10,
        value=200,
        required_skill="electrical",
        required_machine_type="diagnostic",
        predecessor_ids=[],
        mandatory=True,
    )
    disrupted, _, repaired = repair_schedule(
        small, [UrgentTaskArrival(event_time=5, task=urgent)], original
    )
    assert len(disrupted.tasks) == len(small.tasks) + 1
    assert "URGENT" in {item.task_id for item in repaired.assignments}


def test_locked_tasks_remain_unchanged(small: ProblemInstance) -> None:
    original = solve_cp_sat(small)
    first = min(original.assignments, key=lambda item: item.start_time)
    event_time = first.start_time + 1
    event = MachineBreakdown(
        event_time=event_time,
        machine_id="M1",
        recovery_time=min(small.horizon, event_time + 8),
    )
    _, _, repaired = repair_schedule(small, [event], original)
    repaired_by_task = {item.task_id: item for item in repaired.assignments}
    for assignment in original.assignments:
        if assignment.start_time < event_time:
            assert repaired_by_task[assignment.task_id].start_time == assignment.start_time
            assert repaired_by_task[assignment.task_id].worker_id == assignment.worker_id
            assert repaired_by_task[assignment.task_id].machine_id == assignment.machine_id
            assert repaired_by_task[assignment.task_id].locked
