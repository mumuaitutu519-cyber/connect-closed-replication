"""Matched panel WLS: stock/date FE, two-way clustering, event Webb resampling."""
import numpy as np,pandas as pd
from scipy.stats import t as student_t,norm
from estimate_r2 import R,B

def fit(q):
 q=q.replace([np.inf,-np.inf],np.nan).dropna(subset=['y','dose0','weight']);n=len(q)
 if n<100:return dict(status='INSUFFICIENT_MATCHED_ROWS',n=n),None
 e,stocks=pd.factorize(q.code,sort=True);t,dates=pd.factorize(q.date,sort=True);w=q.weight.to_numpy(float);y=q.y.to_numpy(float);z=q.dose0.to_numpy(float);x=q.closed.to_numpy(float)*z;a=np.column_stack([y,x,z]);we=np.bincount(e,weights=w);wt=np.bincount(t,weights=w)
 for it in range(500):
  error=0.
  for j in range(a.shape[1]):
   m=np.bincount(e,weights=w*a[:,j])/we;a[:,j]-=m[e];v=np.bincount(t,weights=w*a[:,j])/wt;a[:,j]-=v[t];error=max(error,np.max(np.abs(m)),np.max(np.abs(v)))
  if error<1e-10:break
 else:raise RuntimeError('matched weighted FE did not converge')
 Y=a[:,0];X=a[:,1:];independent=np.sqrt(np.sum(w[:,None]*X**2,axis=0))>1e-9
 if not independent[0]:return dict(status='NO_MATCHED_VARIATION',n=n),None
 X=X[:,independent];bread=np.linalg.pinv(X.T@(w[:,None]*X));b=bread@(X.T@(w*Y));u=Y-X@b;score=w[:,None]*X*u[:,None];S=np.column_stack([np.bincount(e,weights=score[:,j],minlength=len(stocks))for j in range(X.shape[1])]);D=np.column_stack([np.bincount(t,weights=score[:,j],minlength=len(dates))for j in range(X.shape[1])]);meat=S.T@S*len(stocks)/(len(stocks)-1)+D.T@D*len(dates)/(len(dates)-1)-score.T@score*n/(n-1);V=bread@meat@bread*(n-1)/(n-len(stocks)-len(dates)-X.shape[1]+1);se=np.sqrt(V[0,0])if V[0,0]>0 else np.nan;df=min(len(stocks),len(dates))-1;crit=student_t.ppf(.975,df);xp=X[:,0].copy();yp=Y.copy()
 if X.shape[1]>1:
  c=X[:,1];den=np.sum(w*c*c);xp-=c*np.sum(w*c*xp)/den;yp-=c*np.sum(w*c*yp)/den
 denom=np.sum(w*xp*xp);es=np.bincount(q.event_id.to_numpy(int)-1,weights=w*xp*yp,minlength=46)
 with np.load(R/'data/resampling_plan.npz')as z:W=z['webb']
 boot=W@es/denom;stat=b[0]/se
 return dict(status='OK'if np.isfinite(se)else'NONPOSITIVE_TWO_WAY_VARIANCE',beta=b[0],se=se,t=stat,p=2*student_t.sf(abs(stat),df),ci_low=b[0]-crit*se,ci_high=b[0]+crit*se,df=df,n=n,stocks=len(stocks),dates=len(dates),wild_clusters=q.event_id.nunique(),wild_p=(1+np.sum(np.abs(boot)>=abs(b[0])))/(B+1),wild_B=B,mde80=(crit+norm.ppf(.8))*se,fe_iterations=it+1,ri_status='MATCHING_CALENDAR_RI_NOT_DEFINED_IN_REGISTRATION'),boot

def weights(pairs):
 result=[]
 for ev,g in pairs.groupby('event_id'):
  nh=g.high_code.nunique();high=g[['high_code']].drop_duplicates().rename(columns={'high_code':'code'});high['dose0']=1.;high['weight']=.5/nh
  low=g.copy();low['weight']=.5/nh/low.n_controls;low=low.groupby('low_code').weight.sum().reset_index().rename(columns={'low_code':'code'});low['dose0']=0.;d=pd.concat([high,low],ignore_index=True);d['event_id']=ev;result.append(d)
 return pd.concat(result,ignore_index=True)
