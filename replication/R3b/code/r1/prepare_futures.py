import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[k]='1'
from pathlib import Path
import numpy as np,pandas as pd,concurrent.futures as cf,json,gc
ROOT=Path(__file__).resolve().parents[2];TMP=Path('/Volumes/Extreme SSD/T9/_tmp/282')
def file_daily(p):
 p=Path(p);out=[]
 for d in pd.read_csv(p,chunksize=100000):
  t=pd.to_datetime(d.bob,errors='coerce');day=t.dt.normalize();d['date']=day;d['end_time']=t+pd.Timedelta(minutes=1)
  d=d[day.ge('2016-12-01')&day.le('2026-11-07')]
  if not len(d):continue
  d['contract']=p.stem;out.append(d)
 if not out:return pd.DataFrame()
 d=pd.concat(out,ignore_index=True);d['product']=p.parent.name
 return d
def main():
 files=sorted((TMP/'futures_raw/CFFEX').glob('I[HF]/*.csv'));pieces=[]
 with cf.ProcessPoolExecutor(max_workers=4) as pool:
  for d in pool.map(file_daily,files):
   if len(d):
    p=TMP/'futures_contracts';p.mkdir(exist_ok=True);d.to_parquet(p/(d.contract.iloc[0]+'.parquet'),index=False)
    pieces.append(d.groupby(['product','contract','date'],as_index=False).volume.sum())
 daily=pd.concat(pieces,ignore_index=True);daily.to_csv(ROOT/'tables/futures_daily_volume.csv',index=False)
 choices=[]
 for product,dd in daily.groupby('product'):
  days=sorted(dd.date.unique())
  best=dd.sort_values(['date','volume','contract'],ascending=[True,False,True]).drop_duplicates('date')
  b=best.set_index('date')
  for i,t in enumerate(days):
   if i==0:continue
   previous=days[i-1];r=b.loc[previous];choices.append(dict(product=product,date=t,selection_date=previous,contract=r.contract,prior_day_volume=r.volume))
 ch=pd.DataFrame(choices);ch.to_csv(ROOT/'tables/futures_contract_selection.csv',index=False)
 matrices={};audits=[]
 for product,cp in ch.groupby('product'):
  codes=cp.contract.unique();frames=[]
  for c in codes:
   q=pd.read_parquet(TMP/'futures_contracts'/f'{c}.parquet');valid=set(cp.loc[cp.contract.eq(c),'date']);q=q[q.date.isin(valid)];frames.append(q)
  d=pd.concat(frames,ignore_index=True);d=d.drop_duplicates(['date','end_time']);days=pd.DatetimeIndex(sorted(cp.date.unique()));j=days.get_indexer(d.date);tm=d.end_time.dt.hour*60+d.end_time.dt.minute;slot=np.where(tm.le(690),tm-570,tm-780+120);mask=(tm.between(571,690)|tm.between(781,900))&(j>=0)
  close=np.full((len(days),241),np.nan);op=close.copy();close[j[mask],slot[mask]]=d.loc[mask,'close'];op[j[mask],slot[mask]]=d.loc[mask,'open']
  with np.errstate(divide='ignore',invalid='ignore'):
   r=np.log(close[:,1:]/close[:,:-1]);r[:,0]=np.log(close[:,1]/op[:,1]);r[:,120]=np.log(close[:,121]/op[:,121])
  np.savez_compressed(TMP/f'futures_{product}.npz',dates=days.to_numpy('datetime64[D]').astype('int64'),returns=r)
  audits.append(dict(product=product,dates=len(days),usable_dates=int((np.isfinite(r).sum(1)>=180).sum()),date_min=str(days.min().date()),date_max=str(days.max().date()),missing_selected_contract_days=int(np.sum(np.isfinite(r).sum(1)==0)),timestamp_convention='source bob is minute BEGIN; shifted +1 minute to stock minute END',selection='contract with highest volume on immediately preceding product trading day; no replacement if absent today'))
 pd.DataFrame(audits).to_csv(ROOT/'tables/futures_coverage.csv',index=False);print(pd.DataFrame(audits).to_string(index=False))
 # Remove only this task's extracted CSVs and per-contract temporary copies after aggregation.
 import shutil
 shutil.rmtree(TMP/'futures_raw');shutil.rmtree(TMP/'futures_contracts')
if __name__=='__main__':main()
