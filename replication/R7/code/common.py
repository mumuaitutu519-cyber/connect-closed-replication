import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
from pathlib import Path
import sys,json,time,hashlib,gc,ctypes
import numpy as np,pandas as pd,pyarrow as pa,pyarrow.parquet as pq
pa.set_cpu_count(1);pa.set_io_thread_count(1);pa.set_memory_pool(pa.system_memory_pool())
R=Path(__file__).resolve().parents[1];P=R.parent;T=Path('/Volumes/Extreme SSD/T9/_tmp/287');Q=Path('/Volumes/Extreme SSD/QDC/data/QDCData');SEED=20261119;B=9999
T.mkdir(parents=True,exist_ok=True)
RACE=['logcap','logamount','csi300','sse50','csi500','ifbeta','predelay','analyst']
HK=[f'hk_{p}_{c}'for p in ['HSI','HSCEI']for c in ['beta','corr','lag','lead']]
HKM=['hk_m_beta0',*[f'hk_m_beta{i}' for i in range(1,6)],'hk_m_lagsum','hk_m_corr','hk_m_incr2']
PRIMARY=['if_delay','ih_delay'];NEW=['if_r2_now','if_b0', 'if_b1','if_lag_sum','if_total_beta',*[f'{p}_{h}'for h in [1,5,15,30,60]for p in ['beta','r2']],'day_return','open30_return','nonzero_count','nonzero_share'];METRICS=PRIMARY+NEW
VARIANTS=['w01','raw','w005']
def js(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2,default=str))
def save(f,name):
 d=pd.DataFrame(f)
 for c in ['n','stocks','events']:
  if c not in d:d[c]=np.nan
 d['Obs']=d['n'];d.to_csv(R/'tables'/name,index=False)
def release():
 gc.collect();pa.default_memory_pool().release_unused()
 if sys.platform=='darwin':
  f=ctypes.CDLL(None).malloc_zone_pressure_relief;f.argtypes=[ctypes.c_void_p,ctypes.c_size_t];f.restype=ctypes.c_size_t;f(None,0)
def features():return pd.read_parquet(T/'features.parquet')
def universe():return pd.read_parquet(T/'universe.parquet')
def freezes():
 f=pd.read_csv(R/'tables/design_events.csv',parse_dates=['freeze_date']);return f[f.family.eq('US')][['event_id','freeze_date']]
def code(s):
 s=s.astype(str).str[:6].str.zfill(6);return s+np.where(s.str.startswith(('6','9')),'.SH','.SZ')
def batches(path,cols):
 for b in pq.ParquetFile(path).iter_batches(batch_size=65536,columns=cols,use_threads=False):yield b.to_pandas(use_threads=False)
