from common import *
import concurrent.futures as cf,multiprocessing as mp
PACK_LIMIT=None
def init_pack(lim):
 global PACK_LIMIT
 PACK_LIMIT=lim
def safe_pack(year):
 with PACK_LIMIT:return pack(year)

def pack(year):
 out=T/'history';out.mkdir(exist_ok=True)
 if(out/f'{year}.done.json').exists():return year,'CACHED'
 files=sorted((T/'daily').glob(f'{year}*.parquet'));f=pd.concat([pd.read_parquet(p)for p in files],ignore_index=True);codes=sorted(pd.read_parquet(T/'universe.parquet').code);groups={c:i//50 for i,c in enumerate(codes)};f['block']=f.code.map(groups)
 for b,g in f.groupby('block'):g.drop(columns='block').to_parquet(out/f'{year}_{b:03d}.parquet',index=False,compression='zstd')
 n=len(f);del f,g;release();js(out/f'{year}.done.json',dict(year=year,n=n));return year,n

def verify_cpp():
 import subprocess
 rng=np.random.default_rng(SEED);v=rng.normal(size=10003);v[::7]=0;p=T/'quantile_test.bin';v.tofile(p);req=p.with_suffix('.req.csv');out=p.with_suffix('.out.csv');ns=[0,1,2,3,23,999,5000,10003];pd.DataFrame([dict(event_id=i+1,freeze_day=i,n=n,stocks=0)for i,n in enumerate(ns)]).to_csv(req,index=False);subprocess.run([str(T/'exact_prefix_quantiles'),str(p),str(req),str(out)],check=True);got=pd.read_csv(out);checks=[]
 for i,n in enumerate(ns):
  expected=np.quantile(v[:n],[.005,.01,.99,.995])if n else np.full(4,np.nan);actual=got.loc[i,['q005','q01','q99','q995']].to_numpy(float);ok=np.allclose(expected,actual,rtol=1e-12,atol=1e-12,equal_nan=True);checks.append(dict(check='exact_prefix_linear_quantiles',n=n,stocks=0,events=0,max_abs_error=float(np.nanmax(abs(actual-expected)))if n else 0,status='PASS'if ok else'FAIL'))
 save(pd.DataFrame(checks),'numerical_quantile_cpp_checks.csv');assert all(x['status']=='PASS'for x in checks)
 for x in [p,req,out]:x.unlink()

def pool_parts(year):
 dest=T/'pool_parts';dest.mkdir(exist_ok=True);marker=dest/f'{year}.npz'
 if marker.exists():return year,'CACHED'
 codes=pd.Index(pd.read_parquet(T/'universe.parquet').code);first=np.full((len(METRICS),len(codes)),np.iinfo(np.int32).max,dtype=np.int32);handles=[(dest/f'{year}_{m}.bin').open('wb')for m in METRICS];counts=np.zeros(len(METRICS),np.int64);rows=[];days=[]
 try:
  for path in sorted((T/'daily').glob(f'{year}*.parquet')):
   dt=int(np.datetime64(pd.Timestamp(path.stem),'D').astype('int64'));d=pd.read_parquet(path,columns=['code','eligible_day','nb_open',*METRICS]);ids=codes.get_indexer(d.code);eligible=d.eligible_day.to_numpy()&d.nb_open.to_numpy();vals=d[METRICS].to_numpy(float)
   for j,m in enumerate(METRICS):
    good=eligible&np.isfinite(vals[:,j]);v=vals[good,j];handles[j].write(v.tobytes());counts[j]+=len(v);ii=ids[good];first[j,ii]=np.minimum(first[j,ii],dt)
   days.append(dt);rows.append(counts.copy())
 finally:
  for h in handles:h.close()
 np.savez_compressed(marker,days=np.array(days,np.int32),counts=np.array(rows,np.int64),first=first);release();return year,len(days)

def pooled(metric):
 import shutil
 dest=T/'pool_parts';p=T/f'pooled_{metric}.bin';j=METRICS.index(metric);fr=features()[['event_id','freeze_date']].drop_duplicates().sort_values('freeze_date');records={};first=np.full(len(pd.read_parquet(T/'universe.parquet')),np.iinfo(np.int32).max,dtype=np.int32)
 with p.open('wb')as dst:
  for year in range(2017,2027):
   with(dest/f'{year}_{metric}.bin').open('rb')as src:shutil.copyfileobj(src,dst,length=1024*1024)
   with np.load(dest/f'{year}.npz')as z:records[year]=(z['days'].copy(),z['counts'][:,j].copy());first=np.minimum(first,z['first'][j])
 requests=[]
 for e in fr.itertuples():
  cutoff=int(np.datetime64(e.freeze_date,'D').astype('int64'));nn=0
  for days,counts in records.values():
   k=np.searchsorted(days,cutoff,side='left')
   if k:nn+=int(counts[k-1])
  requests.append(dict(event_id=e.event_id,freeze_day=cutoff,n=nn,stocks=int((first<cutoff).sum())))
 request=p.with_suffix('.request.csv');output=p.with_suffix('.out.csv');pd.DataFrame(requests).to_csv(request,index=False)
 import subprocess
 subprocess.run([str(T/'exact_prefix_quantiles'),str(p),str(request),str(output)],check=True)
 out=pd.read_csv(output);out['freeze_date']=pd.to_datetime(out.freeze_day,unit='D');out['metric']=metric;out['events']=1;save(out.drop(columns='freeze_day'),f'pooled_{metric}.csv')
 for pp in [p,request,output]:pp.unlink()
 release();return metric

def block(b):
 files=sorted((T/'history').glob(f'*_{b:03d}.parquet'))
 if not files:return []
 f=pd.concat([pd.read_parquet(p)for p in files],ignore_index=True).sort_values(['code','date']).reset_index(drop=True);assert not f.duplicated(['code','date']).any();m=pd.read_csv(R/'tables/H_extended_date_map.csv',parse_dates=['date']);feat=features();feat=feat[feat.code.isin(f.code.unique())];out=f[f.eligible_day&f.date.isin(m.date)].merge(m[['event_id','date','relative','role','resume','closed','original_sample']],on='date',validate='m:1').merge(feat,on=['event_id','code'],validate='m:1');audit=[]
 thresholds=pd.read_csv(R/'tables/pooled_winsor_thresholds.csv').set_index(['event_id','metric'])
 for metric in METRICS:
  for variant,lo,hi in [('w01',.01,.99),('w005',.005,.995)]:
   lower=pd.Series(np.nan,index=f.index);upper=lower.copy();nn=lower.copy()
   for c,ix in f.groupby('code',sort=False).groups.items():
    g=f.loc[ix];z=g.loc[g.eligible_day&g.nb_open,metric];z=z[np.isfinite(z)];ql=z.expanding(min_periods=60).quantile(lo);qh=z.expanding(min_periods=60).quantile(hi);n=pd.Series(np.arange(1,len(z)+1),index=z.index);sl=ql.reindex(g.index).ffill();sh=qh.reindex(g.index).ffill();sn=n.reindex(g.index).ffill().fillna(0);sl.loc[z.index]=ql.shift(1);sh.loc[z.index]=qh.shift(1);sn.loc[z.index]=n.shift(1,fill_value=0);lower.loc[ix]=sl;upper.loc[ix]=sh;nn.loc[ix]=sn
   look=pd.DataFrame(dict(code=f.code,date=f.date,lo=lower,hi=upper,npast=nn));o=out[['code','date','event_id',metric]].merge(look,on=['code','date'],validate='1:1');fb=o.npast.lt(60)|o.lo.isna()|o.hi.isna();l='q01'if variant=='w01'else'q005';h='q99'if variant=='w01'else'q995';o.loc[fb,'lo']=[thresholds.loc[(ev,metric),l]for ev in o.loc[fb,'event_id']];o.loc[fb,'hi']=[thresholds.loc[(ev,metric),h]for ev in o.loc[fb,'event_id']];v=o[metric].clip(o.lo,o.hi);out[f'{metric}__{variant}']=v.to_numpy();audit.append(dict(block=b,metric=metric,variant=variant,n=len(o),stocks=out.code.nunique(),events=out.event_id.nunique(),fallback=int(fb.sum()),missing_threshold=int((o.lo.isna()|o.hi.isna()).sum()),clipped=int(((o[metric]<o.lo)|(o[metric]>o.hi)).sum())))
 out['code']=pd.Categorical(out.code);out[out.original_sample].drop(columns='original_sample').to_parquet(T/'panel'/f'{b:03d}.parquet',index=False,compression='zstd');out[~out.original_sample].drop(columns='original_sample').to_parquet(T/'H_extra'/f'{b:03d}.parquet',index=False,compression='zstd');release();return audit

def main():
 ctx=mp.get_context('spawn');stage=sys.argv[1]if len(sys.argv)>1 else'all'
 if stage in ['pack','all']:
  for start in range(2017,2027,2):
   with cf.ProcessPoolExecutor(max_workers=4,mp_context=ctx,initializer=init_pack,initargs=(ctx.Semaphore(1),))as pool:
    for r in pool.map(safe_pack,range(start,min(start+2,2027))):print('PACK',r,flush=True)
 if stage in ['pooled','all']:
  import subprocess
  subprocess.run(['c++','-O3','-std=c++17',str(R/'code/exact_prefix_quantiles.cpp'),'-o',str(T/'exact_prefix_quantiles')],check=True)
  verify_cpp()
  with cf.ProcessPoolExecutor(max_workers=4,mp_context=ctx)as pool:
   for r in pool.map(pool_parts,range(2017,2027)):print('POOL_PARTS',r,flush=True)
  with cf.ProcessPoolExecutor(max_workers=4,mp_context=ctx)as pool:
   for r in pool.map(pooled,METRICS):print('POOLED',r,flush=True)
  save(pd.concat([pd.read_csv(R/'tables'/f'pooled_{m}.csv')for m in METRICS],ignore_index=True),'pooled_winsor_thresholds.csv')
 if stage in ['panel','all']:
  (T/'panel').mkdir(exist_ok=True);(T/'H_extra').mkdir(exist_ok=True);nj=int(np.ceil(len(pd.read_parquet(T/'universe.parquet'))/50));audit=[]
  for start in range(0,nj,16):
   with cf.ProcessPoolExecutor(max_workers=4,mp_context=ctx)as pool:audit.extend(r for rr in pool.map(block,range(start,min(start+16,nj)))for r in rr)
   print('PANEL',min(start+16,nj),'/',nj,flush=True)
  save(pd.DataFrame(audit),'winsor_audit.csv')
if __name__=='__main__':main()
