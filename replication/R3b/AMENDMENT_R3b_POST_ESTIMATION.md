# R3b 事后实现更正：无事前对照的假事件窗口

2026-11-07（Asia/Seoul）。最终冻结时点检查在全部主估计和联合比较数值已被观察后，发现6个一周前假事件的同星期窗口没有可用的事前对照。初版以最早事后对照日冻结，形成向前赋值，违反原预注册的事前信息要求。本更正不是事前注册。

剔除6个不合格窗口（US 2、UK 1、ALL 3），不搜索替代日期，也不放宽同星期前后1–3周规则；剩余窗口仍在最早事前对照日冻结。仅重估US/UK/ALL的假事件同星期规格，四指标×三变换×两暴露，共72行。真实假日主估计、R1型假事件窗口、事件日前的所有有效冻结及全部联合回归不变。

旧的72行（含原多重调整）存档于tables/PRE_CORRECTION_fake_weekday_estimates.csv，旧事件检验存档于tables/PRE_CORRECTION_event_tests.csv；它们是有前视错误的版本，不作为有效稳健性证据。原事件/日期/冻结表及当时结果文件留于meta/boundary_original。拒绝窗口、时间与范围见tables/stack_window_rejections.csv及meta/precontrol_correction.json。

实现保持事件ID不重编号，防止其他冻结和共同随机权重改变；估计读取只使用当前有效事件ID。原PREREGISTRATION_R3b.md与锁定SHA保持原样，明确披露本项在估计后的更正。
