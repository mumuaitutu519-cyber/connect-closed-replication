"""Actual four-specification regression equality after memory-only column projection."""
from common import *
from estimate import one
import concurrent.futures as cf,threading

def main():
 references=sorted((R/'meta/memory_pruning_reference').glob('*.csv'));assert len(references)==4
 jobs=[]
 for path in references:
  ref=pd.read_csv(path);spec=ref.specification.iloc[0];jobs.append(('real','m1_buy_share_1m','raw',spec,['qfii']if spec=='QFII_parallel'else [],None));(R/'tables/estimates'/path.name).unlink(missing_ok=True)
 stop=threading.Event();threading.Thread(target=watch,args=(stop,),daemon=True).start()
 try:
  with cf.ProcessPoolExecutor(max_workers=4,max_tasks_per_child=1)as pool:list(pool.map(one,jobs))
 finally:stop.set()
 for path in references:pd.testing.assert_frame_equal(pd.read_csv(path),pd.read_csv(R/'tables/estimates'/path.name),check_exact=True)
 js(R/'meta/column_pruning_validation.json',dict(status='PASS',specifications=[j[3]for j in jobs],all_record_fields_exact=True,includes_all_beta_SE_CI_CGM_and_9999_wild_fields=True,statistical_change=False,first_estimate_at=json.loads((R/'meta/preregistration_lock.json').read_text())['first_estimate_at'],checked_at=pd.Timestamp.now(tz='UTC')));print('PASS four actual fits; all fields identical',flush=True)
if __name__=='__main__':main()
