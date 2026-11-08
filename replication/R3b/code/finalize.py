from common import *
from scipy.stats import t as td

def fmt(x):
 if pd.isna(x):return 'NA'
 if isinstance(x,(int,np.integer)):return str(x)
 return f'{x:.6g}' if isinstance(x,(float,np.floating)) else str(x)
def md(f,cols=None):
 if cols:f=f[cols]
 return '| '+' | '.join(f.columns)+' |\n|'+'|'.join(['---']*len(f.columns))+'|\n'+'\n'.join('| '+' | '.join(fmt(v) for v in row)+' |' for row in f.itertuples(index=False,name=None))

def finalize():
 # Preserve event-level missingness with explicit scope labels.
 ledger=pd.read_csv(R/'sample_by_event.csv');ledger['event_outcome_status']=np.where(ledger.rows_1.isna(),'NO_MEASURED_TREATED_OUTCOME',np.where(ledger.rows_0.isna(),'NO_MEASURED_CONTROL_OUTCOME','OK'));ledger.to_csv(R/'sample_by_event.csv',index=False)
 details=pd.read_csv(R/'tables/event_day_details.csv');details['unit']=details.unit.fillna('day');save(details,'event_day_details.csv')
 main=pd.read_csv(R/'tables/main_estimates.csv');joint=pd.read_csv(R/'tables/joint_estimates.csv');fake=pd.read_csv(R/'tables/fake_week_estimates.csv');orig=pd.read_csv(R/'tables/R1_R2_original_benchmarks.csv');counts=pd.read_csv(R/'tables/holiday_counts.csv');event=pd.read_csv(R/'tables/event_tests.csv');allest=pd.read_csv(R/'tables/all_estimates.csv');receipt=pd.read_csv(R/'tables/minute_day_receipts.csv');samples=pd.read_csv(R/'sample_by_event.csv');mde=[]
 for m in PRIMARY:
  h=main[main.group.eq('US')&main.window.eq('r1')&main.exposure.eq('dose')&main.variant.eq('w01')&main.metric.eq(m)].iloc[0];j=joint[joint.group.eq('US')&joint.exposure.eq('dose')&joint.variant.eq('w01')&joint.metric.eq(m)&joint.term.eq('treated_minus_closed')].iloc[0]
  for source in ['R1','R2']:
   b=orig[orig.source.eq(source)&orig.metric.eq(m)&orig.variant.eq('w01')&orig.exposure.eq('dose')].iloc[0];mde.append(dict(metric=m,source=source,holiday_beta=h.beta,holiday_se=h.se,holiday_ci_low=h.ci_low,holiday_ci_high=h.ci_high,holiday_mde80=h.mde80,original_closure_beta=b.beta,original_point_above_holiday_95ci=bool(b.beta>h.ci_high),mde_over_abs_original_beta=h.mde80/abs(b.beta),joint_holiday_beta=j.holiday_beta,joint_closure_beta=j.closed_beta,joint_difference=j.beta,joint_difference_ci_low=j.ci_low,joint_difference_ci_high=j.ci_high,joint_equality_p=j.p,exclude_same_positive_size_joint=bool(j.closed_beta>0 and j.ci_high<0)))
 save(pd.DataFrame(mde),'mde_and_benchmark_comparison.csv')
 if (R/'tables/PRE_CORRECTION_fake_weekday_estimates.csv').exists():
  old=pd.read_csv(R/'tables/PRE_CORRECTION_fake_weekday_estimates.csv');keys=['group','fake','window','metric','variant','exposure','term'];cols=['beta','se','p','wild_p','ri_p','q_bh','p_romano_wolf'];comparison=old[keys+cols].merge(fake[keys+cols],on=keys,how='left',suffixes=('_invalid_before','_corrected_after'),validate='1:1');comparison['beta_change']=comparison.beta_corrected_after-comparison.beta_invalid_before;save(comparison,'precontrol_correction_comparison.csv')
 # Dates with any measured outcome and rows retained are distinct from nominal calendar coverage.
 s=pd.read_csv(R/'tables/sample_by_event_metric.csv');measured=s[(~s.joint)&(~s.fake)&s.rows.gt(0)&s.treated.eq(1)];available=measured.groupby(['group','window','metric'],as_index=False).agg(measured_event_segments=('event_id','nunique'),measured_dates=('dates','sum'),stock_days=('rows','sum'));save(available,'measured_event_counts.csv')
 sampleaudit=dict(stock_universe=len(pd.read_csv(R/'meta/stock_universe.csv')),minute_days=len(receipt),minute_date_min=receipt.date.min(),minute_date_max=receipt.date.max(),minute_rows_scanned=int(receipt.input_rows_scanned.sum()),selected_minute_rows=int(receipt.selected_minute_rows.sum()),duplicate_minute_keys=int(receipt.duplicate_minute_keys.sum()),outcome_end='2026-09-01',estimates=len(allest),main=len(main),joint=len(joint),fake=len(fake),seed=SEED,requested_bootstrap_B=B)
 js(R/'meta/final_counts.json',sampleaudit)
 core=main[main.group.eq('US')&main.window.eq('r1')&main.exposure.eq('dose')&main.variant.eq('w01')].copy();core=core.set_index('metric').reindex(PRIMARY).reset_index();binary=main[main.group.eq('US')&main.window.eq('r1')&main.exposure.eq('eligible')&main.variant.eq('w01')];sensitivity=main[main.group.eq('US')&main.window.eq('r1')&main.exposure.eq('dose')&~main.variant.eq('w01')];regional=main[main.exposure.eq('dose')&main.variant.eq('w01')&main.window.eq('r1')];weekday=main[main.exposure.eq('dose')&main.variant.eq('w01')&main.window.eq('weekday')];jcore=joint[joint.group.eq('US')&joint.exposure.eq('dose')&joint.variant.eq('w01')&joint.term.eq('treated_minus_closed')];fcore=fake[fake.exposure.eq('dose')&fake.variant.eq('w01')&fake.window.eq('r1')];ecore=event[event.group.eq('US')&~event.fake&event.window.eq('r1')&event.variant.eq('w01')];bench=orig[orig.variant.eq('w01')&orig.exposure.eq('dose')]
 vals=core[['metric','beta','ci_low','ci_high','p','wild_p','ri_p','q_bh','p_romano_wolf','mde80','n','stocks','dates']];peak=json.loads((R/'logs/resource_peak.json').read_text())
 placebo=pd.read_csv(R/'tables/R1_placebo_estimates.csv');ps=placebo[placebo.metric.isin(PRIMARY)&placebo.variant.eq('w01')]
 cc=core.set_index('metric')
 lead=f"美国主组两项价格延迟系数分别为{fmt(cc.loc['if_delay','beta'])}（IF）与{fmt(cc.loc['ih_delay','beta'])}（IH），双向聚类p分别{fmt(cc.loc['if_delay','p'])}、{fmt(cc.loc['ih_delay','p'])}。滞后1–5分钟系数和分别为{fmt(cc.loc['if_lag_sum','beta'])}、{fmt(cc.loc['ih_lag_sum','beta'])}，四指标族BH q分别{fmt(cc.loc['if_lag_sum','q_bh'])}、{fmt(cc.loc['ih_lag_sum','q_bh'])}。四项结果不一致，不能把延迟两项的近零点估计概括为所有主指标都没有欧美假日关联。"
 text='''# R3b 欧美假日机制补充：统计结果

本文件仅交付统计核数、估计及其限制，不是论文正文或审稿意见。种子20261116；预注册SHA与首次估计时间见meta/preregistration_lock.json。

估计后更正：最终检查剔除6个只有事后对照的假事件同星期窗口，避免冻结日晚于假事件；US/UK/ALL的72行已重估。原预注册保持锁定，这项实现更正不冒充事前注册。真实假日主估计及联合比较不变；旧错误版本和新旧对照完整保留，见[更正说明](AMENDMENT_R3b_POST_ESTIMATION.md)、stack_window_rejections.csv及PRE_CORRECTION_fake_weekday_estimates.csv。

## 1. 核数

'''+md(counts)+f'''\n\n三地区并集去重；地区间可重合，“独有”指A股、港股、北向均照常开放。美国主组不含感恩节次日或哥伦布日。英国England/Wales口径，2020、2022年改期已处理。每类逐日保留/剔除与原因在holiday_calendar_audit.csv，地区重合在holiday_overlap.csv。静态日历的恶劣天气遗漏已按港交所13个全日/部分中断公告（其中12日在原静态日历仍记北向开放）剔除，见HKEX_nonfull_day_audit.csv；2023-10-09哥伦布日因香港延迟开市而不合格。历史缩尾正常日仍沿R1原标记，保持其冻结口径。

股票总体{sampleaudit['stock_universe']}只；按日扫描{sampleaudit['minute_days']}个A交易日，原始分钟行{sampleaudit['minute_rows_scanned']:,}，所选股票分钟行{sampleaudit['selected_minute_rows']:,}，重复键{sampleaudit['duplicate_minute_keys']}。指标日仍须上市满60交易日、非ST、至少180有效分钟、非一字价、正成交额。IF/IH原始期货指标最晚2026-09-01；2026-09-30是登记日历终点，不冒称全月可估。实际有效处理日/段数如下。

'''+md(available[available.window.eq('r1')],['group','metric','measured_event_segments','measured_dates','stock_days'])+'''

各组每个事件×指标的处理/对照股票日、股票数与日期数在sample_by_event.csv；sample_by_event_metric.csv含同框架联合样本。冻结日在未去重窗口最早对照日，资格和持股信息严格事前；2024-08-19后按季末披露时点处理。raw、1/99、0.5/99.5阈值均沿R1过去正常日扩展窗/冻结前池化后备阈值。四指标构造与筛选在实分钟28个股票日逐项比对R1最大差0，FE及双向聚类与显式虚拟变量OLS的唯一单元/重复堆叠样本对照见four_metric_reuse_checks.csv及linear_algebra_checks.csv。

CCASS替代剂量跳过：原QDC只有港股汇总CCASS持股，没有可冻结的北向A股参与者托管行分类；不能识别“事前北向持股中的外资机构托管行份额”。逐文件字段及样例见meta/ccass_audit.json，状态见custodian_specification_status.csv。

## 2. 主估计

股票FE、日期FE、冻结暴露水平及处理×暴露；剂量系数单位为每1pp。下表美国主组、R1前后各5正常日、1/99。价格延迟是无量纲；滞后和系数×100表示期货变动1%时后1–5分钟的bp响应变化，不能解释为永久未吸收比例。

'''+lead+'\n\n'+md(vals)+'''

四指标分别构成每组×窗口×暴露×变换的BH与Romano–Wolf族；后者使用共同Webb权重、固定双向SE，不是studentized wild-t。wild为事件段限制残差、绝对系数统计量。RI严格保留同年、同月、同星期、相同连续A交易日段长、正常北向/A港全日开放、实际窗口内及无重叠规则；无支持记NA，不放宽。RI可用次数与独立日历数、逐段候选在randomization_support.csv及各估计行。9999重复不等于9999独立日历。

美国主组资格二值（1/99，标的−非标的）：

'''+md(binary,['metric','beta','se','p','wild_p','ri_p','q_bh','p_romano_wolf'])+'''

美国主组剂量的另外两种缩尾：

'''+md(sensitivity,['metric','variant','beta','se','p','wild_p','q_bh','p_romano_wolf'])+'''

地区、半日和哥伦布日的同口径剂量估计：

'''+md(regional,['group','metric','beta','se','p','wild_p','ri_p','q_bh','p_romano_wolf','mde80'])+'''

同星期前后1–3周正常日堆叠（股票FE与日历日期FE；股票×日期重复交集先聚合再作双向聚类；同一日期不视为独立）：

'''+md(weekday,['group','metric','beta','se','p','wild_p','ri_p','q_bh','p_romano_wolf','mde80'])+'''

全部三变换×剂量与资格二值见main_estimates.csv；资格项是标的−非标的，单位不是1pp。跨全部主1/99剂量规格的BH/RW另有q_bh_all_main_w01与p_rw_all_main_w01；不能只选择某地区、窗口或缩尾。distributions.csv保留均值/SD/偏度/峰度与尾部分位，winsor_audit.csv保留缩尾与后备阈值数。

事件段/逐处理日：先对冻结剂量五分位算处理−正常差，再取最高−最低五分位；事件段等权双侧t和精确符号检验。逐日结果也报告，但连续段内日期相关，不能用日数冒充独立事件段。

'''+md(ecore,['metric','unit','n','mean','se','p_t','p_sign','mde80'])+'''

## 3. 与R1/R2北向关闭系数的对比

原基准保持原种子与原终点，不对不同样本点估计直接作相等检验；R1与R2基准交互项在1/99四指标上数值一致，两表不是独立证据：

'''+md(bench,['source','metric','beta','se','p','wild_p','ri_p','n','dates'])+'''

正式相等检验使用同一回归：关闭窗口与欧美窗口合并，真实处理优先、其余按最近段首去重，每股每日期唯一；加入两种处理×暴露及冻结暴露水平。美国1/99剂量如下，difference=欧美−关闭；其p检验两系数相等，wild对该线性限制重新限制残差。原R1/R2比本样本更长，联合关闭系数改变不是原结果复算失败。

'''+md(jcore,['metric','holiday_beta','closed_beta','beta','se','p','wild_p','q_bh','p_romano_wolf','ci_low','ci_high','ratio','ratio_ci_low','ratio_ci_high','fieller_status','fieller_low','fieller_high'])+'''

比值为欧美/关闭，delta 95%区间与Fieller集合同时报告；Fieller无界时不能仅按delta区间判断。BOUNDED表示[low,high]，EXTERIOR_UNBOUNDED表示(-∞,low]∪[high,∞)，ALL_REAL表示全实数。所有地区、资格二值与三变换在joint_estimates.csv。两种交互分别报告双向/wild与条件RI（另一交互固定）；差的RI无精确日历设计，明确记NO_EXACT_EQUALITY_CALENDAR_DESIGN，不伪造相等假设的随机化p。

80%功效、双侧5%近似设计MDE=(t.975,df+z.8)×SE；逐指标与原关闭点估计、联合相等检验比较：

'''+md(pd.DataFrame(mde),['metric','source','holiday_mde80','original_closure_beta','mde_over_abs_original_beta','original_point_above_holiday_95ci','joint_equality_p','exclude_same_positive_size_joint'])+'''

original_point_above_holiday_95ci只比较原基准点值，忽略其估计误差；exclude_same_positive_size_joint要求联合差的95%CI全低于0，才表示排除“欧美与关闭一样大”。这些95%差区间与排除标记均为逐指标、名义5%判断；四指标多重调整的相等检验另看联合表q_bh与p_romano_wolf。MDE不是实际为零的证明，也不是事后功效。

## 4. 安慰剂

欧美提前一周、同星期且正常开放的假事件，不搜索替代日期；冻结与阈值重做。下表1/99、剂量、R1窗口；全部暴露/缩尾/两窗口在fake_week_estimates.csv，逐真/假事件支持在fake_week_support.csv；无事前对照的6个同星期窗口列于stack_window_rejections.csv，修正前后72行对照见precontrol_correction_comparison.csv，旧版含前视错误，不作为有效稳健性证据。

'''+md(fcore,['group','metric','beta','se','p','wild_p','ri_p','q_bh','p_romano_wolf'])+'''

R1 A港共同假日前后正常日与北开南闭安慰剂原数重报，保留种子20261110；不是本任务重算。这部分依赖有香港/南向标记的2023–2026日历，沿用R1静态日历，不能视为全2017–2026时期或经过本轮天气净化的新复制。完整表R1_placebo_estimates.csv与R1_placebo_event_dates.csv。四指标1/99记录如下：

'''+md(ps,[x for x in ['kind','metric','exposure','beta','se','p','wild_p','ri_p'] if x in ps.columns])+'''

## 5. 最不利事实

'''
 facts=[]
 facts.append('英国仅22日、欧陆仅18日，均低于30日目标；半日9日、哥伦布日8日，单列估计精度有限，不能靠并入主样本增加显著性。')
 facts.append('欧美公休日只是人员可能休假的代理，没有交易员/基金经理真实在场或假期排班。欧美总部、香港执行台和算法可替代；欧美与中国日期的时差也使冲击不精确。不显著最多约束该代理冲击，不能完全排除注意力机制。')
 facts.append('Ascension/Whit Monday并非欧洲所有国家都放假，也不等于主要交易所全部关闭；Euronext等市场可照常交易。英国普通银行假日也不保证所有雇主让员工休假。参见[英国政府](https://www.gov.uk/bank-holidays)、[法国官方假日说明](https://www.service-public.gouv.fr/particuliers/vosdroits/F2405?lang=en)及[Euronext交易日历](https://www.euronext.com/en/trade/trading-hours-holidays)。')
 facts.append('哥伦布日美股通常仍交易，感恩节次日也只是提前收市，均不是完整市场关闭冲击。其单列结果不可与美国主组等量解释；参见[NYSE官方日历](https://www.nyse.com/trade/hours-calendars)。')
 facts.append('欧美假日还可能改变全球消息、期货波动及流动性；日期FE吸收共同冲击，不能排除这些冲击随持股暴露不同而异。正系数本身不能把人员在场与其他异质全球冲击分离。')
 facts.append('美国纪念日常与英国春季银行假日或欧陆圣灵降临重合；美国主组不是相对于英国/欧陆的纯独有日。地区系数和合并系数也不是相互独立的证据。')
 facts.append('原始IF/IH仅到2026-09-01；美国2026-09-07劳工节无法构造主结果，不能把58个日历处理日全部视为58个有效结果日。缺数据记录不填零；只有正常对照观测的晚期事件仍可能进入面板，其wild簇数不等于有处理结果的事件数。')
 facts.append('持股剂量不区分美国、英国、欧陆、香港及其他地区投资者，无法直接测量真正受该假日影响的持股份额。MDE是对总体北向剂量的效应界限；代理稀释下的小系数不能完全排除人员机制。')
 facts.append('事前持股在2024-08-19后季频披露，暴露更陈旧；无托管参与者分类，无法把境外机构与其他北向持有人区分。R1股票总体和上市年龄代理本身的限制也随复用保留。')
 for r in core.itertuples():
  j=jcore[jcore.metric.eq(r.metric)].iloc[0];facts.append(f'{r.metric}：美国主组MDE={fmt(r.mde80)}每1pp；联合关闭系数={fmt(j.closed_beta)}，欧美−关闭95%CI=[{fmt(j.ci_low)}, {fmt(j.ci_high)}]，相等p={fmt(j.p)}。'+('可在5%双侧水平排除同样大的正效应。' if j.closed_beta>0 and j.ci_high<0 else '不能在5%双侧水平排除与关闭一样大；是否偏离0另看主估计与多重调整。'))
 bad=fcore[fcore.p.lt(.05)|fcore.wild_p.lt(.05)|fcore.ri_p.lt(.05)]
 if len(bad):facts.append('提前一周假事件存在至少一种原始推断p<0.05的记录：'+ '；'.join(f'{r.group}/{r.metric} β={fmt(r.beta)},双向p={fmt(r.p)},wild={fmt(r.wild_p)},RI={fmt(r.ri_p)}' for r in bad.itertuples())+'。必须连同多重调整与真事件结果报告，不能宣称所有安慰剂通过。')
 else:facts.append('提前一周假事件在主1/99剂量/R1窗口没有三种原始p<0.05记录；该结果仍不能证明排除季节性或漏掉的全球消息。')
 no=allest[allest.ri_B.fillna(0).eq(0)&allest.term.ne('treated_minus_closed')];facts.append(f'严格区组RI有{len(no)}条估计没有可用置换；其NA不能作不显著。wild是非studentized的限制残差系数检验，与双向t及区组RI的零假设和有限样本性质不同；小事件组须优先保留最保守结果。')
 facts.append(f"美国滞后和并非近零：IF β={fmt(cc.loc['if_lag_sum','beta'])}、IH β={fmt(cc.loc['ih_lag_sum','beta'])}，均为正且高于原关闭点估计；BH q分别{fmt(cc.loc['if_lag_sum','q_bh'])}、{fmt(cc.loc['ih_lag_sum','q_bh'])}。联合回归滞后和比值的Fieller集合无界，相等检验未能在5%水平拒绝；不能写成四项一致的纯通道证据。")
 facts.append('美国两项滞后和在事件等权的t检验中为正，但符号检验p分别约0.0627与0.111；标的二值的两项滞后和也未通过四指标BH。IH delay的事件符号检验则检出负方向。这些规格不能概括为所有检验一致。')
 facts.append('事后完整性检查发现6个假事件同星期窗口没有事前对照，初版存在冻结时点向前赋值错误；已剔除并重跑72行，旧版完整存档。此更正在观察主结果后发生，不能声称所有交付口径均为事前注册。')
 facts.append('哥伦布日提前一周的日期全部处于A股国庆休市期，没有合格假事件；对应48个回归规格保留NO_VALID_EVENTS，不把NA说成通过安慰剂。')
 facts.append('预定清单未纳入美国退伍军人节、英国王室葬礼/加冕特别银行假日。附加核查发现它们出现在若干假事件和同星期控制窗，见unregistered_holiday_control_audit.csv；这是名义日期审计，不是股票日权重。已知名单没有命中美国真事件R1主窗口，但本核查不是所有国家假日的穷尽检查。')
 facts.append('历史缩尾正常日标记按用户要求复用R1，仍含原静态日历没有识别的恶劣天气日；新欧美处理和对照已剔除这些日期，不能把新旧样本日历质量视为完全一致。')
 single=allest[allest.ri_B.fillna(0).gt(0)&allest.ri_unique.eq(1)]
 if len(single):facts.append(f'{len(single)}条回归的RI只有1个独立日历；9999次重复不会增加独立支持，也不能据此宣称0.0001的精确随机化分辨率。这类p仅是R1口径的条件正常日日历诊断。')
 facts.append('五分位同剂量取值按代码打破平局；低分位可能大量零持股。事件高低组差与每1pp连续剂量不是同一估计量。堆叠窗的重复日期及不同冻结暴露增加依赖，独立事件段wild权重也不能完整保留重叠日期的共同冲击，事件段和逐日t不能互换。')
 text+='\n'.join(f'{i+1}. {fact}' for i,fact in enumerate(facts))
 resource=json.loads((R/'meta/resource_summary.json').read_text());recorded_peak=resource['recorded_peak_gb']
 text+=f'''\n\n## 6. 文件与复现

`bash run_all.sh`一键运行。全部中间面板与重抽样在/Volumes/Extreme SSD/T9/_tmp/282；原始A股分钟ZIP、QDC以及CFFEX.7z只读。进程池4个worker，宽面板最多同时驻留2项、数值库线程1；4GB预算，3.7GB熔断。最近阶段记录峰值{fmt(peak['peak_gb'])}GB；资源重启和实现说明在meta/implementation_notes.md。初版读取曾触发内存熔断；早期后台辅助暴露构建未计入阶段监控，因此不能声称早期全过程低于4GB。已改为阶段顺序执行、全任务RSS监控及65536行日流式矩阵读取，恢复四日并行；5183个后段股票日与原实现的四指标及筛选最大差0。采样监控记录的峰值至少{fmt(recorded_peak)}GB，严格全程峰值因早期监控范围不完整而不可重建；因此4GB全程上限未满足。详情见meta/resource_summary.json及实现记录；没有按系数或显著性修改规格。

预注册、源码摘要、输入摘要、所有估计状态、事件样本、日历与来源均可独立检查。CSV的NA表示缺数据/无支持/协方差不可用，具体看status或ri_status；不是零。最终结构与数值核数见meta/final_validation.json。
'''
 (R/'RESULTS_FOR_CLAUDE.md').write_text(text)
 # Explicit mechanism evidence classification without conflating a null proxy with a causal verdict.
 summary=[]
 for r in core.itertuples():
  j=jcore[jcore.metric.eq(r.metric)].iloc[0];summary.append(dict(metric=r.metric,holiday_beta=r.beta,p_two_way=r.p,p_wild=r.wild_p,p_ri=r.ri_p,mde80=r.mde80,positive_three_inference=(bool(r.beta>0 and r.p<.05 and r.wild_p<.05 and r.ri_p<.05) if np.isfinite([r.p,r.wild_p,r.ri_p]).all() else None),RI_status=r.ri_status,joint_excludes_equal_size=bool(j.closed_beta>0 and j.ci_high<0)))
 save(pd.DataFrame(summary),'mechanism_evidence_summary.csv');print('FINALIZED',flush=True)
if __name__=='__main__':finalize()
