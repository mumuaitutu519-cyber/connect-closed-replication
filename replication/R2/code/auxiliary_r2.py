import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
from pathlib import Path
import sys,json,shutil,multiprocessing as mp,concurrent.futures as cf,numpy as np,pandas as pd,pyarrow.dataset as ds
from scipy.stats import t as student_t,binomtest,norm
from scipy.spatial import cKDTree
from estimate_r2 import R,T,Q,PRIMARY,B,SEED,load,inference,release_memory,task,selected_task
sys.path.insert(0,str(Path(__file__).parent/'r1'))
import auxiliary as a
import estimate_r2 as engine
def bounded_aux(job):
 kind,metric=job;limiter=engine.FIT_LIMITER
 if limiter is None:return globals()[kind](metric)
 with limiter:
  engine.FIT_LIMITER=None
  try:
   result=globals()[kind](metric);release_memory();return result
  finally:engine.FIT_LIMITER=limiter

def extended():
 metrics=['if_delay_f5','ih_delay_f5','if_delay_f15','ih_delay_f15','if_lag_bigday','ih_lag_bigday','if_lag_bigpre','ih_lag_bigpre']
 for variant in ['raw','w01','w005']:
  for exposure in ['dose','eligible']:
   for start in range(0,len(metrics),4):
    with cf.ProcessPoolExecutor(max_workers=4)as pool:
     for m in pool.map(selected_task,[(m,(variant,'baseline',exposure))for m in metrics[start:start+4]]):print('EXTENDED',m,variant,exposure,flush=True)

def event_test(values,ids):
 v=np.asarray(values,float);ids=np.asarray(ids,int);good=np.isfinite(v);v=v[good];ids=ids[good];n=len(v)
 if n<2:return dict(status='INSUFFICIENT_EVENTS',events=n)
 se=np.std(v,ddof=1)/np.sqrt(n);b=np.mean(v);df=n-1;t=b/se if se>0 else np.nan;crit=student_t.ppf(.975,df)
 with np.load(R/'data/resampling_plan.npz')as z:W=z['webb']
 boot=W[:,ids-1]@v/n;nonzero=v[v!=0]
 return dict(status='OK',beta=b,se=se,t=t,df=df,p=2*student_t.sf(abs(t),df),ci_low=b-crit*se,ci_high=b+crit*se,sign_p=binomtest(int((nonzero>0).sum()),len(nonzero),.5).pvalue if len(nonzero)else 1.,events=n,positive_events=int((v>0).sum()),negative_events=int((v<0).sum()),wild_p=(1+np.sum(np.abs(boot)>=abs(b)))/(B+1),wild_B=B,mde80=(crit+norm.ppf(.8))*se)

def aggregates():
 f=load(T/'panel',['code','date','event_id','closed',*[c for m in PRIMARY for c in [m,m+'__w01',m+'__w005']]])
 feat=pd.read_parquet(T/'event_features.parquet',columns=['code','event_id','quintile']);f=f.merge(feat,on=['code','event_id'],how='left',validate='m:1');means=[];tests=[];diffs=[]
 for metric in PRIMARY:
  for variant,col in [('raw',metric),('w01',metric+'__w01'),('w005',metric+'__w005')]:
   d=f.groupby(['event_id','quintile','closed'],observed=True)[col].agg(['mean','count']).reset_index();d['metric']=metric;d['variant']=variant;means.append(d);wide=d.pivot(index=['event_id','quintile'],columns='closed',values='mean');wide['difference']=wide.get(True)-wide.get(False);w=wide.difference.unstack('quintile');v=w.get(4)-w.get(0);tests.append(dict(metric=metric,variant=variant,contrast='quintile5_minus_quintile1',**event_test(v.to_numpy(),v.index.to_numpy())));w=wide.reset_index()[['event_id','quintile','difference']];w['metric']=metric;w['variant']=variant;diffs.append(w)
 pd.concat(means,ignore_index=True).to_csv(R/'tables/event_quintile_means.csv',index=False);pd.concat(diffs,ignore_index=True).to_csv(R/'tables/event_quintile_differences.csv',index=False);pd.DataFrame(tests).to_csv(R/'tables/event_conservative_tests.csv',index=False)

def matching_event(job):
 ev,g=job;pairs=[];status=[]
 known=g[['logcap','logamount','ifbeta','dose']].notna().all(1);g=g[known].copy();positive=g.loc[g.eligible.eq(1)&g.dose.gt(0),'dose']
 if len(positive)<10:return pairs,status
 hi=g[g.eligible.eq(1)&g.dose.ge(positive.quantile(.75))];lo=g[(g.dose.le(positive.median()))|g.eligible.eq(0)];cols=['logcap','logamount','ifbeta'];mu=g[cols].mean();sd=g[cols].std()
 for kind in ['with_industry','without_industry']:
  high=hi[hi.industry.notna()]if kind=='with_industry'else hi;low=lo[lo.industry.notna()]if kind=='with_industry'else lo
  for n in [1,2,3]:
   used=0
   for industry,hg in (high.groupby('industry')if kind=='with_industry'else[('all',high)]):
    lg=low[low.industry.eq(industry)]if kind=='with_industry'else low
    if not len(lg)or not len(hg):continue
    xh=((hg[cols]-mu)/sd).to_numpy();xl=((lg[cols]-mu)/sd).to_numpy();dist,idx=cKDTree(xl).query(xh,k=3)
    for j,h in enumerate(hg.itertuples()):
     ix=[int(ii)for dd,ii in zip(dist[j,:n],idx[j,:n])if dd<=2 and ii<len(lg)]
     if not ix:continue
     used+=1
     for ii in ix:pairs.append(dict(event_id=ev,kind=kind,neighbors=n,high_code=h.code,low_code=lg.iloc[ii].code,n_controls=len(ix),distance=float(np.linalg.norm(xh[j]-xl[ii])),industry=industry))
   status.append(dict(event_id=ev,neighbors=n,kind=kind,high_candidates=len(high),matched_high=used,low_candidates=len(low)))
 return pairs,status

def matching_pairs():
 f=pd.read_parquet(T/'event_features.parquet');pairs=[];status=[]
 with cf.ProcessPoolExecutor(max_workers=4)as pool:
  for pp,ss in pool.map(matching_event,list(f.groupby('event_id'))):pairs.extend(pp);status.extend(ss)
 p=pd.DataFrame(pairs);p.to_csv(R/'tables/matching_pairs.csv',index=False);p[p.kind.eq('without_industry')].to_csv(R/'tables/matching_pairs_without_industry.csv',index=False);pd.DataFrame(status).to_csv(R/'tables/matching_support.csv',index=False);return p

def matching_metric(metric):
 from matched_panel import fit as matched_fit,weights as matched_weights
 pairs=pd.read_csv(R/'tables/matching_pairs.csv');out=[];eventrows=[];panels=[];boots=[]
 f=load(T/'panel',['code','date','event_id','closed',metric,metric+'__w01',metric+'__w005'])
 for variant,col in [('raw',metric),('w01',metric+'__w01'),('w005',metric+'__w005')]:
  m=f.groupby(['event_id','code','closed'],observed=True)[col].mean().unstack('closed');m['diff']=m.get(True)-m.get(False);d=m['diff'].reset_index()
  for kind in ['with_industry','without_industry']:
   for n in [1,2,3]:
    pp=pairs[pairs.neighbors.eq(n)&pairs.kind.eq(kind)];q=pp.merge(d.rename(columns={'code':'high_code','diff':'high_diff'}),on=['event_id','high_code'],validate='m:1').merge(d.rename(columns={'code':'low_code','diff':'low_diff'}),on=['event_id','low_code'],validate='m:1');q=q.dropna(subset=['high_diff','low_diff']);h=q.groupby(['event_id','high_code']).agg(high=('high_diff','first'),low=('low_diff','mean'));h['contrast']=h.high-h.low;v=h.groupby('event_id').contrast.mean();out.append(dict(metric=metric,variant=variant,neighbors=n,specification='matching_'+kind,**event_test(v.to_numpy(),v.index.to_numpy())));eventrows.extend(dict(metric=metric,variant=variant,kind=kind,neighbors=n,event_id=e,contrast=x)for e,x in v.items())
    w=matched_weights(pp);panel=f[['code','date','event_id','closed',col]].rename(columns={col:'y'}).merge(w,on=['code','event_id'],validate='m:1');panel=panel.dropna(subset=['y']);count=panel.groupby(['event_id','code','closed'],observed=True).y.transform('count');panel['weight']/=count;row,boot=matched_fit(panel);panels.append(dict(metric=metric,variant=variant,neighbors=n,specification='matching_'+kind,**row))
    if boot is not None:boots.append(boot);panels[-1]['boot_index']=len(boots)-1
    del panel,q;release_memory()
 pd.DataFrame(out).to_csv(R/f'tables/matching_events_{metric}.csv',index=False);pd.DataFrame(eventrows).to_csv(R/f'tables/matching_by_event_{metric}.csv',index=False);pd.DataFrame(panels).to_csv(R/f'tables/matching_panel_{metric}.csv',index=False);np.savez_compressed(T/f'bootstrap_matching_{metric}.npz',boot=np.array(boots));return metric

def matching():
 pairs=matching_pairs()
 context=mp.get_context('spawn');limiter=context.BoundedSemaphore(2)
 with cf.ProcessPoolExecutor(max_workers=4,max_tasks_per_child=1,mp_context=context,initializer=engine.init_worker,initargs=(limiter,))as pool:
  for m in pool.map(bounded_aux,[('matching_metric',m)for m in PRIMARY]):print('MATCHED',m,flush=True)
 for stem,dest in [('matching_events','matching_estimates'),('matching_by_event','matching_by_event'),('matching_panel','matching_panel_estimates')]:pd.concat([pd.read_csv(R/f'tables/{stem}_{m}.csv')for m in PRIMARY],ignore_index=True).to_csv(R/f'tables/{dest}.csv',index=False)
 balance=[];feat=pd.read_parquet(T/'event_features.parquet')
 for kind in ['with_industry','without_industry']:
  for n in [1,2,3]:
   for c in ['logcap','logamount','ifbeta']:
    hi=feat[['event_id','code',c]].rename(columns={'code':'high_code',c:'high'});lo=feat[['event_id','code',c]].rename(columns={'code':'low_code',c:'low'});q=pairs[pairs.neighbors.eq(n)&pairs.kind.eq(kind)].merge(hi,on=['event_id','high_code'],validate='m:1').merge(lo,on=['event_id','low_code'],validate='m:1');d=q.groupby(['event_id','high_code']).agg(high=('high','first'),low=('low','mean')).reset_index();sd=feat.groupby('event_id')[c].std();d['smd']=(d.high-d.low)/d.event_id.map(sd);balance.append(dict(kind=kind,neighbors=n,feature=c,matched_high=len(d),event_equal_smd=d.groupby('event_id').smd.mean().mean(),high_mean=d.groupby('event_id').high.mean().mean(),low_mean=d.groupby('event_id').low.mean().mean()))
 pd.DataFrame(balance).to_csv(R/'tables/matching_balance.csv',index=False)

def recovery():
 f=load(T/'panel',['code','date','event_id','closed','resume','return_bp','open30_bp']);feat=pd.read_parquet(T/'event_features.parquet',columns=['event_id','code','dose','ifbeta','quintile']);f=f.merge(feat,on=['event_id','code'],how='left',validate='m:1');events=pd.read_csv(R/'tables/events.csv').set_index('event_id')
 with np.load(T/'futures_IF.npz')as z:fr=dict(zip(pd.to_datetime(z['dates'],unit='D'),np.nansum(z['returns'],axis=1)));fn=dict(zip(pd.to_datetime(z['dates'],unit='D'),np.isfinite(z['returns']).sum(1)))
 d=f[f.closed].copy();d['fut']=d.date.map(fr);d.loc[d.date.map(fn).fillna(0).lt(180),'fut']=np.nan;c=d.groupby(['event_id','code'],observed=True).agg(stock=('return_bp','sum'),stock_n=('return_bp','count'),future=('fut','sum'),future_n=('fut','count'));c['required']=c.index.get_level_values('event_id').map(events.n_closed_days);c=c[c.stock_n.eq(c.required)&c.future_n.eq(c.required)];q=f[f.resume].merge(c.reset_index(),on=['event_id','code'],validate='1:1');q['backlog']=q.ifbeta*q.future-q.stock/1e4;q=q.rename(columns={'dose':'dose0'});out=[];boots=[]
 from endpoint_prices import build as build_endpoints
 prices=build_endpoints();cal=pd.read_csv(R/'tables/events.csv',parse_dates=['end','resume']).set_index('event_id');q['end_date']=q.event_id.map(cal.end);q['resume_date']=q.event_id.map(cal.resume);end=prices[['code','date','close','hfq_factor']].rename(columns={'date':'end_date','close':'end_close','hfq_factor':'end_factor'});resume=prices[['code','date','opening','close30','close','hfq_factor']].rename(columns={'date':'resume_date','opening':'resume_open','close30':'resume_close30','close':'resume_close','hfq_factor':'resume_factor'});q=q.merge(end,on=['code','end_date'],how='left',validate='m:1').merge(resume,on=['code','resume_date'],how='left',validate='m:1');q['cross_open30_bp']=np.log(q.resume_close30*q.resume_factor/(q.end_close*q.end_factor))*1e4;q['cross_full_bp']=np.log(q.resume_close*q.resume_factor/(q.end_close*q.end_factor))*1e4
 error=np.abs(np.log(q.resume_close30/q.resume_open)*1e4-q.open30_bp);check=dict(endpoint_open30_max_abs_difference_bp=float(error.max()),comparable_rows=int(error.notna().sum()),crossday30_valid=int(q.cross_open30_bp.notna().sum()),crossday_full_valid=int(q.cross_full_bp.notna().sum()),adjustment_source=str(Q/'cn_adj_factor/full/all.parquet'),return_definition='close at closure end to resume endpoint, adjusted by dated hfq factor ratio; backlog retains preregistered intraday definition');(R/'meta/crossday_recovery_validation.json').write_text(json.dumps(check,ensure_ascii=False,indent=2));assert check['endpoint_open30_max_abs_difference_bp']<1e-7
 for metric in ['open30_bp','return_bp','cross_open30_bp','cross_full_bp']:
  for quintile in range(5):
   d=q[q.quintile.eq(quintile)].copy();d['y']=d[metric]/1e4;rows,boot=inference(d,'y',['backlog','dose0'],term='backlog',ri=False)
   for row in rows:out.append(dict(metric=metric,quintile=quintile+1,specification=('adjusted_crossday_backlog_recovery'if metric.startswith('cross_')else'intraday_backlog_recovery'),**row))
   if boot is not None:boots.append(boot);out[-len(rows)]['boot_index']=len(boots)-1
 pd.DataFrame(out).to_csv(R/'tables/reopening_backlog_estimates.csv',index=False);q.to_csv(R/'tables/reopening_backlog_sample.csv',index=False);np.savez_compressed(T/'bootstrap_reopening.npz',boot=np.array(boots))

def setup_fake(materialize=False):
 root=R/'meta/fake_config';tmp=T/'fake_work';(root/'tables').mkdir(parents=True,exist_ok=True);(root/'meta').mkdir(exist_ok=True);tmp.mkdir(exist_ok=True)
 if materialize:
  fake=pd.read_csv(R/'tables/fake_event_date_map.csv');fake=fake.rename(columns={'closed':'treated'});fake.to_csv(root/'tables/placebo_date_map.csv',index=False);shutil.copy2(R/'meta/actual_full_calendar.csv',root/'meta/actual_full_calendar.csv');shutil.copy2(T/'fake_exposures.parquet',tmp/'placebo_exposure.parquet')
 if not(tmp/'baseline').exists():(tmp/'baseline').symlink_to(T/'baseline',target_is_directory=True)
 a.ROOT=root;a.TMP=tmp;a.METRICS=PRIMARY;a.SEED=SEED
 return root,tmp

def fake_pooled(metric):
 vals=[];dates=[];dataset=ds.dataset(T/'baseline',format='parquet')
 for b in dataset.to_batches(columns=['date',metric],filter=ds.field('eligible_day')&ds.field('nb_open'),batch_size=65536,use_threads=False):
  v=b.column(1).to_numpy(zero_copy_only=False);dt=b.column(0).to_numpy(zero_copy_only=False);good=np.isfinite(v);vals.append(v[good].copy());dates.append(dt[good].copy())
 v=np.concatenate(vals);dt=np.concatenate(dates);del vals,dates;order=np.argsort(dt,kind='stable');v=v[order];dt=dt[order];del order
 ex=pd.read_csv(R/'tables/fake_event_date_map.csv',parse_dates=['freeze_date'])[['event_id','freeze_date']].drop_duplicates();out=[]
 for r in ex.itertuples():
  j=np.searchsorted(dt,np.datetime64(r.freeze_date),side='left');q=np.quantile(v[:j],[.005,.01,.99,.995])if j else np.full(4,np.nan);out.append(dict(event_id=r.event_id,metric=metric,baseline_before=r.freeze_date,n=j,q005=q[0],q01=q[1],q99=q[2],q995=q[3]))
 return out
def fake_block(block):setup_fake();return a.placebo_block(block)

def fake_prepare():
 root,tmp=setup_fake(True);rows=[]
 with cf.ProcessPoolExecutor(max_workers=4)as pool:
  for rs in pool.map(fake_pooled,PRIMARY):rows.extend(rs)
 pd.DataFrame(rows).to_csv(root/'tables/placebo_pooled_winsor_thresholds.csv',index=False);shutil.copy2(root/'tables/placebo_pooled_winsor_thresholds.csv',R/'tables/fake_pooled_winsor_thresholds.csv')
 n=int(np.ceil(len(pd.read_csv(R/'meta/stock_universe.csv'))/20))
 for start in range(0,n,24):
  with cf.ProcessPoolExecutor(max_workers=4)as pool:list(pool.map(fake_block,range(start,min(start+24,n))))
  print('FAKE_PANEL',min(start+24,n),flush=True)

def fake_metric(metric):
 root,tmp=setup_fake();f=load(tmp/'placebo_panel',['code','date','event_id','kind','treated','dose',metric,metric+'__w01',metric+'__w005']);out=[];boots=[]
 for kind,g in f.groupby('kind',observed=True):
  for variant,col in [('raw',metric),('w01',metric+'__w01'),('w005',metric+'__w005')]:
   d=g.rename(columns={'dose':'dose0','treated':'closed',col:'y'}).copy();d['closed_x']=d.closed.astype(float)*d.dose0;rr,boot=inference(d,'y',['closed_x','dose0'],ri=False);q=d.rename(columns={'closed':'treated','closed_x':'placebo_x'});ar=a.placebo_inference(q)
   for row in rr:
    if row['term']=='closed_x':
     rri=next((r for r in ar if r['term']=='placebo_x'),{});row.update(ri_p=rri.get('ri_p'),ri_B=rri.get('ri_B'),ri_method='R1 fake-calendar year/month/weekday block coefficient',ri_status=rri.get('ri_status'))
    out.append(dict(metric=metric,variant=variant,specification=kind,exposure='dose',**row))
   if boot is not None:boots.append(boot);out[-len(rr)]['boot_index']=len(boots)-1
   del d,q,rr,ar,boot;release_memory()
 pd.DataFrame(out).to_csv(R/f'tables/fake_{metric}.csv',index=False);np.savez_compressed(T/f'bootstrap_fake_{metric}.npz',boot=np.array(boots));return metric

def fake_estimate():
 context=mp.get_context('spawn');limiter=context.BoundedSemaphore(2)
 with cf.ProcessPoolExecutor(max_workers=4,max_tasks_per_child=1,mp_context=context,initializer=engine.init_worker,initargs=(limiter,))as pool:
  for m in pool.map(bounded_aux,[('fake_metric',m)for m in PRIMARY]):print('FAKE_ESTIMATED',m,flush=True)
if __name__=='__main__':globals()[sys.argv[1]]()
