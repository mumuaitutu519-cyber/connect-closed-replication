"""Two-way FE, two-way cluster t inference, restricted wild bootstrap and calendar RI."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[k]='1'
from pathlib import Path
import numpy as np,pandas as pd,pyarrow as pa,pyarrow.dataset as ds,concurrent.futures as cf,json,argparse,gc,hashlib,ctypes,sys
from scipy.stats import t as student_t,skew,kurtosis
pa.set_cpu_count(1);pa.set_io_thread_count(1);pa.set_memory_pool(pa.system_memory_pool())
ROOT=Path(__file__).resolve().parents[1];TMP=Path('/Volumes/Extreme SSD/T9/_tmp/266');SEED=20261110;B=9999
PRIMARY=['cs_bp','ar_bp','vr5','autocorr1','amihud','if_lag_sum','if_delay','ih_lag_sum','ih_delay','open30_bp']
EXTRA=['ln_amount','ln_volume','return_bp','rv_bp2','zero_return_share'];METRICS=PRIMARY+EXTRA
FE_CACHE={}
def demean(a,e,t,maxiter=200):
 # Exact stock/date FWL via the date Schur complement. This avoids slow alternating projections on peripheral unbalanced observations.
 a=np.asarray(a,float).copy();ns=np.bincount(e);nt=np.bincount(t);h=hashlib.sha256(memoryview(np.ascontiguousarray(e)).cast('B'));h.update(memoryview(np.ascontiguousarray(t)).cast('B'));key=h.hexdigest()
 if key not in FE_CACHE:
  A=np.zeros((len(ns),len(nt)));A[e,t]=1.;G=np.diag(nt.astype(float))-A.T@(A/ns[:,None]);FE_CACHE[key]=np.linalg.pinv(G,hermitian=True,rcond=1e-11);del A,G
 Gi=FE_CACHE[key]
 for j in range(a.shape[1]):
  mean=np.bincount(e,weights=a[:,j],minlength=len(ns))/ns;a[:,j]-=mean[e];rhs=np.bincount(t,weights=a[:,j],minlength=len(nt));coef=Gi@rhs;stock_average=np.bincount(e,weights=coef[t],minlength=len(ns))/ns;a[:,j]-=coef[t]-stock_average[e]
 return a,1
def fit(frame,y,xs,entity='code',time='date',keep=False):
 values=frame[[y,*xs]].to_numpy(float);valid=np.isfinite(values).all(1)&frame[entity].notna().to_numpy()&frame[time].notna().to_numpy();d=frame.loc[valid,[entity,time,y,*xs]];n=len(d)
 if not n:return {'rows':[],'n':0}
 e,entities=pd.factorize(d[entity],sort=True);t,dates=pd.factorize(d[time],sort=True);a,it=demean(values if valid.all() else values[valid],e,t);del values,valid;Y=a[:,0];X=a[:,1:];k=X.shape[1]
 independent=np.sqrt(np.sum(X*X,axis=0))>1e-7
 if not independent[0]:return {'rows':[dict(term=xs[0],status='NO_IDENTIFYING_VARIATION',n=n)],'n':n}
 X=X[:,independent];names=np.asarray(xs)[independent];k=len(names);bread=np.linalg.pinv(X.T@X);b=bread@(X.T@Y);u=Y-X@b
 S=np.zeros((len(entities),k));T=np.zeros((len(dates),k));cell=np.zeros((k,k))
 for j in range(k):
  score=X[:,j]*u;S[:,j]=np.bincount(e,weights=score,minlength=len(entities));T[:,j]=np.bincount(t,weights=score,minlength=len(dates))
 del score
 for start in range(0,n,65536):
  score=X[start:start+65536]*u[start:start+65536,None];cell+=score.T@score
 del score
 # A unique stock/date cell is one row, so its cluster meat is simply the score outer product.
 M=(S.T@S)*len(entities)/max(len(entities)-1,1)+(T.T@T)*len(dates)/max(len(dates)-1,1)-cell*n/max(n-1,1);correction=(n-1)/max(n-len(entities)-len(dates)-k+1,1);V=bread@M@bread*correction;variance=np.diag(V);se=np.sqrt(np.where(variance>=0,variance,np.nan));df=min(len(entities),len(dates))-1;crit=student_t.ppf(.975,df);sd=float(np.std(Y,ddof=1));rows=[]
 for j,term in enumerate(names):
  stat=b[j]/se[j] if se[j]>0 else np.nan;p=2*student_t.sf(abs(stat),df)
  rows.append(dict(term=term,beta=b[j],se=se[j],t=stat,p=p,ci_low=b[j]-crit*se[j],ci_high=b[j]+crit*se[j],df=df,n=n,stocks=len(entities),dates=len(dates),fe_iterations=it,within_y_sd=sd,effect_in_within_sd=b[j]/sd if sd>0 else np.nan,status='OK' if np.isfinite(se[j]) else 'NONPOSITIVE_TWO_WAY_VARIANCE'))
 ans=dict(rows=rows,n=n)
 if keep:ans.update(d=d,e=e,t=t,entities=entities,dates=dates,Y=Y,X=X,u=u,b=b,bread=bread,names=names)
 return ans
def design_K(d,e,t,dose):
 S=int(e.max())+1;T=int(t.max())+1;ns=np.bincount(e).astype(float);nt=np.bincount(t).astype(float);A=np.zeros((S,T));D=np.zeros((S,T));A[e,t]=1.;D[e,t]=dose
 Q=np.diag(np.bincount(t,weights=dose*dose,minlength=T))-D.T@(D/ns[:,None]);C=np.diag(np.bincount(t,weights=dose,minlength=T))-D.T@(A/ns[:,None]);G=np.diag(nt)-A.T@(A/ns[:,None]);K=Q-C@np.linalg.pinv(G,hermitian=True,rcond=1e-11)@C.T;K=(K+K.T)/2
 one=np.ones(T);v=K@one;den=float(one@v)
 if den>max(1e-8,1e-9*np.trace(K)):
  K-=np.outer(v,v)/den;partial=(v,den)
 else:partial=None
 return K,partial
def resampling_plan():
 mapping=pd.read_csv(ROOT/'tables/event_date_map.csv',parse_dates=['date']);cal=pd.read_csv(ROOT/'tables/official_calendar.csv',parse_dates=['date']);a=cal[cal.a_open].reset_index(drop=True);events=pd.read_csv(ROOT/'tables/events.csv',parse_dates=['start','end']);dates=pd.DatetimeIndex(sorted(mapping.date));index={t:i for i,t in enumerate(dates)};positions={t:i for i,t in enumerate(a.date)};normal=set(a.loc[a.nb_open.eq(True),'date']);choices=[];audit=[]
 for e in events.itertuples():
  blocks=[]
  for date in dates:
   if date not in normal or date.year!=e.start.year or date.month!=e.start.month or date.dayofweek!=e.start.dayofweek:continue
   pos=positions[date];block=a.iloc[pos:pos+e.n_closed_days].date.tolist()
   if len(block)!=e.n_closed_days or any(t not in normal or t not in index for t in block):continue
   blocks.append([index[t] for t in block])
  choices.append(blocks);audit.append(dict(event_id=e.event_id,start=e.start,length=e.n_closed_days,candidate_blocks=len(blocks)))
 pd.DataFrame(audit).to_csv(ROOT/'tables/randomization_support.csv',index=False)
 rng=np.random.default_rng(SEED);Z=[];attempts=0;target=int(cal.closed.sum());infeasible=any(not c for c in choices)
 if not infeasible:
  while len(Z)<B and attempts<B*100:
   attempts+=1;row=np.zeros(len(dates),np.uint8);good=True
   for i in rng.permutation(len(choices)):
    available=[q for q in choices[i] if not row[q].any()]
    if not available:good=False;break
    q=available[rng.integers(len(available))];row[q]=1
   if good and int(row.sum())==target:Z.append(row)
 z=np.asarray(Z,dtype=np.uint8) if Z else np.zeros((0,len(dates)),np.uint8);np.savez_compressed(ROOT/'data/resampling_plan.npz',dates=dates.to_numpy('datetime64[D]').astype('int64'),calendar=z,webb=rng.choice(np.array([-np.sqrt(1.5),-1.,-np.sqrt(.5),np.sqrt(.5),1.,np.sqrt(1.5)]),size=(B,len(events))))
 status=dict(repetitions=len(z),requested=B,attempts=attempts,events=len(events),all_events_have_candidates=not infeasible,unique_assignments=len(np.unique(z,axis=0)) if len(z) else 0,restriction='Consecutive A-share-date blocks; same year, month, starting weekday; all candidate dates verified normal northbound-open; candidate days restricted to observed main-window dates; no block overlap')
 (ROOT/'meta/resampling_status.json').write_text(json.dumps(status,indent=2));print(status)
def main_metric(metric):
 columns=['code','date','event_id','closed','dose','eligible',metric,f'{metric}__w01',f'{metric}__w005'];f=ds.dataset(TMP/'panel',format='parquet').to_table(columns=columns,use_threads=False).to_pandas(use_threads=False)
 f['code']=pd.Categorical(f.code);results=[];raw=[];distributions=[];checks=[];k_cache={}
 with np.load(ROOT/'data/resampling_plan.npz') as zz:ri_dates=zz['dates'];Z=zz['calendar'];W=zz['webb']
 for variant,col in [('raw',metric),('w01',f'{metric}__w01'),('w005',f'{metric}__w005')]:
  v=f[col].to_numpy(float);v=v[np.isfinite(v)];quant=np.quantile(v,[.001,.01,.99,.999]) if len(v) else [np.nan]*4;distributions.append(dict(metric=metric,variant=variant,n=len(v),missing=len(f)-len(v),mean=np.mean(v),sd=np.std(v,ddof=1),skew=skew(v,bias=False),excess_kurtosis=kurtosis(v,fisher=True,bias=False),zero_share=np.mean(v==0),q001=quant[0],q01=quant[1],q99=quant[2],q999=quant[3]))
  for exposure in ['dose','eligible']:
   d=f[['code','date','event_id','closed',exposure,col]].rename(columns={col:'y',exposure:'dose0'}).replace([np.inf,-np.inf],np.nan).dropna();d['interaction']=d.closed.astype(float)*d.dose0
   model=fit(d,'y',['interaction','dose0'],keep=True)
   if 'X' not in model:
    results.append(dict(metric=metric,variant=variant,exposure=exposure,**model['rows'][0]));continue
   r=model['rows'][0];X=model['X'];Y=model['Y'];xp=X[:,0].copy();yp=Y.copy()
   if X.shape[1]>1:
    z=X[:,1];den=z@z;xp-=z*(z@xp)/den;yp-=z*(z@yp)/den
   D=xp@xp;obs=model['d'];group=d.event_id.to_numpy(np.int64)-1
   # d and fit's row-preserving complete-case frame have the same order.
   assert len(group)==len(xp)
   restricted_scores=np.bincount(group,weights=xp*yp,minlength=W.shape[1]);boot=(W@restricted_scores)/D;wildp=(1+np.sum(np.abs(boot)>=abs(r['beta'])))/(len(boot)+1)
   # Exact FE quadratic form yields all 9999 permutation betas without observation-level refits.
   cachekey=(exposure,hashlib.sha256((np.isfinite(f[col].to_numpy())&np.isfinite(f[exposure].to_numpy())).tobytes()).hexdigest())
   if cachekey not in k_cache:k_cache[cachekey]=design_K(obs,model['e'],model['t'],obs.dose0.to_numpy())
   K,partial=k_cache[cachekey];bb=np.bincount(model['t'],weights=obs.dose0.to_numpy()*Y,minlength=K.shape[0])
   if partial is not None:
    vv,den=partial;bb-=vv*(bb.sum()/den)
   td=pd.DatetimeIndex(model['dates']).to_numpy('datetime64[D]').astype('int64');ix=pd.Index(ri_dates).get_indexer(td);assert (ix>=0).all();z0=d.closed.to_numpy();zt=np.bincount(model['t'],weights=z0)/np.bincount(model['t']);check=(zt@bb)/(zt@K@zt);checks.append(dict(metric=metric,variant=variant,exposure=exposure,fe_beta=r['beta'],quadratic_beta=check,abs_difference=abs(r['beta']-check)))
   if len(Z):
    z=Z[:,ix].astype(float);numer=z@bb;denom=np.einsum('ij,ij->i',z@K,z);perms=np.divide(numer,denom,out=np.full(len(z),np.nan),where=denom>1e-10);perms=perms[np.isfinite(perms)];rip=(1+np.sum(np.abs(perms)>=abs(r['beta'])))/(len(perms)+1)
   else:perms=[];rip=np.nan
   results.append(dict(metric=metric,variant=variant,exposure=exposure,**r,wild_p=wildp,wild_B=len(boot),wild_clusters=len(np.unique(group)),wild_statistic='absolute restricted-bootstrap beta; Webb six-point cluster residual weights; FE and dose nuisance refit coefficient is exact by FWL',ri_p=rip,ri_B=len(perms),ri_inference='conditional normal-day block permutation diagnostic'))
   if variant=='raw':
    slopes={};d['positive']=d.dose0.gt(0)
    for (g,c),ss in d.groupby(['positive','closed'],observed=True):raw.append(dict(metric=metric,exposure=exposure,group='positive_exposure' if g else 'zero_exposure',closed=c,n=len(ss),stocks=ss.code.nunique(),dates=ss.date.nunique(),mean=ss.y.mean(),sd=ss.y.std()))
    del ss
    for c,ss in d.groupby('closed',observed=True):
     xd=ss.dose0.to_numpy();yd=ss.y.to_numpy();cov=xd@yd-xd.sum()*yd.sum()/len(xd);den=xd@xd-xd.sum()**2/len(xd);slopes[bool(c)]=cov/den if den>0 else np.nan
    results[-1]['raw_interaction_ols']=slopes.get(True,np.nan)-slopes.get(False,np.nan);del ss,xd,yd
   del model,K,obs,d,X,Y,xp,yp,restricted_scores,boot,bb;gc.collect();pa.default_memory_pool().release_unused()
   if sys.platform=='darwin':
    fun=ctypes.CDLL(None).malloc_zone_pressure_relief;fun.argtypes=[ctypes.c_void_p,ctypes.c_size_t];fun.restype=ctypes.c_size_t;fun(None,0)
 pd.DataFrame(results).to_csv(ROOT/f'tables/main_{metric}.csv',index=False);pd.DataFrame(raw).to_csv(ROOT/f'tables/raw_means_{metric}.csv',index=False);pd.DataFrame(distributions).to_csv(ROOT/f'tables/distribution_{metric}.csv',index=False);pd.DataFrame(checks).to_csv(ROOT/f'logs/fe_quadratic_checks_{metric}.csv',index=False)
 return dict(metric=metric,rows=len(results))
def bh(values):
 p=np.asarray(values,float);out=np.full(len(p),np.nan);good=np.flatnonzero(np.isfinite(p));order=good[np.argsort(p[good])];n=len(order)
 if n:out[order]=np.minimum(1,np.minimum.accumulate((p[order]*n/np.arange(1,n+1))[::-1])[::-1])
 return out
def consolidate():
 f=pd.concat([pd.read_csv(ROOT/f'tables/main_{m}.csv') for m in METRICS],ignore_index=True);f['q_primary_family']=np.nan
 for (v,e),ix in f[f.metric.isin(PRIMARY)].groupby(['variant','exposure']).groups.items():f.loc[ix,'q_primary_family']=bh(f.loc[ix,'p'])
 f.to_csv(ROOT/'tables/main_estimates.csv',index=False)
 pd.concat([pd.read_csv(ROOT/f'tables/raw_means_{m}.csv') for m in METRICS]).to_csv(ROOT/'tables/raw_means.csv',index=False);pd.concat([pd.read_csv(ROOT/f'tables/distribution_{m}.csv') for m in METRICS]).to_csv(ROOT/'tables/distributions.csv',index=False)
 print(f[f.variant.eq('w01')][['metric','exposure','beta','se','p','wild_p','ri_p','n','stocks','dates']].to_string(index=False))
def main():
 ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['plan','main','consolidate']);a=ap.parse_args()
 if a.stage=='plan':resampling_plan()
 elif a.stage=='main':
  for start in range(0,len(METRICS),4):
   with cf.ProcessPoolExecutor(max_workers=4) as p:
    for r in p.map(main_metric,METRICS[start:start+4]):print(r,flush=True)
  consolidate()
 else:consolidate()
if __name__=='__main__':main()
