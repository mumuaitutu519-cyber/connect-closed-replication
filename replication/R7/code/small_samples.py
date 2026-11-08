from common import *
from inference import run,weights,WEBB,plan,episode_plan
from estimate import read
from scipy.stats import t as student_t,binomtest


def eventstats(values,meta,obs,stocks):
 v=np.array(values,float);v=v[np.isfinite(v)];n=len(v);se=np.std(v,ddof=1)/np.sqrt(n)if n>1 else np.nan;t=np.mean(v)/se if se>0 else np.nan;W=np.random.default_rng(SEED).choice(WEBB,(B,n));boot=W@v/n if n else np.array([]);nonzero=v[v!=0];return dict(**meta,beta_x100=np.mean(v)*100 if n else np.nan,se_x100=se*100,event_t=t,event_t_p=2*student_t.sf(abs(t),n-1)if n>1 else np.nan,sign_p=binomtest(int((nonzero>0).sum()),len(nonzero),.5).pvalue if len(nonzero)else np.nan,positive=int((v>0).sum()),negative=int((v<0).sum()),wild_event_mean_p=(1+np.sum(abs(boot)>=abs(np.mean(v))))/(B+1)if n else np.nan,wild_unique_draws=len(np.unique(W,axis=0))if n else 0,wild_B=B,n=obs,stocks=stocks,events=n)

def main_groups():
 rows=[];evrows=[];groups=pd.read_csv(P/'R5/tables/F_event_classification.csv').set_index('event_id')
 for metric in ['if_delay','ih_delay']:
  for v in VARIANTS:
   col=metric if v=='raw'else metric+'__'+v;f=read(['code','date','event_id','closed','dose','quintile',col]);f=f[np.isfinite(f[col])&np.isfinite(f.dose)].copy();f['hkonly']=f.event_id.map(groups.hkonly)
   for group,hk in [('HKOnly',1),('Shared',0)]:
    d=f[f.hkonly.eq(hk)].copy();d['y']=d[col];d['closed_x']=d.closed*d.dose;r=run(d,['closed_x','dose'],plan=plan('main'));rows.append(dict(group=group,metric=metric,variant=v,**r));g=d.groupby(['event_id','quintile','closed'],observed=True)[col].mean().unstack('closed');g['diff']=g.get(True)-g.get(False);z=g['diff'].unstack('quintile');z=z.get(4)-z.get(0);evrows.append(eventstats(z.to_numpy(),dict(group=group,metric=metric,variant=v,contrast='Q5-Q1 treated-minus-control'),len(d),d.code.nunique()))
   fake=read(['code','date','event_id','closed','dose','quintile','anchor',col],family='fake').rename(columns={col:'y'});fake=fake[np.isfinite(fake.y)&np.isfinite(fake.dose)].copy();cal=pd.DatetimeIndex(pd.read_csv(P/'meta/actual_full_calendar.csv',parse_dates=['date']).date);pos={x:i for i,x in enumerate(cal)};anchors=sorted(fake.loc[fake.closed,'date'].unique());episodes=[]
   for a in anchors:
    if not episodes or pos[a]>pos[episodes[-1][-1]]+1:episodes.append([a])
    else:episodes[-1].append(a)
   mapping={a:i+1 for i,ep in enumerate(episodes)for a in ep};fake['original_window']=fake.event_id;fake['event_id']=fake.anchor.map(mapping)+20000;fake['closed_x']=fake.closed*fake.dose;r=run(fake,['closed_x','dose'],plan=episode_plan(fake));rows.append(dict(group='HolidayPlacebo',metric=metric,variant=v,**r));g=fake.groupby(['event_id','quintile','closed'],observed=True).y.mean().unstack('closed');g['diff']=g.get(True)-g.get(False);z=g['diff'].unstack('quintile');z=z.get(4)-z.get(0);evrows.append(eventstats(z.to_numpy(),dict(group='HolidayPlacebo',metric=metric,variant=v,contrast='Q5-Q1 treated-minus-control'),len(fake),fake.code.nunique()))
 save(rows,'small_sample_webb.csv');save(evrows,'small_sample_event_tests.csv')
if __name__=='__main__':main_groups()
