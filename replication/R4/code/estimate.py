from common import *
import importlib.util,concurrent.futures as cf,pyarrow.dataset as ds,pickle,time,multiprocessing as mp
spec=importlib.util.spec_from_file_location('r2engine',P/'R2/code/estimate_r2.py');eng=importlib.util.module_from_spec(spec);spec.loader.exec_module(eng);eng.R=R;eng.T=T;eng.SEED=SEED;eng.B=B
from bounded_inference import inference as bounded
def specifications():
 s=[dict(name='baseline',dose='dose',period='all',controls=[])]
 for c in MINUTE+DAILY:s.append(dict(name='HK_single_'+c,controls=[c]))
 for name,cc in [('minute_all',MINUTE),('daily_all',DAILY),('daily_HSI',DAILY[:4]),('all',MINUTE+DAILY),('available_minute_HSI',MINUTE+DAILY[:4]),('all_race7',MINUTE+DAILY+RACE[:-1]),('all_race8',MINUTE+DAILY+RACE),('available_HSI_race7',MINUTE+DAILY[:4]+RACE[:-1]),('available_HSI_race8',MINUTE+DAILY[:4]+RACE),('race7',RACE[:-1]),('race8',RACE)]:s.append(dict(name='HK_'+name,controls=cc))
 for c in ['hk_m_corr','hk_m_incr2','hk_HSI_corr','hk_HSCEI_corr']:s.append(dict(name='HK_triple_'+c,intl='high_'+c,mode='triple',controls=[]))
 s.append(dict(name='HK_race8_original_sample',controls=RACE[:-1]+['analyst_r2_original']))
 for name,dose,period in [('pre_daily','dose','pre'),('pre_quarter','dose_quarter','pre'),('pre_daily_same_quarter','dose','pre_quarter_sample'),('post_current','dose','post'),('post_quarter','dose_quarter','post'),('post_aug16','dose_aug16','post'),('unified_quarter','dose_quarter','all')]:s.append(dict(name='B_'+name,dose=dose,period=period,controls=[]))
 for dose in ['current','aug16']:
  for target in ['difference','pre','post']:s.append(dict(name=f'B_period_{dose}_{target}',mode='period',target=target,dose_rule=dose,controls=[]))
 for c in ['intl_share','intl_any','h_listed','bh_listed','foreign_first','export_industry']:
  s.append(dict(name='D_triple_'+c,intl=c,mode='triple',controls=[]));s.append(dict(name='D_sensitivity_'+c,intl=c,mode='sensitivity',controls=[]))
 return s
def _estimate_job(job):
 metric,variant,sp=job;start=time.time();name=sp['name'];dest=T/'fits'/f'{metric}_{variant}_{name}.pkl';dest.parent.mkdir(exist_ok=True)
 if dest.exists():return dict(cached=True,metric=metric,variant=variant,specification=name)
 lock=json.loads((R/'meta/preregistration_lock.json').read_text());digest=hashlib.sha256((R/'PREREGISTRATION_R4.md').read_bytes()).hexdigest();assert lock['sha256']==digest
 col=metric if variant=='raw' else metric+'__'+variant
 f=ds.dataset(T/'panel',format='parquet').to_table(columns=['code','date','event_id','closed',col],use_threads=False).to_pandas(use_threads=False);f.code=pd.Categorical(f.code)
 controls=sp.get('controls',[]);c=sp.get('intl');dc=sp.get('dose','dose');mode=sp.get('mode','main');period=sp.get('period','all');needed=list(dict.fromkeys(['code','event_id','dose',dc,'dose_quarter','dose_aug16','freeze_date',*controls]+([c] if c else [])));extra=[cc+'__'+variant for cc in controls+([c] if c else []) if cc in CONTINUOUS and cc not in RACE];features=pd.read_parquet(T/'features.parquet',columns=list(dict.fromkeys(needed+extra)));features=features[features.code.isin(f.code.cat.categories)].copy();feature=features[needed].copy();feature.code=pd.Categorical(feature.code,categories=f.code.cat.categories)
 for cc in controls+([c] if c else []):
  if cc in CONTINUOUS and cc not in RACE:feature[cc]=features[cc+'__'+variant]
 missing_all=[cc for cc in controls+([c] if c else []) if not feature[cc].notna().any()]
 if missing_all:
  target='triple' if mode=='triple' else 'cx_intl' if mode=='sensitivity' else 'closed_x';meta=dict(metric=metric,variant=variant,specification=name,mode=mode,target=target,controls=';'.join(controls),dose=dc,period=period,prereg_sha256=digest);row=dict(**meta,term=target,status='INSUFFICIENT_SOURCE_OR_COMPLETE_CASES',n=0,event_segments=0,reason='FEATURE_ENTIRELY_MISSING: '+','.join(missing_all));result=dict(rows=[row],bootstrap=None,seconds=time.time()-start);temp=dest.with_suffix('.partial');temp.write_bytes(pickle.dumps(result,protocol=5));temp.replace(dest);print(json.dumps(dict(**meta,status=row['status'],n=0,reason=row['reason']),ensure_ascii=False),flush=True);release();return dict(metric=metric,variant=variant,specification=name)
 f=f.merge(feature,on=['code','event_id'],how='left',validate='m:1').rename(columns={col:'y'});del features,feature
 post=f.freeze_date.ge('2024-08-19');keep=np.ones(len(f),bool)
 if period.startswith('pre'):keep&=~post
 if period=='post':keep&=post
 if period=='pre_quarter_sample':keep&=f.dose_quarter.notna()
 f=f.loc[keep].copy();f['dose0']=f[dc];f['closed_x']=f.closed.astype(float)*f.dose0;xs=['closed_x','dose0'];term='closed_x';ri_dose='dose0'
 for cc in controls:f['cx_'+cc]=f.closed.astype(float)*f[cc];xs+=['cx_'+cc,cc]
 if mode=='triple':
  f['hi']=f[c];f['dose_intl']=f.dose0*f.hi;f['cx_intl']=f.closed.astype(float)*f.hi;f['triple']=f.closed.astype(float)*f.dose_intl;xs=['triple','closed_x','cx_intl','dose_intl','dose0','hi'];term='triple';ri_dose='dose_intl'
 elif mode=='sensitivity':
  f['intl0']=f[c];f['cx_intl']=f.closed.astype(float)*f.intl0;xs=['cx_intl','intl0'];term='cx_intl';ri_dose='intl0'
 elif mode=='period':
  f['post']=f.freeze_date.ge('2024-08-19').astype(float)
  if sp['dose_rule']=='aug16':f.loc[f.post.eq(1),'dose0']=f.loc[f.post.eq(1),'dose_aug16']
  f['dose_post']=f.dose0*f.post;f['closed_x']=f.closed.astype(float)*f.dose0;f['triple']=f.closed.astype(float)*f.dose_post
  if sp['target']=='difference':xs=['triple','closed_x','dose0','dose_post'];term='triple';ri_dose='dose_post'
  else:
   f['dose_pre']=f.dose0*(1-f.post);f['cx_pre']=f.closed.astype(float)*f.dose_pre;f['cx_post']=f.closed.astype(float)*f.dose_post;term='cx_'+sp['target'];ri_dose='dose_'+sp['target'];xs=[term,*[x for x in ['cx_pre','cx_post'] if x!=term],'dose0','dose_post']
 valid=np.ones(len(f),dtype=bool)
 for value_column in ['y',*xs]:valid&=np.isfinite(f[value_column].to_numpy(dtype=float,na_value=np.nan))
 # Freeze the original Hold-estimation cohort even when replacing its dose or
 # omitting Hold as a regressor; unknown original Hold must not add observations.
 original_hold_known=np.isfinite(f['dose'].to_numpy(dtype=float,na_value=np.nan));original_hold_unknown_excluded=int((valid&~original_hold_known).sum());valid&=original_hold_known
 model_columns=list(dict.fromkeys(['code','date','event_id','closed','dose0',ri_dose,'y',*xs]));f.drop(columns=[x for x in f.columns if x not in model_columns],inplace=True);release()
 if not valid.all():f=f.loc[valid].reset_index(drop=True)
 else:f.reset_index(drop=True,inplace=True)
 release();meta=dict(metric=metric,variant=variant,specification=name,mode=mode,target=term,controls=';'.join(controls),dose=dc,period=period,prereg_sha256=digest,original_hold_unknown_excluded=original_hold_unknown_excluded)
 if len(f)<100 or f.event_id.nunique()<2:
  rows=[dict(**meta,term=term,status='INSUFFICIENT_SOURCE_OR_COMPLETE_CASES',n=len(f),event_segments=f.event_id.nunique())];boot=None
 else:
  rr,boot=bounded(f,'y',xs,term=term,ri_dose=ri_dose,engine=eng);rows=[dict(**meta,**r,event_segments=f.event_id.nunique()) for r in rr]
  if name=='baseline' and variant=='w01' and metric=='if_delay':
   reference,refboot=eng._inference(f,'y',xs,term=term,ri_dose=ri_dose);left=next(r for r in rr if r['term']==term);right=next(r for r in reference if r['term']==term);checks=[]
   for field in ['beta','se','p','wild_p','ri_p']:
    err=abs(left[field]-right[field]);assert err<1e-8,(field,left[field],right[field]);checks.append(dict(field=field,chunked=left[field],original_r2=right[field],absolute_error=err,status='PASS'))
   assert np.max(abs(boot-refboot))<1e-10;save(checks,'bounded_vs_original_r2_inference.csv');del reference,refboot;eng.RI_CACHE.clear();eng.r1.FE_CACHE.clear();release()
  main=next((r for r in rows if r['term']==term),rows[0]);main['beta_x100']=main.get('beta',np.nan)*100;main['se_x100']=main.get('se',np.nan)*100;main['mde80_x100']=main.get('mde80',np.nan)*100;main['events_with_cross_sectional_dose_variation']=int(f.groupby('event_id')[ri_dose].nunique().gt(1).sum())
  # Same complete-case benchmark quantifies attenuation separately from coverage loss.
  if name.startswith('HK_') and mode=='main' and controls:
   base=f[['code','date','event_id','closed','dose0','closed_x','y']].copy();br,_=bounded(base,'y',['closed_x','dose0'],engine=eng);row=next((r for r in br if r['term']=='closed_x'),{});main['same_sample_baseline_beta']=row.get('beta');main['same_sample_baseline_wild_p']=row.get('wild_p');main['same_sample_retention']=main.get('beta',np.nan)/row['beta'] if row.get('beta') else np.nan
 result=dict(rows=rows,bootstrap=boot,seconds=time.time()-start);tmp=dest.with_suffix('.partial');tmp.write_bytes(pickle.dumps(result,protocol=5));tmp.replace(dest);print(json.dumps(dict(**meta,n=len(f),status=rows[0]['status'],seconds=result['seconds']),ensure_ascii=False),flush=True);eng.RI_CACHE.clear();eng.r1.FE_CACHE.clear();release();return dict(metric=metric,variant=variant,specification=name)
def estimate_job(job):
 # Triple-interaction frames have six within columns despite zero extra controls.
 # Two shared filesystem locks bound their resident memory inside a four-worker pool.
 if job[2].get('mode')!='triple':return _estimate_job(job)
 import fcntl
 handles=[(T/f'triple_memory_slot_{i}.lock').open('a+') for i in range(2)];acquired=None
 try:
  while acquired is None:
   for h in handles:
    try:fcntl.flock(h.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB);acquired=h;break
    except BlockingIOError:pass
   if acquired is None:time.sleep(.1)
  return _estimate_job(job)
 finally:
  if acquired is not None:fcntl.flock(acquired.fileno(),fcntl.LOCK_UN)
  for h in handles:h.close()
def run():
 lock=json.loads((R/'meta/preregistration_lock.json').read_text());lock['estimation_started']=True;lock.setdefault('first_estimation_utc',datetime.datetime.now(datetime.timezone.utc).isoformat());js(R/'meta/preregistration_lock.json',lock)
 specs=specifications();save(specs,'registered_specifications.csv')
 # One fresh process per fit; numerical allocations are released at process exit.
 # Four-worker process ceiling, with a single resident wide specification to stay under 5GB.
 for variant in ['w01','raw','w005']:
  for sp in specs:
   jobs=[(m,variant,sp) for m in PRIMARY if not (T/'fits'/f'{m}_{variant}_{sp["name"]}.pkl').exists()]
   if not jobs:continue
   width=len(sp.get('controls',[]));slots=1 if width>=2 else 2 if width==1 else 4
   if sp.get('mode') in ['triple','period','sensitivity']:slots=min(slots,2)
   for start in range(0,len(jobs),slots):
    # Each batch contains at most one task per configured worker. Closing the
    # batch already releases every process; automatic recycling would start
    # redundant replacement processes while the executor is shutting down.
    with cf.ProcessPoolExecutor(max_workers=slots,mp_context=mp.get_context('spawn')) as pool:list(pool.map(estimate_job,jobs[start:start+slots]))
   print('SPEC_COMPLETE',variant,sp['name'],flush=True)
 consolidate()
def consolidate():
 records=[];bootmap={}
 for p in sorted((T/'fits').glob('*.pkl')):
  payload=pickle.loads(p.read_bytes());records+=payload['rows']
  if payload.get('bootstrap') is not None:
   r=payload['rows'][0];bootmap[(r['metric'],r['variant'],r['specification'])]=payload['bootstrap']
 f=pd.DataFrame(records);f['is_target']=f.term.eq(f.target);f['retention_vs_full_baseline']=np.nan
 for column in ['beta','se','ci_low','ci_high','mde80']:
  if column in f:f[column+'_x100']=f[column]*100
 for (m,v),ix in f.groupby(['metric','variant']).groups.items():
  b=f.loc[ix];base=b[b.specification.eq('baseline')&b.is_target].beta.dropna()
  if len(base) and base.iloc[0]!=0:
   keep=[i for i in ix if bool(f.loc[i,'is_target']) and f.loc[i,'mode']=='main'];f.loc[keep,'retention_vs_full_baseline']=f.loc[keep,'beta']/base.iloc[0]
 f['q_four_metrics']=np.nan;f['q_all_target_specs']=np.nan
 for (v,s),ix in f[f.is_target].groupby(['variant','specification']).groups.items():f.loc[ix,'q_four_metrics']=eng.r1.bh(f.loc[ix,'p']) if 'p' in f else np.nan
 for v,ix in f[f.is_target].groupby('variant').groups.items():f.loc[ix,'q_all_target_specs']=eng.r1.bh(f.loc[ix,'p'])
 # Inherit the original R2 fixed-SE Romano-Wolf routine unchanged.
 rspec=importlib.util.spec_from_file_location('r2_corrections',P/'R2/code/finalize_r2.py');cor=importlib.util.module_from_spec(rspec);rspec.loader.exec_module(cor);valid=f.is_target&f.status.eq('OK')&f.se.gt(0);f['q_bh_wild_four']=np.nan;f['q_bh_ri_four']=np.nan;f['p_romano_wolf_four']=np.nan;f['p_rw_all_main_w01']=np.nan
 for _,ix in f[valid].groupby(['variant','specification']).groups.items():
  ix=list(ix);f.loc[ix,'q_bh_wild_four']=eng.r1.bh(f.loc[ix,'wild_p']);f.loc[ix,'q_bh_ri_four']=eng.r1.bh(f.loc[ix,'ri_p']);bb=np.array([bootmap[(f.loc[i,'metric'],f.loc[i,'variant'],f.loc[i,'specification'])]/f.loc[i,'se'] for i in ix]);f.loc[ix,'p_romano_wolf_four']=cor.rw(None,f.loc[ix,'t'].to_numpy(),bb)
 ix=f.index[valid&f.variant.eq('w01')].tolist()
 if ix:
  bb=np.array([bootmap[(f.loc[i,'metric'],f.loc[i,'variant'],f.loc[i,'specification'])]/f.loc[i,'se'] for i in ix]);f.loc[ix,'p_rw_all_main_w01']=cor.rw(None,f.loc[ix,'t'].to_numpy(),bb)
 save(f,'estimates_all_terms.csv');save(f[f.is_target],'main_estimates.csv');save(f[f.is_target][['metric','variant','specification','status','n','event_segments']],'specification_status.csv')
 baseline=f[f.specification.eq('baseline')&f.is_target];old=pd.read_csv(P/'R2/tables/main_estimates.csv') if (P/'R2/tables/main_estimates.csv').exists() else pd.concat([pd.read_csv(P/'R2/tables'/f'estimates_{m}.csv') for m in PRIMARY]);old=old[old.specification.eq('baseline')&old.term.eq('closed_x')&old.exposure.eq('dose')];check=baseline.merge(old[['metric','variant','beta','n']],on=['metric','variant'],suffixes=('_r4','_r2'));check['beta_abs_error']=(check.beta_r4-check.beta_r2).abs();check['n_equal']=check.n_r4.eq(check.n_r2);save(check[['metric','variant','beta_r4','beta_r2','beta_abs_error','n_r4','n_r2','n_equal']],'r2_baseline_reproduction.csv');assert check.n_equal.all();assert check.beta_abs_error.max()<1e-9
 old=pd.read_csv(P/'R2/tables/main_estimates.csv');old=old[old.term.eq('closed_x')&old.exposure.eq('dose')&old.specification.isin(['race_cumulative_7','race_full_all'])].copy();old['specification']=old.specification.map({'race_cumulative_7':'HK_race7','race_full_all':'HK_race8_original_sample'});race=f[f.is_target&f.specification.isin(['HK_race7','HK_race8_original_sample'])].merge(old[['metric','variant','specification','beta','se','n']],on=['metric','variant','specification'],suffixes=('_r4','_r2'));race['beta_abs_error']=(race.beta_r4-race.beta_r2).abs();race['se_abs_error']=(race.se_r4-race.se_r2).abs();race['n_equal']=race.n_r4.eq(race.n_r2);save(race[['metric','variant','specification','beta_r4','beta_r2','beta_abs_error','se_abs_error','n_r4','n_r2','n_equal']],'r2_race_reproduction.csv');assert len(race)==24;assert race.n_equal.all() and race.beta_abs_error.max()<1e-7
 print('ESTIMATES COMPLETE',len(f),flush=True)
if __name__=='__main__':globals()[sys.argv[1]]()
