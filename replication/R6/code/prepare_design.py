from common import *
import pyarrow.parquet as pq

def main():
 assert json.loads((R/'meta/calendar_gate.json').read_text())['gate']=='PASS'
 cal=loadcal();weather=pd.read_csv(R/'typhoon_calendar.csv',parse_dates=['date']);bad=set(weather.loc[weather.included,'date']);normal=cal.loc[cal.a_open&cal.nb_open&~cal.date.isin(bad),'date'].sort_values();actual=cal.loc[cal.a_open,'date'].sort_values();pos={d:i for i,d in enumerate(actual)}
 holiday=pd.read_csv(P/'tables/events.csv',parse_dates=['start','end','resume']);holiday['kind']='holiday';holiday['anticipation']='scheduled';holiday['dates']=holiday.apply(lambda x:actual[actual.between(x.start,x.end)].tolist(),axis=1);events=holiday.to_dict('records');eid=100
 for kind,sel in [('weather',weather.included),('placebo',weather.placebo)]:
  ww=weather[sel].sort_values('date');blocks=[]
  for r in ww.itertuples():
   if blocks and kind=='placebo' and pos[r.date]==pos[blocks[-1][-1].date]+1 and r.storm==blocks[-1][-1].storm:blocks[-1].append(r)
   else:blocks.append([r])
  for rows in blocks:
   eid+=1;ds=[r.date for r in rows];start,end=ds[0],ds[-1];pre=normal[normal<start].tail(5);post=normal[normal>end].head(5);r=rows[0]
   events.append(dict(event_id=eid,start=start,end=end,resume=post.iloc[0] if len(post) else pd.NaT,n_closed_days=len(ds),n_pre=len(pre),n_post=len(post),kind=kind,anticipation=r.anticipation,closure_type=r.closure_type,storm=r.storm,dates=ds,closed_start=r.nb_closed_start_minute,closed_end=r.nb_closed_end_minute))
 mapping=[]
 oldmap=pd.read_csv(P/'tables/event_date_map.csv',parse_dates=['date','anchor'])
 for ev in events:
  eid=ev['event_id'];start,end=ev['start'],ev['end']
  if ev['kind']=='holiday':
   mm=oldmap[oldmap.event_id.eq(eid)].copy();freeze=pd.read_csv(P/'tables/exposure_by_event.csv',usecols=['event_id','freeze_date']).groupby('event_id').freeze_date.first()[eid];ev['freeze_date']=pd.Timestamp(freeze)
   for q in mm.itertuples():mapping.append(dict(event_id=eid,date=q.date,anchor=start,kind='holiday',role=q.role,closed=int(q.closed),resume=int(q.resume),relative=q.relative))
   continue
  pre=normal[normal<start].tail(5).tolist();post=normal[normal>end].head(5).tolist();ev['freeze_date']=min(pre) if pre else start
  if ev['closure_type'].startswith('partial'):post=[]
  for j,d in enumerate(pre):mapping.append(dict(event_id=eid,date=d,anchor=start,kind=ev['kind'],role='control_pre',closed=0,resume=0,relative=j-len(pre)))
  for j,d in enumerate(ev['dates']):mapping.append(dict(event_id=eid,date=d,anchor=start,kind=ev['kind'],role='closed',closed=1,resume=0,relative=j))
  for j,d in enumerate(post):mapping.append(dict(event_id=eid,date=d,anchor=start,kind=ev['kind'],role='control_post',closed=0,resume=int(j==0),relative=j+1))
 e=pd.DataFrame(events).drop(columns='dates');save(e,R/'tables/events.csv');m=pd.DataFrame(mapping);save(m,R/'tables/event_map_all.csv')
 # Deduplicate within each analytical family; holiday sample is untouched.
 eventkind={r.event_id:('partial' if str(r.closure_type).startswith('partial') else r.kind) for r in e.itertuples()}
 m['family']=m.event_id.map(eventkind);m['distance']=(m.date-m.anchor).abs().dt.days;m=m.sort_values(['family','date','distance','anchor']).drop_duplicates(['family','date']);save(m,R/'tables/event_map.csv')
 univ=pd.read_csv(P/'meta/stock_universe.csv',parse_dates=['first_observed_daily']);elig=pd.read_csv(P/'meta/eligibility_events.csv',parse_dates=['effective_date']);h=[]
 for b in pq.ParquetFile(Q/'cn_hsgt/hk_hold/full/all.parquet').iter_batches(batch_size=100000,columns=['trade_date','ts_code','ratio'],use_threads=False):
  d=b.to_pandas(use_threads=False);d=d[d.ts_code.isin(set(univ.code))];h.append(d)
 h=pd.concat(h,ignore_index=True).rename(columns={'trade_date':'holding_date','ts_code':'code','ratio':'dose'});h.holding_date=pd.to_datetime(h.holding_date);h=h.drop_duplicates(['code','holding_date']);avail={}
 officialnormal=cal.loc[cal.nb_open,'date'].to_numpy('datetime64[ns]')
 for t in h.holding_date.unique():
  if t<pd.Timestamp('2024-08-19'):release=t
  elif t.is_quarter_end:
   ix=np.searchsorted(officialnormal,t.to_datetime64(),side='right')+4;release=pd.Timestamp(officialnormal[ix]) if ix<len(officialnormal) else pd.Timestamp.max
  else:avail[t]=pd.Timestamp.max;continue
  avail[t]=release+pd.Timedelta(days=1) if release!=pd.Timestamp.max else pd.Timestamp.max
 h['available_date']=h.holding_date.map(avail);h=h[h.available_date.lt(pd.Timestamp.max)].sort_values(['available_date','holding_date','code']);h.to_parquet(T/'holdings_public.parquet',index=False)
 ex0=pd.read_csv(P/'tables/exposure_by_event.csv',parse_dates=['freeze_date','anchor','holding_date','available_date','first_observed_daily']);out=[ex0];aud=[]
 def snapshot(freeze,anchor,eid):
  state={}
  for r in elig[elig.effective_date.lt(freeze)].sort_values(['effective_date','source_row'],ascending=[True,False]).itertuples():
   s=str(r.change)
   if s=='Addition' or s.startswith('Addition (from List of Special') or 'changed from' in s:state[r.code]=1
   elif s.startswith('Transfer to List of Special') or s.startswith('Addition to List of Special') or s=='Removal' or 'changed to' in s or s=='Buy orders suspended':state[r.code]=0
   elif s=='Buy orders resumed':state[r.code]=1
  hc=h[h.available_date.lt(freeze)].drop_duplicates('code',keep='last');latest=hc.assign(exchange=hc.code.str[-2:]).groupby('exchange').holding_date.max().to_dict();by=hc.set_index('code');rows=[]
  for r in univ.itertuples():
   rec=by.loc[r.code] if r.code in by.index else None;eligible=state.get(r.code,0);dose=float(rec.dose) if rec is not None else (0. if not eligible else np.nan);hd=rec.holding_date if rec is not None else pd.NaT;ad=rec.available_date if rec is not None else pd.NaT
   if rec is not None and hd<latest.get(r.code[-2:],pd.NaT):dose=0. if not eligible else np.nan;hd=pd.NaT;ad=pd.NaT
   rows.append(dict(event_id=eid,code=r.code,freeze_date=freeze,anchor=anchor,eligible=eligible,dose=dose,holding_date=hd,available_date=ad,frequency='quarterly' if pd.notna(hd) and hd>=pd.Timestamp('2024-08-19') else 'daily',first_observed_daily=r.first_observed_daily))
  return pd.DataFrame(rows)
 for r in e[e.kind.ne('holiday')].itertuples():
  ex=snapshot(r.freeze_date,r.start,r.event_id);last=snapshot(r.start,r.start,r.event_id);delta=ex[['code','dose']].merge(last[['code','dose','holding_date','available_date']],on='code',suffixes=('_window_freeze','_event_latest'));delta['event_id']=r.event_id;aud.append(delta);out.append(ex)
 exposures=pd.concat(out,ignore_index=True);assert (exposures.available_date.isna()|exposures.available_date.lt(exposures.freeze_date)).all();exposures.to_parquet(T/'exposures.parquet',index=False);save(exposures[exposures.event_id>100],R/'tables/exposure_by_event.csv');save(pd.concat(aud),R/'tables/exposure_timing_sensitivity.csv')
 save(exposures.groupby('event_id').agg(stocks=('code','nunique'),known_dose=('dose','count'),positive=('dose',lambda x:int(x.gt(0).sum())),freeze_date=('freeze_date','first')).reset_index(),R/'tables/exposure_coverage.csv')
 from input_manifest import main as manifest_main
 manifest_main()
 current=json.loads((R/'meta/input_manifest.json').read_text());before=R/'meta/input_manifest_before_estimation.json'
 if before.exists():
  frozen=json.loads(before.read_text());assert current['critical_inputs']==frozen['critical_inputs'];assert current['minute_archives']==frozen['minute_archives']
 else:before.write_text(json.dumps(current,ensure_ascii=False,indent=2))
 print(e[['event_id','start','end','kind','closure_type','freeze_date']].to_string(index=False))
if __name__=='__main__':main()
