from common import *
def main():
 m=pd.read_csv(P/'tables/event_date_map.csv',parse_dates=['date']);ev=pd.read_csv(P/'tables/events.csv',parse_dates=['start','resume']);cal=pd.read_csv(P/'tables/official_calendar.csv',parse_dates=['date']);a=pd.DatetimeIndex(cal.loc[cal.a_open,'date']);normal=set(cal.loc[cal.a_open&cal.nb_open,'date']);existing=set(m.date);rows=[];audit=[];used=set()
 for e in ev.itertuples():
  pos=a.get_loc(e.resume)+5;dt=a[pos]if pos<len(a)else pd.NaT;status='KEEP'
  if pd.isna(dt):status='OUTSIDE_CALENDAR'
  elif dt not in normal:status='NOT_NORMAL_NB_OPEN'
  elif dt in existing:status='ORIGINAL_DATE_OWNER_PRESERVED'
  elif dt in used:status='EXTENSION_DATE_ALREADY_ASSIGNED'
  if status=='KEEP':
   used.add(dt);rows.append(dict(event_id=e.event_id,date=dt,relative=99,role='control_post',resume=False,closed=False))
  audit.append(dict(event_id=e.event_id,date=dt,status=status,n=int(status=='KEEP'),stocks=0,events=1))
 m['original_sample']=True;extra=pd.DataFrame(rows);extra['original_sample']=False;save(pd.concat([m,extra],ignore_index=True),'H_extended_date_map.csv');save(pd.DataFrame(audit),'H_extension_support.csv')
if __name__=='__main__':main()
