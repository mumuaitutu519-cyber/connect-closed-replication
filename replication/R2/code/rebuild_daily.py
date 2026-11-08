"""Reuse R1 daily reader and formulas; add registered frequency and big-move outcomes."""
import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parent/'r1'))
import build_metrics as bm,build_metrics_daily as bd
import numpy as np,pandas as pd,concurrent.futures as cf,json,pyarrow as pa
R=Path(__file__).resolve().parents[1];T=Path('/Volumes/Extreme SSD/T9/_tmp/272');ORIGINAL=bm.future_metrics
EXT=[f'{p}_{kind}' for p in ['if','ih'] for kind in ['delay_f5','delay_f15','lag_bigday','lag_bigpre']]
FUT={}
for p in ['IF','IH']:
 with np.load(T/f'futures_{p}.npz') as z:FUT[p]={int(k):v for k,v in zip(z['dates'],z['returns'])}
cal=pd.read_csv(R/'tables/official_calendar.csv',parse_dates=['date']);normal=set(cal.loc[cal.nb_open.eq(True),'date'].to_numpy('datetime64[D]').astype('int64'))
ex=pd.read_parquet(T/'exposures.parquet',columns=['event_id','freeze_date']).drop_duplicates();ev={int(r.event_id):np.datetime64(r.freeze_date,'D').astype('int64') for r in ex.itertuples()}
mp=pd.read_csv(R/'tables/event_date_map.csv',parse_dates=['date']);dayevent=dict(zip(mp.date.to_numpy('datetime64[D]').astype('int64'),mp.event_id))
THRESH={}
for day in FUT['IF']:
 cutoff=ev[dayevent[day]] if day in dayevent else day
 prior=sorted(d for d in FUT['IF'] if d<cutoff and d in normal)[-60:]
 v=np.concatenate([FUT['IF'][d] for d in prior]) if prior else np.array([]);v=v[np.isfinite(v)];THRESH[day]=np.quantile(np.abs(v),.9) if len(prior)>=30 and len(v) else np.nan

def fit_many(y,x,mask,minn):
 out=np.full((len(y),2),np.nan)
 valid=np.isfinite(x).all(1)&mask;x=x[valid];y=y[:,valid]
 if len(x)<minn or np.linalg.matrix_rank(x)<x.shape[1]:return out
 complete=np.isfinite(y).all(1)
 for ids in [np.flatnonzero(complete)]:
  if not len(ids):continue
  yy=y[ids];b=yy@np.linalg.pinv(x).T;b0=yy@np.linalg.pinv(x[:,:2]).T;sst=np.sum((yy-yy.mean(1)[:,None])**2,1)
  with np.errstate(divide='ignore',invalid='ignore'):
   r2=1-np.sum((yy-b@x.T)**2,1)/sst;r20=1-np.sum((yy-b0@x[:,:2].T)**2,1)/sst
   out[ids,0]=b[:,2:].sum(1);out[ids,1]=np.where(r2>1e-10,1-r20/r2,np.nan)
 for i in np.flatnonzero(~complete):
  keep=np.isfinite(y[i]);xx=x[keep];yy=y[i,keep]
  if len(yy)<minn or np.linalg.matrix_rank(xx)<xx.shape[1]:continue
  b=np.linalg.lstsq(xx,yy,rcond=None)[0];b0=np.linalg.lstsq(xx[:,:2],yy,rcond=None)[0];sst=np.sum((yy-yy.mean())**2)
  if sst>0:
   r2=1-np.sum((yy-xx@b)**2)/sst;r20=1-np.sum((yy-xx[:,:2]@b0)**2)/sst;out[i]=[b[2:].sum(),1-r20/r2 if r2>1e-10 else np.nan]
 return out

def extended(r,days):
 out=ORIGINAL(r,days)
 for m in EXT:out[m]=np.full(len(r),np.nan)
 for day in np.unique(days):
  ids=np.flatnonzero(days==day)
  if day not in FUT['IF']:continue
  f0=FUT['IF'][day]
  for p in ['IF','IH']:
   f=FUT[p].get(day)
   if f is None:continue
   for freq in [5,15]:
    yy=r[ids].reshape(len(ids),2,120//freq,freq).sum(3).reshape(len(ids),240//freq);ff=f.reshape(2,120//freq,freq).sum(2).ravel();n=len(ff)
    x=np.column_stack([np.ones(n),ff,*[np.r_[np.full(l,np.nan),ff[:-l]] for l in range(1,6)]]);x[:5]=np.nan;x[n//2:n//2+5]=np.nan
    out[f'{p.lower()}_delay_f{freq}'][ids]=fit_many(yy,x,np.ones(n,bool),int(np.ceil((n-10)*.8)))[:,1]
   x=np.column_stack([np.ones(240),f,*[np.r_[np.full(l,np.nan),f[:-l]] for l in range(1,6)]]);x[:5]=np.nan;x[120:125]=np.nan
   for key,threshold in [('bigday',np.nanquantile(np.abs(f0),.9)),('bigpre',THRESH[day])]:
    out[f'{p.lower()}_lag_{key}'][ids]=fit_many(r[ids],x,np.abs(f0)>=threshold,12)[:,0]
 return out
bm.future_metrics=extended

def main():
 days=cal.loc[cal.a_open,'date'];jobs=[str(t.date()) for t in days if not (bd.OUT/f'{t:%Y%m%d}.parquet').exists()];records=[]
 print(json.dumps(dict(pending=len(jobs),days=len(days))),flush=True)
 for start in range(0,len(jobs),16):
  with cf.ProcessPoolExecutor(max_workers=4) as pool:
   for rr in pool.map(bd.one_day,jobs[start:start+16],chunksize=1):records.append(rr)
  print(json.dumps(dict(completed=len(records),total=len(jobs),last=rr['date'],worker_gb=rr['rss_gb'])),flush=True)
 records=[json.loads(p.read_text()) for p in sorted(bd.OUT.glob('*.json'))];pd.DataFrame(records).to_csv(R/'logs/metric_daily_build.csv',index=False)
 with cf.ProcessPoolExecutor(max_workers=4) as pool:
  for rr in pool.map(bd.pack_year,range(2017,2027)):print(rr,flush=True)
if __name__=='__main__':main()
