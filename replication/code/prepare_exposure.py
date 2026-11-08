import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[k]='1'
from pathlib import Path
import json,datetime,hashlib
import pandas as pd,numpy as np,pyarrow.parquet as pq
ROOT=Path(__file__).resolve().parents[1]
TMP=Path('/Volumes/Extreme SSD/T9/_tmp/266')
QDC=Path('/Volumes/Extreme SSD/QDC/data/QDCData')
def ascode(s):return s.str[:6]+np.where(s.str.endswith(('.SH','.XSHG')),'.SH','.SZ')
def main():
 cal=pd.read_csv(ROOT/'tables/official_calendar.csv',parse_dates=['date']);events=pd.read_csv(ROOT/'tables/events.csv',parse_dates=['start','end','resume'])
 # Primary original eligibility XLS downloaded into this task, not today's list applied retrospectively.
 from fetch_sources import fetch
 jobs=[]
 base='https://www.hkex.com.hk/-/media/HKEX-Market/Mutual-Market/Stock-Connect/Eligible-Stocks/View-All-Eligible-Securities_xls/'
 for market in ['SSE','SZSE']:jobs.append((f'Change_of_{market}_Securities_Lists.xls',base+f'Change_of_{market}_Securities_Lists.xls'))
 jobs += [('quarterly_disclosure_20240726.pdf','https://www.hkex.com.hk/-/media/HKEX-Market/Services/Circulars-and-Notices/Participant-and-Members-Circulars/HKSCC/2024/ce_HKSCC_NOM_217_2024.pdf')]
 rs=[fetch(j) for j in jobs];rpath=ROOT/'meta/official_receipts.json';rpath.write_text(json.dumps(json.loads(rpath.read_text())+rs,indent=2))
 ee=[]
 for market,suffix in [('SSE','SH'),('SZSE','SZ')]:
  p=ROOT/f'meta/official_raw/Change_of_{market}_Securities_Lists.xls'
  if not p.exists():continue
  d=pd.read_excel(p,header=3);d.columns=['source_row','stock_code','name','change','remarks','effective_date'];d=d[d.stock_code.notna()&d.effective_date.notna()].copy();d['code']=pd.to_numeric(d.stock_code,errors='raise').astype(int).astype(str).str.zfill(6)+'.'+suffix;d.effective_date=pd.to_datetime(d.effective_date);ee.append(d)
 eligibility=pd.concat(ee,ignore_index=True);eligibility.to_csv(ROOT/'meta/eligibility_events.csv',index=False)
 # All ownership records fit in 32MB compressed; select three columns in 100k-row batches.
 pieces=[];source=QDC/'cn_hsgt/hk_hold/full/all.parquet'
 for b in pq.ParquetFile(source).iter_batches(batch_size=100000,columns=['trade_date','ts_code','ratio'],use_threads=False):
  d=b.to_pandas();d=d[d.ts_code.str.endswith(('.SH','.SZ'))];pieces.append(d)
 h=pd.concat(pieces,ignore_index=True).rename(columns={'trade_date':'holding_date','ts_code':'code','ratio':'dose'});h.holding_date=pd.to_datetime(h.holding_date)
 del pieces
 dup=h.duplicated(['code','holding_date'],keep=False)
 if dup.any():
  h[dup].to_csv(ROOT/'tables/hold_duplicates.csv',index=False)
  if h[dup].groupby(['code','holding_date']).dose.nunique().max()>1:raise ValueError('Conflicting ownership ratios')
  h=h.drop_duplicates(['code','holding_date'])
 hh=h.groupby('holding_date').agg(stocks=('code','nunique'),mean_ratio=('dose','mean'),min_ratio=('dose','min'),max_ratio=('dose','max')).reset_index();hh.to_csv(ROOT/'tables/holding_coverage_by_date.csv',index=False)
 normal=cal[cal.nb_open.eq(True)].date.sort_values().to_numpy('datetime64[ns]')
 # Available only on the day AFTER the official release day, avoiding intraday publication uncertainty.
 avail={}
 for t in h.holding_date.unique():
  if t<pd.Timestamp('2024-08-19'):release=t
  elif t.is_quarter_end:
   pos=np.searchsorted(normal,t.to_datetime64(),side='right')+4
   release=pd.Timestamp(normal[pos]) if pos<len(normal) else pd.Timestamp.max
  else:
   # Vendor daily dates after dissemination stop are not treated as public daily knowledge.
   avail[t]=pd.Timestamp.max;continue
  avail[t]=release+pd.Timedelta(days=1) if release!=pd.Timestamp.max else pd.Timestamp.max
 h['available_date']=h.holding_date.map(avail)
 h=h[h.available_date<pd.Timestamp.max].sort_values(['available_date','holding_date','code'])
 h.to_parquet(TMP/'holdings_public.parquet',index=False)
 # Stock universe from compact daily files, no minute/tick table loaded wholesale.
 codes=set();first={};daily_files=[]
 for p in sorted((QDC/'cn_daily_full/full').glob('*.parquet')):
  if not p.stem[:4].isdigit() or not 2016<=int(p.stem[:4])<=2026:continue
  daily_files.append(str(p))
  for b in pq.ParquetFile(p).iter_batches(batch_size=100000,columns=['symbol','ts'],use_threads=False):
   d=b.to_pandas();d=d[d.symbol.str.match(r'^(?:60\d{4}|688\d{3})\.XSHG$|^(?:00[0-3]\d{3}|30[01]\d{3})\.XSHE$')];d['code']=ascode(d.symbol);d['date']=pd.to_datetime(d.ts+8*3600000,unit='ms').dt.normalize();d=d[d.date.le(pd.Timestamp('2026-10-30'))]
   for c,t in d.groupby('code').date.min().items():codes.add(c);first[c]=min(first.get(c,t),t)
 pd.DataFrame({'code':sorted(codes),'first_observed_daily':[first[c] for c in sorted(codes)]}).to_csv(ROOT/'meta/stock_universe.csv',index=False)
 out=[];coverage=[]
 for ev in events.itertuples():
  # Freeze on the earliest control day. It is necessarily before the closure and prevents control-window forward assignment.
  em=pd.read_csv(ROOT/'tables/event_date_map_all.csv',parse_dates=['date']);freeze=em.loc[em.event_id.eq(ev.event_id),'date'].min()
  state={}
  for row in eligibility[eligibility.effective_date.lt(freeze)].sort_values(['effective_date','source_row'],ascending=[True,False]).itertuples():
   s=str(row.change);c=row.code
   if s=='Addition' or s.startswith('Addition (from List of Special') or 'changed from' in s:state[c]=1
   elif s.startswith('Transfer to List of Special') or s.startswith('Addition to List of Special') or s=='Removal' or 'changed to' in s or s=='Buy orders suspended':state[c]=0
   elif s=='Buy orders resumed':state[c]=1
  # Nearest available disclosure common date per exchange, not an arbitrary old record per stock.
  hc=h[h.available_date.lt(freeze)].sort_values(['available_date','holding_date']).drop_duplicates('code',keep='last')
  latest_by_exchange=hc.assign(exchange=hc.code.str[-2:]).groupby('exchange').holding_date.max().to_dict()
  by=hc.set_index('code');npositive=0;nknown=0
  for c in sorted(codes):
   eligible=state.get(c,0);rec=by.loc[c] if c in by.index else None
   dose=float(rec.dose) if rec is not None else (0.0 if not eligible else np.nan)
   hd=rec.holding_date if rec is not None else pd.NaT;ad=rec.available_date if rec is not None else pd.NaT
   # Stop stale individual holding records when stock disappears from the latest exchange snapshot.
   if rec is not None:
    exchange=c[-2:];latest=latest_by_exchange.get(exchange,pd.NaT)
    if hd<latest:
     dose=0.0 if not eligible else np.nan;hd=pd.NaT;ad=pd.NaT
   nknown+=np.isfinite(dose);npositive+=bool(np.isfinite(dose) and dose>0)
   out.append(dict(event_id=ev.event_id,code=c,freeze_date=freeze,anchor=ev.start,eligible=eligible,dose=dose,holding_date=hd,available_date=ad,frequency='quarterly' if pd.notna(hd) and hd>=pd.Timestamp('2024-08-19') else 'daily',first_observed_daily=first[c]))
  coverage.append(dict(event_id=ev.event_id,start=ev.start,freeze=freeze,universe=len(codes),eligible=sum(state.get(c,0) for c in codes),dose_known=nknown,dose_positive=npositive))
 o=pd.DataFrame(out);o.to_parquet(TMP/'exposures.parquet',index=False);o.to_csv(ROOT/'tables/exposure_by_event.csv',index=False);pd.DataFrame(coverage).to_csv(ROOT/'tables/exposure_coverage.csv',index=False)
 print(pd.DataFrame(coverage).to_string(index=False))
 print('HOLD_COVERAGE',h.holding_date.min(),h.holding_date.max(),len(h),h.code.nunique())
if __name__=='__main__':main()
