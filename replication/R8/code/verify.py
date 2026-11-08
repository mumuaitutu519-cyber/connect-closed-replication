from common import *
from scipy.stats import t as student_t
from inference import fit,close
import shutil

def main():
 checks=[]
 for name in ['state_all.csv','groups_all.csv','qfii_all.csv','aux_all.csv','pooled_horizon_estimates.csv','pooled_horizon_calendar_RI.csv','sync_1min_bridge.csv','small_sample_webb_all.csv']:
  d=pd.read_csv(R/'tables'/name);assert len(d)>0;assert all(c in d for c in ['n','stocks','events']);checks.append(dict(check=name,rows=len(d),status='PASS',n=d.n.max(),stocks=d.stocks.max(),events=d.events.max()))
 for p in (R/'tables').glob('quiet*_w01.csv'):
  d=pd.read_csv(p);assert d.loc[d.specification.ne('quiet_only_original_FE'),'wild_cluster_scheme'].eq('date_owned_nearest_event_union').all()
 # Reproduce old point estimates and complete samples exactly; Webb seed deliberately differs.
 old=pd.read_csv(P/'R7/tables/main_estimates.csv');new=pd.read_csv(R/'tables/aux_all.csv');out=[]
 for r in new[new.metric.isin(['if_delay','ih_delay','if_r2_now'])].itertuples():
  ref=old[old.family.eq('main')&old.specification.eq('full_control')&old.variant.eq(r.variant)&old.metric.eq(r.metric)&old.term.eq('closed_x')].iloc[0];err=abs(r.beta-ref.beta);seerr=abs(r.se-ref.se);ok=err<1e-8 and seerr<1e-8 and r.n==ref.n;out.append(dict(metric=r.metric,variant=r.variant,old_beta_x100=ref.beta_x100,new_beta_x100=r.beta_x100,beta_abs_error=err,se_abs_error=seerr,old_n=ref.n,n=r.n,stocks=r.stocks,events=r.events,status='PASS'if ok else'FAIL'))
 save(out,'original_full_control_reproduction.csv');assert all(r['status']=='PASS'for r in out)
 bridge=pd.read_csv(R/'tables/sync_1min_bridge.csv');ref1=pd.read_csv(P/'R7/tables/horizon_r2_1_w01.csv');ref1=ref1[ref1.specification.eq('horizon')].iloc[0];b=bridge[(bridge.metric=='r2_1')&(bridge['sample']=='own')].iloc[0];assert b.n==ref1.n and abs(b.beta-ref1.beta)<1e-8
 checks.append(dict(check='1min_R2_reproduction',status='PASS',n=b.n,stocks=b.stocks,events=b.events,max_abs_error=abs(b.beta-ref1.beta)))
 # Duplicated stock-date rows: independently verify dense OLS and cluster intersection aggregation.
 rng=np.random.default_rng(SEED);e=np.repeat(np.arange(14),17);t=np.tile(np.arange(17),14);x=rng.normal(size=(len(e),2));y=x@np.array([.2,-.4])+rng.normal(size=len(e))+rng.normal(size=14)[e]+rng.normal(size=17)[t];q=pd.DataFrame(dict(code=e,date=t,event_id=t//3+1,y=y,x0=x[:,0],x1=x[:,1],closed=t%2,dose=x[:,0]));q=pd.concat([q,q.iloc[::5]],ignore_index=True);m=fit(q,['x0','x1']);E=pd.get_dummies(q.code,dtype=float).to_numpy();D=pd.get_dummies(q.date,dtype=float).to_numpy()[:,1:];XX=np.column_stack([q[['x0','x1']],E,D]);bb=np.linalg.lstsq(XX,q.y,rcond=None)[0];err=max(abs(bb[:2]-m['b']));assert err<1e-10;checks.append(dict(check='duplicated_stock_date_FWL_dense_OLS',status='PASS',n=len(q),stocks=q.code.nunique(),events=q.event_id.nunique(),max_abs_error=err))
 F=np.column_stack([E,D]);X=q[['x0','x1']].to_numpy();Xw=X-F@np.linalg.lstsq(F,X,rcond=None)[0];u=q.y.to_numpy()-XX@bb;S=Xw*u[:,None];ss=pd.DataFrame(S).groupby(q.code).sum().to_numpy();dd=pd.DataFrame(S).groupby(q.date).sum().to_numpy();cc=pd.DataFrame(S).groupby([q.code,q.date]).sum().to_numpy();n=len(q);ns=q.code.nunique();nt=q.date.nunique();nc=len(cc);bread=np.linalg.pinv(Xw.T@Xw);V=bread@(ss.T@ss*ns/(ns-1)+dd.T@dd*nt/(nt-1)-cc.T@cc*nc/(nc-1))@bread*(n-1)/(n-ns-nt-2+1);ve=np.max(abs(V-m['V']));assert ve<1e-10;checks.append(dict(check='duplicate_cell_two_way_covariance_independent',status='PASS',n=n,stocks=ns,events=q.event_id.nunique(),max_abs_error=ve));close(m)
 support=pd.read_csv(R/'tables/quiet_definition_support.csv');assert support.minimum30.all();actual=pd.read_csv(R/'tables/quiet_actual_regression_support.csv');assert actual.minimum30.all();checks.append(dict(check='four_quiet_definitions_at_least30',status='PASS',n=int(support.classified_quiet_days.min()),stocks=np.nan,events=support.events.min()))
 quality=pd.read_csv(R/'tables/IF_quote_quality_exclusions.csv',parse_dates=['date']);assert quality.valid_minutes.lt(180).all()and quality.if_rv.isna().all();receipts=pd.read_csv(R/'tables/minute_day_receipts.csv',parse_dates=['date']).set_index('date');assert receipts.loc[quality.date,'if_rv'].isna().all();windows=pd.read_csv(R/'tables/market_daily_windows.csv');market=pd.read_csv(R/'tables/market_state_paired_tests.csv');assert int(market.loc[market.variable.eq('if_rv'),'n'].iloc[0])==int(windows.if_rv.notna().sum());assert int(quality.loc[quality.date.eq(pd.Timestamp('2025-12-19')),'valid_minutes'].iloc[0])==0
 centering=pd.read_csv(R/'tables/market_centering.csv');assert int(centering.loc[centering.variable.eq('if_rv'),'n'].iloc[0])==int(windows.loc[~windows.closed,'if_rv'].notna().sum())
 checks.append(dict(check='IF_missing_quote_is_missing_not_zero',status='PASS',n=len(quality),stocks=np.nan,events=quality.event_id.nunique()))
 q40=support[support.family.eq('quiet40_rv')].iloc[0];assert q40.classified_quiet_days==757 and q40.retained_quiet_days==757 and q40.events==246;checks.append(dict(check='quote_QC_rebuilt_quiet40_frozen_design',status='PASS',n=q40.retained_quiet_days,stocks=np.nan,events=q40.events))
 web=pd.read_csv(R/'tables/small_sample_webb_all.csv');assert web.wild_B.eq(9999).all();assert web.wild_unique_draws.le(9999).all();assert set(web.group.unique())=={'WeatherFull','WeatherHalf','SellOnly','quiet30_both','quiet40_both','quiet30_rv','quiet40_rv'};checks.append(dict(check='all_small_sample_groups_9999_Webbs',status='PASS',n=web.n.max(),stocks=web.stocks.max(),events=web.events.max()))
 res=pd.DataFrame([json.loads(s)for s in(R/'logs/stage_resource_receipts.jsonl').read_text().splitlines()]);assert res.peak_bytes.max()<13_000_000_000;checks.append(dict(check='process_tree_under13GB',status='PASS',peak_bytes=res.peak_bytes.max(),n=np.nan,stocks=np.nan,events=np.nan))
 assert hashlib.sha256((R/'PREREGISTRATION_R8.md').read_bytes()).hexdigest()==json.loads((R/'meta/preregistration_lock.json').read_text())['sha256'];checks.append(dict(check='preregistration_unchanged',status='PASS',n=np.nan,stocks=np.nan,events=np.nan))
 initial=pd.read_csv(R/'tables/input_manifest.csv');full=pd.read_csv(R/'tables/full_input_source_manifest.csv');joined=initial[['path','sha256']].merge(full[['path','sha256']],on='path',suffixes=('_initial','_final'));assert joined.sha256_initial.eq(joined.sha256_final).all();checks.append(dict(check='frozen_inputs_unchanged_during_run',status='PASS',n=len(joined),stocks=np.nan,events=np.nan))
 addendum=R/'meta/PREREGISTRATION_R8_POOLED_RI_ADDENDUM.md';starts=[r['start']for r in res.to_dict('records')if str(r['command'][-1]).endswith('horizons.py')];assert starts and addendum.stat().st_mtime<min(starts);checks.append(dict(check='pooled_RI_addendum_precedes_first_horizon_fit',status='PASS',n=np.nan,stocks=np.nan,events=np.nan))
 history=R/'meta/development_resource_history.json'
 if not history.exists():js(history,res.to_dict('records'))
 save(checks,'delivery_validation.csv')
 for partial in (R/'tables').glob('*.partial'):
  if partial.with_suffix('').exists():partial.unlink()
 # Statistical and design CSVs all expose the three mandatory count columns.
 for csv in sorted((R/'tables').glob('*.csv')):
  try:d=pd.read_csv(csv)
  except pd.errors.EmptyDataError:continue
  changed=False
  for c in ['n','stocks','events']:
   if c not in d:d[c]=np.nan;changed=True
  if 'Obs'not in d:d['Obs']=d['n'];changed=True
  if changed:d.to_csv(csv,index=False)
 manifest={str(p.relative_to(R)):dict(bytes=p.stat().st_size,sha256=hashlib.file_digest(p.open('rb'),'sha256').hexdigest())for folder in ['code','tables']for p in sorted((R/folder).glob('*'))if p.is_file()};js(R/'meta/output_code_manifest.json',manifest);js(R/'meta/DELIVERY_COMPLETE.json',dict(status='PASS',utc=pd.Timestamp.now(tz='UTC').isoformat(),checks=len(checks),tables=len(list((R/'tables').glob('*.csv'))),seed=SEED));print('DELIVERY_VALIDATED',len(checks),flush=True)
if __name__=='__main__':main()
