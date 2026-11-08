from common import *
def main():
 from finish_inference import main as finish_inference
 finish_inference()
 if not (R/'tables/full_input_source_manifest.csv').exists():
  from provenance import main as hash_inputs
  hash_inputs()
 market=pd.read_csv(R/'tables/market_state_paired_tests.csv');state=pd.read_csv(R/'tables/state_all.csv');qf=pd.read_csv(R/'tables/qfii_all.csv');groups=pd.read_csv(R/'tables/groups_all.csv');parts=[];rows=[]
 def add(message,r):
  parts.append(message);rows.append(dict(fact=message.removeprefix('- '),n=r.n,stocks=r.stocks,events=r.events))
 for r in market.itertuples():add(f'- 关闭日{r.variable}相对配对对照日均值变化{r.mean_relative_change:.2%}，配对t p={r.paired_t_p:.6g}。',r)
 for r in state[state.variant.eq('w01')&state.specification.isin(['Hold_x_both','Hold_x_both_and_Closed'])].itertuples():add(f'- {r.metric}，{r.controls}，{r.specification}：Closed×Hold={r.beta_x100:.6g}，保留{r.retention_same_sample:.2%}，Webb p={r.wild_p:.6g}。',r)
 for p in sorted((R/'tables').glob('quiet*_w01.csv')):
  d=pd.read_csv(p)
  if 'specification'not in d:continue
  for r in d[d.specification.isin(['quiet_only_original_FE','Closed_minus_Quiet_same_regression'])].itertuples():add(f'- {r.family} {r.metric} {r.specification}：β×100={r.beta_x100:.6g}，TW p={r.p:.6g}，Webb p={r.wild_p:.6g}，事件段={r.events}。',r)
 for r in groups[groups.variant.eq('w01')&groups.specification.eq('common_controls')].itertuples():add(f'- 全控制HKOnly−Shared {r.metric}差={r.beta_x100:.6g}，Webb p={r.wild_p:.6g}。',r)
 for r in qf[qf.variant.eq('w01')&qf.term.eq('cx_qfii')].itertuples():add(f'- 全控制QFII {r.metric}：β×100={r.beta_x100:.6g}，80% MDE×100={r.mde80_x100:.6g}，Webb p={r.wild_p:.6g}。',r)
 save(rows,'adverse_summary.csv')
 (R/'meta/adverse_facts.md').write_text('\n'.join(parts)+'\n')
if __name__=='__main__':main()
