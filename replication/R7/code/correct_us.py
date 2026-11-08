from common import *
import supplement,design,concurrent.futures as cf,multiprocessing as mp

def block(b):
 path=T/'panel'/f'{b:03d}.parquet';f=pd.read_parquet(path);feat=pd.read_parquet(T/'feature_blocks'/path.name,columns=['event_id','code','family','analyst','qfii']);feat=feat[feat.family.eq('US')].set_index(['event_id','code']);mask=f.family.eq('US');ix=pd.MultiIndex.from_frame(f.loc[mask,['event_id','code']]);old=f.loc[~mask,['event_id','code','analyst','qfii']].copy()
 for c in ['analyst','qfii']:f.loc[mask,c]=feat[c].reindex(ix).to_numpy()
 assert f.loc[~mask,['event_id','code','analyst','qfii']].equals(old)
 temp=path.with_suffix('.partial');f.to_parquet(temp,index=False,compression='zstd');temp.replace(path);release();return b

def main():
 supplement.static();old=pd.read_csv(P/'R4/tables/frozen_features_by_event.csv',usecols=['event_id','code','analyst','qfii']);old=old[old.event_id.isin([1,23,45])];checks=[]
 for c in ['analyst','qfii']:
  new=pd.read_parquet(T/f'us_{c}.parquet');new=new[new.event_id.isin([1,23,45])];d=old[['event_id','code',c]].merge(new[['event_id','code',c]],on=['event_id','code'],how='left',validate='1:1',suffixes=('_old','_new'))
  for eid,g in d.groupby('event_id'):
   ok=g[c+'_old'].notna()&g[c+'_new'].notna();err=abs(g.loc[ok,c+'_old']-g.loc[ok,c+'_new']).max();missing_equal=g[c+'_old'].isna().equals(g[c+'_new'].isna());checks.append(dict(event_id=eid,variable=c,max_abs_error=err,missing_mask_equal=missing_equal,n=len(g),stocks=g.code.nunique(),events=1,status='PASS'if missing_equal and(err<1e-10 or not ok.any())else'FAIL'))
 save(checks,'US_static_controls_original_rule_validation.csv');assert all(r['status']=='PASS'for r in checks),checks
 design.allfeatures();supplement.combine()
 import panel
 panel.partition_features();release();jobs=range(int(np.ceil(len(universe())/50)))
 with cf.ProcessPoolExecutor(max_workers=4,mp_context=mp.get_context('spawn'))as pool:
  for b in pool.map(block,jobs):
   if b%20==0:print('US_PANEL_FIXED',b,flush=True)
 js(R/'meta/US_code_normalization_fixed.json',dict(status='PASS',source_validation_events=[1,23,45],only_US_fields_modified=['analyst','qfii'],utc=pd.Timestamp.now(tz='UTC').isoformat()))
if __name__=='__main__':main()
