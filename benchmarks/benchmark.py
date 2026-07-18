"""Reproducible scheduler quality and runtime benchmark."""

from __future__ import annotations

import argparse

import pandas as pd

from resilient_ops.domain.models import SolverConfig
from resilient_ops.evaluation.comparison import compare_algorithms
from resilient_ops.generators.synthetic import generate_scenario


def run_benchmark(max_size: int = 50, time_limit: float = 3.0) -> pd.DataFrame:
    """Benchmark standard deterministic instance sizes."""

    rows = []
    for size in [item for item in (8, 25, 50, 100) if item <= max_size]:
        scenario = generate_scenario(
            task_count=size,
            worker_count=max(3, min(12, size // 4)),
            machine_count=max(2, min(8, size // 6)),
            seed=42,
        )
        comparison = compare_algorithms(scenario, SolverConfig(time_limit_seconds=time_limit))
        for algorithm, result in comparison.results.items():
            rows.append(
                {
                    "tasks": size,
                    "algorithm": algorithm,
                    "status": result.solver_status,
                    "runtime_seconds": result.runtime_seconds,
                    "weighted_tardiness": result.metrics.weighted_tardiness,
                    "on_time_rate": result.metrics.on_time_completion_rate,
                    "accepted_value": result.metrics.accepted_task_value,
                    "makespan": result.metrics.makespan,
                    "optimality_gap": result.relative_gap,
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    """Run benchmark and optionally export CSV."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--max-size", type=int, default=50)
    parser.add_argument("--time-limit", type=float, default=3.0)
    parser.add_argument("--output")
    args = parser.parse_args()
    frame = run_benchmark(args.max_size, args.time_limit)
    print(frame.to_string(index=False))
    if args.output:
        frame.to_csv(args.output, index=False)


if __name__ == "__main__":
    main()
