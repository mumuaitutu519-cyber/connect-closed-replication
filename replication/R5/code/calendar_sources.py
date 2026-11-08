from common import *
import exchange_calendars as xc,holidays,requests
from dateutil.easter import easter
URLS={'NYSE':'https://www.nyse.com/trade/hours-calendars','LSE':'https://www.londonstockexchange.com/equities-trading/business-days','Xetra':'https://www.eurexgroup.com/xetra-en/newsroom/trading-calendar','Euronext':'https://www.euronext.com/en/trading/trading-hours-holidays','SGX_cash':'https://www.sgx.com/securities/trading','SGX_A50':'https://www.sgx.com/derivatives/trading','calendar_code':'https://github.com/gerrymanoim/exchange_calendars','SGX_2017_appendix':'https://www.emega.com.tw/emega/upload/bulletin/157fb4018bf000008950.pdf','SGX_2026_circular':'https://api2.sgx.com/sites/default/files/2025-12/DTAM%20109%20of%202025%20-%20SGX-DT%20Derivatives%20Trading%20Holiday%20Schedule%20for%20Year%202026.pdf'}
def main():
 m=pd.read_csv(P/'tables/event_date_map.csv',parse_dates=['date']);ev=pd.read_csv(P/'tables/events.csv',parse_dates=['start','end','resume']);dates=m.loc[m.closed,'date'];c=m[m.closed][['event_id','date']].copy();hk=holidays.HK(years=range(2017,2027),language='en_US',categories=['public','optional']);cal={k:xc.get_calendar(v,start='2017-01-01',end='2026-12-31')for k,v in [('NYSE','XNYS'),('LSE','XLON'),('Xetra','XETR'),('Euronext','XPAR'),('SGX_cash','XSES'),('HK','XHKG')]}
 for k,v in cal.items():
  c[k+'_open']=c.date.isin(v.sessions);c[k+'_half']=c.date.isin(v.early_closes)
 c['HK_holiday']=c.date.map(lambda d:hk.get(d.date(),''));c['foreign_any_closed']=~c[[k+'_open'for k in ['NYSE','LSE','Xetra','Euronext']]].all(axis=1);c['foreign_all_closed']=~c[[k+'_open'for k in ['NYSE','LSE','Xetra','Euronext']]].any(axis=1);c['foreign_any_half']=c[[k+'_half'for k in ['NYSE','LSE','Xetra','Euronext']]].any(axis=1)
 # Product-specific A50 holiday confirmations are supplied in a separate official-source extract.
 af=R/'meta/sgx_a50_confirmed.csv'
 if af.exists():
  a=pd.read_csv(af,parse_dates=['date']);c=c.merge(a,on='date',how='left',validate='1:1')
 else:c['SGX_A50_open']=np.nan;c['SGX_A50_source']='UNVERIFIED_PRODUCT_SPECIFIC_HISTORY'
 c['hkonly_date']=~c.foreign_any_closed&~c.foreign_any_half;c['hk_actual_only_date']=c.hkonly_date&~c.HK_open
 rows=[]
 for eid,g in c.groupby('event_id'):
  hs='; '.join(sorted(set(g.HK_holiday)-{''}));start=ev.set_index('event_id').loc[eid,'start'];ee=pd.Timestamp(easter(start.year));near=(abs((start-ee).days)<=7)
  if near:typ='耶稣受难/复活节'
  elif 'Buddha'in hs:typ='佛诞'
  elif 'Mid-Autumn'in hs:typ='中秋翌日'
  elif 'Christmas'in hs or(start.month==12 and start.day>=20):typ='圣诞/节礼日'
  else:typ='其他'
  only=bool(g.hkonly_date.all());group='欧美全部照常'if only else'至少一欧美市场休市或半日';rows.append(dict(event_id=eid,hkonly=int(only),foreign_group=group,strict_all_west_closed=int(g.foreign_all_closed.all()),classified_closed_days=len(g),n_foreign_any_closed=int(g.foreign_any_closed.sum()),n_foreign_all_closed=int(g.foreign_all_closed.sum()),n_foreign_half=int(g.foreign_any_half.sum()),n_HK_cash_closed=int((~g.HK_open).sum()),holiday_type=typ,HK_holidays=hs))
 eg=ev.merge(pd.DataFrame(rows),on='event_id');save(c,'F_calendar_by_closed_day.csv');save(eg,'F_event_classification.csv');receipts=[]
 for k,u in URLS.items():
  try:
   r=requests.get(u,timeout=20);p=R/'meta'/f'calendar_{k}.html';p.write_bytes(r.content);receipts.append(dict(name=k,url=u,status=r.status_code,sha256=hashlib.sha256(r.content).hexdigest(),bytes=len(r.content)))
  except Exception as ex:receipts.append(dict(name=k,url=u,status=str(ex)))
 js(R/'meta/calendar_sources.json',dict(exchange_calendars=xc.__version__,holidays=holidays.__version__,sources=receipts,EU_definition='Xetra and Euronext Paris; not all euro-area exchanges',SGX_limitation='cash and A50 derivative calendars are distinct; never fill A50 from cash holidays'))
 print(eg.groupby(['foreign_group','holiday_type']).size().to_string(),flush=True)
if __name__=='__main__':main()
