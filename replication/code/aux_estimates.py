"""Parallelize individual registered auxiliary specifications, with narrow column projections."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[k]='1'
from pathlib import Path
import numpy as np,pandas as pd,pyarrow as pa,pyarrow.dataset as ds,concurrent.futures as cf,json
from estimate import ROOT,TMP,PRIMARY,fit,SEED,B
from auxiliary import dynamic_fit,placebo_inference,release_memory
pa.set_cpu_count(1);pa.set_io_thread_count(1);pa.set_memory_pool(pa.system_memory_pool())
METRICS=PRIMARY+['ln_amount','ln_volume','return_bp']
def read(source,columns):
 f=ds.dataset(source,format='parquet').to_table(columns=columns,use_threads=False).to_pandas(use_threads=False);f['code']=pd.Categorical(f.code);return f
def mechanism(metric,exposure):
 cols=['code','date','event_id','closed','resume',exposure,'pre60_normal_amount',metric+'__w01']
 if metric=='return_bp':cols.append('return_bp')
 d=read(TMP/'panel',cols).rename(columns={exposure:'dose0',metric+'__w01':'y'});d['closed_x']=d.closed.astype(float)*d.dose0;d['resume_x']=d.resume.astype(float)*d.dose0;out=[]
 if metric in ['ln_amount','ln_volume','return_bp']:
  model=fit(d,'y',['resume_x','closed_x','dose0']);out.extend(dict(specification='reopening_joint_with_closure',**r) for r in model['rows']);del model;release_memory()
 if metric in PRIMARY:
  caps=pd.read_parquet(TMP/'pre_cap.parquet',columns=['event_id','code','circulating_market_cap']);caps=caps[caps.code.isin(d.code.cat.categories)].copy();caps['code']=pd.Categorical(caps.code,categories=d.code.cat.categories);d=d.merge(caps,on=['event_id','code'],how='left',validate='m:1');del caps
  for label,var in [('pre_liquidity','pre60_normal_amount'),('pre_size','circulating_market_cap')]:
   median=d[['event_id','code',var]].drop_duplicates(['event_id','code']).groupby('event_id')[var].median();high=d[var].gt(d.event_id.map(median));known=d[var].notna()&d[var].gt(0)
   for value in [False,True]:
    q=d.loc[known&high.eq(value),['code','date','y','closed_x','dose0']];model=fit(q,'y',['closed_x','dose0']);out.extend(dict(specification=label,subgroup='high' if value else 'low',**r) for r in model['rows']);del q,model;release_memory()
 if metric=='return_bp':
  cumulative=d[d.closed].groupby(['event_id','code'],observed=True).return_bp.agg(['sum','count']).reset_index().rename(columns={'sum':'closed_cum_bp','count':'observed_closed_days'});events=pd.read_csv(ROOT/'tables/events.csv').set_index('event_id');cumulative['required_closed_days']=cumulative.event_id.map(events.n_closed_days);cumulative=cumulative[cumulative.observed_closed_days.eq(cumulative.required_closed_days)];q=d[d.resume].merge(cumulative,on=['event_id','code'],validate='1:1');q['cum_x']=q.closed_cum_bp*q.dose0;model=fit(q,'y',['cum_x','closed_cum_bp','dose0'],keep=True)
  if 'X' in model:
   X=model['X'];Y=model['Y'];xp=X[:,0].copy();yp=Y.copy()
   if X.shape[1]>1:z=X[:,1:];xp-=z@np.linalg.lstsq(z,xp,rcond=None)[0];yp-=z@np.linalg.lstsq(z,yp,rcond=None)[0]
   score=np.bincount(model['t'],weights=xp*yp);rng=np.random.default_rng(SEED);w=rng.choice(np.array([-np.sqrt(1.5),-1.,-np.sqrt(.5),np.sqrt(.5),1.,np.sqrt(1.5)]),size=(B,len(score)));boot=w@score/(xp@xp);model['rows'][0].update(wild_p=(1+np.sum(np.abs(boot)>=abs(model['rows'][0]['beta'])))/(B+1),wild_B=B)
  out.extend(dict(specification='closed_cumulative_to_reopen_intraday_association',**r) for r in model['rows'])
 return out
def dynamic(metric,exposure):
 d=read(TMP/'panel',['code','date',exposure,metric+'__w01','anchor']).rename(columns={exposure:'dose0',metric+'__w01':'y'});dates=pd.DatetimeIndex(pd.read_csv(ROOT/'meta/actual_full_calendar.csv',parse_dates=['date']).date);position={t:i for i,t in enumerate(dates)};d['event_time']=d.date.map(position)-d.anchor.map(position);q=d.loc[d.event_time.between(-5,5),['code','date','y','dose0','event_time']];del d;release_memory();model=dynamic_fit(q);return [dict(specification='dynamic_w01_reference_minus1',**r) for r in model['rows']]
def placebo(metric,exposure):
 p=read(TMP/'placebo_panel',['code','date','event_id','kind','treated',exposure,metric,metric+'__w01',metric+'__w005']);out=[]
 for kind,g in p.groupby('kind',observed=True):
  for variant,col in [('raw',metric),('w01',metric+'__w01'),('w005',metric+'__w005')]:
   q=g[['code','date','event_id','treated',exposure,col]].rename(columns={exposure:'dose0',col:'y'}).copy();q['placebo_x']=q.treated*q.dose0;rows=placebo_inference(q);out.extend(dict(placebo=kind,variant=variant,independent_placebo_days=q.loc[q.treated.eq(1),'date'].nunique(),**r) for r in rows);del q;release_memory()
 return out
def task(job):
 kind,metric,exposure=job;print(json.dumps({'phase':kind,'metric':metric,'exposure':exposure,'status':'START'}),flush=True);rows=globals()[kind](metric,exposure);f=pd.DataFrame(rows);f['metric']=metric;f['exposure']=exposure;p=ROOT/f'tables/{kind}_{metric}_{exposure}.csv';f.to_csv(p,index=False);print(json.dumps({'phase':kind,'metric':metric,'exposure':exposure,'status':'DONE','rows':len(f)}),flush=True);return dict(kind=kind,path=str(p),rows=len(f))
def main():
 jobs=[('mechanism',m,e) for m in METRICS for e in ['dose','eligible']]+[('dynamic',m,e) for m in PRIMARY for e in ['dose','eligible']]+[('placebo',m,e) for m in METRICS for e in ['dose','eligible']];results=[]
 for start in range(0,len(jobs),4):
  with cf.ProcessPoolExecutor(max_workers=4) as pool:
   for r in pool.map(task,jobs[start:start+4]):results.append(r)
 for kind in ['mechanism','dynamic','placebo']:
  f=pd.concat([pd.read_csv(r['path']) for r in results if r['kind']==kind],ignore_index=True);f.to_csv(ROOT/f'tables/{kind}_estimates.csv',index=False)
 print(json.dumps({'status':'AUX_COMPLETE','tasks':len(results),'rows':sum(r['rows'] for r in results)}),flush=True)
if __name__=='__main__':main()
