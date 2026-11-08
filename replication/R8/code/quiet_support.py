from common import *
import concurrent.futures as cf,multiprocessing as mp

def one(family):
 cols=['code','date','event_id','closed','dose',*[m if v=='raw'else m+'__'+v for m in ['if_delay','ih_delay','if_r2_now']for v in VARIANTS]];stats={(m,v):dict(n=0,stocks=set(),events=set(),treated_events=set(),treated_dates=set())for m in ['if_delay','ih_delay','if_r2_now']for v in VARIANTS}
 for path in sorted((T/'analysis_family'/family).glob('*.parquet')):
  for batch in pq.ParquetFile(path).iter_batches(batch_size=65536,columns=cols,use_threads=False):
   d=batch.to_pandas(use_threads=False);known=np.isfinite(d.dose)
   for (m,v),s in stats.items():
    c=m if v=='raw'else m+'__'+v;ok=known&np.isfinite(d[c]);treated=ok&d.closed;s['n']+=int(ok.sum());s['stocks'].update(d.loc[ok,'code'].unique());s['events'].update(d.loc[ok,'event_id'].unique());s['treated_events'].update(d.loc[treated,'event_id'].unique());s['treated_dates'].update(d.loc[treated,'date'].unique())
 rows=[]
 for (m,v),s in stats.items():rows.append(dict(family=family,metric=m,variant=v,n=s['n'],stocks=len(s['stocks']),events=len(s['events']),quiet_days_actual=len(s['treated_dates']),quiet_date_min=str(pd.Timestamp(min(s['treated_dates'])).date())if s['treated_dates']else'',quiet_date_max=str(pd.Timestamp(max(s['treated_dates'])).date())if s['treated_dates']else'',quiet_events_actual=len(s['treated_events']),minimum30=len(s['treated_dates'])>=30))
 return rows

def main():
 with cf.ProcessPoolExecutor(max_workers=6,mp_context=mp.get_context('spawn'))as pool:rows=[r for rr in pool.map(one,['quiet30_both','quiet40_both','quiet30_rv','quiet40_rv'])for r in rr]
 save(rows,'quiet_actual_regression_support.csv');assert all(r['minimum30']for r in rows),rows;print('QUIET_ACTUAL_MIN_DAYS',min(r['quiet_days_actual']for r in rows),flush=True)
if __name__=='__main__':main()
