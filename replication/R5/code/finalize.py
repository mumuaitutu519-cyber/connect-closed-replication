from common import *
from scipy.stats import norm

def table(f,cols):
 if f.empty:return '（无可用结果；见状态表）'
 d=f[[c for c in cols if c in f]].copy()
 counts=['n','Obs','stocks','events','dates','cell_n','cell_stocks','cell_events','cell_dates','official_events','closure_days','qfii_known_stock_events','positive_stock_days','stock_clusters','date_clusters','joint_unique_cells','baseline_n','eligible_panel_n','raw_metric_n']
 for c in d:
  if c in counts or c.startswith('missing_'):
   d[c]=d[c].map(lambda x:f'{int(x):,}'if pd.notna(x)else'')
 d=d.rename(columns={'n':'Obs','stocks':'股票数','events':'事件段数','cell_n':'每格Obs','cell_stocks':'每格股票数','cell_events':'每格事件段数','dates':'日期数'});return d.to_markdown(index=False,floatfmt='.6g')

def main():
 est=pd.read_csv(R/'tables/all_estimates.csv');est['dose_units']=np.where(est.specification.eq('I_log1p_Hold'),'one log(1+Hold percentage points) unit',np.where(est.specification.eq('I_Hold_quintiles'),'quintile j minus quintile 1','one holding percentage point; auxiliary terms follow named covariate'));dyn=pd.read_csv(R/'tables/H_dynamic_all.csv');dist=pd.concat([pd.read_csv(p)for p in sorted((R/'tables').glob('distribution_*_*.csv'))],ignore_index=True);save(dist,'distributions.csv')
 # Main IF/IH BH family per specification/variant/term; auxiliary components remain separately labeled.
 est['q_IF_IH']=np.nan;est['rw_IF_IH']=np.nan
 with np.load(T/'resampling.npz')as zz:W=zz['webb']
 for _,ix in est[est.metric.isin(PRIMARY)].groupby(['specification','variant','term']).groups.items():
  p=est.loc[ix,'p'].to_numpy(float);good=np.flatnonzero(np.isfinite(p));order=good[np.argsort(p[good])];out=np.full(len(p),np.nan)
  if len(order):out[order]=np.minimum(1,np.minimum.accumulate((p[order]*len(order)/np.arange(1,len(order)+1))[::-1])[::-1])
  est.loc[ix,'q_IF_IH']=out
  gg=est.loc[ix];valid=gg.se.gt(0)&gg.beta.notna()&gg.wild_scores_json.notna();ii=gg.index[valid]
  if len(ii):
   obs=np.abs(est.loc[ii,'beta'].to_numpy()/est.loc[ii,'se'].to_numpy());boots=np.column_stack([np.abs(W@np.array(json.loads(est.loc[k,'wild_scores_json']))/est.loc[k,'wild_denominator'])/est.loc[k,'se']for k in ii]);order=np.argsort(-obs);prior=0
   for kk,k in enumerate(order):
    pv=(1+np.sum(boots[:,order[kk:]].max(axis=1)>=obs[k]))/(B+1);prior=max(prior,pv);est.loc[ii[k],'rw_IF_IH']=prior
 save(est,'all_estimates.csv')
 w=est[est.variant.eq('w01')];coefcols=['metric','specification','term','beta_x100','se_x100','ci_low_x100','ci_high_x100','p','wild_p','ri_p','rw_IF_IH','n','stocks','events','dates','status']
 for letter,spec in [('F',w.specification.str.startswith('F_')),('G',w.specification.str.startswith('G_')|~w.metric.isin(PRIMARY)),('I',w.specification.str.startswith('I_')),('J',w.specification.str.startswith('J_'))]:save(w[spec],f'{letter}_main_w01.csv')
 ret=[]
 for metric in PRIMARY:
  mm=w[w.metric.eq(metric)];get=lambda spec:mm[mm.specification.eq(spec)&mm.term.eq('closed_x')].iloc[0]
  b=get('baseline');c=get('G_contemporaneous_controls');s=get('G_controls_same_sample_baseline');h=get('F_HKonly');r=dyn[dyn.metric.eq(metric)&dyn.variant.eq('w01')&dyn.scheme.eq('resume')&dyn.cell.eq('resume0')].iloc[0]
  ret.append(dict(metric=metric,baseline_x100=b.beta_x100,HKonly_x100=h.beta_x100,HKonly_p=h.p,HKonly_wild_p=h.wild_p,HKonly_ri_p=h.ri_p,HKonly_events=h.events,controlled_x100=c.beta_x100,same_sample_baseline_x100=s.beta_x100,retained_same_sample_pct=c.beta/s.beta*100,retained_full_baseline_pct=c.beta/b.beta*100,resume0_x100=r.beta_x100,resume0_p=r.p,resume0_wild_p=r.wild_p,n=c.n,stocks=c.stocks,events=c.events))
 ret=pd.DataFrame(ret);save(ret,'adverse_facts.csv');qcov=pd.read_csv(R/'tables/J_QFII_positive_distribution.csv');power=w[w.specification.eq('J_QFII_race')&w.term.eq('cx_qfii')];save(power,'J_QFII_MDE80.csv')
 status=est[['metric','variant','specification','term','status','n','stocks','events']].copy();missing=pd.DataFrame([dict(metric=m,variant=v,specification=s,term='closed_x',status=st,n=0,stocks=0,events=0)for m in PRIMARY for v in ['raw','w01','w005']for s,st in [('I_index_weights_full_46_events','UNAVAILABLE_HISTORICAL_PRE2026_WEIGHTS'),('I_northbound_turnover_race','UNAVAILABLE_INDIVIDUAL_TURNOVER')]]);save(pd.concat([status,missing],ignore_index=True),'specification_status.csv')
 bc=est[est.specification.eq('baseline')&est.term.eq('closed_x')&est.metric.isin(PRIMARY)];save(bc,'baseline_all_variants.csv')
 parts=['# 284 R5 统计补跑：F–K 合并结果\n\n只报告统计；种子20261118。全部系数、SE、CI、MDE以×100列展示，原单位同时保留在CSV。Hold单位为持股百分点。主变换1/99；raw及0.5/99.5全部保留。Obs（CSV的n）为各模型完整案例股票日；股票数与事件段数按实际模型样本计算，动态另列每格支持。分布表Obs为有效股票日，QFII正持股分布表Obs为股票×事件；日历/纯数值核验表按各自记录单位计Obs，股票数0表示不适用。未取得来源或无支持不填0系数。\n']
 parts+=['## 原样本与基准复现\n\n一句结论：IF/IH基准的三种变换均从原始分钟重建，并逐项对照272的系数、SE、Obs、股票及日期簇数。\n\n'+table(bc,coefcols+['variant'])+'\n\n最不利事实：46个官方关闭段不等于46个可估计期货事件，IF/IH期货原始数据截至2026-09-01；具体复现状态见R2_baseline_reproduction_checks.csv。\n']
 F=w[w.metric.isin(PRIMARY)&w.specification.str.startswith('F_')];cl=pd.read_csv(R/'tables/F_event_classification.csv');summary=cl.groupby(['foreign_group','holiday_type']).agg(official_events=('event_id','size'),closure_days=('n_closed_days','sum')).reset_index();summary['n']=summary.closure_days;summary['stocks']=0;summary['events']=summary.official_events;save(summary,'F_official_group_counts.csv')
 hks='；'.join(f"{r.metric}: β×100={r.HKonly_x100:.6g}, 双向p={r.HKonly_p:.6g}, wild p={r.HKonly_wild_p:.6g}, RI p={r.HKonly_ri_p:.6g}"for r in ret.itertuples())
 parts+=['## F 外国市场信息是否同时消失\n\n一句结论：欧美全部正常开市的港相关关闭组结果为 '+hks+'。\n\n'+table(F,coefcols)+'\n\n'+table(summary,['foreign_group','holiday_type','official_events','closure_days','n','stocks','events'])+'\n\n最不利事实：这里的“共同休市”指一个事件段内至少一个欧美市场存在休市或半日，不能写成所有欧美市场整段都关闭；北向结算关闭日也不一定是香港现金市场休市日。严格仅香港现金休市日估计单列F_strict_HK_cash_days，原控制窗仍保留。日历分组25段欧美全部照常、21段含共同休市/半日；期货有效样本分组数以回归表为准。同日按各交易所当地民用日期对齐，不等于A股交易时段内欧美连续交易，NYSE核心时段发生在A股收盘以后，这个分组无法独自排除所有跨时区信息渠道。\n\nSGX A50为产品专属日历，不能用XSES现金日历替代。SGX原始2017规则附件列CN于所有在岸假日照常交易合约、元旦除外；2026公告再次确认除元旦外所有工作日开市。本样本关闭日A50均为计划开市。这是交易日历状态，未取得逐日期货成交带验证。[SGX规则附件（原文镜像）](https://www.emega.com.tw/emega/upload/bulletin/157fb4018bf000008950.pdf)、[SGX 2026公告](https://api2.sgx.com/sites/default/files/2025-12/DTAM%20109%20of%202025%20-%20SGX-DT%20Derivatives%20Trading%20Holiday%20Schedule%20for%20Year%202026.pdf)。欧美日历采用exchange_calendars 4.13.2（NYSE/LSE/Xetra/Euronext Paris），官方依据与获取回执见meta/calendar_sources.json；并非整个欧元区每个交易所。\n']
 diff=F[F.specification.eq('F_difference')&F.term.eq('diff_x')];parts += ['F最不利事实补充（组间差异）：'+'；'.join(f"{r.metric} HKonly差异×100={r.beta_x100:.6g}，双向p={r.p:.6g}、wild p={r.wild_p:.6g}、条件RI p={r.ri_p:.6g}"for r in diff.itertuples())+'。不同推断的显著性可能不一致，不能仅挑较小的p。\n']
 r3=P/'R3b/RESULTS_FOR_CLAUDE.md'
 if r3.exists():
  candidates=[P/'R3b/tables/main_estimates.csv',P/'R3b/tables/all_estimates.csv'];reported=False
  for cp in candidates:
   if not cp.exists():continue
   dd=pd.read_csv(cp)
   if'events'not in dd and'wild_clusters'in dd:dd['events']=dd.wild_clusters
   save(dd,'F_282_existing_estimates_reference.csv');ref=dd.copy()
   if'metric'in ref:ref=ref[ref.metric.isin(PRIMARY)]
   if'variant'in ref:ref=ref[ref.variant.eq('w01')]
   if'exposure'in ref:ref=ref[ref.exposure.eq('dose')]
   if'window'in ref:ref=ref[ref.window.eq('r1')]
   if'term'in ref:ref=ref[ref.term.eq('treated_x')]
   if'events'not in ref and'wild_clusters'in ref:ref['events']=ref.wild_clusters
   for cc in ['beta','se','ci_low','ci_high']:
    if cc in ref:ref[cc+'_x100']=ref[cc]*100
   parts += [table(ref,[c for c in ['metric','group','specification','window','term','beta_x100','se_x100','p','wild_p','ri_p','n','stocks','events','event_segments']if c in ref])+'\n']
   parts+=['282结果文件已存在，直接并列保留其原估计表F_282_existing_estimates_reference.csv，保留282原种子/样本/推断口径，不重算。其结论参见 [R3b原结果](../R3b/RESULTS_FOR_CLAUDE.md)。\n'];reported=True;break
  if not reported:parts+=['282结果文件已存在，但本轮未识别其标准主估计CSV；参见 [R3b原结果](../R3b/RESULTS_FOR_CLAUDE.md)，未编造主系数。\n']
 else:parts+=['282的RESULTS_FOR_CLAUDE.md在R5定稿时尚不存在，故不填其主系数、不等待、不重跑。\n']
 comp=w[~w.metric.isin(PRIMARY)&w.specification.eq('baseline')];now=comp[comp.metric.eq('if_r2_now')].iloc[0];full=comp[comp.metric.eq('if_r2_full')].iloc[0];lags=comp[comp.metric.str.match('if_b[1-5]$')];drive=('分解证据集中在同期解释力下降，b1–b5没有一项显著上升；'if now.beta<0 and not((lags.beta>0)&(lags.p<.05)).any()else'同期与滞后项的方向及推断如下；')+f"同期R²交互系数×100={now.beta_x100:.6g}（p={now.p:.6g}），完整R²={full.beta_x100:.6g}（p={full.p:.6g}）；b1…b5中正系数{int((lags.beta>0).sum())}/5、双向p<.05的正系数{int(((lags.beta>0)&(lags.p<.05)).sum())}/5。"
 parts+=['## G 延迟指标拆解与脉冲反应\n\n一句结论：'+drive+'\n\n'+table(comp,coefcols)+'\n\n最不利事实：Delay=1−R²同期/R²完整是非线性比率，不能将两个独立回归系数直接相加解释为精确贡献；R²下降或单个b_k变化也不是交易者缺席的独立因果证明；不能把延迟比率上升直接写成已经检出滞后反应增强。b0指完整滞后模型的同期系数；if_b0_now另列为只有同期的回归斜率。逐股票日恒等式和嵌套检查见G_component_identity_checks.csv。各R²或b结果按各自有限可估计值入模，Obs可能不完全相同，不能将跨方程点估计当成严格可加贡献份额。\n']
 G=w[w.metric.isin(PRIMARY)&(w.specification.str.startswith('G_')|w.specification.eq('baseline'))]
 parts+=['## G 交易强度、有效分钟与高成交子样本\n\n一句结论：控制当日log成交额、有效分钟数、日内实现方差及三项×Closed后，同样本系数保留比例为 '+ '；'.join(f'{r.metric} {r.retained_same_sample_pct:.3f}%'for r in ret.itertuples())+'。\n\n'+table(G,coefcols)+'\n\n'+table(ret,['metric','controlled_x100','same_sample_baseline_x100','retained_same_sample_pct','retained_full_baseline_pct','n','stocks','events'])+'\n\n最不利事实：成交笔数源不可得，使用有效分钟数；当日控制可能是处理后的中介变量，保留比例不是可识别的因果中介份额。高成交组由272事件冻结前60正常日成交额中位数最高三个十分位定义，不以关闭后成交分组。\n']
 adj=comp[comp.metric.eq('adjust5')]
 ar=est[est.metric.eq('adjust5')].set_index('variant');adjfact='原始值系数×100='+f"{ar.loc['raw','beta_x100']:.6g}"+'，主缩尾为'+f"{ar.loc['w01','beta_x100']:.6g}"+'、0.5/99.5为'+f"{ar.loc['w005','beta_x100']:.6g}"+'；原始与缩尾方向不同，且显著性在双向/wild/RI之间不稳健。'
 parts+=['## G 期货大动分钟后的0–5分钟累计调整比例\n\n一句结论：'+adjfact+'\n\n'+table(est[est.metric.eq('adjust5')],['variant',*coefcols])+'\n\n最不利事实：分母为冻结日频IF beta×冲击当分钟IF收益，beta接近0会放大比率，累计反应可负或超过1；0–5口径包含冲击当分钟及后5分钟，共6个分钟收益，冲击窗口允许重叠，同日冲击先平均，回归单位仍为股票日。主窗使用对应事件冻结beta和阈值；历史正常日阈值只用当时已知最近事件的参数，首冻结前比例缺失，首段没有历史阈值时沿266的pandas clip保留原值，明确标记为未缩尾；该部分并未受到1/99或0.5/99.5缩尾保护，raw仍单列。该比例是条件反应代理，不是无误差的永久信息吸收份额。\n']
 hd=dyn[dyn.variant.eq('w01')];dc=['metric','cell','beta_x100','ci_low_x100','ci_high_x100','p','wild_p','n','stocks','events','cell_n','cell_stocks','cell_events','status']
 for scheme,title in [('first','以首个关闭日为0：严格原样本'),('resume','以恢复日为0：严格原样本'),('resume_extended','以恢复日为0：补充+5日扩展')]:
  dd=hd[hd.scheme.eq(scheme)];anchorcell='t0'if scheme=='first'else'resume0';anchorrows=dd[dd.cell.eq(anchorcell)];dyn_summary='；'.join(f"{r.metric} {anchorcell} β×100={r.beta_x100:.6g}, 双向p={r.p:.6g}, wild p={r.wild_p:.6g}"for r in anchorrows.itertuples());parts+=['## H '+title+'\n\n一句结论：'+dyn_summary+'。\n\n'+table(dd,dc)+'\n\n最不利事实：参考格是关闭前−1正常日，绝不是恢复前−1关闭日；置信区间为股票+日期双向聚类，wild检验为非studentized绝对系数。严格原样本恢复日0的IH事件wild p=0.0259，仍在5%水平显著，而双向p=0.1428；IF两种p均未达5%。因此不能声称恢复当天已经消失；不显著也不是效应为0的等价性证据，区间仍允许有经济意义的正效应。原五个后正常日仅覆盖恢复0…+4，恢复+5在严格原样本无支持；扩展表只在无原日期归属冲突且北向正常开放时补第六日，计数与主结果不同。\n']
 I=w[w.metric.isin(PRIMARY)&w.specification.str.startswith('I_')];parts+=['## I 假日类型与极端剂量\n\n一句结论：各假日、P99剔除、log(1+Hold)与五分位剂量全部固定进表，未按显著性筛选假日。\n\n'+table(I[~I.specification.str.contains('weight')],coefcols)+'\n\n最不利事实：假日子组的有效冲击数显著少于45段；佛诞可与欧美假日重合，不等于HKonly。五分位最低组为基准，零持股ties沿272股票代码排序，不能把这些组理解为五个不同正剂量水平。log(1+Hold)系数对应一对数单位，五分位系数对应各组相对最低组，不能直接将点估计大小与每1pp持股的连续剂量系数比较。P99主口径逐股票×事件剔除；任何事件曾超P99即整体删股作为另一固定口径。\n']
 parts+=['## I 指数权重与北向成交剂量赛马\n\n一句结论：仅在真实冻结前指数权重覆盖的晚期子样本估计；本轮未取得可用的个股北向成交额历史。\n\n'+table(I[I.specification.str.contains('weight')],coefcols)+'\n\n'+table(pd.read_csv(R/'tables/I_turnover_dose_status.csv'),['specification','status','n','stocks','events','reason'])+'\n\n最不利事实：权重源仅含2026-05-29以后五个快照，不可用成员虚拟或未来权重冒充全历史权重，完整46段赛马不可估计；可估计的晚期小样本与同样本基准一并列出；有效期货事件若仅1段，事件wild和RI没有通常多冲击推断的支持，不能外推全样本。北向本地源仅有市场合计流量和个股持股；两个公开活跃股接口探测返回报表不存在，不能把十大活跃表未出现股票赋成交额0，也不以持股变化SD冒充成交占比。见I_weight_coverage.csv与meta/northbound_top10_public_probe.json。\n']
 parts+=['## J QFII对照与80% MDE\n\n一句结论：QFII正持股股票×事件支持和交互MDE如下，非显著不能据此断言QFII效应等于零。\n\n'+table(qcov,['metric','n','stocks','events','qfii_known_stock_events','positive_stock_days','positive_mean','positive_sd','p25','p50','p75','p99'])+'\n\n'+table(power,coefcols+['mde80_x100'])+'\n\n最不利事实：QFII源是明确类型的季度十大股东披露代理，有完整最近一期十名披露才把没有QFII记0，其他为缺失。正QFII分布表的Obs是股票×事件数，功效回归表Obs为股票日；MDE=(t.975,df+z.8)×SE为双侧5%下80%功效的近似最小可检测效应，不是事后功效，也不是证明效应落在某等价区间。\n']
 per=pd.read_csv(R/'tables/K_period_reconciliation.csv');race=pd.read_csv(R/'tables/K_cumulative7_event_missingness.csv');miss=race[race.status.ne('OK')];ah=pd.read_csv(R/'tables/K_AH_cluster_counts.csv')
 parts+=['## K 分期、缺失事件与A+H簇数\n\n一句结论：分期和赛马段数逐段核对如下，A+H股票簇与日期簇从实际完整案例样本计数。\n\n'+table(per,['metric','period','n','stocks','events','dates','event_ids'])+'\n\n'+table(miss,['metric','event_id','start','n','stocks','events','baseline_n','eligible_panel_n','raw_metric_n',*[c for c in race if c.startswith('missing_')]])+'\n\n'+table(ah,['metric','n','stocks','events','dates','stock_clusters','date_clusters','joint_unique_cells'])+'\n\n最不利事实：13+19+10=42省略的是2024年1月至8月的3个独立事件（33、34、35），该过渡期既不属于2020–2023，也不属于2024-08-19之后，不能为凑合计并入任一互斥期。cumulative_7完整案例为44段：事件23（2021-10-13）冻结前2021-09-28的BaoStock中证500快照仅返回499行，272按UNEXPECTED_INDEX_COUNT验收失败将csi500整段记缺失；R5按要求复用该冻结控制，基准仍有有效结果但七项完整案例为0；事件46（2026-10-19）没有可用IF/IH期货结果，本来就不在45段基准中。具体缺失字段与事件见K_cumulative7_event_missingness.csv。A+H的69,948是股票日数，不能称独立冲击或聚类数。\n']
 parts+=['## 分布、缩尾与推断完整性\n\n一句结论：新增变量独立实施过去正常日阈值、全三种变换与分布诊断，事件Webb和区组RI沿266/272公式但改本轮种子。\n\n'+table(dist[dist.variant.eq('raw')],['metric','n','stocks','events','missing','mean','sd','skew','excess_kurtosis','zero_share','q001','q01','q99','q999'])+'\n\n最不利事实：新增b系数和调整比例存在重尾，1/99与0.5/99.5阈值也不能消除模型与测量误差；同期控制和假日小组不是新增随机实验。所有CI为双向聚类CI，wild为限制残差绝对系数检验，RI为条件区组日历诊断；完整一页方法见EVENT_WILD_METHOD_R5.md。\n']
 parts+=['## 必报最不利事实\n\n一句结论：最关键的四项约束按估计值、推断和样本支持直接报告。\n\n'+table(ret,['metric','HKonly_x100','HKonly_p','HKonly_wild_p','HKonly_ri_p','HKonly_events','resume0_x100','resume0_p','resume0_wild_p','retained_same_sample_pct','n','stocks','events'])+'\n\n最不利事实：'+drive+'\n\n完整CSV及状态行在tables/；执行`./run_all.sh`从冻结源重建。原266/272以及并行283只读，R5不依赖283。4个重工作进程、数值库单线程，FE拟合以信号量控制并发，聚合RSS监控硬上限4GB；实际峰值和校验状态见meta/final_validation.json。R5大型临时文件完成后仅清理任务284目录。\n']
 (R/'RESULTS_FOR_CLAUDE.md').write_text('\n\n'.join(parts))
 print('FINALIZED',len(est),len(dyn),flush=True)
if __name__=='__main__':main()
