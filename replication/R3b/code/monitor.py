from common import *
import psutil,subprocess
if __name__=='__main__':
 peak=0
 for stage in sys.argv[1:]:
  with (R/'logs'/f'{stage}.log').open('a') as log:
   p=subprocess.Popen([sys.executable,str(R/'code'/f'{stage}.py')],stdout=log,stderr=subprocess.STDOUT)
   while p.poll() is None:
    try:
     parent=psutil.Process(p.pid);children=parent.children(recursive=True);rss=0
     for item in psutil.process_iter(['name']):
      try:
       if item.cwd()==str(R):rss+=item.memory_info().rss
      except psutil.Error:pass
     peak=max(peak,rss)
     with (R/'logs/resource_history.jsonl').open('a') as history:history.write(json.dumps(dict(time=time.time(),stage=stage,rss_gb=rss/1e9))+'\n')
     js(R/'logs/resource_peak.json',dict(peak_gb=peak/1e9,current_gb=rss/1e9,stage=stage,workers=4,worker_capacity=4,threads=1,budget_gb=4))
     if rss>3.7e9:
      for x in children:x.terminate()
      p.terminate();raise MemoryError(f'Aggregate RSS {rss}')
    except psutil.NoSuchProcess:pass
    time.sleep(.5)
   if p.returncode:raise RuntimeError(f'{stage} failed {p.returncode}; see logs/{stage}.log')
  print('STAGE_COMPLETE',stage,flush=True)
