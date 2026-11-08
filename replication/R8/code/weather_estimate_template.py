from common import *
from inference import fit,summarize,EVENTS,W,EVENT_INDEX,legacy,calendar_plan
import pyarrow.parquet as pq
from scipy.stats import t as student_t,binomtest

def evstats(v,meta,n,stocks):
 v=np.array(v,float);v=v[np.isfinite(v)];ne=len(v);se=np.std(v,ddof=1)/np.sqrt(ne)if ne>1 else np.nan;stat=np.mean(v)/se if se>0 else np.nan;nonzero=v[v!=0];return dict(**meta,beta_x100=np.mean(v)*100,se_x100=se*100,event_t=stat,event_t_p=2*student_t.sf(abs(stat),ne-1)if ne>1 else np.nan,sign_p=binomtest(int((nonzero>0).sum()),len(nonzero),.5).pvalue if len(nonzero)else np.nan,n=n,stocks=stocks,events=ne,positive=int((v>0).sum()),negative=int((v<0).sum()))

def main():
 import json
 final=Path('/Volumes/Extreme SSD/T9/connect_closed/R8');rows=[];tests=[];ri_status=[]
 for kind,family in [('daily','weather'),('segments','partial')]:
  fields=['code','date','event_id','closed','dose','if_delay','ih_delay','if_delay__w01','ih_delay__w01','if_delay__w005','ih_delay__w005']+(['segment','mixed_boundary','closed_segment']if kind=='segments'else[]);parts=[]
  for p in sorted((T/('panel_'+kind)).glob('*.parquet')):
   d=pq.read_table(p,columns=fields+['family'],use_threads=False).to_pandas(use_threads=False);parts.append(d[d.family.eq(family)])
  f=pd.concat(parts,ignore_index=True);f.code=f.code.astype('category')
  if kind=='segments':
   f=f[~f.mixed_boundary].copy();f['stock_day']=f.code.astype(str)+'_'+f.date.dt.strftime('%Y%m%d');eventmeta=EVENTS.set_index('event_id');seg=f.segment.to_numpy(np.int64);start=np.where(seg<4,570+30*seg,780+30*(seg-4));f['pattern']=((start>=f.event_id.map(eventmeta.closed_start))&(start+30<=f.event_id.map(eventmeta.closed_end)))
  f['closed_dose']=f.dose*(f.closed_segment if kind=='segments'else f.closed);f['quintile']=np.nan
  uniq=f[['event_id','code','dose']].drop_duplicates().dropna(subset=['dose'])
  for eid,g in uniq.groupby('event_id'):
   g=g.sort_values(['dose','code']);qm=dict(zip(g.code,np.minimum(4,np.arange(len(g))*5//len(g))));ix=f.event_id.eq(eid);f.loc[ix,'quintile']=f.loc[ix,'code'].map(qm)
  for metric in ['if_delay','ih_delay']:
   for v in ['raw','w01','w005']:
    col=metric if v=='raw'else metric+'__'+v;model,status=fit(f,col,['closed_dose','dose']if kind=='daily'else['closed_dose'],'code'if kind=='daily'else'stock_day','date'if kind=='daily'else'segment');names=list(model['names']);c=np.zeros(len(names));c[names.index('closed_dose')]=1;r,_=summarize(model,c,'closed_dose');ids=[EVENT_INDEX[e]for e in sorted(model['d'].event_id.unique())];r['wild_unique_draws']=len(np.unique(W[:,ids],axis=0))
    ri_family='full_day'if kind=='daily'else'half_day';_,calendars,audit,ri_meta=calendar_plan(model['d'],ri_family);assert len(calendars)==0,'Weather RI support changed from original 285; do not silently omit supported RI';audit.to_csv(final/'tables'/f'weather_ri_support_{ri_family}_{metric}_{v}.csv',index=False);ri_status.append(dict(**ri_meta,metric=metric,variant=v,n=model['n'],stocks=model['stocks'],events=model['events']));r.update(group='WeatherFull'if kind=='daily'else'WeatherHalf',metric=metric,variant=v,dose_timing='window_freeze',ri_p=np.nan,ri_B=len(calendars),ri_status=ri_meta['status'],ri_unique_calendars=ri_meta['unique_calendars']);rows.append(r)
    q=model['d'].merge(f[['code','date','event_id','quintile']+(['segment','pattern']if kind=='segments'else[])],on=['code','date','event_id']+(['segment']if kind=='segments'else[]),how='left',validate='1:1')
    if kind=='segments':q=q[q.pattern].copy()
    g=q.groupby(['event_id','quintile','closed'],observed=True)[col].mean().unstack('closed');g['diff']=g.get(1)-g.get(0);z=g['diff'].unstack('quintile');z=z.get(4)-z.get(0);tests.append(evstats(z.to_numpy(),dict(group='WeatherFull'if kind=='daily'else'WeatherHalf',metric=metric,variant=v,contrast='Q5-Q1 event-minus-prior same closed-clock windows'if kind=='segments'else'Q5-Q1 closed-minus-normal'),len(model['d']),model['stocks']));del model;legacy.FE_CACHE.clear();trim();print(kind,metric,v,flush=True)
 pd.DataFrame(rows).to_csv(final/'tables/weather_webb.csv',index=False);pd.DataFrame(tests).to_csv(final/'tables/weather_event_tests.csv',index=False)
 pd.DataFrame(ri_status).to_csv(final/'tables/weather_ri_status.csv',index=False)
 old=pd.read_csv(P/'R6/tables/main_estimates.csv');old=old[old.dose_timing.eq('window_freeze')&old.specification.isin(['full_day','half_day'])];old['group']=old.specification.map({'full_day':'WeatherFull','half_day':'WeatherHalf'});z=pd.DataFrame(rows).merge(old[['group','metric','variant','beta','se','n']],on=['group','metric','variant'],suffixes=('_new','_old'));z['beta_abs_error']=abs(z.beta_new-z.beta_old);z['se_abs_error']=abs(z.se_new-z.se_old);z['n_equal']=z.n_new.eq(z.n_old);z['n']=z.n_new;z.to_csv(final/'tables/weather_reproduction.csv',index=False);assert z.n_equal.all()and z.beta_abs_error.max()<1e-8 and z.se_abs_error.max()<1e-8
if __name__=='__main__':main()
