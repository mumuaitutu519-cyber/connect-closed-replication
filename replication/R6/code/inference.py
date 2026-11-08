from common import *
from scipy.stats import t as student_t,norm
from scipy.linalg import null_space
sys.path.insert(0,str(R/'code/r1'))
import estimate as legacy
B=9999;WEBB=np.array([-np.sqrt(1.5),-1.,-np.sqrt(.5),np.sqrt(.5),1.,np.sqrt(1.5)])
EVENTS=pd.read_csv(R/'tables/events.csv',parse_dates=['start','end']);EVENT_INDEX={int(v):i for i,v in enumerate(EVENTS.event_id)}
W=np.random.default_rng(SEED).choice(WEBB,(B,len(EVENTS)))

def aggregate(v,g,n=None):
 v=np.asarray(v);n=n or int(g.max())+1
 if v.ndim==1:return np.bincount(g,weights=v,minlength=n)
 return np.column_stack([np.bincount(g,weights=v[:,j],minlength=n) for j in range(v.shape[1])])

def fit(d,y,xs,entity='code',time='date'):
 keep=list(dict.fromkeys(['code','date','event_id','kind','anticipation','dose','closed','resume','relative','closed_dose','restore_dose','closed_segment','restored_segment','pattern_closed','pattern_restore',entity,time,y,*xs]));d=d[[c for c in keep if c in d]].dropna(subset=[y,*xs,entity,time]).copy();v=d[[y,*xs]].to_numpy(float);good=np.isfinite(v).all(1);d=d.loc[good].reset_index(drop=True);v=v[good];n=len(d)
 if not n:return None,'NO_COMPLETE_CASES'
 e,ee=pd.factorize(d[entity],sort=True);t,tt=pd.factorize(d[time],sort=True);a,_=legacy.demean(v,e,t);Y=a[:,0];X=a[:,1:];active=np.sqrt(np.sum(X*X,axis=0))>1e-7;names=np.asarray(xs)[active];X=X[:,active]
 if not len(names):return None,'NO_IDENTIFYING_VARIATION'
 if np.linalg.matrix_rank(X.T@X)<X.shape[1]:return None,'RANK_DEFICIENT'
 bread=np.linalg.pinv(X.T@X);b=bread@(X.T@Y);u=Y-X@b;stock,ss=pd.factorize(d.code,sort=True);date,dd=pd.factorize(d.date,sort=True);assert (stock>=0).all() and (date>=0).all();ng,nt=len(ss),len(dd);cell_key=stock.astype(np.int64)*nt+date;nc=len(np.unique(cell_key));scores=X*u[:,None];S=aggregate(scores,stock);D=aggregate(scores,date);k=len(names)
 if nc==n:cell_meat=scores.T@scores
 else:
  cell,_=pd.factorize(cell_key,sort=True);C=aggregate(scores,cell);cell_meat=C.T@C
 meat=S.T@S*ng/max(ng-1,1)+D.T@D*nt/max(nt-1,1)-cell_meat*nc/max(nc-1,1);correction=(n-1)/max(n-len(ee)-len(tt)-k+1,1);V=bread@meat@bread*correction;df=min(ng,nt)-1
 groups=d.event_id.map(EVENT_INDEX).to_numpy(int);return dict(d=d,Y=Y,X=X,b=b,V=V,names=names,e=e,t=t,entities=ee,times=tt,stock=stock,date=date,dates=dd,groups=groups,events=d.event_id.nunique(),stocks=ng,n_dates=nt,n=n,df=df,fe_entities=len(ee),fe_times=len(tt),n_intersection_clusters=nc), 'OK'

def summarize(model,c,name):
 b=float(c@model['b']);var=float(c@model['V']@c);se=np.sqrt(var) if var>=0 else np.nan;df=model['df'];crit=student_t.ppf(.975,df);p=2*student_t.sf(abs(b/se),df) if se>0 else np.nan;events=model['events'];emcrit=student_t.ppf(.975,events-1) if events>1 else np.nan
 # Reparameterize so target theta=c'beta, nuisance spans c-null space; exact restricted FWL coefficient bootstrap.
 X=model['X'];Y=model['Y'];xp=X@c/(c@c);N=X@null_space(c[None,:]);yp=Y.copy()
 if N.shape[1]:
  xp=xp-N@(np.linalg.pinv(N)@xp);yp=yp-N@(np.linalg.pinv(N)@yp)
 den=float(xp@xp);scores=aggregate(xp*yp,model['groups'],len(EVENTS));boot=(W@scores)/den;bp=(1+np.sum(np.abs(boot)>=abs(b)))/(B+1);se_design=se
 row=dict(term=name,wild_fwl_abs_error=abs(float(xp@yp)/den-b),beta=b,beta_x100=b*100,se=se,se_x100=se*100,p=p,ci_low=b-crit*se,ci_high=b+crit*se,ci_low_x100=(b-crit*se)*100,ci_high_x100=(b+crit*se)*100,wild_p=bp,wild_B=B,wild_clusters=events,wild_method='Webb6 restricted residual absolute coefficient, nonstudentized',n=model['n'],stocks=model['stocks'],events=events,dates=model['n_dates'],stock_clusters=model['stocks'],date_clusters=model['n_dates'],intersection_clusters=model['n_intersection_clusters'],fe_entities=model['fe_entities'],fe_times=model['fe_times'],df=df,mde80=(crit+norm.ppf(.8))*se,mde80_x100=(crit+norm.ppf(.8))*se*100,mde80_event_df=(emcrit+norm.ppf(.8))*se,mde80_event_df_x100=(emcrit+norm.ppf(.8))*se*100,status='OK' if np.isfinite(se) else 'NONPOSITIVE_TWO_WAY_VARIANCE')
 return row,boot

def calendar_plan(d,family,B=9999):
 # Same-year/month/weekday, length, normal-day and main-window support as 266.
 cal=loadcal();wc=pd.read_csv(R/'typhoon_calendar.csv',parse_dates=['date']);normal=set(cal.loc[cal.a_open&cal.nb_open&~cal.date.isin(wc.loc[wc.included|wc.placebo,'date']),'date']);a=cal.loc[cal.a_open,'date'].sort_values().tolist();positions={v:i for i,v in enumerate(a)};support=sorted(d.date.unique());ix={v:i for i,v in enumerate(support)};events=EVENTS[EVENTS.event_id.isin(d.event_id.unique())];choices=[];audit=[]
 for ev in events.itertuples():
  opts=[]
  for date in support:
   if date not in normal or date.year!=ev.start.year or date.month!=ev.start.month or date.dayofweek!=ev.start.dayofweek:continue
   block=a[positions[date]:positions[date]+int(ev.n_closed_days)]
   if len(block)==ev.n_closed_days and all(t in normal and t in ix for t in block):opts.append([ix[t] for t in block])
  choices.append(opts);audit.append(dict(family=family,event_id=ev.event_id,start=ev.start,length=ev.n_closed_days,candidate_blocks=len(opts),candidate_starts=';'.join(str(support[b[0]].date()) for b in opts),n=len(d),stocks=d.code.nunique(),events=len(events),stock_clusters=d.code.nunique(),date_clusters=d.date.nunique()))
 def feasible(order,j,used):
  if j==len(order):return True
  for block in choices[order[j]]:
   b=set(block)
   if not used.intersection(b) and feasible(order,j+1,used|b):return True
  return False
 possible=all(choices)
 if possible:
  unions=[set(k for block in options for k in block) for options in choices];remaining=set(range(len(choices)));components=[]
  while remaining:
   stack=[remaining.pop()];component=[]
   while stack:
    node=stack.pop();component.append(node);linked=[q for q in remaining if unions[node].intersection(unions[q])]
    for q in linked:remaining.remove(q);stack.append(q)
   components.append(component)
  possible=all(feasible(sorted(component,key=lambda j:len(choices[j])),0,set()) for component in components)
 rng=np.random.default_rng(SEED);z=[];attempts=0
 if possible:
  while len(z)<B and attempts<B*100:
   attempts+=1;row=np.zeros(len(support),np.uint8);valid=True
   for i in rng.permutation(len(choices)):
    opts=[q for q in choices[i] if not row[q].any()]
    if not opts:valid=False;break
    row[opts[rng.integers(len(opts))]]=1
   if valid:z.append(row)
 Z=np.asarray(z,dtype=np.uint8) if z else np.zeros((0,len(support)),np.uint8);meta=dict(family=family,B=len(Z),requested_B=B,unique_calendars=len(np.unique(Z,axis=0)) if len(Z) else 0,attempts=attempts,status='OK' if len(Z)==B else 'NO_NONOVERLAPPING_BLOCK_SUPPORT',support_dates=len(support))
 return pd.DatetimeIndex(support),Z,pd.DataFrame(audit),meta

def coefficient_ri(model,target,plan,segment=False,mask=None):
 dates,Z,audit,meta=plan
 if not len(Z):return dict(ri_p=np.nan,ri_B=0,ri_unique_calendars=0,ri_status=meta['status']),np.array([])
 d=model['d'];names=list(model['names']);j=names.index(target);X=model['X'];Y=model['Y'];xp=X[:,j];others=np.delete(X,j,axis=1)
 if segment:
  # Event-segment reassignment only among normal candidate dates; block-specific time pattern retained.
  # Restricted score is exact FWL score for each permuted interaction, as declared for extra intraday FE designs.
  v=d.dose.to_numpy()*d.pattern_closed.to_numpy();nuis=others;resid=Y-nuis@(np.linalg.pinv(nuis)@Y) if nuis.shape[1] else Y;dateidx=dates.get_indexer(d.date);b=aggregate(v*resid,dateidx,len(dates));obs=float(xp@resid);stats=Z@b;pv=(1+np.sum(np.abs(stats)>=abs(obs)))/(len(stats)+1)
  return dict(ri_p=pv,ri_B=len(stats),ri_unique_calendars=meta['unique_calendars'],ri_status='OK_CONDITIONAL_RESTRICTED_SCORE',ri_method='intraday event pattern score; nuisance fixed; normal-day calendar diagnostic'),stats
 # Exact target FE quadratic form, residualizing all fixed observed nuisance interactions.
 e=model['e'];t=model['t'];S=len(model['entities']);Tn=len(model['times']);ns=np.bincount(e).astype(float);nt=np.bincount(t).astype(float);dose=d.dose.to_numpy(float)
 if mask is not None:dose=dose*np.asarray(mask,float)
 A=np.zeros((S,Tn));D=np.zeros((S,Tn));A[e,t]=1.;D[e,t]=dose;Q=np.diag(np.bincount(t,weights=dose*dose,minlength=Tn))-D.T@(D/ns[:,None]);C=np.diag(np.bincount(t,weights=dose,minlength=Tn))-D.T@(A/ns[:,None]);G=np.diag(nt)-A.T@(A/ns[:,None]);K=Q-C@np.linalg.pinv(G,hermitian=True,rcond=1e-11)@C.T;del A,D,Q,C,G
 bb=np.bincount(t,weights=dose*Y,minlength=Tn)
 if others.shape[1]:
  H=aggregate(dose[:,None]*others,t,Tn);inv=np.linalg.pinv(others.T@others);K-=H@inv@H.T;bb-=H@inv@(others.T@Y)
 zz=Z[:,dates.get_indexer(pd.DatetimeIndex(model['times']))].astype(float);den=np.einsum('ij,ij->i',zz@K,zz);perms=np.divide(zz@bb,den,out=np.full(len(Z),np.nan),where=den>1e-10);perms=perms[np.isfinite(perms)];obs=float(model['b'][j]);p=(1+np.sum(np.abs(perms)>=abs(obs)))/(len(perms)+1) if len(perms) else np.nan
 actual=d[target].to_numpy()/np.where(dose!=0,dose,1);zt=np.zeros(Tn)
 for k in range(Tn):
  v=actual[(t==k)&(dose!=0)];zt[k]=v[0] if len(v) else 0
 den0=zt@K@zt;check=(zt@bb)/den0 if den0>1e-10 else np.nan
 return dict(ri_p=p,ri_B=len(perms),ri_unique_calendars=meta['unique_calendars'],ri_status='OK' if len(perms) else 'NO_POSITIVE_PERMUTATION_DENOMINATOR',ri_method='exact FWL beta; conditional fixed nuisance; same-year/month/weekday normal blocks',ri_observed_quadratic_beta=check,ri_quadratic_abs_error=abs(obs-check)),perms

def bh(p):
 p=np.array(p,float);q=np.full(len(p),np.nan);ok=np.flatnonzero(np.isfinite(p));order=ok[np.argsort(p[ok])]
 if len(order):q[order]=np.minimum(1,np.minimum.accumulate((p[order]*len(order)/np.arange(1,len(order)+1))[::-1])[::-1])
 return q
