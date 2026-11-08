"""Sequential reproducible pipeline; up to four heavy workers, task-only memory supervision."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[k]='1'
from pathlib import Path
import subprocess,sys,json,argparse,hashlib,threading,time
import psutil
ROOT=Path(__file__).resolve().parents[1]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--after-minutes',action='store_true');ap.add_argument('--start-at');a=ap.parse_args();gate=json.loads((ROOT/'meta/literature_gate.json').read_text());assert gate['estimation_permitted'];assert hashlib.sha256((ROOT/'PREREGISTRATION.md').read_bytes()).hexdigest()==gate['prereg_sha256']
 stages=[]
 if not a.after_minutes:stages += [('calendar',['prepare_calendar.py']),('exposure',['prepare_exposure.py']),('minutes',['build_metrics_daily.py'])]
 stages += [('pack',['build_metrics_daily.py','--pack']),('canonical',['build_panel.py','canonical']),('pooled',['build_panel.py','pooled']),('panel',['build_panel.py','panel']),('resampling',['estimate.py','plan']),('main',['estimate.py','main']),('aux_prepare',['auxiliary.py','prepare']),('aux_pooled',['auxiliary.py','pooled']),('aux_panel',['auxiliary.py','placebo_panel']),('aux_estimate',['aux_estimates.py']),('inference_check',['check_inference.py']),('finalize',['finalize.py'])]
 if a.start_at:stages=stages[next(i for i,s in enumerate(stages) if s[0]==a.start_at):]
 stop=threading.Event();process=psutil.Process()
 def monitor():
  peak=0
  with (ROOT/'logs/pipeline_memory.jsonl').open('a') as log:
   while not stop.wait(.25):
    total=0;live=[]
    try:procs=[process,*process.children(recursive=True)]
    except psutil.Error:continue
    for p in procs:
     try:total+=p.memory_info().rss;live.append(p)
     except psutil.Error:pass
    peak=max(peak,total);log.write(json.dumps(dict(unix_time=time.time(),rss_gb=total/1e9,peak_gb=peak/1e9))+'\n');log.flush()
    if total>6.8e9:
     log.write(json.dumps(dict(status='TERMINATED_MEMORY_BUDGET',rss=total))+'\n');log.flush()
     for p in reversed(live[1:]):
      try:p.terminate()
      except psutil.Error:pass
     return
 thread=threading.Thread(target=monitor,daemon=True);thread.start()
 try:
  for name,args in stages:
   print('START',name,flush=True)
   with (ROOT/f'logs/stage_{name}.log').open('w') as log:
    result=subprocess.run([sys.executable,str(ROOT/'code'/args[0]),*args[1:]],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,env=os.environ.copy())
   if result.returncode:raise RuntimeError(f'Stage {name} failed ({result.returncode}); see logs/stage_{name}.log')
   print('DONE',name,flush=True)
 finally:stop.set();thread.join(timeout=2)
if __name__=='__main__':main()
