# IncidentPilot

基于 LangGraph + MCP 的企业级 AI 智能运维与故障自愈平台。

> 当前状态：**Phase 1 — 基础设施与后端基础已完成**。核心链路（告警 Webhook → 事件聚合 → Outbox → RabbitMQ → Worker）已通过 Docker Compose 端到端验证。

## 项目目标

打通一条可复现、可审计的 AI SRE 闭环：

```
告警接入 → 事件归一化 → 故障关联 → Agent 调查 → 多源证据分析
→ 根因判断 → 修复方案 → 人工审批 → 安全执行 → 恢复验证 → 故障报告
```

核心原则：**AI 负责分析与决策建议，确定性程序负责权限校验与执行，高风险操作必须人工审批。**

## 文档索引

| 文档 | 内容 |
| --- | --- |
| [PLAN.md](PLAN.md) | **实施总纲：当前进度、剩余任务、启动命令、已知问题** |
| [docs/00-prd.md](docs/00-prd.md) | 产品需求、用户旅程、功能与非功能需求、验收标准 |
| [docs/01-architecture.md](docs/01-architecture.md) | 系统架构、技术选型、模块划分、目录结构、部署拓扑 |
| [docs/02-data-model.md](docs/02-data-model.md) | ER 图、核心表设计、索引、状态机、告警去重聚合 |
| [docs/03-agent-workflow.md](docs/03-agent-workflow.md) | LangGraph 状态、节点、路由、证据模型、Checkpoint/审批/恢复 |
| [docs/04-mcp-tools.md](docs/04-mcp-tools.md) | MCP Server 架构、工具目录、权限、超时与错误契约 |
| [docs/05-api-spec.md](docs/05-api-spec.md) | REST API、SSE 协议、Webhook、权限矩阵 |
| [docs/06-frontend-design.md](docs/06-frontend-design.md) | 页面规划、Incident Detail 设计、交互与状态管理 |
| [docs/07-infrastructure.md](docs/07-infrastructure.md) | Docker Compose、可观测性、故障注入、本地模型、资源预算 |
| [docs/08-security-testing.md](docs/08-security-testing.md) | 安全设计、风险策略、测试策略、评测指标 |
| [docs/09-roadmap-risks.md](docs/09-roadmap-risks.md) | 分阶段任务清单、风险登记、待确认决策 |

## 已验证的开发环境

| 项目 | 实测结果 |
| --- | --- |
| OS | Windows (win32)，项目位于 `D:\实习项目\IncidentPilot` |
| CPU / RAM | AMD Ryzen 7 6800H / 16 GB |
| GPU | RTX 3060 Laptop 4 GB（当前 PyTorch 为 CPU 版，默认 CPU 推理） |
| Python | 本地 3.11.9；项目统一使用 3.12（Docker 镜像 / uv 安装） |
| Node | v24.11.1，npm 11.6.2 |
| Docker | 29.6.2，Compose v5.3.1（已验证启动 core profile） |
| Git | 2.50.1，仓库已初始化（main 分支，尚未提交） |
| 磁盘 | D: 剩余约 72 GB，C: 剩余约 33 GB |
| 本地模型 | `D:\mode\bge-m3-safetensors`（1024 维，加载 2.3s）、`D:\mode\bge-reranker-v2-m3`（打分验证通过） |
| LLM | NVIDIA NIM `https://integrate.api.nvidia.com/v1`，`nvidia/nemotron-3.5-super-vl-120b-a12b`；Chat / JSON 模式 / Function Calling 已验证 |

## Phase 1 已实现

- FastAPI + SQLAlchemy 2.0 async + Alembic 初始迁移（users / services / alerts / incidents / agent_runs / audit / outbox）。
- JWT access/refresh token 轮换、Argon2 密码哈希、VIEWER/SRE/ADMIN RBAC、登录限流、审计日志。
- Alertmanager Webhook：Token 校验、指纹去重、按 `service:alertname` 聚合、Incident 创建、时间线、Outbox 事件。
- RabbitMQ topic exchange + 持久化队列 + DLQ；Outbox 投递器；Worker 消费 `incident.created` 并将事件推进到 `INVESTIGATING`。
- Docker Compose core：postgres、redis、rabbitmq、backend、worker、scheduler、nginx。
- 单元测试 9 项 + PostgreSQL 集成测试 1 项，ruff/mypy 全绿。

## 快速启动

```powershell
Copy-Item .env.example .env
# 可选：编辑 .env 填入 LLM_API_KEY
docker compose up -d --build
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.cli seed
```

- API / Swagger：<http://localhost:8080/docs>
- 默认账号：`admin@incidentpilot.io` / `ChangeMe123456!`
- 健康检查：`http://localhost:8080/api/v1/health/ready`

```powershell
# 发送测试告警
$body = @{
  version='4'; groupKey='g'; status='firing'; receiver='incidentpilot'
  commonLabels=@{alertname='DbPoolExhausted'; severity='critical'; service='checkout-service'}
  alerts=@(@{
    status='firing'
    labels=@{alertname='DbPoolExhausted'; severity='critical'; service='checkout-service'}
    annotations=@{summary='Checkout DB pool exhausted'}
    startsAt='2026-11-10T05:00:00Z'; fingerprint='demo-fp-1'
  })
} | ConvertTo-Json -Depth 6
Invoke-RestMethod -Method Post -Uri http://localhost:8080/api/v1/webhooks/alertmanager `
  -Headers @{'X-Webhook-Token'='dev-webhook-token'} -ContentType 'application/json' -Body $body
```

## 下一步

进入 Phase 2：演示微服务、Prometheus/Alertmanager/Loki/Tempo 可观测性栈与故障注入。
