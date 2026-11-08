"""Delete only this task's scratch files, after delivery validation, using four workers."""
from pathlib import Path
import json,concurrent.futures as cf
R=Path(__file__).resolve().parents[1];T=Path('/Volumes/Extreme SSD/T9/_tmp/282')
def remove_file(value):
 p=Path(value)
 assert p.is_relative_to(T) and 'venv'!=p.relative_to(T).parts[0]
 p.unlink(missing_ok=True)
 return 1
if __name__=='__main__':
 assert json.loads((R/'meta/final_validation.json').read_text())['status']=='PASS'
 assert str(T)=='/Volumes/Extreme SSD/T9/_tmp/282'
 tops=[p.name for p in T.iterdir() if p.name!='venv'];paths=[p for p in T.rglob('*') if p.relative_to(T).parts[0]!='venv'];files=[p for p in paths if p.is_symlink() or p.is_file()];dirs=[p for p in paths if p.is_dir() and not p.is_symlink()]
 with cf.ProcessPoolExecutor(max_workers=4) as pool:count=sum(pool.map(remove_file,[str(p) for p in files],chunksize=32))
 for p in sorted(dirs,key=lambda p:len(p.parts),reverse=True):
  try:p.rmdir()
  except FileNotFoundError:pass
 remaining=[p.name for p in T.iterdir() if p.name!='venv'];assert not remaining,remaining
 (R/'meta/cleanup.json').write_text(json.dumps(dict(success=True,workers=4,removed_top_level=tops,files_removed_this_pass=count,remaining_non_environment_files=remaining),indent=2));print('CLEANED',count,'files')
