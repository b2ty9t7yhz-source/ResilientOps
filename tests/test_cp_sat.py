"""CP-SAT optimization tests."""

from resilient_ops.domain.models import AvailabilityInterval, ProblemInstance
from resilient_ops.scheduling.cp_sat import solve_cp_sat
from resilient_ops.scheduling.feasibility import check_schedule


def test_cp_sat_returns_valid_schedule(small: ProblemInstance) -> None:
    result = solve_cp_sat(small)
    assert result.solver_status in {"OPTIMAL", "FEASIBLE"}
    assert not check_schedule(small, result.assignments, result.rejected_task_ids)
    assert result.objective_value is not None


def test_dependencies_are_respected(small: ProblemInstance) -> None:
    result = solve_cp_sat(small)
    by_task = {item.task_id: item for item in result.assignments}
    for task in small.tasks:
        if task.id not in by_task:
            continue
        for predecessor in task.predecessor_ids:
            assert by_task[predecessor].end_time <= by_task[task.id].start_time


def test_infeasible_instance_returns_clear_status(small: ProblemInstance) -> None:
    unavailable_workers = [
        worker.model_copy(update={"available_intervals": [AvailabilityInterval(start=0, end=1)]})
        for worker in small.workers
    ]
    impossible = small.model_copy(update={"workers": unavailable_workers})
    result = solve_cp_sat(impossible)
    assert result.solver_status == "INFEASIBLE"
    assert not result.assignments
    assert "no feasible schedule" in result.warnings[0].lower()
