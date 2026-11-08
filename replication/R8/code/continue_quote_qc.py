from pathlib import Path
import sys,subprocess
R=Path(__file__).resolve().parents[1]
for stage in ['panels','estimates']:
 with (R/'logs'/f'quote_qc_{stage}.log').open('w')as f:subprocess.run([sys.executable,str(R/'code/guard.py'),sys.executable,str(R/'code/correct_quote_qc.py'),stage],stdout=f,stderr=subprocess.STDOUT,check=True)
for stage in ['adverse','finalize','verify']:
 with (R/'logs'/f'quote_qc_{stage}.log').open('w')as f:subprocess.run([sys.executable,str(R/'code/guard.py'),sys.executable,str(R/'code'/f'{stage}.py')],stdout=f,stderr=subprocess.STDOUT,check=True)
print('QUOTE_QC_ALL_COMPLETE',flush=True)
