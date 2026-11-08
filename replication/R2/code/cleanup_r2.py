from pathlib import Path
import shutil,json,datetime
R=Path(__file__).resolve().parents[1];T=Path('/Volumes/Extreme SSD/T9/_tmp/272');assert json.loads((R/'meta/final_validation.json').read_text())['status']=='PASS';removed=[]
for p in list(T.iterdir()):
 if p.name=='venv':continue
 if p.is_dir():shutil.rmtree(p)
 else:p.unlink()
 removed.append(str(p))
(R/'logs/cleanup_receipt.json').write_text(json.dumps(dict(completed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),removed=removed,retained='final statistics, source receipts and code; optional Python environment only',raw_inputs='unchanged; no raw archive copied or removed'),ensure_ascii=False,indent=2));print('Task-owned large intermediate files removed')
