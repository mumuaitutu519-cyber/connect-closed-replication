"""Remove only task-owned large intermediates; preserve final tables and raw input archives."""
from pathlib import Path
import shutil,json,datetime
ROOT=Path(__file__).resolve().parents[1];TMP=Path('/Volumes/Extreme SSD/T9/_tmp/266')
def main():
 validation=json.loads((ROOT/'meta/final_validation.json').read_text());assert validation['status']=='PASS'
 removed=[]
 for p in list(TMP.iterdir()):
  # Preserve the small execution environment so the one-click entrypoint remains immediately usable.
  if p.name=='venv':continue
  if p.is_dir():shutil.rmtree(p)
  else:p.unlink()
  removed.append(str(p))
 (ROOT/'logs/cleanup_receipt.json').write_text(json.dumps(dict(completed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),removed=removed,retained='Python environment only; no extracted data, large caches or intermediate panels retained',raw_zip_downloads=0,raw_archive_move='Not applicable: no raw ZIP was downloaded; existing user ZIP/7z inputs remain read-only'),ensure_ascii=False,indent=2))
 print('Cleaned task-owned extracted data and large intermediates.')
if __name__=='__main__':main()
