# R4 一键复现

在R4目录运行 `bash run_all.sh`。固定种子20261117；最多4个重工作进程；数值库单线程；合计RSS每0.05秒监测、4.4GB提前停止，5GB预算。所有大临时资料只在`/Volumes/Extreme SSD/T9/_tmp/283/`。完成核验后自动删除；检查中间面板可用`KEEP_INTERMEDIATES=1 bash run_all.sh`，检查完执行`.../_tmp/266/venv/bin/python code/cleanup.py`。

原始数据路径和截止日继承父目录R1/R2。原始A股按日分钟ZIP在`/Volumes/Extreme SSD/T9/codex项目/A股分钟线+日频量价/A股分钟数据/1m_price_zip/`；后段用QDC stocks_1m分块回补。真实中金所合约只读`/Volumes/T9/期货1分钟2004~2608/CFFEX.7z`，解压在_tmp/283；不向/Volumes/T9写入。IF/IH前一日成交量选主力与分钟端点严格调用原代码。主指标保留180分钟、上市60日、ST、一字价及成交额筛选。

优先使用仍存在的R3b期货及逐日指标作数值核对缓存；缓存不是复现前提，主指标与其他描述变量都重新从按日原始数据计算。若期货缓存也已清理，则按R1代码重建。逐日缓存匹配结果记在分钟日志。冻结暴露、控制、原日历使用R1/R2保存CSV；不刷新历史标的名单。输入摘要见tables/frozen_input_manifest.csv。

运行顺序：预注册摘要核对→原日历及共享Webb/RI日历→六只ETF逐日择代理→按日按股读分钟→原样本和历史扩展缩尾→公开季末快照与持久性→公布日对齐国际化→港股事前暴露→新增控制事前截面缩尾→三变换全规格→样本内描述/事件聚类平衡→直接堆叠分钟OLS核验与R2主基准复现→中文统计交付。

所有结果变量的缩尾完全调用R1 build_panel；新增连续控制用冻结前可用截面阈值。剂量与0/1不缩尾，断言在tables/dose_binary_unchanged_assertions.csv。宽规格为满足5GB总内存上限，采用按列调用原R1 FE投影、磁盘列存储、分块累加交叉积的执行适配；R1双向聚类校正和R2 FWL/Webb/RI代数不改。主IF基准逐项对照原R2 `_inference` 的系数、SE、p、wild、RI及9999次bootstrap系数，检查表为bounded_vs_original_r2_inference.csv。所有严格缺数据规格有状态行，可得项联合规格明确另名。

季频模拟用自然季末后的第5个正常北向日披露、次日可用（严格早于冻结）。最后日频剂量2024-08-16只用于后段。年报分部与财务报表max(notice_date, UPDATE_DATE)对齐，只用最近已知年报；供应商修订历史不完整的局限在结果文件明确披露。行业出口代理不声称来自投入产出表。cn_estimates的财政年不当作历史报告日期；早期覆盖使用CNINFO declare_date档案，仅填R2原缺失，已有值保留。

文献使用Crossref原API和OpenAlex补充，响应在meta/literature_raw。同一URL缓存不可用于不同DOI；每份OpenAlex补摘要响应校验DOI。打印年与线上年分别保留。当前没有配置M5远程入口，取数走执行主机现有网络并留主机记录。HSCEI在global_index_1d中缺失；保留Yahoo限流响应，随后以东方财富公开历史接口取得真实HSCEI收盘序列，固定CSV和原响应摘要留在meta，复现核对CSV SHA256。数据可用性更新及原缺数据状态均归档，不改原规格。

主要交付：RESULTS_FOR_CLAUDE.md；tables/main_estimates.csv与全部低阶项；holding_frequency_comparison.csv；descriptive_statistics.csv；balance_stock_episode.csv；international_annual_sources.csv；refs_verified.csv与refs_candidates.csv。所有登记规格必须为四指标×三变换保留状态。meta/validation.json核验覆盖，logs/记录阶段与资源峰值。

冻结特征表中report_date_x为原QFII报告期、report_date_y为国际化年报期，known_date为国际化可用日。sample_by_event.csv保留全部46个官方事件（包括最后主结果为0条的事件）。持久性日期支持表显示季度末或目标A日缺快照的全部计划格；不将缺快照补零。

事件计数以原R2冻结日分界2024-08-19为准；官方前35/后11段，主结果可估计前35/后10段。预注册文字“前36段”属于计数笔误，代码始终沿用原日期分界，锁定文件未改。

部分结果产生后的同样本检查发现，替代剂量和不含Hold的国际化对照会额外纳入少量原Hold未知观察；统一要求原Hold已知后，全部受影响登记规格已重跑。修正前结果和证据分别保留在tables/sample_implementation_before_correction.csv及meta/sample_implementation_correction.json。主回归及港股吸收的系数、SE及单项wild/RI不受影响；联合多重检验校正重新计算。两个以上新增控制的规格单个驻留，单控制最多2个，零控制最多4个，三重交互最多2个同时驻留。历史执行曾在四控制×四并行时短时达到5.262GB，已触发停机；此后降并发、提高监测频率，所有早停记录和恢复均在logs/保留，不声称历史全过程未超过5GB。

第一股东字段修正：seq_no是记录序号，shareholder_rank才是持股排名。真实rank=1记录按公告日与报告期严格早于冻结匹配，QFII/明确外资为1，国家队/社保等明确境内类别为0，其余保持未知。初始24个缺数据状态保留归档，修正后只补跑原登记第一股东规格；非第一股东特征逐项不变。
