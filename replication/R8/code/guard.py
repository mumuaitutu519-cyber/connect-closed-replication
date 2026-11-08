import subprocess,sys,time,json,psutil
from pathlib import Path
R=Path(__file__).resolve().parents[1];start=time.time();p=subprocess.Popen(sys.argv[1:]);peak=0;status='RUNNING';last_top=[]
try:
 with (R/'logs/resources.jsonl').open('a') as f:
  while p.poll() is None:
   try:
    me=psutil.Process();root=psutil.Process(p.pid);procs=[root,*root.children(recursive=True)];rss=me.memory_info().rss+sum(x.memory_info().rss for x in procs if x.is_running());controller=me.parent()
    if controller and 'continue_pipeline.py'in ' '.join(controller.cmdline()):rss+=controller.memory_info().rss
    peak=max(peak,rss)
    last_top=[dict(pid=x.pid,rss=x.memory_info().rss)for x in procs]if rss>8e9 else[]
    f.write(json.dumps(dict(unix=time.time(),rss=rss,peak=peak,command=sys.argv[1:],top_rss=last_top))+'\n');f.flush()
    if rss>12_000_000_000:
     status='MEMORY_STOP'
     for x in procs[::-1]:
      try:x.kill()
      except psutil.Error:pass
     raise MemoryError('12GB cutoff protects 13GB hard budget')
   except psutil.NoSuchProcess:pass
   time.sleep(.3)
 status='PASS' if p.returncode==0 else 'FAILED_EXIT'
finally:
 with (R/'logs/stage_resource_receipts.jsonl').open('a') as f:f.write(json.dumps(dict(start=start,end=time.time(),status=status,exit_code=p.poll(),peak_bytes=peak,command=sys.argv[1:],top_rss=last_top))+'\n')
sys.exit(p.returncode)
