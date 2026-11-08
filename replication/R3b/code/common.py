import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
from pathlib import Path
import sys,json,time,hashlib,gc,ctypes
import numpy as np,pandas as pd,pyarrow as pa,pyarrow.parquet as pq
pa.set_cpu_count(1);pa.set_io_thread_count(1);pa.set_memory_pool(pa.system_memory_pool())
R=Path(__file__).resolve().parents[1];P=R.parent;T=Path('/Volumes/Extreme SSD/T9/_tmp/282');Q=Path('/Volumes/Extreme SSD/QDC/data/QDCData');SEED=20261116;B=9999
PRIMARY=['if_delay','ih_delay','if_lag_sum','ih_lag_sum'];GROUPS=['US','UK','EU','ALL','US_half','US_Columbus']
T.mkdir(parents=True,exist_ok=True)
def save(f,name):f.to_csv(R/'tables'/name,index=False)
def js(p,d):p.write_text(json.dumps(d,indent=2,ensure_ascii=False,default=str))
def release():
 gc.collect();pa.default_memory_pool().release_unused()
 if sys.platform=='darwin':
  f=ctypes.CDLL(None).malloc_zone_pressure_relief;f.argtypes=[ctypes.c_void_p,ctypes.c_size_t];f.restype=ctypes.c_size_t;f(None,0)
