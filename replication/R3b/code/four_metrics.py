from common import *
sys.path.insert(0,str(R/'code/r1'))
import build_metrics as bm

def four(d,codes):
 d=d.drop_duplicates(['symbol','ts'],keep='first');ts=d.ts.to_numpy(np.int64)+8*3600000;day=ts//86400000;minute=(ts//60000)%1440;slot=np.where(minute<=690,minute-570,minute-780+120);valid=((minute>=570)&(minute<=690))|((minute>=781)&(minute<=900));d=d.loc[valid];day=day[valid];slot=slot[valid];ci=pd.Categorical(d.symbol,categories=codes).codes.astype(np.int64);unique,ix=np.unique(ci*100000+day,return_inverse=True);x=np.full((len(unique),241,5),np.nan);v=d[['open','high','low','close','amount']].to_numpy(float,copy=True);bad=(v[:,0]<=0)|(v[:,3]<=0)|(v[:,1]<v[:,2])|~np.isfinite(v[:,:4]).all(1);v[bad,:]=np.nan;x[ix,slot,:]=v;op,hi,lo,cl,amt=[x[:,:,k] for k in range(5)]
 with np.errstate(divide='ignore',invalid='ignore'):
  r=np.log(cl[:,1:]/cl[:,:-1]);opening=np.where(np.isfinite(op[:,0]),op[:,0],op[:,1]);r[:,0]=np.log(cl[:,1]/opening);r[:,120]=np.log(cl[:,121]/op[:,121]);r[~np.isfinite(cl[:,1:])]=np.nan;n=np.isfinite(r).sum(1);amount=np.nansum(amt[:,1:],1);one=np.nanmax(hi[:,1:],1)<=np.nanmin(lo[:,1:],1);out=bm.future_metrics(r,unique%100000)
 f=pd.DataFrame(out);f.insert(0,'date',pd.to_datetime(unique%100000,unit='D'));f.insert(0,'code',[codes[i//100000][:6]+('.SH' if codes[i//100000].endswith('XSHG') else '.SZ') for i in unique]);f['amount']=amount;f['valid_minutes']=n;f['one_price']=one;f['raw_eligible_day']=(n>=180)&~one&(amount>0);return f

def chunk(d,codes):
 out=[]
 for i in range(0,len(codes),800):
  sub=codes[i:i+800];q=d[d.symbol.isin(sub)].copy()
  if len(q):out.append(four(q,sub))
 return pd.concat(out,ignore_index=True)
if __name__=='__main__':
 import io,zipfile
 raw=Path('/Volumes/Extreme SSD/T9/codex项目/A股分钟线+日频量价/A股分钟数据/1m_price_zip/2020.zip')
 with zipfile.ZipFile(raw) as z:pf=pq.ParquetFile(io.BytesIO(z.read('20200106.parquet')));d=pf.read().to_pandas()
 d=d[d.code.isin(pd.read_csv(R/'meta/stock_universe.csv').code.iloc[:30])].copy();d['symbol']=d.code.str[:6]+np.where(d.code.str.endswith('.SH'),'.XSHG','.XSHE');codes=sorted(d.symbol.unique());d['ts']=pd.to_datetime(d.trade_time).astype('datetime64[ms]').astype('int64')-8*3600000;d=d.rename(columns={'vol':'volume'});a=bm.metrics(d,codes);b=four(d,codes);a=a.set_index(['code','date']);b=b.set_index(['code','date']);out=[]
 for k in [*PRIMARY,'amount','valid_minutes','one_price','raw_eligible_day']:
  av=a[k].to_numpy(float);bv=b[k].to_numpy(float);assert np.array_equal(np.isnan(av),np.isnan(bv));err=np.nanmax(abs(av-bv));assert err<1e-12;out.append(dict(metric=k,n=len(av),max_abs_error=err,status='PASS'))
 save(pd.DataFrame(out),'four_metric_reuse_checks.csv');print(out)
