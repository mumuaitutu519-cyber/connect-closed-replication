from common import *
import re
TC='https://www.hko.gov.hk/dps/wxinfo/climat/warndb/tc.dat';RAIN='https://www.hko.gov.hk/dps/wxinfo/climat/warndb/rstorm.dat'
RULE='https://www.hkex.com.hk/-/media/HKEX-Market/Services/Rules-and-Forms-and-Fees/Rules/SEHK/Securities/Rule-Update_Rules-of-the-Exchange/105-16-SEHK-Shenzhen-HK-Stock-Connect_e_markup.pdf'
# Exact dates/periods from archived same-day HKEX notices; no outcomes used.
CONFIG=[('2017-08-23','full',570,900,'1708232news','',None),('2019-07-31','partial_close',835,900,'190731news','',None),('2020-08-19','partial_resume',570,810,'200819news','2008192news',810),('2020-10-13','full',570,900,'2010132news','',None),('2021-06-28','partial_resume',570,810,'2106282news','2106283news',810),('2022-08-25','partial_resume',570,780,'220825news','2208252news',775),('2022-11-02','partial_close',835,900,'221102news','',None),('2023-07-17','full',570,900,'2307172news','',None),('2023-09-01','full',570,900,'2309012news','',None),('2023-09-08','full',570,900,'2309083news','',None),('2023-10-09','partial_resume',570,840,'231009news','2310092news',840),('2024-09-06','full',570,900,'2409062news','',None)]
def url(n):return f'https://www.hkex.com.hk/News/Market-Communications/20{n[:2]}/{n}?sc_lang=en'
def main():
 sig=[]
 for line in (R/'sources/tc.dat').read_text(encoding='utf-8-sig').splitlines():
  a=line.split('\t')
  if len(a)<16:continue
  try:
   start=pd.Timestamp(year=int(a[8]),month=int(a[7]),day=int(a[6]))+pd.Timedelta(hours=int(a[5])//100,minutes=int(a[5])%100);end=pd.Timestamp(year=int(a[13]),month=int(a[12]),day=int(a[11]))+pd.Timedelta(hours=int(a[10])//100,minutes=int(a[10])%100);level=int(a[3])
  except ValueError:continue
  if end<pd.Timestamp('2016-12-05') or start>pd.Timestamp('2026-10-30 23:59'):continue
  sig.append(dict(storm=a[2],kind='typhoon',signal=level,start=start,end=end,url=TC))
 for line in (R/'sources/rstorm.dat').read_text(encoding='utf-8-sig').splitlines():
  a=line.split('\t')
  if len(a)<11 or a[0]!='B':continue
  start=pd.Timestamp(*map(int,a[1:6]));end=pd.Timestamp(*map(int,a[6:11]))
  if end<pd.Timestamp('2016-12-05') or start>pd.Timestamp('2026-10-30 23:59'):continue
  sig.append(dict(storm='BLACK_RAIN',kind='black_rain',signal=0,start=start,end=end,url=RAIN))
 signals=pd.DataFrame(sig).sort_values('start');save(signals,R/'meta/hko_signals.csv');danger=signals[signals.signal.ge(8)|signals.kind.eq('black_rain')]
 cal=loadcal().set_index('date');adates=pd.read_csv(P/'meta/actual_full_calendar.csv',parse_dates=['date']).date
 forecast=pd.read_csv(R/'meta/forecast_bulletins.csv',parse_dates=['timestamp']) if (R/'meta/forecast_bulletins.csv').exists() else pd.DataFrame(columns=['timestamp','text','url'])
 rows=[]
 for day in pd.date_range('2016-12-05','2026-10-30'):
  w=danger[danger.start.lt(day+pd.Timedelta(days=1))&danger.end.gt(day)];aopen=day in set(adates);scheduled=bool(cal.loc[day,'nb_open']) if day in cal.index else False
  rows.append(dict(date=day,a_open=aopen,nb_scheduled_open=scheduled,severe_signal_day=len(w)>0,warning_intervals='; '.join(f'{r.kind}:{r.signal}:{r.start}--{r.end}' for r in w.itertuples()),signal_start=w.start.min(),signal_end=w.end.max(),storm=';'.join(w.storm.unique()),hko_urls=';'.join(w.url.unique()),closure_type='none',nb_closed_start_minute=np.nan,nb_closed_end_minute=np.nan,nb_service_resume_minute=np.nan,hk_resume_minute=np.nan,source_urls='',verification_status='NO_QUALIFYING_SIGNAL',included=False,placebo=False,anticipation='not_applicable',prior_A_close_T3_or_higher=False,prior_A_close_forecast8=pd.NA,forecast8_first_time=pd.NaT,forecast8_url='',expectation_note=''))
 out=pd.DataFrame(rows).set_index('date')
 for day in out.index[out.severe_signal_day]:
  out.loc[day,'verification_status']='A_MARKET_CLOSED' if not out.loc[day,'a_open'] else ('SCHEDULED_NB_CLOSED' if not out.loc[day,'nb_scheduled_open'] else 'NO_A_SESSION_INTERRUPTION')
 for date,kind,start,end,notice,resume,service in CONFIG:
  day=pd.Timestamp(date);assert out.loc[day,'a_open'] and out.loc[day,'nb_scheduled_open'];assert (R/'sources'/f'{notice}.txt').exists()
  urls=[url(notice)]+([url(resume)] if resume else []);status='SAME_DAY_EXPLICIT_STOCK_CONNECT_NOTICE'
  if date=='2022-08-25':status='SAME_DAY_NB_DELAY_NOTICE_PLUS_ARCHIVED_RULE_14B03_5';urls.append(RULE)
  out.loc[day,['closure_type','nb_closed_start_minute','nb_closed_end_minute','nb_service_resume_minute','hk_resume_minute','source_urls','verification_status','included']]=[kind,start,end,service if service else np.nan,(780 if date=='2022-08-25' else service) if service else np.nan,';'.join(urls),status,True]
 # Explicit weather-without-interruption checks and scheduled closure.
 for date,n in [('2017-05-24','170524news'),('2021-10-13','2110132news')]:out.loc[pd.Timestamp(date),'source_urls']=url(n)
 out.loc[pd.Timestamp('2021-10-08'),'source_urls']=RULE;out.loc[pd.Timestamp('2021-10-08'),'verification_status']='BLACK_RAIN_AFTER_OPEN_NORMAL_SERVICE_BY_RULE'
 # New-regime placebo needs T8 overlapping A trading, not just a post-close signal.
 for day in out.index[(out.index>=pd.Timestamp('2024-09-23'))&out.a_open&out.nb_scheduled_open]:
  w=danger[danger.signal.ge(8)&danger.start.lt(day+pd.Timedelta(hours=15))&danger.end.gt(day+pd.Timedelta(hours=9,minutes=30))]
  if not len(w):continue
  out.loc[day,['closure_type','placebo','verification_status','source_urls']]=['open_weather_placebo',True,'HKO_TIMES_PLUS_SWT_OFFICIAL_AND_REGULATOR_CONFIRMATION','https://www.hkex.com.hk/News/Market-Communications/2024/240618news?sc_lang=en;'+(url('2411142news') if day.year==2024 else 'https://www.hkex.com.hk/-/media/HKEX-Market/Services/Circulars-and-Notices/Participant-and-Members-Circulars/SEHK/2025/ce_SEHK_CT_132_2025.pdf;https://www.sfc.hk/-/media/EN/files/COM/QR-Reports/202507-09/0_Quarterly-Report-JulSep-2025_E.pdf?rev=a6a3051128ad4fd1b598f24a33a618d3')]
 for day in out.index[out.included|out.placebo]:
  prev=adates[adates<day].max();pc=prev+pd.Timedelta(hours=15);prior3=signals[(signals.kind=='typhoon')&signals.signal.ge(3)&signals.start.le(pc)&signals.end.gt(pc)]
  out.loc[day,'prior_A_close_T3_or_higher']=bool(len(prior3))
  storm=out.loc[day,'storm'];ws=signals[(signals.signal.ge(8)|signals.kind.eq('black_rain'))&signals.storm.isin(storm.split(';'))&signals.start.lt(day+pd.Timedelta(days=1))&signals.start.ge(day-pd.Timedelta(days=14))]
  first=ws.start.min();fu=';'.join(ws.url.unique());pred=[]
  if len(forecast):
   for f in forecast[(forecast.timestamp>=prev)&(forecast.timestamp<day+pd.Timedelta(hours=16))].itertuples():
    txt=str(f.text).upper()
    if (storm!='BLACK_RAIN') and any(n in txt.replace('-','') for n in storm.upper().replace('-','').split(';') if n!='BLACK_RAIN'):
     # Explicit planned issuance, not a conditional safety recommendation or cancelled T8.
     if re.search(r'(?:WILL|WOULD|IS EXPECTED TO|CONSIDER).*?(?:ISSU|RAIS).*?(?:NO\.?\s*8|NUMBER\s*8)',txt) or re.search(r'(?:NO\.?\s*8|NUMBER\s*8).*?(?:WILL BE ISSUED|EXPECTED TO BE ISSUED)',txt):pred.append((f.timestamp,f.url))
  if pred:
   ptime,pu=min(pred)
   if ptime<first:first,fu=ptime,pu
  out.loc[day,'forecast8_first_time']=first;out.loc[day,'forecast8_url']=fu
  # Signals already issued before midnight prove prior-night knowledge; forecasts extend this when archived.
  if first<day:group='prior_night_known'
  elif len(forecast) and ('BLACK_RAIN' in storm or bool(len(forecast[(forecast.timestamp>=prev)&(forecast.timestamp<day)]))):group='morning_determined'
  else:group='unknown'
  out.loc[day,'anticipation']=group;out.loc[day,'prior_A_close_forecast8']=(bool(len(prior3)) and any(t<=pc for t,u in pred)) if (len(pred) or not len(prior3)) else pd.NA
  if len(prior3) and prior3.signal.ge(8).any():out.loc[day,'prior_A_close_forecast8']=True
  out.loc[day,'expectation_note']='Prior-night group uses earliest retrieved explicit T8 plan or already-issued T8/black warning; absence evidence bounded to archived bulletins fetched, not proof traders had no forecasts.'
 out=out.reset_index();save(out,R/'typhoon_calendar.csv');save(out[out.severe_signal_day|out.included|out.placebo],R/'tables/calendar_candidates.csv')
 status=dict(gate='PASS',full_days=int((out.included&out.closure_type.eq('full')).sum()),partial_days=int((out.included&out.closure_type.str.startswith('partial')).sum()),placebo_days=int(out.placebo.sum()),candidate_signal_days=int(out.severe_signal_day.sum()),expectation_unknown=int(out.loc[out.included,'anticipation'].eq('unknown').sum()),no_outcomes_used=True)
 (R/'meta/calendar_gate.json').write_text(json.dumps(status,indent=2));print(status)
 print(out.loc[out.included|out.placebo,['date','storm','closure_type','anticipation','forecast8_first_time','prior_A_close_forecast8']].to_string(index=False))
if __name__=='__main__':main()
