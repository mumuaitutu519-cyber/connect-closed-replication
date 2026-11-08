from common import *
from dateutil.easter import easter
import calendar,requests

def nth(y,m,w,n):
 d=pd.Timestamp(y,m,1);return d+pd.Timedelta(days=(w-d.dayofweek)%7+7*(n-1))
def last(y,m,w):
 d=pd.Timestamp(y,m,calendar.monthrange(y,m)[1]);return d-pd.Timedelta(days=(d.dayofweek-w)%7)
def observed(y,m,d):
 x=pd.Timestamp(y,m,d);return x+pd.Timedelta(days=1 if x.dayofweek==6 else -1 if x.dayofweek==5 else 0)
def prepare():
 c=pd.read_csv(R/'tables/official_calendar.csv',parse_dates=['date']);c=c[c.date.le('2026-09-30')];a=c[c.a_open].date.tolist();full=pd.DatetimeIndex(pd.read_csv(R/'meta/actual_full_calendar.csv',parse_dates=['date']).date);normal=set(c.loc[c.a_open&c.nb_open,'date'])
 # Northbound requires both stock markets open; retain known HK flags, exclude known half days.
 normal-=set(c.loc[c.hk_holiday.eq(True),'date'])
 # HK half-day Christmas/New-Year eves are never admitted as full-day normal controls.
 normal-={x for x in normal if (x.month,x.day) in [(12,24),(12,31)]}
 weather=pd.read_csv(R/'tables/HKEX_nonfull_day_audit.csv',parse_dates=['date']);nonfull=set(weather.loc[weather.exclude_from_full_day.eq(True),'date']);normal-=nonfull
 sources=[('US','https://www.opm.gov/policy-data-oversight/pay-leave/federal-holidays/'),('NYSE','https://www.nyse.com/trade/hours-calendars'),('UK','https://www.gov.uk/bank-holidays'),('UK2020','https://www.gov.uk/government/news/2020-may-bank-holiday-will-be-moved-to-mark-75th-anniversary-of-ve-day'),('UK2022','https://www.gov.uk/government/news/extra-bank-holiday-to-mark-the-queens-platinum-jubilee-in-2022'),('EU','https://www.service-public.gouv.fr/particuliers/vosdroits/F2405?lang=en'),('Euronext','https://www.euronext.com/en/trade/trading-hours-holidays')]
 receipts=[]
 for name,url in sources:
  try:
   r=requests.get(url,timeout=25);p=R/'meta'/f'source_{name}.html';p.write_bytes(r.content);receipts.append(dict(name=name,url=url,status=r.status_code,bytes=len(r.content),sha256=hashlib.sha256(r.content).hexdigest()))
  except Exception as ex:receipts.append(dict(name=name,url=url,status=str(ex)))
 js(R/'meta/source_receipts.json',receipts)
 raw=[]
 def add(group,name,date):raw.append(dict(group=group,holiday=name,date=pd.Timestamp(date)))
 for y in range(2017,2027):
  for name,d in [('MLK',nth(y,1,0,3)),('Presidents',nth(y,2,0,3)),('Memorial',last(y,5,0)),('Independence',observed(y,7,4)),('Labor',nth(y,9,0,1)),('Thanksgiving',nth(y,11,3,4))]:add('US',name,d)
  if y>=2022:add('US','Juneteenth',observed(y,6,19))
  add('US_half','Thanksgiving_next',nth(y,11,3,4)+pd.Timedelta(days=1));add('US_Columbus','Columbus',nth(y,10,0,2))
  add('UK','Early_May',pd.Timestamp('2020-05-08') if y==2020 else nth(y,5,0,1));add('UK','Spring',pd.Timestamp('2022-06-02') if y==2022 else last(y,5,0));add('UK','Summer',last(y,8,0))
  add('EU','Ascension',pd.Timestamp(easter(y))+pd.Timedelta(days=39));add('EU','Whit_Monday',pd.Timestamp(easter(y))+pd.Timedelta(days=50))
 h=pd.DataFrame(raw);h['in_period']=h.date.between('2017-01-01','2026-09-30');h['a_open']=h.date.isin(a);h['nb_full_open']=h.date.isin(normal);h['retained']=h.in_period&h.a_open&h.nb_full_open
 h['status']=np.where(~h.in_period,'OUTSIDE_PERIOD',np.where(~h.a_open,'A_CLOSED',np.where(~h.nb_full_open,'NB_OR_HK_NOT_FULL_OPEN','KEEP')));save(h,'holiday_calendar_audit.csv');good=h[h.retained];allhol=set(good.date);clean=normal-allhol
 overlap=good.pivot_table(index='date',columns='group',values='holiday',aggfunc='first').reset_index();save(overlap,'holiday_overlap.csv')
 maps=[];events=[];fake_support=[];window_rejections=[];eid=0
 for g in GROUPS:
  dates=sorted(set(good.loc[good.group.isin(['US','UK','EU']) if g=='ALL' else good.group.eq(g),'date']));groups=[];pos={d:i for i,d in enumerate(a)}
  for d in dates:
   if not groups or pos[d]>pos[groups[-1][-1]]+1:groups.append([d])
   else:groups[-1].append(d)
  for fake in [False,True]:
   pseudo_all={x-pd.Timedelta(days=7) for origin in groups for x in origin} if fake else set()
   control_clean=clean-pseudo_all
   for origin in groups:
    treated=[x-pd.Timedelta(days=7) for x in origin] if fake else origin
    valid=not fake or all(x in clean for x in treated)
    if fake:fake_support.append(dict(group=g,original_start=origin[0],pseudo_start=treated[0],n_days=len(treated),status='OK' if valid else 'NOT_CLEAN_NORMAL'))
    if not valid:continue
    for window in ['r1','weekday']:
     start,end=min(treated),max(treated);controls=(sorted(x for x in control_clean if x<start)[-5:]+sorted(x for x in control_clean if x>end)[:5]) if window=='r1' else sorted({d+pd.Timedelta(days=7*k) for d in treated for k in [-3,-2,-1,1,2,3] if d+pd.Timedelta(days=7*k) in control_clean and d+pd.Timedelta(days=7*k) not in treated})
     if not controls:continue
     eid+=1
     if not any(d<start for d in controls):
      window_rejections.append(dict(event_id=eid,group=g,fake=fake,window=window,start=start,end=end,origin=origin[0],freeze_date=min(controls),n_treated=len(treated),n_pre=0,n_post=sum(x>end for x in controls),status='NO_PRECONTROL_FOR_FREEZE'));continue
     freeze=min(controls);events.append(dict(event_id=eid,group=g,fake=fake,window=window,start=start,end=end,origin=origin[0],freeze_date=freeze,n_treated=len(treated),n_pre=sum(x<start for x in controls),n_post=sum(x>end for x in controls)))
     for d in sorted(set(controls+treated)):maps.append(dict(event_id=eid,group=g,fake=fake,window=window,date=d,treated=int(d in treated),closed=0,anchor=start,freeze_date=freeze,distance=abs((d-start).days)))
 m=pd.DataFrame(maps);m['owner']=True
 # Dedup only R1 windows; weekday deliberately stacked.
 for key,ix in m[m.window.eq('r1')].groupby(['group','fake','window']).groups.items():
  z=m.loc[ix].sort_values(['date','treated','distance','anchor'],ascending=[True,False,True,True]);m.loc[z.index,'owner']=~z.date.duplicated()
 ev=pd.DataFrame(events);save(ev,'events.csv');save(m,'event_date_map_all.csv');save(m[m.owner],'event_date_map.csv');save(pd.DataFrame(fake_support),'fake_week_support.csv');save(pd.DataFrame(window_rejections),'stack_window_rejections.csv');save(c,'official_calendar.csv');save(pd.DataFrame({'date':sorted(clean)}),'normal_control_dates.csv')
 counts=[]
 for g in GROUPS:
  d=ev[ev.group.eq(g)&~ev.fake&ev.window.eq('r1')];counts.append(dict(group=g,independent_dates=d.n_treated.sum(),event_segments=len(d),target30_met=d.n_treated.sum()>=30))
 save(pd.DataFrame(counts),'holiday_counts.csv')
 # Add original R1 windows with their original event freeze and dedup assignment for joint comparisons.
 orig=pd.read_csv(P/'tables/event_date_map.csv',parse_dates=['date','anchor']);orig=orig[orig.date.le('2026-09-30')];exp=pd.read_csv(P/'tables/exposure_coverage.csv',parse_dates=['freeze']);orig['event_id']+=10000;orig['freeze_date']=orig.event_id.map(dict(zip(exp.event_id+10000,exp.freeze)));orig['treated']=0;orig['closed']=orig.closed.astype(int);orig['group']='CLOSED';orig['fake']=False;orig['window']='r1';orig['owner']=True;orig['distance']=(orig.date-orig.anchor).abs().dt.days
 save(orig[['event_id','group','fake','window','date','treated','closed','anchor','freeze_date','distance','owner']],'closure_date_map.csv')
 fr=pd.concat([ev[['event_id','freeze_date']],orig[['event_id','freeze_date']]]).drop_duplicates('event_id');save(fr,'freezes.csv')
 print(pd.DataFrame(counts).to_string(index=False),flush=True)
 # CCASS schema/market classification bounded audit.
 rec=[]
 for p in (Q/'cn_hk_ccass').rglob('*.parquet'):
  pf=pq.ParquetFile(p);b=next(pf.iter_batches(batch_size=10,use_threads=False));rec.append(dict(path=str(p),schema=str(pf.schema_arrow),sample=b.to_pydict(),rows=pf.metadata.num_rows))
 js(R/'meta/ccass_audit.json',rec);save(pd.DataFrame([dict(specification='foreign_custodian_share',status='SKIPPED_NO_NORTHBOUND_PARTICIPANT_CLASSIFICATION',reason='QDC CCASS is Hong Kong stock aggregate; no northbound A-share participant IDs or custodian category mapping')]),'custodian_specification_status.csv')

def exposures():
 fr=pd.read_csv(R/'tables/freezes.csv',parse_dates=['freeze_date']);un=pd.read_csv(R/'meta/stock_universe.csv',parse_dates=['first_observed_daily']);c=pd.read_csv(R/'tables/official_calendar.csv',parse_dates=['date']);norm=c.loc[c.nb_open,'date'].to_numpy('datetime64[ns]');parts=[]
 for b in pq.ParquetFile(Q/'cn_hsgt/hk_hold/full/all.parquet').iter_batches(batch_size=100000,columns=['trade_date','ts_code','ratio'],use_threads=False):
  d=b.to_pandas();d=d[d.ts_code.str.endswith(('.SH','.SZ'))];parts.append(d)
 h=pd.concat(parts,ignore_index=True).rename(columns={'trade_date':'holding_date','ts_code':'code','ratio':'dose'});del parts;h.holding_date=pd.to_datetime(h.holding_date);h=h[h.holding_date.lt('2024-08-19')|h.holding_date.dt.is_quarter_end].copy();h['available_date']=h.holding_date+pd.Timedelta(days=1)
 for dt in h.loc[h.holding_date.ge('2024-08-19'),'holding_date'].unique():
  i=np.searchsorted(norm,np.datetime64(dt),side='right')+4;h.loc[h.holding_date.eq(dt),'available_date']=pd.Timestamp(norm[i])+pd.Timedelta(days=1) if i<len(norm) else pd.Timestamp.max
 dup=h.duplicated(['code','holding_date'],keep=False)
 if dup.any():assert h[dup].groupby(['code','holding_date']).dose.nunique().max()<=1
 h=h.drop_duplicates(['code','holding_date']).sort_values(['available_date','holding_date']);h.to_parquet(T/'holdings_public.parquet',index=False)
 elig=pd.read_csv(R/'meta/eligibility_events.csv',parse_dates=['effective_date']);full=pd.DatetimeIndex(pd.read_csv(R/'meta/actual_full_calendar.csv',parse_dates=['date']).date);pieces=[];audit=[]
 # R2 quintiles also require known strictly pre-freeze circulating market cap.
 targets={dt:full[full.searchsorted(dt)-1] for dt in fr.freeze_date.unique()};needed=set(targets.values());caps=[]
 for p in sorted((Q/'cn_valuation_1d/full').glob('*.parquet')):
  if not p.stem[:4].isdigit() or not 2016<=int(p.stem[:4])<=2026:continue
  for b in pq.ParquetFile(p).iter_batches(batch_size=100000,columns=['trade_date','symbol','circulating_market_cap'],use_threads=False):
   z=b.to_pandas();z['date']=pd.to_datetime(z.trade_date);z=z[z.date.isin(needed)&z.circulating_market_cap.gt(0)].copy();z['code']=z.symbol.str[:6]+np.where(z.symbol.str.endswith('.XSHG'),'.SH','.SZ');caps.append(z[['date','code','circulating_market_cap']])
 cap=pd.concat(caps,ignore_index=True).drop_duplicates(['date','code']);del caps
 for freeze,eg in fr.groupby('freeze_date'):
  state={}
  for r in elig[elig.effective_date.lt(freeze)].sort_values(['effective_date','source_row'],ascending=[True,False]).itertuples():
   s=str(r.change)
   if s=='Addition' or s.startswith('Addition (from List of Special') or 'changed from' in s or s=='Buy orders resumed':state[r.code]=1
   elif s.startswith(('Transfer to List of Special','Addition to List of Special')) or s=='Removal' or 'changed to' in s or s=='Buy orders suspended':state[r.code]=0
  hh=h[h.available_date.lt(freeze)].drop_duplicates('code',keep='last').copy();latest=hh.assign(ex=hh.code.str[-2:]).groupby('ex').holding_date.max();hh=hh[hh.holding_date.eq(hh.code.str[-2:].map(latest))]
  d=un.copy();d['eligible']=d.code.map(state).fillna(0).astype(np.int8);d=d.merge(hh[['code','dose','holding_date','available_date']],on='code',how='left',validate='1:1');d.loc[d.dose.isna()&d.eligible.eq(0),'dose']=0;d['freeze_date']=freeze;d['pre_age']=full.searchsorted(freeze)-full.searchsorted(d.first_observed_daily);d['quintile']=np.nan;capby=cap[cap.date.eq(targets[freeze])].set_index('code').circulating_market_cap;d['pre_cap']=d.code.map(capby)
  good=d.dose.notna()&d.pre_age.ge(60)&d.pre_cap.notna();rank=d.loc[good].sort_values(['dose','code']).index;d.loc[rank,'quintile']=np.minimum(4,np.floor(np.arange(len(rank))*5/max(len(rank),1)))
  # Keep one freeze-keyed table to avoid duplicating same exposures across groups/windows.
  pieces.append(d)
  audit.append(dict(freeze_date=freeze,events=len(eg),stocks=len(d),dose_known=d.dose.notna().sum(),positive=d.dose.gt(0).sum(),eligible=d.eligible.sum()))
 out=pd.concat(pieces,ignore_index=True);out.to_parquet(T/'exposures.parquet',index=False);save(pd.DataFrame(audit),'exposure_coverage.csv');print('EXPOSURES',len(fr),len(pieces),len(out),flush=True)
if __name__=='__main__':prepare();exposures()
