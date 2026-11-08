from common import *
from inference import bh,rw

def consolidate():
 files=sorted((T/'fits').glob('*.csv'));files=[p for p in files if not any(p.stem.endswith(s) for s in ['_ri','_sample','_event','_event_detail','_dist'])];rows=[];bb=[]
 for p in files:
  f=pd.read_csv(p);rows.append(f)
  with np.load(p.with_name(p.stem+'_boot.npz')) as z:bb.extend(z['boot'])
 f=pd.concat(rows,ignore_index=True);assert len(bb)==len(f);f['q_bh']=np.nan;f['p_romano_wolf']=np.nan;f['q_bh_wild']=np.nan;f['q_bh_ri']=np.nan
 for key,ix in f.groupby(['group','fake','window','joint','variant','exposure','term']).groups.items():
  rr=f.loc[ix].to_dict('records');f.loc[ix,'q_bh']=bh(f.loc[ix,'p']);f.loc[ix,'q_bh_wild']=bh(f.loc[ix,'wild_p']);f.loc[ix,'q_bh_ri']=bh(f.loc[ix,'ri_p']);f.loc[ix,'p_romano_wolf']=rw(rr,[bb[i] for i in ix])
 f['q_bh_all_main_w01']=np.nan;f['p_rw_all_main_w01']=np.nan;ix=f.index[~f.fake&~f.joint&f.variant.eq('w01')&f.exposure.eq('dose')&f.term.eq('treated_x')];f.loc[ix,'q_bh_all_main_w01']=bh(f.loc[ix,'p']);f.loc[ix,'p_rw_all_main_w01']=rw(f.loc[ix].to_dict('records'),[bb[i] for i in ix]);save(f,'all_estimates.csv');save(f[~f.joint&~f.fake],'main_estimates.csv');save(f[f.fake],'fake_week_estimates.csv');save(f[f.joint],'joint_estimates.csv');save(f[['group','fake','window','joint','metric','variant','exposure','term','status','n','ri_status','ri_B']],'specification_status.csv')
 for suffix,name in [('_ri','randomization_support.csv'),('_event','event_tests.csv'),('_event_detail','event_day_details.csv'),('_sample','sample_by_event_metric.csv'),('_dist','distributions.csv')]:
  chunks=[]
  for p in sorted((T/'fits').glob(f'*{suffix}.csv')):
   try:chunks.append(pd.read_csv(p))
   except pd.errors.EmptyDataError:pass
  if chunks:save(pd.concat(chunks,ignore_index=True).drop_duplicates(),name)
 # Original benchmark and placebo records are exact copies with provenance and old seeds retained.
 r1=pd.read_csv(P/'tables/main_estimates.csv');r1=r1[r1.metric.isin(PRIMARY)];r1['source']='R1';r1['seed']=20261110;r2=pd.read_csv(P/'R2/tables/main_estimates.csv');r2=r2[r2.metric.isin(PRIMARY)&r2.specification.eq('baseline')&r2.term.eq('closed_x')];r2['source']='R2';r2['seed']=20261111;save(pd.concat([r1,r2],ignore_index=True),'R1_R2_original_benchmarks.csv')
 import shutil
 shutil.copy2(P/'tables/placebo_estimates.csv',R/'tables/R1_placebo_estimates.csv');shutil.copy2(P/'tables/placebo_event_dates.csv',R/'tables/R1_placebo_event_dates.csv')
 s=pd.read_csv(R/'tables/sample_by_event_metric.csv');ev=pd.read_csv(R/'tables/events.csv');summ=s[~s.joint].groupby(['event_id','metric'],as_index=False).agg(stock_days=('rows','sum'),treated_stock_days=('rows',lambda x:0))
 s=s[~s.joint].pivot_table(index=['event_id','metric'],columns='treated',values=['rows','stocks','dates'],aggfunc='sum').reset_index();s.columns=['event_id','metric']+['%s_%s'%x for x in s.columns[2:]];s=ev.merge(s,on='event_id',how='left');s.to_csv(R/'sample_by_event.csv',index=False)
 print('CONSOLIDATED',len(f),'rows',flush=True)
if __name__=='__main__':consolidate()
