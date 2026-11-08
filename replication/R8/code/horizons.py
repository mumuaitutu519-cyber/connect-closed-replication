from common import *
from analyze import read,load,complete,init_limit,CC
from inference import run,plan,fit,close,legacy
from scipy.stats import t as student_t
import concurrent.futures as cf,multiprocessing as mp

def metric(m,h):
 n=m[f'mom{h}_n'];sx=m[f'mom{h}_sx'];sy=m[f'mom{h}_sy'];xx=m[f'mom{h}_sxx']-sx*sx/n;yy=m[f'mom{h}_syy']-sy*sy/n;xy=m[f'mom{h}_sxy']-sx*sy/n
 return xy/xx,xy*xy/(xx*yy)

def block(b):
 dest=T/'pooled_horizons'/f'{b:03d}.parquet'
 if dest.exists():return b
 maps=pd.read_csv(P/'tables/event_date_map.csv',parse_dates=['date','anchor']);fe=pd.read_parquet(T/'feature_blocks'/f'{b:03d}.parquet');fe=fe[fe.family.eq('main')];history=pd.concat([pd.read_parquet(p,columns=['code','date','eligible_day','nb_open',*[f'mom{h}_{c}'for h in [30,60]for c in ['n','sx','sy','sxx','syy','sxy']]])for p in sorted((T/'history').glob(f'*_{b:03d}.parquet'))],ignore_index=True);hist=history[history.eligible_day];f=hist[hist.date.isin(maps.date)].merge(maps[['event_id','date','anchor','closed']],on='date',validate='m:1');(T/'pooled_daily').mkdir(exist_ok=True);f.to_parquet(T/'pooled_daily'/f'{b:03d}.parquet',index=False);mom=[f'mom{h}_{c}'for h in [30,60]for c in ['n','sx','sy','sxx','syy','sxy']];z=f.groupby(['code','event_id','closed'],observed=True)[mom].sum(min_count=1).reset_index();counts=f.groupby(['code','event_id','closed'],observed=True).size();z['days']=counts.to_numpy();z=z.merge(fe,on=['code','event_id'],validate='m:1');rows=[]
 for eid,g in z.groupby('event_id'):
  freeze=g.freeze_date.iloc[0];prior=hist[hist.nb_open&hist.date.lt(freeze)];pm=prior.groupby('code',observed=True)[mom].sum(min_count=1)
  for h in [30,60]:
   beta,r2=metric(g,h);good=(g[f'mom{h}_n']>=np.maximum(3,.8*g.days*(240//h)))&np.isfinite(beta)&np.isfinite(r2)&r2.between(0,1);g[f'pooled_beta_{h}']=beta.where(good);g[f'pooled_r2_{h}']=r2.where(good)
   pb,pr=metric(pm,h)
   # Each stock's strictly prior normal pooled outcome is a predetermined reference;
   # event cross-sectional quantiles are pooled later across stock blocks.
   g[f'pre_beta_{h}']=g.code.map(pb);g[f'pre_r2_{h}']=g.code.map(pr)
  rows.append(g)
 out=pd.concat(rows,ignore_index=True);out.to_parquet(dest,index=False);release();return b

def fieller(num,den,vnum,vden,cov,df):
 crit=student_t.ppf(.975,df);a=den*den-crit*crit*vden;b=-2*(num*den-crit*crit*cov);c=num*num-crit*crit*vnum;dis=b*b-4*a*c;ratio=num/den if den!=0 else np.nan
 if abs(a)<1e-16:
  if abs(b)<1e-16:return ratio,'ALL_REAL'if c<=0 else'EMPTY',-np.inf,np.inf
  root=-c/b;return ratio,'LEFT_RAY'if b>0 else'RIGHT_RAY',root,root
 if dis<0:return ratio,'ALL_REAL'if a<0 else'EMPTY',-np.inf,np.inf
 roots=sorted([(-b-np.sqrt(dis))/(2*a),(-b+np.sqrt(dis))/(2*a)]);return ratio,'BOUNDED'if a>0 else'TWO_RAYS',roots[0],roots[1]

def joint_different_design(frames,designs,terms):
 mods=[];bet=[];scores=[];indices=[]
 assert all(frames[0][['code','date']].equals(x[['code','date']])for x in frames)
 try:
  for q,xs,term in zip(frames,designs,terms):
   m=fit(q,xs);mods.append(m);j=m['names'].index(term);bet.append(m['b'][j]);influence=np.zeros(len(q))
   for k,pos in enumerate(m['indices']):influence+=m['bread'][j,k]*np.asarray(m['a'][pos])
   scores.append(influence*m['u'])
  m=mods[0];U=np.column_stack(scores);ns=len(m['ss']);nt=len(m['dd']);S=np.column_stack([np.bincount(m['stock'],weights=U[:,j],minlength=ns)for j in range(U.shape[1])]);D=np.column_stack([np.bincount(m['date'],weights=U[:,j],minlength=nt)for j in range(U.shape[1])]);V=(S.T@S*ns/(ns-1)+D.T@D*nt/(nt-1)-U.T@U*len(U)/(len(U)-1));cor=np.sqrt(np.array([mm['corr']for mm in mods]));V*=cor[:,None]*cor[None,:];return np.array(bet),V,m['df']
 finally:
  for m in mods:close(m)

def cumulative(v):
 dest=R/'tables'/f'cumulative_recovery_{v}.csv'
 if dest.exists():return str(dest)
 day='day_return'if v=='raw'else'day_return__'+v;b0='if_b0'if v=='raw'else'if_b0__'+v;cols=['code','date','event_id','closed','dose',day,b0,'next_'+v];f=read(cols).rename(columns={day:'day',b0:'beta0','next_'+v:'next'});
 with np.load(T/'futures_IF.npz')as z:fr=pd.Series(z['day_return'],index=pd.to_datetime(z['dates'],unit='D'));nfr=pd.Series(np.isfinite(z['returns']).sum(1),index=fr.index)
 f['if_day']=f.date.map(fr);f.loc[f.date.map(nfr).fillna(0).lt(180),'if_day']=np.nan;f['closed_x']=f.closed*f.dose;f['if_dose']=f.if_day*f.dose;f['catchup_x']=f.closed*f.if_dose;xs=['catchup_x','closed_x','if_dose','dose'];rows=[]
 for outcome in ['day','next']:
  q=f.copy();q['y']=q[outcome];q=complete(q,xs);r=run(q,xs,term='catchup_x',plan=plan('main'),dosecol='if_dose');r.update(metric=outcome,variant=v,specification='own_sample',dependent_mean=q.y.mean(),dependent_closed_mean=q.loc[q.closed,'y'].mean(),dependent_control_mean=q.loc[~q.closed,'y'].mean());rows.append(r)
 q=f[np.isfinite(f[['day','next','beta0',*xs]].to_numpy(float)).all(1)].reset_index(drop=True);frames=[]
 for outcome in ['day','next','beta0']:a=q.copy();a['y']=a[outcome];frames.append(a)
 bet,V,df=joint_different_design(frames,[xs,xs,['closed_x','dose']],['catchup_x','catchup_x','closed_x']);rat=[]
 for denidx,label in [(2,'Next_over_missing_contemporaneous_Beta0'),(0,'Next_over_missing_Day_beta')]:
  point,kind,lo,hi=fieller(bet[1],-bet[denidx],V[1,1],V[denidx,denidx],-V[1,denidx],df);rat.append(dict(variant=v,definition=label,next_beta_x100=bet[1]*100,denominator_beta_x100=bet[denidx]*100,ratio=point,fieller_type=kind,ci_low=lo,ci_high=hi,df=df,n=len(q),stocks=q.code.nunique(),events=q.event_id.nunique(),dependent_day_mean=q.day.mean(),dependent_next_mean=q.next.mean(),cross_cov=V[1,denidx]))
 save(rows,dest.name);save(rat,f'next_ratio_{v}.csv');return str(dest)

def main():
 ctx=mp.get_context('spawn');(T/'pooled_horizons').mkdir(exist_ok=True)
 with cf.ProcessPoolExecutor(max_workers=6,mp_context=ctx)as pool:list(pool.map(block,range(int(np.ceil(len(universe())/50)))))
 f=pd.concat([pd.read_parquet(p)for p in sorted((T/'pooled_horizons').glob('*.parquet'))],ignore_index=True);ev=pd.read_csv(P/'tables/events.csv',parse_dates=['start']).set_index('event_id');f['date']=f.event_id.map(ev.start)+pd.to_timedelta(f.closed.astype(int),unit='D');f.code=pd.Categorical(f.code);rows=[];thresholds=[];dist=[]
 for h in [30,60]:
  for c in ['beta','r2']:
   col=f'pooled_{c}_{h}';pre=f'pre_{c}_{h}';base=f[['event_id','code',pre]].drop_duplicates();bounds=base.groupby('event_id')[pre].quantile([.005,.01,.99,.995]).unstack()
   for eid,b in bounds.iterrows():thresholds.append(dict(event_id=eid,metric=col,q005=b[.005],q01=b[.01],q99=b[.99],q995=b[.995],n=base[base.event_id.eq(eid)][pre].notna().sum(),stocks=base[base.event_id.eq(eid)].code.nunique(),events=1,source='strictly pre-freeze normal pooled stock outcomes cross-section'))
   for v in VARIANTS:
    q=f[['code','date','event_id','closed','dose',col]].copy();q['y']=q[col]
    if v!='raw':lo=.01 if v=='w01'else .005;hi=1-lo;q['y']=q.y.clip(q.event_id.map(bounds[lo]),q.event_id.map(bounds[hi]))
    q['closed_x']=q.closed*q.dose;q=q[np.isfinite(q.y)&np.isfinite(q.dose)].copy();pairs=q.groupby(['code','event_id'],observed=True).closed.nunique();valid=pairs.index[pairs.eq(2)];index=pd.MultiIndex.from_frame(q[['code','event_id']]);paired=q.loc[index.isin(valid)]
    for label,qq in [('stock_event_state_pooled_paired',paired),('stock_event_state_pooled_unbalanced',q)]:
     r=run(qq,['closed_x','dose'],plan=None);rows.append(dict(metric=col,variant=v,specification=label,time_FE='event x closure state',clustering='stock and event x closure-state labels; Webb event',**r))
  for state,g in f.groupby('closed'):
   z=g[f'mom{h}_n'];dist.append(dict(minutes=h,closed=state,mean=z.mean(),minimum=z.min(),median=z.median(),p05=z.quantile(.05),p95=z.quantile(.95),maximum=z.max(),mean_days=g.days.mean(),n=len(g),stocks=g.code.nunique(),events=g.event_id.nunique()))
 save(rows,'pooled_horizon_estimates.csv');save(thresholds,'pooled_horizon_winsor_thresholds.csv');save(dist,'pooled_horizon_intervals.csv');del f;release()
 for v in VARIANTS:print(cumulative(v),flush=True)
if __name__=='__main__':main()
