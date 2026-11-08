from common import *
from estimate import load
import inference as inf

def main():
 rows=[]
 for metric,joint in [(m,False) for m in PRIMARY]+[('if_delay',True)]:
  f,mapping=load('US',False,'r1',metric,joint);col=metric+'__w01';q=f[['code','date','event_id','treated','closed','dose',col]].rename(columns={'dose':'dose0',col:'y'}).replace([np.inf,-np.inf],np.nan).dropna(subset=['dose0','y']);q['treated_x']=q.treated*q.dose0;xs=['treated_x','dose0']
  if joint:q['closed_x']=q.closed*q.dose0;xs=['treated_x','closed_x','dose0']
  q.attrs['unique_cells']=True;model=inf.fit(q,xs);tag=f'US_0_r1_{metric}_{int(joint)}';old=pd.read_csv(T/'fits'/f'{tag}.csv');old=old[old.variant.eq('w01')&old.exposure.eq('dose')]
  for term in ['treated_x','closed_x'] if joint else ['treated_x']:
   j=model['names'].index(term);b=model['b'][j];se=np.sqrt(model['V'][j,j]);r=old[old.term.eq(term)].iloc[0];be=abs(b-r.beta);seerr=abs(se-r.se);assert be<1e-9 and seerr<1e-9;rows.append(dict(metric=metric,joint=joint,term=term,n=len(q),beta_abs_error=be,se_abs_error=seerr,status='PASS'))
  if joint:
   j=model['names'].index('treated_x');k=model['names'].index('closed_x');b=model['b'][j]-model['b'][k];se=np.sqrt(model['V'][j,j]+model['V'][k,k]-2*model['V'][j,k]);r=old[old.term.eq('treated_minus_closed')].iloc[0];be=abs(b-r.beta);seerr=abs(se-r.se);assert be<1e-9 and seerr<1e-9;rows.append(dict(metric=metric,joint=joint,term='treated_minus_closed',n=len(q),beta_abs_error=be,se_abs_error=seerr,status='PASS'))
  del f,mapping,q,model;inf.CACHE.clear();release()
 save(pd.DataFrame(rows),'actual_engine_reproduction_checks.csv');print(rows)
if __name__=='__main__':main()
