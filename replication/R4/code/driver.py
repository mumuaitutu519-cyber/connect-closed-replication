from common import *
import subprocess,time
def main():
 py=sys.executable
 # A restart resumes complete per-day/per-fit checkpoints with the same locked specs.
 stages=[('initialize',['prepare.py','initialize']),('etf',['prepare.py','etf']),('minutes',['minutes.py','run']),('holdings',['prepare.py','holdings']),('bshares',['fetch_bshares.py']),('international',['prepare.py','international']),('analyst',['prepare.py','analyst']),('panel',['minutes.py','panel']),('minute_features',['features.py','minute']),('daily_features',['features.py','daily']),('combine',['features.py','combine']),('estimate',['estimate.py','run']),('descriptive',['descriptive.py']),('validate',['validate.py']),('finalize',['finalize.py'])]
 for name,args in stages:
  done=T/f'{name}.complete.json'
  if done.exists():continue
  print('STAGE_START',name,flush=True);js(R/'logs/progress.json',dict(stage=name,status='RUNNING',utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
  with (R/'logs'/f'{name}.log').open('a') as log:result=subprocess.run([py,str(R/'code'/args[0]),*args[1:]],stdout=log,stderr=subprocess.STDOUT)
  if result.returncode:
   js(R/'logs/progress.json',dict(stage=name,status='FAILED',returncode=result.returncode));raise RuntimeError('Stage failed: '+name)
  js(done,dict(stage=name,status='COMPLETE',utc=datetime.datetime.now(datetime.timezone.utc).isoformat()));print('STAGE_COMPLETE',name,flush=True)
 js(R/'logs/progress.json',dict(stage='ALL',status='COMPLETE',utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
if __name__=='__main__':main()
