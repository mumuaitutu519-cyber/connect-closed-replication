from common import *
import shutil
import finalize
RR=T/'smoke/root';TT=T/'smoke/tmp'
for p in [RR/'logs/days',RR/'meta']:p.mkdir(parents=True,exist_ok=True)
if not(RR/'code').exists():(RR/'code').symlink_to(R/'code',target_is_directory=True)
for p in (R/'logs/days').glob('*.json'):shutil.copyfile(p,RR/'logs/days'/p.name)
shutil.copyfile(R/'logs/resources.jsonl',RR/'logs/resources.jsonl')
for name in ['download_plan.csv','control_window_audit.csv']:shutil.copyfile(R/'tables'/name,RR/'tables'/name)
for name in ['inference_validation.json','native_reference_validation.json']:shutil.copyfile(R/'meta'/name,RR/'meta'/name)
x=pd.concat([pd.read_csv(p)for p in (RR/'tables/estimates').glob('*.csv')],ignore_index=True)
for c in ['beta','se','p','wild_p','event_wild_p','q_bh_main15','q_bh_wild_main15','reason']:
 if c not in x:x[c]=np.nan
x.to_csv(RR/'tables/all_estimates.csv',index=False);main=x[x.variant.eq('raw')&~x.term.str.startswith('individual')];main.to_csv(RR/'tables/main_family.csv',index=False)
finalize.R=RR;finalize.T=TT;finalize.save=lambda d,name:d.to_csv(RR/'tables'/name,index=False,na_rep='NA');finalize.main();assert (RR/'RESULTS_FOR_CLAUDE.md').stat().st_size>1000;js(R/'meta/finalizer_smoke_validation.json',dict(status='PASS',note='Only isolated fixture; no fixture report delivered as results.'));print('FINALIZER SMOKE PASS')
