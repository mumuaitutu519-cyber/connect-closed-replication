from common import *
import hashlib,zipfile

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 critical=[P/'meta/stock_universe.csv',P/'meta/actual_full_calendar.csv',P/'meta/eligibility_events.csv',P/'tables/official_calendar.csv',P/'tables/exposure_by_event.csv',P/'tables/pooled_winsor_thresholds.csv',P/'tables/main_estimates.csv',Q/'cn_hsgt/hk_hold/full/all.parquet',Q/'cn_st/full/all.parquet'];rows=[]
 for p in critical:rows.append(dict(path=str(p),bytes=p.stat().st_size,sha256=digest(p)))
 archives=[];raw=Path('/Volumes/Extreme SSD/T9/codex项目/A股分钟线+日频量价/A股分钟数据/1m_price_zip')
 for year in range(2017,2027):
  p=raw/f'{year}.zip'
  with zipfile.ZipFile(p) as z:entries=[dict(member=x.filename,bytes=x.file_size,crc32=x.CRC) for x in z.infolist() if x.filename.endswith('.parquet')]
  archives.append(dict(path=str(p),bytes=p.stat().st_size,mtime_ns=p.stat().st_mtime_ns,member_CRC_manifest_sha256=hashlib.sha256(json.dumps(entries,sort_keys=True).encode()).hexdigest(),members=len(entries)))
 receipt=dict(critical_inputs=rows,minute_archives=archives,futures_archive='/Volumes/T9/期货1分钟2004~2608/CFFEX.7z',full_hash_not_claimed_for_large_archives=True,upstream_frozen_manifest=str(P/'meta/input_manifest.json'),upstream_manifest_sha256=digest(P/'meta/input_manifest.json'))
 (R/'meta/input_manifest.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print('Read-only input provenance recorded')
if __name__=='__main__':main()
