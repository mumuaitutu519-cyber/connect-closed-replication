#!/usr/bin/env bash
set -euo pipefail
TASK266_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TASK266_TMP='/Volumes/Extreme SSD/T9/_tmp/266'
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export TMPDIR="$TASK266_TMP/"
mkdir -p "$TASK266_TMP" "$TASK266_ROOT/logs"
cd "$TASK266_ROOT"
if [[ ! -x "$TASK266_TMP/venv/bin/python" ]]; then
  uv venv --python 3.12 "$TASK266_TMP/venv"
  uv pip install --python "$TASK266_TMP/venv/bin/python" -r requirements.lock
fi
TASK266_PY="$TASK266_TMP/venv/bin/python"
if [[ -f meta/input_manifest.json ]]; then
  "$TASK266_PY" code/input_manifest.py --verify > logs/reproduce_input_verification.log 2>&1
fi
if [[ ! -f "$TASK266_TMP/futures_IF.npz" || ! -f "$TASK266_TMP/futures_IH.npz" ]]; then
  "$TASK266_PY" code/extract_futures.py > logs/reproduce_extract.log 2>&1
  "$TASK266_PY" code/prepare_futures.py > logs/reproduce_futures.log 2>&1
fi
"$TASK266_PY" code/run_stages.py > logs/reproduce_pipeline.log 2>&1
"$TASK266_PY" code/verify_delivery.py
if [[ "${KEEP_INTERMEDIATES:-0}" != '1' ]]; then
  "$TASK266_PY" code/cleanup.py
fi
