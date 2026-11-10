# IncidentPilot PRD（Phase 0）

版本：v0.1（待确认）
目标读者：面试官 / 项目评审 / 开发协作者
产品形态：面向微服务架构的企业级 AIOps / AI SRE 平台（本地可完整运行）

---

## 1. 背景与问题

微服务化后，一次线上故障通常同时涉及指标、日志、调用链、发布变更和历史知识。传统排障流程存在六个结构性问题：

| 编号 | 问题 | 业务后果 |
| --- | --- | --- |
| P1 | 告警分散在 Prometheus / Alertmanager，重复告警多 | 工程师被噪声淹没，真正故障被淹没 |
| P2 | 指标、日志、Trace 分散在不同系统 | 人工拼接上下文，MTTD/MTTR 长 |
| P3 | 根因判断依赖个人经验 | 结论不可复用、不可审计 |
| P4 | 历史故障与 SOP 未被有效利用 | 同类故障重复排查 |
| P5 | 修复动作跨多个系统，人工执行易错 | 误操作、无回滚、无审计 |
| P6 | 修复后缺少统一验证 | "以为恢复了"但故障仍在 |

IncidentPilot 的目标不是做一个"会聊天的运维助手"，而是把上述流程产品化，并保证：

- 每个根因结论都能追溯到**真实工具调用产生的证据**；
- 每个执行动作都经过**确定性权限系统**，而不是由模型直接操作基础设施；
- 每次恢复判断都基于**修复前后的真实监控数据**。

---

## 2. 产品定位与边界

### 2.1 是什么

一个接收真实 Alertmanager 告警、自动创建 Incident、由 LangGraph Agent 执行多源调查、生成带证据引用的根因分析与修复方案、经人工审批后由 Remediation Executor 安全执行、并用 Prometheus/Loki/Tempo 数据验证恢复情况的 AI SRE 系统。

### 2.2 不是什么

| 非目标 | 说明 |
| --- | --- |
| 通用 RAG 聊天机器人 | 知识库只作为 Agent 的一个调查维度，不提供独立闲聊入口 |
| 自动执行任意 Shell | 禁止模型生成/执行命令；执行动作来自固定目录 + Schema 校验 |
| 生产环境自动变更 | 第一阶段所有自愈动作仅允许在本地演示环境执行 |
| 多 Agent 自由聊天 | 使用确定性图路由、工具调用、证据校验，不做角色轮流对话 |
| 前端假数据 Demo | 所有页面数据来自真实 API；演示数据由真实故障注入产生 |
| 模型凭直觉猜根因 | 证据不足时输出 `UNKNOWN` / 低置信度，并触发追加调查 |

---

## 3. 用户与权限角色

| 角色 | 典型用户 | 权限 |
| --- | --- | --- |
| `VIEWER` | 观察者 / 面试官 | 查看 Dashboard、Incident、证据、报告；不可触发调查/审批 |
| `SRE` | 一线运维工程师 | 触发调查、查看全部证据、审批 MEDIUM 风险动作 |
| `ADMIN` | 运维负责人 | 审批 HIGH 风险动作、管理模型/MCP/知识库、触发演示故障注入 |
| `SERVICE` | 告警系统 / 内部服务 | 仅可调用 Alertmanager Webhook 与内部任务接口（mTLS/Token） |

约束：

- Agent 以 `SYSTEM` 身份发起修复申请，**永远不能自我审批**；
- 审批人与申请人必须不同（`approver_id != requested_by`）；
- HIGH 风险动作要求 ADMIN 审批，并记录审批时看到的方案快照哈希。

---

## 4. 核心用户旅程

```
① 故障注入（仅演示环境）
      │
② Prometheus 规则触发 → Alertmanager → Webhook
      │
③ 告警归一化 / 去重 / 聚合 → 创建 Incident（DETECTED）
      │
④ 后台任务启动 LangGraph 调查（INVESTIGATING）
      │
⑤ 并行调查：Metrics / Logs / Traces / Changes / Knowledge
      │
⑥ 证据聚合 + 根因分析 + 修复方案 + Reviewer 复核
      │
⑦ 需要审批 → AWAITING_APPROVAL（SSE 实时推送审批卡片）
      │
⑧ SRE/ADMIN 审批 → 恢复图执行 → REMEDIATING
      │
⑨ 修复前后指标对比 → VERIFYING → RESOLVED / PARTIALLY_RECOVERED / NOT_RECOVERED
      │
⑩ 生成故障报告 + 审计记录 + 评测样本
```

关键体验：

- Incident Detail 页面通过 SSE 实时看到 Agent 节点状态、工具调用、证据加入、审批要求；
- 刷新页面或断线重连后，能从数据库回放已发生的全部事件；
- 审批卡片展示：动作类型、目标服务、参数、风险等级、预期影响、回滚方式、证据摘要；
- 验证阶段展示修复前后指标对比与判定依据，数据不足时明确标注"证据不足"。

---

## 5. 功能需求

### FR-01 告警事件中心

- 接收 Alertmanager Webhook（`POST /api/v1/webhooks/alertmanager`），校验共享 Token；
- 告警归一化：统一 `source / service / severity / rule / labels / annotations / startsAt / endsAt`；
- 去重：基于指纹 + 时间窗；
- 聚合：同服务、同告警族在窗口内合并为同一 Incident；
- 服务关联：通过 `service` label / 规则映射表关联 `services`；
- 故障等级：由告警 severity、服务 Tier、影响面计算；
- 状态管理：`firing / resolved / suppressed`，支持 Alertmanager resolved 回调；
- Incident 状态机见 [02-data-model.md](02-data-model.md)。

验收：

- 同一告警重复推送 10 次只产生 1 条 Alert、1 个 Incident；
- 5 分钟内同服务多规则告警合并，时间线保留全部子告警；
- 无效 Token / 非法 JSON 返回 401/422，且不写库；
- Webhook 处理幂等，重复请求不重复入队。

### FR-02 AI 故障调查引擎

- LangGraph 有状态图，节点：Alert Analyzer、Investigation Planner、Metrics/Log/Trace/Change/Knowledge Investigator、Root Cause Analyzer、Remediation Planner、Reviewer；
- 调查必须调用 MCP 工具，证据带来源、查询参数、观测时间、内容哈希；
- 支持并行调查、追加调查（最多 2 轮）、预算控制（工具调用/Token/时长）；
- 支持 Checkpoint（PostgreSQL），进程重启后可恢复；
- 支持暂停等待审批、审批后恢复；
- 根因输出必须包含置信度、不确定性、证据 ID 列表；
- 证据不足时不得编造根因。

验收：

- 7 个故障场景中至少 5 个能给出 Top-3 内正确根因（以真实评测结果为准，不预设通过）；
- 任一结论的证据 ID 均能在 `evidence` 表中查到；
- 杀死 worker 后重启，Run 可从最近 checkpoint 继续；
- 工具调用总数、时长、Token 超限时按策略终止并输出原因。

### FR-03 多源数据关联

- 指标：CPU、内存、QPS、HTTP 5xx 比例、P95/P99、DB 连接池使用率；
- 日志：异常日志、SQL 异常、超时、堆栈、Trace ID；
- 调用链：Span 耗时、错误 Span、服务依赖、关键路径；
- 变更：Git commit / PR / 发布记录 / 文件变更；
- 关联键：服务名、时间窗口、Trace ID、异常类型、发布版本；
- 输出带证据引用的根因报告与时间线。

验收：

- 订单服务 5xx 场景中，报告能指出数据库连接池耗尽或上游超时，并引用对应指标/日志/Trace；
- 若最近 24h 有发布，Change Investigator 必须被调用；
- 时间窗口统一 UTC，展示时转换为本地时区。

### FR-04 MCP 工具管理

- 独立 MCP Server：Prometheus、Loki、Tempo、Kubernetes、GitHub（含发布记录）、Knowledge Base；
- 每个工具具备：名称、描述、输入 Schema、输出结构、权限级别、超时、调用日志；
- 统一注册与调用接口，Agent 不直接拼接查询语句；
- 工具调用记录落库，可在前端查看。

验收：

- 每个 Server 可独立启动并通过 MCP 协议列出工具；
- 非法参数被 Schema 拒绝，返回结构化错误；
- 工具超时/上游不可用时，Agent 收到可处理的错误而不是崩溃；
- Agent 仅能访问 `read` 权限工具。

### FR-05 企业 RAG 故障知识库

- 导入 PDF / Markdown / TXT / 历史 Incident 报告 / SOP；
- 解析 → 清洗 → Chunk → Embedding → Milvus → BM25 + 向量混合检索 → RRF → Rerank → 上下文构建；
- 元数据与服务过滤、文档版本管理、引用溯源、删除与更新、检索测试页；
- 本地 BGE-M3（dense）+ 本地 BGE Reranker v2-m3；
- 为 Agent 提供证据，不提供独立闲聊。

验收：

- 上传文档后可在检索测试页看到 BM25/向量/RRF/Rerank 各阶段结果与耗时；
- 检索结果包含文档名、版本、章节、页码/片段、相似度；
- 文档更新生成新版本，旧版本可追溯；
- 引用可跳转到原始文档片段。

### FR-06 安全自动化处置与自愈

- 动作目录：重启测试服务、清理可控缓存、扩容测试实例、回滚模拟版本、健康检查；
- 只读默认；写操作必须 Schema 校验 + 风险分级 + 审批；
- 执行器独立于 Agent，Agent 无法绕过；
- 审计日志覆盖：申请、审批、执行、结果、回滚；
- 超时、幂等、最大重试次数、失败终止；
- 执行后强制进入验证流程。

验收：

- Agent 无法调用写工具（工具注册层直接拒绝并审计）；
- HIGH 风险动作无 ADMIN 审批时执行器拒绝；
- 重复执行同一幂等键不会产生第二次副作用；
- 执行失败最多重试 1 次，之后标记 FAILED 并保留现场。

### FR-07 故障恢复验证

- 健康检查、5xx 比例、P95、CPU/内存、关键业务接口、修复前后对比；
- 判定：`RECOVERED / PARTIALLY_RECOVERED / NOT_RECOVERED / INSUFFICIENT_DATA`；
- 数据点不足时不得判定恢复成功；
- 恢复后 30 分钟内告警复发视为 False Recovery（评测口径）。

### FR-08 Agent 可观测性与评测

- OpenTelemetry：节点耗时、模型调用、Token、工具调用、异常、整体耗时；
- Langfuse：LLM Trace（可云端或可选自托管）；
- Evaluation Center：可重复执行的故障评测集与指标；
- 指标：Root Cause Top-1/Top-3、Evidence Accuracy、Tool Selection/Argument Accuracy、Task Completion、Remediation Success、False Recovery；
- 只展示真实执行结果，记录数据集版本、模型、时间。

### FR-09 微服务测试环境

- Docker Compose 启动 Order / Payment / Inventory 三个 FastAPI 服务；
- 接入 PostgreSQL、Redis、Prometheus、Grafana、Loki、Tempo、OpenTelemetry；
- 7 类故障注入，前端可触发；
- 注入逻辑与生产执行逻辑隔离（独立 demo-control 服务 + Token + 网络限制）。

### FR-10 前端

- 13 个页面，React + TS + Vite + Ant Design + ECharts；
- 深色侧边导航 + 浅色内容区 + 科技蓝主色；
- 真实 API、加载/空/错误状态、SSE 实时执行；
- 禁止无后端逻辑的按钮。

---

## 6. 非功能需求

| 类别 | 要求 |
| --- | --- |
| 性能 | 告警入库 P95 < 300ms；Incident 列表 P95 < 500ms；单次调查常规 1–5 分钟 |
| 可用性 | 基础环境单机 Compose 可启动；worker 崩溃不丢任务；SSE 断线可回放 |
| 一致性 | 告警去重/Incident 聚合幂等；执行动作幂等；审批决策不可变 |
| 安全 | 密钥不入库明文/不入 Git；写操作强制审批；全量审计 |
| 可观测 | 每个 Run 可追踪节点、工具、模型、Token、耗时、错误 |
| 可测试 | 单元/集成/E2E/评测四层；评测可重复执行 |
| 可移植 | Windows + Docker Desktop 可运行；Linux 服务器同样可运行 |
| 资源 | 默认配置在 16GB RAM 开发机可运行（见 07 资源预算） |

---

## 7. 成功指标（项目验收口径）

不以"页面好看"作为成功标准，以闭环真实性为准：

1. 真实告警能从 Alertmanager 进入系统并创建 Incident；
2. Agent 至少调用 3 类真实数据源（Prometheus / Loki / Tempo）形成证据链；
3. 根因报告 100% 结论带证据引用，0 条悬空引用；
4. 至少 1 个场景完成"审批 → 执行 → 指标验证 → RESOLVED"闭环；
5. 7 个故障场景全部可注入、可观测、可复现；
6. 评测集真实执行并输出 N、日期、模型配置，不伪造指标；
7. 杀死 worker 后任务可恢复；
8. 审计日志可还原一次完整操作链。

---

## 8. 范围与非目标（第一阶段）

**范围内**：本地 Compose 演示环境、单集群/单命名空间、只读调查、5 类安全动作、7 个故障场景、中文 UI。

**范围外**：多租户 SaaS、生产 K8s 接入、真实工单系统集成、移动端、计费、跨云、自动扩缩容策略引擎、模型微调。

---

## 9. 术语表

| 术语 | 含义 |
| --- | --- |
| Incident | 一次故障事件，聚合一个或多个 Alert |
| Evidence | Agent 通过工具调用获得的可追溯证据 |
| Run | 一次 Agent 图执行，绑定 Incident |
| Plan | 修复方案，包含一个或多个 Action |
| Action | 原子修复动作（重启/扩容/回滚等） |
| Approval | 人工审批记录，绑定 Plan 版本与动作 |
| Verification | 修复后的指标验证与判定 |
| Checkpoint | LangGraph 持久化状态快照 |
| MCP | Model Context Protocol，工具服务协议 |
| RRF | Reciprocal Rank Fusion，混合检索融合算法 |

---

## 10. 演示脚本（8 分钟）

1. 打开 Dashboard，展示服务健康与当前无故障（30s）。
2. 进入演示控制，触发"数据库连接池耗尽"（30s）。
3. Prometheus 告警 → Alertmanager → Incident 自动创建，Dashboard 出现红色事件（45s）。
4. 打开 Incident Detail，展示 SSE：Planner → 并行调查 → 工具调用参数与结果（2min）。
5. 展示证据面板：指标曲线、Loki 日志（含 Trace ID）、Tempo 调用链、发布记录、知识库引用（1min）。
6. 展示根因（DB_POOL_EXHAUSTION，置信度 + 证据引用）与修复方案（重启 + 扩容）（45s）。
7. Approval Center 审批，展示风险等级与预期影响；执行后验证曲线恢复（1min）。
8. 展示审计日志、Run 的 Token/耗时/工具统计、Evaluation Center 中该场景的历史结果（1min）。
9. 强调：Agent 无写权限、执行器独立、验证基于真实指标、断线可回放（30s）。
