from common import *
from inference import bh
from collections import defaultdict

def adjusted(d,groups):
 for c in ['p','wild_p','ri_p']:
  if c in d:d['BH_'+c]=d.groupby(groups,dropna=False)[c].transform(bh)
 return d

def main():
 for variant in VARIANTS:
  p=R/'tables'/f'cumulative_recovery_{variant}.csv';d=pd.read_csv(p);save(adjusted(d,['variant']),p.name)
 for name,groups in [('pooled_horizon_estimates.csv',['variant','specification']),('pooled_horizon_calendar_RI.csv',['variant'])]:save(adjusted(pd.read_csv(R/'tables'/name),groups),name)
 for family in ['quiet30_both','quiet40_both','quiet30_rv','quiet40_rv']:
  for variant in VARIANTS:
   d=pd.concat([pd.read_csv(R/'tables'/f'{family}_{m}_{variant}.csv')for m in ['if_delay','ih_delay','if_r2_now']],ignore_index=True);d=adjusted(d,['specification','term'])
   for m,g in d.groupby('metric'):save(g,f'{family}_{m}_{variant}.csv')
 dyn=pd.read_csv(R/'tables/dynamic_all.csv')
 for c in ['p','wild_p']:
  dyn['BH_time_'+c]=dyn.groupby(['metric','variant'],dropna=False)[c].transform(bh);dyn['BH_outcomes_and_time_'+c]=dyn.groupby('variant',dropna=False)[c].transform(bh)
 save(dyn,'dynamic_all.csv')
 common={h:defaultdict(int)for h in [30,60]};actual={h:defaultdict(int)for h in [30,60]}
 for p in sorted((T/'pooled_ri_parts').glob('*.parquet')):
  d=pd.read_parquet(p,columns=['code','event_id','dose','common_30','common_60'])
  for h in [30,60]:
   q=d[d[f'common_{h}']&np.isfinite(d.dose)][['code','event_id']].drop_duplicates();counts=q.groupby('event_id',observed=True).code.nunique()
   for e,n in counts.items():common[h][int(e)]+=int(n)
 for p in sorted((T/'pooled_horizons').glob('*.parquet')):
  d=pd.read_parquet(p,columns=['code','event_id','closed','dose','pooled_beta_30','pooled_beta_60'])
  for h in [30,60]:
   q=d[np.isfinite(d.dose)&np.isfinite(d[f'pooled_beta_{h}'])];both=q.groupby(['code','event_id'],observed=True).closed.nunique();counts=pd.Series(both[both.eq(2)].index.get_level_values('event_id')).value_counts()
   for e,n in counts.items():actual[h][int(e)]+=int(n)
 patterns=json.loads((T/'pooled_ri_patterns.json').read_text());ev=pd.read_csv(P/'tables/events.csv',parse_dates=['start']).set_index('event_id');rows=[]
 with np.load(T/'pooled_ri_draws.npz')as z:events=z['events'].copy();draws=z['codes'].copy();global_unique=int(z['unique_projected'])
 effective={}
 for h in [30,60]:
  support=[e for e,n in common[h].items()if n>0];effective[h]=len(np.unique(draws[np.isin(events,support)].T,axis=0))
  for e,p in patterns.items():
   e=int(e);n=2*common[h][e];a=2*actual[h][e];empty=0 in p['patterns']or 2**len(p['dates'])-1 in p['patterns'];status='COMMON_PATTERN_SAMPLE_AVAILABLE'if n else'PERMUTATION_LEAVES_A_STATE_EMPTY'if empty and a else'NO_ACTUAL_PAIRED_OUTCOME'if not a else'NO_COMMON_STOCKS';rows.append(dict(minutes=h,event_id=e,start=ev.loc[e,'start'],patterns=len(p['patterns']),has_empty_state_pattern=empty,actual_paired_n=a,n=n,stocks=common[h][e],events=int(n>0),status=status))
 main_results=pd.read_csv(R/'tables/pooled_horizon_estimates.csv')
 for h in [30,60]:
  ref=main_results[main_results.metric.eq(f'pooled_beta_{h}')&main_results.variant.eq('w01')&main_results.specification.eq('stock_event_state_pooled_paired')].iloc[0];assert ref.n==2*sum(actual[h].values())
 save(rows,'pooled_RI_event_support.csv');d=pd.read_csv(R/'tables/pooled_horizon_calendar_RI.csv');d['ri_unique_calendars_global']=global_unique;d['ri_unique_effective_patterns']=[effective[int(m.split('_')[-1])]for m in d.metric];d['ri_unique_calendars']=d.ri_unique_effective_patterns
 for row in d.itertuples():assert row.n==2*sum(common[int(row.metric.split('_')[-1])].values())
 save(d,'pooled_horizon_calendar_RI.csv');print('INFERENCE_FINISHED',effective,flush=True)
if __name__=='__main__':main()
