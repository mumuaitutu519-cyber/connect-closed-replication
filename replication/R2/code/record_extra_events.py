from pathlib import Path
import requests,pandas as pd,datetime,hashlib,json
R=Path(__file__).resolve().parents[1]
CANDIDATES=[('2019-07-31','https://www.hkex.com.hk/News/Market-Communications/2019/190731news?sc_lang=en','HK_also_halted_part_day; not full-day HK-open NB-only suspension'),('2023-09-08','https://www.hkex.com.hk/News/Market-Communications/2023/2309083news?sc_lang=en','HK_also_closed_full_day; excluded from HK-open identification'),('2024-09-06','https://www.hkex.com.hk/news/market-communications/2024/2409062news?sc_lang=zh-hk','HK_also_closed_full_day; excluded from HK-open identification')]
def main():
 rows=[]
 for date,url,reason in CANDIDATES:
  p=R/'meta'/('HKEX_extra_'+date+'.html')
  if p.exists():body=p.read_bytes();status='FROZEN_LOCAL'
  else:
   r=requests.get(url,timeout=20);body=r.content;p.write_bytes(body);status=r.status_code
  rows.append(dict(date=date,url=url,retrieved_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),status=status,sha256=hashlib.sha256(body).hexdigest(),qualifies=False,reason=reason))
 pd.DataFrame(rows).to_csv(R/'tables/extra_suspension_candidates.csv',index=False)
 (R/'meta/extra_event_search.json').write_text(json.dumps(dict(query=['site:hkex.com.hk Northbound Trading technical issue suspended','site:hkex.com.hk Northbound suspension system 2018','site:hkex.com.hk Northbound trading typhoon'],qualifying_verified_events=0,status='NO_VERIFIED_QUALIFYING_EVENT; not a proof of absence',R1_calendar_unchanged=True),indent=2))
if __name__=='__main__':main()
