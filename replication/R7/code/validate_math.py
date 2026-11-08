from common import *
from inference import fit,close
from joint import fieller
from scipy.stats import t as student_t

def main():
 rng=np.random.default_rng(SEED);e=np.repeat(np.arange(21),19);tt=np.tile(np.arange(19),21);ok=rng.random(len(e))>.12;e=e[ok];tt=tt[ok];x=rng.normal(size=(len(e),3));Y=x@np.array([.2,-.4,.6])+rng.normal(size=len(e))+rng.normal(size=21)[e]+rng.normal(size=19)[tt];q=pd.DataFrame(dict(code=e,date=tt,event_id=tt//3+1,y=Y,x0=x[:,0],x1=x[:,1],x2=x[:,2]));m=fit(q,['x0','x1','x2']);F=np.column_stack([np.eye(21)[e],np.eye(19)[tt][:,1:]]);XX=np.column_stack([x,F]);b=np.linalg.lstsq(XX,Y,rcond=None)[0];err=np.max(abs(b[:3]-m['b']));assert err<1e-10;rows=[dict(check='unbalanced_FWL_vs_explicit_dummy_OLS',n=len(q),stocks=q.code.nunique(),events=q.event_id.nunique(),max_abs_error=err,status='PASS')];close(m)
 ratio,kind,lo,hi=fieller(.3,1,.01,.01,0,100);assert kind=='BOUNDED'and lo<ratio<hi;rows.append(dict(check='Fieller_bounded_contains_point',n=0,stocks=0,events=0,max_abs_error=0,status='PASS'))
 ratio,kind,lo,hi=fieller(1,.001,.01,.01,0,100);assert kind in ['TWO_RAYS','ALL_REAL'];rows.append(dict(check='Fieller_weak_denominator_keeps_unbounded_set',n=0,stocks=0,events=0,max_abs_error=0,status='PASS'));save(rows,'mathematical_validation.csv');print('MATH_PASS',flush=True)
if __name__=='__main__':main()
