from common import *
from infer import fit,infer,draws
from estimate import read
import concurrent.futures as cf,multiprocessing as mp
LIMIT=None
def init(lim):
 global LIMIT
 LIMIT=lim

def worker(job):
 with LIMIT:return work(job)

def work(job):
 metric,variant=job;dest=R/'tables'/f'H_dynamic_{metric}_{variant}.csv'
 marker=T/f'dynamic_{metric}_{variant}.json'
 if marker.exists()and dest.exists():return str(dest)
 col=metric if variant=='raw'else metric+'__'+variant;f=read(['code','date','event_id','closed','dose','role','relative',col]).rename(columns={col:'y','dose':'dose0'});f=f.replace([np.inf,-np.inf],np.nan).dropna(subset=['y','dose0']);ev=pd.read_csv(P/'tables/events.csv',parse_dates=['start','resume']).set_index('event_id');full=pd.DatetimeIndex(pd.read_csv(P/'meta/actual_full_calendar.csv',parse_dates=['date']).date);pos={d:i for i,d in enumerate(full)};f['first_time']=f.date.map(pos)-f.event_id.map(ev.start.map(pos));f['resume_time']=f.date.map(pos)-f.event_id.map(ev.resume.map(pos));W,_=draws();rows=[]
 original=f.copy()
 for scheme in ['first','resume','resume_extended']:
  f=original.copy()
  if scheme=='resume_extended':
   import pyarrow.dataset as ds
   extra=ds.dataset(T/'H_extra',format='parquet').to_table(columns=['code','date','event_id','closed','dose','role','relative',col],use_threads=False).to_pandas(use_threads=False).rename(columns={col:'y','dose':'dose0'});extra=extra.replace([np.inf,-np.inf],np.nan).dropna(subset=['y','dose0']);extra['first_time']=extra.date.map(pos)-extra.event_id.map(ev.start.map(pos));extra['resume_time']=extra.date.map(pos)-extra.event_id.map(ev.resume.map(pos));f=pd.concat([f,extra],ignore_index=True);assert not f.duplicated(['code','date']).any();f['code']=pd.Categorical(f.code)
  d=f[['code','date','event_id','closed','dose0','y']].copy()
  if scheme=='first':
   # Full original window; first-close index; -1 is the original normal-day reference.
   f['cell']='t'+f.first_time.astype(int).astype(str);f.loc[f.role.eq('control_pre')&f.relative.eq(-1),'cell']='reference_pre_minus1';labels=sorted(set(f.cell)-{'reference_pre_minus1'},key=lambda s:int(s[1:]))
  else:
   f['cell']=np.where(f.role.eq('control_pre'),'pre'+f.relative.astype(int).astype(str),np.where(f.closed,'closed'+f.resume_time.astype(int).astype(str),'resume'+f.resume_time.astype(int).astype(str)));f.loc[f.role.eq('control_pre')&f.relative.eq(-1),'cell']='reference_pre_minus1';labels=[f'pre{k}'for k in range(-5,-1)]+[f'closed{k}'for k in sorted(f.loc[f.closed,'resume_time'].unique())]+[f'resume{k}'for k in range(6)]
  xs=[];present=[]
  for k,label in enumerate(labels):
   mask=f.cell.eq(label)
   if not mask.any():continue
   term=f'cell_{k}';d[term]=mask.astype(float)*d.dose0;xs.append(term);present.append((label,term,mask))
  xs+=['dose0'];model=fit(d,xs)
  for label,term,mask in present:
   r=infer(d,model,term,W);release();support=f.loc[mask];rows.append(dict(metric=metric,variant=variant,scheme=scheme,cell=label,**r,cell_n=len(support),cell_stocks=support.code.nunique(),cell_events=support.event_id.nunique(),cell_dates=support.date.nunique(),reference='normal day -1 before first closure',ri_method='NOT_APPLICABLE_MULTIPLE_EVENT_TIME_LABELS'))
  for label in set(labels)-set(x[0]for x in present):rows.append(dict(metric=metric,variant=variant,scheme=scheme,cell=label,n=len(d),stocks=d.code.nunique(),events=d.event_id.nunique(),dates=d.date.nunique(),cell_n=0,cell_stocks=0,cell_events=0,cell_dates=0,status='NO_ORIGINAL_WINDOW_SUPPORT',ri_B=0))
  # Reference cell has normalized zero, no estimated confidence interval.
  ref=f.cell.eq('reference_pre_minus1');rows.append(dict(metric=metric,variant=variant,scheme=scheme,cell='reference_pre_minus1',beta=0,beta_x100=0,n=len(d),stocks=d.code.nunique(),events=d.event_id.nunique(),dates=d.date.nunique(),cell_n=int(ref.sum()),cell_stocks=f.loc[ref,'code'].nunique(),cell_events=f.loc[ref,'event_id'].nunique(),cell_dates=f.loc[ref,'date'].nunique(),status='NORMALIZED_REFERENCE_NOT_ESTIMATED'))
  del d,model;release()
 save(pd.DataFrame(rows),dest.name);js(marker,dict(prereg=hashlib.sha256((R/'PREREGISTRATION_R5.md').read_bytes()).hexdigest(),output_sha=hashlib.sha256(dest.read_bytes()).hexdigest()));print('DYNAMIC',metric,variant,len(rows),flush=True);return str(dest)

def main():
 ctx=mp.get_context('spawn');lim=ctx.Semaphore(1);jobs=[(m,v)for m in PRIMARY for v in ['raw','w01','w005']]
 for job in jobs:
  with cf.ProcessPoolExecutor(max_workers=4,mp_context=ctx,initializer=init,initargs=(lim,))as pool:list(pool.map(worker,[job]))
 save(pd.concat([pd.read_csv(R/'tables'/f'H_dynamic_{m}_{v}.csv')for m,v in jobs],ignore_index=True),'H_dynamic_all.csv')
if __name__=='__main__':main()
