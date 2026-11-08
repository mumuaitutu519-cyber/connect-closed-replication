"""Historical index/industry source, dated before each event, frozen as raw CSV."""
from pathlib import Path
import sys,socket,json,hashlib,datetime,subprocess,time,concurrent.futures as cf,os
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[key]='1'
R=Path(__file__).resolve().parents[1];T=Path('/Volumes/Extreme SSD/T9/_tmp/272');OUT=R/'meta/historical_members';OUT.mkdir(exist_ok=True)
def main(part=None):
 if (OUT/'COMPLETE.json').exists():print('FROZEN historical membership snapshots retained');return
 if part is None:
  import pandas as pd
  with cf.ProcessPoolExecutor(max_workers=4)as pool:list(pool.map(main,range(4)))
  rows=pd.concat([pd.read_csv(R/f'tables/historical_membership_receipts_part{i}.csv')for i in range(4)],ignore_index=True);rows.to_csv(R/'tables/historical_membership_receipts.csv',index=False)
  (OUT/'COMPLETE.json').write_text(json.dumps(dict(records=len(rows),source='BaoStock date-specific historical member/CSRC industry tables',completed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()),indent=2));return
 pkg=T/'baostock_pkg'
 if not (pkg/'baostock').exists():subprocess.run(['uv','pip','install','--python',sys.executable,'--target',str(pkg),'--no-deps','baostock==0.9.4'],check=True)
 sys.path.insert(0,str(pkg));socket.setdefaulttimeout(8)
 class BoundedSocket(socket.socket):
  def recv(self,*args,**kwargs):
   data=super().recv(*args,**kwargs)
   if not data:raise ConnectionError('EOF from historical source')
   return data
 socket.socket=BoundedSocket
 import baostock as bs,pandas as pd
 import baostock.common.context as context
 ex=pd.read_parquet(T/'exposures.parquet',columns=['event_id','freeze_date']).drop_duplicates();full=pd.DatetimeIndex(pd.read_csv(R/'meta/actual_full_calendar.csv',parse_dates=['date']).date);univ=pd.read_csv(R/'meta/stock_universe.csv',parse_dates=['first_observed_daily']).set_index('code');rows=[]
 # New connection per query prevents a failed packet from poisoning later requests.
 for ev in ex.itertuples():
  if (ev.event_id-1)%4!=part:continue
  date=full[full.searchsorted(ev.freeze_date)-1];day=str(date.date())
  for kind,api,expected in [('csi300','query_hs300_stocks',300),('sse50','query_sz50_stocks',50),('csi500','query_zz500_stocks',500),('industry','query_stock_industry',None)]:
   dest=OUT/f'{ev.event_id:02d}_{kind}.csv'
   if dest.exists()and dest.stat().st_size>20:d=pd.read_csv(dest,dtype=str)
   else:
    d=pd.DataFrame()
    for attempt in range(2):
     try:
      lg=bs.login();assert lg.error_code=='0',lg.error_msg
      rs=getattr(bs,api)(date=day);r=[]
      while rs.error_code=='0'and rs.next():r.append(rs.get_row_data())
      d=pd.DataFrame(r,columns=rs.fields)
     except Exception as e:print('SOURCE_RETRY',ev.event_id,kind,attempt,repr(e),flush=True)
     finally:
      try:getattr(context,'default_socket').close()
      except Exception:pass
     if len(d):break
    d.to_csv(dest,index=False)
   status='OK';future=0
   if not len(d):status='EMPTY_HISTORICAL_SOURCE'
   else:
    dt=pd.to_datetime(d.updateDate,errors='coerce')
    if dt.isna().any()or(dt>=ev.freeze_date).any():status='INVALID_ASOF'
    code=d.code.str[3:]+'.'+d.code.str[:2].str.upper();first=code.map(univ.first_observed_daily);future=int(first.gt(date).sum())
    # Nonempty industry/index assignment to future IPOs would reveal a current roster masquerading as historical.
    if kind=='industry':future=int((first.gt(date)&d.industry.notna()&d.industry.ne('')).sum())
    if future and kind!='industry':status='FIRST_DAILY_DATE_AFTER_INDEX_ASOF'
    if expected is not None and len(d)!=expected:status='UNEXPECTED_INDEX_COUNT'
   rows.append(dict(event_id=ev.event_id,kind=kind,requested_date=day,freeze_date=str(ev.freeze_date.date()),rows=len(d),first_daily_date_after_snapshot=future,status=status,source='BaoStock '+api,documentation='http://baostock.com/baostock/index.php/Python_API文档',file=str(dest.relative_to(R)),sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),retrieved_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
  pd.DataFrame(rows).to_csv(R/f'tables/historical_membership_receipts_part{part}.csv',index=False);print('HISTORY',ev.event_id,day,[r['status']for r in rows[-4:]],flush=True)
 print('SOURCE_PART_COMPLETE',part,flush=True)
if __name__=='__main__':main()
