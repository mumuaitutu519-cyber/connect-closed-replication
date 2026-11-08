from common import *
import concurrent.futures as cf,warnings,multiprocessing as mp
LIMIT=None
def init(lim):
 global LIMIT
 LIMIT=lim
sys.path.insert(0,str(R/'code/r1'))
import build_metrics_daily as bd
ORIG=bd.metrics
def chunk_metrics(d,codes):
 out=[]
 for i in range(0,len(codes),400):
  sub=codes[i:i+400];q=d[d.symbol.isin(sub)].copy()
  if len(q):out.append(ORIG(q,sub))
  del q;release()
 return pd.concat(out,ignore_index=True)
from four_metrics import chunk
bd.metrics=chunk
warnings.filterwarnings('ignore',category=RuntimeWarning)
def one(day):
 with LIMIT:return work(day)
def work(day):
 from stream_day import stream
 r=stream(day);release();return r
if __name__=='__main__':
 c=pd.read_csv(R/'tables/official_calendar.csv',parse_dates=['date']);days=c.loc[c.a_open&c.date.le('2026-09-30'),'date'];jobs=[str(x.date()) for x in days if not (bd.OUT/f'{x:%Y%m%d}.json').exists()]
 print('MINUTES',len(days),'pending',len(jobs),flush=True)
 ctx=mp.get_context('spawn');lim=ctx.Semaphore(4)
 for start in range(0,len(jobs),16):
  with cf.ProcessPoolExecutor(max_workers=4,mp_context=ctx,initializer=init,initargs=(lim,)) as pool:list(pool.map(one,jobs[start:start+16]))
  print('MINUTES',start+min(16,len(jobs)-start),'/',len(jobs),jobs[min(start+15,len(jobs)-1)],flush=True)
 save(pd.DataFrame([json.loads(p.read_text()) for p in sorted(bd.OUT.glob('*.json'))]),'minute_day_receipts.csv')
