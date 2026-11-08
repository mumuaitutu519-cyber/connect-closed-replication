from common import *
from features import lagged
def run():
 f=pd.read_parquet(T/'features.parquet');assert not f.duplicated(['code','event_id']).any();assert f.loc[f.hk_hist_max.notna(),'hk_hist_max'].lt(f.loc[f.hk_hist_max.notna(),'freeze_date']).all();assert f.loc[f.known_date.notna(),'known_date'].lt(f.loc[f.known_date.notna(),'freeze_date']).all();assert f.loc[f.quarter_available.notna(),'quarter_available'].lt(f.loc[f.quarter_available.notna(),'freeze_date']).all();checks=[]
 # Independently stack actual minute returns for three stocks at first/late freezes.
 un=universe();ix=pd.Index(un.code);cal=pd.read_csv(P/'tables/official_calendar.csv',parse_dates=['date'])
 with np.load(T/'etf_proxy.npz') as z:h=dict(zip(z['dates'],z['returns']))
 with np.load(T/'futures_IF.npz') as z:ff=dict(zip(z['dates'],z['returns']))
 for eid in [1,36,45]:
  g=f[f.event_id.eq(eid)&f.hk_m_beta0.notna()].sort_values('code').head(3)
  if g.empty:continue
  freeze=g.freeze_date.iloc[0];days=cal.loc[cal.nb_open&cal.date.lt(freeze),'date'].tail(60);arrays={c:[] for c in g.code}
  for t in days:
   dn=int(np.datetime64(t,'D').astype('int64'))
   if dn not in h or dn not in ff:continue
   X=np.column_stack([np.ones(240),lagged(ff[dn]),lagged(h[dn])]);mask=np.isfinite(X).all(1)
   if mask.sum()<180:continue
   with np.load(T/'returns'/f'{t:%Y%m%d}.npz') as z:ids=z['ids'];r=z['returns'];eligible=z['eligible']
   by={a:j for j,a in enumerate(ids)}
   for c in arrays:
    j=by.get(ix.get_loc(c))
    if j is None or not eligible[j]:continue
    good=mask&np.isfinite(r[j]);arrays[c].append((X[good],r[j,good]))
  for c,parts in arrays.items():
   X=np.concatenate([x for x,y in parts]);Y=np.concatenate([y for x,y in parts]);cols=[0,*range(7,13)];b=np.linalg.lstsq(X[:,cols],Y,rcond=None)[0];bc=np.linalg.lstsq(X,Y,rcond=None)[0];bi=np.linalg.lstsq(X[:,:7],Y,rcond=None)[0];sst=np.sum((Y-Y.mean())**2);incr=(np.sum((Y-X[:,:7]@bi)**2)-np.sum((Y-X@bc)**2))/sst;corr=np.corrcoef(Y,X[:,7])[0,1];row=f[f.event_id.eq(eid)&f.code.eq(c)].iloc[0]
   for metric,actual in [('hk_m_beta0',b[1]),('hk_m_lagsum',b[2:].sum()),('hk_m_corr',corr),('hk_m_incr2',incr)]:
    err=abs(actual-row[metric]);assert err<1e-8,(eid,c,metric,err);checks.append(dict(event_id=eid,code=c,metric=metric,stacked_ols=actual,sufficient_statistics=row[metric],absolute_error=err,status='PASS'))
 save(checks,'minute_exposure_independent_checks.csv');v=f.hk_m_incr2.dropna();assert v.min()>-1e-8;assert v.max()<1+1e-8
 # All official specs must have a target status row for every outcome and transformation.
 m=pd.read_csv(R/'tables/main_estimates.csv');assert not m.duplicated(['specification','metric','variant']).any();names=pd.read_csv(R/'tables/registered_specifications.csv')['name']
 expected={(s,y,v) for s in names for y in PRIMARY for v in ['raw','w01','w005']};got=set(zip(m.specification,m.metric,m.variant));assert expected==got,(expected-got,got-expected);r=pd.read_csv(R/'tables/r2_baseline_reproduction.csv');assert r.n_equal.all() and r.beta_abs_error.max()<1e-9
 engine_check=pd.read_csv(R/'tables/bounded_vs_original_r2_inference.csv');assert engine_check.status.eq('PASS').all()
 protected=pd.read_csv(R/'tables/dose_binary_unchanged_assertions.csv');assert protected.unchanged.all() and not protected.winsorized.any()
 etfs=pd.read_csv(R/'tables/hk_etf_candidate_coverage.csv');assert len(etfs)==6 and etfs.status.eq('AVAILABLE').all();choice=pd.read_csv(R/'tables/hk_etf_daily_choice.csv');assert choice.amount.gt(0).all() and choice.valid_minutes.ge(180).all()
 race_check=pd.read_csv(R/'tables/r2_race_reproduction.csv');assert race_check.n_equal.all() and race_check.beta_abs_error.max()<1e-7 and race_check.se_abs_error.max()<1e-7
 unchanged=pd.read_csv(R/'tables/hscei_backfill_unchanged_features.csv') if (R/'tables/hscei_backfill_unchanged_features.csv').exists() else None
 if unchanged is not None:assert unchanged.status.eq('UNCHANGED').all() and unchanged.max_abs_error.max()<1e-12
 if (R/'tables/first_holder_repair_unchanged_features.csv').exists():assert pd.read_csv(R/'tables/first_holder_repair_unchanged_features.csv').status.eq('UNCHANGED').all()
 if (R/'tables/first_holder_freeze_audit.csv').exists():
  holders=pd.read_csv(R/'tables/first_holder_freeze_audit.csv',parse_dates=['announce_date','report_date','freeze_date']);assert holders.shareholder_rank.eq(1).all() and holders.announce_date.lt(holders.freeze_date).all() and holders.report_date.lt(holders.freeze_date).all()
 for (metric,variant),group in m.groupby(['metric','variant']):
  base_n=int(group.loc[group.specification.eq('baseline'),'n'].iloc[0]);assert group.n.le(base_n).all(),(metric,variant,'sample expanded beyond original Hold cohort')
  n1=group.loc[group.specification.eq('B_pre_quarter'),'n'].iloc[0];n2=group.loc[group.specification.eq('B_pre_daily_same_quarter'),'n'].iloc[0];assert n1==n2,(metric,variant,'quarter comparison sample differs',n1,n2)
  for intl in ['intl_share','intl_any','h_listed','bh_listed','foreign_first','export_industry']:
   a=group.loc[group.specification.eq('D_triple_'+intl),'n'].iloc[0];b=group.loc[group.specification.eq('D_sensitivity_'+intl),'n'].iloc[0];assert a==b,(metric,variant,intl,'sensitivity sample differs',a,b)
 refs=pd.read_csv(R/'refs_verified.csv');assert len(refs)==10;candidate=pd.read_csv(R/'refs_candidates.csv');assert candidate.groupby('search_journal').size().max()<=10;assert not candidate.doi.duplicated().any();assert candidate.abstract_300.fillna('').str.len().max()<=300
 resource=[]
 for path in sorted((R/'logs').glob('resource*.json')):
  try:record=json.loads(path.read_text())
  except json.JSONDecodeError:continue
  if 'peak_bytes' in record:resource.append(dict(file=path.name,peak_bytes=record['peak_bytes'],peak_GB=record['peak_bytes']/1e9,status=record.get('status'),exceeded_5GB=record['peak_bytes']>5e9))
 save(resource,'resource_summary.csv');resource_peak=max((x['peak_bytes'] for x in resource),default=0)
 js(R/'meta/validation.json',dict(status='PASS',scope='Statistical/data checks; resource exception separately disclosed',all_registered_targets=len(expected),unique_target_rows=len(got),r2_baseline_max_error=r.beta_abs_error.max(),minute_direct_checks=len(checks),timing_assertions=['minute last date < freeze','annual notice < freeze','quarter available < freeze'],no_dose_binary_winsor_assertions=True,original_Hold_cohort_fixed=True,quarter_and_daily_comparison_same_sample=True,international_sensitivity_same_sample=True,refs=len(refs),candidates=len(candidate),historical_peak_bytes=resource_peak,resource_budget_compliant_all_recorded_runs=resource_peak<=5e9))
 print('VALIDATION PASS',flush=True)
if __name__=='__main__':run()
