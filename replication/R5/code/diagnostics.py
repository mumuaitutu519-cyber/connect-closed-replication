from common import *
import pyarrow.dataset as ds

def main():
 datasets=ds.dataset(T/'panel',format='parquet');parts=[];checks=[]
 for path in sorted((T/'panel').glob('*.parquet')):
  d=pd.read_parquet(path,columns=['code','date','event_id','closed','dose','if_delay','ih_delay','if_r2_now','if_r2_full','if_b1','if_b2','if_b3','if_b4','if_b5','adjust5','shock_n']);good=d[['if_delay','if_r2_now','if_r2_full']].notna().all(axis=1);err=abs(d.loc[good,'if_delay']-(1-d.loc[good,'if_r2_now']/d.loc[good,'if_r2_full']));checks.append(dict(block=path.stem,n=int(good.sum()),stocks=d.loc[good,'code'].nunique(),events=d.loc[good,'event_id'].nunique(),identity_max_abs=float(err.max())if len(err)else np.nan,r2_now_min=d.if_r2_now.min(),r2_full_min=d.if_r2_full.min(),r2_nested_violations=int((d.if_r2_now>d.if_r2_full+1e-10).sum()),adjust5_n=d.adjust5.notna().sum(),adjust5_negative=(d.adjust5<0).sum(),adjust5_above1=(d.adjust5>1).sum(),mean_shocks=d.loc[d.adjust5.notna(),'shock_n'].mean()))
  a=d.groupby(['event_id','closed'],observed=True).agg(n=('code','size'),stocks=('code','nunique'),if_delay_mean=('if_delay','mean'),r2_now_mean=('if_r2_now','mean'),r2_full_mean=('if_r2_full','mean'),adjust5_mean=('adjust5','mean'),adjust5_n=('adjust5','count'),shocks_mean=('shock_n','mean')).reset_index();a['block']=path.stem;parts.append(a)
 save(pd.DataFrame(checks),'G_component_identity_checks.csv');save(pd.concat(parts,ignore_index=True).assign(events=1),'G_raw_components_by_event_block.csv')
 # Existing 272 baseline comparison is independent of the new sample build and estimator code.
 results=pd.read_csv(R/'tables/all_estimates.csv');repro=[]
 for metric in PRIMARY:
  old=pd.read_csv(P/'R2/tables'/f'estimates_{metric}.csv')
  for variant in ['raw','w01','w005']:
   o=old[old.specification.eq('baseline')&old.exposure.eq('dose')&old.variant.eq(variant)&old.term.eq('closed_x')].iloc[0];n=results[results.metric.eq(metric)&results.variant.eq(variant)&results.specification.eq('baseline')&results.term.eq('closed_x')].iloc[0]
   for field in ['beta','se','n','stocks','dates']:
    delta=abs(n[field]-o[field]);repro.append(dict(metric=metric,variant=variant,field=field,actual=n[field],expected=o[field],abs_error=delta,n=n.n,stocks=n.stocks,events=n.events,status='PASS'if delta<(1e-8 if field in ['beta','se']else .1)else'FAIL'))
 save(pd.DataFrame(repro),'R2_baseline_reproduction_checks.csv')
 wins=[]
 for c in NEW:
  for v in ['raw','w01','w005']:
   dd=pd.read_csv(R/'tables'/f'distribution_{c}_{v}.csv').iloc[0];wins.append(dict(variable=c,variant=v,winsorized=(v!='raw'),rule='past eligible NB-open stock expanding >=60; else pooled strictly pre-freeze; own-variable quantiles',n=dd.n,stocks=dd.stocks,events=dd.events))
 wins += [dict(variable=c,variant='none',winsorized=False,rule='count/group/frozen dose; not winsorized',n=0,stocks=0,events=0)for c in ['valid_minutes','Hold','QFII','quintile','amount_decile']]
 save(pd.DataFrame(wins),'winsorization_variable_list.csv')
 print('DIAGNOSTICS',pd.DataFrame(repro).groupby('status').size().to_dict(),flush=True)
if __name__=='__main__':main()
