from common import *
import requests,re,concurrent.futures as cf
from scipy.stats import t as student_t,binomtest
SRC=R/'sources/hkex_daily';SRC.mkdir(parents=True,exist_ok=True)
CACHE_RECEIPTS={}
if(R/'tables/hkex_fetch_receipts.csv').exists():CACHE_RECEIPTS={str(r['date'])[:10]:r for r in pd.read_csv(R/'tables/hkex_fetch_receipts.csv').to_dict('records')}
def fetch(value):
 d=pd.Timestamp(value);p=SRC/f'{d:%Y%m%d}.js';u=f'https://www.hkex.com.hk/eng/csm/DailyStat/data_tab_daily_{d:%Y%m%d}e.js'
 if p.exists():
  rec=CACHE_RECEIPTS.get(value,dict(date=value,url=u,status=200 if p.read_text().lstrip().startswith('tabData') else 404,bytes=p.stat().st_size));rec['cached']=True;rec['sha256']=hashlib.sha256(p.read_bytes()).hexdigest();return rec
 try:
  r=requests.get(u,timeout=20);p.write_bytes(r.content);return dict(date=value,url=u,status=r.status_code,bytes=len(r.content),cached=False,sha256=hashlib.sha256(r.content).hexdigest())
 except Exception as e:return dict(date=value,url=u,status=str(e),bytes=0)
def main():
 m=pd.read_csv(P/'R3b/tables/event_date_map.csv',parse_dates=['date','anchor','freeze_date']);m=m[m.group.eq('US')&~m.fake&m.window.eq('r1')];dates=sorted(m.date.dt.strftime('%Y-%m-%d').unique());rows=[]
 with cf.ThreadPoolExecutor(max_workers=4)as pool:rows=list(pool.map(fetch,dates))
 save(rows,'hkex_fetch_receipts.csv');d=pd.read_parquet(Q/'cn_hsgt/moneyflow_hsgt/full/all.parquet');d['date']=pd.to_datetime(d.trade_date);d=d.drop_duplicates('date').sort_values('date');save(d[d.date.isin(m.date)].assign(n=1,stocks=np.nan,events=np.nan),'qdc_moneyflow_raw_window.csv')
 print('FETCHED',len(rows),pd.DataFrame(rows).status.value_counts().to_dict(),flush=True)
if __name__=='__main__':main()
