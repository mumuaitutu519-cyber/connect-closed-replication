from pathlib import Path
import subprocess,concurrent.futures as cf
ROOT=Path(__file__).resolve().parents[1];TMP=Path('/Volumes/Extreme SSD/T9/_tmp/266')
def extract(pattern):
 dest=TMP/'futures_raw';dest.mkdir(parents=True,exist_ok=True)
 with (ROOT/'logs'/('extract_'+pattern.replace('/','_').replace('*','ALL')+'.log')).open('w') as log:
  r=subprocess.run(['7zz','x','-y','-mmt=1','-bd',f'-o{dest}','/Volumes/T9/期货1分钟2004~2608/CFFEX.7z',f'CFFEX/{pattern}'],stdout=log,stderr=subprocess.STDOUT)
 if r.returncode:raise RuntimeError(pattern)
 return pattern
if __name__=='__main__':
 with cf.ProcessPoolExecutor(max_workers=4) as p:
  for r in p.map(extract,['IF/IF1*.csv','IF/IF2*.csv','IH/IH1*.csv','IH/IH2*.csv']):print(r,flush=True)
