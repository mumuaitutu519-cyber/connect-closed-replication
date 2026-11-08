import requests
from pathlib import Path
from bs4 import BeautifulSoup
u='https://www.hko.gov.hk/en/wxinfo/climat/warndb/warndb1.shtml'
r=requests.get(u,timeout=30);Path('sources/hko_warning_form.html').write_text(r.text)
s=BeautifulSoup(r.text,'html.parser')
for t in s.find_all(['form','script']):
 if t.name=='form' or t.get('src'):print(str(t)[:10000])
