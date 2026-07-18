"""Shared objective calculations."""

from resilient_ops.domain.models import ProblemInstance, ScheduleAssignment
from resilient_ops.evaluation.metrics import evaluate_schedule


def test_weighted_tardiness_and_change_metrics(small: ProblemInstance) -> None:
    original = [
        ScheduleAssignment(task_id="T1", worker_id="W2", machine_id=None, start_time=0, end_time=3)
    ]
    moved = [
        ScheduleAssignment(task_id="T1", worker_id="W2", machine_id=None, start_time=7, end_time=10)
    ]
    metrics = evaluate_schedule(small, moved, ["T8"], original)
    assert metrics.weighted_tardiness == 4 * 2
    assert metrics.late_tasks == 1
    assert metrics.number_of_changed_tasks == 1
    assert metrics.total_start_time_movement == 7
    assert metrics.rejected_task_value == 25
