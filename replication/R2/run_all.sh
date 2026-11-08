#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
TASK_TMP='/Volumes/Extreme SSD/T9/_tmp/272'
export UV_CACHE_DIR="$TASK_TMP/uv_cache"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1
mkdir -p "$TASK_TMP" logs
TASK_PY='/Volumes/Extreme SSD/T9/_tmp/266/venv/bin/python'
if [[ ! -x "$TASK_PY" ]]; then
  TASK_PY="$TASK_TMP/venv/bin/python"
  if [[ ! -x "$TASK_PY" ]]; then uv venv "$TASK_TMP/venv" --python 3.12; fi
  uv pip install --python "$TASK_PY" -r requirements.lock
fi
"$TASK_PY" code/initialize_r2.py
"$TASK_PY" code/stage_runner.py fetch
if [[ "${KEEP_INTERMEDIATES:-0}" != 1 ]]; then "$TASK_PY" code/cleanup_r2.py; fi
