# Borrowed 文档入口

更新日期：2026-09-13。当前实现 borrower 阶段 1–3，以及无认证 MCP demo：搜索、文字对话、明确确认预约与最小页面。网页对话使用 OpenAI Responses API，MCP 直接调用业务工具；后端为单实例、单 worker、内存字典与 JSON 快照。

## 本地演示

- [MCP demo 接入](../backend/docs/mcp-demo-zh.md)：无认证四工具、Cursor 本地配置、ChatGPT/Claude HTTPS 接入与测试对话。

- [阶段 3 使用说明](../backend/docs/stage3-usage-zh.md)：真实模型启动、无凭据固定演示、双窗口冲突与重启检查。
- [后端 README](../backend/README-zh.md)：后端环境和结构化 API。
- [对话协议](../backend/docs/stage2-usage-zh.md)：SSE、result_id、确认及错误处理。

真实模型模式使用前端 3000 / 后端 8000，需要后端配置 OPENAI_API_KEY、OPENAI_MODEL。固定脚本模式使用 3013 / 8013，只识别完整输入“我周五要参加晚宴”和“汉堡，EU 38”；点击尺码快捷按钮也会超出固定脚本支持范围，不能当作自由聊天。服务需要按说明手动启动，页面地址存在不代表服务正在运行。

演示系统日期为 2026-09-16，穿着日期为 2026-09-18。保留同一 STATE_DIR 可验证重启恢复；全新演示换新目录。刷新页面不恢复完整聊天记录，但预约仍保存在后端。

## 部署

- 后端 Railway 指南：[中文](backend-railway.readme-zh.md) · [English](backend-railway.readme.md)
- 前端 Railway 指南：[中文](frontend-railway.readme-zh.md) · [English](frontend-railway.readme.md)

前端默认连接本地后端；Railway 必须显式设置 API_ORIGIN。模型凭据仅放后端，预约跨部署保存需要后端 Volume。

## 计划与验收

- [阶段 3 实施计划](../backend/docs/stage3-plan-zh.md)
- [阶段 3 验收记录](../backend/docs/stage3-acceptance-zh.md)
- [阶段 2 验收记录](../backend/docs/stage2-acceptance-zh.md)
- [阶段 1 验收记录](../backend/docs/stage1-acceptance-zh.md)

阶段 3 已验证真实后端浏览器搜索、确认、双窗口冲突及刷新和重启后的不可借状态；模型使用固定响应。在线 OpenAI、Railway 发布及云端 Volume 恢复不在该次验收范围内。

## 设计规格

- [完整目标架构](architecture.html)：保留原设计，页首列出当前实现范围。
- [后端规格](../specs/BACKEND_SPEC.md)：完整目标规格；本轮阶段范围见实施计划。

lender、图片上传与识别、搭配、模型二次排序和复杂条件放宽尚未实现。MCP 已实现无认证 demo；部署及真实客户端状态见 [MCP 验收记录](../backend/docs/mcp-acceptance-zh.md)。
