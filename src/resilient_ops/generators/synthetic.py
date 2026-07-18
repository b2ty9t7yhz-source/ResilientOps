"""Deterministic synthetic maintenance scenario generator."""

from __future__ import annotations

import random

from resilient_ops.domain.models import (
    AvailabilityInterval,
    Machine,
    ProblemInstance,
    Task,
    Worker,
)


def generate_scenario(
    task_count: int = 25,
    worker_count: int = 6,
    machine_count: int = 4,
    seed: int = 42,
) -> ProblemInstance:
    """Generate a reproducible, feasible-looking maintenance scenario."""

    if min(task_count, worker_count, machine_count) <= 0:
        raise ValueError("task_count, worker_count, and machine_count must be positive")
    rng = random.Random(seed)
    skills = ["electrical", "mechanical", "inspection"]
    machine_types = ["lift", "diagnostic"]
    horizon = max(80, task_count * 6)
    availability = [AvailabilityInterval(start=0, end=horizon)]
    workers = [
        Worker(
            id=f"W{index + 1}",
            name=f"Technician {index + 1}",
            skills=[skills[index % len(skills)], skills[(index + 1) % len(skills)]],
            available_intervals=availability,
        )
        for index in range(worker_count)
    ]
    machines = [
        Machine(
            id=f"M{index + 1}",
            name=f"Machine {index + 1}",
            machine_type=machine_types[index % len(machine_types)],
            available_intervals=availability,
        )
        for index in range(machine_count)
    ]
    tasks: list[Task] = []
    for index in range(task_count):
        duration = rng.randint(2, 7)
        release = rng.randint(0, min(30, index * 2))
        predecessors = [f"T{index}"] if index and index % 4 == 0 else []
        tasks.append(
            Task(
                id=f"T{index + 1}",
                name=f"Maintenance task {index + 1}",
                duration=duration,
                release_time=release,
                deadline=min(horizon - 1, release + duration + rng.randint(8, 30)),
                priority=rng.randint(1, 5),
                value=rng.randint(10, 100),
                required_skill=skills[index % len(skills)],
                required_machine_type=machine_types[index % len(machine_types)]
                if index % 3 != 2
                else None,
                predecessor_ids=predecessors,
                mandatory=index % 7 != 6,
            )
        )
    return ProblemInstance(
        name=f"Synthetic maintenance scenario ({task_count} tasks)",
        horizon=horizon,
        tasks=tasks,
        workers=workers,
        machines=machines,
    )
