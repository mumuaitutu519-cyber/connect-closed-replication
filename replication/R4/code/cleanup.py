from common import *
import shutil
def main():
 assert json.loads((R/'meta/validation.json').read_text())['status']=='PASS';assert (R/'RESULTS_FOR_CLAUDE.md').exists();size=sum(p.stat().st_size for p in T.rglob('*') if p.is_file());shutil.rmtree(T);js(R/'logs/cleanup_receipt.json',dict(path=str(T),logical_bytes_removed=size,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),status='COMPLETE',original_sources_modified=False))
if __name__=='__main__':main()
