"""HTTP API backed by the core scheduling package."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import Field

from resilient_ops.domain.models import (
    Algorithm,
    ComparisonResult,
    DisruptionEvent,
    ProblemInstance,
    RepairRequest,
    ScheduleResult,
    SolverConfig,
    StrictModel,
)
from resilient_ops.domain.validation import (
    ScenarioValidationError,
    parse_problem,
    validate_scenario,
)
from resilient_ops.evaluation.comparison import compare_algorithms
from resilient_ops.logging_config import configure_logging
from resilient_ops.repair.engine import repair_schedule
from resilient_ops.scheduling.baselines import solve_baseline
from resilient_ops.scheduling.cp_sat import solve_cp_sat


class SolveRequest(StrictModel):
    """API solve payload."""

    scenario: ProblemInstance
    algorithm: Algorithm = "cp-sat"
    config: SolverConfig = Field(default_factory=SolverConfig)


class CompareRequest(StrictModel):
    """API comparison payload."""

    scenario: ProblemInstance
    config: SolverConfig = Field(default_factory=SolverConfig)


class RepairResponse(StrictModel):
    """API repair output containing both schedules."""

    scenario: ProblemInstance
    original: ScheduleResult
    repaired: ScheduleResult


configure_logging()

app = FastAPI(
    title="ResilientOps API",
    version="0.1.0",
    description="Maintenance scheduling and disruption repair powered by CP-SAT.",
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next: Any) -> Response:
    """Attach a correlation ID to every API response."""

    request_id = request.headers.get("x-request-id", str(uuid4()))
    response: Response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response


def _validated(instance: ProblemInstance) -> ProblemInstance:
    try:
        validate_scenario(instance)
    except ScenarioValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors) from exc
    return instance


@app.get("/health")
def health() -> dict[str, str]:
    """Return service health."""

    return {"status": "ok"}


@app.post("/validate")
def validate(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate raw scenario JSON and return useful errors."""

    try:
        scenario = parse_problem(payload)
    except ScenarioValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors) from exc
    return {"valid": True, "messages": ["Scenario is valid."], "scenario": scenario}


@app.post("/solve", response_model=ScheduleResult)
def solve(request: SolveRequest) -> ScheduleResult:
    """Run one selected scheduling algorithm."""

    scenario = _validated(request.scenario)
    if request.algorithm == "cp-sat":
        return solve_cp_sat(scenario, request.config)
    return solve_baseline(scenario, request.algorithm)


@app.post("/repair", response_model=RepairResponse)
def repair(request: RepairRequest) -> RepairResponse:
    """Apply disruption events and repair a schedule."""

    try:
        disrupted, original, repaired = repair_schedule(
            _validated(request.scenario), request.events, request.original_schedule, request.config
        )
    except (ValueError, ScenarioValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return RepairResponse(scenario=disrupted, original=original, repaired=repaired)


@app.post("/compare", response_model=ComparisonResult)
def compare(request: CompareRequest) -> ComparisonResult:
    """Compare the baselines with CP-SAT."""

    return compare_algorithms(_validated(request.scenario), request.config)


__all__ = ["DisruptionEvent", "app"]
