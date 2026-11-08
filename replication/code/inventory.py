import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[k]='1'
from pathlib import Path
import pyarrow.parquet as pq
import json,datetime,collections
ROOT=Path(__file__).resolve().parents[1]
QDC=Path('/Volumes/Extreme SSD/QDC/data/QDCData')
def main():
 rows=[]
 for name,sub in [('stocks_1m','full'),('cn_tick','full'),('cn_hsgt','hk_hold/full'),('cn_hk_ccass','ccass_hold/full'),('cn_daily_full','full'),('cn_valuation_1d','full'),('cn_suspend','full')]:
  p=QDC/name/sub
  if not p.exists():continue
  files=sorted(p.glob('*.parquet'))
  for f in files:
   if f.stem[:4].isdigit() and int(f.stem[:4])<2016:continue
   pf=pq.ParquetFile(f)
   rows.append(dict(dataset=name,path=str(f),bytes=f.stat().st_size,rows=pf.metadata.num_rows,row_groups=pf.num_row_groups,schema=str(pf.schema_arrow)))
 (ROOT/'meta/data_inventory.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
 print('INVENTORY',len(rows))
 for dataset in sorted(set(r['dataset'] for r in rows)):
  rr=[r for r in rows if r['dataset']==dataset];print(dataset,len(rr),sum(r['rows'] for r in rr),sum(r['bytes'] for r in rr))
 # Small block reads only; summary metadata does not imply coverage at every date.
 for name in ['stocks_1m','cn_tick']:
  for year in [2017,2025,2026]:
   rr=[r for r in rows if r['dataset']==name and Path(r['path']).name.startswith(str(year))]
   if not rr:continue
   r=rr[-1];pf=pq.ParquetFile(r['path']);b=next(pf.iter_batches(batch_size=3,use_threads=False));print('SAMPLE',name,year,r['path'],b.to_pydict())
if __name__=='__main__':main()
