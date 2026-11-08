#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
TASK_TMP='/Volumes/Extreme SSD/T9/_tmp/287'
TASK_PY='/Volumes/Extreme SSD/T9/_tmp/266/venv/bin/python'
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export UV_CACHE_DIR="$TASK_TMP/uv_cache" UV_LINK_MODE=copy
mkdir -p "$TASK_TMP" logs tables meta
if [[ ! -x "$TASK_PY" ]]; then
 TASK_PY="$TASK_TMP/venv/bin/python"
 if [[ ! -x "$TASK_PY" ]]; then uv venv "$TASK_TMP/venv" --python 3.12; fi
 uv pip install --python "$TASK_PY" -r requirements.lock
fi
uv pip install --python "$TASK_PY" --target "$TASK_TMP/baostock_pkg" --no-deps 'baostock==0.9.4' > logs/baostock_install.log 2>&1
for TASK_STAGE in initialize minutes build_stage balance preflight joint estimate small_samples sellonly weather fundflow fundflow_analysis reconcile balance export_frozen finalize verify; do
 "$TASK_PY" code/guard.py "$TASK_PY" "code/$TASK_STAGE.py" > "logs/reproduce_$TASK_STAGE.log" 2>&1
done
if [[ "${KEEP_INTERMEDIATES:-0}" != 1 ]]; then "$TASK_PY" code/cleanup.py; fi
