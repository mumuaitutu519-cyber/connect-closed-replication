from common import *
from inference import fit,close,run,summarize,plan,bh,weights,WEBB
from scipy.stats import t as student_t,binomtest,norm
import pyarrow.dataset as ds,concurrent.futures as cf,multiprocessing as mp
CC=RACE+HK
LABEL={'if_delay':'DelayIF','ih_delay':'DelayIH','if_r2_now':'Sync','ln_amount':'Value','cs_bp':'SpreadCS','ar_bp':'SpreadAR','amihud':'Amihud'}
LIMIT=None;AVAILABLE=None
def init_limit(condition,available):
 global LIMIT,AVAILABLE
 LIMIT=condition;AVAILABLE=available

def read(cols,family='main'):
 paths=sorted((T/'analysis_family'/family).glob('*.parquet'));d=ds.dataset(paths,format='parquet').to_table(columns=list(dict.fromkeys(cols)),use_threads=False).to_pandas(use_threads=False);d.code=pd.Categorical(d.code);return d

def load(metric,v='w01',controls=False,family='main',extra=()):
 col=metric if v=='raw'else metric+'__'+v;cols=['code','date','event_id','closed','dose',col,*extra]
 if controls:cols+=RACE+[c+'__'+v for c in HK]
 special=[c for c in ['role','relative']if c in cols];cols=[c for c in cols if c not in special]
 f=read(cols,family).rename(columns={col:'y',**{c+'__'+v:c for c in HK}});
 if special:f=f.merge(pd.read_csv(P/'tables/event_date_map.csv',parse_dates=['date'])[['event_id','date',*special]],on=['event_id','date'],validate='m:1')
 f['closed_x']=f.closed.astype(float)*f.dose;xs=['closed_x','dose']
 if controls:
  for c in CC:f['cx_'+c]=f.closed*f[c];xs += [c,'cx_'+c]
 return f,xs

def complete(f,xs):
 good=np.ones(len(f),bool)
 for c in ['y',*xs]:good &=np.isfinite(f[c].to_numpy(float))
 return f.loc[good].reset_index(drop=True)

def evstats(v,n,stocks,**meta):
 v=np.asarray(v,float);v=v[np.isfinite(v)];e=len(v);se=v.std(ddof=1)/np.sqrt(e)if e>1 else np.nan;tt=v.mean()/se if se>0 else np.nan;nz=v[v!=0];W=np.random.default_rng(SEED).choice(WEBB,(B,e));boot=W@v/e if e else np.array([]);crit=student_t.ppf(.975,e-1)if e>1 else np.nan
 return dict(**meta,beta_x100=v.mean()*100 if e else np.nan,se_x100=se*100,ci_low_x100=(v.mean()-crit*se)*100 if e else np.nan,ci_high_x100=(v.mean()+crit*se)*100 if e else np.nan,event_t=tt,event_t_p=2*student_t.sf(abs(tt),e-1)if e>1 else np.nan,sign_p=binomtest(int((nz>0).sum()),len(nz),.5).pvalue if len(nz)else np.nan,positive=int((v>0).sum()),negative=int((v<0).sum()),wild_event_mean_p=(1+(abs(boot)>=abs(v.mean())).sum())/(B+1)if e else np.nan,wild_unique_draws=len(np.unique(W,axis=0)),wild_B=B,n=n,stocks=stocks,events=e,test_observations=e,test_df=e-1,sign_trials=len(nz))

def market_daily():
 d=pd.read_csv(R/'tables/minute_day_receipts.csv',parse_dates=['date']);d['if_rv']=d.date.map(valid_if_variance());mapping=pd.read_csv(P/'tables/event_date_map.csv',parse_dates=['date']);valid=pd.read_csv(P/'R7/tables/event_complete_case_audit.csv');ids=valid.loc[valid.baseline_n.gt(0),'event_id'];mapping=mapping[mapping.event_id.isin(ids)];sel=pd.read_csv(R/'tables/futures_contract_selection.csv',parse_dates=['date']);vol=pd.read_csv(R/'tables/futures_daily_volume.csv',parse_dates=['date']);allif=vol[vol['product'].eq('IF')].groupby('date',as_index=False).volume.sum().rename(columns={'volume':'if_volume_all'});d=d.merge(allif,on='date',how='left');vol=sel[sel['product'].eq('IF')].merge(vol,on=['product','contract','date'],how='left');d=d.merge(vol[['date','volume']],on='date',how='left')
 with np.load(T/'futures_IF.npz')as quotes:counts=pd.Series(np.isfinite(quotes['returns']).sum(1),index=pd.to_datetime(quotes['dates'],unit='D'))
 quality=d[d.date.between(counts.index.min(),counts.index.max())][['date','if_rv']].copy();quality['valid_minutes']=quality.date.map(counts);quality=quality[quality.valid_minutes.lt(180)];quality['event_id']=quality.date.map(mapping.set_index('date').event_id);quality['status']='SELECTED_CONTRACT_QUOTE_MISSING_NOT_ZERO_VARIANCE';quality['n']=quality.valid_minutes;quality['stocks']=np.nan;quality['events']=quality.event_id.notna().astype(int);save(quality,'IF_quote_quality_exclusions.csv')
 g=mapping.merge(d[['date','market_amount','if_rv','if_volume_all','volume']],on='date',how='left');save(g.assign(n=1,stocks=np.nan,events=1),'market_daily_windows.csv');rows=[];contr=[]
 for variable in ['market_amount','if_rv','if_volume_all','volume']:
  z=g.groupby(['event_id','closed'])[variable].mean().unstack('closed').dropna();val=z[True]-z[False];r=evstats(val,len(g[g[variable].notna()]),np.nan,variable=variable,unit={'market_amount':'RMB','if_rv':'sum minute log returns squared','if_volume_all':'all IF contracts, source volume units','volume':'preselected IF contract, source volume units'}[variable]);r.update(closed_mean=z[True].mean(),control_mean=z[False].mean(),difference=val.mean(),paired_t_p=r['event_t_p'],mean_relative_change=(z[True]/z[False]-1).mean(),closed_days=g.loc[g.closed&g[variable].notna(),'date'].nunique(),control_days=g.loc[~g.closed&g[variable].notna(),'date'].nunique(),daily_closed_mean=g.loc[g.closed,variable].mean(),daily_control_mean=g.loc[~g.closed,variable].mean());rows.append(r)
  for eid in z.index:contr.append(dict(variable=variable,event_id=eid,closed_mean=z.loc[eid,True],control_mean=z.loc[eid,False],difference=val.loc[eid],n=int((g.event_id.eq(eid)&g[variable].notna()).sum()),stocks=np.nan,events=1))
 save(rows,'market_state_paired_tests.csv');save(contr,'market_state_event_contrasts.csv');state=d[['date','market_amount','if_rv']].copy();state['log_market_amount']=np.log(state.market_amount.where(state.market_amount>0));means=state[state.date.isin(mapping.loc[~mapping.closed,'date'])][['if_rv','log_market_amount']].mean();scales=state[state.date.isin(mapping.loc[~mapping.closed,'date'])][['if_rv','log_market_amount']].std()
 for c in ['if_rv','log_market_amount']:state[c+'_z']=(state[c]-means[c])/scales[c]
 save([dict(variable=c,center=means[c],scale=scales[c],n=int(state.loc[state.date.isin(mapping.loc[~mapping.closed,'date']),c].notna().sum()),reference_control_dates=mapping.loc[~mapping.closed,'date'].nunique(),stocks=np.nan,events=len(ids))for c in means.index],'market_centering.csv');state.to_parquet(T/'market_state.parquet',index=False)

def state_job(job):
 metric,v,controls=job;dest=R/'tables'/f'state_{metric}_{v}_{int(controls)}.csv'
 if dest.exists():return str(dest)
 f,xs=load(metric,v,controls);f=f.merge(pd.read_parquet(T/'market_state.parquet'),on='date',how='left',validate='m:1');rows=[]
 for c in ['if_rv_z','log_market_amount_z']:f['hold_'+c]=f.dose*f[c];f['closed_hold_'+c]=f.closed*f['hold_'+c]
 allxs=xs+['hold_if_rv_z','hold_log_market_amount_z','closed_hold_if_rv_z','closed_hold_log_market_amount_z'];f=complete(f,allxs)
 for name,new in [('same_sample_base',[]),('Hold_x_RV',['hold_if_rv_z']),('Hold_x_LogAmount',['hold_log_market_amount_z']),('Hold_x_both',['hold_if_rv_z','hold_log_market_amount_z']),('Hold_x_both_and_Closed',['hold_if_rv_z','hold_log_market_amount_z','closed_hold_if_rv_z','closed_hold_log_market_amount_z'])]:
  r=run(f,xs+new,plan=plan('main'));r.update(metric=metric,variant=v,controls='full16'if controls else'none',specification=name);rows.append(r)
  if name=='Hold_x_both_and_Closed':
   # Marginal Closed×Hold at treated-state mean, estimated with exact parameter redefinition.
   zz=f.loc[f.closed,['if_rv_z','log_market_amount_z']].mean();q=f.copy()
   for c in zz.index:q['closed_hold_'+c]-=zz[c]*q.closed_x
   rr=run(q,xs+new,plan=None);rows.append(dict(**rr,metric=metric,variant=v,controls='full16'if controls else'none',specification='marginal_at_treated_mean'));del q
 base=rows[0]['beta']
 for r in rows:r['retention_same_sample']=r.get('beta',np.nan)/base if base else np.nan
 save(rows,dest.name);return str(dest)

def groups_job(job):
 metric,v=job;dest=R/'tables'/f'groups_{metric}_{v}.csv'
 if dest.exists():return str(dest)
 f,xs=load(metric,v,True);ev=pd.read_csv(P/'R5/tables/F_event_classification.csv').set_index('event_id');f['hk']=f.event_id.map(ev.hkonly);f['hk_dose']=f.hk*f.dose;f['diff_x']=f.closed*f.hk_dose;xs+=['hk_dose','diff_x'];rows=[]
 for saturated in [False,True]:
  xx=xs.copy()
  if saturated:
   for c in CC:f['hk_'+c]=f.hk*f[c];f['hk_cx_'+c]=f.hk*f['cx_'+c];xx+=['hk_'+c,'hk_cx_'+c]
  r=run(f,xx,term='diff_x',plan=plan('main'),dosecol='hk_dose');rows.append(dict(metric=metric,variant=v,specification='group_saturated_controls'if saturated else'common_controls',**r))
 save(rows,dest.name);return str(dest)

def qfii_job(job):
 metric,v=job;dest=R/'tables'/f'qfii_{metric}_{v}.csv'
 if dest.exists():return str(dest)
 f,xs=load(metric,v,True,extra=['qfii']);f['cx_qfii']=f.closed*f.qfii;xs+=['qfii','cx_qfii'];out=[]
 for term,dose in [('closed_x','dose'),('cx_qfii','qfii')]:out.append(dict(metric=metric,variant=v,specification='full16_QFII',**run(f,xs,term=term,plan=plan('main'),dosecol=dose)))
 save(out,dest.name);return str(dest)

def quiet_job(job):
 metric,v,family=job;dest=R/'tables'/f'{family}_{metric}_{v}.csv'
 old=pd.read_csv(dest)if dest.exists()else None
 if old is not None and 'wild_cluster_scheme'in old and old.loc[old.specification.ne('quiet_only_original_FE'),'wild_cluster_scheme'].eq('date_owned_nearest_event_union').all():return str(dest)
 a,_=load(metric,v,False);b,_=load(metric,v,False,family=family,extra=['quintile']);a['quiet_x']=0.;a['quiet_dose']=0.;a['real_dose']=a.dose;b['quiet_x']=b.closed_x;b['quiet_dose']=b.dose;b['real_dose']=0.;b.closed_x=0.;f=pd.concat([a,b],ignore_index=True);del a;f.code=pd.Categorical(f.code);xs=['closed_x','quiet_x','real_dose','quiet_dose'];f=complete(f,xs);ev=pd.read_csv(R/'tables/design_events.csv',parse_dates=['start']).set_index('event_id');owner=f[['date','event_id']].drop_duplicates();owner['anchor']=owner.event_id.map(ev.start);owner['distance']=(owner.date-owner.anchor).abs().dt.days;owner=owner.sort_values(['date','distance','anchor','event_id']).drop_duplicates('date').set_index('date').event_id;f['wild_event_id']=f.date.map(owner);assert f.groupby('date').wild_event_id.nunique().max()==1;rows=[];m=fit(f,xs)
 for term in ['closed_x','quiet_x']:rows.append(dict(metric=metric,variant=v,family=family,specification='joint_common_stock_date_FE',**summarize(f,m,term)))
 # Exact invertible reparameterization: [C,Q] -> [C,Q+C]. Reuse the same
 # within data and covariance; coefficient C is then beta_C - beta_Q.
 ic=m['names'].index('closed_x');iq=m['names'].index('quiet_x');A=np.eye(len(m['names']));A[ic,iq]=1.;Ai=np.linalg.inv(A)
 for start in range(0,len(f),32768):m['a'][m['indices'][iq],start:start+32768]+=np.asarray(m['a'][m['indices'][ic],start:start+32768])
 m['b']=Ai@m['b'];m['V']=Ai@m['V']@Ai.T;m['bread']=Ai@m['bread']@Ai.T;m['xx']=A.T@m['xx']@A;m['xy']=A.T@m['xy'];r=summarize(f,m,'closed_x');assert abs(r['beta']-(rows[0]['beta']-rows[1]['beta']))<1e-8;rows.append(dict(metric=metric,variant=v,family=family,specification='Closed_minus_Quiet_same_regression',**r));
 for row in rows:row['wild_cluster_scheme']='date_owned_nearest_event_union'
 if old is not None:
  for row,previous in zip(rows,old[old.specification.ne('quiet_only_original_FE')].to_dict('records')):assert abs(row['beta']-previous['beta'])<1e-8
 close(m);del f,m;release()
 if old is not None and (R/'tables'/f'{family}_{metric}_{v}_event.csv').exists():
  rows.extend(old[old.specification.eq('quiet_only_original_FE')].to_dict('records'));save(rows,dest.name);return str(dest)
 b['closed_x']=b.quiet_x;r=run(b,['closed_x','dose'],plan=plan(family));rows.append(dict(metric=metric,variant=v,family=family,specification='quiet_only_original_FE',**r));d=complete(b,['closed_x','dose']);means=d.groupby(['event_id','date','closed','quintile'],observed=True).y.mean().unstack('quintile');diff=(means.get(4)-means.get(0)).rename('diff').reset_index();z=diff.groupby(['event_id','closed'])['diff'].mean().unstack('closed');val=z.get(True)-z.get(False);r=evstats(val,len(d),d.code.nunique(),metric=metric,variant=v,group=family,contrast='daily Q5-Q1 then closed-minus-normal');save([r],f'{family}_{metric}_{v}_event.csv');zz=z.assign(contrast=val,n=d.groupby('event_id').size(),stocks=d.groupby('event_id',observed=True).code.nunique(),events=1).reset_index();save(zz,f'{family}_{metric}_{v}_contrasts.csv');save(rows,dest.name);return str(dest)

def auxiliary_job(job):
 metric,v=job;dest=R/'tables'/f'aux_{metric}_{v}.csv'
 if dest.exists():
  if metric not in ['if_delay','ih_delay','if_r2_now']:return str(dest)
  side=R/'tables'/f'table7_pooled_{metric}_{v}.csv'
  if side.exists()and 'quintile_sample'in pd.read_csv(side):return str(dest)
 f,xs=load(metric,v,True,extra=['quintile']);d=complete(f,xs);
 if not dest.exists():
  r=run(d,xs,plan=plan('main'));save([dict(metric=metric,variant=v,specification='full16',**r)],dest.name)
 # Controls partialled from original y; remove FE and nuisance jointly while retaining quintile effects.
 if metric in ['if_delay','ih_delay','if_r2_now']:
  q=d[d.quintile.notna()].copy();xx=['dose']
  for k in range(1,5):q[f'q{k}']=q.quintile.eq(k).astype(float);q[f'cq{k}']=q.closed*q[f'q{k}'];xx += [f'q{k}',f'cq{k}']
  xx += [c for c in xs if c not in ['closed_x','dose']];q=complete(q,xx);m=fit(q,xx);nuis=np.zeros(len(q))
  for j,c in enumerate(m['names']):
   if c not in ['dose',*[f'q{k}'for k in range(1,5)],*[f'cq{k}'for k in range(1,5)]]:nuis += m['b'][j]*q[c].to_numpy(float)
  q['adj']=q.y-nuis;means=q.groupby(['event_id','date','closed','quintile'],observed=True).adj.mean().unstack('quintile');dif=(means.get(4)-means.get(0)).rename('diff').reset_index();z=dif.groupby(['event_id','closed'])['diff'].mean().unstack('closed');val=z.get(True)-z.get(False);save([evstats(val,len(q),q.code.nunique(),metric=metric,variant=v,specification='full16_adjusted_Table7_equal_event')],f'table7_{metric}_{v}.csv');zz=z.assign(contrast=val,n=q.groupby('event_id').size(),stocks=q.groupby('event_id',observed=True).code.nunique(),events=1).reset_index();save(zz,f'table7_{metric}_{v}_events.csv');save([dict(metric=metric,variant=v,specification='full16_quintile_interaction_Q5minusQ1',quintile_sample='frozen_quintile_nonmissing',**summarize(q,m,'cq4'))],f'table7_pooled_{metric}_{v}.csv');close(m)
 return str(dest)

def dynamic_job(job):
 metric,v=job;dest=R/'tables'/f'dynamic_{metric}_{v}.csv'
 if dest.exists():return str(dest)
 f,xs=load(metric,v,True,extra=['role','relative']);ev=pd.read_csv(P/'tables/events.csv',parse_dates=['resume']).set_index('event_id');cal=pd.DatetimeIndex(pd.read_csv(P/'meta/actual_full_calendar.csv',parse_dates=['date']).date);pos={d:i for i,d in enumerate(cal)};f['resume_time']=f.date.map(pos)-f.event_id.map(ev.resume.map(pos));f['cell']=np.where(f.role.eq('control_pre'),'pre'+f.relative.astype(int).astype(str),np.where(f.closed,'closed'+f.resume_time.astype(int).astype(str),'resume'+f.resume_time.astype(int).astype(str)));f.loc[f.role.eq('control_pre')&f.relative.eq(-1),'cell']='reference';labels=sorted(set(f.cell)-{'reference'});xx=[c for c in xs if c!='closed_x'];targets=[]
 for k,label in enumerate(labels):term=f'dyn{k}';f[term]=f.cell.eq(label)*f.dose;xx.append(term);targets.append((label,term))
 f=complete(f,xx);m=fit(f,xx);rows=[]
 for label,term in targets:
  r=summarize(f,m,term);sup=f[f.cell.eq(label)];rows.append(dict(metric=metric,variant=v,cell=label,cell_n=len(sup),cell_stocks=sup.code.nunique(),cell_events=sup.event_id.nunique(),**r))
 close(m);save(rows,dest.name);return str(dest)

def calibrated():
 f,_=load('r2_1','w01');g,_=load('if_r2_now','w01');g=g.rename(columns={'y':'sync'});f=f.merge(g[['code','date','sync']],on=['code','date'],how='left',validate='1:1');cols=[f'{p}_{h}__w01'for p in ['beta','r2']for h in [1,5,15,30,60]];h=read(['code','date','event_id','dose',*cols]);h['common5']=np.isfinite(h[cols].to_numpy(float)).all(1);missing=h[np.isfinite(h.dose)&np.isfinite(h.r2_1__w01)&~h.common5].copy();missing['missing_variables']=[';'.join(c for c in cols if not np.isfinite(row[c]))for _,row in missing.iterrows()];save(missing[['code','date','event_id','missing_variables']].assign(n=1,stocks=1,events=1),'sync_1min_four_coarse_missing_rows.csv');f=f.merge(h[['code','date','common5']],on=['code','date'],validate='1:1');del g,h;release();rows=[]
 for col,sample in [('y','own'),('y','common5'),('y','common5_and_Sync'),('sync','common5_and_Sync'),('y','sync_common'),('sync','sync_common')]:
  q=f.copy();q['y']=f[col]
  if sample=='common5':q=q[f.common5]
  if sample=='common5_and_Sync':q=q[f.common5&np.isfinite(f.sync)&np.isfinite(f.y)]
  if sample=='sync_common':q=q[np.isfinite(f.sync)&np.isfinite(f.y)]
  rows.append(dict(metric='r2_1'if col=='y'else'Sync',sample=sample,**run(q,['closed_x','dose'],plan=plan('main'))))
 save(rows,'sync_1min_bridge.csv')
 # Effective intervals are independent of outcome selection; retain both eligible and regression samples.
 cols=['code','date','event_id','closed','dose','if_r2_now__w01',*[f'mom{h}_n'for h in [1,5,15,30,60]]];d=read(cols);out=[]
 for sample,mask in [('eligible_known_dose_with_IF',np.isfinite(d.dose)&d.mom1_n.gt(0)),('main_Sync',np.isfinite(d.dose)&np.isfinite(d.if_r2_now__w01))]:
  for h in [1,5,15,30,60]:
   c=f'mom{h}_n';z=d.loc[mask,c];qq=z.quantile([0,.01,.05,.25,.5,.75,.95,.99,1]);out.append(dict(sample=sample,minutes=h,mean=z.mean(),sd=z.std(),**{f'p{int(k*100):02d}':v for k,v in qq.items()},n=len(z),stocks=d.loc[z.index,'code'].nunique(),events=d.loc[z.index,'event_id'].nunique()))
 save(out,'effective_intervals_distribution.csv')


def audit_controls():
 rows=[]
 for family in ['main','US']:
  f,xs=load('if_delay','w01',True,family=family);valid=np.isfinite(f[['y',*xs]].to_numpy(float)).all(1)
  for eid,g in f.groupby('event_id',observed=True):
   good=g.index[valid[g.index]];miss=[c for c in CC if g[c].notna().sum()==0];rows.append(dict(family=family,event_id=eid,baseline_n=int((np.isfinite(g.y)&np.isfinite(g.dose)).sum()),complete_n=len(good),missing_all=';'.join(miss),treated_dates=';'.join(str(pd.Timestamp(x).date())for x in sorted(g.loc[g.closed&np.isfinite(g.y),'date'].unique())),complete_treated_dates=';'.join(str(pd.Timestamp(x).date())for x in sorted(f.loc[good].loc[lambda z:z.closed,'date'].unique())),n=len(good),stocks=f.loc[good,'code'].nunique(),events=int(len(good)>0)))
 save(rows,'control_sample_audit.csv')


def worker(job):
 kind,args=job
 light=(kind=='state_job'and not args[2])or(kind=='quiet_job'and args[2].endswith('_both'))
 weight=1 if light else 2
 with LIMIT:
  while AVAILABLE.value<weight:LIMIT.wait()
  AVAILABLE.value-=weight
 try:
  result=globals()[kind](args);release();return result
 finally:
  with LIMIT:AVAILABLE.value+=weight;LIMIT.notify_all()

def prepare():
 lock=json.loads((R/'meta/preregistration_lock.json').read_text());lock['estimation_started']=True
 records=[json.loads(line)for line in (R/'logs/stage_resource_receipts.jsonl').read_text().splitlines()]
 starts=[r['start']for r in records if str(r['command'][-1]).endswith('analyze.py')]
 old_first=pd.Timestamp(lock.get('first_estimation_utc',pd.Timestamp.now(tz='UTC'))).timestamp();lock['first_estimation_utc']=pd.Timestamp(min([old_first,*starts]),unit='s',tz='UTC').isoformat();js(R/'meta/preregistration_lock.json',lock);market_daily();plan('main')
 for family in ['quiet30_both','quiet40_both','quiet30_rv','quiet40_rv']:plan(family)
 audit_controls();calibrated()

def job_process(job,status):
 kind,args=job
 result=globals()[kind](args)
 js(Path(status),dict(result=str(result)))

def main():
 if len(sys.argv)>1 and sys.argv[1]=='--prepare':prepare();return
 import subprocess
 subprocess.run([sys.executable,str(R/'code/analyze.py'),'--prepare'],check=True)
 jobs=[]
 for v in VARIANTS:
  for m in ['if_delay','ih_delay','if_r2_now']:
   for cc in [False,True]:jobs.append(('state_job',(m,v,cc)))
   jobs.append(('groups_job',(m,v)));jobs.append(('qfii_job',(m,v)))
   for family in ['quiet30_both','quiet40_both','quiet30_rv','quiet40_rv']:jobs.append(('quiet_job',(m,v,family)))
  for m in ['if_b0','if_b1','if_lag_sum','if_total_beta']:jobs.append(('qfii_job',(m,v)))
  for m in ['if_delay','ih_delay','if_r2_now','ln_amount','cs_bp','ar_bp','amihud']:jobs.append(('auxiliary_job',(m,v)))
  for m in ['if_delay','ih_delay']:jobs.append(('dynamic_job',(m,v)))
 ctx=mp.get_context('spawn')
 # Up to six one-shot workers; reserve conservative RSS budgets before
 # starting each job. Completed workers exit immediately and release allocator pages.
 pending=list(enumerate(jobs));active=[];statusdir=T/'job_status';statusdir.mkdir(exist_ok=True)
 def budget(job):
  kind,args=job
  if kind=='dynamic_job':return 8.
  if kind=='quiet_job':return 3.5 if args[2].endswith('_both')else 6.
  if kind=='state_job'and not args[2]:return 2.
  return 4.5
 try:
  while pending or active:
   used=sum(item[2]for item in active)
   while len(active)<6:
    possible=next((k for k,(_,job)in enumerate(pending)if used+budget(job)<=9.5),None)
    if possible is None:break
    index,job=pending.pop(possible);status=statusdir/f'{index:04d}.json';process=ctx.Process(target=job_process,args=(job,str(status)));process.start();allocation=budget(job);active.append((process,status,allocation));used+=allocation
   for item in active[:]:
    process,status,allocation=item
    if process.is_alive():continue
    process.join()
    if process.exitcode!=0:raise RuntimeError(f'Analysis worker {process.pid} exited {process.exitcode}')
    print('ANALYZE',json.loads(status.read_text())['result'],flush=True);process.close();active.remove(item)
   if active:time.sleep(.1)
 finally:
  for process,_,_ in active:
   if process.is_alive():process.terminate()
   process.join()
 for prefix in ['state','groups','qfii','aux','dynamic']:
  d=pd.concat([pd.read_csv(p)for p in sorted((R/'tables').glob(prefix+'_*.csv'))if p.name not in ['market_state_paired_tests.csv','market_state_event_contrasts.csv',prefix+'_all.csv']],ignore_index=True)
  keys=[c for c in ['variant','controls','specification','term']if c in d]
  for pp in ['p','wild_p','ri_p']:
   if pp in d:d['BH_'+pp]=d.groupby(keys,dropna=False)[pp].transform(bh)
  save(d,prefix+'_all.csv')
if __name__=='__main__':main()
