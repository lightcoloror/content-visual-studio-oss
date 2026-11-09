# 社交图卡字号回归：源码与测试边界

**文档目标**：`docs/social-card-typography-regression-source.md`
**对应测试**：`tests/test_social_card_typography_gate.py`（遵循 Apache-2.0 许可）

#### 概述与架构定位
本指南针对 ContentStudio 中社交卡片（Social Card，1080x1440）排版门禁回归测试。该测试套件通过 Node.js 桥接脚本（`scripts/social_card_playwright_bridge.mjs`）驱动 Playwright 与无头 Chromium，设计用于检查字号下限、文本角色、CSS／SVG缩放、继承／旋转以及策略哈希；本批不宣称完整覆盖行高、截断、可读性或所有溢出情况。

#### 环境配置与显式路径契约
测试套件移除了历史硬编码路径与缓存通配，改为通过明确的环境变量进行显式配置（在指定子进程 `cwd=ROOT` 前通过 `_env_path` 执行 `Path.resolve()` 解析）：
1. `CONTENT_STUDIO_TEST_SOCIAL_CARD_PLAYWRIGHT_PACKAGE`：显式指定 Playwright 模块 `package.json` 路径（绝对路径，或相对启动cwd并先resolve的路径）（桥接脚本会校验 `package.name === "playwright"`）。
2. `CONTENT_STUDIO_TEST_SOCIAL_CARD_CHROMIUM`：显式指定 Chromium 可执行文件路径，解析方式同上。
3. `CONTENT_STUDIO_TEST_SOCIAL_CARD_RENDERER_REGISTRY`：规范渲染器注册表 JSON 路径，仅在规范用例中延迟读取；模块导入不要求它，但完整运行8方法时该用例需要真实有效绑定，不能用合成策略替代。
4. **类级别跳过门禁**：若未检测到系统 `node` 或上述两项核心运行时文件不存在，测试类通过 `@unittest.skipUnless` 整体跳过。**重要声明：跳过测试绝不等于测试通过**。

#### 7份合成夹具与8个测试意图

6份HTML加1份test-only策略，均为本批第一方Apache-2.0源码，不是“无版权依赖”声明。合成策略三个profiles与已公开文章测试分支共享同一字节内容；本批不合并该分支，不附加文章夹具。

六个核心方法保持：正常角色回执、正文字过小、嵌套／CSS scale／SVG viewBox、字号继承与旋转、缺少主标题、未分类文本。另保留错误策略哈希负例，以及外部正式策略的文件／哈希／回执／profile核对。

哈希负例现名 `test_policy_hash_drift_is_rejected_before_render`，要求退出1、stderr含哈希不匹配、stdout为空且无PNG；不会捏造JSON回执。卡片声明尺寸1080×1440、策略预览声明270×360，不代表本测试导出两幅视口图片。

正式策略用例沿用 `test_registered_canonical_policy_is_current_and_usable`：外部注册表须有 `renderers.social-card.typography_gate` 的绝对 `policy_path`、`profile_id` 和实际匹配的 `policy_sha256`；最终仍要求profile为 `social_card_1080x1440`。默认公开注册表只有AntV，不会被本批修改。缺绑定／非法绑定在用例被调用时明确失败，无新skip或合成回退。若类因浏览器输入缺失而整体skip，则该用例也未执行，不能写成正式绑定通过。

#### 命令行调用示例（非可执行占位符）
```text
# 设置必要运行时路径后执行排版回归测试
$env:CONTENT_STUDIO_TEST_SOCIAL_CARD_PLAYWRIGHT_PACKAGE = "<PATH_TO_PLAYWRIGHT_PACKAGE_JSON>"
$env:CONTENT_STUDIO_TEST_SOCIAL_CARD_CHROMIUM = "<PATH_TO_CHROME_EXE>"
$env:CONTENT_STUDIO_TEST_SOCIAL_CARD_RENDERER_REGISTRY = "<PATH_TO_OPERATOR_SUPPLIED_REGISTRY_JSON>"
python -B tests/test_social_card_typography_gate.py
```

#### 安全与沙箱规范
- 桥接脚本强制保持 Chromium 原生沙箱开启（`chromiumSandbox: true`），严禁添加 `--no-sandbox` 参数；
- HTML 夹具中声明的 `Microsoft YaHei` 等 `font-family` 样式仅为 CSS 引用声明，不代表随附分发真实字体二进制，亦不代表字体商用授权。


## 实际验证、来源与未验证项

基于现有6672字节工作源，原件保留；不冒称固定历史Git原件。模型输入仅将两处旧本机路径替换成标记以保护路径信息，正式候选用上述参数取代它们。DeepSeek原生文件工具完成适配与初步静态验收；Gemini3.8Flash/high核对两处合同并写说明，Owner纠正方法名／覆盖范围等表述后最终核对。没有新建渲染器、修改公开桥接器／采集器／注册表／temp helper或重建历史环境。

最终六个核心方法AST等价，正式策略方法除延迟取绑定外原断言保留，7夹具逐字节一致；非执行Python编译通过。17个受控辅助逻辑检查通过，使用内存输入与受控子进程返回值，不是八个浏览器方法的执行结果，也不读取正式策略。

另实跑一次公开Node桥接器的错误哈希预检：只用明确标记的非可执行哨兵文件／包补足存在性检查，实际退出1、stderr哈希不匹配、stdout空、无PNG，哨兵模块未加载。哨兵不是已安装Playwright／Chromium，更不是真实渲染验证。八个浏览器方法实际执行0个；正式注册表与策略、字体字形、截图／缩放／视觉可读性、安装／跨机能力、业务与发布结果均未验证。不附带浏览器、字体、模型或真实素材，无安装／下载／安全降级步骤。

记录：2026-11-09T14:01:54.754403+00:00，Codex（精确内部运行模型未独立核验）；DeepSeek Flash／high提供代码与初步静态验收，Gemini 3.8 Flash／high提供合同核对与说明草案。
