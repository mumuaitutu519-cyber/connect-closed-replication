from common import *
def main():
 f=features();cons=pd.read_parquet(Q/'cn_index_cons/full/all.parquet');cons.trade_date=pd.to_datetime(cons.trade_date);cons.component_code=cons.component_code.astype(str).str.zfill(6);rows=[]
 for ev,g in f.groupby('event_id'):
  freeze=g.freeze_date.iloc[0];dd=g[['event_id','code']].copy()
  for name,code in [('weight300','000300'),('weight50','000016')]:
   sub=cons[cons.index_code.eq(code)&cons.trade_date.lt(freeze)];dd[name]=np.nan;dd[name+'_asof']=pd.NaT
   if len(sub):
    dt=sub.trade_date.max();q=sub[sub.trade_date.eq(dt)];assert not q.component_code.duplicated().any();by=dict(zip(q.component_code,q.weight));dd[name]=dd.code.str[:6].map(by).fillna(0);dd[name+'_asof']=dt
  rows.append(dd)
 out=pd.concat(rows,ignore_index=True);out.to_parquet(T/'weights.parquet',index=False);save(out.groupby('event_id').agg(n=('code','size'),stocks=('code','nunique'),weight300_known=('weight300','count'),weight50_known=('weight50','count'),weight300_asof=('weight300_asof','first'),weight50_asof=('weight50_asof','first')).reset_index().assign(events=1),'I_weight_coverage.csv')
 audit=[]
 for path in (Q/'cn_hsgt').rglob('*.parquet'):
  pf=pq.ParquetFile(path);audit.append(dict(source=str(path),rows=pf.metadata.num_rows,schema=str(pf.schema_arrow),has_individual_turnover=all(c in pf.schema_arrow.names for c in ['ts_code','buy','sell'])))
 js(R/'meta/northbound_turnover_source_audit.json',audit)
 save(pd.DataFrame([dict(specification='northbound_turnover_dose_race',status='UNAVAILABLE_INDIVIDUAL_PRE_EVENT_TURNOVER',n=0,stocks=0,events=0,reason='Local cn_hsgt contains aggregate money flow and holdings only; absent stocks in top10-active lists cannot be set to zero; no complete usable individual turnover history recovered.')]),'I_turnover_dose_status.csv')
if __name__=='__main__':main()
