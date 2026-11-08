from common import *
import pyarrow.parquet as pq,pyarrow.dataset as ds,concurrent.futures as cf,argparse
for a in ['annual_daily','annual_segments','panel_daily','panel_segments','audits']:(T/a).mkdir(exist_ok=True)
U=pd.read_csv(P/'meta/stock_universe.csv');CODES=sorted(U.code);BLOCKS=[CODES[i:i+20] for i in range(0,len(CODES),20)]

def pack(job):
 kind,year=job;dest=T/('annual_'+kind)/f'{year}.parquet';files=sorted((T/('daily' if kind=='daily' else 'segments')).glob(f'{year}*.parquet'))
 if not files:return dict(kind=kind,year=year,status='empty')
 expected=sum(pq.ParquetFile(p).metadata.num_rows for p in files)
 if dest.exists():
  try:
   if pq.ParquetFile(dest).metadata.num_rows==expected:return dict(kind=kind,year=year,status='cached_verified')
  except Exception:pass
  dest.unlink()
 folder=T/f'pack_{kind}_{year}';folder.mkdir(exist_ok=True);writers={};paths={}
 for p in files:
  d=pq.ParquetFile(p).read(use_threads=False).to_pandas(use_threads=False);d['code']=pd.Categorical(d.code,categories=CODES)
  for col in ['segment','regression_minutes','valid_segment_returns']:
   if col in d:d[col]=d[col].astype('uint8')
  for prefix,g in d.groupby(d.code.astype(str).str[:4],observed=True,sort=False):
   table=pa.Table.from_pandas(g,preserve_index=False)
   if prefix not in writers:
    path=folder/f'{prefix}.parquet';paths[prefix]=path;writers[prefix]=pq.ParquetWriter(path,table.schema,compression='zstd')
   writers[prefix].write_table(table)
  del d;trim()
 for writer in writers.values():writer.close()
 del writers;trim();annual=None;total=0
 for prefix,path in sorted(paths.items()):
  d=pq.ParquetFile(path).read(use_threads=False).to_pandas(use_threads=False);d['code']=pd.Categorical(d.code,categories=CODES);d=d.sort_values(['code','date']+(['segment'] if kind=='segments' else []));table=pa.Table.from_pandas(d,preserve_index=False)
  if annual is None:annual=pq.ParquetWriter(dest,table.schema,compression='zstd')
  annual.write_table(table,row_group_size=20000);total+=len(d);del d,table;path.unlink();trim()
 if annual:annual.close()
 folder.rmdir();assert total==expected;return dict(kind=kind,year=year,n=total,stock_prefix_max_codes=100)

def pooled(job):
 kind,metric,segment=job;dest=T/'audits'/f'pooled_{kind}_{metric}_{segment}.csv'
 if dest.exists():
  try:
   cached=pd.read_csv(dest)
   if len(cached)>0 and 'stocks' in cached:return str(dest)
  except Exception:pass
  dest.unlink()
 cal=loadcal();weather=pd.read_csv(R/'typhoon_calendar.csv',parse_dates=['date']);normal=set(cal.loc[cal.nb_open&cal.a_open&~cal.date.isin(weather.loc[weather.included,'date']),'date']);e=pd.read_csv(R/'tables/events.csv',parse_dates=['freeze_date']);e=e[e.kind.ne('holiday')]
 if kind=='segments':e=e[e.closure_type.str.startswith('partial')]
 cols=['code','date','eligible_day',metric]+(['segment'] if kind=='segments' else []);frames=[]
 for p in sorted((T/('annual_'+kind)).glob('*.parquet')):
  f=pq.read_table(p,columns=cols,filters=[('eligible_day','=',True)]+([('segment','=',segment)] if kind=='segments' else []),use_threads=False).to_pandas(use_threads=False);f=f[f.date.isin(normal)&np.isfinite(f[metric])];frames.append(f[['code','date',metric]])
 f=pd.concat(frames,ignore_index=True).sort_values('date');del frames;v=f[metric].to_numpy();dates=f.date.to_numpy('datetime64[ns]');out=[]
 for r in e.itertuples():
  j=np.searchsorted(dates,np.datetime64(r.freeze_date),side='left');q=np.quantile(v[:j],[.005,.01,.99,.995]) if j else np.full(4,np.nan);out.append(dict(event_id=r.event_id,kind=kind,metric=metric,segment=segment,n=j,stocks=f.code.iloc[:j].nunique(),events=1,stock_clusters=f.code.iloc[:j].nunique(),date_clusters=f.date.iloc[:j].nunique(),count_scope='historical threshold contributors before freeze',freeze_date=r.freeze_date,q005=q[0],q01=q[1],q99=q[2],q995=q[3]))
 save(pd.DataFrame(out),dest);return str(dest)

def panel(job):
 kind,block=job;dest=T/('panel_'+kind)/f'{block:03d}.parquet'
 if dest.exists():
  try:
   pq.ParquetFile(dest).metadata
   if (T/'audits'/f'winsor_{kind}_{block:03d}.csv').exists():return dict(kind=kind,block=block,status='cached_verified')
  except Exception:pass
  dest.unlink()
 codes=BLOCKS[block];cols=['code','date','eligible_day','if_delay','ih_delay']+(['amount','valid_minutes'] if kind=='daily' else ['segment','segment_amount','regression_minutes','valid_segment_returns']);pieces=[]
 for source in sorted((T/('annual_'+kind)).glob('*.parquet')):
  pf=pq.ParquetFile(source);ci=pf.schema_arrow.get_field_index('code');groups=[]
  for j in range(pf.num_row_groups):
   st=pf.metadata.row_group(j).column(ci).statistics
   if st is None or not st.has_min_max or (st.max>=codes[0] and st.min<=codes[-1]):groups.append(j)
  for batch in pf.iter_batches(batch_size=32768,row_groups=groups,columns=cols,use_threads=False):
   part=batch.to_pandas(use_threads=False);part=part[part.code.isin(codes)].copy()
   if len(part):part['code']=part.code.astype(str);pieces.append(part)
  pf.close()
 f=pd.concat(pieces,ignore_index=True) if pieces else pd.DataFrame(columns=cols);del pieces
 f['code']=f.code.astype('category');f=f.sort_values(['code']+(['segment'] if kind=='segments' else [])+['date']).reset_index(drop=True)
 if not len(f):
  templates=sorted((T/('panel_'+kind)).glob('*.parquet'));template=next((p for p in templates if pq.ParquetFile(p).metadata.num_rows>0),None);assert template is not None
  schema=pq.ParquetFile(template).schema_arrow;pq.write_table(pa.Table.from_batches([],schema=schema),dest,compression='zstd')
  audit_cols=['kind','block','event_id','metric','variant','n','stocks','dates','events','stock_clusters','date_clusters','fallback_pooled','winsorized','lower_min','lower_max','upper_min','upper_max','min_prior_n','max_prior_n'];save(pd.DataFrame(columns=audit_cols),T/'audits'/f'winsor_{kind}_{block:03d}.csv');return dict(kind=kind,block=block,rows=0,status='NO_HISTORICAL_STOCK_ROWS')
 cal=loadcal();weather=pd.read_csv(R/'typhoon_calendar.csv',parse_dates=['date']);originalnormal=set(cal.loc[cal.a_open&cal.nb_open,'date']);normal=originalnormal-set(weather.loc[weather.included,'date']);f['normal']=f.date.isin(normal);f['r1normal']=f.date.isin(originalnormal)
 mapping=pd.read_csv(R/'tables/event_map.csv',parse_dates=['date','anchor']);mapping=mapping[mapping.family.eq('partial') if kind=='segments' else ~mapping.family.eq('partial')]
 out=f[f.eligible_day&f.date.isin(set(mapping.date))].merge(mapping,on='date',validate='m:m');ex=pd.read_parquet(T/'exposures.parquet');out=out.merge(ex[ex.code.isin(codes)].drop(columns=['anchor','first_observed_daily']),on=['code','event_id'],validate='m:1')
 out=out.sort_values(['event_id','code','date']+(['segment'] if kind=='segments' else [])).reset_index(drop=True)
 pools=pd.concat([pd.read_csv(p) for p in (T/'audits').glob(f'pooled_{kind}_*.csv')],ignore_index=True)
 if kind=='daily':
  old=pd.read_csv(P/'tables/pooled_winsor_thresholds.csv');old=old[old.metric.isin(['if_delay','ih_delay'])].copy();old['segment']=-1;old['kind']='daily';pools=pd.concat([pools,old],ignore_index=True)
 pools=pools.set_index(['event_id','metric','segment']);assert pools.index.is_unique;threshold_values={c:pools[c].to_dict() for c in ['q005','q01','q99','q995']};counts=[]
 for metric in ['if_delay','ih_delay']:
  for name,lo,hi in [('w01',.01,.99),('w005',.005,.995)]:
   out[f'{metric}__{name}']=np.nan
   for histkind,isold in [('normal',False),('r1normal',True)] if kind=='daily' else [('normal',False)]:
    subset=out.kind.eq('holiday') if isold else out.kind.ne('holiday')
    if not subset.any():continue
    look=[]
    for key,g in f.groupby(['code']+(['segment'] if kind=='segments' else []),observed=True,sort=False):
     z=g.loc[g.eligible_day&g[histkind],metric];z=z[np.isfinite(z)];ql=z.expanding(min_periods=60).quantile(lo);qh=z.expanding(min_periods=60).quantile(hi);nn=pd.Series(np.arange(1,len(z)+1),index=z.index);a=ql.reindex(g.index).ffill();b=qh.reindex(g.index).ffill();n=nn.reindex(g.index).ffill().fillna(0);a.loc[z.index]=ql.shift(1).to_numpy();b.loc[z.index]=qh.shift(1).to_numpy();n.loc[z.index]=nn.shift(1,fill_value=0).to_numpy();q=g[['code','date']+(['segment'] if kind=='segments' else [])].copy();q['lo']=a;q['hi']=b;q['nprior']=n;look.append(q)
    keys=['code','date']+(['segment'] if kind=='segments' else []);o=out.loc[subset,keys+['event_id',metric]].reset_index().merge(pd.concat(look),on=keys,validate='m:1');fallback=o.nprior.lt(60)|o.lo.isna()|o.hi.isna();s=o.segment if kind=='segments' else np.full(len(o),-1);ix=list(zip(o.event_id,o.event_id.map(lambda x:metric),s));ql=np.array([threshold_values['q01' if name=='w01' else 'q005'][k] for k in ix]);qh=np.array([threshold_values['q99' if name=='w01' else 'q995'][k] for k in ix]);o.loc[fallback,'lo']=ql[fallback];o.loc[fallback,'hi']=qh[fallback];out.loc[o['index'],f'{metric}__{name}']=o[metric].clip(o.lo,o.hi).to_numpy()
    o['fallback']=fallback;o['changed']=(o[metric]<o.lo)|(o[metric]>o.hi)
    for event,g in o.groupby('event_id'):
     counts.append(dict(kind=kind,block=block,event_id=event,metric=metric,variant=name,n=len(g),stocks=g.code.nunique(),dates=g.date.nunique(),events=1,stock_clusters=g.code.nunique(),date_clusters=g.date.nunique(),fallback_pooled=int(g.fallback.sum()),winsorized=int(g.changed.sum()),lower_min=g.lo.min(),lower_max=g.lo.max(),upper_min=g.hi.min(),upper_max=g.hi.max(),min_prior_n=g.nprior.min(),max_prior_n=g.nprior.max()))
 out['dose_typhoon']=out.dose*out.kind.eq('weather');out['closed_dose']=out.closed*out.dose
 if kind=='segments':
  ev=pd.read_csv(R/'tables/events.csv').set_index('event_id');seg=out.segment.to_numpy(np.int64);start=np.where(seg<4,570+30*seg,780+30*(seg-4));end=start+30;cs=out.event_id.map(ev.closed_start);ce=out.event_id.map(ev.closed_end);eventday=out.closed.eq(1);closed=eventday&pd.Series(start,index=out.index).ge(cs)&pd.Series(end,index=out.index).le(ce);overlap=eventday&pd.Series(end,index=out.index).gt(cs)&pd.Series(start,index=out.index).lt(ce)&~closed;out['mixed_boundary']=overlap;out['closed_segment']=closed.astype(int);out['restored_segment']=(eventday&ce.lt(900)&pd.Series(start,index=out.index).ge(ce)).astype(int);out['closed_dose']=out.closed_segment*out.dose;out['restore_dose']=out.restored_segment*out.dose;out['stock_day']=out.code.astype(str)+'_'+out.date.dt.strftime('%Y%m%d');out['event_segment']=out.event_id.astype(str)+'_'+out.segment.astype(str)
 else:out['restore_dose']=out.resume*out.dose
 out.to_parquet(dest,index=False,compression='zstd');save(pd.DataFrame(counts),T/'audits'/f'winsor_{kind}_{block:03d}.csv');return dict(kind=kind,block=block,rows=len(out))

def main():
 ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['pack','pooled','panel']);a=ap.parse_args()
 if a.stage=='pack':jobs=[(kind,y) for kind in ['daily','segments'] for y in range(2017,2027)];fn=pack
 elif a.stage=='pooled':jobs=[('daily',m,-1) for m in ['if_delay','ih_delay']]+[('segments',m,j) for m in ['if_delay','ih_delay'] for j in range(8)];fn=pooled
 else:jobs=[(kind,b) for kind in ['daily','segments'] for b in range(len(BLOCKS))];fn=panel
 if a.stage=='panel':
  pending=[]
  for kind,block in jobs:
   path=T/('panel_'+kind)/f'{block:03d}.parquet';audit=T/'audits'/f'winsor_{kind}_{block:03d}.csv'
   if path.exists() and audit.exists():
    try:pq.ParquetFile(path).metadata;continue
    except Exception:pass
   pending.append((kind,block))
  print('panel cached',len(jobs)-len(pending),'pending',len(pending),flush=True);jobs=pending
 batch_size=2 if a.stage=='pooled' else (16 if a.stage=='panel' else max(len(jobs),1))
 for offset in range(0,len(jobs),batch_size):
  with cf.ProcessPoolExecutor(max_workers=4) as pool:
   for j,r in enumerate(pool.map(fn,jobs[offset:offset+batch_size],chunksize=1)):
    i=offset+j
    if i%10==0:print(a.stage,i,r,flush=True)
 if a.stage=='pooled':save(pd.concat([pd.read_csv(p) for p in (T/'audits').glob('pooled_*.csv')]),R/'tables/pooled_winsor_thresholds.csv')
 if a.stage=='panel':
  audits=[]
  for path in (T/'audits').glob('winsor_*.csv'):
   try:audits.append(pd.read_csv(path))
   except pd.errors.EmptyDataError:pass
  save(pd.concat(audits,ignore_index=True),R/'tables/winsor_audit.csv');empty=[]
  for kind in ['daily','segments']:
   for block in range(len(BLOCKS)):
    path=T/('panel_'+kind)/f'{block:03d}.parquet'
    if path.exists() and pq.ParquetFile(path).metadata.num_rows==0:empty.append(dict(kind=kind,block=block,n=0,stocks=0,events=0,stock_clusters=0,date_clusters=0,universe_codes=';'.join(BLOCKS[block]),status='NO_ELIGIBLE_EVENT_WINDOW_ROWS'))
  save(pd.DataFrame(empty,columns=['kind','block','n','stocks','events','stock_clusters','date_clusters','universe_codes','status']),R/'tables/empty_stock_blocks.csv')
if __name__=='__main__':main()
