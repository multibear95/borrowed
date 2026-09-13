# MCP demo 验收记录

日期：2026-09-13。范围：无认证 Streamable HTTP MCP、现有四个工具、同进程存储、客户端配置文档。未提交或推送代码，未部署线上。

## 实现

- `/mcp` 支持官方 SDK 的初始化、工具发现和工具调用；无认证。
- 基于 REGISTRY 自动导出 external=True 工具，Pydantic 输入和输出 schema 随业务模型生成。
- 使用官方 `mcp==1.26.0` 的 low-level Server，直接适配已有注册表；未引入 FastMCP 的第二套函数注册。
- 成功数据包装在 `structuredContent.result`，text content 提供同一 JSON；四个工具的包装内业务结果与进程内调用一致。
- 显式 `isError`、业务 reason、冲突 feasibility；错误不会伪装成成功预约。
- MCP/REST/聊天共用 store、预约锁和快照，仍要求单实例、单 worker。
- `readOnlyHint`、`destructiveHint`、`idempotentHint`、`openWorldHint` 注解以及预约确认说明；这些提示不是认证机制。
- Host/Origin 校验默认限制本机，环境变量可增加部署域名。没有 API key、OAuth 或按 key 限流。
- Cursor 项目配置和 ChatGPT/Claude 远程接入说明已写入 [使用文档](mcp-demo-zh.md)。

## 自动验证

在 backend 目录执行：

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m pip check
```

结果：**76 passed，1 warning，4.68 秒**；`pip check`：No broken requirements found。警告来自 Starlette TestClient 使用 AnyIO 已弃用的 BlockingPortal 别名，不影响测试通过。`git diff --check` 通过。

其中 5 项新增 MCP 测试使用本机随机 TCP 端口、真实 Uvicorn 服务及官方 ClientSession + streamable_http_client；不是仅通过 ASGITransport 或直接函数调用模拟 MCP：

1. initialize/list_tools/call_tool 全链路；全部四个外部工具的 schema、描述和注解核对。固定预约 UUID，对独立 store 的直接 invoke 结果和 HTTP 结果进行规范 JSON 字节比较；日期和枚举序列化一致。
2. MCP 预约后 REST 搜索不再返回原商品；REST 重试得到相同预约；从原目录重建 store 后同一请求仍幂等。
3. 未知/隐藏工具、参数错误、日期溢出、无结果、不可借日期、幂等键复用及冲突原因。
4. 20 个混合 MCP/REST 并发请求争用同一商品和档期，仅 1 次预约成功。
5. 模拟快照失败，MCP 报 PERSISTENCE_FAILED、库存回滚、同一请求可重试；精确 `/mcp` 无重定向、无认证连接成功、错误 Host/Origin 被拒绝。

以上场景分布在 5 个测试函数内。测试使用临时 STATE_DIR，没有写入现有演示数据；测试结束后服务器关闭。

首次运行受执行沙箱限制，无法绑定本机端口；允许本机测试监听后重新运行通过，未跳过 TCP 验证。

## 回归中修复的现有问题

修改前的 HEAD（`388924a`）源码导出到 `/tmp/borrowed-mcp-baseline-20260913`，使用同一环境和旧测试复跑：**63 passed、8 failed**。加 MCP 后最初也是同样 8 个旧测试失败，新增 5 个全部通过。

- 6 个失败来自同一实际问题：聊天搜索保存 `limit=3`，预约确认重新生成请求默认为 `limit=20`，导致有效确认也被拒绝。比较时统一展示数量，继续严格检查城市、日期、尺码、预算等实际条件，保留 result_id 和明确确认校验。原有成功、重试、并发、冲突及状态改变后拒绝测试通过。
- 1 个旧测试仍查找中文提示，现有界面已改为英文；更新为检查英文无结果提示。
- 1 个排序测试使用无颜色商品，却带黑色筛选；改用相同黑色商品测试价格和 ID 的平局排序。生产筛选逻辑未改变。

## 未验证范围

- 未在真实 Cursor、ChatGPT 或 Claude 账号内连接、观察选工具和确认交互；对应说明基于本轮查询的官方文档。
- 未部署 Railway、公网 HTTPS 或隧道，未验证云端连接、域名代理及 Volume 恢复。
- 未调用真实 OpenAI 模型；已有聊天测试使用脚本模型。MCP 本身无需后端 LLM 凭据。
- 本轮没有浏览器 UI 验收；“网页库存同步”已验证到共享 REST 数据层，旧卡片仍需重新搜索刷新。
- 没有认证、支付、预约取消、lender 上架、图片理解或专用 MCP 卡片界面。

下一步：按使用文档启动服务，在 Cursor 连接本机；随后部署同一服务并填写域名允许列表，再在 ChatGPT、Claude 添加无认证远程连接。
