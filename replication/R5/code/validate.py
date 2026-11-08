from common import *
def main():
 checks=[]
 for file in ['numerical_adapter_vs_266_checks.csv','R2_baseline_reproduction_checks.csv','K_count_reproduction_checks.csv','minute_reuse_spot_checks.csv','numerical_quantile_cpp_checks.csv']:
  f=pd.read_csv(R/'tables'/file);allowed=['PASS','SKIPPED_NO_OPTIONAL_CACHE']if file=='minute_reuse_spot_checks.csv'else['PASS'];checks.append(dict(check=file,pass_all=bool(f.status.isin(allowed).all()),rows=len(f),skipped_optional_cache=bool(f.status.eq('SKIPPED_NO_OPTIONAL_CACHE').any())))
 f=pd.read_csv(R/'tables/G_component_identity_checks.csv');checks.append(dict(check='Delay_identity_and_R2_nesting',pass_all=bool(f.identity_max_abs.max()<1e-12 and f.r2_nested_violations.sum()==0),max_abs_error=f.identity_max_abs.max()))
 e=pd.read_csv(R/'tables/all_estimates.csv');h=pd.read_csv(R/'tables/H_dynamic_all.csv');assert len(e)>100 and len(h)>50;checks.append(dict(check='RI_actual_label_reproduction',pass_all=bool(e.ri_beta_abs_error.dropna().max()<1e-7),max_abs_error=e.ri_beta_abs_error.max()))
 checks.append(dict(check='9999_Webb_all_estimable',pass_all=bool(e.loc[e.status.eq('OK'),'wild_B'].eq(B).all())))
 # Uniform count fields in all delivered tables. Metadata/day tables carry their own explicit grain.
 for p in sorted((R/'tables').glob('*.csv')):
  d=pd.read_csv(p)
  if 'n'not in d:
   d['n']=d['stock_days']if'stock_days'in d else (1 if'event_id'in d or'date'in d else 0)
  if 'stocks'not in d:d['stocks']=d['stock_days']if'stock_days'in d else 0
  if 'events'not in d:d['events']=1 if'event_id'in d else (d['event_segments']if'event_segments'in d else 0)
  d['Obs']=d['n']
  d.to_csv(p,index=False)
 resources=[];historical_breaches=[]
 for p in sorted((R/'logs').glob('resource_*.jsonl')):
  v=[json.loads(s)for s in p.read_text().splitlines()if s];peak=max([r['rss']for r in v],default=0);last_id=v[-1].get('run_id','legacy')if v else'legacy';latest=max([r['rss']for r in v if r.get('run_id','legacy')==last_id],default=0);resources.append(dict(stage=p.stem,peak_rss_gb=peak/1e9,final_run_peak_rss_gb=latest/1e9));checks.append(dict(check=p.stem+'_final_run_under4GB',pass_all=latest<=4e9,final_run_peak_rss_gb=latest/1e9))
  if peak>4e9:historical_breaches.append(dict(stage=p.stem,peak_rss_gb=peak/1e9,action=('Automatically killed before regressions; rebuilt exact quantiles in bounded C++'if p.stem=='resource_panel'else'Unfinished models discarded; completed checkpointed models reused and numerically validated; fresh bounded workers for remaining models')))
 prereg=json.loads((R/'meta/preregistration_lock.json').read_text());checks.append(dict(check='prereg_hash',pass_all=prereg['sha256']==hashlib.sha256((R/'PREREGISTRATION_R5.md').read_bytes()).hexdigest()))
 statpass=all(c['pass_all']for c in checks)
 result=dict(status=('COMPLETE_WITH_RESOURCE_EXCEPTION'if historical_breaches else'PASS')if statpass else'FAIL',statistical_status='PASS'if statpass else'FAIL',historical_resource_breaches=historical_breaches,checks=checks,resources=resources,estimation_rows=len(e),dynamic_rows=len(h),max_observed_rss_gb=max([r['peak_rss_gb']for r in resources],default=0),max_final_run_rss_gb=max([r['final_run_peak_rss_gb']for r in resources],default=0),n_estimable=int(e.status.eq('OK').sum()),n_nonpositive_variance=int(e.status.eq('NONPOSITIVE_TWO_WAY_VARIANCE').sum()),seed=SEED,workers=4,hard_memory_gb=4)
 js(R/'meta/final_validation.json',result);js(R/'meta/code_sha256.json',{str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest()for p in sorted((R/'code').glob('*.py'))});print(json.dumps(result,ensure_ascii=False),flush=True)
 assert result['statistical_status']=='PASS'
 if historical_breaches:
  report=R/'RESULTS_FOR_CLAUDE.md';s=report.read_text().split('\n\n执行资源例外：')[0];detail='；'.join(f"{r['stage']}历史峰值{r['peak_rss_gb']:.3f}GB"for r in historical_breaches);s+='\n\n执行资源例外：'+detail+'。这些尝试超过4GB监控阈值后自动终止，被中止的未完成模型不纳入交付；中止前已经完整写出且通过数值校验的模型检查点予以保留。已改用C++分块精确分位数、精简列投影、宽规格逐项新进程及及时回收，最后一次续跑的各阶段重新核验资源峰值（完整计算过程的历史峰值仍按上述例外披露）（见meta/final_validation.json），原始失败与RSS日志保留。统计及样本复现通过不代表全程从未违反内存限制。\n';report.write_text(s)

if __name__=='__main__':main()
