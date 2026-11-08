import pyarrow.parquet as pq,zipfile
from pathlib import Path
p=Path('/Volumes/Extreme SSD/T9/codex项目/A股分钟线+日频量价/A股分钟数据/1m_price_zip/2017.zip')
with zipfile.ZipFile(p) as z:
 n=next(n for n in z.namelist() if '20170823' in n);dest=Path('/Volumes/Extreme SSD/T9/_tmp/285/probe.parquet')
 with z.open(n) as a,dest.open('wb') as b:
  import shutil;shutil.copyfileobj(a,b,1024*1024)
 f=pq.ParquetFile(dest);print(n,f.schema_arrow,f.metadata.num_rows,f.num_row_groups)
 for i in range(min(4,f.num_row_groups)):
  g=f.metadata.row_group(i);print(i,g.num_rows,[(g.column(j).path_in_schema,str(g.column(j).statistics)[:220]) for j in range(2)])
 for b in f.iter_batches(batch_size=10):print(b.to_pandas().to_string());break
 dest.unlink()
