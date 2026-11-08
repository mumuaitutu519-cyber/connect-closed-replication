from common import *
from infer import fit,infer

def main():
 sys.path.insert(0,str(P/'code'));import estimate as original
 rng=np.random.default_rng(SEED);nstock=80;ndate=45;e,t=np.meshgrid(np.arange(nstock),np.arange(ndate),indexing='ij');e=e.ravel();t=t.ravel();keep=rng.random(len(e))>.12;e=e[keep];t=t[keep];dose=rng.random(nstock)[e]+.01*(t//10);cl=(t%11==0).astype(float);q=pd.DataFrame(dict(code=e.astype(str),date=pd.Timestamp('2020-01-01')+pd.to_timedelta(t,unit='D'),event_id=1+t//3,closed=cl,dose0=dose,closed_x=cl*dose,c1=rng.normal(size=len(e)),c2=cl*rng.normal(size=len(e))));q['y']=.02*q.closed_x+.1*q.c1+rng.normal(size=len(e))+.05*e+.01*t;xs=['closed_x','dose0','c1','c2'];a=fit(q,xs);b=original.fit(q,'y',xs,keep=True);err=[]
 for j,k in enumerate(a['names']):
  r=next(x for x in b['rows']if x['term']==k);err +=[dict(check='beta_'+k,abs_error=abs(a['b'][j]-r['beta'])),dict(check='se_'+k,abs_error=abs(np.sqrt(a['V'][j,j])-r['se']))]
 for x in err:x.update(n=len(q),stocks=q.code.nunique(),events=q.event_id.nunique(),status='PASS'if x['abs_error']<1e-9 else'FAIL')
 assert all(x['status']=='PASS'for x in err);save(pd.DataFrame(err),'numerical_adapter_vs_266_checks.csv');print('MATH_PASS',max(x['abs_error']for x in err),flush=True)
if __name__=='__main__':main()
