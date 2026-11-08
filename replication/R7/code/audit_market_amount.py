from common import *
import zipfile,shutil
if __name__=='__main__':
 path=Path('/Volumes/Extreme SSD/T9/codex项目/A股分钟线+日频量价/A股分钟数据/1m_price_zip/2023.zip');temp=T/'amount_audit.parquet'
 with zipfile.ZipFile(path)as z,z.open('20230605.parquet')as a,temp.open('wb')as b:shutil.copyfileobj(a,b,1024*1024)
 codes=set();rows=[]
 for batch in pq.ParquetFile(temp).iter_batches(batch_size=65536,columns=['code','amount'],use_threads=False):
  d=batch.to_pandas(use_threads=False);codes.update(d.code.unique());a=d.code.str.match(r'^(?:60\d{4}|688\d{3})\.SH$|^(?:00[0-3]\d{3}|30[01]\d{3})\.SZ$');rows.append(dict(A_amount=float(d.loc[a,'amount'].sum()),other_amount=float(d.loc[~a,'amount'].sum())))
 temp.unlink();js(R/'meta/market_amount_universe_audit.json',dict(date='2023-06-05',codes=len(codes),other_codes=sorted(c for c in codes if not __import__('re').match(r'^(?:60\d{4}|688\d{3})\.SH$|^(?:00[0-3]\d{3}|30[01]\d{3})\.SZ$',c)),A_amount=sum(r['A_amount']for r in rows),other_amount=sum(r['other_amount']for r in rows)));print('AMOUNT_AUDIT',len(codes),sum(r['other_amount']for r in rows),flush=True)
