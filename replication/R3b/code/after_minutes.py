from common import *
import subprocess
if __name__=='__main__':
 c=pd.read_csv(R/'tables/official_calendar.csv');expected=int((c.a_open&pd.to_datetime(c.date).le('2026-09-30')).sum())
 while len(list((T/'metrics_daily').glob('*.json')))<expected:time.sleep(10)
 subprocess.run([sys.executable,str(R/'code/monitor.py'),'panel','estimate','consolidate'],check=True)
