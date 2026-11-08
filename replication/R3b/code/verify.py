from common import *
from inference import bh

def verify():
 f=pd.read_csv(R/'tables/all_estimates.csv');expected=6*2*2*4*3*2+6*4*3*2*3;assert len(f)==expected,(len(f),expected);assert not f.duplicated(['group','fake','window','joint','metric','variant','exposure','term']).any();assert f.status.isin(['OK','NONPOSITIVE_TWO_WAY_VARIANCE','NO_IDENTIFYING_VARIATION','NO_VALID_EVENTS']).all(),f[~f.status.isin(['OK','NONPOSITIVE_TWO_WAY_VARIANCE','NO_IDENTIFYING_VARIATION','NO_VALID_EVENTS'])][['group','metric','status']].to_dict('records')
 good=f.ri_B.gt(0)
 if good.any():assert f.loc[good,'ri_beta_abs_error'].max()<1e-7
 for col in ['p','wild_p','ri_p','q_bh','p_romano_wolf']:
  v=f[col].dropna();assert v.between(0,1).all()
 core=f[~f.joint&~f.fake&f.group.eq('US')&f.window.eq('r1')&f.variant.eq('w01')&f.exposure.eq('dose')];assert len(core)==4
 ev=pd.read_csv(R/'tables/events.csv',parse_dates=['start','end','freeze_date']);assert (ev.freeze_date<ev.start).all();m=pd.read_csv(R/'tables/event_date_map.csv',parse_dates=['date','freeze_date']);assert (m.date>=m.freeze_date).all();normal=set(pd.read_csv(R/'tables/normal_control_dates.csv',parse_dates=['date']).date);assert set(m.loc[m.treated.eq(0),'date']).issubset(normal)
 weather=pd.read_csv(R/'tables/HKEX_nonfull_day_audit.csv',parse_dates=['date']);assert not set(m.date)&set(weather.loc[weather.exclude_from_full_day,'date'])
 # Each stacked date must have one treatment state, even if frozen doses differ by event.
 assert m.groupby(['group','fake','window','date']).treated.nunique().max()==1
 for key,g in f.groupby(['group','fake','window','joint','variant','exposure','term']):assert np.allclose(bh(g.p),g.q_bh,equal_nan=True)
 audit=json.loads((R/'meta/preregistration_lock.json').read_text());assert audit['sha256']==hashlib.sha256((R/'PREREGISTRATION_R3b.md').read_bytes()).hexdigest();assert audit['first_estimate_at'] is not None
 report=(R/'RESULTS_FOR_CLAUDE.md').read_text();assert all(x in report for x in ['最不利事实','MDE','Fieller','安慰剂','核数']);assert (R/'sample_by_event.csv').stat().st_size>1000
 checks=dict(status='PASS',estimate_rows=len(f),expected_rows=expected,main_rows=int((~f.joint&~f.fake).sum()),fake_rows=int(f.fake.sum()),joint_rows=int(f.joint.sum()),RI_available_rows=int(good.sum()),RI_FWL_max_abs_error=float(f.loc[good,'ri_beta_abs_error'].max()) if good.any() else None,status_counts=f.status.value_counts().to_dict(),unique_registered_cells=True,all_probability_ranges_valid=True,BH_recomputed=True,calendar_controls_valid=True,stacked_date_treatment_unique=True,preregistration_unchanged=True,precontrol_freeze_strictly_before_event=True,post_estimation_boundary_correction_disclosed=(R/'AMENDMENT_R3b_POST_ESTIMATION.md').exists())
 js(R/'meta/final_validation.json',checks)
 manifest=[]
 for directory in [R/'code',R/'tables']:
  for p in sorted(directory.rglob('*')):
   if p.is_file() and '__pycache__' not in str(p):manifest.append(dict(path=str(p.relative_to(R)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
 for p in [R/'RESULTS_FOR_CLAUDE.md',R/'PREREGISTRATION_R3b.md',R/'sample_by_event.csv',R/'run_all.sh',R/'AMENDMENT_R3b_POST_ESTIMATION.md']:manifest.append(dict(path=str(p.relative_to(R)),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
 js(R/'meta/output_sha256.json',manifest);print(checks)
if __name__=='__main__':verify()
