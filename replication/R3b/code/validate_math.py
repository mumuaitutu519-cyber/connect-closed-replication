from common import *
from inference import fit
from scipy.stats import t as td

def main():
 rng=np.random.default_rng(SEED);rows=[]
 for duplicate in [False,True]:
  data=[]
  for e in range(17):
   for t in range(14):
    if rng.random()<.13:continue
    for rep in range(2 if duplicate and t%3==0 else 1):
     dose=rng.normal();x=dose*(t%4==0);y=.25*x+.7*dose+e*.3-t*.2+rng.normal(scale=.3);data.append((str(e),pd.Timestamp('2020-01-01')+pd.Timedelta(days=t),y,x,dose))
  q=pd.DataFrame(data,columns=['code','date','y','treated_x','dose0']);q.attrs['unique_cells']=not duplicate;m=fit(q,['treated_x','dose0']);entity=pd.get_dummies(q.code,dtype=float);date=pd.get_dummies(q.date,dtype=float);A=np.column_stack([q[['treated_x','dose0']].to_numpy(),entity.to_numpy(),date.to_numpy()]);bb=np.linalg.lstsq(A,q.y,rcond=1e-11)[0];u=q.y.to_numpy()-A@bb;bread=np.linalg.pinv(A.T@A,rcond=1e-11);S=[]
  for col in ['code','date']:
   scores=A*u[:,None];S.append(pd.DataFrame(scores).groupby(q[col].to_numpy()).sum().to_numpy())
  C=pd.DataFrame(A*u[:,None]).groupby([q.code.to_numpy(),q.date.to_numpy()]).sum().to_numpy();n=len(q);k=2;ne=q.code.nunique();nt=q.date.nunique();meat=S[0].T@S[0]*ne/(ne-1)+S[1].T@S[1]*nt/(nt-1)-C.T@C*len(C)/(len(C)-1);V=bread@meat@bread*(n-1)/(n-ne-nt-k+1);err=float(np.max(np.abs(bb[:2]-m['b'])));verr=float(np.max(np.abs(V[:2,:2]-m['V'])));assert err<1e-9 and verr<1e-9;rows.append(dict(check='FWL_and_CGM_vs_explicit_dummies',stack_duplicates=duplicate,n=n,beta_max_abs_error=err,covariance_max_abs_error=verr,status='PASS'))
 save(pd.DataFrame(rows),'linear_algebra_checks.csv');print(rows)
if __name__=='__main__':main()
