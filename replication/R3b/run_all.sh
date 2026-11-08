#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
TASK_TMP='/Volumes/Extreme SSD/T9/_tmp/282'
export UV_CACHE_DIR="$TASK_TMP/uv_cache"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1
mkdir -p "$TASK_TMP" logs
TASK_PY='/Volumes/Extreme SSD/T9/_tmp/266/venv/bin/python'
if [[ ! -x "$TASK_PY" ]]; then
  TASK_PY="$TASK_TMP/venv/bin/python"
  if [[ ! -x "$TASK_PY" ]]; then uv venv "$TASK_TMP/venv" --python 3.12; fi
  uv pip install --python "$TASK_PY" -r requirements.lock
fi
"$TASK_PY" code/initialize.py
"$TASK_PY" code/monitor.py futures weather prepare minutes panel estimate consolidate validate_actual
"$TASK_PY" code/validate_math.py
"$TASK_PY" code/validate_ri.py
"$TASK_PY" code/four_metrics.py
"$TASK_PY" code/resource_summary.py
"$TASK_PY" code/control_audit.py
"$TASK_PY" code/finalize.py
"$TASK_PY" code/verify.py
if [[ "${KEEP_INTERMEDIATES:-0}" != 1 ]]; then "$TASK_PY" code/cleanup.py; fi
