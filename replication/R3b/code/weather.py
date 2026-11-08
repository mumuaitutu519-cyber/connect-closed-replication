from common import *
import requests,concurrent.futures as cf,re
DATES=['2017-05-24','2017-08-23','2018-09-17','2019-07-31','2020-08-19','2020-10-13','2021-06-28','2021-10-08','2021-10-13','2022-08-25','2022-11-02','2023-07-17','2023-09-01','2023-09-08','2023-10-09','2024-09-06']
def fetch(d):
 t=pd.Timestamp(d);url=f'https://www.hkex.com.hk/News/Market-Communications/{t.year}/{t:%y%m%d}news?sc_lang=en';p=R/'meta'/f'weather_{d}.html'
 if p.exists():body=p.read_bytes();status=200
 else:
  r=requests.get(url,timeout=25);body=r.content;status=r.status_code;p.write_bytes(body)
 s=body.decode('utf-8',errors='replace');head=re.findall(r'<(?:h1|h2)[^>]*>(.*?)</(?:h1|h2)>',s,re.S);head=[re.sub('<[^>]+>','',x).strip() for x in head];status=200 if head else 404;strip=re.sub('<[^>]+>',' ',s);strip=re.sub(r'\s+',' ',strip);i=strip.find('Market Operations');snippet=strip[i:i+5000] if i>=0 else strip[-10000:];return dict(date=d,url=url,status=status,title=' / '.join(head),sha256=hashlib.sha256(body).hexdigest(),extract=snippet,exclude_from_full_day=bool(status==200 and re.search(r'Delay|Terminated|Suspended|Trading Arrangements', ' / '.join(head),re.I)))
if __name__=='__main__':
 with cf.ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(fetch,DATES))
 save(pd.DataFrame(rows),'HKEX_nonfull_day_audit.csv');print(pd.DataFrame(rows)[['date','status','title']].to_string(index=False))
