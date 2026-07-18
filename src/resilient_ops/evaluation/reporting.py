"""Tabular and serialized exports for schedules."""

from __future__ import annotations

import json
from typing import cast

import pandas as pd

from resilient_ops.domain.models import ProblemInstance, ScheduleResult


def schedule_frame(instance: ProblemInstance, result: ScheduleResult) -> pd.DataFrame:
    """Build a stable, export-ready schedule table."""

    tasks = {task.id: task for task in instance.tasks}
    rows = []
    for assignment in result.assignments:
        task = tasks[assignment.task_id]
        rows.append(
            {
                "task_id": task.id,
                "task_name": task.name,
                "start_time": assignment.start_time,
                "end_time": assignment.end_time,
                "deadline": task.deadline,
                "tardiness": max(0, assignment.end_time - task.deadline),
                "worker_id": assignment.worker_id,
                "machine_id": assignment.machine_id,
                "status": assignment.status,
                "locked": assignment.locked,
                "priority": task.priority,
                "value": task.value,
            }
        )
    return pd.DataFrame(rows)


def schedule_csv(instance: ProblemInstance, result: ScheduleResult) -> bytes:
    """Serialize a result as UTF-8 CSV bytes."""

    content = cast(str, schedule_frame(instance, result).to_csv(index=False))
    return content.encode("utf-8")


def schedule_json(result: ScheduleResult) -> bytes:
    """Serialize the complete result as formatted JSON bytes."""

    return json.dumps(result.model_dump(mode="json"), indent=2).encode("utf-8")
