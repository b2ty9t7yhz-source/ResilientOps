"""Shared pytest fixtures."""

from pathlib import Path

import pytest

from resilient_ops.domain.models import ProblemInstance
from resilient_ops.domain.validation import load_problem

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def small() -> ProblemInstance:
    """Load the manually verifiable small example."""

    return load_problem(ROOT / "data" / "examples" / "small.json")
