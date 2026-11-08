from common import *
import concurrent.futures as cf,pyarrow.parquet as pq
E=pd.read_csv(R/'tables/events.csv');U=pd.read_csv(P/'meta/stock_universe.csv',parse_dates=['first_observed_daily']);EL=pd.read_csv(P/'meta/eligibility_events.csv',parse_dates=['effective_date'])
def cutoff(ev):return pd.Timestamp(ev['start'])+pd.Timedelta(minutes=835 if ev.get('closure_type')=='partial_close' else 570)
def one(codes):
 pieces=[];code_set=set(codes)
 for b in pq.ParquetFile(T/'holdings_public.parquet').iter_batches(batch_size=65536,columns=['code','dose','holding_date','available_date'],use_threads=False):
  d=b.to_pandas(use_threads=False);d=d[d.code.isin(code_set)]
  if len(d):pieces.append(d)
 h=pd.concat(pieces,ignore_index=True).sort_values(['available_date','holding_date','code']) if pieces else pd.DataFrame(columns=['code','dose','holding_date','available_date']);del pieces;elig=EL[EL.code.isin(code_set)];master=pd.read_csv(R/'meta/latest_snapshot_dates.csv',parse_dates=['holding_date']).set_index(['event_id','exchange']).holding_date;out=[]
 for ev in E.to_dict('records'):
  eid=int(ev['event_id']);cut=cutoff(ev);state={}
  for row in elig[elig.effective_date.lt(cut)].sort_values(['effective_date','source_row'],ascending=[True,False]).itertuples():
   s=str(row.change)
   if s=='Addition' or s.startswith('Addition (from List of Special') or 'changed from' in s:state[row.code]=1
   elif s.startswith('Transfer to List of Special') or s.startswith('Addition to List of Special') or s=='Removal' or 'changed to' in s or s=='Buy orders suspended':state[row.code]=0
   elif s=='Buy orders resumed':state[row.code]=1
  by=h[h.available_date.lt(cut)].drop_duplicates('code',keep='last').set_index('code')
  for c in codes:
   rec=by.loc[c] if c in by.index else None;eligible=state.get(c,0);dose=float(rec.dose) if rec is not None else (0. if not eligible else np.nan);hd=rec.holding_date if rec is not None else pd.NaT;ad=rec.available_date if rec is not None else pd.NaT
   if rec is not None and hd<master.get((eid,c[-2:]),pd.NaT):dose=0. if not eligible else np.nan;hd=pd.NaT;ad=pd.NaT
   out.append(dict(event_id=eid,code=c,dose_event_latest=dose,eligible_event_latest=eligible,cutoff_event_latest=cut,holding_date_event_latest=hd,available_date_event_latest=ad))
 return pd.DataFrame(out)
def main():
 # Global exchange snapshot dates are determined in a bounded metadata-column pass.
 dates={}
 for b in pq.ParquetFile(T/'holdings_public.parquet').iter_batches(batch_size=65536,columns=['code','holding_date','available_date'],use_threads=False):
  d=b.to_pandas(use_threads=False);d['exchange']=d.code.str[-2:]
  for (exchange,available),value in d.groupby(['exchange','available_date'],observed=True).holding_date.max().items():dates[(exchange,available)]=max(dates.get((exchange,available),pd.Timestamp.min),value)
 rows=[]
 for ev in E.to_dict('records'):
  for exchange in ['SH','SZ']:
   values=[v for (ex,t),v in dates.items() if ex==exchange and t<cutoff(ev)];rows.append(dict(event_id=int(ev['event_id']),exchange=exchange,holding_date=max(values) if values else pd.NaT))
 save(pd.DataFrame(rows),R/'meta/latest_snapshot_dates.csv');codes=sorted(U.code);jobs=[codes[j:j+200] for j in range(0,len(codes),200)];out=[]
 with cf.ProcessPoolExecutor(max_workers=4) as pool:
  for i,d in enumerate(pool.map(one,jobs,chunksize=1)):
   out.append(d)
   if i%5==0:print('latest_public_dose_stock_block',i,flush=True)
 f=pd.concat(out,ignore_index=True);assert len(f)==len(U)*len(E);assert not f.duplicated(['event_id','code']).any();assert (f.available_date_event_latest.isna()|f.available_date_event_latest.lt(f.cutoff_event_latest)).all();assert (f.holding_date_event_latest.isna()|f.holding_date_event_latest.lt(f.cutoff_event_latest.dt.normalize())).all();f.to_parquet(T/'exposures_event_latest.parquet',index=False);save(f,R/'tables/exposure_event_latest.csv')
 old=pd.read_parquet(T/'exposures.parquet');audit=old[['event_id','code','dose','holding_date','available_date','freeze_date']].rename(columns={'dose':'dose_window_freeze','holding_date':'holding_date_window_freeze','available_date':'available_date_window_freeze'}).merge(f,on=['event_id','code'],validate='1:1');audit['dose_difference']=audit.dose_event_latest-audit.dose_window_freeze;save(audit,R/'tables/exposure_timing_sensitivity.csv')
 if (R/'tables/exposure_by_event.csv').exists():save(pd.read_csv(R/'tables/exposure_by_event.csv'),R/'tables/exposure_window_freeze_by_event.csv')
 save(audit[audit.event_id>100],R/'tables/exposure_by_event.csv');print('Latest public holding frozen before actual event time',len(f))
if __name__=='__main__':main()
