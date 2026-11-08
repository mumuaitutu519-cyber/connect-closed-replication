from common import *
def main():
 rows=[]
 for day in ['20170413','20190513','20200410','20210519','20220630','20240701','20260403']:
  p=T/'daily'/f'{day}.parquet';old=Path('/Volumes/Extreme SSD/T9/_tmp/282/metrics_daily')/p.name
  if not p.exists()or not old.exists():continue
  a=pd.read_parquet(p).set_index('code');b=pd.read_parquet(old).set_index('code');assert set(a.index)==set(b.index);a=a.sort_index();b=b.sort_index();a['if_lag_sum']=a[[f'if_b{k}'for k in range(1,6)]].sum(axis=1,min_count=5)
  for c in ['if_delay','ih_delay','if_lag_sum','amount','valid_minutes','one_price','raw_eligible_day']:
   x=a[c].to_numpy(float);y=b[c].to_numpy(float);mask=np.isfinite(x)&np.isfinite(y);err=max(abs(x[mask]-y[mask]),default=0);nanagree=np.array_equal(np.isnan(x),np.isnan(y));rows.append(dict(date=day,metric=c,n=len(a),stocks=len(a),events=0,abs_error=err,missingness_match=nanagree,status='PASS'if nanagree and err<1e-10 else'FAIL'))
 assert all(x['status']=='PASS'for x in rows)
 if not rows:rows=[dict(date='',metric='',n=0,stocks=0,events=0,abs_error=np.nan,missingness_match=np.nan,status='SKIPPED_NO_OPTIONAL_CACHE')]
 save(pd.DataFrame(rows),'minute_reuse_spot_checks.csv');print('MINUTE_CHECKS',len(rows),flush=True)
if __name__=='__main__':main()
