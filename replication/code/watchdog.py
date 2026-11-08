"""Task-only RSS guard; ignore all unrelated concurrent projects."""
import argparse,time,json,os,sys
from pathlib import Path
import psutil
def watch(pid,log,limit=6.8e9):
 me=psutil.Process();peak=0
 try:root=psutil.Process(pid)
 except psutil.Error:return
 with Path(log).open('a') as out:
  while root.is_running() and root.status()!=psutil.STATUS_ZOMBIE:
   rss=me.memory_info().rss
   try:procs=[root,*root.children(recursive=True)]
   except psutil.Error:break
   live=[]
   for p in procs:
    try:rss+=p.memory_info().rss;live.append(p)
    except psutil.Error:pass
   peak=max(peak,rss);out.write(json.dumps(dict(unix_time=time.time(),root_pid=pid,aggregate_rss_gb=rss/1e9,peak_gb=peak/1e9))+'\n');out.flush()
   if rss>limit:
    out.write(json.dumps(dict(status='TERMINATED_MEMORY_BUDGET',rss=rss))+'\n');out.flush()
    for p in reversed(live):
     try:p.terminate()
     except psutil.Error:pass
    return
   time.sleep(.25)
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--pid',type=int);a.add_argument('--find-script');a.add_argument('--log',required=True);r=a.parse_args();pid=r.pid
 if pid is None:
  for p in psutil.process_iter(['cmdline']):
   try:
    if r.find_script in (p.info['cmdline'] or []):pid=p.pid;break
   except psutil.Error:pass
 if pid is None:sys.exit(0)
 watch(pid,r.log)
