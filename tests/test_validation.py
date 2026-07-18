"""Scenario validation tests."""

from pathlib import Path

import pytest

from resilient_ops.domain.models import Task
from resilient_ops.domain.validation import ScenarioValidationError, load_problem, validate_scenario

ROOT = Path(__file__).resolve().parents[1]


def test_examples_validate() -> None:
    assert load_problem(ROOT / "data/examples/small.json").name
    assert len(load_problem(ROOT / "data/examples/medium.json").tasks) == 25


def test_dependency_cycle_has_useful_path() -> None:
    with pytest.raises(ScenarioValidationError, match=r"T2 -> T5 -> T2"):
        load_problem(ROOT / "data/invalid/cyclic_dependencies.json")


def test_unknown_skill_is_reported(small: object) -> None:
    instance = small
    assert hasattr(instance, "model_copy")
    changed = instance.model_copy(
        update={
            "tasks": [
                instance.tasks[0].model_copy(update={"required_skill": "welding"}),
                *instance.tasks[1:],
            ]
        }
    )
    with pytest.raises(ScenarioValidationError, match="no worker has that skill"):
        validate_scenario(changed)


def test_task_rejects_nonpositive_duration() -> None:
    with pytest.raises(ValueError, match="greater than 0"):
        Task(
            id="X",
            name="Bad",
            duration=0,
            release_time=0,
            deadline=2,
            priority=1,
            value=1,
            predecessor_ids=[],
            mandatory=True,
        )
