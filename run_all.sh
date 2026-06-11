#!/usr/bin/env sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python "$PROJECT_ROOT/scripts/run_pipeline.py" "$@"
