#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
TASK_TMP='/Volumes/Extreme SSD/T9/_tmp/284'
mkdir -p "$TASK_TMP" logs
export UV_CACHE_DIR="$TASK_TMP/uv_cache"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1
TASK_PY='/Volumes/Extreme SSD/T9/_tmp/266/venv/bin/python'
if [[ ! -x "$TASK_PY" ]]; then
  TASK_PY="$TASK_TMP/venv/bin/python"
  if [[ ! -x "$TASK_PY" ]]; then uv venv "$TASK_TMP/venv" --python 3.12; fi
  uv pip install --python "$TASK_PY" -r requirements.lock
fi
"$TASK_PY" code/run_stage.py initialize
"$TASK_PY" code/calendar_sources.py > logs/calendar_sources.log 2>&1
"$TASK_PY" code/h_extension.py
"$TASK_PY" code/aux_sources.py
"$TASK_PY" code/validate_math.py
"$TASK_PY" code/infer.py
for stage in minutes check_minutes panel estimate dynamic consistency diagnostics finalize validate; do
  "$TASK_PY" code/run_stage.py "$stage"
done
if [[ "${KEEP_INTERMEDIATES:-0}" != 1 ]]; then "$TASK_PY" code/cleanup.py; fi
