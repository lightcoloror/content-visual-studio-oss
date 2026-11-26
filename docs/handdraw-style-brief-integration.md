# handraw-style 可选视觉 brief 接入

> 2026-10-01 增量：保留下述 9 月 15 日历史记录和四风格 `brief/list` 接口。全量画廊和提示词接入已补充到 [新版调用说明](handdraw-style-library.md)，独立固定源版本，旧限制与旧失败不代表新版运行结果。

更新时间：2026-09-15 17:53:42 (Asia/Shanghai)
执行工具/模型：Codex (运行时未暴露模型 ID)

## 当前边界

这是**候选 brief 接口**，不是新 Visual Profile、渲染器、图库或 AI 生图入口。只有内容对象明确指定目标和四个已登记的通用风格候选时，才输出一份 `visual_brief`。脚本不修改原内容对象，不下载/复制上游图片，不调用生图模型，不自动发布。

适用目标：

- `reflective-personal-essay` 的文章解释配图候选和社交卡构图候选；
- `editorial-field-guide` 的文章/Web 概念解释候选，仅限 `conceptual-line`、`ink-spot-color`；
- 文章槽需仍在 `planned` / `candidates-ready`，且只能承担解释或情境任务；社交卡/Web 成品需仍在 `planned`。

不适用：医疗决策、事实证据照片、保险条款证据图、数据图、已选/已渲染成品、未清权素材和自动生成图片。社交卡输出目前只供构图规划，**现有 social-card 渲染器不会自动消费它**；文章输出复用现有 `visual_brief` 合同，待人工选择素材后由既有文章管线消费。

## 使用

```powershell
python -B scripts/handdraw_style_brief.py list
python -B scripts/handdraw_style_brief.py brief --item <content-item.json> --target-id <article-slot-or-social-artifact-id> --style-id ink-spot-color --metaphor <content-metaphor> --central-action <visible-action>
```

可加 `--output <new-json-path>` 保存候选回执；已存在文件会拒绝覆盖。可选候选为 `conceptual-line` (#157)、`ink-spot-color` (#175)、`colored-pencil-notes` (#169)、`two-color-riso` (#167)。编号仅用于回溯上游通用 F 类条目，最终 brief 不带作者名称，也不引用示例图片。

真实内容对象的只读试运行回执：`outputs/acceptance/handdraw-style-brief-v1/social-card-brief.json`。该文件是候选构图 brief，不是新封面图，也不改变原社交卡内容对象。

## 变更记录

| 实际变动 | 意图 | 决策与理由 | 证据 | 生效范围 | 回滚方式 |
| --- | --- | --- | --- | --- | --- |
| `config/handdraw-style-brief.v1.json` | 建立少量可控候选 | 只选四个通用媒介风格，不移入在世创作者模仿条目；固定提交与索引哈希 | 上游 `styles.json` 的 F 类编号；仓库无许可证/逐图权利声明 | 可选风格 brief，不改变品牌与渲染 | 删除新配置及其调用入口 |
| `scripts/handdraw_style_brief.py` | 让现有内容对象能显式引用候选 | 读取结构化索引与既有设计方向注册表，输出符合 `visual_brief` 字段预算的候选；不复制上游代码 | 固定源提交 `70bf51d`；现有 `content-item.schema.json` 与 `design-directions.v1.json` | 文章、反思型社交卡、编辑型 Web 的规划阶段 | 停止调用并移除新脚本 |
| `tests/test_handdraw_style_brief.py` | 防止误用 | 错路由、作者风格、证据用途、索引漂移及选中成品一律 fail closed | 18/18 定向测试通过；真实反思型社交卡对象只读试调用通过 | 仅新增适配器 | 移除新测试，既有测试保持原样 |
| 共享设计系统参考记录与 `SOURCE_INVENTORY.json` | 记录选型来龙去脉 | 登记为参考/本地试用，不升级默认路由或工具注册表 | 上游索引构建 261 风格/19 拼图；提示词边界用例通过；`resolve_reference.py`、`validate_library.py` 因缺少模块失败 | 源码证据账本和参考层 | 撤销本次新增记录，保留其他历史条目 |

上游浏览器画廊交互因本地 `file:` URL 安全策略未验证，不能算通过。上游 `MANIFEST.md` 仍写旧的 217 编号；模型激活能力表缺逐模型实测回执，参考图决策模块当前不可运行。未来若要将真实图像投入成品，必须另走素材权利、隐私、适用性与人工复核；只有用户明确说“模型生成图片/AI 生图”时才能调用生图能力。

## 验证状态

- 新适配器 18/18 定向测试通过；现有反思型方向 8/8、文章视觉合同 14/14 通过。
- 共享设计系统合同校验通过；整套测试 14/15，唯一旧失败为路由排序断言，新增参考来源测试通过。本次差异没有修改路由排序合同。
- 源码账本 `show handraw-style` 的本地路径、部署入口与证据文档均存在。全库严格校验仍有 20 条其他历史条目的状态枚举错误，不把它宣称为通过，也不批量改写无关账本条目。
