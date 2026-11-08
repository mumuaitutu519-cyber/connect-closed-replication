import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[k]='1'
from pathlib import Path
import json,hashlib,datetime,shutil
import numpy as np,pandas as pd,pyarrow as pa,pyarrow.dataset as ds
from estimate import ROOT,TMP,PRIMARY,METRICS
pa.set_cpu_count(1);pa.set_io_thread_count(1)
NAMES={'cs_bp':'CS价差代理(bp)','ar_bp':'AR价差代理(bp)','vr5':'5分钟方差比','autocorr1':'分钟收益自相关','amihud':'Amihud(每百万元)','if_lag_sum':'IF滞后1–5分钟系数和','if_delay':'IF价格延迟','ih_lag_sum':'IH滞后1–5分钟系数和','ih_delay':'IH价格延迟','open30_bp':'开盘30分钟收益(bp)','ln_amount':'log成交额','ln_volume':'log成交量','return_bp':'日内开收盘收益(bp)','rv_bp2':'日内已实现方差(bp²)','zero_return_share':'零收益分钟占比'}
def md(f):return f.to_markdown(index=False,floatfmt='.6g')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 main=pd.read_csv(ROOT/'tables/main_estimates.csv');mech=pd.read_csv(ROOT/'tables/mechanism_estimates.csv');placebo=pd.read_csv(ROOT/'tables/placebo_estimates.csv');dynamic=pd.read_csv(ROOT/'tables/dynamic_estimates.csv');cal=pd.read_csv(ROOT/'tables/official_calendar.csv',parse_dates=['date']);ev=pd.read_csv(ROOT/'tables/events.csv',parse_dates=['start','end','resume']);core=ds.dataset(TMP/'panel',format='parquet').to_table(columns=['code','date','event_id','closed','dose','eligible','freeze_date','holding_date','available_date','frequency','amount','pre60_normal_amount'],use_threads=False).to_pandas(use_threads=False)
 independent=pd.read_csv(ROOT/'logs/inference_independent_checks.csv');assert independent.pass_.all();runtime=json.loads((ROOT/'meta/runtime.json').read_text());assert all(v=='1' for v in runtime['numeric_threads'].values())
 inputs=json.loads((ROOT/'meta/input_manifest.json').read_text())
 for stem in ['mechanism','dynamic','placebo']:
  for metric in PRIMARY+['ln_amount','ln_volume','return_bp']:
   old=ROOT/f'tables/{stem}_{metric}.csv'
   if old.exists():old.unlink()
 for metric in METRICS:
  path=ROOT/f'tables/distribution_{metric}.csv';distribution=pd.read_csv(path);distribution['pearson_kurtosis']=distribution.excess_kurtosis+3;distribution.to_csv(path,index=False)
 pd.concat([pd.read_csv(ROOT/f'tables/distribution_{metric}.csv') for metric in METRICS],ignore_index=True).to_csv(ROOT/'tables/distributions.csv',index=False)
 assert not core.duplicated(['code','date']).any();assert core.date.max()<=pd.Timestamp('2026-11-07');assert (core.freeze_date<=core.date).all();known=core.available_date.notna();assert (core.loc[known,'available_date']<core.loc[known,'freeze_date']).all()
 caps=pd.read_parquet(TMP/'pre_cap.parquet');core=core.merge(caps,on=['event_id','code'],how='left',validate='m:1');assert (core.loc[core.cap_observation_date.notna(),'cap_observation_date']<core.loc[core.cap_observation_date.notna(),'freeze_date']).all()
 samples=[]
 for r in ev.itertuples():
  d=core[core.event_id.eq(r.event_id)];closed=d[d.closed];normal=d[~d.closed];stock=d.drop_duplicates('code');samples.append(dict(event_id=r.event_id,start=r.start,end=r.end,resume=r.resume,official_closed_days=r.n_closed_days,observed_closed_days=closed.date.nunique(),normal_control_days=normal.date.nunique(),stocks=d.code.nunique(),eligible_stocks=int(stock.eligible.sum()),positive_dose_stocks=int(stock.dose.gt(0).sum()),known_dose_stocks=int(stock.dose.notna().sum()),stock_days=len(d),closed_stock_days=len(closed),normal_stock_days=len(normal),holding_frequency=','.join(sorted(stock.frequency.unique())),source_url=r.source_url))
 sample=pd.DataFrame(samples);sample.to_csv(ROOT/'tables/sample_by_event.csv',index=False)
 counts=pd.read_csv(ROOT/'logs/metric_daily_build.csv');held=pd.read_csv(ROOT/'tables/holding_coverage_by_date.csv');inventory=json.loads((ROOT/'meta/data_inventory.json').read_text());scale=[('已确认北向关闭且A股开市日',int(cal.closed.sum()),'days'),('独立连续关闭事件段',len(ev),'episodes'),('主窗口日期',core.date.nunique(),'dates'),('主窗口股票',core.code.nunique(),'stocks'),('主窗口有效股票×日期',len(core),'stock_days'),('主窗口正剂量股票',core.loc[core.dose.gt(0),'code'].nunique(),'stocks'),('主窗口剂量缺失股票×日期',int(core.dose.isna().sum()),'stock_days'),('本轮处理分钟原始行数',int(counts.selected_minute_rows.sum()),'minute_rows'),('本轮股票×日期指标行数',int(counts.stock_days.sum()),'stock_days_before_eligibility'),('可用持股记录日期',len(held),'disclosure_dates'),('本地cn_tick库存行数(2016起，仅库存核查)',sum(r['rows'] for r in inventory if r['dataset']=='cn_tick'),'tick_rows_not_estimation_rows'),('原始分钟重复键',int(counts.duplicate_minute_keys.sum()),'rows'),('原始盘口报价字段',0,'quote_fields')]
 pd.DataFrame(scale,columns=['measure','value','unit']).to_csv(ROOT/'tables/data_scale.csv',index=False)
 balance=[];units=core.drop_duplicates(['event_id','code'])
 for exposure in ['eligible','dose']:
  if exposure=='eligible':treated=units.eligible.eq(1);control=units.eligible.eq(0)
  else:
   med=units[units.dose.gt(0)].groupby('event_id').dose.median();treated=units.dose.gt(0)&units.dose.ge(units.event_id.map(med));control=units.dose.eq(0)
  variables={'北向持股比例(pp)':units.dose,'事前60正常日成交额log':np.log(units.pre60_normal_amount.where(units.pre60_normal_amount>0)),'事前流通市值log':np.log(units.circulating_market_cap.where(units.circulating_market_cap>0))}
  for name,x in variables.items():
   a=x[treated].dropna();b=x[control].dropna();den=np.sqrt((a.var()+b.var())/2);balance.append(dict(exposure=exposure,variable=name,n_treated=len(a),n_control=len(b),mean_treated=a.mean(),mean_control=b.mean(),sd_treated=a.std(),sd_control=b.std(),standardized_difference=(a.mean()-b.mean())/den if den>0 else np.nan,grain='unique stock x event; all measures fixed before earliest control day'))
 pd.DataFrame(balance).to_csv(ROOT/'tables/balance.csv',index=False)
 # Actual coverage by metric and exposure, not the nominal universe.
 main[main.variant.eq('w01')][['metric','exposure','n','stocks','dates','wild_clusters','ri_B']].to_csv(ROOT/'tables/metric_coverage.csv',index=False)
 dictionary=[]
 for m in METRICS:dictionary.append(dict(metric=m,label=NAMES[m],primary_family=m in PRIMARY,unit='bp' if m.endswith('_bp') else ('dimensionless' if m not in ['amihud','rv_bp2'] else ('absolute log return per RMB million' if m=='amihud' else 'bp squared')),source='original day OHLCV; QDC day fallback after 2026-04-10; IF/IH actual contracts for futures outcomes'))
 pd.DataFrame(dictionary).to_csv(ROOT/'tables/outcome_dictionary.csv',index=False)
 pd.DataFrame([dict(exposure='dose',source_field='QDC cn_hsgt/hk_hold ratio',unit='reported percent; coefficient per percentage point',denominator='HKEX displayed total A shares listed and traded on the relevant SSE/SZSE market; not necessarily total company issued shares or free float',timing='publicly available before earliest control day; daily before 2024-08-19 and quarterly afterwards',limitation='Historical vendor values not individually reverified; absent non-eligible stock record set to zero, eligible stock with missing snapshot stays missing; HKEX denominator may lag corporate actions',official_definition='https://www3.hkexnews.hk/sdw/mutualmarket/SZ.htm'),dict(exposure='eligible',source_field='official historical eligibility changes',unit='1=buy-eligible before freeze; 0=otherwise',denominator='not applicable',timing='effective date strictly before earliest control day',limitation='Sell-only stocks can still have positive holdings; binary control does not mean zero foreign access')]).to_csv(ROOT/'tables/exposure_dictionary.csv',index=False)
 unavailable=pd.DataFrame([dict(specification='Hang Seng minute response',status='UNAVAILABLE',reason='Located A-share index minutes and global daily indices; no verified historical Hang Seng minute source located; Hong Kong holiday returns never zero-filled'),dict(specification='True effective bid-ask spread and order-book depth',status='UNAVAILABLE_REPLACED_AS_REGISTERED',reason='cn_tick has code/date/seq/minute/price/volume/bs only, no bid/ask/depth; CS/AR and Amihud are proxies, not measured quoted/effective spreads')]);unavailable.to_csv(ROOT/'tables/unavailable_specifications.csv',index=False)
 # Per-event official source receipt with the original time precision preserved.
 receipts=json.loads((ROOT/'meta/official_receipts.json').read_text());lookup={r['url']:r for r in receipts if r.get('status')==200};source=[]
 for r in cal[cal.closed].itertuples():
  rr=lookup.get(r.source_url,{})
  source.append(dict(event_date=r.date,original_time_value=str(r.date.date()),original_time_precision='calendar day; all-day northbound unavailability',original_northbound_flag='Closed' if str(r.source_file).endswith('.csv') else r.nb_original_flag,source_url=r.source_url,retrieved_utc=rr.get('retrieved_utc'),source_sha256=rr.get('sha256'),event_timezone='Asia/Shanghai / Asia/Hong_Kong, UTC+08:00',analysis_continuous_session_start='09:30:00+08:00',intraday_closure_announcement_timestamp='not applicable: scheduled all-day closure; no intraday timestamp invented'))
 pd.DataFrame(source).to_csv(ROOT/'meta/event_time_provenance.csv',index=False);assert pd.DataFrame(source).retrieved_utc.notna().all()
 algebra=pd.concat([pd.read_csv(p) for p in (ROOT/'logs').glob('fe_quadratic_checks_*.csv')],ignore_index=True);algebra.to_csv(ROOT/'logs/fe_quadratic_checks_all.csv',index=False);assert algebra.abs_difference.max()<1e-6
 assert len(main)==len(METRICS)*2*3;assert not main.duplicated(['metric','variant','exposure']).any();assert main.n.gt(0).all();assert np.all(main.df==np.minimum(main.stocks,main.dates)-1);assert main.wild_B.eq(9999).all();assert main.ri_B.eq(9999).all();assert sample.observed_closed_days.sum()==int(cal.closed.sum())
 primary=main[main.variant.eq('w01')&main.metric.isin(PRIMARY)].copy();primary['指标']=primary.metric.map(NAMES);primary['暴露']=primary.exposure.map({'dose':'持股每1pp','eligible':'北向标的=1'});primary['95%区间']=[f'[{l:.6g}, {h:.6g}]' for l,h in zip(primary.ci_low,primary.ci_high)]
 view=primary[['指标','暴露','beta','95%区间','p','wild_p','ri_p','q_primary_family']]
 raw=main[main.variant.eq('raw')&main.metric.isin(PRIMARY)][['metric','exposure','raw_interaction_ols','beta']].rename(columns={'beta':'raw_FE_beta'});raw=raw.merge(main[main.variant.eq('w01')][['metric','exposure','beta']],on=['metric','exposure']).rename(columns={'beta':'w01_FE_beta'});raw['指标']=raw.metric.map(NAMES);raw['暴露']=raw.exposure.map({'dose':'持股每1pp','eligible':'北向标的=1'});raw=raw[['指标','暴露','raw_interaction_ols','raw_FE_beta','w01_FE_beta']]
 pc=placebo[placebo.variant.eq('w01')&placebo.term.eq('placebo_x')&placebo.exposure.eq('dose')&placebo.metric.isin(PRIMARY)].copy();pc['指标']=pc.metric.map(NAMES);pcview=pc[['placebo','指标','beta','ci_low','ci_high','p','wild_p','ri_p','ri_B','independent_placebo_days','independent_placebo_episodes']]
 recovery=mech[mech.specification.eq('reopening_joint_with_closure')&mech.term.eq('resume_x')][['metric','exposure','beta','ci_low','ci_high','p','n','dates']]
 reversal=mech[mech.specification.eq('closed_cumulative_to_reopen_intraday_association')&mech.term.isin(['cum_x','closed_cum_bp'])][['exposure','term','beta','ci_low','ci_high','p','n','dates']]
 support=json.loads((ROOT/'meta/resampling_status.json').read_text());fu=pd.read_csv(ROOT/'tables/futures_coverage.csv');resources=[]
 for p in [ROOT/'logs/resource_monitor.jsonl',ROOT/'logs/daily_resource_monitor.jsonl',ROOT/'logs/active_resource_watchdog.jsonl',ROOT/'logs/pipeline_memory.jsonl']:
  if p.exists():
   for l in p.read_text().splitlines():
    try:r=json.loads(l);resources.append(r.get('aggregate_rss_gb',r.get('rss_gb',r.get('rss',0)/1e9)))
    except:pass
 resource_peak=max(resources or [0]);significant=int(primary.q_primary_family.lt(.05).sum());dosecore=primary[primary.exposure.eq('dose')]
 lookup_main=main[main.variant.eq('w01')&main.exposure.eq('dose')].set_index('metric');amount_effect=100*np.expm1(lookup_main.loc['ln_amount','beta']);if_effect=lookup_main.loc['if_delay','beta'];ih_effect=lookup_main.loc['ih_delay','beta']
 pc_lookup=placebo[placebo.variant.eq('w01')&placebo.term.eq('placebo_x')&placebo.exposure.eq('dose')&placebo.placebo.eq('joint_holiday_adjacent')].set_index('metric');placebo_vr=pc_lookup.loc['vr5'];placebo_ac=pc_lookup.loc['autocorr1']
 # All registered specifications appear, including unavailable measurements.
 registry=pd.concat([main.assign(specification_class='main'),mech.assign(specification_class='mechanism',variant='w01'),dynamic.assign(specification_class='dynamic',variant='w01'),placebo.assign(specification_class='placebo'),unavailable.assign(specification_class='availability')],ignore_index=True);registry.to_csv(ROOT/'tables/specification_registry_results.csv',index=False)
 report=f'''# 266 北向关闭而A股开市：第一轮统计结果

执行日：2026-11-07；随机种子：20261110。只交统计、数据核数和可复现代码，不含稿件或审稿意见。**预注册的90行主估计已完成**（10个核心指标+5个辅助指标 × 2种暴露 × 3种缩尾）。小效应和不显著结果全部保留。

## 1. 查重结论

未确认已有“北向日历关闭 × 事前北向持股比例”的同设计论文，故没有触发停止条件。近10篇的样本、设计、结论、同设计判断及额外近邻在 `meta/lit_check.md`；查询原响应、抓取UTC、HTTP状态和SHA256均保留。SSRN直接检索403、部分期刊全文不可读，结论以可读取原始摘要/正文为界，不能据此声称穷尽所有工作论文。Zhang（JBF 2025）已使用非重叠假期研究日本市场质量，是识别逻辑上的明确近邻。

## 2. 核数表与数据能否支撑

{md(pd.DataFrame(scale,columns=['核数项','值','单位']))}

样本行情日期：2017-01-03至2026-10-30，2026不是完整年度。已确认92个关闭日，分属46个独立连续事件段；不能把数百万股票×日当作数百万独立外资缺席冲击。逐事件股票数、剂量覆盖、样本行数和官方URL在 `tables/sample_by_event.csv`；按指标/暴露的实际股票、日期和行数在 `tables/metric_coverage.csv`。沪深原始标的变更按生效日前重建，未把今天名单回填到历史。

主样本：股票与日期去重；至少180个有效分钟、上市/首个可见交易日至少60个A股交易日、剔除历史ST区间与全天一字价日。持股和资格在每个事件最早对照日前冻结。每日持股仅在次日之后使用；2024-08-19后，只接受季末数据，并按官方“季末后第5个北向交易日公布”规则，再延后一日使用。日频与季频分开标记；缺失的标的股持股不强填零。主模型同时放入时变剂量水平项。

剂量沿用供应库ratio（%），分母按港交所列示的上市交易A股数口径解释，不能当作公司全部已发行股或自由流通股占比；原始定义网页和回执已保存，见 `tables/exposure_dictionary.csv`。非标的且无当期持股记录按0处理；非标的若有当期持股仍使用该值，标的缺失记录保留缺失。

{md(fu[['product','dates','usable_dates','date_min','date_max','missing_selected_contract_days']])}

IF/IH使用前一交易日成交量最高的真实合约，未用当日未来成交量选主力。源文件bob是分钟起点，统一向后移1分钟，与股票分钟终点对齐；午休两侧不串联。期货到2026-09-01为止，2026-10事件没有期货结果。恒生分钟未取得，不将休市缺值填零。cn_tick虽有逐笔成交库存，但没有买卖报价或深度字段，不能支持真实有效价差与盘口深度。CS/AR是分钟OHLC代理，Amihud是成交冲击代理。

数据支持股×日流动性代理、分钟方差比/自相关、IF/IH滞后反应、开盘30分钟收益及恢复日交易量；不能支持“全体外资完全退出”或实测盘口深度的结论。两分钟数据版本并非逐行完全相同，抽样源核验在 `logs/cross_source_minute_checks.csv` 与 `logs/minute_alignment_source_audit.csv`，不代表全库逐分钟复核。主链优先使用既有按日原始分钟档案至2026-04-10，后段用QDC按日读取；换源限制保留。

## 3. 原始差与完整主估计

连续剂量每高1个百分点，关闭日成交额相对变化为{amount_effect:.3f}%；IF/IH延迟指标分别增加{if_effect:.6f}/{ih_effect:.6f}。CS、AR和Amihud的连续剂量主规格95%区间均跨零，流动性代理没有一致恶化；期货滞后系数和的主区间也跨零。这里报告指标变化，不把延迟比、方差比和自相关合并成“总体效率下降”的单一结论。

下表的raw_interaction_ols是无FE的Closed×Dose交互回归（含截距、Closed和Dose水平）；二值时对应原始2×2均值差分。raw_FE_beta是不缩尾股票/日期FE，w01_FE_beta是主1/99缩尾。四格原始均值、SD和行数在 `tables/raw_means.csv`，不把未调整差异当作因果量。

{md(raw)}

主模型：股票FE+日期FE+Closed×事前暴露+暴露水平项。dose以持股比例**1个百分点**计；eligible是事前北向可买入标的。股票与日期双向聚类，自由度=min(两类簇数)−1。价格和收益指标按表名单位读取；log量指标的变化可按 exp(beta)−1 换算。

{md(view)}

主1/99核心族共20行（两种暴露各10指标），BH q<0.05的行数为{significant}；该数仅作多重检验核对，不作为成功/失败闸门。所有不缩尾、1/99、0.5/99.5结果在 `tables/main_estimates.csv`，共90行。分布诊断逐指标、逐变换报告均值、SD、偏度、超额峰度、零值比例、0.1/1/99/99.9分位及缺失数，见 `tables/distributions.csv`。阈值只使用此前正常北向开放日；个股历史不足60日时用事件最早对照日前的历史全截面阈值，计数在 `tables/winsor_audit.csv`。

46个事件段少于50，因此附9999次Webb六点权重、按事件段聚类的限制残差wild bootstrap（统计量为绝对beta），以及9999次同年/月/起始星期、保留连续关闭长度的正常日区组置换。置换限制在可观测主窗口日期，拒绝区组重叠；可支持的独立置换日历数为{support['unique_assignments']}。RI是条件日历置换诊断，不能消除假期与境外信息生产共同变化的问题。FE系数与独立二次型计算的最大绝对差为{algebra.abs_difference.max():.3g}；另已与显式虚拟变量OLS核对不平衡小样本。

### 事前分组与恢复首日

按事前60个正常日成交额中位数、事前流通市值中位数的高/低组分别估计，股票与日期双向聚类；全部分组结果在 `tables/mechanism_estimates.csv`。分组变量在事件最早对照日前冻结，不使用关闭日成交额分类。事前组间水平差和标准化差见 `tables/balance.csv`，它不是随机平衡检验的通过证书。-5至+5交易日动态、以-1为基准，见 `tables/dynamic_estimates.csv`。

恢复首日与关闭日交互在同一模型中估计，避免把关闭日误作正常恢复日对照：

{md(recovery)}

完整关闭段日内累计收益与恢复首日日内收益的回归（cum_x为累计收益×事前暴露；这是机制关联，不另作因果识别）：

{md(reversal)}

收益是日内开收盘部分；不能据此描述含隔夜收益的全部补偿性交易。每个主指标的方向须按经济含义分别解释；方差比或自相关的正负变化本身不等同于价格效率单调变好或变坏。

## 4. 安慰剂

普通交易日安慰剂使用官方可核对的A股与香港共同假日前后最近北向正常开放日，并排除真实事件及其±5正常日窗口。香港/南向状态的原始CSV可核对范围为2023–2026。北向开放、南向关闭只找到2个日期；不能把它当作具有充分独立冲击的强否证检验。具体日历在 `tables/placebo_event_dates.csv` 和 `tables/placebo_date_map.csv`。

{md(pcview)}

安慰剂所有暴露、所有三种缩尾和模型水平项在 `tables/placebo_estimates.csv`；wild与可行的同年/月/星期置换均保留。若无法形成匹配正常日支持，ri_B=0并给出原因，不制造p值。少事件情形下的p值不能补充实际缺少的独立事件。

## 5. 最不利事实

1. **两项普通假日安慰剂同向。** 共同假日前后，连续剂量VR5为{placebo_vr.beta:.6f}（双向聚类p={placebo_vr.p:.6g}），分钟自相关为{placebo_ac.beta:.6f}（p={placebo_ac.p:.6g}），都与北向关闭主结果同向。不能把这两项独立归因于北向缺席。普通假日的IF/IH延迟估计区间跨零，但匹配置换日历没有可行支持，未据此证明排除一般假日影响。
2. **通道关闭不等于全体外资缺席。** QFII/RQFII等通道仍可存在，北向也可能含绕道境内交易。识别对象是北向通道不可用的差异暴露效应。
3. **冲击只有46个连续段，并与香港/全球假期信息环境共同变化。** 日期FE吸收共同日效应，却不能自动排除外资偏好股票对境外消息的异质敏感性；wild/RI只是补充推断。
4. **剂量披露频率发生断点。** 2024-08后季频、严格滞后，不能视为每日最新持仓；历史个股持股值来自本地供应库，官方留存期限不足以逐值重抓核验全部历史。
5. **盘口指标是代理。** 分钟CS/AR并非实测有效价差，无报价深度；高零值、非线性截断及分钟数据版本差异会影响解释。原始/两种缩尾结果、分布和换源核验全部公开，未凭显著性选规格。
6. **样本不含完整2026，IF/IH更早止于9月初。** 北开南闭安慰剂仅2天；恢复日收益只覆盖日内部分，不包括隔夜补偿。
7. **补偿性交易和反转未得到一致支持。** 连续剂量的恢复日成交额/成交量区间均跨零；关闭段累计日内收益×剂量的恢复日反转系数区间也跨零。恢复日平均日内收益为负不等于已验证价格反转。事前组间构成差明显，余额与标准化差完整保留于balance表。

## 6. 复现与执行核验

在本目录运行 `bash run_all.sh`。预注册SHA256：`{sha(ROOT/'PREREGISTRATION.md')}`。规格锁定、随机种子、官方取数回执与决策日志均可核对。完整代码在 `code/`，依赖版本在 `requirements.lock`；最终统计表校验见 `meta/final_validation.json`。

四个重工作进程，数值库每进程1线程；本轮连同中止尝试的最高已记录合计RSS为{resource_peak:.3f}GB。超过6.8GB工作预算的早期读取/估计尝试已被监控终止；没有记录到超过8GB硬上限的采样值。最终改为按日读取、精确FWL和按规格并行，重建全部最终指标；失败日志保留。大型临时文件位于 `/Volumes/Extreme SSD/T9/_tmp/266/`，最终交付前清理。本轮没有下载原始zip；现有原盘zip与7z只读，不移动他人原始数据。
'''
 (ROOT/'RESULTS_FOR_CLAUDE.md').write_text(report)
 validation=dict(status='PASS',completed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),prereg_sha256=sha(ROOT/'PREREGISTRATION.md'),registered_main_rows=90,actual_main_rows=len(main),main_unique_specs=len(main.drop_duplicates(['metric','variant','exposure'])),mechanism_coefficient_rows=len(mech),dynamic_coefficient_rows=len(dynamic),placebo_coefficient_rows=len(placebo),registry_rows=len(registry),raw_input_files=len(inputs['files']),raw_input_bytes=sum(r['bytes'] for r in inputs['files']),raw_input_manifest_sha256=sha(ROOT/'meta/input_manifest.json'),two_way_df_rule=True,no_duplicate_stock_dates=True,pre_window_exposure_timing=True,all_92_closed_days_observed=True,bootstrap_repetitions=9999,main_randomization_repetitions=9999,maximum_fe_quadratic_difference=float(algebra.abs_difference.max()),independent_inference_checks_passed=len(independent),numeric_thread_environment_all_one=True,resource_peak_including_aborted_attempts_gb=resource_peak,independent_events=len(ev),unavailable_measurements=len(unavailable),report_sha256=sha(ROOT/'RESULTS_FOR_CLAUDE.md'))
 (ROOT/'meta/final_validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2))
 for name in ['sample_by_event','balance','data_scale']:shutil.copyfile(ROOT/f'tables/{name}.csv',ROOT/f'{name}.csv')
 files={str(p.relative_to(ROOT)):sha(p) for p in list((ROOT/'tables').glob('*.csv'))+[ROOT/'PREREGISTRATION.md',ROOT/'RESULTS_FOR_CLAUDE.md']};(ROOT/'meta/output_sha256.json').write_text(json.dumps(files,indent=2));print(json.dumps(validation,ensure_ascii=False,indent=2))
 code_files=list((ROOT/'code').glob('*.py'))+[ROOT/'run_all.sh',ROOT/'requirements.lock',ROOT/'meta/frozen_input_cutoff.json',ROOT/'meta/literature_gate.json'];(ROOT/'meta/code_sha256.json').write_text(json.dumps({str(p.relative_to(ROOT)):sha(p) for p in code_files},indent=2))
if __name__=='__main__':main()
