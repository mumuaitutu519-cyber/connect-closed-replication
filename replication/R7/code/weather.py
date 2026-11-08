from common import *
import shutil,subprocess,concurrent.futures as cf,multiprocessing as mp

def seed_daily(job):
 source,dest=map(Path,job);dest.parent.mkdir(exist_ok=True)
 if dest.exists():return
 columns=['code','date','valid_minutes','one_price','amount','eligible_day','if_lag_sum','if_delay','ih_delay']
 pd.read_parquet(source,columns=columns).to_parquet(dest,index=False,compression='zstd')
 shutil.copyfile(source.with_suffix('.json'),dest.with_suffix('.json'))

def setup():
 root=T/'weather_root';work=T/'weather';root.mkdir(exist_ok=True);work.mkdir(exist_ok=True)
 for d in ['code/r1','tables','meta','logs','data']:(root/d).mkdir(parents=True,exist_ok=True)
 for f in ['common.py','build_daily.py','build_panels.py','inference.py']:
  s=(P/'R6/code'/f).read_text()
  if f=='common.py':s=s.replace('P=R.parent;',f'P=Path({str(P)!r});').replace("T=Path('/Volumes/Extreme SSD/T9/_tmp/285')",f'T=Path({str(work)!r})')
  if f=='build_daily.py':
   # All full-day weather windows extend through 2024; half-day history stops
   # at the original 2023-10-09 segment endpoint. Reuse validated R7 daily
   # outcomes while rebuilding every historical half-hour from raw minutes.
   s=s.replace("if not (T/'daily'/f'{d.replace(\"-\",\"\")}.json').exists()", "if not (T/'daily'/f'{d.replace(\"-\",\"\")}.json').exists() or (d<='2023-10-09' and not (T/'segments'/f'{d.replace(\"-\",\"\")}.parquet').exists())")
   s=s.replace("d.to_parquet(p,index=False,compression='zstd');rows=len(d)", "\n if p.exists():\n  previous=pd.read_parquet(p,columns=['code','eligible_day','if_delay','ih_delay']).set_index('code').sort_index();current=d.set_index('code').sort_index();assert previous.index.equals(current.index);assert previous.eligible_day.equals(current.eligible_day);assert np.allclose(previous[['if_delay','ih_delay']],current[['if_delay','ih_delay']],equal_nan=True,atol=1e-10,rtol=0);del previous,current\n else:d.to_parquet(p,index=False,compression='zstd')\n rows=len(d)")
  (root/'code'/f).write_text(s)
 for f in ['estimate.py','build_metrics.py']:
  source=(P/'code'/f).read_text().replace("TMP=Path('/Volumes/Extreme SSD/T9/_tmp/266')",f'TMP=Path({str(work)!r})');(root/'code/r1'/f).write_text(source)
 for f in ['events.csv','event_map.csv']:shutil.copyfile(P/'R6/tables'/f,root/'tables'/f)
 shutil.copyfile(P/'R6/typhoon_calendar.csv',root/'typhoon_calendar.csv')
 e=pd.read_csv(P/'R6/tables/exposure_window_freeze_by_event.csv',parse_dates=['freeze_date','anchor','holding_date','available_date','first_observed_daily']);base=pd.read_csv(P/'tables/exposure_by_event.csv',parse_dates=['freeze_date','anchor','holding_date','available_date','first_observed_daily']);pd.concat([base,e],ignore_index=True).drop_duplicates(['event_id','code']).to_parquet(work/'exposures.parquet',index=False)
 for p in ['IF','IH']:shutil.copyfile(T/f'futures_{p}.npz',work/f'futures_{p}.npz')
 (work/'audits').mkdir(exist_ok=True);pool=pd.read_csv(P/'R6/tables/pooled_winsor_thresholds.csv')
 for key,g in pool.groupby(['kind','metric','segment']):g.to_csv(work/'audits'/f'pooled_{key[0]}_{key[1]}_{key[2]}.csv',index=False)
 (work/'daily').mkdir(exist_ok=True)
 cal=pd.read_csv(P/'tables/official_calendar.csv',parse_dates=['date']);days=cal.loc[cal.a_open&cal.date.le('2026-09-01'),'date']
 jobs=[(str(T/'daily'/f'{d:%Y%m%d}.parquet'),str(work/'daily'/f'{d:%Y%m%d}.parquet'))for d in days]
 with cf.ProcessPoolExecutor(max_workers=4,mp_context=mp.get_context('spawn'))as executor:list(executor.map(seed_daily,jobs,chunksize=4))
 return root,work

def main():
 root,work=setup()
 for script,args in [('build_daily.py',[]),('build_panels.py',['pack']),('build_panels.py',['panel'])]:
  subprocess.run([sys.executable,str(root/'code'/script),*args],check=True)
 shutil.copyfile(R/'code/weather_estimate_template.py',root/'code/r7_estimate.py');subprocess.run([sys.executable,str(root/'code/r7_estimate.py')],check=True);print('WEATHER_BUILT',flush=True)
if __name__=='__main__':main()
