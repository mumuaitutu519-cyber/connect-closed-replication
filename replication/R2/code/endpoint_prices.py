"""Only registered reopening endpoints, streamed by day; R1 opening-price convention."""
import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
from pathlib import Path
import io,zipfile,numpy as np,pandas as pd,pyarrow.parquet as pq,concurrent.futures as cf,json,gc
R=Path(__file__).resolve().parents[1];T=Path('/Volumes/Extreme SSD/T9/_tmp/272');Q=Path('/Volumes/Extreme SSD/QDC/data/QDCData');RAW=Path('/Volumes/Extreme SSD/T9/codex项目/A股分钟线+日频量价/A股分钟数据/1m_price_zip');OUT=T/'endpoint_prices';OUT.mkdir(exist_ok=True)
def day(value):
 date=pd.Timestamp(value);dest=OUT/f'{date:%Y%m%d}.parquet'
 if dest.exists():return str(dest)
 univ=set(pd.read_csv(R/'meta/stock_universe.csv').code);archive=RAW/f'{date.year}.zip';member=f'{date:%Y%m%d}.parquet';pieces=[];source=[]
 if archive.exists()and member in zipfile.ZipFile(archive).namelist():
  with zipfile.ZipFile(archive)as z:
   p=pq.ParquetFile(io.BytesIO(z.read(member)))
   for b in p.iter_batches(batch_size=65536,columns=['code','trade_time','open','high','low','close'],use_threads=False):
    d=b.to_pandas();d=d[d.code.isin(univ)].copy();tm=pd.to_datetime(d.trade_time);d['minute']=tm.dt.hour*60+tm.dt.minute;d=d[d.minute.isin([570,571,600,900])];pieces.append(d[['code','minute','open','high','low','close']])
  source=[str(archive)+'!'+member]
 else:
  lower=int(date.value//10**6)-8*3600000;upper=lower+86400000
  for file in sorted((Q/'stocks_1m/full').glob('*.parquet')):
   if file.stem not in[str(date.year),f'{date:%Y-%m}',f'{date:%Y-%m-%d}']:continue
   p=pq.ParquetFile(file);groups=[]
   for j in range(p.num_row_groups):
    st=p.metadata.row_group(j).column(0).statistics
    if st is None or not st.has_min_max or(st.max>=lower and st.min<upper):groups.append(j)
   for b in p.iter_batches(batch_size=65536,row_groups=groups,columns=['ts','symbol','open','high','low','close'],use_threads=False):
    d=b.to_pandas();d=d[d.ts.ge(lower)&d.ts.lt(upper)].copy();d['minute']=((d.ts+8*3600000)//60000)%1440;d=d[d.minute.isin([570,571,600,900])].copy();d['code']=d.symbol.str[:6]+np.where(d.symbol.str.endswith('XSHG'),'.SH','.SZ');d=d[d.code.isin(univ)];pieces.append(d[['code','minute','open','high','low','close']])
   source.append(str(file))
 d=pd.concat(pieces,ignore_index=True).drop_duplicates(['code','minute']);bad=(d.open.le(0)|d.close.le(0)|d.high.lt(d.low)|~np.isfinite(d[['open','high','low','close']]).all(1));d.loc[bad,['open','close']]=np.nan
 op=d.pivot(index='code',columns='minute',values='open');cl=d.pivot(index='code',columns='minute',values='close');opening=op.get(570,pd.Series(np.nan,index=op.index)).fillna(op.get(571));out=pd.DataFrame(dict(code=cl.index,opening=opening,close30=cl.get(600),close=cl.get(900)));out['date']=date;out.to_parquet(dest,index=False);dest.with_suffix('.json').write_text(json.dumps(dict(date=str(date.date()),source=source,stocks=len(out)),ensure_ascii=False));return str(dest)
def build():
 events=pd.read_csv(R/'tables/events.csv',parse_dates=['end','resume']);days=sorted(set(events.end)|set(events.resume))
 with cf.ProcessPoolExecutor(max_workers=4)as pool:paths=list(pool.map(day,[str(d.date())for d in days]))
 prices=pd.concat([pd.read_parquet(p)for p in paths],ignore_index=True);factors=[]
 for b in pq.ParquetFile(Q/'cn_adj_factor/full/all.parquet').iter_batches(batch_size=100000,columns=['symbol','d','hfq_factor'],use_threads=False):
  f=b.to_pandas();f['code']=f.symbol.str[:6]+np.where(f.symbol.str.endswith('XSHG'),'.SH','.SZ');f=f[f.code.isin(prices.code.unique())];factors.append(f[['code','d','hfq_factor']])
 fac=pd.concat(factors,ignore_index=True);fac.d=pd.to_datetime(fac.d);dup=fac.duplicated(['code','d'],keep=False)
 if dup.any():assert fac[dup].groupby(['code','d']).hfq_factor.nunique().max()==1
 fac=fac.drop_duplicates(['code','d']).sort_values(['code','d']);rows=[]
 for code,g in prices.groupby('code'):
  h=fac[fac.code.eq(code)];h=h[h.hfq_factor.gt(0)&np.isfinite(h.hfq_factor)];g=g.sort_values('date');ix=np.searchsorted(h.d.to_numpy(),g.date.to_numpy(),side='right')-1;v=np.full(len(g),np.nan);good=ix>=0
  if len(h):v[good]=h.hfq_factor.to_numpy()[ix[good]]
  g=g.copy();g['hfq_factor']=v;rows.append(g)
 p=pd.concat(rows,ignore_index=True);p.to_parquet(T/'endpoint_prices_all.parquet',index=False);return p
if __name__=='__main__':build()
