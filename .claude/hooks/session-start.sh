#!/bin/bash
# Installs TradeCC's Python dependencies so tests run in a fresh web session.
#
# Deliberately narrow: this installs the project and its dev extras and
# nothing else. It does not create wallets, fetch credentials, or install
# unrelated tooling — a script that runs automatically at every session
# start is the wrong place for anything that touches money or keys.
set -euo pipefail

# Web sessions only; local machines manage their own environment.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

./.venv/bin/python -m pip install --quiet --upgrade pip
# Editable install so `pythonpath = ["src"]` in pyproject.toml resolves,
# plus the dev extras (pytest, pytest-cov) the suite and CI floor need.
./.venv/bin/python -m pip install --quiet -e ".[dev]"

# Put the venv first on PATH so `pytest` resolves for the rest of the session.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export PATH=\"${CLAUDE_PROJECT_DIR:-.}/.venv/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
fi

echo "TradeCC dependencies installed. Run: pytest -m 'not network'"
