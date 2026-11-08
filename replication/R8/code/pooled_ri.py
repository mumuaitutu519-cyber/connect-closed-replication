from common import *
from horizons import metric
from inference import fit,close,summarize,plan
import concurrent.futures as cf,multiprocessing as mp

def patterns():
 dates,Z,meta=plan('main');m=pd.read_csv(P/'tables/event_date_map.csv',parse_dates=['date']);out={};index=[]
 for eid,g in m.groupby('event_id'):
  g=g.sort_values('date');ix=pd.Index(dates).get_indexer(g.date);assert(ix>=0).all();powers=2**np.arange(len(g),dtype=np.int64);codes=Z[:,ix].astype(np.int64)@powers;actual=int(g.closed.to_numpy(np.int64)@powers);allcodes=sorted(set(codes.tolist())|{actual});out[int(eid)]=dict(dates=g.date.dt.strftime('%Y-%m-%d').tolist(),patterns=allcodes,actual=actual);index.append(codes)
 np.savez_compressed(T/'pooled_ri_draws.npz',events=np.array(sorted(out)),codes=np.array(index),unique_projected=len(np.unique(np.array(index).T,axis=0)));js(T/'pooled_ri_patterns.json',out)

def block(b):
 dest=T/'pooled_ri_parts'/f'{b:03d}.parquet'
 if dest.exists():return b
 source=T/'pooled_daily'/f'{b:03d}.parquet'
 if not source.exists():return b
 f=pd.read_parquet(source);spec=json.loads((T/'pooled_ri_patterns.json').read_text());fe=pd.read_parquet(T/'feature_blocks'/f'{b:03d}.parquet',columns=['code','event_id','dose','family']);fe=fe[fe.family.eq('main')][['code','event_id','dose']];out=[];mom=[f'mom{h}_{c}'for h in [30,60]for c in ['n','sx','sy','sxx','syy','sxy']]
 for eid,g in f.groupby('event_id'):
  p=spec[str(eid)];dateindex={pd.Timestamp(dt):j for j,dt in enumerate(p['dates'])};positions=g.date.map(dateindex).to_numpy(np.int64);parts=[]
  for mask in p['patterns']:
   q=g[['code',*mom]].copy();q['closed']=((int(mask)>>positions)&1).astype(bool);z=q.groupby(['code','closed'],observed=True)[mom].sum(min_count=1).reset_index();z['days']=q.groupby(['code','closed'],observed=True).size().to_numpy();z['pattern']=mask;z['event_id']=eid
   for h in [30,60]:
    beta,r2=metric(z,h);good=(z[f'mom{h}_n']>=np.maximum(3,.8*z.days*(240//h)))&np.isfinite(beta)&np.isfinite(r2)&r2.between(0,1);z[f'beta_{h}']=beta.where(good);z[f'r2_{h}']=r2.where(good)
   parts.append(z[['code','closed','pattern','event_id','beta_30','r2_30','beta_60','r2_60']])
  z=pd.concat(parts,ignore_index=True)
  for h in [30,60]:
   valid=z[f'beta_{h}'].notna()&z[f'r2_{h}'].notna();counts=z[valid].groupby('code',observed=True).size();codes=counts.index[counts.eq(2*len(p['patterns']))];z[f'common_{h}']=z.code.isin(codes)
  out.append(z)
 if out:
  z=pd.concat(out,ignore_index=True).merge(fe,on=['code','event_id'],validate='m:1');z.to_parquet(dest,index=False)
 release();return b

def main():
 patterns();(T/'pooled_ri_parts').mkdir(exist_ok=True);ctx=mp.get_context('spawn');nb=int(np.ceil(len(universe())/50))
 for first in range(0,nb,6):
  with cf.ProcessPoolExecutor(max_workers=6,mp_context=ctx)as pool:list(pool.map(block,range(first,min(first+6,nb))))
  print('POOLED_RI_PREP',min(first+6,nb),'/',nb,flush=True)
 f=pd.concat([pd.read_parquet(p)for p in sorted((T/'pooled_ri_parts').glob('*.parquet'))],ignore_index=True);f.code=pd.Categorical(f.code);spec=json.loads((T/'pooled_ri_patterns.json').read_text());actual={int(e):p['actual']for e,p in spec.items()};ev=pd.read_csv(P/'tables/events.csv',parse_dates=['start']).set_index('event_id');bounds=pd.read_csv(R/'tables/pooled_horizon_winsor_thresholds.csv').set_index(['metric','event_id']);rows=[]
 with np.load(T/'pooled_ri_draws.npz')as z:draws=z['codes'].copy();events=z['events'].copy();unique=int(z['unique_projected'])
 for h in [30,60]:
  for name in ['beta','r2']:
   metricname=f'pooled_{name}_{h}';col=f'{name}_{h}';g=f[f[f'common_{h}']&np.isfinite(f.dose)].copy()
   for variant in VARIANTS:
    g['y']=g[col]
    if variant!='raw':bb=bounds.loc[metricname];lo='q01'if variant=='w01'else'q005';hi='q99'if variant=='w01'else'q995';g['y']=g.y.clip(g.event_id.map(bb[lo]),g.event_id.map(bb[hi]))
    q=g[g.pattern.eq(g.event_id.map(actual))].copy().reset_index(drop=True);q['date']=q.event_id.map(ev.start)+pd.to_timedelta(q.closed.astype(int),unit='D');q['closed_x']=q.closed*q.dose;q['event_id']=q.event_id.astype(int);m=fit(q,['closed_x','dose']);r=summarize(q,m,'closed_x');j=m['names'].index('closed_x');other=np.delete(np.arange(len(m['names'])),j);xp=np.array(m['a'][m['indices'][j]]);cx=np.linalg.pinv(m['xx'][np.ix_(other,other)])@m['xx'][other,j]
    for start in range(0,len(q),32768):xp[start:start+32768]-=cx@np.array(m['a'][m['indices'][other],start:start+32768])
    den=xp@xp;weights=q[['code','event_id','closed']].copy();weights['score_weight']=xp;score=g.merge(weights,on=['code','event_id','closed'],validate='m:1');score['score']=score.score_weight*score.y;contribution=score.groupby(['event_id','pattern'],observed=True).score.sum();permuted=np.zeros(draws.shape[1]);obs=0.
    for i,eid in enumerate(events):
     if eid not in q.event_id.unique():continue
     series=contribution.loc[eid];permuted+=pd.Series(draws[i]).map(series).to_numpy();obs+=series.loc[actual[eid]]
    permuted/=den;assert np.isfinite(permuted).all();error=abs(obs/den-r['beta']);assert error<1e-8,(metricname,error);r.update(metric=metricname,variant=variant,specification='recomputed_calendar_RI_common_pattern_sample',ri_p=(1+np.sum(abs(permuted)>=abs(r['beta'])))/(len(permuted)+1),ri_B=len(permuted),ri_unique_calendars=unique,ri_status='OK_RECOMPUTED_POOLS_FIXED_COMMON_PATTERN_SAMPLE',ri_fwl_error=error,pattern_sample_rule='each stock-event has valid both states under actual and every eligible calendar pattern');rows.append(r);close(m);del q,score,weights;release();print('POOLED_RI',metricname,variant,r['ri_p'],r['n'],flush=True)
 save(rows,'pooled_horizon_calendar_RI.csv')
if __name__=='__main__':main()
