from common import *
from scipy import sparse
from scipy.stats import t as student_t,norm
# Same two-way FWL and CGM formula as 266; sparse incidence lowers peak RSS.
def fit(q,xs):
 e,entities=pd.factorize(q.code,sort=True);t,dates=pd.factorize(q.date,sort=True);ns=np.bincount(e).astype(float);nt=np.bincount(t).astype(float);A=sparse.csr_matrix((np.ones(len(e)),(e,t)),shape=(len(ns),len(nt)));G=np.diag(nt)-(A.T@A.multiply(1/ns[:,None])).toarray();Gi=np.linalg.pinv(G,hermitian=True,rcond=1e-11);a=q[['y',*xs]].to_numpy(float,copy=True)
 for j in range(a.shape[1]):
  a[:,j]-=(np.bincount(e,weights=a[:,j])/ns)[e];coef=Gi@np.bincount(t,weights=a[:,j],minlength=len(nt));av=(A@coef)/ns;a[:,j]-=coef[t]-av[e]
 Y=a[:,0];xx=a[:,1:];good=np.sqrt(np.einsum('ij,ij->j',xx,xx))>1e-7;X=xx if good.all()else xx[:,good];names=list(np.array(xs)[good]);bread=np.linalg.pinv(X.T@X);b=bread@(X.T@Y);u=Y-X@b;n,k=X.shape;S=np.zeros((len(ns),k));D=np.zeros((len(nt),k));cell=np.zeros((k,k))
 for j in range(k):
  score=X[:,j]*u;S[:,j]=np.bincount(e,weights=score,minlength=len(ns));D[:,j]=np.bincount(t,weights=score,minlength=len(nt))
 for start in range(0,n,65536):
  score=X[start:start+65536]*u[start:start+65536,None];cell+=score.T@score
 meat=S.T@S*len(ns)/max(len(ns)-1,1)+D.T@D*len(nt)/max(len(nt)-1,1)-cell*n/max(n-1,1);V=bread@meat@bread*(n-1)/max(n-len(ns)-len(nt)-k+1,1)
 return dict(Y=Y,X=X,b=b,u=u,bread=bread,V=V,names=names,e=e,t=t,entities=entities,dates=dates,ns=ns,nt=nt,A=A,Gi=Gi,n=n,df=min(len(ns),len(nt))-1)

def infer(q,model,term,W,plan=None,dose=None,actual=None):
 if term not in model['names']:return dict(term=term,status='NO_IDENTIFYING_VARIATION',n=len(q),stocks=q.code.nunique(),events=q.event_id.nunique(),dates=q.date.nunique())
 j=model['names'].index(term);X=model['X'];Y=model['Y'];other=[i for i in range(X.shape[1])if i!=j];N=X[:,other];Ni=np.linalg.pinv(N.T@N)if other else np.zeros((0,0));xp=X[:,j].copy();yp=Y.copy()
 if other:xp-=N@(Ni@(N.T@xp));yp-=N@(Ni@(N.T@yp))
 den=xp@xp;g=q.event_id.to_numpy(int)-1;scores=np.bincount(g,weights=xp*yp,minlength=46);boot=W@scores/den;b=model['b'][j];v=model['V'][j,j];se=np.sqrt(v)if v>=0 else np.nan;df=model['df'];crit=student_t.ppf(.975,df)
 row=dict(wild_scores_json=json.dumps(scores.tolist()),wild_denominator=den,term=term,beta=b,se=se,t=b/se if se>0 else np.nan,p=2*student_t.sf(abs(b/se),df)if se>0 else np.nan,ci_low=b-crit*se,ci_high=b+crit*se,n=len(q),stocks=len(model['entities']),dates=len(model['dates']),events=q.event_id.nunique(),df=df,wild_p=(1+np.sum(abs(boot)>=abs(b)))/(B+1),wild_B=B,wild_clusters=len(np.unique(g)),ri_p=np.nan,ri_B=0,mde80=(crit+norm.ppf(.8))*se,status='OK'if np.isfinite(se)else'NONPOSITIVE_TWO_WAY_VARIANCE',within_r2=1-np.sum(model['u']**2)/np.sum(Y**2))
 if plan is not None and dose is not None:
  pdates,Z=plan;e=model['e'];t=model['t'];ns=model['ns'];nt=model['nt'];A=model['A'];Gi=model['Gi'];dd=np.asarray(dose,float);D=sparse.csr_matrix((dd,(e,t)),shape=A.shape);C=np.diag(np.bincount(t,weights=dd,minlength=len(nt)))-(D.T@A.multiply(1/ns[:,None])).toarray();K=np.diag(np.bincount(t,weights=dd*dd,minlength=len(nt)))-(D.T@D.multiply(1/ns[:,None])).toarray()-C@Gi@C.T
  if other:
   H=np.column_stack([np.bincount(t,weights=dd*N[:,k],minlength=len(nt))for k in range(N.shape[1])]);K-=H@Ni@H.T
  bb=np.bincount(t,weights=dd*yp,minlength=len(nt));ix=pd.Index(pdates).get_indexer(model['dates']);assert (ix>=0).all();z=Z[:,ix].astype(float);denom=np.einsum('ij,ij->i',z@K,z);bet=np.divide(z@bb,denom,out=np.full(len(z),np.nan),where=denom>1e-10);bet=bet[np.isfinite(bet)];row.update(ri_p=(1+np.sum(abs(bet)>=abs(b)))/(len(bet)+1),ri_B=len(bet),ri_method='266/272 conditional block coefficient')
  obs=q.groupby('date',observed=True)[actual or'closed'].first().reindex(model['dates']).to_numpy(float);check=(obs@bb)/(obs@K@obs);row['ri_beta_abs_error']=abs(check-b);assert abs(check-b)<1e-7,(term,b,check)
 for c in ['beta','se','ci_low','ci_high','mde80']:row[c+'_x100']=row[c]*100
 return row

def draws():
 with np.load(T/'resampling.npz')as z:return z['webb'],(pd.to_datetime(z['dates'],unit='D'),z['calendar'])

def plan():
 # Execute the original 266 calendar algorithm, changing only seed and output destination.
 sys.path.insert(0,str(P/'code'));import estimate as r1
 for d in ['data','meta','tables']:(T/'planroot'/d).mkdir(parents=True,exist_ok=True)
 import shutil
 for f in ['event_date_map.csv','official_calendar.csv','events.csv']:shutil.copyfile(P/'tables'/f,T/'planroot/tables'/f)
 r1.ROOT=T/'planroot';r1.SEED=SEED;r1.B=B;r1.resampling_plan();shutil.copyfile(T/'planroot/data/resampling_plan.npz',T/'resampling.npz');shutil.copyfile(T/'planroot/tables/randomization_support.csv',R/'tables/randomization_support.csv');shutil.copyfile(T/'planroot/meta/resampling_status.json',R/'meta/resampling_status.json')
if __name__=='__main__':plan()
