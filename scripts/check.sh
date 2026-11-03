#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ -x ".venv/Scripts/python.exe" ]; then
    PYTHON_BIN=".venv/Scripts/python.exe"
elif [ -x ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v py >/dev/null 2>&1; then
    PYTHON_BIN="py -3"
else
    echo "Error: Python interpreter not found." >&2
    exit 1
fi

export PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}"

echo "==> Running ruff lint check..."
$PYTHON_BIN -m ruff check src tests

echo "==> Running ruff format check..."
$PYTHON_BIN -m ruff format --check src tests

echo "==> Running mypy type check..."
$PYTHON_BIN -m mypy src tests

echo "==> Running pytest with coverage (>=85%, network tests deselected)..."
$PYTHON_BIN -m pytest -q -m "not network" --cov=toolschema_compat --cov-fail-under=85

echo "==> All checks passed!"
