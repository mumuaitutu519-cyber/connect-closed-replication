from common import *
import concurrent.futures as cf,shutil,socket,platform

def initialize():
 lock=json.loads((R/'meta/preregistration_lock.json').read_text());assert lock['sha256']==hashlib.sha256((R/'PREREGISTRATION_R4.md').read_bytes()).hexdigest()
 if (R/'meta/hscei_supplement.csv').exists():
  receipt=json.loads((R/'meta/hscei_supplement_receipt.json').read_text());assert receipt['csv_sha256']==hashlib.sha256((R/'meta/hscei_supplement.csv').read_bytes()).hexdigest()
 # Pin optional sibling caches by hardlink; fallback rebuild reads original files.
 for name in ['history','metrics_daily']:
  dest=T/'r3b_cache'/name;dest.mkdir(parents=True,exist_ok=True)
  for p in (P.parent/'_tmp/282'/name).glob('*.parquet'):
   if not (dest/p.name).exists():
    try:os.link(p,dest/p.name)
    except FileNotFoundError:pass
 for product in ['IF','IH']:
  dest=T/f'futures_{product}.npz'
  if not dest.exists():
   for parent in [T.parent/'282',T.parent/'272',T.parent/'266']:
    if (parent/dest.name).exists():shutil.copy2(parent/dest.name,dest);break
   else:
    # Rebuild from the exact original real-contract archive if sibling caches were cleaned.
    sys.path.insert(0,str(P/'code'));import extract_futures as ex,prepare_futures as pf,multiprocessing as mp
    ex.ROOT=R;ex.TMP=T;pf.ROOT=R;pf.TMP=T
    with cf.ProcessPoolExecutor(max_workers=4,mp_context=mp.get_context('fork')) as pool:list(pool.map(ex.extract,['IF/IF1*.csv','IF/IF2*.csv','IH/IH1*.csv','IH/IH2*.csv']))
    pf.main()
 for p in ['frozen_features_by_event.csv','AH_listing_history.csv']:
  shutil.copy2(P/'R2/tables'/p,R/'meta'/p)
 f=pd.read_csv(R/'meta/frozen_features_by_event.csv',parse_dates=['freeze_date','first_observed_daily','announce_date','report_date','event_start','hk_listing_date','hk_delisting_date','cap_date']);f.to_parquet(T/'r2_features.parquet',index=False)
 import importlib.util
 spec=importlib.util.spec_from_file_location('r1plan',P/'code/estimate.py');e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e);e.ROOT=R;e.SEED=SEED;e.B=B
 for name in ['official_calendar.csv','event_date_map.csv','events.csv']:shutil.copy2(P/'tables'/name,R/'tables'/name)
 e.resampling_plan()
 js(R/'meta/execution_environment.json',dict(host=socket.gethostname(),platform=platform.platform(),workers=4,blas_threads=1,aggregate_rss_limit_bytes=5_000_000_000,network='local existing network; no configured remote M5 SSH entry',seed=SEED))
 files=[P/'tables/exposure_by_event.csv',P/'tables/events.csv',P/'tables/event_date_map.csv',P/'R2/tables/frozen_features_by_event.csv']
 save([dict(path=str(p),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files],'frozen_input_manifest.csv')

def etf_file(path):
 dest=T/'etf_parts'/path.name;dest.parent.mkdir(exist_ok=True)
 if dest.exists():return str(dest)
 selected=[];wanted={'159920.XSHE','513660.XSHG','513600.XSHG','510900.XSHG','513130.XSHG','513180.XSHG'}
 for d in batches(path,['ts','symbol','open','close','amount']):
  d=d[d.symbol.isin(wanted)];
  if len(d):selected.append(d)
 f=pd.concat(selected,ignore_index=True) if selected else pd.DataFrame(columns=['ts','symbol','open','close','amount']);f.to_parquet(dest,index=False);return str(dest)

def etf():
 paths=sorted(p for p in (Q/'cn_etf_1m/full').glob('*.parquet') if p.stem[:4].isdigit() and 2017<=int(p.stem[:4])<=2026)
 with cf.ProcessPoolExecutor(max_workers=4) as pool:parts=list(pool.map(etf_file,paths))
 # Selected six symbols are small; split per year to bound concatenation.
 rows=[];dt=[];rr=[]
 for year in range(2017,2027):
  pp=[pd.read_parquet(p) for p in parts if Path(p).stem.startswith(str(year))];f=pd.concat(pp,ignore_index=True) if pp else pd.DataFrame();del pp
  if f.empty:continue
  f=f.drop_duplicates(['symbol','ts']).sort_values(['ts','symbol']);f['date']=pd.to_datetime(f.ts+28800000,unit='ms').dt.normalize();f=f[f.date.le('2026-10-30')]
  sums=f.groupby(['date','symbol']).amount.sum().reset_index().sort_values(['date','amount','symbol'],ascending=[True,False,True]);chosen=sums.drop_duplicates('date');d=f.merge(chosen[['date','symbol']],on=['date','symbol'],validate='m:1');d['minute']=((d.ts+28800000)//60000%1440).astype(int)
  for row in chosen.itertuples():
   g=d[d.date.eq(row.date)];cl=np.full(241,np.nan);op=cl.copy();m=g.minute.to_numpy();ok=((m>=570)&(m<=690))|((m>=781)&(m<=900));slot=np.where(m<=690,m-570,m-780+120);cl[slot[ok]]=g.close.to_numpy()[ok];op[slot[ok]]=g.open.to_numpy()[ok]
   with np.errstate(all='ignore'):
    r=np.log(cl[1:]/cl[:-1]);opening=op[0] if np.isfinite(op[0]) else op[1];r[0]=np.log(cl[1]/opening);r[120]=np.log(cl[121]/op[121])
   rows.append(dict(date=row.date,symbol=row.symbol,amount=row.amount,valid_minutes=np.isfinite(r).sum(),selection='largest same-day amount among six eligible ETFs; historical dates only'))
   dt.append(np.datetime64(row.date,'D').astype('int64'));rr.append(r)
  release()
 save(rows,'hk_etf_daily_choice.csv');np.savez_compressed(T/'etf_proxy.npz',dates=np.array(dt),returns=np.array(rr))
 etf_candidate_audit();print('ETF',len(rows),flush=True)

def etf_candidate_audit():
 symbols=['159920.XSHE','513660.XSHG','513600.XSHG','510900.XSHG','513130.XSHG','513180.XSHG'];by={s:dict(rows=0,dates=set(),amount=0.) for s in symbols}
 for path in sorted((T/'etf_parts').glob('*.parquet')):
  for d in batches(path,['ts','symbol','amount']):
   for s,g in d.groupby('symbol'):
    z=by[s];z['rows']+=len(g);z['dates'].update(pd.to_datetime(g.ts+28800000,unit='ms').dt.normalize());z['amount']+=g.amount.sum()
 out=[]
 for s,z in by.items():out.append(dict(symbol=s,minute_rows=z['rows'],days=len(z['dates']),first=min(z['dates']) if z['dates'] else pd.NaT,last=max(z['dates']) if z['dates'] else pd.NaT,total_amount=z['amount'],status='AVAILABLE' if z['rows'] else 'SOURCE_ABSENT'))
 save(out,'hk_etf_candidate_coverage.csv')

def holdings():
 cal=pd.read_csv(P/'tables/official_calendar.csv',parse_dates=['date']);norm=cal.loc[cal.nb_open,'date'].to_numpy('datetime64[ns]');full=pd.DatetimeIndex(pd.read_csv(P/'meta/actual_full_calendar.csv',parse_dates=['date']).date);pieces=[]
 for d in batches(Q/'cn_hsgt/hk_hold/full/all.parquet',['trade_date','ts_code','ratio']):
  d=d[d.ts_code.str.endswith(('.SH','.SZ'))].copy();d['date']=pd.to_datetime(d.trade_date);pieces.append(d[['ts_code','date','ratio']].rename(columns={'ts_code':'code'}))
 h=pd.concat(pieces,ignore_index=True).drop_duplicates(['code','date']);del pieces
 dup=h.duplicated(['code','date']);assert not dup.any();h['quarter']=h.date.dt.to_period('Q');pre=h[h.date.le('2024-08-16')];snap=[]
 for quarter,g in h.groupby('quarter'):
  end=quarter.end_time.normalize();z=g[g.date.eq(g.date.max())]
  # Only use completed quarter-end snapshots, not current partial quarter.
  expected=full[full<=end][-1] if (full<=end).any() else pd.NaT
  if z.date.iloc[0]!=expected:continue
  i=np.searchsorted(norm,np.datetime64(end),side='right')+4
  if i>=len(norm):continue
  z=z.copy();z['available_date']=pd.Timestamp(norm[i])+pd.Timedelta(days=1);snap.append(z)
 q=pd.concat(snap,ignore_index=True);q.to_parquet(T/'quarter_holdings.parquet',index=False)
 orig=pd.read_parquet(T/'r2_features.parquet');out=[];audit=[]
 last=pre[pre.date.eq('2024-08-16')].set_index('code').ratio
 for ev in freezes().itertuples():
  e=orig[orig.event_id.eq(ev.event_id)][['event_id','code','eligible','dose']].copy();hist=q[q.available_date.lt(ev.freeze_date)];latest=hist.assign(ex=hist.code.str[-2:]).groupby('ex').date.max();hist=hist[hist.date.eq(hist.code.str[-2:].map(latest))].drop_duplicates('code',keep='last').set_index('code');e['dose_quarter']=e.code.map(hist.ratio);e.loc[e.dose_quarter.isna()&e.eligible.eq(0),'dose_quarter']=0.;e['quarter_date']=e.code.map(hist.date);e['quarter_available']=e.code.map(hist.available_date);e['dose_aug16']=e.code.map(last) if ev.freeze_date>pd.Timestamp('2024-08-16') else np.nan
  if ev.freeze_date>pd.Timestamp('2024-08-16'):e.loc[e.dose_aug16.isna()&e.eligible.eq(0),'dose_aug16']=0.
  assert e.quarter_available.dropna().lt(ev.freeze_date).all();out.append(e);audit.append(dict(event_id=ev.event_id,freeze_date=ev.freeze_date,quarter_date=e.quarter_date.max(),available=e.quarter_available.max(),quarter_known=e.dose_quarter.notna().sum(),aug16_known=e.dose_aug16.notna().sum()))
 pd.concat(out,ignore_index=True).to_parquet(T/'doses.parquet',index=False);save(audit,'quarter_dose_audit.csv')
 # Persistence uses observed pairs only; output both full observed snapshot and baseline positive holders.
 dates={d:g.set_index('code').ratio for d,g in pre.groupby('date')};records=[]
 for quarter,g in pre.groupby('quarter'):
  end=quarter.end_time.normalize()
  if end>pd.Timestamp('2024-08-16'):continue
  anchor=full[full<=end][-1];base=dates.get(anchor)
  if base is None:continue
  pos=full.get_loc(anchor)
  for horizon in [1,20,40,60,90]:
   if pos+horizon>=len(full):continue
   target=full[pos+horizon];later=dates.get(target)
   if later is None:continue
   z=pd.concat([base.rename('before'),later.rename('after')],axis=1).dropna()
   for group,v in [('observed_pairs',z),('positive_at_quarter',z[z.before.gt(0)])]:
    records.append(dict(quarter=str(quarter),anchor=anchor,target=target,horizon=horizon,group=group,n=len(v),pearson=v.before.corr(v.after),spearman=v.before.corr(v.after,method='spearman'),mean_abs_change_pp=(v.after-v.before).abs().mean()))
 save(records,'holding_persistence_by_quarter.csv');s=pd.DataFrame(records);save(s.groupby(['group','horizon']).agg(quarters=('quarter','nunique'),mean_pair_n=('n','mean'),pearson=('pearson','mean'),spearman=('spearman','mean'),mean_abs_change_pp=('mean_abs_change_pp','mean')).reset_index(),'holding_persistence_summary.csv')
 print('HOLDINGS COMPLETE',len(h),flush=True)

def first_holders():
 hh=[]
 for d in batches(Q/'cn_top_holders/top10/full/all.parquet',['symbol','report_date','announce_date','seq_no','shareholder_rank','shareholder_name','shareholder_type']):
  d=d[d.shareholder_rank.eq(1)].copy();d['code']=code(d.symbol);hh.append(d)
 holders=pd.concat(hh,ignore_index=True);holders.report_date=pd.to_datetime(holders.report_date);holders.announce_date=pd.to_datetime(holders.announce_date);typ=holders.shareholder_type.fillna('');holders['foreign_first']=np.where(typ.str.contains('外资|外商|境外|QFII',case=False),1.,np.where(typ.str.contains('国有|国资|境内|集体|国家队|社保'),0.,np.nan));save(holders.groupby('shareholder_type',dropna=False).agg(first_holder_rows=('code','size'),classified_rows=('foreign_first','count')).reset_index(),'first_holder_type_audit.csv');save(holders[holders.foreign_first.notna()].drop(columns='shareholder_name'),'first_holder_classified_records.csv');return holders

def repair_first_holder():
 holders=first_holders();orig=pd.read_parquet(T/'r2_features.parquet');intl=pd.read_parquet(T/'international.parquet');new=[];audits=[]
 for ev in freezes().itertuples():
  v=holders[holders.announce_date.lt(ev.freeze_date)&holders.report_date.lt(ev.freeze_date)].sort_values(['report_date','announce_date','seq_no']).drop_duplicates('code',keep='last').set_index('code');d=orig[orig.event_id.eq(ev.event_id)][['code','event_id']].copy();d['foreign_first']=d.code.map(v.foreign_first);new.append(d);known=v[v.foreign_first.notna()].reset_index();known['event_id']=ev.event_id;known['freeze_date']=ev.freeze_date;assert known.announce_date.lt(ev.freeze_date).all();audits.append(known)
 new=pd.concat(new,ignore_index=True);save(pd.concat(audits,ignore_index=True),'first_holder_freeze_audit.csv');intl=intl.drop(columns='foreign_first').merge(new,on=['code','event_id'],validate='1:1');intl.to_parquet(T/'international.parquet',index=False)
 old=pd.read_parquet(T/'features.parquet');old.to_parquet(T/'features_before_first_holder_repair.parquet',index=False);f=old.copy();by=new.set_index(['event_id','code']).foreign_first;f['foreign_first']=pd.MultiIndex.from_frame(f[['event_id','code']]).map(by).to_numpy();checks=[]
 for c in old.columns:
  if c=='foreign_first':continue
  assert old[c].equals(f[c]),c;checks.append(dict(feature=c,status='UNCHANGED'))
 assert set(f.foreign_first.dropna()).issubset({0.,1.});save(checks,'first_holder_repair_unchanged_features.csv');f.to_parquet(T/'features.parquet',index=False);f.to_csv(R/'tables/frozen_features_by_event.csv',index=False);save(f.groupby('event_id')[['dose',*CONTINUOUS,'intl_any','foreign_first','bh_listed']].count().reset_index(),'feature_coverage.csv')
 print('FIRST_HOLDER_RANK_REPAIRED',f.foreign_first.notna().sum(),flush=True)

def international():
 # Report dates alone cannot timestamp revenue-segment records. Financial statements supply notice dates.
 inc=pd.read_parquet(Q/'cn_fin_statements/income/full/all.parquet',columns=['symbol','report_date','notice_date','UPDATE_DATE','OPERATE_INCOME','TOTAL_OPERATE_INCOME']);inc['code']=code(inc.symbol);inc.report_date=pd.to_datetime(inc.report_date);inc.notice_date=pd.to_datetime(inc.notice_date);inc['update_date']=pd.to_datetime(inc.UPDATE_DATE,errors='coerce');inc['known_date']=inc[['notice_date','update_date']].max(axis=1);inc=inc[inc.report_date.dt.month.eq(12)&inc.report_date.dt.day.eq(31)&inc.known_date.ge(inc.report_date)];inc=inc.sort_values('known_date').drop_duplicates(['code','report_date'],keep='last')
 # Last available notice is conservative when source has subsequent restatements; do not date a revised value back to its first release.
 seg=pd.read_parquet(Q/'cn_revenue_segment/full/all.parquet',columns=['symbol','report_date','category_type','main_business_composition','operating_revenue','revenue_ratio']);seg['code']=code(seg.symbol);seg.report_date=pd.to_datetime(seg.report_date);seg=seg[seg.code.isin(set(universe().code))&seg.report_date.dt.month.eq(12)&seg.category_type.str.contains('地区|地域|地理',na=False)].drop_duplicates();save(seg.groupby('main_business_composition').agg(rows=('code','size'),stocks=('code','nunique')).reset_index(),'international_segment_labels.csv')
 broad=r'境外|海外|国外|港澳台|香港|澳门|台湾|foreign|overseas|international|outside china|outside prc';country=r'美国|加拿大|墨西哥|巴西|阿根廷|美洲|欧洲|德国|英国|法国|意大利|西班牙|俄罗斯|非洲|南非|澳大利亚|新西兰|大洋洲|日本|韩国|印度|印尼|印度尼西亚|越南|泰国|马来西亚|新加坡|菲律宾|中东|阿联酋|沙特|巴基斯坦|孟加拉|土耳其';summary=[]
 for (c,dt),g in seg.groupby(['code','report_date']):
  labels=g.main_business_composition.astype(str);hit=labels.str.contains(broad,case=False,regex=True);aggregate=labels.str.fullmatch(r'.*(?:境外|海外|国外|港澳台)(?:地区|市场|业务|收入|销售|合计|小计|部分|主营业务)?',case=False);v=g.loc[aggregate,'operating_revenue'].dropna();status='NO_EXPLICIT_OVERSEAS_LABEL';foreign=np.nan
  if len(v)==1:foreign=float(v.iloc[0]);status='EXPLICIT_AGGREGATE'
  elif len(v)>1:
   if np.allclose(v,v.iloc[0],rtol=1e-6):foreign=float(v.iloc[0]);status='DUPLICATE_EQUIVALENT_AGGREGATE'
   else:status='AMBIGUOUS_OVERLAPPING_AGGREGATES'
  elif hit.any() or labels.str.contains(country,regex=True).any():
   # Named overseas regions are accepted only if no broad parent labels overlap.
   named=hit|labels.str.contains(country,regex=True);parents=[('欧洲','德国|英国|法国|意大利|西班牙'),('美洲','美国|加拿大|墨西哥|巴西|阿根廷'),('北美','美国|加拿大|墨西哥'),('南美','巴西|阿根廷'),('大洋洲','澳大利亚|新西兰'),('非洲','南非')];overlap=any(labels.str.contains(parent,regex=True).any() and labels.str.contains(child,regex=True).any() for parent,child in parents)
   if overlap:status='AMBIGUOUS_PARENT_CHILD_FOREIGN_REGIONS'
   else:foreign=float(g.loc[named,'operating_revenue'].sum(min_count=1));status='EXPLICIT_NAMED_OVERSEAS_COMPONENTS'
  # Without an explicit foreign component, zero is assigned only if domestic
  # segment revenue reconciles to annual total below. Unknown regions stay unknown.
  summary.append(dict(code=c,report_date=dt,foreign_revenue=foreign,segment_rows=len(g),keyword_hits=int(hit.sum()),rule=status))
 s=pd.DataFrame(summary).merge(inc[['code','report_date','notice_date','update_date','known_date','OPERATE_INCOME','TOTAL_OPERATE_INCOME']],on=['code','report_date'],how='left',validate='1:1');s['denominator']=s.OPERATE_INCOME.where(s.OPERATE_INCOME.gt(0),s.TOTAL_OPERATE_INCOME)
 domestic=seg[seg.main_business_composition.str.fullmatch(r'(?:境内|国内|中国大陆|大陆地区)(?:地区|市场|业务|收入|销售|合计|小计|部分)?',na=False)].groupby(['code','report_date']).operating_revenue.max();s['domestic_revenue']=[domestic.get((c,dt),np.nan) for c,dt in zip(s.code,s.report_date)];zero=s.foreign_revenue.isna()&s.rule.eq('NO_EXPLICIT_OVERSEAS_LABEL')&((s.domestic_revenue/s.denominator-1).abs()<.001);s.loc[zero,'foreign_revenue']=0.;s.loc[zero,'rule']='DOMESTIC_RECONCILES_ANNUAL_TOTAL';s['intl_share']=s.foreign_revenue/s.denominator;bad=~s.intl_share.between(0,1);s.loc[bad,'intl_share']=np.nan;s['intl_any']=np.where(s.intl_share.notna(),s.intl_share.gt(0).astype(float),np.nan);save(s,'international_annual_sources.csv');save([dict(universe='annual stock records with regional segments',records=len(s),keyword_hit_records=s.keyword_hits.gt(0).sum(),keyword_hit_rate=s.keyword_hits.gt(0).mean(),valid_share_records=s.intl_share.notna().sum(),valid_share_rate=s.intl_share.notna().mean(),known_publication_records=s.known_date.notna().sum())],'international_detection_rates.csv')
 orig=pd.read_parquet(T/'r2_features.parquet');out=[]
 # Foreign first shareholder: only explicitly labelled foreign classifications/QFII, unknown "other" remains unknown.
 holders=first_holders()
 for ev in freezes().itertuples():
  d=orig[orig.event_id.eq(ev.event_id)][['event_id','code','industry','freeze_date','hk_listing_date','hk_delisting_date','pre_age']].copy();ann=inc[inc.known_date.lt(ev.freeze_date)].sort_values(['report_date','known_date']).drop_duplicates('code',keep='last')[['code','report_date','notice_date','update_date','known_date']];ann=ann.merge(s[['code','report_date','intl_share','intl_any','rule']],on=['code','report_date'],how='left',validate='1:1');d=d.merge(ann,on='code',how='left',validate='1:1');assert d.known_date.dropna().lt(ev.freeze_date).all();d['h_listed']=(d.hk_listing_date.lt(ev.freeze_date)&(d.hk_delisting_date.isna()|d.hk_delisting_date.gt(ev.freeze_date))).astype(float)
  v=holders[holders.announce_date.lt(ev.freeze_date)&holders.report_date.lt(ev.freeze_date)].sort_values(['report_date','announce_date','seq_no']).drop_duplicates('code',keep='last').set_index('code');d['foreign_first']=d.code.map(v.foreign_first);d['bh_listed']=np.nan # B share historical mapping lacks verified listing effective dates.
  industry=d[d.pre_age.ge(60)].groupby('industry').intl_share.median().dropna();med=industry.median();d['industry_intl']=d.industry.map(industry);d['export_industry']=np.where(d.industry_intl.notna(),d.industry_intl.gt(med).astype(float),np.nan);out.append(d.drop(columns=['hk_listing_date','hk_delisting_date','industry','freeze_date','pre_age']))
 pd.concat(out,ignore_index=True).to_parquet(T/'international.parquet',index=False)
 # Analyst source timing audit, including all cninfo observation partitions.
 rec=[]
 for p in (Q/'cn_analyst_rating').rglob('*.parquet'):
  pf=pq.ParquetFile(p);cols=pf.schema_arrow.names;datecol='report_date' if 'report_date' in cols else 'declare_date';mn=None;mx=None
  for d in batches(p,[datecol]):
   dates=pd.to_datetime(d[datecol],errors='coerce');mn=min(mn,dates.min()) if mn is not None else dates.min();mx=max(mx,dates.max()) if mx is not None else dates.max()
  rec.append(dict(path=str(p),date_column=datecol,earliest=mn,latest=mx,usable_for_historical_365day=True,archive='R2_report_rc' if 'report_rc' in str(p) else 'CNINFO_declared_date_archive'))
 e=pd.read_parquet(Q/'cn_estimates/full/all.parquet',columns=['fiscal_year','updated_at']);rec.append(dict(path=str(Q/'cn_estimates/full/all.parquet'),date_column='updated_at',earliest=e.updated_at.min(),latest=e.updated_at.max(),fiscal_year_min=e.fiscal_year.min(),usable_for_historical_365day=False,reason='Fiscal year is forecast target; only 2026 snapshot update timestamps; no historical report/organisation records'))
 save(rec,'analyst_source_audit.csv');save([dict(specification='B_or_H_listing',status='B_HISTORY_UNAVAILABLE',reason='Issuer links available; verified historical B listing effective dates unavailable; H estimated separately'),dict(specification='HK_closed_NB_open_placebo',status='NO_EVENTS',reason='HKEX Northbound rules require both markets open'),dict(specification='Foreign_first_holder',status='SPARSE_EXPLICIT_CLASSIFICATION',reason='Actual shareholder_rank=1; only309/411521 source records explicitly classified;356 frozen universe stock-episodes known')],'source_status.csv')
 c=pd.read_csv(P/'tables/official_calendar.csv',parse_dates=['date']);v=c[c.a_open&c.nb_open&c.hk_holiday.eq(True)];save(v,'hk_closed_nb_open_dates.csv');assert v.empty
 print('INTERNATIONAL COMPLETE',len(s),flush=True)

def analyst():
 parts=[];receipts=[]
 for p in sorted((Q/'cn_analyst_rating/cninfo_rating_obs/full').glob('*.parquet')):
  for d in batches(p,['seccode','declare_date','org']):
   d['code']=code(d.seccode);d['report_date']=pd.to_datetime(d.declare_date,errors='coerce');d=d[d.code.isin(set(universe().code))&d.report_date.notna()&d.org.notna()];parts.append(d[['code','report_date','org']])
 a=pd.concat(parts,ignore_index=True).drop_duplicates();start=a.report_date.min();orig=pd.read_parquet(T/'r2_features.parquet');out=[];summary=[]
 save(a.assign(year=a.report_date.dt.year).groupby('year').agg(rows=('code','size'),stocks=('code','nunique'),organisations=('org','nunique'),first=('report_date','min'),last=('report_date','max')).reset_index(),'cninfo_analyst_archive_coverage.csv')
 for ev in freezes().itertuples():
  low=ev.freeze_date-pd.Timedelta(days=365);hist=a[a.report_date.ge(low)&a.report_date.lt(ev.freeze_date)];counts=hist.groupby('code').org.nunique();d=orig[orig.event_id.eq(ev.event_id)][['code','event_id','analyst']].copy();d['analyst_r2_original']=d.analyst;d['analyst_source']=np.where(d.analyst.notna(),'R2_report_rc','MISSING');candidate=np.log1p(d.code.map(counts).fillna(0)) if low>=start else pd.Series(np.nan,index=d.index);fill=d.analyst.isna()&candidate.notna();d.loc[fill,'analyst']=candidate[fill];d.loc[fill,'analyst_source']='CNINFO_declared_date_archive';d['analyst_history_end']=hist.report_date.max();d['analyst_history_start']=low;assert d.analyst_history_end.dropna().lt(ev.freeze_date).all();out.append(d);summary.append(dict(event_id=ev.event_id,freeze_date=ev.freeze_date,cninfo_earliest=start,old_known=d.analyst_r2_original.notna().sum(),extended_known=d.analyst.notna().sum(),filled=fill.sum(),source_policy='Keep every existing R2 value; use CNINFO full 365-day window only for previously missing values'))
 pd.concat(out,ignore_index=True).to_parquet(T/'extended_analyst.parquet',index=False);save(summary,'analyst_extension_summary.csv');print('ANALYST EXTENDED',start,sum(r['filled'] for r in summary),flush=True)

def holding_dates_audit():
 observed=set()
 for d in batches(Q/'cn_hsgt/hk_hold/full/all.parquet',['trade_date']):observed.update(pd.Timestamp(v) for v in pd.to_datetime(d.trade_date).unique())
 full=pd.DatetimeIndex(pd.read_csv(P/'meta/actual_full_calendar.csv',parse_dates=['date']).date);rows=[]
 for quarter in pd.period_range('2017Q1','2024Q2',freq='Q'):
  end=quarter.end_time.normalize();anchor=full[full<=end][-1];pos=full.get_loc(anchor)
  for h in [1,20,40,60,90]:
   target=full[pos+h] if pos+h<len(full) else pd.NaT;status='AVAILABLE'
   if anchor not in observed:status='QUARTER_END_SNAPSHOT_MISSING'
   elif pd.isna(target) or target>pd.Timestamp('2024-08-16'):status='BEYOND_LAST_DAILY_DISCLOSURE'
   elif target not in observed:status='TARGET_A_DAY_SNAPSHOT_MISSING'
   rows.append(dict(quarter=str(quarter),anchor=anchor,horizon=h,target=target,status=status))
 save(rows,'holding_persistence_date_support.csv')

if __name__=='__main__':globals()[sys.argv[1]]()
