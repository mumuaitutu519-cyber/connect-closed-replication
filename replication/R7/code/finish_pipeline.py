"""Wait without loading numeric libraries; finalize only after every estimation stage succeeded."""
from pathlib import Path
import sys,time,json,subprocess
r=Path(__file__).resolve().parents[1]
if __name__=='__main__':
 while not(r/'meta/estimation_complete.json').exists():time.sleep(2)
 for name in ['sellonly','fundflow_analysis','reconcile','balance','export_frozen','finalize','verify']:
  with(r/'logs'/f'{name}.log').open('a')as log:
   result=subprocess.run([sys.executable,str(r/'code/guard.py'),sys.executable,str(r/'code'/f'{name}.py')],stdout=log,stderr=subprocess.STDOUT)
  if result.returncode:raise RuntimeError(name)
 subprocess.run([sys.executable,str(r/'code/cleanup.py')],check=True)
 (r/'meta/DELIVERY_COMPLETE.json').write_text(json.dumps(dict(status='PASS',all_estimation_stages_complete=True,final_validation_complete=True,scratch_cleaned=True),indent=2))
