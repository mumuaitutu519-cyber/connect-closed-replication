#!/bin/bash
set -euo pipefail
TASK277_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TASK277_TMP='/Volumes/Extreme SSD/T9/_tmp/277'
mkdir -p "$TASK277_TMP" "$TASK277_ROOT/logs"
export TMPDIR="$TASK277_TMP/"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1 BLIS_NUM_THREADS=1 ARROW_NUM_THREADS=1 POLARS_MAX_THREADS=1
cd "$TASK277_ROOT"
TASK277_PY='/Volumes/Extreme SSD/T9/_tmp/266/venv/bin/python'
if [[ ! -x "$TASK277_PY" ]]; then
 uv venv --python 3.12 "$TASK277_TMP/venv"
 uv pip install --python "$TASK277_TMP/venv/bin/python" -r requirements.lock
 TASK277_PY="$TASK277_TMP/venv/bin/python"
fi
clang++ -O3 -std=c++17 -I/opt/homebrew/opt/libarchive/include -L/opt/homebrew/opt/libarchive/lib code/scan.cpp -larchive -liconv -o "$TASK277_TMP/scan.build.$$"
mv "$TASK277_TMP/scan.build.$$" code/scan
"$TASK277_PY" -u code/driver.py
