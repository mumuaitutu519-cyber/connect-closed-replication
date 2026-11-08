from common import *
import shutil,datetime
if __name__=='__main__':
 assert json.loads((R/'meta/final_validation.json').read_text())['statistical_status']=='PASS';removed=[]
 for p in list(T.iterdir()):
  if p.name=='venv':continue
  if p.is_dir():shutil.rmtree(p)
  else:p.unlink()
  removed.append(str(p))
 js(R/'logs/cleanup_receipt.json',dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),removed=removed,retained='R5 final statistics, source evidence, code and small optional environment',raw_inputs_modified=False));print('284 temporary data removed')
