"""Day-partitioned original minute archives; QDC bounded day fallback after archive coverage."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[k]='1'
from pathlib import Path
import io,zipfile,json,time,gc,concurrent.futures as cf,threading,ctypes,sys,warnings
import pandas as pd,numpy as np,pyarrow as pa,pyarrow.parquet as pq,psutil
from build_metrics import metrics,ROOT,TMP
pa.set_cpu_count(1);pa.set_io_thread_count(1);pa.set_memory_pool(pa.system_memory_pool())
RAW=Path('/Volumes/Extreme SSD/T9/codex项目/A股分钟线+日频量价/A股分钟数据/1m_price_zip');QDC=Path('/Volumes/Extreme SSD/QDC/data/QDCData/stocks_1m/full');OUT=TMP/'metrics_daily';OUT.mkdir(exist_ok=True)
def trim():
 gc.collect();pa.default_memory_pool().release_unused()
 if sys.platform=='darwin':
  f=ctypes.CDLL(None).malloc_zone_pressure_relief;f.argtypes=[ctypes.c_void_p,ctypes.c_size_t];f.restype=ctypes.c_size_t;f(None,0)
def one_day(value):
 t=pd.Timestamp(value);dest=OUT/f'{t:%Y%m%d}.parquet';receipt=dest.with_suffix('.json')
 if dest.exists() and receipt.exists():return json.loads(receipt.read_text())
 start=time.time();universe=pd.read_csv(ROOT/'meta/stock_universe.csv').code.tolist();codes=sorted(c[:6]+('.XSHG' if c.endswith('.SH') else '.XSHE') for c in universe);pieces=[];raw=RAW/f'{t.year}.zip';member=f'{t:%Y%m%d}.parquet';source=[];scanned=0
 available=False
 if raw.exists():
  with zipfile.ZipFile(raw) as z:
   if member in z.namelist():
    available=True;pf=pq.ParquetFile(io.BytesIO(z.read(member)))
    for b in pf.iter_batches(batch_size=65536,columns=['code','trade_time','open','high','low','close','vol','amount'],use_threads=False):
     d=b.to_pandas(use_threads=False);scanned+=len(d);d=d[d.code.isin(universe)].copy();d['symbol']=pd.Categorical(d.code.str[:6]+np.where(d.code.str.endswith('.SH'),'.XSHG','.XSHE'),categories=codes);d['ts']=pd.to_datetime(d.trade_time).astype('datetime64[ms]').astype('int64')-8*3600000;d=d.rename(columns={'vol':'volume'});pieces.append(d[['ts','symbol','open','high','low','close','volume','amount']])
    source=[str(raw)+'!'+member];pf.close()
 if not available:
  lower=int(t.value//10**6)-8*3600000;upper=lower+86400000
  files=[p for p in QDC.glob('*.parquet') if p.stem in [f'{t.year}',f'{t:%Y-%m}',f'{t:%Y-%m-%d}']]
  for p in files:
   pf=pq.ParquetFile(p);groups=[]
   for j in range(pf.num_row_groups):
    st=pf.metadata.row_group(j).column(0).statistics
    if st is None or not st.has_min_max or (st.max>=lower and st.min<upper):groups.append(j)
   for b in pf.iter_batches(batch_size=65536,row_groups=groups,columns=['ts','symbol','open','high','low','close','volume','amount'],use_threads=False):
    d=b.to_pandas(use_threads=False);scanned+=len(d);d=d[d.ts.ge(lower)&d.ts.lt(upper)&d.symbol.isin(codes)].copy()
    if len(d):d['symbol']=pd.Categorical(d.symbol,categories=codes);pieces.append(d)
   pf.close();source.append(str(p))
 if not pieces:raise ValueError(f'No source minutes for actual trading day {t}')
 d=pd.concat(pieces,ignore_index=True);del pieces;selected=len(d);duplicates=int(d.duplicated(['symbol','ts']).sum());f=metrics(d,codes);del d;f.to_parquet(dest,index=False,compression='zstd');rows=len(f);del f;trim();rss=psutil.Process().memory_info().rss
 rec=dict(date=str(t.date()),source=source,original_day_archive=available,input_rows_scanned=scanned,selected_minute_rows=selected,duplicate_minute_keys=duplicates,stock_days=rows,rss_gb=rss/1e9,seconds=time.time()-start,path=str(dest));receipt.write_text(json.dumps(rec));return rec
def pack_year(year):
 universe=pd.read_csv(ROOT/'meta/stock_universe.csv').code.tolist();codes=sorted(c[:6]+('.XSHG' if c.endswith('.SH') else '.XSHE') for c in universe);blocks={s[:6]+('.SH' if s.endswith('.XSHG') else '.SZ'):i//20 for i,s in enumerate(codes)};files=sorted(OUT.glob(f'{year}*.parquet'));frames=[pq.ParquetFile(p).read(use_threads=False).to_pandas(use_threads=False) for p in files];f=pd.concat(frames,ignore_index=True);del frames;f['block']=f.code.map(blocks);out=TMP/'metrics';out.mkdir(exist_ok=True)
 for block in range(int(np.ceil(len(codes)/20))):
  d=f[f.block.eq(block)].drop(columns='block');p=out/f'{year}_{block:03d}.parquet';d.to_parquet(p,index=False,compression='zstd');p.with_suffix('.json').write_text(json.dumps(dict(year=year,block=block,stock_days=len(d),source='verified day-partitioned minute archives plus QDC daily fallback',path=str(p))))
 return dict(year=year,stock_days=len(f),source_days=len(files))
def main():
 import argparse
 ap=argparse.ArgumentParser();ap.add_argument('--pack',action='store_true');a=ap.parse_args()
 if a.pack:
  with cf.ProcessPoolExecutor(max_workers=4) as pool:r=list(pool.map(pack_year,range(2017,2027)))
  pd.DataFrame(r).to_csv(ROOT/'logs/daily_pack.csv',index=False);print(r);return
 assert json.loads((ROOT/'meta/literature_gate.json').read_text())['estimation_permitted']
 days=pd.read_csv(ROOT/'tables/official_calendar.csv',parse_dates=['date']);days=days.loc[days.a_open,'date'];records=[];jobs=[]
 for t in days:
  p=OUT/f'{t:%Y%m%d}.json'
  if p.exists() and p.with_suffix('.parquet').exists():records.append(json.loads(p.read_text()))
  else:jobs.append(str(t.date()))
 print(json.dumps({'cached':len(records),'pending':len(jobs)}),flush=True);stop=threading.Event()
 def monitor():
  me=psutil.Process();peak=0
  with (ROOT/'logs/daily_resource_monitor.jsonl').open('a') as log:
   while not stop.wait(.25):
    children=me.children(recursive=True);rss=me.memory_info().rss+sum(p.memory_info().rss for p in children if p.is_running());peak=max(peak,rss);log.write(json.dumps({'unix_time':time.time(),'aggregate_rss_gb':rss/1e9,'peak_gb':peak/1e9})+'\n');log.flush()
    if rss>6.8e9:
     for p in children:p.terminate()
     log.write(json.dumps({'status':'TERMINATED_MEMORY_BUDGET','rss':rss})+'\n');break
 thread=threading.Thread(target=monitor,daemon=True);thread.start()
 for start in range(0,len(jobs),16):
  with cf.ProcessPoolExecutor(max_workers=4) as pool:
   for r in pool.map(one_day,jobs[start:start+16]):records.append(r)
  print(json.dumps({'completed':len(records),'total':len(days),'last':r['date'],'last_rss_gb':r['rss_gb']}),flush=True)
 stop.set();thread.join(timeout=2);pd.DataFrame(records).to_csv(ROOT/'logs/metric_daily_build.csv',index=False)
if __name__=='__main__':
 warnings.filterwarnings('ignore',category=RuntimeWarning);main()
