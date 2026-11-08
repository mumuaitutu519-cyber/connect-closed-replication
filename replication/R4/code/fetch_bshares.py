from common import *
import subprocess,socket
def main():
 inc=pd.read_parquet(Q/'cn_fin_statements/income/full/all.parquet',columns=['symbol','ORG_CODE','report_date','notice_date']);inc['code']=code(inc.symbol);inc.notice_date=pd.to_datetime(inc.notice_date);b=inc[inc.symbol.str.match(r'^(200|900)')].copy();a=inc[inc.code.isin(set(universe().code))].copy();links=a[['code','ORG_CODE']].drop_duplicates().merge(b[['code','ORG_CODE']].drop_duplicates().rename(columns={'code':'b_code'}),on='ORG_CODE');links=links.drop_duplicates(['code','b_code']);save(links,'bshare_issuer_links.csv');pkg=T/'baostock_pkg'
 if not(pkg/'baostock').exists():subprocess.run(['uv','pip','install','--python',sys.executable,'--target',str(pkg),'--no-deps','baostock==0.9.4'],check=True)
 sys.path.insert(0,str(pkg));socket.setdefaulttimeout(8)
 class BoundSocket(socket.socket):
  def recv(self,*args,**kwargs):
   x=super().recv(*args,**kwargs)
   if not x:raise ConnectionError('EOF')
   return x
 socket.socket=BoundSocket
 import baostock as bs,baostock.common.context as context
 rows=[]
 for c in sorted(b.code.unique()):
  dest=R/'meta'/f'basic_{c}.csv'
  if dest.exists():d=pd.read_csv(dest,dtype=str)
  else:
   d=pd.DataFrame()
   try:
    lg=bs.login();assert lg.error_code=='0';rs=bs.query_stock_basic(code=c[-2:].lower()+'.'+c[:6]);data=[]
    while rs.error_code=='0' and rs.next():data.append(rs.get_row_data())
    d=pd.DataFrame(data,columns=rs.fields);d.to_csv(dest,index=False)
   except Exception as e:print('BASIC_FAILED',c,repr(e),flush=True)
   finally:
    try:context.default_socket.close()
    except Exception:pass
  if len(d):
   z=d.iloc[0].to_dict();z['b_code']=c;rows.append(z)
 save(pd.DataFrame(rows) if rows else pd.DataFrame(columns=['b_code','ipoDate','outDate','status']),'bshare_listing_dates.csv');js(R/'meta/bshare_source_status.json',dict(issuer_links=len(links),dated_listing_records=len(rows),status='AVAILABLE' if rows else 'BAOSTOCK_NO_B_SHARE_RECORDS',rule='No listing effective dates means no historical B flag; H listing estimated separately'));print('BASIC COMPLETE',len(rows),len(links),flush=True)
if __name__=='__main__':main()
