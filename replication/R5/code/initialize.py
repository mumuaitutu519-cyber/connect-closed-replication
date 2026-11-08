from common import *
import shutil,importlib.metadata
def extract_own(pattern):
 import subprocess
 dest=T/'futures_raw';dest.mkdir(parents=True,exist_ok=True)
 with(R/'logs'/('extract_'+pattern.replace('/','_').replace('*','ALL')+'.log')).open('w')as log:
  r=subprocess.run(['7zz','x','-y','-mmt=1','-bd',f'-o{dest}','/Volumes/T9/期货1分钟2004~2608/CFFEX.7z',f'CFFEX/{pattern}'],stdout=log,stderr=subprocess.STDOUT)
 if r.returncode:raise RuntimeError(pattern)
 return pattern
if __name__=='__main__':
 lock=json.loads((R/'meta/preregistration_lock.json').read_text());assert lock['sha256']==hashlib.sha256((R/'PREREGISTRATION_R5.md').read_bytes()).hexdigest()
 srcroot=Path('/Volumes/Extreme SSD/T9/_tmp/282')
 if all((srcroot/f'futures_{p}.npz').exists()for p in ['IF','IH']):
  for p in ['IF','IH']:
   if not(T/f'futures_{p}.npz').exists():shutil.copyfile(srcroot/f'futures_{p}.npz',T/f'futures_{p}.npz')
 elif not all((T/f'futures_{p}.npz').exists()for p in ['IF','IH']):
  import concurrent.futures as cf
  sys.path.insert(0,str(P/'code'))
  import prepare_futures as pf
  with cf.ProcessPoolExecutor(max_workers=4)as pool:list(pool.map(extract_own,['IF/IF1*.csv','IF/IF2*.csv','IH/IH1*.csv','IH/IH2*.csv']))
  pf.TMP=T;pf.ROOT=R;pf.main()
 f=pd.read_csv(P/'R2/tables/frozen_features_by_event.csv',parse_dates=['freeze_date','event_start']);f['amount_decile']=np.nan;f['hold_p99']=np.nan
 for ev,ix in f.groupby('event_id').groups.items():
  eligible=f.loc[ix].dose.notna()&f.loc[ix].pre_age.ge(60)&f.loc[ix].logcap.notna();threshold=f.loc[ix].loc[eligible,'dose'].quantile(.99);f.loc[ix,'hold_p99']=threshold
  q=f.loc[ix].sort_values('code');q=q[q.logamount.notna()&q.pre_age.ge(60)];rank=q.logamount.rank(method='first');f.loc[rank.index,'amount_decile']=np.minimum(9,np.floor((rank-1)*10/len(rank)))
 f.to_parquet(T/'features.writing',index=False);(T/'features.writing').replace(T/'features.parquet')
 un=pd.read_csv(P/'meta/stock_universe.csv',parse_dates=['first_observed_daily']);un.to_parquet(T/'universe.parquet',index=False)
 files={str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in [P/'R2/tables/frozen_features_by_event.csv',P/'meta/input_manifest.json',P/'code/estimate.py',P/'code/build_metrics.py',P/'tables/event_date_map.csv',P/'tables/events.csv',R/'PREREGISTRATION_R5.md',*[T/f'futures_{p}.npz'for p in ['IF','IH']]]};js(R/'meta/input_manifest.json',files)
 js(R/'meta/environment.json',dict(packages={d.metadata['Name']:d.version for d in importlib.metadata.distributions()},python=sys.version))
 print('INITIALIZED',len(f),flush=True)
