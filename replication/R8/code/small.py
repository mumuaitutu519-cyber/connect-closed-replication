from common import *
import subprocess
if __name__=='__main__':
 subprocess.run([sys.executable,str(R/'code/fix_joint.py')],check=True)
 subprocess.run([sys.executable,str(R/'code/quiet_support.py')],check=True)
 if not (R/'tables/pooled_horizon_calendar_RI.csv').exists():
  subprocess.run([sys.executable,str(R/'code/pooled_ri.py')],check=True)
 for name in ['sellonly','weather']:
  subprocess.run([sys.executable,str(R/'code'/f'{name}.py')],check=True)
 # Combine placebo results and event tests using actual completed tables.
 rows=[pd.read_csv(R/'tables'/f'{name}_webb.csv')for name in ['weather','sellonly']]
 tests=[pd.read_csv(R/'tables'/f'{name}_event_tests.csv')for name in ['weather','sellonly']]
 for p in sorted((R/'tables').glob('quiet*_event.csv')):tests.append(pd.read_csv(p))
 for p in sorted((R/'tables').glob('quiet*.csv')):
  if p.stem.endswith(('_event','_contrasts'))or p.stem in ['quiet_classification','quiet_definition_support']:continue
  d=pd.read_csv(p)
  if 'specification'in d:d=d[d.specification.eq('quiet_only_original_FE')].copy();d['group']=d.family;rows.append(d)
 a=pd.concat(rows,ignore_index=True);b=pd.concat(tests,ignore_index=True);b['test_observations']=b.events;b['test_df']=b.events-1;b['sign_trials']=b.positive+b.negative
 from inference import bh
 for d in [a,b]:
  for p in ['p','wild_p','event_t_p','sign_p']:
   if p in d:d['BH_'+p]=d.groupby(['group','variant'],dropna=False)[p].transform(bh)
 save(a,'small_sample_webb_all.csv');save(b,'small_sample_event_tests_all.csv')
