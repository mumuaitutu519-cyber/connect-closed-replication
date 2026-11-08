"""Freeze hashes of actual raw inputs; never hash unused multi-billion-row tick inventories."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[k]='1'
from pathlib import Path
import csv,ast,json,hashlib,datetime,argparse,concurrent.futures as cf
ROOT=Path(__file__).resolve().parents[1]
def digest(path):
 p=Path(path);h=hashlib.sha256()
 with p.open('rb') as f:
  while chunk:=f.read(4*1024*1024):h.update(chunk)
 st=p.stat();return dict(path=str(p),bytes=st.st_size,mtime_ns=st.st_mtime_ns,sha256=h.hexdigest())
def paths():
 files=set()
 for r in csv.DictReader((ROOT/'logs/metric_daily_build.csv').open()):
  for p in ast.literal_eval(r['source']):files.add(p.split('!')[0])
 q=Path('/Volumes/Extreme SSD/QDC/data/QDCData')
 files.add(str(q/'cn_hsgt/hk_hold/full/all.parquet'));files.add(str(q/'cn_st/full/all.parquet'));files.add('/Volumes/T9/期货1分钟2004~2608/CFFEX.7z')
 for name,start in [('cn_daily_full',2016),('cn_valuation_1d',2017)]:
  for p in (q/name/'full').glob('*.parquet'):
   if p.stem[:4].isdigit() and start<=int(p.stem[:4])<=2026:files.add(str(p))
 files.update(str(p) for p in (ROOT/'meta/official_raw').iterdir() if p.is_file());return sorted(files)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--verify',action='store_true');a=ap.parse_args();out=ROOT/'meta/input_manifest.json'
 if a.verify:
  manifest=json.loads(out.read_text());jobs=[r['path'] for r in manifest['files']]
 else:jobs=paths()
 with cf.ProcessPoolExecutor(max_workers=4) as p:results=list(p.map(digest,jobs))
 if a.verify:
  expected={r['path']:r for r in manifest['files']};bad=[r['path'] for r in results if r['sha256']!=expected[r['path']]['sha256'] or r['bytes']!=expected[r['path']]['bytes']];assert not bad,f'Raw inputs changed; frozen results must not be silently recomputed from different inputs: {bad}';print('PASS raw input SHA256 manifest',len(results))
 else:
  out.write_text(json.dumps(dict(frozen_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),task_asof='2026-11-07',last_observed_date='2026-10-30',files=results),ensure_ascii=False,indent=2));print(json.dumps(dict(files=len(results),total_bytes=sum(r['bytes'] for r in results)),ensure_ascii=False))
if __name__=='__main__':main()
