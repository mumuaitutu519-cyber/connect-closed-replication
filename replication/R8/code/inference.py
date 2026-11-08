from common import *
from scipy import sparse
from scipy.stats import t as student_t,norm
import tempfile,shutil,importlib.util
sp=importlib.util.spec_from_file_location('r7_legacy',P/'code/estimate.py');legacy=importlib.util.module_from_spec(sp);sp.loader.exec_module(legacy)
WEBB=np.array([-np.sqrt(1.5),-1.,-np.sqrt(.5),np.sqrt(.5),1.,np.sqrt(1.5)])

def counted_demean(a,e,t,maxiter=200):
 # The family-combined panel can repeat a stock-date cell. Its FE incidence
 # matrix must contain cell counts, rather than a binary presence indicator.
 a=np.asarray(a,float).copy();ns=np.bincount(e);nt=np.bincount(t);h=hashlib.sha256(memoryview(np.ascontiguousarray(e)).cast('B'));h.update(memoryview(np.ascontiguousarray(t)).cast('B'));key='counted:'+h.hexdigest()
 if key not in legacy.FE_CACHE:
  A=np.zeros((len(ns),len(nt)));np.add.at(A,(e,t),1.);G=np.diag(nt.astype(float))-A.T@(A/ns[:,None]);legacy.FE_CACHE[key]=np.linalg.pinv(G,hermitian=True,rcond=1e-11)
 Gi=legacy.FE_CACHE[key]
 for j in range(a.shape[1]):
  mean=np.bincount(e,weights=a[:,j],minlength=len(ns))/ns;a[:,j]-=mean[e];rhs=np.bincount(t,weights=a[:,j],minlength=len(nt));coef=Gi@rhs;average=np.bincount(e,weights=coef[t],minlength=len(ns))/ns;a[:,j]-=coef[t]-average[e]
 return a,1

legacy.demean=counted_demean


def fit(q,xs,entity='code',timecol='date'):
 n=len(q);e,ee=pd.factorize(q[entity],sort=True);t,tt=pd.factorize(q[timecol],sort=True);stock,ss=pd.factorize(q.code,sort=True);date,dd=pd.factorize(q.date,sort=True);ns=len(ss);nt=len(dd);folder=Path(tempfile.mkdtemp(prefix='fwl_',dir=T));shape=(len(xs)+1,n);a=np.empty(shape,dtype='float64')if shape[0]*shape[1]*8<=800_000_000 else np.memmap(folder/'within.bin',mode='w+',dtype='float64',shape=shape);cross=np.zeros((len(xs)+1,len(xs)+1))
 for j,c in enumerate(['y',*xs]):a[j]=legacy.demean(q[c].to_numpy(float).reshape(-1,1),e,t)[0][:,0]
 for start in range(0,n,32768):z=np.array(a[:,start:start+32768]);cross+=z@z.T
 norms=np.sqrt(np.maximum(np.diag(cross)[1:],0));active=np.flatnonzero(norms>1e-7);indices=active+1;names=list(np.array(xs)[active]);xx=cross[np.ix_(indices,indices)];xy=cross[indices,0];bread=np.linalg.pinv(xx);b=bread@xy;u=np.array(a[0]);k=len(names)
 for start in range(0,n,32768):z=np.array(a[indices,start:start+32768]);u[start:start+z.shape[1]]-=b@z
 S=np.zeros((ns,k));D=np.zeros((nt,k));cell=np.zeros((k,k));cellids=None
 if q.duplicated(['code','date']).any():cellids,_=pd.factorize(stock.astype(np.int64)*nt+date,sort=True)
 for j,p in enumerate(indices):
  z=np.asarray(a[p])*u;S[:,j]=np.bincount(stock,weights=z,minlength=ns);D[:,j]=np.bincount(date,weights=z,minlength=nt)
 nc=n if cellids is None else int(cellids.max())+1
 if cellids is not None:
  C=np.column_stack([np.bincount(cellids,weights=np.asarray(a[p])*u,minlength=nc)for p in indices]);cell=C.T@C;del C
 else:
  for start in range(0,n,32768):z=np.array(a[indices,start:start+32768]).T*u[start:start+32768,None];cell+=z.T@z
 corr=(n-1)/max(n-len(ee)-len(tt)-k+1,1);V=bread@(S.T@S*ns/max(ns-1,1)+D.T@D*nt/max(nt-1,1)-cell*nc/max(nc-1,1))@bread*corr
 return dict(a=a,indices=indices,names=names,b=b,V=V,xx=xx,xy=xy,bread=bread,u=u,e=e,t=t,ee=ee,tt=tt,stock=stock,date=date,ss=ss,dd=dd,n=n,df=min(ns,nt)-1,folder=folder,cellids=cellids,nc=nc,corr=corr)

def close(m):
 del m['a'];shutil.rmtree(m['folder']);legacy.FE_CACHE.clear();release()

def weights(q):
 event_column='wild_event_id'if'wild_event_id'in q else'event_id';observed=np.sort(q[event_column].unique());ids=np.arange(1,47)if observed.min()>=1 and observed.max()<=46 else observed
 if observed.min()>=1000 and observed.max()<2000:
  ev=pd.read_csv(R/'tables/design_events.csv');ids=np.sort(ev.loc[ev.family.eq('US'),'event_id'].unique())
 if observed.min()>=1000 and observed.max()<2000:
  dates=dict(zip(ev.event_id,pd.to_datetime(ev.start)));W0=np.column_stack([np.random.default_rng(np.random.SeedSequence([SEED,int(np.datetime64(dates[e],'D').astype('int64'))])).choice(WEBB,size=B)for e in ids])
 else:W0=np.random.default_rng(SEED).choice(WEBB,(B,len(ids)))
 selected=pd.Index(ids).get_indexer(observed);W=W0[:,selected];g=pd.Index(observed).get_indexer(q[event_column]);return W,g

def summarize(q,m,term,plan=None,dosecol='dose'):
 if term not in m['names']:return dict(term=term,status='NO_IDENTIFYING_VARIATION',n=len(q),stocks=q.code.nunique(),dates=q.date.nunique(),events=q.event_id.nunique())
 j=m['names'].index(term);other=np.delete(np.arange(len(m['names'])),j);xp=np.array(m['a'][m['indices'][j]]);yp=np.array(m['a'][0]);inv=np.linalg.pinv(m['xx'][np.ix_(other,other)])if len(other)else np.empty((0,0));cx=inv@m['xx'][other,j];cy=inv@m['xy'][other]
 for start in range(0,len(q),32768):
  z=np.array(m['a'][m['indices'][other],start:start+32768]);xp[start:start+z.shape[1]]-=cx@z;yp[start:start+z.shape[1]]-=cy@z
 den=xp@xp;b=m['b'][j];se=np.sqrt(m['V'][j,j])if m['V'][j,j]>=0 else np.nan;crit=student_t.ppf(.975,m['df']);W,g=weights(q);scores=np.bincount(g,weights=xp*yp,minlength=W.shape[1]);boot=W@scores/den
 row=dict(term=term,beta=b,se=se,t=b/se if se>0 else np.nan,p=2*student_t.sf(abs(b/se),m['df'])if se>0 else np.nan,ci_low=b-crit*se,ci_high=b+crit*se,n=len(q),stocks=len(m['ss']),dates=len(m['dd']),events=q.event_id.nunique(),treated_events=q.loc[q.closed.eq(1),'event_id'].nunique(),control_only_events=q.event_id.nunique()-q.loc[q.closed.eq(1),'event_id'].nunique(),df=m['df'],wild_p=(1+np.sum(abs(boot)>=abs(b)))/(B+1),wild_B=B,wild_unique_draws=len(np.unique(W,axis=0)),wild_clusters=W.shape[1],wild_statistic='Webb6 restricted absolute coefficient',wild_scores_json=json.dumps(scores.tolist()),wild_denominator=den,ri_p=np.nan,ri_B=0,ri_status='NOT_A_CALENDAR_CLOSED_DOSE_TARGET'if plan is None else'PENDING',status='OK'if np.isfinite(se)else'NONPOSITIVE_TWO_WAY_VARIANCE',fwl_error=abs(xp@yp/den-b),design_columns=len(m['names']),design_rank=int(np.linalg.matrix_rank(m['xx'])),mde80=(crit+norm.ppf(.8))*se)
 if plan is not None:
  dates,Z,meta=plan;row.update(ri_B=0,ri_unique_calendars=meta['unique_calendars'],ri_status=meta['status'])
  if len(Z):
   e=m['e'];t=m['t'];nn=np.bincount(e).astype(float);nt=np.bincount(t).astype(float);A=sparse.csr_matrix((np.ones(len(q)),(e,t)),shape=(len(nn),len(nt)));dd=q[dosecol].to_numpy(float);D=sparse.csr_matrix((dd,(e,t)),shape=A.shape);G=np.diag(nt)-(A.T@A.multiply(1/nn[:,None])).toarray();Gi=np.linalg.pinv(G,hermitian=True,rcond=1e-11);C=np.diag(np.bincount(t,weights=dd,minlength=len(nt)))-(D.T@A.multiply(1/nn[:,None])).toarray();K=np.diag(np.bincount(t,weights=dd*dd,minlength=len(nt)))-(D.T@D.multiply(1/nn[:,None])).toarray()-C@Gi@C.T
   if len(other):H=np.column_stack([np.bincount(t,weights=dd*np.asarray(m['a'][m['indices'][i]]),minlength=len(nt))for i in other]);K-=H@inv@H.T
   bb=np.bincount(t,weights=dd*yp,minlength=len(nt));ix=pd.Index(dates).get_indexer(pd.DatetimeIndex(m['tt']));assert(ix>=0).all();perms=[]
   for start in range(0,len(Z),512):z=Z[start:start+512,ix].astype(float);de=np.einsum('ij,ij->i',z@K,z);perms.append(np.divide(z@bb,de,out=np.full(len(z),np.nan),where=de>1e-10))
   p=np.concatenate(perms);p=p[np.isfinite(p)];row.update(ri_p=(1+np.sum(abs(p)>=abs(b)))/(len(p)+1)if len(p)else np.nan,ri_B=len(p),ri_status='OK_CONDITIONAL_FIXED_NUISANCE'if len(p)else'NO_VALID_DENOMINATOR');actual=q.groupby('date',observed=True).closed.first().reindex(m['tt']).to_numpy(float);obs=actual@bb/(actual@K@actual);row['ri_fwl_error']=abs(obs-b)
 for c in ['beta','se','ci_low','ci_high','mde80']:row[c+'_x100']=row[c]*100
 return row

def run(q,xs,term='closed_x',plan=None,dosecol='dose',entity='code',timecol='date'):
 cols=list(dict.fromkeys(['code','date','event_id','closed',dosecol,'y',*xs,entity,timecol]+(['wild_event_id']if'wild_event_id'in q else[])));q=q[[c for c in cols if c in q]];good=np.ones(len(q),bool)
 for c in ['y',*xs]:good&=np.isfinite(q[c].to_numpy(float))
 if not good.all():q=q.loc[good].reset_index(drop=True)
 else:q=q.reset_index(drop=True)
 if len(q)<10:return dict(term=term,status='INSUFFICIENT_COMPLETE_CASES',n=len(q),stocks=q.code.nunique(),dates=q.date.nunique(),events=q.event_id.nunique())
 release();m=fit(q,xs,entity,timecol)
 try:return summarize(q,m,term,plan,dosecol)
 finally:close(m)

def global_feasible(choices):
 if not choices or any(not c for c in choices):return False,[]
 parent=list(range(len(choices)))
 def root(i):
  while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
  return i
 owner={}
 for i,blocks in enumerate(choices):
  for d in {d for block in blocks for d in block}:
   if d in owner:parent[root(i)]=root(owner[d])
   else:owner[d]=i
 comps={}
 for i in range(len(choices)):comps.setdefault(root(i),[]).append(i)
 for component in comps.values():
  order=sorted(component,key=lambda i:len(choices[i]))
  def search(j,used):
   if j==len(order):return True
   for block in choices[order[j]]:
    if not any(d in used for d in block) and search(j+1,used|set(block)):return True
   return False
  if not search(0,set()):return False,component
 return True,[]

def plan(family):
 dest=T/f'plan_{family}.npz';metapath=R/'meta'/f'ri_{family}.json'
 if dest.exists():
  with np.load(dest)as z:return pd.to_datetime(z['dates'],unit='D'),z['calendar'],json.loads(metapath.read_text())
 if family=='main':
  root=T/'planroot';(root/'tables').mkdir(parents=True,exist_ok=True);(root/'meta').mkdir(exist_ok=True);(root/'data').mkdir(exist_ok=True)
  for f in ['events.csv','event_date_map.csv','official_calendar.csv']:shutil.copyfile(P/'tables'/f,root/'tables'/f)
  legacy.ROOT=root;legacy.SEED=SEED;legacy.B=B;legacy.resampling_plan()
  with np.load(root/'data/resampling_plan.npz')as z:dates=z['dates'].copy();Z=z['calendar'].copy()
  meta=json.loads((root/'meta/resampling_status.json').read_text());meta['status']='OK'if len(Z)else'NO_NONOVERLAPPING_BLOCK_SUPPORT';meta['unique_calendars']=len(np.unique(Z,axis=0))if len(Z)else 0;shutil.copyfile(root/'tables/randomization_support.csv',R/'tables/ri_support_main.csv')
 else:
  mapping=pd.read_csv(R/'tables/design_map.csv',parse_dates=['date']);mapping=mapping[mapping.family.eq(family)];ev=pd.read_csv(R/'tables/design_events.csv',parse_dates=['start']);ev=ev[ev.family.eq(family)];cal=pd.read_csv(P/'tables/official_calendar.csv',parse_dates=['date']);normal=set(cal.loc[cal.a_open&cal.nb_open,'date']);normal-=set(mapping.loc[mapping.closed,'date'])
  if family=='US':normal&=set(pd.read_csv(P/'R3b/tables/normal_control_dates.csv',parse_dates=['date']).date)
  weather=pd.read_csv(P/'R6/typhoon_calendar.csv',parse_dates=['date']);normal-=set(weather.loc[weather.included,'date']);allad=pd.DatetimeIndex(cal.loc[cal.a_open,'date']);positions={v:i for i,v in enumerate(allad)};dt=pd.DatetimeIndex(sorted(mapping.date.unique()));ix={v:i for i,v in enumerate(dt)};choices=[];audit=[]
  for r in ev.itertuples():
   opts=[]
   for d in dt:
    if d not in normal or d.year!=r.start.year or d.month!=r.start.month or d.dayofweek!=r.start.dayofweek:continue
    block=allad[positions[d]:positions[d]+int(r.n_closed_days)]
    if len(block)==r.n_closed_days and all(v in normal and v in ix for v in block):opts.append([ix[v]for v in block])
   choices.append(opts);audit.append(dict(event_id=r.event_id,candidate_blocks=len(opts),n=len(mapping),stocks=np.nan,events=len(ev)))
  save(audit,f'ri_support_{family}.csv');Z=[];rng=np.random.default_rng(SEED);attempt=0
  feasible,blocking=global_feasible(choices)
  if feasible:
   while len(Z)<B and attempt<B*100:
    attempt+=1;z=np.zeros(len(dt),np.uint8);ok=True
    for j in rng.permutation(len(choices)):
     opts=[v for v in choices[j]if not z[v].any()]
     if not opts:ok=False;break
     z[opts[rng.integers(len(opts))]]=1
    if ok:Z.append(z)
  Z=np.array(Z,np.uint8)if len(Z)else np.zeros((0,len(dt)),np.uint8);dates=dt.to_numpy('datetime64[D]').astype('int64');meta=dict(status='OK'if len(Z)==B else'NO_NONOVERLAPPING_BLOCK_SUPPORT',unique_calendars=len(np.unique(Z,axis=0))if len(Z)else 0,B=len(Z),global_feasible=feasible,blocking_event_positions=blocking)
 np.savez_compressed(dest,dates=dates,calendar=Z);js(metapath,meta);return pd.to_datetime(dates,unit='D'),Z,meta

def bh(p):
 a=np.array(p,float);q=np.full(len(a),np.nan);ix=np.flatnonzero(np.isfinite(a));ix=ix[np.argsort(a[ix])]
 if len(ix):q[ix]=np.minimum(1,np.minimum.accumulate((a[ix]*len(ix)/np.arange(1,len(ix)+1))[::-1])[::-1])
 return q

def episode_plan(q):
 mapping=q[['event_id','date','closed']].drop_duplicates();dates=pd.DatetimeIndex(sorted(mapping.date.unique()));actual=set(mapping.loc[mapping.closed,'date']);cal=pd.DatetimeIndex(pd.read_csv(P/'meta/actual_full_calendar.csv',parse_dates=['date']).date);pos={d:i for i,d in enumerate(cal)};ix={d:i for i,d in enumerate(dates)};choices=[];audit=[]
 for eid,g in mapping[mapping.closed].groupby('event_id'):
  treated=sorted(g.date.unique());start=treated[0];length=len(treated);opts=[]
  for d in dates:
   if d.year!=start.year or d.month!=start.month or d.dayofweek!=start.dayofweek:continue
   block=cal[pos[d]:pos[d]+length]
   if len(block)==length and all(v in ix and v not in actual for v in block):opts.append([ix[v]for v in block])
  choices.append(opts);audit.append(dict(event_id=eid,start=start,length=length,candidate_blocks=len(opts),n=len(q),stocks=q.code.nunique(),events=q.event_id.nunique()))
 feasible,blocking=global_feasible(choices);rng=np.random.default_rng(SEED);Z=[];attempts=0
 if feasible:
  while len(Z)<B and attempts<B*100:
   attempts+=1;z=np.zeros(len(dates),np.uint8);ok=True
   for j in rng.permutation(len(choices)):
    opts=[v for v in choices[j]if not z[v].any()]
    if not opts:ok=False;break
    z[opts[rng.integers(len(opts))]]=1
   if ok:Z.append(z)
 Z=np.array(Z,np.uint8)if len(Z)else np.zeros((0,len(dates)),np.uint8);meta=dict(status='OK'if len(Z)==B else'NO_MATCHED_NORMAL_DAY_SUPPORT',unique_calendars=len(np.unique(Z,axis=0))if len(Z)else 0,B=len(Z),global_feasible=feasible,blocking=blocking);save(audit,'holiday_placebo_RI_support.csv');return dates,Z,meta
