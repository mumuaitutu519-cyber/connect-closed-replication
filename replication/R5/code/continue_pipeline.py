from common import *
import subprocess,psutil
if __name__=='__main__':
 started=time.time()
 while not(R/'tables/minute_day_receipts.csv').exists():
  if time.time()-started>3600:raise RuntimeError('Minute stage did not complete within 1 hour; inspect logs/minutes.log')
  time.sleep(5)
 for stage in ([]if len(sys.argv)>1 else['check_minutes','infer']):
  subprocess.run([sys.executable,str(R/'code'/f'{stage}.py')],check=True)
 stages=['panel','estimate','dynamic','consistency','diagnostics','finalize','validate'];stages=stages[stages.index(sys.argv[1]):]if len(sys.argv)>1 else stages
 for stage in stages:
  print('START_STAGE',stage,flush=True);subprocess.run([sys.executable,str(R/'code/run_stage.py'),stage],check=True)
 print('PIPELINE_COMPLETE',flush=True)
