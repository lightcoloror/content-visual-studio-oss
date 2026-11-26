# 原创综合候选转换

更新：2026-09-12 19:07:00（Asia/Shanghai）。实际工具/模型：Codex / GPT-6 Astra。

入口为 `scripts/original_synthesis_adapter.py`。它消费固定 SHA 的编辑计划、QRP offline evidence brief 和公开归档 consumer index，复用 QRP public archive loader、候选转换器、Content/事实卡合同、HTML 适配器及跨平台一致性 gate。没有新写作引擎、模型调用、抓取或发布动作。

## 意图、决策、理由、证据、生效范围、回滚

- 意图：把已准入的短摘录变成原创解释结构的图文与口播候选，同时保留逐项追溯。
- 决策：使用 mechanism-explanation 路由和同一组规范主张。事实卡保持 draft。story-arc 的故事设计门仅适用于故事路由；本次没有可用真人案例，不虚构故事卡。
- 理由：现有 QRP builder 提供可靠的候选合同，但默认稿主要按主张排列；现有跨平台 gate 只检查声明与哈希。本适配器补上固定编辑计划、正文确定性编译与完整比对。
- 证据：`outputs/content-original-synthesis-20260912-01/acceptance-v2.json`；13 项定向测试、实际 CLI 暂停/恢复、重复执行字节及修改时间不变。
- 生效范围：显式运行的新入口与本次 `candidate-v2`。共享 Registry、已有源码和服务没有变更；SOURCE_INVENTORY 对 Content 的反向链接仍为 missing，本任务没有补登记或提升成熟度。
- 回滚：停止使用本入口即可。旧 candidate 保留为历史证据，当前有效目录是 candidate-v2；不删除输出，不回滚其他人的 dirty edits。

## 调用与恢复

必填参数：`--plan`、`--expected-plan-sha256`、`--pack`、`--expected-pack-sha256`、`--upstream`、`--output`。计划 SHA 由调用者从已审阅的任务材料取得。输出必须在工作区内以满足现有 gate 的路径合同。

`--stop-after N` 用于中断注入；恢复时移除此参数。先写 checkpoint，再写候选。所有既存文件先按预期字节比对，出现漂移就停止，不覆盖。新代码或新计划使用新输出目录；gate 回执名绑定计划和输出路径。正式消费以 review-packet 出现、当前 gate 验证通过为完成条件，checkpoint 的 prepared_candidate 不表示完成。

输入哈希有两种：consumer index 的 artifact SHA 绑定原始文件字节；QRP input SHA 绑定 native loader 核验并补入 capture 字段后的规范 JSON。不得混用。

## 类型与能力边界

`source_fact` 在本次 partial 输入上不准入，数量为零。`verified_quote` 只表示引文字符串存在于准入摘录；不表示产品事实被人类核实。`author_position` 是拟作者观点，等待作者认可。`agent_inference` 中的文档解释保持与上游主张一致，其余连接句是明确标记的解释或建议。

缺来源 case/number 留在 withheld，状态 needs_source；平台样本不能进入事实依据。两种文本都要求完整的同一主张集合。图示由相同主张生成，属于概念示意，未进行浏览器视觉验收。

机器检查不能识别任意自然语言中伪装的案例、暗示或拼写出的所有数字。固定计划的 SHA 能阻止未经重新审阅的文字替换，字段/字符串检查能拒绝已覆盖的反例；它们不是语义真值判定器。人工审核、产品实测、录制和发布仍未执行。
