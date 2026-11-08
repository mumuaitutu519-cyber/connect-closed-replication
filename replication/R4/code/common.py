import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS'): os.environ[k]='1'
from pathlib import Path
import sys,json,hashlib,gc,ctypes,datetime
import numpy as np,pandas as pd,pyarrow as pa,pyarrow.parquet as pq
R=Path(__file__).resolve().parents[1];P=R.parent;T=Path('/Volumes/Extreme SSD/T9/_tmp/283');Q=Path('/Volumes/Extreme SSD/QDC/data/QDCData')
SEED=20261117;B=9999;PRIMARY=['if_delay','ih_delay','if_lag_sum','ih_lag_sum'];OTHER=['cs_bp','ar_bp','amihud','ln_amount'];METRICS=PRIMARY+OTHER
RACE=['logcap','logamount','csi300','sse50','csi500','ifbeta','predelay','analyst']
MINUTE=['hk_m_beta0',*[f'hk_m_beta{i}' for i in range(1,6)],'hk_m_lagsum','hk_m_corr','hk_m_incr2']
DAILY=[f'hk_{p}_{c}' for p in ['HSI','HSCEI'] for c in ['beta','corr','lag','lead']]
CONTINUOUS=MINUTE+DAILY+['logcap','logamount','ifbeta','predelay','analyst','qfii','intl_share']
for p in [T,R/'meta',R/'logs',R/'tables',R/'data']:p.mkdir(exist_ok=True,parents=True)
pa.set_cpu_count(1);pa.set_io_thread_count(1);pa.set_memory_pool(pa.system_memory_pool())
def js(p,x):
 temp=p.with_name(p.name+f'.{os.getpid()}.partial');temp.write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str));temp.replace(p)
def save(x,name):pd.DataFrame(x).to_csv(R/'tables'/name,index=False)
def release():
 gc.collect();pa.default_memory_pool().release_unused()
 if sys.platform=='darwin':
  f=ctypes.CDLL(None).malloc_zone_pressure_relief;f.argtypes=[ctypes.c_void_p,ctypes.c_size_t];f.restype=ctypes.c_size_t;f(None,0)
def freezes():return pd.read_csv(P/'tables/exposure_coverage.csv',parse_dates=['freeze','start']).rename(columns={'freeze':'freeze_date'})
def mapping():return pd.read_csv(P/'tables/event_date_map.csv',parse_dates=['date','anchor'])
def universe():return pd.read_csv(P/'meta/stock_universe.csv',parse_dates=['first_observed_daily'])
def code(s):
 s=s.astype(str).str[:6].str.zfill(6);return s+np.where(s.str.startswith(('6','9')),'.SH','.SZ')
def batches(path,cols):
 for b in pq.ParquetFile(path).iter_batches(batch_size=65536,columns=cols,use_threads=False):yield b.to_pandas(use_threads=False)
