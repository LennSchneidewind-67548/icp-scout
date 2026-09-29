#!/usr/bin/env bash
# Installs the project in Claude Code remote sessions. Local sessions use .venv.
set -euo pipefail
[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0
cd "${CLAUDE_PROJECT_DIR:-.}"
python3 -m pip install -q -e ".[dev]"
