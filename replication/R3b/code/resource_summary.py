from common import *
import re

def main():
 peaks={};samples=[]
 for p in [R/'logs/resource_history.jsonl',R/'logs/native_total_resource.jsonl']:
  if not p.exists():continue
  for line in p.read_text().splitlines():
   try:
    x=json.loads(line);v=x['rss_gb'];stage=x.get('stage','native_observer');peaks[stage]=max(peaks.get(stage,0),v);samples.append(v)
   except (ValueError,KeyError):pass
 stops=[]
 for p in (R/'logs').glob('*.log'):
  for value in re.findall(r'Aggregate RSS (\d+)',p.read_text(errors='replace')):stops.append(dict(log=p.name,rss_gb=int(value)/1e9))
 js(R/'meta/resource_summary.json',dict(budget_gb=4,sampling_guard_gb=3.7,recorded_peak_gb=max(samples+[x['rss_gb'] for x in stops]),phase_peaks_gb=peaks,samples_above_budget=sum(v>4 for v in samples),stops=stops,initial_monitor_scope_incomplete=True,compliance='EARLY_BUDGET_EXCEEDANCES_DISCLOSED; final scheduling repaired',note='Early background exposures and initial native subprocess scope were not fully included; a strict whole-run peak cannot be reconstructed. Recorded peak is a lower bound, not a guarantee of the total peak.'))
if __name__=='__main__':main()
