PYTHON ?= python3.12
VENV := .venv
PY := $(VENV)/bin/python
PIP := $(PY) -m pip
SRC_ENV := PYTHONPATH=$(CURDIR)/src

.PHONY: install test quality dashboard api smoke benchmark lock

install:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install '.[dev]'

test:
	$(SRC_ENV) $(PY) -m pytest

quality:
	$(PY) -m ruff check .
	$(SRC_ENV) $(PY) -m mypy src

dashboard:
	$(SRC_ENV) $(PY) -m streamlit run dashboard/app.py

api:
	$(SRC_ENV) $(PY) -m uvicorn resilient_ops.api.app:app --reload

smoke:
	$(SRC_ENV) $(PY) scripts/smoke.py

benchmark:
	$(SRC_ENV) $(PY) benchmarks/benchmark.py

lock:
	$(PIP) freeze --exclude-editable --exclude resilient-ops > requirements.lock
