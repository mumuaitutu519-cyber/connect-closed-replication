from common import *
import shutil,datetime
if __name__=='__main__':
 assert json.loads((R/'meta/final_validation.json').read_text())['status']=='PASS';removed=[]
 for p in T.iterdir():
  if p.name=='venv':continue
  removed.append(str(p))
  if p.is_dir():shutil.rmtree(p)
  else:p.unlink()
 (R/'logs/cleanup_receipt.json').write_text(json.dumps(dict(removed=removed,timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),raw_user_inputs_modified=False),ensure_ascii=False,indent=2));print('Removed task-owned temporary data')
