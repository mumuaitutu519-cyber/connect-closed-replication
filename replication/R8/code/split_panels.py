from common import *
import pyarrow.compute as pc,concurrent.futures as cf,multiprocessing as mp

def one(path):
 path=Path(path);marker=T/'analysis_family'/f'{path.stem}.json'
 if marker.exists():return json.loads(marker.read_text())
 pf=pq.ParquetFile(path);cols=['code','date','event_id','closed','dose','family','quintile',*RACE,*HK,*[c+'__'+v for c in HK for v in VARIANTS],*[m if v=='raw'else m+'__'+v for m in METRICS for v in VARIANTS],*[f'mom{h}_n'for h in [1,5,15,30,60]],'nextdate','next_raw','next_w01','next_w005','qfii'];cols=list(dict.fromkeys(c for c in cols if c in pf.schema_arrow.names));writers={};counts={}
 try:
  for batch in pf.iter_batches(batch_size=16384,columns=cols,use_threads=False):
   tab=pa.Table.from_batches([batch])
   for fam in pc.unique(tab.column('family')).to_pylist():
    part=tab.filter(pc.equal(tab.column('family'),fam))
    if fam.startswith('quiet'):
     keep=['code','date','event_id','closed','dose','family','quintile',*[m if v=='raw'else m+'__'+v for m in ['if_delay','ih_delay','if_r2_now']for v in VARIANTS]];part=part.select(keep)
    elif fam=='US':
     keep=['code','date','event_id','closed','dose','family','if_delay__w01',*RACE,*[c+'__w01'for c in HK]];part=part.select(keep)
    dest=T/'analysis_family'/fam;dest.mkdir(exist_ok=True)
    if fam not in writers:writers[fam]=pq.ParquetWriter(dest/path.name,part.schema,compression='zstd')
    writers[fam].write_table(part);counts[fam]=counts.get(fam,0)+len(part)
 finally:
  for w in writers.values():w.close()
 assert sum(counts.values())==pf.metadata.num_rows
 pf.close();js(marker,counts);return counts

def main():
 (T/'analysis_family').mkdir(exist_ok=True);paths=sorted((T/'panel').glob('*.parquet'));ctx=mp.get_context('spawn');rows=[]
 for first in range(0,len(paths),6):
  with cf.ProcessPoolExecutor(max_workers=6,mp_context=ctx)as pool:
   for result in pool.map(one,paths[first:first+6]):rows.append(result)
  print('FAMILY_SPLIT',min(first+6,len(paths)),'/',len(paths),flush=True)
 sums=pd.DataFrame(rows).sum();save([dict(family=k,n=int(v),stocks=np.nan,events=np.nan,status='EXACT_ROW_PARTITION')for k,v in sums.items()],'family_partition_row_audit.csv')
if __name__=='__main__':main()
