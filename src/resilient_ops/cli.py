"""Command-line interface for ResilientOps."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import uvicorn
from pydantic import TypeAdapter

from resilient_ops.domain.models import DisruptionEvent, SolverConfig
from resilient_ops.domain.validation import ScenarioValidationError, load_problem, parse_problem
from resilient_ops.evaluation.comparison import compare_algorithms
from resilient_ops.logging_config import configure_logging
from resilient_ops.repair.engine import repair_schedule
from resilient_ops.scheduling.baselines import solve_baseline
from resilient_ops.scheduling.cp_sat import solve_cp_sat


def _print(data: Any) -> None:
    if hasattr(data, "model_dump"):
        data = data.model_dump(mode="json")
    print(
        json.dumps(
            data,
            indent=2,
            default=lambda value: value.model_dump(mode="json"),
        )
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="resilient-ops", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="validate scenario JSON")
    validate.add_argument("path", type=Path)
    solve = commands.add_parser("solve", help="create a schedule")
    solve.add_argument("path", type=Path)
    solve.add_argument("--solver", choices=["edf", "priority", "slack", "cp-sat"], default="cp-sat")
    solve.add_argument("--time-limit", type=float, default=10.0)
    compare = commands.add_parser("compare", help="compare every algorithm")
    compare.add_argument("path", type=Path)
    compare.add_argument("--time-limit", type=float, default=10.0)
    repair = commands.add_parser("repair", help="repair the scenario/events JSON document")
    repair.add_argument("path", type=Path)
    repair.add_argument("--time-limit", type=float, default=10.0)
    commands.add_parser("api", help="run the FastAPI service")
    commands.add_parser("dashboard", help="run the Streamlit dashboard")
    return parser


def _load_repair(path: Path) -> tuple[Any, list[DisruptionEvent]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "scenario" not in raw or "events" not in raw:
        raise ScenarioValidationError(
            ["Repair JSON must contain top-level 'scenario' and 'events' fields."]
        )
    scenario = parse_problem(raw["scenario"])
    events = TypeAdapter(list[DisruptionEvent]).validate_python(raw["events"])
    return scenario, events


def main(argv: list[str] | None = None) -> int:
    """Run the requested CLI command and return an exit code."""

    configure_logging()
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate":
            scenario = load_problem(args.path)
            _print({"valid": True, "name": scenario.name, "messages": ["Scenario is valid."]})
        elif args.command == "solve":
            scenario = load_problem(args.path)
            config = SolverConfig(time_limit_seconds=args.time_limit)
            result = (
                solve_cp_sat(scenario, config)
                if args.solver == "cp-sat"
                else solve_baseline(scenario, args.solver)
            )
            _print(result)
        elif args.command == "compare":
            scenario = load_problem(args.path)
            _print(compare_algorithms(scenario, SolverConfig(time_limit_seconds=args.time_limit)))
        elif args.command == "repair":
            scenario, events = _load_repair(args.path)
            disrupted, original, repaired = repair_schedule(
                scenario, events, config=SolverConfig(time_limit_seconds=args.time_limit)
            )
            _print({"scenario": disrupted, "original": original, "repaired": repaired})
        elif args.command == "api":
            uvicorn.run("resilient_ops.api.app:app", host="0.0.0.0", port=8000)
        elif args.command == "dashboard":
            return subprocess.call([sys.executable, "-m", "streamlit", "run", "dashboard/app.py"])
    except (OSError, ValueError, ScenarioValidationError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
