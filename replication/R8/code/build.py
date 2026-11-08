from common import *
import concurrent.futures as cf,multiprocessing as mp,shutil

# Keep frozen original controls intact; extra placebo families need only publicly frozen dose.
def design():
 receipts=pd.read_csv(R/'tables/minute_day_receipts.csv',parse_dates=['date']);receipts['if_rv']=receipts.date.map(valid_if_variance());save(receipts,'minute_day_receipts.csv');cal=pd.read_csv(P/'tables/official_calendar.csv',parse_dates=['date']);w=pd.read_csv(P/'R6/typhoon_calendar.csv',parse_dates=['date']);rc=receipts.merge(cal[['date','a_open','nb_open']],on='date').sort_values('date');normal=rc[rc.a_open&rc.nb_open&~rc.date.isin(w.loc[w.included,'date'])].copy();parts=[]
 main=pd.read_csv(P/'tables/event_date_map.csv',parse_dates=['date','anchor']);main['family']='main';main=main.merge(features()[['event_id','freeze_date']].drop_duplicates(),on='event_id');parts.append(main[['event_id','date','anchor','closed','freeze_date','family']]);ad=pd.DatetimeIndex(cal.loc[cal.a_open,'date']);pos={d:i for i,d in enumerate(ad)};classes=[];support=[]
 for j,(pct,condition) in enumerate([(30,'both'),(40,'both'),(30,'rv'),(40,'rv')]):
  family=f'quiet{pct}_{condition}';q=normal.copy()
  for c in ['market_amount','if_rv']:q[c+'_threshold']=q[c].expanding(min_periods=60).quantile(pct/100).shift(1)
  q['quiet']=q.if_rv.lt(q.if_rv_threshold)&q.if_rv.gt(0)
  if condition=='both':q['quiet']&=q.market_amount.lt(q.market_amount_threshold)
  q['family']=family;classes.append(q);qd=q.loc[q.quiet,'date'].tolist();episodes=[]
  for d in qd:
   if not episodes or pos[d]>pos[episodes[-1][-1]]+1:episodes.append([d])
   else:episodes[-1].append(d)
  allowed=set(q.loc[~q.quiet,'date']);rows=[]
  for k,days in enumerate(episodes,1):
   pre=[d for d in ad if d<days[0]and d in allowed][-5:];post=[d for d in ad if d>days[-1]and d in allowed][:5]
   if len(pre)<5 or len(post)<5:continue
   for d in pre+days+post:rows.append(dict(event_id=20000+j*1000+k,date=d,anchor=days[0],closed=d in days,freeze_date=min(pre),family=family))
  z=pd.DataFrame(rows);z['distance']=(z.date-z.anchor).abs().dt.days;z=z.sort_values(['date','distance','anchor']).drop_duplicates('date');parts.append(z[parts[0].columns]);support.append(dict(family=family,quantile=pct,condition=condition,classified_quiet_days=len(qd),retained_quiet_days=int(z.closed.sum()),events=z.loc[z.closed,'event_id'].nunique(),n=len(z),stocks=np.nan,minimum30=len(qd)>=30))
 # US audited with exact original historical freezes, no new controls inferred.
 us=pd.read_csv(P/'R7/tables/design_map.csv',parse_dates=['date','anchor','freeze_date']);parts.append(us.loc[us.family.eq('US'),parts[0].columns]);mapping=pd.concat(parts,ignore_index=True);mapping.closed=mapping.closed.astype(bool);mapping.to_csv(R/'tables/design_map.csv',index=False)
 ev=[]
 for (family,eid),g in mapping.groupby(['family','event_id']):ev.append(dict(family=family,event_id=eid,start=g.anchor.iloc[0],end=g.loc[g.closed,'date'].max(),freeze_date=g.freeze_date.iloc[0],n_closed_days=int(g.closed.sum()),dates=len(g)))
 save(ev,'design_events.csv');save(pd.concat(classes,ignore_index=True).assign(n=1,stocks=np.nan,events=np.nan),'quiet_classification.csv');save(support,'quiet_definition_support.csv')
 print('DESIGN',support,flush=True)

def extra_features():
 if (T/'all_features.parquet').exists():return
 import importlib.util
 spec=importlib.util.spec_from_file_location('origdesign',P/'R7/code/design.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);mod.exposures()
 a=features();a['family']='main';b=pd.read_parquet(T/'extra_features.parquet');b=b[b.family.ne('US')];us=pd.read_parquet(P/'R7/data/frozen_US_controls.parquet');us['family']='US'
 for c in HK:us[c+'__raw']=us[c]
 f=pd.concat([a,b,us],ignore_index=True);f.to_parquet(T/'all_features.parquet',index=False);del f,a,b,us;release()

def partition():
 src=T/'all_features.parquet';codes=universe().code.tolist();mapping={c:i//50 for i,c in enumerate(codes)};folder=T/'feature_blocks';folder.mkdir(exist_ok=True);marker=folder/'COMPLETE.json';identity=dict(bytes=src.stat().st_size,mtime_ns=src.stat().st_mtime_ns)
 if marker.exists()and json.loads(marker.read_text())==identity:return
 writers={};buffers={};counts={}
 def flush(b):
  tab=pa.concat_tables(buffers.pop(b));counts[b]=0
  if b not in writers:writers[b]=pq.ParquetWriter(folder/f'{b:03d}.parquet',tab.schema,compression='zstd')
  writers[b].write_table(tab,row_group_size=8192)
 try:
  pf=pq.ParquetFile(src)
  for batch in pf.iter_batches(batch_size=8192,use_threads=False):
   tab=pa.Table.from_batches([batch]);ids=tab.column('code').to_pandas().map(mapping).to_numpy()
   for b in np.unique(ids):
    b=int(b);part=tab.filter(pa.array(ids==b));buffers.setdefault(b,[]).append(part);counts[b]=counts.get(b,0)+len(part)
    if counts[b]>=8192:flush(b)
  for b in list(buffers):flush(b)
  pf.close()
 finally:
  for w in writers.values():w.close()
 writers.clear();buffers.clear();js(marker,identity);release()

def pack(year):
 dest=T/'history';dest.mkdir(exist_ok=True);marker=dest/f'{year}.done'
 if marker.exists():return year
 ids={c:i//50 for i,c in enumerate(universe().code)};writers={}
 try:
  for p in sorted((T/'daily').glob(f'{year}*.parquet')):
   f=pd.read_parquet(p)
   for c in f:
    if c.startswith('mom')and c.endswith('_n'):f[c]=f[c].astype(float)
   f['block']=f.code.map(ids)
   for b,g in f.groupby('block'):
    b=int(b);tab=pa.Table.from_pandas(g.drop(columns='block'),preserve_index=False)
    if b not in writers:writers[b]=pq.ParquetWriter(dest/f'{year}_{b:03d}.parquet',tab.schema,compression='zstd')
    writers[b].write_table(tab)
 finally:
  for w in writers.values():w.close()
 marker.write_text('done');release();return year

PANEL_LIMIT=None
def init_panel(lim):
 global PANEL_LIMIT
 PANEL_LIMIT=lim
def bounded_panel(b):
 with PANEL_LIMIT:
  result=panel_block(b);release();return result
def panel_block(b):
 dest=T/'panel'/f'{b:03d}.parquet';marker=dest.with_suffix('.audit.json')
 if dest.exists()and marker.exists():return json.loads(marker.read_text())
 files=sorted((T/'history').glob(f'*_{b:03d}.parquet'));f=pd.concat([pd.read_parquet(p)for p in files],ignore_index=True).sort_values(['code','date']).reset_index(drop=True);mapping=pd.read_csv(R/'tables/design_map.csv',parse_dates=['date','anchor','freeze_date']);feat=pd.read_parquet(T/'feature_blocks'/f'{b:03d}.parquet');out=f[f.eligible_day&f.date.isin(mapping.date)].merge(mapping[['event_id','date','anchor','closed','family']],on='date',validate='m:m').merge(feat.drop(columns='family'),on=['event_id','code'],validate='m:1');audit=[]
 # Pool before freeze only if <60 historical valid normal stock days; exact historical quantile.
 for metric in METRICS:
  for variant,lo,hi in [('w01',.01,.99),('w005',.005,.995)]:
   looks=[]
   for c,g in f.groupby('code',sort=False):
    z=g.loc[g.eligible_day&g.nb_open,metric].replace([np.inf,-np.inf],np.nan).dropna();ql=z.expanding(min_periods=60).quantile(lo);qh=z.expanding(min_periods=60).quantile(hi);nn=pd.Series(np.arange(1,len(z)+1),index=z.index);a=ql.reindex(g.index).ffill();bb=qh.reindex(g.index).ffill();n=nn.reindex(g.index).ffill().fillna(0);a.loc[z.index]=ql.shift(1);bb.loc[z.index]=qh.shift(1);n.loc[z.index]=nn.shift(1,fill_value=0);looks.append(pd.DataFrame(dict(code=c,date=g.date,lo=a,hi=bb,npast=n)))
   o=out[['code','date','event_id',metric]].merge(pd.concat(looks),on=['code','date'],validate='m:1');fb=o.npast.lt(60)|o.lo.isna()|o.hi.isna()
   pool=pd.read_csv(R/'tables'/f'pooled_{metric}.csv').set_index('event_id');l='q01'if variant=='w01'else'q005';h='q99'if variant=='w01'else'q995';o.loc[fb,'lo']=o.loc[fb,'event_id'].map(pool[l]);o.loc[fb,'hi']=o.loc[fb,'event_id'].map(pool[h]);out[f'{metric}__{variant}']=o[metric].clip(o.lo,o.hi).to_numpy();audit.append(dict(block=b,metric=metric,variant=variant,n=len(o),stocks=out.code.nunique(),events=out.event_id.nunique(),fallback=int(fb.sum()),missing_threshold=int((o.lo.isna()|o.hi.isna()).sum())))
 # Next-day raw and exact history-based winsorized returns are mapped on original source dates.
 full=pd.DatetimeIndex(pd.read_csv(P/'meta/actual_full_calendar.csv',parse_dates=['date']).date);back=dict(zip(full[1:],full[:-1]));nexty=f[['code','date','open30_return','eligible_day']].copy();nexty['source_date']=nexty.date.map(back)
 for v,lo,hi in [('w01',.01,.99),('w005',.005,.995)]:
  pieces=[]
  for c,g in f.groupby('code',sort=False):
   z=g.loc[g.eligible_day&g.nb_open,'open30_return'].dropna();a=z.expanding(min_periods=60).quantile(lo);bb=z.expanding(min_periods=60).quantile(hi);l=a.reindex(g.index).ffill();h=bb.reindex(g.index).ffill();l.loc[z.index]=a.shift(1);h.loc[z.index]=bb.shift(1);pieces.append(pd.DataFrame(dict(code=c,date=g.date,lo=l,hi=h)))
  nxt=nexty.merge(pd.concat(pieces),on=['code','date']);nexty['next_'+v]=nxt.open30_return.clip(nxt.lo,nxt.hi).to_numpy();nexty['lo_'+v]=nxt.lo.to_numpy();nexty['hi_'+v]=nxt.hi.to_numpy()
 nexty=nexty[nexty.eligible_day].rename(columns={'date':'nextdate','source_date':'date','open30_return':'next_raw'});out=out.merge(nexty[['code','date','nextdate','next_raw','next_w01','next_w005','lo_w01','hi_w01','lo_w005','hi_w005']],on=['code','date'],how='left',validate='m:1')
 pool=pd.read_csv(R/'tables/pooled_open30_return.csv').set_index('event_id')
 for v,l,h in [('w01','q01','q99'),('w005','q005','q995')]:
  lo=out['lo_'+v].fillna(out.event_id.map(pool[l]));hi=out['hi_'+v].fillna(out.event_id.map(pool[h]));out['next_'+v]=out.next_raw.clip(lo,hi)
 out=out.drop(columns=['lo_w01','hi_w01','lo_w005','hi_w005']);out['code']=pd.Categorical(out.code);out.to_parquet(dest.with_suffix('.partial'),index=False,compression='zstd');dest.with_suffix('.partial').replace(dest);js(marker,audit);del f,out;release();return audit

def main():
 design();extra_features()
 # Reuse exact prefix pooling implementation for all new event freezes, six workers.
 import importlib.util,subprocess
 spec=importlib.util.spec_from_file_location('pooling',P/'R7/code/panel.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
 subprocess.run(['c++','-O3','-std=c++17',str(R/'code/exact_prefix_quantiles.cpp'),'-o',str(T/'exact_prefix_quantiles')],check=True)
 ctx=mp.get_context('spawn')
 with cf.ProcessPoolExecutor(max_workers=6,mp_context=ctx)as pool:
  for r in pool.map(pack,range(2017,2027)):print('PACK',r,flush=True)
 # pool_parts/pooled must be importable through the local module for spawn.
 with cf.ProcessPoolExecutor(max_workers=6,mp_context=ctx)as pool:list(pool.map(pool_parts,range(2017,2027)))
 with cf.ProcessPoolExecutor(max_workers=6,mp_context=ctx)as pool:list(pool.map(pooled,METRICS))
 partition();release();(T/'panel').mkdir(exist_ok=True);audit=[]
 nj=int(np.ceil(len(universe())/50))
 for first in range(0,nj,6):
  with cf.ProcessPoolExecutor(max_workers=6,mp_context=ctx,initializer=init_panel,initargs=(ctx.Semaphore(3),))as pool:
   for r in pool.map(bounded_panel,range(first,min(first+6,nj))):
    if isinstance(r,list):audit.extend(r)
    print('PANEL',len(audit),flush=True)
 save(audit,'winsor_audit.csv')

# Copied pooling helpers resolve local common and preserve exact old algorithm.

def pool_parts(year):
 dest=T/'pool_parts';dest.mkdir(exist_ok=True);marker=dest/f'{year}.npz'
 if marker.exists():return year,'CACHED'
 codes=pd.Index(pd.read_parquet(T/'universe.parquet').code);first=np.full((len(METRICS),len(codes)),np.iinfo(np.int32).max,dtype=np.int32);handles=[(dest/f'{year}_{m}.bin').open('wb')for m in METRICS];counts=np.zeros(len(METRICS),np.int64);rows=[];days=[]
 try:
  for path in sorted((T/'daily').glob(f'{year}*.parquet')):
   dt=int(np.datetime64(pd.Timestamp(path.stem),'D').astype('int64'));d=pd.read_parquet(path,columns=['code','eligible_day','nb_open',*METRICS]);ids=codes.get_indexer(d.code);eligible=d.eligible_day.to_numpy()&d.nb_open.to_numpy();vals=d[METRICS].to_numpy(float)
   for j,m in enumerate(METRICS):
    good=eligible&np.isfinite(vals[:,j]);v=vals[good,j];handles[j].write(v.tobytes());counts[j]+=len(v);ii=ids[good];first[j,ii]=np.minimum(first[j,ii],dt)
   days.append(dt);rows.append(counts.copy())
 finally:
  for h in handles:h.close()
 np.savez_compressed(marker,days=np.array(days,np.int32),counts=np.array(rows,np.int64),first=first);release();return year,len(days)

def pooled(metric):
 import shutil
 dest=T/'pool_parts';p=T/f'pooled_{metric}.bin';j=METRICS.index(metric);fr=pd.read_parquet(T/'all_features.parquet',columns=['event_id','freeze_date']).drop_duplicates().sort_values('freeze_date');records={};first=np.full(len(pd.read_parquet(T/'universe.parquet')),np.iinfo(np.int32).max,dtype=np.int32)
 with p.open('wb')as dst:
  for year in range(2017,2027):
   with(dest/f'{year}_{metric}.bin').open('rb')as src:shutil.copyfileobj(src,dst,length=1024*1024)
   with np.load(dest/f'{year}.npz')as z:records[year]=(z['days'].copy(),z['counts'][:,j].copy());first=np.minimum(first,z['first'][j])
 requests=[]
 for e in fr.itertuples():
  cutoff=int(np.datetime64(e.freeze_date,'D').astype('int64'));nn=0
  for days,counts in records.values():
   k=np.searchsorted(days,cutoff,side='left')
   if k:nn+=int(counts[k-1])
  requests.append(dict(event_id=e.event_id,freeze_day=cutoff,n=nn,stocks=int((first<cutoff).sum())))
 request=p.with_suffix('.request.csv');output=p.with_suffix('.out.csv');pd.DataFrame(requests).to_csv(request,index=False)
 import subprocess
 subprocess.run([str(T/'exact_prefix_quantiles'),str(p),str(request),str(output)],check=True)
 out=pd.read_csv(output);out['freeze_date']=pd.to_datetime(out.freeze_day,unit='D');out['metric']=metric;out['events']=1;save(out.drop(columns='freeze_day'),f'pooled_{metric}.csv')
 for pp in [p,request,output]:pp.unlink()
 release();return metric


if __name__=='__main__':main()
