from common import *
import ast,concurrent.futures as cf,multiprocessing as mp

def digest(value):
 p=Path(value)
 with p.open('rb')as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
 return dict(path=str(p),bytes=p.stat().st_size,mtime_ns=p.stat().st_mtime_ns,sha256=sha,n=np.nan,stocks=np.nan,events=np.nan)

def main():
 sources={R/'PREREGISTRATION_R8.md',R/'meta/PREREGISTRATION_R8_POOLED_RI_ADDENDUM.md',P/'R2/tables/frozen_features_by_event.csv',P/'R4/tables/frozen_features_by_event.csv',P/'R7/data/frozen_US_controls.parquet',P/'R7/tables/us_index_source_status.csv',P/'R2/tables/historical_membership_receipts.csv',Q/'cn_st/full/all.parquet',Q/'cn_hsgt/hk_hold/full/all.parquet',Path('/Volumes/T9/期货1分钟2004~2608/CFFEX.7z')}
 receipts=pd.read_csv(R/'tables/minute_day_receipts.csv')
 for cell in receipts.source:
  for source in ast.literal_eval(cell):sources.add(Path(source.split('!')[0]))
 for folder,patterns in [(P/'tables',['events.csv','event_date_map.csv','official_calendar.csv']), (P/'meta',['stock_universe.csv','actual_full_calendar.csv','eligibility_events.csv']), (P/'R5/tables',['F_event_classification.csv']), (P/'R6/tables',['events.csv','event_map.csv','exposure_window_freeze_by_event.csv','pooled_winsor_thresholds.csv']), (P/'R6',['typhoon_calendar.csv']), (P.parent/'nb_sellonly/tables',['exposure_by_event.csv','distribution_if_delay.csv','distribution_ih_delay.csv']), (P.parent/'nb_sellonly/meta',['sample_counts.json','trading_calendar.csv'])]:
  for pattern in patterns:sources.add(folder/pattern)
 for folder in [P/'code',P/'R7/code',P/'R6/code',P.parent/'nb_sellonly/code']:
  for p in folder.glob('*.py'):sources.add(p)
 missing=[str(p)for p in sources if not p.exists()]
 assert not missing,missing
 sources=sorted(str(p)for p in sources);ctx=mp.get_context('spawn')
 with cf.ProcessPoolExecutor(max_workers=6,mp_context=ctx)as pool:rows=list(pool.map(digest,sources))
 save(rows,'full_input_source_manifest.csv');print('INPUT_HASHES',len(rows),sum(x['bytes']for x in rows),flush=True)
if __name__=='__main__':main()
