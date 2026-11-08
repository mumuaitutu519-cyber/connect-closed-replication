from common import *
import shutil

def main():
 ev=pd.read_csv(R/'tables/events.csv',parse_dates=['start','end','freeze_date']);bad=ev[ev.freeze_date.ge(ev.start)].copy()
 if not len(bad):return
 assert bad.fake.all() and bad.window.eq('weekday').all()
 archive=R/'meta/boundary_original';archive.mkdir(exist_ok=True)
 for name in ['events.csv','event_date_map.csv','event_date_map_all.csv','freezes.csv','exposure_coverage.csv']:
  dest=archive/name
  if not dest.exists():shutil.copy2(R/'tables'/name,dest)
 if (R/'RESULTS_FOR_CLAUDE.md').exists() and not (archive/'RESULTS_BEFORE_CORRECTION.md').exists():shutil.copy2(R/'RESULTS_FOR_CLAUDE.md',archive/'RESULTS_BEFORE_CORRECTION.md')
 bad['status']='NO_PRECONTROL_FOR_FREEZE';save(bad,'stack_window_rejections.csv');ids=set(bad.event_id);groups=set(bad.group)
 f=pd.read_csv(R/'tables/all_estimates.csv');old=f[f.fake&f.window.eq('weekday')&f.group.isin(groups)].copy();old['archive_status']='INVALID_FORWARD_FREEZE_VERSION; not valid robustness evidence';save(old,'PRE_CORRECTION_fake_weekday_estimates.csv')
 e=pd.read_csv(R/'tables/event_tests.csv');save(e[e.fake&e.window.eq('weekday')&e.group.isin(groups)],'PRE_CORRECTION_event_tests.csv')
 for name in ['events.csv','event_date_map.csv','event_date_map_all.csv','freezes.csv']:
  q=pd.read_csv(R/'tables'/name);q=q[~q.event_id.isin(ids)];save(q,name)
 fr=pd.read_csv(R/'tables/freezes.csv',parse_dates=['freeze_date']);n=fr.groupby('freeze_date').size();q=pd.read_csv(R/'tables/exposure_coverage.csv',parse_dates=['freeze_date']);q=q[q.freeze_date.isin(n.index)];q['events']=q.freeze_date.map(n);save(q,'exposure_coverage.csv')
 # In-memory panels remain immutable; the estimator projects them onto active event ids.
 dest=T/'boundary_original_fits';dest.mkdir(exist_ok=True);moved=[]
 for g in groups:
  for m in PRIMARY:
   tag=f'{g}_1_weekday_{m}_0'
   for p in (T/'fits').glob(tag+'*'):
    moved.append(p.name);p.replace(dest/p.name)
 js(R/'meta/precontrol_correction.json',dict(discovered_at=pd.Timestamp.now(tz='UTC'),post_estimation=True,original_main_results_already_observed=True,rejected_ids=sorted(ids),affected_groups=sorted(groups),affected_specification_rows=len(old),main_real_and_joint_changed=False,old_results_table='tables/PRE_CORRECTION_fake_weekday_estimates.csv',moved_checkpoints=moved))
 print('PRECONTROL_CORRECTED',len(bad),'windows',len(old),'specification rows')
if __name__=='__main__':main()
