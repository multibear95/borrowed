# MORE MCP demo：Cursor / ChatGPT / Claude

2026-09-13。无认证 demo，共享现有商品、预约锁和 JSON 快照。四个工具均可调用，预约真实占位、不收款。无需为 MCP 配置 OpenAI API key：理解对话由客户端的模型完成，MCP 调用不经过 BorrowerGraph。

## 本地启动

在 `borrowed/backend` 中运行：

```bash
.venv/bin/python -m pip install -r requirements.lock.txt
STATE_DIR=/tmp/more-mcp-demo-01 PYTHONPATH=src .venv/bin/python -m borrowed_backend --demo-date 2026-09-16
```

服务地址为 `http://127.0.0.1:8000/mcp`，健康检查为 `http://127.0.0.1:8000/health`。启动命令占用当前终端。若 8000 已有后端运行，先确认是否要使用该后端，或通过 `--port 8014` 启动，并同步修改客户端地址。不要运行多个进程共用同一 STATE_DIR。

演示固定系统日期为 2026-09-16，推荐测试穿着日期 2026-09-18。反复预约会耗尽对应档期库存；停止服务后换一个新的 STATE_DIR 即可重置演示，无需修改 catalog.json。只有保留同一目录，才能验证重启后预约仍然存在。

## Cursor

在 Cursor 中打开 `borrowed` 文件夹。项目已提供 [`.cursor/mcp.json`](../../.cursor/mcp.json)：

```json
{
  "mcpServers": {
    "more": { "url": "http://127.0.0.1:8000/mcp" }
  }
}
```

如果打开的是上一级 `hackathon-202609`，将该配置合并到打开目录的 `.cursor/mcp.json`；不要覆盖已有服务配置。启动后端，在 Cursor 的 MCP 设置中检查 `more` 的四个工具，然后使用 Agent 对话。

## ChatGPT 和 Claude：共享一个远程地址

网页版连接来自平台云端，不能直接访问这台电脑的 `127.0.0.1`。将同一个后端部署到 Railway，或通过 HTTPS 开发隧道转发本地 8000。两者都使用同一个完整 `/mcp` URL，例如 `https://your-demo.example/mcp`。

后端新增环境配置示例（JSON 数组）：

```text
DEMO_DATE=2026-09-16
MCP_ALLOWED_HOSTS=["127.0.0.1:*","localhost:*","your-demo.example"]
MCP_ALLOWED_ORIGINS=["http://127.0.0.1:*","http://localhost:*","https://chatgpt.com","https://claude.ai"]
```

将 `your-demo.example` 换成真实域名，不带协议和路径。若使用隧道，同样加入隧道域名。Host/Origin 校验是传输层检查，不是账号认证；无 Origin 的云端请求可正常通过。无需配置 API key、OAuth 或 Authorization 请求头。

保持单实例、`--workers 1`。Railway 按 [部署说明](../../docs/backend-railway.readme-zh.md)设置 Start Command，使用平台 PORT 覆盖 Procfile 的固定 8000 端口：

```bash
python -m uvicorn borrowed_backend.main:create_app --factory --app-dir src --host 0.0.0.0 --port $PORT --workers 1
```

配置 Volume 与 STATE_DIR 才能跨重新部署保留预约。只测试 MCP 时无需填写部署指南中的 OPENAI_API_KEY 和 OPENAI_MODEL；网页自由对话才需要它们。

这是公开可调用的 demo：任何能连接地址的客户端都可以占用 demo 库存。客户端确认提示与工具 annotations 不构成服务端身份验证。

### ChatGPT 网页

1. 在支持该功能的账号/工作区中开启 Developer mode（当前文档入口：Settings → Security and login）。
2. 在 Plugins 中添加自定义 MCP，填写 HTTPS `/mcp` 地址，选择 **No Authentication**。
3. 新建对话，选择 MORE 连接，执行下方测试对话。

当前官方文档列出网页版 Plus、Pro、Business、Enterprise、Education；工作区策略可能限制入口。仅连接开发者测试，不需要提交公开商店。修改工具描述或 schema 后，在连接设置中 Refresh，再新建对话。

### Claude 网页 / Desktop 的远程连接

1. 在 Settings → Connectors 中添加自定义连接。
2. 输入 MORE 和同一个 HTTPS `/mcp` 地址；该服务器无需登录。
3. 在对话工具中启用 MORE，执行下方测试。

Claude 的远程连接同样由云端访问后端。账号/组织需允许自定义连接。此处使用远程连接流程，不使用 Desktop 的本地 stdio 配置。

## 测试对话

依次发送，检查客户端展示的真实工具名、参数、返回值和确认行为：

> 使用 MORE 的 search_garments，找 Hamburg、EU 38、2026-09-18 能穿的礼服，预算 100 欧元。先不要预约。

> 使用 get_garment 和 check_availability，查看第一件的详情和档期。告诉我送达日期、最后穿着日，以及清洗结束后何时可再租。

> 确认预约刚才这件，使用刚才的城市、尺码和日期。我知道这是占位预约，不付款。

预约调用必须带唯一 `idempotency_key`。需要重试时保留该键与原参数，返回同一 booking_id，`already_existed=true`。该 demo 的幂等键为全局命名空间，客户端使用 UUID 等唯一值避免互相碰撞。

预约后重新搜索，原商品应消失；另一个客户端尝试相同档期但不同幂等键，会得到冲突。网页连接到同一个后端时也会看到更新；**需要重新搜索**，已显示的旧卡片不会自动推送刷新。

## 工具和返回约定

| 工具 | 用途 |
| --- | --- |
| search_garments | 确定性筛选及排序，仅返回可借商品 |
| get_garment | 详情；不代表具体日期可借 |
| check_availability | 日期、城市、尺码、物流与清洗档期检查 |
| create_booking | 用户确认后真实占位，锁内重检、幂等、原子快照 |

`return_date` 是最后穿着日（包含当天），不是衣服寄回到达日。省略时使用商品租期。

成功响应的 `structuredContent` 为 `{"result": ...}`，文本 content 是同一对象的 JSON。`search_garments` 的 result 为数组，其余为对象。外层包装使数组符合 MCP 对象型 outputSchema；包装内业务数据与直接 invoke/REST 相同。图片字段仍为后端相对路径，需以 MCP 后端域名解析；本轮不包含专用卡片 UI。

工具错误使用 `isError=true`，结构化数据及文本中保留 `reason`，如 INVALID_ARGUMENTS、GARMENT_NOT_FOUND、OVERLAPS_BOOKING、IDEMPOTENCY_KEY_REUSED、PERSISTENCE_FAILED。档期冲突附带 feasibility。查询返回 `feasible=false` 或空数组是正常业务结果。

## 实现与验证

- 官方 Python SDK `mcp==1.26.0`，使用 low-level Server + StreamableHTTPSessionManager，对 REGISTRY 自动适配；不是另一份手写工具列表。
- FastAPI 精确 `/mcp` ASGI 路由，管理器由主 lifespan 启停，避免 `/mcp/mcp` 或尾斜杠重定向。
- Stateless Streamable HTTP + JSON 响应；无 MCP 会话持久化。业务 store 仍为单进程共享，预约仍持久化。
- 当前无 key、OAuth、scope 鉴权、按 key 限流。external=False 工具不列出且不能被直接调用；scope 仅用于只读/写入注解。
- 自带 Host/Origin 校验，默认只允许本机，部署时显式添加域名。若报 421 检查 Host 配置；403 检查 Origin；连接失败也需确认服务仍在运行及 URL 包含 `/mcp`。
- 在 MCP Inspector 中选择 Streamable HTTP 并连接上述 URL，可独立检查工具。仅用浏览器 GET `/mcp` 或 health 成功不足以证明 MCP 可用。

```bash
.venv/bin/python -m pytest -q tests/test_mcp_contract.py
.venv/bin/python -m pytest -q
.venv/bin/python -m pip check
```

MCP 测试会临时监听本机随机端口，使用官方客户端执行 initialize/list_tools/call_tool，覆盖全部四个工具与直接调用的序列化结果一致性、REST 库存可见性、幂等重试、恢复、20 个跨 MCP/REST 并发预约、隐藏工具、无效参数、保存失败回滚及 Host/Origin 检查。

验收结果和未覆盖范围见 [MCP 验收记录](mcp-acceptance-zh.md)。

## 官方参考

- [MCP Python SDK 1.26.0](https://github.com/modelcontextprotocol/python-sdk/tree/v1.26.0)
- [Cursor MCP](https://prod.cursor.com/docs/mcp)
- [ChatGPT Developer mode](https://developers.openai.com/api/docs/guides/developer-mode)
- [ChatGPT 连接与测试](https://developers.openai.com/plugins/deploy/connect-chatgpt)
- [Claude 自定义连接](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp)
- [Claude 无认证支持](https://claude.com/docs/connectors/building/authentication)

客户端入口按 2026-09-13 官方文档整理，实际账号可见入口及客户端兼容性需要实测。
