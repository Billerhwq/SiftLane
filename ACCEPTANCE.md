# Siftlane 阶段验收清单

本文档是 [8 节产品生命周期 PRD](PRD-SiftLane-product-lifecycle.md) 的证据账本。实现、测试文件或本地输出存在都不自动等于正式阶段通过；只有同一候选提交的自动证据、所需人工证据、远端门禁和发布后检查全部满足，阶段才能晋级。

## 状态定义与晋级规则

| 状态 | 含义 |
| --- | --- |
| `Passed` | 本项强制结果和列出的证据已满足 |
| `Failed` | 已执行但不满足门槛 |
| `Blocked` | 实现可存在，但前序发布、外部系统、远端 CI 或具名人工证据缺失 |
| `Planned` | 尚未实施或执行 |

上一阶段必须正式完成；当前阶段所有编号项必须为 `Passed`；自动证据必须来自同一候选提交；人工证据必须含评审人、UTC 日期、结论和关联提交/制品；版本、迁移、兼容、回滚、标签和发布后检查不得拆分拼接。`Blocked`、`Failed`、`Planned`、跳过或例外均不推动阶段状态。

## 阶段总览

| 阶段 | 工程状态 | 正式状态 | 结论 |
| --- | --- | --- | --- |
| P0 | 完成 | 追溯确认 | Passed |
| P1 | 完成 | `0.1.x` 功能基线，无独立 Release 声明 | Passed |
| P2 | 完成 | `v0.2.0` 已发布并校验资产 | Released |
| P3 | 功能与本地全量回归通过 | 未正式发布 | Blocked by `P3-00`, `P3-10`, `GOV-01` |
| P4 | 功能与 `v0.4.0` 本地候选通过 | 未正式发布 | Blocked by `P4-00`, `P4-10`, `GOV-01` |
| P5 | 实现与 `v1.0.0` 本地 GA 候选门禁通过 | 未达到 GA | Blocked by `P5-00`, `P5-04`, `P5-05`, `P5-08`-`P5-11`, `GOV-01` |

## P0 验收：产品边界与工程基础

| ID | 强制结果 | 证据 | 状态 |
| --- | --- | --- | --- |
| P0-01 | 产品名称、目标、独立性、能力和非目标有仓库事实源。 | `PRODUCT.md`, `README.md` | Passed |
| P0-02 | 组件、数据流、信任/存储边界和单节点假设已记录。 | `documentation/architecture.md` | Passed |
| P0-03 | HTTP 受 scheme、DNS/IP、robots、超时、重定向、速率和大小控制。 | `engine/tests/test_security.py` | Passed |
| P0-04 | 设计基线和响应式约束可构建、可检查。 | `DESIGN.md`, `design-system/`, Web 构建和布局断言 | Passed |
| P0-05 | 启动、测试、架构和操作入口可发现且可复用。 | `scripts/verify.ps1`, `documentation/` | Passed |

## P1 验收：单操作员核心工作流

| ID | 强制结果 | 证据 | 状态 |
| --- | --- | --- | --- |
| P1-01 | 浏览器可创建、编辑、连线、保存、删除和运行 DAG。 | `apps/web/tests/p1.spec.ts`, `outputs/p1-desktop.png` | Passed |
| P1-02 | 节点配置由 Schema 驱动，无效图/配置被拒绝。 | `test_models.py`, P1 E2E | Passed |
| P1-03 | 固定四节点流程恰好写入两条规范化结果。 | P1 E2E, `outputs/p1-desktop-results.png` | Passed |
| P1-04 | 持久事件、活动摘要、事件账本和可恢复 SSE 可用。 | API/服务测试和 P1 E2E | Passed |
| P1-05 | 队列、取消、运行快照、重启恢复和受控 HTTP 有自动断言。 | 存储、服务、进程恢复、安全测试 | Passed |
| P1-06 | 390x844 抽屉可用且无文档级横向溢出。 | P1 移动 E2E, `outputs/p1-mobile.png` | Passed |
| P1-07 | Connector SDK v1 契约与发现边界存在且不伪造安装。 | Connector/API 测试, `engine/CONNECTOR_SDK.md` | Passed |

## P2 验收：可靠编排、恢复、调度与发布

| ID | 强制结果 | 证据 | 状态 |
| --- | --- | --- | --- |
| P2-01 | 条件只通过明确 `true`/`false` 端口路由。 | P2 引擎/E2E, `outputs/p2-branch-retry.png` | Passed |
| P2-02 | 循环和分页有节点/流程上限且不生成图回边。 | `test_loop_and_pagination_are_bounded` | Passed |
| P2-03 | 瞬时失败有界重试，耗尽后明确失败。 | `test_retry_succeeds_and_exhausts`, P2 E2E | Passed |
| P2-04 | 校验和检查点在进程重启后精确恢复且无重复结果。 | 检查点和进程恢复测试 | Passed |
| P2-05 | 时区调度具备租约、幂等、CRUD、暂停、触发和竞争领取。 | Schedule 测试/E2E, `outputs/p2-scheduler.png` | Passed |
| P2-06 | 一个根命令执行后端、构建、浏览器和元数据门禁。 | `scripts/verify.ps1` | Passed |
| P2-07 | wheel、sdist、Web zip、manifest 和 SHA-256 可构建并冒烟安装。 | `scripts/package-release.ps1` | Passed |
| P2-08 | 标签工作流先验收再创建 Release，回滚/停止条件有文档。 | Actions runs `30666925268`, `30667147413`; `documentation/release.md` | Passed |
| P2-09 | `v0.2.0` 标签、提交和五个下载资产已独立复核。 | GitHub Release `v0.2.0`, commit `6e4c92a` | Passed |

## P3 验收：安全团队协作

| ID | 强制结果 | 自动/仓库证据 | 缺失证据或结论 | 状态 |
| --- | --- | --- | --- | --- |
| P3-00 | P2 已发布，`main` 必需检查已确认，P0-P2 在候选提交通过。 | `v0.2.0`; 当前 `37 passed`/`8 passed` | GitHub API 确认 `main protected=false`、rulesets 为空 | Blocked |
| P3-01 | 登录、续期、退出、过期、撤销、固定和节流安全。 | `test_p3_security.py`, `p3.spec.ts` | 无 | Passed |
| P3-02 | 非回环空凭据启动被拒绝，错误不泄密。 | P3 负向配置/API 测试 | 无 | Passed |
| P3-03 | admin/editor/viewer、所有权、private/team 和旧数据迁移明确。 | P3 模型/存储回归, `permissions.md`, `migrations.md` | 无 | Passed |
| P3-04 | 流程、运行、结果、SSE、取消和调度逐资源服务端授权。 | 资源授权矩阵与角色降级后的 owner 权限回归 | 无 | Passed |
| P3-05 | 跨用户枚举、直接 ID 和 viewer 变更/执行被拒绝。 | P3 deny tests | 无 | Passed |
| P3-06 | 敏感操作和拒绝结果进入普通用户不可变的审计记录。 | P3 audit API/E2E, `outputs/p3-team-audit.png` | 无 | Passed |
| P3-07 | 连接器发现崩溃、超时、超限和环境秘密在子进程边界内。 | P3 isolation tests, `threat-model.md` | 非内核沙箱限制已公开 | Passed |
| P3-08 | 认证拒绝和隔离故障有安全计数/告警视图。 | Security operations API/E2E | 无 | Passed |
| P3-09 | 威胁模型、权限、迁移和回滚路径已记录。 | P3 shipping artifacts | 无 | Passed |
| P3-10 | P0-P3 同提交候选、远端 CI、正式标签和发布后检查全部通过。 | 本地全量回归已通过 | `v0.3.0` 正式标签/CI/发布后证据缺失 | Blocked |

## P4 验收：托管连接器与数据交付

| ID | 强制结果 | 自动/仓库证据 | 缺失证据或结论 | 状态 |
| --- | --- | --- | --- | --- |
| P4-00 | P3 已正式发布且 P0-P3 在候选提交回归。 | 当前全量本地回归 | P3 未正式发布 | Blocked |
| P4-01 | 管理员可校验 wheel 并安装、启停、升级、回退、卸载。 | `test_p4_integrations.py` | 无 | Passed |
| P4-02 | 主程序/SDK/连接器兼容性和 SHA-256 在变更前校验。 | P4 兼容与负向安装测试 | 无 | Passed |
| P4-03 | Fernet 作用域密钥仅以密文持久化，明文不进入 API/审计/导出。 | P4 secret/redaction、连接器结果回显拒绝和安全扫描 | 无 | Passed |
| P4-04 | JSON Feed 参考连接器完成真实 HTTP、游标、错误和隔离执行。 | 参考连接器与 worker 集成测试 | 无 | Passed |
| P4-05 | NDJSON/Webhook 支持 Bearer/HMAC、超时、取消和明确结果。 | P4 delivery tests | 无 | Passed |
| P4-06 | 幂等键、固定尝试上限和指数退避阻止无界重复。 | 重复/失败/恢复断言 | 无 | Passed |
| P4-07 | 历史、错误、下次重试、死信、取消和受控重放可查可审计。 | P4 API/E2E | 无 | Passed |
| P4-08 | 权限一致的连接器、密钥、目标和交付控制台不回显敏感值。 | `p4.spec.ts`, `outputs/p4-integrations-delivery.png` | 无 | Passed |
| P4-09 | 连接器和目标可独立禁用/回退，积压不会无界重试。 | P4 rollback/dead-letter tests, runbooks | 无 | Passed |
| P4-10 | P0-P4 候选、远端 CI、升级/回滚、标签和发布后检查全部通过。 | `v0.4.0` 本地候选：后端 32、E2E 6、五项制品均通过 | P3/P4 正式标签与远端证据缺失 | Blocked |

## P5 验收：生产就绪与 GA

| ID | 强制结果 | 自动/仓库证据 | 缺失证据或结论 | 状态 |
| --- | --- | --- | --- | --- |
| P5-00 | P4 已发布，代表负载、资源、生产负责人和支持边界确认。 | 负载参数与单节点边界已文档化 | P4 发布、负责人/环境签署缺失 | Blocked |
| P5-01 | 吞吐、并发、数据库增长和门槛有可复现报告。 | `p5-capacity-report.json`: 120 runs/2400 items/concurrency 8/37.036845s/1,552,384 bytes | 无 | Passed |
| P5-02 | 正式长稳门槛内无数据丢失和异常资源增长。 | `p5-soak-report.json`: 30s/80 cycles/400 items/37,325-byte heap growth | 无 | Passed |
| P5-03 | 备份恢复达到 RPO/RTO，SHA-256、计数和 integrity 通过。 | `p5-backup-restore-report.json`: 0.100643s/schema 5/integrity ok | 无 | Passed |
| P5-04 | 从上一正式版本升级、失败中止和允许回滚完成演练。 | schema 2-5/`v0.2` 契约、tamper/restore 自动测试 | P4 未正式发布，无法形成“上一正式 P4”演练 | Blocked |
| P5-05 | 干净 Linux 部署验证启动、停止、持久化、日志和加固。 | Dockerfiles/Compose/YAML 解析；CI job 已定义 | 本机无 Docker；远端 `linux deployment` 未执行 | Blocked |
| P5-06 | live/ready、指标、JSON 日志、SLO 和告警指向操作步骤。 | P5 API/E2E, `slo.md`, `alerts.yml`, runbooks | 无 | Passed |
| P5-07 | API、流程、SDK、数据库和备份具有 v1 兼容/弃用策略。 | `compatibility.md`, `v0.2-flow.json`, schema tests | 无 | Passed |
| P5-08 | 生产依赖、凭据、权限和制品无未接受高危问题。 | Python 无已知漏洞；npm 0；repo scan 0；最终候选制品扫描 0 | 具名安全签署缺失 | Blocked |
| P5-09 | axe、键盘、焦点、Escape、对比度和 200% 重排无阻断。 | `p5.spec.ts`, `outputs/p5-production-readiness.png`; 自动 `8 passed` | 具名人工关键流审查缺失 | Blocked |
| P5-10 | 非作者可执行部署、运维、事故、备份、恢复、升级和回滚文档。 | 完整 shipping artifacts 与命令门禁 | 非作者桌面演练记录缺失 | Blocked |
| P5-11 | P0-P5 RC、GA 标签、远端 Windows/Linux、发布后健康/迁移/路径/哈希均通过。 | 本地最终制品和 lifecycle gate 已通过 | 远端 CI、GA/发布后证据缺失 | Blocked |

## 跨阶段治理债务

| ID | 必须结果 | 证据要求 | 状态 | 阻断范围 |
| --- | --- | --- | --- | --- |
| GOV-01 | 管理员确认 `main` 必需 `P2 acceptance / acceptance` 和 `P2 acceptance / linux deployment`。 | 2026-08-01 GitHub 只读 API：`main protected=false`，repository rulesets `[]` | Open：尚未配置且无管理员签署 | 不撤销 `v0.2.0`；阻断 P3/P4/P5 正式发布 |

## 当前同工作树验证记录

- 2026-08-01：`scripts/verify.ps1 -BrowserChannel chrome` 通过。
- 后端：`37 passed`；仅有上游 Starlette `httpx` 弃用警告。
- Web：TypeScript/Vite 生产构建通过，1,796 modules；Playwright P1-P5 `8 passed`。
- 端口：E2E 隔离启动并释放 `5173`、`8090`、`8877`。
- 安全：Python 生产依赖无已知漏洞；npm 生产依赖 0；仓库凭据和最终候选制品扫描 0。
- P5 报告：容量、备份恢复、正式 30 秒长稳全部 `passed: true`；最终数据与 P5-01 至 P5-03 一致。
- 制品：`v1.0.0` 本地候选的 manifest、sdist、wheel、Web zip 在 `SHA256SUMS.txt` 中重算一致；manifest 如实标记基线提交 `b854869` 和 `gitDirty: true`。
- Linux/Docker：当前 Windows 主机无 Docker CLI，只有待远端执行的 CI 定义，不能记为通过。
- 远端：GitHub `main` 指向 `b854869`；该提交的 `P2 acceptance` 仅有 `acceptance` job 成功。当前工作树未推送，且没有 `linux deployment` 运行证据。

## 当前晋级决定

本地工程结论：P3、P4 功能实现和 P5 生命周期候选门禁均已通过；`v1.0.0` 本地 GA 候选已经形成。该候选来自 dirty worktree，仅用于本地验收，不是正式发布制品。正式产品结论：P3 未正式发布，因此 P4/P5 的前序进入条件不成立；`GOV-01`、Linux CI、上一正式版本升级演练及具名人工签署未关闭，当前不得标记 P3/P4 为 `Released`，也不得标记 `v1.0.0` 为 GA。
