from pathlib import Path
import subprocess,sys,time,json
R=Path(__file__).resolve().parents[1]
# Resume only after the first minute build reports a successful exit.
while True:
 p=R/'logs/stage_resource_receipts.jsonl';rows=[json.loads(s)for s in p.read_text().splitlines()]if p.exists()else[];matching=[r for r in rows if str(r['command'][-1]).endswith('/minutes.py')]
 if matching:
  if matching[-1]['status']!='PASS':raise RuntimeError('Minute stage failed; inspect log before resuming')
  break
 time.sleep(2)
stages=['build','split_panels','prune_caches','analyze','horizons','pooled_ri','small','provenance','adverse','finalize','verify']
start=sys.argv[1]if len(sys.argv)>1 else'build'
for stage in stages[stages.index(start):]:
 print('STAGE',stage,flush=True)
 with (R/'logs'/f'reproduce_{stage}.log').open('w')as log:subprocess.run([sys.executable,str(R/'code/guard.py'),sys.executable,str(R/'code'/f'{stage}.py')],stdout=log,stderr=subprocess.STDOUT,check=True)
print('ALL_STAGES_COMPLETE',flush=True)
