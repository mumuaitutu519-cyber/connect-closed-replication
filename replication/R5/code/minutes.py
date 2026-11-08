from common import *
import io,zipfile,concurrent.futures as cf,multiprocessing as mp,warnings
RAW=Path('/Volumes/Extreme SSD/T9/codex项目/A股分钟线+日频量价/A股分钟数据/1m_price_zip')
FUT={};FC={};INFO=None

def setup():
 global INFO
 if INFO is not None:return
 un=pd.read_parquet(T/'universe.parquet');codes=un.code.tolist();sym=[c[:6]+('.XSHG' if c.endswith('.SH') else '.XSHE')for c in codes]
 cal=pd.read_csv(P/'tables/official_calendar.csv',parse_dates=['date']).set_index('date');full=pd.DatetimeIndex(pd.read_csv(P/'meta/actual_full_calendar.csv',parse_dates=['date']).date);st=pd.read_parquet(Q/'cn_st/full/all.parquet');feat=features();mapping=pd.read_csv(P/'tables/event_date_map.csv',parse_dates=['date']);eids=dict(zip(mapping.date,mapping.event_id));fr=feat[['event_id','freeze_date']].drop_duplicates()
 for product in ['IF','IH']:
  with np.load(T/f'futures_{product}.npz')as z:FUT[product]={int(d):r.copy()for d,r in zip(z['dates'],z['returns'])}
 for ev in fr.itertuples():
  normal=set(cal.index[cal.nb_open.eq(True)].to_numpy('datetime64[D]').astype('int64'));cutoff=int(np.datetime64(ev.freeze_date,'D').astype('int64'));prior=sorted(d for d in FUT['IF']if d<cutoff and d in normal)[-60:];arr=np.concatenate([FUT['IF'][d]for d in prior])if prior else np.array([]);v=np.abs(arr[np.isfinite(arr)]);FC[ev.event_id]=np.quantile(v,.9)if len(prior)>=30 and len(v)else np.nan
 INFO=(codes,pd.Index(codes),pd.Index(sym),un,cal,full,st,feat,eids)

def regression(r,fr):
 n=len(r);out={}
 for prod in ['IF','IH']:
  f=fr.get(prod)
  if f is None:
   out[prod.lower()+'_delay']=np.full(n,np.nan)
   if prod=='IF':
    for k in ['if_r2_now','if_r2_full','if_b0_now',*[f'if_b{k}'for k in range(6)]]:out[k]=np.full(n,np.nan)
   continue
  X=np.column_stack([np.ones(240),f,*[np.r_[np.full(l,np.nan),f[:-l]]for l in range(1,6)]]);X[:5]=np.nan;X[120:125]=np.nan;v=np.isfinite(X).all(1);x=X[v];yy=r[:,v];good=np.isfinite(yy).all(1);delay=np.full(n,np.nan);rnow=delay.copy();rfull=delay.copy();bnow=delay.copy();bs=np.full((n,6),np.nan)
  if v.sum()>=180:
   for ids in [np.flatnonzero(good)]:
    if not len(ids):continue
    y=yy[ids];a=y@np.linalg.pinv(x).T;a0=y@np.linalg.pinv(x[:,:2]).T;sst=np.sum((y-y.mean(1)[:,None])**2,1)
    with np.errstate(divide='ignore',invalid='ignore'):
     rr=1-np.sum((y-a@x.T)**2,1)/sst;rr0=1-np.sum((y-a0@x[:,:2].T)**2,1)/sst;delay[ids]=np.where(rr>1e-10,1-rr0/rr,np.nan)
    rnow[ids]=rr0;rfull[ids]=rr;bnow[ids]=a0[:,1];bs[ids]=a[:,1:]
   for i in np.flatnonzero(~good):
    vv=np.isfinite(yy[i]);y=yy[i,vv];xx=x[vv]
    if len(y)<180:continue
    a=np.linalg.lstsq(xx,y,rcond=None)[0];a0=np.linalg.lstsq(xx[:,:2],y,rcond=None)[0];sst=np.sum((y-y.mean())**2)
    if sst<=0:continue
    rr=1-np.sum((y-xx@a)**2)/sst;rr0=1-np.sum((y-xx[:,:2]@a0)**2)/sst;delay[i]=1-rr0/rr if rr>1e-10 else np.nan;rnow[i]=rr0;rfull[i]=rr;bnow[i]=a0[1];bs[i]=a[1:]
  out[prod.lower()+'_delay']=delay
  if prod=='IF':
   out.update(if_r2_now=rnow,if_r2_full=rfull,if_b0_now=bnow)
   for k in range(6):out[f'if_b{k}']=bs[:,k]
 return out

def one(value):
 setup();t=pd.Timestamp(value);dest=T/'daily'/f'{t:%Y%m%d}.parquet'
 if dest.exists():return {'date':value,'status':'CACHED'}
 start=time.time();codes,index,symindex,un,cal,full,st,feat,eids=INFO;N=len(codes);x=np.full((N,241,5),np.nan);seen=np.zeros((N,1440),bool);observed=np.zeros(N,bool);scanned=selected=dup=0;source=[];available=False;raw=RAW/f'{t.year}.zip';member=f'{t:%Y%m%d}.parquet';day=int(np.datetime64(t,'D').astype('int64'));lower=day*86400000-8*3600000;upper=lower+86400000
 def consume(d,israw):
  nonlocal scanned,selected,dup
  scanned+=len(d)
  if israw:ids=index.get_indexer(d.code);ts=pd.to_datetime(d.trade_time).astype('datetime64[ms]').astype('int64').to_numpy()-8*3600000
  else:ids=symindex.get_indexer(d.symbol);ts=d.ts.to_numpy(np.int64)
  mask=(ids>=0)&(ts>=lower)&(ts<upper);selected+=int(mask.sum())
  if not mask.any():return
  ii=ids[mask];tt=ts[mask]+8*3600000;minute=((tt//60000)%1440).astype(int);key=ii*1440+minute;_,first=np.unique(key,return_index=True);dup+=len(key)-len(first);ii=ii[first];minute=minute[first];prev=seen[ii,minute];dup+=int(prev.sum());keep=~prev;seen[ii,minute]=True;ii=ii[keep];minute=minute[keep];row=np.flatnonzero(mask)[first[keep]];valid=((minute>=570)&(minute<=690))|((minute>=781)&(minute<=900));ii=ii[valid];minute=minute[valid];row=row[valid];slot=np.where(minute<=690,minute-570,minute-780+120);v=d.iloc[row][['open','high','low','close','amount']].to_numpy(float,copy=True);bad=(v[:,0]<=0)|(v[:,3]<=0)|(v[:,1]<v[:,2])|~np.isfinite(v[:,:4]).all(1);v[bad]=np.nan;x[ii,slot]=v;observed[ii]=True
 if raw.exists():
  with zipfile.ZipFile(raw)as z:
   if member in z.namelist():
    available=True
    # The day member is decompressed directly into task-owned temporary storage.
    tmp=T/'extract'/member
    with z.open(member)as src,tmp.open('wb')as dst:
     import shutil
     shutil.copyfileobj(src,dst,length=1024*1024)
    pf=pq.ParquetFile(tmp)
    for b in pf.iter_batches(batch_size=65536,columns=['code','trade_time','open','high','low','close','amount'],use_threads=False):consume(b.to_pandas(use_threads=False),True)
    pf.close();tmp.unlink();source=[str(raw)+'!'+member]
 if not available:
  for p in (Q/'stocks_1m/full').glob('*.parquet'):
   if p.stem not in [f'{t.year}',f'{t:%Y-%m}',f'{t:%Y-%m-%d}']:continue
   pf=pq.ParquetFile(p);groups=[]
   for j in range(pf.num_row_groups):
    s=pf.metadata.row_group(j).column(0).statistics
    if s is None or not s.has_min_max or(s.max>=lower and s.min<upper):groups.append(j)
   for b in pf.iter_batches(batch_size=65536,row_groups=groups,columns=['ts','symbol','open','high','low','close','amount'],use_threads=False):consume(b.to_pandas(use_threads=False),False)
   pf.close();source.append(str(p))
 if not observed.any():raise ValueError(f'No raw minutes {t}')
 ii=np.flatnonzero(observed);rows=[];fr={p:FUT[p].get(day)for p in ['IF','IH']}
 past=feat.loc[feat.freeze_date.le(t),['event_id','freeze_date']].drop_duplicates().sort_values('freeze_date');ev=eids.get(t,int(past.iloc[-1].event_id)if len(past)else None);betaby=feat[feat.event_id.eq(ev)].set_index('code').ifbeta if ev is not None else pd.Series(dtype=float)
 for starti in range(0,len(ii),250):
  sel=ii[starti:starti+250];z=x[sel];op,hi,lo,cl,amt=[z[:,:,k]for k in range(5)]
  with np.errstate(divide='ignore',invalid='ignore'):
   r=np.log(cl[:,1:]/cl[:,:-1]);opening=np.where(np.isfinite(op[:,0]),op[:,0],op[:,1]);r[:,0]=np.log(cl[:,1]/opening);r[:,120]=np.log(cl[:,121]/op[:,121]);r[~np.isfinite(cl[:,1:])]=np.nan;n=np.isfinite(r).sum(1);amount=np.nansum(amt[:,1:],1);oneprice=np.nanmax(hi[:,1:],1)<=np.nanmin(lo[:,1:],1);vals=regression(r,fr);vals.update(ln_amount=np.log(np.where(amount>0,amount,np.nan)),rv_bp2=np.nansum(r*r,1)*1e8)
  f=pd.DataFrame(vals);f['code']=np.array(codes)[sel];f['date']=t;f['valid_minutes']=n;f['one_price']=oneprice;f['amount']=amount;f['raw_eligible_day']=(n>=180)&~oneprice&(amount>0);f['adjust5']=np.nan;f['shock_n']=0
  # Compute the ratio for each relevant frozen event; main dates have a unique owner.
  # Non-window historical dates use the latest already-known event freeze; before first freeze ratios are missing.
  if fr['IF']is not None and ev is not None:
   shock=fr['IF'];ixs=np.flatnonzero(np.isfinite(shock)&(abs(shock)>=FC[ev])&(abs(shock)>0));ixs=ixs[(ixs%120)<=114];bt=betaby.reindex(f.code).to_numpy();rat=[]
   for j in ixs:
    s=np.sum(r[:,j:j+6],axis=1);den=bt*shock[j];ratio=np.divide(s,den,out=np.full(len(f),np.nan),where=np.isfinite(den)&(abs(bt)>1e-8));rat.append(ratio)
   if rat:
    a=np.column_stack(rat);nn=np.isfinite(a).sum(1);f['adjust5']=np.divide(np.nansum(a,axis=1),nn,out=np.full(len(f),np.nan),where=nn>0);f['shock_n']=nn
  rows.append(f)
 out=pd.concat(rows,ignore_index=True);first=un.set_index('code').first_observed_daily;age=full.searchsorted(out.date)-full.searchsorted(out.code.map(first))+1;risk=np.zeros(len(out),bool)
 for s in st.itertuples():
  if pd.Timestamp(s.st_start)>t or(pd.notna(s.st_end)and pd.Timestamp(s.st_end)<t):continue
  risk|=out.code.eq(s.ts_code).to_numpy()
 out['eligible_day']=out.raw_eligible_day&(age>=60)&~risk;out['nb_open']=bool(cal.loc[t,'nb_open']);out.to_parquet(dest,index=False,compression='zstd');rec=dict(date=value,stock_days=len(out),eligible=int(out.eligible_day.sum()),scanned=scanned,selected=selected,duplicates=dup,seconds=time.time()-start,source=source);js(dest.with_suffix('.json'),rec);del x,out,rows;release();return rec

def main():
 for d in ['daily','extract']: (T/d).mkdir(exist_ok=True)
 cal=pd.read_csv(P/'tables/official_calendar.csv',parse_dates=['date']);days=cal.loc[cal.a_open,'date'];jobs=[str(d.date())for d in days if not(T/'daily'/f'{d:%Y%m%d}.parquet').exists()];ctx=mp.get_context('spawn')
 for i in range(0,len(jobs),40):
  with cf.ProcessPoolExecutor(max_workers=4,mp_context=ctx)as pool:
   for rec in pool.map(one,jobs[i:i+40]):pass
  print('MINUTES',i+min(40,len(jobs)-i),'/',len(jobs),rec['date'],rec.get('seconds'),flush=True)
 save(pd.DataFrame([json.loads(p.read_text())for p in sorted((T/'daily').glob('*.json'))]),'minute_day_receipts.csv')
if __name__=='__main__':
 warnings.filterwarnings('ignore',category=RuntimeWarning);main()
