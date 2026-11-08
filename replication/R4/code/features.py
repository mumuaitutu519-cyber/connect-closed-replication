from common import *
import concurrent.futures as cf
def lagged(r):
 x=np.column_stack([r,*[np.r_[np.full(k,np.nan),r[:-k]] for k in range(1,6)]]);x[:5]=np.nan;x[120:125]=np.nan;return x
def minute_event(eid):
 dest=T/'hk_features'/f'{eid:03d}.parquet';dest.parent.mkdir(exist_ok=True)
 if dest.exists():return eid
 ev=freezes().set_index('event_id').loc[eid];cal=pd.read_csv(P/'tables/official_calendar.csv',parse_dates=['date']);days=cal.loc[cal.nb_open&cal.date.lt(ev.freeze_date),'date'].tail(60);un=universe();n=len(un);gram=np.zeros((n,13,13));xy=np.zeros((n,13));yy=np.zeros(n);ndays=np.zeros(n,int)
 with np.load(T/'etf_proxy.npz') as z:proxy=dict(zip(z['dates'],z['returns']))
 with np.load(T/'futures_IF.npz') as z:future=dict(zip(z['dates'],z['returns']))
 used=[]
 for t in days:
  dn=int(np.datetime64(t,'D').astype('int64'));h=proxy.get(dn);f=future.get(dn)
  if h is None or f is None:continue
  X=np.column_stack([np.ones(240),lagged(f),lagged(h)]);good=np.isfinite(X).all(1)
  if good.sum()<180:continue
  with np.load(T/'returns'/f'{t:%Y%m%d}.npz') as z:ids=z['ids'];r=z['returns'][:,good];eligible=z['eligible']
  x=X[good];ids=ids[eligible];r=r[eligible];mask=np.isfinite(r);r0=np.nan_to_num(r);xy[ids]+=r0@x;yy[ids]+=np.sum(r0*r0,axis=1);complete=mask.all(1);gram[ids[complete]]+=x.T@x;ndays[ids]+=mask.sum(1)>=180
  for j in np.flatnonzero(~complete):
   xx=x[mask[j]];gram[ids[j]]+=xx.T@xx
  used.append(t)
 nobs=gram[:,0,0];valid=(nobs>=3000)&(ndays>=30);rows={'code':un.code,'event_id':eid,'hk_minute_n':nobs,'hk_minute_days':ndays,'hk_hist_max':max(used) if used else pd.NaT}
 indices=[0,*range(7,13)];g=gram[:,indices][:,:,indices];a=np.linalg.pinv(g,hermitian=True,rcond=1e-11);bet=np.einsum('nij,nj->ni',a,xy[:,indices]);combined=np.einsum('nij,nj->ni',np.linalg.pinv(gram,hermitian=True,rcond=1e-11),xy);ifbet=np.einsum('nij,nj->ni',np.linalg.pinv(gram[:,:7,:7],hermitian=True,rcond=1e-11),xy[:,:7]);sst=yy-np.divide(xy[:,0]**2,nobs,out=np.zeros(n),where=nobs>0)
 with np.errstate(all='ignore'):
  corr=(xy[:,7]-gram[:,0,7]*xy[:,0]/nobs)/np.sqrt((gram[:,7,7]-gram[:,0,7]**2/nobs)*sst);incr=(np.sum(combined*xy,axis=1)-np.sum(ifbet*xy[:,:7],axis=1))/sst
 for i in range(6):rows[f'hk_m_beta{i}']=np.where(valid,bet[:,i+1],np.nan)
 rows['hk_m_lagsum']=np.where(valid,bet[:,2:].sum(1),np.nan);rows['hk_m_corr']=np.where(valid,corr,np.nan);rows['hk_m_incr2']=np.where(valid,incr,np.nan)
 out=pd.DataFrame(rows);assert out.hk_hist_max.dropna().lt(ev.freeze_date).all();out.to_parquet(dest,index=False);print('HK_MINUTE',eid,int(valid.sum()),flush=True);return eid
def minute():
 jobs=freezes().event_id.tolist()
 with cf.ProcessPoolExecutor(max_workers=4) as pool:list(pool.map(minute_event,jobs))

def daily_file(path):
 dest=T/'daily_returns_parts'/path.name;dest.parent.mkdir(exist_ok=True)
 if dest.exists():return str(dest)
 wanted=set(universe().code);out=[]
 for d in batches(path,['symbol','ts','close']):
  d['code']=code(d.symbol);d=d[d.code.isin(wanted)].copy();d['date']=pd.to_datetime(d.ts+28800000,unit='ms').dt.normalize();out.append(d[['code','date','close']])
 f=pd.concat(out,ignore_index=True);f.to_parquet(dest,index=False);return str(dest)
def daily():
 paths=sorted(p for p in (Q/'cn_daily_full/full').glob('*.parquet') if p.stem[:4].isdigit() and 2016<=int(p.stem[:4])<=2026)
 with cf.ProcessPoolExecutor(max_workers=4) as pool:parts=list(pool.map(daily_file,paths))
 # Bounded by stock blocks: only compact daily close prices, never minute tables.
 index_parts=[]
 for p in (Q/'cn_index_1d/full').glob('*.parquet'):
  if not p.stem[:4].isdigit() or not 2016<=int(p.stem[:4])<=2026:continue
  for d in batches(p,['symbol','ts','close']):
   d=d[d.symbol.eq('000300.XSHG')].copy();d['date']=pd.to_datetime(d.ts+28800000,unit='ms').dt.normalize();index_parts.append(d[['date','close']])
 ci=pd.concat(index_parts).drop_duplicates('date').sort_values('date');ci['csi']=np.log(ci.close/ci.close.shift());ci=ci.set_index('date').csi
 glob=pd.read_parquet(Q/'global_index_1d/full/all.parquet');glob.date=pd.to_datetime(glob.date);save(glob[['ticker','name']].drop_duplicates(),'global_index_inventory.csv');hr={}
 for ticker in ['HSI','HSCEI']:
  g=glob[glob.ticker.eq(ticker)].sort_values('date').drop_duplicates('date');g['ret']=np.log(g.close/g.close.shift());hr[ticker]=g.set_index('date').ret
  # HSCEI is not silently substituted. Optional verified supplementary download is separate and labelled.
  if ticker=='HSCEI' and g.empty and (R/'meta/hscei_supplement.csv').exists():
   g=pd.read_csv(R/'meta/hscei_supplement.csv',parse_dates=['date']).sort_values('date');g['ret']=np.log(g.close/g.close.shift());hr[ticker]=g.set_index('date').ret
 save([dict(ticker=k,source='QDC global_index_1d' if k=='HSI' else 'Eastmoney verified true HSCEI supplement' if len(v) else 'MISSING',source_file=str(Q/'global_index_1d/full/all.parquet') if k=='HSI' else str(R/'meta/hscei_supplement.csv'),return_observations=v.notna().sum(),first=v.index.min(),last=v.index.max()) for k,v in hr.items()],'hk_daily_index_sources.csv')
 market=pd.concat([ci.rename('csi'),*[v.rename(k) for k,v in hr.items()]],axis=1).sort_index().rename_axis('date').reset_index();market.to_parquet(T/'daily_market.parquet',index=False)
 nblocks=int(np.ceil(len(universe())/100))
 for first in range(0,nblocks,4):
  with cf.ProcessPoolExecutor(max_workers=4) as pool:list(pool.map(daily_block,range(first,min(first+4,nblocks))))

def daily_block(block):
 import pyarrow.dataset as ds
 un=universe();nblocks=int(np.ceil(len(un)/100));outdir=T/'daily_hk_features';outdir.mkdir(exist_ok=True);market=pd.read_parquet(T/'daily_market.parquet').set_index('date');ci=market.csi.dropna();hr={k:market[k].dropna() for k in ['HSI','HSCEI']};dataset=ds.dataset(T/'daily_returns_parts',format='parquet')
 dest=outdir/f'{block:03d}.parquet'
 if dest.exists():return block
 codes=un.code.iloc[block*100:(block+1)*100].tolist();f=dataset.to_table(filter=ds.field('code').isin(codes),use_threads=False).to_pandas();f=f.drop_duplicates(['code','date']).sort_values(['code','date']);f['ret']=np.log(f.close/f.groupby('code').close.shift());f['csi']=f.date.map(ci);valid=ds.dataset(T/'baseline',format='parquet').to_table(columns=['code','date'],filter=ds.field('code').isin(codes)&ds.field('eligible_day')&ds.field('nb_open'),use_threads=False).to_pandas();f=f.merge(valid,on=['code','date'],how='inner',validate='1:1');records=[]
 for ev in freezes().itertuples():
  cal=pd.read_csv(P/'tables/official_calendar.csv',parse_dates=['date']);days=cal.loc[cal.nb_open&cal.date.lt(ev.freeze_date),'date'].tail(60);hist=f[f.date.isin(days)].copy()
  for ticker,h in hr.items():
   if h.empty:
    records.extend(dict(code=c,event_id=ev.event_id,source=ticker,hk_daily_n=0,hk_daily_hist_max=hist.date.max(),beta=np.nan,corr=np.nan,lag=np.nan,lead=np.nan) for c in hist.code.unique());continue
   hist['hk']=hist.date.map(h);hist['hk_lag']=hist.date.map(h.shift(1));hist['hk_lead']=hist.date.map(h.shift(-1));future_dates=pd.Series(h.index,index=h.index).shift(-1);latest=hist.date.map(future_dates);hist.loc[latest.ge(ev.freeze_date),'hk_lead']=np.nan
   for c,g in hist.groupby('code'):
    z=g[['ret','csi','hk']].replace([np.inf,-np.inf],np.nan).dropna();rec=dict(code=c,event_id=ev.event_id,source=ticker,hk_daily_n=len(z),hk_daily_hist_max=g.date.max(),beta=np.nan,corr=np.nan,lag=np.nan,lead=np.nan)
    if len(z)>=30:
     X=np.column_stack([np.ones(len(z)),z.csi]);y=z.ret.to_numpy();x=z.hk.to_numpy();yp=y-X@np.linalg.lstsq(X,y,rcond=None)[0];xp=x-X@np.linalg.lstsq(X,x,rcond=None)[0];rec['beta']=xp@yp/(xp@xp) if xp@xp>1e-12 else np.nan;rec['corr']=np.corrcoef(xp,yp)[0,1]
    zz=g[['ret','csi','hk_lag','hk','hk_lead']].replace([np.inf,-np.inf],np.nan).dropna()
    if len(zz)>=30:
     assert latest.loc[zz.index].dropna().lt(ev.freeze_date).all()
     X=np.column_stack([np.ones(len(zz)),zz[['csi','hk_lag','hk','hk_lead']]]);b=np.linalg.lstsq(X,zz.ret,rcond=None)[0];rec['lag']=b[2];rec['lead']=b[4]
    records.append(rec)
 d=pd.DataFrame(records);wide=d.pivot(index=['code','event_id'],columns='source',values=['beta','corr','lag','lead']);wide.columns=[f'hk_{source}_{metric}' for metric,source in wide.columns];wide=wide.reset_index();wide.to_parquet(dest,index=False)
 print('HK_DAILY',block+1,'/',nblocks,flush=True);release()
 return block

def combine():
 if (T/'international_needs_refresh').exists():
  from prepare import international
  international();(T/'international_needs_refresh').unlink()
 orig=pd.read_parquet(T/'r2_features.parquet');extended=pd.read_parquet(T/'extended_analyst.parquet');orig=orig.drop(columns='analyst').merge(extended,on=['event_id','code'],how='left',validate='1:1');doses=pd.read_parquet(T/'doses.parquet').drop(columns=['dose','eligible']);intl=pd.read_parquet(T/'international.parquet');minute=pd.concat([pd.read_parquet(p) for p in (T/'hk_features').glob('*.parquet')],ignore_index=True);daily=pd.concat([pd.read_parquet(p) for p in (T/'daily_hk_features').glob('*.parquet')],ignore_index=True)
 f=orig.merge(doses,on=['event_id','code'],how='left',validate='1:1').merge(intl,on=['event_id','code'],how='left',validate='1:1').merge(minute,on=['event_id','code'],how='left',validate='1:1').merge(daily,on=['event_id','code'],how='left',validate='1:1');diagnostics=[];thresholds=[]
 from scipy.stats import skew,kurtosis
 frozen=['dose','eligible','dose_quarter','dose_aug16','qfii','csi300','sse50','csi500','intl_any','h_listed','bh_listed','foreign_first','export_industry']
 original=f[frozen].copy()
 for ev,ix in f.groupby('event_id').groups.items():
  good=f.loc[ix,'pre_age'].ge(60)
  for c in CONTINUOUS:
   v=f.loc[ix,c].replace([np.inf,-np.inf],np.nan);baseline=v[good].dropna();quant=np.quantile(baseline,[.005,.01,.99,.995]) if len(baseline) else np.full(4,np.nan);thresholds.append(dict(event_id=ev,feature=c,n=len(baseline),q005=quant[0],q01=quant[1],q99=quant[2],q995=quant[3],threshold_source='pre-freeze known-age cross section'))
   for variant,lo,hi in [('raw',None,None),('w01',quant[1],quant[2]),('w005',quant[0],quant[3])]:
    z=v if variant=='raw' or c=='qfii' else v.clip(lo,hi);f.loc[ix,c+'__'+variant]=z;z=z.dropna();qs=np.quantile(z,[.001,.01,.25,.5,.75,.99,.999]) if len(z) else np.full(7,np.nan);diagnostics.append(dict(event_id=ev,feature=c,variant=variant,winsor_applied=variant!='raw' and c!='qfii',used_in_race_regression='original R2 raw value' if c in RACE else 'variant value',n=len(z),missing=len(ix)-len(z),mean=z.mean(),sd=z.std(),skew=skew(z,bias=False) if len(z)>2 else np.nan,kurtosis=kurtosis(z,bias=False) if len(z)>3 else np.nan,zero_share=(z==0).mean(),**dict(zip(['q001','q01','p25','median','p75','q99','q999'],qs))))
  for c in ['hk_m_corr','hk_m_incr2','hk_HSI_corr','hk_HSCEI_corr']:
   vv=f.loc[ix,c];med=vv[good].median();f.loc[ix,'high_'+c]=np.where(vv.notna(),vv.gt(med).astype(float),np.nan)
 for c in frozen:assert f[c].equals(original[c]),c
 for v in ['raw','w01','w005']:assert np.allclose(f['qfii__'+v],f.qfii,equal_nan=True)
 binaries=[c for c in frozen if not c.startswith('dose') and c!='qfii']+[c for c in f if c.startswith('high_')]
 for c in binaries:assert set(f[c].dropna().unique()).issubset({0.,1.}),c
 backup=T/'features_before_HSCEI.parquet'
 if backup.exists():
  comparable=[c for c in f.columns if 'hk_HSCEI' not in c];old=pd.read_parquet(backup,columns=comparable);assert len(old)==len(f);checks=[]
  for c in comparable:
   a=old[c];b=f[c]
   if pd.api.types.is_numeric_dtype(b):
    av=a.to_numpy(dtype=float,na_value=np.nan);bv=b.to_numpy(dtype=float,na_value=np.nan);assert np.array_equal(np.isnan(av),np.isnan(bv)),c;good=np.isfinite(av)&np.isfinite(bv);err=float(np.max(abs(av[good]-bv[good]))) if good.any() else 0.;assert err<1e-12,(c,err);checks.append(dict(feature=c,status='UNCHANGED',max_abs_error=err))
   elif pd.api.types.is_datetime64_any_dtype(b):assert a.astype('datetime64[ns]').equals(b.astype('datetime64[ns]')),c;checks.append(dict(feature=c,status='UNCHANGED',max_abs_error=0.))
   else:assert a.astype('string').fillna('<NA>').equals(b.astype('string').fillna('<NA>')),c;checks.append(dict(feature=c,status='UNCHANGED',max_abs_error=0.))
  save(checks,'hscei_backfill_unchanged_features.csv');del old;release()
 f.to_parquet(T/'features.parquet',index=False);f.to_csv(R/'tables/frozen_features_by_event.csv',index=False);save(diagnostics,'feature_distributions.csv');save(thresholds,'feature_winsor_thresholds.csv');save([dict(variable=c,unchanged=True,winsorized=False,binary_domain_checked=c in binaries) for c in list(dict.fromkeys(frozen+binaries))],'dose_binary_unchanged_assertions.csv');save(f.groupby('event_id')[['dose',*CONTINUOUS,'intl_any','foreign_first','bh_listed']].count().reset_index(),'feature_coverage.csv')
 print('FEATURES COMBINED',len(f),flush=True)
if __name__=='__main__':globals()[sys.argv[1]]()
