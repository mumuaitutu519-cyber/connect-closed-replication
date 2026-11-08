import requests,pandas as pd
from pathlib import Path
u='https://www.hko.gov.hk/dps/wxinfo/climat/warndb/rstorm.dat'
p=Path('sources/rstorm.dat');p.write_bytes(requests.get(u,timeout=40).content)
tc=pd.DataFrame([x.split('\t')[:16] for x in Path('sources/tc.dat').read_text(encoding='utf-8-sig').splitlines()])
tc[8]=pd.to_numeric(tc[8])
print(tc[tc[8].between(2017,2026)&tc[3].astype(str).isin(['8','9','10'])].to_string(index=False,header=False))
print('RAINFORMAT',p.read_text()[-2000:])
