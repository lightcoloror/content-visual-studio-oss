# Sveltia CMS 入口页面说明

## 概述与定位
`admin/index.html` 为第一方可选的内容管理系统（CMS）加载器入口页面。该页面通过载入固定的 Sveltia CMS 运行时脚本，为操作员提供可选的浏览器端内容编辑界面。

## 网络行为与边界约束
1. **外联加载特征**：本页面属于可选的外联入口。在浏览器中打开此 HTML 将向指定的外部 CDN 发起对 `@sveltia/cms@0.172.4` 的脚本请求；本仓库未分发离线 CMS 完整 bundle，亦不构成完全离线可用的 CMS 承诺。
2. **元数据边界说明**：运行时配置 `config/sveltia-runtime.v1.json` 中的 `boundary.automatic_network_fetch: false` 专指当前的模式（schema）离线校验工具链行为，不代表阻止浏览器解析此 HTML 时的网络请求。
3. **上游许可证与许可**：既有配置将上游源码许可记录为 MIT；本批未新增上游许可核验，也不分发该 CMS bundle。

## 配置、身份验证与审核分离
- **CMS 配置与认证**：仓库已有 `admin/config.yml` 模板；操作员仍需核对配置、后端身份验证机制（Auth）和部署环境。本批未验证这些能力，也未加入私有凭据或生产配置。
- **审核界面独立性**：审核工具（`admin/review.html` 及 `admin/review.js`）为独立子模块，需由调用方提供哈希绑定的审核数据包（review bundle）；本入口页面已移除指向不存在生成路径的陈旧导航链接，且不负责加载审核数据。

## 安全与验证声明
- 脚本标签严格保留 Subresource Integrity（SRI）校验及 `crossorigin="anonymous"` 属性；现有源码中的 SRI 字符串不构成当前 CDN 字节匹配的独立运行时证明。
- 源码公开不代表运行验收：原缓存依赖 pin 测试未执行，CDN 字节、CMS 界面、身份验证和内容发布均未验证。
