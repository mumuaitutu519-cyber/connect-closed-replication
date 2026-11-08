from common import *
import io,zipfile,concurrent.futures as cf,time
sys.path.insert(0,str(P/'code'));import build_metrics as bm
bm.TMP=T
RAW=Path('/Volumes/Extreme SSD/T9/codex项目/A股分钟线+日频量价/A股分钟数据/1m_price_zip')
OUT=T/'metrics_daily';RET=T/'returns';OUT.mkdir(exist_ok=True);RET.mkdir(exist_ok=True)
def day(value):
 t=pd.Timestamp(value);dest=OUT/f'{t:%Y%m%d}.parquet';rp=RET/f'{t:%Y%m%d}.npz';receipt=dest.with_suffix('.json')
 if dest.exists() and receipt.exists() and (rp.exists() or not needs_returns(t)):return json.loads(receipt.read_text())
 start=time.time();un=universe();codes=un.code.tolist();symbols=[c[:6]+('.XSHG' if c.endswith('.SH') else '.XSHE') for c in codes];idx=pd.Index(codes);symidx=pd.Index(symbols);x=np.full((len(codes),241,5),np.nan);seen=np.zeros((len(codes),1440),bool);observed=np.zeros(len(codes),bool);scanned=selected=duplicates=0;source=[];available=False;raw=RAW/f'{t.year}.zip';member=f'{t:%Y%m%d}.parquet';dn=int(np.datetime64(t,'D').astype('int64'));lower=dn*86400000-28800000;upper=lower+86400000
 def consume(d,israw):
  nonlocal scanned,selected,duplicates
  scanned+=len(d)
  if israw:ids=idx.get_indexer(d.code);ts=pd.to_datetime(d.trade_time).astype('datetime64[ms]').astype('int64').to_numpy()-28800000
  else:ids=symidx.get_indexer(d.symbol);ts=d.ts.to_numpy(np.int64)
  keep=(ids>=0)&(ts>=lower)&(ts<upper);selected+=int(keep.sum())
  if not keep.any():return
  ii=ids[keep];tt=ts[keep]+28800000;assert (tt%60000==0).all();m=((tt//60000)%1440).astype(int);key=ii*1440+m;_,first=np.unique(key,return_index=True);duplicates+=len(key)-len(first);ii=ii[first];m=m[first];prev=seen[ii,m];duplicates+=int(prev.sum());good=~prev;seen[ii,m]=True;ii=ii[good];m=m[good];row=np.flatnonzero(keep)[first[good]];good=((m>=570)&(m<=690))|((m>=781)&(m<=900));ii=ii[good];m=m[good];row=row[good];slot=np.where(m<=690,m-570,m-780+120);v=d.iloc[row][['open','high','low','close','amount']].to_numpy(float,copy=True);bad=(v[:,0]<=0)|(v[:,3]<=0)|(v[:,1]<v[:,2])|~np.isfinite(v[:,:4]).all(1);v[bad,:]=np.nan;x[ii,slot,:]=v;observed[ii]=True
 if raw.exists():
  with zipfile.ZipFile(raw) as z:
   if member in z.namelist():
    available=True;pf=pq.ParquetFile(io.BytesIO(z.read(member)))
    for b in pf.iter_batches(batch_size=65536,columns=['code','trade_time','open','high','low','close','amount'],use_threads=False):consume(b.to_pandas(use_threads=False),True)
    source=[str(raw)+'!'+member];pf.close()
 if not available:
  for p in (Q/'stocks_1m/full').glob('*.parquet'):
   if p.stem not in [f'{t.year}',f'{t:%Y-%m}',f'{t:%Y-%m-%d}']:continue
   pf=pq.ParquetFile(p);groups=[]
   for j in range(pf.num_row_groups):
    st=pf.metadata.row_group(j).column(0).statistics
    if st is None or not st.has_min_max or(st.max>=lower and st.min<upper):groups.append(j)
   for b in pf.iter_batches(batch_size=65536,row_groups=groups,columns=['ts','symbol','open','high','low','close','amount'],use_threads=False):consume(b.to_pandas(use_threads=False),False)
   pf.close();source.append(str(p))
 if not observed.any():raise ValueError(f'No minute source {t}')
 ii=np.flatnonzero(observed);x=x[ii];op,hi,lo,cl,amt=[x[:,:,k] for k in range(5)]
 with np.errstate(all='ignore'):
  ret=np.log(cl[:,1:]/cl[:,:-1]);opening=np.where(np.isfinite(op[:,0]),op[:,0],op[:,1]);ret[:,0]=np.log(cl[:,1]/opening);ret[:,120]=np.log(cl[:,121]/op[:,121]);ret[~np.isfinite(cl[:,1:])]=np.nan;n=np.isfinite(ret).sum(1);amount=np.nansum(amt[:,1:],1);one=np.nanmax(hi[:,1:],1)<=np.nanmin(lo[:,1:],1)
  hl=np.log(hi[:,1:]/lo[:,1:]);bet=hl[:,:-1]**2+hl[:,1:]**2;gamma=np.log(np.maximum(hi[:,1:-1],hi[:,2:])/np.minimum(lo[:,1:-1],lo[:,2:]))**2;den=3-2*np.sqrt(2);alpha=(np.sqrt(2*bet)-np.sqrt(bet))/den-np.sqrt(gamma/den);spread=2*np.tanh(np.maximum(alpha,0)/2)*1e4;spread[:,119]=np.nan;cs=bm.safe_mean(spread)
  eta=(np.log(hi)+np.log(lo))/2;lc=np.log(cl);arprod=(lc[:,1:-1]-eta[:,1:-1])*(lc[:,1:-1]-eta[:,2:]);arprod[:,119]=np.nan;ar=2*np.sqrt(np.maximum(bm.safe_mean(arprod),0))*1e4
  ill=np.where(amt[:,1:]>0,np.abs(ret)/amt[:,1:]*1e6,np.nan);amihud=bm.safe_mean(ill);values=bm.future_metrics(ret,np.full(len(ii),dn));f=pd.DataFrame(values);f['cs_bp']=cs;f['ar_bp']=ar;f['amihud']=amihud;f['ln_amount']=np.log(np.where(amount>0,amount,np.nan));f['return_bp']=np.log(cl[:,240]/opening)*1e4
 f.insert(0,'date',t);f.insert(0,'code',np.array(codes)[ii]);f['amount']=amount;f['valid_minutes']=n;f['one_price']=one;f['raw_eligible_day']=(n>=180)&~one&(amount>0)
 full=pd.DatetimeIndex(pd.read_csv(P/'meta/actual_full_calendar.csv',parse_dates=['date']).date);age=full.searchsorted(t)-full.searchsorted(un.set_index('code').loc[f.code,'first_observed_daily'])+1;st=pd.read_parquet(Q/'cn_st/full/all.parquet');risk=set(st.loc[pd.to_datetime(st.st_start).le(t)&(pd.to_datetime(st.st_end).ge(t)|st.st_end.isna()),'ts_code']);f['eligible_day']=f.raw_eligible_day&np.asarray(age>=60)&~f.code.isin(risk);cal=pd.read_csv(P/'tables/official_calendar.csv',parse_dates=['date']).set_index('date');f['nb_open']=bool(cal.loc[t,'nb_open'])
 checks=[];cache=T/'r3b_cache/metrics_daily'/dest.name
 if cache.exists():
  old=pd.read_parquet(cache).set_index('code');new=f.set_index('code');assert set(old.index)==set(new.index)
  for k in PRIMARY:
   a=old[k].sort_index().to_numpy();b=new[k].sort_index().to_numpy();assert np.array_equal(np.isnan(a),np.isnan(b));paired=np.isfinite(a)&np.isfinite(b);err=np.max(abs(a[paired]-b[paired])) if paired.any() else 0.;assert err<1e-11;checks.append(dict(metric=k,max_abs_error=err,finite_pairs=int(paired.sum()),same_missing_pattern=True))
 f.to_parquet(dest,index=False,compression='zstd')
 if needs_returns(t):np.savez_compressed(rp,ids=ii,returns=ret,eligible=f.eligible_day.to_numpy())
 rec=dict(date=str(t.date()),stock_days=len(f),scanned=scanned,selected=selected,duplicates=duplicates,source=source,cache_checks=checks,seconds=time.time()-start);js(receipt,rec);return rec
NEEDED=None
def needs_returns(t):
 global NEEDED
 if NEEDED is None:
  cal=pd.read_csv(P/'tables/official_calendar.csv',parse_dates=['date']);normal=cal.loc[cal.nb_open,'date'];NEEDED=set()
  for ev in freezes().itertuples():NEEDED.update(normal[normal.lt(ev.freeze_date)].tail(60))
 return t in NEEDED
def run():
 c=pd.read_csv(P/'tables/official_calendar.csv',parse_dates=['date']);days=c.loc[c.a_open,'date'];pending=[str(d.date()) for d in days if not(OUT/f'{d:%Y%m%d}.parquet').exists() or(needs_returns(d) and not(RET/f'{d:%Y%m%d}.npz').exists())];print('DAYS',len(days),'PENDING',len(pending),flush=True)
 for start in range(0,len(pending),24):
  with cf.ProcessPoolExecutor(max_workers=4) as pool:
   for r in pool.map(day,pending[start:start+24]):pass
  print('MINUTES',start+min(24,len(pending)-start),'/',len(pending),r['date'],flush=True)
def pack(year):
 out=T/'baseline';out.mkdir(exist_ok=True);files=sorted(OUT.glob(f'{year}*.parquet'));parts=[pd.read_parquet(p) for p in files]
 if not parts:return
 f=pd.concat(parts,ignore_index=True);del parts;codes=universe().code.tolist();block={c:i//50 for i,c in enumerate(codes)};f['block']=f.code.map(block)
 for b,g in f.groupby('block'):g.drop(columns='block').to_parquet(out/f'y{year}_{b:03d}.parquet',index=False,compression='zstd')
 print('PACK',year,len(f),flush=True)
def pack_block(b):
 pp=list((T/'baseline').glob(f'y*_{b:03d}.parquet'));f=pd.concat([pd.read_parquet(p) for p in pp],ignore_index=True).sort_values(['code','date']);f.to_parquet(T/'baseline'/f'block_{b:03d}.parquet',index=False,compression='zstd')
 for p in pp:p.unlink()
def panel():
 import build_panel as bp
 bp.ROOT=R;bp.TMP=T;bp.BASE=T/'baseline';bp.PANEL=T/'panel';bp.PANEL.mkdir(exist_ok=True);bp.METRICS=METRICS
 # Original exposures and all-date maps are kept verbatim.
 exp=pd.read_csv(P/'tables/exposure_by_event.csv',parse_dates=['freeze_date','anchor','holding_date','available_date','first_observed_daily']);exp.to_parquet(T/'exposures.parquet',index=False)
 n=int(np.ceil(len(universe())/50));missing=any(not(T/'baseline'/f'block_{b:03d}.parquet').exists() for b in range(n))
 if missing:
  with cf.ProcessPoolExecutor(max_workers=4) as pool:list(pool.map(pack,range(2017,2027)))
  with cf.ProcessPoolExecutor(max_workers=4) as pool:list(pool.map(pack_block,range(n)))
 if not (R/'tables/pooled_winsor_thresholds.csv').exists():
  rows=[]
  # Bound pooled scans to two concurrent tasks; four process workers remain the ceiling.
  import multiprocessing as mp
  for start in range(0,len(METRICS),2):
   with cf.ProcessPoolExecutor(max_workers=2,mp_context=mp.get_context('fork')) as pool:
    for v in pool.map(bp.pooled,METRICS[start:start+2]):rows+=v
  save(rows,'pooled_winsor_thresholds.csv')
 records=[]
 # Fork inherits the explicitly redirected original module globals.
 import multiprocessing as mp
 for start in range(0,n,12):
  with cf.ProcessPoolExecutor(max_workers=4,mp_context=mp.get_context('fork')) as pool:records+=list(pool.map(bp.panel,range(start,min(start+12,n))))
  print('PANEL',min(start+12,n),'/',n,flush=True)
 save([x for r in records for x in r.get('winsor',[])],'outcome_winsor_audit.csv')
if __name__=='__main__':globals()[sys.argv[1]]()
