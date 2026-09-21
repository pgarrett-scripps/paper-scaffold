#!/usr/bin/env bash
# Compatibility entrypoint used by manuscript reports and existing projects.
set -euo pipefail
cd "$(dirname "$0")/.."
exec uv run --quiet python tools/wordcount.py "$@"
