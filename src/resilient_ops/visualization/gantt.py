"""Accessible Plotly schedule and comparison charts."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from resilient_ops.domain.models import (
    DisruptionEvent,
    MachineBreakdown,
    ProblemInstance,
    ScheduleResult,
    WorkerUnavailable,
)
from resilient_ops.repair.stability import classify_changes

if TYPE_CHECKING:
    from plotly.basedatatypes import BaseFigure


STATUS_PATTERNS = {"planned": "", "in_progress": "/", "completed": "x"}


def _add_schedule(
    figure: go.Figure,
    instance: ProblemInstance,
    result: ScheduleResult,
    row: int | None = None,
    labels: dict[str, str] | None = None,
) -> None:
    tasks = {task.id: task for task in instance.tasks}
    for assignment in result.assignments:
        task = tasks[assignment.task_id]
        late = assignment.end_time > task.deadline
        change = labels.get(task.id, "") if labels else ""
        text = " | ".join(
            item
            for item in [
                f"{task.id}: {assignment.status}",
                "LATE" if late else "on time",
                change,
                f"W={assignment.worker_id or 'none'}",
                f"M={assignment.machine_id or 'none'}",
            ]
            if item
        )
        kwargs = {"row": row, "col": 1} if row is not None else {}
        figure.add_trace(
            go.Bar(
                x=[assignment.end_time - assignment.start_time],
                base=[assignment.start_time],
                y=[task.name],
                orientation="h",
                name=assignment.status,
                legendgroup=assignment.status,
                showlegend=not any(trace.name == assignment.status for trace in figure.data),
                marker={
                    "color": "#d62728" if late else "#2a6fbb",
                    "pattern": {"shape": STATUS_PATTERNS[assignment.status]},
                    "line": {"color": "#222", "width": 1},
                },
                text=[text],
                textposition="inside",
                hovertemplate=f"{text}<br>Start %{{base}}<br>Duration %{{x}}<extra></extra>",
            ),
            **kwargs,
        )
        figure.add_vline(x=task.deadline, line_dash="dot", line_color="#555", **kwargs)


def _add_event_overlays(
    figure: go.Figure,
    events: list[DisruptionEvent],
    frozen_horizon: int,
    row: int | None = None,
) -> None:
    """Add labeled event, outage, and frozen-horizon regions."""

    kwargs = {"row": row, "col": 1} if row is not None else {}
    for index, event in enumerate(events):
        figure.add_vline(
            x=event.event_time,
            line_dash="dash",
            line_color="#111",
            annotation_text="EVENT" if index == 0 else None,
            **kwargs,
        )
        if isinstance(event, (WorkerUnavailable, MachineBreakdown)):
            resource = (
                f"Worker {event.worker_id} unavailable"
                if isinstance(event, WorkerUnavailable)
                else f"Machine {event.machine_id} breakdown"
            )
            figure.add_vrect(
                x0=event.event_time,
                x1=event.recovery_time,
                fillcolor="#d62728",
                opacity=0.12,
                line_width=1,
                line_dash="dot",
                annotation_text=resource,
                annotation_position="top left",
                **kwargs,
            )
    if events and frozen_horizon:
        event_time = max(event.event_time for event in events)
        figure.add_vrect(
            x0=event_time,
            x1=event_time + frozen_horizon,
            fillcolor="#f2c94c",
            opacity=0.10,
            line_width=0,
            annotation_text="Frozen horizon (soft)",
            annotation_position="bottom left",
            **kwargs,
        )


def gantt_chart(
    instance: ProblemInstance,
    result: ScheduleResult,
    events: list[DisruptionEvent] | None = None,
    frozen_horizon: int = 0,
) -> BaseFigure:
    """Create a Gantt chart with status patterns, labels, and deadline markers."""

    figure = go.Figure()
    _add_schedule(figure, instance, result)
    _add_event_overlays(figure, events or [], frozen_horizon)
    figure.update_layout(
        title=f"{instance.name} — {result.algorithm}",
        barmode="overlay",
        xaxis_title="Time unit (dotted lines are deadlines)",
        yaxis_title="Task",
        height=max(450, 45 * len(result.assignments)),
        template="plotly_white",
    )
    return figure


def comparison_gantt(
    instance: ProblemInstance,
    original: ScheduleResult,
    repaired: ScheduleResult,
    events: list[DisruptionEvent] | None = None,
    frozen_horizon: int = 0,
) -> BaseFigure:
    """Show original and repaired schedules in separate labeled panels."""

    figure = make_subplots(
        rows=2, cols=1, shared_xaxes=True, subplot_titles=("Original", "Repaired")
    )
    labels = classify_changes(original.assignments, repaired.assignments)
    _add_schedule(figure, instance, original, row=1)
    _add_schedule(figure, instance, repaired, row=2, labels=labels)
    _add_event_overlays(figure, events or [], frozen_horizon, row=2)
    figure.update_layout(
        title="Original versus repaired schedule",
        barmode="overlay",
        height=max(700, 65 * len(repaired.assignments)),
        template="plotly_white",
    )
    figure.update_xaxes(title_text="Time unit")
    return figure


def metrics_frame(results: dict[str, ScheduleResult]) -> pd.DataFrame:
    """Create a presentation-friendly algorithm comparison table."""

    rows = []
    for name, result in results.items():
        row = result.metrics.model_dump()
        row.update(
            {
                "algorithm": name,
                "runtime_seconds": result.runtime_seconds,
                "solver_status": result.solver_status,
            }
        )
        rows.append(row)
    return pd.DataFrame(rows).set_index("algorithm")
