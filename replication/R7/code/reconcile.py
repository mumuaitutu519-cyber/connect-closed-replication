from common import *
from estimate import one_spec
from inference import bh
import concurrent.futures as cf,multiprocessing as mp

def main():
 for v in VARIANTS:
  for m in ['if_delay','ih_delay','if_r2_now','if_b0','if_b1','if_lag_sum','if_total_beta']:
   path=R/'tables'/f'fit_{m}_{v}.csv';d=pd.read_csv(path);mask=d.family.eq('US')&d.specification.eq('full_control_no_AH');timing=d.loc[mask,'ah_timing']if'ah_timing'in d else pd.Series(['old'])
   if len(timing)!=1 or not timing.eq('event_start_R2').fillna(False).all():
    with cf.ProcessPoolExecutor(max_workers=4,mp_context=mp.get_context('spawn'))as pool:rows=list(pool.map(one_spec,[(m,v,'US','full_control_no_AH',RACE+HK,'noAH')]))[0]
    d=pd.concat([d.loc[~mask],pd.DataFrame(rows)],ignore_index=True)
    for family,ix in d.groupby('family').groups.items():
     b=d.loc[ix];base=b[b.specification.eq('baseline')&b.term.eq('closed_x')].beta
     if len(base):d.loc[ix,'retention_vs_full_baseline']=d.loc[ix,'beta']/base.iloc[0]
    save(d,path.name)
 out=pd.concat([pd.read_csv(p)for p in(R/'tables').glob('fit_*.csv')],ignore_index=True)
 baselines=out[out.term.eq('closed_x')&out.specification.isin(['baseline','HKOnly_baseline','Shared_baseline'])].set_index(['metric','variant','family','specification']).beta.to_dict()
 def retained(row):
  if row.term!='closed_x':return np.nan
  reference='HKOnly_baseline'if row.specification.startswith('HKOnly_')else'Shared_baseline'if row.specification.startswith('Shared_')else'baseline'
  denominator=baselines.get((row.metric,row.variant,row.family,reference),np.nan)
  return row.beta/denominator if denominator else np.nan
 out['retention_vs_original_group']=out.apply(retained,axis=1);out['q_BH_seven']=out.groupby(['family','specification','variant','term']).p.transform(bh);save(out,'main_estimates.csv');print('RECONCILED_AH_TIMING',flush=True)
if __name__=='__main__':main()
