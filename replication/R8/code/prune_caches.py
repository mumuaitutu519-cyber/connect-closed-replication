from pathlib import Path
import csv,json,shutil,time
R=Path(__file__).resolve().parents[1];T=Path('/Volumes/Extreme SSD/T9/_tmp/288')
markers=list((T/'analysis_family').glob('*.json'))
assert len(markers)==len(list((T/'feature_blocks').glob('*.parquet')))>0
sums={}
for p in markers:
 for key,value in json.loads(p.read_text()).items():sums[key]=sums.get(key,0)+int(value)
with (R/'tables/family_partition_row_audit.csv').open()as f:expected={r['family']:int(float(r['n']))for r in csv.DictReader(f)}
assert sums==expected,(sums,expected)
records=[]
for name in ['panel','pool_parts']:
 p=T/name
 if p.exists():
  assert p.parent==T and not p.is_symlink();size=sum(f.stat().st_size for f in p.rglob('*')if f.is_file());shutil.rmtree(p);records.append(dict(path=str(p),bytes=size,reason='verified family partitions and frozen quantile CSVs complete'))
receipt=R/'logs/stage_resource_receipts.jsonl';rows=[json.loads(s)for s in receipt.read_text().splitlines()];cutoff=max(r['end']for r in rows)
for p in T.glob('fwl_*'):
 if p.is_dir()and not p.is_symlink()and p.stat().st_mtime<cutoff:
  size=sum(f.stat().st_size for f in p.rglob('*')if f.is_file());shutil.rmtree(p);records.append(dict(path=str(p),bytes=size,reason='orphan cache from completed or terminated stage'))
with (R/'meta/cache_pruning_receipts.jsonl').open('a')as f:f.write(json.dumps(dict(unix=time.time(),removed=records),ensure_ascii=False)+'\n')
print('PRUNED_BYTES',sum(r['bytes']for r in records),flush=True)
