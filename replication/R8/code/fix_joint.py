from common import *
import concurrent.futures as cf,multiprocessing as mp
from analyze import quiet_job,auxiliary_job

def main():
 jobs=[]
 for v in VARIANTS:
  for m in ['if_delay','ih_delay','if_r2_now']:
   for family in ['quiet30_both','quiet40_both','quiet30_rv','quiet40_rv']:
    p=R/'tables'/f'{family}_{m}_{v}.csv';d=pd.read_csv(p)
    if 'wild_cluster_scheme'not in d or not d.loc[d.specification.ne('quiet_only_original_FE'),'wild_cluster_scheme'].eq('date_owned_nearest_event_union').all():jobs.append((m,v,family))
 ctx=mp.get_context('spawn')
 for job in jobs:
  with cf.ProcessPoolExecutor(max_workers=6,mp_context=ctx)as pool:
   for result in pool.map(quiet_job,[job]):print('JOINT_WEBB_ALIGNED',result,flush=True)
 print('JOINT_WEBB_ALIGNMENT_COMPLETE',len(jobs),flush=True)
 for v in VARIANTS:
  for m in ['if_delay','ih_delay','if_r2_now']:
   side=R/'tables'/f'table7_pooled_{m}_{v}.csv'
   if side.exists()and 'quintile_sample'in pd.read_csv(side):continue
   with cf.ProcessPoolExecutor(max_workers=6,mp_context=ctx)as pool:list(pool.map(auxiliary_job,[(m,v)]))
   print('QUINTILE_KNOWN_SUPPORT',m,v,flush=True)
if __name__=='__main__':main()
