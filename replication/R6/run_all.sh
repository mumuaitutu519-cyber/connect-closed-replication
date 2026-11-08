#!/usr/bin/env bash
set -euo pipefail
TASK285_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TASK285_TMP='/Volumes/Extreme SSD/T9/_tmp/285'
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONWARNINGS=ignore
export TMPDIR="$TASK285_TMP/"
mkdir -p "$TASK285_TMP" "$TASK285_ROOT/logs"
cd "$TASK285_ROOT"
TASK285_PY='/Volumes/Extreme SSD/T9/_tmp/266/venv/bin/python'
if [[ ! -x "$TASK285_PY" ]]; then
  uv venv --python 3.12 "$TASK285_TMP/venv"
  uv pip install --python "$TASK285_TMP/venv/bin/python" -r requirements.lock
  TASK285_PY="$TASK285_TMP/venv/bin/python"
fi
stage() {
  local stage_name="$1"
  shift
  "$TASK285_PY" code/guard.py "$TASK285_PY" "$@" > "logs/reproduce_${stage_name}.log" 2>&1
}
# Official source snapshots are cached with URLs. Keep their initial historical cutoff.
"$TASK285_PY" code/fetch_weather.py > logs/reproduce_weather_fetch.log 2>&1
"$TASK285_PY" code/fetch_hkex.py > logs/reproduce_hkex_fetch.log 2>&1
"$TASK285_PY" code/fetch_forecasts.py > logs/reproduce_forecast_fetch.log 2>&1
"$TASK285_PY" code/fetch_supplemental_sources.py > logs/reproduce_supplemental_fetch.log 2>&1
stage source_snapshots code/source_manifest.py
stage calendar code/weather_calendar.py
stage design code/prepare_design.py
stage independent_inference code/validate_inference.py
stage latest_exposure code/prepare_latest_dose.py
if [[ ! -f "$TASK285_TMP/futures_IF.npz" || ! -f "$TASK285_TMP/futures_IH.npz" ]]; then
  stage futures_extract code/r1/extract_futures.py
  stage futures_prepare code/r1/prepare_futures.py
fi
stage daily code/build_daily.py
stage formula_validation code/validate_measurements.py
stage pack code/build_panels.py pack
stage pooled code/build_panels.py pooled
stage panel code/build_panels.py panel
stage estimate code/estimate_r6.py
stage provenance code/input_manifest.py
stage finalize code/finalize.py
stage verify code/verify.py
if [[ "${KEEP_INTERMEDIATES:-0}" != '1' ]]; then
  "$TASK285_PY" code/cleanup.py
fi
