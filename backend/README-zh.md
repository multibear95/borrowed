# borrowed backend — 阶段 1–2

已新增无认证 MCP demo：`/mcp` 暴露现有四个工具，复用相同库存和预约存储。见 [Cursor / ChatGPT / Claude 接入说明](docs/mcp-demo-zh.md)。MCP 工具调用无需配置 OpenAI 凭据。

文字对话 → 补充日期、城市和尺码 → 搜索推荐 → 明确确认预约 → 立即占用 → 重启恢复。Python 3.12，FastAPI、Pydantic v2、LangGraph 和 OpenAI Responses API，单进程内存字典与 JSON 快照。

阶段 1 的结构化搜索和预约接口仍然可用；完整对话示例见 [阶段 2 使用说明](docs/stage2-usage-zh.md)。

## 安装与启动

```bash
cd /Users/jingwu/hackathon-202609/borrowed/backend
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
PYTHONPATH=src .venv/bin/python -m borrowed_backend --demo-date 2026-09-16
```

```bash
conda create -n env_borrowed python=3.12 -y
conda activate env_borrowed
python -m pip install -r requirements.lock.txt
PYTHONPATH=src python -m borrowed_backend --demo-date 2026-09-16
```

`requirements.lock.txt` 固定本次验证过的运行和测试依赖。也可安装 Python 包：`.venv/bin/python -m pip install -e '.[test]'`，然后使用 `.venv/bin/borrowed-backend --demo-date 2026-09-16`。

服务默认监听 `127.0.0.1:8000`，交互式 API 文档位于 `http://127.0.0.1:8000/docs`。CLI 接受 `--host`、`--port`、`--demo-date`；CLI 日期优先于环境变量 `DEMO_DATE`。不提供日期时使用当前系统日期。

必须保持 **一个服务实例、一个 worker**。CLI 固定 `workers=1`，Procfile 也固定 `--workers 1`。不要启动多个进程共享同一状态目录。直接使用 uvicorn 的等价命令：

```bash
DEMO_DATE=2026-09-16 .venv/bin/python -m uvicorn borrowed_backend.main:create_app --factory --app-dir src --host 127.0.0.1 --port 8000 --workers 1

```

```bash
conda activate env_borrowed
DEMO_DATE=2026-09-16 python -m uvicorn borrowed_backend.main:create_app --factory --app-dir src --host 127.0.0.1 --port 8000 --workers 1
```

可配置环境变量：`DEMO_DATE`、`CATALOG_PATH`、`STATE_DIR`、`IMAGES_DIR`、`OPENAI_API_KEY`、`OPENAI_MODEL`、`LLM_TIMEOUT_S`、`DEBUG`。默认路径以 backend 目录为基准，不依赖启动时的工作目录。非 editable 安装时，应显式配置外部 catalog、图片和状态目录。

## 配置 OpenAI：OPENAI_API_KEY 和 OPENAI_MODEL

这两个参数通过**启动服务的终端环境变量**传入，无需修改 Python 代码。

| 参数 | 填写内容 |
| --- | --- |
| `OPENAI_API_KEY` | 在 OpenAI API 平台创建的 API Key |
| `OPENAI_MODEL` | 模型 ID；下面用 `gpt-4.1-mini` 举例，该模型支持 Responses、结构化输出和流式响应。实际调用仍取决于账户访问权限 |

Key 的创建方式见 [OpenAI 官方快速入门](https://developers.openai.com/api/docs/quickstart)，模型能力见 [GPT-4.1 Mini 官方说明](https://developers.openai.com/api/docs/models/gpt-4.1-mini)。

在 macOS 终端执行以下命令，将 Key 占位符替换为真实值，然后在**同一个终端**启动服务。如果服务已经运行，先按 Ctrl+C 停止它：

```bash
cd /Users/jingwu/hackathon-202609/borrowed/backend
export OPENAI_API_KEY='替换为你的真实API Key'
export OPENAI_MODEL='gpt-4.1-mini'

PYTHONPATH=src .venv/bin/python -m borrowed_backend --demo-date 2026-09-16
```

如果使用现有 Conda 环境，前两个 export 命令相同，启动方式改为：

```bash
conda activate env_borrowed
PYTHONPATH=src python -m borrowed_backend --demo-date 2026-09-16
```

这些 export 只对当前终端及其启动的进程生效。关闭终端后需要重新设置；改变参数后需要重启服务。当前代码**不会自动读取 `.env` 文件**，因此仅创建 `.env` 并填写两个参数不会生效。不要将真实 Key 填入本 README 或提交到 Git。

如需确认应用读到了参数，可以在启动前运行以下命令（不输出 Key 内容）：

```bash
PYTHONPATH=src .venv/bin/python - <<'PYCONFIG'
from borrowed_backend.config import Settings
settings = Settings()
print("API key configured:", bool(settings.openai_api_key and settings.openai_api_key.get_secret_value()))
print("Model:", settings.openai_model)
PYCONFIG
```

使用 Conda 时将 `.venv/bin/python` 换成 `python`。这一步只验证配置读取，不验证 Key 有效性、账户额度或模型调用；真实对话验证按 [阶段 2 API 示例](docs/stage2-usage-zh.md) 执行。未配置参数时，对话返回 `LLM_NOT_CONFIGURED`；结构化搜索仍可用。

可选参数 `LLM_TIMEOUT_S` 默认 25 秒，`DEBUG` 默认 false。模型 ID 没有硬编码默认值。

## 阶段 1：结构化接口演示

先查询健康状态和所有候选商品：

```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/api/garments/search \
  -H 'Content-Type: application/json' \
  -d '{"city":"Hamburg","sizes_eu":[38],"wear_date":"2026-09-18","limit":1000}'
```

以下命令自动选择搜索结果中的第一件商品并预约，打印请求与结果；再次运行会选择下一件商品，因此会创建另一笔预约。预约仅占用商品，不收取费用。

```bash
.venv/bin/python - <<'PY'
import httpx

with httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False) as client:
    search = {"city": "Hamburg", "sizes_eu": [38], "wear_date": "2026-09-18"}
    response = client.post("/api/garments/search", json=search)
    response.raise_for_status()
    hits = response.json()
    if not hits:
        raise SystemExit("No feasible garments remain for this demo.")
    garment_id = hits[0]["garment"]["id"]
    booking = {**search, "garment_id": garment_id, "idempotency_key": f"demo-{garment_id}"}
    print("Request:", booking)
    response = client.post("/api/bookings", json=booking)
    response.raise_for_status()
    print("Booking:", response.json())
    response = client.post("/api/bookings", json=booking)
    response.raise_for_status()
    print("Retry:", response.json())
PY
```

再次搜索时该商品消失。停止服务后，使用同一日期、同一状态目录重新启动，占用仍然存在。要从干净状态演示，可停服后用新的 `STATE_DIR` 启动；无需修改种子 catalog。

## 接口约定

| 接口 | 请求与响应 |
| --- | --- |
| `POST /api/conversations` | 创建 borrower 对话，返回 conversation_id |
| `POST /api/conversations/{id}/turn` | JSON 或文字表单；返回 SSE，支持补槽、推荐和显式确认预约 |
| `GET /health` | `status`、`garments`、`bookings`（种子与运行期合计）、`today` |
| `POST /api/garments/search` | 必填城市、穿着日；尺码数组默认空；返回 `SearchHit[]`，默认最多 20 条，`limit` 为 1–1000 |
| `GET /api/garments/{id}` | 公共商品投影，排除来源链接及预约内部信息 |
| `GET /api/garments/{id}/availability` | `wear=2026-09-18&return=2026-09-21&city=Hamburg&sizes_eu=38`；多尺码重复 `sizes_eu` 参数 |
| `POST /api/bookings` | 必填 `garment_id`、`wear_date`、`city`、`sizes_eu`、`idempotency_key`；可选 `return_date`、`borrower_name` |
| `GET /images/{filename}` | 现有本地图片 |

搜索另支持 `category`（默认 dress）、`occasion`、`colour_family`、`style_hints`、`max_price`。缺少或不匹配的 dress 尺码不会返回可借商品；配饰跳过尺码检查。颜色、场合、风格、正式程度只影响评分，未知颜色不排除商品。

`return_date` 是**最后穿着日（包含当天）**，不是归还送达日期。省略时使用商品租期，当前种子为 4 天。发货前额外一天缓冲；返程和清洗继续占用商品。两个占用区间在同一天相接也算冲突。清洗期原因沿用规格定义，涵盖已有穿着结束之后至占用结束的区间。

预约成功返回 `BookingResult`，包括日期、`status: reserved`、`payment_taken: false`、`already_existed`。同一幂等键与等价请求返回原预约，重启后仍有效；城市忽略大小写、尺码去重排序、省略结束日与明确填写默认结束日视为等价。其他请求变化返回 409 `IDEMPOTENCY_KEY_REUSED`。

其他错误：422 请求无效，404 `GARMENT_NOT_FOUND`，409 可用性冲突（顶层 `reason`、`feasibility`），503 `PERSISTENCE_FAILED`。预约失败不得显示成功，应保留幂等键重试。

## 存储和边界

- catalog 只读；运行预约保存到 `data/state/bookings.json`，版本为 1，含预约与用于幂等比较的结构化请求。
- 每笔预约在锁内复检、更新内存、原子保存；写入失败恢复旧内存。损坏、不一致或重复的快照记录使启动失败，应检查并恢复备份，不能静默清空。
- 仅提供本地开发与 Hackathon 单实例能力；本阶段没有身份认证、支付、取消预约、数据库、多进程协调或跨机器持久化。
- 阶段 2 已包含 OpenAI 对话、补槽、推荐解释、显式确认预约和对话快照。对话状态保存到 `data/state/conversations.json`。
- 暂不包含阶段 3 页面、MCP、lender、上架、搭配、图片处理、模型重排或复杂条件放宽。
- 代码注释及 docstring 使用英文。

## 验收与规格差异

干净状态、演示日期 2026-09-16、穿着日 2026-09-18、Hamburg、EU 38、dress：

| 结果 | 数量 |
| --- | ---: |
| 可借 | 22 |
| 城市不符 | 66 |
| 尺码不符 | 69 |
| 发货过晚 | 72 |
| 预约冲突 | 21 |

总计 250 件 dress；另有 136 件配饰。原 BACKEND_SPEC / ARCHITECTURE 写 24 件可借和 19 件预约冲突，与当前种子按 booked 穿着窗口扩展后的规则不符。本轮已确认采用 **22 / 21**，保持数据与规则不变。默认 `limit=20`，验证总数需显式提高 limit。

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scripts/smoke_stage1.py
.venv/bin/python scripts/smoke_stage2.py
```

冒烟脚本使用临时状态目录，启动真实 HTTP 服务，发起 20 次并发预约、关闭并重启进程，再验证搜索和幂等恢复；退出时关闭服务并清理临时状态。阶段 1 结果见 [阶段 1 验收记录](docs/stage1-acceptance-zh.md)。

阶段 2 的测试与真实 HTTP/SSE 冒烟验证已通过，但冒烟脚本注入固定模型响应，没有调用真实 OpenAI 服务；在线模型效果需配置参数后验证。详见 [阶段 2 验收记录](docs/stage2-acceptance-zh.md)。

阶段 3 浏览器入口、固定日期演示与双窗口冲突步骤见 [阶段 3 使用说明](docs/stage3-usage-zh.md)。
