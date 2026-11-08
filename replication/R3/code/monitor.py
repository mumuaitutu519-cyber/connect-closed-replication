"""Read-only execution monitor; exits when the complete pipeline succeeds or fails."""
from common import *
import runpy,psutil
def readjson(p,default=None):
 for attempt in range(3):
  try:return json.loads(Path(p).read_text())
  except (json.JSONDecodeError,FileNotFoundError):time.sleep(.02)
 return {}if default is None else default
while True:
 p=R/'logs/pipeline_status.json';status=readjson(p);stage=status.get('stage','L2_RUNNING')
 if stage=='DELIVERED':print('PIPELINE_FINISHED '+json.dumps(status,ensure_ascii=False),flush=True);break
 if status.get('status')=='FAILED':print('PIPELINE_FAILED '+json.dumps(status,ensure_ascii=False),flush=True);sys.exit(1)
 identity=hashlib.sha256(b''.join((R/'code'/v).read_bytes()for v in ['scan.cpp','book169.cpp','numeric229.hpp'])).hexdigest();rr=[readjson(p)for p in (R/'logs/days').glob('*.json')];ok=sum(z.get('status')=='OK'and z.get('scanner_sha256')in accepted_native_hashes(identity) for z in rr);stale=sum(z.get('status')=='OK'and z.get('scanner_sha256')not in accepted_native_hashes(identity) for z in rr);fail=sum(z.get('status')!='OK'for z in rr);resource=readjson(R/'logs/resource_peak.json');summary=dict(time=str(pd.Timestamp.now(tz='Asia/Seoul')),stage=stage,valid_days=ok,total_days=512,awaiting_recompute=stale,recorded_failed_days=fail,rss_gb=round(resource.get('rss_gb',0),2));print(json.dumps(summary,ensure_ascii=False),flush=True);js(R/'logs/live_summary.json',summary)
 procs=json.loads((R/'meta/execution_processes.json').read_text());alive=[]
 for pid in [procs['source_pid'],procs['completion_pid']]:
  try:
   pp=psutil.Process(pid);alive.append(pp.is_running()and pp.status()!=psutil.STATUS_ZOMBIE)
  except psutil.Error:alive.append(False)
 if not any(alive):print('EXECUTION_PROCESSES_EXITED_WITHOUT_DELIVERY',flush=True);sys.exit(2)
 time.sleep(45)
