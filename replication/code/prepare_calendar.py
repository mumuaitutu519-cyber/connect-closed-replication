import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[k]='1'
from pathlib import Path
import pandas as pd,numpy as np,pdfplumber,json,re,datetime,collections,io
ROOT=Path(__file__).resolve().parents[1]
MON={m:i+1 for i,m in enumerate(['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'])}
def main():
 receipts=json.loads((ROOT/'meta/official_receipts.json').read_text());rr={r['name']:r for r in receipts if r['status']==200}
 dates=[];meta=[]
 for year in range(2017,2027):
  if year<=2020 or year==2023:name=f'calendar_historical_{year}.pdf'
  else:name=next(n for n in rr if str(year) in n and n.endswith('.pdf') and ('Settlement' in n or '(Eng)' in n))
  r=rr[name];p=Path(r['path']);count=0
  with pdfplumber.open(p) as pdf:
   meta.append(dict(year=year,source_url=r['url'],retrieved_utc=r['retrieved_utc'],original_file_creation_timestamp=pdf.metadata.get('CreationDate'),original_file_modification_timestamp=pdf.metadata.get('ModDate'),publication_timestamp=None,publication_timestamp_status='not stated in file; PDF metadata is not publication time',timezone='metadata specifies UTC+08:00',path=str(p)))
   for page in pdf.pages:
    for tab in page.extract_tables():
     month=None;days=None
     for row in tab:
      label=(row[0] or '').strip()
      if label[:3] in MON:
       month=MON[label[:3]];days=[int(re.search(r'\d+',c).group()) if c and re.search(r'\d+',c) else None for c in row[1:]]
      elif 'Northbound Trading' in label and days:
       for day,flag in zip(days,row[1:]):
        if day is None:continue
        flag=(flag or '').strip();flag=''.join(chr(ord(c)-0xf000) if 0xf020<=ord(c)<=0xf07e else c for c in flag).strip()
        if flag not in ['P','O','#']:raise ValueError((year,month,day,flag))
        dates.append(dict(date=f'{year}-{month:02d}-{day:02d}',nb_open=flag.startswith('P') if flag in ['P','O'] else None,nb_original_flag=flag,source_url=r['url'],source_file=name,source_page=page.page_number,official_event_timezone='Asia/Shanghai; UTC+08:00',event_session_start='09:30:00',calendar_asof_type='official archived/revised settlement calendar'))
        count+=1
  if count<250:raise ValueError((year,count,'expected full weekday calendar'))
 f=pd.DataFrame(dates).drop_duplicates('date');f['date']=pd.to_datetime(f.date)
 # Actual A-share dates from the daily data source. Read dates only, in blocks.
 base=Path('/Volumes/Extreme SSD/QDC/data/QDCData/cn_daily_full/full');days=set();scales=[]
 import pyarrow.parquet as pq
 for p in sorted(base.glob('*.parquet')):
  if not p.stem[:4].isdigit() or not 2016<=int(p.stem[:4])<=2026:continue
  pf=pq.ParquetFile(p)
  for b in pf.iter_batches(batch_size=100000,columns=['ts'],use_threads=False):
   t=b.column(0).to_numpy();days.update((t+8*3600000)//86400000)
  scales.append(dict(path=str(p),rows=pf.metadata.num_rows,bytes=p.stat().st_size))
 actual=pd.to_datetime(sorted(days),unit='D');actual=actual[actual<=pd.Timestamp('2026-11-07')]
 freeze=ROOT/'meta/frozen_input_cutoff.json'
 if freeze.exists():actual=actual[actual<=pd.Timestamp(json.loads(freeze.read_text())['last_observed_date'])]
 pd.DataFrame({'date':actual}).to_csv(ROOT/'meta/actual_full_calendar.csv',index=False)
 f['a_open']=f.date.isin(actual)
 f['hk_holiday']=pd.NA;f['sb_open']=pd.NA
 for year in [2023,2024,2025,2026]:
  p=(ROOT/f'meta/official_raw/calendar_trading_{year}.csv') if year<=2024 else next((ROOT/'meta/official_raw').glob(f'*{year}-Calendar_csv_e.csv'))
  if not p.exists():continue
  text=p.read_text(encoding='utf-8-sig');lines=text.splitlines();header=next(i for i,s in enumerate(lines) if s.startswith('Date,'));d=pd.read_csv(io.StringIO('\n'.join(lines[header:]))).fillna('');d=d[d.Date.astype(str).str.match(r'^\d{4}-')];d.Date=pd.to_datetime(d.Date)
  m=d.set_index('Date');ix=f.date.isin(m.index)
  f.loc[ix,'hk_holiday']=f.loc[ix,'date'].map(m['Hong Kong'].eq('Holiday'))
  f.loc[ix,'sb_open']=f.loc[ix,'date'].map(m['Southbound Trading'].ne('Closed'))
  check=f.loc[ix,'date'].map(m['Northbound Trading'].ne('Closed')).to_numpy(bool);known=f.loc[ix,'nb_open'].notna().to_numpy()
  assert np.array_equal(check[known],f.loc[ix,'nb_open'].to_numpy()[known].astype(bool))
  f.loc[ix,'nb_open']=check
  r=next((r for r in rr.values() if r.get('path')==str(p)),None)
  if r:
   f.loc[ix,'source_url']=r['url'];f.loc[ix,'source_file']=p.name;f.loc[ix,'source_page']=np.nan;f.loc[ix,'calendar_asof_type']='official trading CSV cross-checked against settlement PDF'
 f=f[f.date<=actual.max()].sort_values('date').reset_index(drop=True)
 f['closed']=f.a_open&f.nb_open.eq(False)
 a=f[f.a_open].copy();positions={d:i for i,d in enumerate(a.date)};closed=a[a.closed].date.tolist();episodes=[]
 for d in closed:
  if not episodes or positions[d]>positions[episodes[-1][-1]]+1:episodes.append([d])
  else:episodes[-1].append(d)
 events=[];mapping=[]
 for i,ed in enumerate(episodes,1):
  start,end=ed[0],ed[-1];pre=a[(a.date<start)&a.nb_open.eq(True)].tail(5).date.tolist();post=a[(a.date>end)&a.nb_open.eq(True)].head(5).date.tolist();resume=post[0] if post else pd.NaT
  events.append(dict(event_id=i,start=start,end=end,n_closed_days=len(ed),resume=resume,n_pre=len(pre),n_post=len(post),source_url=a.loc[a.date.eq(start),'source_url'].iloc[0]))
  for rank,d in enumerate(pre):mapping.append(dict(event_id=i,date=d,relative=rank-len(pre),role='control_pre',anchor=start,resume=False))
  for rank,d in enumerate(ed):mapping.append(dict(event_id=i,date=d,relative=rank,role='closed',anchor=start,resume=False))
  for rank,d in enumerate(post,1):mapping.append(dict(event_id=i,date=d,relative=rank,role='control_post',anchor=start,resume=d==resume))
 f.to_csv(ROOT/'tables/official_calendar.csv',index=False)
 e=pd.DataFrame(events);e.to_csv(ROOT/'tables/events.csv',index=False)
 m=pd.DataFrame(mapping);m.to_csv(ROOT/'tables/event_date_map_all.csv',index=False)
 # Nearest anchor resolves overlapping event windows without weighting duplicate days.
 m['distance']=(m.date-m.anchor).abs().dt.days;m=m.sort_values(['date','distance','anchor']).drop_duplicates('date')
 m=m.merge(a[['date','closed','nb_open']],on='date',validate='1:1');m.to_csv(ROOT/'tables/event_date_map.csv',index=False)
 pd.DataFrame(meta).to_csv(ROOT/'meta/calendar_provenance.csv',index=False)
 pd.DataFrame(scales).to_csv(ROOT/'meta/daily_source_files.csv',index=False)
 (ROOT/'meta/calendar_status.json').write_text(json.dumps(dict(status='PASS',a_dates=len(a),last_actual_date=str(actual.max().date()),closure_dates=len(closed),independent_episodes=len(episodes),main_window_dates=len(m),years=a.groupby(a.date.dt.year).closed.agg(['sum','size']).to_dict(),southbound_placebo_known_2023_26=int(((f.sb_open==False)&f.nb_open&f.a_open).fillna(False).sum()),unknown_northbound_dates=int(f.nb_open.isna().sum())),indent=2,default=str))
 print((ROOT/'meta/calendar_status.json').read_text())
 # Render a representative original page for visual symbol verification.
 with pdfplumber.open(ROOT/'meta/official_raw/calendar_historical_2017.pdf') as pdf:pdf.pages[1].to_image(resolution=130).save('/Volumes/Extreme SSD/T9/_tmp/266/calendar2017.png')
if __name__=='__main__':main()
