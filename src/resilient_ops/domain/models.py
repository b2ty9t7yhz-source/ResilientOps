"""Typed domain and result models used by every interface."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    """Base model that rejects unknown JSON fields."""

    model_config = ConfigDict(extra="forbid")


class AvailabilityInterval(StrictModel):
    """Half-open resource availability interval ``[start, end)``."""

    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @model_validator(mode="after")
    def ordered(self) -> AvailabilityInterval:
        if self.end <= self.start:
            raise ValueError("availability interval end must be greater than start")
        return self


class Task(StrictModel):
    """A maintenance task to schedule."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    duration: int = Field(gt=0)
    release_time: int = Field(ge=0)
    deadline: int = Field(gt=0)
    priority: int = Field(ge=1)
    value: int = Field(ge=0)
    required_skill: str | None = None
    required_machine_type: str | None = None
    predecessor_ids: list[str] = Field(default_factory=list)
    mandatory: bool = True

    @model_validator(mode="after")
    def sensible_times(self) -> Task:
        if self.deadline <= self.release_time:
            raise ValueError("deadline must be greater than release_time")
        if self.id in self.predecessor_ids:
            raise ValueError(f"task {self.id} cannot depend on itself")
        return self


class Worker(StrictModel):
    """A worker with skills and availability."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    skills: list[str]
    available_intervals: list[AvailabilityInterval]


class Machine(StrictModel):
    """A machine with a type and availability."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    machine_type: str = Field(min_length=1)
    available_intervals: list[AvailabilityInterval]


class ProblemInstance(StrictModel):
    """A validated scheduling scenario."""

    name: str = "ResilientOps scenario"
    horizon: int = Field(gt=0)
    tasks: list[Task] = Field(min_length=1)
    workers: list[Worker]
    machines: list[Machine]


class ScheduleAssignment(StrictModel):
    """A scheduled task and its selected resources."""

    task_id: str
    worker_id: str | None
    machine_id: str | None
    start_time: int = Field(ge=0)
    end_time: int = Field(gt=0)
    status: Literal["planned", "in_progress", "completed"] = "planned"
    locked: bool = False

    @model_validator(mode="after")
    def valid_span(self) -> ScheduleAssignment:
        if self.end_time <= self.start_time:
            raise ValueError("assignment end_time must be greater than start_time")
        return self


class ObjectiveWeights(StrictModel):
    """Configurable integer CP-SAT objective weights."""

    weighted_tardiness: int = Field(default=10, ge=0)
    rejected_value: int = Field(default=20, ge=0)
    schedule_change: int = Field(default=5, ge=0)
    makespan: int = Field(default=1, ge=0)
    moved_task: int = Field(default=2, ge=0)
    worker_change: int = Field(default=4, ge=0)
    machine_change: int = Field(default=4, ge=0)
    previously_accepted_rejection: int = Field(default=10, ge=0)
    frozen_horizon: int = Field(default=20, ge=0)


class SolverConfig(StrictModel):
    """Solver controls shared by CLI, API, and dashboard."""

    time_limit_seconds: float = Field(default=10.0, gt=0, le=300)
    random_seed: int = 42
    num_workers: int = Field(default=1, ge=1)
    weights: ObjectiveWeights = Field(default_factory=ObjectiveWeights)


class ObjectiveMetrics(StrictModel):
    """Common schedule quality measurements."""

    weighted_tardiness: int = 0
    late_tasks: int = 0
    on_time_completion_rate: float = 0.0
    accepted_task_value: int = 0
    rejected_task_value: int = 0
    worker_utilization: float = 0.0
    machine_utilization: float = 0.0
    makespan: int = 0
    number_of_changed_tasks: int = 0
    total_start_time_movement: int = 0


class ScheduleResult(StrictModel):
    """Normalized output returned by all scheduling algorithms."""

    algorithm: str
    assignments: list[ScheduleAssignment] = Field(default_factory=list)
    rejected_task_ids: list[str] = Field(default_factory=list)
    metrics: ObjectiveMetrics = Field(default_factory=ObjectiveMetrics)
    runtime_seconds: float = 0.0
    solver_status: str
    objective_value: float | None = None
    best_objective_bound: float | None = None
    relative_gap: float | None = None
    warnings: list[str] = Field(default_factory=list)
    validation_results: list[str] = Field(default_factory=list)


class UrgentTaskArrival(StrictModel):
    """A high-priority task introduced at the event time."""

    event_type: Literal["urgent_task_arrival"] = "urgent_task_arrival"
    event_time: int = Field(ge=0)
    task: Task


class WorkerUnavailable(StrictModel):
    """A worker absence over a half-open interval."""

    event_type: Literal["worker_unavailable"] = "worker_unavailable"
    event_time: int = Field(ge=0)
    worker_id: str
    recovery_time: int

    @model_validator(mode="after")
    def recovery_after_event(self) -> WorkerUnavailable:
        if self.recovery_time <= self.event_time:
            raise ValueError("recovery_time must be after event_time")
        return self


class MachineBreakdown(StrictModel):
    """A machine outage over a half-open interval."""

    event_type: Literal["machine_breakdown"] = "machine_breakdown"
    event_time: int = Field(ge=0)
    machine_id: str
    recovery_time: int

    @model_validator(mode="after")
    def recovery_after_event(self) -> MachineBreakdown:
        if self.recovery_time <= self.event_time:
            raise ValueError("recovery_time must be after event_time")
        return self


DisruptionEvent = Annotated[
    UrgentTaskArrival | WorkerUnavailable | MachineBreakdown,
    Field(discriminator="event_type"),
]
Algorithm = Literal["edf", "priority", "slack", "cp-sat"]


class RepairRequest(StrictModel):
    """Inputs required to repair an existing schedule."""

    scenario: ProblemInstance
    original_schedule: ScheduleResult | None = None
    events: list[DisruptionEvent]
    config: SolverConfig = Field(default_factory=SolverConfig)


class ComparisonResult(StrictModel):
    """Results for multiple algorithms on the same scenario."""

    results: dict[str, ScheduleResult]


class ScheduleExplanation(StrictModel):
    """Human-readable explanation for a scheduled, moved, or rejected task."""

    task_id: str
    classification: str
    summary: str
    start_time_movement: int = 0
    worker_changed: bool = False
    machine_changed: bool = False
