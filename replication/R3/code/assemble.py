from common import *
from scipy.stats import skew,kurtosis
import concurrent.futures as cf,threading
PRIMARY=['m1_buy_share_1m','m1_sell_share_1m','m1_buy_n_1m','m1_sell_n_1m','m3_wait_median','m3_update60','m4_spread_bp','m4_depth5_yuan','m5_cancel_rate','m5_limit_market_ratio','m5_avg_order_yuan']
ALL=PRIMARY+[f'm1_{side}_{kind}_{th}'for th in ['500k','3m']for side in ['buy','sell']for kind in ['share','n']]+['m3_snapshot_wait','m3_snapshot_update60','m3_updated_wait','m5_cancel_volume_rate','m5_limit_share','m5_market_share','m5_avg_order_shares']+[f'm1_agg_{side}_{kind}_{th}'for th in ['500k','1m','3m']for side in ['buy','sell']for kind in ['share','n']]
def completed_files(kind):
 identity=hashlib.sha256(b''.join((Path(__file__).parent/v).read_bytes()for v in ['scan.cpp','book169.cpp','numeric229.hpp'])).hexdigest();keep=set()
 for p in (R/'logs/days').glob('*.json'):
  z=json.loads(p.read_text());ds=z.get('date','').replace('-','')
  if z.get('status')=='OK'and z.get('scanner_sha256')in accepted_native_hashes(identity) and all((R/'data'/k/(ds+'.parquet')).exists()for k in ['daily','minute','shocks']):keep.add(ds)
 return [p for p in sorted((R/'data'/kind).glob('*.parquet'))if p.stem in keep]

def assign_stock_bounds(panel,idx,metric,bounds):
 # Same per-stock quantiles as before; align all event rows and write each variant once.
 if not bounds:return
 codes=panel.loc[idx,'code'];use=codes.index[codes.isin(bounds)]
 for variant,lo,hi in [('w01',1,2),('w005',0,3)]:
  low=codes.loc[use].map({code:q[lo]for code,q in bounds.items()});high=codes.loc[use].map({code:q[hi]for code,q in bounds.items()})
  panel.loc[use,metric+'__'+variant]=panel.loc[use,metric].clip(low,high)

def raw_day(p):
 ds=p.stem;d=pd.read_parquet(p);m=pd.read_parquet(R/'data/minute'/f'{ds}.parquet');m=m[m.slot.lt(237)];sums=m.groupby('code').sum(numeric_only=True);quotes=m[m.quote_seconds.gt(0)].groupby('code').agg(m4_spread_bp=('spread_bp','mean'),m4_depth5_yuan=('depth5_yuan','mean'),valid_quote_minutes=('slot','count'));d=d.merge(sums.reset_index().drop(columns=['slot','spread_bp','depth5_yuan'],errors='ignore'),on='code',validate='1:1').merge(quotes,on='code',how='left',validate='1:1')
 for h,th in enumerate(['500k','1m','3m']):
  for side in ['buy','sell']:
   den=d[f'{side}_value'].replace(0,np.nan);d[f'm1_{side}_share_{th}']=d[f'big_{h}_{side}_value']/den;d[f'm1_{side}_n_{th}']=d[f'big_{h}_{side}_n'];d[f'm1_agg_{side}_share_{th}']=d[f'agg_{h}_{side}_value']/den;d[f'm1_agg_{side}_n_{th}']=d[f'agg_{h}_{side}_n']
 d['m5_cancel_rate']=d.cancels/d.adds.replace(0,np.nan);d['m5_cancel_volume_rate']=d.cancel_qty/d.order_qty.replace(0,np.nan);d['m5_limit_market_ratio']=d.limit_n/d.market_n.replace(0,np.nan);d['m5_limit_share']=d.limit_n/d.adds.replace(0,np.nan);d['m5_market_share']=d.market_n/d.adds.replace(0,np.nan);d['m5_avg_order_yuan']=d.order_value/d.priced_orders.replace(0,np.nan);d['m5_avg_order_shares']=d.order_qty/d.adds.replace(0,np.nan)
 d.loc[~(d.order_table.eq(1)&d.trade_table.eq(1)),[x for x in ALL if x.startswith(('m1','m5'))]]=np.nan
 d.loc[d.unknown_types.gt(0),[x for x in ALL if x.startswith('m5')]]=np.nan
 d.loc[d.valid_quote_minutes.lt(180),['m4_spread_bp','m4_depth5_yuan']]=np.nan
 d.to_parquet(T/'daily_raw'/f'{ds}.parquet',index=False);return ds

def daily():
 (T/'daily_raw').mkdir(exist_ok=True);stop=threading.Event();threading.Thread(target=watch,args=(stop,),daemon=True).start()
 try:
  sources=completed_files('daily')
  with cf.ProcessPoolExecutor(max_workers=4,max_tasks_per_child=1)as pool:
   for x in pool.map(raw_day,sources):pass
 finally:stop.set()
 pieces=[pd.read_parquet(T/'daily_raw'/p.name)for p in sources];raw=pd.concat(pieces,ignore_index=True);m=pd.read_csv(R/'tables/event_date_map.csv',parse_dates=['date','treatment_date','freeze_date','anchor']);f=pd.read_csv(R/'tables/frozen_features.csv',parse_dates=['freeze_date','anchor','earliest_sample'],low_memory=False);panel=m.drop(columns=['freeze_date','anchor']).merge(f,on=['kind','event_id'],validate='m:m').merge(raw,on=['date','code'],how='left',validate='m:1');out=[]
 for p in completed_files('shocks'):
  s=pd.read_parquet(p)
  if not len(s):continue
  quality=raw.loc[raw.date.eq(pd.Timestamp(p.stem)),['code','clock_ok']];s=s.merge(quality,on='code',how='left',validate='m:1')
  for key,x in s.groupby(['date','code','event_id']):
   good=x[x.queue_ok.eq(1)&x.wait_seconds.notna()];snap=x[x.snapshot_wait_seconds.notna()&x.clock_ok.eq(1)];out.append(dict(date=key[0],code=key[1],event_id=key[2],m3_wait_median=good.wait_seconds.median(),m3_update60=good.updated.mean(),m3_updated_wait=good.loc[good.updated.eq(1),'wait_seconds'].median(),m3_snapshot_wait=snap.snapshot_wait_seconds.median(),m3_snapshot_update60=snap.snapshot_updated.mean(),n_shocks=len(good),n_snapshot_shocks=len(snap)))
 shock=pd.DataFrame(out,columns=['date','code','event_id','m3_wait_median','m3_update60','m3_updated_wait','m3_snapshot_wait','m3_snapshot_update60','n_shocks','n_snapshot_shocks']);panel=panel.merge(shock,on=['date','code','event_id'],how='left',validate='m:1');thresholds=[];normal=set(pd.read_csv(R/'tables/official_calendar.csv').query('nb_open').date);pool=panel[panel.date.dt.strftime('%Y-%m-%d').isin(normal)].sort_values(['date','code','freeze_date','event_id']).drop_duplicates(['date','code'])[['date','code','freeze_date',*ALL]]
 for i,metric in enumerate(ALL):
  print('DAILY_WINSOR',i+1,len(ALL),metric,flush=True)
  for var in ['w01','w005']:panel[metric+'__'+var]=np.nan
  for key,idx in panel.groupby(['kind','event_id']).groups.items():
   cutoff=panel.loc[idx,'earliest_sample'].min();history_mask=pool.date.lt(cutoff)
   if metric.startswith('m3'):history_mask&=pool.freeze_date.lt(cutoff)
   hist=pool.loc[history_mask,['date','code',metric]];vals=hist[metric].dropna().to_numpy();q=np.quantile(vals,[.005,.01,.99,.995])if len(vals)else np.full(4,np.nan);thresholds.append(dict(kind=key[0],event_id=key[1],metric=metric,cutoff=cutoff,history_max=hist.date.max(),n=len(vals),q005=q[0],q01=q[1],q99=q[2],q995=q[3],method='pre-sample pooled normal stock-days'))
   if np.isfinite(q).all():
    panel.loc[idx,metric+'__w01']=panel.loc[idx,metric].clip(q[1],q[2]);panel.loc[idx,metric+'__w005']=panel.loc[idx,metric].clip(q[0],q[3])
   validhist=hist.dropna(subset=[metric]);counts=validhist.groupby('code').date.nunique();validcodes=counts.index[counts.ge(60)]
   bounds={}
   for code,hh in validhist[validhist.code.isin(validcodes)].groupby('code'):
    qq=np.quantile(hh[metric],[.005,.01,.99,.995]);bounds[code]=qq;thresholds.append(dict(kind=key[0],event_id=key[1],code=code,metric=metric,cutoff=cutoff,history_max=hh.date.max(),n=len(hh),q005=qq[0],q01=qq[1],q99=qq[2],q995=qq[3],method='stock history >=60 normal dates'))
   assign_stock_bounds(panel,idx,metric,bounds)
 panel.to_parquet(T/'daily_panel.parquet',index=False);save(pd.DataFrame(thresholds),'winsor_thresholds_daily.csv');dist=[]
 for kind,x in panel.groupby('kind'):
  for metric in ALL:
   for variant,col in [('raw',metric),('w01',metric+'__w01'),('w005',metric+'__w005')]:
    v=x[col].dropna().to_numpy();quant=np.quantile(v,[.001,.005,.01,.25,.5,.75,.99,.995,.999])if len(v)else np.full(9,np.nan);dist.append(dict(kind=kind,metric=metric,variant=variant,n=len(v),missing=len(x)-len(v),mean=np.mean(v)if len(v)else np.nan,sd=np.std(v,ddof=1)if len(v)>1 else np.nan,skew=skew(v)if len(v)>2 else np.nan,excess_kurtosis=kurtosis(v)if len(v)>3 else np.nan,zero_share=np.mean(v==0)if len(v)else np.nan,**dict(zip(['q001','q005','q01','q25','q50','q75','q99','q995','q999'],quant))))
 save(pd.DataFrame(dist),'distributions_daily.csv');save(raw.groupby('date').agg(stocks=('code','nunique'),order_rows=('raw_order_rows','sum'),trade_rows=('raw_trade_rows','sum'),quote_rows=('raw_quote_rows','sum'),duplicates=('duplicate_order_ids','sum'),conflicts=('conflicting_order_ids','sum'),queue_pass=('queue_ok','sum'),unknown_aggressor=('unknown_aggressor','sum'),quote_minutes=('valid_quote_minutes','sum')).reset_index(),'l2_scale_by_date.csv');print('DAILY PANEL',len(panel),flush=True)

def moment_day(value):
 dt=pd.Timestamp(value);ds=dt.strftime('%Y%m%d');m=pd.read_parquet(R/'data/minute'/f'{ds}.parquet');quality=pd.read_parquet(R/'data/daily'/f'{ds}.parquet');valid=set(quality.loc[quality.order_table.eq(1)&quality.trade_table.eq(1),'code']);m=m[m.code.isin(valid)];m=m[(m.slot.ge(5)&m.slot.lt(120))|(m.slot.ge(125)&m.slot.lt(237))].copy();mp=pd.read_csv(R/'tables/event_date_map.csv',parse_dates=['date']);mp=mp[mp.date.eq(dt)];feat=pd.read_csv(R/'tables/frozen_features.csv',parse_dates=['earliest_sample'],low_memory=False);rows=[];diagnostics=[]
 for product in ['IF','IH']:
  with np.load(T/f'futures_{product}.npz') as z:
   days=pd.to_datetime(z['dates'],unit='D');ix=np.flatnonzero(days==dt)
   if not len(ix):continue
   r=z['returns'][ix[0]]*1e4
  F=np.column_stack([r,*[np.r_[np.full(j,np.nan),r[:-j]]for j in range(1,6)]]);slots=m.slot.unique();slots=slots[np.isfinite(F[slots]).all(1)];mm=m[m.slot.isin(slots)];fx=F[slots];n=len(slots);sf=fx.sum(0);sff=fx.T@fx
  if not n:continue
  for e in mp.itertuples():
   ef=feat[(feat.kind==e.kind)&(feat.event_id==e.event_id)].set_index('code');x=mm[mm.code.isin(ef.index)].copy()
   if x.empty:continue
   x['y']=((x.buy_value-x.sell_value)/x.code.map(ef.circulating_market_cap).astype(float)*1e4).replace([np.inf,-np.inf],np.nan)
   # Thresholds saved before this phase using ONLY earlier designated normal-day flows.
   th=pd.read_csv(R/'tables/winsor_thresholds_flow.csv');th=th[(th.kind==e.kind)&(th.event_id==e.event_id)];poolth=th[th.code.eq('__POOL__')].iloc[0];byth=th.set_index('code')
   for var,low,high in [('raw',-np.inf,np.inf),('w01',poolth.q01,poolth.q99),('w005',poolth.q005,poolth.q995)]:
    xx=x.copy();xx['y']=xx.y.clip(low,high)if np.isfinite(low)or var=='raw'else np.nan;
    if var!='raw':
     lc,hc=('q01','q99')if var=='w01'else('q005','q995');lo=x.code.map(byth[lc]).fillna(low);hi=x.code.map(byth[hc]).fillna(high);xx['y']=x.y.clip(lo,hi).where(lo.notna()&hi.notna())
    xx['y2']=xx.y**2
    if product=='IF':diagnostics.append(pd.DataFrame({'kind':e.kind,'variant':var,'y':xx.y.to_numpy(float)}))
    for j in range(6):xx[f'syf{j}']=xx.y*F[xx.slot,j]
    g=xx.groupby('code').agg(n=('y','count'),sy=('y','sum'),sy2=('y2','sum'),**{f'syf{j}':(f'syf{j}','sum')for j in range(6)}).reset_index();g=g[g.n.eq(n)];g['date']=dt;g['kind']=e.kind;g['event_id']=e.event_id;g['product']=product;g['variant']=var
    for j in range(6):g[f'sf{j}']=sf[j]
    for j in range(6):
     for k in range(6):g[f'sff{j}_{k}']=sff[j,k]
    rows.append(g)
 if rows:pd.concat(rows,ignore_index=True).to_parquet(T/'moments'/f'{ds}.parquet',index=False)
 if diagnostics:
  (T/'flow_diag').mkdir(exist_ok=True);pd.concat(diagnostics,ignore_index=True).to_parquet(T/'flow_diag'/f'{ds}.parquet',index=False)
 return ds

def flow_threshold_event(job):
 key,ef,sources,normal=job;out=[]
 cutoff=ef.earliest_sample.min();by=ef.set_index('code').circulating_market_cap;vals=[];last=None;stockvals={};stockdays={}
 for filename in sources:
  p=Path(filename)
  dt=pd.Timestamp(p.stem)
  if dt>=cutoff or str(dt.date())not in normal:continue
  d=pd.read_parquet(p,columns=['code','buy_value','sell_value','slot']);quality=pd.read_parquet(R/'data/daily'/p.name);valid=set(quality.loc[quality.order_table.eq(1)&quality.trade_table.eq(1),'code']);d=d[d.code.isin(by.index)&d.code.isin(valid)&d.slot.lt(237)];v=((d.buy_value-d.sell_value)/d.code.map(by).astype(float)*1e4).replace([np.inf,-np.inf],np.nan).dropna().to_numpy(copy=True);vals.append(v);last=dt
  d['flow']=((d.buy_value-d.sell_value)/d.code.map(by).astype(float)*1e4).replace([np.inf,-np.inf],np.nan)
  for code,x in d.groupby('code'):
   vv=x.flow.dropna().to_numpy(copy=True);stockvals.setdefault(code,[]).append(vv);stockdays[code]=stockdays.get(code,0)+int(len(vv)>0)
 v=np.concatenate(vals)if vals else np.array([]);vals.clear();q=np.quantile(v,[.005,.01,.99,.995])if len(v)else np.full(4,np.nan);out.append(dict(kind=key[0],event_id=key[1],code='__POOL__',cutoff=cutoff,history_max=last,n=len(v),q005=q[0],q01=q[1],q99=q[2],q995=q[3]))
 for code,vv in stockvals.items():
  if stockdays[code]<60:continue
  v=np.concatenate(vv);q=np.quantile(v,[.005,.01,.99,.995]);out.append(dict(kind=key[0],event_id=key[1],code=code,cutoff=cutoff,history_max=last,n=len(v),q005=q[0],q01=q[1],q99=q[2],q995=q[3]))
 return out

def futures_requested_coverage():
 plan=pd.read_csv(R/'tables/download_plan.csv',parse_dates=['date']);mapping=pd.read_csv(R/'tables/event_date_map.csv',parse_dates=['date']);rows=[]
 treated=set(mapping.loc[mapping.kind.eq('real')&mapping.closed,'date']);control=set(mapping.loc[mapping.kind.eq('real')&~mapping.closed,'date'])
 valid_slots=np.r_[np.arange(5,120),np.arange(125,237)]
 for product in ['IF','IH']:
  with np.load(T/f'futures_{product}.npz')as z:
   bydate={pd.Timestamp(d):j for j,d in enumerate(pd.to_datetime(z['dates'],unit='D'))}
   for dt in plan.date:
    nret=nlag=0
    if dt not in bydate:status='NO_SOURCE_DATE'
    else:
     r=z['returns'][bydate[dt]];nret=int(np.isfinite(r).sum());F=np.column_stack([r,*[np.r_[np.full(j,np.nan),r[:-j]]for j in range(1,6)]]);nlag=int(np.isfinite(F[valid_slots]).all(1).sum());status='OK'if nlag else 'ALL_RETURNS_MISSING'if not nret else 'NO_COMPLETE_LAG_MINUTES'
    rows.append(dict(date=dt,product=product,status=status,finite_return_minutes=nret,complete_lag_minutes=nlag,real_treatment=dt in treated,real_control=dt in control,source='original_minute'if dt<=pd.Timestamp('2026-09-01')else 'tick_supplement'if dt<=pd.Timestamp('2026-09-30')else 'no_local_source'))
 save(pd.DataFrame(rows),'futures_coverage_by_requested_date.csv')

def flow():
 futures_requested_coverage()
 # Four event workers; values remain strictly pre-sample and use unchanged frozen caps.
 f=pd.read_csv(R/'tables/frozen_features.csv',usecols=['kind','event_id','code','earliest_sample','circulating_market_cap'],parse_dates=['earliest_sample'],low_memory=False);normal=set(pd.read_csv(R/'tables/official_calendar.csv').query('nb_open').date);sources=[str(p)for p in completed_files('minute')];out=[];jobs=[(key,ef,sources,normal)for key,ef in f.groupby(['kind','event_id'])]
 with cf.ProcessPoolExecutor(max_workers=4,max_tasks_per_child=1)as pool:
  for i,rows in enumerate(pool.map(flow_threshold_event,jobs,chunksize=1)):
   out.extend(rows)
   if i%10==0:print('FLOW_THRESHOLDS',i+1,len(jobs),flush=True)
 save(pd.DataFrame(out),'winsor_thresholds_flow.csv');(T/'moments').mkdir(exist_ok=True)
 for folder in ['moments','flow_diag']:
  for prior in (T/folder).glob('*.parquet'):prior.unlink()
 days=[str(pd.Timestamp(p.stem).date())for p in completed_files('minute')]
 with cf.ProcessPoolExecutor(max_workers=4,max_tasks_per_child=1)as pool:
  for x in pool.map(moment_day,days):pass
 dist=[]
 for kind in ['real','fake20','common_holiday']:
  for var in ['raw','w01','w005']:
   vals=[];total=0
   for p in sorted((T/'flow_diag').glob('*.parquet')):
    dd=pd.read_parquet(p);vv=dd.loc[dd.kind.eq(kind)&dd.variant.eq(var),'y'];total+=len(vv);vals.append(vv.dropna().to_numpy(float))
   v=np.concatenate(vals)if vals else np.array([]);q=np.quantile(v,[.001,.005,.01,.25,.5,.75,.99,.995,.999])if len(v)else np.full(9,np.nan);dist.append(dict(kind=kind,variant=var,metric='m2_net_flow_cap_bp',n=len(v),missing=total-len(v),mean=np.mean(v)if len(v)else np.nan,sd=np.std(v,ddof=1)if len(v)>1 else np.nan,skew=skew(v)if len(v)>2 else np.nan,excess_kurtosis=kurtosis(v)if len(v)>3 else np.nan,zero_share=np.mean(v==0)if len(v)else np.nan,**dict(zip(['q001','q005','q01','q25','q50','q75','q99','q995','q999'],q))))
 save(pd.DataFrame(dist),'distributions_flow.csv')
 print('MOMENTS COMPLETE',len(days),flush=True)
if __name__=='__main__':globals()[sys.argv[1]]()
