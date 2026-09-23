#!/usr/bin/env bash
# Compatibility entrypoint used by manuscript reports and existing projects.
# wordcount.py finds the manuscript itself (tools/paths.py).
set -euo pipefail
exec uv run --quiet python "$(dirname "$0")/wordcount.py" "$@"
