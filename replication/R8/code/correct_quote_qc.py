from common import *
import pyarrow.compute as pc,shutil,importlib.util,concurrent.futures as cf,multiprocessing as mp
D=T/'quote_correction';A=R/'meta/quote_correction';FAMILY='quiet40_rv';TARGET=['if_delay','ih_delay','if_r2_now']

def align(tab,schema):
 return pa.Table.from_arrays([tab[c.name].cast(c.type)if c.name in tab.column_names else pa.nulls(len(tab),type=c.type)for c in schema],schema=schema)

def rewrite_family(path,newframe):
 pf=pq.ParquetFile(path);schema=pf.schema_arrow;tmp=path.with_suffix('.qc.partial');writer=pq.ParquetWriter(tmp,schema,compression='zstd');removed=0
 try:
  for batch in pf.iter_batches(batch_size=32768,use_threads=False):
   tab=pa.Table.from_batches([batch]);mask=pc.fill_null(pc.not_equal(tab['family'],FAMILY),True);part=tab.filter(mask);removed+=len(tab)-len(part)
   if len(part):writer.write_table(part,row_group_size=8192)
  for start in range(0,len(newframe),8192):writer.write_table(align(pa.Table.from_pandas(newframe.iloc[start:start+8192],preserve_index=False),schema),row_group_size=8192)
 finally:writer.close();pf.close()
 tmp.replace(path);return removed

def prepare():
 root=D/'root';(root/'tables').mkdir(parents=True,exist_ok=True);shutil.copyfile(T/'universe.parquet',D/'universe.parquet');fr=pd.read_csv(R/'tables/design_events.csv',parse_dates=['freeze_date','start']);fr=fr[fr.family.eq(FAMILY)];fr.to_csv(root/'tables/design_events.csv',index=False)
 spec=importlib.util.spec_from_file_location('quote_original_exposures',P/'R7/code/design.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);mod.R=root;mod.P=P;mod.T=D;mod.exposures();new=pd.read_parquet(D/'extra_features.parquet')
 # Public information cutoffs are enforced inside the original exposure function.
 (D/'feature_blocks').mkdir(exist_ok=True);mapping={c:i//50 for i,c in enumerate(universe().code)};new['block']=new.code.map(mapping)
 for b,g in new.groupby('block',sort=True):g.drop(columns='block').to_parquet(D/'feature_blocks'/f'{int(b):03d}.parquet',index=False)
 new=new.drop(columns='block');new.to_parquet(D/'new_features.parquet',index=False)
 for name in ['all_features.parquet','extra_features.parquet']:
  path=T/name
  if path.exists():rewrite_family(path,new)
 for metric in METRICS:
  path=R/'tables'/f'pooled_{metric}.csv';old=pd.read_csv(path,parse_dates=['freeze_date']);old.to_csv(D/f'old_pool_{metric}.csv',index=False);valuecols=['n','stocks','q005','q01','q99','q995'];bydate=old.sort_values('event_id').drop_duplicates('freeze_date').set_index('freeze_date');assert set(fr.freeze_date).issubset(bydate.index)
  add=[]
  for e in fr.itertuples():
   row=bydate.loc[e.freeze_date].to_dict();row.update(event_id=e.event_id,freeze_date=e.freeze_date,metric=metric,events=1);add.append(row)
  out=pd.concat([old[~old.event_id.between(23001,23999)],pd.DataFrame(add)],ignore_index=True).sort_values(['freeze_date','event_id']);assert np.isfinite(out[['q005','q01','q99','q995']].to_numpy(float)).all();save(out,path.name)
 js(D/'prepared.json',dict(events=len(fr),features=len(new),freeze_thresholds_reused_exactly=True));del new;release();print('QUOTE_QC_PREPARED',len(fr),flush=True)

def block(b):
 marker=D/f'block_{b:03d}.json'
 if marker.exists():return json.loads(marker.read_text())
 cols=['code','date','eligible_day','nb_open',*TARGET];f=pd.concat([pd.read_parquet(p,columns=cols)for p in sorted((T/'history').glob(f'*_{b:03d}.parquet'))],ignore_index=True).sort_values(['code','date']).reset_index(drop=True)
 oldmap=pd.read_csv(D/'design_map.csv',parse_dates=['date','freeze_date']);oldmap=oldmap[oldmap.family.eq(FAMILY)];newmap=pd.read_csv(R/'tables/design_map.csv',parse_dates=['date','anchor','freeze_date']);newmap=newmap[newmap.family.eq(FAMILY)];assert set(oldmap.date)==set(newmap.date)
 fe=pd.read_parquet(D/'feature_blocks'/f'{b:03d}.parquet');out=f[f.eligible_day&f.date.isin(newmap.date)].merge(newmap[['event_id','date','anchor','closed','family']],on='date',validate='m:1').merge(fe.drop(columns='family'),on=['event_id','code'],validate='m:1')
 oldfile=T/'analysis_family'/FAMILY/f'{b:03d}.parquet';old=pq.read_table(oldfile,columns=['code','date','event_id','dose','quintile',*TARGET],use_threads=False).to_pandas()if oldfile.exists()else pd.DataFrame(columns=['code','date','event_id','dose','quintile',*TARGET]);assert len(old)==len(out)
 if len(out):
  old['old_freeze_date']=old.event_id.map(oldmap.drop_duplicates('event_id').set_index('event_id').freeze_date);chk=out[['code','date','dose','quintile','freeze_date',*TARGET]].merge(old,on=['code','date'],validate='1:1',suffixes=('_new','_old'));assert len(chk)==len(out)
  for metric in TARGET:assert np.allclose(chk[metric+'_new'],chk[metric+'_old'],atol=0,rtol=0,equal_nan=True)
  same=chk.freeze_date.eq(chk.old_freeze_date)
  for c in ['dose','quintile']:assert np.allclose(chk.loc[same,c+'_new'],chk.loc[same,c+'_old'],atol=0,rtol=0,equal_nan=True)
 audit=[]
 for metric in TARGET:
  pool=pd.read_csv(R/'tables'/f'pooled_{metric}.csv').set_index('event_id')
  for variant,lo,hi in [('w01',.01,.99),('w005',.005,.995)]:
   looks=[]
   for code,g in f.groupby('code',sort=False):
    z=g.loc[g.eligible_day&g.nb_open,metric].replace([np.inf,-np.inf],np.nan).dropna();ql=z.expanding(min_periods=60).quantile(lo);qh=z.expanding(min_periods=60).quantile(hi);nn=pd.Series(np.arange(1,len(z)+1),index=z.index);l=ql.reindex(g.index).ffill();h=qh.reindex(g.index).ffill();n=nn.reindex(g.index).ffill().fillna(0);l.loc[z.index]=ql.shift(1);h.loc[z.index]=qh.shift(1);n.loc[z.index]=nn.shift(1,fill_value=0);looks.append(pd.DataFrame(dict(code=code,date=g.date,lo=l,hi=h,npast=n)))
   o=out[['code','date','event_id',metric]].merge(pd.concat(looks),on=['code','date'],validate='m:1');fb=o.npast.lt(60)|o.lo.isna()|o.hi.isna();l='q01'if variant=='w01'else'q005';h='q99'if variant=='w01'else'q995';o.loc[fb,'lo']=o.loc[fb,'event_id'].map(pool[l]);o.loc[fb,'hi']=o.loc[fb,'event_id'].map(pool[h]);out[f'{metric}__{variant}']=o[metric].clip(o.lo,o.hi).to_numpy();audit.append(dict(block=b,metric=metric,variant=variant,family=FAMILY,n=len(out),stocks=out.code.nunique(),events=out.event_id.nunique(),fallback=int(fb.sum()),missing_threshold=int((o.lo.isna()|o.hi.isna()).sum())))
 keep=['code','date','event_id','closed','dose','family','quintile',*TARGET,*[m+'__'+v for m in TARGET for v in ['w01','w005']]];(D/'panel').mkdir(exist_ok=True)
 if len(out):out[keep].to_parquet(D/'panel'/f'{b:03d}.parquet',index=False,compression='zstd')
 # The complete raw stock-date set and the historical valid-normal series are
 # unchanged, so aggregate fallback counts for all 25 variables are unchanged.
 result=dict(block=b,n=len(out),stocks=out.code.nunique(),old_events=old.event_id.nunique(),new_events=out.event_id.nunique(),audit=audit)
 rewrite_family(T/'feature_blocks'/f'{b:03d}.parquet',fe);js(marker,result);release();return result

def panels():
 ctx=mp.get_context('spawn');nb=int(np.ceil(len(universe())/50));results=[]
 for start in range(0,nb,6):
  with cf.ProcessPoolExecutor(max_workers=6,mp_context=ctx)as pool:results.extend(pool.map(block,range(start,min(start+6,nb))))
  print('QUOTE_QC_PANEL',min(start+6,nb),'/',nb,flush=True)
 old=T/'analysis_family'/FAMILY;archive=D/'old_analysis_family'
 if old.exists()and not archive.exists():old.replace(archive)
 if (D/'panel').exists():(D/'panel').replace(old)
 audit=pd.read_csv(D/'winsor_audit.csv');assert audit.missing_threshold.sum()==0
 for result in results:
  b=result['block'];ix=audit.block.eq(b);audit.loc[ix,'events']+=result['new_events']-result['old_events'];p=T/'analysis_family'/f'{b:03d}.json';counts=json.loads(p.read_text())
  assert counts.get(FAMILY,0)==result['n']
  if result['n']:counts[FAMILY]=result['n']
  else:counts.pop(FAMILY,None)
  js(p,counts)
 save(audit,'winsor_audit.csv');pd.DataFrame([a for r in results for a in r['audit']]).to_csv(A/'quiet40_winsor_audit.csv',index=False);js(D/'panel_complete.json',dict(blocks=nb,raw_stock_date_rows_unchanged=True,raw_outcomes_unchanged=True))
 for p in list((R/'tables').glob('state_*.csv'))+list((R/'tables').glob('quiet40_rv_*.csv')):p.unlink()
 for p in [T/'plan_quiet40_rv.npz',R/'meta/ri_quiet40_rv.json']:
  if p.exists():p.unlink()
 from analyze import market_daily
 from inference import plan
 market_daily();plan(FAMILY);print('QUOTE_QC_PANELS_FINISHED',flush=True)

def estimates():
 from analyze import job_process
 ctx=mp.get_context('spawn');jobs=[('state_job',(m,v,c))for v in VARIANTS for m in TARGET for c in [False,True]]+[('quiet_job',(m,v,FAMILY))for v in VARIANTS for m in TARGET];pending=list(enumerate(jobs));active=[];(D/'status').mkdir(exist_ok=True)
 def size(job):return 6. if job[0]=='quiet_job'else 4.5 if job[1][2]else 2.
 try:
  while pending or active:
   used=sum(r[2]for r in active)
   while len(active)<6:
    k=next((k for k,(_,j)in enumerate(pending)if used+size(j)<=9.5),None)
    if k is None:break
    index,job=pending.pop(k);p=D/'status'/f'{index:03d}.json';process=ctx.Process(target=job_process,args=(job,str(p)));process.start();allocation=size(job);active.append((process,p,allocation));used+=allocation
   for item in active[:]:
    process,p,_=item
    if process.is_alive():continue
    process.join()
    if process.exitcode:raise RuntimeError(f'QC worker {process.pid} exited {process.exitcode}')
    print('QUOTE_QC_FIT',json.loads(p.read_text())['result'],flush=True);process.close();active.remove(item)
   if active:time.sleep(.1)
 finally:
  for process,_,_ in active:
   if process.is_alive():process.terminate()
   process.join()
 from inference import bh
 d=pd.concat([pd.read_csv(p)for p in sorted((R/'tables').glob('state_*.csv'))if p.name!='state_all.csv'],ignore_index=True)
 for c in ['p','wild_p','ri_p']:d['BH_'+c]=d.groupby(['variant','controls','specification','term'],dropna=False)[c].transform(bh)
 save(d,'state_all.csv')
 from quiet_support import main as support
 support()
 # Rebuild combined small-sample exports without rerunning unaffected weather/sell-only fits.
 rows=[pd.read_csv(R/'tables'/f'{n}_webb.csv')for n in ['weather','sellonly']];tests=[pd.read_csv(R/'tables'/f'{n}_event_tests.csv')for n in ['weather','sellonly']]
 for p in (R/'tables').glob('quiet*_event.csv'):tests.append(pd.read_csv(p))
 for v in VARIANTS:
  for m in TARGET:
   for family in ['quiet30_both','quiet40_both','quiet30_rv','quiet40_rv']:
    q=pd.read_csv(R/'tables'/f'{family}_{m}_{v}.csv');q=q[q.specification.eq('quiet_only_original_FE')].copy();q['group']=family;rows.append(q)
 a=pd.concat(rows,ignore_index=True);b=pd.concat(tests,ignore_index=True);b['test_observations']=b.events;b['test_df']=b.events-1;b['sign_trials']=b.positive+b.negative
 for frame in [a,b]:
  for c in ['p','wild_p','event_t_p','sign_p']:
   if c in frame:frame['BH_'+c]=frame.groupby(['group','variant'],dropna=False)[c].transform(bh)
 save(a,'small_sample_webb_all.csv');save(b,'small_sample_event_tests_all.csv')
 compare=[]
 for p in sorted((A).glob('state_*.csv')):
  if p.name=='state_all.csv':continue
  old=pd.read_csv(p);new=pd.read_csv(R/'tables'/p.name);z=old[['specification','beta','n']].merge(new[['specification','beta','n']],on='specification',suffixes=('_old','_new'));assert z.n_old.eq(z.n_new).all();z['beta_change_x100']=(z.beta_new-z.beta_old)*100;z['file']=p.name;z['n']=z.n_new;z['stocks']=new.stocks.iloc[0];z['events']=new.events.iloc[0];compare.append(z)
 pd.concat(compare,ignore_index=True).to_csv(A/'state_centering_comparison.csv',index=False);print('QUOTE_QC_ESTIMATES_FINISHED',flush=True)

if __name__=='__main__':globals()[sys.argv[1]]()
