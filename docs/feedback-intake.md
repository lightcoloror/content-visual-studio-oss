# 简明审核中的采用反馈与本地导入

更新时间：2026-09-13 13:59:55（Asia/Shanghai）。工具/模型：Codex / GPT-6 Astra / high。

现有审核页增加可选反馈区。选择候选后点击“采用”“修改后采用”或“弃用”，入口自动生成候选 SHA、审核版本、content_id、closure_run_id、account_id 和证据引用。修改时只需填写原因，分钟数可空；候选详情保留每条待审反馈及返工原因，不把历史记录数量当采用率。

本入口是虚构验收与本地待审适配，不追加 outcome ledger，不修改 publication store，不写 CRM。真实材料仍走现有人工审核和经营入库门；本轮没有开放真实材料的自动点击或写入。`publication=null`、观察窗口和 scheduled_tasks 为空。

## 使用入口

在工作区根目录准备一个新的虚构目录，不启动服务：

```powershell
python -X utf8 -B content-studio-poc/tests/feedback_fixture.py --output outputs/my-synthetic-feedback-preview
```

仅在已获临时本机预览授权时启动：

```powershell
python -X utf8 -B content-studio-poc/scripts/feedback_intake.py serve-synthetic --output outputs/my-synthetic-feedback-preview --seconds 900
```

该入口读取 Content Studio 的既有 `config/local_webui.json`，强制 127.0.0.1，打印带 `?feedback=1` 的实际入口。启动前仍需检查配置端口、监听和排除范围；服务不会关闭已有用户进程。900 秒后自动结束；主动结束可向该目录写入 `stop-request.json`，其内容必须匹配 lifecycle 中的 PID 与创建时间。结束后核对 PID、监听与端口绑定。不要复用含旧 stop-request 的目录启动另一轮。

已有合成候选可通过 `feedback_intake.py prepare --bundle <review-bundle> --candidate <review-key>=<candidate-file> --import-csv <key>=wechat_official_template_v1=<synthetic.csv> --output <new-dir>` 准备。用户不需要手填 SHA；候选须有唯一已绑定账号、closure_run_id 和匹配的 review_binding。示例生成器使用现有 Content 合同与审核 bundle，不创建第二套账本。

页面只发送已指定文件的 key，由本地适配器读取 CSV；没有文件上传接口，也不会接受浏览器传入的任意路径。GET 只开放审核静态文件和反馈上下文，POST 校验 Host、同源 Origin 与会话 token。未加 `feedback=1` 时原审核页行为不变。

## 证据与未知值

底层 `outcome_feedback_link` 保留原有起止时间证据合同，新增明确的 `manual_duration_report` 分支：duration_seconds 可空，时间报告、原因、分类、身份和报告时间均由哈希绑定证据校验。空值不会推算成 0，也不会伪造 started_at/ended_at。

人工基线和修改分钟数都填写时，详情展示其差值并标注“人工报告”；缺少任意一项时节省时间为 unknown。差值只存在于本地待审结果，原生 outcome 的 time_saved_minutes 仍为空，不据此宣称实测效率或整体节省时间。

每次提交生成不可变 submission、decision/edit evidence 和原生 request/review-packet/outcome-candidate/receipt。重复同一候选版本与同一输入会校验已有内容并返回 duplicate，保留字节与修改时间；修改过的历史结果拒绝覆盖。新的反馈输入生成独立待审条目。

## 公众号模板 v1

稳定导入脚本仍为 `self-media-creation-system/scripts/platform_metrics_intake.py`，新增 profile 为 `wechat_official_template_v1`。模板在 `self-media-creation-system/templates/wechat-account-day-template.v1.csv`。没有本地可验证的官方列名证据，因此每条来源与记录都强制标记 `template_only`，不宣称兼容官方 CSV/XLSX 导出。

| 列名 | 合同 |
| --- | --- |
| format_version | 固定 wechat-account-day-template.v1 |
| source_grain | 固定 account_day |
| date | YYYY-MM-DD |
| read_users | 此模板所定义的送达用户中的阅读人数，非阅读次数；非负整数或缺测 |
| delivered_users | 同一人群的送达人数；非负整数或缺测 |
| open_rate_percent | read_users / delivered_users × 100，百分数单位；例如 25% 或 25，不是小数比例 0.25 |

这是明确的自定义统计合同，不推断平台官方口径。非空百分比要求两个计数已知且分母大于 0；人数不能超过送达人数，百分数范围 0–100，允许 0.01 个百分点的舍入误差。缺测保留 null；明确的 0 保留 0。重复/空列名、多余/缺少单元格、未知格式版本或日期会被拒绝。账户日数据不绑定 content_id，content_label 为空。

CLI 示例：

```powershell
python -X utf8 -B self-media-creation-system/scripts/platform_metrics_intake.py import --source wechat_official_template_v1=content-studio-poc/fixtures/feedback-intake/synthetic-wechat-template.v1.csv --captured-at 2026-09-13T13:55:00+08:00 --output self-media-creation-system/.runtime/platform-metrics-intake/my-preview/intake.json
```

在有计算线程预算的工作区运行 CLI 时，先设置 OPENBLAS_NUM_THREADS、OMP_NUM_THREADS、MKL_NUM_THREADS、NUMEXPR_NUM_THREADS 为 1；反馈预览入口在导入依赖前自动设置这些限制。已有 jsonschema/openpyxl 与本机 psutil 被复用，本轮没有安装或下载依赖。

## 本轮变更六要素

| 要素 | 说明 |
| --- | --- |
| 意图 | 减少反馈填表负担，保留版本、粒度和来源真值 |
| 决策 | 现有审核页附加区 + 原 outcome/link 与 metrics 入口薄适配 |
| 理由 | 旧入口要求多个 JSON/哈希，未知修改耗时会报 started_at 缺失；公众号配置不存在 |
| 证据 | 本轮 44 项不同定向用例、浏览器 adopt/edit/reject 与 CSV 去重、实际原生候选回读及进程退出证据 |
| 生效范围 | 本 Owner 的审核页、反馈适配、公众号 template_only；原五平台配置与发布/CRM门保持不变 |
| 回滚 | 根据本轮 task-only.patch 选择性回退代码；关闭本次预览，保留所有历史记录、旧 dirty 与 blocked 回执 |

本轮浏览器为桌面引擎的 1280×900 与 375×812 视口；移动点击/键盘通过，未测实体触屏。实际截图保留在任务工具记录中。没有真实发布、人审采用率、线上平台读取或观察任务。
