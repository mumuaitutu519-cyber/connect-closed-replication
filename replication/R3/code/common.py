import os,sys
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS','BLIS_NUM_THREADS','POLARS_MAX_THREADS','ARROW_NUM_THREADS'):os.environ[k]='1'
sys.dont_write_bytecode=True
from pathlib import Path
import json,time,hashlib,gc
import numpy as np,pandas as pd,pyarrow as pa,pyarrow.parquet as pq
pa.set_cpu_count(1);pa.set_io_thread_count(1)
R=Path(__file__).resolve().parents[1];P=R.parent;T=Path('/Volumes/Extreme SSD/T9/_tmp/277');Q=Path('/Volumes/Extreme SSD/QDC/data/QDCData');L=Path('/Volumes/Extreme SSD/QDC/L2');SEED=20261115
for x in [T,R/'tables',R/'logs',R/'meta',R/'data']:x.mkdir(parents=True,exist_ok=True)
for kind in ['daily','minute','shocks']:
 target=T/'l2_cache'/kind;target.mkdir(parents=True,exist_ok=True);link=R/'data'/kind
 if not link.exists():link.symlink_to(target,target_is_directory=True)
def save(d,name):d.to_csv(R/'tables'/name,index=False,na_rep='NA')
def js(p,x):
 import threading
 p=Path(p);tmp=p.with_name(p.name+f'.{os.getpid()}.{threading.get_ident()}.tmp');tmp.write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str));tmp.replace(p)
def watch(stop):
 import psutil
 me=psutil.Process();peak=0
 with (R/'logs/resources.jsonl').open('a') as f:
  while not stop.wait(1):
   ps=[me]+me.children(recursive=True);rss=0
   for p in ps:
    try:rss+=p.memory_info().rss
    except psutil.Error:pass
   peak=max(peak,rss);z=dict(time=time.time(),rss_gb=rss/1e9,peak_gb=peak/1e9,workers=4,threads=1);f.write(json.dumps(z)+'\n');f.flush();js(R/'logs/resource_peak.json',z)
   if rss>8e9:
    for p in reversed(ps[1:]):
     try:p.terminate()
     except psutil.Error:pass
    os._exit(78)

def accepted_native_hashes(current):
 """Exact input-domain extension only; never aliases a changed measurement algorithm."""
 allowed={current};p=R/'meta/native_cache_compatibility.json'
 if p.exists():
  rule=json.loads(p.read_text())
  if rule.get('current_sha256')==current:
   proof=json.loads((R/rule['validation_file']).read_text());previous=set(rule['equivalent_successful_hashes'])
   if rule.get('status')!='PASS'or proof.get('status')!='PASS'or proof.get('new_sha256')!=current or previous!={proof.get('old_sha256')}:
    raise RuntimeError('Invalid native cache input-domain equivalence receipt')
   allowed.update(previous)
 return allowed
