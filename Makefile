.PHONY: setup app discover replay replay-not-found handoff test eval model-eval lint typecheck console

UV ?= uv
PY := $(UV) run

setup:
	$(UV) sync --all-extras
	$(PY) playwright install chromium

app:
	$(PY) uvicorn demo.legacy_bank.app:app --host 127.0.0.1 --port 8765

console:
	$(PY) python -m zimam.cli console

discover:
	$(PY) python -m zimam.cli discover --member-id 10001 --tenant pine

replay:
	$(PY) python -m zimam.cli replay --member-id 10002 --tenant pine

replay-not-found:
	$(PY) python -m zimam.cli replay --member-id 99999 --tenant pine

handoff:
	$(PY) python -m zimam.cli handoff

test:
	$(PY) pytest tests/unit tests/integration tests/evals

eval:
	$(PY) python -m zimam.cli evals

model-eval:
	$(PY) python -m zimam.cli qualify

lint:
	$(PY) ruff check src demo operator_console tests
	$(PY) ruff format --check src demo operator_console tests

format:
	$(PY) ruff check --fix src demo operator_console tests
	$(PY) ruff format src demo operator_console tests

typecheck:
	$(PY) pyright src demo operator_console tests
