"""Schedule explanation and export tests."""

from resilient_ops.domain.models import (
    MachineBreakdown,
    ProblemInstance,
    ScheduleAssignment,
    ScheduleResult,
)
from resilient_ops.evaluation.explanations import explain_repair, explain_schedule
from resilient_ops.evaluation.reporting import schedule_csv, schedule_json
from resilient_ops.scheduling.cp_sat import solve_cp_sat


def test_schedule_exports_are_machine_readable(small: ProblemInstance) -> None:
    result = solve_cp_sat(small)
    assert schedule_csv(small, result).startswith(b"task_id,task_name")
    assert b'"solver_status": "OPTIMAL"' in schedule_json(result)


def test_rejected_task_explanation(small: ProblemInstance) -> None:
    result = ScheduleResult(
        algorithm="test",
        assignments=[],
        rejected_task_ids=["T8"],
        solver_status="FEASIBLE",
    )
    explanations = explain_schedule(small, result)
    assert explanations[0].classification == "rejected"
    assert "capacity" in explanations[0].summary


def test_repair_explains_breakdown_reassignment(small: ProblemInstance) -> None:
    original = ScheduleResult(
        algorithm="test",
        assignments=[
            ScheduleAssignment(
                task_id="T3",
                worker_id="W1",
                machine_id="M1",
                start_time=10,
                end_time=15,
            )
        ],
        solver_status="FEASIBLE",
    )
    repaired = ScheduleResult(
        algorithm="test",
        assignments=[
            ScheduleAssignment(
                task_id="T3",
                worker_id="W1",
                machine_id="M1",
                start_time=24,
                end_time=29,
            )
        ],
        solver_status="FEASIBLE",
    )
    explanations = explain_repair(
        small,
        original,
        repaired,
        [MachineBreakdown(event_time=9, machine_id="M1", recovery_time=24)],
    )
    assert explanations[0].classification == "delayed"
    assert "broke down" in explanations[0].summary
