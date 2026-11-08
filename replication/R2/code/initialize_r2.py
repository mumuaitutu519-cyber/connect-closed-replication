from pathlib import Path
import pandas as pd,json,hashlib,datetime
R=Path(__file__).resolve().parents[1];T=Path('/Volumes/Extreme SSD/T9/_tmp/272');T.mkdir(parents=True,exist_ok=True);(R/'data').mkdir(exist_ok=True)
lock=json.loads((R/'meta/preregistration_lock.json').read_text());assert lock['sha256']==hashlib.sha256((R/'PREREGISTRATION_R2.md').read_bytes()).hexdigest()
# R1 exposure CSV is the frozen controlling source; no fresh eligibility download.
d=pd.read_csv(R.parent/'tables/exposure_by_event.csv',parse_dates=['freeze_date','anchor','holding_date','available_date','first_observed_daily']);d.to_parquet(T/'exposures.parquet',index=False)
manifest=json.loads((R/'meta/r1_code_manifest.json').read_text())
for rec in manifest:assert hashlib.sha256(Path(rec['path']).read_bytes()).hexdigest()==rec['sha256'],rec['path']
print('Frozen R1 definitions and R2 registration verified',flush=True)
