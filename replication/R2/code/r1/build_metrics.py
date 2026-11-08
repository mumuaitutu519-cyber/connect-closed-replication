"""Stream code/year blocks from QDC minute parquet, at most 4 single-thread workers."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[k]='1'
from pathlib import Path
import concurrent.futures as cf,multiprocessing as mp,json,time,warnings,gc,threading,ctypes,sys
import numpy as np,pandas as pd,pyarrow as pa,pyarrow.parquet as pq,psutil
pa.set_memory_pool(pa.system_memory_pool())
ROOT=Path(__file__).resolve().parents[2];TMP=Path('/Volumes/Extreme SSD/T9/_tmp/272');OUT=TMP/'metrics';OUT.mkdir(exist_ok=True)
QDC=Path('/Volumes/Extreme SSD/QDC/data/QDCData');FILES=sorted((QDC/'stocks_1m/full').glob('*.parquet'));PF={}
FUT={};FUTX={}
COLS=['ts','symbol','open','high','low','close','volume','amount']
def getpf(path):
 return pq.ParquetFile(path)
def safe_mean(a,axis=1):
 n=np.isfinite(a).sum(axis);return np.divide(np.nansum(a,axis),n,out=np.full(np.shape(n),np.nan,dtype=float),where=n>0)
def future_metrics(r,days):
 output={}
 for product in ['IF','IH']:
  if product not in FUT:
   p=TMP/f'futures_{product}.npz'
   if not p.exists():raise FileNotFoundError('Prepare futures before minute aggregation')
   with np.load(p) as z:FUT[product]={int(t):v.copy() for t,v in zip(z['dates'],z['returns'])}
  coefficient=np.full(len(r),np.nan);delay=coefficient.copy()
  for day in np.unique(days):
   if int(day) not in FUT[product]:continue
   key=(product,int(day))
   if key not in FUTX:
    f=FUT[product][int(day)];X=np.column_stack([np.ones(240),f,*[np.r_[np.full(lag,np.nan),f[:-lag]] for lag in range(1,6)]])
    X[:5,:]=np.nan;X[120:125,:]=np.nan;valid=np.isfinite(X).all(1);X=X[valid]
    if len(X)<180:FUTX[key]=None
    else:FUTX[key]=(valid,X,np.linalg.pinv(X),np.linalg.pinv(X[:,:2]))
   design=FUTX[key]
   if design is None:continue
   valid,X,A,A0=design;ids=np.flatnonzero(days==day);Y=r[ids][:,valid];complete=np.isfinite(Y).all(1)
   for group in [ids[complete]]:
    if not len(group):continue
    y=r[group][:,valid];b=y@A.T;b0=y@A0.T;sst=np.sum((y-y.mean(1)[:,None])**2,1);rss=np.sum((y-b@X.T)**2,1);rss0=np.sum((y-b0@X[:,:2].T)**2,1);r2=1-rss/sst;r20=1-rss0/sst;coefficient[group]=b[:,2:].sum(1);delay[group]=np.where(r2>1e-10,1-r20/r2,np.nan)
   for ii in ids[~complete]:
    y=r[ii,valid];v=np.isfinite(y)
    if v.sum()<180:continue
    x=X[v];y=y[v];b=np.linalg.lstsq(x,y,rcond=None)[0];b0=np.linalg.lstsq(x[:,:2],y,rcond=None)[0];sst=np.sum((y-y.mean())**2);r2=1-np.sum((y-x@b)**2)/sst;r20=1-np.sum((y-x[:,:2]@b0)**2)/sst;coefficient[ii]=b[2:].sum();delay[ii]=1-r20/r2 if r2>1e-10 else np.nan
  output[f'{product.lower()}_lag_sum']=coefficient;output[f'{product.lower()}_delay']=delay
 return output
def metrics(d,codes):
 d=d.drop_duplicates(['symbol','ts'],keep='first')
 ts=d.ts.to_numpy(np.int64)+8*3600000;day=ts//86400000;minute=(ts//60000)%1440
 slot=np.where(minute<=690,minute-570,minute-780+120)
 valid=((minute>=570)&(minute<=690))|((minute>=781)&(minute<=900))
 d=d.loc[valid];day=day[valid];slot=slot[valid]
 ci=pd.Categorical(d.symbol,categories=codes).codes.astype(np.int64);key=ci*100000+day;unique,ix=np.unique(key,return_inverse=True)
 x=np.full((len(unique),241,6),np.nan)
 values=d[['open','high','low','close','volume','amount']].to_numpy(np.float64,copy=True)
 bad=(values[:,0]<=0)|(values[:,3]<=0)|(values[:,1]<values[:,2])|~np.isfinite(values[:,:4]).all(1)
 values[bad,:]=np.nan;x[ix,slot,:]=values
 del d,values,ci,ix,key,ts,minute,day,slot
 op,hi,lo,cl,vol,amt=[x[:,:,k] for k in range(6)]
 with np.errstate(divide='ignore',invalid='ignore'):
  r=np.log(cl[:,1:]/cl[:,:-1]);opening=np.where(np.isfinite(op[:,0]),op[:,0],op[:,1]);r[:,0]=np.log(cl[:,1]/opening);r[:,120]=np.log(cl[:,121]/op[:,121])
  # Missing/invalid OHLC bars remain missing, never zero-filled returns.
  r[~np.isfinite(cl[:,1:])]=np.nan;n=np.isfinite(r).sum(1)
  hl=np.log(hi[:,1:]/lo[:,1:]);beta=hl[:,:-1]**2+hl[:,1:]**2
  gamma=np.log(np.maximum(hi[:,1:-1],hi[:,2:])/np.minimum(lo[:,1:-1],lo[:,2:]))**2
  den=3-2*np.sqrt(2);alpha=((np.sqrt(2*beta)-np.sqrt(beta))/den)-np.sqrt(gamma/den)
  spread=2*np.tanh(np.maximum(alpha,0)/2)*1e4;spread[:,119]=np.nan;cs=safe_mean(spread)
  eta=(np.log(hi)+np.log(lo))/2;lc=np.log(cl);arprod=(lc[:,1:-1]-eta[:,1:-1])*(lc[:,1:-1]-eta[:,2:]);arprod[:,119]=np.nan;ar=2*np.sqrt(np.maximum(safe_mean(arprod),0))*1e4
  sumn=np.zeros(len(n));den5=np.zeros(len(n));ss1=np.zeros(len(n));df1=np.zeros(len(n))
  for start,end in [(0,120),(120,240)]:
   rr=r[:,start:end];nn=np.isfinite(rr).sum(1);mu=safe_mean(rr);ss1+=np.nansum((rr-mu[:,None])**2,1);df1+=np.maximum(nn-1,0)
   w=np.lib.stride_tricks.sliding_window_view(rr,5,axis=1);s=w.sum(2);good=np.isfinite(s);sumn+=np.nansum((s-5*mu[:,None])**2,1);den5+=5*good.sum(1)*np.maximum(1-5/np.maximum(nn,1),0)
  var1=ss1/df1;vr=(sumn/den5)/var1
  a=r[:,:-1].copy();b=r[:,1:].copy();a[:,119]=np.nan;b[:,119]=np.nan;pair=np.isfinite(a)&np.isfinite(b);a[~pair]=np.nan;b[~pair]=np.nan;am=safe_mean(a);bm=safe_mean(b);a-=am[:,None];b-=bm[:,None];ac=np.nansum(a*b,1)/np.sqrt(np.nansum(a*a,1)*np.nansum(b*b,1))
  ill=np.where(amt[:,1:]>0,np.abs(r)/amt[:,1:]*1e6,np.nan);amihud=safe_mean(ill)
  amount=np.nansum(amt[:,1:],1);volume=np.nansum(vol[:,1:],1)
  o30=np.log(cl[:,30]/opening)*1e4;ret=np.log(cl[:,240]/opening)*1e4
  one=np.nanmax(hi[:,1:],1)<=np.nanmin(lo[:,1:],1)
  q=dict(cs_bp=cs,ar_bp=ar,vr5=vr,autocorr1=ac,amihud=amihud,open30_bp=o30,return_bp=ret,ln_amount=np.log(np.where(amount>0,amount,np.nan)),ln_volume=np.log(np.where(volume>0,volume,np.nan)),amount=amount,volume=volume,rv_bp2=np.nansum(r*r,1)*1e8,zero_return_share=np.sum(r==0,1)/n,valid_minutes=n,one_price=one)
  q.update(future_metrics(r,unique%100000))
 result=pd.DataFrame(q);result.insert(0,'date',pd.to_datetime(unique%100000,unit='D'));result.insert(0,'code',[(codes[i//100000][:6]+('.SH' if codes[i//100000].endswith('XSHG') else '.SZ')) for i in unique]);result['raw_eligible_day']=(n>=180)&~one&(amount>0)
 return result
def run_piece(job):
 year,block,codes,part=job;sub=OUT/'sub';sub.mkdir(exist_ok=True);dest=sub/f'{year}_{block:03d}_{part}.parquet';receipt=dest.with_suffix('.json')
 if dest.exists() and receipt.exists():return json.loads(receipt.read_text())
 start=time.time();pieces=[];ninput=0;rgread=0
 for path in FILES:
  if not path.name.startswith(str(year)):continue
  pf=getpf(path);idx=pf.schema_arrow.get_field_index('symbol');groups=[]
  for i in range(pf.num_row_groups):
   stat=pf.metadata.row_group(i).column(idx).statistics
   if not stat or not stat.has_min_max or (stat.max>=codes[0] and stat.min<=codes[-1]):groups.append(i)
  rgread+=len(groups)
  batch=None;d=None
  for batch in pf.iter_batches(batch_size=65536,row_groups=groups,columns=COLS,use_threads=False):
   d=batch.to_pandas(use_threads=False);ninput+=len(d);d=d[d.symbol.isin(codes)].copy()
   if len(d):
    d['symbol']=pd.Categorical(d.symbol,categories=codes);pieces.append(d)
  del batch,d;pf.close();del pf;gc.collect();pa.default_memory_pool().release_unused()
 if pieces:
  d=pd.concat(pieces,ignore_index=True);del pieces;duplicate=int(d.duplicated(['symbol','ts']).sum());nr=len(d);out=metrics(d,codes);del d
 else:out=pd.DataFrame();duplicate=0;nr=0
 out.to_parquet(dest,index=False,compression='zstd');n_days=len(out);del out;gc.collect();pa.default_memory_pool().release_unused()
 if sys.platform=='darwin':
  lib=ctypes.CDLL(None);relief=lib.malloc_zone_pressure_relief;relief.argtypes=[ctypes.c_void_p,ctypes.c_size_t];relief.restype=ctypes.c_size_t;relief(None,0)
 rss=psutil.Process().memory_info().rss
 rec=dict(year=year,block=block,stocks=len(codes),row_groups=rgread,input_rows_scanned=ninput,selected_minute_rows=nr,duplicate_minute_keys=duplicate,stock_days=n_days,rss_gb=rss/1e9,seconds=time.time()-start,path=str(dest));receipt.write_text(json.dumps(rec))
 if rss>1.7e9:raise MemoryError(f'Worker memory target exceeded: {rss}')
 return rec
def run(job):
 year,block,codes=job;dest=OUT/f'{year}_{block:03d}.parquet';receipt=dest.with_suffix('.json')
 if dest.exists() and receipt.exists():return json.loads(receipt.read_text())
 frames=[];receipts=[]
 for part,start in enumerate(range(0,len(codes),10)):
  rr=run_piece((year,block,codes[start:start+10],part));receipts.append(rr)
  if rr['stock_days']:frames.append(pq.ParquetFile(rr['path']).read(use_threads=False).to_pandas(use_threads=False))
 out=pd.concat(frames,ignore_index=True) if frames else pd.DataFrame();out.to_parquet(dest,index=False,compression='zstd')
 rec=dict(year=year,block=block,stocks=len(codes),row_groups=sum(x['row_groups'] for x in receipts),input_rows_scanned=sum(x['input_rows_scanned'] for x in receipts),selected_minute_rows=sum(x['selected_minute_rows'] for x in receipts),duplicate_minute_keys=sum(x['duplicate_minute_keys'] for x in receipts),stock_days=len(out),rss_gb=max(x['rss_gb'] for x in receipts),seconds=sum(x['seconds'] for x in receipts),path=str(dest));receipt.write_text(json.dumps(rec))
 for rr in receipts:Path(rr['path']).unlink();Path(rr['path']).with_suffix('.json').unlink()
 return rec
def main():
 import argparse
 ap=argparse.ArgumentParser();ap.add_argument('--pilot',action='store_true');a=ap.parse_args()
 assert json.loads((ROOT/'meta/literature_gate.json').read_text())['estimation_permitted']
 universe=pd.read_csv(ROOT/'meta/stock_universe.csv').code.tolist();sym=sorted([c[:6]+('.XSHG' if c.endswith('.SH') else '.XSHE') for c in universe]);blocks=[sym[i:i+20] for i in range(0,len(sym),20)]
 jobs=[(year,i,block) for year in range(2017,2027) for i,block in enumerate(blocks)]
 if a.pilot:jobs=[(2023,0,blocks[0]),(2026,0,blocks[0])]
 records=[];pending=[]
 for j in jobs:
  p=OUT/f'{j[0]}_{j[1]:03d}.json'
  if p.exists() and p.with_suffix('.parquet').exists():records.append(json.loads(p.read_text()))
  else:pending.append(j)
 print(json.dumps({'cached':len(records),'pending':len(pending)}),flush=True)
 stop=threading.Event()
 def monitor():
  me=psutil.Process();peak=0
  with (ROOT/'logs/resource_monitor.jsonl').open('a') as log:
   while not stop.wait(1):
    children=me.children(recursive=True);rss=me.memory_info().rss+sum(p.memory_info().rss for p in children if p.is_running());peak=max(peak,rss)
    log.write(json.dumps({'unix_time':time.time(),'aggregate_rss_gb':rss/1e9,'peak_gb':peak/1e9})+'\n');log.flush()
    if rss>6.8e9:
     for p in children:p.terminate()
     log.write(json.dumps({'status':'TERMINATED_MEMORY_BUDGET','rss':rss})+'\n');break
 thread=threading.Thread(target=monitor,daemon=True);thread.start()
 # Explicit bounded batches also work around Python 3.12 process-pool worker-recycling hangs.
 for start in range(0,len(pending),4):
  with cf.ProcessPoolExecutor(max_workers=4,mp_context=mp.get_context('spawn')) as pool:
   for r in pool.map(run,pending[start:start+4],chunksize=1):records.append(r)
  print(json.dumps(dict(completed=len(records),total=len(jobs),selected_minutes=sum(t['selected_minute_rows'] for t in records),max_worker_rss_gb=max(t['rss_gb'] for t in records),last=r)),flush=True)
 pd.DataFrame(records).to_csv(ROOT/('logs/metric_pilot.csv' if a.pilot else 'logs/metric_build.csv'),index=False)
 stop.set();thread.join(timeout=2)
if __name__=='__main__':
 warnings.filterwarnings('ignore',category=RuntimeWarning);main()
