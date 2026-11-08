from common import *
import zipfile,shutil,pyarrow.parquet as pq,concurrent.futures as cf
sys.path.insert(0,str(R/'code/r1'))
import build_metrics as bm
RAW=Path('/Volumes/Extreme SSD/T9/codex项目/A股分钟线+日频量价/A股分钟数据/1m_price_zip')
def one(day):
 t=pd.Timestamp(day);dest=T/f'audit_{t:%Y%m%d}.parquet';member=f'{t:%Y%m%d}.parquet'
 with zipfile.ZipFile(RAW/f'{t.year}.zip') as z:
  with z.open(member) as a,dest.open('wb') as b:shutil.copyfileobj(a,b,1024*1024)
 frames=[]
 for b in pq.ParquetFile(dest).iter_batches(batch_size=32768,columns=['code','trade_time','open','high','low','close','vol','amount'],use_threads=False):
  d=b.to_pandas(use_threads=False);d=d[d.code.eq('000001.SZ')].copy()
  if len(d):frames.append(d)
 d=pd.concat(frames,ignore_index=True);d['symbol']='000001.XSHE';d['ts']=pd.to_datetime(d.trade_time).astype('datetime64[ms]').astype('int64')-8*3600000;d=d.rename(columns={'vol':'volume'});original=bm.metrics(d,['000001.XSHE']).iloc[0];new=pd.read_parquet(T/'daily'/member);new=new[new.code.eq('000001.SZ')].iloc[0];dest.unlink();out=dict(date=day,code='000001.SZ',status='PASS')
 for metric in ['if_delay','ih_delay','amount','valid_minutes']:
  err=float(abs(original[metric]-new[metric]));out[metric+'_abs_error']=err;assert err<1e-9,(day,metric,err)
 # Independently reconstruct all eight 30-minute regressions for the sampled stock.
 bars=d.copy();bars['minute']=((bars.ts+8*3600000)//60000)%1440;bars=bars.set_index('minute');cc=bars.close.astype(float);oo=bars.open.astype(float);rr=[]
 for minute in list(range(571,691))+list(range(781,901)):
  if minute==571:den=oo.get(570,oo.get(571,np.nan))
  elif minute==781:den=oo.get(781,np.nan)
  else:den=cc.get(minute-1,np.nan)
  rr.append(np.log(cc.get(minute,np.nan)/den))
 rr=np.asarray(rr,float);ss=pd.read_parquet(T/'segments'/member);ss=ss[ss.code.eq('000001.SZ')].set_index('segment');errors=[]
 for product in ['IF','IH']:
  with np.load(T/f'futures_{product}.npz') as z:
   ii=np.flatnonzero(z['dates']==np.datetime64(day,'D').astype('int64'));ff=z['returns'][ii[0]] if len(ii) else np.full(240,np.nan)
  for j in range(8):
   v=ff[j*30:(j+1)*30];y=rr[j*30+5:(j+1)*30];x=np.column_stack([np.ones(25),v[5:],*[v[5-k:30-k] for k in range(1,6)]]);keep=np.isfinite(y)&np.isfinite(x).all(1);x=x[keep];y=y[keep];value=np.nan
   if len(y)>=20 and np.linalg.matrix_rank(x)==7:
    sst=((y-y.mean())**2).sum();b=np.linalg.lstsq(x,y,rcond=None)[0];b0=np.linalg.lstsq(x[:,:2],y,rcond=None)[0]
    if sst>0:
     r2=1-((y-x@b)**2).sum()/sst;r20=1-((y-x[:,:2]@b0)**2).sum()/sst
     if r2>1e-10:value=1-r20/r2
   actual=ss.loc[j,product.lower()+'_delay'];assert (np.isnan(value) and np.isnan(actual)) or abs(value-actual)<1e-8,(day,product,j,value,actual)
   if np.isfinite(value):errors.append(abs(value-actual))
 out['segment_regressions_checked']=16;out['segment_max_abs_error']=float(max(errors)) if errors else 0.;return out
if __name__=='__main__':
 from audit_source_scales import main as audit_scales
 audit_scales()
 with cf.ProcessPoolExecutor(max_workers=4) as pool:r=list(pool.map(one,['2017-01-03','2017-08-23','2019-07-31','2020-08-19']))
 save(pd.DataFrame(r),R/'logs/original_formula_checks.csv');print(r)
