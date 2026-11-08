from common import *
import importlib.util
from scipy.stats import t as student_t,binomtest
SRC=P.parent/'nb_sellonly'
sp=importlib.util.spec_from_file_location('sell_engine',SRC/'code/inference.py');engine=importlib.util.module_from_spec(sp);sp.loader.exec_module(engine);engine.SEED=SEED

def main():
 ex=pd.read_csv(SRC/'tables/exposure_by_event.csv',parse_dates=['batch','next_change']);choice=json.loads((SRC/'meta/sample_counts.json').read_text())['choice'];ex=ex[ex.direction.eq('sell')&ex.group.isin(['T',choice])].copy()
 if choice=='A':ex=ex[ex.sell.eq(0)|(ex.official_index_removed.eq(True)&ex.reason.eq('index_review'))]
 full=pd.DatetimeIndex(pd.read_csv(SRC/'meta/trading_calendar.csv',parse_dates=['date']).date);pos={d:i for i,d in enumerate(full)};rows=[]
 for r in ex.itertuples():
  for tau in range(-20,41):
   if -1<=tau<=1:continue
   date=full[pos[r.batch]+tau]
   if pd.notna(r.next_change)and date>=r.next_change:continue
   rows.append(dict(batch_id=r.batch_id,unit=r.unit,code=r.code,batch=r.batch,sell=r.sell,hold=r.hold,date=date,tau=tau,post=int(tau>=2)))
 plan=pd.DataFrame(rows);parts=[]
 with np.load(T/'futures_IF.npz')as z:minfuture=pd.Timestamp(int(z['dates'].min()),unit='D');maxfuture=pd.Timestamp(int(z['dates'].max()),unit='D')
 missing=[str(day.date())for day in sorted(plan.date.unique())if day>=minfuture and day<=maxfuture and not(T/'daily'/f'{day:%Y%m%d}.parquet').exists()]
 if missing:
  import minutes,concurrent.futures as cf
  with cf.ProcessPoolExecutor(max_workers=6)as pool:receipts=list(pool.map(minutes.one,missing))
  save(receipts,'sellonly_additional_day_receipts.csv')
 for day,g in plan.groupby('date'):
  p=T/'daily'/f'{day:%Y%m%d}.parquet'
  if not p.exists():continue
  m=pd.read_parquet(p,columns=['code','date','raw_eligible_day','if_delay','ih_delay']);parts.append(g.merge(m,on=['code','date'],how='left',validate='m:1'))
 f=pd.concat(parts,ignore_index=True);out=[];tests=[];contrasts=[];checks=[]
 old=pd.read_csv(SRC/'tables/main_estimates.csv');old=old[old.model.eq('dose')&old.spec.eq('main')]
 for metric in ['if_delay','ih_delay']:
  q=f[f.raw_eligible_day.fillna(False).astype(bool)&np.isfinite(f[metric])].copy();batches=q.groupby('batch_id').sell.agg(['min','max']);valid=batches.index[(batches['min']==0)&(batches['max']==1)];q=q[q.batch_id.isin(valid)]
  dist=pd.read_csv(SRC/'tables'/f'distribution_{metric}.csv').iloc[0]
  for v in VARIANTS:
   lo=-np.inf if v=='raw'else dist['winsor01_low'if v=='w01'else'winsor005_low'];hi=np.inf if v=='raw'else dist['winsor01_high'if v=='w01'else'winsor005_high'];q['y']=q[metric].clip(lo,hi);r=engine.fit(q,'y','dose','unit_batchdate',keep=True)
   if r.get('status')=='OK':
    r.update(engine.wild(r));k=r['_keep'];ids=sorted(k['d'].batch_id.unique());W=np.random.default_rng(SEED).choice(np.array([-np.sqrt(1.5),-1.,-np.sqrt(.5),np.sqrt(.5),1.,np.sqrt(1.5)]),(B,len(ids)));r['wild_unique_draws']=len(np.unique(W,axis=0));r['events']=len(ids);r.update(engine.permute(r,'dose'))
   r.pop('_keep',None);r.update(metric=metric,variant=v,group='SellOnly',specification='main_dose',dose_timing='286 original frozen');r['beta_x100']=r.get('beta',np.nan)*100;r['se_x100']=r.get('se',np.nan)*100;r['ci_low_x100']=r.get('ci_low',np.nan)*100;r['ci_high_x100']=r.get('ci_high',np.nan)*100;out.append(r)
   ref=old[old.metric.eq(metric)&old.variant.eq(v)]
   if len(ref):checks.append(dict(metric=metric,variant=v,old_n=ref.iloc[0]['n'],new_n=r.get('n'),old_beta=ref.iloc[0].beta,new_beta=r.get('beta'),n_equal=ref.iloc[0]['n']==r.get('n'),beta_abs_error=abs(ref.iloc[0].beta-r.get('beta',np.nan)),n=r.get('n'),stocks=r.get('stocks'),events=r.get('events')))
   values=[];binary_values=[];unidentified=[];dd=q[q.hold.notna()].copy()
   for batch,g in dd.groupby('batch_id'):
    doses=g[['unit','hold']].drop_duplicates().sort_values(['hold','unit']);ranks=dict(zip(doses.unit,np.minimum(4,np.arange(len(doses))*5//len(doses))));g=g.copy();g['quintile']=g.unit.map(ranks);means=g.groupby(['sell','quintile','post']).y.mean();z=[]
    # Dose-gradient DID: high-minus-low treatment-control, before-after.
    for sell in [0,1]:
     try:z.append((means.loc[(sell,4,1)]-means.loc[(sell,4,0)])-(means.loc[(sell,0,1)]-means.loc[(sell,0,0)]))
     except KeyError:z.append(np.nan)
    val=z[1]-z[0];binary_fit=engine.fit(g,'y','binary','unit_batchdate');binary_values.append(binary_fit.get('beta',np.nan));batch_fit=engine.fit(g,'y','dose','unit_batchdate');values.append(batch_fit.get('beta',np.nan))
    if not np.isfinite(batch_fit.get('beta',np.nan)):unidentified.append(str(batch))
    contrasts.append(dict(metric=metric,variant=v,batch_id=batch,contrast=val,dose_beta=batch_fit.get('beta',np.nan),binary_beta=binary_fit.get('beta',np.nan),dose_status=batch_fit.get('status'),dose_reason=batch_fit.get('reason',''),binary_status=binary_fit.get('status'),binary_reason=binary_fit.get('reason',''),treatment_groups=g.sell.nunique(),units=g.unit.nunique(),n=len(g),stocks=g.code.nunique(),events=1))
   vals=np.array(values);vals=vals[np.isfinite(vals)];n=len(vals);se=np.std(vals,ddof=1)/np.sqrt(n)if n>1 else np.nan;stat=np.mean(vals)/se if se>0 else np.nan;nz=vals[vals!=0];tests.append(dict(group='SellOnly',metric=metric,variant=v,contrast='equal-weight batch-specific original dose DDD coefficient',beta_x100=np.mean(vals)*100,se_x100=se*100,event_t=stat,event_t_p=2*student_t.sf(abs(stat),n-1)if n>1 else np.nan,sign_p=binomtest(int((nz>0).sum()),len(nz),.5).pvalue if len(nz)else np.nan,n=r.get('n'),stocks=r.get('stocks'),events=n,positive=int((vals>0).sum()),negative=int((vals<0).sum())))
   r.update(event_test_identified_batches=n,nonidentifying_batches=';'.join(unidentified))
   from small_samples import eventstats
   tests.append(eventstats(binary_values,dict(group='SellOnly',metric=metric,variant=v,contrast='equal-weight batch-specific binary DID on original dose-complete sample'),r.get('n'),r.get('stocks')))
   print('SELL',metric,v,r.get('n'),r.get('beta'),flush=True)
 save(out,'sellonly_webb.csv');save(tests,'sellonly_event_tests.csv');save(contrasts,'sellonly_batch_contrasts.csv');save(checks,'sellonly_reproduction.csv')
if __name__=='__main__':main()
