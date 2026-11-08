from common import *
import shutil,concurrent.futures as cf,subprocess,importlib.util

def extract(pattern):
 dest=T/'futures_raw';dest.mkdir(exist_ok=True)
 with (R/'logs'/('extract_'+pattern.replace('/','_').replace('*','ALL')+'.log')).open('w')as log:
  subprocess.run(['7zz','x','-y','-mmt=1','-bd',f'-o{dest}','/Volumes/T9/期货1分钟2004~2608/CFFEX.7z',f'CFFEX/{pattern}'],stdout=log,stderr=subprocess.STDOUT,check=True)
 return pattern

def main():
 lock=R/'meta/preregistration_lock.json'
 if not lock.exists():js(lock,dict(sha256=hashlib.sha256((R/'PREREGISTRATION_R7.md').read_bytes()).hexdigest(),registered_utc=pd.Timestamp.now(tz='UTC').isoformat(),estimation_started=False))
 assert json.loads(lock.read_text())['sha256']==hashlib.sha256((R/'PREREGISTRATION_R7.md').read_bytes()).hexdigest()
 if not(T/'features.parquet').exists():
  needed=['event_id','code','freeze_date','dose','eligible','first_observed_daily','qfii','ah','hk_listing_date','hk_delisting_date','event_start','pre_age','quintile',*RACE,*HK,*HKM,*[c+'__'+v for c in HK+HKM for v in VARIANTS]]
  d=pd.read_csv(P/'R4/tables/frozen_features_by_event.csv',usecols=needed,parse_dates=['freeze_date','first_observed_daily','event_start','hk_listing_date','hk_delisting_date']);d.to_parquet(T/'features.parquet',index=False)
 pd.read_csv(P/'meta/stock_universe.csv',parse_dates=['first_observed_daily']).to_parquet(T/'universe.parquet',index=False)
 if not all((T/f'futures_{p}.npz').exists()for p in ['IF','IH']):
  with cf.ProcessPoolExecutor(max_workers=4)as pool:list(pool.map(extract,['IF/IF1*.csv','IF/IF2*.csv','IH/IH1*.csv','IH/IH2*.csv']))
  import prepare_futures_reused as pf;pf.TMP=T;pf.ROOT=R;pf.main()
 sources=[P/'R4/tables/frozen_features_by_event.csv',P/'R2/tables/frozen_features_by_event.csv',P/'tables/event_date_map.csv',P/'tables/events.csv',P/'code/build_metrics.py',P/'R5/code/minutes.py',P/'R5/code/infer.py',R/'PREREGISTRATION_R7.md']
 save([dict(path=str(p),bytes=p.stat().st_size,sha256=hashlib.file_digest(p.open('rb'),'sha256').hexdigest())for p in sources],'input_manifest.csv')
 print('INITIALIZED',flush=True)
if __name__=='__main__':main()
