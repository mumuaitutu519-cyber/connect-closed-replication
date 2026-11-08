"""Exact sufficient-statistic two-way FE for stock-day cells with repeated minutes.
CGM intersection clusters are STOCK-DATE, not individual minutes.
"""
from common import *
from scipy import stats,linalg
B=9999
WEBB=np.array([-np.sqrt(1.5),-1.,-np.sqrt(.5),np.sqrt(.5),1.,np.sqrt(1.5)])
def sums(v,index,n):
 if v.ndim==1:return np.bincount(index,weights=v,minlength=n)
 return np.column_stack([np.bincount(index,weights=v[:,j],minlength=n)for j in range(v.shape[1])])
def fit(f,G,H,targets,moments,seed=SEED):
 # f is unique stock/date; moment(date) = n, sum(F), sum(FF'), sum_y, sum_yF, sum_y2.
 f=f.reset_index(drop=True);e,en=pd.factorize(f.code,sort=True);t,dt=pd.factorize(f.date,sort=True);S=len(en);D=len(dt);C=len(f);p=G.shape[1];h=H.shape[1] if H is not None else 0;K=p+6*h
 if C==0 or S<2 or D<2:return [dict(term=x,status='EMPTY_OR_ONE_CLUSTER',n=0)for x in targets]
 n=f['n'].to_numpy(float);sy=f.sy.to_numpy(float);sy2=f.sy2.to_numpy(float);N=n.sum();A=np.zeros((S,D));A[e,t]=n;ns=A.sum(1);nt=A.sum(0);fs=np.array([moments[pd.Timestamp(d)][1]for d in f.date]) if h else np.empty((C,0));ff={pd.Timestamp(d):moments[pd.Timestamp(d)][2]for d in dt} if h else {};yf=f[[f'syf{j}'for j in range(6)]].to_numpy(float) if h else np.empty((C,0));Xsum=np.column_stack([G*n[:,None],(H[:,:,None]*fs[:,None,:]).reshape(C,-1)]) if h else G*n[:,None];XX=np.zeros((K,K));XY=np.zeros(K)
 for day,idx in f.groupby('date',sort=False).indices.items():
  ix=np.asarray(idx);g=G[ix];nn=n[ix][0];sg=g.T@g;XX[:p,:p]+=nn*sg;XY[:p]+=g.T@sy[ix]
  if h:
   z=H[ix];sf=fs[ix[0]];cross=(g.T@z)[:,:,None]*sf[None,None,:];XX[:p,p:]+=cross.reshape(p,-1);XX[p:,:p]+=cross.reshape(p,-1).T;XX[p:,p:]+=np.kron(z.T@z,ff[pd.Timestamp(day)]);XY[p:]+=(z.T@yf[ix]).ravel()
 XS=sums(Xsum,e,S);XD=sums(Xsum,t,D);YS=sums(sy,e,S);YD=sums(sy,t,D);Gi=np.linalg.pinv(np.diag(nt)-A.T@(A/ns[:,None]),hermitian=True,rcond=1e-10);rx=XD-A.T@(XS/ns[:,None]);ry=YD-A.T@(YS/ns);XX-=XS.T@(XS/ns[:,None])+rx.T@Gi@rx;XY-=XS.T@(YS/ns)+rx.T@Gi@ry;YY=sy2.sum()-np.sum(YS**2/ns)-ry@Gi@ry;XX=(XX+XX.T)/2
 scale=np.sqrt(np.maximum(np.diag(XX),0));ok=scale>1e-9;active=np.flatnonzero(ok)
 if not len(active):return [dict(term=x,status='NO_VARIATION',n=N)for x in targets]
 zz=XX[np.ix_(active,active)]/scale[active,None]/scale[None,active];_,rr,piv=linalg.qr(zz,pivoting=True);rank=int((np.abs(np.diag(rr))>1e-9).sum());keep=np.sort(active[piv[:rank]]);bread=np.zeros((K,K));sub=XX[np.ix_(keep,keep)];bread[np.ix_(keep,keep)]=np.linalg.pinv(sub/scale[keep,None]/scale[None,keep],hermitian=True,rcond=1e-10)/scale[keep,None]/scale[None,keep];b=bread@XY
 dx=Gi@rx;sx=XS/ns[:,None]-(A@dx)/ns[:,None];dy=Gi@ry;ssy=YS/ns-(A@dy)/ns;xfe=sx[e]+dx[t];yfe=ssy[e]+dy[t];
 def cellscores(coef):
  const=yfe-xfe@coef+G@coef[:p];theta=H@coef[p:].reshape(h,6) if h else np.empty((C,0));su=sy-n*const-(fs*theta).sum(1) if h else sy-n*const
  score=G*su[:,None]
  if h:
   fu=np.empty((C,6))
   for day,idx in f.groupby('date',sort=False).indices.items():
    ix=np.asarray(idx);fu[ix]=yf[ix]-fs[ix]*const[ix,None]-theta[ix]@ff[pd.Timestamp(day)]
   score=np.column_stack([score,(H[:,:,None]*fu[:,None,:]).reshape(C,-1)])
  score-=xfe*su[:,None];return score
 sc=cellscores(b);scs=sums(sc,e,S);scd=sums(sc,t,D);meat=S/(S-1)*(scs.T@scs)+D/(D-1)*(scd.T@scd)-C/max(1,C-1)*(sc.T@sc);V=bread@meat@bread*(N-1)/max(1,N-S-D-rank+1);df=min(S,D)-1;out=[]
 for name,Lvec in targets.items():
  ll=np.asarray(Lvec);ls=ll[active]/scale[active];projection=zz@np.linalg.pinv(zz,hermitian=True,rcond=1e-9)@ls;identified=np.linalg.norm(ls-projection)<=1e-6*max(1e-12,np.linalg.norm(ls)) and np.all(abs(ll[~ok])<1e-12);effect=float(ll@b);var=float(ll@V@ll);se=np.sqrt(var) if var>0 else np.nan;v=float(ll@bread@ll);status='OK' if np.isfinite(se) else 'NONPOSITIVE_TWO_WAY_VARIANCE';r=dict(term=name,beta=effect,se=se,t=effect/se,p=2*stats.t.sf(abs(effect/se),df),ci_low=effect-stats.t.ppf(.975,df)*se,ci_high=effect+stats.t.ppf(.975,df)*se,n=int(N),cells=C,stocks=S,dates=D,rank=rank,k=K,df=df,status=status,within_r2=float(b@XY/YY) if YY>0 else np.nan,mde80=(stats.t.ppf(.975,df)+stats.norm.ppf(.8))*se)
  if v<=1e-18 or not identified:r.update(status='NOT_IDENTIFIED',beta=np.nan,se=np.nan,t=np.nan,p=np.nan,ci_low=np.nan,ci_high=np.nan,mde80=np.nan,wild_p=np.nan,event_wild_p=np.nan);out.append(r);continue
  if name.startswith('individual_'):out.append(r);continue
  restricted=b-(bread@ll)*(effect/v);rs=cellscores(restricted)@(bread@ll)
  for cluster,label in [('treatment_date','wild'),('event_id','event_wild')]:
   codes,groups=pd.factorize(f[cluster],sort=True);sg=sums(rs,codes,len(groups));rng=np.random.default_rng(seed);boot=np.empty(B)
   for start in range(0,B,1000):boot[start:start+1000]=(rng.choice(WEBB,size=(min(1000,B-start),len(groups)))@sg)
   r[label+'_p']=(1+np.sum(abs(boot)>=abs(effect)))/(B+1);r[label+'_clusters']=len(groups)
  r['wild_B']=B;out.append(r)
 return out
