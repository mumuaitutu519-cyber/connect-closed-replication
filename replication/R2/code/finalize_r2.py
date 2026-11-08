"""Source-backed Chinese statistical handoff, correction families, reconciliation and checks."""
from pathlib import Path
import sys,json,hashlib,datetime,shutil,os,numpy as np,pandas as pd
from scipy.stats import t as student_t
R=Path(__file__).resolve().parents[1];T=Path('/Volumes/Extreme SSD/T9/_tmp/272');sys.path.insert(0,str(Path(__file__).parent/'r1'))
from estimate import bh
PRIMARY=['if_delay','ih_delay','if_lag_sum','ih_lag_sum'];EXT=['if_delay_f5','ih_delay_f5','if_delay_f15','ih_delay_f15','if_lag_bigday','ih_lag_bigday','if_lag_bigpre','ih_lag_bigpre']
LABEL={'if_delay':'IF价格延迟','ih_delay':'IH价格延迟','if_lag_sum':'IF滞后1–5分钟系数和','ih_lag_sum':'IH滞后1–5分钟系数和'}

def rw(p,stats,bootstrap):
 out=np.full(len(stats),np.nan);valid=np.flatnonzero(np.isfinite(stats));order=valid[np.argsort(-np.abs(np.asarray(stats)[valid]))];last=0.
 for j,i in enumerate(order):
  mx=np.max(np.abs(bootstrap[order[j:]]),axis=0);raw=(1+np.sum(mx>=abs(stats[i])))/(bootstrap.shape[1]+1);last=max(last,raw);out[i]=min(1,last)
 return out

def corrections(f,bootmap,familycols):
 f=f.reset_index(drop=True);f['q_bh']=np.nan;f['q_bh_wild']=np.nan;f['q_bh_ri']=np.nan;f['p_romano_wolf']=np.nan;f['family_size']=np.nan
 target=f.term.eq('closed_x')&f.status.eq('OK')&f.beta.notna()&f.se.gt(0)
 for _,ix in f[target].groupby(familycols,dropna=False).groups.items():
  ix=list(ix);f.loc[ix,'q_bh']=bh(f.loc[ix,'p']);f.loc[ix,'q_bh_wild']=bh(f.loc[ix,'wild_p']);f.loc[ix,'q_bh_ri']=bh(f.loc[ix,'ri_p'])if 'ri_p'in f else np.nan;f.loc[ix,'family_size']=len(ix);withboot=[i for i in ix if pd.notna(f.loc[i].get('boot_index'))]
  if withboot:
   boot=np.array([bootmap[(f.loc[i,'metric'],int(f.loc[i,'boot_index']))]/f.loc[i,'se']for i in withboot]);f.loc[withboot,'p_romano_wolf']=rw(None,f.loc[withboot,'t'].to_numpy(),boot)
 f['q_bh_all_main_w01']=np.nan;f['p_rw_all_main_w01']=np.nan
 ix=f.index[target&f.variant.eq('w01')&f.exposure.eq('dose')&f.metric.isin(PRIMARY)].tolist()
 if ix:
  f.loc[ix,'q_bh_all_main_w01']=bh(f.loc[ix,'p']);withboot=[i for i in ix if pd.notna(f.loc[i].get('boot_index'))];boot=np.array([bootmap[(f.loc[i,'metric'],int(f.loc[i,'boot_index']))]/f.loc[i,'se']for i in withboot]);f.loc[withboot,'p_rw_all_main_w01']=rw(None,f.loc[withboot,'t'].to_numpy(),boot)
 return f

def md(df):
 if not len(df):return '| 状态 |\n|---|\n| 无可估计结果 |\n'
 return df.astype(object).where(pd.notna(df),None).to_markdown(index=False,floatfmt='.6g',missingval='NA')+'\n'
def read(name):return pd.read_csv(R/'tables'/name)
def num(x):return f'{x:.6g}'if pd.notna(x)else'NA'
def section(parts,title,table,conclusion,adverse):parts.extend(['\n## '+title+'\n',md(table),'一句话结论：'+conclusion+'\n','最不利事实：'+adverse+'\n'])

def collect():
 frames=[];bootmap={}
 for m in PRIMARY+EXT:
  frames.append(read('estimates_'+m+'.csv'))
  with np.load(T/f'bootstrap_{m}.npz')as z:
   for j,v in enumerate(z['boot']):bootmap[(m,j)]=v
 f=pd.concat(frames,ignore_index=True);f['result_family']=f.metric.map(lambda m:'main_four'if m in PRIMARY else('frequency_5'if m.endswith('_f5')else'frequency_15'if m.endswith('_f15')else'bigmove_day'if m.endswith('bigday')else'bigmove_pre60'));f=corrections(f,bootmap,['specification','exposure','variant','result_family']);f.to_csv(R/'tables/all_estimates.csv',index=False);f[f.metric.isin(PRIMARY)].to_csv(R/'tables/main_estimates.csv',index=False)
 # Auxiliary tested terms retain separate correction families.
 aux=f[f.get('auxiliary_target',pd.Series(False,index=f.index)).fillna(False)].copy();aux['q_bh_auxiliary']=np.nan;aux['p_rw_auxiliary']=np.nan
 for _,ix in aux.groupby(['specification','variant','term']).groups.items():
  ix=list(ix);aux.loc[ix,'q_bh_auxiliary']=bh(aux.loc[ix,'p']);valid=[i for i in ix if pd.notna(aux.loc[i].get('boot_index'))and pd.notna(aux.loc[i,'se'])and aux.loc[i,'se']>0]
  if valid:
   boots=np.array([bootmap[(aux.loc[i,'metric'],int(aux.loc[i,'boot_index']))]/aux.loc[i,'se']for i in valid]);aux.loc[valid,'p_rw_auxiliary']=rw(None,aux.loc[valid,'t'].to_numpy(),boots)
 aux.to_csv(R/'tables/auxiliary_dose_estimates.csv',index=False)
 pd.concat([read('distribution_'+m+'.csv')for m in PRIMARY+EXT]).to_csv(R/'tables/distributions.csv',index=False)
 fake=[];fb={}
 for m in PRIMARY:
  fake.append(read('fake_'+m+'.csv'))
  with np.load(T/f'bootstrap_fake_{m}.npz')as z:
   for j,v in enumerate(z['boot']):fb[(m,j)]=v
 fake=corrections(pd.concat(fake,ignore_index=True),fb,['specification','exposure','variant']);fake.to_csv(R/'tables/fake_estimates.csv',index=False)
 return f,aux,fake

def audits(f):
 import pyarrow.dataset as ds
 p=ds.dataset(T/'panel',format='parquet');cols=['code','date','event_id','closed','dose','eligible','pre60_normal_amount','if_delay','ih_delay','if_lag_sum','ih_lag_sum'];d=p.to_table(columns=cols,use_threads=False).to_pandas(use_threads=False);assert not d.duplicated(['code','date']).any()
 feat=pd.read_parquet(T/'event_features.parquet',columns=['code','event_id','ah','logcap','logamount','ifbeta','predelay','analyst','qfii','activity']);d=d.merge(feat,on=['code','event_id'],how='left',validate='m:1')
 sample=d.groupby('event_id').agg(stock_days=('code','size'),stocks=('code','nunique'),dates=('date','nunique'),closed_stock_days=('closed','sum'),dose_known=('dose','count'),dose_positive=('dose',lambda x:x.gt(0).sum()),AH_stock_days=('ah','sum'),IF_days=('if_delay','count'),IH_days=('ih_delay','count'),IF_lag_days=('if_lag_sum','count'),IH_lag_days=('ih_lag_sum','count'),QFII_days=('qfii','count')).reset_index();sample=read('events.csv').merge(sample,on='event_id',validate='1:1');ahs=d[d.ah.eq(1)].groupby('event_id').code.nunique();sample['AH_stocks']=sample.event_id.map(ahs).fillna(0).astype(int);sample.to_csv(R/'sample_by_event.csv',index=False)
 b=feat.drop_duplicates(['event_id','code']).merge(pd.read_parquet(T/'exposures.parquet',columns=['event_id','code','dose','eligible']),on=['event_id','code'],validate='1:1');balance=[]
 for c in ['ah','logcap','logamount','ifbeta','predelay','analyst','qfii','activity']:
  for exposure in ['positive_dose','eligible']:
   high=b.dose.gt(0)if exposure=='positive_dose'else b.eligible.eq(1);x=b.loc[high,c].dropna();y=b.loc[~high,c].dropna();sd=np.sqrt((x.var()+y.var())/2);balance.append(dict(feature=c,exposure=exposure,treated_n=len(x),control_n=len(y),treated_mean=x.mean(),control_mean=y.mean(),difference=x.mean()-y.mean(),smd=(x.mean()-y.mean())/sd if sd>0 else np.nan))
 pd.DataFrame(balance).to_csv(R/'balance.csv',index=False)
 log=pd.read_csv(R/'logs/metric_daily_build.csv');events=read('events.csv');mapping=read('event_date_map.csv');scale=[('R1关闭日期',int(mapping.closed.sum()),'dates'),('R1事件段',len(events),'episodes'),('主窗口日期',d.date.nunique(),'dates'),('主窗口股票',d.code.nunique(),'stocks'),('主窗口股票日',len(d),'stock_days'),('逐日原始分钟扫描',int(log.input_rows_scanned.sum()),'minute_rows'),('逐日筛中股票分钟',int(log.selected_minute_rows.sum()),'minute_rows'),('全部指标股票日',int(log.stock_days.sum()),'stock_days'),('原始分钟重复键',int(log.duplicate_minute_keys.sum()),'rows'),('IF延迟有效股票日',int(d.if_delay.count()),'stock_days'),('IH延迟有效股票日',int(d.ih_delay.count()),'stock_days')];scale.extend((m+'有效股票日',int(read('distributions.csv').query("metric == @m and variant == 'raw'").n.iloc[0]),'stock_days')for m in EXT);pd.DataFrame(scale,columns=['measure','value','unit']).to_csv(R/'data_scale.csv',index=False)
 # Frozen features must precede earliest controls. AH dates only explain assigned AH stocks.
 rawfeat=pd.read_parquet(T/'event_features.parquet');assert(rawfeat.loc[rawfeat.ah.eq(1),'hk_listing_date']<rawfeat.loc[rawfeat.ah.eq(1),'event_start']).all();q=rawfeat.dropna(subset=['qfii']);assert(q.announce_date<q.freeze_date).all();cc=rawfeat[rawfeat.cap_date.notna()];assert(cc.cap_date<cc.freeze_date).all()
 # Direct R1 baseline coefficient reconciliation; seed changes only resampling p, not estimates.
 old=pd.read_csv(R.parent/'tables/main_estimates.csv');new=f[f.specification.eq('baseline')&f.term.eq('closed_x')&f.metric.isin(PRIMARY)];comp=new.merge(old,on=['metric','variant','exposure'],suffixes=('_r2','_r1'),validate='1:1');comp['beta_abs_difference']=(comp.beta_r2-comp.beta_r1).abs();comp['se_abs_difference']=(comp.se_r2-comp.se_r1).abs();comp.to_csv(R/'tables/R1_reproduction_checks.csv',index=False)
 status=f[f.term.eq('closed_x')][[c for c in ['metric','variant','specification','exposure','status','n','reason']if c in f]].copy();status['category']='model';status['n_unit']='stock_days';other=[]
 other.extend([dict(metric=m,variant=v,specification='verified_HKopen_NB_suspension',exposure='dose',status='NO_VERIFIED_QUALIFYING_EVENT',n=0)for m in PRIMARY for v in ['raw','w01','w005']]);status=pd.concat([status,pd.DataFrame(other),read('fake_estimates.csv').query("term == 'closed_x'")[[ 'metric','variant','specification','exposure','status','n']]],ignore_index=True);extras=[]
 for file,category in [('matching_panel_estimates.csv','matched_panel'),('matching_estimates.csv','matched_event_DID'),('event_conservative_tests.csv','event_aggregate'),('reopening_backlog_estimates.csv','reopening')]:
  z=read(file)
  if category=='reopening':z=z[z.term.eq('backlog')]
  for row in z.to_dict('records'):
   name=row.get('specification',category)
   if 'neighbors'in row:name+='_k'+str(int(row['neighbors']))
   if 'quintile'in row:name+='_q'+str(int(row['quintile']))
   extras.append(dict(metric=row['metric'],variant=row.get('variant','raw'),specification=name,exposure='dose'if category=='reopening'else'group_contrast',status=row.get('status','OK'),n=row.get('n',row.get('events')),n_unit='events'if category in['matched_event_DID','event_aggregate']else'stock_days',category=category))
 status=pd.concat([status,pd.DataFrame(extras)],ignore_index=True);status.to_csv(R/'tables/specification_status.csv',index=False)
 # R1 secondary metrics and original placebo numbers are clearly labeled retained results.
 for src,dst in [('main_estimates.csv','R1_secondary_estimates.csv'),('placebo_estimates.csv','R1_placebo_estimates.csv'),('distributions.csv','R1_distributions.csv'),('mechanism_estimates.csv','R1_mechanism_estimates.csv')]:
  z=pd.read_csv(R.parent/'tables'/src)
  if src=='main_estimates.csv':z=z[~z.metric.isin(PRIMARY)]
  z['provenance']='R1 retained output; original seed 20261110';z.to_csv(R/'tables'/dst,index=False)
 checks=dict(main_panel_rows=len(d),R1_main_panel_rows=int(pd.read_csv(R.parent/'data_scale.csv').query("measure=='主窗口有效股票×日期'").value.iloc[0]),R1_beta_max_abs_difference=float(comp.beta_abs_difference.max()),R1_se_max_abs_difference=float(comp.se_abs_difference.max()),RI_fwl_max_abs_difference=float(f.get('ri_beta_abs_error',pd.Series(dtype=float)).max()),preregistration_sha256=hashlib.sha256((R/'PREREGISTRATION_R2.md').read_bytes()).hexdigest(),raw_duplicate_minutes=int(log.duplicate_minute_keys.sum()),future_lag_15_status='rank deficient by construction: 6 observations and 7 regressors')
 assert checks['main_panel_rows']==checks['R1_main_panel_rows'];assert checks['R1_beta_max_abs_difference']<1e-9;assert checks['R1_se_max_abs_difference']<1e-9;assert checks['RI_fwl_max_abs_difference']<1e-7
 (R/'meta/final_validation.json').write_text(json.dumps(dict(status='NUMERICAL_CHECKS_PASS_PENDING_DELIVERY',**checks),ensure_ascii=False,indent=2));return d,status,checks

def oster(f):
 rows=[]
 for m in PRIMARY:
  for v in ['raw','w01','w005']:
   g=f[f.metric.eq(m)&f.variant.eq(v)&f.exposure.eq('dose')&f.term.eq('closed_x')]
   for controlled,base in [('race_available_all','race_available_same_sample_baseline'),('race_full_all','race_full_same_sample_baseline')]:
    c=g[g.specification.eq(controlled)];b=g[g.specification.eq(base)]
    if not len(c)or not len(b)or c.beta.isna().all()or b.beta.isna().all():rows.append(dict(metric=m,variant=v,specification=controlled,status='UNAVAILABLE'));continue
    c=c.iloc[0];b=b.iloc[0];rmax=min(1,1.3*c.within_r2);den=(b.beta-c.beta)*(rmax-c.within_r2);delta=c.beta*(c.within_r2-b.within_r2)/den if den else np.nan;rows.append(dict(metric=m,variant=v,specification=controlled,beta_base=b.beta,beta_controlled=c.beta,coefficient_retained=c.beta/b.beta if b.beta else np.nan,R_base=b.within_r2,R_controlled=c.within_r2,Rmax=rmax,delta_approx=delta,n=c.n,status='OK'if np.isfinite(delta)else'UNDEFINED'))
 out=pd.DataFrame(rows);out.to_csv(R/'tables/oster_delta.csv',index=False);return out

def report(f,aux,fake,d,status,checks,ost):
 primary=f[f.metric.isin(PRIMARY)&f.variant.eq('w01')&f.term.eq('closed_x')&f.exposure.eq('dose')].copy();baseline=primary[primary.specification.eq('baseline')].set_index('metric');parts=['# 272 R2：价格延迟的渠道排除与机制统计结果\n','仅统计结果；固定种子20261111，R1定义与样本不改。A+H时点初版误用控制窗前冻结，部分raw规格运行后按用户要求更正为事件日前；原口径完整保留，详见第3c节和预注册更正记录。表中NA表示缺数据或不可识别，不表示效应为零。完整数值、三种缩尾、所有失败规格均见`tables/`。\n']
 def show(specs,cols=None):
  z=primary[primary.specification.isin(specs)].copy();default=['metric','specification','beta','se','p','wild_p','ri_p','q_bh','q_bh_wild','q_bh_ri','p_romano_wolf','n','wild_clusters','mde80'];return z[[c for c in(cols or default)if c in z]]
 section(parts,'1. 样本与复现',pd.read_csv(R/'data_scale.csv'),f"主窗含{len(d):,}个股票日、{d.code.nunique():,}只股票、{d.date.nunique()}个日期；四主指标的R1基准系数最大绝对复算差为{num(checks['R1_beta_max_abs_difference'])}。",'日历共46段，但最后一段2026-10-19已超出真实期货数据覆盖，价格延迟与滞后系数的有效独立段最多45；这些固定效应估计不能排除未观测的关闭日差异。')
 section(parts,'2. 四项主结果',show(['baseline']), '；'.join(f"{LABEL[m]} β={num(baseline.loc[m,'beta'])}，双向p={num(baseline.loc[m,'p'])}，wild p={num(baseline.loc[m,'wild_p'])}，RI p={num(baseline.loc[m,'ri_p'])}"for m in PRIMARY)+'。','wild采用R1固定设计的限制残差系数统计量，RW用相同联合系数分布/固定双向SE；未进行逐次bootstrap studentization，RI仍是条件正常日历诊断。跨全部1/99主规格的更严调整另见主表q_bh_all_main_w01与p_rw_all_main_w01。')
 z=show(['baseline','exclude_AH','AH_interactions','AH_only']);z['retained_vs_R1_baseline']=[row.beta/baseline.loc[row.metric,'beta']if pd.notna(row.get('beta'))and baseline.loc[row.metric,'beta']else np.nan for _,row in z.iterrows()]
 ah=primary[primary.specification.eq('exclude_AH')].set_index('metric');ret='；'.join(f"{LABEL[m]}剔除A+H后保留{num(100*ah.loc[m,'beta']/baseline.loc[m,'beta'])}%"for m in PRIMARY if m in ah.index)
 section(parts,'3. 港股休市渠道：剔除与交互',z,ret+'。','A/H对应以公开当前名单及上市日期反推，另补东北电气、昆明机床、海通证券、中集车辆及拉夏贝尔的上市/撤销区间；无法保证覆盖所有历史合并或退市对应关系。A+H标签说明两地上市，不能自动说明香港行情在每段正常提供了价格信息。')
 section(parts,'3c. 原控制窗冻结口径（完整保留）',show(['exclude_AH_control_freeze','AH_interactions_control_freeze','AH_only_control_freeze']),'此处保留初版更早冻结A+H状态的原规格，供与按用户要求的事件日前主口径直接比较。','初版A+H时点写错，部分raw估计后才更正；12个股票×事件标签不同。该更正不是事前注册，初始冻结文件、摘要及更正日志全部保留，不能掩盖这一事实。')
 ahaux=aux[aux.variant.eq('w01')&aux.specification.eq('AH_interactions')];section(parts,'3b. A+H全样本交互与线性组合',ahaux[[c for c in ['metric','term','beta','se','p','wild_p','ri_p','q_bh_auxiliary','p_rw_auxiliary','n','mde80']if c in ahaux]],'cx_ahdose为A+H与非A+H剂量斜率之差，ah_slope为全样本模型中A+H剂量斜率的重参数化估计。','A+H股数量远少于非A+H，组内方差和共同支持不同；AH_only与全样本AH线性组合也不必数值相同。')
 hk=status[status.specification.str.startswith('HK_')].groupby(['specification','status'],dropna=False).size().reset_index(name='规格行数');section(parts,'4. 恒生暴露吸收',hk,'HSI/HSCEI历史分钟未取得，相关及beta四个吸收规格和同时加入规格均不可估计。','这是排除港股共同信息渠道的关键缺口；不能把未估计说成剂量系数未被吸收，不能用日频、ETF或期货替代。')
 race=show([s for s in primary.specification.unique()if s.startswith('race_')]);race['retained_vs_uncontrolled']=race.apply(lambda row:row.beta/baseline.loc[row.metric,'beta']if pd.notna(row.get('beta'))and baseline.loc[row.metric,'beta']else np.nan,axis=1);race.to_csv(R/'tables/coefficient_stability.csv',index=False)
 section(parts,'5. 规模、指数、beta与延迟水平赛马',race,'七项控制（不含分析师）后IF/IH延迟保留'+num(100*primary.query("metric == 'if_delay' and specification == 'race_cumulative_7'").beta.iloc[0]/baseline.loc['if_delay','beta'])+'%/'+num(100*primary.query("metric == 'ih_delay' and specification == 'race_cumulative_7'").beta.iloc[0]/baseline.loc['ih_delay','beta'])+'%；完整八项后四个主结果均未通过四指标族Romano–Wolf的5%门槛。','QDC指数成分仅2026-05-29起，已用通过时点核查的BaoStock历史名单补充；补充BaoStock逐事件历史快照后，完整八项模型有历史成分支持；分析师365日窗口仍令其主要限于2021年以后的事件，不能据此宣布排除了2017年以来全部时期的规模与指数渠道。分析师完整365日窗口进一步改变样本，系数变化同时可能反映样本选择。')
 section(parts,'6. Oster选择敏感度',ost[ost.variant.eq('w01')],'δ按预注册的比例选择近似和同样本within R²计算，Rmax=min(1,1.3R受控)。','δ是带假设的近似敏感度量；股票与日期FE后的R²及关闭交互并不能证明可观测和不可观测选择可比，完整控制样本与最初全样本不同。')
 section(parts,'7. 标的内部与市值组内比较',show(['eligible_only','size_decile_date_FE']),'内部标的与市值组×日期FE中，IF/IH延迟均为正且RW p<0.001，两项滞后系数和均未通过RW的5%门槛。','市值组内并不随机分配剂量；十分位×日期FE的RI为相同R1区组日历上的限制得分检验，不能与其他规格的系数RI当成完全同一统计量。')
 matches=read('matching_estimates.csv');section(parts,'8. 匹配事件内差中差',matches[matches.variant.eq('w01')], '使用BaoStock冻结日前的证监会行业作精确匹配，1–3邻居、距离≤2及事件等权结果全部列出；不含行业的匹配保留为辅助。','历史行业来自事后获取的供应商历史快照，原始updateDate和请求日期均早于冻结日；个别停牌、退市和缺行业股票无法匹配。行业精确匹配加卡尺也可能改变高剂量样本。匹配后均衡见matching_balance.csv，缺少关闭/正常有效结果的匹配另有流失。')
 matched=read('matching_panel_estimates.csv');section(parts,'8b. 匹配面板双向聚类',matched[matched.variant.eq('w01')][[c for c in ['metric','specification','neighbors','beta','se','p','wild_p','q_bh','p_romano_wolf','n','wild_clusters','mde80']if c in matched]],'匹配面板另报股票/日期FE、归一权重、双向聚类、事件wild及四指标族调整。','面板FE与先做事件内差再事件等权的估计量不同；匹配不是随机赋值，未给匹配面板伪造日历RI。')
 ext=f[f.metric.isin(EXT)&f.variant.eq('w01')&f.term.eq('closed_x')&f.exposure.eq('dose')];section(parts,'9. 期货大动分钟与不同频率',ext[[c for c in ['metric','status','beta','se','p','wild_p','ri_p','n','mde80']if c in ext]],'大动分钟分别用当日前10%与事件前60正常日阈值；5分钟延迟可估，15分钟即时加五滞后因观测数小于参数数不可估。','大动日回归通常只有约24分钟且需至少12个有效分钟，系数噪声大；当日阈值是事后状态。5分钟模型的五滞后覆盖5–25分钟，和1分钟模型时距不同，不能逐项等同解释。')
 section(parts,'10. IF实现方差分组',show(['RV_high','RV_low']),'按事件段关闭日IF实现方差均值的中位数分组，对照窗继承事件分组。','高低波动由事后实现状态定义；组间差别不能被解释为关闭冲击的外生强度差别，也不是分组效应差异的正式检验。')
 auxw=aux[aux.variant.eq('w01')&aux.specification.isin(['dose_activity','dose_QFII'])];section(parts,'11. 活跃度与QFII对照剂量',pd.concat([show(['dose_activity','dose_QFII']),auxw[[c for c in ['metric','specification','term','beta','se','p','wild_p','ri_p','q_bh_auxiliary','p_rw_auxiliary','n','wild_clusters','mde80']if c in auxw]]],ignore_index=True),'QFII剂量在'+str(int(((auxw.term.eq('cx_qfii'))&(auxw.wild_p.lt(.05))).sum()))+'个主指标上wild p<0.05（共4项）；逐项系数、双向p与辅助族BH/RW均如表。','QFII仅季度十大股东中的明确QFII，不是全部境外场外交易；零值只对完整披露赋值。2024-08后公开季频造成60日活跃度缺失；这种缺失不能补成零。若QFII同样有效应，会削弱“仅北向缺席”的解释。')
 rec=read('reopening_backlog_estimates.csv');section(parts,'12. 恢复首日回补',rec[rec.term.eq('backlog')][[c for c in ['metric','quintile','beta','se','p','wild_p','n','wild_clusters','mde80']if c in rec]],'按剂量五组分别报告R1日内口径，以及关闭段末收盘到恢复日10:00/收盘的复权跨日回补。','日内口径漏掉隔夜开盘跳空，补充跨日口径使用QDC hfq因子按日期比值调整；累计信息缺口仍是事前注册的IF/个股日内累计定义，没有覆盖关闭段内所有隔夜信息。事前beta误差与缺口测量误差可能影响斜率。')
 section(parts,'13. 假事件与既有安慰剂',fake[fake.variant.eq('w01')&fake.term.eq('closed_x')][[c for c in ['metric','specification','beta','se','p','wild_p','ri_p','ri_B','q_bh','p_romano_wolf','n']if c in fake]],'前移20/40个A交易日且同星期、整段北向正常的固定假事件已重估；R1共同假日前后与北开南闭保留在R1_placebo_estimates.csv。','前移20/40个交易日通常不再同星期，严格规则会剔除很多段；假事件区组RI可能无同年/月/星期支持。港交所可核实的天气候选往往香港也关闭或只半日暂停，未核实到符合A开、HK开、NB全日暂停的额外事件，不能声称这类事件不存在。')
 section(parts,'14. 分期',show([s for s in primary.specification.unique()if s.startswith('period_')]),'2017–2019、2020–2023、2024年8月前、8月后及全样本8月前均固定列出。','持股披露转季频、可用股票与期货覆盖共同变化；分期系数差不能单独归因为披露制度，子期事件数也明显下降。')
 agg=read('event_conservative_tests.csv');section(parts,'15. 事件段最保守推断',agg[agg.variant.eq('w01')],'；'.join(f"{LABEL[row.metric]}：事件t p={num(row.p)}、符号p={num(row.sign_p)}，有效段数{int(row.events)}"for row in agg[agg.variant.eq('w01')].itertuples())+'。','有效期货事件最多45而非名义46；这种聚合与连续剂量股票/日期FE估计量不同，t检验和符号检验若不显著，不能用海量股票日掩盖。')
 econ=show(['baseline','exclude_AH','race_available_all','race_cumulative_7','race_full_all','eligible_only'],['metric','specification','beta','dose_p25','dose_p75','effect_iqr','effect_iqr_over_mean','effect_iqr_over_sd','effect_iqr_over_raw_mean','effect_iqr_over_raw_sd','late_bp_per_1pct_futures_iqr','mde80','mde80_iqr']);econ.loc[~econ.metric.str.contains('lag'),'late_bp_per_1pct_futures_iqr']=np.nan
 section(parts,'16. 经济量级与80%功效MDE',econ,'P25到P75效应按每个规格的完整样本股票×事件等权剂量分位换算；滞后系数变化×100给出期货变动1%后迟1–5分钟反映的bp变化。','全样本剂量下四分位常为0，IQR含标的与非标的差异；内部标的IQR更适合解释内部变异。MDE是双侧5%、80%功效的t加正态近似，未按跨规格多重检验扩大；不能用“不显著”推出经济效应为零。')
 eligible=f[f.specification.eq('baseline')&f.variant.eq('w01')&f.exposure.eq('eligible')&f.term.eq('closed_x')&f.metric.isin(PRIMARY)];section(parts,'17. 标的相对非标的量级',eligible[[c for c in ['metric','beta','se','p','wild_p','ri_p','sample_y_mean','sample_y_sd','mde80']if c in eligible]],'资格二值系数直接是标的相对非标的的关闭日差异变化。','历史资格及持股不等价于实际关闭日交易需要；资格二值也是公司规模、指数和信息环境的组合标签。')
 dist=read('distributions.csv');section(parts,'18. 分布诊断与全部规格核数',dist[dist.metric.isin(PRIMARY)&dist.variant.eq('raw')],f"主四指标三种缩尾、频率/机制扩展、所有失败状态均保留；登记状态表共有{len(status)}行。",'分布重尾和部分逐日延迟接近边界会影响OLS；缩尾仅使用过去正常日阈值，不等于消除了分布差异。完整分布见distributions.csv，R1其余指标只作附表。')
 adverse=[]
 for m in PRIMARY:
  arow=ah.loc[m];c=primary[primary.metric.eq(m)&primary.specification.eq('race_available_all')];full=primary[primary.metric.eq(m)&primary.specification.eq('race_full_all')];noanalyst=primary[primary.metric.eq(m)&primary.specification.eq('race_cumulative_7')];same=primary[primary.metric.eq(m)&primary.specification.eq('race_full_same_sample_baseline')];q=auxw[auxw.metric.eq(m)&auxw.term.eq('cx_qfii')];g=agg[agg.metric.eq(m)&agg.variant.eq('w01')]
  adverse.append(dict(metric=LABEL[m],baseline_beta=baseline.loc[m,'beta'],nonAH_beta=arow.beta,nonAH_retained_pct=100*arow.beta/baseline.loc[m,'beta'],race_available_beta=c.beta.iloc[0]if len(c)else np.nan,race_retained_vs_full_baseline_pct=100*c.beta.iloc[0]/baseline.loc[m,'beta']if len(c)else np.nan,race_seven_without_analyst_beta=noanalyst.beta.iloc[0]if len(noanalyst)else np.nan,race_seven_retained_vs_R1_pct=100*noanalyst.beta.iloc[0]/baseline.loc[m,'beta']if len(noanalyst)else np.nan,race_full_beta=full.beta.iloc[0]if len(full)else np.nan,race_full_retained_vs_R1_pct=100*full.beta.iloc[0]/baseline.loc[m,'beta']if len(full)else np.nan,race_full_retained_same_sample_pct=100*full.beta.iloc[0]/same.beta.iloc[0]if len(full)and len(same)and same.beta.iloc[0]else np.nan,QFII_beta=q.beta.iloc[0]if len(q)else np.nan,QFII_two_way_p=q.p.iloc[0]if len(q)else np.nan,QFII_wild_p=q.wild_p.iloc[0]if len(q)else np.nan,event_t_p=g.p.iloc[0]if len(g)else np.nan,event_sign_p=g.sign_p.iloc[0]if len(g)else np.nan))
 adverse=pd.DataFrame(adverse);adverse.to_csv(R/'tables/adverse_facts.csv',index=False)
 section(parts,'19. 最不利事实汇总',adverse,'剔除A+H后延迟系数基本保留，但完整八项赛马仅余约20%–23%且四主结果的RW p均大于0.05；QFII剂量四项wild p均大于0.24。','最直接的不利统计事实是：两项滞后系数和在基准中即不显著，完整赛马中点估计转为轻微负值；事件等权t检验的IF/IH滞后项p分别为0.050686与0.050009；完整八项延迟RW p分别为0.0792与0.1282。另有以下限制：①恒生分钟暴露不可估；②完整赛马受分析师历史覆盖和完整样本限制；③行业匹配有共同支持和卡尺筛选且不等于随机分配；④QFII未检出显著效应，但仅是十大股东披露代理；⑤有效期货事件45段，最保守p必须正视；⑥日内恢复口径漏隔夜跳空，补充复权跨日口径仍依赖代理信息缺口；⑦15分钟五滞后模型不满秩；⑧季频后活跃度缺失；⑨当前A/H名单的历史存续覆盖未必完全；⑩RW与wild未逐次studentize，条件RI不等于随机化自然实验；⑪A+H时点在部分raw估计后更正，须连同完整保留的原时点结果读取。')
 parts.extend(['\n## 20. 文件与复现\n','| 文件 | 内容 |\n|---|---|\n| `tables/main_estimates.csv` | 主四指标全部规格、三变换、双向SE、wild、RI、BH/RW、MDE |\n| `tables/coefficient_stability.csv` | 剂量系数逐项与全部控制稳定性 |\n| `tables/oster_delta.csv` | 同样本Oster近似δ |\n| `tables/specification_status.csv` | 包含不可估计与缺来源的登记清单 |\n| `sample_by_event.csv` / `balance.csv` / `data_scale.csv` | 逐事件样本、事前差异、原始处理规模 |\n| `tables/R1_secondary_estimates.csv` / `R1_placebo_estimates.csv` | R1其他指标与既有安慰剂，保留原种子 |\n| `meta/final_validation.json` | R1重算、RI二次型、时点及核数检查 |\n| `run_all.sh` | 一键复现；临时目录272 |\n','一句话结论：全部统计结果按登记规格交付，缺失来源与失败规格都有显式状态。\n','最不利事实：本轮部分关键渠道检验因数据历史覆盖不足仍未闭合，结果只能支持实际可估计范围内的判断。\n'])
 (R/'RESULTS_FOR_CLAUDE.md').write_text('\n'.join(parts))

def main():
 import platform,threadpoolctl
 peaks=[]
 for log in (R/'logs').glob('resources*.jsonl'):
  for line in log.open():
   try:
    z=json.loads(line);value=z.get('rss_bytes',z.get('rss',z.get('aggregate_rss_gb',0)*1e9));peaks.append(value)
   except (ValueError,TypeError):pass
 peak=max(peaks,default=0);assert peak<8e9,peak
 runtime=dict(seed=20261111,workers=4,wide_model_memory_scheduler='one active wide task, four fresh worker processes; idle worker exits after one task',peak_observed_aggregate_rss_gb=peak/1e9,working_circuit_breaker_gb=6.8,hard_budget_gb=8,python=platform.python_version(),libraries=threadpoolctl.threadpool_info(),numeric_threads={k:os.environ.get(k)for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS']});(R/'meta/runtime.json').write_text(json.dumps(runtime,indent=2))
 f,aux,fake=collect();
 # Matched panel families are four outcomes per kind/neighbour/variant.
 matched=read('matching_panel_estimates.csv');mb={}
 for m in PRIMARY:
  with np.load(T/f'bootstrap_matching_{m}.npz')as z:
   for j,v in enumerate(z['boot']):mb[(m,j)]=v
 matched['term']='closed_x';matched['exposure']='matched_high';matched=corrections(matched,mb,['specification','neighbors','variant']);matched.to_csv(R/'tables/matching_panel_estimates.csv',index=False)
 d,status,checks=audits(f);ost=oster(f);report(f,aux,fake,d,status,checks,ost)
 from estimate_r2 import specs
 expected={(m,v,s,e)for m in PRIMARY for v in ['raw','w01','w005']for s,_,_ in specs()for e in(['dose','eligible']if s=='baseline'else['dose'])};actual=f[f.metric.isin(PRIMARY)&f.term.eq('closed_x')];assert not actual.duplicated(['metric','variant','specification','exposure']).any();assert set(zip(actual.metric,actual.variant,actual.specification,actual.exposure))==expected
 valid=actual[actual.status.eq('OK')];assert np.isfinite(valid.mde80).all();assert valid.wild_B.eq(9999).all();assert valid.family_size.dropna().le(4).all();assert(valid.q_bh.dropna().between(0,1)).all();assert(valid.p_romano_wolf.dropna().between(0,1)).all()
 required=['RESULTS_FOR_CLAUDE.md','tables/main_estimates.csv','tables/specification_status.csv','tables/distributions.csv','tables/adverse_facts.csv','tables/matching_estimates.csv','tables/matching_panel_estimates.csv','tables/reopening_backlog_estimates.csv','tables/fake_estimates.csv','tables/event_conservative_tests.csv','sample_by_event.csv','balance.csv','data_scale.csv','run_all.sh']
 for name in required:assert(R/name).is_file()and(R/name).stat().st_size>10,name
 validation=json.loads((R/'meta/final_validation.json').read_text());validation.update(status='PASS',registered_main_grid_rows=len(expected),checked_main_grid_rows=len(actual),required_deliverables=required,AH_timing_correction_disclosed=True);(R/'meta/final_validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2))
 outputs={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest()for p in R.rglob('*')if p.is_file()and any(x in p.parts for x in ['tables','code'])and'__pycache__'not in p.parts};(R/'meta/output_sha256.json').write_text(json.dumps(outputs,indent=2));print(json.dumps(checks,ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':main()
