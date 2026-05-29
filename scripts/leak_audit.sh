#!/usr/bin/env bash
# Run the Aegis RD look-ahead / data-leak / bias audit under the repo's venv
# python (needs numpy/pandas + the aerd CLI). Forwards all args to leak_audit.py.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
exec "$REPO_ROOT/.venv/bin/python" "$REPO_ROOT/scripts/leak_audit.py" "$@"
