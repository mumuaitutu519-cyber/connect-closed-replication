from common import *
from inference import run,plan,bh
import pyarrow.dataset as ds,concurrent.futures as cf,multiprocessing as mp
TARGETS=['if_delay','ih_delay','if_r2_now','if_b0','if_b1','if_lag_sum','if_total_beta']

def read(cols,family='main'):
 f=ds.dataset(T/'panel',format='parquet').to_table(columns=list(dict.fromkeys(cols)),filter=ds.field('family')==family,use_threads=False).to_pandas(use_threads=False);f['code']=pd.Categorical(f.code);return f

def specifications(family):
 cc=RACE+HK
 specs=[('baseline',[],None),('full_control',cc,None),('full_control_no_AH',cc,'noAH'),('full_control_QFII',cc+['qfii'],None)]
 if family=='main':specs += [('full_control_HK17',RACE+HK+HKM,None),('HKOnly_baseline',[],'HKOnly'),('Shared_baseline',[],'Shared'),('HKOnly_full',cc,'HKOnly'),('Shared_full',cc,'Shared'),('HKOnly_full_no_AH',cc,'HKOnly_noAH'),('Shared_full_no_AH',cc,'Shared_noAH'),('HKOnly_full_QFII',cc+['qfii'],'HKOnly'),('Shared_full_QFII',cc+['qfii'],'Shared')]
 return specs

def one_spec(job):
 import pickle
 metric,v,family,name,controls,mask=job;folder=T/'fits';folder.mkdir(exist_ok=True);dest=folder/f'{metric}_{v}_{family}_{name}.pkl';digest=hashlib.sha256((R/'code/inference.py').read_bytes()).hexdigest()+(':AH_event_start_R2'if family=='US'and mask and 'noAH'in mask else'')
 if dest.exists():
  payload=pickle.loads(dest.read_bytes())
  if payload.get('inference_sha256')==digest:return payload['rows']
 col=metric if v=='raw'else metric+'__'+v;expr=ds.field('family')==family
 if mask and ('HKOnly'in mask or'Shared'in mask):
  eg=pd.read_csv(P/'R5/tables/F_event_classification.csv');ids=eg.loc[eg.hkonly.eq(1 if 'HKOnly'in mask else 0),'event_id'].tolist();expr=expr&ds.field('event_id').isin(ids)
 if mask and 'noAH'in mask and family=='main':expr=expr&((ds.field('ah')==0.0)|ds.field('ah').is_null())
 sourcecols=[c+'__'+v if c in HK+HKM else c for c in controls];cols=list(dict.fromkeys(['code','date','event_id','closed','dose',col,*sourcecols]));f=ds.dataset(T/'panel',format='parquet').to_table(columns=cols,filter=expr,use_threads=False).to_pandas(use_threads=False);f['code']=pd.Categorical(f.code)
 if mask and 'noAH'in mask and family=='US':
  ah=pd.read_csv(P/'R2/tables/AH_listing_history.csv').drop_duplicates('code').set_index('code')
  for c in ['hk_listing_date','hk_delisting_date']:ah[c]=pd.to_datetime(ah[c],format='mixed',errors='coerce')
  ev=pd.read_csv(R/'tables/design_events.csv',parse_dates=['start']).set_index('event_id');start=f.event_id.map(ev.start);listed=pd.to_datetime(f.code.map(ah.hk_listing_date),errors='coerce');delisted=pd.to_datetime(f.code.map(ah.hk_delisting_date),errors='coerce');isah=listed.lt(start)&(delisted.isna()|delisted.gt(start));f=f.loc[~isah].copy();release()
 f.rename(columns={col:'y',**{c+'__'+v:c for c in controls if c in HK+HKM}},inplace=True);f['closed_x']=f.closed.astype(float)*f.dose;xs=['closed_x','dose']
 for c in controls:f['cx_'+c]=f.closed.astype(float)*f[c];xs+=['cx_'+c,c]
 valid=np.ones(len(f),bool)
 for c in ['y',*xs]:valid&=np.isfinite(f[c].to_numpy(float))
 if not valid.all():f=f.loc[valid].reset_index(drop=True)
 release();meta=dict(metric=metric,variant=v,family=family,specification=name,controls=';'.join(controls),ah_timing='event_start_R2'if mask and 'noAH'in mask else'not_applicable');r=run(f,xs,plan=plan(family));rows=[dict(**meta,**r)]
 if controls:
  br=run(f[['code','date','event_id','closed','dose','closed_x','y']],['closed_x','dose'],plan=plan(family));rows[0].update(same_sample_baseline_beta=br.get('beta'),same_sample_baseline_p=br.get('p'),same_sample_baseline_wild_p=br.get('wild_p'),same_sample_retention=r.get('beta',np.nan)/br['beta']if br.get('beta')else np.nan)
 if name.endswith('QFII'):rows.append(dict(**meta,**run(f,xs,term='cx_qfii',plan=plan(family),dosecol='qfii')))
 temp=dest.with_suffix('.partial');temp.write_bytes(pickle.dumps(dict(rows=rows,inference_sha256=digest),protocol=5));temp.replace(dest);print('FIT',metric,v,family,name,r.get('beta'),r.get('n'),flush=True);return rows

def stale(job):
 metric,v=job;col=metric if v=='raw'else metric+'__'+v;f=read(['code','date','event_id','closed','dose',col,'nonzero_count']).rename(columns={col:'y'});f['closed_x']=f.closed*f.dose;f['cx_nonzero_count']=f.closed*f.nonzero_count;r=run(f,['closed_x','dose','nonzero_count','cx_nonzero_count'],plan=plan('main'));save([dict(metric=metric,variant=v,specification='stale_count_control',**r)],f'stale_{metric}_{v}.csv');return r

def horizon(job):
 metric,v=job;col=metric if v=='raw'else metric+'__'+v;family='quiet'if metric in ['quiet_delay','quiet_delay_ih','quiet_sync']else'main';actual={'quiet_delay':'if_delay','quiet_delay_ih':'ih_delay','quiet_sync':'if_r2_now'}.get(metric,metric);col=actual if v=='raw'else actual+'__'+v;f=read(['code','date','event_id','closed','dose',col],family).rename(columns={col:'y'});f['closed_x']=f.closed*f.dose;r=run(f,['closed_x','dose'],plan=plan(family));rows=[dict(metric=metric,variant=v,specification='horizon'if family=='main'else'quiet',family=family,**r)]
 if metric.startswith(('beta_','r2_')):
  levels=[];z=f[np.isfinite(f.y)&np.isfinite(f.dose)]
  for closed,g0 in z.groupby('closed'):
   qs=g0.y.quantile([.01,.25,.5,.75,.99]);levels.append(dict(metric=metric,variant=v,closed=closed,mean=g0.y.mean(),sd=g0.y.std(),minimum=g0.y.min(),p01=qs.loc[.01],p25=qs.loc[.25],median=qs.loc[.5],p75=qs.loc[.75],p99=qs.loc[.99],maximum=g0.y.max(),n=len(g0),stocks=g0.code.nunique(),events=g0.event_id.nunique(),unit='stock-day OLS metric'))
  save(levels,f'levels_{metric}_{v}.csv')
  del z,g0,qs
 del f;release()
 if metric.startswith(('beta_','r2_')):
  commoncols=[(f'{p}_{h}'if v=='raw'else f'{p}_{h}__{v}')for p in ['beta','r2']for h in [1,5,15,30,60]];g=read(['code','date','event_id','closed','dose',*commoncols]);good=np.ones(len(g),bool)
  for c in commoncols:good&=np.isfinite(g[c].to_numpy(float))
  c1='beta_1'if v=='raw'else'beta_1__'+v;keep=list(dict.fromkeys(['code','date','event_id','closed','dose',col]+([c1]if metric.startswith('beta_')and metric!='beta_1'else[])));g=g.loc[good,keep].copy();del good;release();g['y']=g[col];g['closed_x']=g.closed*g.dose;rows.append(dict(metric=metric,variant=v,specification='horizon_common5',family='main',**run(g,['closed_x','dose'],plan=plan('main'))))
  if metric.startswith('beta_')and metric!='beta_1':
   c1='beta_1'if v=='raw'else'beta_1__'+v;g['y']=g[col]-g[c1];rows.append(dict(metric=metric,variant=v,specification='common5_difference_vs_1min',family='main',**run(g,['closed_x','dose'],plan=plan('main'))))
  del g;release()
 if metric.startswith('beta_')and metric!='beta_1':
  col1='beta_1'if v=='raw'else'beta_1__'+v;g=read(['code','date','event_id','closed','dose',col,col1]);g['y']=g[col]-g[col1];g['closed_x']=g.closed*g.dose;rows.append(dict(metric=metric,variant=v,specification='difference_vs_1min',family='main',**run(g,['closed_x','dose'],plan=plan('main'))))
 save(rows,f'horizon_{metric}_{v}.csv');return str(metric)

def cumulative(job):
 which,v=job;col='day_return'if v=='raw'else'day_return__'+v;f=read(['code','date','event_id','closed','dose',col]);f.rename(columns={col:'y'},inplace=True)
 if which=='next_open30':
  full=pd.DatetimeIndex(pd.read_csv(P/'meta/actual_full_calendar.csv',parse_dates=['date']).date);nextday=dict(zip(full[:-1],full[1:]));f['nextdate']=f.date.map(nextday);parts=[];open_col='open30_return'if v=='raw'else'open30_return__'+v
  # Reuse stock-specific past-day winsor thresholds where a next date is in the panel;
  # for non-window next dates, exact clipping is built in the history block below.
  for p in sorted((T/'next_returns').glob('*.parquet')):parts.append(pd.read_parquet(p,columns=['code','date',open_col]))
  g=pd.concat(parts,ignore_index=True).rename(columns={'date':'nextdate',open_col:'nexty'});f=f.merge(g,on=['code','nextdate'],how='left',validate='m:1');f['y']=f.nexty
 with np.load(T/'futures_IF.npz')as z:fr=pd.Series(z['day_return'],index=pd.to_datetime(z['dates'],unit='D'));valid=pd.Series(np.isfinite(z['returns']).sum(1),index=fr.index)
 f['if_day']=f.date.map(fr);f.loc[f.date.map(valid).fillna(0).lt(180),'if_day']=np.nan;f['closed_x']=f.closed*f.dose;f['if_dose']=f.if_day*f.dose;f['catchup_x']=f.closed*f.if_dose;r=run(f,['catchup_x','closed_x','if_dose','dose'],term='catchup_x',plan=plan('main'),dosecol='if_dose');save([dict(metric=which,variant=v,specification='cumulative_IF_closed_hold',**r)],f'cumulative_{which}_{v}.csv');return which

def special():
 for v in VARIANTS:
  for m in ['if_delay','ih_delay','if_r2_now']:
   if(R/'tables'/f'stale_{m}_{v}.csv').exists():continue
   with cf.ProcessPoolExecutor(max_workers=4,mp_context=mp.get_context('spawn'))as pool:list(pool.map(stale,[(m,v)]))
 jobs=[(f'{p}_{h}',v)for p in ['beta','r2']for h in [1,5,15,30,60]for v in VARIANTS]+[('nonzero_share',v)for v in VARIANTS]+[(m,v)for m in ['quiet_delay','quiet_delay_ih','quiet_sync']for v in VARIANTS]
 for job in jobs:
  if(R/'tables'/f'horizon_{job[0]}_{job[1]}.csv').exists():continue
  with cf.ProcessPoolExecutor(max_workers=4,mp_context=mp.get_context('spawn'))as pool:list(pool.map(horizon,[job]))
 for which in ['daily','next_open30']:
  for v in VARIANTS:
   if(R/'tables'/f'cumulative_{which}_{v}.csv').exists():continue
   with cf.ProcessPoolExecutor(max_workers=4,mp_context=mp.get_context('spawn'))as pool:list(pool.map(cumulative,[(which,v)]))


def main():
 lock=json.loads((R/'meta/preregistration_lock.json').read_text());lock['estimation_started']=True;lock.setdefault('first_estimation_utc',pd.Timestamp.now(tz='UTC').isoformat());js(R/'meta/preregistration_lock.json',lock)
 for v in VARIANTS:
  for metric in TARGETS:
   dest=R/'tables'/f'fit_{metric}_{v}.csv'
   if dest.exists():continue
   rows=[]
   for family in ['main','US']:
    for name,controls,mask in specifications(family):
     job=(metric,v,family,name,controls,mask)
     with cf.ProcessPoolExecutor(max_workers=4,mp_context=mp.get_context('spawn'))as pool:rows.extend(list(pool.map(one_spec,[job]))[0])
   out=pd.DataFrame(rows)
   for family,ix in out.groupby('family').groups.items():
    base=out.loc[ix];a=base[base.specification.eq('baseline')&base.term.eq('closed_x')].beta
    if len(a):out.loc[ix,'retention_vs_full_baseline']=out.loc[ix,'beta']/a.iloc[0]
   save(out,dest.name);release()
 out=pd.concat([pd.read_csv(R/'tables'/f'fit_{m}_{v}.csv')for m in TARGETS for v in VARIANTS],ignore_index=True);out['q_BH_seven']=out.groupby(['family','specification','variant','term']).p.transform(bh);save(out,'main_estimates.csv');special()
if __name__=='__main__':main()
