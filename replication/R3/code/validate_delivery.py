"""Independent artifact, multiplicity, as-of and numerical delivery checks; safe after cleanup."""
import os
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS']:
    os.environ[key]='1'
from pathlib import Path
import json,hashlib,datetime
import numpy as np
import pandas as pd
from scipy import stats

R=Path(__file__).resolve().parents[1]
def sha(path):
    h=hashlib.sha256()
    with path.open('rb')as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()

def main():
    m=pd.read_csv(R/'tables/main_family.csv');a=pd.read_csv(R/'tables/all_estimates.csv')
    daily=['m1_buy_share_1m','m1_sell_share_1m','m1_buy_n_1m','m1_sell_n_1m','m3_wait_median','m3_update60','m4_spread_bp','m4_depth5_yuan','m5_cancel_rate','m5_limit_market_ratio','m5_avg_order_yuan']
    expected={(v,'closed_dose')for v in daily}|{('m2_'+p,t)for p in ['IF','IH']for t in ['contemporaneous','lag1_5_sum']}
    assert len(m)==15 and set(zip(m.metric,m.term))==expected
    assert m.status.eq('OK').all()and m.variant.eq('w01').all()and m.specification.eq('baseline').all()
    assert m.wild_B.eq(9999).all()and not a.status.eq('IMPLEMENTATION_ERROR').any()
    for source,target in [('p','q_bh_main15'),('wild_p','q_bh_wild_main15')]:
        p=m[source].to_numpy();order=np.argsort(p);q=np.minimum.accumulate((p[order]*15/np.arange(1,16))[::-1])[::-1];actual=m[target].to_numpy()[order]
        np.testing.assert_allclose(np.minimum(q,1),actual,rtol=1e-12,atol=1e-12)
    np.testing.assert_allclose(m.p,2*stats.t.sf(np.abs(m.beta/m.se),m.df),rtol=1e-11,atol=1e-12)
    np.testing.assert_allclose(m.ci_low,m.beta-stats.t.ppf(.975,m.df)*m.se,rtol=1e-11,atol=1e-10)
    assert len(list((R/'tables/estimates').glob('*.csv')))==1230
    days=pd.read_csv(R/'tables/day_processing_status.csv');assert len(days)==512 and days.status.eq('OK').all()and days.accepted.eq(True).all()
    counts=pd.read_csv(R/'data_scale.csv').set_index('item').value
    for name,value in [('planned_real_treated_dates',42),('planned_real_control_dates',158),('processed_OK_dates',512),('processed_failed_dates',0),('real_distinct_stocks',2705)]:assert counts[name]==value
    lock=json.loads((R/'meta/preregistration_lock.json').read_text());assert sha(R/'PREREGISTRATION_R3.md')==lock['sha256'];assert pd.Timestamp(lock['locked_at'])<pd.Timestamp(lock['first_estimate_at'])
    for file in ['final_feature_scope_asof_validation.json','QFII_asof_validation.json','column_pruning_validation.json','unsigned_market_parser_validation.json','missing_futures_empty_flow_validation.json']:
        assert json.loads((R/'meta'/file).read_text())['status']=='PASS'
    threshold_rows={}
    for file in ['winsor_thresholds_daily.csv','winsor_thresholds_flow.csv']:
        n=0
        for chunk in pd.read_csv(R/'tables'/file,usecols=['cutoff','history_max','n','q005','q01','q99','q995'],chunksize=100000):
            cutoff=pd.to_datetime(chunk.cutoff);history=pd.to_datetime(chunk.history_max,errors='coerce');has=chunk.n.gt(0)
            assert history[has].notna().all()and history[has].lt(cutoff[has]).all()
            q=chunk[['q005','q01','q99','q995']].to_numpy(float);finite=np.isfinite(q).all(1);assert (np.diff(q[finite],axis=1)>=0).all();n+=len(chunk)
        threshold_rows[file]=n
    weights=pd.read_csv(R/'tables/event_window_weights.csv');np.testing.assert_allclose(weights.groupby(['kind','date']).inverse_date_use_weight.sum(),1,rtol=0,atol=1e-12)
    for manifest in ['output_manifest.json','code_manifest.json']:
        for row in json.loads((R/'meta'/manifest).read_text()):
            path=R/row['path'];assert path.is_file()and path.stat().st_size==row['bytes']and sha(path)==row['sha256'],str(path)
    identity=json.loads((R/'meta/estimation_identity.json').read_text());present=all(Path(p).exists()for p in identity['files'])
    if present:
        h=hashlib.sha256()
        for filename in identity['files']:
            h.update(filename.encode())
            with Path(filename).open('rb')as stream:
                for block in iter(lambda:stream.read(8*1024*1024),b''):h.update(block)
        assert h.hexdigest()==identity['sha256']
    for path in (R/'meta/memory_pruning_reference').glob('*.csv'):
        pd.testing.assert_frame_equal(pd.read_csv(path),pd.read_csv(R/'tables/estimates'/path.name),check_exact=True)
    runtime=json.loads((R/'meta/runtime.json').read_text());assert runtime['workers']==4 and runtime['numeric_threads']==1 and runtime['seed']==20261115 and runtime['peak_aggregate_rss_gb']<10
    final=json.loads((R/'meta/final_validation.json').read_text());assert final['status']=='PASS'and final['complete_raw_days']is True
    out=dict(status='PASS',primary_tests=15,estimated_jobs=len(list((R/'tables/estimates').glob('*.csv'))),coefficient_records=len(a),primary_CGM_BH_under_005=int(m.q_bh_main15.lt(.05).sum()),primary_wild_BH_under_005=int(m.q_bh_wild_main15.lt(.05).sum()),threshold_rows=threshold_rows,estimation_input_identity_checked=present,output_and_code_hashes_verified=True,checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (R/'meta/delivery_validation.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False))
if __name__=='__main__':main()
