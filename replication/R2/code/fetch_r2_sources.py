"""Frozen public AH pair map and HK listing dates; bounded HK-minute probes."""
from pathlib import Path
import requests,json,hashlib,datetime,pandas as pd,numpy as np,re
from html.parser import HTMLParser
R=Path(__file__).resolve().parents[1];M=R/'meta';receipts=[]
def get(name,url,params=None):
 p=M/name
 if p.exists():body=p.read_bytes();status='FROZEN_LOCAL'
 else:
  r=requests.get(url,params=params,timeout=20);body=r.content;p.write_bytes(body);status=r.status_code
 receipts.append(dict(file=name,url=url,parameters=params,status=status,bytes=len(body),sha256=hashlib.sha256(body).hexdigest(),retrieved_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
 return body

def main():
 raw=json.loads(get('em_ah_pairs.json','https://push2.eastmoney.com/api/qt/clist/get',dict(pn=1,pz=500,po=1,np=1,fltt=2,invt=2,fid='f191',fs='b:MK0101',fields='f12,f13,f14,f191,f192,f193,f194')))
 pairs=raw['data']['diff'];print('PAIRS',len(pairs),'TOTAL',raw['data']['total'],flush=True)
 # Endpoint caps pages at 100; retain all pages before pairing.
 if len(pairs)<raw['data']['total']:
  for i in range(2,1+int(np.ceil(raw['data']['total']/len(pairs)))):
   q=json.loads(get(f'em_ah_pairs_{i}.json','https://push2.eastmoney.com/api/qt/clist/get',dict(pn=i,pz=100,po=1,np=1,fltt=2,invt=2,fid='f191',fs='b:MK0101',fields='f12,f13,f14,f191,f192,f193,f194')));pairs+=q['data']['diff']
 profiles=[]
 for i in range(1,8):
  name='emlist_ah_raw.txt' if i==1 else f'em_hk_listing_{i}.json'
  raw=json.loads(get(name,'https://datacenter.eastmoney.com/securities/api/data/v1/get',dict(reportName='RPT_HKF10_INFO_SECURITYINFO',columns='ALL',pageSize=500,pageNumber=i,source='F10',client='PC')))
  profiles+=raw['result']['data']
 profiles=pd.DataFrame(profiles).drop_duplicates('SECURITY_CODE').set_index('SECURITY_CODE')
 a=pd.DataFrame(pairs).drop_duplicates('f191');a=a.rename(columns={'f191':'a_code','f12':'hk_code','f193':'a_name','f14':'hk_name'})
 a['code']=a.a_code.astype(str).str.zfill(6)+np.where(a.a_code.astype(str).str.startswith('6'),'.SH','.SZ');a['hk_listing_date']=a.hk_code.map(profiles.LISTING_DATE);a['pair_source']='https://push2.eastmoney.com/api/qt/clist/get?fs=b:MK0101';a['listing_source']='https://datacenter.eastmoney.com/securities/api/data/v1/get?reportName=RPT_HKF10_INFO_SECURITYINFO';a['mapping_status']='current_public_AH_map_historical_listing_date'
 # Historical name in old public A+H roster; A delisting during sample must not be classified non-AH.
 old=get('qz_ah_raw.txt','https://stock.qianzhan.com/hs/trade/hssc07.html').decode('utf-8')
 oldcodes=set(re.findall(r'gongsixinxi_(\d{6}\.(?:SH|SZ))',old));missing=oldcodes-set(a.code)
 pd.DataFrame({'code':sorted(missing)}).to_csv(R/'tables/AH_historical_roster_unmatched.csv',index=False)
 # Known historical A+H Northeastern Electric: retained in Qianzhan roster and CSRC official H-share list.
 if '000585.SZ' not in set(a.code):
  b=dict(code='000585.SZ',a_code='000585',hk_code='00042',a_name='东北电气',hk_name='东北电气',hk_listing_date='1995-07-06',pair_source='https://stock.qianzhan.com/hs/trade/hssc07.html',listing_source='https://www.csrc.gov.cn/csrc_en/c102054/c1371739/content.shtml',mapping_status='historical_delisted_A_in_public_roster')
  a=pd.concat([a,pd.DataFrame([b])],ignore_index=True)
 a=pd.concat([a,pd.DataFrame([dict(code='600806.SH',hk_code='00300',a_name='昆明机床',hk_name='昆明机床',hk_listing_date='1993-12-07',hk_delisting_date='2019-08-26',pair_source='https://www1.hkexnews.hk/listedco/listconews/sehk/2010/0413/ltn20100413195_c.pdf',listing_source='https://www.csrc.gov.cn/csrc_en/c102054/c1371739/content.shtml',mapping_status='historical_AH_delisted_2019')])],ignore_index=True).drop_duplicates('code');a.to_csv(R/'tables/AH_listing_history.csv',index=False)
 additions=M/'AH_historical_additions.csv'
 if additions.exists():a=pd.concat([a,pd.read_csv(additions,dtype={'code':str,'hk_code':str})],ignore_index=True).drop_duplicates('code');a.to_csv(R/'tables/AH_listing_history.csv',index=False)
 # Public minute probes of historical dates; no daily or ETF fallback.
 probes=[]
 for asset,symbol in [('HSI','100.HSI'),('HSCEI','100.HSCEI')]:
  for day in ['20170403','20230404']:
   u='https://push2his.eastmoney.com/api/qt/stock/kline/get';params=dict(secid=symbol,fields1='f1,f2,f3,f4,f5,f6',fields2='f51,f52,f53,f54,f55,f56,f57',klt=1,fqt=0,beg=day,end=day,lmt=100000)
   try:
    z=json.loads(get(f'HK_{asset}_{day}.json',u,params));bars=(z.get('data')or{}).get('klines')or[];bars=[s for s in bars if s.startswith(day[:4]+'-'+day[4:6]+'-'+day[6:])];probes.append(dict(asset=asset,date=day,minute_rows=len(bars),status='AVAILABLE'if bars else'NO_HISTORICAL_MINUTES'))
   except Exception as e:probes.append(dict(asset=asset,date=day,minute_rows=0,status=repr(e)))
 pd.DataFrame(probes).to_csv(R/'tables/HK_minute_availability.csv',index=False)
 (M/'r2_public_receipts.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2))
 print('AH',len(a),'unknown_dates',a.hk_listing_date.isna().sum(),'historical_unmatched',sorted(missing),flush=True)
if __name__=='__main__':main()
