"""Greedy scheduler behavior."""

import pytest

from resilient_ops.domain.models import ProblemInstance
from resilient_ops.scheduling.baselines import solve_baseline
from resilient_ops.scheduling.feasibility import check_schedule


@pytest.mark.parametrize("algorithm", ["edf", "priority", "slack"])
def test_baseline_is_feasible(small: ProblemInstance, algorithm: str) -> None:
    result = solve_baseline(small, algorithm)
    assert result.solver_status == "FEASIBLE"
    assert not check_schedule(small, result.assignments, result.rejected_task_ids)
    assert {task.id for task in small.tasks if task.mandatory} <= {
        assignment.task_id for assignment in result.assignments
    }


def test_baseline_is_deterministic(small: ProblemInstance) -> None:
    first = solve_baseline(small, "edf")
    second = solve_baseline(small, "edf")
    assert first.assignments == second.assignments
    assert first.rejected_task_ids == second.rejected_task_ids


def test_skill_and_machine_compatibility(small: ProblemInstance) -> None:
    result = solve_baseline(small, "priority")
    tasks = {task.id: task for task in small.tasks}
    workers = {worker.id: worker for worker in small.workers}
    machines = {machine.id: machine for machine in small.machines}
    for assignment in result.assignments:
        task = tasks[assignment.task_id]
        if task.required_skill:
            assert task.required_skill in workers[assignment.worker_id or ""].skills
        if task.required_machine_type:
            assert machines[assignment.machine_id or ""].machine_type == task.required_machine_type
