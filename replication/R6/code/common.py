import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[k]='1'
from pathlib import Path
import sys,json,gc,ctypes
import numpy as np,pandas as pd,pyarrow as pa
R=Path(__file__).resolve().parents[1];P=R.parent;T=Path('/Volumes/Extreme SSD/T9/_tmp/285');Q=Path('/Volumes/Extreme SSD/QDC/data/QDCData');SEED=20261119
pa.set_cpu_count(1);pa.set_io_thread_count(1);pa.set_memory_pool(pa.system_memory_pool())
def trim():
 gc.collect();pa.default_memory_pool().release_unused()
 if sys.platform=='darwin':
  fun=ctypes.CDLL(None).malloc_zone_pressure_relief;fun.argtypes=[ctypes.c_void_p,ctypes.c_size_t];fun.restype=ctypes.c_size_t;fun(None,0)
def save(frame,path):frame.to_csv(path,index=False)
def loadcal():return pd.read_csv(P/'tables/official_calendar.csv',parse_dates=['date'])
