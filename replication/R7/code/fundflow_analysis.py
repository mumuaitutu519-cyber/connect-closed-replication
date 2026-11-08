from common import *
from scipy.stats import t as student_t,binomtest

def main():
 official=[]
 for p in sorted((R/'sources/hkex_daily').glob('*.js')):
  s=p.read_text()
  if not s.strip().startswith('tabData'):continue
  try:arr=json.loads(s[s.index('['):].strip().rstrip(';'))
  except Exception:continue
  z={};rec=dict(date=pd.Timestamp(p.stem))
  for market in arr:
   if 'Northbound'not in market.get('market',''):continue
   tab=market['content'][0]['table'];headers=tab['schema'][0];values=[r['td'][0][0]for r in tab['tr']];stats=dict(zip(headers,values));turn=stats.get('Total Turnover');z[market['market']]=float(turn.replace(',',''))if turn and turn!='-'else np.nan
  if len(z)==2:rec.update(hkex_north_turnover_million=sum(z.values()),markets=json.dumps(z));official.append(rec)
 o=pd.DataFrame(official);save(o.assign(n=1,stocks=np.nan,events=np.nan),'hkex_north_turnover_available.csv')
 q=pd.read_parquet(Q/'cn_hsgt/moneyflow_hsgt/full/all.parquet');q['date']=pd.to_datetime(q.trade_date);q=q.drop_duplicates('date').sort_values('date');q['qdc_netflow_million']=q.north_money.where(q.date.lt('2024-08-19'));q['qdc_turnover_million']=q.north_money.where(q.date.ge('2024-08-19'));cross=q.merge(o,on='date',how='inner');cross['absolute_difference']=abs(cross.qdc_turnover_million-cross.hkex_north_turnover_million);save(cross.assign(n=1,stocks=np.nan,events=np.nan),'qdc_hkex_recent_scale_validation.csv')
 m=pd.read_csv(P/'R3b/tables/event_date_map.csv',parse_dates=['date','anchor']);m=m[m.group.eq('US')&~m.fake&m.window.eq('r1')];raw=m.merge(q[['date','north_money','qdc_netflow_million','qdc_turnover_million']],on='date',how='left',validate='m:1').merge(o.drop(columns='markets'),on='date',how='left',validate='m:1');raw['n']=1;raw['stocks']=np.nan;raw['events']=1;save(raw,'us58_moneyflow_daily_windows.csv');by=[];summary=[]
 for var in ['qdc_netflow_million','qdc_turnover_million','hkex_north_turnover_million']:
  for eid,g in raw.groupby('event_id'):
   treated=g.loc[g.treated.eq(1),var].dropna();control=g.loc[g.treated.eq(0),var].dropna();pre=g.loc[g.treated.eq(0)&g.date.lt(g.anchor),var].dropna();post=g.loc[g.treated.eq(0)&g.date.gt(g.anchor),var].dropna();val=treated.mean()if len(treated)else np.nan;mean=control.mean()if len(control)else np.nan;valid=len(treated)==1 and len(pre)>0 and len(post)>0;by.append(dict(variable=var,event_id=eid,date=g.anchor.iloc[0],holiday=val,normal_mean=mean,pre_mean=pre.mean(),post_mean=post.mean(),difference=val-mean if valid else np.nan,relative_change=val/mean-1 if valid and mean>0 and 'turnover'in var else np.nan,log_difference=np.log(val)-np.log(control).mean()if valid and val>0 and(control>0).all()and'turnover'in var else np.nan,valid_pair=valid,n=len(treated)+len(control),stocks=np.nan,events=1,control_days=len(control)))
 by=pd.DataFrame(by);save(by,'us58_moneyflow_event_comparisons.csv')
 for var,g in by.groupby('variable'):
  z=g[g.valid_pair].copy();vals=z.difference.to_numpy();nn=len(vals);se=np.std(vals,ddof=1)/np.sqrt(nn)if nn>1 else np.nan;mean=np.mean(vals)if nn else np.nan;crit=student_t.ppf(.975,nn-1)if nn>1 else np.nan;nonzero=vals[vals!=0];summary.append(dict(variable=var,registered_holidays=58,valid_holidays=nn,holiday_mean=z.holiday.mean(),normal_mean=z.normal_mean.mean(),difference=mean,ci_low=mean-crit*se,ci_high=mean+crit*se,paired_t_p=2*student_t.sf(abs(mean/se),nn-1)if se>0 else np.nan,sign_p=binomtest(int((nonzero>0).sum()),len(nonzero),.5).pvalue if len(nonzero)else np.nan,mean_relative_change=z.relative_change.mean(),mean_log_difference=z.log_difference.mean(),n=int(z.n.sum()),stocks=np.nan,events=nn,unit='CNY million; daily market series, stock count not applicable'))
 summary=pd.DataFrame(summary)
 for i,r in summary.iterrows():
  z=by[(by.variable==r.variable)&by.valid_pair]
  for field in ['relative_change','log_difference']:
   vals=z[field].dropna().to_numpy();nrel=len(vals);ser=np.std(vals,ddof=1)/np.sqrt(nrel)if nrel>1 else np.nan;mu=np.mean(vals)if nrel else np.nan;crit=student_t.ppf(.975,nrel-1)if nrel>1 else np.nan;summary.loc[i,field+'_ci_low']=mu-crit*ser;summary.loc[i,field+'_ci_high']=mu+crit*ser;summary.loc[i,field+'_t_p']=2*student_t.sf(abs(mu/ser),nrel-1)if ser>0 else np.nan
 save(summary,'us_holiday_turnover_summary.csv');save(q[q.date.between('2024-08-01','2024-08-30')].assign(n=1,stocks=np.nan,events=np.nan),'qdc_field_regime_transition.csv');audit=[]
 for p in (Q/'cn_hk_ccass').glob('*/full/*.parquet'):
  pf=pq.ParquetFile(p);audit.append(dict(path=str(p),rows=pf.metadata.num_rows,fields=pf.schema_arrow.names,participant_identifier_present=any('participant'in c.lower()for c in pf.schema_arrow.names),scope='HK-listed shares; no northbound A-share custodian participant split'))
 js(R/'meta/ccass_source_audit.json',audit);save([dict(specification='ForeignCustodian_vs_ChineseBroker',status='UNAVAILABLE_NORTHBOUND_PARTICIPANT_LEVEL_HISTORICAL_HOLDINGS',n=0,stocks=0,events=0)],'custodian_specification_status.csv');print(pd.DataFrame(summary).to_string(index=False),flush=True)
if __name__=='__main__':main()
