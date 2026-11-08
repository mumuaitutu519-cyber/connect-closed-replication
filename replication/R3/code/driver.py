from common import *
import subprocess,threading,shutil,psutil

def run(name,args):
 js(R/'logs/pipeline_status.json',dict(stage=name,status='RUNNING',updated_at=pd.Timestamp.now(tz='UTC')))
 with (R/'logs'/f'pipeline_{name}.log').open('a')as f:subprocess.run([sys.executable,'-u',*args],stdout=f,stderr=subprocess.STDOUT,check=True)
 print('STAGE COMPLETE',name,flush=True)

def main():
 # One task lock, including resumed invocations. A supplied active source PID is awaited before taking over.
 import fcntl
 with (T/'pipeline.lock').open('a')as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  prior=int(os.environ.get('WAIT_FOR_SOURCE_PID','0'))
  while prior and psutil.pid_exists(prior):
   try:
    p=psutil.Process(prior)
    if p.status()==psutil.STATUS_ZOMBIE:break
   except psutil.Error:break
   time.sleep(10)
  stop=threading.Event();threading.Thread(target=watch,args=(stop,),daemon=True).start()
  try:
   if not (R/'tables/download_plan.csv').exists():run('calendar',['code/prepare.py','calendar']);run('features',['code/prepare.py','features'])
   if not (T/'futures_IF.npz').exists():run('extract_futures',['code/extract_futures.py']);run('futures',['code/prepare_futures.py'])
   run('tick_supplement',['code/supplement_futures.py'])
   run('shocks',['code/process.py','make_shocks'])
   identity=hashlib.sha256(b''.join((R/'code'/v).read_bytes()for v in ['scan.cpp','book169.cpp','numeric229.hpp'])).hexdigest();plan=pd.read_csv(R/'tables/download_plan.csv')
   for attempt in range(3):
    run('l2_'+str(attempt+1),['code/process.py','main']);good=[]
    for dt in plan.date:
     p=R/'logs/days'/f'{dt.replace("-","")}.json'
     if p.exists():
      z=json.loads(p.read_text())
      if z.get('status')=='OK'and z.get('scanner_sha256')in accepted_native_hashes(identity):good.append(dt)
    if len(good)==len(plan):break
   run('inference_validation',['code/validate_inference.py'])
   run('daily',['code/assemble.py','daily']);run('flow',['code/assemble.py','flow']);run('estimates',['code/estimate.py']);run('finalize',['code/finalize.py'])
   if len(good)==len(plan):run('delivery_validation',['code/validate_delivery.py'])
   js(R/'logs/pipeline_status.json',dict(stage='DELIVERED',status='COMPLETE',updated_at=pd.Timestamp.now(tz='UTC'),raw_days_complete=len(good)==len(plan),report=str(R/'RESULTS_FOR_CLAUDE.md')))
   if os.environ.get('KEEP_INTERMEDIATES','0')!='1'and len(good)==len(plan):
    # Delete only task-owned scratch, after source-backed results and validation receipts exist.
    for link in (R/'data').iterdir():
     if link.is_symlink()and str(link.resolve()).startswith(str(T)+'/'):link.unlink()
    for p in T.iterdir():
     if p.name in ['pipeline.lock','venv']:continue
     if p.is_dir():shutil.rmtree(p)
     else:p.unlink()
   print('DELIVERY COMPLETE',R/'RESULTS_FOR_CLAUDE.md',flush=True)
  except Exception as e:
   js(R/'logs/pipeline_status.json',dict(stage='FAILED',status='FAILED',error=str(e),updated_at=pd.Timestamp.now(tz='UTC')));raise
  finally:stop.set()
if __name__=='__main__':main()
