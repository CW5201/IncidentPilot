# 开发路线、风险与待确认决策（Phase 0）

版本：v0.1（待确认）

---

## 1. 分阶段任务清单

> 工作量为单人全职估算，仅用于排期参考；每阶段以"可运行 + 可测试 + 可联调"为完成标准。

### Phase 0：分析与架构（已完成，待确认）

交付：

- 环境核验（Python/Node/Docker/模型/端口/磁盘）；
- PRD、架构、数据模型、Agent 工作流、MCP、API、前端、基础设施、安全测试、路线图共 10 份文档；
- 本地 BGE-M3 与 Reranker 加载验证；
- Git 仓库初始化（未提交）。

退出标准：你确认架构与待定决策。

---

### Phase 1：基础设施与后端基础（预计 6–8 人日）

任务：

1. [x] Monorepo 脚手架：`backend/`、`frontend/`、`infrastructure/`、`scripts/`；
2. [x] `pyproject.toml`（uv）、ruff、mypy、pytest、pre-commit；
3. [x] 配置系统（pydantic-settings）、结构化日志、统一异常、request_id；
4. [x] PostgreSQL 连接池、Alembic 初始化、首批迁移（users/services/alerts/incidents/agent_runs/audit/outbox）；
5. [x] 认证：登录、刷新、注销、JWT、Argon2、RBAC 依赖；
6. [x] 用户种子（admin/sre/viewer）；
7. [x] 告警 Webhook：Token 校验、归一化、去重、聚合、Incident 创建、Outbox；
8. [x] Incident 查询 API + 时间线；
9. [x] RabbitMQ 拓扑（exchange/queue/DLQ）+ Outbox 投递器；
10. [x] 统一错误码、分页、幂等中间件；
11. [x] Docker Compose core（postgres/redis/rabbitmq/backend/worker/nginx）；
12. [x] 单元 + 集成测试（auth、webhook、incident、幂等）；
13. [x] 审计服务与基础审计接口。

退出标准：

- `docker compose up` 后登录、创建事件、查询列表可用；
- 重复 Webhook 不重复建事件；
- `pytest` 全绿；
- OpenAPI 可访问，前端可生成类型。

---

### Phase 2：微服务测试环境与可观测性（预计 5–7 人日）

任务：

1. Order / Payment / Inventory 三个 FastAPI 服务（SQLAlchemy async、Redis、HTTPX）；
2. 服务间调用与 OTel 上下文传播；
3. Prometheus 指标（HTTP、连接池、Redis、业务）；
4. OTel Collector → Tempo；Alloy → Loki；Grafana 数据源与 Dashboard；
5. Prometheus 告警规则 + Alertmanager → 后端 Webhook；
6. chaos-controller：7 个场景、Token、TTL、状态查询；
7. toxiproxy 集成（Redis/payment 链路延迟与断连）；
8. `order-service-b` 副本（默认停止）与 Nginx 上游；
9. 种子数据与演示 SOP 文档；
10. 端到端验证脚本：注入 → 告警 → Incident；
11. 观测数据校验（指标/日志/Trace 三源可查）。

退出标准：

- 7 个场景均能产生预期告警与三源数据；
- Grafana 能看到服务指标与 Trace；
- 告警自动创建 Incident；
- 注入可停止、可重复。

---

### Phase 3：Agent 执行引擎（预计 8–10 人日）

任务：

1. MCP 公共库（认证、错误契约、超时、日志、结果裁剪）；
2. Prometheus / Loki / Tempo MCP Server；
3. MCP 注册表同步与工具目录缓存；
4. GovernedTool（Schema、权限、重试、熔断、证据生成、审计）；
5. LangGraph State、节点、条件边、并行 `Send`；
6. LLM 客户端（NVIDIA NIM / Nemotron、推理内容剥离、超时、重试、限流、JSON 模式 + Function Calling）；
7. Alert Analyzer / Planner / 三个 Investigator / Aggregator / Root Cause / Reviewer；
8. Checkpoint（Postgres）+ worker 恢复；
9. RabbitMQ 调查任务消费 + 幂等；
10. SSE 事件落库 + Redis 广播 + 回放；
11. 预算、超时、取消、失败处理；
12. 最小可用的 Run 查询 API 与前端时间线（可先简版）。

退出标准：

- 3 个场景可完成调查并输出带证据引用的根因；
- 工具调用可在数据库与前端查看；
- `kill -9` worker 后可恢复；
- SSE 断线重连不丢事件。

---

### Phase 4：RAG 与多源根因分析（预计 6–8 人日）

任务：

1. RAG 推理服务（embedding/rerank、批处理、健康检查）；
2. 文档上传、解析（PyMuPDF）、清洗、Chunk、版本管理；
3. BGE-M3 向量化 + Milvus 写入/删除/过滤；
4. BM25（bm25s + jieba）索引与持久化；
5. 混合检索 → RRF → Rerank → 引用构建；
6. Knowledge Base MCP + 内部 RAG API；
7. 检索测试页（各阶段结果与耗时）；
8. 多源证据关联（时间/服务/Trace ID/变更）；
9. 根因分析 Prompt + 引用校验 + 置信度校准；
10. 证据不足路由与追加调查；
11. 知识库 SOP 文档导入（7 个场景各 1 篇）。

退出标准：

- 检索可返回 BM25/向量/RRF/Rerank 各阶段结果与引用；
- Agent 在 5/7 场景中 Top-3 命中（真实执行结果）；
- 所有结论引用有效；
- 文档更新后新版本可检索，旧版本可追溯。

---

### Phase 5：安全自愈与恢复验证（预计 6–8 人日）

任务：

1. 动作目录与参数模型（restart/clear_cache/scale_out/rollback/health_check）；
2. 风险策略、审批策略、目标白名单、环境限制；
3. RemediationPlan / Action / Approval 持久化与状态机；
4. LangGraph `interrupt()` 审批门禁；
5. 审批 API + 过期调度 + 恢复执行；
6. Docker 执行后端（restart/scale/rollback/clear cache）；
7. 幂等键、执行快照、失败处理、回滚信息；
8. 审计链（申请/审批/执行/验证）；
9. Verification：前后指标对比、判定、数据不足处理；
10. 审批中心前端 + 验证面板；
11. 安全测试（越权、哈希篡改、重放、写工具隔离）。

退出标准：

- 2 个场景完成"审批 → 执行 → 验证 → RESOLVED"闭环；
- HIGH 风险无 ADMIN 审批被拒绝；
- 重复执行无第二次副作用；
- 验证数据不足时不判成功；
- 审计可还原完整链路。

---

### Phase 6：前端完整实现（预计 8–10 人日）

任务：

1. 设计系统、布局、路由、权限守卫；
2. Dashboard、Incident Center、Incident Detail（核心）；
3. Agent Investigation（SSE、节点图、工具表、证据流）；
4. Service Monitoring、Log Explorer、Trace Explorer；
5. Knowledge Base（上传/版本/检索测试）；
6. MCP Tools、Approval Center、Remediation History；
7. Evaluation Center、System Settings、演示控制；
8. 加载/空/错误/403 状态；
9. ECharts 指标图、Trace 瀑布、依赖图；
10. 类型生成、错误边界、可访问性；
11. Playwright 关键路径。

退出标准：

- 13 个页面全部接真实 API；
- 无假数据、无空按钮；
- SSE 实时展示与断线回放可用；
- 权限差异在 UI 与 API 一致。

---

### Phase 7：评测与交付（预计 4–6 人日）

任务：

1. 评测数据集（20 用例，7 场景 × 变体）；
2. 评测运行器（重置、注入、等待、收集、清理）；
3. 指标计算与报告（Top-1/3、Evidence、Tool、Completion、Remediation、False Recovery）；
4. 真实执行评测并记录 N/日期/模型/版本；
5. 架构图、ER 图、部署图、API 文档定稿；
6. README、部署说明、演示脚本、故障排查；
7. 性能与稳定性测试；
8. 安全验收清单；
9. 已知问题与替代方案清单；
10. 最终演示彩排（8 分钟）。

退出标准：

- 评测报告真实可复现；
- 一键启动文档可用；
- 演示闭环稳定；
- 所有 TODO 有归属或明确说明。

---

## 2. 总体里程碑

| 里程碑 | 内容 | 判定 |
| --- | --- | --- |
| M1 | 告警 → Incident | 真实 Webhook 入库 |
| M2 | 三源可观测 | 指标/日志/Trace 可查 |
| M3 | Agent 调查 | 带证据根因 |
| M4 | RAG 增强 | 引用可溯源 |
| M5 | 安全闭环 | 审批 → 执行 → 验证 |
| M6 | 产品化前端 | 全页面真实数据 |
| M7 | 可评测交付 | 真实评测报告 |

---

## 3. 待确认决策

| # | 决策 | 推荐 | 备选 | 影响 |
| --- | --- | --- | --- | --- |
| D1 | 向量库默认 | **Milvus standalone**（满足企业栈），保留 pgvector 适配器 | pgvector 默认、Milvus 可选 | 内存 +1.8 GB；Milvus 运维复杂度 |
| D2 | RAG 推理部署 | **宿主机进程**（16 GB 最优，已验证模型可用） | 容器 profile（需 WSL ≥ 12 GB） | 启动方式、内存、可移植性 |
| D3 | Langfuse | **云端免费额度 + 完整 OTel**；自托管为可选 profile | 仅 OTel（暂不接 Langfuse） | 是否依赖外部服务、隐私 |
| D4 | 修复后端 | **Docker（Compose）默认**，k3d/K8s 可选 | 直接 k3d 默认 | 演示复杂度、真实性 |
| D5 | 主 LLM | **NVIDIA NIM `nvidia/nemotron-3.5-super-vl-120b-a12b`**（已验证 Chat/JSON/Function Calling） | Qwen/DeepSeek 作为可选切换 | 推理模型需预留 `reasoning_tokens`；Key 只放 `.env` |
| D6 | Python 运行时 | **Docker 3.12 + uv**，不改本地 3.11 | 本地安装 3.12 | 环境一致性 |
| D7 | GitHub 变更调查 | **本地 Git 默认 + 远程 PAT 可选** | 仅远程 GitHub | 离线可演示性、真实 PR 数据 |
| D8 | 首个闭环场景 | **数据库连接池耗尽**（信号最完整） | 上游超时 / 坏发布 | 演示效果与开发顺序 |
| D9 | Tempo MCP | **新增第 6 个 MCP Server** | 合并进可观测性 Server | 满足 Trace 调查，增加一个容器 |
| D10 | 认证实现 | **自研轻量 JWT + RBAC** | fastapi-users | 可控性 vs 开发量 |

> 若你未特别指定，我将按"推荐"列执行。

---

## 4. 风险登记

| # | 风险 | 概率 | 影响 | 缓解 | 触发信号 |
| --- | --- | --- | --- | --- | --- |
| R1 | 16 GB 内存不足，WSL OOM | 高 | 高 | profiles、宿主机推理、`.wslconfig` 10 GB、关闭 Langfuse 自托管 | 容器被 OOM kill、Docker 卡顿 |
| R2 | Docker Desktop/WSL 环境问题 | 中 | 高 | 启动检查脚本、文档、回退到 Linux 服务器 | daemon 连不上、端口不通 |
| R3 | Milvus 启动/资源复杂 | 中 | 中 | pgvector 适配器、健康检查、延迟启动 | milvus 反复重启 |
| R4 | 本地模型 CPU 延迟高 | 中 | 中 | 独立服务、批处理、缓存、可选 GPU、限制 TopK | 检索 > 3s |
| R5 | LLM 结构化输出不稳定 | 高 | 中 | Schema 校验 + 修复重试 + 规则兜底 + 评测 | JSON 解析失败率 > 5% |
| R6 | LangGraph/MCP SDK 版本变化 | 中 | 中 | 锁定版本、适配层、契约测试 | 升级后图/工具异常 |
| R7 | 告警风暴/重复 Incident | 中 | 中 | 去重聚合、限流、背压、人工合并 | Incident 数量异常 |
| R8 | Windows 路径/CRLF/挂载问题 | 中 | 中 | `.gitattributes`、容器内 Linux 路径、D 盘共享 | 脚本换行错误、挂载为空 |
| R9 | 时间窗口/时区错位 | 中 | 高 | 全 UTC、显式 start/end、测试覆盖 | 查询无数据、证据时间错 |
| R10 | 修复动作误操作 | 低 | 极高 | 白名单、审批、幂等、超时、DEMO 限制、默认关闭 | 非 demo 目标、重复执行 |
| R11 | 评测成本/耗时高 | 中 | 中 | 20 用例、夜间运行、缓存、较小模型 | 单轮 > 1 小时 |
| R12 | 范围蔓延导致闭环不完整 | 高 | 高 | 先闭环后扩展、每阶段退出标准、砍非核心页面 | TODO 增多、演示不稳定 |
| R13 | GitHub API 限流/无网络 | 中 | 低 | 本地 Git 模式、缓存、降级 | 403 rate limit |
| R14 | Prompt 注入导致错误结论 | 中 | 高 | 不可信标记、引用校验、规则优先、红队用例 | 结论引用缺失/异常动作 |
| R15 | Langfuse 自托管资源不足 | 高 | 低 | 云端优先、可选 profile | ClickHouse OOM |
| R16 | 演示环境不可复现 | 中 | 高 | 固定版本、种子、重置脚本、一键启动 | 换机器失败 |
| R17 | 模型许可/合规 | 低 | 中 | BGE 系列 MIT/Apache 许可核查，文档注明 | 商用限制 |
| R18 | 端口冲突 | 低 | 低 | 可配置端口、启动前检查 | 容器启动失败 |
| R19 | 证据/日志含敏感信息 | 中 | 高 | 脱敏、访问控制、演示数据 | 日志出现 Key |
| R20 | SSE 代理缓冲导致"卡住" | 中 | 中 | Nginx 配置、心跳、回放、E2E | 前端无实时更新 |
| R21 | 推理模型耗尽 `max_tokens` 返回空内容 | 中 | 中 | 默认 4096、检测 `finish_reason=length`、提高上限重试 1 次、空内容视为失败 | 节点返回空 content |
| R22 | API Key 已在聊天中暴露 | 已发生 | 高 | 立即轮换；只写本机 `.env`；日志脱敏；不提交 Git | Key 出现在仓库/日志/截图 |

---

## 5. 完成定义（DoD）

### 5.1 每阶段 DoD

- 代码可运行，依赖锁定；
- 迁移可升级/回滚；
- 新增 API 有 OpenAPI 与权限校验；
- 关键路径有日志、指标、错误处理；
- 单元/集成测试通过（真实结果）；
- 前端对接真实 API（若涉及）；
- 更新文档与 `.env.example`；
- 无新增未说明的 TODO；
- 输出阶段总结（实现内容、文件、启动方式、测试结果、已知问题、下一步）。

### 5.2 项目最终 DoD

- 告警 → 调查 → 证据 → 根因 → 方案 → 审批 → 执行 → 验证 → 报告闭环可演示；
- 7 个故障场景可注入、可复现；
- Agent 结论 100% 引用有效证据；
- 修复动作 100% 经权限系统，HIGH 风险 100% 人工审批；
- 验证基于真实指标，数据不足不判成功；
- SSE 断线可回放；
- 审计可还原完整操作链；
- 评测报告真实（N、日期、模型、版本）；
- 一键启动文档在干净环境验证通过；
- 安全验收清单全部通过；
- README、架构图、ER 图、API 文档、演示脚本齐备。

---

## 6. 我需要你确认/提供

1. **确认架构与 D1–D10 决策**（默认按推荐执行；D5 已确定为 NVIDIA NIM）；
2. **LLM API Key**：已提供 NVIDIA Key，**建议立即轮换**，仅写入本机 `.env`；
3. **GitHub PAT（可选）**：若希望变更调查使用真实 PR/发布；否则默认本地 Git；
4. **启动 Docker Desktop**：当前 daemon 未运行；
5. **确认演示范围**：7 个场景全做，还是先做 3 个（池耗尽、上游超时、坏发布）打通闭环；
6. **是否接受宿主机运行 RAG 推理**（推荐；若必须全容器，需要把 WSL 内存调到 12 GB）。

确认后我将从 Phase 1 开始，按阶段交付，不一次性生成全部代码。
