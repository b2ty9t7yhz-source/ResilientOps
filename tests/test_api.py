"""FastAPI integration tests."""

from fastapi.testclient import TestClient

from resilient_ops.api.app import app
from resilient_ops.domain.models import ProblemInstance

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health", headers={"x-request-id": "test-request"})
    assert response.json() == {"status": "ok"}
    assert response.headers["x-request-id"] == "test-request"


def test_validate_and_solve(small: ProblemInstance) -> None:
    payload = small.model_dump(mode="json")
    assert client.post("/validate", json=payload).status_code == 200
    response = client.post("/solve", json={"scenario": payload, "algorithm": "edf"})
    assert response.status_code == 200
    assert response.json()["solver_status"] == "FEASIBLE"


def test_compare_endpoint(small: ProblemInstance) -> None:
    response = client.post("/compare", json={"scenario": small.model_dump(mode="json")})
    assert response.status_code == 200
    assert set(response.json()["results"]) == {
        "Earliest Deadline First",
        "Highest Priority First",
        "Minimum Slack First",
        "CP-SAT",
    }


def test_repair_endpoint(small: ProblemInstance) -> None:
    payload = {
        "scenario": small.model_dump(mode="json"),
        "events": [
            {
                "event_type": "worker_unavailable",
                "event_time": 10,
                "worker_id": "W1",
                "recovery_time": 18,
            }
        ],
    }
    response = client.post("/repair", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["original"]["solver_status"] in {"OPTIMAL", "FEASIBLE"}
    assert body["repaired"]["solver_status"] in {"OPTIMAL", "FEASIBLE"}
