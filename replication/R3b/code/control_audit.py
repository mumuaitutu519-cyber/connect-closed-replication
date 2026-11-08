from common import *

def main():
 m=pd.read_csv(R/'tables/event_date_map.csv',parse_dates=['date']);out=[];extra=[('UK_funeral',pd.Timestamp('2022-09-19')),('UK_coronation',pd.Timestamp('2023-05-08'))]
 for y in range(2017,2027):
  d=pd.Timestamp(y,11,11);d+=pd.Timedelta(days=-1 if d.dayofweek==5 else 1 if d.dayofweek==6 else 0);extra.append(('US_Veterans',d))
 for name,date in extra:
  q=m[m.date.eq(date)&m.treated.eq(0)]
  for key,g in q.groupby(['group','fake','window']):out.append(dict(holiday=name,date=date,group=key[0],fake=key[1],window=key[2],control_event_rows=len(g),scope='nominal registered calendar; not stock-day weighted',registration_status='not included in prespecified treatment list; retained as control',source_url='https://www.gov.uk/bank-holidays' if name.startswith('UK') else 'https://www.opm.gov/policy-data-oversight/pay-leave/federal-holidays/'))
 save(pd.DataFrame(out),'unregistered_holiday_control_audit.csv')
if __name__=='__main__':main()
