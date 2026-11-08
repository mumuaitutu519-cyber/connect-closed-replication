from fetch_literature import query,ROOT
from pathlib import Path
import json,urllib.parse
DOIS=['10.1016/j.frl.2026.110639','10.1016/j.pacfin.2026.103124','10.1016/j.iref.2026.105356','10.1016/j.pacfin.2026.103425','10.2139/ssrn.6260559','10.2139/ssrn.7049101','10.2139/ssrn.7397644','10.3386/w35095','10.1016/j.irfa.2026.105155','10.1016/j.jbankfin.2025.107420','10.1111/irfi.70008','10.1016/j.chieco.2025.102518']
if __name__=='__main__':
 rs=[]
 for i,doi in enumerate(DOIS):
  r=query(f'crossref_final_{i}','https://api.crossref.org/works/'+urllib.parse.quote(doi,safe=''));rs.append(r)
  if r['status']==200:
   a=json.loads(Path(r['path']).read_text())['message'];print(json.dumps(a,ensure_ascii=False))
 p=ROOT/'meta/literature_receipts.json';p.write_text(json.dumps(json.loads(p.read_text())+rs,indent=2))
