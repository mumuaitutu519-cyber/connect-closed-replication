from common import *
import subprocess
if __name__=='__main__':
 while not(R/'tables/minute_day_receipts.csv').exists():time.sleep(2)
 subprocess.run([sys.executable,str(R/'code/guard.py'),sys.executable,str(R/'code/build_stage.py')],check=True)
