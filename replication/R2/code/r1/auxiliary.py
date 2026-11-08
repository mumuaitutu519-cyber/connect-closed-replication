import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[k]='1'
from pathlib import Path
import numpy as np,pandas as pd,pyarrow as pa,pyarrow.parquet as pq,pyarrow.dataset as ds,concurrent.futures as cf,json,argparse,gc,ctypes,sys
from estimate import ROOT,TMP,PRIMARY,fit,bh,design_K,SEED,B,demean
from scipy.stats import t as student_t
from build_panel import METRICS
pa.set_cpu_count(1);pa.set_io_thread_count(1);pa.set_memory_pool(pa.system_memory_pool())
def release_memory():
 gc.collect();pa.default_memory_pool().release_unused()
 if sys.platform=='darwin':
  fun=ctypes.CDLL(None).malloc_zone_pressure_relief;fun.argtypes=[ctypes.c_void_p,ctypes.c_size_t];fun.restype=ctypes.c_size_t;fun(None,0)
def dynamic_fit(frame):
 # Build one residualized numeric design only; never materialize twelve full predictor columns in several DataFrames.
 valid=np.isfinite(frame.y.to_numpy())&np.isfinite(frame.dose0.to_numpy());d=frame.loc[valid,['code','date','y','dose0','event_time']];e,entities=pd.factorize(d.code,sort=True);tt,dates=pd.factorize(d.date,sort=True);dose=d.dose0.to_numpy(float);time=d.event_time.to_numpy();Y=demean(d.y.to_numpy()[:,None],e,tt)[0][:,0];ks=[-5,-4,-3,-2,0,1,2,3,4,5];names=[f'event_{k}' for k in ks]+['dose0'];X=np.empty((len(d),len(names)))
 for j,k in enumerate(ks):X[:,j]=demean((dose*(time==k))[:,None],e,tt)[0][:,0]
 X[:,-1]=demean(dose[:,None],e,tt)[0][:,0];independent=np.sqrt(np.sum(X*X,axis=0))>1e-7
 if not independent.all():X=X[:,independent];names=list(np.asarray(names)[independent])
 n,k=X.shape;bread=np.linalg.pinv(X.T@X);beta=bread@(X.T@Y);u=Y-X@beta;S=np.zeros((len(entities),k));T=np.zeros((len(dates),k));cell=np.zeros((k,k))
 for j in range(k):
  score=X[:,j]*u;S[:,j]=np.bincount(e,weights=score,minlength=len(entities));T[:,j]=np.bincount(tt,weights=score,minlength=len(dates))
 for start in range(0,n,65536):score=X[start:start+65536]*u[start:start+65536,None];cell+=score.T@score
 M=S.T@S*len(entities)/max(len(entities)-1,1)+T.T@T*len(dates)/max(len(dates)-1,1)-cell*n/max(n-1,1);V=bread@M@bread*(n-1)/max(n-len(entities)-len(dates)-k+1,1);se=np.sqrt(np.where(np.diag(V)>=0,np.diag(V),np.nan));df=min(len(entities),len(dates))-1;crit=student_t.ppf(.975,df);rows=[]
 for j,name in enumerate(names):
  stat=beta[j]/se[j] if se[j]>0 else np.nan;rows.append(dict(term=name,beta=beta[j],se=se[j],t=stat,p=2*student_t.sf(abs(stat),df),ci_low=beta[j]-crit*se[j],ci_high=beta[j]+crit*se[j],df=df,n=n,stocks=len(entities),dates=len(dates),status='OK' if np.isfinite(se[j]) else 'NONPOSITIVE_TWO_WAY_VARIANCE'))
 return dict(rows=rows)
def prepare_aux():
 # Pre-event size is observed before the earliest control day, same timing as exposure.
 ex=pd.read_parquet(TMP/'exposures.parquet');cal=pd.read_csv(ROOT/'meta/actual_full_calendar.csv',parse_dates=['date']);dates=cal.date.to_numpy('datetime64[ns]');freezes=ex[['event_id','freeze_date']].drop_duplicates();targets={r.event_id:pd.Timestamp(dates[np.searchsorted(dates,np.datetime64(r.freeze_date),side='left')-1]) for r in freezes.itertuples()};needed=set(targets.values());pieces=[]
 for p in sorted(Path('/Volumes/Extreme SSD/QDC/data/QDCData/cn_valuation_1d/full').glob('*.parquet')):
  if not p.stem[:4].isdigit() or not 2017<=int(p.stem[:4])<=2026:continue
  for b in pq.ParquetFile(p).iter_batches(batch_size=100000,columns=['trade_date','symbol','circulating_market_cap'],use_threads=False):
   d=b.to_pandas(use_threads=False);d['date']=pd.to_datetime(d.trade_date,errors='coerce');d=d[d.date.isin(needed)];d['code']=d.symbol.str[:6]+np.where(d.symbol.str.endswith('.XSHG'),'.SH','.SZ');pieces.append(d[['date','code','circulating_market_cap']])
 caps=pd.concat(pieces,ignore_index=True).drop_duplicates(['code','date']);cc=[]
 for event,date in targets.items():
  c=caps[caps.date.eq(date)].copy();c['event_id']=event;c['cap_observation_date']=date;cc.append(c.drop(columns='date'))
 c=pd.concat(cc,ignore_index=True);c.to_parquet(TMP/'pre_cap.parquet',index=False)
 # Official joint-holiday placebo dates, restricted to years with original CSV Hong Kong and Southbound status.
 official=pd.read_csv(ROOT/'tables/official_calendar.csv',parse_dates=['date']);a=official[official.a_open].reset_index(drop=True);main_dates=set(pd.read_csv(ROOT/'tables/event_date_map.csv',parse_dates=['date']).date);joint=official[official.hk_holiday.eq(True)&~official.a_open].copy();joint['group']=(joint.date.diff().dt.days.gt(4)|joint.date.diff().isna()).cumsum();fake=[]
 for _,g in joint.groupby('group'):
  before=a[a.date.lt(g.date.min())].tail(1);after=a[a.date.gt(g.date.max())].head(1)
  for label,row in [('joint_before',before),('joint_after',after)]:
   if len(row) and bool(row.nb_open.iloc[0]) and row.date.iloc[0] not in main_dates:fake.append(dict(date=row.date.iloc[0],kind='joint_holiday_adjacent',role=label))
 south=a[a.nb_open.eq(True)&a.sb_open.eq(False)]
 for r in south.itertuples():fake.append(dict(date=r.date,kind='north_open_south_closed',role='southbound_only_closed'))
 fake=pd.DataFrame(fake).drop_duplicates(['date','kind']).sort_values('date');fake.to_csv(ROOT/'tables/placebo_event_dates.csv',index=False)
 # A normal day outside all actual event windows; all placebo controls are also verified northbound-open.
 maps=[];fevents=[]
 for j,r in enumerate(fake.itertuples(),1001):
  normal=a[a.nb_open.eq(True)&~a.date.isin(main_dates)&~a.date.isin(fake.date)];pre=normal[normal.date.lt(r.date)].tail(5).date.tolist();post=normal[normal.date.gt(r.date)].head(5).date.tolist()
  if len(pre)!=5 or len(post)!=5:continue
  freeze=min(pre);fevents.append(dict(event_id=j,start=r.date,freeze=freeze,kind=r.kind))
  for d in pre+post+[r.date]:maps.append(dict(event_id=j,date=d,treated=int(d==r.date),kind=r.kind,anchor=r.date,freeze_date=freeze))
 fm=pd.DataFrame(maps);fm['distance']=(fm.date-fm.anchor).abs().dt.days;fm=fm.sort_values(['kind','date','distance','event_id']).drop_duplicates(['kind','date']);fm.to_csv(ROOT/'tables/placebo_date_map.csv',index=False)
 # Reconstruct contemporaneous placebo exposures using the same public-data timing rule.
 h=pd.read_parquet(TMP/'holdings_public.parquet');elig=pd.read_csv(ROOT/'meta/eligibility_events.csv',parse_dates=['effective_date']);codes=pd.read_csv(ROOT/'meta/stock_universe.csv').code.tolist();out=[]
 for ev in fevents:
  freeze=ev['freeze'];state={}
  for r in elig[elig.effective_date.lt(freeze)].sort_values(['effective_date','source_row'],ascending=[True,False]).itertuples():
   s=str(r.change)
   if s=='Addition' or s.startswith('Addition (from List of Special') or 'changed from' in s:state[r.code]=1
   elif s.startswith('Transfer to List of Special') or s.startswith('Addition to List of Special') or s=='Removal' or 'changed to' in s or s=='Buy orders suspended':state[r.code]=0
   elif s=='Buy orders resumed':state[r.code]=1
  hc=h[h.available_date.lt(freeze)].sort_values(['available_date','holding_date']).drop_duplicates('code',keep='last');latest=hc.assign(ex=hc.code.str[-2:]).groupby('ex').holding_date.max().to_dict();hc=hc.set_index('code')
  for code in codes:
   el=state.get(code,0);rr=hc.loc[code] if code in hc.index else None;valid=rr is not None and rr.holding_date==latest.get(code[-2:]);dose=float(rr.dose) if valid else (0. if not el else np.nan);out.append(dict(event_id=ev['event_id'],code=code,dose=dose,eligible=el))
 pd.DataFrame(out).to_parquet(TMP/'placebo_exposure.parquet',index=False)
 print('AUX_PREPARED',len(fake),'placebo dates',len(fevents),'placebo windows',len(c),'cap snapshots')
def placebo_pooled(metric):
 tab=ds.dataset(TMP/'baseline',format='parquet').to_table(columns=['date','eligible_day','nb_open',metric],filter=ds.field('eligible_day')&ds.field('nb_open'),use_threads=False);d=tab.to_pandas(use_threads=False);del tab;d=d[np.isfinite(d[metric])].sort_values('date');v=d[metric].to_numpy();dates=d.date.to_numpy('datetime64[ns]');ex=pd.read_csv(ROOT/'tables/placebo_date_map.csv',parse_dates=['freeze_date'])[['event_id','freeze_date']].drop_duplicates();out=[]
 for r in ex.itertuples():
  j=np.searchsorted(dates,np.datetime64(r.freeze_date),side='left');q=np.quantile(v[:j],[.005,.01,.99,.995]) if j else np.full(4,np.nan);out.append(dict(event_id=r.event_id,metric=metric,baseline_before=r.freeze_date,n=j,q005=q[0],q01=q[1],q99=q[2],q995=q[3]))
 return out
def placebo_block(block):
 base=TMP/'baseline'/f'block_{block:03d}.parquet'
 if not base.exists():return
 history=pd.read_parquet(base).sort_values(['code','date']);d=history[history.eligible_day].copy();mapping=pd.read_csv(ROOT/'tables/placebo_date_map.csv',parse_dates=['date']);d=d.merge(mapping,on='date',validate='m:m');ex=pd.read_parquet(TMP/'placebo_exposure.parquet');ex=ex[ex.code.isin(d.code.unique())];d=d.merge(ex,on=['code','event_id'],validate='m:1');thresholds=pd.read_csv(ROOT/'tables/placebo_pooled_winsor_thresholds.csv').set_index(['event_id','metric'])
 for metric in METRICS:
  for name,lo,hi in [('w01',.01,.99),('w005',.005,.995)]:
   lower=pd.Series(np.nan,index=history.index);upper=lower.copy();nprior=lower.copy()
   for c,ix in history.groupby('code',sort=False).groups.items():
    g=history.loc[ix];z=g.loc[g.eligible_day&g.nb_open,metric];z=z[np.isfinite(z)];ql=z.expanding(min_periods=60).quantile(lo);qh=z.expanding(min_periods=60).quantile(hi);nn=pd.Series(np.arange(1,len(z)+1),index=z.index);sl=ql.reindex(g.index).ffill();sh=qh.reindex(g.index).ffill();sn=nn.reindex(g.index).ffill().fillna(0);sl.loc[z.index]=ql.shift(1).to_numpy();sh.loc[z.index]=qh.shift(1).to_numpy();sn.loc[z.index]=nn.shift(1,fill_value=0).to_numpy();lower.loc[ix]=sl;upper.loc[ix]=sh;nprior.loc[ix]=sn
   look=pd.DataFrame({'code':history.code,'date':history.date,'lo':lower,'hi':upper,'nprior':nprior});o=d[['code','date','event_id',metric]].merge(look,on=['code','date'],validate='m:1');fallback=o.nprior.lt(60)|o.lo.isna()|o.hi.isna();l='q01' if name=='w01' else 'q005';h='q99' if name=='w01' else 'q995';o.loc[fallback,'lo']=[thresholds.loc[(e,metric),l] for e in o.loc[fallback,'event_id']];o.loc[fallback,'hi']=[thresholds.loc[(e,metric),h] for e in o.loc[fallback,'event_id']];d[f'{metric}__{name}']=o[metric].clip(o.lo,o.hi).to_numpy()
 out=TMP/'placebo_panel';out.mkdir(exist_ok=True);d.to_parquet(out/f'{block:03d}.parquet',index=False)
def placebo_inference(q):
 q=q.replace([np.inf,-np.inf],np.nan).dropna(subset=['dose0','y']);model=fit(q,'y',['placebo_x','dose0'],keep=True)
 if 'X' not in model:return model['rows']
 r=model['rows'][0];X=model['X'];Y=model['Y'];xp=X[:,0].copy();yp=Y.copy()
 if X.shape[1]>1:z=X[:,1];xp-=z*(z@xp)/(z@z);yp-=z*(z@yp)/(z@z)
 dates=pd.DatetimeIndex(model['dates']);actual=q.groupby('date').treated.first().reindex(dates).to_numpy(bool);all_dates=pd.DatetimeIndex(pd.read_csv(ROOT/'meta/actual_full_calendar.csv',parse_dates=['date']).date);positions={t:i for i,t in enumerate(all_dates)};episodes=[]
 for date in dates[actual]:
  if not episodes or positions[date]>positions[episodes[-1][-1]]+1:episodes.append([date])
  else:episodes[-1].append(date)
 episode_map={date:i for i,episode in enumerate(episodes) for date in episode};mapping=pd.read_csv(ROOT/'tables/placebo_date_map.csv',parse_dates=['anchor']).drop_duplicates('event_id').set_index('event_id');anchors=q.event_id.map(mapping.anchor);group=anchors.map(episode_map)
 if group.isna().any():group=group.fillna(len(episodes))
 group,labels=pd.factorize(group,sort=True);scores=np.bincount(group,weights=xp*yp);rng=np.random.default_rng(SEED);weights=rng.choice(np.array([-np.sqrt(1.5),-1.,-np.sqrt(.5),np.sqrt(.5),1.,np.sqrt(1.5)]),size=(B,len(labels)));boot=weights@scores/(xp@xp);r['wild_p']=(1+np.sum(np.abs(boot)>=abs(r['beta'])))/(B+1);r['wild_B']=B;r['wild_clusters']=len(labels);r['independent_placebo_episodes']=len(episodes)
 choices=[];index={date:i for i,date in enumerate(dates)}
 for episode in episodes:
  start=episode[0];candidates=[]
  for date in dates:
   if date.year!=start.year or date.month!=start.month or date.dayofweek!=start.dayofweek:continue
   ii=positions[date];block=all_dates[ii:ii+len(episode)]
   if len(block)==len(episode) and all(t in index and not actual[index[t]] for t in block):candidates.append([index[t] for t in block])
  choices.append(candidates)
 if not choices or any(len(c)==0 for c in choices):r['ri_p']=np.nan;r['ri_B']=0;r['ri_status']='NO_MATCHED_NORMAL_DAY_SUPPORT'
 else:
  Z=[]
  for _ in range(B):
   z=np.zeros(len(dates));valid=True
   for c in choices:
    available=[b for b in c if not z[b].any()]
    if not len(available):valid=False;break
    z[available[rng.integers(len(available))]]=1
   if valid:Z.append(z)
  if not Z:r['ri_p']=np.nan;r['ri_B']=0;r['ri_status']='NO_NONOVERLAPPING_MATCHED_CALENDAR';return model['rows']
  Z=np.unique(np.asarray(Z),axis=0);obs=model['d'];K,partial=design_K(obs,model['e'],model['t'],obs.dose0.to_numpy());bb=np.bincount(model['t'],weights=obs.dose0.to_numpy()*Y)
  if partial is not None:v,den=partial;bb-=v*bb.sum()/den
  numerator=Z@bb;denominator=np.einsum('ij,ij->i',Z@K,Z);beta=numerator[denominator>1e-10]/denominator[denominator>1e-10];r['ri_p']=(1+np.sum(np.abs(beta)>=abs(r['beta'])))/(len(beta)+1);r['ri_B']=len(beta);r['ri_status']='MATCHED_YEAR_MONTH_WEEKDAY_NORMAL_DATES'
 return model['rows']
def auxiliary_metric(metric):
 col=metric+'__w01';columns=['code','date','event_id','closed','resume','relative','anchor','dose','eligible','pre60_normal_amount',metric,col];f=ds.dataset(TMP/'panel',format='parquet').to_table(columns=columns,use_threads=False).to_pandas(use_threads=False);caps=pd.read_parquet(TMP/'pre_cap.parquet');f=f.merge(caps,on=['event_id','code'],how='left',validate='m:1');f['code']=pd.Categorical(f.code);out=[];dynamic=[]
 cal=pd.read_csv(ROOT/'meta/actual_full_calendar.csv',parse_dates=['date']);pos={t:i for i,t in enumerate(cal.date)};f['event_time']=f.date.map(pos)-f.anchor.map(pos)
 for exposure in ['dose','eligible']:
  d=f.rename(columns={col:'y',exposure:'dose0'}).copy();d['closed_x']=d.closed.astype(float)*d.dose0;d['resume_x']=d.resume.astype(float)*d.dose0
  # Recovery is jointly estimated with the closure, rather than treating closure days as ordinary controls.
  if metric in ['ln_amount','ln_volume','return_bp']:
   model=fit(d,'y',['resume_x','closed_x','dose0'])
   out.extend(dict(metric=metric,exposure=exposure,specification='reopening_joint_with_closure',**r) for r in model['rows'])
  if metric=='return_bp':
   cumulative=d[d.closed].groupby(['event_id','code'])[metric].agg(['sum','count']).reset_index().rename(columns={'sum':'closed_cum_bp','count':'observed_closed_days'});events=pd.read_csv(ROOT/'tables/events.csv').set_index('event_id');cumulative['required_closed_days']=cumulative.event_id.map(events.n_closed_days);cumulative=cumulative[cumulative.observed_closed_days.eq(cumulative.required_closed_days)]
   q=d[d.resume].merge(cumulative,on=['event_id','code'],validate='1:1');q['cum_x']=q.closed_cum_bp*q.dose0;model=fit(q,'y',['cum_x','closed_cum_bp','dose0'],keep=True)
   if 'X' in model:
    X=model['X'];Y=model['Y'];xp=X[:,0].copy();yp=Y.copy()
    if X.shape[1]>1:
     z=X[:,1:];xp-=z@np.linalg.lstsq(z,xp,rcond=None)[0];yp-=z@np.linalg.lstsq(z,yp,rcond=None)[0]
    groups=model['t'];score=np.bincount(groups,weights=xp*yp);rng=np.random.default_rng(SEED);w=rng.choice(np.array([-np.sqrt(1.5),-1.,-np.sqrt(.5),np.sqrt(.5),1.,np.sqrt(1.5)]),size=(B,len(score)));boot=w@score/(xp@xp);model['rows'][0]['wild_p']=(1+np.sum(np.abs(boot)>=abs(model['rows'][0]['beta'])))/(B+1);model['rows'][0]['wild_B']=B
   out.extend(dict(metric=metric,exposure=exposure,specification='closed_cumulative_to_reopen_intraday_association',**r) for r in model['rows'])
  if metric in PRIMARY:
   for group_name,var in [('pre_liquidity','pre60_normal_amount'),('pre_size','circulating_market_cap')]:
    med=d[['event_id','code',var]].drop_duplicates(['event_id','code']).groupby('event_id')[var].median();d['high_group']=d[var].gt(d.event_id.map(med));known=d[var].notna()&d[var].gt(0)
    for high in [False,True]:
     q=d[known&d.high_group.eq(high)];model=fit(q,'y',['closed_x','dose0']);out.extend(dict(metric=metric,exposure=exposure,specification=group_name,subgroup='high' if high else 'low',**r) for r in model['rows'])
   # Drop post days beyond +5 rather than make them part of the omitted category.
   q=d.loc[d.event_time.between(-5,5),['code','date','y','dose0','event_time']];model=dynamic_fit(q);dynamic.extend(dict(metric=metric,exposure=exposure,specification='dynamic_w01_reference_minus1',**r) for r in model['rows'])
 pd.DataFrame(out).to_csv(ROOT/f'tables/mechanism_{metric}.csv',index=False);pd.DataFrame(dynamic).to_csv(ROOT/f'tables/dynamic_{metric}.csv',index=False)
 pc=['code','date','event_id','kind','treated','dose','eligible',metric,metric+'__w01',metric+'__w005'];p=ds.dataset(TMP/'placebo_panel',format='parquet').to_table(columns=pc,use_threads=False).to_pandas(use_threads=False);rows=[]
 for kind,g in p.groupby('kind'):
  for exposure in ['dose','eligible']:
   for variant,col in [('raw',metric),('w01',metric+'__w01'),('w005',metric+'__w005')]:
    q=g.rename(columns={exposure:'dose0',col:'y'}).copy();q['placebo_x']=q.treated*q.dose0;rr=placebo_inference(q);rows.extend(dict(metric=metric,exposure=exposure,placebo=kind,variant=variant,independent_placebo_days=q.loc[q.treated.eq(1),'date'].nunique(),**r) for r in rr)
 pd.DataFrame(rows).to_csv(ROOT/f'tables/placebo_{metric}.csv',index=False);return dict(metric=metric,mechanism=len(out),dynamic=len(dynamic),placebo=len(rows))
def main():
 ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['prepare','pooled','placebo_panel','estimate']);a=ap.parse_args()
 if a.stage=='prepare':prepare_aux()
 elif a.stage=='pooled':
  records=[]
  for start in range(0,len(METRICS),4):
   with cf.ProcessPoolExecutor(max_workers=4) as p:records.extend(r for rr in p.map(placebo_pooled,METRICS[start:start+4]) for r in rr)
  pd.DataFrame(records).to_csv(ROOT/'tables/placebo_pooled_winsor_thresholds.csv',index=False)
 elif a.stage=='placebo_panel':
  n=int(np.ceil(len(pd.read_csv(ROOT/'meta/stock_universe.csv'))/20))
  with cf.ProcessPoolExecutor(max_workers=4) as p:list(p.map(placebo_block,range(n)))
 else:
  metrics=PRIMARY+['ln_amount','ln_volume','return_bp']
  for start in range(0,len(metrics),4):
   with cf.ProcessPoolExecutor(max_workers=4) as p:
    for r in p.map(auxiliary_metric,metrics[start:start+4]):print(r,flush=True)
  for stem in ['mechanism','dynamic','placebo']:
   pieces=[]
   for m in metrics:
    p=ROOT/f'tables/{stem}_{m}.csv'
    if p.stat().st_size>2:pieces.append(pd.read_csv(p))
   pd.concat(pieces,ignore_index=True).to_csv(ROOT/f'tables/{stem}_estimates.csv',index=False)
if __name__=='__main__':main()
