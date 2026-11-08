# 一键复现

在本目录执行 `bash run_all.sh`。固定种子20261110；4个重工作进程；数值库线程均为1；总体工作RSS预算6.8GB，硬上限8GB。主入口只运行预注册规格，不搜索显著结果。

依赖：Python3.12、uv、7zz；Python包版本锁定于 `requirements.lock`。环境位于 `/Volumes/Extreme SSD/T9/_tmp/266/venv`，若不存在会自动安装。原始数据保持只读：

- A股按日分钟原始成员：`/Volumes/Extreme SSD/T9/codex项目/A股分钟线+日频量价/A股分钟数据/1m_price_zip/2017.zip` 至 `2026.zip`。
- QDC分钟及日频、持股、ST与市值：`/Volumes/Extreme SSD/QDC/data/QDCData/`。2026-04-10以后的分钟用按日筛选、65536行批次读取；不整表读入。
- IF/IH真实合约分钟：`/Volumes/T9/期货1分钟2004~2608/CFFEX.7z`。只读这一原盘路径，解压和中间文件全部写到本任务同盘临时目录；不往 `/Volumes/T9` 写入。
- 官方原始日历、标的变更和披露公告保留在 `meta/official_raw/`，URL、UTC抓取时刻、SHA256和原始时间精度见对应provenance/receipts文件。固定复用本轮冻结的原始记录，不自动刷新或把后续公告写入历史。

实际行情样本截止2026-10-30，已固定于 `meta/frozen_input_cutoff.json`。脚本先核对 `meta/input_manifest.json` 中实际使用原始文件的SHA256；如果外部原始数据已变化，会明确拒绝悄悄混用不同版本。未用于估计的巨量cn_tick库存不作无意义全盘哈希。

查重的判断本身是人工核验记录，不是自动“查无同设计”的检索程序。复现脚本先检查 `meta/literature_gate.json` 与预注册SHA256，确认本轮冻结的可估计状态。查询原响应可重新核查。

主链顺序：官方日历 → 事前暴露 → 真实期货主力（前日成交量） → 按日分钟聚合 → 历史年龄/ST过滤 → 只用过去正常日的缩尾 → 主FE与双向聚类 → 9999次wild/9999次RI → 事前分组、恢复/反转、动态 → 两类安慰剂 → 核数与交付校验。

计算结束自动清理本任务大中间文件，保留数值环境与最终统计表。需要逐行检查中间面板时执行 `KEEP_INTERMEDIATES=1 bash run_all.sh`，检查完成后运行 `.../_tmp/266/venv/bin/python code/cleanup.py`。

主表：`tables/main_estimates.csv`；全分布：`tables/distributions.csv`；逐事件：`sample_by_event.csv`；组间事前差：`balance.csv`；核数：`data_scale.csv`；安慰剂与机制：`tables/placebo_estimates.csv`、`tables/mechanism_estimates.csv`、`tables/dynamic_estimates.csv`。报告中的全部数值直接由这些表生成。
