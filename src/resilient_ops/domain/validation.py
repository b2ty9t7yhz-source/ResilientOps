"""Cross-record validation and JSON loading."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from resilient_ops.domain.models import ProblemInstance


class ScenarioValidationError(ValueError):
    """Raised when a scenario is structurally valid JSON but is not schedulable."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("\n".join(errors))


def _duplicates(values: list[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def _find_cycle(instance: ProblemInstance) -> list[str] | None:
    graph = {task.id: task.predecessor_ids for task in instance.tasks}
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        if node in visiting:
            start = stack.index(node)
            return [*stack[start:], node]
        if node in visited:
            return None
        visiting.add(node)
        stack.append(node)
        for predecessor in graph.get(node, []):
            cycle = visit(predecessor)
            if cycle:
                return cycle
        stack.pop()
        visiting.remove(node)
        visited.add(node)
        return None

    for task_id in graph:
        cycle = visit(task_id)
        if cycle:
            return cycle
    return None


def _intervals_overlap(intervals: list[tuple[int, int]]) -> bool:
    ordered = sorted(intervals)
    return any(
        current[0] < previous[1] for previous, current in zip(ordered, ordered[1:], strict=False)
    )


def validate_scenario(instance: ProblemInstance) -> list[str]:
    """Validate identifiers, dependencies, resource coverage, and availability."""

    errors: list[str] = []
    task_ids = [task.id for task in instance.tasks]
    worker_ids = [worker.id for worker in instance.workers]
    machine_ids = [machine.id for machine in instance.machines]
    for label, values in (("task", task_ids), ("worker", worker_ids), ("machine", machine_ids)):
        duplicates = _duplicates(values)
        if duplicates:
            errors.append(f"Duplicate {label} IDs: {', '.join(sorted(duplicates))}.")

    known_tasks = set(task_ids)
    for task in instance.tasks:
        unknown = sorted(set(task.predecessor_ids) - known_tasks)
        if unknown:
            errors.append(f"Task {task.id} references unknown predecessors: {', '.join(unknown)}.")
        if (
            task.mandatory
            and task.required_skill
            and not any(task.required_skill in worker.skills for worker in instance.workers)
        ):
            errors.append(
                f"Task {task.id} requires skill {task.required_skill}, "
                "but no worker has that skill."
            )
        if (
            task.mandatory
            and task.required_machine_type
            and not any(
                task.required_machine_type == machine.machine_type for machine in instance.machines
            )
        ):
            errors.append(
                f"Task {task.id} requires machine type {task.required_machine_type}, "
                "but no matching machine exists."
            )

    cycle = _find_cycle(instance)
    if cycle:
        errors.append(f"Dependency cycle detected: {' -> '.join(cycle)}.")

    for worker in instance.workers:
        intervals = [(item.start, item.end) for item in worker.available_intervals]
        if _intervals_overlap(intervals):
            errors.append(f"Resource {worker.id} has overlapping availability intervals.")
    for machine in instance.machines:
        intervals = [(item.start, item.end) for item in machine.available_intervals]
        if _intervals_overlap(intervals):
            errors.append(f"Resource {machine.id} has overlapping availability intervals.")

    if errors:
        raise ScenarioValidationError(errors)
    return ["Scenario is valid."]


def parse_problem(data: dict[str, Any]) -> ProblemInstance:
    """Parse and cross-validate a problem dictionary."""

    try:
        instance = ProblemInstance.model_validate(data)
    except ValidationError as exc:
        messages = [
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        ]
        raise ScenarioValidationError(messages) from exc
    validate_scenario(instance)
    return instance


def load_problem(path: str | Path) -> ProblemInstance:
    """Load and validate a scenario from a JSON file."""

    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScenarioValidationError([f"Could not read valid JSON from {source}: {exc}"]) from exc
    if not isinstance(data, dict):
        raise ScenarioValidationError(["Top-level JSON value must be an object."])
    return parse_problem(data)
