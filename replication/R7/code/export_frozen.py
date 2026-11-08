from common import *
import shutil

def main():
 dest=R/'data/frozen_US_controls.parquet';dest.parent.mkdir(exist_ok=True);writer=None;n=0;codes=set();events=set();columns=['event_id','code','freeze_date','event_start','holding_date','available_date','eligible','dose','qfii','ah',*RACE,*HK,*[c+'__'+v for c in HK for v in ['w01','w005']]]
 ah_history=pd.read_csv(P/'R2/tables/AH_listing_history.csv').drop_duplicates('code').set_index('code')
 for c in ['hk_listing_date','hk_delisting_date']:ah_history[c]=pd.to_datetime(ah_history[c],format='mixed',errors='coerce')
 for p in sorted((T/'feature_blocks').glob('*.parquet')):
  d=pd.read_parquet(p,columns=list(dict.fromkeys(columns)));d=d[d.event_id.ge(1000)&d.event_id.lt(2000)].copy()
  if not len(d):continue
  assert (d.available_date.isna()|d.available_date.lt(d.freeze_date)).all()
  listed=pd.to_datetime(d.code.map(ah_history.hk_listing_date),errors='coerce');delisted=pd.to_datetime(d.code.map(ah_history.hk_delisting_date),errors='coerce');d['ah_at_event_start_R2']=(listed.lt(d.event_start)&(delisted.isna()|delisted.gt(d.event_start))).astype('int8')
  table=pa.Table.from_pandas(d,preserve_index=False)
  if writer is None:writer=pq.ParquetWriter(dest,table.schema,compression='zstd')
  writer.write_table(table);n+=len(d);codes.update(d.code);events.update(d.event_id);del d,table;release()
 if writer:writer.close()
 save([dict(path='data/frozen_US_controls.parquet',sample='58 event freezes × full 5473 stock universe; before daily outcome selection',ah_definition='ah: frozen-date status; ah_at_event_start_R2: original R2 event-start status used by all US no-AH regressions',n=n,stocks=len(codes),events=len(events),bytes=dest.stat().st_size,sha256=hashlib.sha256(dest.read_bytes()).hexdigest())],'frozen_US_controls_manifest.csv')
 for source,target in [('event_complete_case_audit.csv','sample_by_event.csv'),('hold_quintile_balance.csv','balance.csv')]:shutil.copyfile(R/'tables'/source,R/target)
 counts=pd.read_csv(R/'tables/minute_day_receipts.csv');save([dict(source='A-share original minutes',n=int(counts.selected.sum()),stocks=len(universe()),events=46,stock_days=int(counts.stock_days.sum()),calendar_days=len(counts),count_scope='selected minute rows for original main-study calendar')],'data_scale.csv');shutil.copyfile(R/'tables/data_scale.csv',R/'data_scale.csv');print('EXPORTED_FROZEN_US',n,flush=True)
if __name__=='__main__':main()
