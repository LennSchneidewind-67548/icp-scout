#!/usr/bin/env bash
# Installs the project in Claude Code remote sessions. Local sessions use .venv.
# The remote image's default python3 can be older than the project needs, so
# the venv is built with python3.12 when it is there.
set -euo pipefail
[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0
cd "${CLAUDE_PROJECT_DIR:-.}"
python="$(command -v python3.12 || command -v python3)"
[ -d .venv ] || "$python" -m venv .venv
.venv/bin/python -m pip install -q -e ".[dev]"
