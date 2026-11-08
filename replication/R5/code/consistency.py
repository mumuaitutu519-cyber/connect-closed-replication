from common import *
import pyarrow.dataset as ds
from estimate import read

def main():
 ev=pd.read_csv(P/'tables/events.csv',parse_dates=['start','end','resume']).set_index('event_id');feat=features();mapping=pd.read_csv(P/'tables/event_date_map.csv',parse_dates=['date']);qcov=[];ahrows=[];period=[];race=[];sample=[];checks=[]
 for metric in PRIMARY:
  f=read(['code','date','event_id','closed','dose','qfii','ah','freeze_date','logcap','logamount','csi300','sse50','csi500','ifbeta','predelay',metric,metric+'__w01']);valid=f[['dose',metric+'__w01']].notna().all(axis=1);q=f[valid];uq=q[['event_id','code','qfii']].drop_duplicates();pos=uq[uq.qfii.gt(0)];vv=pos.qfii.to_numpy();pp=np.quantile(vv,[0,.01,.1,.25,.5,.75,.9,.99,1])if len(vv)else np.full(9,np.nan)
  qcov.append(dict(metric=metric,n=len(pos),stocks=pos.code.nunique(),events=pos.event_id.nunique(),sample_stock_events=len(uq),qfii_known_stock_events=uq.qfii.notna().sum(),positive_stock_days=q.qfii.gt(0).sum(),positive_mean=pos.qfii.mean(),positive_sd=pos.qfii.std(),**dict(zip(['min','p01','p10','p25','p50','p75','p90','p99','max'],pp))))
  for eid,g in uq.groupby('event_id'):
   p=g[g.qfii.gt(0)];sample.append(dict(metric=metric,event_id=eid,n=len(p),stocks=p.code.nunique(),events=1,qfii_known=g.qfii.notna().sum(),all_stock_events=len(g)))
  a=q[q.ah.eq(1)];ahrows.append(dict(metric=metric,n=len(a),stocks=a.code.nunique(),events=a.event_id.nunique(),dates=a.date.nunique(),stock_clusters=a.code.nunique(),date_clusters=a.date.nunique(),joint_unique_cells=len(a[['code','date']].drop_duplicates())))
  for label,mask in [('2017_2019',q.freeze_date.dt.year.between(2017,2019)),('2020_2023',q.freeze_date.dt.year.between(2020,2023)),('2024_Jan_Aug',q.freeze_date.ge('2024-01-01')&q.freeze_date.lt('2024-08-19')),('post_Aug2024',q.freeze_date.ge('2024-08-19'))]:
   d=q[mask];period.append(dict(metric=metric,period=label,n=len(d),stocks=d.code.nunique(),events=d.event_id.nunique(),dates=d.date.nunique(),event_ids=','.join(map(str,sorted(d.event_id.unique())))))
  cc=['logcap','logamount','csi300','sse50','csi500','ifbeta','predelay'];allok=q[cc].notna().all(axis=1)
  for eid,ee in ev.iterrows():
   before=f[f.event_id.eq(eid)];g=q[q.event_id.eq(eid)];r=g[g[cc].notna().all(axis=1)];miss={c:int(g[c].isna().sum())for c in cc};race.append(dict(metric=metric,event_id=eid,start=ee.start,n=len(r),stocks=r.code.nunique(),events=int(len(r)>0),baseline_n=len(g),baseline_stocks=g.code.nunique(),eligible_panel_n=len(before),raw_metric_n=before[metric].notna().sum(),**{'missing_'+k:v for k,v in miss.items()},status='OK'if len(r)else'NO_COMPLETE_CASES'))
  old=pd.read_csv(P/'R2/tables'/f'estimates_{metric}.csv');old=old[old.specification.eq('AH_only')&old.variant.eq('w01')&old.term.eq('closed_x')].iloc[0];checks +=[dict(check=f'{metric}_AH_n',actual=len(a),expected=old.n,abs_error=abs(len(a)-old.n),status='PASS'if len(a)==old.n else'FAIL'),dict(check=f'{metric}_AH_stocks',actual=a.code.nunique(),expected=old.stocks,abs_error=abs(a.code.nunique()-old.stocks),status='PASS'if a.code.nunique()==old.stocks else'FAIL'),dict(check=f'{metric}_AH_dates',actual=a.date.nunique(),expected=old.dates,abs_error=abs(a.date.nunique()-old.dates),status='PASS'if a.date.nunique()==old.dates else'FAIL')]
  del f,q;release()
 save(pd.DataFrame(qcov),'J_QFII_positive_distribution.csv');save(pd.DataFrame(sample),'J_QFII_by_event.csv');save(pd.DataFrame(ahrows),'K_AH_cluster_counts.csv');save(pd.DataFrame(period),'K_period_reconciliation.csv');save(pd.DataFrame(race),'K_cumulative7_event_missingness.csv');save(pd.DataFrame(checks),'K_count_reproduction_checks.csv')
 # Add raw source feature availability to identify a fully absent control versus no futures outcome.
 fr=feat.groupby('event_id').agg(n=('code','size'),stocks=('code','nunique'),logcap_n=('logcap','count'),logamount_n=('logamount','count'),csi300_n=('csi300','count'),sse50_n=('sse50','count'),csi500_n=('csi500','count'),ifbeta_n=('ifbeta','count'),predelay_n=('predelay','count')).reset_index();fr['events']=1;save(fr,'K_frozen_feature_availability.csv')
 print('CONSISTENCY',ahrows,flush=True)
if __name__=='__main__':main()
