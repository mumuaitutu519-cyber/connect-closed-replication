from pathlib import Path
import json,hashlib,csv
ROOT=Path(__file__).resolve().parents[1]
def main():
 validation=json.loads((ROOT/'meta/final_validation.json').read_text());assert validation['status']=='PASS'
 manifest=json.loads((ROOT/'meta/output_sha256.json').read_text())
 for path,digest in manifest.items():assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest,path
 for path,digest in json.loads((ROOT/'meta/code_sha256.json').read_text()).items():assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest,path
 main=list(csv.DictReader((ROOT/'tables/main_estimates.csv').open()));assert len(main)==90;assert len({(r['metric'],r['exposure'],r['variant']) for r in main})==90
 assert all(int(r['wild_B'])==9999 and int(r['ri_B'])==9999 for r in main)
 for p in ['PREREGISTRATION.md','meta/lit_check.md','RESULTS_FOR_CLAUDE.md','sample_by_event.csv','balance.csv','data_scale.csv','run_all.sh','requirements.lock']:assert (ROOT/p).exists(),p
 for name in ['sample_by_event','balance','data_scale']:assert (ROOT/f'{name}.csv').read_bytes()==(ROOT/f'tables/{name}.csv').read_bytes()
 assert validation['independent_inference_checks_passed']==6;assert validation['registry_rows']==730
 print('PASS: 90 registered main specifications; 9999 bootstrap and RI draws each; output hashes verified.')
if __name__=='__main__':main()
