from common import *
from scipy import sparse
from scipy.stats import t as tdist,norm,binomtest
from scipy.optimize import brentq
CACHE={}
def bh(p):
 p=np.array(p,float);q=np.full(len(p),np.nan);i=np.flatnonzero(np.isfinite(p));i=i[np.argsort(p[i])];q[i]=np.minimum(1,np.minimum.accumulate((p[i]*len(i)/np.arange(1,len(i)+1))[::-1])[::-1]);return q

def geometry(e,t):
 h=hashlib.sha256(memoryview(np.ascontiguousarray(e)).cast('B'));h.update(memoryview(np.ascontiguousarray(t)).cast('B'));key=('geometry',h.hexdigest())
 if key not in CACHE:
  ns=np.bincount(e).astype(float);nt=np.bincount(t).astype(float);A=np.zeros((len(ns),len(nt)));np.add.at(A,(e,t),1.);G=np.diag(nt)-A.T@(A/ns[:,None]);Gi=np.linalg.pinv(G,hermitian=True,rcond=1e-11);CACHE[key]=(ns,nt,A,Gi)
 return CACHE[key]

def demean(a,e,t,geo):
 ns,nt,A,Gi=geo;a=np.asarray(a,float).copy()
 for j in range(a.shape[1]):
  a[:,j]-=(np.bincount(e,weights=a[:,j])/ns)[e];coef=Gi@np.bincount(t,weights=a[:,j],minlength=len(nt));av=(A@coef)/ns;a[:,j]-=coef[t]-av[e]
 return a

def fit(q,xnames):
 e,entities=pd.factorize(q.code,sort=True);t,dates=pd.factorize(q.date,sort=True);geo=geometry(e,t);a=demean(q[['y',*xnames]].to_numpy(float),e,t,geo);Y=a[:,0];X=a[:,1:];keep=np.sqrt((X*X).sum(0))>1e-7;names=np.array(xnames)[keep];X=X[:,keep];bread=np.linalg.pinv(X.T@X);b=bread@(X.T@Y);u=Y-X@b;n,k=X.shape;S=np.zeros((len(entities),k));TT=np.zeros((len(dates),k))
 for j in range(k):
  score=X[:,j]*u;S[:,j]=np.bincount(e,weights=score,minlength=len(entities));TT[:,j]=np.bincount(t,weights=score,minlength=len(dates))
 # CGM intersection must aggregate duplicate stock×calendar-date cells in weekday stacks.
 if q.attrs.get('unique_cells',False):
  cell_n=n;cell_meat=np.zeros((k,k))
  for start in range(0,n,65536):
   score=X[start:start+65536]*u[start:start+65536,None];cell_meat+=score.T@score
 else:
  cellkey=e.astype(np.int64)*len(dates)+t;cell,inv=np.unique(cellkey,return_inverse=True);C=np.empty((len(cell),k))
  for j in range(k):C[:,j]=np.bincount(inv,weights=X[:,j]*u,minlength=len(cell))
  cell_n=len(cell);cell_meat=C.T@C
 meat=S.T@S*len(entities)/max(len(entities)-1,1)+TT.T@TT*len(dates)/max(len(dates)-1,1)-cell_meat*cell_n/max(cell_n-1,1);V=bread@meat@bread*(n-1)/max(n-len(entities)-len(dates)-k+1,1)

 return dict(e=e,t=t,dates=dates,entities=entities,geo=geo,Y=Y,X=X,names=list(names),bread=bread,b=b,u=u,V=V,n=n,df=min(len(entities),len(dates))-1,cell_n=cell_n)

def weights(eventids):
 # Repeated regional specifications share weights for the same actual anchor date.
 ev=pd.read_csv(R/'tables/events.csv',parse_dates=['start']);anchors=dict(zip(ev.event_id,ev.start))
 cl=pd.read_csv(R/'tables/closure_date_map.csv',parse_dates=['anchor']);anchors.update(dict(zip(cl.event_id,cl.anchor)))
 keys=[int(np.datetime64(anchors[int(e)],'D').astype('int64')) for e in eventids]
 return np.column_stack([np.random.default_rng(np.random.SeedSequence([SEED,k])).choice([-np.sqrt(1.5),-1,-np.sqrt(.5),np.sqrt(.5),1,np.sqrt(1.5)],size=B) for k in keys])

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

def calendar_plan(mapping,target):
 # Shared exact calendar cache; four equations use the same calendar draws.
 pack=mapping[['event_id','date',target]].copy();pack['date']=pack.date.to_numpy('datetime64[D]').astype('int64');pack=pack.sort_values(['event_id','date']);digest=hashlib.sha256(pack.to_numpy(np.int64).tobytes());digest.update((R/'tables/normal_control_dates.csv').read_bytes());digest.update((R/'tables/official_calendar.csv').read_bytes());digest.update(f'{SEED}:{B}:{target}'.encode());folder=T/'ri_calendars';folder.mkdir(exist_ok=True);base=folder/digest.hexdigest()
 if base.with_suffix('.npz').exists() and base.with_suffix('.json').exists() and base.with_suffix('.csv').exists():
  with np.load(base.with_suffix('.npz')) as zz:dates=pd.to_datetime(zz['dates'],unit='D');z=zz['calendar']
  return dates,z,pd.read_csv(base.with_suffix('.csv')),json.loads(base.with_suffix('.json').read_text())
 normal=set(pd.read_csv(R/'tables/normal_control_dates.csv',parse_dates=['date']).date);allA=pd.DatetimeIndex(pd.read_csv(R/'tables/official_calendar.csv',parse_dates=['date']).query('a_open').date);pos={d:i for i,d in enumerate(allA)};dates=pd.DatetimeIndex(sorted(mapping.date.unique()));ix={d:i for i,d in enumerate(dates)};choices=[];audit=[]
 for eid,g in mapping[mapping[target].eq(1)].groupby('event_id'):
  treat=sorted(g.date.unique());start=pd.Timestamp(treat[0]);length=len(treat);blocks=[]
  for d in dates:
   if d not in normal or d.year!=start.year or d.month!=start.month or d.dayofweek!=start.dayofweek:continue
   ii=pos[d];block=list(allA[ii:ii+length])
   if len(block)==length and all(x in normal and x in ix for x in block):blocks.append([ix[x] for x in block])
  choices.append(blocks);audit.append(dict(event_id=eid,start=start,length=length,candidate_blocks=len(blocks)))
 rng=np.random.default_rng(SEED);rows=[];attempts=0;feasible,blocking=global_feasible(choices)
 if feasible:
  while len(rows)<B and attempts<B*100:
   attempts+=1;row=np.zeros(len(dates),np.uint8);good=True
   for j in rng.permutation(len(choices)):
    av=[x for x in choices[j] if not row[x].any()]
    if not av:good=False;break
    z=av[rng.integers(len(av))];row[z]=1
   if good:rows.append(row)
 z=np.array(rows,np.uint8) if rows else np.zeros((0,len(dates)),np.uint8)
 status=dict(ri_requested=B,ri_repetitions=len(z),ri_unique=len(np.unique(z,axis=0)) if len(z) else 0,ri_attempts=attempts,ri_global_feasible=feasible,ri_blocking_events=';'.join(str(audit[i]['event_id']) for i in blocking),ri_status='OK' if len(z) else 'NO_SUPPORT_NO_RELAXATION')
 temp=base.with_name(base.name+f'_{os.getpid()}');np.savez_compressed(temp.with_suffix('.npz'),dates=dates.to_numpy('datetime64[D]').astype('int64'),calendar=z);temp.with_suffix('.npz').replace(base.with_suffix('.npz'));pd.DataFrame(audit).to_csv(temp.with_suffix('.csv'),index=False);temp.with_suffix('.csv').replace(base.with_suffix('.csv'));temp.with_suffix('.json').write_text(json.dumps(status));temp.with_suffix('.json').replace(base.with_suffix('.json'))
 return dates,z,pd.DataFrame(audit),status

def infer(q,model,term,W,plan):
 names=model['names'];j=names.index(term);X=model['X'];Y=model['Y'];others=[i for i in range(X.shape[1]) if i!=j];N=X[:,others];Ni=np.linalg.pinv(N.T@N) if len(others) else np.zeros((0,0));xp=X[:,j].copy();yp=Y.copy()
 if len(others):xp-=N@(Ni@(N.T@xp));yp-=N@(Ni@(N.T@yp))
 den=xp@xp;g=pd.Categorical(q.event_id,categories=W[0]).codes;scores=np.bincount(g,weights=xp*yp,minlength=len(W[0]));boot=W[1]@scores/den;b=model['b'][j];v=model['V'][j,j];se=np.sqrt(v) if v>=0 else np.nan;df=model['df'];crit=tdist.ppf(.975,df);row=dict(term=term,beta=b,se=se,t=b/se if se>0 else np.nan,p=2*tdist.sf(abs(b/se),df) if se>0 else np.nan,ci_low=b-crit*se,ci_high=b+crit*se,df=df,n=len(q),stocks=len(model['entities']),dates=len(model['dates']),stock_date_cells=model['cell_n'],wild_p=(1+np.sum(np.abs(boot)>=abs(b)))/(B+1),wild_B=B,wild_clusters=len(np.unique(g)),mde80=(crit+norm.ppf(.8))*se,status='OK' if np.isfinite(se) else 'NONPOSITIVE_TWO_WAY_VARIANCE',ri_p=np.nan,ri_B=0)
 if plan is not None:
  pdates,Z,status=plan;row.update(status)
  if len(Z):
   e=model['e'];t=model['t'];ns,nt,A,Gi=model['geo'];dose=q.dose0.to_numpy(float)
   h=hashlib.sha256(memoryview(np.ascontiguousarray(e)).cast('B'));h.update(memoryview(np.ascontiguousarray(t)).cast('B'));h.update(memoryview(np.ascontiguousarray(dose)).cast('B'))
   for k in others:h.update(memoryview(np.ascontiguousarray(X[:,k])).cast('B'))
   h.update(pd.DatetimeIndex(model['dates']).to_numpy('datetime64[D]').astype('int64').tobytes())
   key=('RI_design',term,h.hexdigest())
   if key not in CACHE:
    D=np.zeros_like(A);np.add.at(D,(e,t),dose);C=np.diag(np.bincount(t,weights=dose,minlength=len(nt)))-D.T@(A/ns[:,None]);K=np.diag(np.bincount(t,weights=dose*dose,minlength=len(nt)))-D.T@(D/ns[:,None])-C@Gi@C.T
    if len(others):
     H=np.column_stack([np.bincount(t,weights=dose*N[:,k],minlength=len(nt)) for k in range(N.shape[1])]);K-=H@Ni@H.T
    ix=pd.Index(pdates).get_indexer(model['dates']);assert (ix>=0).all();z=Z[:,ix].astype(float);dd=np.einsum('ij,ij->i',z@K,z);CACHE[key]=(K,dd,ix);del D,C,z
   K,dd,ix=CACHE[key];bb=np.bincount(t,weights=dose*yp,minlength=len(nt));z=Z[:,ix].astype(float);perm=np.divide(z@bb,dd,out=np.full(len(z),np.nan),where=dd>1e-10);perm=perm[np.isfinite(perm)];row.update(ri_p=(1+np.sum(np.abs(perm)>=abs(b)))/(len(perm)+1) if len(perm) else np.nan,ri_B=len(perm))
   if not len(perm):row['ri_status']='NO_ESTIMABLE_ASSIGNMENTS'
   actual=q.groupby('date',observed=True)[term.split('_')[0]].first().reindex(model['dates']).to_numpy(float);check=(actual@bb)/(actual@K@actual);row['ri_beta_abs_error']=abs(check-b);assert abs(check-b)<1e-7
   del z

 return row,boot

def rw(rows,boots):
 obs=np.array([abs(r['beta']/r['se']) if r.get('se',0)>0 else np.nan for r in rows]);bb=np.column_stack([np.abs(b)/r['se'] if r.get('se',0)>0 else np.full(B,np.nan) for r,b in zip(rows,boots)]);out=np.full(len(rows),np.nan);order=np.flatnonzero(np.isfinite(obs));order=order[np.argsort(-obs[order])];prev=0
 for i,k in enumerate(order):
  p=(1+np.sum(np.nanmax(bb[:,order[i:]],axis=1)>=obs[k]))/(B+1);prev=max(prev,p);out[k]=prev
 return out

def event_stats(d,metric,variant,metadata):
 col=metric if variant=='raw' else f'{metric}__{variant}';z=d[d.quintile.isin([0,4])&d.dose.notna()].groupby(['event_id','date','treated','quintile'],observed=True)[col].mean().unstack('quintile')
 if not {0,4}.issubset(z.columns):return [],[]
 z['gap']=z[4]-z[0];z=z.reset_index();dayrows=[];seg=[]
 for eid,g in z.groupby('event_id'):
  control=g.loc[g.treated.eq(0),'gap'].mean();v=g.loc[g.treated.eq(1)].copy()
  for r in v.itertuples():dayrows.append(dict(**metadata,metric=metric,variant=variant,event_id=eid,date=r.date,gap_treated=r.gap,gap_control=control,did=r.gap-control))
  if len(v):seg.append(dict(**metadata,metric=metric,variant=variant,event_id=eid,did=v.gap.mean()-control))
 out=[]
 for unit,rr in [('day',dayrows),('segment',seg)]:
  a=pd.DataFrame(rr).did.dropna().to_numpy() if rr else np.array([]);n=len(a);sd=a.std(ddof=1) if n>1 else np.nan;se=sd/np.sqrt(n) if n else np.nan;stat=a.mean()/se if se>0 else np.nan;nz=a[a!=0];out.append(dict(**metadata,metric=metric,variant=variant,unit=unit,n=n,mean=a.mean() if n else np.nan,se=se,t=stat,p_t=2*tdist.sf(abs(stat),n-1) if n>1 else np.nan,p_sign=binomtest(int((nz>0).sum()),len(nz),.5).pvalue if len(nz) else np.nan,n_positive=int((a>0).sum()),mde80=(tdist.ppf(.975,n-1)+norm.ppf(.8))*se if n>1 else np.nan))
 return out,dayrows+[{**r,'date':None,'unit':'segment'} for r in seg]
