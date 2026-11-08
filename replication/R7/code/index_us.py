from common import *
import socket,concurrent.futures as cf
sys.path.insert(0,str(T/'baostock_pkg'))

def one(row):
 import baostock as bs
 import baostock.common.context as context
 socket.setdefaulttimeout(8)
 class BoundedSocket(socket.socket):
  def recv(self,*args,**kwargs):
   x=super().recv(*args,**kwargs)
   if not x:raise ConnectionError('EOF from historical source')
   return x
 socket.socket=BoundedSocket
 eid,freeze=row;outdir=R/'sources/us_members';outdir.mkdir(parents=True,exist_ok=True);full=pd.DatetimeIndex(pd.read_csv(P/'meta/actual_full_calendar.csv',parse_dates=['date']).date);day=full[full.searchsorted(freeze)-1];un=pd.read_parquet(T/'universe.parquet');d=un[['code']].copy();d['event_id']=eid;audit=[]
 for kind,api,expected in [('csi300','query_hs300_stocks',300),('sse50','query_sz50_stocks',50),('csi500','query_zz500_stocks',500)]:
  dest=outdir/f'{eid}_{kind}.csv';g=pd.DataFrame()
  if dest.exists()and dest.stat().st_size>20:g=pd.read_csv(dest,dtype=str)
  else:
   for attempt in range(2):
    try:
     lg=bs.login();assert lg.error_code=='0',lg.error_msg;rs=getattr(bs,api)(date=str(day.date()));r=[]
     while rs.error_code=='0'and rs.next():r.append(rs.get_row_data())
     g=pd.DataFrame(r,columns=rs.fields)
    except Exception as e:print('INDEX_RETRY',eid,kind,str(e),flush=True)
    finally:
     try:getattr(context,'default_socket').close()
     except Exception:pass
    if len(g):break
   g.to_csv(dest,index=False)
  status='OK'
  if not len(g):status='NO_HISTORICAL_SOURCE'
  elif len(g)!=expected:status='UNEXPECTED_INDEX_COUNT'
  elif pd.to_datetime(g.updateDate).ge(freeze).any():status='INVALID_ASOF'
  if status=='OK':
   codes=g.code.str[3:]+'.'+g.code.str[:2].str.upper();future=codes.map(un.set_index('code').first_observed_daily).gt(day)
   if future.any():status='FIRST_DAILY_DATE_AFTER_INDEX_ASOF'
  if status=='OK':
   codes=g.code.str[3:]+'.'+g.code.str[:2].str.upper();d[kind]=d.code.isin(codes).astype(float)
  else:d[kind]=np.nan
  audit.append(dict(event_id=eid,variable=kind,date=day,freeze=freeze,n=len(g),stocks=len(g),events=1,status=status))
 return d,audit

def main():
 fr=pd.read_csv(P/'R3b/tables/event_date_map.csv',parse_dates=['freeze_date']);fr=fr[fr.group.eq('US')&~fr.fake&fr.window.eq('r1')][['event_id','freeze_date']].drop_duplicates();fr.event_id+=1000;out=[];audit=[]
 with cf.ProcessPoolExecutor(max_workers=4)as pool:
  for d,a in pool.map(one,list(fr.itertuples(index=False,name=None))):out.append(d);audit+=a;print('INDEX',d.event_id.iloc[0],flush=True)
 pd.concat(out,ignore_index=True).to_parquet(T/'us_index.parquet',index=False);save(audit,'us_index_source_status.csv')
if __name__=='__main__':main()
