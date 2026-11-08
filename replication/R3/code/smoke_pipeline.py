"""Isolated small execution check. No test output becomes an empirical estimate."""
from common import *
import shutil,concurrent.futures as cf
import assemble,estimate
REAL=R;ST=T/'smoke';RR=ST/'root';TT=ST/'tmp'
for p in [RR/'tables',RR/'meta',RR/'data',RR/'logs/days',TT]:p.mkdir(parents=True,exist_ok=True)
for name in ['event_date_map.csv','event_date_map_all.csv','frozen_features.csv','official_calendar.csv','fake20_support.csv']:shutil.copyfile(REAL/'tables'/name,RR/'tables'/name)
normal=set(pd.read_csv(REAL/'tables/official_calendar.csv').query('nb_open').date);real_dates=set(pd.read_csv(REAL/'tables/event_date_map.csv').query("kind=='real'").date);selected=[p.stem for p in assemble.completed_files('daily')if str(pd.Timestamp(p.stem).date())in normal&real_dates][:4];assert len(selected)==4
for ds in selected:shutil.copyfile(REAL/'logs/days'/(ds+'.json'),RR/'logs/days'/(ds+'.json'))
for k in ['daily','minute','shocks']:
 (RR/'data'/k).mkdir(exist_ok=True)
 for ds in selected:
  p=REAL/'data'/k/(ds+'.parquet')
  if p.exists():shutil.copyfile(p,RR/'data'/k/p.name)
for prod in ['IF','IH']:shutil.copyfile(T/f'futures_{prod}.npz',TT/f'futures_{prod}.npz')
assemble.R=RR;assemble.T=TT;estimate.R=RR;estimate.T=TT
assemble.save=lambda d,name:d.to_csv(RR/'tables'/name,index=False,na_rep='NA')
# Limit this four-date plumbing check to one executor thread. Production uses four processes.
class SmallPool:
 def __init__(self,*args,**kwargs):self.pool=cf.ThreadPoolExecutor(max_workers=1)
 def __enter__(self):return self.pool
 def __exit__(self,*args):self.pool.shutdown()
assemble.cf.ProcessPoolExecutor=SmallPool

if not(TT/'daily_panel.parquet').exists():assemble.daily()
assemble.flow()
for job in [('real','m1_buy_share_1m','raw','baseline',[],None),('real','m2_IF','raw','baseline',[],None),('real','m2_IF','w01','race_cumulative_7',estimate.CONTROLS,None),('real','m2_IH','raw','QFII_parallel',['qfii'],None)]:print(estimate.one(job),flush=True)
checks=pd.concat([pd.read_csv(p)for p in (RR/'tables/estimates').glob('*.csv')],ignore_index=True);reason=checks['reason'].fillna('')if 'reason'in checks else pd.Series('',index=checks.index);bad=checks[checks.status.eq('NOT_ESTIMABLE')&~reason.str.contains('NO_COMPLETE|NO_FUTURES')]
assert not len(bad),bad[['metric','reason']].to_dict('records');js(REAL/'meta/pipeline_smoke_validation.json',dict(status='PASS',fixture_dates=4,fixture_estimate_rows=len(checks),note='Isolated plumbing test; no test output enters actual empirical results.',rows=checks[['metric','term','status']].to_dict('records')));print('PIPELINE SMOKE PASS',len(checks),flush=True)
