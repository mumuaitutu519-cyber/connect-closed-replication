"""Resume validated statistical stages after an implementation repair; retain scratch for QA."""
from common import *
from driver import run
import fcntl,threading

def main():
 start=sys.argv[1]if len(sys.argv)>1 else 'flow'
 stages=[('flow',['code/assemble.py','flow']),('estimates',['code/estimate.py']),('finalize',['code/finalize.py'])]
 names=[s[0]for s in stages];assert start in names
 with (T/'pipeline.lock').open('a')as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  plan=pd.read_csv(R/'tables/download_plan.csv');identity=hashlib.sha256(b''.join((R/'code'/v).read_bytes()for v in ['scan.cpp','book169.cpp','numeric229.hpp'])).hexdigest();accepted=accepted_native_hashes(identity);good=[]
  for dt in plan.date:
   ds=dt.replace('-','');receipt=json.loads((R/'logs/days'/f'{ds}.json').read_text())
   if receipt.get('status')=='OK'and receipt.get('scanner_sha256')in accepted and all((R/'data'/kind/f'{ds}.parquet').exists()for kind in ['daily','minute','shocks']):good.append(dt)
  assert len(good)==len(plan),'Raw cache incomplete; use full run_all.sh'
  assert (T/'daily_panel.parquet').exists()
  stop=threading.Event();threading.Thread(target=watch,args=(stop,),daemon=True).start()
  try:
   for name,args in stages[names.index(start):]:run(name,args)
   run('delivery_validation',['code/validate_delivery.py'])
   js(R/'logs/pipeline_status.json',dict(stage='DELIVERED',status='COMPLETE',updated_at=pd.Timestamp.now(tz='UTC'),raw_days_complete=True,report=str(R/'RESULTS_FOR_CLAUDE.md'),scratch_retained_for_QA=True))
   print('DELIVERY COMPLETE',R/'RESULTS_FOR_CLAUDE.md',flush=True)
  except Exception as e:
   js(R/'logs/pipeline_status.json',dict(stage='FAILED',status='FAILED',error=str(e),updated_at=pd.Timestamp.now(tz='UTC')));raise
  finally:stop.set()
if __name__=='__main__':main()
