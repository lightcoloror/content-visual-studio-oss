# 简明审核入口

本次更新：2026-10-07 22:43（Asia/Shanghai）。工具：Codex（GPT-6；精确运行变体和推理档位未独立暴露）。本次范围：Content 时间线依赖绑定、迁移执行和受影响验收。

历史更新：2026-10-07 16:55（Asia/Shanghai）。工具：Codex；精确运行模型和推理档位未独立暴露。范围：合成 cue 编辑、不可变决策和现有 Video 时间线接线。

历史更新：2026-09-13 12:22:12（Asia/Shanghai）。工具/模型：Codex / GPT-6 Astra / high。

本页是现有 Content Studio 编辑台的局部入口。`scripts/human_voice_review.py` 复用 `human_voice_gate` 的文件/正文哈希与表达诊断，投影上游审核材料，不签发本人确认、朗读通过或发布回执。原 `human_voice_gate` 的最终审核合同不变。

默认展示优先级最高的五项，其他可展开。每项包含来源、可用时间码、当前内容和建议。真人材料及当前两题材料只读；交互样例可保留、修改、拒绝建议，并保存、撤销、导出本地草稿。拒绝建议保留原内容。原有视频建议只产生 sidecar 草稿；下文新增的合成 cue 分支可显式调用既有时间线生成候选。

## 稳定命令

在工作区根目录执行；输出必须在当前工作区内。

```text
python -X utf8 -B content-studio-poc/scripts/human_voice_review.py build --request content-studio-poc/fixtures/minimal-review/request.json --allowed-root . --output content-studio-poc/outputs/minimal-review/synthetic-v1
python -X utf8 -B content-studio-poc/scripts/human_voice_review.py apply --bundle content-studio-poc/outputs/minimal-review/synthetic-v1/bundle.json --draft <导出的选择草稿.json> --allowed-root . --output content-studio-poc/outputs/minimal-review/local-updates
```

`apply --stop-after 1` 用于暂停恢复验收；恢复时去掉参数。相同输入重复调用不改写已存在文件。不同决策写入不同不可变修订，只写发生变化的文本/建议 sidecar，未变化的研究、ASR和其他产物通过原路径及哈希引用。撤销后的空草稿生成继承原件的修订，保留此前历史，不删除文件。

## 输入与安全边界

版本为 `1.0.0`。输入包含 `review_id`、`sources`、`candidates`、`artifacts`、`choices`，可选 `media`。来源路径限制在 `--allowed-root`；文件 SHA、正文、候选来源、候选版本与正文身份全部校验。来源缺失、正文漂移、重叠替换、跨候选目标、过期草稿和既有修订污染均拒绝。

构建器将 `synthetic_only=false` 的候选强制设为只读；草稿不能解除它。所有真实输入的自动 apply 均禁止。虚构交互数据不得替代真实用户批准。`source_refs` 和文件路径是机器绑定信息，前台不堆叠显示哈希。

本地浏览器存储键包含审核 ID；草稿另绑定整个包、候选版本、输入和正文哈希。保存前重新读取同源 `bundle.json`，发现版本变化或另一个页面已保存则拒绝。刷新恢复、存储不可用、并发保存及按钮状态仍需真实浏览器验收。没有同步服务器；导出 JSON 后调用 `apply` 才产生文件修订，`apply` 会重新校验上游文件，浏览器预览不是文件写入证明。

## 预览与视觉

现有编辑台入口 `admin/index.html` 链接到 `admin/review.html?bundle=../outputs/minimal-review/current/bundle.json`；也可打开构建输出的 `index.html`。使用已有获授权的预览服务；本模块不启动服务。跨源 bundle 拒绝，不加载外部样式、字体、脚本或媒体。未知/缺失 bundle 显示错误，不静默展示其他题目。

现有编辑台控件延用 `tokens/brand.tokens.json` 的 v0.3 纸白、墨色和青绿色值及中文字体回退，仅作为界面结构和编辑标记；不据此为媒体画面强制选择整套 IP 配色。素材本色及风险、类别、状态等事实编码保留原义。布局采用分隔行、前后对照、44px 最小控件和手机单栏；没有装饰动画。未重新设计 Sveltia CMS。

原始验收记录：37 项 Python 与 10 项 JavaScript 纯逻辑测试通过，另有 5 次真实 argparse CLI 验收。当时浏览器工具拒绝 `file://`，预览服务未运行，UI 项未验收；后续浏览器阶段结果见本页末尾，不以静态文件或纯逻辑测试代替交互验收。

通用代码依赖现有 Content Studio 模块与 jsonschema。原始 fixture 使用工作区相对路径；本次新增的独立目录验收及外部 Video 依赖要求见下文。真实上游包、媒体和本地验收产物不在通用代码提交清单内。

## 可选合成 cue 分支（2026-10-07）

`scripts/cue_review.py` 在既有 bundle 上增加 `kind: "cue"` 选择，目标仅为一个来源绑定的 cue track JSON。每项包含 `cue_id`、`before_cue`，修改后的 replacement 使用同一个 `cue_id`，并完整提供 `scene_id`、`start_ms`、`end_ms`、`text`。页面显示前后对照，可编辑后三类值；保存每个变化的选择各追加一个独立事件。旧版文字草稿格式和 `apply` 命令保留。

track 使用 `schema_version: "content-cue-track.v1"`，包含 `synthetic_only`、`scenes`、`cues`、`packaging_ref`、`binding_ref`。场景从 0 开始连续，时间均为整数毫秒；cue 使用 `[start_ms, end_ms)`，必须完整位于指定场景、同场景不重叠、每个场景至少保留一条。允许同时修改场景 ID 和时间，但不自动切分或夹紧。字幕遵守既有 Video 合同：非空、最多 34 个字符、不含换行、反斜杠或花括号。

新增命令在工作区根目录运行：

```text
python -B -X utf8 content-studio-poc/scripts/human_voice_review.py decide --bundle <bundle.json> --event <event.json> --allowed-root <已绑定来源目录> --output <决策目录>
python -B -X utf8 content-studio-poc/scripts/human_voice_review.py apply-session --bundle <bundle.json> --session <浏览器导出的content-review-session.json> --allowed-root <已绑定来源目录> --output <决策目录>
python -B -X utf8 content-studio-poc/scripts/human_voice_review.py render-cues --bundle <bundle.json> --decisions <决策目录> --track track.json --allowed-root <已绑定来源目录> --cache <场景缓存目录> --output <本次渲染目录> --video-source <Video项目根目录>
```

`decide` 接受下列事件；`unset` 仅需 `choice_id`，`undo`、`redo` 无需 decision。`binding` 必须逐字段匹配 bundle 中该 choice 的绑定；事件 ID 不可复用为其他内容。

```json
{
  "schema_version": "content-review-decision.v1",
  "event_id": "edit-c1",
  "bundle_sha256": "<bundle的SHA256>",
  "parent_event_id": null,
  "operation": "set",
  "choice_id": "cue-c1",
  "decision": {
    "action": "modify",
    "binding": {"...": "从该choice原样复制"},
    "replacement": {"cue_id": "c1", "scene_id": "s1", "start_ms": 100, "end_ms": 900, "text": "VERIFY SOURCE FILES"}
  }
}
```

决策目录内 `decisions/*.json` 是追加提交点，`revisions/<digest>/` 保存每次不可变投影。撤销和重做追加新事件，不删除旧修订。旧事件重试返回原修订和当前 head，不把当前状态退回；同 ID 不同内容、过期 parent、截断或分叉 session 均拒绝。`apply-session` 先验证完整事件链，再逐个提交；中断后用同一文件恢复，已有事件去重。提交前后的输入哈希都检查，已存决策、投影或索引污染会被拒绝。

写入由操作系统锁互斥，进程退出后锁自动释放；遗留 `.decision-writer.lock` 文件不代表仍有人写入，也无需删除。提交前中断留下的准备修订会按原字节恢复。临时写入采用当前目录原子提交，不覆盖不一致的旧文件。

`scripts/cue_timeline_adapter.py` 只在 Content 侧把 cue 投影到 binding，调用显式绑定的 Video `audio_timeline.compose`；不查找临时工作树，也不新增渲染器。输入先按来源哈希复制为稳定快照，场景时长不能通过此入口修改；片段缓存键和渲染沿用 Video 实现，外层按运行依赖锁 SHA 分目录。单场景字幕变化只重渲该场景，跨场景移动会使两个涉及场景的字幕绑定变化。最终拼接允许重做；普通中断的未完成尝试保留，恢复使用新 attempt 和已完成片段缓存。

本入口仅支持显式合成 track、候选和 binding，且最长 6 秒、最大 540×960 / 30fps；没有真实材料解锁入口。`real_material_read_only` 保留，UI 导出、代码测试和候选成片均不签发本人确认、朗读通过或发布许可。

## 2026-10-07 首轮验收记录

13 项 cue Python、20 项既有 Python、10 项 cue JS 和 10 项既有 JS 通过；JS 导出的事件链已由真实 CLI 导入。4 秒、270×480 / 30fps 合成音调、图形和字幕经真实 CLI 生成：修改 c1 仅重渲 s1，s2 缓存键、SHA256、mtime 不变；撤销回到原候选、重做回到修改候选，均未再渲片段。进程中断锁释放、准备修订恢复、重复提交及旧 head 拒绝均有反例验证。

首轮浏览器工具明确禁止 `file://` 地址，临时 HTTP 预览当时未获该任务许可，因此未启动服务。该轮未覆盖桌面/移动、控件操作、刷新、多标签、焦点和媒体播放；后续单独授权的浏览器阶段补齐了这些项目。

证据在 `outputs/priority-adoption-20261007/review/DELIVERY.md`。首轮合成输入生成曾出现 35 个聚合线程，超出 32 上限，失败证据保留；修正输入方式后后续有界运行通过。不能把最终通过改写成全程未超限。

## 版本绑定与迁移（2026-10-07 22:43）

`--video-source` 必须指向包含 `pyproject.toml` 和 `src/video_creation_pipeline/` 的依赖根。当前已核验 Registry 的 `mvp-video-pipeline` 稳定根为 `<mvp-video-pipeline-root>`，分发名 `video-creation-pipeline`、版本 `0.8.1`。这个地址只是本机已验证示例，代码和锁文件均不将它作为默认路径。更换电脑或目录时显式传新位置。

`config/video-timeline-runtime.v1.lock.json` 固定接口 `audio_timeline.compose/v1`、版本及 195 个运行文件的实际 SHA。`scripts/video_timeline_dependency.py` 检查文件集合、内容和真实路径，拒绝包内符号链接或 junction；从已校验源码字节导入，不使用已有同名包或 `.pyc`。不修改 `sys.path`。导入后的模块位置、加载器及运行文件在渲染前后复验；回执包含依赖锁及实际来源。重复成片返回 `validated_video_dependency`，区分当前核验位置与原渲染回执记录。

需要已有 Python 3.11+、Video 声明的 Python 依赖，以及 PATH 上的 FFmpeg/ffprobe。本入口不安装软件。缺少参数、目录、Python 包或可执行文件会报具体原因；同版本源码漂移也拒绝。锁只绑定 Video 运行源码，不承诺不同操作系统、第三方包或 FFmpeg 版本间成片逐字节一致。更新 Video 后，应复核受影响接口、显式更新锁并运行对应回归，不能运行时自动刷新锁来消除报错。

依赖锁进入最终渲染身份和场景缓存目录。升级前的完整回执不会被覆盖；如出现 `existing_render_revision_drift`，使用新的输出目录并保留旧证据。渲染中检测到依赖漂移时不签发最终回执，在该缓存命名空间留下 `runtime-rejected.json`，保留旧片段、成片与失败尝试。后续明确返回 `video_dependency_cache_quarantined`；先修复/核验依赖，再用新缓存目录重试，不删除标记来强行复用。

迁移验收从独立工作区的空 cwd 调用真实 CLI，复制的是 9 个 Content 本地 Python 依赖模块、4 个 UI 文件和锁文件；Video 仅以独立外部运行包快照作为验收依赖，没有复制整个 Video 项目到 Content。每个迁移 CLI 进程拒绝读取旧工作树、原 Content 和原稳定 Video 根，并主动验证三个拒绝。Python 审计钩子记录/约束原生子进程参数及 Python 网络调用；这不是操作系统范围的所有文件或网络系统调用审计。

本次新增 10 项依赖回归、18 次迁移 CLI，以及稳定根直接调用和真实渲染后漂移注入。4 秒、270×480 / 30fps、120 帧纯合成候选通过：s1 字幕改动仅重渲 s1，s2 缓存 SHA/mtime 不变；撤销/重做对应成片字节恢复，旧 head 拒绝，session 恢复不重复追加。缺依赖、版本不符、源码漂移、只读候选和来源漂移负例未改变既有缓存；渲染中漂移的失败缓存已隔离。实际提取的 0.5 秒画面由 `COLLECT SOURCES` 变为 `VERIFY SOURCE FILES`。

此次未重跑旧 53 项测试或浏览器。`admin/review.html/js/css`、`feedback.js` 与已验收版本 SHA 一致，沿用 `outputs/priority-adoption-20261007/review/browser-continuation-01/DELIVERY.md` 的桌面和移动视口证据，未启动服务。此结论只适用于相同 UI 源码，不表示真实材料获准编辑、本人听验完成或内容可发布。

本批证据：`outputs/priority-portability-20261007/content/DELIVERY.md`、`migration-acceptance.json`、`inflight-drift-acceptance.json` 和 `ui-compatibility.json`。改动意图是移除临时路径；选择显式依赖与固定锁，原因是仅版本号不能识别脏源码；生效范围仅 `render-cues`，build/decide/apply 的合同和 UI 不变。回退应依据任务基线撤回本批六个文件差异，保留新旧输出和所有其他未提交改动，不执行整仓重置。
