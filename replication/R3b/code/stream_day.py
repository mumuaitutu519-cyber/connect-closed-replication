from common import *
import io,zipfile
sys.path.insert(0,str(R/'code/r1'))
import build_metrics as bm
RAW=Path('/Volumes/Extreme SSD/T9/codex项目/A股分钟线+日频量价/A股分钟数据/1m_price_zip');OUT=T/'metrics_daily';OUT.mkdir(exist_ok=True)
def stream(value,force=False):
 t=pd.Timestamp(value);dest=OUT/f'{t:%Y%m%d}.parquet';receipt=dest.with_suffix('.json')
 if not force and dest.exists() and receipt.exists():return json.loads(receipt.read_text())
 start=time.time();codes=pd.read_csv(R/'meta/stock_universe.csv').code.tolist();symbols=[c[:6]+('.XSHG' if c.endswith('.SH') else '.XSHE') for c in codes];index=pd.Index(codes);symindex=pd.Index(symbols);x=np.full((len(codes),241,5),np.nan);seen=np.zeros((len(codes),1440),bool);observed=np.zeros(len(codes),bool);scanned=selected=duplicates=0;source=[];available=False;raw=RAW/f'{t.year}.zip';member=f'{t:%Y%m%d}.parquet';day=int(np.datetime64(t,'D').astype('int64'));lower=day*86400000-8*3600000;upper=lower+86400000
 def consume(d,israw):
  nonlocal scanned,selected,duplicates
  scanned+=len(d)
  if israw:
   ids=index.get_indexer(d.code);ts=pd.to_datetime(d.trade_time).astype('datetime64[ms]').astype('int64').to_numpy()-8*3600000
  else:ids=symindex.get_indexer(d.symbol);ts=d.ts.to_numpy(np.int64)
  mask=(ids>=0)&(ts>=lower)&(ts<upper);selected+=int(mask.sum())
  if not mask.any():return
  ii=ids[mask];ts=ts[mask]+8*3600000;assert (ts%60000==0).all();minute=((ts//60000)%1440).astype(int);key=ii*1440+minute;_,first=np.unique(key,return_index=True);duplicates+=len(key)-len(first);ii=ii[first];minute=minute[first];previous=seen[ii,minute];duplicates+=int(previous.sum());keep=~previous;seen[ii,minute]=True;ii=ii[keep];minute=minute[keep];row=np.flatnonzero(mask)[first[keep]];valid=((minute>=570)&(minute<=690))|((minute>=781)&(minute<=900));ii=ii[valid];minute=minute[valid];row=row[valid];slot=np.where(minute<=690,minute-570,minute-780+120);v=d.iloc[row][['open','high','low','close','amount']].to_numpy(float,copy=True);bad=(v[:,0]<=0)|(v[:,3]<=0)|(v[:,1]<v[:,2])|~np.isfinite(v[:,:4]).all(1);v[bad,:]=np.nan;x[ii,slot,:]=v;observed[ii]=True
 if raw.exists():
  with zipfile.ZipFile(raw) as z:
   if member in z.namelist():
    available=True;pf=pq.ParquetFile(io.BytesIO(z.read(member)))
    for b in pf.iter_batches(batch_size=65536,columns=['code','trade_time','open','high','low','close','amount'],use_threads=False):consume(b.to_pandas(use_threads=False),True)
    pf.close();source=[str(raw)+'!'+member]
 if not available:
  for p in (Q/'stocks_1m/full').glob('*.parquet'):
   if p.stem not in [f'{t.year}',f'{t:%Y-%m}',f'{t:%Y-%m-%d}']:continue
   pf=pq.ParquetFile(p);groups=[]
   for j in range(pf.num_row_groups):
    st=pf.metadata.row_group(j).column(0).statistics
    if st is None or not st.has_min_max or (st.max>=lower and st.min<upper):groups.append(j)
   for b in pf.iter_batches(batch_size=65536,row_groups=groups,columns=['ts','symbol','open','high','low','close','amount'],use_threads=False):consume(b.to_pandas(use_threads=False),False)
   pf.close();source.append(str(p))
 if not observed.any():raise ValueError(f'No source minute rows {t}')
 ii=np.flatnonzero(observed);x=x[ii];op,hi,lo,cl,amt=[x[:,:,k] for k in range(5)]
 with np.errstate(divide='ignore',invalid='ignore'):
  r=np.log(cl[:,1:]/cl[:,:-1]);opening=np.where(np.isfinite(op[:,0]),op[:,0],op[:,1]);r[:,0]=np.log(cl[:,1]/opening);r[:,120]=np.log(cl[:,121]/op[:,121]);r[~np.isfinite(cl[:,1:])]=np.nan;n=np.isfinite(r).sum(1);amount=np.nansum(amt[:,1:],1);one=np.nanmax(hi[:,1:],1)<=np.nanmin(lo[:,1:],1);values=bm.future_metrics(r,np.full(len(ii),day));f=pd.DataFrame(values);f.insert(0,'date',t);f.insert(0,'code',np.array(codes)[ii]);f['amount']=amount;f['valid_minutes']=n;f['one_price']=one;f['raw_eligible_day']=(n>=180)&~one&(amount>0)
 temp=dest.with_suffix('.partial');f.to_parquet(temp,index=False,compression='zstd');temp.replace(dest);rec=dict(date=str(t.date()),source=source,original_day_archive=available,input_rows_scanned=scanned,selected_minute_rows=selected,duplicate_minute_keys=duplicates,stock_days=len(f),seconds=time.time()-start,path=str(dest),reader='day_stream_65536_rows');js(receipt,rec);return rec
if __name__=='__main__':
 day='2026-05-08';p=OUT/f'{pd.Timestamp(day):%Y%m%d}.parquet';old=pd.read_parquet(p).set_index('code');rr=stream(day,True);new=pd.read_parquet(p).set_index('code');checks=[];assert set(old.index)==set(new.index)
 for k in [*PRIMARY,'amount','valid_minutes','one_price','raw_eligible_day']:
  a=old[k].sort_index().to_numpy(float);b=new[k].sort_index().to_numpy(float);assert np.array_equal(np.isnan(a),np.isnan(b));err=np.nanmax(abs(a-b));assert err<1e-12;checks.append(dict(metric=k,n=len(a),max_abs_error=err,status='PASS'))
 save(pd.DataFrame(checks),'stream_reader_reuse_checks.csv');print(rr,checks)
