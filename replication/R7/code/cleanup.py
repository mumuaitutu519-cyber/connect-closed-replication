from common import *
import shutil
if __name__=='__main__':
 assert json.loads((R/'meta/final_validation.json').read_text())['status']=='PASS'
 assert str(T)=='/Volumes/Extreme SSD/T9/_tmp/287'
 size=sum(p.stat().st_size for p in T.rglob('*')if p.is_file());shutil.rmtree(T);js(R/'logs/cleanup_receipt.json',dict(path=str(T),logical_bytes_removed=size,utc=pd.Timestamp.now(tz='UTC').isoformat(),original_sources_modified=False,status='COMPLETE'))
