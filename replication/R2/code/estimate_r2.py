"""Locked R2 specs, R1 FWL/CGM inference, shared event wild and calendar RI."""
import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
from pathlib import Path
import sys,json,gc,hashlib,time,pickle,multiprocessing as mp,concurrent.futures as cf,numpy as np,pandas as pd,pyarrow.dataset as ds,pyarrow as pa
from scipy.stats import t as student_t,norm,skew,kurtosis,binomtest
sys.path.insert(0,str(Path(__file__).parent/'r1'))
import estimate as r1
from auxiliary import release_memory
R=Path(__file__).resolve().parents[1];T=Path('/Volumes/Extreme SSD/T9/_tmp/272');Q=Path('/Volumes/Extreme SSD/QDC/data/QDCData');SEED=20261111;B=9999
PRIMARY=['if_delay','ih_delay','if_lag_sum','ih_lag_sum'];CONTROLS=['logcap','logamount','csi300','sse50','csi500','ifbeta','predelay','analyst'];AVAILABLE=['logcap','logamount','ifbeta','predelay','analyst'];ORIG_DEMEAN=r1.demean
RI_CACHE={}
FIT_LIMITER=None
def init_worker(limiter):
 global FIT_LIMITER
 FIT_LIMITER=limiter

def inference(*args,**kwargs):
 if FIT_LIMITER is None:return _inference(*args,**kwargs)
 with FIT_LIMITER:return _inference(*args,**kwargs)

def demean(a,e,t,maxiter=200):
 if t.max()<1200:return ORIG_DEMEAN(a,e,t,maxiter)
 a=np.asarray(a,float).copy();ne=np.bincount(e);nt=np.bincount(t)
 for it in range(500):
  err=0.
  for j in range(a.shape[1]):
   m=np.bincount(e,weights=a[:,j])/ne;a[:,j]-=m[e];v=np.bincount(t,weights=a[:,j])/nt;a[:,j]-=v[t];err=max(err,np.max(np.abs(m)),np.max(np.abs(v)))
  if err<1e-10:return a,it+1
 raise RuntimeError('FE did not converge')
r1.demean=demean

def load(source,cols):
 f=ds.dataset(source,format='parquet').to_table(columns=cols,use_threads=False).to_pandas(use_threads=False);f['code']=pd.Categorical(f.code);return f

def prepare_features():
 while not (R/'meta/historical_members/COMPLETE.json').exists():
  print('Waiting for bounded historical-source fetch',flush=True);time.sleep(10)
 f=load(T/'features',['event_id','code','logamount','ifbeta','predelay']);ex=pd.read_parquet(T/'exposures.parquet');f=ex[['event_id','code','freeze_date','dose','eligible','first_observed_daily']].merge(f,on=['event_id','code'],how='left',validate='1:1')
 for name,cols in [('pre_cap',['event_id','code','circulating_market_cap','cap_date']),('activity',['event_id','code','activity','activity_n']),('analyst',['event_id','code','analyst']),('qfii',['event_id','code','qfii','announce_date','report_date'])]:
  q=pd.read_parquet(T/f'{name}.parquet',columns=cols);f=f.merge(q,on=['event_id','code'],how='left',validate='1:1')
 f['logcap']=np.log(f.circulating_market_cap.where(f.circulating_market_cap.gt(0)));f.loc[f.eligible.eq(0)&f.dose.eq(0),'activity']=f.loc[f.eligible.eq(0)&f.dose.eq(0),'activity'].fillna(0)
 ah=pd.read_csv(R/'tables/AH_listing_history.csv',dtype={'code':str,'hk_code':str});ah.hk_listing_date=pd.to_datetime(ah.hk_listing_date,format="mixed");ah['hk_delisting_date']=pd.to_datetime(ah.get('hk_delisting_date'),errors='coerce',format='mixed');f=f.merge(ah[['code','hk_listing_date','hk_delisting_date']],on='code',how='left',validate='m:1');f['ah']=(f.hk_listing_date.lt(f.freeze_date)&(f.hk_delisting_date.isna()|f.hk_delisting_date.gt(f.freeze_date))).astype(float)
 f['ah_control_freeze']=f['ah'];events=pd.read_csv(R/'tables/events.csv',parse_dates=['start']).set_index('event_id');f['event_start']=f.event_id.map(events.start);f['ah']=(f.hk_listing_date.lt(f.event_start)&(f.hk_delisting_date.isna()|f.hk_delisting_date.gt(f.event_start))).astype(float)
 dates=pd.DatetimeIndex(pd.read_csv(R/'meta/actual_full_calendar.csv',parse_dates=['date']).date);f['pre_age']=dates.searchsorted(f.freeze_date.to_numpy())-dates.searchsorted(f.first_observed_daily.to_numpy())
 f['decile']=np.nan;f['quintile']=np.nan
 for ev,ix in f.groupby('event_id').groups.items():
  g=f.loc[ix].sort_values('code');known=g.logcap.notna()&g.pre_age.ge(60);r=g.loc[known,'logcap'].rank(method='first');f.loc[r.index,'decile']=np.minimum(9,np.floor((r-1)*10/len(r)))
  known=g.dose.notna()&g.logcap.notna()&g.pre_age.ge(60);r=g.loc[known,'dose'].rank(method='first');f.loc[r.index,'quintile']=np.minimum(4,np.floor((r-1)*5/len(r)))
 cons=pd.read_parquet(Q/'cn_index_cons/full/all.parquet');cons.trade_date=pd.to_datetime(cons.trade_date);cons.component_code=cons.component_code.astype(str).str.zfill(6)
 for name,idx in [('csi300','000300'),('sse50','000016'),('csi500','000905')]:
  f[name]=np.nan;f[name+'_asof']=pd.NaT
  for ev,ix in f.groupby('event_id').groups.items():
   cutoff=f.loc[ix,'freeze_date'].iloc[0];dd=cons[cons.index_code.eq(idx)&cons.trade_date.lt(cutoff)]
   if len(dd):
    dt=dd.trade_date.max();members=set(dd.loc[dd.trade_date.eq(dt),'component_code']);f.loc[ix,name]=f.loc[ix,'code'].astype(str).str[:6].isin(members).astype(float);f.loc[ix,name+'_asof']=dt
 # Static industry snapshot cannot be used before its observation date.
 ind=pd.read_parquet(Q/'cn_industry_tdx/full/all.parquet');ind.snapshot_date=pd.to_datetime(ind.snapshot_date);industry=dict(zip(ind.code6.astype(str).str.zfill(6),ind.l1_code));f['industry']=f.code.astype(str).str[:6].map(industry);f.loc[f.freeze_date.le(ind.snapshot_date.max()),'industry']=np.nan
 receipts=pd.read_csv(R/'tables/historical_membership_receipts.csv')
 for record in receipts[receipts.status.eq('OK')].itertuples():
  dd=pd.read_csv(R/record.file,dtype=str);ix=f.index[f.event_id.eq(record.event_id)];codes=dd.code.str[3:]+'.'+dd.code.str[:2].str.upper()
  if record.kind=='industry':
   by=dict(zip(codes,dd.industry));f.loc[ix,'industry']=f.loc[ix,'code'].astype(str).map(by).replace('',np.nan)
  else:
   f.loc[ix,record.kind]=f.loc[ix,'code'].astype(str).isin(set(codes)).astype(float);f.loc[ix,record.kind+'_asof']=pd.Timestamp(record.requested_date)
 f.to_parquet(T/'event_features.parquet',index=False);f.to_csv(R/'tables/frozen_features_by_event.csv',index=False)
 report=[]
 for ev,g in f.groupby('event_id'):
  for c in ['ah',*CONTROLS,'activity','qfii','industry']:report.append(dict(event_id=ev,feature=c,n=len(g),available=g[c].notna().sum(),missing=g[c].isna().sum(),positive=(g[c].gt(0).sum()if c!='industry'else np.nan)))
 pd.DataFrame(report).to_csv(R/'tables/covariate_coverage.csv',index=False)

def plan():
 r1.SEED=SEED;r1.resampling_plan()

def _inference(d,y,xs,term='closed_x',time='date',ri=True,ri_dose='dose0'):
 # Narrow complete-case frame keeps R1's row order and unique stock/date cell invariant.
 cols=list(dict.fromkeys(['code',time,'date','event_id','closed','dose0',ri_dose,y,*xs]));q=d[cols].replace([np.inf,-np.inf],np.nan).dropna(subset=[y,*xs,time]);model=r1.fit(q,y,xs,time=time,keep=True)
 if 'X'not in model:return [dict(term=term,status='NO_IDENTIFYING_VARIATION',n=len(q))],None
 model.pop('d',None);model['Y']=model['Y'].copy()
 X=model['X'];Y=model['Y'];bread=model['bread'];b=model['b'];names=list(model['names']);ix=names.index(term)if term in names else None
 if ix is None:return [dict(term=term,status='TEST_TERM_DROPPED',n=len(q))],None
 j=ix;xp=X[:,j].copy();yp=Y.copy();other=np.delete(np.arange(X.shape[1]),j);Zx=X[:,1:]if j==0 else X[:,other]
 if len(other):
  zz=np.linalg.pinv(Zx.T@Zx);xp-=Zx@(zz@(Zx.T@xp));yp-=Zx@(zz@(Zx.T@yp))
 den=xp@xp;groups=q.event_id.to_numpy(int);gindex=groups-1
 if groups.max()>46:
  # Placebo ids project to original real-event episode for joint resampling.
  gindex=(groups%100)-1
 with np.load(R/'data/resampling_plan.npz')as draws:W=draws['webb'];P=draws['calendar'];ri_dates=draws['dates']
 scores=np.bincount(gindex,weights=xp*yp,minlength=46);boot=W@scores/den
 rows=model['rows'];row=next(r for r in rows if r['term']==term);row.update(wild_p=(1+np.sum(np.abs(boot)>=abs(row['beta'])))/(B+1),wild_B=B,wild_clusters=len(np.unique(gindex)),wild_statistic='R1 restricted Webb coefficient')
 row['within_r2']=1-np.sum(model['u']**2)/np.sum(Y**2);row['mde80']=(student_t.ppf(.975,row['df'])+norm.ppf(.8))*row['se'];row['ri_p']=np.nan;row['ri_B']=0
 # Exact conditional RI: only tested interaction relabels; nuisance interactions stay observed.
 if ri and len(P):
  origdates=pd.DatetimeIndex(sorted(q.date.unique()));tt=pd.Categorical(q.date,categories=origdates).codes;ixdate=pd.Index(ri_dates).get_indexer(origdates.to_numpy('datetime64[D]').astype('int64'))
  if (ixdate>=0).all():
   z=P[:,ixdate].astype(float);bb=np.bincount(tt,weights=q[ri_dose].to_numpy()*yp,minlength=len(origdates));obs=np.array(q.groupby('date',observed=True).closed.first().reindex(origdates),float)
   if time=='date':
    digest=hashlib.sha256(q.index.to_numpy().tobytes());digest.update(q[ri_dose].to_numpy().tobytes());digest.update(q.date.to_numpy().tobytes());key=(tuple(xs),term,ri_dose,digest.hexdigest())
    if key not in RI_CACHE:
     ee=model['e'];nt=len(origdates);ns=np.bincount(ee).astype(float);A=np.zeros((len(ns),nt));D=np.zeros_like(A);A[ee,tt]=1.;D[ee,tt]=q[ri_dose].to_numpy();Qm=np.diag(np.bincount(tt,weights=q[ri_dose].to_numpy()**2,minlength=nt))-D.T@(D/ns[:,None]);C=np.diag(np.bincount(tt,weights=q[ri_dose].to_numpy(),minlength=nt))-D.T@(A/ns[:,None]);G=np.diag(np.bincount(tt).astype(float))-A.T@(A/ns[:,None]);K=Qm-C@np.linalg.pinv(G,hermitian=True,rcond=1e-11)@C.T
     if len(other):
      H=np.column_stack([np.bincount(tt,weights=q[ri_dose].to_numpy()*Zx[:,k],minlength=nt)for k in range(len(other))]);K-=H@zz@H.T
     K=(K+K.T)/2;RI_CACHE[key]=(np.einsum('ij,ij->i',z@K,z),float(obs@K@obs));del A,D,Qm,C,G,K
    denom,obsdenom=RI_CACHE[key];numer=z@bb;perms=np.divide(numer,denom,out=np.full(len(z),np.nan),where=denom>1e-10);perms=perms[np.isfinite(perms)];observed_check=(obs@bb)/obsdenom;row['ri_beta_abs_error']=abs(observed_check-row['beta']);assert row['ri_beta_abs_error']<1e-7,(term,row['beta'],observed_check);row['ri_method']='R1 calendar / conditional FWL coefficient';row['ri_p']=(1+np.sum(np.abs(perms)>=abs(row['beta'])))/(len(perms)+1);row['ri_B']=len(perms)
   else:
    null=z@bb;observed=obs@bb;row['ri_p']=(1+np.sum(np.abs(null)>=abs(observed)))/(len(null)+1);row['ri_B']=len(null);row['ri_method']='R1 calendar / restricted score for size-decile-date FE'
  else:row['ri_method']='OUTSIDE_R1_CALENDAR_SUPPORT'
 row['sample_y_mean']=q[y].mean();row['sample_y_sd']=q[y].std();raw=d.loc[q.index,'raw_y']if 'raw_y'in d else q[y];row['raw_sample_y_mean']=raw.mean();row['raw_sample_y_sd']=raw.std();uniq=q[['event_id','code',ri_dose]].drop_duplicates();p25,p75=np.quantile(uniq[ri_dose],[.25,.75]);row.update(dose_p25=p25,dose_p75=p75,effect_iqr=row['beta']*(p75-p25),effect_iqr_over_mean=row['beta']*(p75-p25)/row['sample_y_mean']if row['sample_y_mean']else np.nan,effect_iqr_over_sd=row['beta']*(p75-p25)/row['sample_y_sd']if row['sample_y_sd']else np.nan,late_bp_per_1pct_futures_iqr=row['beta']*(p75-p25)*100,effect_iqr_over_raw_mean=row['beta']*(p75-p25)/row['raw_sample_y_mean']if row['raw_sample_y_mean']else np.nan,effect_iqr_over_raw_sd=row['beta']*(p75-p25)/row['raw_sample_y_sd']if row['raw_sample_y_sd']else np.nan,mde80_iqr=row['mde80']*(p75-p25),mde80_iqr_over_sd=row['mde80']*(p75-p25)/row['sample_y_sd']if row['sample_y_sd']else np.nan)
 return rows,boot

def specs():
 out=[('baseline',[],None),('exclude_AH',[],'nonah'),('AH_interactions',['ah','ahdose'],None),('AH_only',[],'ah'),('exclude_AH_control_freeze',[],'nonah'),('AH_interactions_control_freeze',['ah','ahdose'],None),('AH_only_control_freeze',[],'ah')]
 for c in ['HSI_corr','HSI_beta','HSCEI_corr','HSCEI_beta']:out.append(('HK_'+c,['hk_'+c],None))
 out.append(('HK_all',['hk_'+c for c in ['HSI_corr','HSI_beta','HSCEI_corr','HSCEI_beta']],None))
 for i,c in enumerate(CONTROLS):
  out.append(('race_single_'+c,[c],None));out.append(('race_cumulative_'+str(i+1),CONTROLS[:i+1],None))
 out += [('race_available_all',AVAILABLE,None),('race_full_all',CONTROLS,None),('race_available_same_sample_baseline',[], 'race_sample'),('race_full_same_sample_baseline',[], 'full_sample'),('eligible_only',[],'eligible'),('size_decile_date_FE',[],'size'),('RV_high',[],'rvhigh'),('RV_low',[],'rvlow'),('dose_activity',['activity'],None),('dose_QFII',['qfii'],None)]
 for period in ['2017_2019','2020_2023','2024_pre_aug','post_aug2024','all_pre_aug2024']:out.append(('period_'+period,[],period))
 return out

def task(metric,selected=None):
 early=T/f'checkpoint_{metric}.pkl'
 if selected is not None and early.exists():
  saved=pickle.loads(early.read_bytes());assert saved['prereg']==hashlib.sha256((R/'PREREGISTRATION_R2.md').read_bytes()).hexdigest()
  if any((r.get('variant'),r.get('specification'),r.get('exposure'))==selected and r.get('term')=='closed_x'for r in saved['results']):return metric
 columns=['code','date','event_id','closed','dose','eligible',metric,*([metric+'__w01',metric+'__w005']if selected is None else[metric if selected[0]=='raw'else metric+'__'+selected[0]])];columns=list(dict.fromkeys(columns))
 # Frequency and big-move extensions use the same family machinery with a mapped outcome.
 f=load(T/'panel',columns);features=pd.read_parquet(T/'event_features.parquet',columns=['event_id','code','freeze_date','ah','ah_control_freeze','decile','quintile',*CONTROLS,'activity','qfii']);features=features[features.code.isin(f.code.cat.categories)].copy();features['code']=pd.Categorical(features.code,categories=f.code.cat.categories);features['available_sample']=features[AVAILABLE].notna().all(1);features['full_sample']=features[CONTROLS].notna().all(1)
 if selected is not None and selected[1].endswith('_control_freeze'):features['ah']=features.ah_control_freeze
 if selected is None:labels=['freeze_date','ah','decile','available_sample','full_sample']
 else:
  chosen=next(x for x in specs()if x[0]==selected[1]);labels=[]
  if chosen[2]in['nonah','ah']or'ah'in chosen[1]:labels+=['ah']
  if chosen[2]=='size':labels+=['decile']
  if chosen[2]=='race_sample':labels+=['available_sample']
  if chosen[2]=='full_sample':labels+=['full_sample']
  if str(chosen[2])in['2017_2019','2020_2023','2024_pre_aug','post_aug2024','all_pre_aug2024']:labels+=['freeze_date']
 if labels:f=f.merge(features[['event_id','code',*labels]],on=['event_id','code'],how='left',validate='m:1')
 if 'ah'in f:f['ahdose']=f.ah*f.dose
 with np.load(T/'futures_IF.npz')as z:rv=dict(zip(pd.to_datetime(z['dates'],unit='D'),np.sum(z['returns']**2,axis=1)))
 dates=pd.read_csv(R/'tables/event_date_map.csv',parse_dates=['date']);dates['rv']=dates.date.map(rv);groups=dates[dates.closed].groupby('event_id').rv.mean();high=groups.gt(groups.median());f['rvhigh']=f.event_id.map(high)
 checkpoint=T/f'checkpoint_{metric}.pkl'
 if checkpoint.exists():
  saved=pickle.loads(checkpoint.read_bytes());assert saved['prereg']==hashlib.sha256((R/'PREREGISTRATION_R2.md').read_bytes()).hexdigest();results=saved['results'];boots=saved['boots'];dist=saved['dist']
 else:results=[];boots=[];dist=[]
 done={(r['variant'],r['specification'],r['exposure'])for r in results if r.get('term')=='closed_x'}
 joblist=specs()if metric in PRIMARY else [('baseline',[],None)]
 for variant,col in [('raw',metric),('w01',metric+'__w01'),('w005',metric+'__w005')]:
  if selected is not None and variant!=selected[0]:continue
  vals=f[col].to_numpy();v=vals[np.isfinite(vals)];quant=np.quantile(v,[.001,.01,.99,.999])if len(v)else[np.nan]*4;dist=[r for r in dist if r['variant']!=variant];dist.append(dict(metric=metric,variant=variant,n=len(v),missing=len(vals)-len(v),mean=np.mean(v),sd=np.std(v,ddof=1),skew=skew(v,bias=False),excess_kurtosis=kurtosis(v,bias=False),zero_share=np.mean(v==0),q001=quant[0],q01=quant[1],q99=quant[2],q999=quant[3]))
  for spec,controls,subset in joblist:
   for exposure in (['dose','eligible']if spec=='baseline'else['dose']):
    meta=dict(metric=metric,variant=variant,specification=spec,exposure=exposure)
    if selected is not None and (variant,spec,exposure)!=selected:continue
    if (variant,spec,exposure)in done:continue
    if any(c not in f and c not in features for c in controls):results.append(dict(**meta,term='closed_x',status='MISSING_SOURCE',n=0,reason=','.join(c for c in controls if c not in f and c not in features)));continue
    keep=np.ones(len(f),bool);time='date'
    if subset=='nonah':keep=f.ah.eq(0).to_numpy()
    elif subset=='ah':keep=f.ah.eq(1).to_numpy()
    elif subset=='eligible':keep=f.eligible.eq(1).to_numpy()
    elif subset=='race_sample':keep=f.available_sample.to_numpy()
    elif subset=='full_sample':keep=f.full_sample.to_numpy()
    elif subset=='size':keep=f.decile.notna().to_numpy();time='time_group'
    elif subset in ['rvhigh','rvlow']:keep=f.rvhigh.eq(subset=='rvhigh').to_numpy()
    elif subset=='2017_2019':keep=f.freeze_date.dt.year.between(2017,2019).to_numpy()
    elif subset=='2020_2023':keep=f.freeze_date.dt.year.between(2020,2023).to_numpy()
    elif subset=='2024_pre_aug':keep=(f.freeze_date.ge('2024-01-01')&f.freeze_date.lt('2024-08-19')).to_numpy()
    elif subset=='post_aug2024':keep=f.freeze_date.ge('2024-08-19').to_numpy()
    elif subset=='all_pre_aug2024':keep=f.freeze_date.lt('2024-08-19').to_numpy()
    cols=list(dict.fromkeys(['code','date','event_id','closed',exposure,col,*[c for c in controls if c in f]]+(['decile']if time!='date'else[])));d=f.loc[keep,cols].rename(columns={exposure:'dose0',col:'y'}).copy();needed=[c for c in controls if c not in d];d['_rowid']=d.index
    if needed:d=d.merge(features[['event_id','code',*needed]],on=['event_id','code'],how='left',validate='m:1').set_index('_rowid')
    else:d=d.drop(columns='_rowid')
    d['raw_y']=f.loc[keep,metric];d['closed_x']=d.closed.astype(float)*d.dose0;xs=['closed_x','dose0']
    for c in controls:d['cx_'+c]=d.closed.astype(float)*d[c];xs+=['cx_'+c,c]
    if time!='date':d['time_group']=d.date.astype(str)+'_'+d.decile.astype(str)
    if len(d.dropna(subset=['y',*xs]))<100:
     results.append(dict(**meta,term='closed_x',status=('RANK_DEFICIENT_6_OBS_7_REGRESSORS'if metric.endswith('_f15')else'INSUFFICIENT_COMPLETE_CASES'),n=0));del d;release_memory();continue
    rr,boot=inference(d,'y',xs,time=time)
    for row in rr:results.append(dict(**meta,**row))
    if boot is not None:
     boots.append(boot);results[-len(rr)]['boot_index']=len(boots)-1
    release_memory()
    if spec in ['dose_QFII','dose_activity','AH_interactions','AH_interactions_control_freeze']:
     auxterm={'dose_QFII':'qfii','dose_activity':'activity','AH_interactions':'ahdose','AH_interactions_control_freeze':'ahdose'}[spec]
     ar,ab=inference(d,'y',xs,term='cx_'+auxterm,time=time,ri_dose=auxterm)
     for row in ar:
      if row['term']=='cx_'+auxterm:
       results.append(dict(**meta,**row,auxiliary_target=True))
       if ab is not None:boots.append(ab);results[-1]['boot_index']=len(boots)-1
     del ar,ab;release_memory()
     if spec.startswith('AH_interactions'):
      d['ah_slope']=d['cx_ahdose'];d['nonah_slope']=d['closed_x']-d['cx_ahdose'];asx=['ah_slope','nonah_slope','dose0','cx_ah','ah','ahdose'];ar,ab=inference(d,'y',asx,term='ah_slope',ri_dose='ahdose')
      for row in ar:
       if row['term']=='ah_slope':
        results.append(dict(**meta,**row,auxiliary_target=True))
        if ab is not None:boots.append(ab);results[-1]['boot_index']=len(boots)-1
      del ar,ab
    print(json.dumps(dict(**meta,status='DONE',n=rr[0].get('n'),beta=rr[0].get('beta'))),flush=True)
    saved=dict(prereg=hashlib.sha256((R/'PREREGISTRATION_R2.md').read_bytes()).hexdigest(),results=results,boots=boots,dist=dist);temp=checkpoint.with_suffix('.writing');temp.write_bytes(pickle.dumps(saved,protocol=5));temp.replace(checkpoint)
    del d,rr,boot;release_memory()
 saved=dict(prereg=hashlib.sha256((R/'PREREGISTRATION_R2.md').read_bytes()).hexdigest(),results=results,boots=boots,dist=dist);temp=checkpoint.with_suffix('.writing');temp.write_bytes(pickle.dumps(saved,protocol=5));temp.replace(checkpoint)
 pd.DataFrame(results).to_csv(R/f'tables/estimates_{metric}.csv',index=False);pd.DataFrame(dist).to_csv(R/f'tables/distribution_{metric}.csv',index=False);np.savez_compressed(T/f'bootstrap_{metric}.npz',boot=np.array(boots));return metric

def selected_task(job):
 global FIT_LIMITER
 if FIT_LIMITER is None:
  result=task(job[0],job[1]);release_memory();return result
 limiter=FIT_LIMITER
 with limiter:
  FIT_LIMITER=None
  try:
   result=task(job[0],job[1]);release_memory();return result
  finally:FIT_LIMITER=limiter

def run():
 import datetime
 lp=R/'meta/preregistration_lock.json';lock=json.loads(lp.read_text());assert lock['sha256']==hashlib.sha256((R/'PREREGISTRATION_R2.md').read_bytes()).hexdigest();lock['estimation_started']=True;lock['first_estimation_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();lp.write_text(json.dumps(lock,indent=2))
 # One specification per fresh worker releases native allocator arenas without reducing the four-process pool.
 for variant in ['raw','w01','w005']:
  for spec,controls,subset in specs():
   for exposure in (['dose','eligible']if spec=='baseline'else['dose']):
    selected=(variant,spec,exposure)
    slots=1 if len(controls)>0 or spec=='size_decile_date_FE'else 4;context=mp.get_context('spawn');limiter=context.BoundedSemaphore(slots)
    with cf.ProcessPoolExecutor(max_workers=4,max_tasks_per_child=1,mp_context=context,initializer=init_worker,initargs=(limiter,))as pool:list(pool.map(selected_task,[(m,selected)for m in PRIMARY]))
    print('BATCH_COMPLETE',selected,flush=True)
 for metric in PRIMARY:
  saved=pickle.loads((T/f'checkpoint_{metric}.pkl').read_bytes());pd.DataFrame(saved['results']).to_csv(R/f'tables/estimates_{metric}.csv',index=False);pd.DataFrame(saved['dist']).to_csv(R/f'tables/distribution_{metric}.csv',index=False);np.savez_compressed(T/f'bootstrap_{metric}.npz',boot=np.array(saved['boots']))
if __name__=='__main__':globals()[sys.argv[1]]()
