# Siftlane Engine

Siftlane 的独立 Python 爬虫执行引擎。它使用声明式 JSON DAG 定义流程，使用
SQLite 保存流程、运行、事件和结果，并通过异步 Worker 与 SSE 提供可取消、
可恢复、可观察的执行闭环。

每次运行都会固化创建时的流程版本和完整定义。即使随后修改流程，排队任务、
重启恢复和历史检查仍使用原始快照，不会静默切换到新配置。

引擎不执行任意 Python 或 JavaScript。HTTP 节点默认执行 SSRF、robots.txt、
限速、重定向和响应大小约束。

## 节点

| 节点 | 职责 |
| --- | --- |
| `start` | 生成入口 URL 和运行参数 |
| `http_request` | 执行受控 HTTP 请求 |
| `html_extract` | 使用 CSS Selector 提取重复记录 |
| `json_extract` | 使用安全点路径提取 JSON |
| `transform` | 使用 `{{field}}` 模板映射字段，不执行代码 |
| `emit` | 输出统一标题、URL、正文和元数据 |

## 本地启动

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[test]"
.\.venv\Scripts\siftlane-engine
```

服务默认监听 `http://127.0.0.1:8090`，OpenAPI 位于 `/docs`。

## API

```text
GET    /health
GET    /api/v1/capabilities
GET    /api/v1/flows
POST   /api/v1/flows
GET    /api/v1/flows/{flowId}
PUT    /api/v1/flows/{flowId}?expectedRevision=1
DELETE /api/v1/flows/{flowId}
GET    /api/v1/runs
POST   /api/v1/runs
GET    /api/v1/runs/{runId}
GET    /api/v1/runs/{runId}/flow
POST   /api/v1/runs/{runId}/cancel
GET    /api/v1/runs/{runId}/items
GET    /api/v1/runs/{runId}/events
GET    /api/v1/runs/{runId}/events/stream
GET    /api/v1/schedules
POST   /api/v1/schedules
PUT    /api/v1/schedules/{scheduleId}?expectedRevision=1
DELETE /api/v1/schedules/{scheduleId}
POST   /api/v1/schedules/{scheduleId}/trigger
```

## P2 execution semantics

- `condition` routes data over explicit `true` and `false` edge ports.
- `loop` and `pagination` expand data within configured and flow-level bounds;
  workflow graphs remain acyclic.
- Every node has a validated retry policy with bounded exponential backoff.
- Completed node outputs are zlib-compressed, checksummed, and persisted in
  `node_checkpoints`; restart recovery emits `node.restored` and skips execution.
- `emit` is replay-safe because item identity is unique within each run. Final
  processed counts always come from the persisted item table.
- The scheduler uses database leases and the idempotency key
  `schedule:{schedule_id}:{scheduled_fire_time}` to survive scheduler crashes.

SSE 支持 `Last-Event-ID` 和 `after` 续传，运行期间发送注释心跳，终态事件写入与
运行状态更新在同一个 SQLite 事务中完成。

## 验证

```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python scripts\smoke_test.py --base-url http://127.0.0.1:8090
```

Smoke test 会启动一个临时本地网页，创建四节点流程并验证 HTTP 获取、HTML
提取、结果持久化、流程快照和 SSE 断点续传。运行该测试时，引擎必须临时设置
`SIFTLANE_ENGINE_ALLOW_PRIVATE_NETWORKS=true`；常规运行应保持默认 `false`。

## 容器

```powershell
docker compose up --build
```

容器以非 root 用户运行，数据保存在命名卷中，并提供 `/health` 健康检查。
本机端口只绑定到 `127.0.0.1:8090`。

生产环境应设置 `SIFTLANE_ENGINE_API_TOKEN`。敏感请求头使用
`${secret:NAME}`，实际值从 `SIFTLANE_ENGINE_SECRET_NAME` 环境变量读取。

默认拒绝环回、内网和保留地址。只有本地 fixture 联调时才应临时设置
`SIFTLANE_ENGINE_ALLOW_PRIVATE_NETWORKS=true`。

前端开发默认允许 `http://127.0.0.1:5173` 和 `http://localhost:5173`。生产环境
通过 `SIFTLANE_ENGINE_ALLOWED_ORIGINS` 配置明确来源，并必须设置 API token。
