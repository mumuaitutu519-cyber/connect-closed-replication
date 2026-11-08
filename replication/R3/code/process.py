from common import *
import concurrent.futures as cf,threading,subprocess,shutil
from download import ensure

def make_shocks():
 f=pd.read_csv(R/'tables/frozen_features.csv',parse_dates=['freeze_date']).drop_duplicates(['event_id']);cal=pd.read_csv(R/'tables/official_calendar.csv',parse_dates=['date']);normal=set(cal.loc[cal.nb_open,'date']);mp=pd.read_csv(R/'tables/event_date_map.csv',parse_dates=['date']);ret={}
 with np.load(T/'futures_IF.npz') as z:ret={pd.Timestamp(int(d)*86400000000000):r for d,r in zip(z['dates'],z['returns'])}
 info=[];rows=[]
 for e in f.itertuples():
  days=sorted(d for d in ret if d<e.freeze_date and d in normal)[-60:];v=np.concatenate([ret[d] for d in days]) if days else np.array([]);sd=np.nanstd(v,ddof=1) if len(days)>=30 else np.nan;info.append(dict(event_id=e.event_id,freeze_date=e.freeze_date,history_days=len(days),history_max=max(days) if days else None,sd=sd,threshold=2*sd))
  for dt in mp.loc[mp.event_id.eq(e.event_id),'date']:
   if dt not in ret:continue
   for k,r in enumerate(ret[dt]):
    end=(34200000+(k+1)*60000) if k<120 else (46800000+(k-119)*60000)
    if np.isfinite(sd) and abs(r)>2*sd and k not in [119,236,237,238,239]:rows.append(dict(date=dt,event_id=e.event_id,time_ms=end,sign=1 if r>0 else -1))
 save(pd.DataFrame(info),'shock_thresholds.csv');s=pd.DataFrame(rows,columns=['date','event_id','time_ms','sign']);s.to_parquet(T/'shock_plan.parquet',index=False)

def one(row,validation_bypass=False):
 while (T/'validation_hold').exists()and not validation_bypass:time.sleep(.5)
 d=row['date'];ds=d.replace('-','');rec=R/'logs/days'/f'{ds}.json';rec.parent.mkdir(exist_ok=True)
 identity=hashlib.sha256(b''.join((R/'code'/v).read_bytes()for v in ['scan.cpp','book169.cpp','numeric229.hpp'])).hexdigest()
 if rec.exists():
  prior=json.loads(rec.read_text())
  if prior.get('status')=='OK'and prior.get('scanner_sha256')in accepted_native_hashes(identity) and all((R/'data'/k/f'{ds}.parquet').exists()for k in ['daily','minute','shocks']):return prior
 tmp=T/ds;tmp.mkdir(exist_ok=True);t0=time.time();own=False;archive=None
 try:
  archive,own=ensure(row);plan=pd.read_parquet(R/'meta/date_stock_plan.parquet');codes=sorted(plan.loc[plan.date.eq(pd.Timestamp(d)),'code'].unique());(tmp/'codes.txt').write_text('\n'.join(codes)+'\n');sp=pd.read_parquet(T/'shock_plan.parquet');sp=sp[sp.date.eq(pd.Timestamp(d))];sp[['event_id','time_ms','sign']].to_csv(tmp/'shocks.txt',index=False,header=False)
  with (R/'logs'/f'scan_{ds}.log').open('w')as log:subprocess.run([str(R/'code/scan'),str(archive),str(tmp/'scan'),ds,str(tmp/'codes.txt'),str(tmp/'shocks.txt')],stdout=log,stderr=subprocess.STDOUT,check=True)
  counts={}
  for kind in ['daily','minute','shocks']:
   inp=tmp/f'scan_{kind}.csv';out=R/'data'/kind/f'{ds}.parquet';writer=None;count=0
   try:
    header=pd.read_csv(inp,nrows=0).columns;types={c:('str'if c in ['date','code']else 'int64'if c in ['slot','event_id','time_ms','sign','queue_ok','updated','snapshot_updated']else 'float64')for c in header}
    for x in pd.read_csv(inp,dtype=types,chunksize=50000):
     x.date=pd.to_datetime(x.date,format='%Y%m%d');table=pa.Table.from_pandas(x,preserve_index=False)
     if writer is None:writer=pq.ParquetWriter(out,table.schema,compression='zstd')
     writer.write_table(table);count+=len(x)
   finally:
    if writer:writer.close()
   counts[kind]=count
  if counts.get('daily',0)==0 or counts.get('minute',0)==0:raise ValueError('NO_SELECTED_STOCK_TABLES_IN_DAY_PACKAGE')
  z=dict(date=d,status='OK',scanner_sha256=identity,stocks_requested=len(codes),rows=counts,seconds=time.time()-t0,archive_bytes=int(row['size_bytes']),downloaded=own)
 except Exception as e:z=dict(date=d,status='FAILED',error=str(e),seconds=time.time()-t0)
 finally:
  if own and archive and archive.exists():archive.unlink()
  shutil.rmtree(tmp,ignore_errors=True)
 js(rec,z);return z

def main():
 rows=pd.read_csv(R/'tables/download_plan.csv').sort_values(['local','date'],ascending=[False,True]).to_dict('records');stop=threading.Event();threading.Thread(target=watch,args=(stop,),daemon=True).start()
 # Native decoding/replay is executed by four child processes; no extra decompression pool.
 try:
  with cf.ProcessPoolExecutor(max_workers=4,max_tasks_per_child=1)as pool:
   for z in pool.map(one,rows,chunksize=1):print('DAY',json.dumps(z),flush=True)
 finally:stop.set()
 records=[json.loads(p.read_text())for p in sorted((R/'logs/days').glob('*.json'))];save(pd.DataFrame(records),'day_processing_status.csv')
if __name__=='__main__':globals()[sys.argv[1]]()
