from common import *
import concurrent.futures as cf
sys.path.insert(0,str(R/'code/r1'))
import prepare_futures as pf,extract_futures as ex
if __name__=='__main__':
 with cf.ProcessPoolExecutor(max_workers=4) as pool:list(pool.map(ex.extract,['IF/IF1*.csv','IF/IF2*.csv','IH/IH1*.csv','IH/IH2*.csv']))
 pf.main()
 js(R/'meta/futures_receipt.json',[dict(path=str(T/f'futures_{p}.npz'),sha256=hashlib.sha256((T/f'futures_{p}.npz').read_bytes()).hexdigest()) for p in ['IF','IH']])
