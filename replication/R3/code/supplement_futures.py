"""Observed CFFEX ticks => minute returns; actual-contract prior-day volume selection.
Synthetic 8888/9998/9999 series are never eligible. Preserve old minute values.
"""
from common import *
import re,subprocess,shutil,concurrent.futures as cf,threading
ARC=Path('/Volumes/T9/FutureTickV3/2026-自然日/202609.7z');S=T/'futures_supplement';RAW=S/'raw';OUT=S/'contract_minutes'

def contract_file(task):
 member,date,contract,method=task;p=RAW/member;parts=[]
 for b in pd.read_csv(p,usecols=['CalendarDate','UpdateTime','UpdateMillisec','LastPrice','Volume'],chunksize=100000):
  z=b.UpdateTime.str.split(':',expand=True).astype(int);b['ms']=z[0]*3600000+z[1]*60000+z[2]*1000+pd.to_numeric(b.UpdateMillisec);assert b.CalendarDate.eq(int(date)).all(),str(p);parts.append(b[['ms','LastPrice','Volume']])
 d=pd.concat(parts,ignore_index=True).sort_values('ms',kind='stable');d['dv']=d.Volume.diff().fillna(d.Volume);volume=float(d.Volume.max());d=d[d.LastPrice.gt(0)&d.LastPrice.lt(1e8)&d.Volume.gt(0)].copy();left=method.split('_')[0]=='left';opmode=method.split('_',1)[1];cl=np.full(240,np.nan);op=np.full(240,np.nan)
 for start,end,off in [(34200000,41400000,0),(46800000,54000000,120)]:
  v=d[d.ms.ge(start)&d.ms.lt(end)].copy()if left else d[d.ms.gt(start)&d.ms.le(end)].copy();v['slot']=((v.ms-start)//60000 if left else np.ceil((v.ms-start)/60000).astype(int)-1)+off
  if len(v):
   first=v.groupby('slot',sort=True).first();last=v.groupby('slot',sort=True).last();ix=last.index.to_numpy(int);cl[ix]=last.LastPrice.to_numpy(float);op[ix]=first.LastPrice.to_numpy(float)
   if opmode=='newtrade':
    firsttrade=v[v.dv.gt(0)].groupby('slot').first()
    if off in firsttrade.index:op[off]=firsttrade.loc[off,'LastPrice']
   elif opmode=='auction'and off==0:
    auction=d[d.ms.lt(start)&d.ms.ge(33900000)]
    if len(auction):op[0]=auction.LastPrice.iloc[-1]
 with np.errstate(divide='ignore',invalid='ignore'):
  r=np.log(cl/np.r_[np.nan,cl[:-1]]);r[0]=np.log(cl[0]/op[0]);r[120]=np.log(cl[120]/op[120])
 return dict(date=date,contract=contract,product=contract[:2],volume=volume,returns=r,valid=int(np.isfinite(r).sum()),first_price=op[0],afternoon_first=op[120])

def calibration():
 allchoices=pd.read_csv(R/'tables/futures_contract_selection.csv');reports=[]
 for day in ['2026-08-31','2026-09-01']:
  choices=allchoices[allchoices.date.eq(day)].set_index('product');ds=day.replace('-','')
  for method in ['left_first','right_first','left_newtrade','right_newtrade','left_auction','right_auction']:
   for prod in ['IF','IH']:
    code=choices.loc[prod,'contract'];x=contract_file((f'{ds[:6]}/{ds}/{code}.csv',ds,code,method))
    with np.load(T/f'futures_{prod}.npz')as z:i=np.flatnonzero(pd.to_datetime(z['dates'],unit='D')==pd.Timestamp(day))[0];old=z['returns'][i]
    good=np.isfinite(old)&np.isfinite(x['returns']);diff=old[good]-x['returns'][good];reports.append(dict(date=day,method=method,product=prod,n=int(good.sum()),rmse=float(np.sqrt(np.mean(diff**2))),max_abs=float(abs(diff).max()),corr=float(np.corrcoef(old[good],x['returns'][good])[0,1]),first_diff=float(old[0]-x['returns'][0]),afternoon_diff=float(old[120]-x['returns'][120])))
 df=pd.DataFrame(reports);save(df,'futures_tick_calibration.csv');print(df.to_string(index=False));return df

def extract_sources():
 RAW.mkdir(parents=True,exist_ok=True);entries=json.loads((R/'meta/futures_tick_selected_members.json').read_text());lst=S/'members.txt';lst.write_text('\n'.join(x['member']for x in entries)+'\n')
 if not all((RAW/x['member']).exists()and (RAW/x['member']).stat().st_size==x['size']for x in entries):
  with (R/'logs/futures_sep_extract.log').open('w')as f:subprocess.run(['7zz','x','-y','-bd','-mmt=1',f'-o{RAW}',str(ARC),f'@{lst}'],stdout=f,stderr=f,check=True)
 aug=ARC.with_name('202608.7z');probes=[f'202608/20260831/{p}2609.csv'for p in ['IF','IH']]
 if not all((RAW/p).exists()for p in probes):
  with (R/'logs/futures_aug_probe_extract.log').open('w')as f:subprocess.run(['7zz','x','-y','-bd','-mmt=1',f'-o{RAW}',str(aug),*probes],stdout=f,stderr=f,check=True)
 return entries

def main():
 S.mkdir(exist_ok=True);marker=S/'complete.json'
 if marker.exists():
  valid=True
  for prod in ['IF','IH']:
   with np.load(T/f'futures_{prod}.npz')as z:valid&=pd.to_datetime(z['dates'],unit='D').max()>=pd.Timestamp('2026-09-30')
  if valid:print('TICK SUPPLEMENT ALREADY PRESENT',flush=True);return
 entries=extract_sources();calib=calibration();chosen=calib[calib.method.eq('left_auction')];assert chosen.n.eq(240).all();assert chosen['corr'].ge(.995).all()and chosen.rmse.le(5e-5).all()and chosen.max_abs.le(3e-4).all(),chosen.to_dict('records')
 tasks=[(e['member'],e['date'],e['contract'],'left_auction')for e in entries];rows=[];stop=threading.Event();threading.Thread(target=watch,args=(stop,),daemon=True).start()
 try:
  with cf.ProcessPoolExecutor(max_workers=4)as pool:
   for z in pool.map(contract_file,tasks,chunksize=1):rows.append(z)
 finally:stop.set()
 scalar=pd.DataFrame([{k:v for k,v in z.items()if k!='returns'}for z in rows]);scalar['date']=pd.to_datetime(scalar.date,format='%Y%m%d');save(scalar,'futures_tick_daily_contract_volume.csv');lookup={(pd.Timestamp(z['date']),z['contract']):z for z in rows};calendar=pd.read_csv(R/'tables/official_calendar.csv',parse_dates=['date']);ad=pd.DatetimeIndex(calendar.loc[calendar.a_open,'date'].sort_values());days=ad[(ad>pd.Timestamp('2026-09-01'))&(ad<=pd.Timestamp('2026-09-30'))];choices=[];coverage=[]
 for prod in ['IF','IH']:
  path=T/f'futures_{prod}.npz'
  with np.load(path)as z:old_dates=z['dates'].copy();old_ret=z['returns'].copy()
  keep=pd.to_datetime(old_dates,unit='D')<=pd.Timestamp('2026-09-01');old_dates=old_dates[keep];old_ret=old_ret[keep];new_dates=[];new_ret=[]
  for day in days:
   previous=ad[ad.get_loc(day)-1];v=scalar[scalar['product'].eq(prod)&scalar.date.eq(previous)&scalar.volume.gt(0)].sort_values(['volume','contract'],ascending=[False,True]);ret=np.full(240,np.nan);status='NO_PRIOR_TRADING_DAY_VOLUME';contract=None;prior_volume=np.nan
   if len(v):
    contract=v.contract.iloc[0];prior_volume=v.volume.iloc[0];record=lookup.get((day,contract));status='SELECTED_CONTRACT_NOT_OBSERVED'
    if record is not None:ret=record['returns'];status='OBSERVED'
   assert previous<day;choices.append(dict(product=prod,date=day,selection_date=previous,contract=contract,prior_day_volume=prior_volume,status=status,source='FutureTickV3 actual contracts; previous A/CFFEX trading-day cumulative volume max'));new_dates.append(np.datetime64(day.date(),'D').astype('int64'));new_ret.append(ret)
  dates=np.r_[old_dates,np.asarray(new_dates,dtype='int64')];ret=np.vstack([old_ret,*new_ret]);assert np.array_equal(ret[:len(old_ret)],old_ret,equal_nan=True);assert len(np.unique(dates))==len(dates);tmp=path.with_suffix('.atomic.tmp')
  with tmp.open('wb')as f:np.savez_compressed(f,dates=dates,returns=ret)
  tmp.replace(path);n=np.isfinite(ret).sum(1);dt=pd.to_datetime(dates,unit='D');coverage.append(dict(product=prod,dates=len(dates),usable_dates=int((n>=180).sum()),date_min=str(dt.min().date()),date_max=str(dt.max().date()),last_valid_date=str(dt[n>=180].max().date()),new_tick_days=len(new_dates),prefix_through_20260901_unchanged=True))
 save(pd.DataFrame(choices),'futures_tick_contract_selection.csv');save(pd.DataFrame(coverage),'futures_coverage_augmented.csv')
 original=R/'tables/futures_coverage.csv'
 if original.exists():shutil.copyfile(original,R/'tables/futures_coverage_original.csv')
 save(pd.DataFrame(coverage),'futures_coverage.csv');selections=pd.read_csv(R/'tables/futures_contract_selection.csv');selections=selections[selections.date.le('2026-09-01')];extra=pd.DataFrame(choices);extra['date']=extra.date.dt.strftime('%Y-%m-%d');extra['selection_date']=extra.selection_date.dt.strftime('%Y-%m-%d');save(pd.concat([selections,extra],ignore_index=True),'futures_contract_selection.csv')
 js(marker,dict(status='OK',method='left-closed minute bins; first minute opens at observed opening-auction last price; afternoon resets at first quote',coverage=coverage));js(R/'meta/futures_tick_supplement_validation.json',dict(status='PASS',archive=str(ARC),bytes=ARC.stat().st_size,mtime_ns=ARC.stat().st_mtime_ns,actual_contract_files=len(entries),synthetic_series_excluded=True,method='left_auction',calibration=chosen.to_dict('records'),coverage=coverage,original_minute_prefix_unchanged=True,limitation='Observed tick LastPrice sampling; IF holdout max return discrepancy up to about 2.18bp; October still unavailable.'))
 shutil.rmtree(RAW);print('TICK SUPPLEMENT COMPLETE',coverage,flush=True)

if __name__=='__main__':
 if len(sys.argv)>1 and sys.argv[1]=='calibrate':calibration()
 else:main()
