from common import *
import subprocess
if __name__=='__main__':
 while not(R/'meta/build_complete.json').exists():time.sleep(2)
 stages=['balance.py','preflight.py','joint.py','estimate.py','small_samples.py','sellonly.py','weather.py'];start=stages.index(sys.argv[1]+'.py')if len(sys.argv)>1 else 0
 for script in stages[start:]:
  with(R/'logs'/f'{script[:-3]}.log').open('a')as log:
   result=subprocess.run([sys.executable,str(R/'code/guard.py'),sys.executable,str(R/'code'/script)],stdout=log,stderr=subprocess.STDOUT)
  if result.returncode:raise RuntimeError(f'{script} exit {result.returncode}')
 js(R/'meta/estimation_complete.json',dict(utc=pd.Timestamp.now(tz='UTC').isoformat()))
