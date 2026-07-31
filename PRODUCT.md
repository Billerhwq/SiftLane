# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Python 3.11+、FastAPI、Pydantic、SQLite WAL 与异步 Worker 构成独立执行引擎；
React、TypeScript、Vite、React Flow、TanStack Query 和 Lucide 构成 Web 控制面。
这一选择沿用已验证的原型技术路径，但不继承 SubtleSight 的 Java 服务或 UI。

## Users

主要用户是需要反复定义、运行和观察网页采集流程的数据工程师、研究人员与
小型数据团队。他们在本地或受控服务器环境中工作，需要在不编写任意脚本的
前提下把 HTTP、提取、转换和输出步骤组织成可复用流程。

## Product Purpose

Siftlane 是一个独立的可视化爬虫工作流产品。用户可以设计声明式 DAG、运行
任务、查看实时事件和结构化结果，并在进程重启后恢复未完成任务。成功意味着
一次采集的配置、状态、错误、事件和输出都能被追踪并再次运行。

## Positioning

产品把现代 Python 执行引擎、可视化流程编排与受控网络安全策略放在同一协议
中。它借鉴 spider-flow 的可视化工作流和 MediaCrawler 的平台采集工程经验，
但不复刻旧 Java 架构，也不通过任意脚本执行来获得扩展性。

## Operating Context

- 用户在浏览器中创建或选择流程，配置节点与边，保存版本并启动运行。
- 运行期间，界面持续显示一到两行当前活动，并可展开完整有序事件记录。
- 运行完成后，用户检查统一结果、错误与原始来源，再决定后续导出或接入方式。
- Python 引擎作为独立进程或容器运行，前端只通过版本化 HTTP/SSE API 通信。

## Capabilities and Constraints

- 支持 `start`、`http_request`、`html_extract`、`json_extract`、`transform` 和 `emit` 节点。
- 支持持久队列、幂等运行、取消、重启恢复、SSE、版本冲突和分页结果。
- 默认执行 SSRF、robots.txt、限速、重定向和响应体大小限制。
- 首版不声称支持浏览器自动化、登录态平台适配器或任意 Python/JavaScript 执行。
- 执行引擎数据库独立，不依赖 SubtleSight 的数据、服务或认证。
- 插件和更多节点将通过稳定工具/节点协议扩展；具体市场与授权模式尚未决定。

## Brand Commitments

工作品牌为 **Siftlane**，用于本轮方向探索，最终命名仍可由用户调整。产品语气
应直接、技术可信且面向操作，不使用营销化夸张、虚构连接器或虚构性能数据。

## Evidence on Hand

- `engine/` 包含已通过测试的 Python DAG 执行引擎、安全 HTTP 客户端、SQLite
  存储、SSE 和 fixture。
- 已有真实联调证据证明四节点 HTML 流程可输出两条结构化结果。
- 当前没有客户案例、生产规模指标、已认证平台连接器或商业授权信息，界面不得虚构。

## Product Principles

1. 流程是可检查的数据，不是隐藏脚本。
2. 当前活动保持紧凑，完整历史随时可展开且不打断工作位置。
3. 网络能力默认受限，扩展能力必须显式声明。
4. 失败、取消、恢复和空状态与成功路径同等重要。
5. 独立部署和稳定协议优先于对任何宿主产品的耦合。

## Accessibility & Inclusion

关键流程必须支持键盘操作、清晰焦点、非颜色状态、缩放和窄屏使用。动态事件
应使用合适的 live region，并在 `prefers-reduced-motion` 下移除非必要动画。
