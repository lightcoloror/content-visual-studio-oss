# 原创综合适配器 v2

更新：2026-09-13 09:42:00（Asia/Shanghai）。工具/模型：Codex / GPT-6 Astra / high。

`scripts/original_synthesis_adapter.py` 的机器版本为 `2.0.0`。入口继续消费已准入、带哈希绑定的 QRP pack 与归档材料，输出 Content 候选。它不执行选题研究，不声称从 question-only 输入自动发现了这些证据。

## 稳定入口

```text
python -X utf8 -B scripts/original_synthesis_adapter.py
  --plan <editorial-plan.json> --expected-plan-sha256 <sha256>
  --pack <offline-evidence-brief.v1.json> --expected-pack-sha256 <sha256>
  --upstream <archive-input-directory> --output <new-workspace-directory>
  --text-only
```

示例为分行展示，执行时合并成一行。`--upstream` 延用既有 consumer-index.json/public-input.json 合同。依赖已存在的 sibling QRP、self-media gate 与本项目 HTML pipeline；没有新依赖或在线模型。

`--text-only` 不调用 HTML 适配器，不生成 SVG、图片或视频。文字版图文候选和口播均包含出处；visual-plan.json 复用 Content 的 `render_recipe=none`。允许无图，后续审核任务可另选视觉路线。未指定该参数时保留既有 HTML 文本适配能力，仍不启动浏览器。

## 输入、事实层次与兼容性

接受 `content-original-editorial-plan.v1` 和 `.v2`；输出的 adapter_version 均为 2.0.0。v1 是兼容输入，不保证覆盖旧输出为相同字节。旧候选和回执保留，新版本写新目录。

v2 短引单位必须显式包含 `quote_evidence_id` 和 `quote_source_id`，后者必须等于该 evidence 的真实 source_id。相同文字出现在不同来源时，不能借字符串相同换出处。来源显示名从已校验 source.title 派生，缺标题仅使用其 URL 主机名，不回退到示例来源。

内容 ID 与事实卡 ID 从题目、标题、来源内容哈希及主张派生。不同主题可重复使用 c1/e1 等局部编号，边界是各自 content_id/fact_card_id。局部编号不作为全局身份。

来源完整性与事实审核分开：逐源 capture_status/capture_scope/content_ok 保留，缺失为 unknown/null；汇总不同值为 mixed。full 不自动等于 verified。直接引文核对也不等于事实核实。

`source_fact` 只在可选 `reviewed_research` 通过现有原生证据政策后可用。该字段形如 `{"path":"reviewed-research.json","sha256":"..."}`，路径限制在 upstream 内。适配器复用 research-output.v1 schema 和 `validate_research_semantics`，再逐项核对原始 claim 文本、证据 excerpt、来源 URL/内容哈希及 complete capture；只有政策中的 verified_claims 能进入 source_fact。原始候选源不被改写为 reviewed。没有该政策时仍是 agent_inference、verified_quote 或待作者确认的 author_position。

## 恢复与 RCP 消费

`--stop-after N` 保留既有中断注入方式；恢复时去掉该参数。先检查全部既存产物字节，再补写缺失项；不同输入不得覆盖同目录。checkpoint 绑定输入 SHA、产物 SHA 与适配器语义版本，不要求整个可变仓库 Git HEAD 相等。

完成入口为 `consumer-index.json`，schema 为 `content-original-consumer-index.v2`。包含 content_id、closure_run_id、adapter_version、candidate_only、publication_authorized=false、text_only、逐文件 SHA 和跨平台一致性回执地址。索引覆盖 article.md、oral-script.md、content-item.json、fact-card.json、trace.json、visual-plan.json 和 review-packet.json。源事实存在也不授予发布权。

结构测试覆盖长中文标题与超过三个主张，输出不再使用固定尺寸示意图，因此不产生旧 SVG 的框高溢出。浏览器视觉质量、真人采用及真实发布不属于这些检查的结论。
