"""No-look-ahead eligibility and expanding winsorization; all registered variants retained."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[k]='1'
from pathlib import Path
import numpy as np,pandas as pd,pyarrow as pa,pyarrow.parquet as pq,pyarrow.dataset as ds,concurrent.futures as cf,json,gc,argparse
pa.set_cpu_count(1);pa.set_io_thread_count(1)
ROOT=Path(__file__).resolve().parents[2];TMP=Path('/Volumes/Extreme SSD/T9/_tmp/272');BASE=TMP/'baseline';BASE.mkdir(exist_ok=True);PANEL=TMP/'panel';PANEL.mkdir(exist_ok=True)
METRICS=['cs_bp','ar_bp','vr5','autocorr1','amihud','if_lag_sum','if_delay','ih_lag_sum','ih_delay','open30_bp','ln_amount','ln_volume','return_bp','rv_bp2','zero_return_share']
def canonical(block):
 target=BASE/f'block_{block:03d}.parquet'
 if target.exists():return dict(block=block,status='CACHED')
 pieces=[]
 for year in range(2017,2027):
  p=TMP/'metrics'/f'{year}_{block:03d}.parquet'
  pf=pq.ParquetFile(p)
  if pf.metadata.num_rows:pieces.append(pf.read(use_threads=False).to_pandas(use_threads=False))
 if not pieces:return dict(block=block,status='EMPTY')
 f=pd.concat(pieces,ignore_index=True).sort_values(['code','date']);del pieces
 assert not f.duplicated(['code','date']).any()
 cal=pd.read_csv(ROOT/'meta/actual_full_calendar.csv',parse_dates=['date']);dates=cal.date.to_numpy('datetime64[ns]');univ=pd.read_csv(ROOT/'meta/stock_universe.csv',parse_dates=['first_observed_daily']).set_index('code')
 first=f.code.map(univ.first_observed_daily).to_numpy('datetime64[ns]');f['age']=np.searchsorted(dates,f.date.to_numpy('datetime64[ns]'))-np.searchsorted(dates,first)+1
 st=pq.ParquetFile('/Volumes/Extreme SSD/QDC/data/QDCData/cn_st/full/all.parquet').read(use_threads=False).to_pandas(use_threads=False);st=st[st.ts_code.isin(f.code.unique())];risk=np.zeros(len(f),bool)
 for rr in st.itertuples():risk|=(f.code.eq(rr.ts_code)&f.date.ge(pd.Timestamp(rr.st_start))&f.date.le(pd.Timestamp(rr.st_end) if pd.notna(rr.st_end) else pd.Timestamp('2100-01-01'))).to_numpy()
 f['st']=risk;f['eligible_day']=f.raw_eligible_day&f.age.ge(60)&~f.st
 official=pd.read_csv(ROOT/'tables/official_calendar.csv',parse_dates=['date']).set_index('date');f['nb_open']=f.date.map(official.nb_open).fillna(False).astype(bool)
 f.to_parquet(target,index=False,compression='zstd')
 return dict(block=block,stock_days=len(f),eligible=int(f.eligible_day.sum()),stocks=f.code.nunique())
def pooled(metric):
 tab=ds.dataset(BASE,format='parquet').to_table(columns=['date','eligible_day','nb_open',metric],filter=ds.field('eligible_day')&ds.field('nb_open'),use_threads=False);d=tab.to_pandas(use_threads=False);del tab;d=d[np.isfinite(d[metric])].sort_values('date');v=d[metric].to_numpy();dates=d.date.to_numpy('datetime64[ns]')
 ex=pd.read_parquet(TMP/'exposures.parquet',columns=['event_id','freeze_date']).drop_duplicates('event_id');out=[]
 for r in ex.itertuples():
  j=np.searchsorted(dates,np.datetime64(r.freeze_date),side='left');vals=v[:j];q=np.quantile(vals,[.005,.01,.99,.995]) if len(vals) else np.full(4,np.nan)
  out.append(dict(event_id=r.event_id,metric=metric,baseline_before=r.freeze_date,n=len(vals),q005=q[0],q01=q[1],q99=q[2],q995=q[3]))
 return out
def panel(block):
 p=BASE/f'block_{block:03d}.parquet'
 if not p.exists():return dict(block=block,status='EMPTY')
 f=pd.read_parquet(p).sort_values(['code','date']);f['pre60_normal_amount']=np.nan
 mapping=pd.read_csv(ROOT/'tables/event_date_map.csv',parse_dates=['date','anchor']);main_dates=set(mapping.date)
 out=f[f.date.isin(main_dates)&f.eligible_day].copy();out=out.merge(mapping[['date','event_id','closed','relative','resume','anchor']],on='date',validate='m:1')
 exp=pd.read_parquet(TMP/'exposures.parquet');exp=exp[exp.code.isin(f.code.unique())].drop(columns=['anchor','first_observed_daily']);out=out.merge(exp,on=['event_id','code'],validate='m:1')
 for event,idx in out.groupby('event_id').groups.items():
  freeze=out.loc[idx,'freeze_date'].iloc[0];hist=f[f.date.lt(freeze)&f.eligible_day&f.nb_open].groupby('code').tail(60);summary=hist.groupby('code').amount.agg(['median','count']);summary.loc[summary['count']<30,'median']=np.nan;out.loc[idx,'pre60_normal_amount']=out.loc[idx,'code'].map(summary['median']).to_numpy()
 thresholds=pd.read_csv(ROOT/'tables/pooled_winsor_thresholds.csv').set_index(['event_id','metric'])
 counts=[]
 for metric in METRICS:
  for name,lo,hi in [('w01',.01,.99),('w005',.005,.995)]:
   lower=pd.Series(np.nan,index=f.index);upper=lower.copy();nprior=lower.copy()
   for c,ix in f.groupby('code',sort=False).groups.items():
    g=f.loc[ix];z=g.loc[g.eligible_day&g.nb_open,metric];z=z[np.isfinite(z)]
    # Threshold at a normal day uses only earlier normal days; at a closed day carry last normal-day quantile including that last normal day.
    ql=z.expanding(min_periods=60).quantile(lo);qh=z.expanding(min_periods=60).quantile(hi);nn=pd.Series(np.arange(1,len(z)+1),index=z.index)
    sparse_l=ql.reindex(g.index).ffill();sparse_h=qh.reindex(g.index).ffill();sparse_n=nn.reindex(g.index).ffill().fillna(0)
    normal_ix=z.index
    sparse_l.loc[normal_ix]=ql.shift(1).to_numpy();sparse_h.loc[normal_ix]=qh.shift(1).to_numpy();sparse_n.loc[normal_ix]=nn.shift(1,fill_value=0).to_numpy()
    lower.loc[ix]=sparse_l;upper.loc[ix]=sparse_h;nprior.loc[ix]=sparse_n
   look=pd.DataFrame({'code':f.code,'date':f.date,'lo':lower,'hi':upper,'nprior':nprior});o=out[['code','date','event_id',metric]].merge(look,on=['code','date'],validate='1:1');fallback=o.nprior.lt(60)|o.lo.isna()|o.hi.isna()
   preflo='q01' if name=='w01' else 'q005';prefhi='q99' if name=='w01' else 'q995'
   o.loc[fallback,'lo']=[thresholds.loc[(e,metric),preflo] for e in o.loc[fallback,'event_id']];o.loc[fallback,'hi']=[thresholds.loc[(e,metric),prefhi] for e in o.loc[fallback,'event_id']]
   out[f'{metric}__{name}']=o[metric].clip(o.lo,o.hi).to_numpy();counts.append(dict(block=block,metric=metric,variant=name,n=len(out),fallback_pooled=int(fallback.sum()),winsorized=int(((o[metric]<o.lo)|(o[metric]>o.hi)).sum())))
 out.to_parquet(PANEL/f'block_{block:03d}.parquet',index=False,compression='zstd');return dict(block=block,rows=len(out),stocks=out.code.nunique(),winsor=counts)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['canonical','pooled','panel']);a=ap.parse_args();n=int(np.ceil(len(pd.read_csv(ROOT/'meta/stock_universe.csv'))/20));jobs=range(n)
 if a.stage=='canonical':
  with cf.ProcessPoolExecutor(max_workers=4) as p:records=list(p.map(canonical,jobs))
  pd.DataFrame(records).to_csv(ROOT/'logs/canonical_build.csv',index=False)
 elif a.stage=='pooled':
  # Each worker reads one numeric outcome and two flags, keeping aggregate RSS below the reserved budget.
  records=[]
  for start in range(0,len(METRICS),4):
   with cf.ProcessPoolExecutor(max_workers=4) as p:records.extend(r for rr in p.map(pooled,METRICS[start:start+4]) for r in rr)
  pd.DataFrame(records).to_csv(ROOT/'tables/pooled_winsor_thresholds.csv',index=False)
 else:
  with cf.ProcessPoolExecutor(max_workers=4) as p:records=list(p.map(panel,jobs))
  pd.DataFrame([{k:v for k,v in r.items() if k!='winsor'} for r in records]).to_csv(ROOT/'logs/panel_build.csv',index=False);pd.DataFrame([v for r in records for v in r.get('winsor',[])]).to_csv(ROOT/'tables/winsor_audit.csv',index=False)
 print(a.stage,'COMPLETE',len(records),flush=True)
if __name__=='__main__':main()
