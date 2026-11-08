from common import *
import pyarrow.dataset as ds,pyarrow.parquet as pq,concurrent.futures as cf
from scipy.stats import skew,kurtosis
from inference import fit,summarize,calendar_plan,coefficient_ri,bh,EVENTS,legacy,W


def empty(spec,metric,variant,status):return dict(specification=spec,metric=metric,variant=variant,term='closed_dose',status=status,n=0,stocks=0,dates=0,events=0,stock_clusters=0,date_clusters=0,wild_clusters=0,wild_B=0,ri_B=0,beta=np.nan,beta_x100=np.nan,se=np.nan,p=np.nan)

def run_job(job):
 kind,metric=job;cols=['code','date','event_id','kind','family','closed','resume','relative','dose','closed_dose','restore_dose',metric,metric+'__w01',metric+'__w005']
 if kind=='segments':cols+=['segment','mixed_boundary','closed_segment','restored_segment']
 frames=[];universe=pd.read_csv(P/'meta/stock_universe.csv').code.tolist();code_type=pd.CategoricalDtype(categories=sorted(universe));kind_type=pd.CategoricalDtype(categories=['holiday','weather','placebo']);family_type=pd.CategoricalDtype(categories=['holiday','weather','partial','placebo'])
 for path in sorted((T/('panel_'+kind)).glob('*.parquet')):
  pf=pq.ParquetFile(path);tab=pf.read(columns=cols,use_threads=False);pf.close()
  part=tab.to_pandas(use_threads=False)
  if not len(part):continue
  part['code']=part.code.astype(code_type);part['kind']=part.kind.astype(kind_type);part['family']=part.family.astype(family_type);part['event_id']=part.event_id.astype('int16')
  for name in ['closed','resume','relative']:
   if name in part:part[name]=part[name].astype('int8')
  if kind=='segments':
   days=part.date.to_numpy('datetime64[D]').astype('int64');assert ((days>=0)&(days<1000000)).all();idx=part.code.cat.codes.to_numpy(np.int64);assert (idx>=0).all();part['stock_day']=idx*1000000+days;part['event_segment']=part.event_id.to_numpy(np.int64)*8+part.segment.to_numpy(np.int64)
  frames.append(part)
 f=pd.concat(frames,ignore_index=True);del frames,tab,part;trim();latest=pd.read_parquet(T/'exposures_event_latest.parquet',columns=['event_id','code','dose_event_latest']);latest['code']=latest.code.astype(code_type);latest['event_id']=latest.event_id.astype('int16');f=f.merge(latest,on=['event_id','code'],validate='m:1');del latest;f['dose_window_freeze']=f.dose;f['code']=f.code.astype(code_type);f['kind']=f.kind.astype(kind_type);f['family']=f.family.astype(family_type);print('LOADED',kind,metric,len(f),round(f.memory_usage(deep=True).sum()/1e9,3),flush=True);eventmeta=EVENTS.set_index('event_id');f['anticipation']=f.event_id.map(eventmeta.anticipation).astype('category');rows=[];diags=[];rirows=[];riaudit=[];samples=[];checks=[]
 if kind=='segments':
  seg=f.segment.to_numpy(np.int64);start=np.where(seg<4,570+30*seg,780+30*(seg-4));end=start+30;cs=f.event_id.map(eventmeta.closed_start);ce=f.event_id.map(eventmeta.closed_end);f['pattern_closed']=((start>=cs)&(end<=ce)).astype(int);f['pattern_restore']=((ce<900)&(start>=ce)).astype(int);f=f[~f.mixed_boundary].copy()
 if kind=='daily':
  encoded=f.code.cat.codes.to_numpy(np.int64)*100000+f.date.to_numpy('datetime64[D]').astype('int64');weather=f.kind.eq('weather').to_numpy();weather_keys=np.unique(encoded[weather]);combined_keep=f.kind.isin(['holiday','weather']).to_numpy()&(weather|~np.isin(encoded,weather_keys,kind='sort'));del encoded,weather_keys
 cases=['holiday_baseline','full_day','combined','open_weather_placebo','full_prior_night','full_morning','full_recovery'] if kind=='daily' else ['half_day','half_event_segment_FE','half_prior_night','half_morning','half_recovery']
 for timing in ['event_latest','window_freeze']:
  r0,d0,a0,s0,c0,i0=len(rows),len(diags),len(riaudit),len(samples),len(checks),len(rirows)
  f['dose']=f['dose_event_latest' if timing=='event_latest' else 'dose_window_freeze']
  f['closed_dose']=f.dose*(f.closed_segment if kind=='segments' else f.closed)
  f['restore_dose']=f.dose*(f.restored_segment if kind=='segments' else f.resume)
  for variant in ['raw','w01','w005']:
   y=metric if variant=='raw' else metric+'__'+variant
   for spec in cases:
    if spec=='holiday_baseline':d=f[f.kind.eq('holiday')].copy()
    elif spec=='combined':
     d=f.loc[combined_keep].copy();d['closed_dose_typhoon']=d.closed_dose*d.kind.eq('weather');d['dose_typhoon']=d.dose*d.kind.eq('weather')
    elif spec=='open_weather_placebo':d=f[f.kind.eq('placebo')].copy()
    elif kind=='daily':d=f[f.kind.eq('weather')].copy()
    else:d=f.copy()
    if spec.endswith('_prior_night'):d=d[d.anticipation.eq('prior_night_known')].copy()
    if spec.endswith('_morning'):d=d[d.anticipation.eq('morning_determined')].copy()
    if not len(d):rows.append(empty(spec,metric,variant,'NO_EVENTS_IN_REGISTERED_GROUP'));continue
    xs=['closed_dose','dose'] if kind=='daily' else ['closed_dose'];entity='code' if kind=='daily' else 'stock_day';time='date' if kind=='daily' else ('event_segment' if spec=='half_event_segment_FE' else 'segment');targets=['closed_dose']
    if spec=='combined':xs=['closed_dose','closed_dose_typhoon','dose','dose_typhoon'];targets=['closed_dose','closed_dose_typhoon','weather_total']
    if spec.endswith('_recovery'):xs=['restore_dose','closed_dose']+(['dose'] if kind=='daily' else []);targets=['restore_dose']
    print('FIT',timing,kind,metric,variant,spec,len(d),flush=True)
    trim();model,status=fit(d,y,xs,entity,time)
    if model is None:rows.append(empty(spec,metric,variant,status));continue
    dd=model['d'];v=dd[y].to_numpy();diags.append(dict(specification=spec,kind=kind,metric=metric,variant=variant,n=len(v),stocks=dd.code.nunique(),events=dd.event_id.nunique(),stock_clusters=dd.code.nunique(),date_clusters=dd.date.nunique(),mean=np.mean(v),sd=np.std(v,ddof=1),skew=skew(v,bias=False),excess_kurtosis=kurtosis(v,bias=False),zero_share=np.mean(v==0),min=np.min(v),max=np.max(v),q001=np.quantile(v,.001),q01=np.quantile(v,.01),q99=np.quantile(v,.99),q999=np.quantile(v,.999)))
    if variant=='w01':
     for eid,g in dd.groupby('event_id',observed=True):samples.append(dict(specification=spec,metric=metric,event_id=eid,n=len(g),stocks=g.code.nunique(),events=1,stock_clusters=g.code.nunique(),date_clusters=g.date.nunique(),actual_pre_dates=g.loc[g.closed.eq(0)&g.relative.lt(0),'date'].nunique(),actual_post_dates=g.loc[g.closed.eq(0)&g.relative.gt(0),'date'].nunique(),actual_event_dates=g.loc[g.closed.eq(1),'date'].nunique(),treated_obs=int(g.closed_dose.ne(0).sum()),closed_rows=int((g.closed_segment.eq(1) if kind=='segments' else g.closed.eq(1)).sum()),restore_rows=int(g.restore_dose.ne(0).sum()),normal_rows=int(g.closed.eq(0).sum()),dose_missing_in_input=int(d[d.event_id.eq(eid)].dose.isna().sum())))
    plan=calendar_plan(dd,spec);riaudit.append(plan[2].assign(metric=metric,variant=variant));rirows.append(dict(**plan[3],metric=metric,variant=variant,n=len(dd),stocks=dd.code.nunique(),events=dd.event_id.nunique(),stock_clusters=dd.code.nunique(),date_clusters=dd.date.nunique()))
    for target in targets:
     names=list(model['names']);c=np.zeros(len(names))
     if target=='weather_total':
      if any(n not in names for n in ['closed_dose','closed_dose_typhoon']):rows.append(empty(spec,metric,variant,'CONTRAST_NOT_IDENTIFIED'));continue
      c[names.index('closed_dose')]=1;c[names.index('closed_dose_typhoon')]=1
     elif target not in names:rows.append(empty(spec,metric,variant,'TARGET_ABSORBED'));continue
     else:c[names.index(target)]=1
     row,boot=summarize(model,c,target);row.update(specification=spec,metric=metric,variant=variant,fe='stock+date' if kind=='daily' else 'stock_by_date+'+time,treated_events=int(dd.loc[dd.closed_dose.ne(0),'event_id'].nunique()),restoration_events=int(dd.loc[dd.restore_dose.ne(0),'event_id'].nunique()),anticipation_unknown_events=int(dd.loc[dd.anticipation.eq('unknown'),'event_id'].nunique()))
     if target=='weather_total':row.update(ri_p=np.nan,ri_B=0,ri_status='DERIVED_CONTRAST_NO_SEPARATE_CALENDAR_RI',ri_unique_calendars=plan[3]['unique_calendars']);perms=np.array([])
     else:
      if kind=='segments' and target=='restore_dose':model['d']['pattern_closed']=model['d'].pattern_restore
      mask=dd.kind.eq('weather').to_numpy() if target=='closed_dose_typhoon' else None
      ri,perms=coefficient_ri(model,target,plan,segment=kind=='segments',mask=mask);row.update(ri)
     if target=='closed_dose' and spec in ['full_day','half_day']:
      # Separate preregistered 1000 false-date draws; exact coefficient for daily, score diagnostic for intraday.
      p1000=calendar_plan(dd,spec+'_false_dates',1000);fr,fb=coefficient_ri(model,target,p1000,segment=kind=='segments');row.update(false_dates_B=len(fb),false_dates_unique=p1000[3]['unique_calendars'],false_dates_status=p1000[3]['status'],false_dates_mean=float(np.mean(fb)) if len(fb) else np.nan,false_dates_q025=float(np.quantile(fb,.025)) if len(fb) else np.nan,false_dates_q975=float(np.quantile(fb,.975)) if len(fb) else np.nan,false_dates_tail_p=fr.get('ri_p',np.nan),false_dates_statistic='coefficient' if kind=='daily' else 'restricted score')
      save(pd.DataFrame({'draw':np.arange(len(fb))+1,'statistic':fb}),R/'tables'/f'false_dates_{timing}_{spec}_{metric}_{variant}.csv')
     rows.append(row)
     if 'ri_quadratic_abs_error' in row:checks.append(dict(specification=spec,metric=metric,variant=variant,term=target,error=row['ri_quadratic_abs_error']))
    del model,d,dd,v
    if 'g' in locals():del g
    legacy.FE_CACHE.clear();trim();print(kind,metric,variant,spec,'done',flush=True)
  for collection,start_idx in [(rows,r0),(diags,d0),(samples,s0),(checks,c0),(rirows,i0)]:
   for rec in collection[start_idx:]:rec['dose_timing']=timing
  for frame in riaudit[a0:]:frame['dose_timing']=timing
 save(pd.DataFrame(rows),R/'tables'/f'estimates_{kind}_{metric}.csv');save(pd.DataFrame(diags),R/'tables'/f'distributions_{kind}_{metric}.csv');save(pd.concat(riaudit,ignore_index=True),R/'tables'/f'ri_support_{kind}_{metric}.csv');save(pd.DataFrame(rirows),R/'tables'/f'ri_status_{kind}_{metric}.csv');save(pd.DataFrame(samples),R/'tables'/f'sample_{kind}_{metric}.csv');save(pd.DataFrame(checks),R/'logs'/f'quadratic_{kind}_{metric}.csv');return dict(kind=kind,metric=metric,rows=len(rows))

def main():
 import hashlib,datetime
 import pyarrow.parquet as pq
 expected_blocks=int(np.ceil(len(pd.read_csv(P/'meta/stock_universe.csv'))/20))
 for kind in ['daily','segments']:
  for block in range(expected_blocks):
   path=T/('panel_'+kind)/f'{block:03d}.parquet';assert path.exists(),str(path);pq.ParquetFile(path).metadata
   assert (T/'audits'/f'winsor_{kind}_{block:03d}.csv').exists()
 sample=pd.read_parquet(T/'panel_segments/000.parquet');sample=sample[sample.code.eq('000001.SZ')&sample.closed.eq(1)]
 expected_labels={102:([6,7],[],[5]),103:([0,1,2,3,4],[5,6,7],[]),105:([0,1,2,3,4],[5,6,7],[]),106:([0,1,2,3],[4,5,6,7],[]),107:([6,7],[],[5]),111:([0,1,2,3,4,5],[6,7],[])}
 label_checks=[]
 for eid,(closed,restored,mixed) in expected_labels.items():
  g=sample[sample.event_id.eq(eid)]
  assert sorted(g.loc[g.closed_segment.eq(1),'segment'].tolist())==closed
  assert sorted(g.loc[g.restored_segment.eq(1),'segment'].tolist())==restored
  assert sorted(g.loc[g.mixed_boundary,'segment'].tolist())==mixed
  label_checks.append(dict(event_id=eid,status='PASS',closed_segments=str(closed),restored_segments=str(restored),excluded_mixed_segments=str(mixed)))
 save(pd.DataFrame(label_checks),R/'logs/intraday_clock_label_checks.csv')
 lock=dict(timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),preregistration_sha256=hashlib.sha256((R/'PREREGISTRATION_R6.md').read_bytes()).hexdigest(),calendar_gate_sha256=hashlib.sha256((R/'meta/calendar_gate.json').read_bytes()).hexdigest());
 if not (R/'meta/first_estimation.json').exists():(R/'meta/first_estimation.json').write_text(json.dumps(lock,indent=2))
 (R/'meta/last_estimation.json').write_text(json.dumps(lock,indent=2))
 (R/'data').mkdir(exist_ok=True);np.savez_compressed(R/'data/webb_weights.npz',seed=SEED,event_ids=EVENTS.event_id.to_numpy(),weights=W)
 jobs=[(kind,m) for m in ['if_delay','ih_delay'] for kind in ['daily','segments']]
 for start in range(0,len(jobs),1):
  with cf.ProcessPoolExecutor(max_workers=4) as pool:
   for r in pool.map(run_job,jobs[start:start+1],chunksize=1):print(r,flush=True)
 result=pd.concat([pd.read_csv(R/'tables'/f'estimates_{k}_{m}.csv') for k,m in jobs],ignore_index=True)
 for key,idx in result.groupby(['dose_timing','specification','variant','term'],dropna=False).groups.items():result.loc[idx,'q_BH_two_outcomes']=bh(result.loc[idx,'p'])
 save(result,R/'tables/main_estimates.csv');save(result[['dose_timing','specification','metric','variant','term','status','n','stocks','events','stock_clusters','date_clusters','wild_clusters','ri_B']],R/'tables/specification_status.csv')
 save(pd.concat([pd.read_csv(R/'tables'/f'sample_{k}_{m}.csv') for k,m in jobs]),R/'sample_by_event.csv');save(pd.concat([pd.read_csv(R/'tables'/f'distributions_{k}_{m}.csv') for k,m in jobs]),R/'tables/distributions.csv')
if __name__=='__main__':main()
