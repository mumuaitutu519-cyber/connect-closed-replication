from common import *
import concurrent.futures as cf

def calendar():
 c=pd.read_csv(P/'tables/official_calendar.csv',parse_dates=['date']);c=c[c.date.le('2026-10-30')].copy();a=c[c.a_open].copy();ev=pd.read_csv(P/'tables/events.csv',parse_dates=['start','end']);
 # Archived pre-2023 HK flags have holes: NB calendar O denotes HK holiday or clearing holiday.
 # Cleaning conservatively excludes all A-open NB-closed dates and adjacent A sessions as well as A holiday boundaries.
 dates=pd.DatetimeIndex(a.date);bad=set(a.loc[~a.nb_open,'date']);
 hk=c.hk_holiday.astype(str).str.lower().eq('true');holiday=set(c.loc[hk | (~c.a_open & c.date.dt.dayofweek.lt(5)),'date'])
 adjacent=set()
 for h in holiday|bad:
  i=dates.searchsorted(h);adjacent.update(dates[max(0,i-1):min(len(dates),i+2)].tolist())
 clean=set(a.loc[a.nb_open,'date'])-adjacent
 def controls(d):
  same=sorted(x for x in clean if x.dayofweek==d.dayofweek);return [x for x in same if x<d][-2:]+[x for x in same if x>d][:2]
 rows=[];support=[]
 for e in ev.itertuples():
  treated=a.loc[a.date.between(e.start,e.end)&~a.nb_open,'date'].tolist()
  treated=[d for d in treated if d>=pd.Timestamp('2021-07-23')]
  if not treated:continue
  freeze=a.loc[a.date.lt(e.start)&a.nb_open,'date'].max()
  for d in treated:
   for t in [d]+controls(d):rows.append(dict(kind='real',event_id=e.event_id,treatment_date=d,date=t,closed=t==d,anchor=e.start,freeze_date=freeze))
   # Literal shift; do not move an ineligible pseudo-date to a nearby day.
   i=dates.get_loc(d)-20;fd=dates[i] if i>=0 else pd.NaT;valid=fd in clean
   support.append(dict(original_date=d,pseudo_date=fd,status='OK' if valid else 'NOT_CLEAN_NORMAL',same_weekday=pd.notna(fd) and fd.dayofweek==d.dayofweek))
   if valid:
    fr=a.loc[a.date.lt(fd)&a.nb_open,'date'].max()
    for t in [fd]+controls(fd):rows.append(dict(kind='fake20',event_id=1000+e.event_id,treatment_date=fd,date=t,closed=t==fd,anchor=fd,freeze_date=fr))
 # Common holidays use the normal NB-open A sessions adjacent to a joint weekday closure block.
 joint=c[~c.a_open & hk & c.date.dt.dayofweek.lt(5) & c.date.ge('2021-07-23')]
 common=set()
 for h in joint.date:
  i=dates.searchsorted(h)
  for j in [i-1,i]:
   if 0<=j<len(dates):
    d=dates[j]
    if bool(a.set_index('date').loc[d,'nb_open']):common.add(d)
 for n,d in enumerate(sorted(common)):
  fr=a.loc[a.date.lt(d)&a.nb_open,'date'].max()
  for t in [d]+controls(d):rows.append(dict(kind='common_holiday',event_id=2000+n,treatment_date=d,date=t,closed=t==d,anchor=d,freeze_date=fr))
 m=pd.DataFrame(rows);m['distance']=(m.date-m.treatment_date).abs().dt.days
 # Treatment wins collisions within each kind. Stocks can change by event; assignment precedes stock filtering.
 m=m.sort_values(['kind','date','closed','distance','anchor','treatment_date'],ascending=[True,True,False,True,True,True]);m['owner']=~m.duplicated(['kind','date']);save(m,'event_date_map_all.csv');save(m[m.owner],'event_date_map.csv');save(pd.DataFrame(support),'fake20_support.csv');save(c,'official_calendar.csv')
 audit=[]
 for key,d in m.groupby(['kind','event_id','treatment_date']):
  pre=d.loc[d.date<key[2],'date'].nunique();post=d.loc[d.date>key[2],'date'].nunique();audit.append(dict(kind=key[0],event_id=key[1],treatment_date=key[2],pre_normal_same_weekday=pre,post_normal_same_weekday=post,complete_two_each_side=pre==2 and post==2))
 save(pd.DataFrame(audit),'control_window_audit.csv')
 f=m.groupby(['kind','event_id'],as_index=False).agg(freeze_date=('freeze_date','min'),anchor=('anchor','min'),earliest_sample=('date','min'));save(f,'freezes.csv');print('CALENDAR',m.groupby('kind').agg(days=('date','nunique'),treated=('treatment_date','nunique')).to_dict(),flush=True)

 definputs=[]
 for p in [Q/'cn_hsgt/hk_hold/full/all.parquet',P/'tables/official_calendar.csv',P/'tables/events.csv',P/'tables/exposure_by_event.csv',P/'R2/tables/frozen_features_by_event.csv',P/'R2/tables/AH_listing_history.csv',L/'L2_inventory.csv',Path('/Volumes/Extreme SSD/T9/l2_diag/code/rebuild_v2.py'),Path('/Volumes/Extreme SSD/T9/l2_diag/code/book169.cpp'),Path('/Volumes/Extreme SSD/T9/l2_closestale/code/manager229.py'),L/'download_dates.sh']:
  definputs.append(dict(path=str(p),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
 js(R/'meta/input_sources.json',definputs)
 lockpath=R/'meta/preregistration_lock.json';digest=hashlib.sha256((R/'PREREGISTRATION_R3.md').read_bytes()).hexdigest()
 if lockpath.exists():assert json.loads(lockpath.read_text())['sha256']==digest
 else:js(lockpath,dict(sha256=digest,locked_at=pd.Timestamp.now(tz='UTC'),first_estimate_at=None))

def features():
 fr=pd.read_csv(R/'tables/freezes.csv',parse_dates=['freeze_date','anchor','earliest_sample']);orig=pd.read_csv(P/'R2/tables/frozen_features_by_event.csv',parse_dates=['freeze_date','cap_date','announce_date','hk_listing_date','hk_delisting_date']);cal=pd.read_csv(R/'tables/official_calendar.csv',parse_dates=['date']);norm=cal.loc[cal.nb_open,'date'].to_numpy('datetime64[ns]');parts=[]
 for b in pq.ParquetFile(Q/'cn_hsgt/hk_hold/full/all.parquet').iter_batches(batch_size=100000,columns=['trade_date','ts_code','ratio'],use_threads=False):
  d=b.to_pandas();d=d[d.ts_code.str.endswith(('.SH','.SZ'))].copy();d['holding_date']=pd.to_datetime(d.trade_date);d=d[d.holding_date.lt('2024-08-19')|d.holding_date.dt.is_quarter_end];d['available_date']=d.holding_date+pd.Timedelta(days=1)
  for dt in d.loc[d.holding_date.ge('2024-08-19'),'holding_date'].unique():
   i=np.searchsorted(norm,np.datetime64(dt),side='right')+4;d.loc[d.holding_date.eq(dt),'available_date']=pd.Timestamp(norm[i])+pd.Timedelta(days=1) if i<len(norm) else pd.Timestamp.max
  parts.append(d.rename(columns={'ts_code':'code','ratio':'dose'})[['code','holding_date','available_date','dose']])
 h=pd.concat(parts,ignore_index=True);duplicates=h.duplicated(['code','holding_date'],keep=False)
 if duplicates.any()and h[duplicates].groupby(['code','holding_date']).dose.nunique().max()>1:raise ValueError('Conflicting ownership ratios for stock/date')
 h=h.drop_duplicates(['code','holding_date']).sort_values(['available_date','holding_date']);del parts
 elig=pd.read_csv(P/'meta/eligibility_events.csv',parse_dates=['effective_date']);un=pd.read_csv(P/'meta/stock_universe.csv',parse_dates=['first_observed_daily']);full=pd.DatetimeIndex(pd.read_csv(P/'meta/actual_full_calendar.csv',parse_dates=['date']).date);allfeat=[]
 for f in fr.itertuples():
  prev=orig[orig.freeze_date.lt(f.freeze_date)].sort_values('freeze_date').drop_duplicates('code',keep='last').copy();prev=prev.rename(columns={'freeze_date':'controls_freeze_date','dose':'dose_272','event_id':'source_event_id'});prev=prev.drop(columns=['anchor'],errors='ignore');d=un.merge(prev.drop(columns='first_observed_daily'),on='code',how='left',validate='1:1');d['event_id']=f.event_id;d['kind']=f.kind;d['freeze_date']=f.freeze_date;d['anchor']=f.anchor;d['earliest_sample']=f.earliest_sample
  state={}
  for row in elig[elig.effective_date.lt(f.freeze_date)].sort_values(['effective_date','source_row'],ascending=[True,False]).itertuples():
   s=str(row.change)
   if s=='Addition' or s.startswith('Addition (from List of Special') or 'changed from' in s or s=='Buy orders resumed':state[row.code]=1
   elif s.startswith(('Transfer to List of Special','Addition to List of Special')) or s=='Removal' or 'changed to' in s or s=='Buy orders suspended':state[row.code]=0
  d['eligible']=d.code.map(state).fillna(0).astype(int);hh=h[h.available_date.lt(f.freeze_date)].drop_duplicates('code',keep='last').copy();latest=hh.assign(ex=hh.code.str[-2:]).groupby('ex').holding_date.max();hh=hh[hh.holding_date.eq(hh.code.str[-2:].map(latest))];d=d.drop(columns=['holding_date','available_date','dose'],errors='ignore').merge(hh,on='code',how='left',validate='1:1');d.loc[d.dose.isna()&d.eligible.eq(0),'dose']=0
  d['ah']=((d.hk_listing_date<f.anchor)&(d.hk_delisting_date.isna()|(d.hk_delisting_date>=f.anchor))).astype(float);d['pre_age']=full.searchsorted(f.freeze_date)-full.searchsorted(d.first_observed_daily);d['controls_age_days']=(f.freeze_date-d.controls_freeze_date).dt.days;allfeat.append(d)
 f=pd.concat(allfeat,ignore_index=True);assert (f.available_date.dropna()<f.loc[f.available_date.notna(),'freeze_date']).all();selected=[];matches=[]
 for key,d in f.groupby(['kind','event_id']):
  good=d[d.pre_age.ge(60)];hi=good[good.eligible.eq(1)&good.dose.gt(0)].sort_values(['dose','code'],ascending=[False,True]).head(300);lo=good[good.eligible.eq(0)&good.industry.notna()&good.logcap.notna()].copy();used=set()
  for row in hi.itertuples():
   choices=lo[lo.industry.eq(row.industry)&~lo.code.isin(used)].copy();choices['distance']=(choices.logcap-row.logcap).abs()
   if not len(choices) or not np.isfinite(row.logcap):continue
   match=choices.sort_values(['distance','code']).iloc[0];used.add(match.code);matches.append(dict(kind=key[0],event_id=key[1],treated=row.code,control=match.code,distance=match.distance,industry=row.industry))
  x=pd.concat([hi,lo[lo.code.isin(used)]],ignore_index=True);x['sample_group']=np.where(x.eligible.eq(1),'top300','noneligible_match');selected.append(x)
 f=pd.concat(selected,ignore_index=True);save(f,'frozen_features.csv');save(pd.DataFrame(matches),'matches.csv');f.to_parquet(T/'features.parquet',index=False);print('FEATURES',len(f),f.code.nunique(),flush=True)
 m=pd.read_csv(R/'tables/event_date_map.csv',parse_dates=['date']);jobs=m[['kind','event_id','date']].merge(f[['kind','event_id','code']],on=['kind','event_id'],validate='m:m').drop_duplicates(['date','code']);jobs.to_parquet(R/'meta/date_stock_plan.parquet',index=False);days=sorted(jobs.date.dt.strftime('%Y-%m-%d').unique());(R/'meta/requested_dates.txt').write_text('\n'.join(days)+'\n');inv=pd.read_csv(L/'L2_inventory.csv');inv=inv[inv.is_daily_package.astype(str).str.lower().eq('true')];z=pd.DataFrame({'date':days}).merge(inv,on='date',how='left',validate='1:m');z['local']=z.filename.fillna('').map(lambda s:bool(s) and (L/'raw'/s).exists());save(z,'download_plan.csv');js(R/'meta/sample_plan.json',dict(days=len(days),bytes_remote=z.size_bytes.sum(),missing_days=z.date[z.filename.isna()].tolist(),stocks=jobs.code.nunique()));print('PLAN',len(days),z.size_bytes.sum()/1e9,'GB',flush=True)

if __name__=='__main__':globals()[sys.argv[1]]()
