from common import *
import concurrent.futures as cf,shutil

def ascode(s):return s.astype(str).str[:6]+np.where(s.astype(str).str.startswith('6'),'.SH','.SZ')
def static():
 if all((T/p).exists()for p in ['valuation.parquet','us_analyst.parquet','us_qfii.parquet']):return
 fr=pd.read_csv(R/'tables/design_events.csv',parse_dates=['freeze_date']);fr=fr[fr.family.isin(['main','US'])];full=pd.DatetimeIndex(pd.read_csv(P/'meta/actual_full_calendar.csv',parse_dates=['date']).date);targets={r.event_id:full[full.searchsorted(r.freeze_date)-1]for r in fr.itertuples()};wanted=set(targets.values());parts=[]
 for p in sorted((Q/'cn_valuation_1d/full').glob('*.parquet')):
  if not p.stem[:4].isdigit()or not 2017<=int(p.stem[:4])<=2026:continue
  for b in pq.ParquetFile(p).iter_batches(batch_size=65536,columns=['trade_date','symbol','circulating_market_cap','total_shares','pb'],use_threads=False):
   d=b.to_pandas(use_threads=False);d['date']=pd.to_datetime(d.trade_date);d=d[d.date.isin(wanted)].copy();d['code']=ascode(d.symbol);parts.append(d[['date','code','circulating_market_cap','total_shares','pb']])
 val=pd.concat(parts,ignore_index=True).drop_duplicates(['date','code']);out=[]
 for eid,day in targets.items():d=val[val.date.eq(day)].copy();d['event_id']=eid;d['logcap']=np.log(d.circulating_market_cap.where(d.circulating_market_cap>0));d['value']=1/d.pb.where(d.pb>0);out.append(d)
 cap=pd.concat(out,ignore_index=True);cap.to_parquet(T/'valuation.parquet',index=False);del val,out;release()
 us=fr[fr.family.eq('US')|fr.event_id.isin([1,23,45])];parts=[]
 for b in pq.ParquetFile(Q/'cn_analyst_rating/report_rc/full/all.parquet').iter_batches(batch_size=65536,columns=['ts_code','report_date','org_name'],use_threads=False):parts.append(b.to_pandas(use_threads=False).rename(columns={'ts_code':'code','org_name':'org'}))
 ar=pd.concat(parts,ignore_index=True).drop_duplicates();ar.report_date=pd.to_datetime(ar.report_date);ars=ar.report_date.min();parts=[]
 for p in sorted((Q/'cn_analyst_rating/cninfo_rating_obs/full').glob('*.parquet')):
  for b in pq.ParquetFile(p).iter_batches(batch_size=65536,columns=['seccode','declare_date','org'],use_threads=False):
   d=b.to_pandas(use_threads=False);d['code']=ascode(d.seccode);d['report_date']=pd.to_datetime(d.declare_date,errors='coerce');parts.append(d[['code','report_date','org']])
 ac=pd.concat(parts,ignore_index=True).dropna().drop_duplicates();acs=ac.report_date.min();out=[];codes=pd.read_parquet(T/'universe.parquet').code
 for r in us.itertuples():
  low=r.freeze_date-pd.Timedelta(days=365);a=ar if low>=ars else ac;start=ars if low>=ars else acs;cnt=a[a.report_date.ge(low)&a.report_date.lt(r.freeze_date)].groupby('code').org.nunique();d=pd.DataFrame({'code':codes});d['event_id']=r.event_id;d['analyst']=np.log1p(d.code.map(cnt).fillna(0))if low>=start else np.nan;out.append(d)
 pd.concat(out,ignore_index=True).to_parquet(T/'us_analyst.parquet',index=False);del ar,ac,parts;release()
 # QFII exact 272 explicit-type and complete-ten-holders proxy.
 parts=[]
 for b in pq.ParquetFile(Q/'cn_top_holders/top10/full/all.parquet').iter_batches(batch_size=65536,columns=['symbol','report_date','announce_date','shareholder_type','end_holding_qty','seq_no'],use_threads=False):
  d=b.to_pandas(use_threads=False);d['qfii_qty']=d.end_holding_qty.where(d.shareholder_type.eq('QFII'),0);parts.append(d.groupby(['symbol','report_date','announce_date'],dropna=False).agg(qfii_qty=('qfii_qty','sum'),holder_rows=('seq_no','count'),max_seq=('seq_no','max')).reset_index())
 h=pd.concat(parts,ignore_index=True).groupby(['symbol','report_date','announce_date'],dropna=False).agg(qfii_qty=('qfii_qty','sum'),holder_rows=('holder_rows','sum'),max_seq=('max_seq','max')).reset_index();h['code']=ascode(h.symbol);h.report_date=pd.to_datetime(h.report_date);h.announce_date=pd.to_datetime(h.announce_date);out=[]
 for r in us.itertuples():
  d=h[h.announce_date.lt(r.freeze_date)].sort_values(['report_date','announce_date']).drop_duplicates('code',keep='last').copy();d=d.merge(cap[cap.event_id.eq(r.event_id)][['code','total_shares']],on='code',how='left',validate='1:1');d['qfii']=d.qfii_qty/d.total_shares*100;d.loc[d.max_seq.lt(10)|d.holder_rows.lt(10),'qfii']=np.nan;d['event_id']=r.event_id;out.append(d[['event_id','code','qfii']])
 pd.concat(out,ignore_index=True).to_parquet(T/'us_qfii.parquet',index=False);print('STATIC COMPLETE',flush=True)

def history_block(b):
 outdir=T/'us_history_features';outdir.mkdir(exist_ok=True);dest=outdir/f'{b:03d}.parquet'
 if dest.exists():return b
 paths=sorted((T/'history').glob(f'*_{b:03d}.parquet'));f=pd.concat([pd.read_parquet(p,columns=['code','date','eligible_day','nb_open','day_return','if_delay','amount'])for p in paths],ignore_index=True).sort_values(['code','date']);fr=pd.read_csv(R/'tables/design_events.csv',parse_dates=['freeze_date']);fr=fr[fr.family.eq('US')]
 with np.load(T/'futures_IF.npz')as z:future=pd.Series(np.nansum(z['returns'],axis=1),index=pd.to_datetime(z['dates'],unit='D'));valid=pd.Series(np.isfinite(z['returns']).sum(1),index=future.index)
 f['ifret']=f.date.map(future);f.loc[f.date.map(valid).fillna(0).lt(180),'ifret']=np.nan;out=[]
 for r in fr.itertuples():
  hist=f[f.date.lt(r.freeze_date)&f.eligible_day&f.nb_open].groupby('code',sort=False).tail(60)
  for c,g in hist.groupby('code',sort=False):
   q=g[['day_return','ifret']].dropna();beta=np.cov(q.day_return,q.ifret,ddof=1)[0,1]/np.var(q.ifret,ddof=1)if len(q)>=30 and q.ifret.var()>0 else np.nan;out.append(dict(event_id=r.event_id,code=c,logamount=np.log(g.amount.median())if len(g)>=30 else np.nan,ifbeta=beta,predelay=g.if_delay.mean()if g.if_delay.count()>=30 else np.nan))
 pd.DataFrame(out).to_parquet(dest,index=False);release();return b

def combine():
 dest=T/'all_features.parquet';f=pd.read_parquet(dest);us=f[f.family.eq('US')].copy();cap=pd.read_parquet(T/'valuation.parquet');value=cap[cap.event_id.le(46)][['event_id','code','value']];f=f.merge(value,on=['event_id','code'],how='left',validate='1:1')
 h=pd.concat([pd.read_parquet(p)for p in(T/'us_history_features').glob('*.parquet')],ignore_index=True);hk=pd.concat([pd.read_parquet(p)for p in(T/'daily_hk_features').glob('*.parquet')],ignore_index=True);idx=pd.read_parquet(T/'us_index.parquet');ah=pd.read_csv(P/'R2/tables/AH_listing_history.csv',parse_dates=['hk_listing_date','hk_delisting_date']).drop_duplicates('code');us=us.drop(columns=[c for c in ['value','logcap','analyst','qfii',*RACE,*HK]if c in us]);us=us.merge(cap[['event_id','code','logcap','value']],on=['event_id','code'],how='left',validate='1:1').merge(h,on=['event_id','code'],how='left',validate='1:1').merge(hk,on=['event_id','code'],how='left',validate='1:1').merge(idx,on=['event_id','code'],how='left',validate='1:1').merge(pd.read_parquet(T/'us_analyst.parquet'),on=['event_id','code'],how='left',validate='1:1').merge(pd.read_parquet(T/'us_qfii.parquet'),on=['event_id','code'],how='left',validate='1:1')
 for c in HK:
  for v,lo,hi in [('raw',None,None),('w01',.01,.99),('w005',.005,.995)]:
   if v=='raw':us[c+'__'+v]=us[c]
   else:
    a=us.groupby('event_id')[c].transform(lambda s:s[us.loc[s.index,'pre_age'].ge(60)].quantile(lo));b=us.groupby('event_id')[c].transform(lambda s:s[us.loc[s.index,'pre_age'].ge(60)].quantile(hi));us[c+'__'+v]=us[c].clip(a,b)
 us['ah']=False
 for r in ah.itertuples():us.loc[us.code.eq(r.code)&us.freeze_date.gt(r.hk_listing_date)&(us.freeze_date.lt(r.hk_delisting_date)if pd.notna(r.hk_delisting_date)else True),'ah']=True
 known=us.dose.notna()&us.pre_age.ge(60)&us.logcap.notna()
 for eid,ix in us[known].groupby('event_id').groups.items():rank=us.loc[ix].sort_values(['dose','code']).index;us.loc[rank,'quintile']=np.minimum(4,np.arange(len(rank))*5//len(rank))
 f=pd.concat([f[f.family.ne('US')],us],ignore_index=True);f.to_parquet(dest,index=False);save(f.groupby(['family','event_id'])[['dose',*RACE,*HK]].count().reset_index(),'frozen_feature_coverage.csv');print('COMBINED US',len(us),flush=True)
if __name__=='__main__':globals()[sys.argv[1]]()
