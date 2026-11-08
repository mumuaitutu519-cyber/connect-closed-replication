"""Independent explicit-dummy checks of coefficients, two-way covariance, wild refits and streamed dynamic estimation."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[k]='1'
import numpy as np,pandas as pd,json
from pathlib import Path
from estimate import fit,design_K,ROOT,SEED
from auxiliary import dynamic_fit
def main():
 rng=np.random.default_rng(SEED);S,T=17,13;ee,tt=np.indices((S,T));mask=rng.random(ee.shape)>.15;e=ee[mask];t=tt[mask];dose=rng.random(len(e))+e/5+t/20;closed=(t%4==0).astype(float);y=.37*closed*dose+rng.normal(size=S)[e]+rng.normal(size=T)[t]+rng.normal(size=len(e))*.1
 d=pd.DataFrame(dict(code=e,date=pd.to_datetime('2020-01-01')+pd.to_timedelta(t,unit='D'),dose0=dose,interaction=dose*closed,y=y));model=fit(d,'y',['interaction','dose0'],keep=True);X=np.column_stack([d.interaction,d.dose0,pd.get_dummies(d.code,drop_first=True),pd.get_dummies(d.date,drop_first=True),np.ones(len(d))]);bread=np.linalg.pinv(X.T@X);beta=np.linalg.lstsq(X,y,rcond=None)[0];u=y-X@beta;score=X*u[:,None]
 def meat(ids):
  G=len(np.unique(ids));ss=np.zeros((G,X.shape[1]));np.add.at(ss,ids,score);return ss.T@ss*G/(G-1)
 V=bread@(meat(e)+meat(t)-score.T@score*len(d)/(len(d)-1))@bread*(len(d)-1)/(len(d)-X.shape[1]);rows=[]
 def check(name,difference,tol=1e-9):rows.append(dict(check=name,pass_=bool(difference<tol),absolute_difference=float(difference),tolerance=tol))
 check('unbalanced_FE_coefficient_vs_explicit_dummy_OLS',abs(model['rows'][0]['beta']-beta[0]));check('two_way_cluster_variance_vs_full_dummy_sandwich',abs(model['rows'][0]['se']**2-V[0,0]))
 K,partial=design_K(model['d'],model['e'],model['t'],dose);bb=np.bincount(model['t'],weights=dose*model['Y']);v,den=partial;bb-=v*bb.sum()/den;z=np.array([j%4==0 for j in range(T)]);check('RI_quadratic_coefficient_vs_explicit_dummy_OLS',abs(z@bb/(z@K@z)-beta[0]))
 xp=model['X'][:,0].copy();yp=model['Y'].copy();zz=model['X'][:,1];xp-=zz*(zz@xp)/(zz@zz);yp-=zz*(zz@yp)/(zz@zz);g=t//4;weights=rng.choice(np.array([-np.sqrt(1.5),-1.,-np.sqrt(.5),np.sqrt(.5),1.,np.sqrt(1.5)]),size=len(np.unique(g)));bootstrap_from_scores=(xp@(yp*weights[g]))/(xp@xp);bootstrap_refit=np.linalg.lstsq(X,yp*weights[g],rcond=None)[0][0];check('restricted_wild_beta_vs_explicit_dummy_bootstrap_refit',abs(bootstrap_from_scores-bootstrap_refit))
 dy=d.rename(columns={'y':'unused'}).copy();dy['y']=y;dy['event_time']=t-5;dy=dy[dy.event_time.between(-5,5)].copy();names=[]
 for k in [-5,-4,-3,-2,0,1,2,3,4,5]:name=f'event_{k}';dy[name]=dy.event_time.eq(k)*dy.dose0;names.append(name)
 ordinary=fit(dy,'y',[*names,'dose0'])['rows'];stream=dynamic_fit(dy)['rows'];ordinary=pd.DataFrame(ordinary).set_index('term');stream=pd.DataFrame(stream).set_index('term');check('streamed_dynamic_beta_vs_materialized_design',np.nanmax(np.abs(ordinary.beta-stream.beta)));check('streamed_dynamic_SE_vs_materialized_design',np.nanmax(np.abs(ordinary.se-stream.se)))
 result=pd.DataFrame(rows);result.to_csv(ROOT/'logs/inference_independent_checks.csv',index=False);assert result.pass_.all(),result.to_string(index=False)
 import scipy,pyarrow
 runtime=dict(seed=SEED,workers=4,numeric_threads={k:os.environ[k] for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS')},versions=dict(numpy=np.__version__,pandas=pd.__version__,scipy=scipy.__version__,pyarrow=pyarrow.__version__),working_memory_bytes=6800000000,hard_limit_bytes=8000000000)
 try:
  from threadpoolctl import threadpool_info
  runtime['loaded_numeric_libraries']=threadpool_info();assert all(x.get('num_threads',1)==1 for x in runtime['loaded_numeric_libraries'])
 except ImportError:runtime['loaded_numeric_libraries']='threadpoolctl unavailable; environment limits recorded'
 (ROOT/'meta/runtime.json').write_text(json.dumps(runtime,indent=2));print(result.to_string(index=False))
if __name__=='__main__':main()
