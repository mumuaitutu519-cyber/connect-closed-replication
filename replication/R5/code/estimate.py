from common import *
from infer import fit,infer,draws
import pyarrow.dataset as ds,concurrent.futures as cf,multiprocessing as mp
from scipy.stats import skew,kurtosis
LIMIT=None

def init(lim):
 global LIMIT
 LIMIT=lim

def read(cols):
 f=ds.dataset(T/'panel',format='parquet').to_table(columns=list(dict.fromkeys(cols)),use_threads=False).to_pandas(use_threads=False);f['code']=pd.Categorical(f.code);return f

def run_fit(d,xs,targets,W,plan,meta,mask=None):
 if mask is not None:d=d.loc[mask].copy()
 q=d.replace([np.inf,-np.inf],np.nan).dropna(subset=['y',*xs]);del d
 if len(q)<100:return[dict(**meta,term=k,n=len(q),stocks=q.code.nunique(),dates=q.date.nunique(),events=q.event_id.nunique(),status='INSUFFICIENT_COMPLETE_CASES')for k,_ in targets]
 model=fit(q,xs);out=[]
 for term,dosecol in targets:
  r=infer(q,model,term,W,plan if dosecol is not None else None,dose=q[dosecol].to_numpy()if dosecol is not None else None);out.append(dict(**meta,**r));release()
 del model,q;release()
 if out:print('FIT',meta.get('metric'),meta.get('variant'),meta.get('specification'),out[0].get('beta'),out[0].get('n'),out[0].get('events'),flush=True)
 return out

def task(job):
 with LIMIT:return worker(job)

def worker(job):
 metric,variant=job;dest=R/'tables'/f'estimates_{metric}_{variant}.csv'
 marker=T/f'fit_{metric}_{variant}.json'
 if marker.exists()and dest.exists():return str(dest)
 col=metric if variant=='raw'else metric+'__'+variant;needed=['code','date','event_id','closed','dose',col]
 if metric in PRIMARY:needed+=['valid_minutes','amount_decile','hold_p99','quintile','qfii','ln_amount','rv_bp2']+[f'{c}__{variant}'for c in ['ln_amount','rv_bp2']if variant!='raw']
 f=read(needed);f=f.rename(columns={col:'y','dose':'dose0'});f['closed_x']=f.closed.astype(float)*f.dose0;W,plan=draws();base=['code','date','event_id','closed','dose0','closed_x','y'];rows=[]
 v=f.y.to_numpy(float);v=v[np.isfinite(v)];q=np.quantile(v,[.001,.01,.99,.999])if len(v)else[np.nan]*4
 save(pd.DataFrame([dict(metric=metric,variant=variant,n=len(v),stocks=f.loc[f.y.notna(),'code'].nunique(),events=f.loc[f.y.notna(),'event_id'].nunique(),missing=len(f)-len(v),mean=np.mean(v),sd=np.std(v,ddof=1),skew=skew(v,bias=False),excess_kurtosis=kurtosis(v,bias=False),zero_share=np.mean(v==0),q001=q[0],q01=q[1],q99=q[2],q999=q[3])]),f'distribution_{metric}_{variant}.csv')
 meta=dict(metric=metric,variant=variant,specification='baseline');rows+=run_fit(f[base],['closed_x','dose0'],[('closed_x','dose0')],W,plan,meta)
 if metric not in PRIMARY:
  save(pd.DataFrame(rows),dest.name);js(marker,dict(prereg=hashlib.sha256((R/'PREREGISTRATION_R5.md').read_bytes()).hexdigest(),output_sha=hashlib.sha256(dest.read_bytes()).hexdigest()));return str(dest)
 eg=pd.read_csv(R/'tables/F_event_classification.csv').set_index('event_id');f['hkonly']=f.event_id.map(eg.hkonly);f['holiday_type']=f.event_id.map(eg.holiday_type)
 specs=[]
 for label,val in [('F_HKonly',1),('F_shared',0)]:
  rows+=run_fit(f.loc[f.hkonly.eq(val),base],['closed_x','dose0'],[('closed_x','dose0')],W,plan,dict(metric=metric,variant=variant,specification=label))
 d=f[base].copy();d['hk_dose']=f.hkonly*f.dose0;d['diff_x']=d.closed.astype(float)*d.hk_dose
 rows+=run_fit(d,['closed_x','diff_x','dose0','hk_dose'],[('closed_x','dose0'),('diff_x','hk_dose')],W,plan,dict(metric=metric,variant=variant,specification='F_difference'))
 # The HK-only slope in the same model is an explicitly reparameterized linear combination.
 d=f[base].copy();d['hk_dose']=f.hkonly*f.dose0;d['other_dose']=(1-f.hkonly)*f.dose0;d['hk_x']=d.closed*d.hk_dose;d['other_x']=d.closed*d.other_dose
 rows+=run_fit(d,['hk_x','other_x','dose0','hk_dose'],[('hk_x','hk_dose')],W,plan,dict(metric=metric,variant=variant,specification='F_HKonly_joint_slope'))
 # Strict HK cash holiday / all western venues full open, retaining original normal controls.
 cm=pd.read_csv(R/'tables/F_calendar_by_closed_day.csv',parse_dates=['date']);strict=set(cm.loc[cm.hk_actual_only_date,'date']);strict_ev=set(cm.loc[cm.hk_actual_only_date,'event_id']);d=f.loc[f.event_id.isin(strict_ev)&((~f.closed)|f.date.isin(strict)),base]
 rows+=run_fit(d,['closed_x','dose0'],[('closed_x','dose0')],W,plan,dict(metric=metric,variant=variant,specification='F_strict_HK_cash_days'))
 ctrl=['ln_amount','valid_minutes','rv_bp2'];d=f[base].copy();xs=['closed_x','dose0']
 for c in ctrl:
  cc=c if variant=='raw'or c=='valid_minutes'else c+'__'+variant;d['c_'+c]=f[cc];d['cx_'+c]=d.closed.astype(float)*d['c_'+c];xs+=['c_'+c,'cx_'+c]
 complete=d[['y',*xs]].replace([np.inf,-np.inf],np.nan).notna().all(1)
 rows+=run_fit(d,xs,[('closed_x','dose0')],W,plan,dict(metric=metric,variant=variant,specification='G_contemporaneous_controls'))
 rows+=run_fit(f.loc[complete,base],['closed_x','dose0'],[('closed_x','dose0')],W,plan,dict(metric=metric,variant=variant,specification='G_controls_same_sample_baseline'))
 for spec,mask in [('G_minutes_ge230',f.valid_minutes.ge(230)),('G_preamount_top3deciles',f.amount_decile.ge(7)),*[(f'G_preamount_D{k+1}',f.amount_decile.eq(k))for k in [7,8,9]]]:rows+=run_fit(f.loc[mask,base],['closed_x','dose0'],[('closed_x','dose0')],W,plan,dict(metric=metric,variant=variant,specification=spec))
 for label in ['耶稣受难/复活节','佛诞','中秋翌日','圣诞/节礼日','其他']:
  rows+=run_fit(f.loc[f.holiday_type.eq(label),base],['closed_x','dose0'],[('closed_x','dose0')],W,plan,dict(metric=metric,variant=variant,specification='I_holiday_'+label))
 over=f.dose0.gt(f.hold_p99);frozen=features();badstocks=set(frozen.loc[frozen.dose.gt(frozen.hold_p99),'code'])
 for spec,mask in [('I_drop_Hold_P99_stock_event',~over),('I_drop_any_P99_stock',~f.code.isin(badstocks))]:rows+=run_fit(f.loc[mask,base],['closed_x','dose0'],[('closed_x','dose0')],W,plan,dict(metric=metric,variant=variant,specification=spec))
 d=f[base].copy();d['dose0']=np.log1p(d.dose0);d['closed_x']=d.closed.astype(float)*d.dose0;rows+=run_fit(d,['closed_x','dose0'],[('closed_x','dose0')],W,plan,dict(metric=metric,variant=variant,specification='I_log1p_Hold'))
 d=f.loc[f.quintile.notna(),base].copy();xs=[];targets=[]
 for k in range(1,5):
  d[f'q{k}']=f.loc[d.index,'quintile'].eq(k).astype(float);d[f'closed_q{k}']=d.closed*d[f'q{k}'];xs+=[f'closed_q{k}',f'q{k}'];targets.append((f'closed_q{k}',f'q{k}'))
 rows+=run_fit(d,xs,targets,W,plan,dict(metric=metric,variant=variant,specification='I_Hold_quintiles'))
 weights=pd.read_parquet(T/'weights.parquet');weights=weights[weights.code.isin(f.code.cat.categories)].copy();weights['code']=pd.Categorical(weights.code,categories=f.code.cat.categories);d=f[base].merge(weights[['event_id','code','weight300','weight50']],on=['event_id','code'],validate='m:1');xs=['closed_x','dose0']
 for c in ['weight300','weight50']:d['cx_'+c]=d.closed*d[c];xs +=['cx_'+c,c]
 mask=d[['y',*xs]].notna().all(1)
 rows+=run_fit(d,xs,[('closed_x','dose0'),('cx_weight300','weight300'),('cx_weight50','weight50')],W,plan,dict(metric=metric,variant=variant,specification='I_index_weights_partial_race'))
 rows+=run_fit(d.loc[mask,base],['closed_x','dose0'],[('closed_x','dose0')],W,plan,dict(metric=metric,variant=variant,specification='I_weights_same_sample_baseline'))
 d=f[base].copy();d['qfii']=f.qfii;d['cx_qfii']=d.closed*d.qfii
 rows+=run_fit(d,['closed_x','dose0','cx_qfii','qfii'],[('closed_x','dose0'),('cx_qfii','qfii')],W,plan,dict(metric=metric,variant=variant,specification='J_QFII_race'))
 save(pd.DataFrame(rows),dest.name);js(marker,dict(prereg=hashlib.sha256((R/'PREREGISTRATION_R5.md').read_bytes()).hexdigest(),output_sha=hashlib.sha256(dest.read_bytes()).hexdigest()));print('ESTIMATED',metric,variant,len(rows),flush=True);return str(dest)

def main():
 lock=json.loads((R/'meta/preregistration_lock.json').read_text());assert lock['sha256']==hashlib.sha256((R/'PREREGISTRATION_R5.md').read_bytes()).hexdigest();lock['estimation_started']=True;js(R/'meta/preregistration_lock.json',lock)
 jobs=[(m,v)for m in METRICS for v in ['raw','w01','w005']];ctx=mp.get_context('spawn');lim=ctx.Semaphore(1)
 # 4 process workers; serialized large FE fits keep aggregate RSS below 4 GB.
 for i,job in enumerate(jobs):
  # Large primary designs use one fresh active worker; narrow component designs run in parallel below.
  if job[0]not in PRIMARY:continue
  with cf.ProcessPoolExecutor(max_workers=4,mp_context=ctx,initializer=init,initargs=(lim,))as pool:list(pool.map(task,[job]))
  print('ESTIMATE_PRIMARY',i+1,'/',6,flush=True)
 narrow=[job for job in jobs if job[0]not in PRIMARY]
 for i,job in enumerate(narrow):
  m,v=job
  if(T/f'fit_{m}_{v}.json').exists()and(R/'tables'/f'estimates_{m}_{v}.csv').exists():continue
  with cf.ProcessPoolExecutor(max_workers=4,mp_context=ctx,initializer=init,initargs=(lim,))as pool:list(pool.map(task,[job]))
  print('ESTIMATE_COMPONENT',i+1,'/',len(narrow),flush=True)
 save(pd.concat([pd.read_csv(R/'tables'/f'estimates_{m}_{v}.csv')for m,v in jobs],ignore_index=True),'all_estimates.csv')
if __name__=='__main__':main()
