from common import *
import subprocess,time,psutil,signal
def main():
 cmd=sys.argv[1:];proc=subprocess.Popen(cmd,start_new_session=True);peak=0;status='RUNNING'
 while proc.poll() is None:
  try:
   root=psutil.Process(proc.pid);pp=[root]+root.children(recursive=True);rss=sum(p.memory_info().rss for p in pp if p.is_running());peak=max(peak,rss)
   if rss>4.4e9:
    status='MEMORY_LIMIT_STOP';os.killpg(proc.pid,signal.SIGTERM);break
  except psutil.NoSuchProcess:pass
  js(R/'logs/resource_peak.json',dict(command=cmd,pid=proc.pid,peak_bytes=peak,status=status,hard_limit_bytes=5_000_000_000));time.sleep(.05)
 rc=proc.wait();record=dict(command=cmd,peak_bytes=peak,status=status if status!='RUNNING' else ('COMPLETE' if rc==0 else 'FAILED'),returncode=rc,hard_limit_bytes=5_000_000_000);js(R/'logs/resource_peak.json',record);js(R/'logs'/('resource_'+Path(cmd[-2] if len(cmd)>2 else cmd[-1]).stem+'.json'),record);sys.exit(rc if rc else 0)
if __name__=='__main__':main()
