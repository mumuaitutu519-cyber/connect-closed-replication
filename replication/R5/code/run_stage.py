from common import *
import subprocess,psutil
if __name__=='__main__':
 stage=sys.argv[1];run_id=str(time.time_ns());log=(R/'logs'/f'{stage}.log').open('a');proc=subprocess.Popen([sys.executable,str(R/'code'/f'{stage}.py')],stdout=log,stderr=subprocess.STDOUT);peak=0
 with(R/'logs'/f'resource_{stage}.jsonl').open('a')as f:
  while proc.poll()is None:
   rss=0
   try:
    pp=psutil.Process(proc.pid);children=pp.children(recursive=True);rss=sum(p.memory_info().rss for p in [pp,*children]if p.is_running())
   except psutil.NoSuchProcess:pass
   peak=max(peak,rss);f.write(json.dumps(dict(unix=time.time(),rss=rss,peak=peak,run_id=run_id))+'\n');f.flush()
   if rss>4e9:
    for p in children:p.kill()
    proc.kill();raise MemoryError(f'284 exceeded hard memory ceiling: {rss}')
   time.sleep(.2)
 print(stage,'EXIT',proc.returncode,'PEAK_GB',peak/1e9,flush=True);sys.exit(proc.returncode)
