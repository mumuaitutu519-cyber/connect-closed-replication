from common import *
if __name__=='__main__':
 p=R/'PREREGISTRATION_R3b.md';lock=R/'meta/preregistration_lock.json';digest=hashlib.sha256(p.read_bytes()).hexdigest()
 if lock.exists():assert json.loads(lock.read_text())['sha256']==digest
 else:js(lock,dict(sha256=digest,locked_at=pd.Timestamp.now(tz='UTC'),first_estimate_at=None,seed=SEED))
 manifest=[]
 for root in [P/'code',P/'R2/code']:
  for p in sorted(root.glob('*.py')):manifest.append(dict(path=str(p),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
 for p in [P/'meta/stock_universe.csv',P/'meta/actual_full_calendar.csv',P/'meta/eligibility_events.csv',P/'tables/official_calendar.csv',P/'tables/events.csv',P/'tables/main_estimates.csv',P/'R2/tables/main_estimates.csv',Q/'cn_hsgt/hk_hold/full/all.parquet',Q/'cn_hk_ccass/ccass_hold/full/all.parquet',Path('/Volumes/T9/期货1分钟2004~2608/CFFEX.7z')]:
  h=hashlib.sha256()
  with p.open('rb') as f:
   for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
  manifest.append(dict(path=str(p),bytes=p.stat().st_size,sha256=h.hexdigest()))
 js(R/'meta/input_manifest.json',manifest)
 for name in ['stock_universe.csv','actual_full_calendar.csv','eligibility_events.csv']:
  assert (R/'meta'/name).read_bytes()==(P/'meta'/name).read_bytes()
 print('INITIALIZED',digest)
