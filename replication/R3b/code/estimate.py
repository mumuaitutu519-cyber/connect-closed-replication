from common import *
from inference import fit,infer,weights,calendar_plan,bh,rw,event_stats
from scipy.stats import t as td,norm,skew,kurtosis
import pyarrow.dataset as ds,concurrent.futures as cf,multiprocessing as mp
LIMIT=None
SLOTS=None

def init(lim,slots):
 global LIMIT,SLOTS
 LIMIT=lim;SLOTS=slots

def load(group,fake,window,metric,joint=False):
 cols=['code','date','event_id','group','fake','window','treated','closed','dose','eligible','quintile',metric,f'{metric}__w01',f'{metric}__w005'];expr=(ds.field('group').isin([group,'CLOSED']) if joint else ds.field('group')==group)
 expr=expr&(ds.field('fake')==fake)&(ds.field('window')==window);f=ds.dataset(T/'panel',format='parquet').to_table(columns=cols,filter=expr,use_threads=False).to_pandas(use_threads=False)
 if joint:
  m=pd.read_csv(R/'tables/event_date_map.csv',parse_dates=['date','anchor']);m=m[m.group.eq(group)&~m.fake&m.window.eq('r1')];c=pd.read_csv(R/'tables/closure_date_map.csv',parse_dates=['date','anchor']);m=pd.concat([m,c],ignore_index=True);m['active']=m.treated.astype(int)+m.closed.astype(int);owner=m.sort_values(['date','active','distance','anchor'],ascending=[True,False,True,True]).drop_duplicates('date');keys=set(zip(owner.event_id,owner.date));keep=np.fromiter(((e,d) in keys for e,d in zip(f.event_id,f.date)),bool,count=len(f));f=f[keep].copy();mapping=owner
 else:
  mapping=pd.read_csv(R/'tables/event_date_map.csv',parse_dates=['date','anchor']);mapping=mapping[mapping.group.eq(group)&mapping.fake.eq(fake)&mapping.window.eq(window)]
 if not joint:
  active=f.event_id.isin(mapping.event_id)
  if not active.all():f=f[active].copy()
 f['code']=pd.Categorical(f.code);f=f.drop(columns=['group','fake','window']);f['treated']=f.treated.astype(np.int8);f['closed']=f.closed.astype(np.int8);assert not f.duplicated(['code','date']).any() or window=='weekday';release();return f,mapping

def fieller(a,b,va,vb,cov,crit):
 A=b*b-crit*crit*vb;BB=-2*a*b+2*crit*crit*cov;C=a*a-crit*crit*va;disc=BB*BB-4*A*C
 if disc<0:return ('ALL_REAL' if A<0 else 'EMPTY',np.nan,np.nan)
 if abs(A)<1e-15:return ('HALF_LINE',np.nan,np.nan)
 roots=sorted([(-BB-np.sqrt(disc))/(2*A),(-BB+np.sqrt(disc))/(2*A)]);return ('BOUNDED' if A>0 else 'EXTERIOR_UNBOUNDED',roots[0],roots[1])

def run(job):
 cost=4 if job[4] or job[0] in ['US','ALL'] else 2 if job[0] in ['UK','EU'] else 1
 with LIMIT:
  LIMIT.wait_for(lambda:SLOTS.value>=cost);SLOTS.value-=cost
 try:
  answer=work(job);release();return answer
 finally:
  with LIMIT:SLOTS.value+=cost;LIMIT.notify_all()

def work(job):
 group,fake,window,metric,joint=job;tag=f'{group}_{int(fake)}_{window}_{metric}_{int(joint)}';dest=T/'fits';dest.mkdir(exist_ok=True)
 if all((dest/f'{tag}{suffix}').exists() for suffix in ['.csv','_boot.npz','_ri.csv','_dist.csv','_event.csv']):return tag
 f,mapping=load(group,fake,window,metric,joint);metadata=dict(group=group,fake=fake,window=window,metric=metric,joint=joint)
 if not len(f):
  empty=[]
  for variant in ['raw','w01','w005']:
   for exposure in ['dose','eligible']:
    empty.append(dict(**metadata,variant=variant,exposure=exposure,term='treated_x',status='NO_VALID_EVENTS',n=0,stocks=0,dates=0,beta=np.nan,se=np.nan,p=np.nan,ci_low=np.nan,ci_high=np.nan,wild_p=np.nan,wild_B=0,ri_p=np.nan,ri_B=0,ri_status='NO_VALID_EVENTS',mde80=np.nan))
  pd.DataFrame(empty).to_csv(dest/f'{tag}.csv',index=False);np.savez_compressed(dest/f'{tag}_boot.npz',boot=np.full((6,B),np.nan));pd.DataFrame([dict(**metadata,target='treated',status='NO_VALID_EVENTS',candidate_blocks=0)]).to_csv(dest/f'{tag}_ri.csv',index=False);pd.DataFrame([dict(**metadata,variant=v,n=0,status='NO_VALID_EVENTS') for v in ['raw','w01','w005']]).to_csv(dest/f'{tag}_dist.csv',index=False)
  pd.DataFrame([dict(**metadata,variant=v,unit=u,n=0,status='NO_VALID_EVENTS') for v in ['raw','w01','w005'] for u in ['day','segment']]).to_csv(dest/f'{tag}_event.csv',index=False);pd.DataFrame().to_csv(dest/f'{tag}_event_detail.csv',index=False);print('NO_VALID_EVENTS',tag,flush=True);return tag
 eventids=sorted(f.event_id.unique());W=(eventids,weights(eventids));plans={};audits=[];rows=[];boots=[];stats=[];ed=[];dist=[];samples=[]
 for target in (['treated','closed'] if joint else ['treated']):
  dates,Z,audit,status=calendar_plan(mapping,target);plans[target]=(dates,Z,status);audit['group']=group;audit['fake']=fake;audit['window']=window;audit['joint']=joint;audit['target']=target;audits.append(audit)
 for variant,col in [('raw',metric),('w01',f'{metric}__w01'),('w005',f'{metric}__w005')]:
  v=f[col].to_numpy(float);v=v[np.isfinite(v)];qs=np.quantile(v,[.001,.01,.99,.999]) if len(v) else [np.nan]*4;dist.append(dict(**metadata,variant=variant,n=len(v),missing=len(f)-len(v),mean=v.mean() if len(v) else np.nan,sd=v.std(ddof=1) if len(v)>1 else np.nan,skew=skew(v) if len(v) else np.nan,excess_kurtosis=kurtosis(v) if len(v) else np.nan,q001=qs[0],q01=qs[1],q99=qs[2],q999=qs[3]))
  if not joint:
   ss,ee=event_stats(f,metric,variant,{k:v for k,v in metadata.items() if k!='metric'});stats+=ss;ed+=ee
  for exposure in ['dose','eligible']:
   q=f[['code','date','event_id','treated','closed',exposure,col]].rename(columns={exposure:'dose0',col:'y'}).replace([np.inf,-np.inf],np.nan).dropna(subset=['dose0','y']);q['treated_x']=q.treated*q.dose0;xs=['treated_x','dose0']
   if joint:q['closed_x']=q.closed*q.dose0;xs=['treated_x','closed_x','dose0']
   md={**metadata,'variant':variant,'exposure':exposure};q.attrs['unique_cells']=joint or window!='weekday';model=fit(q,xs);before=len(rows)
   if not all(x in model['names'] for x in xs if x.endswith('_x')):
    rows.append(dict(**md,status='NO_IDENTIFYING_VARIATION',n=len(q)));boots.append(np.full(B,np.nan));continue
   for target in (['treated','closed'] if joint else ['treated']):
    rr,boot=infer(q,model,f'{target}_x',W,plans[target]);rr.update(md);rr['sample_y_mean']=q.y.mean();rr['sample_y_sd']=q.y.std();dd=q[['event_id','code','dose0']].drop_duplicates(['event_id','code']);iqr=dd.dose0.quantile(.75)-dd.dose0.quantile(.25);rr['dose_iqr']=iqr;rr['effect_iqr']=rr['beta']*iqr;rows.append(rr);boots.append(boot);release()
   if joint:
    j=model['names'].index('treated_x');k=model['names'].index('closed_x');a,b=model['b'][[j,k]];V=model['V'];va,vb,cov=V[j,j],V[k,k],V[j,k];var=va+vb-2*cov;se=np.sqrt(var) if var>=0 else np.nan;diff=a-b;df=model['df'];crit=td.ppf(.975,df);ratio=a/b if b!=0 else np.nan;rv=va/b**2+a*a*vb/b**4-2*a*cov/b**3 if b!=0 else np.nan;rse=np.sqrt(rv) if rv>=0 else np.nan;fst,fl,fh=fieller(a,b,va,vb,cov,crit)
    # Null-restricted wild for beta_holiday=beta_closed, FWL contrast after reparameterization.
    X=model['X'];l=np.zeros(X.shape[1]);l[j]=1;l[k]=-1;vec=X@(model['bread']@l);u0=model['u']+vec*diff/(l@model['bread']@l);gi=pd.Categorical(q.event_id,categories=eventids).codes;sc=np.bincount(gi,weights=vec*u0,minlength=len(eventids));boot=W[1]@sc
    row=dict(**md,term='treated_minus_closed',beta=diff,se=se,p=2*td.sf(abs(diff/se),df) if se>0 else np.nan,ci_low=diff-crit*se,ci_high=diff+crit*se,df=df,n=len(q),stocks=len(model['entities']),dates=len(model['dates']),holiday_beta=a,closed_beta=b,cov_holiday_closed=cov,ratio=ratio,ratio_delta_se=rse,ratio_ci_low=ratio-crit*rse,ratio_ci_high=ratio+crit*rse,fieller_status=fst,fieller_low=fl,fieller_high=fh,wild_p=(1+np.sum(np.abs(boot)>=abs(diff)))/(B+1),wild_B=B,ri_p=np.nan,ri_B=0,ri_status='NO_EXACT_EQUALITY_CALENDAR_DESIGN',mde80=(crit+norm.ppf(.8))*se,status='OK' if np.isfinite(se) else 'NONPOSITIVE_TWO_WAY_VARIANCE');rows.append(row);boots.append(boot);del X,vec,u0,gi,sc,boot
   if variant=='w01' and exposure=='dose':
    z=q.groupby(['event_id','treated','closed'],observed=True).agg(rows=('code','size'),stocks=('code','nunique'),dates=('date','nunique')).reset_index();z['group']=group;z['fake']=fake;z['window']=window;z['metric']=metric;z['joint']=joint;samples.append(z)
   del q,model;release()
 out=pd.DataFrame(rows);out.to_csv(dest/f'{tag}.csv',index=False);np.savez_compressed(dest/f'{tag}_boot.npz',boot=np.array(boots));pd.concat(audits,ignore_index=True).to_csv(dest/f'{tag}_ri.csv',index=False)
 if samples:pd.concat(samples).to_csv(dest/f'{tag}_sample.csv',index=False)
 pd.DataFrame(stats).to_csv(dest/f'{tag}_event.csv',index=False);pd.DataFrame(ed).to_csv(dest/f'{tag}_event_detail.csv',index=False);pd.DataFrame(dist).to_csv(dest/f'{tag}_dist.csv',index=False);print('FIT',tag,len(rows),flush=True);return tag

def main():
 lock=json.loads((R/'meta/preregistration_lock.json').read_text());assert hashlib.sha256((R/'PREREGISTRATION_R3b.md').read_bytes()).hexdigest()==lock['sha256']
 if lock['first_estimate_at'] is None:lock['first_estimate_at']=pd.Timestamp.now(tz='UTC').isoformat();js(R/'meta/preregistration_lock.json',lock)
 jobs=[(g,f,w,m,False) for g in GROUPS for f in [False,True] for w in ['r1','weekday'] for m in PRIMARY]+[(g,False,'r1',m,True) for g in GROUPS for m in PRIMARY]
 pending=[]
 for job in jobs:
  g,f,w,m,j=job;tag=f'{g}_{int(f)}_{w}_{m}_{int(j)}'
  if not all((T/'fits'/f'{tag}{suffix}').exists() for suffix in ['.csv','_boot.npz','_ri.csv','_dist.csv','_event.csv']):pending.append(job)
 jobs=pending
 # Recycle wide-job workers; smaller groups share the four-process memory budget.
 ctx=mp.get_context('spawn');lim=ctx.Condition();slots=ctx.Value('i',4)
 cursor=0
 while cursor<len(jobs):
  g,f,w,m,joint=jobs[cursor];width=1 if joint or g in ['US','ALL'] else 2 if g in ['UK','EU'] else 4
  batch=jobs[cursor:cursor+width]
  if any(x[0]!=g or x[4]!=joint for x in batch):batch=[jobs[cursor]]
  with cf.ProcessPoolExecutor(max_workers=len(batch),mp_context=ctx,initializer=init,initargs=(lim,slots)) as pool:
   for tag in pool.map(run,batch):pass
  cursor+=len(batch)

if __name__=='__main__':main()
