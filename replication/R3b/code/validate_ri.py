from common import *
import inference as inf

def main():
 rng=np.random.default_rng(SEED);records=[]
 for stacked in [False,True]:
  rows=[]
  for e in range(12):
   for day in range(12):
    if rng.random()<.1:continue
    for rep in range(2 if stacked and day%3==0 else 1):
     d=rng.normal();treated=int(day in [2,7,10]);closed=int(day in [0,6]);y=e*.3+day*.2+.3*d*treated+.1*d*closed+.4*d+rng.normal(scale=.2);rows.append((str(e),pd.Timestamp('2020-01-01')+pd.Timedelta(days=day),1+day//6,treated,closed,d,y))
  q=pd.DataFrame(rows,columns=['code','date','event_id','treated','closed','dose0','y']);q['treated_x']=q.dose0*q.treated;q['closed_x']=q.dose0*q.closed;model=inf.fit(q,['treated_x','closed_x','dose0']);dates=pd.DatetimeIndex(sorted(q.date.unique()));Z=rng.integers(0,2,(49,len(dates)),dtype=np.uint8);Z[0]=q.groupby('date').treated.first().reindex(dates);inf.B=49;W=([1,2],rng.choice([-1,1],(49,2)));r,boot=inf.infer(q,model,'treated_x',W,(dates,Z,dict(ri_status='SYNTHETIC_VALIDATION')))
  perms=[]
  for z in Z:
   qq=q.copy();qq['treated_x']=qq.dose0*qq.date.map(dict(zip(dates,z)));m=inf.fit(qq,['treated_x','closed_x','dose0']);j=m['names'].index('treated_x');perms.append(m['b'][j])
  expected=(1+np.sum(np.abs(perms)>=abs(r['beta'])))/50;assert abs(expected-r['ri_p'])<=.0200000001 # observed draw may straddle equality by floating point
  assert r['ri_beta_abs_error']<1e-9;records.append(dict(check='conditional_calendar_FWL_vs_explicit_refits',stacked=stacked,B=49,ri_p_quadratic=r['ri_p'],ri_p_direct=expected,observed_beta_error=r['ri_beta_abs_error'],status='PASS'))
 save(pd.DataFrame(records),'RI_quadratic_checks.csv');print(records)
if __name__=='__main__':main()
