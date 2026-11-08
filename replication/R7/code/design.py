from common import *
import shutil

def maps():
 main=pd.read_csv(P/'tables/event_date_map.csv',parse_dates=['date','anchor']);main['family']='main';main=main.merge(features()[['event_id','freeze_date']].drop_duplicates(),on='event_id',validate='m:1');parts=[main[['event_id','date','anchor','closed','freeze_date','family']]]
 us=pd.read_csv(P/'R3b/tables/event_date_map.csv',parse_dates=['date','anchor','freeze_date']);us=us[us.group.eq('US')&~us.fake&us.window.eq('r1')].copy();us['event_id']+=1000;us['family']='US';us['closed']=us.treated.astype(bool);parts.append(us[parts[0].columns])
 fake=pd.read_csv(P/'tables/placebo_date_map.csv',parse_dates=['date','anchor','freeze_date']);fake=fake[fake.kind.eq('joint_holiday_adjacent')].copy();fake['event_id']+=10000;fake['family']='fake';fake['closed']=fake.treated.astype(bool);parts.append(fake[parts[0].columns])
 # Quiet classification uses strictly past full market amounts, not selected-stock amounts.
 receipts=pd.DataFrame([json.loads(p.read_text())for p in sorted((T/'daily').glob('*.json'))]);receipts['date']=pd.to_datetime(receipts.date);cal=pd.read_csv(P/'tables/official_calendar.csv',parse_dates=['date']);rc=receipts.merge(cal[['date','a_open','nb_open']],on='date',validate='1:1').sort_values('date');weather=pd.read_csv(P/'R6/typhoon_calendar.csv',parse_dates=['date']);weather_bad=set(weather.loc[weather.included,'date']);norm=rc[rc.nb_open&rc.a_open&~rc.date.isin(weather_bad)].copy()
 for col in ['market_amount','if_rv']:
  norm[col+'_q20']=norm[col].expanding(min_periods=60).quantile(.2).shift(1)
 norm['quiet']=(norm.market_amount<norm.market_amount_q20)&(norm.if_rv<norm.if_rv_q20)&norm.if_rv.gt(0);save(norm[['date','market_amount','if_rv','market_amount_q20','if_rv_q20','quiet']].assign(n=1,stocks=np.nan,events=np.nan),'quiet_day_classification.csv')
 ad=pd.DatetimeIndex(cal.loc[cal.a_open,'date']);pos={d:i for i,d in enumerate(ad)};qd=norm.loc[norm.quiet,'date'].tolist();episodes=[]
 for d in qd:
  if not episodes or pos[d]>pos[episodes[-1][-1]]+1:episodes.append([d])
  else:episodes[-1].append(d)
 normal=set(norm.loc[~norm.quiet,'date']);qrows=[]
 for i,days in enumerate(episodes,2001):
  pre=[d for d in ad if d<days[0]and d in normal][-5:];post=[d for d in ad if d>days[-1]and d in normal][:5]
  if len(pre)<5 or len(post)<5:continue
  for d in pre+days+post:qrows.append(dict(event_id=i,date=d,anchor=days[0],closed=d in days,freeze_date=min(pre),family='quiet'))
 quiet=pd.DataFrame(qrows);quiet['distance']=(quiet.date-quiet.anchor).abs().dt.days;quiet=quiet.sort_values(['date','distance','anchor']).drop_duplicates('date');parts.append(quiet[parts[0].columns])
 out=pd.concat(parts,ignore_index=True);out.closed=out.closed.astype(bool);out.to_csv(R/'tables/design_map.csv',index=False)
 ev=out.groupby(['family','event_id']).agg(start=('anchor','first'),end=('date',lambda s:pd.NaT),freeze_date=('freeze_date','first'),dates=('date','nunique')).reset_index();ends=out[out.closed].groupby('event_id').date.agg(['max','count']);ev['end']=ev.event_id.map(ends['max']);ev['n_closed_days']=ev.event_id.map(ends['count']);save(ev,'design_events.csv')
 print('MAPS',out.groupby('family').event_id.nunique().to_dict(),flush=True)

def exposures():
 dest=T/'extra_features.parquet'
 if dest.exists():return
 fr=pd.read_csv(R/'tables/design_events.csv',parse_dates=['freeze_date','start']);fr=fr[fr.family.ne('main')];un=pd.read_parquet(T/'universe.parquet');c=pd.read_csv(P/'tables/official_calendar.csv',parse_dates=['date']);norm=c.loc[c.nb_open,'date'].to_numpy('datetime64[ns]');parts=[]
 for b in pq.ParquetFile(Q/'cn_hsgt/hk_hold/full/all.parquet').iter_batches(batch_size=100000,columns=['trade_date','ts_code','ratio'],use_threads=False):
  d=b.to_pandas();d=d[d.ts_code.str.endswith(('.SH','.SZ'))];parts.append(d)
 h=pd.concat(parts,ignore_index=True).rename(columns={'trade_date':'holding_date','ts_code':'code','ratio':'dose'});del parts;h.holding_date=pd.to_datetime(h.holding_date);h=h[h.holding_date.lt('2024-08-19')|h.holding_date.dt.is_quarter_end].copy();h['available_date']=h.holding_date+pd.Timedelta(days=1)
 for dt in h.loc[h.holding_date.ge('2024-08-19'),'holding_date'].unique():
  j=np.searchsorted(norm,np.datetime64(dt),side='right')+4;h.loc[h.holding_date.eq(dt),'available_date']=pd.Timestamp(norm[j])+pd.Timedelta(days=1)if j<len(norm)else pd.Timestamp.max
 h=h.drop_duplicates(['code','holding_date']).sort_values(['available_date','holding_date']);h.to_parquet(T/'holdings_public.parquet',index=False);elig=pd.read_csv(P/'meta/eligibility_events.csv',parse_dates=['effective_date']);full=pd.DatetimeIndex(pd.read_csv(P/'meta/actual_full_calendar.csv',parse_dates=['date']).date);out=[]
 for freeze,ev in fr.groupby('freeze_date'):
  state={}
  for r in elig[elig.effective_date.lt(freeze)].sort_values(['effective_date','source_row'],ascending=[True,False]).itertuples():
   s=str(r.change)
   if s=='Addition'or s.startswith('Addition (from List of Special')or'changed from'in s or s=='Buy orders resumed':state[r.code]=1
   elif s.startswith(('Transfer to List of Special','Addition to List of Special'))or s=='Removal'or'changed to'in s or s=='Buy orders suspended':state[r.code]=0
  hh=h[h.available_date.lt(freeze)].drop_duplicates('code',keep='last');latest=hh.assign(ex=hh.code.str[-2:]).groupby('ex').holding_date.max();hh=hh[hh.holding_date.eq(hh.code.str[-2:].map(latest))];d=un.copy();d['eligible']=d.code.map(state).fillna(0).astype('int8');d=d.merge(hh[['code','dose','holding_date','available_date']],on='code',how='left',validate='1:1');d.loc[d.dose.isna()&d.eligible.eq(0),'dose']=0.;d['freeze_date']=freeze;d['pre_age']=full.searchsorted(freeze)-full.searchsorted(d.first_observed_daily);d['quintile']=np.nan
  assert d.available_date.dropna().lt(freeze).all()
  good=d.dose.notna()&d.pre_age.ge(60);rank=d.loc[good].sort_values(['dose','code']).index;d.loc[rank,'quintile']=np.minimum(4,np.arange(len(rank))*5//max(len(rank),1))
  for e in ev.itertuples():q=d.copy();q['event_id']=e.event_id;q['family']=e.family;q['event_start']=e.start;out.append(q)
 pd.concat(out,ignore_index=True).to_parquet(dest,index=False);print('EXTRA_EXPOSURES',len(fr),flush=True)

def allfeatures():
 a=features();a['family']='main';b=pd.read_parquet(T/'extra_features.parquet');pd.concat([a,b],ignore_index=True).to_parquet(T/'all_features.parquet',index=False)
if __name__=='__main__':
 maps();exposures();allfeatures()
