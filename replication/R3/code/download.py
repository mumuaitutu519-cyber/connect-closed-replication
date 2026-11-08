"""Reuse exact-date verify/download implementation of 229, with task-owned scratch.
No successor-date matching and no shared inventory mutation.
"""
from common import *
import subprocess,fcntl,shutil
source=(L/'download_dates.sh').read_text().split("<<'QDC_PYTHON'\n",1)[1].rsplit('\nQDC_PYTHON',1)[0]
ns={'__name__':'download277_reuse'};exec(compile(source,str(L/'download_dates.sh'),'exec'),ns);ns['ROOT']=T/'download';ns['ROOT'].mkdir(exist_ok=True);ns['RESERVE']=20_000_000_000
def ensure(row):
 filename=row['filename'];baseline=L/'raw'/filename
 if baseline.exists() and baseline.stat().st_size==int(row['size_bytes']):return baseline,False
 rootfile=L/filename
 if rootfile.exists() and rootfile.stat().st_size==int(row['size_bytes']):return rootfile,False
 final=ns['ROOT']/filename
 for k in ['md5_reliable','is_daily_package']:row[k]=str(row[k]).lower()
 # A network failure is recorded verbatim and never replaced with another date.
 with (T/('download_'+filename+'.lock')).open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  while not final.exists():
   need=int(row['size_bytes'])+ns['RESERVE']
   while shutil.disk_usage(ns['VOLUME']).free<need:
    print('WAIT_DISK_RESERVE',filename,shutil.disk_usage(ns['VOLUME']).free,need,flush=True);time.sleep(15)
   try:ns['download'](row)
   except RuntimeError:
    if shutil.disk_usage(ns['VOLUME']).free<need:continue
    raise
 return final,True
if __name__=='__main__':
 rows=pd.read_csv(R/'tables/download_plan.csv').to_dict('records');row=next(x for x in rows if x['date']==sys.argv[1]);print(ensure(row),flush=True)
