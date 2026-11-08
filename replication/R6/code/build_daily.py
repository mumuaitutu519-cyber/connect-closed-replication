from common import *
import zipfile,shutil,time,concurrent.futures as cf,pyarrow.parquet as pq,psutil
sys.path.insert(0,str(R/'code/r1'))
import build_metrics as bm
RAW=Path('/Volumes/Extreme SSD/T9/codex项目/A股分钟线+日频量价/A股分钟数据/1m_price_zip')
for a in ['daily','segments','decompressed']: (T/a).mkdir(exist_ok=True)
U=pd.read_csv(P/'meta/stock_universe.csv');UNIVERSE=set(U.code);CODES=sorted(c[:6]+('.XSHG' if c.endswith('.SH') else '.XSHE') for c in UNIVERSE)
ST=pd.read_parquet(Q/'cn_st/full/all.parquet');FIRST=U.set_index('code').first_observed_daily.apply(pd.Timestamp).to_dict();ADATES=pd.read_csv(P/'meta/actual_full_calendar.csv',parse_dates=['date']).date.to_numpy('datetime64[ns]')
F={};SX={};RISK={};CURRENT_DAY=None
import warnings
warnings.filterwarnings("ignore",category=RuntimeWarning)
def getfuture():
 if F:return
 for p in ['IF','IH']:
  with np.load(T/f'futures_{p}.npz') as z:F[p]={int(k):v.copy() for k,v in zip(z['dates'],z['returns'])}
def delay(yy,x,minn):
 out=np.full(len(yy),np.nan);good=np.isfinite(x).all(1);xx=x[good];y=yy[:,good]
 if len(xx)<minn or np.linalg.matrix_rank(xx)<7:return out
 complete=np.isfinite(y).all(1);ids=np.flatnonzero(complete)
 if len(ids):
  v=y[ids];b=v@np.linalg.pinv(xx).T;b0=v@np.linalg.pinv(xx[:,:2]).T;sst=((v-v.mean(1)[:,None])**2).sum(1)
  with np.errstate(divide='ignore',invalid='ignore'):
   r2=1-((v-b@xx.T)**2).sum(1)/sst;r20=1-((v-b0@xx[:,:2].T)**2).sum(1)/sst;out[ids]=np.where(r2>1e-10,1-r20/r2,np.nan)
 for i in np.flatnonzero(~complete):
  v=np.isfinite(y[i]);a=xx[v];b=y[i,v]
  if len(b)<minn or np.linalg.matrix_rank(a)<7:continue
  ss=((b-b.mean())**2).sum()
  if ss<=0:continue
  r2=1-((b-a@np.linalg.lstsq(a,b,rcond=None)[0])**2).sum()/ss;r20=1-((b-a[:,:2]@np.linalg.lstsq(a[:,:2],b,rcond=None)[0])**2).sum()/ss
  if r2>1e-10:out[i]=1-r20/r2
 return out

def block_metrics(d,day,segments):
 # Only complete small stock blocks are resident; original return/OHLC convention preserved.
 d=d.drop_duplicates(['code','minute']);codes=sorted(d.code.unique());ix=pd.Categorical(d.code,categories=codes).codes
 minute=d.minute.to_numpy();slot=np.where(minute<=690,minute-570,minute-780+120);keep=((minute>=570)&(minute<=690))|((minute>=781)&(minute<=900));d=d.loc[keep];ix=ix[keep];slot=slot[keep]
 x=np.full((len(codes),241,6),np.nan);v=d[['open','high','low','close','vol','amount']].to_numpy(float,copy=True);bad=(v[:,0]<=0)|(v[:,3]<=0)|(v[:,1]<v[:,2])|~np.isfinite(v[:,:4]).all(1);v[bad]=np.nan;x[ix,slot]=v
 op,hi,lo,cl,vol,amt=[x[:,:,j] for j in range(6)]
 with np.errstate(divide='ignore',invalid='ignore'):
  rr=np.log(cl[:,1:]/cl[:,:-1]);opening=np.where(np.isfinite(op[:,0]),op[:,0],op[:,1]);rr[:,0]=np.log(cl[:,1]/opening);rr[:,120]=np.log(cl[:,121]/op[:,121]);rr[~np.isfinite(cl[:,1:])]=np.nan
 n=np.isfinite(rr).sum(1);amount=np.nansum(amt[:,1:],1)
 with np.errstate(invalid='ignore'):
  one=np.nanmax(hi[:,1:],1)<=np.nanmin(lo[:,1:],1)
 dd=pd.DataFrame({'code':codes,'date':pd.Timestamp(day),'valid_minutes':n,'one_price':one,'amount':amount,'volume':np.nansum(vol[:,1:],1)})
 dd['age']=[np.searchsorted(ADATES,np.datetime64(day))-np.searchsorted(ADATES,np.datetime64(FIRST[c]))+1 for c in codes]
 dd['eligible_day']=(n>=180)&~one&(amount>0)&dd.age.ge(60)&~dd.code.isin(RISK)
 dd=pd.concat([dd,pd.DataFrame(bm.future_metrics(rr,np.full(len(rr),np.datetime64(day,'D').astype('int64'))))],axis=1)
 seg=None
 if segments:
  getfuture();dk=np.datetime64(day,'D').astype('int64');data={'code':np.tile(codes,8),'date':pd.Timestamp(day),'eligible_day':np.tile(dd.eligible_day.to_numpy(),8),'segment':np.repeat(np.arange(8),len(codes)),'segment_amount':np.nansum(amt[:,1:].reshape(len(codes),8,30),axis=2).T.ravel(),'valid_segment_returns':np.isfinite(rr.reshape(len(codes),8,30)).sum(2).T.ravel(),'regression_minutes':np.isfinite(rr.reshape(len(codes),8,30)[:,:,5:]).sum(2).T.ravel()}
  for p in ['IF','IH']:
   f=F[p].get(dk);ans=[]
   for j in range(8):
    key=(dk,p,j)
    if key not in SX:
     if f is None:SX[key]=None
     else:
      v=f[j*30:(j+1)*30];xx=np.column_stack([np.ones(30),v,*[np.r_[np.full(l,np.nan),v[:-l]] for l in range(1,6)]]);xx[:5]=np.nan;good=np.isfinite(xx).all(1);x=xx[good];SX[key]=(good,x,np.linalg.pinv(x),np.linalg.pinv(x[:,:2])) if len(x)>=20 and np.linalg.matrix_rank(x)==7 else None
    ds=SX[key];z=np.full(len(rr),np.nan)
    if ds is not None:
     good,x,A,A0=ds;y=rr[:,j*30:(j+1)*30][:,good];complete=np.isfinite(y).all(1);ids=np.flatnonzero(complete)
     if len(ids):
      v=y[ids];b=v@A.T;b0=v@A0.T;sst=((v-v.mean(1)[:,None])**2).sum(1)
      with np.errstate(divide='ignore',invalid='ignore'):
       r2=1-((v-b@x.T)**2).sum(1)/sst;r20=1-((v-b0@x[:,:2].T)**2).sum(1)/sst;z[ids]=np.where(r2>1e-10,1-r20/r2,np.nan)
     for i in np.flatnonzero(~complete):
      v=np.isfinite(y[i]);a=x[v];yy=y[i,v]
      if len(yy)<20 or np.linalg.matrix_rank(a)<7:continue
      ss=((yy-yy.mean())**2).sum()
      if ss<=0:continue
      r2=1-((yy-a@np.linalg.lstsq(a,yy,rcond=None)[0])**2).sum()/ss;r20=1-((yy-a[:,:2]@np.linalg.lstsq(a[:,:2],yy,rcond=None)[0])**2).sum()/ss
      if r2>1e-10:z[i]=1-r20/r2
    ans.append(z)
   data[p.lower()+'_delay']=np.concatenate(ans)
  seg=pd.DataFrame(data)
 return dd,seg

def one_day(day):
 global SX,RISK
 SX={};day=str(day);t=pd.Timestamp(day);RISK=set(ST.loc[pd.to_datetime(ST.st_start).le(t)&pd.to_datetime(ST.st_end).fillna(pd.Timestamp('2100-01-01')).ge(t),'ts_code']);p=T/'daily'/f'{t:%Y%m%d}.parquet';sp=T/'segments'/p.name;rec=p.with_suffix('.json')
 if p.exists() and rec.exists() and (t>pd.Timestamp('2023-10-09') or sp.exists()):return json.loads(rec.read_text())
 tick=time.time();decomp=T/'decompressed'/p.name;source=[];archive=RAW/f'{t.year}.zip';pf=None;fallback=False
 if archive.exists():
  with zipfile.ZipFile(archive) as z:
   if p.name in z.namelist():
    with z.open(p.name) as a,decomp.open('wb') as b:shutil.copyfileobj(a,b,1024*1024)
    pf=pq.ParquetFile(decomp);source=[str(archive)+'!'+p.name]
 if pf is None:
  # QDC date-pruned fallback, partition into small stock files; never concatenate a full day.
  fallback=True;lower=int(t.value//10**6)-8*3600000;upper=lower+86400000;bucket={};writers={};paths=[]
  for q in sorted((Q/'stocks_1m/full').glob('*.parquet')):
   if q.stem not in [f'{t.year}',f'{t:%Y-%m}',day]:continue
   source.append(str(q));z=pq.ParquetFile(q);groups=[]
   for j in range(z.num_row_groups):
    st=z.metadata.row_group(j).column(0).statistics
    if st is None or not st.has_min_max or (st.max>=lower and st.min<upper):groups.append(j)
   for b in z.iter_batches(batch_size=32768,row_groups=groups,columns=['ts','symbol','open','high','low','close','volume','amount'],use_threads=False):
    d=b.to_pandas(use_threads=False);d=d[d.ts.ge(lower)&d.ts.lt(upper)].copy()
    if not len(d):continue
    d['code']=d.symbol.str[:6]+np.where(d.symbol.str.endswith('XSHG'),'.SH','.SZ');d=d[d.code.isin(UNIVERSE)];d['minute']=((d.ts+8*3600000)//60000)%1440;d=d.rename(columns={'volume':'vol'});d=d[['code','minute','open','high','low','close','vol','amount']]
    for k,g in d.groupby(d.code.str[:3]):
     tab=pa.Table.from_pandas(g,preserve_index=False)
     if k not in writers:
      dest=T/'decompressed'/f'{t:%Y%m%d}_{k}.parquet';paths.append(dest);writers[k]=pq.ParquetWriter(dest,tab.schema)
     writers[k].write_table(tab)
   z.close()
  for w in writers.values():w.close()
  def fallback_blocks():
   for q in sorted(paths):
    z=pq.ParquetFile(q);a=z.read(use_threads=False).to_pandas(use_threads=False).sort_values(['code','minute']);z.close()
    for j in range(0,len(a),32768):yield a.iloc[j:j+32768].copy()
    del a;q.unlink();trim()
  batches=fallback_blocks()
 else:batches=pf.iter_batches(batch_size=32768,columns=['code','trade_time','open','high','low','close','vol','amount'],use_threads=False)
 frames=[];sf=[];carry=None;scanned=0;selected=0;last='';dups=0;wantseg=t<=pd.Timestamp('2023-10-09')
 for b in batches:
  d=b.copy() if fallback else b.to_pandas(use_threads=False);scanned+=len(d)
  if not fallback:d['minute']=d.trade_time.str[11:13].astype(int)*60+d.trade_time.str[14:16].astype(int);d=d.drop(columns='trade_time')
  d=d[d.code.isin(UNIVERSE)].copy();selected+=len(d)
  if carry is not None:d=pd.concat([carry,d],ignore_index=True)
  if not len(d):continue
  end=d.code.iloc[-1];carry=d[d.code.eq(end)].copy();d=d[d.code.ne(end)]
  if not len(d):continue
  assert d.code.is_monotonic_increasing,(day,'stock order');dups+=d.duplicated(['code','minute']).sum();a,s=block_metrics(d,day,wantseg);frames.append(a)
  if s is not None:sf.append(s)
 if carry is not None and len(carry):
  a,s=block_metrics(carry,day,wantseg);frames.append(a)
  if s is not None:sf.append(s)
 if not frames:raise ValueError('No minutes '+day)
 d=pd.concat(frames,ignore_index=True);assert not d.code.duplicated().any(),day;d.to_parquet(p,index=False,compression='zstd');rows=len(d);eligible=int(d.eligible_day.sum())
 if sf:pd.concat(sf,ignore_index=True).to_parquet(sp,index=False,compression='zstd')
 if pf:pf.close()
 if decomp.exists():decomp.unlink()
 del d,frames,sf,carry;trim();r=dict(date=day,scanned_minutes=scanned,selected_minutes=selected,stock_days=rows,eligible_stock_days=eligible,duplicate_keys=int(dups),source=source,seconds=time.time()-tick,rss_gb=psutil.Process().memory_info().rss/1e9);rec.write_text(json.dumps(r));return r

def main():
 cal=loadcal();days=cal.loc[cal.a_open & cal.date.le('2026-09-01'),'date'].dt.strftime('%Y-%m-%d');pending=[d for d in days if not (T/'daily'/f'{d.replace("-","")}.json').exists()];print('PENDING',len(pending),flush=True)
 with cf.ProcessPoolExecutor(max_workers=4) as pool:
  for i,r in enumerate(pool.map(one_day,pending,chunksize=1)):
   if i%20==0:print(i,r,flush=True)
 save(pd.DataFrame([json.loads(p.read_text()) for p in (T/'daily').glob('*.json')]),R/'logs/daily_build.csv')
if __name__=='__main__':main()
