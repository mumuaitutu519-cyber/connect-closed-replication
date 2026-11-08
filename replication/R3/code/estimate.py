from common import *
from infer import fit
from assemble import PRIMARY,ALL
import concurrent.futures as cf,threading,traceback
CONTROLS=['logcap','logamount','csi300','sse50','csi500','ifbeta','predelay']
def specs():
 out=[('baseline',[],None),('exclude_AH',[],None),('QFII_parallel',['qfii'],None),('dose272_freeze',[],None),('market_SH',[],None),('market_SZ',[],None)]
 for i,c in enumerate(CONTROLS):out.append(('race_single_'+c,[c],None));out.append(('race_cumulative_'+str(i+1),CONTROLS[:i+1],None))
 out.extend([('race_all_seven_same_sample_baseline',[],CONTROLS),('race_all_eight',CONTROLS+['analyst'],None)])
 return out

def design(f,controls,minute):
 d=f.dose.to_numpy(float);c=f.closed.to_numpy(float);g=[d,c*d];gn=['dose','closed_dose'];h=[np.ones(len(f)),d,c,c*d];hn=['futures','dose_futures','closed_futures','closed_dose_futures']
 for k in controls:
  v=f[k].to_numpy(float)
  if k!='qfii':v=v-np.mean(v);sd=np.std(v);v=v/sd if sd>0 else v
  g.extend([v,c*v]);gn.extend([k,'closed_'+k]);h.extend([v,c*v]);hn.extend([k+'_futures','closed_'+k+'_futures'])
 G=np.column_stack(g);H=np.column_stack(h)if minute else None;K=G.shape[1]+(6*H.shape[1]if minute else 0);targets={}
 if minute:
  p=G.shape[1];L=np.zeros(K);L[p+3*6]=1;targets['contemporaneous']=L;L=np.zeros(K);L[p+3*6+1:p+3*6+6]=1;targets['lag1_5_sum']=L
 else:L=np.zeros(K);L[1]=1;targets['closed_dose']=L
 if 'qfii'in controls:
  if minute:
   p=G.shape[1];j=hn.index('closed_qfii_futures');L=np.zeros(K);L[p+j*6]=1;targets['QFII_contemporaneous']=L;L=np.zeros(K);L[p+j*6+1:p+j*6+6]=1;targets['QFII_lag1_5_sum']=L
  else:L=np.zeros(K);L[gn.index('closed_qfii')]=1;targets['closed_QFII']=L
 return G,H,targets,gn+[name+'_L'+str(j)for name in hn for j in range(6)]if minute else gn

def one(job):
 kind,metric,variant,spec,controls,complete=job;minute=metric.startswith('m2_');tag='_'.join([kind,metric,variant,spec]);dest=R/'tables/estimates'/f'{tag}.csv';dest.parent.mkdir(exist_ok=True)
 if dest.exists():return tag
 try:
  feature_cols=list(dict.fromkeys(['kind','event_id','code','dose',*controls,*(complete or []),*(['ah']if spec=='exclude_AH'else []),*(['dose_272']if spec=='dose272_freeze'else [])]))
  if minute:
   prod=metric[-2:];frames=[]
   for p in sorted((T/'moments').glob('*.parquet')):
    z=pd.read_parquet(p,filters=[('kind','=',kind),('product','=',prod),('variant','=',variant)]);z=z[z.kind.eq(kind)&z['product'].eq(prod)&z.variant.eq(variant)];frames.append(z)
   f=pd.concat(frames,ignore_index=True)if frames else pd.DataFrame()
   if not len(f):raise ValueError('NO_FUTURES_OR_FLOW_MOMENTS')
   mp=pd.read_csv(R/'tables/event_date_map.csv',parse_dates=['date','treatment_date']);feat=pd.read_csv(R/'tables/frozen_features.csv',usecols=feature_cols,low_memory=False);f=f.merge(mp[['kind','event_id','date','closed','treatment_date']],on=['kind','event_id','date'],validate='m:1').merge(feat,on=['kind','event_id','code'],validate='m:1')
   moments={pd.Timestamp(dt):(x.n.iloc[0],x[[f'sf{j}'for j in range(6)]].iloc[0].to_numpy(float),x[[f'sff{j}_{k}'for j in range(6)for k in range(6)]].iloc[0].to_numpy(float).reshape(6,6))for dt,x in f.groupby('date')}
  else:
   col=metric if variant=='raw'else metric+'__'+variant;columns=list(dict.fromkeys([*feature_cols,'date','closed','treatment_date',col]));f=pd.read_parquet(T/'daily_panel.parquet',columns=columns,filters=[('kind','=',kind)]);f=f[f.kind.eq(kind)].copy();f['sy']=f[col];f['sy2']=f.sy**2;f['n']=1;moments={}
  if spec=='original_futures_only':f=f[f.date.le(pd.Timestamp('2026-09-01'))]
  if spec=='exclude_AH':f=f[f.ah.eq(0)]
  if spec in ['market_SH','market_SZ']:f=f[f.code.str.endswith('.'+spec[-2:])]
  if spec=='same_weekday':
   support=pd.read_csv(R/'tables/fake20_support.csv',parse_dates=['pseudo_date']);valid=set(support.loc[support.same_weekday&support.status.eq('OK'),'pseudo_date']);f=f[f.treatment_date.isin(valid)]
  if spec=='dose272_freeze':f['dose']=f.dose_272
  need=list(dict.fromkeys(['dose','sy',*controls,*(complete or [])]));f=f.replace([np.inf,-np.inf],np.nan).dropna(subset=need);f=f[f.n.gt(0)].copy()
  if not len(f):raise ValueError('NO_COMPLETE_CASES_OR_NO_PRE_SAMPLE_WINSOR_HISTORY')
  support=f.groupby(['event_id','closed']).date.nunique().unstack(fill_value=0);supported=support.index[(support.get(True,0)>0)&(support.get(False,0)>0)]if {True,False}.issubset(support.columns)else [];unsupported=support.loc[~support.index.isin(supported)].reset_index();folder=R/'tables/event_support';folder.mkdir(exist_ok=True);unsupported.to_csv(folder/(tag+'.csv'),index=False);f=f[f.event_id.isin(supported)]
  if not len(f):raise ValueError('NO_EVENT_WITH_OBSERVED_TREATMENT_AND_CONTROL')
  assert not f.duplicated(['code','date']).any();G,H,targets,names=design(f,controls,minute)
  # Full lag coefficients share the same fit; wild tests reserved for registered contrasts.
  if minute:
   K=len(names)
   for j in range(6):L=np.zeros(K);L[G.shape[1]+18+j]=1;targets['individual_L'+str(j)]=L
   quant=f[['event_id','code','dose']].drop_duplicates().dose.quantile([.25,.75]);offset=G.shape[1]
   for timing,jj in [('contemporaneous',[0]),('lag1_5_sum',list(range(1,6)))]:
    for state in ['normal','closed']:
     L=np.zeros(K)
     for j in jj:
      L[offset+6+j]=1
      if state=='closed':L[offset+18+j]=1
     targets['individual_'+state+'_dose_gradient_'+timing]=L
     for label,dd in [('low',quant.loc[.25]),('high',quant.loc[.75])]:
      L=np.zeros(K)
      for j in jj:
       L[offset+j]=1;L[offset+6+j]=dd
       if state=='closed':L[offset+12+j]=1;L[offset+18+j]=dd
      targets['individual_'+state+'_'+label+'_'+timing]=L
  res=fit(f,G,H,targets,moments)
  for z in res:z.update(kind=kind,metric=metric,variant=variant,specification=spec,sample_y_mean=f.sy.sum()/f.n.sum(),dose_p25=f[['event_id','code','qfii'if 'QFII'in z['term']else 'dose']].drop_duplicates()['qfii'if 'QFII'in z['term']else 'dose'].quantile(.25),dose_p75=f[['event_id','code','qfii'if 'QFII'in z['term']else 'dose']].drop_duplicates()['qfii'if 'QFII'in z['term']else 'dose'].quantile(.75),events=f.event_id.nunique(),treated_days=f.loc[f.closed,'date'].nunique(),exposure='QFII'if 'QFII'in z['term']else 'NB')
  pd.DataFrame(res).to_csv(dest,index=False,na_rep='NA')
 except Exception as e:
  terms=['contemporaneous','lag1_5_sum']if minute else ['closed_dose']
  if 'qfii'in controls:terms+=['QFII_contemporaneous','QFII_lag1_5_sum']if minute else ['closed_QFII']
  expected=isinstance(e,ValueError)and str(e).startswith('NO_');status='NOT_ESTIMABLE'if expected else 'IMPLEMENTATION_ERROR'
  if not expected:
   folder=R/'logs/estimate_errors';folder.mkdir(exist_ok=True);(folder/(tag+'.txt')).write_text(traceback.format_exc())
  pd.DataFrame([dict(kind=kind,metric=metric,variant=variant,specification=spec,term=term,status=status,reason=str(e),error_type=type(e).__name__,exposure='QFII'if 'QFII'in term else 'NB')for term in terms]).to_csv(dest,index=False)
 return tag

def main():
 lock=json.loads((R/'meta/preregistration_lock.json').read_text());assert lock['sha256']==hashlib.sha256((R/'PREREGISTRATION_R3.md').read_bytes()).hexdigest()
 if not lock['first_estimate_at']:lock['first_estimate_at']=str(pd.Timestamp.now(tz='UTC'));js(R/'meta/preregistration_lock.json',lock)
 fingerprint=hashlib.sha256()
 files=[R/'code'/v for v in ['infer.py','estimate.py','assemble.py']]+[R/'tables/frozen_features.csv',R/'tables/event_date_map.csv',T/'daily_panel.parquet']+sorted((T/'moments').glob('*.parquet'))
 for p in files:
  fingerprint.update(str(p).encode())
  with p.open('rb')as stream:
   for block in iter(lambda:stream.read(8*1024*1024),b''):fingerprint.update(block)
 digest=fingerprint.hexdigest();identity=R/'meta/estimation_identity.json';old=json.loads(identity.read_text()).get('sha256')if identity.exists()else None
 if old!=digest:
  dest=R/'tables/estimates'
  if dest.exists():
   for p in dest.glob('*.csv'):p.unlink()
 js(identity,dict(sha256=digest,files=[str(p)for p in files],verified_at=pd.Timestamp.now(tz='UTC')))
 jobs=[]
 for kind in ['real','fake20','common_holiday']:
  metrics=ALL+['m2_IF','m2_IH']if kind=='real'else PRIMARY+['m2_IF','m2_IH']
  for metric in metrics:
   for variant in ['raw','w01','w005']:
    ss=specs()if kind=='real'and metric in PRIMARY+['m2_IF','m2_IH']else ([('baseline',[],None),('market_SH',[],None),('market_SZ',[],None)]if kind=='real'else [('baseline',[],None),('same_weekday',[],None)]if kind=='fake20'else [('baseline',[],None)])
    if kind=='real'and(metric.startswith('m2_')or metric in ['m3_wait_median','m3_update60']):ss=ss+[('original_futures_only',[],None)]
    for spec,ctl,complete in ss:jobs.append((kind,metric,variant,spec,ctl,complete))
 stop=threading.Event();threading.Thread(target=watch,args=(stop,),daemon=True).start()
 try:
  with cf.ProcessPoolExecutor(max_workers=4,max_tasks_per_child=1)as pool:
   for i,z in enumerate(pool.map(one,jobs,chunksize=1)):
    if i%50==0:print('ESTIMATES',i,len(jobs),z,flush=True)
 finally:stop.set()
 records=pd.concat([pd.read_csv(p)for p in sorted((R/'tables/estimates').glob('*.csv'))],ignore_index=True);records['q_bh']=np.nan
 for col in ['beta','se','dose_p25','dose_p75','p','wild_p','event_wild_p']:
  if col not in records:records[col]=np.nan
 records['effect_iqr']=records.beta*(records.dose_p75-records.dose_p25)
 def bh(v):
  good=v.dropna();order=np.argsort(good.to_numpy());x=good.to_numpy()[order];q=np.minimum.accumulate((x*len(v)/np.arange(1,len(x)+1))[::-1])[::-1];out=pd.Series(np.nan,index=v.index);out.loc[good.index[order]]=np.minimum(q,1);return out
 main=records.kind.eq('real')&records.variant.eq('w01')&records.specification.eq('baseline')&records.metric.isin(PRIMARY+['m2_IF','m2_IH'])&~records.term.astype(str).str.startswith('individual')&records.exposure.eq('NB');records.loc[main,'q_bh_main15']=bh(records.loc[main,'p']);records.loc[main,'q_bh_wild_main15']=bh(records.loc[main,'wild_p'])
 records.loc[main,'mechanism']=records.loc[main,'metric'].str.extract(r'^(m[1-5])',expand=False)
 for mechanism,idx in records[main].groupby('mechanism').groups.items():
  records.loc[idx,'q_bh_mechanism']=bh(records.loc[idx,'p']);records.loc[idx,'q_bh_wild_mechanism']=bh(records.loc[idx,'wild_p'])
 for key,idx in records.groupby(['kind','variant','specification']).groups.items():
  subset=records.loc[idx];primary=subset.metric.isin(PRIMARY+['m2_IF','m2_IH'])&~subset.term.astype(str).str.startswith('individual')
  ii=subset.index[primary&subset.exposure.eq('NB')];qq=subset.index[primary&subset.exposure.eq('QFII')]
  records.loc[ii,'q_bh']=bh(records.loc[ii,'p']);records.loc[ii,'q_bh_wild']=bh(records.loc[ii,'wild_p'])
  if len(qq):records.loc[qq,'q_bh_QFII']=bh(records.loc[qq,'p']);records.loc[qq,'q_bh_wild_QFII']=bh(records.loc[qq,'wild_p'])
 assert int(main.sum())==15,('Registered primary family must have 15 rows',int(main.sum()))
 save(records,'all_estimates.csv')
 if records.status.eq('IMPLEMENTATION_ERROR').any():
  save(records[records.status.eq('IMPLEMENTATION_ERROR')],'implementation_errors.csv');raise RuntimeError('Unexpected estimation errors; see tables/implementation_errors.csv and logs/estimate_errors. They are NOT data-unavailability results.')
 save(records[main],'main_family.csv');save(records[records.metric.str.startswith('m2_')],'M2_estimates.csv');save(records[[c for c in ['kind','metric','variant','specification','exposure','term','status','reason','n','stocks','dates','events','treated_days']if c in records]],'specification_status.csv');save(records[~records.status.eq('OK')],'unavailable_estimates.csv');print('ALL ESTIMATES COMPLETE',len(records),flush=True)
if __name__=='__main__':main()
