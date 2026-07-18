"""Run all algorithms against one scenario."""

from __future__ import annotations

from resilient_ops.domain.models import ComparisonResult, ProblemInstance, SolverConfig
from resilient_ops.scheduling.baselines import solve_baseline
from resilient_ops.scheduling.cp_sat import solve_cp_sat


def compare_algorithms(
    instance: ProblemInstance, config: SolverConfig | None = None
) -> ComparisonResult:
    """Evaluate the three baselines and CP-SAT using shared metrics."""

    return ComparisonResult(
        results={
            "Earliest Deadline First": solve_baseline(instance, "edf"),
            "Highest Priority First": solve_baseline(instance, "priority"),
            "Minimum Slack First": solve_baseline(instance, "slack"),
            "CP-SAT": solve_cp_sat(instance, config),
        }
    )
