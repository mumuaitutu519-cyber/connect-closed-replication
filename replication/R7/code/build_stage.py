from common import *
import subprocess,concurrent.futures as cf,multiprocessing as mp

def stage(script,*args):
 print('STAGE',script,*args,flush=True);subprocess.run([sys.executable,str(R/'code'/script),*args],check=True)
def main():
 stage('design.py');stage('panel.py','pack');stage('supplement.py','static');stage('hk_features.py','daily')
 import supplement
 jobs=range(int(np.ceil(len(universe())/50)))
 with cf.ProcessPoolExecutor(max_workers=4,mp_context=mp.get_context('spawn'))as pool:list(pool.map(supplement.history_block,jobs))
 stage('index_us.py');stage('supplement.py','combine');stage('panel.py','pooled');stage('panel.py','panel');js(R/'meta/build_complete.json',dict(utc=pd.Timestamp.now(tz='UTC').isoformat()));print('BUILD_COMPLETE',flush=True)
if __name__=='__main__':main()
