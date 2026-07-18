"""Four-page Streamlit interface for ResilientOps."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from resilient_ops.domain.models import (
    AvailabilityInterval,
    Machine,
    MachineBreakdown,
    ObjectiveWeights,
    ProblemInstance,
    ScheduleResult,
    SolverConfig,
    Task,
    UrgentTaskArrival,
    Worker,
    WorkerUnavailable,
)
from resilient_ops.domain.validation import (
    ScenarioValidationError,
    parse_problem,
    validate_scenario,
)
from resilient_ops.evaluation.comparison import compare_algorithms
from resilient_ops.evaluation.explanations import explain_repair, explain_schedule
from resilient_ops.evaluation.reporting import schedule_csv, schedule_frame, schedule_json
from resilient_ops.repair.engine import repair_schedule
from resilient_ops.scheduling.baselines import solve_baseline
from resilient_ops.scheduling.cp_sat import solve_cp_sat
from resilient_ops.visualization.gantt import comparison_gantt, gantt_chart, metrics_frame

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "data" / "examples"

st.set_page_config(page_title="ResilientOps", page_icon="🛠️", layout="wide")
st.title("ResilientOps")
st.caption("Optimized maintenance scheduling that adapts when operations change.")


def load_json(raw: bytes) -> None:
    """Validate uploaded bytes and save the scenario in session state."""

    data = json.loads(raw)
    if "scenario" in data:
        data = data["scenario"]
    st.session_state.scenario = parse_problem(data)
    for key in (
        "schedule",
        "repair",
        "comparison",
        "task_editor",
        "worker_editor",
        "machine_editor",
    ):
        st.session_state.pop(key, None)


def current_config() -> SolverConfig:
    """Build settings from session-state controls."""

    return SolverConfig(
        time_limit_seconds=float(st.session_state.get("time_limit", 10.0)),
        weights=ObjectiveWeights(
            weighted_tardiness=int(st.session_state.get("tardiness_weight", 10)),
            rejected_value=int(st.session_state.get("rejection_weight", 20)),
            schedule_change=int(st.session_state.get("change_weight", 5)),
            makespan=int(st.session_state.get("makespan_weight", 1)),
            frozen_horizon=int(st.session_state.get("frozen_horizon", 20)),
        ),
    )


def scenario_frames(
    scenario: ProblemInstance,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build editable tables while keeping list fields human-readable."""

    task_rows = []
    for task in scenario.tasks:
        row = task.model_dump()
        row["predecessor_ids"] = ", ".join(task.predecessor_ids)
        task_rows.append(row)
    worker_rows = []
    for worker in scenario.workers:
        worker_rows.append(
            {
                "id": worker.id,
                "name": worker.name,
                "skills": ", ".join(worker.skills),
                "available_intervals": json.dumps(
                    [item.model_dump() for item in worker.available_intervals]
                ),
            }
        )
    machine_rows = []
    for machine in scenario.machines:
        machine_rows.append(
            {
                "id": machine.id,
                "name": machine.name,
                "machine_type": machine.machine_type,
                "available_intervals": json.dumps(
                    [item.model_dump() for item in machine.available_intervals]
                ),
            }
        )
    return pd.DataFrame(task_rows), pd.DataFrame(worker_rows), pd.DataFrame(machine_rows)


def _optional_text(value: object) -> str | None:
    """Normalize empty data-editor cells to None."""

    if value is None or pd.isna(value) or str(value).strip() == "":
        return None
    return str(value).strip()


def scenario_from_frames(
    original: ProblemInstance,
    task_frame: pd.DataFrame,
    worker_frame: pd.DataFrame,
    machine_frame: pd.DataFrame,
) -> ProblemInstance:
    """Rebuild and validate a scenario from edited tables."""

    tasks = []
    for row in task_frame.to_dict(orient="records"):
        row["required_skill"] = _optional_text(row.get("required_skill"))
        row["required_machine_type"] = _optional_text(row.get("required_machine_type"))
        row["predecessor_ids"] = [
            item.strip() for item in str(row.get("predecessor_ids", "")).split(",") if item.strip()
        ]
        tasks.append(Task.model_validate(row))
    workers = [
        Worker(
            id=str(row["id"]),
            name=str(row["name"]),
            skills=[item.strip() for item in str(row["skills"]).split(",") if item.strip()],
            available_intervals=[
                AvailabilityInterval.model_validate(item)
                for item in json.loads(str(row["available_intervals"]))
            ],
        )
        for row in worker_frame.to_dict(orient="records")
    ]
    machines = [
        Machine(
            id=str(row["id"]),
            name=str(row["name"]),
            machine_type=str(row["machine_type"]),
            available_intervals=[
                AvailabilityInterval.model_validate(item)
                for item in json.loads(str(row["available_intervals"]))
            ],
        )
        for row in machine_frame.to_dict(orient="records")
    ]
    scenario = ProblemInstance(
        name=original.name,
        horizon=original.horizon,
        tasks=tasks,
        workers=workers,
        machines=machines,
    )
    validate_scenario(scenario)
    return scenario


def download_buttons(instance: ProblemInstance, result: ScheduleResult, prefix: str) -> None:
    """Render CSV and JSON result downloads."""

    left, right = st.columns(2)
    left.download_button(
        "Download schedule CSV",
        schedule_csv(instance, result),
        file_name=f"{prefix}-schedule.csv",
        mime="text/csv",
        width="stretch",
    )
    right.download_button(
        "Download full result JSON",
        schedule_json(result),
        file_name=f"{prefix}-result.json",
        mime="application/json",
        width="stretch",
    )


if "scenario" not in st.session_state:
    load_json((EXAMPLES / "small.json").read_bytes())
    st.session_state.auto_loaded = True


page = st.sidebar.radio(
    "Page",
    ["1. Scenario", "2. Generate Schedule", "3. Simulate Disruption", "4. Compare Algorithms"],
)

if page == "1. Scenario":
    st.header("Scenario")
    if st.session_state.pop("auto_loaded", False):
        st.info(
            "The small example was loaded automatically. Edit it below or upload your own JSON."
        )
    example = st.selectbox("Example", ["small.json", "medium.json"])
    left, right = st.columns(2)
    if left.button("Load example", width="stretch"):
        try:
            load_json((EXAMPLES / example).read_bytes())
            st.success("Example loaded and validated.")
        except (OSError, ValueError, ScenarioValidationError) as exc:
            st.error(str(exc))
    upload = right.file_uploader("Or upload JSON", type="json")
    if upload is not None:
        try:
            load_json(upload.getvalue())
            st.success("Upload loaded and validated.")
        except (ValueError, ScenarioValidationError) as exc:
            st.error(str(exc))
    scenario = st.session_state.get("scenario")
    if scenario:
        st.success("Scenario is valid.")
        tabs = st.tabs(["Tasks", "Workers", "Machines"])
        task_frame, worker_frame, machine_frame = scenario_frames(scenario)
        edited_tasks = tabs[0].data_editor(
            task_frame,
            num_rows="dynamic",
            width="stretch",
            key="task_editor",
        )
        edited_workers = tabs[1].data_editor(
            worker_frame,
            num_rows="dynamic",
            width="stretch",
            key="worker_editor",
        )
        edited_machines = tabs[2].data_editor(
            machine_frame,
            num_rows="dynamic",
            width="stretch",
            key="machine_editor",
        )
        st.caption(
            "Separate skills and predecessor IDs with commas. Availability intervals use JSON, "
            'for example [{"start": 0, "end": 24}].'
        )
        if st.button("Validate and apply table edits", type="primary"):
            try:
                st.session_state.scenario = scenario_from_frames(
                    scenario, edited_tasks, edited_workers, edited_machines
                )
                st.session_state.pop("schedule", None)
                st.success("Edits applied. Generate a new schedule on page 2.")
            except (ValueError, TypeError, json.JSONDecodeError, ScenarioValidationError) as exc:
                st.error(f"Could not apply edits: {exc}")

elif page == "2. Generate Schedule":
    st.header("Generate Schedule")
    scenario = st.session_state.get("scenario")
    if not scenario:
        st.info("Load a scenario on page 1 first.")
        st.stop()
    algorithm = st.selectbox(
        "Algorithm",
        ["cp-sat", "edf", "priority", "slack"],
        format_func=lambda value: {
            "cp-sat": "CP-SAT optimizer",
            "edf": "Earliest Deadline First",
            "priority": "Highest Priority First",
            "slack": "Minimum Slack First",
        }[value],
    )
    cols = st.columns(5)
    cols[0].number_input("Tardiness weight", 0, 100, 10, key="tardiness_weight")
    cols[1].number_input("Rejection weight", 0, 100, 20, key="rejection_weight")
    cols[2].number_input("Change weight", 0, 100, 5, key="change_weight")
    cols[3].number_input("Makespan weight", 0, 100, 1, key="makespan_weight")
    cols[4].number_input("Time limit (s)", 0.1, 300.0, 10.0, key="time_limit")
    if st.button("Generate schedule", type="primary"):
        with st.spinner("Scheduling…"):
            st.session_state.schedule = (
                solve_cp_sat(scenario, current_config())
                if algorithm == "cp-sat"
                else solve_baseline(scenario, algorithm)
            )
    result = st.session_state.get("schedule")
    if result:
        status_columns = st.columns(4)
        status_columns[0].metric("Solver status", result.solver_status)
        status_columns[1].metric("Runtime", f"{result.runtime_seconds:.3f}s")
        status_columns[2].metric(
            "On-time rate", f"{100 * result.metrics.on_time_completion_rate:.1f}%"
        )
        status_columns[3].metric(
            "Optimality gap",
            f"{100 * result.relative_gap:.2f}%" if result.relative_gap is not None else "N/A",
        )
        st.plotly_chart(gantt_chart(scenario, result), width="stretch")
        st.dataframe(pd.DataFrame([result.metrics.model_dump()]), width="stretch")
        st.subheader("Schedule table")
        st.dataframe(schedule_frame(scenario, result), width="stretch")
        download_buttons(scenario, result, "resilient-ops")
        explanations = explain_schedule(scenario, result)
        if explanations:
            st.subheader("Why tasks are late or rejected")
            st.dataframe(
                pd.DataFrame([item.model_dump() for item in explanations]),
                width="stretch",
                hide_index=True,
            )
        else:
            st.success("Every accepted task is on time and no optional task was rejected.")
        if result.warnings:
            st.warning("\n".join(result.warnings))

elif page == "3. Simulate Disruption":
    st.header("Simulate Disruption")
    scenario = st.session_state.get("scenario")
    original = st.session_state.get("schedule")
    if not scenario or not original:
        st.info("Load a scenario and generate a schedule first.")
        st.stop()
    event_type = st.selectbox(
        "Event", ["urgent_task_arrival", "worker_unavailable", "machine_breakdown"]
    )
    event_time = st.number_input(
        "Event time", 0, scenario.horizon - 1, min(10, scenario.horizon - 1)
    )
    recovery = min(scenario.horizon, int(event_time) + 12)
    if event_type == "worker_unavailable":
        worker_id = st.selectbox("Worker", [item.id for item in scenario.workers])
        recovery = st.number_input(
            "Recovery time", int(event_time) + 1, scenario.horizon * 2, recovery
        )
        event = WorkerUnavailable(
            event_time=event_time, worker_id=worker_id, recovery_time=recovery
        )
    elif event_type == "machine_breakdown":
        machine_id = st.selectbox("Machine", [item.id for item in scenario.machines])
        recovery = st.number_input(
            "Recovery time", int(event_time) + 1, scenario.horizon * 2, recovery
        )
        event = MachineBreakdown(
            event_time=event_time, machine_id=machine_id, recovery_time=recovery
        )
    else:
        skill = st.selectbox(
            "Required skill",
            sorted({skill for worker in scenario.workers for skill in worker.skills}),
        )
        machine_type = st.selectbox(
            "Machine type", sorted({machine.machine_type for machine in scenario.machines})
        )
        duration = st.number_input("Duration", 1, 24, 3)
        urgent = Task(
            id="URGENT-1",
            name="Urgent repair",
            duration=duration,
            release_time=event_time,
            deadline=int(event_time + duration + 3),
            priority=10,
            value=200,
            required_skill=skill,
            required_machine_type=machine_type,
            predecessor_ids=[],
            mandatory=True,
        )
        event = UrgentTaskArrival(event_time=event_time, task=urgent)
    st.number_input("Frozen horizon", 0, scenario.horizon, 20, key="frozen_horizon")
    if st.button("Repair schedule", type="primary"):
        with st.spinner("Repairing…"):
            disrupted, original_result, repaired = repair_schedule(
                scenario, [event], original, current_config()
            )
            st.session_state.repair = (disrupted, original_result, repaired, [event])
    if "repair" in st.session_state:
        repair_state = st.session_state.repair
        if len(repair_state) == 3:
            disrupted, original_result, repaired = repair_state
            events = []
        else:
            disrupted, original_result, repaired, events = repair_state
        st.plotly_chart(
            comparison_gantt(
                disrupted,
                original_result,
                repaired,
                events=events,
                frozen_horizon=current_config().weights.frozen_horizon,
            ),
            width="stretch",
        )
        st.dataframe(
            metrics_frame({"Original": original_result, "Repaired": repaired}),
            width="stretch",
        )
        st.subheader("What changed and why")
        repair_explanations = explain_repair(disrupted, original_result, repaired, events)
        st.dataframe(
            pd.DataFrame([item.model_dump() for item in repair_explanations]),
            width="stretch",
            hide_index=True,
        )
        download_buttons(disrupted, repaired, "resilient-ops-repaired")

else:
    st.header("Compare Algorithms")
    scenario = st.session_state.get("scenario")
    if not scenario:
        st.info("Load a scenario on page 1 first.")
        st.stop()
    st.number_input("CP-SAT time limit (s)", 0.1, 300.0, 10.0, key="time_limit")
    if st.button("Run comparison", type="primary"):
        with st.spinner("Running four schedulers…"):
            st.session_state.comparison = compare_algorithms(scenario, current_config())
    comparison = st.session_state.get("comparison")
    if comparison:
        frame = metrics_frame(comparison.results)
        st.dataframe(frame, width="stretch")
        st.bar_chart(frame[["weighted_tardiness", "rejected_task_value", "makespan"]])
        st.bar_chart(
            frame[["on_time_completion_rate", "worker_utilization", "machine_utilization"]]
        )
        st.bar_chart(frame[["runtime_seconds", "number_of_changed_tasks"]])
