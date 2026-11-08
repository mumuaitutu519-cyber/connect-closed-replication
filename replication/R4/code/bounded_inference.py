"""Memory-bounded execution of the unchanged R1/R2 FWL, CGM, Webb and RI algebra.

Columns are demeaned by the original R1 routine and retained on disk; all
cross-products/scores are accumulated in bounded row blocks. No estimator,
small-sample correction, resampling draw or tested statistic is changed.
"""
from common import *
import tempfile
from scipy.stats import t as student_t,norm
def inference(d,y,xs,term='closed_x',ri_dose='dose0',engine=None):
 assert not d.duplicated(['code','date']).any()
 good=np.ones(len(d),dtype=bool)
 for c in [y,*xs]:good&=np.isfinite(d[c].to_numpy(dtype=float,na_value=np.nan))
 if not good.all():d=d.loc[good].reset_index(drop=True)
 n=len(d)
 if n<2:return [dict(term=term,status='INSUFFICIENT_COMPLETE_CASES',n=n)],None
 e,entities=pd.factorize(d.code,sort=True);t,dates=pd.factorize(d.date,sort=True);ns=len(entities);nt=len(dates);k=len(xs);tmpdir=Path(tempfile.mkdtemp(prefix='fwl_',dir=T));mm=np.memmap(tmpdir/'within.bin',dtype='float64',mode='w+',shape=(k+1,n));demean=engine.ORIG_DEMEAN
 try:
  for j,c in enumerate([y,*xs]):
   a,_=demean(d[c].to_numpy(float).reshape(-1,1),e,t);mm[j]=a[:,0];del a
  mm.flush();cross=np.zeros((k+1,k+1))
  for start in range(0,n,32768):
   q=np.array(mm[:,start:start+32768],order='C');cross+=q@q.T
  norms=np.sqrt(np.maximum(np.diag(cross)[1:],0));keep=np.flatnonzero(norms>1e-7);names=[xs[i] for i in keep];indices=keep+1
  if term not in names:return [dict(term=term,status='NO_IDENTIFYING_VARIATION',n=n)],None
  XtX=cross[np.ix_(indices,indices)];Xty=cross[indices,0];bread=np.linalg.pinv(XtX);b=bread@Xty;kk=len(keep);Y=np.array(mm[0]);u=Y.copy()
  for start in range(0,n,32768):
   q=np.array(mm[indices,start:start+32768]);u[start:start+len(q.T)]-=b@q
  S=np.zeros((ns,kk));D=np.zeros((nt,kk));cell=np.zeros((kk,kk))
  for j,pos in enumerate(indices):
   score=np.asarray(mm[pos])*u;S[:,j]=np.bincount(e,weights=score,minlength=ns);D[:,j]=np.bincount(t,weights=score,minlength=nt)
  del score
  for start in range(0,n,32768):
   q=np.array(mm[indices,start:start+32768]).T*u[start:start+32768,None];cell+=q.T@q
  meat=(S.T@S)*ns/max(ns-1,1)+(D.T@D)*nt/max(nt-1,1)-cell*n/max(n-1,1);V=bread@meat@bread*(n-1)/max(n-ns-nt-kk+1,1);variance=np.diag(V);se=np.sqrt(np.where(variance>=0,variance,np.nan));df=min(ns,nt)-1;crit=student_t.ppf(.975,df);sd=Y.std(ddof=1);rows=[]
  for j,name in enumerate(names):
   stat=b[j]/se[j] if se[j]>0 else np.nan;rows.append(dict(term=name,beta=b[j],se=se[j],t=stat,p=2*student_t.sf(abs(stat),df),ci_low=b[j]-crit*se[j],ci_high=b[j]+crit*se[j],df=df,n=n,stocks=ns,dates=nt,fe_iterations=1,within_y_sd=sd,effect_in_within_sd=b[j]/sd if sd>0 else np.nan,status='OK' if np.isfinite(se[j]) else 'NONPOSITIVE_TWO_WAY_VARIANCE'))
  target=names.index(term);other=np.delete(np.arange(kk),target);xp=np.array(mm[indices[target]]);yp=Y.copy();zz=np.linalg.pinv(XtX[np.ix_(other,other)]) if len(other) else np.empty((0,0));cx=zz@XtX[other,target] if len(other) else np.empty(0);cy=zz@Xty[other] if len(other) else np.empty(0)
  for start in range(0,n,32768):
   q=np.array(mm[indices[other],start:start+32768]);xp[start:start+q.shape[1]]-=cx@q;yp[start:start+q.shape[1]]-=cy@q
  den=xp@xp
  if den<=max(1e-12,XtX[target,target]*1e-12):return [dict(term=term,status='TARGET_COLLINEAR_NOT_IDENTIFIED',n=n)],None
  groups=d.event_id.to_numpy(int)-1
  with np.load(R/'data/resampling_plan.npz') as z:W=z['webb'];P0=z['calendar'];ri_dates=z['dates']
  scores=np.bincount(groups,weights=xp*yp,minlength=46);boot=W@scores/den;row=rows[target];row.update(wild_p=(1+np.sum(abs(boot)>=abs(row['beta'])))/(B+1),wild_B=B,wild_clusters=len(np.unique(groups)),wild_statistic='R1 restricted Webb coefficient',within_r2=1-u@u/(Y@Y),mde80=(crit+norm.ppf(.8))*row['se'],ri_p=np.nan,ri_B=0,within_design_columns=kk,within_design_rank=int(np.linalg.matrix_rank(XtX)),inference_execution='R1/R2 algebra; original FE projection; chunked cross-products')
  dose=d[ri_dose].to_numpy(float);counts=np.bincount(e).astype(float);A=np.zeros((ns,nt));Da=np.zeros_like(A);A[e,t]=1.;Da[e,t]=dose;Qm=np.diag(np.bincount(t,weights=dose*dose,minlength=nt))-Da.T@(Da/counts[:,None]);C=np.diag(np.bincount(t,weights=dose,minlength=nt))-Da.T@(A/counts[:,None]);G=np.diag(np.bincount(t).astype(float))-A.T@(A/counts[:,None]);K=Qm-C@np.linalg.pinv(G,hermitian=True,rcond=1e-11)@C.T;del A,Da,Qm,C,G
  if len(other):
   H=np.column_stack([np.bincount(t,weights=dose*np.asarray(mm[indices[j]]),minlength=nt) for j in other]);K-=H@zz@H.T
  K=(K+K.T)/2;bb=np.bincount(t,weights=dose*yp,minlength=nt);obs=d.groupby('date',observed=True).closed.first().reindex(dates).to_numpy(float);observed_check=(obs@bb)/(obs@K@obs);row['ri_beta_abs_error']=abs(observed_check-row['beta']);assert row['ri_beta_abs_error']<1e-7,(term,row['beta'],observed_check);ix=pd.Index(ri_dates).get_indexer(pd.DatetimeIndex(dates).to_numpy('datetime64[D]').astype('int64'));assert (ix>=0).all();perms=[]
  for start in range(0,len(P0),512):
   z=P0[start:start+512,ix].astype(float);numer=z@bb;denom=np.einsum('ij,ij->i',z@K,z);perms.append(np.divide(numer,denom,out=np.full(len(z),np.nan),where=denom>1e-10))
  perms=np.concatenate(perms) if perms else np.array([]);perms=perms[np.isfinite(perms)];row['ri_p']=(1+np.sum(abs(perms)>=abs(row['beta'])))/(len(perms)+1) if len(perms) else np.nan;row['ri_B']=len(perms);row['ri_method']='R1 calendar / conditional FWL coefficient';row['sample_y_mean']=d[y].mean();row['sample_y_sd']=d[y].std();uniq=d[['event_id','code',ri_dose]].drop_duplicates();p25,p75=np.quantile(uniq[ri_dose],[.25,.75]);row.update(dose_p25=p25,dose_p75=p75,effect_iqr=row['beta']*(p75-p25),mde80_iqr=row['mde80']*(p75-p25))
  return rows,boot
 finally:
  del mm
  import shutil
  shutil.rmtree(tmpdir);engine.r1.FE_CACHE.clear();release()
