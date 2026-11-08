from common import *
from assemble import PRIMARY
from scipy import stats

def event_tables(panel):
 out=[]
 for key,x in panel[panel.kind.eq('real')].groupby('event_id'):
  for metric in PRIMARY:
   for variant in ['raw','w01','w005']:
    col=metric if variant=='raw'else metric+'__'+variant;v=x.groupby(['code','closed'])[col].mean().unstack('closed')
    if not {False,True}.issubset(v.columns):continue
    v['change']=v[True]-v[False];v=v.join(x.drop_duplicates('code').set_index('code').dose).dropna(subset=['change','dose'])
    if len(v)<3 or v.dose.var()==0:out.append(dict(event_id=key,metric=metric,variant=variant,status='NOT_ESTIMABLE',stocks=len(v)));continue
    z=stats.linregress(v.dose,v.change);out.append(dict(event_id=key,metric=metric,variant=variant,status='OK',stocks=len(v),slope=z.slope,se_crosssection=z.stderr,p_crosssection=z.pvalue))
 ev=pd.DataFrame(out);save(ev,'event_level_slopes.csv');agg=[]
 if len(ev):
  for key,x in ev[ev.status.eq('OK')].groupby(['metric','variant']):
   v=x.slope.dropna();n=len(v);p=stats.ttest_1samp(v,0).pvalue if n>1 else np.nan;sg=stats.binomtest(int((v>0).sum()),int((v!=0).sum()),.5).pvalue if (v!=0).sum()else np.nan;agg.append(dict(metric=key[0],variant=key[1],events=n,event_equal_mean=v.mean(),event_median=v.median(),positive_share=(v>0).mean(),event_t_p=p,exact_sign_p=sg))
 save(pd.DataFrame(agg),'event_equal_inference.csv')

def original_event_support():
 # Preserve all pre-registered comparison-window mappings alongside the unique-date main panel.
 from assemble import completed_files
 m=pd.read_csv(R/'tables/event_date_map_all.csv',parse_dates=['date','treatment_date']);f=pd.read_csv(R/'tables/frozen_features.csv',usecols=['kind','event_id','code'])
 quality=[]
 for p in completed_files('daily'):
  q=pd.read_parquet(p,columns=['date','code','order_table','trade_table','queue_ok']);quality.append(q)
 q=pd.concat(quality,ignore_index=True)if quality else pd.DataFrame(columns=['date','code','order_table','trade_table','queue_ok'])
 m['date_use_count']=m.groupby(['kind','date']).date.transform('size');m['inverse_date_use_weight']=1/m.date_use_count
 rows=[]
 for (kind,eid),mm in m.groupby(['kind','event_id']):
  codes=set(f.loc[f.kind.eq(kind)&f.event_id.eq(eid),'code']);actual=q[q.code.isin(codes)].set_index('date')
  for z in mm.itertuples():
   qq=actual.loc[[z.date]]if z.date in actual.index else actual.iloc[:0]
   rows.append(dict(kind=kind,event_id=eid,treatment_date=z.treatment_date,date=z.date,closed=z.closed,primary_date_owner=z.owner,date_use_count=z.date_use_count,inverse_date_use_weight=z.inverse_date_use_weight,planned_stocks=len(codes),available_order_stock_days=int(qq.order_table.eq(1).sum()),available_trade_stock_days=int(qq.trade_table.eq(1).sum()),available_queue_stock_days=int(qq.queue_ok.eq(1).sum())))
 weights=pd.DataFrame(rows);save(weights,'event_window_weights.csv');summary=[]
 for (kind,eid),xx in weights.groupby(['kind','event_id']):
  unique=xx.drop_duplicates('date');summary.append(dict(kind=kind,event_id=eid,original_window_rows=len(xx),original_unique_treatment_days=xx.loc[xx.closed,'date'].nunique(),original_unique_control_days=xx.loc[~xx.closed,'date'].nunique(),unique_dates_retained_by_primary_owner=xx.loc[xx.primary_date_owner,'date'].nunique(),original_available_order_stock_days=unique.available_order_stock_days.sum(),inverse_reuse_weighted_order_stock_days=(xx.available_order_stock_days*xx.inverse_date_use_weight).sum()))
 save(pd.DataFrame(summary),'sample_by_event_original_mapping.csv')

def observed_daily_balance(panel):
 # Descriptive stock-day balance on each daily main mechanism's actual baseline support.
 variables=['dose','logcap','logamount','ifbeta','predelay','qfii','csi300','sse50','csi500'];rows=[]
 for metric in PRIMARY:
  for variant in ['raw','w01','w005']:
   col=metric if variant=='raw'else metric+'__'+variant
   f=panel[['event_id','code','date','closed','eligible',*variables,col]].replace([np.inf,-np.inf],np.nan).dropna(subset=['dose',col])
   support=f.groupby(['event_id','closed']).date.nunique().unstack(fill_value=0)
   supported=support.index[(support.get(True,0)>0)&(support.get(False,0)>0)]if {True,False}.issubset(support.columns)else []
   f=f[f.event_id.isin(supported)]
   for closed,x in f.groupby('closed'):
    for variable in variables:
     a=x.loc[x.eligible.eq(1),variable].dropna();b=x.loc[x.eligible.eq(0),variable].dropna();den=np.sqrt((a.var()+b.var())/2)
     rows.append(dict(metric=metric,variant=variant,closed=closed,variable=variable,grain='stock-day, equal cell weights',events=x.event_id.nunique(),dates=x.date.nunique(),stocks=x.code.nunique(),eligible_n=len(a),noneligible_n=len(b),eligible_mean=a.mean(),noneligible_mean=b.mean(),standardized_difference=(a.mean()-b.mean())/den if den>0 else np.nan))
 return pd.DataFrame(rows,columns=['metric','variant','closed','variable','grain','events','dates','stocks','eligible_n','noneligible_n','eligible_mean','noneligible_mean','standardized_difference'])

def variant_comparison(est):
 x=est[est.kind.eq('real')&est.specification.eq('baseline')&est.metric.isin(PRIMARY+['m2_IF','m2_IH'])&est.exposure.eq('NB')&~est.term.astype(str).str.startswith('individual')];rows=[]
 for (metric,term),f in x.groupby(['metric','term']):
  b=f.set_index('variant').beta;main=b.get('w01',np.nan);raw=b.get('raw',np.nan);alt=b.get('w005',np.nan)
  flag=lambda value:'不可比较'if not(np.isfinite(value)and np.isfinite(main))else '反转'if value*main<0 else '未反转或含零'
  rows.append(dict(metric=metric,term=term,raw_beta=raw,main_w01_beta=main,w005_beta=alt,raw_vs_main_sign=flag(raw),w005_vs_main_sign=flag(alt)))
 return pd.DataFrame(rows)

def main():
 panel=pd.read_parquet(T/'daily_panel.parquet');est=pd.read_csv(R/'tables/all_estimates.csv');plan=pd.read_csv(R/'tables/download_plan.csv');mapping=pd.read_csv(R/'tables/event_date_map.csv',parse_dates=['date']);ft=pd.read_csv(R/'tables/frozen_features.csv',low_memory=False);records=[json.loads(p.read_text())for p in (R/'logs/days').glob('*.json')];process=pd.DataFrame(records);identity=hashlib.sha256(b''.join((R/'code'/v).read_bytes()for v in ['scan.cpp','book169.cpp','numeric229.hpp'])).hexdigest();process['accepted']=process.status.eq('OK')&process.scanner_sha256.isin(accepted_native_hashes(identity));save(process,'day_processing_status.csv');event_tables(panel);original_event_support()
 sample=[]
 for (kind,eid),x in panel.groupby(['kind','event_id']):
  z=dict(kind=kind,event_id=eid,planned_treatment_days=x.loc[x.closed,'date'].nunique(),planned_control_days=x.loc[~x.closed,'date'].nunique(),planned_stocks=x.code.nunique(),observed_stocks_with_orders=x.loc[x.order_table.eq(1),'code'].nunique(),observed_stocks_with_trades=x.loc[x.trade_table.eq(1),'code'].nunique(),eligible_stocks=x.loc[x.eligible.eq(1),'code'].nunique(),noneligible_stocks=x.loc[x.eligible.eq(0),'code'].nunique(),actual_stock_days=x.quote_table.notna().sum(),order_stock_days=x.order_table.eq(1).sum(),trade_stock_days=x.trade_table.eq(1).sum(),queue_pass_stock_days=x.queue_ok.eq(1).sum(),treated_with_data=x.loc[x.closed&x.order_table.eq(1),'date'].nunique())
  for metric in PRIMARY:
   z[metric+'_n']=x[metric].notna().sum();z[metric+'_treated_days']=x.loc[x.closed&x[metric].notna(),'date'].nunique()
  sample.append(z)
 sdf=pd.DataFrame(sample);sdf.to_csv(R/'sample_by_event.csv',index=False);save(sdf,'sample_by_event.csv');bal=[]
 for kind,f in ft.groupby('kind'):
  for eid,ff in [('ALL',f),*list(f.groupby('event_id'))]:
   for col in ['dose','dose_272','logcap','logamount','ifbeta','predelay','qfii','csi300','sse50','csi500','controls_age_days']:
    a=ff.loc[ff.sample_group.eq('top300'),col].dropna();b=ff.loc[ff.sample_group.eq('noneligible_match'),col].dropna();den=np.sqrt((a.var()+b.var())/2);bal.append(dict(kind=kind,event_id=eid,variable=col,top300_n=len(a),control_n=len(b),top300_mean=a.mean(),control_mean=b.mean(),standardized_difference=(a.mean()-b.mean())/den if den>0 else np.nan))
 pd.DataFrame(bal).to_csv(R/'balance.csv',index=False);save(pd.DataFrame(bal),'balance.csv');raw=pd.read_csv(R/'tables/l2_scale_by_date.csv');r=panel[panel.kind.eq('real')];save(observed_daily_balance(r),'balance_daily_mechanisms.csv');scale=[dict(item='planned_real_treated_dates',value=mapping.loc[mapping.kind.eq('real')&mapping.closed,'date'].nunique()),dict(item='planned_real_control_dates',value=mapping.loc[mapping.kind.eq('real')&~mapping.closed,'date'].nunique()),dict(item='planned_all_dates',value=len(plan)),dict(item='processed_OK_dates',value=process.accepted.sum()),dict(item='processed_failed_dates',value=(~process.accepted).sum()),dict(item='real_distinct_stocks',value=r.code.nunique()),dict(item='real_stocks_with_order_tables',value=r.loc[r.order_table.eq(1),'code'].nunique()),dict(item='real_stocks_with_trade_tables',value=r.loc[r.trade_table.eq(1),'code'].nunique()),dict(item='all_kinds_distinct_stocks',value=panel.code.nunique()),dict(item='real_stock_days_planned',value=len(r)),dict(item='real_stock_days_with_orders',value=r.order_table.eq(1).sum()),dict(item='real_events',value=r.event_id.nunique()),dict(item='raw_order_rows',value=raw.order_rows.sum()),dict(item='raw_trade_rows',value=raw.trade_rows.sum()),dict(item='raw_quote_rows',value=raw.quote_rows.sum()),dict(item='planned_remote_bytes',value=plan.size_bytes.sum()),dict(item='successful_downloaded_archive_days',value=process.loc[process.accepted,'downloaded'].fillna(False).astype(bool).sum()),dict(item='successful_downloaded_archive_bytes',value=process.loc[process.accepted&process.downloaded.fillna(False).astype(bool),'archive_bytes'].sum()),dict(item='successful_local_reused_archive_days',value=(process.accepted&~process.downloaded.fillna(False).astype(bool)).sum()),dict(item='duplicate_order_ids',value=raw.duplicates.sum()),dict(item='conflicting_order_ids',value=raw.conflicts.sum()),dict(item='unknown_aggressor_trades',value=raw.unknown_aggressor.sum())];pd.DataFrame(scale).to_csv(R/'data_scale.csv',index=False);save(pd.DataFrame(scale),'data_scale.csv')
 r=r.assign(market=r.code.str[-2:]);coverage=r.groupby(['market','eligible','closed']).agg(planned_stock_days=('code','size'),with_orders=('order_table',lambda v:v.eq(1).sum()),queue_pass=('queue_ok',lambda v:v.eq(1).sum()),clock_pass=('clock_ok',lambda v:v.eq(1).sum()),M3_valid=('m3_wait_median','count'),M4_valid=('m4_spread_bp','count')).reset_index();save(coverage,'mechanism_coverage_by_market.csv')
 qcoverage=ft.groupby(['kind','event_id']).agg(stocks=('code','size'),qfii_known=('qfii','count'),qfii_positive=('qfii',lambda v:v.gt(0).sum()),qfii_max=('qfii','max')).reset_index();save(qcoverage,'QFII_dose_coverage.csv')
 runtime_peak=0.0
 for line in (R/'logs/resources.jsonl').read_text().splitlines():
  try:runtime_peak=max(runtime_peak,float(json.loads(line).get('rss_gb',0)))
  except (ValueError,json.JSONDecodeError):pass
 js(R/'meta/runtime.json',dict(seed=SEED,workers=4,numeric_threads=1,peak_aggregate_rss_gb=runtime_peak,circuit_breaker_gb=8,hard_budget_gb=10,disk_reserve_gb=20))
 main=pd.read_csv(R/'tables/main_family.csv');complete=bool(process.accepted.sum()==len(plan));title='完整统计交付'if complete else '存在原始日包缺口的统计交付';ntr=mapping.loc[mapping.kind.eq('real')&mapping.closed,'date'].nunique();small='**处理日少于10，事件推断不稳。**\n'if ntr<10 else ''
 if 'treated_days'in main:
  low=main.loc[main.treated_days.lt(10),['metric','term','treated_days']];small+=('**以下指标实际处理日不足10：** '+low.to_json(orient='records',force_ascii=False)+'\n')if len(low)else ''
 lines=['# 277 R3 统计结果（只统计，不写稿、不审稿）','',f'状态：{title}。生成时间：{pd.Timestamp.now(tz="Asia/Seoul")}。',small,'## 核数','',pd.DataFrame(scale).to_markdown(index=False),'','样本、匹配和数据核数见 sample_by_event.csv、balance.csv、data_scale.csv。原始比较窗、每日期重用次数及倒数权重保留在event_window_weights.csv，原始事件支持见sample_by_event_original_mapping.csv。处理日与对照日的唯一归属见 tables/event_date_map.csv；不能把日期重用当独立事件。','',f'日包成功{int(process.accepted.sum())}/{len(plan)}；逐项失败见 tables/day_processing_status.csv。报文行数仅计预定股票表中的原始行（含非主估计时段），并非全市场报文总数。计划股票数是事件样本的并集，实际有委托表/成交表的股票数另列，不把无表记为零。balance.csv为计划事件×股票平衡；balance_daily_mechanisms.csv按每项日机制实际有效stock-day样本列出正常/关闭状态的平衡。每事件最多300只高持股标的和300只行业精确匹配非标的；不足数量及市值差异原样保留。','', '剂量以本轮要求的事件前最后正常日冻结，披露可得性沿272；272实际成果采用最早对照日前冻结，两种口径另列dose272_freeze。历史行业、指数、QFII和七项控制复用272更早冻结信息，时间滞后见frozen_features.csv，不能声称每项都恰为本轮cutoff最新值。','', '原IF/IH分钟档至2026-09-01，已用本地真实tick补至2026-09-30并保留旧值不变；本地期货源缺10月分钟数据，不填零。新增月采用上一交易日真实合约成交量择主，开盘竞价价与旧分钟源对齐；IF重叠日最大收益差约2.18bp，补源明细及误差见futures_tick_calibration.csv。逐请求日期、逐产品的收益分钟覆盖见futures_coverage_by_requested_date.csv；原分钟源内2025-12-19的IF/IH收益整日缺失，也保留缺失而不填零。共同假日前后安慰剂只在原日历有HK假日明确标识的2023年以后计算。样本末端2026-10-19只有1个后方同星期对照，另一日超出日包覆盖；此窗口不冒充完整2+2，见control_window_audit.csv。','', '## 主估计','', '股票FE与日期FE；剂量单位每1pp。两向聚类、处理日比较窗Webb限制零假设wild 9999与独立事件段wild均报告；wild使用绝对系数统计量，未学生化，不能当作两向t统计量的另一种写法。主族固定15项，1/99为主，raw与0.5/99.5全部在all_estimates.csv；多重检验见q_bh_main15与q_bh_wild_main15。','']
 def primary(metric,term='closed_dose'):
  return main.loc[main.metric.eq(metric)&main.term.eq(term)].iloc[0]
 cg_sig=int(main.q_bh_main15.lt(.05).sum());wild_sig=int(main.q_bh_wild_main15.lt(.05).sum())
 lines+=['数值提要（均为关闭×剂量，每1pp；显著性须区分两向聚类与wild）：',
 f"- M1：100万元阈值主动买/卖金额占比分别变动{primary('m1_buy_share_1m').beta*100:.5f}/{primary('m1_sell_share_1m').beta*100:.5f}个百分点；笔数分别变动{primary('m1_buy_n_1m').beta:.4f}/{primary('m1_sell_n_1m').beta:.4f}。这是成交记录的参与变化，不能识别投资者国籍。",
 f"- M2：IF/IH同期三重项分别为{primary('m2_IF','contemporaneous').beta:.7f}/{primary('m2_IH','contemporaneous').beta:.7f}；滞后1–5分钟和的两向p分别{primary('m2_IF','lag1_5_sum').p:.3f}/{primary('m2_IH','lag1_5_sum').p:.3f}。同期结果是剂量梯度的相对变化。",
 f"- M3：冲击分钟结束后的截断等待中位数变动{primary('m3_wait_median').beta:.4f}秒；60秒更新比例变动{primary('m3_update60').beta*100:.4f}个百分点，两向p={primary('m3_update60').p:.3f}。有效处理日{int(primary('m3_wait_median').treated_days)}，独立事件{int(primary('m3_wait_median').events)}，按预定处理日归属的wild比较窗簇{int(primary('m3_wait_median').wild_clusters)}；其中部分窗仅余有效对照，不能把比较窗簇数当作有效处理日数。",
 f"- M4：价差系数{primary('m4_spread_bp').beta:.5f}bp，两向p={primary('m4_spread_bp').p:.3f}；前五档深度增加{primary('m4_depth5_yuan').beta:,.2f}元，两向主族BH q={primary('m4_depth5_yuan').q_bh_main15:.4f}。精确盘口结果不能统称流动性为零。",
 f"- M5：撤单率变动{primary('m5_cancel_rate').beta*100:.5f}个百分点；限价/市价笔数比变动{primary('m5_limit_market_ratio').beta:.3f}（该比仅深市）；有定价委托均额变动{primary('m5_avg_order_yuan').beta:.2f}元，两向p={primary('m5_avg_order_yuan').p:.3f}。",
 f"主族15项中，两向聚类BH q<0.05为{cg_sig}项，处理日比较窗wild BH q<0.05为{wild_sig}项。两套推断出现明显分歧，不能只引用其中较小的p值。",'']
 lines+=['M3市场及处理状态覆盖（原始代码复核见market_queue_reference_validation.json；未过门槛不强行校正）：','',coverage.to_markdown(index=False),'']
 cols=[c for c in ['metric','term','beta','se','ci_low','ci_high','mde80','p','wild_p','wild_clusters','event_wild_p','event_wild_clusters','q_bh_main15','q_bh_wild_main15','q_bh_mechanism','q_bh_wild_mechanism','n','stocks','dates','events','treated_days','status']if c in main];lines.append(main[cols].to_markdown(index=False,floatfmt='.6g'))
 reference_slopes=est[est.kind.eq('real')&est.variant.eq('w01')&est.specification.eq('baseline')&est.term.astype(str).str.startswith(('individual_normal_','individual_closed_'))];save(reference_slopes,'M2_reference_slopes.csv');lines+=['','M2正常日与关闭日的参考斜率（控制取中心值、剂量取P25/P75；梯度为每1pp剂量）：','',reference_slopes[[c for c in ['metric','term','beta','se','ci_low','ci_high','status']if c in reference_slopes]].to_markdown(index=False,floatfmt='.6g')]
 source_sensitivity=est[est.kind.eq('real')&est.specification.eq('original_futures_only')&~est.term.astype(str).str.startswith('individual')];save(source_sensitivity,'futures_source_sensitivity.csv');lines+=['','新增tick来源的额外敏感性（登记后、首次正式估计前加入；主族不变）：仅原分钟源截至2026-09-01的M2/M3结果见futures_source_sensitivity.csv，仍要求事件同时有处理与对照。该规格不属于事前主族。','']
 lines+=['','M1金额占比0–1；500k/1m/3m后缀分别表示50万/100万/300万元阈值；成交笔数为连续竞价逐笔成交记录数；M2因变量为净主动买入/流通市值bp、期货收益bp；M3为冲击分钟结束后、60秒右删失的同向续动等待中位数（秒）和更新比例；M4为价差bp和前五档双边深度元；M5撤单/新增事件比、限价/市价笔数比和有定价限价委托的平均金额。M4未拒绝零不能证明效应为零；95%区间与基于两向聚类标准误的近似80%可检出幅度（mde80）并列，未事后设置等效界限。市价无法精确定价，平均金额不能解释成全部初始订单均值。沪市A是主动撮合后的剩余挂单，SH没有可核实市价分母时比例缺失。','', 'M3只用逐单重建与独立时钟校准同时过关的股票日；时钟校准过关的原快照辅助结果分开列，不能以快照采样等待替代逐单速度。逐股队列通过、缺表与重复编号见核数表。','', 'M5 分市场结果','']
 market_m5=est[est.kind.eq('real')&est.variant.eq('w01')&est.specification.isin(['market_SH','market_SZ'])&est.metric.str.startswith('m5_')];save(market_m5,'M5_by_market.csv');lines+=['沪市A为剩余报文，深市包含初始申报；不能直接合称同口径初始订单。平均股数覆盖可识别新增类型，平均金额限有定价申报。','',market_m5[[c for c in ['specification','metric','beta','se','p','wild_p','status']if c in market_m5]].to_markdown(index=False,floatfmt='.6g'),'','## 安慰剂与替代解释','']
 alt=est[(est.kind!='real')&est.specification.eq('baseline')&est.variant.eq('w01')&~est.term.astype(str).str.startswith('individual')];lines.append(alt[[c for c in ['kind','metric','term','beta','p','wild_p','status','reason']if c in alt]].to_markdown(index=False,floatfmt='.6g'))
 for spec in ['exclude_AH','QFII_parallel','dose272_freeze','race_cumulative_7','race_all_seven_same_sample_baseline','race_all_eight']:
  x=est[est.specification.eq(spec)&est.variant.eq('w01')&~est.term.astype(str).str.startswith('individual')];lines+=['',f'### {spec}','',x[[c for c in ['metric','term','beta','p','wild_p','n','status','reason']if c in x]].to_markdown(index=False,floatfmt='.6g')]
 lines+=['','## 最不利事实','']
 # Explicit adverse numerical facts, drawn from pre-specified fits without adding tests.
 race=est[est.kind.eq('real')&est.variant.eq('w01')&est.specification.eq('race_cumulative_7')&~est.term.astype(str).str.startswith('individual')].set_index(['metric','term'])
 same=est[est.kind.eq('real')&est.variant.eq('w01')&est.specification.eq('race_all_seven_same_sample_baseline')&~est.term.astype(str).str.startswith('individual')].set_index(['metric','term'])
 share_buy=race.loc[('m1_buy_share_1m','closed_dose')];share_sell=race.loc[('m1_sell_share_1m','closed_dose')]
 r_if=race.loc[('m2_IF','contemporaneous')];r_ih=race.loc[('m2_IH','contemporaneous')];r_m3=race.loc[('m3_wait_median','closed_dose')]
 balance=pd.DataFrame(bal);bb=balance[balance.kind.eq('real')&balance.event_id.eq('ALL')].set_index('variable');ee=pd.read_csv(R/'tables/event_equal_inference.csv');ee=ee[ee.variant.eq('w01')].set_index('metric')
 placebo=est[est.kind.ne('real')&est.variant.eq('w01')&~est.term.astype(str).str.startswith('individual')];fp=placebo[placebo.kind.eq('fake20')&placebo.specification.eq('baseline')&placebo.metric.eq('m3_wait_median')].iloc[0]
 cp=placebo[placebo.kind.eq('common_holiday')&placebo.specification.eq('baseline')];fq=placebo[placebo.kind.eq('fake20')&placebo.specification.eq('baseline')];sq=placebo[placebo.kind.eq('fake20')&placebo.specification.eq('same_weekday')];qproxy=est[est.kind.eq('real')&est.variant.eq('w01')&est.specification.eq('QFII_parallel')&est.exposure.eq('QFII')]
 ref=reference_slopes.set_index(['metric','term']);threshold_buy=est[est.kind.eq('real')&est.variant.eq('w01')&est.specification.eq('baseline')&est.metric.eq('m1_buy_share_3m')].iloc[0]
 lines+=['必须连同主表报告的数值事实：',
 f"1. 两向主族BH只有{cg_sig}/15项通过，处理日wild为{wild_sig}/15。M1买/卖笔数的两向p为{primary('m1_buy_n_1m').p:.3f}/{primary('m1_sell_n_1m').p:.3f}，虽然对应wild p很小；重抽比较窗与双向股票/日期聚类对依赖结构的处理不同。",
 f"2. 七项赛马使用同样本基准后，M1四项均由负转正。买/卖金额占比系数变为{share_buy.beta:.7f}/{share_sell.beta:.7f}，wild p={share_buy.wild_p:.4f}/{share_sell.wild_p:.4f}。同期M2 IF/IH仅保留同样本基准的{r_if.beta/same.loc[('m2_IF','contemporaneous'),'beta']:.1%}/{r_ih.beta/same.loc[('m2_IH','contemporaneous'),'beta']:.1%}，wild p={r_if.wild_p:.4f}/{r_ih.wild_p:.4f}；M3等待仅保留{r_m3.beta/same.loc[('m3_wait_median','closed_dose'),'beta']:.1%}，wild p={r_m3.wild_p:.4f}。这不只是样本被删导致的衰减。",
 f"3. 匹配后的事件×股票汇总SMD：log流通市值{bb.loc['logcap','standardized_difference']:.3f}，log成交额{bb.loc['logamount','standardized_difference']:.3f}，事前delay{bb.loc['predelay','standardized_difference']:.3f}。行业精确匹配没有实现良好的规模/交易活跃度平衡。",
 f"4. 阈值升至300万元时，主动买金额占比系数为{threshold_buy.beta:.7f}，符号转正，wild p={threshold_buy.wild_p:.4f}；卖方金额占比亦未拒绝零。50万/100万结果不能外推为所有大单、尤其最大单都缺席。",
 f"5. M3等待主系数的事件段wild p={primary('m3_wait_median').event_wild_p:.4f}；事件等权t检验p={ee.loc['m3_wait_median','event_t_p']:.4f}，精确符号p={ee.loc['m3_wait_median','exact_sign_p']:.4f}。前移20日假事件的同指标系数{fp.beta:.4f}秒，wild p={fp.wild_p:.4f}，其15项BH q={fp.q_bh_wild:.4f}；幅度与真事件相近，不能把安慰剂概括为全部为零。",
 f"6. 共同假日安慰剂有{int(cp.q_bh_wild.lt(.05).sum())}/15项通过wild BH，{int(cp.q_bh.lt(.05).sum())}/15项通过两向BH；前移20日基准分别为{int(fq.q_bh_wild.lt(.05).sum())}/{int(fq.q_bh.lt(.05).sum())}项，严格同星期版本分别为{int(sq.q_bh_wild.lt(.05).sum())}/{int(sq.q_bh.lt(.05).sum())}项。严格同星期版本仅6–7个有效独立事件。QFII代理15项的两向/wild BH分别为{int(qproxy.q_bh_QFII.lt(.05).sum())}/{int(qproxy.q_bh_wild_QFII.lt(.05).sum())}项，未拒绝不等于等效于零。",
 f"7. 剂量P75股票的IF同期参考斜率正常日{ref.loc[('m2_IF','individual_normal_high_contemporaneous'),'beta']:.6f}、关闭日{ref.loc[('m2_IF','individual_closed_high_contemporaneous'),'beta']:.6f}；IH为{ref.loc[('m2_IH','individual_normal_high_contemporaneous'),'beta']:.6f}/{ref.loc[('m2_IH','individual_closed_high_contemporaneous'),'beta']:.6f}。高剂量绝对参考斜率并未下降，三重项为负表示相对低剂量的变化更小，不能等同绝对同步反应下降。参考斜率之差没有另加检验。",
 '8. 沪市表中市价类型未被单独识别，辅助m5_market_share的结构性0仅指原表没有市价标记，不能读作真实市价单参与为零；对应零方差/不可估计状态完整保留。','']
 variants=variant_comparison(est);assert len(variants)==15;save(variants,'transformation_sensitivity.csv');lines+=['','原值与两种缩尾的主族点估计符号核对（仅比较点估计，不把符号差别当作显著异质性）：','',variants.to_markdown(index=False,floatfmt='.6g'),'']
 threshold_metrics=[f'm1_{side}_{measure}_{th}'for side in ['buy','sell']for measure in ['share','n']for th in ['500k','1m','3m']];thresholds=est[est.kind.eq('real')&est.variant.eq('w01')&est.specification.eq('baseline')&est.metric.isin(threshold_metrics)];save(thresholds,'large_trade_threshold_sensitivity.csv');lines+=['大单阈值敏感性：','',thresholds[[c for c in ['metric','beta','p','wild_p','status']if c in thresholds]].to_markdown(index=False,floatfmt='.6g'),'']
 retention=[]
 for spec in ['exclude_AH','race_cumulative_7']:
  xx=est[est.kind.eq('real')&est.variant.eq('w01')&est.specification.eq(spec)&est.exposure.eq('NB')&~est.term.astype(str).str.startswith('individual')]
  for z in xx.itertuples():
   base=main[main.metric.eq(z.metric)&main.term.eq(z.term)];same=est[est.kind.eq('real')&est.variant.eq('w01')&est.specification.eq('race_all_seven_same_sample_baseline')&est.metric.eq(z.metric)&est.term.eq(z.term)];b0=base.beta.iloc[0]if len(base)else np.nan;bs=same.beta.iloc[0]if len(same)else np.nan;retention.append(dict(specification=spec,metric=z.metric,term=z.term,beta=z.beta,baseline_beta=b0,retention=z.beta/b0 if np.isfinite(b0)and b0!=0 else np.nan,same_sample_baseline_beta=bs,same_sample_retention=z.beta/bs if spec=='race_cumulative_7'and np.isfinite(bs)and bs!=0 else np.nan,p=z.p,wild_p=getattr(z,'wild_p',np.nan)))
 ret=pd.DataFrame(retention);save(ret,'AH_race_retention.csv');lines+=['剔除A+H与七项赛马的系数保留（小分母时比例不稳定）：','',ret.to_markdown(index=False,floatfmt='.6g'),'']
 qf=est[est.kind.eq('real')&est.variant.eq('w01')&est.specification.eq('QFII_parallel')&est.exposure.eq('QFII')];save(qf,'QFII_parallel_results.csv');lines+=['QFII并列系数（每1pp；不显著不能证明等于零）：','',qf[[c for c in ['metric','term','beta','p','wild_p','status']if c in qf]].to_markdown(index=False,floatfmt='.6g'),'']
 dates=r.loc[r.closed,['date','event_id']].drop_duplicates();years=dates.date.dt.year.value_counts();save(years.rename_axis('year').reset_index(name='treated_days'),'treated_date_concentration_by_year.csv');save(dates.groupby('event_id').date.nunique().rename('treated_days').reset_index(),'treated_date_concentration_by_event.csv');lines+=[f'1. 处理日{ntr}，独立事件段{r.event_id.nunique()}；最多年份占{years.max()/max(1,len(dates)):.1%}。主推断不能把股票分钟数当处理自由度。',f'2. 事前前300股与非标的行业匹配仍可能严重市值不平衡。实际SMD、匹配距离和对照不足不隐藏，详见balance.csv、matches.csv。',f'3. 报价重建过关的股票日{int(r.queue_ok.eq(1).sum())}/{int(r.order_table.eq(1).sum())}；M3可能有选择性覆盖，快照辅助也不能解除该选择问题。','4. 大单是成交记录金额，拆单、撮合拆分、撤单再下单和沪市剩余A均影响订单识别。50万/100万/300万及同主动委托号聚合阈值结果全部保留；任何一种阈值显著不等于已识别外资身份。','5. QFII仅披露完整十大股东中的已识别类别代理，更早272冻结值并非全体可交易境外资金；无法据代理零值推出没有其他外资。','6. 前样本正常日不足时缩尾用池化历史阈值；没有任何先验L2正常样本的事件缩尾版本不可估计，不能借用未来。分布与阈值文件须同时看。','7. M2同期关联不能区分期货领先、共同新闻与成分股对期货的反向影响。M3从冲击分钟结束开始计时，衡量后续同向变价；若股票已在冲击分钟内充分反应，后续可能无需再变价。因此它不能单独识别最初吸收信息所需时间，预设符号一致也不等于证明反应速度机制。','8. IF/IH有效数据覆盖补至2026-09-30，本地期货源仍缺10月分钟数据。每项估计只纳入同时有处理与对照有效观测的事件；无法观察处理的孤立对照窗不充作可估计事件，剔除清单在tables/event_support。9月补源是采样tick聚合，存在已量化的分钟末价误差；不得将其当作无误差逐笔成交分钟源。','9. 限价/市价比的市场间可比性有限；平均金额是有定价委托，沪市委托规模只对应剩余申报，不能与深市原始全量直接解释为同一母单机制。','10. 主统计限定连续竞价，集合竞价无一致的主动方定义。与272的全日分钟估计在时段和股票样本上不同，方向比较是描述性核对。','11. 本轮剂量冻结与272实际冻结存在差异；主口径、272口径及更早控制信息的时效性需并列。','']
 direction=[]
 for prod in ['IF','IH']:
  for term in ['contemporaneous','lag1_5_sum']:
   x=main[main.metric.eq('m2_'+prod)&main.term.eq(term)]
   if len(x):direction.append(dict(metric='m2_'+prod,term=term,beta=x.beta.iloc[0],consistency=('与272延迟方向相容'if np.isfinite(x.beta.iloc[0])and x.beta.iloc[0]<0 else '同期结果不支持变慢或不可估计')if term=='contemporaneous'else '须与同期及M3联合判断；滞后和无预定单一符号'))
 for metric,expected in [('m3_wait_median',1),('m3_update60',-1)]:
  x=main[main.metric.eq(metric)]
  if len(x):direction.append(dict(metric=metric,term='closed_dose',beta=x.beta.iloc[0],consistency='按预设符号与272相容；仅为冲击后续动'if x.beta.iloc[0]*expected>0 else '预设符号不一致或不可估计；不能单独识别初始速度'))
 save(pd.DataFrame(direction),'direction_vs_272.csv');lines+=['M2/M3与272方向逐项列在direction_vs_272.csv；M2滞后和没有必然的单一方向。唯一日期归属后的事件等权斜率和精确符号检验在event_equal_inference.csv，不能用股票横截面p值替代独立事件推断。','',pd.DataFrame(direction).to_markdown(index=False,floatfmt='.6g'),'','## 复现与验证','', '运行 bash run_all.sh。原始输入来源、预注册锁、原生重建对照与独立OLS/CGM验证保存在meta/。所有大中间量在指定277临时目录，任务完成后清理；KEEP_INTERMEDIATES=1保留。源码修复与失败重跑见logs及meta，不把实现修复冒充额外事前注册。市价单无价字段的已知无符号哨兵仅在委托类型1、委托价格字段兼容；旧成功输入域调用原整数解析函数不变。原日状态保留实际执行源码哈希，旧缓存严格等价依据见native_cache_compatibility.json及unsigned_market_parser_validation.json。']
 (R/'RESULTS_FOR_CLAUDE.md').write_text('\n'.join(lines))
 artifacts=[R/v for v in ['RESULTS_FOR_CLAUDE.md','PREREGISTRATION_R3.md','run_all.sh','REPRODUCE.md','sample_by_event.csv','balance.csv','data_scale.csv']]+sorted((R/'tables').rglob('*.csv'))
 js(R/'meta/output_manifest.json',[dict(path=str(p.relative_to(R)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())for p in artifacts if p.exists()])
 js(R/'meta/code_manifest.json',[dict(path=str(p.relative_to(R)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())for p in sorted((R/'code').iterdir())if p.suffix in ['.py','.cpp','.hpp']])
 js(R/'meta/final_validation.json',dict(status='PASS'if complete and len(main)==15 and not est.status.eq('IMPLEMENTATION_ERROR').any()else 'INCOMPLETE',complete_raw_days=complete,requested_days=len(plan),processed_ok=int(process.accepted.sum()),main_rows=len(main),registered_main_tests=15,inference_validation=json.loads((R/'meta/inference_validation.json').read_text()),native_validation=json.loads((R/'meta/native_reference_validation.json').read_text()),finished_at=pd.Timestamp.now(tz='UTC')));print('FINALIZED',complete,len(main),flush=True)
if __name__=='__main__':main()
