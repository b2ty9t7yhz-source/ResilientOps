"""End-to-end smoke checks for examples, solver, repair, and API."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from resilient_ops.api.app import app
from resilient_ops.domain.models import DisruptionEvent
from resilient_ops.domain.validation import load_problem, parse_problem
from resilient_ops.repair.engine import repair_schedule
from resilient_ops.scheduling.cp_sat import solve_cp_sat

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    """Fail fast when any user-visible workflow is broken."""

    small = load_problem(ROOT / "data/examples/small.json")
    schedule = solve_cp_sat(small)
    assert schedule.solver_status in {"OPTIMAL", "FEASIBLE"}
    raw = json.loads((ROOT / "data/examples/disruption.json").read_text())
    disruption = parse_problem(raw["scenario"])
    events = TypeAdapter(list[DisruptionEvent]).validate_python(raw["events"])
    _, _, repaired = repair_schedule(disruption, events)
    assert repaired.solver_status in {"OPTIMAL", "FEASIBLE"}
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}
    response = client.post(
        "/solve",
        json={"scenario": small.model_dump(mode="json"), "algorithm": "cp-sat"},
    )
    assert response.status_code == 200
    print(
        "Smoke check passed:",
        len(schedule.assignments),
        "original assignments and",
        len(repaired.assignments),
        "repaired assignments.",
    )


if __name__ == "__main__":
    main()
