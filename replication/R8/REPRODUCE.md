# R8 一键复现

在本目录执行：

```bash
./run_all.sh
```

使用本机既有Python 3.12环境`/Volumes/Extreme SSD/T9/_tmp/266/venv/bin/python`，依赖版本见`requirements.lock`。需要`7zz`及C++编译器。原始分钟ZIP位于`/Volumes/Extreme SSD/T9/codex项目/A股分钟线+日频量价/A股分钟数据/1m_price_zip/`，QDC位于`/Volumes/Extreme SSD/QDC/data/QDCData/`，期货原始7z沿原266实际路径`/Volumes/T9/期货1分钟2004~2608/CFFEX.7z`只读。

冻结输入为父目录266原设计/股票总体/日历、R2原五分位及只卖来源、R4最终冻结特征、R5事件类型、R6天气设计/冻结剂量/原汇总缩尾阈值、R7已验收美国冻结控制。只卖来源为同层`nb_sellonly`（286）。所有大中间文件写`/Volumes/Extreme SSD/T9/_tmp/288/`，与其他任务隔离；验证通过后自动清除。`KEEP_INTERMEDIATES=1 ./run_all.sh`保留缓存。默认重新生成本轮可重建缓存和结果，保留预注册与源数据；`RESUME=1 ./run_all.sh`使用本任务已有检查点。冷启动不依赖旧轮已清理的缓存。

6个工作进程，数值库单线程。面板使用6进程池、同时放行3个重股票块并每6块重启池；回归使用上限6个进程的池，准备/校准独立退出，每规格使用一次性进程，按保守RSS预算合计≤9.5GB安排可承载的独立规格并行，上限6个；动态和特别大的规格单独运行，避免完成任务的分配器页继续计入RSS，以控制进程树RSS；分钟/解压/按股段汇总/池化阈值均使用6工作进程。资源保护器在12GB提前熔断，硬预算13GB。所有分钟输入按日、65536行批读、250股块计算。归档解压日文件随用随删。

顺序：预注册锁→真实期货合约→分钟指标及充分统计量→四类安静日设计与公开持股冻结→历史缩尾面板→按事件族精确分区→市场状态/组差/QFII/辅助/动态→股段汇总及Day/Next联合区间→原9999日历重新汇总的共同模式样本RI→天气/只卖Webb→中文结果→原轮系数/样本校准及验收。

统计口径与例外见`PREREGISTRATION_R8.md`、`meta/implementation_notes.md`和中文结果。`tables/delivery_validation.csv`给校准状态；`meta/output_code_manifest.json`给代码/表哈希；`logs/stage_resource_receipts.jsonl`给实际进程树内存记录。
