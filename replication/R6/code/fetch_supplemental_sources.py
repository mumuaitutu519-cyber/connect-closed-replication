from common import *
import requests,hashlib
from concurrent.futures import ThreadPoolExecutor
urls={
'new_regime_announcement.html':'https://www.hkex.com.hk/News/Market-Communications/2024/240618news?sc_lang=en',
'20250922_SWT_reminder.pdf':'https://www.hkex.com.hk/-/media/HKEX-Market/Services/Circulars-and-Notices/Participant-and-Members-Circulars/SEHK/2025/ce_SEHK_CT_132_2025.pdf',
'2025Q3_SFC_operations.pdf':'https://www.sfc.hk/-/media/EN/files/COM/QR-Reports/202507-09/0_Quarterly-Report-JulSep-2025_E.pdf?rev=a6a3051128ad4fd1b598f24a33a618d3'}
def get(j):
 n,u=j;p=R/'sources'/n
 if not p.exists():
  q=requests.get(u,timeout=40)
  if q.status_code==403 and n=='2025Q3_SFC_operations.pdf' and (R/'sources/SFC_2025Q3_web_evidence.json').exists():return dict(name=n,url=u,status='DIRECT_PDF_403_OFFICIAL_SEARCH_EXTRACTION_ARCHIVED',evidence_note='sources/SFC_2025Q3_web_evidence.json')
  q.raise_for_status();p.write_bytes(q.content)
 return dict(name=n,url=u,bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
if __name__=='__main__':
 rows=list(ThreadPoolExecutor(4).map(get,urls.items()));(R/'meta/supplemental_source_receipts.json').write_text(json.dumps(rows,indent=2))
