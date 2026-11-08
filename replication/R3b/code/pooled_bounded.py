from common import *
import subprocess,concurrent.futures as cf,multiprocessing as mp
LIMIT=None
def init(lim):
 global LIMIT
 LIMIT=lim
def safe_pooled(metric):
 with LIMIT:
  ans=pooled(metric);release();return ans

def pooled(metric):
 dest=T/f'pooled_{metric}.csv'
 if dest.exists():return pd.read_csv(dest,parse_dates=['freeze_date']).to_dict('records')
 dd=[];vv=[]
 for p in sorted((T/'history').glob('*.parquet')):
  pf=pq.ParquetFile(p)
  for b in pf.iter_batches(batch_size=65536,columns=['date','eligible_day','nb_open',metric],use_threads=False):
   z=b.to_pandas(use_threads=False);good=z.eligible_day.to_numpy()&z.nb_open.to_numpy()&np.isfinite(z[metric].to_numpy());dd.append(z.date.to_numpy('datetime64[D]').astype(np.int32)[good].copy());vv.append(z[metric].to_numpy(float)[good].copy())
  pf.close()
 dates=np.concatenate(dd);v=np.concatenate(vv);del dd,vv;release();freezes=np.sort(pd.read_csv(R/'tables/freezes.csv',parse_dates=['freeze_date']).freeze_date.unique()).astype('datetime64[D]').astype(np.int32);inp=T/f'quantile_{metric}.bin';out=inp.with_suffix('.csv')
 with inp.open('wb') as f:np.array([len(v),len(freezes)],np.uint64).tofile(f);dates.astype(np.int32).tofile(f);v.astype(np.float64).tofile(f);freezes.tofile(f)
 subprocess.run([str(T/'exact_quantiles'),str(inp),str(out)],check=True);ans=pd.read_csv(out);checks=[]
 # Independently verify every twentieth freeze plus endpoints against original np.quantile interpolation.
 for i in sorted(set([0,len(freezes)-1,*range(0,len(freezes),20)])):
  values=v[dates<freezes[i]];expected=np.quantile(values,[.005,.01,.99,.995]) if len(values) else np.full(4,np.nan);actual=ans.loc[i,['q005','q01','q99','q995']].to_numpy(float);assert np.allclose(expected,actual,atol=1e-12,rtol=1e-12,equal_nan=True);checks.append(dict(metric=metric,freeze_day=int(freezes[i]),n=len(values),max_abs_error=float(np.nanmax(abs(expected-actual))) if len(values) else np.nan,status='PASS'))
 pd.DataFrame(checks).to_csv(T/f'quantile_checks_{metric}.csv',index=False);ans['freeze_date']=pd.to_datetime(ans.freeze_day,unit='D');ans['metric']=metric;ans.drop(columns='freeze_day').to_csv(dest,index=False);inp.unlink();out.unlink();print('POOLED',metric,len(ans),len(v),flush=True);return ans.drop(columns='freeze_day').to_dict('records')

def main():
 subprocess.run(['c++','-O3','-std=c++17',str(R/'code/exact_quantiles.cpp'),'-o',str(T/'exact_quantiles')],check=True)
 records=[]
 # Recycle the process after each full-history metric; cached completed metrics survive retries.
 for metric in PRIMARY:
  cached=T/f'pooled_{metric}.csv'
  if cached.exists():records.extend(pd.read_csv(cached,parse_dates=['freeze_date']).to_dict('records'));continue
  with cf.ProcessPoolExecutor(max_workers=4) as pool:records.extend(r for rr in pool.map(pooled,[metric]) for r in rr)
 save(pd.DataFrame(records),'pooled_winsor_thresholds.csv');save(pd.concat([pd.read_csv(T/f'quantile_checks_{m}.csv') for m in PRIMARY]),'pooled_quantile_checks.csv')
if __name__=='__main__':main()
