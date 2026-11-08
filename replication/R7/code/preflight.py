from common import *
from estimate import read
from inference import run

def main():
 lock=json.loads((R/'meta/preregistration_lock.json').read_text());lock['estimation_started']=True;lock.setdefault('first_estimation_utc',pd.Timestamp.now(tz='UTC').isoformat());js(R/'meta/preregistration_lock.json',lock);js(R/'meta/pre_estimation_code_manifest.json',{str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest()for p in (R/'code').glob('*')if p.is_file()});checks=[]
 old2=pd.read_csv(P/'R2/tables/main_estimates.csv');old5=pd.read_csv(P/'R5/tables/all_estimates.csv')
 for metric in ['if_delay','ih_delay','if_r2_now','if_b0','if_b1','if_lag_sum']:
  d=read(['code','date','event_id','closed','dose',metric+'__w01']).rename(columns={metric+'__w01':'y'});d['closed_x']=d.closed*d.dose;r=run(d,['closed_x','dose']);old=old2 if metric in ['if_delay','ih_delay','if_lag_sum']else old5;f=old[old.metric.eq(metric)&old.variant.eq('w01')&old.specification.eq('baseline')&old.term.eq('closed_x')]
  if 'exposure'in f:f=f[f.exposure.eq('dose')]
  o=f.iloc[0]
  for col in ['beta','se','n','stocks','dates']:
   err=abs(r[col]-o[col]);checks.append(dict(metric=metric,field=col,new=r[col],reference=o[col],max_abs_error=err,n=r['n'],stocks=r['stocks'],events=r['events'],status='PASS'if err<(1e-8 if col in ['beta','se']else.1)else'FAIL'))
  save(checks,'baseline_reproduction.csv');print('PREFLIGHT',metric,r['n'],r['beta'],flush=True)
 old3=pd.read_csv(P/'R3b/tables/main_estimates.csv')
 for metric in ['if_delay','ih_delay','if_lag_sum']:
  d=read(['code','date','event_id','closed','dose',metric+'__w01'],family='US').rename(columns={metric+'__w01':'y'});d['closed_x']=d.closed*d.dose;r=run(d,['closed_x','dose']);o=old3[old3.group.eq('US')&~old3.fake&old3.window.eq('r1')&~old3.joint&old3.variant.eq('w01')&old3.exposure.eq('dose')&old3.metric.eq(metric)].iloc[0]
  for col in ['beta','se','n','stocks','dates']:
   err=abs(r[col]-o[col]);checks.append(dict(metric='US_'+metric,field=col,new=r[col],reference=o[col],max_abs_error=err,n=r['n'],stocks=r['stocks'],events=r['events'],status='PASS'if err<(1e-8 if col in ['beta','se']else.1)else'FAIL'))
  save(checks,'baseline_reproduction.csv');print('PREFLIGHT_US',metric,r['n'],r['beta'],flush=True)
 assert all(r['status']=='PASS'for r in checks),checks
if __name__=='__main__':main()
