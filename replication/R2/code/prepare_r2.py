import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
from pathlib import Path
import sys,json,concurrent.futures as cf,numpy as np,pandas as pd,pyarrow.parquet as pq,pyarrow as pa,hashlib,gc
R=Path(__file__).resolve().parents[1];T=Path('/Volumes/Extreme SSD/T9/_tmp/272');Q=Path('/Volumes/Extreme SSD/QDC/data/QDCData')
sys.path.insert(0,str(Path(__file__).parent/'r1'))
import build_panel as bp
EXT=[f'{p}_{kind}' for p in ['if','ih'] for kind in ['delay_f5','delay_f15','lag_bigday','lag_bigpre']]
BASEMET=bp.METRICS.copy();bp.METRICS=BASEMET+EXT

def allmap():
 cal=pd.read_csv(R/'tables/official_calendar.csv',parse_dates=['date']);a=cal[cal.a_open].reset_index(drop=True);normal=set(a.loc[a.nb_open.eq(True),'date']);events=pd.read_csv(R/'tables/events.csv',parse_dates=['start','end']);rows=[];audit=[]
 for shift in [20,40]:
  for ev in events.itertuples():
   pos=a.index[a.date.eq(ev.start)][0]-shift;days=a.iloc[max(0,pos):max(0,pos)+ev.n_closed_days].date.tolist();status='OK'
   if pos<0 or len(days)!=ev.n_closed_days:status='NO_HISTORY'
   elif days[0].dayofweek!=ev.start.dayofweek:status='WEEKDAY_MISMATCH'
   elif any(d not in normal for d in days):status='SHIFT_NOT_ALL_NORMAL_NB'
   eid=shift*100+ev.event_id
   if status=='OK':
    pre=a[a.date.lt(days[0])&a.nb_open.eq(True)].tail(5).date.tolist();post=a[a.date.gt(days[-1])&a.nb_open.eq(True)].head(5).date.tolist();freeze=min(pre)
    for d in pre+days+post:rows.append(dict(kind=f'fake{shift}',event_id=eid,original_event_id=ev.event_id,date=d,closed=d in days,freeze_date=freeze,anchor=days[0]))
   audit.append(dict(shift=shift,original_event_id=ev.event_id,status=status,shifted_start=days[0]if days else pd.NaT))
 f=pd.DataFrame(rows);f['distance']=(f.date-f.anchor).abs().dt.days;f=f.sort_values(['kind','date','distance','anchor']).drop_duplicates(['kind','date']);f.to_csv(R/'tables/fake_event_date_map.csv',index=False);pd.DataFrame(audit).to_csv(R/'tables/fake_event_support.csv',index=False)
 return f

def snapshots():
 fake=allmap();real=pd.read_parquet(T/'exposures.parquet');fr=pd.concat([real[['event_id','freeze_date']].drop_duplicates(),fake[['event_id','freeze_date']].drop_duplicates()]);fr.to_csv(R/'tables/all_freezes.csv',index=False)
 # Holding table projected and streamed; only public dates, use R1 availability rule.
 cal=pd.read_csv(R/'tables/official_calendar.csv',parse_dates=['date']);normal=cal.loc[cal.nb_open.eq(True),'date'].sort_values().to_numpy('datetime64[ns]');pieces=[]
 for b in pq.ParquetFile(Q/'cn_hsgt/hk_hold/full/all.parquet').iter_batches(batch_size=100000,columns=['trade_date','ts_code','ratio'],use_threads=False):
  d=b.to_pandas();d=d[d.ts_code.str.endswith(('.SH','.SZ'))].copy();d['holding_date']=pd.to_datetime(d.trade_date);d['available_date']=d.holding_date+pd.Timedelta(days=1);late=d.holding_date.ge('2024-08-19');quarter=d.holding_date.dt.is_quarter_end
  d=d[~late|quarter].copy();late=d.holding_date.ge('2024-08-19')
  for dt in d.loc[late,'holding_date'].unique():
   ix=np.searchsorted(normal,np.datetime64(dt),side='right')+4;avail=pd.Timestamp(normal[ix])+pd.Timedelta(days=1)if ix<len(normal)else pd.Timestamp.max;d.loc[d.holding_date.eq(dt),'available_date']=avail
  pieces.append(d[['ts_code','holding_date','available_date','ratio']].rename(columns={'ts_code':'code'}))
 h=pd.concat(pieces,ignore_index=True).drop_duplicates(['code','holding_date']);del pieces;h['code']=pd.Categorical(h.code);h=h.sort_values(['available_date','holding_date','code']);h.to_parquet(T/'holdings_public.parquet',index=False)
 universe=pd.read_csv(R/'meta/stock_universe.csv').code.tolist();elig=pd.read_csv(R/'meta/eligibility_events.csv',parse_dates=['effective_date']);out=[];activity=[]
 normals=pd.DatetimeIndex(cal.loc[cal.nb_open.eq(True),'date'])
 for ev in fr.itertuples():
  cutoff=ev.freeze_date;hist=h[h.available_date.lt(cutoff)];latest=hist.drop_duplicates('code',keep='last');by=latest.set_index('code');last=latest.assign(ex=latest.code.astype(str).str[-2:]).groupby('ex').holding_date.max();state={}
  if ev.event_id>=2000:
   for row in elig[elig.effective_date.lt(cutoff)].sort_values(['effective_date','source_row'],ascending=[True,False]).itertuples():
    s=str(row.change)
    if s=='Addition' or s.startswith('Addition (from List of Special') or 'changed from'in s or s=='Buy orders resumed':state[row.code]=1
    elif s.startswith(('Transfer to List of Special','Addition to List of Special'))or s=='Removal'or'changed to'in s or s=='Buy orders suspended':state[row.code]=0
   for c in universe:
    e=state.get(c,0);rr=by.loc[c]if c in by.index else None;valid=rr is not None and rr.holding_date==last.get(c[-2:]);dose=float(rr.ratio)if valid else(0. if not e else np.nan);out.append(dict(event_id=ev.event_id,code=c,freeze_date=cutoff,dose=dose,eligible=e))
  dates=normals[normals<cutoff][-61:];hh=hist[hist.holding_date.isin(dates)].sort_values(['code','holding_date']);hh['change']=hh.groupby('code',observed=True).ratio.diff();s=hh.groupby('code',observed=True).change.agg(['std','count']);s.loc[s['count']<30,'std']=np.nan;s=s.rename(columns={'std':'activity','count':'activity_n'}).reset_index();s['event_id']=ev.event_id;activity.append(s)
 pd.DataFrame(out).to_parquet(T/'fake_exposures.parquet',index=False);pd.concat(activity,ignore_index=True).to_parquet(T/'activity.parquet',index=False);del h,hist;gc.collect()
 # Market cap and shares at preceding trading date, same no-lookahead timestamp as R1.
 full=pd.DatetimeIndex(pd.read_csv(R/'meta/actual_full_calendar.csv',parse_dates=['date']).date);targets={ev.event_id:full[full.searchsorted(ev.freeze_date)-1]for ev in fr.itertuples()};wanted=set(targets.values());cc=[]
 for p in sorted((Q/'cn_valuation_1d/full').glob('*.parquet')):
  if not p.stem[:4].isdigit()or not 2017<=int(p.stem[:4])<=2026:continue
  for b in pq.ParquetFile(p).iter_batches(batch_size=100000,columns=['trade_date','symbol','circulating_market_cap','total_shares'],use_threads=False):
   d=b.to_pandas();d['date']=pd.to_datetime(d.trade_date);d=d[d.date.isin(wanted)].copy();d['code']=d.symbol.str[:6]+np.where(d.symbol.str.endswith('XSHG'),'.SH','.SZ');cc.append(d[['date','code','circulating_market_cap','total_shares']])
 c=pd.concat(cc,ignore_index=True).drop_duplicates(['code','date']);out=[]
 for eid,dt in targets.items():
  d=c[c.date.eq(dt)].copy();d['event_id']=eid;out.append(d.rename(columns={'date':'cap_date'}))
 caps=pd.concat(out,ignore_index=True);caps.to_parquet(T/'pre_cap.parquet',index=False)
 # Explicitly typed QFII, and completeness coverage from all ten holders (not zero for absent reports).
 parts=[]
 for b in pq.ParquetFile(Q/'cn_top_holders/top10/full/all.parquet').iter_batches(batch_size=100000,columns=['symbol','report_date','announce_date','shareholder_type','end_holding_qty','seq_no'],use_threads=False):
  d=b.to_pandas();d['qfii_qty']=d.end_holding_qty.where(d.shareholder_type.eq('QFII'),0);parts.append(d.groupby(['symbol','report_date','announce_date'],dropna=False).agg(qfii_qty=('qfii_qty','sum'),holder_rows=('seq_no','count'),max_seq=('seq_no','max')).reset_index())
 holders=pd.concat(parts).groupby(['symbol','report_date','announce_date'],dropna=False).agg(qfii_qty=('qfii_qty','sum'),holder_rows=('holder_rows','sum'),max_seq=('max_seq','max')).reset_index();holders['announce_date']=pd.to_datetime(holders.announce_date);holders['report_date']=pd.to_datetime(holders.report_date);holders['code']=holders.symbol.astype(str).str[:6]+np.where(holders.symbol.astype(str).str.startswith('6'),'.SH','.SZ');out=[]
 for ev in fr.itertuples():
  d=holders[holders.announce_date.lt(ev.freeze_date)].sort_values(['report_date','announce_date']).drop_duplicates('code',keep='last').copy();d['event_id']=ev.event_id;d=d.merge(caps[caps.event_id.eq(ev.event_id)][['code','total_shares']],on='code',how='left',validate='1:1');d['qfii']=d.qfii_qty/d.total_shares*100;d.loc[d.max_seq.lt(10)|d.holder_rows.lt(10),'qfii']=np.nan;out.append(d[['event_id','code','qfii','report_date','announce_date','holder_rows']])
 pd.concat(out,ignore_index=True).to_parquet(T/'qfii.parquet',index=False)
 # Analyst distinct organisations; all records deduplicated across forecast horizons.
 ap=Q/'cn_analyst_rating/report_rc/full/all.parquet';aa=[]
 for b in pq.ParquetFile(ap).iter_batches(batch_size=100000,columns=['ts_code','report_date','org_name'],use_threads=False):aa.append(b.to_pandas())
 a=pd.concat(aa).drop_duplicates();a.report_date=pd.to_datetime(a.report_date);start=a.report_date.min();out=[]
 for ev in fr.itertuples():
  low=ev.freeze_date-pd.Timedelta(days=365);d=a[a.report_date.ge(low)&a.report_date.lt(ev.freeze_date)];counts=d.groupby('ts_code').org_name.nunique();s=pd.DataFrame({'code':universe,'event_id':ev.event_id});s['analyst']=np.log1p(s.code.map(counts).fillna(0))if low>=start else np.nan;out.append(s)
 pd.concat(out,ignore_index=True).to_parquet(T/'analyst.parquet',index=False)
 (R/'meta/covariate_source_coverage.json').write_text(json.dumps(dict(analyst_start=str(start.date()),index_dates=[str(x)for x in pd.read_parquet(Q/'cn_index_cons/full/all.parquet',columns=['trade_date']).trade_date.unique()],industry_dates=[str(x)for x in pd.read_parquet(Q/'cn_industry_tdx/full/all.parquet',columns=['snapshot_date']).snapshot_date.unique()],qfii_report_min=str(holders.report_date.min().date()),qfii_report_max=str(holders.report_date.max().date())),indent=2))
 print('SNAPSHOTS COMPLETE',len(fr),flush=True)

def pooled_extended(metric):
 import pyarrow.dataset as ds
 vals=[];dates=[]
 dataset=ds.dataset(T/'baseline',format='parquet')
 for b in dataset.to_batches(columns=['date',metric],filter=ds.field('eligible_day')&ds.field('nb_open'),batch_size=65536,use_threads=False):
  v=b.column(1).to_numpy(zero_copy_only=False);dt=b.column(0).to_numpy(zero_copy_only=False);good=np.isfinite(v);vals.append(v[good].copy());dates.append(dt[good].copy())
 v=np.concatenate(vals);dt=np.concatenate(dates);del vals,dates;order=np.argsort(dt,kind='stable');v=v[order];dt=dt[order];del order
 ex=pd.read_parquet(T/'exposures.parquet',columns=['event_id','freeze_date']).drop_duplicates('event_id');out=[]
 for r in ex.itertuples():
  j=np.searchsorted(dt,np.datetime64(r.freeze_date),side='left');q=np.quantile(v[:j],[.005,.01,.99,.995])if j else np.full(4,np.nan);out.append(dict(event_id=r.event_id,metric=metric,baseline_before=r.freeze_date,n=j,q005=q[0],q01=q[1],q99=q[2],q995=q[3]))
 return out

def canonical():
 jobs=range(int(np.ceil(len(pd.read_csv(R/'meta/stock_universe.csv'))/20)))
 with cf.ProcessPoolExecutor(max_workers=4)as pool:
  for i,r in enumerate(pool.map(bp.canonical,jobs)):
   if i%30==0:print('CANONICAL',i,r,flush=True)
 out=[]
 with cf.ProcessPoolExecutor(max_workers=4)as pool:
  for rows in pool.map(pooled_extended,EXT):out.extend(rows)
 old=pd.read_csv(R/'tables/pooled_winsor_thresholds.csv');old=old[~old.metric.isin(EXT)];pd.concat([old,pd.DataFrame(out)]).to_csv(R/'tables/pooled_winsor_thresholds.csv',index=False)
 for start in range(0,len(jobs),24):
  with cf.ProcessPoolExecutor(max_workers=4)as pool:
   for i,r in enumerate(pool.map(bp.panel,list(jobs)[start:start+24])):pass
  print('PANEL',start+24,flush=True)
 print('PANELS COMPLETE',flush=True)

def feature_block(block):
 p=T/'baseline'/f'block_{block:03d}.parquet';f=pd.read_parquet(p);ex=pd.read_parquet(T/'exposures.parquet');ex=ex[ex.code.isin(f.code.unique())];out=[]
 with np.load(T/'futures_IF.npz')as z:fr=dict(zip(pd.to_datetime(z['dates'],unit='D'),np.nansum(z['returns'],axis=1)));fn=dict(zip(pd.to_datetime(z['dates'],unit='D'),np.isfinite(z['returns']).sum(1)))
 for ev,ee in ex.groupby('event_id'):
  cutoff=ee.freeze_date.iloc[0];hist=f[f.date.lt(cutoff)&f.eligible_day&f.nb_open].sort_values(['code','date']).groupby('code').tail(60);hist['if_ret']=hist.date.map(fr);hist.loc[hist.date.map(fn).fillna(0).lt(180),'if_ret']=np.nan;groups=[]
  for code,g in hist.groupby('code'):
   q=g[['return_bp','if_ret']].dropna();beta=np.cov(q.return_bp/1e4,q.if_ret,ddof=1)[0,1]/np.var(q.if_ret,ddof=1)if len(q)>=30 and q.if_ret.var()>0 else np.nan
   groups.append(dict(event_id=ev,code=code,logamount=np.log(g.amount.median())if len(g)>=30 else np.nan,ifbeta=beta,predelay=g.if_delay.mean()if g.if_delay.count()>=30 else np.nan))
  out.extend(groups)
 d=pd.DataFrame(out);dest=T/'features';dest.mkdir(exist_ok=True);d.to_parquet(dest/f'{block:03d}.parquet',index=False);return block

def features():
 jobs=range(int(np.ceil(len(pd.read_csv(R/'meta/stock_universe.csv'))/20)))
 with cf.ProcessPoolExecutor(max_workers=4)as pool:
  for i,x in enumerate(pool.map(feature_block,jobs)):
   if i%40==0:print('FEATURES',i,flush=True)
 print('FEATURES COMPLETE',flush=True)
if __name__=='__main__':globals()[sys.argv[1]]()
