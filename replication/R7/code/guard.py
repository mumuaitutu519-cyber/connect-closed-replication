import subprocess,sys,time,json,psutil
from pathlib import Path
r=Path(__file__).resolve().parents[1];started=time.time();p=subprocess.Popen(sys.argv[1:]);parent=psutil.Process(p.pid);peak=0;status='RUNNING'
try:
 with (r/'logs/resources.jsonl').open('a') as f:
  while p.poll() is None:
   try:
    procs=[parent,*parent.children(recursive=True)];rss=sum(x.memory_info().rss for x in procs if x.is_running());guardian=psutil.Process();rss+=guardian.memory_info().rss
    controller=guardian.parent()
    if controller and any(n in ' '.join(controller.cmdline())for n in ['continue_pipeline.py','after_minutes.py']):rss+=controller.memory_info().rss
    peak=max(peak,rss);f.write(json.dumps(dict(time=time.time(),rss=rss,peak=peak,command=sys.argv[1:],pid=p.pid,scope='child_tree_plus_guard_and_pipeline_controller'))+'\n');f.flush()
    if rss>4_500_000_000:
     status='MEMORY_STOP'
     for x in procs[::-1]:
      try:x.kill()
      except psutil.Error:pass
     raise MemoryError(f'Operational RSS cutoff 4.5GB protects hard 6GB budget: {rss}')
   except psutil.NoSuchProcess:pass
   time.sleep(.1)
 status='PASS' if p.returncode==0 else 'FAILED_EXIT'
finally:
 with (r/'logs/stage_resource_receipts.jsonl').open('a') as f:f.write(json.dumps(dict(started_unix=started,ended_unix=time.time(),status=status,exit_code=p.poll(),peak_bytes=peak,command=sys.argv[1:]))+'\n')
sys.exit(p.returncode)
