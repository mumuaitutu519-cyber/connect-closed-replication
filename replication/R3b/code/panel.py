from common import *
import concurrent.futures as cf,pyarrow.dataset as ds,multiprocessing as mp
LIMIT=None
def init(lim):
 global LIMIT
 LIMIT=lim
def safe_pooled(metric):
 with LIMIT:
  answer=pooled(metric);release();return answer

def pack(y):
 out=T/'history';out.mkdir(exist_ok=True);un=pd.read_csv(R/'meta/stock_universe.csv',parse_dates=['first_observed_daily']).set_index('code');full=pd.DatetimeIndex(pd.read_csv(R/'meta/actual_full_calendar.csv',parse_dates=['date']).date);cal=pd.read_csv(R/'tables/official_calendar.csv',parse_dates=['date']).set_index('date');st=pd.read_parquet(Q/'cn_st/full/all.parquet');frames=[]
 for p in sorted((T/'metrics_daily').glob(f'{y}*.parquet')):
  f=pd.read_parquet(p);f['age']=full.searchsorted(f.date)-full.searchsorted(f.code.map(un.first_observed_daily))+1;f['st']=False
  # ST table is small. Interval conditions precisely match original R1.
  for r in st.itertuples():
   if pd.Timestamp(r.st_start)>f.date.iloc[0] or (pd.notna(r.st_end) and pd.Timestamp(r.st_end)<f.date.iloc[0]):continue
   f.loc[f.code.eq(r.ts_code),'st']=True
  f['eligible_day']=f.raw_eligible_day&f.age.ge(60)&~f.st;f['nb_open']=f.date.map(cal.nb_open).fillna(False).astype(bool);frames.append(f[['code','date','eligible_day','nb_open',*PRIMARY]])
 if not frames:return
 f=pd.concat(frames,ignore_index=True);codes=sorted(un.index);block={c:i//50 for i,c in enumerate(codes)};f['block']=f.code.map(block)
 for b,g in f.groupby('block'):g.drop(columns='block').to_parquet(out/f'{y}_{b:03d}.parquet',index=False,compression='zstd')
 print('PACK',y,len(f),flush=True)

def pooled(metric):
 d=ds.dataset(T/'history',format='parquet').to_table(columns=['date',metric],filter=ds.field('eligible_day')&ds.field('nb_open'),use_threads=False).to_pandas();d=d[np.isfinite(d[metric])].sort_values('date');dates=d.date.to_numpy();v=d[metric].to_numpy();out=[];fr=pd.read_csv(R/'tables/freezes.csv',parse_dates=['freeze_date'])
 for freeze in sorted(fr.freeze_date.unique()):
  i=np.searchsorted(dates,freeze);q=np.quantile(v[:i],[.005,.01,.99,.995]) if i else np.full(4,np.nan);out.append(dict(freeze_date=freeze,metric=metric,n=i,q005=q[0],q01=q[1],q99=q[2],q995=q[3]))
 return out

def block(b):
 files=sorted((T/'history').glob(f'*_{b:03d}.parquet'))
 if not files:return
 f=pd.concat([pd.read_parquet(p) for p in files],ignore_index=True).sort_values(['code','date']).reset_index(drop=True);assert not f.duplicated(['code','date']).any();m=pd.read_csv(R/'tables/event_date_map.csv',parse_dates=['date','freeze_date','anchor']);orig=pd.read_csv(R/'tables/closure_date_map.csv',parse_dates=['date','freeze_date','anchor']);m=pd.concat([m,orig],ignore_index=True);codes=f.code.unique();ex=pd.read_parquet(T/'exposures.parquet',filters=[('code','in',list(codes))]);th=pd.read_csv(R/'tables/pooled_winsor_thresholds.csv',parse_dates=['freeze_date']).set_index(['freeze_date','metric']);out=f[f.eligible_day&f.date.isin(m.date)].merge(m,on='date',validate='m:m').merge(ex[['code','freeze_date','dose','eligible','quintile','holding_date','available_date']],on=['code','freeze_date'],validate='m:1');counts=[]
 for metric in PRIMARY:
  look=f[['code','date']].copy()
  for name,lo,hi in [('w01',.01,.99),('w005',.005,.995)]:
   lower=pd.Series(np.nan,index=f.index);upper=lower.copy();nn=lower.copy()
   for code,ix in f.groupby('code',sort=False).groups.items():
    g=f.loc[ix];z=g.loc[g.eligible_day&g.nb_open,metric];z=z[np.isfinite(z)];ql=z.expanding(min_periods=60).quantile(lo);qh=z.expanding(min_periods=60).quantile(hi);n=pd.Series(np.arange(1,len(z)+1),index=z.index);sl=ql.reindex(ix).ffill();sh=qh.reindex(ix).ffill();sn=n.reindex(ix).ffill().fillna(0);sl.loc[z.index]=ql.shift(1);sh.loc[z.index]=qh.shift(1);sn.loc[z.index]=n.shift(1,fill_value=0);lower.loc[ix]=sl;upper.loc[ix]=sh;nn.loc[ix]=sn
   look['lo']=lower;look['hi']=upper;look['npast']=nn;o=out[['code','date','freeze_date',metric]].merge(look,on=['code','date'],validate='m:1');fallback=o.npast.lt(60)|o.lo.isna()|o.hi.isna();l='q01' if name=='w01' else 'q005';h='q99' if name=='w01' else 'q995';o.loc[fallback,'lo']=[th.loc[(dt,metric),l] for dt in o.loc[fallback,'freeze_date']];o.loc[fallback,'hi']=[th.loc[(dt,metric),h] for dt in o.loc[fallback,'freeze_date']];out[f'{metric}__{name}']=o[metric].clip(o.lo,o.hi).to_numpy();counts.append(dict(block=b,metric=metric,variant=name,n=len(out),fallback=int(fallback.sum()),clipped=int(((o[metric]<o.lo)|(o[metric]>o.hi)).sum())))
 out['code']=pd.Categorical(out.code);out['group']=pd.Categorical(out.group);out['window']=pd.Categorical(out.window);out['event_id']=out.event_id.astype(np.int32);out['quintile']=out.quintile.astype('float32');(T/'panel').mkdir(exist_ok=True);out.drop(columns=['owner','distance','nb_open','eligible_day'],errors='ignore').to_parquet(T/'panel'/f'{b:03d}.parquet',index=False,compression='zstd');return counts

def safe_block(b):
 answer=block(b);release();return answer

def main():
 stage=sys.argv[1] if len(sys.argv)>1 else 'all'
 if stage in ['pack','all']:
  with cf.ProcessPoolExecutor(max_workers=4) as pool:list(pool.map(pack,range(2017,2027)))
 if stage in ['pooled','all']:
  from pooled_bounded import main as bounded_main
  bounded_main()
 if stage in ['panel','all']:
  n=int(np.ceil(len(pd.read_csv(R/'meta/stock_universe.csv'))/50));records=[]
  for start in range(0,n,8):
   with cf.ProcessPoolExecutor(max_workers=4) as pool:records.extend(r for rr in pool.map(safe_block,range(start,min(start+8,n))) if rr for r in rr)
   print('PANEL',min(start+8,n),'/',n,flush=True)
  save(pd.DataFrame(records),'winsor_audit.csv')
if __name__=='__main__':main()
