from common import *
from estimate import read

def main():
 f=read(['code','date','event_id','dose','if_delay__w01']);f=f[np.isfinite(f.dose)&np.isfinite(f.if_delay__w01)];u=f[['event_id','code']].drop_duplicates();feat=pd.read_parquet(T/'all_features.parquet');feat=feat[feat.family.eq('main')];d=u.merge(feat,on=['event_id','code'],validate='1:1');d['HoldQuintile']=np.nan
 for eid,ix in d.groupby('event_id').groups.items():
  q=d.loc[ix].sort_values(['dose','code']);d.loc[q.index,'HoldQuintile']=np.minimum(5,1+np.arange(len(q))*5//len(q))
 rows=[]
 for grouping,column,offset in [('original_R2_frozen_quintile','quintile',1),('R7_estimation_sample_rank','HoldQuintile',0)]:
  for quintile,g in d.groupby(column):
   for name,c in [('Hold_pp','dose'),('Size_log_circulating_cap','logcap'),('Value_BM_positive_PB','value'),('BetaIF','ifbeta'),('PreDelay','predelay'),('Analysts_log1p_orgs','analyst')]:
    z=g[g[c].notna()];rows.append(dict(grouping=grouping,quintile=int(quintile+offset),variable=name,mean=z[c].mean(),sd=z[c].std(),n=len(z),stocks=z.code.nunique(),events=z.event_id.nunique(),sample_unit='stock-event',total_group_stock_events=len(g)))
 save(rows,'hold_quintile_balance.csv');events=pd.read_csv(P/'tables/events.csv',parse_dates=['start']);counts=[]
 for eid,g in f.groupby('event_id'):
  a=feat[feat.event_id.eq(eid)];valid=a[['dose',*RACE,*HK]].notna().all(1);keys=set(a.loc[valid,'code']);z=g[g.code.isin(keys)];counts.append(dict(metric='if_delay',variant='w01',sample='full16',event_id=eid,start=events.set_index('event_id').loc[eid,'start'],baseline_n=len(g),baseline_stocks=g.code.nunique(),n=len(z),stocks=z.code.nunique(),events=int(len(z)>0),status='OK'if len(z)else'NO_COMPLETE_FROZEN_CONTROLS',missing_features=';'.join(c for c in RACE+HK if not a[c].notna().any())))
 counts.append(dict(metric='if_delay',variant='w01',sample='full16',event_id=46,start=events.set_index('event_id').loc[46,'start'],baseline_n=0,baseline_stocks=0,n=0,stocks=0,events=0,status='IF_IH_SOURCE_ENDS_2026_09_01',missing_features='outcomes'));save(counts,'event_complete_case_audit.csv')
 wins=[]
 for c in METRICS:
  for v in VARIANTS:wins.append(dict(variable=c,variant=v,winsorized=v!='raw',rule='strictly past eligible normal-NB stock expanding quantiles >=60; otherwise pooled before event freeze',n=np.nan,stocks=np.nan,events=np.nan))
 for c in ['dose','qfii','closed','quintile','value','nonzero_count_control']:wins.append(dict(variable=c,variant='none',winsorized=False,rule='frozen dose/dummy/pre-event descriptive BM/original count control',n=np.nan,stocks=np.nan,events=np.nan))
 for c in ['market_amount','if_rv','quiet','if_day_return','qdc_turnover_million','qdc_netflow_million','hkex_turnover_million','log_turnover']:
  wins.append(dict(variable=c,variant='none',winsorized=False,rule='raw market/IF path or daily flow; log uses positive raw total turnover; no post-event truncation',n=np.nan,stocks=np.nan,events=np.nan))
 for c in HK:
  for v in VARIANTS:wins.append(dict(variable=c,variant=v,winsorized=v!='raw',rule='R4 already-frozen cross-sectional exposure variant; US same construction at own freeze; never refit from future observations',n=np.nan,stocks=np.nan,events=np.nan))
 wins.append(dict(variable='IF_day_x_Closed_x_Hold',variant='none',winsorized=False,rule='interaction of raw IF daily path, original frozen Hold and Closed; dependent daily/open30 return receives registered variant',n=np.nan,stocks=np.nan,events=np.nan))
 save(wins,'winsorization_variable_list.csv');print('BALANCE_COMPLETE',flush=True)
if __name__=='__main__':main()
