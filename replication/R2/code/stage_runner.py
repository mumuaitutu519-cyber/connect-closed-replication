"""Sequential stage driver; 4 heavy workers, aggregate RSS circuit breaker at 6.8GB."""
from pathlib import Path
import os,sys,subprocess,time,json,psutil,datetime,hashlib
R=Path(__file__).resolve().parents[1]
STAGES=[('fetch',['code/fetch_r2_sources.py']),('extra_events',['code/record_extra_events.py']),('historical_members',['code/fetch_historical_members.py']),('extract_futures',['code/r1/extract_futures.py']),('prepare_futures',['code/r1/prepare_futures.py']),('daily',['code/rebuild_daily.py']),('canonical',['code/prepare_r2.py','canonical']),('snapshots',['code/prepare_r2.py','snapshots']),('features',['code/prepare_r2.py','features']),('merge_features',['code/estimate_r2.py','prepare_features']),('plan',['code/estimate_r2.py','plan']),('main',['code/estimate_r2.py','run']),('extended',['code/auxiliary_r2.py','extended']),('aggregates',['code/auxiliary_r2.py','aggregates']),('matching',['code/auxiliary_r2.py','matching']),('recovery',['code/auxiliary_r2.py','recovery']),('fake_prepare',['code/auxiliary_r2.py','fake_prepare']),('fake_estimate',['code/auxiliary_r2.py','fake_estimate']),('finalize',['code/finalize_r2.py'])]
def run_stage(name,args):
 if name=='main':
  lp=R/'meta/preregistration_lock.json';lock=json.loads(lp.read_text());assert lock['sha256']==hashlib.sha256((R/'PREREGISTRATION_R2.md').read_bytes()).hexdigest();lock['estimation_started']=True;lock['first_estimation_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();lp.write_text(json.dumps(lock,indent=2))
 env=os.environ.copy()
 for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS']:env[k]='1'
 with (R/'logs'/f'{name}.log').open('a')as output,(R/'logs/resources_stages.jsonl').open('a')as log:
  p=subprocess.Popen([sys.executable,*args],cwd=R,env=env,stdout=output,stderr=subprocess.STDOUT);root=psutil.Process(p.pid);peak=0
  while p.poll()is None:
   try:procs=[root,*root.children(recursive=True)];rss=sum(q.memory_info().rss for q in procs if q.is_running())+psutil.Process().memory_info().rss
   except psutil.Error:rss=0
   peak=max(peak,rss);log.write(json.dumps(dict(stage=name,time=time.time(),rss_bytes=rss,peak_bytes=peak))+'\n');log.flush()
   if rss>6.8e9:
    for q in reversed(procs):
     try:q.terminate()
     except psutil.Error:pass
    raise MemoryError(f'{name}: RSS circuit breaker {rss}')
   time.sleep(.15)
  if p.returncode:raise RuntimeError(f'{name} failed, exit={p.returncode}, see logs/{name}.log')
  with (R/'logs/completed_stages.jsonl').open('a')as done:done.write(json.dumps(dict(stage=name,completed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),peak_rss_bytes=peak))+'\n')
 print('COMPLETE',name,'peak_GB',peak/1e9,flush=True)
def main():
 start=sys.argv[1]if len(sys.argv)>1 else'canonical';active=False
 for name,args in STAGES:
  if name==start:active=True
  if active:run_stage(name,args)
if __name__=='__main__':main()
